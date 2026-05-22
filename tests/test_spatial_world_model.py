import math
import pytest
from duck_agent_sim.simulator.spatial_world_model import SpatialWorldModel

def test_spatial_world_model_init():
    model = SpatialWorldModel(size_m=8.0, resolution=0.1)
    assert model.grid_size == 80
    assert model.half_grid == 40
    assert len(model.grid) == 80
    assert len(model.grid[0]) == 80
    assert model.landmarks == {}

def test_spatial_world_model_coordinates():
    model = SpatialWorldModel(size_m=8.0, resolution=0.1)
    
    # Origin (0.0, 0.0) -> (40, 40)
    gx, gy = model.world_to_grid(0.0, 0.0)
    assert gx == 40
    assert gy == 40
    
    # Convert back to world coordinates
    wx, wy = model.grid_to_world(gx, gy)
    assert abs(wx - 0.05) < 1e-5
    assert abs(wy - 0.05) < 1e-5

    # Out of bounds clamping
    gx_out, gy_out = model.world_to_grid(-10.0, 10.0)
    assert gx_out == 0
    assert gy_out == 79

def test_spatial_world_model_reset():
    model = SpatialWorldModel(size_m=8.0, resolution=0.1)
    model.grid[10][10] = 2
    model.landmarks["chair"] = {"x": 1.0, "y": 2.0, "confidence": 0.8, "last_updated": 0.0}
    
    model.reset()
    assert model.grid[10][10] == 0
    assert model.landmarks == {}

def test_spatial_world_model_update_landmark_and_grid():
    model = SpatialWorldModel(size_m=8.0, resolution=0.1)
    
    # Mock a YOLO detection of a chair in front of the robot
    # Robot at (0.0, 0.0), facing 0 degrees (along X axis)
    detections = [
        {
            "label": "chair",
            "confidence": 0.85,
            "bbox": [100, 100, 200, 300], # height = 200
            "center": [320, 240], # centered horizontally
        }
    ]
    
    # Calculate estimated distance
    # box_height = 200
    # real_h = 0.6 (REAL_HEIGHTS["chair"])
    # distance = (focal_length * real_h) / box_height
    expected_dist = (model.focal_length * 0.6) / 200.0
    
    model.update(
        robot_x=0.0,
        robot_y=0.0,
        robot_yaw_deg=0.0,
        detections=detections,
        img_w=640,
        img_h=480
    )
    
    assert "chair" in model.landmarks
    chair = model.landmarks["chair"]
    assert abs(chair["x"] - expected_dist) < 0.01
    assert abs(chair["y"] - 0.0) < 0.01
    assert chair["confidence"] == 0.85
    
    # Check that robot cell is marked as Free (1)
    rgx, rgy = model.world_to_grid(0.0, 0.0)
    assert model.grid[rgy][rgx] == 1
    
    # Check that target cell is marked as Occupied (2)
    tgx, tgy = model.world_to_grid(chair["x"], chair["y"])
    assert model.grid[tgy][tgx] == 2

def test_spatial_world_model_landmark_ema_filter():
    model = SpatialWorldModel(size_m=8.0, resolution=0.1)
    
    # First detection
    model.update(
        robot_x=0.0,
        robot_y=0.0,
        robot_yaw_deg=0.0,
        detections=[{"label": "chair", "confidence": 0.8, "bbox": [100, 100, 200, 300], "center": [320, 240]}],
        img_w=640,
        img_h=480
    )
    
    chair_initial = model.landmarks["chair"].copy()
    
    # Second detection slightly offsetted
    model.update(
        robot_x=0.0,
        robot_y=0.0,
        robot_yaw_deg=0.0,
        detections=[{"label": "chair", "confidence": 0.9, "bbox": [100, 100, 200, 280], "center": [340, 240]}],
        img_w=640,
        img_h=480
    )
    
    chair_updated = model.landmarks["chair"]
    
    # Position should be smoothed via EMA (alpha = 0.2)
    # Target X and Y should be intermediate between first and second coordinates
    assert chair_updated["confidence"] == 0.9
    assert chair_updated["x"] != chair_initial["x"]
    assert chair_updated["y"] != chair_initial["y"]
