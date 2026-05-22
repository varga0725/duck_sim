#!/usr/bin/env python3
import argparse
import json
import os
import statistics
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class DiagnosticCase:
    name: str
    dynamics_mode: str
    qvel_scale: float | None = None
    z_force_scale: float | None = None
    rp_qvel_zero_scale: float | None = None
    torso_orientation_scale: float | None = None


PHASE2D_MATRIX = (
    DiagnosticCase("legacy", "legacy", None),
    DiagnosticCase("hybrid_scale_1_0", "hybrid", 1.0),
    DiagnosticCase("hybrid_scale_0_5", "hybrid", 0.5),
    DiagnosticCase("hybrid_scale_0_0", "hybrid", 0.0),
)

PHASE2E_MATRIX = (
    DiagnosticCase("legacy", "legacy", None, None),
    DiagnosticCase("hybrid_qvel_0_0_z_1_0", "hybrid", 0.0, 1.0),
    DiagnosticCase("hybrid_qvel_0_0_z_0_5", "hybrid", 0.0, 0.5),
    DiagnosticCase("hybrid_qvel_0_0_z_0_0", "hybrid", 0.0, 0.0),
    DiagnosticCase("hybrid_qvel_1_0_z_1_0", "hybrid", 1.0, 1.0),
    DiagnosticCase("hybrid_qvel_1_0_z_0_5", "hybrid", 1.0, 0.5),
    DiagnosticCase("hybrid_qvel_1_0_z_0_0", "hybrid", 1.0, 0.0),
)

PHASE2F_MATRIX = (
    DiagnosticCase("legacy", "legacy", None, None, None),
    DiagnosticCase("hybrid_qvel_0_0_z_1_0_rp_1_0", "hybrid", 0.0, 1.0, 1.0),
    DiagnosticCase("hybrid_qvel_0_0_z_1_0_rp_0_5", "hybrid", 0.0, 1.0, 0.5),
    DiagnosticCase("hybrid_qvel_0_0_z_1_0_rp_0_0", "hybrid", 0.0, 1.0, 0.0),
    DiagnosticCase("hybrid_qvel_0_0_z_0_5_rp_1_0", "hybrid", 0.0, 0.5, 1.0),
    DiagnosticCase("hybrid_qvel_0_0_z_0_5_rp_0_5", "hybrid", 0.0, 0.5, 0.5),
    DiagnosticCase("hybrid_qvel_0_0_z_0_5_rp_0_0", "hybrid", 0.0, 0.5, 0.0),
)

PHASE2G_MATRIX = (
    DiagnosticCase("legacy", "legacy", None, None, None, None),
    DiagnosticCase("hybrid_qvel_0_0_z_1_0_rp_0_5_torso_1_0", "hybrid", 0.0, 1.0, 0.5, 1.0),
    DiagnosticCase("hybrid_qvel_0_0_z_1_0_rp_0_5_torso_0_5", "hybrid", 0.0, 1.0, 0.5, 0.5),
    DiagnosticCase("hybrid_qvel_0_0_z_1_0_rp_0_5_torso_0_0", "hybrid", 0.0, 1.0, 0.5, 0.0),
    DiagnosticCase("hybrid_qvel_0_0_z_0_5_rp_0_5_torso_1_0", "hybrid", 0.0, 0.5, 0.5, 1.0),
    DiagnosticCase("hybrid_qvel_0_0_z_0_5_rp_0_5_torso_0_5", "hybrid", 0.0, 0.5, 0.5, 0.5),
    DiagnosticCase("hybrid_qvel_0_0_z_0_5_rp_0_5_torso_0_0", "hybrid", 0.0, 0.5, 0.5, 0.0),
)


def _avg(values: list[float]) -> float | None:
    return statistics.fmean(values) if values else None


def _min(values: list[float]) -> float | None:
    return min(values) if values else None


def _max(values: list[float]) -> float | None:
    return max(values) if values else None


def _stats(values: list[float]) -> dict[str, float | None]:
    return {"min": _min(values), "max": _max(values), "avg": _avg(values)}


def _unwrap_delta_deg(start_deg: float, end_deg: float) -> float:
    return ((end_deg - start_deg + 180.0) % 360.0) - 180.0


