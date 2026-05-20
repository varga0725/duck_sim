import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from duck_agent_sim.agent.voice_control import LocalVoiceController

def test_parse_command_hungarian():
    """Tests if Hungarian spoken commands are correctly parsed into robot actions."""
    controller = LocalVoiceController()
    
    # Positive forward commands
    assert controller.parse_command("Menj előre kérlek") == "walk_forward"
    assert controller.parse_command("sétálj előre") == "walk_forward"
    assert controller.parse_command("előre") == "walk_forward"
    
    # Positive backward commands
    assert controller.parse_command("Menj hátra") == "walk_backward"
    assert controller.parse_command("sétálj hátra gyorsan") == "walk_backward"
    
    # Positive turn commands
    assert controller.parse_command("fordulj balra") == "turn_left"
    assert controller.parse_command("fordulj jobbra most") == "turn_right"
    
    # Positive stop and reset commands
    assert controller.parse_command("állj meg!") == "stop"
    assert controller.parse_command("indítsd újra a rendszert") == "reset"
    assert controller.parse_command("alaphelyzet") == "reset"
    
    # Positive follower commands
    assert controller.parse_command("kövesd a széket") == "follow_chair"
    assert controller.parse_command("keresd a széket") == "follow_chair"
    assert controller.parse_command("ne kövesd tovább") == "stop_following"
    assert controller.parse_command("állítsd le a követést") == "stop_following"

    # Negative / unmatched commands
    assert controller.parse_command("valami más szöveg") is None
    assert controller.parse_command("szeretem a kacsákat") is None


@pytest.mark.anyio
async def test_execute_action_mapping():
    """Tests if parsed actions call the underlying client API correctly."""
    controller = LocalVoiceController()
    
    # Mock the client endpoints
    controller.client.send_command = AsyncMock()
    controller.client.stop = AsyncMock()
    controller.client.reset = AsyncMock()
    controller.client.start_following = AsyncMock()
    controller.client.stop_following = AsyncMock()

    # Test walk_forward
    await controller.execute_action("walk_forward")
    controller.client.send_command.assert_called_with(command="walk_forward", speed=0.3, turn=0.0, duration_sec=1.5)
    
    # Test turn_left
    await controller.execute_action("turn_left")
    controller.client.send_command.assert_called_with(command="turn_left", speed=0.0, turn=0.4, duration_sec=1.2)

    # Test stop
    await controller.execute_action("stop")
    controller.client.stop.assert_called_once()

    # Test reset
    await controller.execute_action("reset")
    controller.client.reset.assert_called_once()

    # Test follow_chair
    await controller.execute_action("follow_chair")
    controller.client.start_following.assert_called_once()
    
    # Test stop_following
    await controller.execute_action("stop_following")
    controller.client.stop_following.assert_called_once()
