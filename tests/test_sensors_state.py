from fastapi.testclient import TestClient

from duck_agent_sim.config import DUCK_SIM_MODE
from duck_agent_sim.main import app
from duck_agent_sim.schemas import SensorAvailability, SensorsState


import pytest

@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def test_sensors_state_schema_marks_unavailable_values_as_null():
    sensors = SensorsState(
        mode="mock",
        sim_time=1.25,
        timestamp=123.0,
        imu=SensorAvailability(available=False),
        feet={
            "left": SensorAvailability(available=False),
            "right": SensorAvailability(available=False),
        },
    )

    data = sensors.model_dump()

    assert data["mode"] == "mock"
    assert data["imu"]["available"] is False
    assert data["imu"]["gyro"] is None
    assert data["imu"]["orientation"] is None
    assert data["feet"]["left"]["available"] is False
    assert data["feet"]["left"]["position"] is None
    assert data["feet"]["right"]["velocity"] is None


def test_get_sensors_state_mock_or_webcam_returns_explicit_unavailable_raw_sensor_contract(client):
    response = client.get("/sensors/state")

    assert response.status_code == 200
    data = response.json()
    assert data["robot"] == "open_duck_mini_v2"
    assert data["mode"] == DUCK_SIM_MODE
    assert isinstance(data["sim_time"], (int, float))
    assert isinstance(data["timestamp"], (int, float))

    if DUCK_SIM_MODE in ("mock", "webcam"):
        assert data["imu"]["available"] is False
        for field in (
            "gyro",
            "accelerometer",
            "local_linvel",
            "global_linvel",
            "global_angvel",
            "position",
            "orientation",
            "upvector",
            "forwardvector",
        ):
            assert data["imu"][field] is None

        assert set(data["feet"].keys()) == {"left", "right"}
        for foot in ("left", "right"):
            assert data["feet"][foot]["available"] is False
            assert data["feet"][foot]["position"] is None
            assert data["feet"][foot]["velocity"] is None
            assert data["feet"][foot]["axis"] is None
            assert data["feet"][foot]["upvector"] is None


def test_get_sensors_state_real_contract_shape_when_available(client):
    response = client.get("/sensors/state")

    assert response.status_code == 200
    data = response.json()
    if data["mode"] != "real" or data["imu"]["available"] is not True:
        return

    assert len(data["imu"]["gyro"]) == 3
    assert len(data["imu"]["accelerometer"]) == 3
    assert len(data["imu"]["local_linvel"]) == 3
    assert len(data["imu"]["global_linvel"]) == 3
    assert len(data["imu"]["global_angvel"]) == 3
    assert len(data["imu"]["position"]) == 3
    assert len(data["imu"]["orientation"]) == 4
    assert len(data["imu"]["upvector"]) == 3
    assert len(data["imu"]["forwardvector"]) == 3

    for foot in ("left", "right"):
        assert data["feet"][foot]["available"] is True
        assert len(data["feet"][foot]["position"]) == 3
        assert len(data["feet"][foot]["velocity"]) == 3
        assert len(data["feet"][foot]["axis"]) == 3
