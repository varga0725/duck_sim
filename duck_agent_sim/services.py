import logging
import threading
from typing import Dict, Any, Optional

logger = logging.getLogger("duck-agent-sim")

class SharedMemoryFrameBufferProxy:
    def __init__(self, proxy):
        self.proxy = proxy
        
    def get(self):
        try:
            frame_ref = self.proxy.bus.get_frame_ref()
            w = frame_ref.width
            h = frame_ref.height
            if w <= 0 or h <= 0:
                return None
            import numpy as np
            frame = np.frombuffer(frame_ref.frame_data, dtype=np.uint8).reshape((h, w, 3)).copy()
            return frame
        except Exception:
            return None

class SharedMemorySimulatorProxy:
    """
    Simulated or physical robot interface proxy using Shared Memory IPC.
    Connects the FastAPI bridge process to the background realtime processes.
    """
    def __init__(self, namespace: str = "duck_robot"):
        self.namespace = namespace
        self._bus = None

    @property
    def bus(self):
        if self._bus is None:
            from duck_agent_sim.runtime.shared_telemetry_bus import SharedTelemetryBus
            self._bus = SharedTelemetryBus(create=False, namespace=self.namespace)
        return self._bus

    def get_state(self) -> Any:
        from duck_agent_sim.schemas import RobotState, Orientation, FeetContact, StabilityState
        state_ref = self.bus.get_state_ref()
        sensors_ref = self.bus.get_sensors_ref()
        
        status = state_ref.status.decode("utf-8").strip('\x00')
        if not status:
            status = "idle"
            
        return RobotState(
            robot="open_duck_mini_v2",
            status=status,
            sim_time=sensors_ref.sim_time,
            position=(state_ref.pos_x, state_ref.pos_y, state_ref.pos_z),
            orientation=Orientation(
                roll_deg=state_ref.roll,
                pitch_deg=state_ref.pitch,
                yaw_deg=state_ref.yaw
            ),
            feet_contact=FeetContact(
                left=sensors_ref.left_contact,
                right=sensors_ref.right_contact
            ),
            fallen=state_ref.fallen,
            last_command="",
            stability=StabilityState(
                status="stable" if not state_ref.fallen else "fallen",
                reasons=[]
            )
        )

    def get_sensor_state(self) -> Any:
        from duck_agent_sim.schemas import SensorsState, SensorAvailability
        sensors_ref = self.bus.get_sensors_ref()
        
        return SensorsState(
            robot="open_duck_mini_v2",
            mode="real",
            sim_time=sensors_ref.sim_time,
            timestamp=sensors_ref.timestamp,
            imu=SensorAvailability(
                available=True,
                gyro=(sensors_ref.gyro_x, sensors_ref.gyro_y, sensors_ref.gyro_z),
                accelerometer=(sensors_ref.accel_x, sensors_ref.accel_y, sensors_ref.accel_z),
                orientation=(sensors_ref.quat_w, sensors_ref.quat_x, sensors_ref.quat_y, sensors_ref.quat_z)
            ),
            feet={
                "left": SensorAvailability(available=True, velocity=(0.0, 0.0, 0.0)),
                "right": SensorAvailability(available=True, velocity=(0.0, 0.0, 0.0))
            }
        )

    def set_desired_control(self, control, safety=None, *, command="external_control", duration_sec=None, request_id=None):
        cmd_ref = self.bus.get_command_ref()
        cmd_ref.cmd_type = command.encode("utf-8")[:32]
        cmd_ref.linear_x = control.linear_x
        cmd_ref.linear_y = control.linear_y
        cmd_ref.yaw = control.yaw
        if duration_sec is not None:
            cmd_ref.duration_sec = duration_sec
        return self.get_state()

    def apply_command(self, command) -> Any:
        import time
        cmd_ref = self.bus.get_command_ref()
        cmd_ref.cmd_type = command.command.encode("utf-8")[:32]
        cmd_ref.linear_x = command.speed
        cmd_ref.yaw = command.turn
        cmd_ref.duration_sec = command.duration_sec
        
        # Wait for command duration
        time.sleep(command.duration_sec)
        
        from duck_agent_sim.schemas import CommandResponse, ControlIntent
        return CommandResponse(
            accepted=True,
            command=command.command,
            mapped_control=ControlIntent(linear_x=command.speed, linear_y=0.0, yaw=command.turn),
            state=self.get_state()
        )

    async def execute_command_async(self, command, *, request_id=None, cancel_event=None) -> Any:
        import asyncio
        import time
        cmd_ref = self.bus.get_command_ref()
        cmd_ref.cmd_type = command.command.encode("utf-8")[:32]
        cmd_ref.linear_x = command.speed
        cmd_ref.yaw = command.turn
        cmd_ref.duration_sec = command.duration_sec
        
        # Wait for command duration asynchronously
        deadline = time.monotonic() + command.duration_sec
        while time.monotonic() < deadline:
            if cancel_event is not None and cancel_event.is_set():
                self.stop()
                raise asyncio.CancelledError()
            await asyncio.sleep(0.01)
            
        from duck_agent_sim.schemas import CommandResponse, ControlIntent
        return CommandResponse(
            accepted=True,
            command=command.command,
            mapped_control=ControlIntent(linear_x=command.speed, linear_y=0.0, yaw=command.turn),
            state=self.get_state()
        )

    def stop(self) -> Any:
        cmd_ref = self.bus.get_command_ref()
        cmd_ref.cmd_type = b"stop"
        return self.get_state()

    def reset(self) -> Any:
        cmd_ref = self.bus.get_command_ref()
        cmd_ref.cmd_type = b"reset"
        return self.get_state()

    def close(self):
        if self._bus:
            self._bus.close()
            self._bus = None

    @property
    def frame_buffer(self):
        if not hasattr(self, "_frame_buffer_proxy"):
            self._frame_buffer_proxy = SharedMemoryFrameBufferProxy(self)
        return self._frame_buffer_proxy


