"""Emergency rescue quadruped: frozen shared data contracts v0.2.1.

Only Python stdlib is needed to import this file; vision implementers use NumPy/OpenCV.
Times are monotonic milliseconds from one process clock; they are NOT Unix timestamps.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import numpy as np


class TargetType(str, Enum):
    LINE = "LINE"
    SIGN = "SIGN"
    BALL = "BALL"
    CUP = "CUP"
    BLOCK = "BLOCK"
    STORAGE_AREA = "STORAGE_AREA"


class TargetColor(str, Enum):
    RED = "RED"
    GREEN = "GREEN"
    BLUE = "BLUE"
    YELLOW = "YELLOW"
    BLACK = "BLACK"


class VisionStatus(str, Enum):
    OK = "OK"
    INVALID_FRAME = "INVALID_FRAME"
    STALE_FRAME = "STALE_FRAME"
    AMBIGUOUS = "AMBIGUOUS"
    PROCESSING_ERROR = "PROCESSING_ERROR"


class ControlMode(str, Enum):
    SAFE = "SAFE"
    AUTO = "AUTO"
    REMOTE = "REMOTE"


class CommandSource(str, Enum):
    AUTO = "AUTO"
    REMOTE = "REMOTE"
    SAFETY = "SAFETY"


class ErrorCode(str, Enum):
    INVALID_ARGUMENT = "INVALID_ARGUMENT"
    STALE_DATA = "STALE_DATA"
    BUSY = "BUSY"
    UNSUPPORTED = "UNSUPPORTED"
    TIMEOUT = "TIMEOUT"
    COMM_ERROR = "COMM_ERROR"
    UNREACHABLE = "UNREACHABLE"
    SAFETY_STOP = "SAFETY_STOP"
    MODE_DENIED = "MODE_DENIED"
    CONFLICT = "CONFLICT"
    NOT_READY = "NOT_READY"
    NOT_FOUND = "NOT_FOUND"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class MotionMeasuredState(str, Enum):
    UNKNOWN = "UNKNOWN"
    STOPPED = "STOPPED"
    MOVING = "MOVING"


class ArmAction(str, Enum):
    HOME = "HOME"
    HIT_SIGN = "HIT_SIGN"
    PICK_BALL = "PICK_BALL"
    PLACE_CUP_2X = "PLACE_CUP_2X"
    PLACE_CUP_3X = "PLACE_CUP_3X"
    PICK_BLOCK = "PICK_BLOCK"
    PLACE_STORAGE = "PLACE_STORAGE"
    OPEN_CLAW = "OPEN_CLAW"
    CLOSE_CLAW = "CLOSE_CLAW"


class ActionState(str, Enum):
    ACCEPTED = "ACCEPTED"
    RUNNING = "RUNNING"
    DONE_UNVERIFIED = "DONE_UNVERIFIED"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    TIMEOUT = "TIMEOUT"
    CANCELLED = "CANCELLED"


@dataclass(frozen=True)
class ImageFrame:
    bgr: np.ndarray  # runtime import of NumPy not required by contract layer
    frame_id: int
    timestamp_ms: int  # image capture timestamp, monotonic ms
    width: int
    height: int


@dataclass(frozen=True)
class LineDetection:
    found: bool
    error_px: float | None  # image X(center of line) - image X(reference)
    quality: float  # algorithm-specific [0, 1], NOT a calibrated probability


@dataclass(frozen=True)
class Detection:
    kind: TargetType
    center_px: tuple[float, float]  # u-right, v-down in image
    bbox_xywh_px: tuple[int, int, int, int]  # left, top, width, height
    area_px2: float
    score: float  # algorithm-specific quality score [0, 1]
    confirmed: bool
    color: TargetColor | None = None
    cup_multiplier: int | None = None  # only 2 or 3 for a cup
    position_body_mm: tuple[float, float, float] | None = None  # X-front, Y-left, Z-up
    distance_mm: float | None = None  # reference point must be calibrated and documented


@dataclass(frozen=True)
class VisionResult:
    frame_id: int
    timestamp_ms: int  # source frame capture time
    status: VisionStatus
    line: LineDetection | None = None  # None: LINE not requested
    objects: list[Detection] = field(default_factory=list)
    error_code: ErrorCode | None = None
    message: str = ""


@dataclass(frozen=True)
class DriveCommand:
    request_id: str
    timestamp_ms: int  # issuing time (monotonic ms)
    x_norm: float
    y_norm: float
    yaw_norm: float
    ttl_ms: int
    source: CommandSource


@dataclass(frozen=True)
class CommandAck:
    request_id: str
    accepted: bool  # NOT proof of physical motion or stop
    timestamp_ms: int
    error_code: ErrorCode | None = None
    message: str = ""


@dataclass(frozen=True)
class MotionStatus:
    timestamp_ms: int
    commanded: DriveCommand | None
    measured_state: MotionMeasuredState  # UNKNOWN if no trusted physical feedback
    last_command_ms: int | None
    watchdog_expired: bool
    error_code: ErrorCode | None = None


@dataclass(frozen=True)
class ArmTarget:
    color: TargetColor | None = None
    preset_id: str | None = None
    position_arm_mm: tuple[float, float, float] | None = None  # only if calibrated
    source_frame_id: int | None = None


@dataclass(frozen=True)
class ArmActionRequest:
    request_id: str
    timestamp_ms: int
    action: ArmAction
    target: ArmTarget | None
    timeout_ms: int
    source: CommandSource


@dataclass(frozen=True)
class ActionAck:
    request_id: str
    accepted: bool
    timestamp_ms: int
    action_id: str | None = None
    error_code: ErrorCode | None = None
    message: str = ""


@dataclass(frozen=True)
class ActionResult:
    action_id: str
    state: ActionState
    timestamp_ms: int
    started_ms: int | None = None
    finished_ms: int | None = None
    error_code: ErrorCode | None = None
    message: str = ""
