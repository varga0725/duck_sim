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

def test_spatial_world_model_multi_instance():
    model = SpatialWorldModel(size_m=8.0, resolution=0.1)
    
    # Update with first chair detection
    model.update(
        robot_x=0.0,
        robot_y=0.0,
        robot_yaw_deg=0.0,
        detections=[{"label": "chair", "confidence": 0.85, "bbox": [100, 100, 200, 300], "center": [320, 240]}],
        img_w=640,
        img_h=480
    )
    
    # We should have chair_1 and legacy fallback chair
    assert "chair_1" in model.landmarks
    assert "chair" in model.get_map_data()["landmarks"]
    chair_1_pos = (model.landmarks["chair_1"]["x"], model.landmarks["chair_1"]["y"])
    
    # Add a second chair far away (offsetted box center)
    model.update(
        robot_x=0.0,
        robot_y=0.0,
        robot_yaw_deg=0.0,
        detections=[{"label": "chair", "confidence": 0.90, "bbox": [100, 100, 200, 300], "center": [100, 240]}], # far left
        img_w=640,
        img_h=480
    )
    
    # We should have two instances now: chair_1 and chair_2
    assert "chair_1" in model.landmarks
    assert "chair_2" in model.landmarks
    assert model.landmarks["chair_2"]["x"] != chair_1_pos[0]

def test_spatial_world_model_confidence_decay_and_pruning():
    model = SpatialWorldModel(size_m=8.0, resolution=0.1)
    
    # Add chair instance
    model.update(
        robot_x=0.0,
        robot_y=0.0,
        robot_yaw_deg=0.0,
        detections=[{"label": "chair", "confidence": 0.5, "bbox": [100, 100, 200, 300], "center": [320, 240]}],
        img_w=640,
        img_h=480
    )
    assert "chair_1" in model.landmarks
    initial_conf = model.landmarks["chair_1"]["confidence"]
    
    # Trigger updates facing the landmark, but with NO detections -> should decay confidence
    model.update(
        robot_x=0.0,
        robot_y=0.0,
        robot_yaw_deg=0.0,
        detections=[], # no detections in FOV
        img_w=640,
        img_h=480
    )
    
    # Confidence should decay from 0.5 by 0.15 to 0.35
    assert model.landmarks["chair_1"]["confidence"] < initial_conf
    
    # Update again to trigger pruning (< 0.1)
    model.update(
        robot_x=0.0,
        robot_y=0.0,
        robot_yaw_deg=0.0,
        detections=[],
        img_w=640,
        img_h=480
    )
    assert "chair_1" in model.landmarks
    
    model.update(
        robot_x=0.0,
        robot_y=0.0,
        robot_yaw_deg=0.0,
        detections=[],
        img_w=640,
        img_h=480
    )
    # Confidence should drop below 0.1 -> pruned
    assert "chair_1" not in model.landmarks

def test_mock_yolo_projection():
    from duck_agent_sim.vision.yolo_detector import YOLODetector
    
    detector = YOLODetector()
    
    # 1. At origin (0,0) facing forward (yaw=0)
    dets_forward = detector._detect_mock()
    labels_forward = [d["label"] for d in dets_forward]
    assert "chair" in labels_forward
    assert "sports_ball" in labels_forward
    assert "person" in labels_forward
    
    # 2. Mock turned state where chair is outside horizontal FOV
    from unittest.mock import MagicMock
    import duck_agent_sim.simulator.instance as inst
    
    orig_sim = inst.active_simulator
    mock_sim = MagicMock()
    mock_state = MagicMock()
    mock_state.position = (0.0, 0.0, 0.15)
    mock_state.orientation.yaw_deg = -30.0
    mock_sim.get_state.return_value = mock_state
    inst.active_simulator = mock_sim
    
    try:
        dets_turned = detector._detect_mock()
        labels_turned = [d["label"] for d in dets_turned]
        
        # Chair should not be detected since it went out of FOV
        assert "chair" not in labels_turned
        # Sports ball should still be detected
        assert "sports_ball" in labels_turned
    finally:
        inst.active_simulator = orig_sim
