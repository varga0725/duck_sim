import logging
import multiprocessing
import os
import sys
import time
import signal
from typing import List

logger = logging.getLogger("duck-launcher")

def configure_process_rt(core_id: int, policy_name: str, priority: int):
    """
    Sets CPU core affinity and scheduler policy/priority on Linux hosts.
    Fails back silently on macOS or windows.
    """
    if sys.platform != 'linux':
        logger.debug(f"Not running on Linux. Skipping RT priority and core pinning for core {core_id}.")
        return

    try:
        # Core pinning
        os.sched_setaffinity(0, {core_id})
        logger.info(f"Pinned process PID {os.getpid()} to CPU core {core_id}.")
    except Exception as e:
        logger.error(f"Failed to pin CPU core {core_id}: {e}")

    try:
        # Scheduler policy mapping
        policy = os.SCHED_OTHER
        if policy_name == "SCHED_FIFO":
            policy = os.SCHED_FIFO
        elif policy_name == "SCHED_RR":
            policy = os.SCHED_RR
            
        param = os.sched_param(priority)
        os.sched_setscheduler(0, policy, param)
        logger.info(f"Set process PID {os.getpid()} scheduler policy to {policy_name} (priority: {priority}).")
    except Exception as e:
        logger.error(f"Failed to set scheduler policy {policy_name}: {e}. (Are you running as root/sudo?)")

