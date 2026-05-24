import os
import time
import numpy as np
import pytest
from unittest.mock import MagicMock

from duck_agent_sim.runtime.shared_telemetry_bus import SharedTelemetryBus
from duck_agent_sim.vision.perception_state import PerceptionState
from duck_agent_sim.services import SharedMemorySimulatorProxy

def test_frame_shared_memory_ipc():
    # Initialize a test bus that creates shared memory segments
    bus = SharedTelemetryBus(create=True, namespace="duck_test_frame_ipc")
    
    try:
        # Create a mock frame (640x480x3 uint8 array)
        np.random.seed(42)
        mock_frame = np.random.randint(0, 256, (480, 640, 3), dtype=np.uint8)
        
        # Write to shared memory
        frame_ref = bus.get_frame_ref()
        frame_ref.width = 640
        frame_ref.height = 480
        frame_ref.timestamp = 123.45
        
        import ctypes
        ctypes.memmove(frame_ref.frame_data, mock_frame.ctypes.data, mock_frame.size)
        
        # Read back from shared memory
        read_ref = bus.get_frame_ref()
        assert read_ref.width == 640
        assert read_ref.height == 480
        assert read_ref.timestamp == 123.45
        
        read_frame = np.frombuffer(read_ref.frame_data, dtype=np.uint8).reshape((480, 640, 3)).copy()
        assert np.array_equal(mock_frame, read_frame)
    finally:
        bus.close()

def test_detections_shared_memory_ipc():
    # Initialize a test bus
    bus = SharedTelemetryBus(create=True, namespace="duck_test_det_ipc")
    
    try:
        detections = [
            {"label": "chair", "confidence": 0.95, "bbox": [1.0, 2.0, 3.0, 4.0], "center": [1.5, 3.0], "tracking_id": 1},
            {"label": "person", "confidence": 0.82, "bbox": [10.0, 20.0, 30.0, 40.0], "center": [15.0, 30.0], "tracking_id": 2}
        ]
        
        # Write to shared memory
        vision_ref = bus.get_vision_ref()
        vision_ref.timestamp = 456.78
        vision_ref.fps = 12.5
        vision_ref.num_detections = len(detections)
        for i, det in enumerate(detections):
            det_struct = vision_ref.detections[i]
            det_struct.label = det["label"].encode("utf-8")
            det_struct.confidence = det["confidence"]
            for j in range(4):
                det_struct.bbox[j] = det["bbox"][j]
            for j in range(2):
                det_struct.center[j] = det["center"][j]
            det_struct.tracking_id = det["tracking_id"]
            
        # Read back from shared memory
        read_ref = bus.get_vision_ref()
        assert read_ref.timestamp == 456.78
        assert read_ref.fps == 12.5
        assert read_ref.num_detections == 2
        
        for i, expected in enumerate(detections):
            det_struct = read_ref.detections[i]
            assert det_struct.label.decode("utf-8").strip('\x00') == expected["label"]
            assert det_struct.confidence == expected["confidence"]
            assert list(det_struct.bbox) == expected["bbox"]
            assert list(det_struct.center) == expected["center"]
            assert det_struct.tracking_id == expected["tracking_id"]
    finally:
        bus.close()

def test_perception_state_multiprocess_routing(monkeypatch):
    monkeypatch.setenv("DUCK_MULTIPROCESS", "true")
    
    # Initialize a test bus
    bus = SharedTelemetryBus(create=True, namespace="duck_robot")
    
    try:
        state = PerceptionState()
        
        # Update using local list
        test_dets = [
            {"label": "sports_ball", "confidence": 0.99, "bbox": [5.0, 5.0, 10.0, 10.0], "center": [7.5, 7.5], "tracking_id": 99}
        ]
        state.update(test_dets, width=640, height=480)
        
        # Check that it wrote to shared memory
        vision_ref = bus.get_vision_ref()
        assert vision_ref.num_detections == 1
        assert vision_ref.detections[0].label.decode("utf-8").strip('\x00') == "sports_ball"
        assert vision_ref.detections[0].confidence == 0.99
        
        # Check that get_detections reads from shared memory
        read_dets = state.get_detections()
        assert len(read_dets) == 1
        assert read_dets[0]["label"] == "sports_ball"
        assert read_dets[0]["confidence"] == 0.99
        assert read_dets[0]["bbox"] == [5.0, 5.0, 10.0, 10.0]
        assert read_dets[0]["center"] == [7.5, 7.5]
        assert read_dets[0]["tracking_id"] == 99
        
        # Check get_summary reads from shared memory
        summary = state.get_summary()
        assert summary["num_objects"] == 1
        assert "sports_ball" in summary["labels"]
        assert 99 in summary["tracked_ids"]
    finally:
        bus.close()

