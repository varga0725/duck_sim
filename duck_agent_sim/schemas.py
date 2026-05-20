from typing import List, Literal, Tuple, Dict, Optional
from pydantic import BaseModel, Field

# Allowed high-level commands
CommandType = Literal[
    "walk_forward",
    "walk_backward",
    "turn_left",
    "turn_right",
    "stop",
    "reset",
    "look_around"
]

class SafetyConfig(BaseModel):
    stop_on_fall: bool = Field(default=True, description="Whether to automatically stop the robot upon falling.")
    max_pitch_deg: float = Field(default=35.0, ge=0.0, le=90.0, description="Max pitch angle in degrees before safety triggers.")
    max_roll_deg: float = Field(default=35.0, ge=0.0, le=90.0, description="Max roll angle in degrees before safety triggers.")
    min_body_height_m: Optional[float] = Field(
        default=None,
        ge=0.0,
        description="Optional internal fallen body-height threshold override in meters; defaults depend on sim mode.",
    )

class RobotCommand(BaseModel):
    command: CommandType = Field(..., description="High level movement command.")
    speed: float = Field(default=0.25, ge=0.0, le=1.0, description="Target movement speed.")
    turn: float = Field(default=0.0, ge=-1.0, le=1.0, description="Yaw rate or turn factor.")
    duration_sec: float = Field(default=1.0, ge=0.1, le=10.0, description="How long to execute the command.")
    safety: SafetyConfig = Field(default_factory=SafetyConfig, description="Safety configuration overrides.")

class Orientation(BaseModel):
    roll_deg: float = Field(default=0.0, description="Roll angle in degrees.")
    pitch_deg: float = Field(default=0.0, description="Pitch angle in degrees.")
    yaw_deg: float = Field(default=0.0, description="Yaw angle in degrees.")

class FeetContact(BaseModel):
    left: bool = Field(default=True, description="Left foot touch contact status.")
    right: bool = Field(default=True, description="Right foot touch contact status.")

SensorVector3 = Tuple[float, float, float]
SensorQuaternion = Tuple[float, float, float, float]

class StabilityThresholds(BaseModel):
    max_roll_deg: float = Field(default=35.0, description="Roll fallen threshold in degrees.")
    max_pitch_deg: float = Field(default=35.0, description="Pitch fallen threshold in degrees.")
    min_body_height_m: float = Field(default=0.15, description="Internal fallen body-height threshold in meters.")
    agent_preflight_min_body_height_m: float = Field(default=0.25, description="Conservative agent preflight body-height guard in meters.")
    state_freshness_timeout_sec: Optional[float] = Field(default=None, description="Maximum accepted state age in seconds when freshness is evaluated.")
    require_feet_contact: bool = Field(default=False, description="Whether the assessment treats no foot contact as unstable.")

class StabilityState(BaseModel):
    status: Literal["stable", "unstable", "fallen"] = Field(default="stable", description="Public stability classification.")
    reasons: List[str] = Field(default_factory=list, description="Machine-readable reason codes explaining non-stable status.")
    min_body_height_m: float = Field(default=0.15, description="Effective internal fallen body-height threshold in meters.")
    thresholds: StabilityThresholds = Field(default_factory=StabilityThresholds, description="Safety thresholds used for this assessment.")
    internal_fallen_min_body_height_m: float = Field(default=0.15, description="Body-height threshold that marks the robot fallen internally.")
    agent_preflight_min_body_height_m: float = Field(default=0.25, description="Stricter body-height guard recommended before agent commands.")
    freshness_sec: Optional[float] = Field(default=None, description="Age of the sampled state when freshness was evaluated.")

class SensorAvailability(BaseModel):
    """Raw sensor channel with explicit availability and nulls for unavailable values."""

    available: bool = Field(..., description="Whether raw values are backed by real simulator sensor data.")
    gyro: Optional[SensorVector3] = Field(default=None, description="IMU gyro, if this channel represents IMU data.")
    accelerometer: Optional[SensorVector3] = Field(default=None, description="IMU accelerometer, if available.")
    local_linvel: Optional[SensorVector3] = Field(default=None, description="IMU local-frame linear velocity.")
    global_linvel: Optional[SensorVector3] = Field(default=None, description="IMU world-frame linear velocity.")
    global_angvel: Optional[SensorVector3] = Field(default=None, description="IMU world-frame angular velocity.")
    position: Optional[SensorVector3] = Field(default=None, description="World-frame sensor/site position.")
    orientation: Optional[SensorQuaternion] = Field(default=None, description="World-frame quaternion (w, x, y, z), when available.")
    upvector: Optional[SensorVector3] = Field(default=None, description="World-frame up/axis vector, when available.")
    forwardvector: Optional[SensorVector3] = Field(default=None, description="World-frame forward vector, when available.")
    velocity: Optional[SensorVector3] = Field(default=None, description="World-frame linear velocity, if this channel represents a foot.")
    axis: Optional[SensorVector3] = Field(default=None, description="Foot local axis vector expressed in world frame.")

class SensorsState(BaseModel):
    robot: str = Field(default="open_duck_mini_v2", description="Name of the simulated robot.")
    mode: Literal["mock", "real", "webcam"] = Field(..., description="Running simulation backend mode.")
    sim_time: float = Field(default=0.0, description="Simulation elapsed time in seconds.")
    timestamp: float = Field(..., description="Wall-clock timestamp in seconds since epoch when sampled.")
    imu: SensorAvailability = Field(..., description="Raw IMU sensor bundle.")
    feet: Dict[Literal["left", "right"], SensorAvailability] = Field(..., description="Raw left/right foot sensor bundles.")

