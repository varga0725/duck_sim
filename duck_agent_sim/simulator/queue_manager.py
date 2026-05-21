import asyncio
import logging
import time
import uuid
from dataclasses import dataclass
from typing import Any, Dict, Optional

from duck_agent_sim.schemas import CommandResponse, RobotCommand

logger = logging.getLogger("duck-agent-sim")


@dataclass
class CommandRequest:
    command: RobotCommand
    future: asyncio.Future
    cancel_event: asyncio.Event
    request_id: str
    created_at: float

    @classmethod
    def create(cls, command: RobotCommand) -> "CommandRequest":
        loop = asyncio.get_running_loop()
        return cls(
            command=command,
            future=loop.create_future(),
            cancel_event=asyncio.Event(),
            request_id=str(uuid.uuid4()),
            created_at=time.monotonic(),
        )


class QueueManager:
    """
    Bounded command queue for the control plane.

    The worker serializes command application and publishes desired intent through
    the simulator command interface. It never calls simulator.step() and never
    owns physics timing.
    """

    def __init__(self, simulator: Any, max_queue_size: int = 50):
        self._simulator = simulator
        self._max_queue_size = max_queue_size
        self._queue: Optional[asyncio.Queue[CommandRequest]] = None
        self._worker_task: Optional[asyncio.Task] = None
        self._running = False
        self._current_request: Optional[CommandRequest] = None
        self._lifecycle_lock = asyncio.Lock()
        self._completed = 0
        self._failed = 0
        self._cancelled = 0
        self._rejected = 0
        self._last_latency_sec: Optional[float] = None

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        try:
            self._ensure_worker()
        except RuntimeError:
            logger.info("QueueManager will start lazily when an event loop is available.")

    async def shutdown(self) -> None:
        self._running = False
        if self._current_request is not None:
            self._current_request.cancel_event.set()
            if not self._current_request.future.done():
                self._current_request.future.set_exception(RuntimeError("Queue manager is shutting down."))

        if self._queue is not None:
            while not self._queue.empty():
                try:
                    request = self._queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
                request.cancel_event.set()
                if not request.future.done():
                    request.future.set_exception(RuntimeError("Queue manager is shutting down."))
                self._queue.task_done()

        if self._worker_task is not None:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
            self._worker_task = None

        self._halt_simulator()

    def stop(self) -> None:
        """Synchronous compatibility shutdown for legacy tests and app teardown."""
        self._running = False
        if self._current_request is not None:
            self._current_request.cancel_event.set()
            if not self._current_request.future.done():
                self._current_request.future.set_exception(RuntimeError("Queue manager is shutting down."))
        if self._queue is not None:
            while not self._queue.empty():
                try:
                    request = self._queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
                request.cancel_event.set()
                if not request.future.done():
                    request.future.set_exception(RuntimeError("Queue manager is shutting down."))
                self._queue.task_done()
        if self._worker_task is not None:
            self._worker_task.cancel()
        self._halt_simulator()

    async def submit_command(self, command: RobotCommand, timeout: Optional[float] = None) -> CommandResponse:
        if not self._running:
            raise RuntimeError("Queue manager is not running.")

        async with self._lifecycle_lock:
            self._ensure_worker()

            if command.command in ("stop", "reset"):
                await self.cancel_active_command()
                self._drain_pending(f"Cancelled by priority {command.command} command.")

            request = CommandRequest.create(command)
            try:
                self._queue.put_nowait(request)
            except asyncio.QueueFull:
                self._rejected += 1
                raise RuntimeError("Command queue is full. Please wait for current commands to finish.")

        try:
            if timeout is not None:
                return await asyncio.wait_for(request.future, timeout)
            return await request.future
        except asyncio.TimeoutError as exc:
            request.cancel_event.set()
            if self._current_request == request:
                self._halt_simulator()
            raise TimeoutError("Command execution timed out.") from exc

    async def cancel_active_command(self) -> None:
        request = self._current_request
        if request is None:
            self._halt_simulator()
            return
        request.cancel_event.set()
        if not request.future.done():
            request.future.cancel()
        self._cancelled += 1
        self._halt_simulator()

    def get_telemetry(self) -> Dict[str, Any]:
        queue_size = self._queue.qsize() if self._queue is not None else 0
        return {
            "queue_size": queue_size,
            "max_queue_size": self._max_queue_size,
            "active_command": self._current_request.command.command if self._current_request else None,
            "active_request_id": self._current_request.request_id if self._current_request else None,
            "running": self._running,
            "completed": self._completed,
            "failed": self._failed,
            "cancelled": self._cancelled,
            "rejected": self._rejected,
            "last_latency_sec": self._last_latency_sec,
        }

    def _ensure_worker(self) -> None:
        loop = asyncio.get_running_loop()
        if self._queue is None:
            self._queue = asyncio.Queue(maxsize=self._max_queue_size)
        if self._worker_task is None or self._worker_task.done():
            self._worker_task = loop.create_task(self._worker_loop())

    def _drain_pending(self, reason: str) -> None:
        if self._queue is None:
            return
        while not self._queue.empty():
            try:
                request = self._queue.get_nowait()
            except asyncio.QueueEmpty:
                break
            request.cancel_event.set()
            if not request.future.done():
                request.future.set_exception(asyncio.CancelledError(reason))
            self._cancelled += 1
            self._queue.task_done()

    async def _worker_loop(self) -> None:
        assert self._queue is not None
        while self._running:
            try:
                request = await self._queue.get()
            except asyncio.CancelledError:
                break

            self._current_request = request
            started_at = time.monotonic()
            try:
                if request.future.done():
                    continue
                response = await self._execute_on_simulator(request)
                if not request.future.done():
                    request.future.set_result(response)
                self._completed += 1
                self._last_latency_sec = time.monotonic() - started_at
            except asyncio.CancelledError as exc:
                request.cancel_event.set()
                self._halt_simulator()
                if not request.future.done():
                    request.future.set_exception(exc)
                self._cancelled += 1
            except Exception as exc:
                logger.error("Command worker failed while executing %s", request.command.command, exc_info=True)
                self._halt_simulator()
                if not request.future.done():
                    request.future.set_exception(exc)
                self._failed += 1
            finally:
                if self._current_request == request:
                    self._current_request = None
                self._queue.task_done()

    async def _execute_on_simulator(self, request: CommandRequest) -> CommandResponse:
        executor = getattr(self._simulator, "execute_command_async", None)
        if executor is None:
            raise RuntimeError("Simulator does not expose execute_command_async; refusing executor fallback.")
        return await executor(
            request.command,
            request_id=request.request_id,
            cancel_event=request.cancel_event,
        )

    def _halt_simulator(self) -> None:
        try:
            self._simulator.stop()
        except Exception:
            logger.warning("Failed to halt simulator during queue cancellation/shutdown.", exc_info=True)
