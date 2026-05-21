from duck_agent_sim.services import SimulatorProxy

# Dynamic transparent proxy representing the active simulator singleton.
# The real instance is lifecycle-managed and injected via AppContext/ServiceRegistry.
active_simulator = SimulatorProxy()