class RobotState(BaseModel):
    robot: str = Field(default="open_duck_mini_v2", description="Name of the simulated robot.")
    status: Literal["idle", "walking", "turning", "stopped", "fallen", "resetting"] = Field(
        default="idle", description="Current high level operation status."
    )
    sim_time: float = Field(default=0.0, description="Simulation elapsed time in seconds.")
    position: Tuple[float, float, float] = Field(default=(0.0, 0.0, 0.41), description="XYZ coordinates of the robot.")
    orientation: Orientation = Field(default_factory=Orientation, description="RPY Euler angles of the robot.")
    feet_contact: FeetContact = Field(default_factory=FeetContact, description="Feet floor contact status.")
    fallen: bool = Field(default=False, description="Whether the safety monitor detects a fall.")
    last_command: str = Field(default="stop", description="Last received command identifier.")
    stability: StabilityState = Field(default_factory=StabilityState, description="Public stability contract for agent preflight and diagnostics.")

class ControlIntent(BaseModel):
    linear_x: float = Field(default=0.0, description="Target linear velocity X.")
    linear_y: float = Field(default=0.0, description="Target linear velocity Y.")
    yaw: float = Field(default=0.0, description="Target angular velocity Z (yaw).")

class CommandResponse(BaseModel):
    accepted: bool = Field(..., description="Whether the command was successfully validated and scheduled.")
    command: str = Field(..., description="The command string executed.")
    mapped_control: ControlIntent = Field(..., description="The control mapping applied to the controller.")
    state: RobotState = Field(..., description="Robot state immediately following command scheduling or execution.")
    safety_intervention: Optional[str] = Field(default=None, description="Safety recovery phase if stop+reset was triggered.")
    safety_reasons: List[str] = Field(default_factory=list, description="Unified safety assessment reason codes.")

class HealthResponse(BaseModel):
    status: Literal["ok", "error"] = Field(default="ok")
    sim_mode: Literal["mock", "real", "webcam"] = Field(..., description="The running simulation backend mode.")
    robot: str = Field(default="open_duck_mini_v2")

class CameraIntrinsics(BaseModel):
    fx: float = Field(..., description="Focal length in pixels along image X.")
    fy: float = Field(..., description="Focal length in pixels along image Y.")
    cx: float = Field(..., description="Principal point X coordinate in pixels.")
    cy: float = Field(..., description="Principal point Y coordinate in pixels.")

class CameraExtrinsics(BaseModel):
    reference_frame: str = Field(..., description="Frame this camera transform is expressed relative to.")
    translation_m: Tuple[float, float, float] = Field(..., description="Camera origin translation in meters.")
    quaternion_wxyz: Tuple[float, float, float, float] = Field(..., description="Camera orientation quaternion as w,x,y,z.")

class CameraInfoResponse(BaseModel):
    mode: Literal["mock", "real", "webcam"] = Field(..., description="Simulation/camera backend mode.")
    width: int = Field(..., description="Camera image width in pixels.")
    height: int = Field(..., description="Camera image height in pixels.")
    fovy: Optional[float] = Field(default=None, description="Vertical field of view in degrees if known.")
    intrinsics: Optional[CameraIntrinsics] = Field(default=None, description="Pinhole intrinsics if derivable/known.")
    distortion: Optional[List[float]] = Field(default=None, description="Distortion coefficients if calibrated, otherwise null.")
    calibrated: bool = Field(..., description="Whether intrinsics/extrinsics are calibrated or contract-defined.")
    camera_frame: str = Field(..., description="Public name of the camera frame.")
    extrinsics: Optional[CameraExtrinsics] = Field(default=None, description="Local camera extrinsics if known.")

class ScenarioStepResponse(BaseModel):
    command: str
    duration_sec: float
    state: RobotState

class ScenarioResponse(BaseModel):
    scenario: str = Field(..., description="Name of the scenario run.")
    success: bool = Field(..., description="Whether all steps were successfully executed without safety violations.")
    steps_executed: List[ScenarioStepResponse] = Field(default_factory=list, description="A trace of steps executed.")
    safety_intervention: Optional[str] = Field(default=None, description="Safety recovery phase if stop+reset was triggered.")
    safety_reasons: List[str] = Field(default_factory=list, description="Unified safety assessment reason codes.")

class FollowerConfigSchema(BaseModel):
    target_label: Optional[str] = Field(default=None, description="Object label to follow (e.g. 'person')")
    target_id: Optional[int] = Field(default=None, description="Specific tracking ID to follow. -1 to follow first detected matching label.")
    follow_height: Optional[float] = Field(default=None, description="Desired target bounding box height in pixels.")
    height_tolerance: Optional[float] = Field(default=None, description="Bounding box height tolerance in pixels.")
    center_deadzone: Optional[float] = Field(default=None, description="Bounding box centering error deadzone in pixels.")
    deadman_timeout: Optional[float] = Field(default=None, description="Failsafe timeout in seconds before stopping if target is lost.")
    K_p_yaw: Optional[float] = Field(default=None, description="Proportional gain for turning rate.")
    K_p_speed: Optional[float] = Field(default=None, description="Proportional gain for forward/backward speed.")
    max_speed: Optional[float] = Field(default=None, description="Maximum linear speed limit.")
    max_yaw: Optional[float] = Field(default=None, description="Maximum yaw (turning) rate limit.")
    yaw_smooth_alpha: Optional[float] = Field(default=None, description="Low pass exponential smoothing filter for turning.")
    search_yaw_speed: Optional[float] = Field(default=None, description="Spin rate while searching for a lost target.")
    search_timeout: Optional[float] = Field(default=None, description="Search/scan duration in seconds before giving up.")
