import logging
import threading
from typing import Dict, Any, Optional

logger = logging.getLogger("duck-agent-sim")

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
        self._lock = threading.Lock()

    def set_instance(self, instance: Any):
        with self._lock:
            self._wrapped = instance

    def _ensure_initialized(self):
        with self._lock:
            if self._wrapped is None:
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
