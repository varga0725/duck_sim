from duck_agent_sim.config import DUCK_SIM_MODE
from duck_agent_sim.simulator.duck_sim import MockDuckSimulator, RealDuckSimulator

# Instantiate singleton simulator based on the configuration
if DUCK_SIM_MODE == "real":
    active_simulator = RealDuckSimulator()
else:
    active_simulator = MockDuckSimulator()
