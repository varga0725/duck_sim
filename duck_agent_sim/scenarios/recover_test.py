import logging
from duck_agent_sim.simulator.duck_sim import MockDuckSimulator
from duck_agent_sim.agent.scripted_agent import ScriptedAgent

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("scenario-recover-test")

def main():
    logger.info("=== Running Local Scenario: Recover & Safety Test ===")
    sim = MockDuckSimulator()
    agent = ScriptedAgent(sim)

    history = agent.run_recover_test()

    logger.info("--- Execution History ---")
    titles = [
        "1. Forced Severe Tilt State",
        "2. Rejected Walking Action (Safety Tripped)",
        "3. Post-Reset Recovery State"
    ]
    for idx, state in enumerate(history):
        logger.info(f"--- {titles[idx]} ---")
        logger.info(
            f"Time={state.sim_time:.2f}s, Status={state.status}, "
            f"XYZ=[{state.position[0]:.3f}, {state.position[1]:.3f}, {state.position[2]:.3f}], "
            f"Roll={state.orientation.roll_deg:.1f} deg, Pitch={state.orientation.pitch_deg:.1f} deg, "
            f"Fallen={state.fallen}"
        )

if __name__ == "__main__":
    main()
