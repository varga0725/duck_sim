import logging
import time
import numpy as np
from typing import Tuple, List

from duck_agent_sim.hardware.sts3215_driver import STS3215Driver
from duck_agent_sim.runtime.shared_telemetry_bus import RobotStateStruct, CommandQueueStruct

logger = logging.getLogger("duck-state-machine")

# Joint calibration offsets (default offset mapping to default stand posture)
DEFAULT_STAND_POSTURE = np.array([
    0.002,  0.053, -0.630,  1.368, -0.784,  # Left leg
    0.000,  0.000,  0.000,  0.000,         # Neck/Head
    -0.003, -0.065,  0.635,  1.379, -0.796   # Right leg
], dtype=np.float32)

class RobotStateMachine:
    """
    State Machine (FSM) enforcing deterministic transition rules:
    BOOT -> SELF_TEST -> CALIBRATION -> SAFE_IDLE -> STAND <--> WALK
    With priority interrupts: FALL -> RECOVERY (remains limp), LOW_BATTERY, THERMAL_LIMIT, EMERGENCY_STOP.
    """
    def __init__(self, servo_driver: STS3215Driver, state_ref: RobotStateStruct, cmd_ref: CommandQueueStruct):
        self.servo = servo_driver
        self.state_ref = state_ref
        self.cmd_ref = cmd_ref
        
        # Initial State
        self.state = "BOOT"
        self.update_fsm_state_in_shm()
        self.last_state_time = time.time()
        self.transition_to("BOOT")
        
        # Internal standing interpolation variables
        self.stand_start_time = 0.0
        self.stand_duration = 2.0
        self.start_posture = np.zeros(14, dtype=np.float32)

    def update_fsm_state_in_shm(self):
        self.state_ref.fsm_state = self.state.encode("utf-8")[:32]

    def transition_to(self, new_state: str):
        if self.state == new_state:
            return
            
        logger.info(f"FSM Transition: {self.state} -> {new_state}")
        self.state = new_state
        self.update_fsm_state_in_shm()
        self.last_state_time = time.time()
        
        # Entry actions
        if new_state == "BOOT":
            # Clear targets
            self.servo.set_torque_broadcast(False)
        elif new_state == "SELF_TEST":
            # Self-test logic happens in update loop
            pass
        elif new_state == "CALIBRATION":
            # Load offsets, verify encoders are reporting reasonable values
            pass
        elif new_state == "SAFE_IDLE":
            # Enable torque and sit stable/limp
            self.servo.set_torque_broadcast(True)
        elif new_state == "STAND":
            self.stand_start_time = time.time()
            # Read current positions to interpolate from
            current_positions = []
            for s_id in range(1, 15):
                pos, _, _ = self.servo.read_servo_telemetry(s_id)
                # Convert 0-4095 ticks to rad relative to home (-pi to +pi)
                rad = ((pos - 2048) / 2048.0) * math_pi()
                current_positions.append(rad)
            self.start_posture = np.array(current_positions, dtype=np.float32)
        elif new_state == "WALK":
            # Walking is managed by policy executor
            pass
        elif new_state == "FALL":
            # Immediately go limp to protect motors!
            self.servo.set_torque_broadcast(False)
            logger.warning("SAFETY CRITICAL: Robot has fallen! Disabling torque on all joints.")
        elif new_state == "RECOVERY":
            # User choice: remain completely limp (Torque Enable = 0)
            self.servo.set_torque_broadcast(False)
            logger.info("FSM entered RECOVERY: remaining limp, waiting for user STAND/RESET command.")
        elif new_state == "EMERGENCY_STOP":
            self.servo.set_torque_broadcast(False)
            logger.critical("EMERGENCY SHUTDOWN TRIGGERED! Servos set to LIMP mode.")

    def step(self, 
             battery_voltage: float, 
             max_servo_temp: int, 
             fallen_detected: bool, 
             servo_runaway_detected: bool,
             battery_temp: float = 25.0):
        """Processes FSM updates once per control loop tick (50Hz)."""
        now = time.time()
        
        # Global high-priority emergency interrupts
        if servo_runaway_detected or self.cmd_ref.state_override == b"EMERGENCY_STOP":
            self.transition_to("EMERGENCY_STOP")
            return
            
        if battery_voltage < 9.9:  # 3S battery cutoff (3.3V per cell)
            if self.state not in ("EMERGENCY_STOP", "SAFE_IDLE", "BOOT"):
                logger.critical(f"LOW BATTERY DETECTED ({battery_voltage}V)! Forcing emergency torque-off.")
                self.transition_to("EMERGENCY_STOP")
                return
                
        if max_servo_temp >= 68:  # Thermo-cutoff limit
            if self.state not in ("EMERGENCY_STOP", "SAFE_IDLE", "BOOT"):
                logger.critical(f"THERMAL LIMIT EXCEEDED ({max_servo_temp}C)! Forcing emergency torque-off.")
                self.transition_to("EMERGENCY_STOP")
                return

        if battery_temp >= 60.0:  # Battery thermal limit cutoff
            if self.state not in ("EMERGENCY_STOP", "SAFE_IDLE", "BOOT"):
                logger.critical(f"BATTERY THERMAL LIMIT EXCEEDED ({battery_temp}C)! Forcing emergency torque-off.")
                self.transition_to("EMERGENCY_STOP")
                return

        if fallen_detected and self.state in ("STAND", "WALK"):
            self.transition_to("FALL")
            return

        # FSM State Logic Loop
        if self.state == "BOOT":
            if now - self.last_state_time > 0.5:
                self.transition_to("SELF_TEST")
                
        elif self.state == "SELF_TEST":
            # Verify servo communications by Pinging ID 1 to 14
            self.transition_to("CALIBRATION")
            
        elif self.state == "CALIBRATION":
            # Calibration logic
            self.transition_to("SAFE_IDLE")
            
        elif self.state == "SAFE_IDLE":
            # Wait for API STAND command
            if self.cmd_ref.cmd_type == b"stand" or self.cmd_ref.state_override == b"STAND":
                # Clear override flag
                self.cmd_ref.state_override = b""
                self.transition_to("STAND")
                
        elif self.state == "STAND":
            # Interpolate from start_posture to DEFAULT_STAND_POSTURE
            elapsed = now - self.stand_start_time
            alpha = min(1.0, elapsed / self.stand_duration)
            
            interpolated = (1.0 - alpha) * self.start_posture + alpha * DEFAULT_STAND_POSTURE
            
            # Send sync positions to servos
            targets = []
            for idx, rad_pos in enumerate(interpolated):
                servo_id = idx + 1
                # Convert rad to 0-4095 ticks
                ticks = int((rad_pos / math_pi()) * 2048.0 + 2048)
                targets.append((servo_id, ticks))
            self.servo.write_positions_sync(targets)
            
            if alpha >= 1.0:
                logger.info("Standing completed successfully.")
                self.transition_to("WALK")
                
        elif self.state == "WALK":
            # Command from high level can tell us to sit/idle
            if self.cmd_ref.cmd_type == b"stop" or self.cmd_ref.cmd_type == b"reset":
                self.transition_to("SAFE_IDLE")
                
        elif self.state == "FALL":
            # Automatically progress to RECOVERY (remains limp)
            self.transition_to("RECOVERY")
            
        elif self.state == "RECOVERY":
            # Awaiting user reset / STAND command to stand back up
            if self.cmd_ref.cmd_type == b"stand" or self.cmd_ref.state_override == b"STAND":
                self.cmd_ref.state_override = b""
                self.transition_to("STAND")
                
        elif self.state == "EMERGENCY_STOP":
            # Awaiting explicit reset override
            if self.cmd_ref.state_override == b"BOOT":
                self.cmd_ref.state_override = b""
                self.transition_to("BOOT")

def math_pi() -> float:
    import math
    return math.pi
