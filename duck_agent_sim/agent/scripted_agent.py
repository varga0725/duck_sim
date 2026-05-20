import time
import logging
from typing import Dict, Any, List

from duck_agent_sim.schemas import RobotCommand, RobotState, SafetyConfig

logger = logging.getLogger("scripted-agent")

class ScriptedAgent:
    """
    A deterministic scripting agent that controls a Duck simulator.
    Can be run directly via local Python calls or later integrated via REST HTTP clients.
    """

    def __init__(self, simulator_or_client: Any):
        # Can accept the active simulator instance or a mock client
        self.simulator = simulator_or_client

    def run_basic_walk(self) -> List[RobotState]:
        """
        Executes a basic walk scenario:
        1. Check state, reset if fallen
        2. Walk forward for 2.0 seconds
        3. Stop
        """
        logger.info("Starting Basic Walk scenario...")
        state = self.simulator.get_state()
        history = [state]

        if state.fallen:
            logger.info("Robot is fallen. Issuing reset command first...")
            self.simulator.reset()
            state = self.simulator.get_state()
            history.append(state)

        # Walk forward
        cmd_walk = RobotCommand(
            command="walk_forward",
            speed=0.25,
            turn=0.0,
            duration_sec=2.0,
            safety=SafetyConfig()
        )
        logger.info("Executing walk_forward for 2.0s...")
        res = self.simulator.apply_command(cmd_walk)
        history.append(res.state)

        if res.state.fallen:
            logger.warning("Robot fell during walk forward step!")
            return history

        # Stop
        cmd_stop = RobotCommand(
            command="stop",
            speed=0.0,
            turn=0.0,
            duration_sec=1.0,
            safety=SafetyConfig()
        )
        logger.info("Executing stop...")
        res_stop = self.simulator.apply_command(cmd_stop)
        history.append(res_stop.state)

        logger.info("Basic Walk scenario completed.")
        return history

    def run_walk_square(self) -> List[RobotState]:
        """
        Executes a 4-sided square route:
        - Walk forward 3 sec
        - Turn left 1.5 sec
        - Repeat 4 times
        - Stop
        """
        logger.info("Starting Walk Square scenario...")
        self.simulator.reset()
        history = [self.simulator.get_state()]

        steps = [
            ("walk_forward", 3.0, 0.0),
            ("turn_left", 1.57, 1.0),
            ("walk_forward", 3.0, 0.0),
            ("turn_left", 1.57, 1.0),
            ("walk_forward", 3.0, 0.0),
            ("turn_left", 1.57, 1.0),
            ("walk_forward", 3.0, 0.0),
            ("stop", 1.0, 0.0)
        ]

        for idx, (command, duration, turn) in enumerate(steps):
            cmd = RobotCommand(
                command=command,
                speed=0.25 if command != "stop" else 0.0,
                turn=turn,
                duration_sec=duration,
                safety=SafetyConfig()
            )
            logger.info(f"Step {idx+1}: Executing {command} (duration={duration}s, turn={turn})...")
            res = self.simulator.apply_command(cmd)
            history.append(res.state)

            if res.state.fallen:
                logger.error(f"Safety violation! Robot fell at Step {idx+1} ({command}). Aborting.")
                break

        logger.info("Walk Square scenario completed.")
        return history

    def run_recover_test(self) -> List[RobotState]:
        """
        Tests the safety and recovery loop:
        1. Force a fallen state in mock mode
        2. Verify subsequent walk commands are rejected
        3. Issue reset and verify recovery to idle state
        """
        logger.info("Starting Recover Test scenario...")
        self.simulator.reset()

        # Force a fall by calling simulator tilt method directly
        if hasattr(self.simulator, "force_tilt"):
            logger.info("Injecting severe roll (50 deg) to trigger fall safety...")
            self.simulator.force_tilt(roll=50.0, pitch=0.0)
        else:
            logger.warning("Simulator does not support direct force_tilt injection. Skipping tilt injection.")

        state_before = self.simulator.get_state()
        # Verify it registers as fallen
        logger.info(f"Fallen state registered? {state_before.fallen} (Status: {state_before.status})")

        # Try to walk forward - should be rejected by safety layers
        cmd_walk = RobotCommand(
            command="walk_forward",
            speed=0.25,
            turn=0.0,
            duration_sec=1.0,
            safety=SafetyConfig()
        )
        logger.info("Attempting to walk while fallen...")
        res = self.simulator.apply_command(cmd_walk)
        logger.info(f"Command accepted? {res.accepted} (Status: {res.state.status})")

        # Issue reset recovery
        logger.info("Issuing recovery reset command...")
        cmd_reset = RobotCommand(
            command="reset",
            speed=0.0,
            turn=0.0,
            duration_sec=1.0,
            safety=SafetyConfig()
        )
        res_reset = self.simulator.apply_command(cmd_reset)
        logger.info(f"Recovered? Fallen={res_reset.state.fallen} (Status: {res_reset.state.status}, Pos Z: {res_reset.state.position[2]}m)")

        return [state_before, res.state, res_reset.state]