def _latest_dynamics(simulator: Any) -> dict[str, Any]:
    getter = getattr(simulator, "get_dynamics_diagnostics", None)
    if getter is None:
        return {}
    return getter()


def _queue_telemetry() -> dict[str, Any]:
    try:
        from duck_agent_sim.services import app_context

        return app_context.registry.get("queue_manager").get_telemetry()
    except Exception:
        return {}


def _simulator() -> Any:
    from duck_agent_sim.services import app_context

    return app_context.registry.get("simulator")


def _run_child(args: argparse.Namespace) -> dict[str, Any]:
    from fastapi.testclient import TestClient

    from duck_agent_sim.main import app

    case = {
        "name": args.case_name,
        "dynamics_mode": os.environ.get("DUCK_DYNAMICS_MODE", ""),
        "qvel_scale": os.environ.get("DUCK_HYBRID_QVEL_XY_SCALE"),
        "z_force_scale": os.environ.get("DUCK_HYBRID_Z_FORCE_SCALE"),
        "rp_qvel_zero_scale": os.environ.get("DUCK_HYBRID_RP_QVEL_ZERO_SCALE"),
        "torso_orientation_scale": os.environ.get("DUCK_HYBRID_TORSO_ORIENTATION_SCALE"),
        "repeats": args.repeats,
        "duration_sec": args.duration_sec,
        "speed": args.speed,
    }
    repeats: list[dict[str, Any]] = []

    with TestClient(app) as client:
        sim = _simulator()
        for repeat_index in range(args.repeats):
            reset = client.post("/reset")
            reset.raise_for_status()
            time.sleep(args.stable_wait_sec)

            start_state = client.get("/state")
            start_state.raise_for_status()
            start = start_state.json()
            start_pos = start["position"]
            start_yaw = start["orientation"]["yaw_deg"]

            samples: list[dict[str, Any]] = []
            sample_errors = 0
            command_result: dict[str, Any] = {}
            command_error: str | None = None

            def issue_command() -> None:
                nonlocal command_result, command_error
                payload = {
                    "command": "walk_forward",
                    "speed": args.speed,
                    "turn": 0.0,
                    "duration_sec": args.duration_sec,
                }
                started = time.monotonic()
                try:
                    response = client.post("/command", json=payload)
                    command_result = {
                        "status_code": response.status_code,
                        "latency_sec": time.monotonic() - started,
                        "body": response.json(),
                    }
                except Exception as exc:
                    command_error = repr(exc)
                    command_result = {"latency_sec": time.monotonic() - started}

            command_thread = threading.Thread(target=issue_command, name="phase2d-command")
            queue_before = _queue_telemetry()
            command_thread.start()
            sample_deadline = time.monotonic() + args.duration_sec
            while time.monotonic() < sample_deadline:
                try:
                    state_response = client.get("/state")
                    state_response.raise_for_status()
                    state = state_response.json()
                    samples.append(
                        {
                            "t": time.monotonic(),
                            "position": state["position"],
                            "orientation": state["orientation"],
                            "feet_contact": state["feet_contact"],
                            "fallen": state["fallen"],
                            "dynamics": _latest_dynamics(sim),
                        }
                    )
                except Exception:
                    sample_errors += 1
                time.sleep(args.sample_period_sec)

            command_thread.join(timeout=args.duration_sec + 5.0)
            if command_thread.is_alive():
                command_error = "command_thread_timeout"
            stop = client.post("/stop")
            stop.raise_for_status()
            queue_after = _queue_telemetry()

            end_state = client.get("/state")
            end_state.raise_for_status()
            end = end_state.json()
            end_pos = end["position"]
            end_yaw = end["orientation"]["yaw_deg"]

            xs = [float(sample["position"][0]) for sample in samples]
            ys = [float(sample["position"][1]) for sample in samples]
            yaws = [float(sample["orientation"]["yaw_deg"]) for sample in samples]
            rolls = [float(sample["orientation"]["roll_deg"]) for sample in samples]
            pitches = [float(sample["orientation"]["pitch_deg"]) for sample in samples]
            heights = [float(sample["position"][2]) for sample in samples]
            left_contacts = [bool(sample["feet_contact"]["left"]) for sample in samples]
            right_contacts = [bool(sample["feet_contact"]["right"]) for sample in samples]
            dynamics_samples = [sample["dynamics"] for sample in samples if sample["dynamics"]]
            latest_dynamics = dynamics_samples[-1] if dynamics_samples else _latest_dynamics(sim)

            elapsed = max(float(command_result.get("latency_sec") or args.duration_sec), 1e-9)
            forward_displacement = float(end_pos[0]) - float(start_pos[0])
            lateral_displacement = float(end_pos[1]) - float(start_pos[1])
            yaw_displacement = float(end_yaw) - float(start_yaw)
            yaw_unwrapped_displacement = _unwrap_delta_deg(float(start_yaw), float(end_yaw))
            actuator_saturations = [
                float(item["dynamics"]["last_actuator_saturation"])
                for item in samples
                if item["dynamics"] and item["dynamics"].get("last_actuator_saturation") is not None
            ]
            correction_sums = [
                float(item["dynamics"]["correction_magnitude_sum"])
                for item in samples
                if item["dynamics"] and item["dynamics"].get("correction_magnitude_sum") is not None
            ]
            correction_rates = [
                max(0.0, end - start) / max(args.sample_period_sec, 1e-9)
                for start, end in zip(correction_sums, correction_sums[1:])
            ]
            no_contact_samples = sum(not (l or r) for l, r in zip(left_contacts, right_contacts))
            first_fall_timestamp = next((sample["t"] for sample in samples if sample["fallen"]), None)
            first_safety_timestamp = time.monotonic() if command_result.get("body", {}).get("safety_intervention") else None

            repeats.append(
                {
                    "repeat": repeat_index + 1,
                    "start_position": start_pos,
                    "end_position": end_pos,
                    "forward_displacement": forward_displacement,
                    "lateral_displacement": lateral_displacement,
                    "yaw_displacement": yaw_displacement,
                    "yaw_unwrapped_displacement": yaw_unwrapped_displacement,
                    "actual_base_velocity": {
                        "x": forward_displacement / elapsed,
                        "y": lateral_displacement / elapsed,
                    },
                    "qpos_xy_integration_count": latest_dynamics.get("qpos_xy_integration_count"),
                    "qvel_xy_forcing_count": latest_dynamics.get("qvel_xy_forcing_count"),
                    "qvel_xy_commanded_magnitude": latest_dynamics.get("last_qvel_xy_commanded_magnitude"),
                    "qpos_z_forcing_count": latest_dynamics.get("qpos_z_forcing_count"),
                    "qpos_z_correction_magnitude_sum": latest_dynamics.get("qpos_z_correction_magnitude_sum"),
                    "qpos_z_correction_magnitude_max": latest_dynamics.get("qpos_z_correction_magnitude_max"),
                    "torso_quaternion_overwrite_count": latest_dynamics.get("torso_quaternion_overwrite_count"),
                    "torso_orientation_correction_magnitude_sum": latest_dynamics.get(
                        "torso_orientation_correction_magnitude_sum"
                    ),
                    "torso_orientation_correction_magnitude_max": latest_dynamics.get(
                        "torso_orientation_correction_magnitude_max"
                    ),
                    "qvel_roll_pitch_zeroing_count": latest_dynamics.get("qvel_roll_pitch_zeroing_count"),
                    "qvel_roll_pitch_damping_magnitude_sum": latest_dynamics.get(
                        "qvel_roll_pitch_damping_magnitude_sum"
                    ),
                    "qvel_roll_pitch_damping_magnitude_max": latest_dynamics.get(
                        "qvel_roll_pitch_damping_magnitude_max"
                    ),
                    "contact_duty_factor": latest_dynamics.get("contact_duty_factor"),
                    "sampled_contact_ratio": {
                        "left": sum(left_contacts) / len(left_contacts) if left_contacts else 0.0,
                        "right": sum(right_contacts) / len(right_contacts) if right_contacts else 0.0,
                        "both": sum(l and r for l, r in zip(left_contacts, right_contacts)) / len(left_contacts)
                        if left_contacts
                        else 0.0,
                    },
                    "no_contact_duration_sec": no_contact_samples * args.sample_period_sec,
                    "roll_deg": _stats(rolls),
                    "pitch_deg": _stats(pitches),
                    "body_height_m": _stats(heights),
                    "correction_magnitude_sum": latest_dynamics.get("correction_magnitude_sum"),
                    "correction_magnitude_max": latest_dynamics.get("correction_magnitude_max"),
                    "correction_rate": _stats(correction_rates),
                    "actuator_saturation": latest_dynamics.get("last_actuator_saturation"),
                    "actuator_saturation_window": _stats(actuator_saturations),
                    "fall_reason": latest_dynamics.get("last_fall_reason"),
                    "fall_event_timestamp": first_fall_timestamp,
                    "safety_intervention_count": int(bool(command_result.get("body", {}).get("safety_intervention"))),
                    "safety_event_timestamp": first_safety_timestamp,
                    "command_latency_sec": command_result.get("latency_sec"),
                    "command_status_code": command_result.get("status_code"),
                    "command_error": command_error,
                    "queue_stability": {
                        "before": queue_before,
                        "after": queue_after,
                        "stable": queue_after.get("active_command") is None and queue_after.get("queue_size", 0) == 0,
                    },
                    "telemetry_publication": {
                        "samples": len(samples),
                        "errors": sample_errors,
                        "stable": len(samples) > 0 and sample_errors == 0,
                    },
                    "sampled_position_range": {
                        "x": {"min": _min(xs), "max": _max(xs)},
                        "y": {"min": _min(ys), "max": _max(ys)},
                        "yaw": {"min": _min(yaws), "max": _max(yaws)},
                    },
                }
            )

    return {"case": case, "repeats": repeats, "summary": _summarize_repeats(repeats)}


