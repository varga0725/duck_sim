"""
HermesDelegator — routes complex / NLU tasks to the Hermes LLM agent.

Supports three communication modes:

* ``warm_cli``  – Keeps a Hermes CLI process running in the background and
                  communicates over stdin/stdout.  Avoids the 2-5 s cold-start
                  penalty on every call.  **Recommended default.**
* ``oneshot``   – Spawns ``hermes --oneshot`` per request (legacy behaviour
                  from voice_control.py).  Simple but slow.
* ``http``      – Calls a Hermes HTTP API endpoint (for future use when
                  Hermes exposes one).
"""

import asyncio
import logging
import os
import time
from typing import Literal, Optional

from duck_agent_sim.agent.agent_response import AgentResponse

logger = logging.getLogger("hermes-delegator")

# Configurable defaults
_HERMES_BIN = os.getenv(
    "DUCK_HERMES_BIN",
    "/Users/vargaferenc/.local/bin/hermes",
)
_HERMES_TOOLSETS = os.getenv(
    "DUCK_HERMES_TOOLS",
    "duck-robot,terminal,code_execution,file,vision,browser,web",
)
_HERMES_CWD = os.getenv(
    "DUCK_HERMES_CWD",
    "/Users/vargaferenc/Desktop/duck_sim",
)
_HERMES_HTTP_URL = os.getenv("DUCK_HERMES_HTTP_URL", "")

HermesMode = Literal["warm_cli", "oneshot", "http"]


class HermesDelegator:
    """
    Delegates complex requests to the Hermes Agent.

    Usage::

        delegator = HermesDelegator(mode="warm_cli")
        await delegator.start()          # warm up (only needed for warm_cli)
        response = await delegator.delegate("mit látsz a kamerán?")
        await delegator.stop()
    """

    def __init__(self, mode: HermesMode = "oneshot"):
        self.mode = mode
        self._warm_process: Optional[asyncio.subprocess.Process] = None
        self._warm_lock = asyncio.Lock()

    # ──────────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────────

    async def delegate(self, prompt: str) -> AgentResponse:
        """Send *prompt* to Hermes and return an AgentResponse."""
        t0 = time.perf_counter()

        try:
            if self.mode == "warm_cli":
                raw = await self._delegate_warm_cli(prompt)
            elif self.mode == "http":
                raw = await self._delegate_http(prompt)
            else:
                raw = await self._delegate_oneshot(prompt)

            elapsed = (time.perf_counter() - t0) * 1000
            return AgentResponse(
                action="hermes_chat",
                source="hermes",
                hermes_raw=raw,
                speech=raw,
                latency_ms=round(elapsed, 2),
            )

        except Exception as exc:
            elapsed = (time.perf_counter() - t0) * 1000
            logger.error("Hermes delegation failed: %s", exc)
            return AgentResponse(
                action="hermes_chat",
                source="hermes",
                success=False,
                error=str(exc),
                speech="Sajnálom, nem tudtam elérni a Hermes-t.",
                latency_ms=round(elapsed, 2),
            )

    async def start(self):
        """Pre-warm the Hermes process (only relevant for ``warm_cli`` mode)."""
        if self.mode == "warm_cli":
            await self._ensure_warm_process()

    async def stop(self):
        """Terminate any background Hermes process."""
        if self._warm_process is not None:
            try:
                self._warm_process.terminate()
                await asyncio.wait_for(self._warm_process.wait(), timeout=5.0)
            except Exception:
                self._warm_process.kill()
            self._warm_process = None
            logger.info("Warm Hermes process terminated.")

    # ──────────────────────────────────────────────────────
    # Mode: oneshot (legacy subprocess per call)
    # ──────────────────────────────────────────────────────

    async def _delegate_oneshot(self, prompt: str) -> str:
        """Spawn ``hermes --oneshot <prompt>`` and collect stdout."""
        logger.info("Hermes oneshot: %s", prompt[:80])
        process = await asyncio.create_subprocess_exec(
            _HERMES_BIN,
            "-t", _HERMES_TOOLSETS,
            "--oneshot",
            prompt,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=_HERMES_CWD,
        )
        stdout, stderr = await asyncio.wait_for(
            process.communicate(), timeout=60.0,
        )

        if process.returncode != 0:
            err = stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(f"Hermes CLI exited {process.returncode}: {err}")

        return stdout.decode("utf-8", errors="replace").strip()

    # ──────────────────────────────────────────────────────
    # Mode: warm_cli (persistent background process)
    # ──────────────────────────────────────────────────────

    async def _ensure_warm_process(self):
        """Start the warm Hermes process if it isn't running yet."""
        async with self._warm_lock:
            if self._warm_process is not None and self._warm_process.returncode is None:
                return  # still alive

            logger.info("Starting warm Hermes process...")
            self._warm_process = await asyncio.create_subprocess_exec(
                _HERMES_BIN,
                "-t", _HERMES_TOOLSETS,
                "--interactive",
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=_HERMES_CWD,
            )
            # Wait a bit for the process to initialise
            await asyncio.sleep(2.0)
            logger.info("Warm Hermes process started (PID %s).", self._warm_process.pid)

    async def _delegate_warm_cli(self, prompt: str) -> str:
        """Send a prompt to the warm Hermes process over stdin/stdout."""
        await self._ensure_warm_process()

        assert self._warm_process is not None
        assert self._warm_process.stdin is not None
        assert self._warm_process.stdout is not None

        # Use a delimiter so we know when the response ends
        delimiter = "<<<DUCK_AGENT_END>>>"
        wrapped_prompt = (
            f"{prompt}\n"
            f"(When you have finished your response, print exactly: {delimiter})\n"
        )

        self._warm_process.stdin.write(wrapped_prompt.encode("utf-8"))
        await self._warm_process.stdin.drain()

        # Read lines until delimiter or timeout
        lines = []
        try:
            while True:
                line_bytes = await asyncio.wait_for(
                    self._warm_process.stdout.readline(),
                    timeout=30.0,
                )
                line = line_bytes.decode("utf-8", errors="replace").rstrip()
                if delimiter in line:
                    break
                lines.append(line)
        except asyncio.TimeoutError:
            logger.warning("Warm CLI read timed out after 30s.")

        return "\n".join(lines).strip()

    # ──────────────────────────────────────────────────────
    # Mode: http (future Hermes HTTP API)
    # ──────────────────────────────────────────────────────

    async def _delegate_http(self, prompt: str) -> str:
        """Call the Hermes HTTP API (when available)."""
        if not _HERMES_HTTP_URL:
            raise RuntimeError(
                "DUCK_HERMES_HTTP_URL is not set.  "
                "Please configure it or switch to 'oneshot' / 'warm_cli' mode."
            )

        import httpx

        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{_HERMES_HTTP_URL}/v1/chat",
                json={
                    "messages": [
                        {
                            "role": "system",
                            "content": (
                                "Te a Duck Robot irányító asszisztense vagy. "
                                "Magyarul válaszolj, röviden és tömören."
                            ),
                        },
                        {"role": "user", "content": prompt},
                    ],
                },
            )
            resp.raise_for_status()
            data = resp.json()
            # Adapt to whichever response shape Hermes uses
            return (
                data.get("content")
                or data.get("choices", [{}])[0].get("message", {}).get("content", "")
                or str(data)
            )
