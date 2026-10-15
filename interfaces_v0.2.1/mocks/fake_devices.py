"""Hardware-free mocks for cross-team contract testing, not a physical simulator.

The motion adapter still exposes ``tick()`` for deterministic compatibility,
but production-style tests should call ``MotionWatchdog.check()`` separately.
The real implementation also needs a lower-level firmware failsafe verified on
the actual robot.
"""
from __future__ import annotations
from dataclasses import replace
from math import isfinite
from threading import Event, RLock, Thread
from time import monotonic_ns
from rescue_contracts import (
    ActionAck, ActionResult, ActionState, ArmAction, ArmActionRequest,
    CommandAck, CommandSource, ControlMode, DriveCommand, ErrorCode,
    ImageFrame, LineDetection, MotionMeasuredState, MotionStatus, TargetType,
    VisionResult, VisionStatus,
)


def _finite_norm(v: object) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and isfinite(v) and -1.0 <= v <= 1.0


class FakeClock:
    def __init__(self, initial_ms: int = 0) -> None:
        if not isinstance(initial_ms, int) or isinstance(initial_ms, bool):
            raise ValueError('initial_ms must be an integer')
        self.now_ms = initial_ms

    def advance(self, ms: int) -> None:
        if not isinstance(ms, int) or isinstance(ms, bool) or ms < 0:
            raise ValueError('advance must be nonnegative integer milliseconds')
        self.now_ms += ms


