from fastapi.testclient import TestClient
from duck_agent_sim.main import app
from duck_agent_sim.simulator.instance import active_simulator
from duck_agent_sim.simulator.policy_contract import POLICY_COMMAND_LIMITS

client = TestClient(app)

def test_api_health():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["robot"] == "open_duck_mini_v2"
    assert data["sim_mode"] in ("mock", "real")

def test_api_state():
    response = client.get("/state")
    assert response.status_code == 200
    data = response.json()
    assert data["robot"] == "open_duck_mini_v2"
    assert "position" in data
    assert "orientation" in data
    assert data["stability"]["status"] in ("stable", "unstable", "fallen")
    assert isinstance(data["stability"]["reasons"], list)
    assert "min_body_height_m" in data["stability"]
    assert data["stability"]["thresholds"]["max_roll_deg"] == 35.0
    assert data["stability"]["thresholds"]["max_pitch_deg"] == 35.0


def test_camera_info_mock_contract():
    response = client.get("/camera/info")
    assert response.status_code == 200
    data = response.json()

    assert data["mode"] == "mock"
    assert data["width"] == 640
    assert data["height"] == 480
    assert data["camera_frame"] == "mock_camera"
    assert data["calibrated"] is True
    assert data["fovy"] == 45.0
    assert data["intrinsics"]["cx"] == 320.0
    assert data["intrinsics"]["cy"] == 240.0
    assert data["intrinsics"]["fx"] == data["intrinsics"]["fy"]
    assert data["distortion"] is None
    assert data["extrinsics"]["reference_frame"] == "mock_world"
    assert data["extrinsics"]["translation_m"] == [0.0, 0.0, 0.0]
    assert data["extrinsics"]["quaternion_wxyz"] == [1.0, 0.0, 0.0, 0.0]


def test_camera_info_webcam_marks_uncalibrated(monkeypatch):
    from duck_agent_sim.bridge import api

    monkeypatch.setattr(api, "DUCK_SIM_MODE", "webcam")
    response = client.get("/camera/info")
    assert response.status_code == 200
    data = response.json()

    assert data["mode"] == "webcam"
    assert data["width"] == 640
    assert data["height"] == 480
    assert data["camera_frame"] == "webcam"
    assert data["calibrated"] is False
    assert data["fovy"] is None
    assert data["intrinsics"] is None
    assert data["distortion"] is None
    assert data["extrinsics"] is None


def test_camera_info_real_fpv_contract(monkeypatch):
    from duck_agent_sim.bridge import api

    monkeypatch.setattr(api, "DUCK_SIM_MODE", "real")
    response = client.get("/camera/info")
    assert response.status_code == 200
    data = response.json()

    assert data["mode"] == "real"
    assert data["width"] == 640
    assert data["height"] == 480
    assert data["camera_frame"] == "fpv"
    assert data["calibrated"] is True
    assert data["fovy"] == 45.0
    assert data["intrinsics"]["cx"] == 320.0
    assert data["intrinsics"]["cy"] == 240.0
    assert round(data["intrinsics"]["fx"], 6) == round(data["intrinsics"]["fy"], 6)
    assert data["distortion"] is None
    assert data["extrinsics"]["reference_frame"] == "head_assembly"
    assert data["extrinsics"]["translation_m"] == [0.08, 0.0, 0.05]
    assert data["extrinsics"]["quaternion_wxyz"] == [0.70710678, 0.0, -0.0, -0.70710678]

def test_api_stop():
    response = client.post("/stop")
    assert response.status_code == 200
    data = response.json()
    assert data["stopped"] is True
    assert data["state"]["status"] == "stopped"

def test_api_reset():
    response = client.post("/reset")
    assert response.status_code == 200
    data = response.json()
    assert data["reset"] is True
    assert data["state"]["status"] == "idle"

def test_api_command_execution():
    # Only verify behavior if mock mode is running to ensure deterministic pass
    response = client.get("/health")
    if response.json()["sim_mode"] == "mock":
        # Reset simulator
        client.post("/reset")
        
        # Send command
        payload = {
            "command": "walk_forward",
            "speed": 0.25,
            "turn": 0.0,
            "duration_sec": 1.0,
            "safety": {
                "stop_on_fall": True,
                "max_pitch_deg": 35,
                "max_roll_deg": 35
            }
        }
        res = client.post("/command", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert data["accepted"] is True
        assert data["command"] == "walk_forward"
        assert data["mapped_control"]["linear_x"] == POLICY_COMMAND_LIMITS.linear_x[1]
        assert data["state"]["status"] == "walking"
        # Since it walked forward, position x should have advanced
        assert data["state"]["position"][0] > 0.0

def test_api_walk_square_scenario():
    response = client.get("/health")
    if response.json()["sim_mode"] == "mock":
        res = client.post("/scenario/walk-square")
        assert res.status_code == 200
        data = res.json()
        assert data["scenario"] == "walk_square"
        assert data["success"] is True
        assert len(data["steps_executed"]) == 8
