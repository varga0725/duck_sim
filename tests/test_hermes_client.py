import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from duck_agent_sim.agent.hermes_client import HermesRobotClient
from duck_agent_sim.schemas import RobotState, Orientation, FeetContact, StabilityState


@pytest.mark.anyio
async def test_hermes_client_initialization():
    client = HermesRobotClient(base_url="http://127.0.0.1:8765")
    assert client.base_url == "http://127.0.0.1:8765"
    assert client.ws_url == "ws://127.0.0.1:8765/ws"
    await client.close()


@pytest.mark.anyio
@patch("httpx.AsyncClient.get")
async def test_hermes_client_get_state(mock_get):
    # Construct a valid RobotState JSON response
    mock_state_data = {
        "robot": "open_duck_mini_v2",
        "status": "idle",
        "sim_time": 10.5,
        "position": (0.1, 0.2, 0.15),
        "orientation": {
            "roll_deg": 1.2,
            "pitch_deg": -0.5,
            "yaw_deg": 45.0,
        },
        "feet_contact": {
            "left": True,
            "right": True,
        },
        "fallen": False,
        "last_command": "stop",
        "stability": {
            "status": "stable",
            "reasons": [],
            "min_body_height_m": 0.15,
            "thresholds": {
                "max_roll_deg": 35.0,
                "max_pitch_deg": 35.0,
                "min_body_height_m": 0.15,
                "agent_preflight_min_body_height_m": 0.25,
                "require_feet_contact": False,
            },
            "internal_fallen_min_body_height_m": 0.15,
            "agent_preflight_min_body_height_m": 0.25,
        }
    }

    mock_response = MagicMock()
    mock_response.json.return_value = mock_state_data
    mock_response.raise_for_status = MagicMock()
    mock_get.return_value = mock_response

    async with HermesRobotClient(base_url="http://127.0.0.1:8765") as client:
        state = await client.get_state()
        assert isinstance(state, RobotState)
        assert state.robot == "open_duck_mini_v2"
        assert state.status == "idle"
        assert state.sim_time == 10.5
        assert state.position == (0.1, 0.2, 0.15)
        assert state.orientation.yaw_deg == 45.0
        assert state.fallen is False


@pytest.mark.anyio
async def test_hermes_client_callbacks_triggering():
    client = HermesRobotClient(base_url="http://127.0.0.1:8765")
    
    # Track callback execution
    telemetry_received = []
    fall_received = []
    status_changes = []

    client.on_telemetry(lambda s: telemetry_received.append(s))
    client.on_fall(lambda s: fall_received.append(s))
    client.on_status_change(lambda old, new: status_changes.append((old, new)))

    # Initial state (None to State 1)
    state1 = RobotState(
        robot="open_duck_mini_v2",
        status="idle",
        sim_time=1.0,
        position=(0.0, 0.0, 0.15),
        orientation=Orientation(roll_deg=0.0, pitch_deg=0.0, yaw_deg=0.0),
        feet_contact=FeetContact(left=True, right=True),
        fallen=False,
        last_command="stop"
    )
    client._update_internal_state(state1)

    # Initial state transition doesn't trigger callbacks (since _last_state was None)
    assert len(telemetry_received) == 0
    assert len(fall_received) == 0
    assert len(status_changes) == 0

    # Transition to State 2 (stable -> walking)
    state2 = RobotState(
        robot="open_duck_mini_v2",
        status="walking",
        sim_time=2.0,
        position=(0.1, 0.0, 0.15),
        orientation=Orientation(roll_deg=0.0, pitch_deg=0.0, yaw_deg=0.0),
        feet_contact=FeetContact(left=True, right=True),
        fallen=False,
        last_command="walk_forward"
    )
    client._update_internal_state(state2)

    assert len(fall_received) == 0
    assert len(status_changes) == 1
    assert status_changes[0] == ("idle", "walking")

    # Transition to State 3 (walking -> fallen)
    state3 = RobotState(
        robot="open_duck_mini_v2",
        status="fallen",
        sim_time=3.0,
        position=(0.1, 0.0, 0.05),
        orientation=Orientation(roll_deg=45.0, pitch_deg=0.0, yaw_deg=0.0),
        feet_contact=FeetContact(left=False, right=False),
        fallen=True,
        last_command="walk_forward"
    )
    client._update_internal_state(state3)

    assert len(fall_received) == 1
    assert fall_received[0].sim_time == 3.0
    assert len(status_changes) == 2
    assert status_changes[1] == ("walking", "fallen")

    await client.close()

