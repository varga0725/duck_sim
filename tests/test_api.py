from fastapi.testclient import TestClient
from duck_agent_sim.main import app
from duck_agent_sim.simulator.instance import active_simulator

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
        assert data["mapped_control"]["linear_x"] == 0.25
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
