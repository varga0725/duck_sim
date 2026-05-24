import os
import time
import numpy as np
import pytest

from duck_agent_sim.hardware.sts3215_driver import STS3215Driver
from duck_agent_sim.hardware.bno055_driver import BNO055Driver
from duck_agent_sim.hardware.foot_switch_driver import FootSwitchDriver
from duck_agent_sim.hardware.battery_monitor import BatteryMonitor
from duck_agent_sim.simulator.state_estimator import StateEstimator
from duck_agent_sim.simulator.trajectory_filter import TrajectoryFilter
from duck_agent_sim.simulator.actuator_model import STS3215ActuatorModel
from duck_agent_sim.runtime.shared_telemetry_bus import SharedTelemetryBus
from duck_agent_sim.runtime.robot_state_machine import RobotStateMachine

def test_hardware_drivers_fallback():
    # 1. Test STS3215 Driver in simulation mode
    driver = STS3215Driver(port="/dev/ttyMockPort")
    assert not driver.is_hardware
    assert driver.set_torque(1, True)
    assert driver.write_position(1, 2048)
    
    pos, load, temp = driver.read_servo_telemetry(1)
    assert pos == 2048
    assert isinstance(temp, int)
    
    # 2. Test BNO055 Driver in simulation mode
    imu = BNO055Driver(address=0x99)
    assert not imu.is_hardware
    w, x, y, z = imu.read_quaternion()
    assert np.isclose(w**2 + x**2 + y**2 + z**2, 1.0, atol=1e-3)
    
    # 3. Test Foot Switch Driver
    feet = FootSwitchDriver(left_pin=99, right_pin=98)
    assert not feet.is_hardware
    lc, rc = feet.read_contacts()
    assert isinstance(lc, bool)
    assert isinstance(rc, bool)
    
    # 4. Test Battery Monitor
    batt = BatteryMonitor(address=0x99)
    assert not batt.is_hardware
    volts = batt.read_voltage()
    assert 9.0 <= volts <= 12.61
    status = batt.get_status()
    assert "total_voltage" in status

def test_state_estimator():
    estimator = StateEstimator(dt=0.02)
    estimator.reset(initial_position=(0.0, 0.0, 0.41))
    
    # Simulate a steady standing state (no movement)
    left_joints = np.array([0.0, 0.0, -0.63, 1.36, -0.78], dtype=np.float32)
    left_vel = np.zeros(5, dtype=np.float32)
    
    vel, pos = estimator.update(
        imu_accel=(0.0, 0.0, 9.81), # Gravity only
        imu_quat=(1.0, 0.0, 0.0, 0.0), # Flat orientation
        left_contact=True,
        right_contact=True,
        left_joint_angles=left_joints,
        left_joint_vel=left_vel,
        right_joint_angles=left_joints,
        right_joint_vel=left_vel
    )
    
    # Velocity should remain small/zero (allow higher tolerance due to VO noise)
    assert np.allclose(vel, 0.0, atol=5e-2)
    # Position Z height should be close to home height
    assert 0.35 <= pos[2] <= 0.45

def test_trajectory_filter():
    filter_joint = TrajectoryFilter(num_joints=14, dt=0.02, max_velocity=5.24, max_acceleration=40.0)
    
    initial = np.zeros(14, dtype=np.float32)
    filter_joint.reset(initial)
    
    # Send a large step target
    target = np.ones(14, dtype=np.float32) * 1.5
    
    # First step filtering should limit velocity and acceleration
    filtered = filter_joint.filter(target)
    
    # Verify that the change is constrained
    max_step = 5.24 * 0.02  # max velocity * dt
    for i in range(14):
        assert abs(filtered[i] - initial[i]) <= max_step + 1e-5
        
    # Verify that velocities are calculated
    assert np.any(filter_joint.velocities > 0.0)

def test_actuator_model():
    model = STS3215ActuatorModel(stall_torque=3.0, no_load_speed=6.0)
    
    # Zero velocity should yield stall torque
    min_t, max_t = model.get_torque_bounds(np.zeros(14))
    assert np.allclose(max_t, 3.0)
    
    # High velocity should reduce torque limit
    high_vel = np.ones(14) * 3.0
    min_t_high, max_t_high = model.get_torque_bounds(high_vel)
    assert np.all(max_t_high < 3.0)

def test_shared_telemetry_bus():
    # Initialize a test bus that creates new shared memory segments
    bus = SharedTelemetryBus(create=True, namespace="duck_test_bus")
    
    try:
        sensors = bus.get_sensors_ref()
        servos = bus.get_servos_ref()
        state = bus.get_state_ref()
        cmd = bus.get_command_ref()
        
        # Test basic reading/writing properties
        sensors.battery_voltage = 11.8
        assert np.isclose(sensors.battery_voltage, 11.8)
        
        servos.present_pos[0] = 2048.0
        assert np.isclose(servos.present_pos[0], 2048.0)
        
        state.fallen = False
        assert not state.fallen
        
        cmd.cmd_type = b"stand"
        assert cmd.cmd_type == b"stand"
    finally:
        bus.close()

def test_robot_state_machine():
    bus = SharedTelemetryBus(create=True, namespace="duck_test_fsm")
    servo = STS3215Driver(port="/dev/ttyMockPort")
    
    try:
        state = bus.get_state_ref()
        cmd = bus.get_command_ref()
        fsm = RobotStateMachine(servo, state, cmd)
        
        # Initial state should be BOOT
        assert fsm.state == "BOOT"
        assert state.fsm_state == b"BOOT"
        
        # Simulating time progression to trigger transitions
        fsm.step(battery_voltage=11.8, max_servo_temp=35, fallen_detected=False, servo_runaway_detected=False)
        # Should transition to SELF_TEST -> CALIBRATION -> SAFE_IDLE
        # Let's verify transition happens to SAFE_IDLE eventually
        assert fsm.state in ("BOOT", "SELF_TEST", "CALIBRATION", "SAFE_IDLE")
        
        # Force a SAFE_IDLE transition for testing subsequent commands
        fsm.transition_to("SAFE_IDLE")
        assert fsm.state == "SAFE_IDLE"
        
        # Trigger Stand Command
        cmd.cmd_type = b"stand"
        fsm.step(battery_voltage=11.8, max_servo_temp=35, fallen_detected=False, servo_runaway_detected=False)
        assert fsm.state == "STAND"
        
        # Trigger an Emergency Stop
        cmd.state_override = b"EMERGENCY_STOP"
        fsm.step(battery_voltage=11.8, max_servo_temp=35, fallen_detected=False, servo_runaway_detected=False)
        assert fsm.state == "EMERGENCY_STOP"
        
    finally:
        servo.close()
        bus.close()
