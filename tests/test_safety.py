from duck_agent_sim.schemas import RobotState, Orientation, SafetyConfig
from duck_agent_sim.simulator.safety import is_fallen, should_auto_stop

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
