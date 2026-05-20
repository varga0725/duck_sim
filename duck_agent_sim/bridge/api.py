from fastapi import APIRouter, HTTPException
from typing import Dict, Any, Optional

from duck_agent_sim.schemas import (
    RobotCommand,
    RobotState,
    CommandResponse,
    HealthResponse,
    ScenarioResponse,
    ScenarioStepResponse,
    SafetyConfig,
    FollowerConfigSchema
)
from duck_agent_sim.simulator.instance import active_simulator
from duck_agent_sim.config import DUCK_SIM_MODE

router = APIRouter()

@router.get("/health", response_model=HealthResponse)
def get_health():
    """Returns application health and current simulation backend mode."""
    return HealthResponse(
        status="ok",
        sim_mode=DUCK_SIM_MODE,
        robot="open_duck_mini_v2"
    )

@router.post("/command", response_model=CommandResponse)
def post_command(cmd: RobotCommand):
    """
    Accepts a high-level motion command, validates safety parameters,
    translates it to control intent, steps the simulator, and returns the result.
    """
    try:
        response = active_simulator.apply_command(cmd)
        return response
    except NotImplementedError as e:
        raise HTTPException(status_code=501, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal simulator error: {str(e)}")

@router.get("/state", response_model=RobotState)
def get_state():
    """Returns the current state of the robot simulation (XYZ, RPY, feet contacts, fallen status)."""
    return active_simulator.get_state()

@router.post("/stop")
def post_stop():
    """Immediately halts robot motion and resets waddling cycles."""
    state = active_simulator.stop()
    return {"stopped": True, "state": state}

@router.post("/reset")
def post_reset():
    """Resets the robot to the initial stable coordinate and clears fallen/instability states."""
    state = active_simulator.reset()
    return {"reset": True, "state": state}

@router.post("/scenario/walk-square", response_model=ScenarioResponse)
def post_walk_square():
    """
    Executes a pre-scripted 4-sided square walking route.
    If safety triggers (fall detected), halts execution immediately.
    """
    steps = [
        {"command": "walk_forward", "speed": 0.25, "turn": 0.0, "duration": 3.0},
        {"command": "turn_left", "speed": 0.25, "turn": 1.0, "duration": 1.57},
        {"command": "walk_forward", "speed": 0.25, "turn": 0.0, "duration": 3.0},
        {"command": "turn_left", "speed": 0.25, "turn": 1.0, "duration": 1.57},
        {"command": "walk_forward", "speed": 0.25, "turn": 0.0, "duration": 3.0},
        {"command": "turn_left", "speed": 0.25, "turn": 1.0, "duration": 1.57},
        {"command": "walk_forward", "speed": 0.25, "turn": 0.0, "duration": 3.0},
        {"command": "stop", "speed": 0.0, "turn": 0.0, "duration": 1.0}
    ]

    steps_executed = []
    success = True

    # Ensure simulator starts from reset
    active_simulator.reset()

    for idx, step in enumerate(steps):
        cmd = RobotCommand(
            command=step["command"],
            speed=step["speed"],
            turn=step["turn"],
            duration_sec=step["duration"],
            safety=SafetyConfig()
        )

        try:
            response = active_simulator.apply_command(cmd)
            state = response.state

            steps_executed.append(
                ScenarioStepResponse(
                    command=step["command"],
                    duration_sec=step["duration"],
                    state=state
                )
            )

            # Check if robot fell during the step
            if state.fallen:
                success = False
                break

        except Exception as e:
            # Handle step failures
            success = False
            break

    return ScenarioResponse(
        scenario="walk_square",
        success=success,
        steps_executed=steps_executed
    )

import io
import cv2
from fastapi.responses import StreamingResponse
from duck_agent_sim.vision.camera import get_active_camera
from duck_agent_sim.vision import get_visible_objects, perception_state, follower

@router.get("/vision/frame")
def get_vision_frame():
    """
    Returns the latest RGB frame captured from the active simulator.
    Encoded as a streaming image/jpeg response.
    """
    # Prefer the background vision loop's latest buffered frame instead of
    # grabbing the webcam again for every HTTP request. On macOS, competing
    # VideoCapture reads from the perception thread + live viewer can make the
    # camera appear to zoom, freeze, or restart. The FrameBuffer is already
    # thread-safe and exposes only the newest frame.
    frame = None
    frame_buffer = getattr(active_simulator, "frame_buffer", None)
    if frame_buffer is not None:
        frame = frame_buffer.get()

    if frame is None:
        camera = get_active_camera()
        frame = camera.capture_frame()
    if frame is None:
        raise HTTPException(status_code=404, detail="No camera frame available")
    
    # Convert RGB (MuJoCo format) to BGR for OpenCV encoding
    bgr_frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
    success, jpeg = cv2.imencode(".jpg", bgr_frame)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to encode frame to JPEG")
        
    return StreamingResponse(io.BytesIO(jpeg.tobytes()), media_type="image/jpeg")

@router.get("/vision/detections")
def get_vision_detections():
    """
    Returns the latest structured object detections.
    """
    objs = get_visible_objects()
    formatted = []
    for obj in objs:
        formatted.append({
            "label": obj["label"],
            "confidence": obj["confidence"],
            "bbox": obj["bbox"],
            "tracking_id": obj["tracking_id"]
        })
    return {"objects": formatted}

@router.get("/vision/state")
def get_vision_state():
    """
    Returns the latest perception state and FPS metrics.
    """
    return perception_state.get_summary()

@router.post("/vision/follow/start")
def post_follow_start(config: Optional[FollowerConfigSchema] = None):
    """
    Starts the vision-guided target follower.
    Accepts optional configuration parameters to tune target filters, gains, and deadzones.
    """
    if config:
        # Filter out None values to keep defaults
        params = {k: v for k, v in config.model_dump().items() if v is not None}
        follower.configure(params)
    follower.start()
    return {"status": "started", "follower": follower.get_status()}

@router.post("/vision/follow/stop")
def post_follow_stop():
    """
    Stops the vision-guided target follower and commands the robot to halt.
    """
    follower.stop()
    return {"status": "stopped", "follower": follower.get_status()}

@router.get("/vision/follow/status")
def get_follow_status():
    """
    Returns the telemetry and control loop status of the target follower.
    """
    return follower.get_status()

