import logging
import numpy as np
from typing import Dict, Tuple

logger = logging.getLogger("duck-trajectory-filter")

class TrajectoryFilter:
    """
    Trajectory joint filter with velocity and acceleration limiting.
    Smoothes step changes in position commands to protect physical actuators from
    extreme acceleration/jerk spikes.
    """
    def __init__(self, 
                 num_joints: int = 14, 
                 dt: float = 0.02, 
                 max_velocity: float = 5.24,       # rad/s
                 max_acceleration: float = 40.0):   # rad/s^2
        self.num_joints = num_joints
        self.dt = dt
        self.max_velocity = max_velocity
        self.max_acceleration = max_acceleration
        
        # Filter states
        self.positions = None
        self.velocities = None

    def reset(self, initial_positions: np.ndarray):
        """Resets filter state to the given starting coordinates."""
        self.positions = np.array(initial_positions, dtype=np.float32)
        self.velocities = np.zeros(self.num_joints, dtype=np.float32)
        logger.info(f"Trajectory filter reset to positions: {self.positions}")

    def filter(self, target_positions: np.ndarray) -> np.ndarray:
        """
        Filters target positions to obey velocity and acceleration bounds.
        Returns the safe target positions to send to the actuator bus.
        """
        targets = np.array(target_positions, dtype=np.float32)
        
        if self.positions is None:
            self.reset(targets)
            return self.positions.copy()
            
        # Calculate nominal required velocity
        v_required = (targets - self.positions) / self.dt
        
        # Calculate nominal required acceleration
        a_required = (v_required - self.velocities) / self.dt
        
        # Clamp acceleration to limits
        a_clamped = np.clip(a_required, -self.max_acceleration, self.max_acceleration)
        
        # Update velocities with clamped acceleration
        v_next = self.velocities + a_clamped * self.dt
        
        # Clamp velocities to limits
        self.velocities = np.clip(v_next, -self.max_velocity, self.max_velocity)
        
        # Integrate to get new positions
        self.positions += self.velocities * self.dt
        
        return self.positions.copy()