class ProcessLauncher:
    """
    Coordinates launcher tasks for running:
    - Motor Control Loop & Watchdog (Core 1, SCHED_FIFO)
    - Sensor Fusion & Estimation (Core 2, SCHED_FIFO)
    - High-Level Policy & NPU inference (Core 3)
    - FastAPI Bridge & WS API (Core 0)
    """
    def __init__(self):
        self.processes: List[multiprocessing.Process] = []
        self._running = False

    def start_all(self):
        self._running = True
        logger.info("Initializing Embodied Robotics Runtime Processes...")

        # Initialize the Shared Memory segments in the parent process
        from duck_agent_sim.runtime.shared_telemetry_bus import SharedTelemetryBus
        self.bus = SharedTelemetryBus(create=True)

        # Define targets for processes
        target_map = [
            (self._run_motor_loop, "motor_loop_process"),
            (self._run_sensor_fusion, "sensor_fusion_process"),
            (self._run_vision_loop, "vision_perception_process"),
            (self._run_api_bridge, "api_bridge_process")
        ]

        for target, name in target_map:
            p = multiprocessing.Process(target=target, name=name, daemon=True)
            self.processes.append(p)
            p.start()
            logger.info(f"Started child process {name} (PID: {p.pid}).")

    def stop_all(self):
        self._running = False
        logger.info("Stopping all runtime processes...")
        for p in self.processes:
            if p.is_alive():
                logger.info(f"Terminating process {p.name} (PID: {p.pid})...")
                os.kill(p.pid, signal.SIGINT)
                p.join(timeout=1.0)
                if p.is_alive():
                    p.terminate()
        self.processes.clear()
        
        # Clean up shared memory segments in the parent process
        if hasattr(self, "bus") and self.bus:
            self.bus.close()
            self.bus = None

    def _run_motor_loop(self):
        # CPU 1, SCHED_FIFO, Priority 80
        configure_process_rt(core_id=1, policy_name="SCHED_FIFO", priority=80)
        logger.info("Motor Loop running...")
        
        # Init shared bus connection
        from duck_agent_sim.runtime.shared_telemetry_bus import SharedTelemetryBus
        from duck_agent_sim.hardware.sts3215_driver import STS3215Driver
        from duck_agent_sim.runtime.robot_state_machine import RobotStateMachine
        from duck_agent_sim.simulator.safety import check_servo_runaway, check_impossible_pose
        
        bus = SharedTelemetryBus(create=False)
        servo = STS3215Driver()
        state = bus.get_state_ref()
        cmd = bus.get_command_ref()
        fsm = RobotStateMachine(servo, state, cmd)
        
        runaway_ticks = 0
        
        try:
            while self._running:
                start_tick = time.monotonic()
                # Read sensors from bus (which are updated by sensor_fusion)
                sensor_ref = bus.get_sensors_ref()
                battery_voltage = sensor_ref.battery_voltage
                battery_temp = getattr(sensor_ref, "battery_temp", 25.0)
                
                # Fetch max servo temp
                servos_ref = bus.get_servos_ref()
                max_temp = max(list(servos_ref.present_temp)) if hasattr(servos_ref.present_temp, "__iter__") else 35
                
                # Run safety checks
                fallen = state.fallen
                
                # Servo runaway detection (discrepancy > 15 deg for > 5 ticks)
                mismatch = check_servo_runaway(list(servos_ref.target_pos), list(servos_ref.present_pos), 15.0)
                if mismatch:
                    runaway_ticks += 1
                else:
                    runaway_ticks = 0
                    
                # Check for impossible pose command
                unsafe_pose = check_impossible_pose(list(servos_ref.target_pos))
                
                runaway = (runaway_ticks > 5) or unsafe_pose
                
                # FSM Tick
                fsm.step(battery_voltage, max_temp, fallen, runaway, battery_temp)
                
                # Sleep exactly until next tick (50Hz = 20ms)
                elapsed = time.monotonic() - start_tick
                sleep_time = max(0.001, 0.020 - elapsed)
                time.sleep(sleep_time)
        except KeyboardInterrupt:
            pass
        finally:
            servo.close()
            bus.close()

    def _run_sensor_fusion(self):
        # CPU 2, SCHED_FIFO, Priority 50
        configure_process_rt(core_id=2, policy_name="SCHED_FIFO", priority=50)
        logger.info("Sensor Fusion & State Estimation Loop running...")
        
        import numpy as np
        from duck_agent_sim.runtime.shared_telemetry_bus import SharedTelemetryBus
        from duck_agent_sim.hardware.bno055_driver import BNO055Driver
        from duck_agent_sim.hardware.foot_switch_driver import FootSwitchDriver
        from duck_agent_sim.hardware.battery_monitor import BatteryMonitor
        from duck_agent_sim.simulator.state_estimator import StateEstimator
        
        bus = SharedTelemetryBus(create=False)
        imu = BNO055Driver()
        feet = FootSwitchDriver()
        batt = BatteryMonitor()
        estimator = StateEstimator(dt=0.02)
        
        sensors_ref = bus.get_sensors_ref()
        servos_ref = bus.get_servos_ref()
        state_ref = bus.get_state_ref()
        
        try:
            while self._running:
                start_tick = time.monotonic()
                
                # 1. Read hardware sensors
                accel = imu.read_accelerometer()
                gyro = imu.read_gyroscope()
                quat = imu.read_quaternion()
                left_c, right_c = feet.read_contacts()
                
                # Sum the present loads of all 14 servos to get total servo current draw
                # present_load is in centiamperes in simulated mode.
                total_servo_load = sum(servos_ref.present_load[i] for i in range(14))
                total_current = (total_servo_load / 100.0) + 0.7
                voltage = batt.read_voltage(total_current)
                
                # Fetch battery status for temperature
                batt_status = batt.get_status()
                battery_temp = batt_status.get("temperature", 25.0)
                
                # 2. Write raw sensor state to shared bus
                sensors_ref.timestamp = time.time()
                sensors_ref.battery_voltage = voltage
                sensors_ref.battery_temp = battery_temp
                sensors_ref.left_contact = left_c
                sensors_ref.right_contact = right_c
                sensors_ref.accel_x, sensors_ref.accel_y, sensors_ref.accel_z = accel
                sensors_ref.gyro_x, sensors_ref.gyro_y, sensors_ref.gyro_z = gyro
                sensors_ref.quat_w, sensors_ref.quat_x, sensors_ref.quat_y, sensors_ref.quat_z = quat
                
                # 3. Read joint telemetry from servos_ref (updated by motor loop)
                left_joints = np.array(servos_ref.present_pos[0:5])
                left_vel = np.array(servos_ref.present_vel[0:5])
                right_joints = np.array(servos_ref.present_pos[9:14])
                right_vel = np.array(servos_ref.present_vel[9:14])
                
                # 4. Perform EKF fusion
                vel, pos = estimator.update(
                    imu_accel=accel,
                    imu_quat=quat,
                    left_contact=left_c,
                    right_contact=right_c,
                    left_joint_angles=left_joints,
                    left_joint_vel=left_vel,
                    right_joint_angles=right_joints,
                    right_joint_vel=right_vel
                )
                
                # 5. Write estimated state back to bus
                state_ref.pos_x, state_ref.pos_y, state_ref.pos_z = pos
                state_ref.vel_x, state_ref.vel_y, state_ref.vel_z = vel
                
                # Sleep until next 50Hz tick (20ms)
                elapsed = time.monotonic() - start_tick
                sleep_time = max(0.001, 0.020 - elapsed)
                time.sleep(sleep_time)
        except KeyboardInterrupt:
            pass
        finally:
            imu.bus.close() if hasattr(imu, "bus") and imu.bus else None
            feet.close()
            bus.close()

    def _run_vision_loop(self):
        # CPU 3, SCHED_OTHER, Nice -5 (Decoupled Perception)
        configure_process_rt(core_id=3, policy_name="SCHED_OTHER", priority=0)
        logger.info("Vision Loop running...")
        
        import numpy as np
        from duck_agent_sim.runtime.shared_telemetry_bus import SharedTelemetryBus
        from duck_agent_sim.vision.yolo_detector import YOLODetector
        from duck_agent_sim.vision.tracker import CentroidTracker
        from duck_agent_sim.config import DUCK_SIM_MODE
        
        bus = SharedTelemetryBus(create=False)
        detector = YOLODetector()
        tracker = CentroidTracker()
        
        # If in webcam mode, we need a CameraDevice to capture from cv2 VideoCapture(0)
        camera_device = None
        if DUCK_SIM_MODE == "webcam":
            from duck_agent_sim.vision.camera import CameraDevice
            camera_device = CameraDevice(None)
            
        last_frame_timestamp = 0.0
        
        try:
            while self._running:
                start_time = time.monotonic()
                frame = None
                timestamp = 0.0
                
                if DUCK_SIM_MODE == "webcam":
                    if camera_device:
                        frame = camera_device.capture_frame()
                        timestamp = time.time()
                else:
                    # Read from shared memory
                    try:
                        frame_ref = bus.get_frame_ref()
                        # Only process if we have a new frame timestamp
                        if frame_ref.timestamp > last_frame_timestamp:
                            last_frame_timestamp = frame_ref.timestamp
                            timestamp = frame_ref.timestamp
                            w = frame_ref.width
                            h = frame_ref.height
                            # Reconstruct numpy array from ctypes buffer
                            frame = np.frombuffer(frame_ref.frame_data, dtype=np.uint8).reshape((h, w, 3)).copy()
                    except Exception as e:
                        pass
                
                if frame is not None:
                    # Run YOLO detection
                    detections = detector.detect(frame)
                    # Run centroid tracking
                    detections = tracker.update(detections)
                    
                    # Write to shared memory vision segment
                    try:
                        vision_ref = bus.get_vision_ref()
                        vision_ref.timestamp = timestamp
                        
                        # Calculate vision FPS
                        if not hasattr(self, "_frame_count"):
                            self._frame_count = 0
                            self._fps_start_time = time.time()
                        self._frame_count += 1
                        now = time.time()
                        elapsed = now - self._fps_start_time
                        if elapsed >= 2.0:
                            self._current_fps = self._frame_count / elapsed
                            self._frame_count = 0
                            self._fps_start_time = now
                        
                        fps = getattr(self, "_current_fps", 10.0)
                        vision_ref.fps = fps
                        
                        vision_ref.num_detections = min(len(detections), 10)
                        for i, det in enumerate(detections[:10]):
                            det_struct = vision_ref.detections[i]
                            det_struct.label = det["label"].encode("utf-8")[:32]
                            det_struct.confidence = float(det["confidence"])
                            for j in range(4):
                                det_struct.bbox[j] = float(det["bbox"][j])
                            for j in range(2):
                                det_struct.center[j] = float(det["center"][j])
                            det_struct.tracking_id = int(det.get("tracking_id", -1))
                    except Exception as e:
                        logger.error(f"Failed to write detections to shared memory: {e}")
                        
                # sleep to target 10Hz (0.1s period)
                elapsed = time.monotonic() - start_time
                sleep_time = max(0.001, 0.1 - elapsed)
                time.sleep(sleep_time)
        except KeyboardInterrupt:
            pass
        finally:
            if camera_device:
                camera_device.close()
            bus.close()

    def _run_api_bridge(self):
        # CPU 0, Low Priority System & Web APIs
        configure_process_rt(core_id=0, policy_name="SCHED_OTHER", priority=0)
        logger.info("Starting FastAPI Uvicorn Bridge...")
        
        # Set Multiprocess flag for AppContext to route telemetry to SHM
        os.environ["DUCK_MULTIPROCESS"] = "true"
        
        import uvicorn
        from duck_agent_sim.config import BRIDGE_HOST, BRIDGE_PORT
        
        uvicorn.run(
            "duck_agent_sim.main:app",
            host=BRIDGE_HOST,
            port=BRIDGE_PORT,
            log_level="warning",
            loop="asyncio"
        )
