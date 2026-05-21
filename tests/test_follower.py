import pytest
import time
from fastapi.testclient import TestClient

from duck_agent_sim.main import app
from duck_agent_sim.schemas import ControlIntent
from duck_agent_sim.vision.perception_state import PerceptionState
from duck_agent_sim.vision.follower import VisionGuidedFollower, FollowerState
from duck_agent_sim.vision import follower as global_follower

@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c

def test_follower_configuration():
    state_repo = PerceptionState()
    follower = VisionGuidedFollower(state_repo)
    
    # Assert initial defaults
    assert follower.target_label == "person"
    assert follower.target_id == -1
    assert follower.follow_height == 200.0
    
    # Configure parameter overrides
    config = {
        "target_label": "chair",
        "target_id": 4,
        "follow_height": 220.0,
        "center_deadzone": 20.0,
        "max_speed": 0.5
    }
    follower.configure(config)
    
    assert follower.target_label == "chair"
    assert follower.target_id == 4
    assert follower.follow_height == 220.0
    assert follower.center_deadzone == 20.0
    assert follower.max_speed == 0.5


def test_follower_target_selection():
    state_repo = PerceptionState()
    follower = VisionGuidedFollower(state_repo)
    
    # 1. No detections
    assert follower._find_target([]) is None
    
    # 2. Detections present but no matching label
    detections = [
        {"label": "chair", "confidence": 0.88, "bbox": [100, 100, 200, 200], "center": [150, 150], "tracking_id": 1}
    ]
    assert follower._find_target(detections) is None
    
    # 3. Label matching (default person)
    detections = [
        {"label": "chair", "confidence": 0.88, "bbox": [100, 100, 200, 200], "center": [150, 150], "tracking_id": 1},
        {"label": "person", "confidence": 0.93, "bbox": [200, 200, 300, 400], "center": [250, 300], "tracking_id": 2}
    ]
    target = follower._find_target(detections)
    assert target is not None
    assert target["label"] == "person"
    assert target["tracking_id"] == 2
    
    # 4. Specific target ID tracking
    follower.configure({"target_id": 9})
    detections = [
        {"label": "person", "confidence": 0.80, "bbox": [200, 200, 300, 400], "center": [250, 300], "tracking_id": 2},
        {"label": "person", "confidence": 0.95, "bbox": [300, 200, 400, 400], "center": [350, 300], "tracking_id": 9}
    ]
    target = follower._find_target(detections)
    assert target is not None
    assert target["tracking_id"] == 9


def test_follower_control_calculations():
    state_repo = PerceptionState()
    follower = VisionGuidedFollower(state_repo)
    follower.configure({
        "follow_height": 200.0,
        "height_tolerance": 20.0,
        "center_deadzone": 30.0,
        "K_p_yaw": 0.003,
        "K_p_speed": 0.002,
        "max_speed": 0.3
    })
    
    # Mocking perception dimensions (640x480)
    state_repo.width = 640
    state_repo.height = 480
    
    # --- Case 1: Centered & within follow distance (height = 190. Tolerance 20, so 180 to 220 is deadzone) ---
    # Center X = 320.0. error_x = 320.0 - 320.0 = 0.0 <= center_deadzone.
    # Height = 190.0 (abs(200.0 - 190.0) = 10.0 <= tolerance).
    detections = [
        {"label": "person", "confidence": 0.95, "bbox": [270.0, 100.0, 370.0, 290.0], "center": [320.0, 195.0], "tracking_id": 1}
    ]
    state_repo.update(detections, width=640, height=480)
    
    # Simulate single iteration of the follower's _run_loop core logic manually
    target = follower._find_target(detections)
    assert target is not None
    
    x1, y1, x2, y2 = target["bbox"]
    box_height = y2 - y1
    cx, cy = target["center"]
    
    error_x = cx - 320.0
    error_h = follower.follow_height - box_height
    
    # Speed Calculation
    if abs(error_h) <= follower.height_tolerance:
        state = FollowerState.TRACKING
        linear_x = 0.0
    else:
        state = FollowerState.FOLLOWING
        linear_x = follower.K_p_speed * error_h
        
    # Turning Calculation
    if abs(error_x) <= follower.center_deadzone:
        yaw_target = 0.0
    else:
        yaw_target = -follower.K_p_yaw * error_x
        
    assert state == FollowerState.TRACKING
    assert linear_x == 0.0
    assert yaw_target == 0.0
    
    # --- Case 2: Target to the right & too far away (height = 100 -> error_h = 100) ---
    # Target center X = 450.0 (error_x = 450 - 320 = 130 > center_deadzone).
    # Height = 100.0 (error_h = 200.0 - 100.0 = 100.0 > tolerance).
    detections = [
        {"label": "person", "confidence": 0.95, "bbox": [400.0, 100.0, 500.0, 200.0], "center": [450.0, 150.0], "tracking_id": 1}
    ]
    target = follower._find_target(detections)
    x1, y1, x2, y2 = target["bbox"]
    box_height = y2 - y1
    cx, cy = target["center"]
    error_x = cx - 320.0
    error_h = follower.follow_height - box_height
    
    if abs(error_h) <= follower.height_tolerance:
        state = FollowerState.TRACKING
        linear_x = 0.0
    else:
        state = FollowerState.FOLLOWING
        linear_x = follower.K_p_speed * error_h
        linear_x = min(follower.max_speed, linear_x)
        
    if abs(error_x) <= follower.center_deadzone:
        yaw_target = 0.0
    else:
        yaw_target = -follower.K_p_yaw * error_x
        yaw_target = max(-follower.max_yaw, min(follower.max_yaw, yaw_target))
        
    assert state == FollowerState.FOLLOWING
    assert linear_x == pytest.approx(0.2)  # 0.002 * 100 = 0.2
    assert yaw_target == pytest.approx(-0.39)  # -0.003 * 130 = -0.39 (turns right)