def test_shared_memory_frame_buffer_proxy(monkeypatch):
    monkeypatch.setenv("DUCK_MULTIPROCESS", "true")
    
    # Initialize a test bus
    bus = SharedTelemetryBus(create=True, namespace="duck_robot")
    
    try:
        np.random.seed(100)
        mock_frame = np.random.randint(0, 256, (480, 640, 3), dtype=np.uint8)
        
        # Write mock frame to shared memory
        frame_ref = bus.get_frame_ref()
        frame_ref.width = 640
        frame_ref.height = 480
        frame_ref.timestamp = 999.9
        import ctypes
        ctypes.memmove(frame_ref.frame_data, mock_frame.ctypes.data, mock_frame.size)
        
        # Initialize proxy and read frame
        proxy = SharedMemorySimulatorProxy(namespace="duck_robot")
        frame_buffer = proxy.frame_buffer
        assert frame_buffer is not None
        
        retrieved_frame = frame_buffer.get()
        assert retrieved_frame is not None
        assert np.array_equal(mock_frame, retrieved_frame)
        
        proxy.close()
    finally:
        bus.close()

def test_api_endpoints_multiprocess(monkeypatch):
    monkeypatch.setenv("DUCK_MULTIPROCESS", "true")
    
    # Initialize a test bus
    bus = SharedTelemetryBus(create=True, namespace="duck_robot")
    
    try:
        # 1. Populate mock frame in shared memory
        np.random.seed(42)
        mock_frame = np.random.randint(0, 256, (480, 640, 3), dtype=np.uint8)
        frame_ref = bus.get_frame_ref()
        frame_ref.width = 640
        frame_ref.height = 480
        frame_ref.timestamp = time.time()
        import ctypes
        ctypes.memmove(frame_ref.frame_data, mock_frame.ctypes.data, mock_frame.size)
        
        # 2. Populate mock detections in shared memory
        vision_ref = bus.get_vision_ref()
        vision_ref.timestamp = time.time()
        vision_ref.fps = 15.0
        vision_ref.num_detections = 1
        
        det_struct = vision_ref.detections[0]
        det_struct.label = b"chair"
        det_struct.confidence = 0.92
        det_struct.bbox[0], det_struct.bbox[1], det_struct.bbox[2], det_struct.bbox[3] = 100.0, 200.0, 300.0, 400.0
        det_struct.center[0], det_struct.center[1] = 200.0, 300.0
        det_struct.tracking_id = 42
        
        # 3. Create FastAPI test client
        from fastapi.testclient import TestClient
        from duck_agent_sim.main import app
        
        # Clear/force app_context restart under multiprocess env
        from duck_agent_sim.services import app_context
        app_context.shutdown()
        app_context.start()
        
        with TestClient(app) as client:
            # Test /vision/frame
            response = client.get("/vision/frame")
            assert response.status_code == 200
            assert response.headers["content-type"] == "image/jpeg"
            assert len(response.content) > 0
            
            # Test /vision/detections
            response = client.get("/vision/detections")
            assert response.status_code == 200
            data = response.json()
            assert "objects" in data
            assert len(data["objects"]) == 1
            assert data["objects"][0]["label"] == "chair"
            assert data["objects"][0]["confidence"] == 0.92
            assert data["objects"][0]["tracking_id"] == 42
            
            # Test /vision/state
            response = client.get("/vision/state")
            assert response.status_code == 200
            state = response.json()
            assert state["num_objects"] == 1
            assert "chair" in state["labels"]
            assert state["vision_fps"] == 15.0
            
    finally:
        # Shutdown and restore single-process mode
        from duck_agent_sim.services import app_context
        app_context.shutdown()
        
        # Restore environment variable
        monkeypatch.delenv("DUCK_MULTIPROCESS", raising=False)
        app_context.start()
        
        bus.close()
