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
    qvel_xy_forcing_count: int = 0
    qvel_roll_pitch_zeroing_count: int = 0
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
    diagnostics: LegacyDynamicsDiagnostics = field(default_factory=LegacyDynamicsDiagnostics)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def __post_init__(self) -> None:
        self.diagnostics.mode = self.mode

    def apply(self, simulator: Any) -> None:
        before_qpos = np.array(simulator.data.qpos[0:7], copy=True)
        before_qvel = np.array(simulator.data.qvel[0:6], copy=True)

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

        simulator.data.qpos[3] = cr * cp * cy + sr * sp * sy
        simulator.data.qpos[4] = sr * cp * cy - cr * sp * sy
        simulator.data.qpos[5] = cr * sp * cy + sr * cp * sy
        simulator.data.qpos[6] = cr * cp * sy - sr * sp * cy

        simulator.data.qpos[2] = 0.15
        simulator.data.qvel[2] = 0.0

        global_vx = simulator._current_linear_x * math.cos(yaw_rad) - simulator._current_linear_y * math.sin(yaw_rad)
        global_vy = simulator._current_linear_x * math.sin(yaw_rad) + simulator._current_linear_y * math.cos(yaw_rad)

        simulator.data.qvel[0] = global_vx
        simulator.data.qvel[1] = global_vy

        qpos_xy_integrated = self.mode != "hybrid"
        if qpos_xy_integrated:
            simulator.data.qpos[0] += global_vx * self.fixed_dt_sec
            simulator.data.qpos[1] += global_vy * self.fixed_dt_sec

        simulator.data.qvel[3] = 0.0
        simulator.data.qvel[4] = 0.0
        simulator.data.qvel[5] = simulator._current_yaw_rate

        left_contact = simulator.check_contact("foot_assembly", "floor")
        right_contact = simulator.check_contact("foot_assembly_2", "floor")
        actuator_saturation = self._actuator_saturation(simulator)
        fall_reason = self._fall_reason(roll, pitch, float(simulator.data.qpos[2]))

        self.record(
            before_qpos=before_qpos,
            after_qpos=np.array(simulator.data.qpos[0:7], copy=True),
            before_qvel=before_qvel,
            after_qvel=np.array(simulator.data.qvel[0:6], copy=True),
            roll_deg=roll,
            pitch_deg=pitch,
            body_height_m=float(simulator.data.qpos[2]),
            left_contact=left_contact,
            right_contact=right_contact,
            actuator_saturation=actuator_saturation,
            fall_reason=fall_reason,
            qpos_xy_integrated=qpos_xy_integrated,
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
    ) -> None:
        correction = float(np.linalg.norm(after_qpos - before_qpos) + np.linalg.norm(after_qvel - before_qvel))
        with self._lock:
            d = self.diagnostics
            d.qpos_xy_integration_count += int(qpos_xy_integrated)
            d.qpos_z_forcing_count += 1
            d.torso_quaternion_overwrite_count += 1
            d.qvel_xy_forcing_count += 1
            d.qvel_roll_pitch_zeroing_count += 1
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
