import logging
from duck_agent_sim.simulator.duck_sim import MockDuckSimulator
from duck_agent_sim.agent.scripted_agent import ScriptedAgent

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("scenario-basic-walk")

def main():
    logger.info("=== Running Local Scenario: Basic Walk ===")
    sim = MockDuckSimulator()
    agent = ScriptedAgent(sim)

    history = agent.run_basic_walk()

    for idx, state in enumerate(history):
        logger.info(
            f"Step {idx}: Time={state.sim_time:.2f}s, Status={state.status}, "
            f"XYZ=[{state.position[0]:.3f}, {state.position[1]:.3f}, {state.position[2]:.3f}], "
            f"RPY=[{state.orientation.roll_deg:.1f}, {state.orientation.pitch_deg:.1f}, {state.orientation.yaw_deg:.1f}], "
            f"Fallen={state.fallen}"
        )

if __name__ == "__main__":
    main()
