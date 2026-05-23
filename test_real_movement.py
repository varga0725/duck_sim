import os
import time
import asyncio

# Set env vars to match real simulator run
os.environ["DUCK_SIM_MODE"] = "real"
os.environ["DUCK_HEADLESS"] = "true"

from duck_agent_sim.simulator.duck_sim import RealDuckSimulator
from duck_agent_sim.schemas import ControlIntent, SafetyConfig

async def test_movement():
    print("Initializing simulator...")
    sim = RealDuckSimulator(headless=True)
    sim.reset()
    time.sleep(1.0) # Settle
    
    print("Initial state:")
    state = sim.get_state()
    print(f"Position: {state.position}, Orientation: {state.orientation}, Status: {state.status}")
    print(f"Diagnostics: {sim.get_dynamics_diagnostics()}")
    
    print("\nSending walk command...")
    # Walk forward at 0.15 speed for 3 seconds
    control = ControlIntent(linear_x=0.15, linear_y=0.0, yaw=0.0)
    sim.set_desired_control(control, SafetyConfig(), command="walk_forward", duration_sec=3.0)
    
    for i in range(15):
        time.sleep(0.2)
        state = sim.get_state()
        print(f"Step {i}: Position: {state.position}, Status: {state.status}")
        
    print("\nDiagnostics after walk:")
    print(f"Diagnostics: {sim.get_dynamics_diagnostics()}")
    
    print("\nClosing simulator...")
    sim.close()

if __name__ == "__main__":
    asyncio.run(test_movement())