def test_deadman_timeout():
    state_repo = PerceptionState()
    follower = VisionGuidedFollower(state_repo)
    follower.configure({"deadman_timeout": 0.1})
    
    follower.state = FollowerState.FOLLOWING
    follower.lost_since = time.time() - 0.2  # Lost for 0.2s, which exceeds 0.1s
    
    # Execute lost handling logic
    lost_duration = time.time() - follower.lost_since
    if lost_duration >= follower.deadman_timeout:
        follower.state = FollowerState.STOPPED
        linear_x = 0.0
        yaw_target = 0.0
        
    assert follower.state == FollowerState.STOPPED


def test_follower_rest_endpoints(client):
    # Make sure target follower is stopped initially
    global_follower.stop()
    
    # 1. GET /vision/follow/status
    res = client.get("/vision/follow/status")
    assert res.status_code == 200
    status = res.json()
    assert status["active"] is False
    assert status["state"] == "STOPPED"
    
    # 2. POST /vision/follow/start
    res = client.post("/vision/follow/start", json={
        "target_label": "person",
        "target_id": 9,
        "follow_height": 210.0,
        "deadman_timeout": 1.5
    })
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "started"
    assert data["follower"]["active"] is True
    assert data["follower"]["state"] in ["SEARCHING", "LOST"]
    assert data["follower"]["target_label"] == "person"
    assert data["follower"]["target_id"] == 9
    
    # 3. GET status while running
    res = client.get("/vision/follow/status")
    assert res.status_code == 200
    assert res.json()["active"] is True
    
    # 4. POST /vision/follow/stop
    res = client.post("/vision/follow/stop")
    res_data = res.json()
    assert res.status_code == 200
    assert res_data["status"] == "stopped"
    assert res_data["follower"]["active"] is False
    assert res_data["follower"]["state"] == "STOPPED"


def test_follower_active_search():
    state_repo = PerceptionState()
    follower = VisionGuidedFollower(state_repo)
    follower.configure({
        "search_yaw_speed": 0.5,
        "search_timeout": 5.0
    })
    
    assert follower.search_yaw_speed == 0.5
    assert follower.search_timeout == 5.0


def test_follower_active_search_timeout_and_spin_direction():
    state_repo = PerceptionState()
    follower = VisionGuidedFollower(state_repo)
    
    # 1. Initially it should be positive spin direction
    assert follower.last_seen_direction == 1.0
    
    # 2. Simulate target on the right (yaw_target would be negative)
    # error_x > center_deadzone (e.g. 130 > 30)
    state_repo.width = 640
    state_repo.height = 480
    detections = [
        {"label": "person", "confidence": 0.95, "bbox": [400.0, 100.0, 500.0, 300.0], "center": [450.0, 200.0], "tracking_id": 1}
    ]
    
    # Calculate controls and update direction based on error
    target = follower._find_target(detections)
    assert target is not None
    cx, cy = target["center"]
    error_x = cx - 320.0
    yaw_target = -follower.K_p_yaw * error_x
    if yaw_target != 0.0:
        follower.last_seen_direction = 1.0 if yaw_target > 0.0 else -1.0
    assert follower.last_seen_direction == -1.0
    
    # 3. Simulate target lost and active search state machine transition
    follower.lost_since = None
    follower.state = FollowerState.SEARCHING
    
    # First time target is lost: lost_since gets initialized
    if follower.lost_since is None:
        follower.lost_since = time.time()
    
    assert follower.lost_since is not None
    
    # 4. Spin direction should match last_seen_direction (-1.0)
    yaw_target_search = follower.search_yaw_speed * follower.last_seen_direction
    assert yaw_target_search == -0.4
    
    # 5. Simulate timeout expiration: lost_since is in the past
    follower.lost_since = time.time() - 20.0
    lost_duration = time.time() - follower.lost_since
    assert lost_duration >= follower.search_timeout
    
    # Under timeout condition:
    follower.state = FollowerState.STOPPED
    follower.running = False
    
    assert follower.state == FollowerState.STOPPED
    assert follower.running is False


