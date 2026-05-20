"""
DirectController — zero-LLM command executor.

Maps classified Intent actions to HermesRobotClient calls with sub-100ms
latency.  Every action produces a Hungarian speech string for TTS feedback.
"""

import logging
import time
from typing import Dict, Any, Optional

from duck_agent_sim.agent.hermes_client import HermesRobotClient
from duck_agent_sim.agent.agent_response import AgentResponse
from duck_agent_sim.agent.smart_router import Intent
from duck_agent_sim.schemas import FollowerConfigSchema

logger = logging.getLogger("direct-controller")


# Default motion parameters per action
_MOTION_DEFAULTS: Dict[str, Dict[str, Any]] = {
    "walk_forward": {"command": "walk_forward", "speed": 0.3, "turn": 0.0, "duration_sec": 1.5},
    "walk_backward": {"command": "walk_backward", "speed": 0.3, "turn": 0.0, "duration_sec": 1.5},
    "turn_left": {"command": "turn_left", "speed": 0.0, "turn": 0.4, "duration_sec": 1.2},
    "turn_right": {"command": "turn_right", "speed": 0.0, "turn": -0.4, "duration_sec": 1.2},
    "stop": {"command": "stop", "speed": 0.0, "turn": 0.0, "duration_sec": 0.5},
    "reset": None,  # handled separately via client.reset()
}

# Hungarian TTS responses per action
_ACTION_SPEECH: Dict[str, str] = {
    "walk_forward": "Előrehaladok.",
    "walk_backward": "Hátrahaladok.",
    "turn_left": "Balra fordulok.",
    "turn_right": "Jobbra fordulok.",
    "stop": "Megálltam.",
    "reset": "Alaphelyzet visszaállítva.",
    "follow_target": "Követem a célpontot.",
    "stop_following": "Követés leállítva.",
}


class DirectController:
    """
    Executes simple robot commands directly via the Bridge API without
    involving any LLM.  Designed for <100ms round-trip on local connections.

    Usage::

        ctrl = DirectController("http://127.0.0.1:8765")
        response = await ctrl.execute(intent)
    """

    def __init__(self, bridge_url: str = "http://127.0.0.1:8765"):
        self.client = HermesRobotClient(base_url=bridge_url)

    async def execute(self, intent: Intent) -> AgentResponse:
        """
        Execute an Intent that was routed to ``direct``.

        Returns an :class:`AgentResponse` with robot state, speech text,
        and measured latency.
        """
        t0 = time.perf_counter()

        try:
            if intent.action == "reset":
                state = await self.client.reset()
                return self._ok(intent, state, t0)

            if intent.action == "follow_target":
                return await self._start_follow(intent, t0)

            if intent.action == "stop_following":
                return await self._stop_follow(intent, t0)

            # Standard motor commands
            params = _MOTION_DEFAULTS.get(intent.action)
            if params is None:
                return self._error(intent, f"Unknown direct action: {intent.action}", t0)

            response = await self.client.send_command(**params)
            return self._ok(intent, response.state, t0)

        except Exception as exc:
            logger.error("DirectController error for %s: %s", intent.action, exc)
            return self._error(intent, str(exc), t0)

    # ──────────────────────────────────────────────────────
    # Vision follower shortcuts
    # ──────────────────────────────────────────────────────

    async def _start_follow(self, intent: Intent, t0: float) -> AgentResponse:
        target_label = intent.params.get("target_label", "chair")
        follow_height = intent.params.get("follow_height", 380.0)
        config = FollowerConfigSchema(
            target_label=target_label,
            follow_height=follow_height,
        )
        await self.client.start_following(config)
        # Update speech to include the target
        speech = f"Követem: {target_label}."
        elapsed = (time.perf_counter() - t0) * 1000
        return AgentResponse(
            action=intent.action,
            source="direct",
            speech=speech,
            latency_ms=round(elapsed, 2),
        )

    async def _stop_follow(self, intent: Intent, t0: float) -> AgentResponse:
        await self.client.stop_following()
        elapsed = (time.perf_counter() - t0) * 1000
        return AgentResponse(
            action=intent.action,
            source="direct",
            speech=_ACTION_SPEECH.get("stop_following", "Kész."),
            latency_ms=round(elapsed, 2),
        )

    # ──────────────────────────────────────────────────────
    # Response builders
    # ──────────────────────────────────────────────────────

    @staticmethod
    def _ok(intent: Intent, state, t0: float) -> AgentResponse:
        elapsed = (time.perf_counter() - t0) * 1000
        return AgentResponse(
            action=intent.action,
            source="direct",
            robot_state=state,
            speech=_ACTION_SPEECH.get(intent.action, "Kész."),
            latency_ms=round(elapsed, 2),
        )

    @staticmethod
    def _error(intent: Intent, message: str, t0: float) -> AgentResponse:
        elapsed = (time.perf_counter() - t0) * 1000
        return AgentResponse(
            action=intent.action,
            source="direct",
            success=False,
            error=message,
            speech="Hiba történt.",
            latency_ms=round(elapsed, 2),
        )

    async def close(self):
        """Shutdown the underlying HTTP client."""
        await self.client.close()
