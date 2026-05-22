"""
Integration tests for DuckAgent — end-to-end from text input to AgentResponse.

Uses mocked Bridge API and Hermes to test the full routing pipeline:
    Input → SmartRouter → Direct/Hermes → AgentResponse
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from duck_agent_sim.agent.duck_agent import DuckAgent
from duck_agent_sim.schemas import RobotState, CommandResponse, ControlIntent, Orientation


def _mock_robot_state(**overrides) -> RobotState:
    defaults = {
        "robot": "open_duck_mini_v2",
        "status": "idle",
        "sim_time": 0.0,
        "position": (0.0, 0.0, 0.41),
        "fallen": False,
        "last_command": "stop",
    }
    defaults.update(overrides)
    return RobotState(**defaults)


def _mock_command_response(command: str = "walk_forward") -> CommandResponse:
    return CommandResponse(
        accepted=True,
        command=command,
        mapped_control=ControlIntent(linear_x=0.3, linear_y=0.0, yaw=0.0),
        state=_mock_robot_state(status="walking", last_command=command),
    )


@pytest.fixture
def agent():
    """Create a DuckAgent with mocked subsystems."""
    a = DuckAgent(bridge_url="http://127.0.0.1:8765", hermes_mode="oneshot")
    # Mock the direct controller's client
    a.direct.client.send_command = AsyncMock(
        return_value=_mock_command_response("walk_forward")
    )
    a.direct.client.reset = AsyncMock(
        return_value=_mock_robot_state(status="idle")
    )
    a.direct.client.stop = AsyncMock(
        return_value=_mock_robot_state(status="stopped")
    )
    a.direct.client.start_following = AsyncMock(
        return_value={"status": "started"}
    )
    a.direct.client.stop_following = AsyncMock(
        return_value={"status": "stopped"}
    )

    # Mock the local agent client (used for A2A and local navigation checks)
    from duck_agent_sim.schemas import SensorsState, SensorAvailability
    a._agent.client.get_state = AsyncMock(
        return_value=_mock_robot_state(status="idle")
    )
    a._agent.client.get_sensors_state = AsyncMock(
        return_value=SensorsState(
            mode="mock",
            sim_time=0.0,
            timestamp=0.0,
            imu=SensorAvailability(available=False),
            feet={
                "left": SensorAvailability(available=False),
                "right": SensorAvailability(available=False),
            },
        )
    )
    a._agent.client.get_map = AsyncMock(
        return_value={"grid": [[0]*80]*80, "resolution": 0.1, "grid_size": 80, "landmarks": {}}
    )
    a._agent.client.send_command = AsyncMock(
        return_value=_mock_command_response("walk_forward")
    )
    a._agent.client.reset = AsyncMock(
        return_value=_mock_robot_state(status="idle")
    )
    a._agent.client.stop = AsyncMock(
        return_value=_mock_robot_state(status="stopped")
    )
    return a


class TestDirectRouting:
    """Simple commands should be handled by DirectController (source='direct')."""

    @pytest.mark.asyncio
    async def test_elore_routes_direct(self, agent):
        resp = await agent.process("előre")
        assert resp.source == "direct"
        assert resp.action == "walk_forward"
        assert resp.success is True
        assert resp.latency_ms < 1000  # should be very fast with mocks

    @pytest.mark.asyncio
    async def test_hatra_routes_direct(self, agent):
        agent.direct.client.send_command = AsyncMock(
            return_value=_mock_command_response("walk_backward")
        )
        resp = await agent.process("hátra")
        assert resp.source == "direct"
        assert resp.action == "walk_backward"

    @pytest.mark.asyncio
    async def test_balra_routes_direct(self, agent):
        agent.direct.client.send_command = AsyncMock(
            return_value=_mock_command_response("turn_left")
        )
        resp = await agent.process("balra")
        assert resp.source == "direct"
        assert resp.action == "turn_left"

    @pytest.mark.asyncio
    async def test_stop_routes_direct(self, agent):
        agent.direct.client.send_command = AsyncMock(
            return_value=_mock_command_response("stop")
        )
        resp = await agent.process("állj meg")
        assert resp.source == "direct"
        assert resp.action == "stop"

    @pytest.mark.asyncio
    async def test_reset_routes_direct(self, agent):
        resp = await agent.process("reset")
        assert resp.source == "direct"
        assert resp.action == "reset"

    @pytest.mark.asyncio
    async def test_follow_routes_direct(self, agent):
        resp = await agent.process("kövesd a széket")
        assert resp.source == "direct"
        assert resp.action == "follow_target"


class TestHermesRouting:
    """Complex queries should be delegated to Hermes (source='hermes')."""

    @pytest.mark.asyncio
    async def test_mit_latsz_routes_hermes(self, agent):
        # Mock the Hermes delegator
        agent.hermes.delegate = AsyncMock(
            return_value=MagicMock(
                action="hermes_chat",
                source="hermes",
                hermes_raw="Egy széket és egy asztalt látok.",
                speech="Egy széket és egy asztalt látok.",
                latency_ms=2500.0,
                success=True,
            )
        )
        resp = await agent.process("mit látsz?")
        assert resp.source == "hermes"
        agent.hermes.delegate.assert_awaited_once()
        called_arg = agent.hermes.delegate.call_args[0][0]
        assert "A2A_PROTOCOL_REQUEST" in called_arg
        assert "mit látsz?" in called_arg

    @pytest.mark.asyncio
    async def test_unknown_routes_hermes(self, agent):
        agent.hermes.delegate = AsyncMock(
            return_value=MagicMock(
                action="hermes_chat",
                source="hermes",
                hermes_raw="Nem értem pontosan, mit szeretnél.",
                speech="Nem értem pontosan, mit szeretnél.",
                latency_ms=3000.0,
                success=True,
            )
        )
        resp = await agent.process("zsiráf pingvin delfin")
        assert resp.source == "hermes"
        agent.hermes.delegate.assert_awaited_once()
        called_arg = agent.hermes.delegate.call_args[0][0]
        assert "A2A_PROTOCOL_REQUEST" in called_arg
        assert "zsiráf pingvin delfin" in called_arg


class TestProcessWithIntent:
    """process_with_intent should return both Intent and AgentResponse."""

    @pytest.mark.asyncio
    async def test_returns_intent_and_response(self, agent):
        intent, resp = await agent.process_with_intent("előre")
        assert intent.action == "walk_forward"
        assert intent.route == "direct"
        assert resp.source == "direct"
        assert resp.success is True

    @pytest.mark.asyncio
    async def test_hermes_intent_and_response(self, agent):
        agent.hermes.delegate = AsyncMock(
            return_value=MagicMock(
                action="hermes_chat",
                source="hermes",
                success=True,
            )
        )
        intent, resp = await agent.process_with_intent("hol vagyok?")
        assert intent.action == "hermes_chat"
        assert intent.route == "hermes"
        assert resp.source == "hermes"


class TestSpeechOutput:
    """Every response should include a Hungarian speech string."""

    @pytest.mark.asyncio
    async def test_direct_commands_have_speech(self, agent):
        for text in ["előre", "hátra", "balra", "jobbra", "állj", "reset"]:
            if text in ("hátra", "balra", "jobbra", "állj"):
                agent.direct.client.send_command = AsyncMock(
                    return_value=_mock_command_response(text)
                )
            resp = await agent.process(text)
            assert resp.speech is not None
            assert len(resp.speech) > 0


class TestLocalNavigationHeuristics:
    """Tests the local navigation heuristics of LocalDuckAgent when a landmark is known."""

    @pytest.mark.asyncio
    async def test_navigate_to_known_landmark_turn(self, agent):
        # Landmark is chair at (2.0, 2.0). Robot is at (0.0, 0.0) with yaw = 0.
        # Yaw diff is 45 degrees, which is > 15 deg. Should turn left.
        agent._agent.client.get_map = AsyncMock(
            return_value={
                "grid": [[0]*80]*80,
                "resolution": 0.1,
                "grid_size": 80,
                "landmarks": {
                    "chair": {"x": 2.0, "y": 2.0, "confidence": 0.9}
                }
            }
        )
        agent._agent.client.get_state = AsyncMock(
            return_value=_mock_robot_state(position=(0.0, 0.0, 0.41), orientation=Orientation(yaw_deg=0.0))
        )
        agent._agent.client.send_command = AsyncMock(
            return_value=_mock_command_response("turn_left")
        )
        
        resp = await agent.process("kövesd a széket")
        assert resp.source == "direct"
        assert resp.action == "turn_left"
        assert "Fordulok a chair felé" in resp.speech
        agent._agent.client.send_command.assert_called_once()
        kwargs = agent._agent.client.send_command.call_args[1]
        assert kwargs["command"] == "turn_left"
        assert kwargs["speed"] == 0.0
        assert kwargs["turn"] == 0.4
        assert abs(kwargs["duration_sec"] - 1.0) < 1e-5

    @pytest.mark.asyncio
    async def test_navigate_to_known_landmark_walk(self, agent):
        # Landmark is chair at (2.0, 0.0). Robot is at (0.0, 0.0) with yaw = 0.
        # Yaw diff is 0. Should walk forward.
        agent._agent.client.get_map = AsyncMock(
            return_value={
                "grid": [[0]*80]*80,
                "resolution": 0.1,
                "grid_size": 80,
                "landmarks": {
                    "chair": {"x": 2.0, "y": 0.0, "confidence": 0.9}
                }
            }
        )
        agent._agent.client.get_state = AsyncMock(
            return_value=_mock_robot_state(position=(0.0, 0.0, 0.41), orientation=Orientation(yaw_deg=0.0))
        )
        agent._agent.client.send_command = AsyncMock(
            return_value=_mock_command_response("walk_forward")
        )
        
        resp = await agent.process("menj a székhez")
        assert resp.source == "direct"
        assert resp.action == "walk_forward"
        assert "Közeledem a chair-hoz" in resp.speech
        agent._agent.client.send_command.assert_called_once()
        kwargs = agent._agent.client.send_command.call_args[1]
        assert kwargs["command"] == "walk_forward"
        assert kwargs["speed"] == 0.3
        assert kwargs["turn"] == 0.0
        assert abs(kwargs["duration_sec"] - 2.0) < 1e-5

    @pytest.mark.asyncio
    async def test_navigate_to_known_landmark_stop(self, agent):
        # Landmark is chair at (0.2, 0.0). Robot is at (0.0, 0.0) with yaw = 0.
        # Distance is 0.2m (< 0.3m). Should stop.
        agent._agent.client.get_map = AsyncMock(
            return_value={
                "grid": [[0]*80]*80,
                "resolution": 0.1,
                "grid_size": 80,
                "landmarks": {
                    "chair": {"x": 0.2, "y": 0.0, "confidence": 0.9}
                }
            }
        )
        agent._agent.client.get_state = AsyncMock(
            return_value=_mock_robot_state(position=(0.0, 0.0, 0.41), orientation=Orientation(yaw_deg=0.0))
        )
        
        resp = await agent.process("menj a székhez")
        assert resp.source == "direct"
        assert resp.action == "stop"
        assert "Megérkeztem a chair közelébe" in resp.speech
        agent._agent.client.stop.assert_called_once()

