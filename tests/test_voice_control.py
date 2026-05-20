import pytest
import re
from unittest.mock import AsyncMock, MagicMock, patch
from duck_agent_sim.agent.voice_control import LocalVoiceController, COMMAND_MAP


def test_hungarian_command_regex_patterns():
    """Verify that Hungarian spoken commands are correctly recognized by COMMAND_MAP regexes."""
    
    # walk_forward
    assert COMMAND_MAP["walk_forward"].search("Menj előre kérlek") is not None
    assert COMMAND_MAP["walk_forward"].search("sétálj előre") is not None
    assert COMMAND_MAP["walk_forward"].search("előre") is not None
    
    # walk_backward
    assert COMMAND_MAP["walk_backward"].search("Menj hátra") is not None
    assert COMMAND_MAP["walk_backward"].search("sétálj hátra gyorsan") is not None
    
    # turn_left
    assert COMMAND_MAP["turn_left"].search("fordulj balra") is not None
    assert COMMAND_MAP["turn_left"].search("menj balra") is not None
    
    # turn_right
    assert COMMAND_MAP["turn_right"].search("fordulj jobbra most") is not None
    
    # stop
    assert COMMAND_MAP["stop"].search("állj meg!") is not None
    assert COMMAND_MAP["stop"].search("stop") is not None
    
    # reset
    assert COMMAND_MAP["reset"].search("indítsd újra a rendszert") is not None
    assert COMMAND_MAP["reset"].search("alaphelyzet") is not None
    
    # follow_chair
    assert COMMAND_MAP["follow_chair"].search("kövesd a széket") is not None
    assert COMMAND_MAP["follow_chair"].search("keresd a széket") is not None
    
    # stop_following
    assert COMMAND_MAP["stop_following"].search("ne kövesd tovább") is not None
    assert COMMAND_MAP["stop_following"].search("állítsd le a követést") is not None


def test_resolve_device():
    """Tests if audio devices are correctly resolved by integer or name substring matching."""
    controller = LocalVoiceController()
    
    # Test direct integer string
    assert controller.resolve_device("3") == 3
    
    # Test name match with mock list
    with patch("speech_recognition.Microphone.list_microphone_names", return_value=["Default", "iPhone Microphone", "External Mic"]):
        assert controller.resolve_device("iPhone") == 1
        assert controller.resolve_device("External") == 2
        assert controller.resolve_device("Nonexistent") is None


@pytest.mark.anyio
async def test_start_voice_loop_calls_agent():
    """Verify that start_voice_loop pre-warms the agent, transcribes input, routes to DuckAgent, and speaks response."""
    controller = LocalVoiceController(live=False)
    
    # Mock DuckAgent methods
    controller.agent.start = AsyncMock()
    controller.agent.stop = AsyncMock()
    
    mock_response = MagicMock()
    mock_response.source = "direct"
    mock_response.action = "walk_forward"
    mock_response.latency_ms = 50.0
    mock_response.hermes_raw = ""
    mock_response.success = True
    mock_response.speech = "Haladok előre."
    
    controller.agent.process_with_intent = AsyncMock(return_value=(None, mock_response))
    
    # Mock listen_and_process_sync to yield one command then raise KeyboardInterrupt to exit loop
    controller.listen_and_process_sync = MagicMock(side_effect=["menj előre", KeyboardInterrupt])
    controller.speak = MagicMock()
    
    with pytest.raises(SystemExit):
        with patch("sys.exit") as mock_exit:
            mock_exit.side_effect = SystemExit(0)
            await controller.start_voice_loop()
            
    controller.agent.start.assert_awaited_once()
    controller.agent.process_with_intent.assert_awaited_once_with("menj előre")
    controller.speak.assert_called_once_with("Haladok előre.")
    controller.agent.stop.assert_awaited_once()
