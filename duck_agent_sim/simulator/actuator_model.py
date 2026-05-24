import numpy as np
from typing import Tuple

class STS3215ActuatorModel:
    """
    Simulated actuator model for the Feetech STS3215 servo.
    Models the motor speed-torque curve (back-EMF torque decay) and voltage limitations.
    Formula: max_torque = stall_torque * (1 - speed / no_load_speed)
    """
    def __init__(self, 
                 stall_torque: float = 3.23,       # N*m (forcerange in MuJoCo config)
                 no_load_speed: float = 6.28,      # rad/s (~60 RPM)
                 voltage: float = 12.0):           # V
        self.stall_torque = stall_torque
        self.no_load_speed = no_load_speed
        self.voltage = voltage

    def get_torque_bounds(self, current_joint_velocities: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """
        Calculates dynamic torque (force) limits based on the present joint velocities.
        Returns: (min_torque, max_torque) bounds arrays.
        """
        speeds = np.abs(current_joint_velocities)
        
        # Calculate dynamic torque limit based on motor speed curve
        # Torque decays linearly with speed
        torque_limit = self.stall_torque * (1.0 - np.clip(speeds / self.no_load_speed, 0.0, 0.95))
        
        # Positive speed opposes positive torque, negative speed opposes negative torque
        # So maximum force we can apply in the direction of motion is reduced,
        # but braking torque can be slightly higher (here we clamp symmetrically for simplicity)
        min_torque = -torque_limit
        max_torque = torque_limit
        
        return min_torque, max_torque
