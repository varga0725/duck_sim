import math
import threading
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Tuple

import numpy as np


@dataclass
class LegacyDynamicsDiagnostics:
    mode: str = "legacy"
    qpos_xy_integration_count: int = 0
    qpos_z_forcing_count: int = 0
    torso_quaternion_overwrite_count: int = 0
    torso_orientation_correction_magnitude_sum: float = 0.0
    torso_orientation_correction_magnitude_max: float = 0.0
    qvel_xy_forcing_count: int = 0
    qvel_roll_pitch_zeroing_count: int = 0
    qvel_roll_pitch_damping_magnitude_sum: float = 0.0
    qvel_roll_pitch_damping_magnitude_max: float = 0.0
    qpos_z_correction_magnitude_sum: float = 0.0
    qpos_z_correction_magnitude_max: float = 0.0
    correction_magnitude_sum: float = 0.0
    correction_magnitude_max: float = 0.0
    contact_samples: int = 0
    left_contact_samples: int = 0
    right_contact_samples: int = 0
    both_contact_samples: int = 0
    last_roll_deg: float = 0.0
    last_pitch_deg: float = 0.0
    last_body_height_m: float = 0.0
    last_actuator_saturation: float = 0.0
    last_qvel_xy_commanded_magnitude: float = 0.0
    last_fall_reason: str | None = None

    def snapshot(self) -> Dict[str, Any]:
        data = asdict(self)
        if self.contact_samples > 0:
            data["contact_duty_factor"] = {
                "left": self.left_contact_samples / self.contact_samples,
                "right": self.right_contact_samples / self.contact_samples,
                "both": self.both_contact_samples / self.contact_samples,
            }
        else:
            data["contact_duty_factor"] = {"left": 0.0, "right": 0.0, "both": 0.0}
        return data