class SimulatorProxy:
    """
    Transparent proxy for the active simulator singleton.
    Forwards all attribute and method calls to the underlying concrete simulator.
    Ensures 100% backward-compatibility for legacy imports while allowing
    explicit lifecycle and dependency injection through AppContext.
    """
    __test__ = False

    def __init__(self):
        self._wrapped = None
        self._lock = threading.RLock()

    def set_instance(self, instance: Any):
        with self._lock:
            self._wrapped = instance

    def _ensure_initialized(self):
        with self._lock:
            if self._wrapped is None:
                import os
                if os.getenv("DUCK_MULTIPROCESS", "false").lower() == "true":
                    logger.info("[SimulatorProxy] Initializing SharedMemorySimulatorProxy in multiprocess mode.")
                    self._wrapped = SharedMemorySimulatorProxy()
                    return

                # Fallback to lazy instantiation matching old behavior if registry/AppContext is not active yet
                from duck_agent_sim.config import DUCK_SIM_MODE
                from duck_agent_sim.simulator.duck_sim import MockDuckSimulator, RealDuckSimulator
                logger.info(f"[SimulatorProxy] Lazily initializing active simulator (mode: {DUCK_SIM_MODE})")
                if DUCK_SIM_MODE == "real":
                    self._wrapped = RealDuckSimulator()
                else:
                    self._wrapped = MockDuckSimulator()
                self._wrapped.reset()

    def __getattr__(self, name: str) -> Any:
        self._ensure_initialized()
        return getattr(self._wrapped, name)

    def __dir__(self) -> list[str]:
        self._ensure_initialized()
        return dir(self._wrapped)


class ServiceRegistry:
    """
    Explicit registry to resolve and manage application services.
    """

    def __init__(self):
        self._services: Dict[str, Any] = {}
        self._lock = threading.Lock()

    def register(self, name: str, service: Any):
        with self._lock:
            if name in self._services:
                logger.warning(f"Service '{name}' is already registered and will be overwritten.")
            self._services[name] = service

    def get(self, name: str) -> Any:
        with self._lock:
            if name not in self._services:
                raise KeyError(f"Service '{name}' not found in registry.")
            return self._services[name]


class AppContext:
    """
    Main Application Context representing explicit dependency graph and services lifecycle.
    """

    def __init__(self):
        self.registry = ServiceRegistry()
        self._started = False
        self._lock = threading.Lock()

    def start(self):
        with self._lock:
            if self._started:
                return
            logger.info("Initializing AppContext services...")
            
            import os
            if os.getenv("DUCK_MULTIPROCESS", "false").lower() == "true":
                logger.info("[AppContext] Running in Multiprocess mode. Initializing SharedMemorySimulatorProxy...")
                simulator = SharedMemorySimulatorProxy()
                self.registry.register("simulator", simulator)
                
                from duck_agent_sim.simulator.instance import active_simulator
                if isinstance(active_simulator, SimulatorProxy):
                    active_simulator.set_instance(simulator)
                
                from duck_agent_sim.simulator.queue_manager import QueueManager
                queue_manager = QueueManager(simulator)
                self.registry.register("queue_manager", queue_manager)
                queue_manager.start()
                
                self._started = True
                logger.info("AppContext services started successfully in Multiprocess mode.")
                return
            
            from duck_agent_sim.config import DUCK_SIM_MODE
            from duck_agent_sim.simulator.duck_sim import MockDuckSimulator, RealDuckSimulator
            
            # 1. Instantiate the Simulator service
            if DUCK_SIM_MODE == "real":
                simulator = RealDuckSimulator()
            else:
                simulator = MockDuckSimulator()
                
            # Eagerly initialize the simulator (physics engine & FPV camera thread)
            # and launch the interactive MuJoCo passive viewer window on startup
            logger.info("[AppContext] Eagerly initializing simulator and launching viewer window...")
            simulator.reset()
            
            self.registry.register("simulator", simulator)
            
            # Wire up to the global backward-compatible proxy
            from duck_agent_sim.simulator.instance import active_simulator
            if isinstance(active_simulator, SimulatorProxy):
                active_simulator.set_instance(simulator)
            
            # 2. Instantiate and start QueueManager and ControlWorker
            from duck_agent_sim.simulator.queue_manager import QueueManager
            queue_manager = QueueManager(simulator)
            self.registry.register("queue_manager", queue_manager)
            queue_manager.start()
            
            self._started = True
            logger.info("AppContext services started successfully.")

    def shutdown(self):
        with self._lock:
            if not self._started:
                return
            logger.info("Shutting down AppContext services...")
            
            # Stop QueueManager / ControlWorker
            try:
                queue_manager = self.registry.get("queue_manager")
                queue_manager.stop()
            except Exception as e:
                logger.error(f"Error shutting down queue_manager: {e}")
                
            # Stop Simulator
            try:
                simulator = self.registry.get("simulator")
                if hasattr(simulator, "close"):
                    simulator.close()
            except Exception as e:
                logger.error(f"Error shutting down simulator: {e}")
                
            self._started = False
            logger.info("AppContext services shut down successfully.")


# Global AppContext instance
app_context = AppContext()
