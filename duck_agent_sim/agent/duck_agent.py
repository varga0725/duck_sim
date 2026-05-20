"""
DuckAgent — the main orchestrator.

Combines the SmartRouter, DirectController, and HermesDelegator into a single
entry-point that voice control, CLI scripts, and future web UIs can call.

Architecture::

    Input text
        │
        ▼
    SmartRouter.classify()
        │
        ├─ route="direct"  ──▶  DirectController.execute()   (~<100ms)
        │
        └─ route="hermes"  ──▶  HermesDelegator.delegate()   (~2-5s)
        │
        ▼
    AgentResponse (unified envelope)
"""

import logging
from typing import Optional

from duck_agent_sim.agent.smart_router import SmartRouter, Intent
from duck_agent_sim.agent.direct_controller import DirectController
from duck_agent_sim.agent.hermes_delegator import HermesDelegator, HermesMode
from duck_agent_sim.agent.agent_response import AgentResponse

logger = logging.getLogger("duck-agent")


class DuckAgent:
    """
    Top-level agent that intelligently routes inputs between a fast local
    controller and the Hermes LLM.

    Usage::

        agent = DuckAgent(bridge_url="http://127.0.0.1:8765")
        await agent.start()

        resp = await agent.process("előre")      # → DirectController, <100ms
        resp = await agent.process("mit látsz?")  # → Hermes, ~3s

        await agent.stop()

    Parameters
    ----------
    bridge_url : str
        URL of the Duck Simulator Bridge API.
    hermes_mode : HermesMode
        How to communicate with Hermes: ``"oneshot"`` (default),
        ``"warm_cli"``, or ``"http"``.
    """

    def __init__(
        self,
        bridge_url: str = "http://127.0.0.1:8765",
        hermes_mode: HermesMode = "oneshot",
    ):
        self.router = SmartRouter()
        self.direct = DirectController(bridge_url=bridge_url)
        self.hermes = HermesDelegator(mode=hermes_mode)
        self._bridge_url = bridge_url

    async def start(self):
        """
        Pre-warm any background resources (e.g. Hermes warm pool).
        Call this once before the first ``process()`` invocation.
        """
        await self.hermes.start()
        logger.info(
            "DuckAgent started (bridge=%s, hermes_mode=%s)",
            self._bridge_url,
            self.hermes.mode,
        )

    async def stop(self):
        """Gracefully shut down all subsystems."""
        await self.direct.close()
        await self.hermes.stop()
        logger.info("DuckAgent stopped.")

    async def process(self, text: str) -> AgentResponse:
        """
        Process a natural-language input and return a unified AgentResponse.

        The SmartRouter decides whether the input is a simple motor command
        (handled locally in <100ms) or a complex request (delegated to
        Hermes).

        Parameters
        ----------
        text : str
            Raw transcribed speech or typed input in Hungarian.

        Returns
        -------
        AgentResponse
            Contains action name, robot state, TTS speech, latency, and
            the routing source (``"direct"`` or ``"hermes"``).
        """
        intent = self.router.classify(text)

        logger.info(
            "Routing: '%s' → action=%s, route=%s (confidence=%.2f)",
            text[:60],
            intent.action,
            intent.route,
            intent.confidence,
        )

        if intent.route == "direct":
            return await self.direct.execute(intent)
        else:
            return await self.hermes.delegate(text)

    async def process_with_intent(self, text: str) -> tuple[Intent, AgentResponse]:
        """Like :meth:`process` but also returns the classified Intent for debugging."""
        intent = self.router.classify(text)

        logger.info(
            "Routing: '%s' → action=%s, route=%s (confidence=%.2f)",
            text[:60],
            intent.action,
            intent.route,
            intent.confidence,
        )

        if intent.route == "direct":
            response = await self.direct.execute(intent)
        else:
            response = await self.hermes.delegate(text)

        return intent, response
