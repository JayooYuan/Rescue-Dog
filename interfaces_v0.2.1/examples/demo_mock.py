"""Run from ``interfaces_v0.2.1``: ``python -m examples.demo_mock``.

A demonstration of the contracts; no real robot action takes place.
"""
from rescue_contracts import (
    ActionState, ArmAction, ArmActionRequest, CommandSource, ControlMode,
    Detection, ImageFrame, TargetColor, TargetType, VisionResult, VisionStatus,
)
from mocks import ControlGate, FakeClock, MockVision, MockMotion, MockArm


def main():
    clock = FakeClock(1000)
    gate = ControlGate(ControlMode.AUTO)
    vision = MockVision(clock)
    motion = MockMotion(clock, gate)
    arm = MockArm(clock, gate)

    vision.script[1] = VisionResult(
        1, 1000, VisionStatus.OK,
        objects=[Detection(TargetType.SIGN, (320.0, 180.0), (295, 155, 50, 50),
                           1950.0, 0.94, True, TargetColor.BLACK)],
    )
    frame = ImageFrame(bgr='mock data; use np.ndarray for actual vision',
                       frame_id=1, timestamp_ms=1000, width=640, height=480)
    detected = vision.observe(frame, {TargetType.SIGN})
    print('Vision objects:', [(obj.kind.value, obj.color.value) for obj in detected.objects])
    print('Stop ACK:', motion.stop('stop-black-sign').accepted)
    print('Buzzer step: coordinator would call a separate Buzzer API here')

    req = ArmActionRequest('arm-hit-1', clock.now_ms, ArmAction.HIT_SIGN,
                           None, timeout_ms=1000, source=CommandSource.AUTO)
    ack = arm.start_action(req)
    print('Arm accepted:', ack.accepted, 'action_id:', ack.action_id)
    clock.advance(320)
    result = arm.get_status(ack.action_id)
    print('Arm state:', result.state.value)
    assert result.state == ActionState.DONE_UNVERIFIED
    print('Physical sign knockdown: NOT VERIFIED; coordinator must verify separately')


if __name__ == '__main__':
    main()