def _summarize_repeats(repeats: list[dict[str, Any]]) -> dict[str, Any]:
    fields = (
        "forward_displacement",
        "lateral_displacement",
        "yaw_displacement",
        "yaw_unwrapped_displacement",
        "command_latency_sec",
        "no_contact_duration_sec",
    )
    summary: dict[str, Any] = {}
    for field in fields:
        values = [float(item[field]) for item in repeats if item.get(field) is not None]
        summary[field] = {"min": _min(values), "max": _max(values), "avg": _avg(values)}

    summary["queue_stable"] = all(item["queue_stability"]["stable"] for item in repeats)
    summary["telemetry_stable"] = all(item["telemetry_publication"]["stable"] for item in repeats)
    summary["safety_interventions"] = sum(int(item["safety_intervention_count"]) for item in repeats)
    if repeats:
        latest = repeats[-1]
        summary["qpos_xy_integration_count"] = latest.get("qpos_xy_integration_count")
        summary["qvel_xy_forcing_count"] = latest.get("qvel_xy_forcing_count")
        summary["qvel_xy_commanded_magnitude"] = latest.get("qvel_xy_commanded_magnitude")
        summary["qpos_z_forcing_count"] = latest.get("qpos_z_forcing_count")
        summary["qpos_z_correction_magnitude_sum"] = latest.get("qpos_z_correction_magnitude_sum")
        summary["qpos_z_correction_magnitude_max"] = latest.get("qpos_z_correction_magnitude_max")
        summary["torso_quaternion_overwrite_count"] = latest.get("torso_quaternion_overwrite_count")
        summary["torso_orientation_correction_magnitude_sum"] = latest.get(
            "torso_orientation_correction_magnitude_sum"
        )
        summary["torso_orientation_correction_magnitude_max"] = latest.get(
            "torso_orientation_correction_magnitude_max"
        )
        summary["qvel_roll_pitch_zeroing_count"] = latest.get("qvel_roll_pitch_zeroing_count")
        summary["qvel_roll_pitch_damping_magnitude_sum"] = latest.get("qvel_roll_pitch_damping_magnitude_sum")
        summary["qvel_roll_pitch_damping_magnitude_max"] = latest.get("qvel_roll_pitch_damping_magnitude_max")
        summary["contact_duty_factor"] = latest.get("contact_duty_factor")
        summary["actuator_saturation"] = latest.get("actuator_saturation")
        summary["actuator_saturation_window"] = latest.get("actuator_saturation_window")
        summary["roll_deg"] = latest.get("roll_deg")
        summary["pitch_deg"] = latest.get("pitch_deg")
        summary["body_height_m"] = latest.get("body_height_m")
        summary["correction_rate"] = latest.get("correction_rate")
        summary["fall_reason"] = latest.get("fall_reason")
        summary["fall_event_count"] = sum(1 for item in repeats if item.get("fall_event_timestamp") is not None)
        summary["movement_detected"] = any(abs(float(item["forward_displacement"])) > 1e-4 for item in repeats)
    return summary


