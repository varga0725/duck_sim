from duck_agent_sim.schemas import RobotState, SafetyConfig
from duck_agent_sim.config import DUCK_SIM_MODE

def is_fallen(state: RobotState, safety: SafetyConfig) -> bool:
    """
    Evaluates orientation angles, Z-height position, or pre-existing state
    to determine if the simulated robot has fallen over.
    """
    # 1. Direct state flag
    if state.fallen:
        return True

    # 2. Check roll angle limits
    if abs(state.orientation.roll_deg) > safety.max_roll_deg:
        return True

    # 3. Check pitch angle limits
    if abs(state.orientation.pitch_deg) > safety.max_pitch_deg:
        return True

    # 4. Check Z height coordinate (position[2]) - default rest height is 0.41 (0.15 in real simulation).
    # If it falls below 0.08 in real mode or 0.15 in mock mode, it's considered collapsed/fallen.
    threshold = 0.08 if DUCK_SIM_MODE == "real" else 0.15
    if len(state.position) >= 3 and state.position[2] < threshold:
        return True

    return False

def should_auto_stop(state: RobotState, safety: SafetyConfig) -> bool:
    """
    Returns True if a stop command should be automatically issued due to safety constraints.
    """
    if safety.stop_on_fall and is_fallen(state, safety):
        return True
    return False