class ControlGate:
    """Mock control owner, used in tests; real mode switch must check contest conditions."""
    def __init__(self, mode: ControlMode = ControlMode.SAFE) -> None:
        if not isinstance(mode, ControlMode):
            raise ValueError('mode must be a ControlMode')
        self._mode = mode
        self.motion_active = False
        self.arm_busy = False
        self._safety_latched = False
        self._mode_requests: dict[str, tuple[tuple[object, ...], CommandAck]] = {}
        self._lock = RLock()

    @property
    def mode(self) -> ControlMode:
        with self._lock:
            return self._mode

    @property
    def safety_latched(self) -> bool:
        with self._lock:
            return self._safety_latched

    def latch_safety(self) -> None:
        """Enter SAFE and require an explicit recovery acknowledgement."""
        with self._lock:
            self._mode = ControlMode.SAFE
            self._safety_latched = True

    def request_mode(self, request_id: str, target: ControlMode,
                     *, mission_complete: bool = False,
                     safety_ack: bool = False,
                     timestamp_ms: int | None = None) -> CommandAck:
        """Perform a guarded mode transition and return a standard CommandAck.

        AUTO and REMOTE may only be entered from SAFE. REMOTE additionally
        requires the coordinator to assert that the autonomous mission is
        complete. A watchdog fault keeps the gate latched until a separate
        safety acknowledgement is supplied.
        """
        if (not isinstance(mission_complete, bool)
                or not isinstance(safety_ack, bool)
                or (timestamp_ms is not None
                    and (not isinstance(timestamp_ms, int)
                         or isinstance(timestamp_ms, bool)))):
            now = monotonic_ns() // 1_000_000
            return CommandAck(request_id, False, now, ErrorCode.INVALID_ARGUMENT)
        now = (monotonic_ns() // 1_000_000 if timestamp_ms is None else timestamp_ms)
        if not isinstance(request_id, str) or not request_id.strip():
            return CommandAck(request_id, False, now, ErrorCode.INVALID_ARGUMENT)
        if not isinstance(target, ControlMode):
            return CommandAck(request_id, False, now, ErrorCode.INVALID_ARGUMENT)
        payload = (target, mission_complete, safety_ack)
        with self._lock:
            cached = self._mode_requests.get(request_id)
            if cached is not None:
                old_payload, old_ack = cached
                return old_ack if old_payload == payload else CommandAck(
                    request_id, False, now, ErrorCode.CONFLICT,
                    'mode request_id was already used for another transition')

            def finish(ack: CommandAck) -> CommandAck:
                self._mode_requests[request_id] = (payload, ack)
                return ack

            current = self._mode
            if target == ControlMode.SAFE:
                self._mode = ControlMode.SAFE
                if safety_ack:
                    self._safety_latched = False
                return finish(CommandAck(request_id, True, now,
                                         message='control mode set to SAFE'))
            if self._safety_latched:
                return finish(CommandAck(request_id, False, now, ErrorCode.SAFETY_STOP,
                                         'watchdog recovery acknowledgement required'))
            if target == current:
                return finish(CommandAck(request_id, True, now,
                                         message=f'control mode already {target.value}'))
            if current != ControlMode.SAFE:
                return finish(CommandAck(request_id, False, now, ErrorCode.MODE_DENIED,
                                         'AUTO and REMOTE require a SAFE hand-off'))
            if not safety_ack:
                return finish(CommandAck(request_id, False, now, ErrorCode.MODE_DENIED,
                                         'explicit safety acknowledgement required'))
            if target == ControlMode.REMOTE and not mission_complete:
                return finish(CommandAck(request_id, False, now, ErrorCode.MODE_DENIED,
                                         'REMOTE requires completed autonomous mission'))
            self._mode = target
            return finish(CommandAck(request_id, True, now,
                                     message=f'control mode set to {target.value}'))

    def allows(self, source: CommandSource) -> bool:
        with self._lock:
            return ((self._mode == ControlMode.AUTO and source == CommandSource.AUTO)
                    or (self._mode == ControlMode.REMOTE and source == CommandSource.REMOTE))


class MockVision:
    def __init__(self, clock: FakeClock, max_frame_age_ms: int = 200) -> None:
        if (not isinstance(max_frame_age_ms, int)
                or isinstance(max_frame_age_ms, bool) or max_frame_age_ms < 0):
            raise ValueError('max_frame_age_ms must be a nonnegative integer')
        self.clock = clock
        self.max_frame_age_ms = max_frame_age_ms
        self.script: dict[int, VisionResult] = {}

    def observe(self, frame: ImageFrame, interests: set[TargetType]) -> VisionResult:
        if (not isinstance(interests, (set, frozenset))
                or not all(isinstance(item, TargetType) for item in interests)):
            frame_id = getattr(frame, 'frame_id', -1)
            timestamp_ms = getattr(frame, 'timestamp_ms', -1)
            return VisionResult(frame_id, timestamp_ms, VisionStatus.INVALID_FRAME,
                                error_code=ErrorCode.INVALID_ARGUMENT,
                                message='interests must contain only TargetType values')
        if not isinstance(frame, ImageFrame):
            return VisionResult(getattr(frame, 'frame_id', -1),
                                getattr(frame, 'timestamp_ms', -1),
                                VisionStatus.INVALID_FRAME,
                                error_code=ErrorCode.INVALID_ARGUMENT)
        if (frame.bgr is None
                or not isinstance(frame.width, int) or isinstance(frame.width, bool)
                or not isinstance(frame.height, int) or isinstance(frame.height, bool)
                or frame.width <= 0 or frame.height <= 0
                or isinstance(frame.frame_id, bool) or frame.frame_id < 0
                or isinstance(frame.timestamp_ms, bool)
                or not isinstance(frame.frame_id, int)
                or not isinstance(frame.timestamp_ms, int)):
            return VisionResult(frame.frame_id, frame.timestamp_ms, VisionStatus.INVALID_FRAME,
                                error_code=ErrorCode.INVALID_ARGUMENT)
        age = self.clock.now_ms - frame.timestamp_ms
        if age < 0 or age > self.max_frame_age_ms:
            return VisionResult(frame.frame_id, frame.timestamp_ms, VisionStatus.STALE_FRAME,
                                error_code=ErrorCode.STALE_DATA)
        scripted = self.script.get(frame.frame_id)
        if scripted is None:
            return VisionResult(frame.frame_id, frame.timestamp_ms, VisionStatus.OK,
                                line=LineDetection(False, None, 0.0) if TargetType.LINE in interests else None)
        return replace(scripted,
                       frame_id=frame.frame_id,
                       timestamp_ms=frame.timestamp_ms,
                       line=scripted.line if TargetType.LINE in interests else None,
                       objects=[v for v in scripted.objects if v.kind in interests])


class MockBuzzer:
    """Idempotent auxiliary buzzer service used by the FSM Mock flow."""

    def __init__(self, clock) -> None:
        self.clock = clock
        self.events: list[tuple[str, int]] = []
        self._cache: dict[str, CommandAck] = {}

    def beep(self, request_id: str, duration_ms: int) -> CommandAck:
        valid_request_id = isinstance(request_id, str) and bool(request_id.strip())
        cached = self._cache.get(request_id) if valid_request_id else None
        if cached is not None:
            return cached
        if not valid_request_id:
            ack = CommandAck(request_id, False, self.clock.now_ms,
                             ErrorCode.INVALID_ARGUMENT)
        elif (not isinstance(duration_ms, int) or isinstance(duration_ms, bool)
              or not 1 <= duration_ms <= 2000):
            ack = CommandAck(request_id, False, self.clock.now_ms,
                             ErrorCode.INVALID_ARGUMENT)
        else:
            self.events.append((request_id, duration_ms))
            ack = CommandAck(request_id, True, self.clock.now_ms)
        if valid_request_id:
            self._cache[request_id] = ack
        return ack


class MockMotion:
    def __init__(self, clock: FakeClock, gate: ControlGate,
                 supports_combined: bool = False) -> None:
        if not isinstance(supports_combined, bool):
            raise ValueError('supports_combined must be a boolean')
        self.clock = clock
        self.gate = gate
        self.supports_combined = supports_combined
        self.commanded: DriveCommand | None = None
        self.last_command_ms: int | None = None
        self.expires_at_ms: int | None = None
        self.watchdog_expired = False
        self.error_code: ErrorCode | None = None
        self._cached: dict[str, tuple[object, CommandAck]] = {}
        self._lock = RLock()

    def _ack(self, request_id: str, accepted: bool,
             code: ErrorCode | None = None, message: str = '') -> CommandAck:
        return CommandAck(request_id, accepted, self.clock.now_ms, code, message)

    def _expire_if_needed(self) -> None:
        if self.expires_at_ms is not None and self.clock.now_ms >= self.expires_at_ms:
            self.commanded = None
            self.expires_at_ms = None
            self.gate.motion_active = False
            self.watchdog_expired = True  # simulated commanded-stop, not physical feedback
            self.error_code = ErrorCode.SAFETY_STOP
            self.gate.latch_safety()  # inhibit further non-safety actions until recovery

    def tick(self) -> None:
        with self._lock:
            self._expire_if_needed()

    def watchdog_check(self) -> None:
        """Run only the expiry check; intended for an independent monitor."""
        self.tick()

    def drive(self, command: DriveCommand) -> CommandAck:
        with self._lock:
            return self._drive_unlocked(command)

    def _drive_unlocked(self, command: DriveCommand) -> CommandAck:
        if not isinstance(command, DriveCommand):
            request_id = getattr(command, 'request_id', '')
            return self._ack(request_id, False, ErrorCode.INVALID_ARGUMENT)
        self._expire_if_needed()
        valid_request_id = (isinstance(command.request_id, str)
                            and bool(command.request_id.strip()))
        cached = self._cached.get(command.request_id) if valid_request_id else None
        if cached is not None:
            old_payload, old_ack = cached
            return old_ack if old_payload == command else self._ack(command.request_id, False, ErrorCode.CONFLICT)
        if not valid_request_id:
            ack = self._ack(command.request_id, False, ErrorCode.INVALID_ARGUMENT)
        elif (not isinstance(command.timestamp_ms, int)
              or isinstance(command.timestamp_ms, bool)
              or not all(_finite_norm(v) for v in (command.x_norm, command.y_norm, command.yaw_norm))
              or not isinstance(command.ttl_ms, int) or isinstance(command.ttl_ms, bool)
              or not (100 <= command.ttl_ms <= 2000)):
            ack = self._ack(command.request_id, False, ErrorCode.INVALID_ARGUMENT)
        elif (command.timestamp_ms > self.clock.now_ms
              or self.clock.now_ms - command.timestamp_ms >= command.ttl_ms):
            ack = self._ack(command.request_id, False, ErrorCode.STALE_DATA)
        elif not isinstance(command.source, CommandSource):
            ack = self._ack(command.request_id, False, ErrorCode.INVALID_ARGUMENT)
        elif not self.gate.allows(command.source):
            ack = self._ack(command.request_id, False, ErrorCode.MODE_DENIED)
        elif self.gate.arm_busy:
            ack = self._ack(command.request_id, False, ErrorCode.BUSY)
        elif not self.supports_combined and sum(abs(v) > 1e-9 for v in
                                                (command.x_norm, command.y_norm, command.yaw_norm)) > 1:
            ack = self._ack(command.request_id, False, ErrorCode.UNSUPPORTED)
        else:
            self.commanded = command
            self.last_command_ms = self.clock.now_ms
            self.expires_at_ms = self.clock.now_ms + command.ttl_ms
            self.watchdog_expired = False
            self.error_code = None
            self.gate.motion_active = any(abs(v) > 1e-9 for v in
                                          (command.x_norm, command.y_norm, command.yaw_norm))
            ack = self._ack(command.request_id, True)
        if isinstance(command.request_id, str) and command.request_id.strip():
            self._cached[command.request_id] = (command, ack)
        return ack

    def stop(self, request_id: str) -> CommandAck:
        with self._lock:
            return self._stop_unlocked(request_id)

    def _stop_unlocked(self, request_id: str) -> CommandAck:
        self._expire_if_needed()
        valid_request_id = isinstance(request_id, str) and bool(request_id.strip())
        cached = self._cached.get(request_id) if valid_request_id else None
        if cached is not None:
            old_payload, old_ack = cached
            return old_ack if old_payload == 'STOP' else self._ack(request_id, False, ErrorCode.CONFLICT)
        if not valid_request_id:
            return self._ack(request_id, False, ErrorCode.INVALID_ARGUMENT)
        self.commanded = None
        self.expires_at_ms = None
        self.gate.motion_active = False
        if not self.gate.safety_latched:
            self.watchdog_expired = False
            self.error_code = None
        ack = self._ack(request_id, True, message='stop requested; physical standstill unverified')
        self._cached[request_id] = ('STOP', ack)
        return ack

    def get_motion_status(self) -> MotionStatus:
        with self._lock:
            return self._get_motion_status_unlocked()

    def _get_motion_status_unlocked(self) -> MotionStatus:
        self._expire_if_needed()
        return MotionStatus(self.clock.now_ms, self.commanded, MotionMeasuredState.UNKNOWN,
                            self.last_command_ms, self.watchdog_expired, self.error_code)


class MotionWatchdog:
    """Independent motion-expiry monitor for the MockMotion adapter.

    ``check()`` is deterministic and is used by tests/coordinators. ``start()``
    provides the same check on a daemon thread for an integration-style run;
    the mock clock remains injectable, so no wall-clock behaviour is hidden.
    """
    def __init__(self, motion: MockMotion, period_ms: int = 50) -> None:
        if not isinstance(period_ms, int) or isinstance(period_ms, bool) or period_ms <= 0:
            raise ValueError('period_ms must be a positive integer')
        self.motion = motion
        self.period_ms = period_ms
        self._stop_event = Event()
        self._thread: Thread | None = None

    def check(self) -> None:
        self.motion.watchdog_check()

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = Thread(target=self._run, name='motion-watchdog', daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=max(0.1, self.period_ms / 1000 * 2))
        self._thread = None

    def _run(self) -> None:
        while not self._stop_event.wait(self.period_ms / 1000):
            self.check()


class MockArm:
    def __init__(self, clock: FakeClock, gate: ControlGate,
                 simulated_duration_ms: int = 300, supports_cancel: bool = True) -> None:
        if (not isinstance(simulated_duration_ms, int)
                or isinstance(simulated_duration_ms, bool)
                or simulated_duration_ms < 0):
            raise ValueError('simulated_duration_ms must be a nonnegative integer')
        if not isinstance(supports_cancel, bool):
            raise ValueError('supports_cancel must be a boolean')
        self.clock = clock
        self.gate = gate
        self.simulated_duration_ms = simulated_duration_ms
        self.supports_cancel = supports_cancel
        self._requests: dict[str, tuple[ArmActionRequest, ActionAck]] = {}
        self._results: dict[str, ActionResult] = {}
        self._cancel_cache: dict[str, tuple[str, CommandAck]] = {}
        self._sequence = 0
        self._active_id: str | None = None
        self.start_count = 0
        self._lock = RLock()

    def _reject(self, req: ArmActionRequest, code: ErrorCode) -> ActionAck:
        return ActionAck(req.request_id, False, self.clock.now_ms, error_code=code)

    def start_action(self, request: ArmActionRequest) -> ActionAck:
        with self._lock:
            return self._start_action_unlocked(request)

    def _start_action_unlocked(self, request: ArmActionRequest) -> ActionAck:
        if not isinstance(request, ArmActionRequest):
            request_id = getattr(request, 'request_id', '')
            return ActionAck(request_id, False, self.clock.now_ms,
                             error_code=ErrorCode.INVALID_ARGUMENT)
        self._tick_unlocked()
        valid_request_id = (isinstance(request.request_id, str)
                            and bool(request.request_id.strip()))
        cached = self._requests.get(request.request_id) if valid_request_id else None
        if cached is not None:
            original, ack = cached
            return ack if original == request else self._reject(request, ErrorCode.CONFLICT)
        if not valid_request_id:
            ack = self._reject(request, ErrorCode.INVALID_ARGUMENT)
        elif not isinstance(request.action, ArmAction) or (not isinstance(request.timeout_ms, int)
             or isinstance(request.timeout_ms, bool) or not 100 <= request.timeout_ms <= 30000):
            ack = self._reject(request, ErrorCode.INVALID_ARGUMENT)
        elif (not isinstance(request.timestamp_ms, int)
              or isinstance(request.timestamp_ms, bool)):
            ack = self._reject(request, ErrorCode.INVALID_ARGUMENT)
        elif (request.timestamp_ms > self.clock.now_ms
              or self.clock.now_ms - request.timestamp_ms >= request.timeout_ms):
            ack = self._reject(request, ErrorCode.STALE_DATA)
        elif not isinstance(request.source, CommandSource):
            ack = self._reject(request, ErrorCode.INVALID_ARGUMENT)
        elif not self.gate.allows(request.source):
            ack = self._reject(request, ErrorCode.MODE_DENIED)
        elif self._active_id is not None or self.gate.arm_busy or self.gate.motion_active:
            ack = self._reject(request, ErrorCode.BUSY)
        else:
            self._sequence += 1
            action_id = f'arm-{self._sequence:04d}'
            result = ActionResult(action_id, ActionState.ACCEPTED, self.clock.now_ms,
                                  started_ms=self.clock.now_ms)
            self._results[action_id] = result
            self._active_id = action_id
            self.gate.arm_busy = True
            self.start_count += 1
            ack = ActionAck(request.request_id, True, self.clock.now_ms, action_id=action_id)
        if isinstance(request.request_id, str) and request.request_id.strip():
            self._requests[request.request_id] = (request, ack)
        return ack

    def tick(self) -> None:
        with self._lock:
            self._tick_unlocked()

    def _tick_unlocked(self) -> None:
        if self._active_id is None:
            return
        result = self._results[self._active_id]
        elapsed = self.clock.now_ms - (result.started_ms or 0)
        if elapsed >= self._get_timeout_ms(self._active_id):
            next_state = ActionState.TIMEOUT
            code = ErrorCode.TIMEOUT
        elif elapsed >= self.simulated_duration_ms:
            next_state = ActionState.DONE_UNVERIFIED
            code = None
        else:
            self._results[self._active_id] = replace(result, state=ActionState.RUNNING,
                                                      timestamp_ms=self.clock.now_ms)
            return
        self._results[self._active_id] = replace(result, state=next_state,
                                                timestamp_ms=self.clock.now_ms,
                                                finished_ms=self.clock.now_ms,
                                                error_code=code)
        self._active_id = None
        # An unverified timeout must NOT permit motion while servos could still be moving.
        # Recovery requires an explicit, out-of-band safety check by the coordinator.
        self.gate.arm_busy = (next_state == ActionState.TIMEOUT)

    def release_after_safety_check(self) -> None:
        """TEST HARNESS ONLY: imitate explicit safe recovery after a real halt check."""
        with self._lock:
            if self._active_id is not None:
                raise RuntimeError("cannot release an active arm action")
            self.gate.arm_busy = False

    def _get_timeout_ms(self, action_id: str) -> int:
        for request, ack in self._requests.values():
            if ack.action_id == action_id:
                return request.timeout_ms
        # start_action inserts cache after _active_id, so tick is not called before then.
        return 30000

    def get_status(self, action_id: str) -> ActionResult:
        with self._lock:
            return self._get_status_unlocked(action_id)

    def _get_status_unlocked(self, action_id: str) -> ActionResult:
        if not isinstance(action_id, str) or not action_id.strip():
            return ActionResult(action_id, ActionState.FAILED, self.clock.now_ms,
                                error_code=ErrorCode.INVALID_ARGUMENT,
                                message='action_id must be a non-empty string')
        self._tick_unlocked()
        return self._results.get(action_id) or ActionResult(
            action_id, ActionState.FAILED, self.clock.now_ms,
            error_code=ErrorCode.NOT_FOUND, message='unknown action_id')

    def cancel_action(self, action_id: str, request_id: str) -> CommandAck:
        with self._lock:
            return self._cancel_action_unlocked(action_id, request_id)

    def _cancel_action_unlocked(self, action_id: str, request_id: str) -> CommandAck:
        if not isinstance(action_id, str) or not action_id.strip():
            return CommandAck(request_id, False, self.clock.now_ms,
                              ErrorCode.INVALID_ARGUMENT,
                              'action_id must be a non-empty string')
        self._tick_unlocked()
        valid_request_id = isinstance(request_id, str) and bool(request_id.strip())
        cached = self._cancel_cache.get(request_id) if valid_request_id else None
        if cached is not None:
            original_id, ack = cached
            return ack if original_id == action_id else CommandAck(
                request_id, False, self.clock.now_ms, ErrorCode.CONFLICT)
        if not valid_request_id:
            return CommandAck(request_id, False, self.clock.now_ms, ErrorCode.INVALID_ARGUMENT)
        result = self._results.get(action_id)
        if result is None:
            ack = CommandAck(request_id, False, self.clock.now_ms, ErrorCode.NOT_FOUND)
        elif not self.supports_cancel:
            ack = CommandAck(request_id, False, self.clock.now_ms, ErrorCode.UNSUPPORTED)
        elif action_id != self._active_id:
            ack = CommandAck(request_id, True, self.clock.now_ms,
                             message='already terminal; no state change')
        else:
            self._results[action_id] = replace(result, state=ActionState.CANCELLED,
                                               timestamp_ms=self.clock.now_ms,
                                               finished_ms=self.clock.now_ms)
            self._active_id = None
            self.gate.arm_busy = False
            ack = CommandAck(request_id, True, self.clock.now_ms,
                             message='mock cancel completed; physical cancellation not guaranteed')
        self._cancel_cache[request_id] = (action_id, ack)
        return ack