def _run_parent(args: argparse.Namespace) -> dict[str, Any]:
    results = []
    if args.matrix == "phase2g":
        matrix = PHASE2G_MATRIX
    elif args.matrix == "phase2f":
        matrix = PHASE2F_MATRIX
    elif args.matrix == "phase2e":
        matrix = PHASE2E_MATRIX
    else:
        matrix = PHASE2D_MATRIX
    for case in matrix:
        env = os.environ.copy()
        env["DUCK_SIM_MODE"] = "real"
        env["DUCK_HEADLESS"] = "true"
        env["DUCK_DYNAMICS_MODE"] = case.dynamics_mode
        env["PYTHONPATH"] = str(ROOT)
        if case.qvel_scale is not None:
            env["DUCK_HYBRID_QVEL_XY_SCALE"] = str(case.qvel_scale)
        else:
            env.pop("DUCK_HYBRID_QVEL_XY_SCALE", None)
        if case.z_force_scale is not None:
            env["DUCK_HYBRID_Z_FORCE_SCALE"] = str(case.z_force_scale)
        else:
            env.pop("DUCK_HYBRID_Z_FORCE_SCALE", None)
        if case.rp_qvel_zero_scale is not None:
            env["DUCK_HYBRID_RP_QVEL_ZERO_SCALE"] = str(case.rp_qvel_zero_scale)
        else:
            env.pop("DUCK_HYBRID_RP_QVEL_ZERO_SCALE", None)
        if case.torso_orientation_scale is not None:
            env["DUCK_HYBRID_TORSO_ORIENTATION_SCALE"] = str(case.torso_orientation_scale)
        else:
            env.pop("DUCK_HYBRID_TORSO_ORIENTATION_SCALE", None)

        cmd = [
            sys.executable,
            str(Path(__file__).resolve()),
            "--child",
            "--case-name",
            case.name,
            "--repeats",
            str(args.repeats),
            "--duration-sec",
            str(args.duration_sec),
            "--stable-wait-sec",
            str(args.stable_wait_sec),
            "--sample-period-sec",
            str(args.sample_period_sec),
            "--speed",
            str(args.speed),
        ]
        completed = subprocess.run(cmd, cwd=ROOT, env=env, text=True, capture_output=True, check=False)
        if completed.returncode != 0:
            raise RuntimeError(
                f"diagnostic case {case.name} failed with code {completed.returncode}\n"
                f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
            )
        lines = [line for line in completed.stdout.splitlines() if line.strip()]
        results.append(json.loads(lines[-1]))

    payload = {
        "matrix": [case.__dict__ for case in matrix],
        "matrix_name": args.matrix,
        "profile": {
            "repeats": args.repeats,
            "duration_sec": args.duration_sec,
            "stable_wait_sec": args.stable_wait_sec,
            "sample_period_sec": args.sample_period_sec,
            "speed": args.speed,
        },
        "results": results,
    }

    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 2D moving-window dynamics diagnostics.")
    parser.add_argument("--child", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--case-name", default="manual")
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--duration-sec", type=float, default=2.0)
    parser.add_argument("--stable-wait-sec", type=float, default=0.25)
    parser.add_argument("--sample-period-sec", type=float, default=0.1)
    parser.add_argument("--speed", type=float, default=0.25)
    parser.add_argument("--matrix", choices=("phase2d", "phase2e", "phase2f", "phase2g"), default="phase2d")
    parser.add_argument("--output", default="docs/phase2d_moving_window_diagnostics_results.json")
    args = parser.parse_args()

    if args.child:
        print(json.dumps(_run_child(args), sort_keys=True))
    else:
        print(json.dumps(_run_parent(args), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
