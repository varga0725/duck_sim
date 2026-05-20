import logging
from duck_agent_sim.simulator.duck_sim import MockDuckSimulator
from duck_agent_sim.agent.scripted_agent import ScriptedAgent

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("scenario-walk-square")

def main():
    logger.info("=== Running Local Scenario: Walk Square ===")
    sim = MockDuckSimulator()
    agent = ScriptedAgent(sim)

    history = agent.run_walk_square()

    logger.info("--- Execution History ---")
    for idx, state in enumerate(history):
        logger.info(
            f"State {idx:02d}: Time={state.sim_time:.2f}s, Status={state.status:8s}, "
            f"XYZ=[{state.position[0]:.2f}, {state.position[1]:.2f}, {state.position[2]:.2f}], "
            f"Yaw={state.orientation.yaw_deg:.1f} deg, Fallen={state.fallen}"
        )

if __name__ == "__main__":
    main()
