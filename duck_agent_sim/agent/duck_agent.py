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
from duck_agent_sim.agent.local_agent import LocalDuckAgent

logger = logging.getLogger("duck-agent")


class DuckAgent:
    """
    Top-level agent that intelligently routes inputs using LocalDuckAgent,
    supporting Spatial World Model landmarks and structured A2A protocol communication.

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
        self._agent = LocalDuckAgent(bridge_url=bridge_url, hermes_mode=hermes_mode)
        self.router = self._agent.router
        self.direct = self._agent.direct
        self.hermes = self._agent.hermes
        self._bridge_url = bridge_url

    async def start(self):
        """
        Pre-warm any background resources.
        """
        await self._agent.start()

    async def stop(self):
        """Gracefully shut down all subsystems."""
        await self._agent.stop()

    async def process(self, text: str) -> AgentResponse:
        """
        Process a natural-language input and return a unified AgentResponse.
        """
        return await self._agent.process(text)

    async def process_with_intent(self, text: str) -> tuple[Intent, AgentResponse]:
        """Like :meth:`process` but also returns the classified Intent for debugging."""
        return await self._agent.process_with_intent(text)

