from typing import List, Dict, Any, Tuple, Optional
from pydantic import BaseModel, Field

class A2ARobotState(BaseModel):
    position: Tuple[float, float, float] = Field(..., description="Current coordinates (x, y, z) of the robot.")
    yaw_deg: float = Field(..., description="Current yaw/heading angle in degrees.")
    status: str = Field(..., description="Status like idle, walking, stopped.")
    fallen: bool = Field(..., description="Fallen status.")
    speed: float = Field(0.0, description="Current estimated speed.")

class A2ALandmark(BaseModel):
    label: str = Field(..., description="Landmark label/class name (e.g. chair, table).")
    x: float = Field(..., description="Remembered world X coordinate in meters.")
    y: float = Field(..., description="Remembered world Y coordinate in meters.")
    confidence: float = Field(..., description="Landmark tracking confidence.")

class A2ASpatialModel(BaseModel):
    landmarks: List[A2ALandmark] = Field(default_factory=list, description="Currently mapped landmarks.")
    obstacle_close: bool = Field(False, description="Flag indicating if an obstacle is very close to the robot.")

class A2ARequest(BaseModel):
    prompt: str = Field(..., description="The user instructions/natural language command.")
    robot_state: A2ARobotState = Field(..., description="Summarized robot state.")
    spatial_world_model: A2ASpatialModel = Field(..., description="Spatial world model summary.")

class A2AResponse(BaseModel):
    action: str = Field(..., description="Determined action (e.g. walk_forward, turn_left, stop, reset, navigate_to).")
    speed: float = Field(0.0, description="Speed parameter for the action (0.0 to 1.0).")
    turn: float = Field(0.0, description="Turn/yaw intensity parameter (-1.0 to 1.0).")
    duration: float = Field(1.0, description="Target duration for the action in seconds.")
    target_landmark: Optional[str] = Field(None, description="Optional target landmark label to navigate to.")
    target_coordinates: Optional[Tuple[float, float]] = Field(None, description="Optional target coordinates (x, y) to navigate to.")
    speech: str = Field("", description="Text-to-speech response to play back to the user.")
    reasoning: str = Field("", description="Cognitive reasoning explainability notes.")
