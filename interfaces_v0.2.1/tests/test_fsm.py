import unittest

from rescue_contracts import (
    ActionState, CommandSource, ControlMode, Detection, ErrorCode, ImageFrame,
    LineDetection, TargetColor, TargetType, VisionResult, VisionStatus,
)
from mocks import ControlGate, FakeClock, MockArm, MockBuzzer, MockMotion, MockVision, MotionWatchdog
from fsm import AutonomousFSM, FSMConfig, MissionState


class FSMTests(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock(1000)
        self.gate = ControlGate(ControlMode.AUTO)
        self.vision = MockVision(self.clock)
        self.motion = MockMotion(self.clock, self.gate, supports_combined=True)
        self.arm = MockArm(self.clock, self.gate, simulated_duration_ms=100)
        self.buzzer = MockBuzzer(self.clock)
        self.fsm = AutonomousFSM(self.vision, self.motion, self.arm, self.buzzer,
                                 self.clock, bypass_ticks=1, return_ticks=1)

    def _script(self, frame_id, line=True, objects=None):
        self.vision.script[frame_id] = VisionResult(
            frame_id, self.clock.now_ms, VisionStatus.OK,
            line=LineDetection(line, 0.0 if line else None, 0.9),
            objects=list(objects or []),
        )
        return ImageFrame('fake', frame_id, self.clock.now_ms, 640, 480)

    def _step(self, frame_id, line=True, objects=None, home_reached=False):
        frame = self._script(frame_id, line=line, objects=objects)
        return self.fsm.process_frame(frame, home_reached=home_reached)

    def test_black_sign_to_ball_cup_and_home(self):
        black = Detection(TargetType.SIGN, (320, 180), (300, 150, 40, 60),
                          2000, 0.95, True, TargetColor.BLACK, distance_mm=180)
        ball = Detection(TargetType.BALL, (320, 220), (300, 200, 40, 40),
                         1000, 0.9, True, TargetColor.RED)
        cup = Detection(TargetType.CUP, (420, 220), (400, 200, 40, 40),
                        1000, 0.9, True, TargetColor.YELLOW, cup_multiplier=3)

        self.assertEqual(self._step(1, objects=[black]).state_after,
                         MissionState.KNOCK_SIGN)
        self.assertTrue(self._step(2).arm_ack.accepted)
        self.clock.advance(50)
        self.assertEqual(self._step(3).arm_result.state, ActionState.RUNNING)
        self.clock.advance(60)
        self.assertEqual(self._step(4).state_after, MissionState.LINE_TRACKING)
        self.assertEqual(self._step(5, objects=[ball]).state_after, MissionState.PICK_BALL)
        self.assertTrue(self._step(6).arm_ack.accepted)
        self.clock.advance(110)
        self.assertEqual(self._step(7, objects=[cup]).state_after, MissionState.PLACE_CUP)
        self.assertTrue(self._step(8).arm_ack.accepted)
        self.clock.advance(110)
        self.assertEqual(self._step(9).state_after, MissionState.RETURN_HOME)
        self.assertEqual(self._step(10).state_after, MissionState.COMPLETE)
        self.assertEqual(len(self.buzzer.events), 1)

    def test_yellow_sign_bypass_branch(self):
        yellow = Detection(TargetType.SIGN, (320, 180), (300, 150, 40, 60),
                           2000, 0.95, True, TargetColor.YELLOW, distance_mm=180)
        self.assertEqual(self._step(1, objects=[yellow]).state_after,
                         MissionState.BYPASS_SIGN)
        self.assertEqual(self._step(2).state_after, MissionState.LINE_TRACKING)

    def test_fsm_config_validates_limits(self):
        with self.assertRaises(ValueError):
            FSMConfig(command_ttl_ms=50)
        with self.assertRaises(ValueError):
            FSMConfig(track_speed_norm=1.1)
        with self.assertRaises(ValueError):
            AutonomousFSM(self.vision, self.motion, self.arm, self.buzzer,
                          self.clock, config=FSMConfig(), bypass_ticks=1)
        with self.assertRaises(TypeError):
            AutonomousFSM(self.vision, self.motion, self.arm, self.buzzer,
                          self.clock, config=object())

    def test_line_search_has_a_finite_stop(self):
        self.assertEqual(self._step(1, line=False).state_after,
                         MissionState.SEARCH_LINE)
        self.assertEqual(self._step(2, line=False).state_after,
                         MissionState.SEARCH_LINE)
        self.assertEqual(self._step(3, line=False).state_after,
                         MissionState.SAFE_HOLD)

    def test_watchdog_is_independent_from_status_poll(self):
        self.assertTrue(self.motion.drive(self.motion_command()).accepted)
        self.clock.advance(400)
        watchdog = MotionWatchdog(self.motion)
        watchdog.check()
        self.assertTrue(self.motion.watchdog_expired)
        self.assertEqual(self.gate.mode, ControlMode.SAFE)
        self.assertTrue(self.gate.safety_latched)

    def test_mode_handoff_requires_safe_and_explicit_ack(self):
        self.assertFalse(self.gate.request_mode('to-remote', ControlMode.REMOTE,
                                                mission_complete=True).accepted)
        self.assertTrue(self.gate.request_mode('to-safe', ControlMode.SAFE,
                                               safety_ack=True).accepted)
        self.assertTrue(self.gate.request_mode('to-auto', ControlMode.AUTO,
                                               safety_ack=True).accepted)
        self.assertFalse(self.gate.request_mode('direct-remote', ControlMode.REMOTE,
                                                mission_complete=True,
                                                safety_ack=True).accepted)
        repeat = self.gate.request_mode('to-auto', ControlMode.AUTO,
                                        safety_ack=True)
        self.assertTrue(repeat.accepted)
        conflict = self.gate.request_mode('to-auto', ControlMode.REMOTE,
                                          mission_complete=True,
                                          safety_ack=True)
        self.assertEqual(conflict.error_code, ErrorCode.CONFLICT)

    def motion_command(self):
        from rescue_contracts import DriveCommand
        return DriveCommand('watchdog-command', self.clock.now_ms, 0.2, 0.0, 0.0,
                            400, CommandSource.AUTO)


if __name__ == '__main__':
    unittest.main()
