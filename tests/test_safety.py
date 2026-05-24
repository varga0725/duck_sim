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


def test_impossible_pose_limits():
    from duck_agent_sim.simulator.safety import check_impossible_pose
    
    # Standard zero posture should be valid
    safe_pose = [0.0] * 14
    assert check_impossible_pose(safe_pose) is False
    
    # Exceed limit
    unsafe_pose = [0.0] * 14
    unsafe_pose[3] = 2.0  # Left knee limit is ~1.57 rad
    assert check_impossible_pose(unsafe_pose) is True
    
    # Knee/ankle self-collision overlap
    collision_pose = [0.0] * 14
    collision_pose[3] = 1.3   # Knee flexed
    collision_pose[4] = -1.3  # Ankle flexed conflicting
    assert check_impossible_pose(collision_pose) is True


def test_battery_thermal_limit():
    from duck_agent_sim.simulator.safety import check_battery_thermal_limit
    
    assert check_battery_thermal_limit(55.0) is False
    assert check_battery_thermal_limit(60.0) is True
    assert check_battery_thermal_limit(65.0) is True


def test_battery_voltage_dip_and_brownout():
    from duck_agent_sim.hardware.battery_monitor import BatteryMonitor
    
    batt = BatteryMonitor(address=0x99)
    assert not batt.is_hardware
    
    # Nominal voltage at zero current
    v_idle = batt.read_voltage(0.0)
    assert 12.0 <= v_idle <= 12.61
    
    # Voltage dip under heavy motor current (10A)
    import time
    batt._last_time = time.time() - 0.95  # Simulate 0.95 seconds passing
    v_heavy = batt.read_voltage(10.0)
    # V = V_nominal - 10 * 0.05 -> should be approx 0.5V lower than nominal
    assert v_heavy < v_idle
    assert v_heavy > 5.0
    
    # Simulated temperature rise
    status = batt.get_status()
    assert status["temperature"] > 25.0


def test_runaway_temporal_filter():
    from duck_agent_sim.simulator.safety import check_servo_runaway
    
    # Case with target vs present discrepancy
    target_pos = [0.0] * 14
    present_pos = [0.0] * 14
    present_pos[0] = 0.3  # ~17.2 degrees (> 15 degrees)
    
    assert check_servo_runaway(target_pos, present_pos, 15.0) is True
    
    # Test FSM runaway state transition
    from duck_agent_sim.runtime.robot_state_machine import RobotStateMachine
    from duck_agent_sim.runtime.shared_telemetry_bus import SharedTelemetryBus
    from duck_agent_sim.hardware.sts3215_driver import STS3215Driver
    
    bus = SharedTelemetryBus(create=True, namespace="duck_test_runaway")
    driver = STS3215Driver(port="/dev/ttyMockPort")
    try:
        state = bus.get_state_ref()
        cmd = bus.get_command_ref()
        fsm = RobotStateMachine(driver, state, cmd)
        fsm.transition_to("SAFE_IDLE")
        
        # Non-runaway tick
        fsm.step(battery_voltage=11.5, max_servo_temp=35, fallen_detected=False, servo_runaway_detected=False, battery_temp=25.0)
        assert fsm.state == "SAFE_IDLE"
        
        # Triggered runaway tick
        fsm.step(battery_voltage=11.5, max_servo_temp=35, fallen_detected=False, servo_runaway_detected=True, battery_temp=25.0)
        assert fsm.state == "EMERGENCY_STOP"
    finally:
        driver.close()
        bus.close()


def test_mock_simulator_battery_brownout():
    from duck_agent_sim.simulator.duck_sim import MockDuckSimulator
    from duck_agent_sim.schemas import ControlIntent, SafetyConfig
    
    sim = MockDuckSimulator()
    try:
        sim.reset()
        
        # Manually drain the battery capacity to force a brownout
        sim._battery_capacity_mah = 5.0  # almost empty
        
        # Tick the simulation with walking command (draws 3.5A)
        control = ControlIntent(linear_x=0.15)
        # Advance 1 step
        state = sim._advance_from_intent(control, dt=0.05, safety=SafetyConfig())
        
        # Check that it drops below 9.9V and triggers fall/status change
        assert sim._battery_voltage < 9.9
        assert state.fallen is True
        assert state.status == "fallen"
    finally:
        sim.close()


