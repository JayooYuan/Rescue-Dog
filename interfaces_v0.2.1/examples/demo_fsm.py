"""Run the complete autonomous Mock mission without hardware.

From ``interfaces_v0.2.1``::

    python -m examples.demo_fsm
"""
from __future__ import annotations

from rescue_contracts import (
    ControlMode, Detection, ImageFrame, LineDetection, TargetColor, TargetType,
    VisionResult, VisionStatus,
)
from fsm import AutonomousFSM
from mocks import ControlGate, FakeClock, MockArm, MockBuzzer, MockMotion, MockVision


def main() -> None:
    clock = FakeClock(1000)
    gate = ControlGate(ControlMode.AUTO)
    vision = MockVision(clock)
    motion = MockMotion(clock, gate, supports_combined=True)
    arm = MockArm(clock, gate, simulated_duration_ms=100)
    buzzer = MockBuzzer(clock)
    fsm = AutonomousFSM(vision, motion, arm, buzzer, clock,
                        bypass_ticks=1, return_ticks=1)

    black = Detection(TargetType.SIGN, (320, 180), (300, 150, 40, 60),
                      2000, 0.95, True, TargetColor.BLACK, distance_mm=180)
    ball = Detection(TargetType.BALL, (320, 220), (300, 200, 40, 40),
                     1000, 0.90, True, TargetColor.RED)
    cup = Detection(TargetType.CUP, (420, 220), (400, 200, 40, 40),
                    1000, 0.90, True, TargetColor.YELLOW, cup_multiplier=3)
    script = {
        1: [black],
        5: [ball],
        7: [cup],
    }

    for frame_id in range(1, 14):
        objects = script.get(frame_id, [])
        vision.script[frame_id] = VisionResult(
            frame_id, clock.now_ms, VisionStatus.OK,
            line=LineDetection(True, 0.0, 0.9), objects=objects,
        )
        frame = ImageFrame('mock-frame', frame_id, clock.now_ms, 640, 480)
        event = fsm.process_frame(frame)
        details = event.message
        if event.arm_result is not None:
            details += f' ({event.arm_result.state.value})'
        print(f'{frame_id:02d} {event.state_before.value:>14} -> '
              f'{event.state_after.value:<14} {details}')
        # A real loop would tick the independent watchdog in a separate
        # scheduler. Advancing the injected clock keeps this demo deterministic.
        clock.advance(110 if event.arm_result is not None else 10)

    print('Final state:', fsm.state.value)
    print('Buzzer events:', buzzer.events)
    print('Physical manipulation:', 'unverified (by contract)')


if __name__ == '__main__':
    main()
