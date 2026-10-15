"""Three public Python protocols. Actual SDK integration is NOT implemented here."""
from __future__ import annotations
from typing import Protocol
from .types import (ActionAck, ActionResult, ArmActionRequest, CommandAck,
                    DriveCommand, ImageFrame, MotionStatus, TargetType, VisionResult)


class VisionAPI(Protocol):
    def observe(self, frame: ImageFrame, interests: set[TargetType]) -> VisionResult:
        ...


class MotionAPI(Protocol):
    def drive(self, command: DriveCommand) -> CommandAck:
        ...

    def stop(self, request_id: str) -> CommandAck:
        ...

    def get_motion_status(self) -> MotionStatus:
        ...


class ArmAPI(Protocol):
    def start_action(self, request: ArmActionRequest) -> ActionAck:
        ...

    def get_status(self, action_id: str) -> ActionResult:
        ...

    # v0.2.1 adjustment: explicit request_id prevents accidental repeated cancellation
    def cancel_action(self, action_id: str, request_id: str) -> CommandAck:
        ...
