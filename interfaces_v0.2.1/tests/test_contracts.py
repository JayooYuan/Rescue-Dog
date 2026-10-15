import unittest
from rescue_contracts import (
    ActionState, ArmAction, ArmActionRequest, CommandSource, ControlMode,
    Detection, DriveCommand, ErrorCode, ImageFrame, LineDetection,
    TargetColor, TargetType, VisionResult, VisionStatus,
)
from mocks import FakeClock, ControlGate, MockVision, MockMotion, MockArm


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock(1000)
        self.gate = ControlGate(ControlMode.AUTO)
        self.vision = MockVision(self.clock)
        self.motion = MockMotion(self.clock, self.gate)
        self.arm = MockArm(self.clock, self.gate)

    def frame(self, frame_id=1, timestamp_ms=1000, bgr='fake-frame'):
        return ImageFrame(bgr, frame_id, timestamp_ms, 640, 480)

    def drive(self, request_id='move-1', x=0.3, y=0.0, yaw=0.0,
              source=CommandSource.AUTO, ttl_ms=400, timestamp_ms=None):
        return DriveCommand(request_id, self.clock.now_ms if timestamp_ms is None else timestamp_ms,
                            x, y, yaw, ttl_ms, source)

    def arm_request(self, request_id='arm-request-1', timeout_ms=1000,
                    source=CommandSource.AUTO):
        return ArmActionRequest(request_id, self.clock.now_ms, ArmAction.PICK_BALL,
                                None, timeout_ms, source)

    def test_vision_no_target_is_not_error(self):
        result = self.vision.observe(self.frame(), {TargetType.LINE, TargetType.SIGN})
        self.assertEqual(result.status, VisionStatus.OK)
        self.assertEqual(result.objects, [])
        self.assertIsNotNone(result.line)
        self.assertFalse(result.line.found)
        self.assertIsNone(result.line.error_px)

    def test_vision_line_sign_and_filtering(self):
        sign = Detection(TargetType.SIGN, (320.0, 200.0), (300, 170, 40, 60),
                         1000.0, 0.95, True, TargetColor.BLACK)
        self.vision.script[1] = VisionResult(1, 1000, VisionStatus.OK,
                                             LineDetection(True, -50.0, 0.8), [sign])
        result = self.vision.observe(self.frame(), {TargetType.LINE, TargetType.SIGN})
        self.assertLess(result.line.error_px, 0)
        self.assertEqual(result.objects[0].color, TargetColor.BLACK)
        filtered = self.vision.observe(self.frame(), {TargetType.BALL})
        self.assertIsNone(filtered.line)
        self.assertEqual(filtered.objects, [])

    def test_vision_rejects_stale_and_invalid(self):
        self.assertEqual(self.vision.observe(self.frame(timestamp_ms=700),
                                            {TargetType.SIGN}).status, VisionStatus.STALE_FRAME)
        self.assertEqual(self.vision.observe(self.frame(bgr=None),
                                            {TargetType.SIGN}).status, VisionStatus.INVALID_FRAME)
        self.assertEqual(self.vision.observe(self.frame(), ['SIGN']).error_code,
                         ErrorCode.INVALID_ARGUMENT)
        self.assertEqual(self.vision.observe(
            ImageFrame('fake', 2, 1000, '640', 480), {TargetType.SIGN}).error_code,
            ErrorCode.INVALID_ARGUMENT)

    def test_motion_accept_and_no_physical_claim(self):
        ack = self.motion.drive(self.drive())
        self.assertTrue(ack.accepted)
        self.assertEqual(self.motion.get_motion_status().measured_state.value, 'UNKNOWN')
        self.assertTrue(self.gate.motion_active)

    def test_motion_invalid_normalized_value(self):
        for bad in (1.01, -1.01, float('nan'), float('inf')):
            ack = self.motion.drive(self.drive(request_id=f'bad-{bad}', x=bad))
            self.assertFalse(ack.accepted)
            self.assertEqual(ack.error_code, ErrorCode.INVALID_ARGUMENT)

    def test_motion_rejects_wrong_mode(self):
        self.assertTrue(self.gate.request_mode('mode-safe', ControlMode.SAFE).accepted)
        self.assertTrue(self.gate.request_mode(
            'mode-remote', ControlMode.REMOTE, mission_complete=True,
            safety_ack=True).accepted)
        ack = self.motion.drive(self.drive())
        self.assertEqual(ack.error_code, ErrorCode.MODE_DENIED)

    def test_motion_rejects_stale_command(self):
        ack = self.motion.drive(self.drive(timestamp_ms=200))
        self.assertEqual(ack.error_code, ErrorCode.STALE_DATA)

    def test_motion_rejects_combined_axes_unless_supported(self):
        ack = self.motion.drive(self.drive(y=0.2))
        self.assertEqual(ack.error_code, ErrorCode.UNSUPPORTED)

    def test_motion_watchdog_expires(self):
        self.assertTrue(self.motion.drive(self.drive()).accepted)
        self.clock.advance(400)
        status = self.motion.get_motion_status()
        self.assertTrue(status.watchdog_expired)
        self.assertIsNone(status.commanded)
        self.assertFalse(self.gate.motion_active)
        self.assertEqual(self.gate.mode, ControlMode.SAFE)
        self.assertEqual(status.measured_state.value, 'UNKNOWN')
        self.assertEqual(status.error_code, ErrorCode.SAFETY_STOP)

    def test_stop_does_not_clear_watchdog_fault_latch(self):
        self.assertTrue(self.motion.drive(self.drive()).accepted)
        self.clock.advance(400)
        self.motion.get_motion_status()
        self.assertTrue(self.motion.stop('stop-after-watchdog').accepted)
        self.assertTrue(self.motion.get_motion_status().watchdog_expired)
        self.assertTrue(self.gate.safety_latched)

    def test_repeated_motion_command_does_not_refresh_ttl(self):
        cmd = self.drive()
        self.motion.drive(cmd)
        self.clock.advance(350)
        self.assertTrue(self.motion.drive(cmd).accepted)
        self.clock.advance(50)
        self.assertTrue(self.motion.get_motion_status().watchdog_expired)

    def test_same_request_id_different_payload_is_conflict(self):
        self.motion.drive(self.drive())
        ack = self.motion.drive(self.drive(x=0.7))
        self.assertFalse(ack.accepted)
        self.assertEqual(ack.error_code, ErrorCode.CONFLICT)

    def test_stop_allowed_in_safe_mode(self):
        self.assertTrue(self.gate.request_mode('mode-safe-stop', ControlMode.SAFE).accepted)
        ack = self.motion.stop('stop-safe')
        self.assertTrue(ack.accepted)
        self.assertEqual(self.motion.get_motion_status().measured_state.value, 'UNKNOWN')

    def test_arm_and_motion_mutual_exclusion(self):
        self.motion.drive(self.drive())
        self.assertEqual(self.arm.start_action(self.arm_request()).error_code, ErrorCode.BUSY)
        self.motion.stop('stop-1')
        self.assertTrue(self.arm.start_action(self.arm_request('arm-request-2')).accepted)
        self.assertEqual(self.motion.drive(self.drive('move-2')).error_code, ErrorCode.BUSY)

    def test_arm_action_lifecycle(self):
        ack = self.arm.start_action(self.arm_request())
        self.assertTrue(ack.accepted)
        self.assertEqual(self.arm.get_status(ack.action_id).state, ActionState.RUNNING)
        self.clock.advance(301)
        self.assertEqual(self.arm.get_status(ack.action_id).state, ActionState.DONE_UNVERIFIED)
        self.assertFalse(self.gate.arm_busy)

    def test_arm_timeout(self):
        ack = self.arm.start_action(self.arm_request(timeout_ms=100))
        self.clock.advance(101)
        result = self.arm.get_status(ack.action_id)
        self.assertEqual(result.state, ActionState.TIMEOUT)
        self.assertEqual(result.error_code, ErrorCode.TIMEOUT)
        self.assertTrue(self.gate.arm_busy)  # fault lock persists until verified recovery
        self.assertEqual(self.motion.drive(self.drive()).error_code, ErrorCode.BUSY)
        self.arm.release_after_safety_check()  # test-only simulated safety check
        self.assertFalse(self.gate.arm_busy)

    def test_arm_idempotent_request(self):
        req = self.arm_request()
        ack1 = self.arm.start_action(req)
        ack2 = self.arm.start_action(req)
        self.assertEqual(ack1.action_id, ack2.action_id)
        self.assertEqual(self.arm.start_count, 1)
        altered = ArmActionRequest(req.request_id, req.timestamp_ms, ArmAction.HIT_SIGN,
                                   None, req.timeout_ms, req.source)
        self.assertEqual(self.arm.start_action(altered).error_code, ErrorCode.CONFLICT)

    def test_arm_cancel_is_explicit(self):
        ack = self.arm.start_action(self.arm_request())
        cancel = self.arm.cancel_action(ack.action_id, 'cancel-1')
        self.assertTrue(cancel.accepted)
        self.assertEqual(self.arm.get_status(ack.action_id).state, ActionState.CANCELLED)
        self.assertTrue(self.arm.cancel_action(ack.action_id, 'cancel-1').accepted)

    def test_cancel_unsupported_is_not_fake_success(self):
        arm = MockArm(self.clock, self.gate, supports_cancel=False)
        ack = arm.start_action(self.arm_request())
        rejected = arm.cancel_action(ack.action_id, 'cancel-2')
        self.assertEqual(rejected.error_code, ErrorCode.UNSUPPORTED)
        self.assertEqual(arm.get_status(ack.action_id).state, ActionState.RUNNING)

    def test_missing_action_id_is_not_found(self):
        result = self.arm.get_status('missing-id')
        self.assertEqual(result.error_code, ErrorCode.NOT_FOUND)

    def test_safe_mode_rejects_arm(self):
        self.assertTrue(self.gate.request_mode('mode-safe-arm', ControlMode.SAFE).accepted)
        self.assertEqual(self.arm.start_action(self.arm_request()).error_code,
                         ErrorCode.MODE_DENIED)

    def test_invalid_sources_and_malformed_requests_are_rejected(self):
        invalid_source = self.motion.drive(
            DriveCommand('bad-source', self.clock.now_ms, 0.1, 0.0, 0.0, 400, 'AUTO'))
        self.assertEqual(invalid_source.error_code, ErrorCode.INVALID_ARGUMENT)
        invalid_arm_source = self.arm.start_action(
            ArmActionRequest('bad-arm-source', self.clock.now_ms, ArmAction.PICK_BALL,
                             None, 1000, 'AUTO'))
        self.assertEqual(invalid_arm_source.error_code, ErrorCode.INVALID_ARGUMENT)
        invalid_arm_timestamp = self.arm.start_action(
            ArmActionRequest('bad-arm-time', True, ArmAction.PICK_BALL,
                             None, 1000, CommandSource.AUTO))
        self.assertEqual(invalid_arm_timestamp.error_code, ErrorCode.INVALID_ARGUMENT)
        self.assertEqual(self.motion.drive(None).error_code, ErrorCode.INVALID_ARGUMENT)
        self.assertEqual(self.arm.start_action(None).error_code, ErrorCode.INVALID_ARGUMENT)
        self.assertEqual(self.arm.get_status(None).error_code, ErrorCode.INVALID_ARGUMENT)
        self.assertEqual(self.arm.cancel_action(None, 'cancel-invalid').error_code,
                         ErrorCode.INVALID_ARGUMENT)
        self.assertEqual(self.gate.request_mode('bad-mode-flags', ControlMode.AUTO,
                                                safety_ack=1).error_code,
                         ErrorCode.INVALID_ARGUMENT)


if __name__ == '__main__':
    unittest.main()
