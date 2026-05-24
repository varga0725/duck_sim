import argparse
import time
import numpy as np
from duck_agent_sim.hardware.sts3215_driver import STS3215Driver
from duck_agent_sim.hardware.bno055_driver import BNO055Driver

def calibrate_imu_drift(duration_sec: int = 5):
    print(f"\n[1/3] Calibrating IMU Drift. PLEASE KEEP THE ROBOT COMPLETELY STILL.")
    time.sleep(1.0)
    
    imu = BNO055Driver()
    if not imu.is_hardware:
        print("SIMULATION MODE: Using nominal zero offsets for IMU.")
        print("Calibrated biases: gyro = [0.0, 0.0, 0.0] rad/s, accel = [0.0, 0.0, 0.0] m/s^2")
        return
        
    num_samples = int(duration_sec * 50)
    gyro_data = []
    accel_data = []
    
    for i in range(num_samples):
        gyro_data.append(imu.read_gyroscope())
        accel_data.append(imu.read_accelerometer())
        time.sleep(0.02)
        
    gyro_arr = np.array(gyro_data)
    accel_arr = np.array(accel_data)
    
    gyro_bias = np.mean(gyro_arr, axis=0)
    # Gravity is along Z axis, so subtract 9.81 from Z acceleration
    accel_bias = np.mean(accel_arr, axis=0)
    accel_bias[2] -= 9.81
    
    print("\nCalibration Results:")
    print(f"Gyro biases (X, Y, Z):   {gyro_bias[0]:.6f}, {gyro_bias[1]:.6f}, {gyro_bias[2]:.6f} rad/s")
    print(f"Accel biases (X, Y, Z):  {accel_bias[0]:.6f}, {accel_bias[1]:.6f}, {accel_bias[2]:.6f} m/s^2")
    print("These biases can now be subtracted from raw measurements in state_estimator.py.")

def map_servo_deadzones(servo_id: int):
    print(f"\n[2/3] Mapping Servo {servo_id} Deadzones...")
    servo = STS3215Driver()
    
    if not servo.is_hardware:
        print("SIMULATION MODE: Deadzone is mapped to a nominal 0.08 degrees.")
        return
        
    # Enable torque
    servo.set_torque(servo_id, True)
    time.sleep(0.2)
    
    # Read starting position
    start_pos, _, _ = servo.read_servo_telemetry(servo_id)
    print(f"Starting position ticks: {start_pos}")
    
    deadzone_detected = 0
    # Command small step changes
    for step in range(1, 20):
        target = start_pos + step
        servo.write_position(servo_id, target)
        time.sleep(0.1)
        present, _, _ = servo.read_servo_telemetry(servo_id)
        
        if abs(present - start_pos) > 1:
            deadzone_detected = step
            print(f"Movement detected at step delta: +{step} ticks ({~step * 0.088:.3f} degrees)")
            break
            
    # Reset back to start
    servo.write_position(servo_id, start_pos)
    servo.close()

def evaluate_backlash(servo_id: int):
    print(f"\n[3/3] Measuring Backlash on Servo {servo_id}...")
    servo = STS3215Driver()
    if not servo.is_hardware:
        print("SIMULATION MODE: Backlash is estimated at typical STS3215 specifications of +/- 0.5 degrees.")
        return
        
    # Enable torque
    servo.set_torque(servo_id, True)
    time.sleep(0.2)
    
    start_pos, _, _ = servo.read_servo_telemetry(servo_id)
    
    # Write a command in positive direction, wait, read
    servo.write_position(servo_id, start_pos + 100)
    time.sleep(0.5)
    pos_forward, _, _ = servo.read_servo_telemetry(servo_id)
    
    # Write a command in negative direction, wait, read
    servo.write_position(servo_id, start_pos - 100)
    time.sleep(0.5)
    pos_backward, _, _ = servo.read_servo_telemetry(servo_id)
    
    # Write back to start
    servo.write_position(servo_id, start_pos)
    time.sleep(0.5)
    
    # Backlash corresponds to the error between expected and actual position delta
    # during direction reversal
    backlash_ticks = abs(100 - abs(pos_forward - start_pos)) + abs(100 - abs(pos_backward - start_pos))
    backlash_deg = backlash_ticks * 0.088  # 360 / 4096 = 0.088 deg/tick
    print(f"Backlash measure: {backlash_deg:.3f} degrees ({backlash_ticks} ticks)")
    servo.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Sim2Real Actuator/Sensor Calibration Suite.")
    parser.add_argument("--servo-id", type=int, default=1, help="Servo ID to test for deadzone and backlash (default: 1)")
    args = parser.parse_args()
    
    calibrate_imu_drift()
    map_servo_deadzones(args.servo_id)
    evaluate_backlash(args.servo_id)
