import pytest
import numpy as np
from unittest.mock import MagicMock, AsyncMock

from duck_agent_sim.simulator.spatial_world_model import SpatialWorldModel
from duck_agent_sim.simulator.path_planner import AStarPlanner, PurePursuitTracker
from duck_agent_sim.simulator.state_estimator import StateEstimator
from duck_agent_sim.agent.scripted_agent import ScriptedAgent
from duck_agent_sim.schemas import RobotState, RobotCommand, SafetyConfig

def test_astar_planner_obstacle_avoidance():
    # Setup spatial model with size 8.0 and resolution 0.1
    spatial_model = SpatialWorldModel(size_m=8.0, resolution=0.1)
    
    # Place an obstacle at (1.0, 0.0) -> grid index (50, 40)
    # Cell 2 = Occupied
    gx, gy = spatial_model.world_to_grid(1.0, 0.0)
    spatial_model.grid[gy][gx] = 2
    # Add buffer/neighbor occupancy to make sure it routes around it
    for dy in [-1, 0, 1]:
        for dx in [-1, 0, 1]:
            spatial_model.grid[gy + dy][gx + dx] = 2
            
    planner = AStarPlanner(spatial_model)
    
    # Plan a path from (0.0, 0.0) to (2.0, 0.0)
    path = planner.plan_path((0.0, 0.0), (2.0, 0.0))
    
    # Path should not be empty, and none of the waypoints should lie on/near the obstacle
    assert len(path) > 2
    for wp in path:
        wgx, wgy = spatial_model.world_to_grid(wp[0], wp[1])
        assert spatial_model.grid[wgy][wgx] != 2

def test_pure_pursuit_tracker():
    tracker = PurePursuitTracker(lookahead_distance=0.4, max_speed=0.25, max_yaw_speed=0.5)
    
    # Robot at (0.0, 0.0, 0.0), path straight to (1.0, 0.0)
    path = [(0.0, 0.0), (0.5, 0.0), (1.0, 0.0)]
    pose = (0.0, 0.0, 0.0)
    
    linear_x, yaw_rate, arrived = tracker.get_steering_command(pose, path)
    assert arrived is False
    assert linear_x > 0.0
    assert abs(yaw_rate) < 1e-3  # should drive straight
    
    # Robot at (0.0, 0.0, 90.0) (facing left/Y+), target straight ahead (1.0, 0.0) (needs right turn)
    pose_turn = (0.0, 0.0, 90.0)
    linear_x_t, yaw_rate_t, arrived_t = tracker.get_steering_command(pose_turn, path)
    assert arrived_t is False
    assert yaw_rate_t < 0.0  # turn right (negative yaw_rate)
    
    # Robot close to goal
    pose_arrived = (0.95, 0.0, 0.0)
    linear_x_a, yaw_rate_a, arrived_a = tracker.get_steering_command(pose_arrived, path)
    assert arrived_a is True

def test_height_map_calculation():
    spatial_model = SpatialWorldModel(size_m=8.0, resolution=0.1)
    
    # Mock a YOLO detection of a chair in front of the robot
    # Robot at (0.0, 0.0), camera height = 0.41m
    # Pitch geometry test
    detections = [
        {
            "label": "chair",
            "confidence": 0.9,
            "bbox": [100, 100, 200, 300], # height = 200
            "center": [320, 120], # cy = 120 (above center 240, so pitch is positive)
        }
    ]
    
    spatial_model.update(
        robot_x=0.0,
        robot_y=0.0,
        robot_yaw_deg=0.0,
        detections=detections,
        img_w=640,
        img_h=480
    )
    
    # Height map should have some cells containing positive elevation values
    has_elevation = False
    for r in spatial_model.height_map:
        for val in r:
            if val > 0.41:  # camera height is 0.41, with pitch upwards, it should be > 0.41
                has_elevation = True
                break
    assert has_elevation is True

def test_state_estimator_vo_stub():
    estimator = StateEstimator(dt=0.02, alpha=0.15, beta=0.10)
    assert estimator.beta == 0.10
    
    # Check that estimate_visual_odometry returns something close to zero when active simulator is not running
    vo = estimator.estimate_visual_odometry()
    assert len(vo) == 3
    # Check that we can call update without issues
    imu_accel = (0.0, 0.0, 0.0)
    imu_quat = (1.0, 0.0, 0.0, 0.0)
    left_c, right_c = True, True
    left_joints = np.zeros(5)
    left_vel = np.zeros(5)
    right_joints = np.zeros(5)
    right_vel = np.zeros(5)
    
    vel, pos = estimator.update(
        imu_accel, imu_quat, left_c, right_c,
        left_joints, left_vel, right_joints, right_vel
    )
    assert len(vel) == 3
    assert len(pos) == 3

def test_scripted_agent_navigate_map():
    # Mock simulator
    mock_sim = MagicMock()
    mock_state = MagicMock()
    mock_state.position = (0.0, 0.0, 0.41)
    mock_state.orientation.yaw_deg = 0.0
    mock_state.fallen = False
    
    mock_sim.get_state.return_value = mock_state
    mock_sim.reset = MagicMock()
    
    mock_response = MagicMock()
    mock_response.state = mock_state
    mock_sim.apply_command.return_value = mock_response
    
    # Setup spatial model
    spatial_model = SpatialWorldModel(size_m=8.0, resolution=0.1)
    mock_sim.spatial_model = spatial_model
    
    agent = ScriptedAgent(mock_sim)
    
    # Plan navigation
    history = agent.run_navigate_map((1.0, 0.0))
    
    # Verify that reset was called, waypoints planned, and at least some commands sent
    assert len(history) > 1
    mock_sim.reset.assert_called()
    assert mock_sim.apply_command.called


from fastapi.testclient import TestClient
from duck_agent_sim.main import app

@pytest.fixture
def test_client():
    with TestClient(app) as c:
        yield c

def test_api_get_map_elevation(test_client):
    response = test_client.get("/map/elevation")
    assert response.status_code == 200
    data = response.json()
    assert "height_map" in data
    assert len(data["height_map"]) == 80

def test_api_post_voice_command(test_client):
    # Send a Hungarian command to voice command route
    response = test_client.post("/voice/command", json={"text": "előre"})
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["action"] == "walk_forward"

def test_api_post_scenario_follow_target(test_client):
    # Send a target follow request
    response = test_client.post("/scenario/follow-target", json={"target_label": "chair"})
    assert response.status_code == 200
    data = response.json()
    assert data["status"] in ("started", "blocked_by_safety")

