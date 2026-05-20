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

class ControlIntent(BaseModel):
    linear_x: float = Field(default=0.0, description="Target linear velocity X.")
    linear_y: float = Field(default=0.0, description="Target linear velocity Y.")
    yaw: float = Field(default=0.0, description="Target angular velocity Z (yaw).")

class CommandResponse(BaseModel):
    accepted: bool = Field(..., description="Whether the command was successfully validated and scheduled.")
    command: str = Field(..., description="The command string executed.")
    mapped_control: ControlIntent = Field(..., description="The control mapping applied to the controller.")
    state: RobotState = Field(..., description="Robot state immediately following command scheduling or execution.")

class HealthResponse(BaseModel):
    status: Literal["ok", "error"] = Field(default="ok")
    sim_mode: Literal["mock", "real", "webcam"] = Field(..., description="The running simulation backend mode.")
    robot: str = Field(default="open_duck_mini_v2")

class ScenarioStepResponse(BaseModel):
    command: str
    duration_sec: float
    state: RobotState

class ScenarioResponse(BaseModel):
    scenario: str = Field(..., description="Name of the scenario run.")
    success: bool = Field(..., description="Whether all steps were successfully executed without safety violations.")
    steps_executed: List[ScenarioStepResponse] = Field(default_factory=list, description="A trace of steps executed.")

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
