"""
Tests for DirectController — verifies that Intent → Bridge API calls
produce correct AgentResponse envelopes without hitting a real simulator.
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from duck_agent_sim.agent.direct_controller import DirectController
from duck_agent_sim.agent.smart_router import Intent
from duck_agent_sim.schemas import RobotState, CommandResponse, ControlIntent


def _mock_robot_state(**overrides) -> RobotState:
    """Build a minimal RobotState for testing."""
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
def controller():
    ctrl = DirectController("http://127.0.0.1:8765")
    return ctrl


class TestMotorExecution:
    """Motor commands produce correct AgentResponse with source='direct'."""

    @pytest.mark.asyncio
    async def test_walk_forward(self, controller):
        controller.client.send_command = AsyncMock(
            return_value=_mock_command_response("walk_forward")
        )
        intent = Intent(action="walk_forward", route="direct", raw_text="előre")
        resp = await controller.execute(intent)

        assert resp.success is True
        assert resp.source == "direct"
        assert resp.action == "walk_forward"
        assert resp.speech == "Előrehaladok."
        assert resp.latency_ms >= 0
        assert resp.robot_state is not None
        controller.client.send_command.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_walk_backward(self, controller):
        controller.client.send_command = AsyncMock(
            return_value=_mock_command_response("walk_backward")
        )
        intent = Intent(action="walk_backward", route="direct", raw_text="hátra")
        resp = await controller.execute(intent)

        assert resp.success is True
        assert resp.action == "walk_backward"
        assert resp.speech == "Hátrahaladok."

    @pytest.mark.asyncio
    async def test_turn_left(self, controller):
        controller.client.send_command = AsyncMock(
            return_value=_mock_command_response("turn_left")
        )
        intent = Intent(action="turn_left", route="direct", raw_text="balra")
        resp = await controller.execute(intent)

        assert resp.success is True
        assert resp.action == "turn_left"
        assert resp.speech == "Balra fordulok."

    @pytest.mark.asyncio
    async def test_turn_right(self, controller):
        controller.client.send_command = AsyncMock(
            return_value=_mock_command_response("turn_right")
        )
        intent = Intent(action="turn_right", route="direct", raw_text="jobbra")
        resp = await controller.execute(intent)

        assert resp.success is True
        assert resp.action == "turn_right"
        assert resp.speech == "Jobbra fordulok."

    @pytest.mark.asyncio
    async def test_stop(self, controller):
        controller.client.send_command = AsyncMock(
            return_value=_mock_command_response("stop")
        )
        intent = Intent(action="stop", route="direct", raw_text="állj")
        resp = await controller.execute(intent)

        assert resp.success is True
        assert resp.action == "stop"
        assert resp.speech == "Megálltam."


class TestSpecialActions:
    """Non-motor actions: reset, follow, stop_following."""

    @pytest.mark.asyncio
    async def test_reset(self, controller):
        controller.client.reset = AsyncMock(
            return_value=_mock_robot_state(status="idle")
        )
        intent = Intent(action="reset", route="direct", raw_text="reset")
        resp = await controller.execute(intent)

        assert resp.success is True
        assert resp.action == "reset"
        assert resp.speech == "Alaphelyzet visszaállítva."
        controller.client.reset.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_follow_target(self, controller):
        controller.client.start_following = AsyncMock(
            return_value={"status": "started"}
        )
        intent = Intent(
            action="follow_target",
            route="direct",
            params={"target_label": "chair"},
            raw_text="kövesd a széket",
        )
        resp = await controller.execute(intent)

        assert resp.success is True
        assert resp.action == "follow_target"
        assert "chair" in resp.speech
        controller.client.start_following.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_stop_following(self, controller):
        controller.client.stop_following = AsyncMock(
            return_value={"status": "stopped"}
        )
        intent = Intent(
            action="stop_following", route="direct", raw_text="ne kövesd"
        )
        resp = await controller.execute(intent)

        assert resp.success is True
        assert resp.action == "stop_following"
        assert resp.speech == "Követés leállítva."


class TestErrorHandling:
    """Errors should produce success=False with an error message."""

    @pytest.mark.asyncio
    async def test_network_error(self, controller):
        controller.client.send_command = AsyncMock(
            side_effect=ConnectionError("Connection refused")
        )
        intent = Intent(action="walk_forward", route="direct", raw_text="előre")
        resp = await controller.execute(intent)

        assert resp.success is False
        assert "Connection refused" in resp.error
        assert resp.speech == "Hiba történt."

    @pytest.mark.asyncio
    async def test_unknown_action(self, controller):
        intent = Intent(action="fly_to_moon", route="direct", raw_text="repülj a holdra")
        resp = await controller.execute(intent)

        assert resp.success is False
        assert "Unknown" in resp.error


class TestLatencyMeasurement:
    """Latency should always be reported and non-negative."""

    @pytest.mark.asyncio
    async def test_latency_is_measured(self, controller):
        controller.client.send_command = AsyncMock(
            return_value=_mock_command_response("walk_forward")
        )
        intent = Intent(action="walk_forward", route="direct", raw_text="előre")
        resp = await controller.execute(intent)

        assert resp.latency_ms >= 0
        assert isinstance(resp.latency_ms, float)
