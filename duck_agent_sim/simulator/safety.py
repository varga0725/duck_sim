from typing import Optional

from duck_agent_sim.schemas import (
    RobotState,
    SafetyConfig,
    StabilityState,
    StabilityThresholds,
)
from duck_agent_sim.config import DUCK_SIM_MODE


INTERNAL_MIN_BODY_HEIGHT_M = {
    "real": 0.08,
    "mock": 0.15,
    "webcam": 0.15,
}

AGENT_PREFLIGHT_MIN_BODY_HEIGHT_M = {
    "real": 0.10,
    "mock": 0.25,
    "webcam": 0.25,
}


def get_internal_min_body_height_m(
    safety: Optional[SafetyConfig] = None,
    sim_mode: str = DUCK_SIM_MODE,
) -> float:
    if safety is not None and safety.min_body_height_m is not None:
        return safety.min_body_height_m
    return INTERNAL_MIN_BODY_HEIGHT_M.get(sim_mode, INTERNAL_MIN_BODY_HEIGHT_M["mock"])


def get_agent_preflight_min_body_height_m(sim_mode: str = DUCK_SIM_MODE) -> float:
    return AGENT_PREFLIGHT_MIN_BODY_HEIGHT_M.get(
        sim_mode,
        AGENT_PREFLIGHT_MIN_BODY_HEIGHT_M["mock"],
    )


def evaluate_stability(
    state: RobotState,
    safety: Optional[SafetyConfig] = None,
    sim_mode: str = DUCK_SIM_MODE,
    *,
    use_agent_preflight_guard: bool = False,
    require_feet_contact: bool = False,
    state_age_sec: Optional[float] = None,
    freshness_timeout_sec: Optional[float] = None,
) -> StabilityState:
    """Build the public stability contract for a RobotState.

    Status semantics:
    - fallen: internal fallen conditions are met (fallen flag/status, roll/pitch, or
      internal min body height threshold).
    - unstable: not internally fallen, but a conservative agent preflight,
      contact, or freshness guard is violated.
    - stable: no assessed reason is present.
    """
    safety = safety or SafetyConfig()
    internal_min_height = get_internal_min_body_height_m(safety, sim_mode)
    agent_min_height = get_agent_preflight_min_body_height_m(sim_mode)

    reasons = []
    unstable_reasons = []

    if state.fallen:
        reasons.append("fallen_flag")
    if state.status == "fallen":
        reasons.append("fallen_status")
    if abs(state.orientation.roll_deg) > safety.max_roll_deg:
        reasons.append("roll_exceeds_max")
    if abs(state.orientation.pitch_deg) > safety.max_pitch_deg:
        reasons.append("pitch_exceeds_max")
    if len(state.position) >= 3 and state.position[2] < internal_min_height:
        reasons.append("body_height_below_min")

    if (
        use_agent_preflight_guard
        and len(state.position) >= 3
        and state.position[2] < agent_min_height
        and "body_height_below_min" not in reasons
    ):
        unstable_reasons.append("body_height_below_agent_preflight_min")

    if require_feet_contact and not (state.feet_contact.left or state.feet_contact.right):
        unstable_reasons.append("no_feet_contact")

    if (
        state_age_sec is not None
        and freshness_timeout_sec is not None
        and state_age_sec > freshness_timeout_sec
    ):
        unstable_reasons.append("state_stale")

    all_reasons = reasons + unstable_reasons
    if reasons:
        status = "fallen"
    elif unstable_reasons:
        status = "unstable"
    else:
        status = "stable"

    thresholds = StabilityThresholds(
        max_roll_deg=safety.max_roll_deg,
        max_pitch_deg=safety.max_pitch_deg,
        min_body_height_m=internal_min_height,
        agent_preflight_min_body_height_m=agent_min_height,
        state_freshness_timeout_sec=freshness_timeout_sec,
        require_feet_contact=require_feet_contact,
    )
    return StabilityState(
        status=status,
        reasons=all_reasons,
        min_body_height_m=internal_min_height,
        thresholds=thresholds,
        internal_fallen_min_body_height_m=internal_min_height,
        agent_preflight_min_body_height_m=agent_min_height,
        freshness_sec=state_age_sec,
    )


def with_stability(
    state: RobotState,
    safety: Optional[SafetyConfig] = None,
    sim_mode: str = DUCK_SIM_MODE,
    **kwargs,
) -> RobotState:
    state.stability = evaluate_stability(state, safety=safety, sim_mode=sim_mode, **kwargs)
    return state


def is_fallen(state: RobotState, safety: SafetyConfig) -> bool:
    """
    Evaluates orientation angles, Z-height position, or pre-existing state
    to determine if the simulated robot has fallen over.
    """
    return evaluate_stability(state, safety=safety).status == "fallen"


def should_auto_stop(state: RobotState, safety: SafetyConfig) -> bool:
    """
    Returns True if a stop command should be automatically issued due to safety constraints.
    """
    if safety.stop_on_fall and is_fallen(state, safety):
        return True
    return False
