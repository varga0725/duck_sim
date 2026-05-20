import math

from fastapi import APIRouter, HTTPException
from typing import Dict, Any, Optional

from duck_agent_sim.schemas import (
    RobotCommand,
    RobotState,
    CommandResponse,
    HealthResponse,
    CameraExtrinsics,
    CameraInfoResponse,
    CameraIntrinsics,
    ScenarioResponse,
    ScenarioStepResponse,
    SafetyConfig,
    FollowerConfigSchema,
    ControlIntent,
    SensorsState,
)
from duck_agent_sim.simulator.instance import active_simulator
from duck_agent_sim.simulator.safety import evaluate_stability
from duck_agent_sim.config import DUCK_SIM_MODE

router = APIRouter()


def _assess_bridge_state(state: RobotState, safety: SafetyConfig):
    """Run the unified conservative safety assessment used by all high-level starts."""
    return evaluate_stability(
        state,
        safety,
        sim_mode=DUCK_SIM_MODE,
        use_agent_preflight_guard=True,
        require_feet_contact=True,
    )


def _recover_from_unstable_state() -> RobotState:
    """High-level recovery: stop, then reset. Never executes the original motion in this call."""
    active_simulator.stop()
    return active_simulator.reset()


def _preflight_recovery(safety: SafetyConfig):
    assessment = _assess_bridge_state(active_simulator.get_state(), safety)
    if assessment.status == "stable":
        return assessment, None
    return assessment, _recover_from_unstable_state()


def _command_response_for_preflight_recovery(cmd: RobotCommand, assessment, recovered_state: RobotState) -> CommandResponse:
    return CommandResponse(
        accepted=False,
        command=cmd.command,
        mapped_control=ControlIntent(linear_x=0.0, linear_y=0.0, yaw=0.0),
        state=recovered_state,
        safety_intervention="preflight_recovered",
        safety_reasons=assessment.reasons,
    )

@router.get("/health", response_model=HealthResponse)
def get_health():
    """Returns application health and current simulation backend mode."""
    return HealthResponse(
        status="ok",
        sim_mode=DUCK_SIM_MODE,
        robot="open_duck_mini_v2"
    )

def _pinhole_intrinsics(width: int, height: int, fovy_deg: float) -> CameraIntrinsics:
    focal_px = (height / 2.0) / math.tan(math.radians(fovy_deg) / 2.0)
    return CameraIntrinsics(
        fx=focal_px,
        fy=focal_px,
        cx=width / 2.0,
        cy=height / 2.0,
    )


@router.get("/camera/info", response_model=CameraInfoResponse)
def get_camera_info():
    """Returns the public camera intrinsics/extrinsics contract for the active mode."""
    width = 640
    height = 480

    if DUCK_SIM_MODE == "webcam":
        return CameraInfoResponse(
            mode="webcam",
            width=width,
            height=height,
            fovy=None,
            intrinsics=None,
            distortion=None,
            calibrated=False,
            camera_frame="webcam",
            extrinsics=None,
        )

    if DUCK_SIM_MODE == "real":
        fovy = 45.0
        return CameraInfoResponse(
            mode="real",
            width=width,
            height=height,
            fovy=fovy,
            intrinsics=_pinhole_intrinsics(width, height, fovy),
            distortion=None,
            calibrated=True,
            camera_frame="fpv",
            extrinsics=CameraExtrinsics(
                reference_frame="head_assembly",
                translation_m=(0.08, 0.0, 0.05),
                quaternion_wxyz=(0.70710678, 0.0, -0.0, -0.70710678),
            ),
        )

    fovy = 45.0
    return CameraInfoResponse(
        mode="mock",
        width=width,
        height=height,
        fovy=fovy,
        intrinsics=_pinhole_intrinsics(width, height, fovy),
        distortion=None,
        calibrated=True,
        camera_frame="mock_camera",
        extrinsics=CameraExtrinsics(
            reference_frame="mock_world",
            translation_m=(0.0, 0.0, 0.0),
            quaternion_wxyz=(1.0, 0.0, 0.0, 0.0),
        ),
    )


@router.post("/command", response_model=CommandResponse)
def post_command(cmd: RobotCommand):
    """
    Accepts a high-level motion command after a mandatory unified safety preflight.
    Unstable preflight triggers stop+reset and the requested command is not executed.
    Post-command instability also triggers stop+reset recovery before returning.
    """
    try:
        assessment, recovered_state = _preflight_recovery(cmd.safety)
        if recovered_state is not None:
            return _command_response_for_preflight_recovery(cmd, assessment, recovered_state)

        response = active_simulator.apply_command(cmd)
        post_assessment = _assess_bridge_state(response.state, cmd.safety)
        if post_assessment.status != "stable":
            recovered_state = _recover_from_unstable_state()
            return response.model_copy(update={
                "state": recovered_state,
                "safety_intervention": "post_command_recovered",
                "safety_reasons": post_assessment.reasons,
            })
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

@router.get("/sensors/state", response_model=SensorsState)
def get_sensors_state():
    """Returns raw simulator sensor channels with explicit availability/null markers."""
    return active_simulator.get_sensor_state()

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
    The same safety preflight runs before the scenario and before every step;
    any unstable state triggers stop+reset and aborts the remaining route.
    """
    safety = SafetyConfig()
    assessment, recovered_state = _preflight_recovery(safety)
    if recovered_state is not None:
        return ScenarioResponse(
            scenario="walk_square",
            success=False,
            steps_executed=[],
            safety_intervention="preflight_recovered",
            safety_reasons=assessment.reasons,
        )

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
    safety_intervention = None
    safety_reasons = []

    for step in steps:
        step_assessment, recovered_state = _preflight_recovery(safety)
        if recovered_state is not None:
            success = False
            safety_intervention = "preflight_recovered"
            safety_reasons = step_assessment.reasons
            break

        cmd = RobotCommand(
            command=step["command"],
            speed=step["speed"],
            turn=step["turn"],
            duration_sec=step["duration"],
            safety=safety,
        )

        try:
            response = active_simulator.apply_command(cmd)
            state = response.state
            post_assessment = _assess_bridge_state(state, safety)
            if post_assessment.status != "stable":
                state = _recover_from_unstable_state()
                success = False
                safety_intervention = "post_command_recovered"
                safety_reasons = post_assessment.reasons

            steps_executed.append(
                ScenarioStepResponse(
                    command=step["command"],
                    duration_sec=step["duration"],
                    state=state
                )
            )

            if not success:
                break

        except Exception:
            success = False
            break

    return ScenarioResponse(
        scenario="walk_square",
        success=success,
        steps_executed=steps_executed,
        safety_intervention=safety_intervention,
        safety_reasons=safety_reasons,
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
    Starts the vision-guided target follower after the same mandatory safety preflight.
    Unstable preflight triggers stop+reset and the follower is not started.
    """
    safety = SafetyConfig()
    assessment, recovered_state = _preflight_recovery(safety)
    if recovered_state is not None:
        return {
            "status": "blocked_by_safety",
            "follower": follower.get_status(),
            "state": recovered_state,
            "safety_intervention": "preflight_recovered",
            "safety_reasons": assessment.reasons,
        }

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

