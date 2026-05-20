from duck_agent_sim.schemas import RobotState, Orientation, SafetyConfig, FeetContact
from duck_agent_sim.simulator.safety import evaluate_stability, is_fallen, should_auto_stop

def test_fallen_direct_flag():
    state = RobotState(fallen=True)
    safety = SafetyConfig()
    assert is_fallen(state, safety) is True

def test_fallen_roll_threshold():
    safety = SafetyConfig(max_roll_deg=35.0)
    
    # Under limit
    state_ok = RobotState(orientation=Orientation(roll_deg=20.0))
    assert is_fallen(state_ok, safety) is False
    
    # Over limit
    state_fail = RobotState(orientation=Orientation(roll_deg=40.0))
    assert is_fallen(state_fail, safety) is True

def test_fallen_pitch_threshold():
    safety = SafetyConfig(max_pitch_deg=35.0)
    
    # Under limit
    state_ok = RobotState(orientation=Orientation(pitch_deg=20.0))
    assert is_fallen(state_ok, safety) is False
    
    # Over limit
    state_fail = RobotState(orientation=Orientation(pitch_deg=40.0))
    assert is_fallen(state_fail, safety) is True

def test_fallen_height_threshold():
    safety = SafetyConfig()
    
    # Normal standing Z height (0.41m)
    state_ok = RobotState(position=(0.0, 0.0, 0.41))
    assert is_fallen(state_ok, safety) is False
    
    # Collapsed/dropped Z height (0.05m)
    state_fail = RobotState(position=(0.0, 0.0, 0.05))
    assert is_fallen(state_fail, safety) is True

def test_should_auto_stop():
    safety_stop = SafetyConfig(stop_on_fall=True)
    safety_no_stop = SafetyConfig(stop_on_fall=False)
    
    # OK state
    state_ok = RobotState(position=(0.0, 0.0, 0.41))
    assert should_auto_stop(state_ok, safety_stop) is False
    
    # Fallen state
    state_fail = RobotState(position=(0.0, 0.0, 0.05))
    assert should_auto_stop(state_fail, safety_stop) is True
    assert should_auto_stop(state_fail, safety_no_stop) is False


def test_evaluate_stability_reports_public_reasons_and_thresholds():
    safety = SafetyConfig(max_roll_deg=35.0, max_pitch_deg=30.0)
    state = RobotState(
        orientation=Orientation(roll_deg=36.0, pitch_deg=5.0),
        position=(0.0, 0.0, 0.41),
    )

    stability = evaluate_stability(state, safety=safety, sim_mode="mock")

    assert stability.status == "fallen"
    assert stability.reasons == ["roll_exceeds_max"]
    assert stability.min_body_height_m == 0.15
    assert stability.thresholds.max_roll_deg == 35.0
    assert stability.thresholds.max_pitch_deg == 30.0
    assert stability.thresholds.min_body_height_m == 0.15
    assert stability.thresholds.agent_preflight_min_body_height_m == 0.25
    assert stability.internal_fallen_min_body_height_m == 0.15
    assert stability.agent_preflight_min_body_height_m == 0.25


def test_evaluate_stability_distinguishes_preflight_guard_from_fallen_threshold():
    state = RobotState(position=(0.0, 0.0, 0.20))

    internal = evaluate_stability(state, sim_mode="mock")
    preflight = evaluate_stability(state, sim_mode="mock", use_agent_preflight_guard=True)

    assert internal.status == "stable"
    assert internal.reasons == []
    assert preflight.status == "unstable"
    assert preflight.reasons == ["body_height_below_agent_preflight_min"]


def test_evaluate_stability_can_report_contact_and_freshness_unstable_reasons():
    state = RobotState(feet_contact=FeetContact(left=False, right=False))

    stability = evaluate_stability(
        state,
        sim_mode="mock",
        require_feet_contact=True,
        state_age_sec=2.5,
        freshness_timeout_sec=1.0,
    )

    assert stability.status == "unstable"
    assert stability.reasons == ["no_feet_contact", "state_stale"]
    assert stability.thresholds.state_freshness_timeout_sec == 1.0
    assert stability.freshness_sec == 2.5
