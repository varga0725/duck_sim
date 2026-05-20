import pytest
import time
from fastapi.testclient import TestClient
from duck_agent_sim.main import app
from duck_agent_sim.vision.yolo_detector import YOLODetector
from duck_agent_sim.vision.tracker import CentroidTracker
from duck_agent_sim.vision import get_visible_objects, find_object, get_tracking_target

client = TestClient(app)

def test_detector_initialization():
    detector = YOLODetector()
    assert detector is not None
    # Check singleton property
    detector2 = YOLODetector()
    assert detector is detector2

def test_detections_schema_and_tracker():
    tracker = CentroidTracker(max_distance=100.0)
    
    # Simulate frame 1 detections
    detections_f1 = [
        {"label": "chair", "confidence": 0.88, "bbox": [100.0, 200.0, 200.0, 300.0], "center": [150.0, 250.0], "tracking_id": -1},
        {"label": "person", "confidence": 0.93, "bbox": [400.0, 100.0, 500.0, 400.0], "center": [450.0, 250.0], "tracking_id": -1}
    ]
    tracked_f1 = tracker.update(detections_f1)
    
    # Check that tracking IDs were assigned
    assert tracked_f1[0]["tracking_id"] == 1
    assert tracked_f1[1]["tracking_id"] == 2
    
    # Simulate frame 2 detections (moved slightly)
    detections_f2 = [
        {"label": "chair", "confidence": 0.89, "bbox": [105.0, 205.0, 205.0, 305.0], "center": [155.0, 255.0], "tracking_id": -1},
        {"label": "person", "confidence": 0.94, "bbox": [402.0, 102.0, 502.0, 402.0], "center": [452.0, 252.0], "tracking_id": -1}
    ]
    tracked_f2 = tracker.update(detections_f2)
    
    # Centroid tracking should persist IDs
    assert tracked_f2[0]["tracking_id"] == 1
    assert tracked_f2[1]["tracking_id"] == 2

def test_api_endpoints():
    # 1. GET /vision/frame
    response = client.get("/vision/frame")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/jpeg"
    assert len(response.content) > 0
    
    # 2. GET /vision/detections
    response = client.get("/vision/detections")
    assert response.status_code == 200
    data = response.json()
    assert "objects" in data
    assert len(data["objects"]) > 0
    for obj in data["objects"]:
        assert "label" in obj
        assert "confidence" in obj
        assert "bbox" in obj
        assert "tracking_id" in obj
        
    # 3. GET /vision/state
    response = client.get("/vision/state")
    assert response.status_code == 200
    state = response.json()
    assert "num_objects" in state
    assert "tracked_ids" in state
    assert "labels" in state
    assert "vision_fps" in state
    assert "last_update_sec" in state

def test_agent_integration_helpers():
    # Let the vision system start and populate the state
    time.sleep(0.5)
    
    objs = get_visible_objects()
    assert isinstance(objs, list)
    assert len(objs) > 0
    
    # Check mock objects are visible
    chair = find_object("chair")
    assert chair is not None
    assert chair["label"] == "chair"
    
    person = find_object("person")
    assert person is not None
    assert person["label"] == "person"
    
    # Check invalid label
    none_obj = find_object("invalid_label")
    assert none_obj is None
    
    # Check tracking target
    target = get_tracking_target(chair["tracking_id"])
    assert target is not None
    assert target["label"] == "chair"

def test_webcam_mode_config_and_blank_fallback(monkeypatch):
    monkeypatch.setenv("DUCK_SIM_MODE", "webcam")
    
    from duck_agent_sim.simulator.duck_sim import MockDuckSimulator
    sim = MockDuckSimulator()
    try:
        assert sim.camera_device is not None
        frame = sim.camera_device.capture_frame()
        assert frame is not None
        assert frame.shape == (480, 640, 3)
    finally:
        sim.close()

def test_detect_real_projected_capsule_cylinder(monkeypatch):
    import numpy as np
    import mujoco
    from unittest.mock import MagicMock
    from duck_agent_sim.simulator import instance
    
    # Mock active_simulator
    mock_sim = MagicMock()
    mock_model = MagicMock()
    mock_data = MagicMock()
    
    # Set up simulator model and data mocks
    mock_sim.model = mock_model
    mock_sim.data = mock_data
    mock_sim._lock = MagicMock()
    
    # Set up global camera attributes
    mock_model.vis.global_.fovy = 45.0
    mock_data.cam_xpos = {0: np.array([0.0, 0.0, 1.0])}
    mock_data.cam_xmat = {0: np.identity(3).flatten()}
    
    # Mock mj_name2id
    def name2id_side_effect(model, obj_type, name):
        if obj_type == mujoco.mjtObj.mjOBJ_CAMERA:
            return 0
        if obj_type == mujoco.mjtObj.mjOBJ_BODY:
            if name == "person":
                return 4
        raise KeyError()
    
    monkeypatch.setattr(mujoco, "mj_name2id", name2id_side_effect)
    
    # Mock model geom addresses
    mock_model.body_geomadr = {4: 0}
    mock_model.body_geomnum = {4: 2}
    
    # Geoms for body 4 (person):
    # Geom 0: mjGEOM_CAPSULE
    # Geom 1: mjGEOM_CYLINDER
    mock_model.geom_type = {0: mujoco.mjtGeom.mjGEOM_CAPSULE, 1: mujoco.mjtGeom.mjGEOM_CYLINDER}
    mock_data.geom_xpos = {0: np.array([0.0, 0.0, -0.5]), 1: np.array([0.0, 0.0, -1.0])}
    mock_data.geom_xmat = {0: np.identity(3).flatten(), 1: np.identity(3).flatten()}
    mock_model.geom_size = {0: np.array([0.15, 0.35, 0.0]), 1: np.array([0.05, 0.2, 0.0])}
    
    # Patch active_simulator
    monkeypatch.setattr(instance, "active_simulator", mock_sim)
    
    detector = YOLODetector()
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    
    # Call _detect_real_projected
    projected = detector._detect_real_projected(frame)
    
    # Verify that the person was projected
    assert len(projected) == 1
    assert projected[0]["label"] == "person"
    assert projected[0]["confidence"] == 0.99
    assert len(projected[0]["bbox"]) == 4

