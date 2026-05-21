import pytest
import asyncio
import threading
import time
from fastapi.testclient import TestClient
from duck_agent_sim.schemas import RobotState, RobotCommand, SafetyConfig
from duck_agent_sim.simulator.double_buffered_state import DoubleBufferedState
from duck_agent_sim.simulator.queue_manager import QueueManager
from duck_agent_sim.simulator.duck_sim import MockDuckSimulator
from duck_agent_sim.main import app
from duck_agent_sim.services import ServiceRegistry, AppContext

def test_double_buffered_state_concurrency():
    initial = RobotState(sim_time=0.0)
    db = DoubleBufferedState(initial)
    
    # Check that initial reads are deep copies and equal to initial
    read1 = db.get_read_state()
    assert read1.sim_time == 0.0
    assert read1 is not initial  # Must be a copy
    
    # Modifying read state doesn't affect DB internal write state
    read1.sim_time = 10.0
    assert db.get_read_state().sim_time == 0.0
    
    # Update write state and verify swap
    updated = RobotState(sim_time=5.0)
    db.update_write_state(updated)
    assert db.get_read_state().sim_time == 0.0  # Not swapped yet
    
    db.swap()
    assert db.get_read_state().sim_time == 5.0  # Swapped!

    # High frequency concurrent reads/writes thread safety test
    stop_event = threading.Event()
    
    def reader():
        while not stop_event.is_set():
            state = db.get_read_state()
            assert state.sim_time in (5.0, 12.0)
            
    def writer():
        while not stop_event.is_set():
            db.update_write_state(RobotState(sim_time=12.0))
            db.swap()
            time.sleep(0.001)

    threads = [
        threading.Thread(target=reader) for _ in range(5)
    ] + [threading.Thread(target=writer)]
    
    for t in threads:
        t.start()
        
    time.sleep(0.1)
    stop_event.set()
    
    for t in threads:
        t.join()


def test_queue_manager_sequential_execution():
    asyncio.run(_test_queue_manager_sequential_execution())


async def _test_queue_manager_sequential_execution():
    simulator = MockDuckSimulator()
    queue = QueueManager(simulator, max_queue_size=5)
    queue.start()
    
    try:
        cmd1 = RobotCommand(command="walk_forward", duration_sec=0.1)
        cmd2 = RobotCommand(command="turn_left", duration_sec=0.1)
        
        # Submit concurrently
        t1 = asyncio.create_task(queue.submit_command(cmd1))
        t2 = asyncio.create_task(queue.submit_command(cmd2))
        
        res1, res2 = await asyncio.gather(t1, t2)
        
        assert res1.accepted is True
        assert res1.command == "walk_forward"
        assert res2.accepted is True
        assert res2.command == "turn_left"
    finally:
        queue.stop()
        simulator.close()


def test_queue_manager_emergency_stop():
    asyncio.run(_test_queue_manager_emergency_stop())


async def _test_queue_manager_emergency_stop():
    simulator = MockDuckSimulator()
    queue = QueueManager(simulator, max_queue_size=5)
    queue.start()
    
    try:
        # Submit long running command
        cmd_long = RobotCommand(command="walk_forward", duration_sec=5.0)
        t_long = asyncio.create_task(queue.submit_command(cmd_long))
        
        # Give it a tiny fraction of time to start
        await asyncio.sleep(0.05)
        assert queue.get_telemetry()["active_command"] == "walk_forward"
        
        # Submit emergency stop
        cmd_stop = RobotCommand(command="stop")
        res_stop = await queue.submit_command(cmd_stop)
        
        assert res_stop.accepted is True
        assert res_stop.command == "stop"
        
        # The long running command should be cancelled
        with pytest.raises(asyncio.CancelledError):
            await t_long
            
        assert queue.get_telemetry()["active_command"] is None
    finally:
        queue.stop()
        simulator.close()


def test_queue_manager_bounded_overflow():
    asyncio.run(_test_queue_manager_bounded_overflow())


async def _test_queue_manager_bounded_overflow():
    simulator = MockDuckSimulator()
    # Tiny queue size to trigger overflow easily
    queue = QueueManager(simulator, max_queue_size=1)
    queue.start()
    
    try:
        # Start a command that takes a bit of time
        cmd1 = RobotCommand(command="walk_forward", duration_sec=0.5)
        # Bypasses queue capacity as it runs instantly as the active command, but fills queue manager
        t1 = asyncio.create_task(queue.submit_command(cmd1))
        
        await asyncio.sleep(0.02)
        
        # Push another to fill the queue slot (max size 1)
        cmd2 = RobotCommand(command="turn_left", duration_sec=0.5)
        t2 = asyncio.create_task(queue.submit_command(cmd2))
        
        await asyncio.sleep(0.02)
        
        # Third command should overflow and fail instantly
        cmd3 = RobotCommand(command="walk_forward", duration_sec=0.5)
        with pytest.raises(RuntimeError) as exc_info:
            await queue.submit_command(cmd3)
        assert "queue is full" in str(exc_info.value)
        
        # Let them finish
        await asyncio.gather(t1, t2, return_exceptions=True)
    finally:
        queue.stop()
        simulator.close()


def test_queue_manager_shutdown_resolves_pending_commands():
    asyncio.run(_test_queue_manager_shutdown_resolves_pending_commands())


async def _test_queue_manager_shutdown_resolves_pending_commands():
    simulator = MockDuckSimulator()
    queue = QueueManager(simulator, max_queue_size=5)
    queue.start()

    task = asyncio.create_task(queue.submit_command(RobotCommand(command="walk_forward", duration_sec=5.0)))
    await asyncio.sleep(0.05)
    await queue.shutdown()

    with pytest.raises((RuntimeError, asyncio.CancelledError)):
        await task

    simulator.close()


def test_mock_physics_clock_continues_while_command_is_active():
    asyncio.run(_test_mock_physics_clock_continues_while_command_is_active())


async def _test_mock_physics_clock_continues_while_command_is_active():
    simulator = MockDuckSimulator()
    queue = QueueManager(simulator, max_queue_size=5)
    queue.start()

    try:
        before_ticks = simulator.get_clock_telemetry().tick_count
        task = asyncio.create_task(queue.submit_command(RobotCommand(command="walk_forward", duration_sec=0.3)))
        await asyncio.sleep(0.15)
        mid_ticks = simulator.get_clock_telemetry().tick_count
        assert mid_ticks > before_ticks
        await task
    finally:
        queue.stop()
        simulator.close()


def test_websocket_telemetry_stays_live_under_command_load():
    with TestClient(app) as client:
        with client.websocket_connect("/ws") as ws:
            first_state = ws.receive_json()
            assert first_state["robot"] == "open_duck_mini_v2"

            ws.send_json({"command": "walk_forward", "duration_sec": 0.1})
            messages = [ws.receive_json(), ws.receive_json(), ws.receive_json()]

            assert any(message.get("event") == "command_received" for message in messages)
            assert any(message.get("robot") == "open_duck_mini_v2" for message in messages)


def test_service_registry_and_app_context():
    registry = ServiceRegistry()
    registry.register("test_service", "hello")
    assert registry.get("test_service") == "hello"
    
    with pytest.raises(KeyError):
        registry.get("invalid")

    # AppContext lifecycle
    ctx = AppContext()
    ctx.start()
    
    try:
        sim = ctx.registry.get("simulator")
        qm = ctx.registry.get("queue_manager")
        
        assert isinstance(sim, MockDuckSimulator)
        assert isinstance(qm, QueueManager)
        assert qm._running is True
    finally:
        ctx.shutdown()
        assert qm._running is False