@dataclass
class LegacyDynamicsController:
    mode: str = "legacy"
    fixed_dt_sec: float = 0.002
    hybrid_qvel_xy_scale: float = 1.0
    hybrid_z_force_scale: float = 1.0
    hybrid_rp_qvel_zero_scale: float = 1.0
    hybrid_torso_orientation_scale: float = 1.0
    diagnostics: LegacyDynamicsDiagnostics = field(default_factory=LegacyDynamicsDiagnostics)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def __post_init__(self) -> None:
        self.diagnostics.mode = self.mode

    def apply(self, simulator: Any) -> None:
        before_qpos = np.array(simulator.data.qpos[0:7], copy=True)
        before_qvel = np.array(simulator.data.qvel[0:6], copy=True)

        if self.mode == "pure_physics":
            # Pure physics mode: no state injection, no coordinate/velocity forcing.
            qw, qx, qy, qz = simulator.data.qpos[3:7]
            roll, pitch, yaw = simulator.quaternion_to_euler(qw, qx, qy, qz)
            simulator._kinematic_yaw = math.radians(yaw)
            
            left_contact = simulator.check_contact("foot_assembly", "floor")
            right_contact = simulator.check_contact("foot_assembly_2", "floor")
            actuator_saturation = self._actuator_saturation(simulator)
            body_height = float(simulator.data.qpos[2])
            fall_reason = self._fall_reason(roll, pitch, body_height)
            
            self.record(
                before_qpos=before_qpos,
                after_qpos=before_qpos,
                before_qvel=before_qvel,
                after_qvel=before_qvel,
                roll_deg=roll,
                pitch_deg=pitch,
                body_height_m=body_height,
                left_contact=left_contact,
                right_contact=right_contact,
                actuator_saturation=actuator_saturation,
                fall_reason=fall_reason,
                qpos_xy_integrated=False,
                qvel_xy_forced=False,
                qvel_xy_commanded_magnitude=0.0,
                qpos_z_forced=False,
                qpos_z_correction_magnitude=0.0,
                rp_qvel_zeroed=False,
                rp_qvel_damping_magnitude=0.0,
                torso_orientation_overwritten=False,
                torso_orientation_correction_magnitude=0.0,
            )
            return

        simulator._kinematic_yaw += simulator._current_yaw_rate * self.fixed_dt_sec
        yaw_rad = simulator._kinematic_yaw

        qw, qx, qy, qz = simulator.data.qpos[3:7]
        roll, pitch, _yaw = simulator.quaternion_to_euler(qw, qx, qy, qz)

        max_roll_allow = 6.0
        max_pitch_allow = 4.0
        roll_stabilized = max(-max_roll_allow, min(max_roll_allow, roll))
        pitch_stabilized = max(-max_pitch_allow, min(max_pitch_allow, pitch))

        roll_rad = math.radians(roll_stabilized)
        pitch_rad = math.radians(pitch_stabilized)

        cr = math.cos(roll_rad / 2.0)
        sr = math.sin(roll_rad / 2.0)
        cp = math.cos(pitch_rad / 2.0)
        sp = math.sin(pitch_rad / 2.0)
        cy = math.cos(yaw_rad / 2.0)
        sy = math.sin(yaw_rad / 2.0)

        current_quat = np.array(simulator.data.qpos[3:7], dtype=float, copy=True)
        target_quat = np.array(
            [
                cr * cp * cy + sr * sp * sy,
                sr * cp * cy - cr * sp * sy,
                cr * sp * cy + sr * cp * sy,
                cr * cp * sy - sr * sp * cy,
            ],
            dtype=float,
        )
        torso_orientation_scale = self.hybrid_torso_orientation_scale if self.mode == "hybrid" else 1.0
        torso_orientation_overwritten = not (self.mode == "hybrid" and torso_orientation_scale == 0.0)
        torso_orientation_correction_magnitude = float(np.linalg.norm(target_quat - current_quat) * torso_orientation_scale)
        if torso_orientation_overwritten:
            if float(np.dot(current_quat, target_quat)) < 0.0:
                target_quat = -target_quat
            blended_quat = current_quat + (target_quat - current_quat) * torso_orientation_scale
            norm = float(np.linalg.norm(blended_quat))
            if norm > 1e-12:
                blended_quat = blended_quat / norm
            simulator.data.qpos[3:7] = blended_quat

        z_force_scale = self.hybrid_z_force_scale if self.mode == "hybrid" else 1.0
        target_z = 0.15
        before_z = float(simulator.data.qpos[2])
        z_correction = (target_z - before_z) * z_force_scale
        z_forced = not (self.mode == "hybrid" and z_force_scale == 0.0)
        if z_forced:
            simulator.data.qpos[2] = before_z + z_correction
            simulator.data.qvel[2] = 0.0

        global_vx = simulator._current_linear_x * math.cos(yaw_rad) - simulator._current_linear_y * math.sin(yaw_rad)
        global_vy = simulator._current_linear_x * math.sin(yaw_rad) + simulator._current_linear_y * math.cos(yaw_rad)
        qvel_xy_scale = self.hybrid_qvel_xy_scale if self.mode == "hybrid" else 1.0
        applied_vx = global_vx * qvel_xy_scale
        applied_vy = global_vy * qvel_xy_scale

        qvel_xy_forced = not (self.mode == "hybrid" and qvel_xy_scale == 0.0)
        if qvel_xy_forced:
            simulator.data.qvel[0] = applied_vx
            simulator.data.qvel[1] = applied_vy

        qpos_xy_integrated = self.mode != "hybrid"
        if qpos_xy_integrated:
            simulator.data.qpos[0] += global_vx * self.fixed_dt_sec
            simulator.data.qpos[1] += global_vy * self.fixed_dt_sec

        rp_qvel_zero_scale = self.hybrid_rp_qvel_zero_scale if self.mode == "hybrid" else 1.0
        before_roll_qvel = float(simulator.data.qvel[3])
        before_pitch_qvel = float(simulator.data.qvel[4])
        rp_qvel_damping_magnitude = math.hypot(before_roll_qvel, before_pitch_qvel) * rp_qvel_zero_scale
        rp_qvel_zeroed = not (self.mode == "hybrid" and rp_qvel_zero_scale == 0.0)
        if rp_qvel_zeroed:
            simulator.data.qvel[3] = before_roll_qvel * (1.0 - rp_qvel_zero_scale)
            simulator.data.qvel[4] = before_pitch_qvel * (1.0 - rp_qvel_zero_scale)
        simulator.data.qvel[5] = simulator._current_yaw_rate

        left_contact = simulator.check_contact("foot_assembly", "floor")
        right_contact = simulator.check_contact("foot_assembly_2", "floor")
        actuator_saturation = self._actuator_saturation(simulator)
        body_height = float(simulator.data.qpos[2])
        fall_reason = self._fall_reason(roll, pitch, body_height)
        qvel_xy_commanded_magnitude = math.hypot(applied_vx, applied_vy)

        self.record(
            before_qpos=before_qpos,
            after_qpos=np.array(simulator.data.qpos[0:7], copy=True),
            before_qvel=before_qvel,
            after_qvel=np.array(simulator.data.qvel[0:6], copy=True),
            roll_deg=roll,
            pitch_deg=pitch,
            body_height_m=body_height,
            left_contact=left_contact,
            right_contact=right_contact,
            actuator_saturation=actuator_saturation,
            fall_reason=fall_reason,
            qpos_xy_integrated=qpos_xy_integrated,
            qvel_xy_forced=qvel_xy_forced,
            qvel_xy_commanded_magnitude=qvel_xy_commanded_magnitude,
            qpos_z_forced=z_forced,
            qpos_z_correction_magnitude=abs(float(z_correction)),
            rp_qvel_zeroed=rp_qvel_zeroed,
            rp_qvel_damping_magnitude=rp_qvel_damping_magnitude,
            torso_orientation_overwritten=torso_orientation_overwritten,
            torso_orientation_correction_magnitude=torso_orientation_correction_magnitude,
        )

    def record(
        self,
        *,
        before_qpos: np.ndarray,
        after_qpos: np.ndarray,
        before_qvel: np.ndarray,
        after_qvel: np.ndarray,
        roll_deg: float,
        pitch_deg: float,
        body_height_m: float,
        left_contact: bool,
        right_contact: bool,
        actuator_saturation: float,
        fall_reason: str | None,
        qpos_xy_integrated: bool,
        qvel_xy_forced: bool,
        qvel_xy_commanded_magnitude: float,
        qpos_z_forced: bool,
        qpos_z_correction_magnitude: float,
        rp_qvel_zeroed: bool,
        rp_qvel_damping_magnitude: float,
        torso_orientation_overwritten: bool,
        torso_orientation_correction_magnitude: float,
    ) -> None:
        correction = float(np.linalg.norm(after_qpos - before_qpos) + np.linalg.norm(after_qvel - before_qvel))
        with self._lock:
            d = self.diagnostics
            d.qpos_xy_integration_count += int(qpos_xy_integrated)
            d.qpos_z_forcing_count += int(qpos_z_forced)
            d.torso_quaternion_overwrite_count += int(torso_orientation_overwritten)
            d.torso_orientation_correction_magnitude_sum += float(torso_orientation_correction_magnitude)
            d.torso_orientation_correction_magnitude_max = max(
                d.torso_orientation_correction_magnitude_max,
                float(torso_orientation_correction_magnitude),
            )
            d.qvel_xy_forcing_count += int(qvel_xy_forced)
            d.qvel_roll_pitch_zeroing_count += int(rp_qvel_zeroed)
            d.qvel_roll_pitch_damping_magnitude_sum += float(rp_qvel_damping_magnitude)
            d.qvel_roll_pitch_damping_magnitude_max = max(
                d.qvel_roll_pitch_damping_magnitude_max,
                float(rp_qvel_damping_magnitude),
            )
            d.qpos_z_correction_magnitude_sum += float(qpos_z_correction_magnitude)
            d.qpos_z_correction_magnitude_max = max(
                d.qpos_z_correction_magnitude_max,
                float(qpos_z_correction_magnitude),
            )
            d.correction_magnitude_sum += correction
            d.correction_magnitude_max = max(d.correction_magnitude_max, correction)
            d.contact_samples += 1
            d.left_contact_samples += int(left_contact)
            d.right_contact_samples += int(right_contact)
            d.both_contact_samples += int(left_contact and right_contact)
            d.last_roll_deg = float(roll_deg)
            d.last_pitch_deg = float(pitch_deg)
            d.last_body_height_m = float(body_height_m)
            d.last_actuator_saturation = float(actuator_saturation)
            d.last_qvel_xy_commanded_magnitude = float(qvel_xy_commanded_magnitude)
            d.last_fall_reason = fall_reason

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return self.diagnostics.snapshot()

    @staticmethod
    def _actuator_saturation(simulator: Any) -> float:
        ctrl = getattr(simulator.data, "ctrl", None)
        ctrlrange = getattr(simulator.model, "actuator_ctrlrange", None)
        if ctrl is None or ctrlrange is None or len(ctrl) == 0:
            return 0.0

        lower = ctrlrange[:, 0]
        upper = ctrlrange[:, 1]
        span = np.maximum(upper - lower, 1e-9)
        normalized = np.maximum((ctrl - lower) / span, (upper - ctrl) / span)
        return float(np.clip(np.max(normalized), 0.0, 1.0))

    @staticmethod
    def _fall_reason(roll_deg: float, pitch_deg: float, body_height_m: float) -> str | None:
        reasons: list[str] = []
        if abs(roll_deg) > 35.0:
            reasons.append("roll_limit")
        if abs(pitch_deg) > 35.0:
            reasons.append("pitch_limit")
        if body_height_m < 0.15:
            reasons.append("body_height")
        return ",".join(reasons) if reasons else None
