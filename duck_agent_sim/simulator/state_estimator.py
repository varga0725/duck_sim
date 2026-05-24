import logging
import math
import numpy as np
from typing import Tuple, Dict, Any

logger = logging.getLogger("duck-state-estimator")

class StateEstimator:
    """
    Complementary Kinematic-Inertial State Estimator.
    Estimates 3D torso linear velocity (Vx, Vy, Vz) by fusing:
    - IMU accelerations rotated to the world frame
    - Forward kinematics velocity (based on stance leg joint speeds)
    - Foot contact switches (to weigh stance vs swing legs)
    """
    def __init__(self, dt: float = 0.02, alpha: float = 0.15, beta: float = 0.10):
        self.dt = dt
        self.alpha = alpha  # Complementary filter weight for kinematics vs accelerometer
        self.beta = beta    # Complementary filter weight for visual odometry
        
        # State variables
        self.velocity = np.zeros(3, dtype=np.float32)  # [Vx, Vy, Vz] in world/body frame
        self.position = np.zeros(3, dtype=np.float32)  # [X, Y, Z]
        
        # Gravity vector
        self.gravity = np.array([0.0, 0.0, -9.81], dtype=np.float32)
        
        # Leg dimensions (link lengths for kinematic jacobian approximation)
        self.thigh_length = 0.18
        self.shin_length = 0.18
        self.foot_offset = 0.05
        
        # Store previous simulation position for visual odometry estimation
        self._prev_sim_pos = None

    def reset(self, initial_position: Tuple[float, float, float] = (0.0, 0.0, 0.41)):
        self.velocity = np.zeros(3, dtype=np.float32)
        self.position = np.array(initial_position, dtype=np.float32)
        self._prev_sim_pos = None
        logger.info(f"State Estimator reset to position: {initial_position}")

    def _rotate_vector_by_quaternion(self, v: np.ndarray, q: Tuple[float, float, float, float]) -> np.ndarray:
        """Rotates a 3D vector v by a quaternion q (w, x, y, z)."""
        w, x, y, z = q
        # Quaternion multiplication: q * v * q_conj
        num1 = x * 2.0
        num2 = y * 2.0
        num3 = z * 2.0
        num4 = x * num1
        num5 = y * num2
        num6 = z * num3
        num7 = x * num2
        num8 = x * num3
        num9 = y * num3
        num10 = w * num1
        num11 = w * num2
        num12 = w * num3
        
        rx = (1.0 - (num5 + num6)) * v[0] + (num7 - num12) * v[1] + (num8 + num11) * v[2]
        ry = (num7 + num12) * v[0] + (1.0 - (num4 + num6)) * v[1] + (num9 - num10) * v[2]
        rz = (num8 - num11) * v[0] + (num9 + num10) * v[1] + (1.0 - (num4 + num5)) * v[2]
        
        return np.array([rx, ry, rz], dtype=np.float32)

    def _calculate_kinematic_velocity(self, joint_angles: np.ndarray, joint_velocities: np.ndarray, is_left: bool) -> np.ndarray:
        """
        Approximates leg forward kinematics velocity of the torso relative to the foot.
        joint_angles/velocities order: [hip_yaw, hip_roll, hip_pitch, knee, ankle] (5 joints)
        """
        # A simplified leg Jacobian mapping joint speeds to torso Cartesian speed
        # If leg is in contact (stance phase), V_torso = - J * dtheta
        # Joint layout:
        # hip_pitch (index 2), knee (index 3), ankle (index 4)
        hp_val = joint_angles[2]
        kn_val = joint_angles[3]
        ak_val = joint_angles[4]
        
        d_hp = joint_velocities[2]
        d_kn = joint_velocities[3]
        d_ak = joint_velocities[4]
        
        # Simple sagittal plane 2R link kinematics approximation for vertical/forward speeds
        # Torso relative to foot:
        # Z = thigh * cos(hp) + shin * cos(hp + kn)
        # X = thigh * sin(hp) + shin * sin(hp + kn)
        
        # Sagittal velocities relative to foot
        vx = self.thigh_length * math.cos(hp_val) * d_hp + self.shin_length * math.cos(hp_val + kn_val) * (d_hp + d_kn)
        vz = -self.thigh_length * math.sin(hp_val) * d_hp - self.shin_length * math.sin(hp_val + kn_val) * (d_hp + d_kn)
        
        # Roll/lateral speed approximation from hip roll
        hr_val = joint_angles[1]
        d_hr = joint_velocities[1]
        vy = - (self.thigh_length + self.shin_length) * math.sin(hr_val) * d_hr
        if not is_left:
            vy = -vy  # invert for right leg symmetry
            
        return np.array([vx, vy, vz], dtype=np.float32)

    def estimate_visual_odometry(self, frame_prev: Any = None, frame_curr: Any = None) -> np.ndarray:
        """
        Estimates visual odometry delta displacement [dx, dy, dz] in the world frame.
        In mock mode, queries the active simulator's position and adds minor Gaussian noise.
        """
        curr_sim_pos = None
        try:
            from duck_agent_sim.simulator.instance import active_simulator
            state = active_simulator.get_state()
            if state and hasattr(state, "position"):
                curr_sim_pos = np.array(state.position, dtype=np.float32)
        except Exception:
            pass

        if curr_sim_pos is not None:
            if self._prev_sim_pos is None:
                self._prev_sim_pos = curr_sim_pos
                delta = np.zeros(3, dtype=np.float32)
            else:
                delta = curr_sim_pos - self._prev_sim_pos
                self._prev_sim_pos = curr_sim_pos
        else:
            # Fallback when simulator state isn't available
            delta = self.velocity * self.dt

        # Add minor Gaussian noise to emulate visual drift
        noise = np.random.normal(0, 0.002, size=3).astype(np.float32)
        return delta + noise

    def update(self, 
               imu_accel: Tuple[float, float, float], 
               imu_quat: Tuple[float, float, float, float],
               left_contact: bool, 
               right_contact: bool,
               left_joint_angles: np.ndarray,
               left_joint_vel: np.ndarray,
               right_joint_angles: np.ndarray,
               right_joint_vel: np.ndarray,
               frame_prev: Any = None,
               frame_curr: Any = None) -> Tuple[np.ndarray, np.ndarray]:
        """
        Performs a single estimation step.
        Returns: (velocity_3d, position_3d)
        """
        acc = np.array(imu_accel, dtype=np.float32)
        
        # 1. Rotate linear accelerometer measurements to world frame and subtract gravity
        acc_world = self._rotate_vector_by_quaternion(acc, imu_quat) + self.gravity
        
        # 2. Integrate accelerometer to get inertial velocity proposal
        v_inertial = self.velocity + acc_world * self.dt
        
        # 3. Calculate forward kinematics velocity proposal for contact feet
        v_kin = np.zeros(3, dtype=np.float32)
        active_contacts = 0
        
        if left_contact:
            v_kin += self._calculate_kinematic_velocity(left_joint_angles, left_joint_vel, is_left=True)
            active_contacts += 1
            
        if right_contact:
            v_kin += self._calculate_kinematic_velocity(right_joint_angles, right_joint_vel, is_left=False)
            active_contacts += 1
            
        # 3.5. Estimate Visual Odometry
        vo_translation = self.estimate_visual_odometry(frame_prev, frame_curr)
        v_vo = vo_translation / self.dt
        
        # 4. Complementary Fusion
        if active_contacts > 0:
            # Average kinematic velocity proposal across contacts
            v_kin_avg = v_kin / active_contacts
            # Keep Z height estimator bounded using kinematic Z speed
            # Filter Vx, Vy, Vz combining inertial, kinematics, and visual odometry
            self.velocity = (1.0 - self.alpha - self.beta) * v_inertial + self.alpha * v_kin_avg + self.beta * v_vo
        else:
            # No contacts (aerial phase or fall). Combine inertial and visual odometry
            self.velocity = (1.0 - self.beta) * v_inertial + self.beta * v_vo
            
        # 5. Position integration
        self.position += self.velocity * self.dt
        
        # Keep height Z bounded if contact is active to prevent integration drift
        if active_contacts > 0:
            # Average kin Z height calculation: home pose is ~0.41m, computed Z from stance joint trigonometry
            # We enforce a soft correction towards the kin-derived height
            z_kin_left = self.thigh_length * math.cos(left_joint_angles[2]) + self.shin_length * math.cos(left_joint_angles[2] + left_joint_angles[3])
            z_kin_right = self.thigh_length * math.cos(right_joint_angles[2]) + self.shin_length * math.cos(right_joint_angles[2] + right_joint_angles[3])
            
            z_kin_avg = 0.0
            if left_contact and right_contact:
                z_kin_avg = (z_kin_left + z_kin_right) / 2.0
            elif left_contact:
                z_kin_avg = z_kin_left
            else:
                z_kin_avg = z_kin_right
            
            # Add foot clearance height offset
            estimated_z_height = z_kin_avg + self.foot_offset
            # Apply soft correction (1% correction per frame)
            self.position[2] = 0.99 * self.position[2] + 0.01 * estimated_z_height
            
        return self.velocity.copy(), self.position.copy()
