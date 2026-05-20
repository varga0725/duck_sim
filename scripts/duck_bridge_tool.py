#!/usr/bin/env python3
"""Safe high-level CLI for the Duck Agent Bridge API.

This helper is intended for AI-agent use. It deliberately exposes only the
bridge's high-level REST endpoints and refuses raw joint/motor controls.

Examples:
  python scripts/duck_bridge_tool.py health
  python scripts/duck_bridge_tool.py state
  python scripts/duck_bridge_tool.py command walk_forward --speed 0.25 --duration 1.0
  python scripts/duck_bridge_tool.py stop
  python scripts/duck_bridge_tool.py reset
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from typing import Any, Dict, Optional

DEFAULT_BASE_URL = "http://127.0.0.1:8765"
ALLOWED_COMMANDS = {
    "walk_forward",
    "walk_backward",
    "turn_left",
    "turn_right",
    "stop",
    "reset",
    "look_around",
}
MOTION_COMMANDS = ALLOWED_COMMANDS - {"stop", "reset"}
FORBIDDEN_HINTS = (
    "joint",
    "joints",
    "servo",
    "motor",
    "motors",
    "pwm",
    "angle",
    "angles",
    "ctrl",
    "qpos",
    "qvel",
)


class BridgeError(RuntimeError):
    pass


def _json_dumps(data: Any) -> str:
    return json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False)


def request_json(base_url: str, method: str, path: str, payload: Optional[Dict[str, Any]] = None, timeout: float = 5.0) -> Dict[str, Any]:
    url = base_url.rstrip("/") + path
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=body, method=method)
    req.add_header("Accept", "application/json")
    if payload is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            if not raw:
                return {}
            return json.loads(raw)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise BridgeError(f"HTTP {exc.code} from {url}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise BridgeError(f"Cannot connect to Duck Agent Bridge at {url}: {exc.reason}") from exc
    except TimeoutError as exc:
        raise BridgeError(f"Timeout talking to Duck Agent Bridge at {url}") from exc
    except json.JSONDecodeError as exc:
        raise BridgeError(f"Bridge returned non-JSON from {url}: {exc}") from exc


def request_bytes(base_url: str, method: str, path: str, timeout: float = 5.0) -> tuple[bytes, str]:
    url = base_url.rstrip("/") + path
    req = urllib.request.Request(url, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            content_type = resp.headers.get("Content-Type", "application/octet-stream")
            return resp.read(), content_type
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise BridgeError(f"HTTP {exc.code} from {url}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise BridgeError(f"Cannot connect to Duck Agent Bridge at {url}: {exc.reason}") from exc
    except TimeoutError as exc:
        raise BridgeError(f"Timeout talking to Duck Agent Bridge at {url}") from exc


def get_health(base_url: str) -> Dict[str, Any]:
    return request_json(base_url, "GET", "/health")


def get_state(base_url: str) -> Dict[str, Any]:
    return request_json(base_url, "GET", "/state")


def stop(base_url: str) -> Dict[str, Any]:
    return request_json(base_url, "POST", "/stop")


def reset(base_url: str) -> Dict[str, Any]:
    return request_json(base_url, "POST", "/reset")


def is_unstable(state: Dict[str, Any], max_pitch: float, max_roll: float, min_height: float) -> bool:
    orientation = state.get("orientation") or {}
    position = state.get("position") or [0.0, 0.0, 0.0]
    try:
        z = float(position[2])
    except Exception:
        z = 0.0
    roll = abs(float(orientation.get("roll_deg", 0.0)))
    pitch = abs(float(orientation.get("pitch_deg", 0.0)))
    return bool(
        state.get("fallen")
        or state.get("status") == "fallen"
        or roll >= max_roll
        or pitch >= max_pitch
        or z < min_height
    )


def recover_if_unstable(base_url: str, state: Dict[str, Any], max_pitch: float, max_roll: float, min_height: float) -> Optional[Dict[str, Any]]:
    if not is_unstable(state, max_pitch=max_pitch, max_roll=max_roll, min_height=min_height):
        return None
    stop_result = stop(base_url)
    reset_result = reset(base_url)
    return {
        "safety_intervention": "unstable_or_fallen_detected",
        "state_before_recovery": state,
        "stop_result": stop_result,
        "reset_result": reset_result,
        "requested_command_executed": False,
    }


def post_command(
    base_url: str,
    command: str,
    speed: float,
    turn: float,
    duration: float,
    max_pitch: float,
    max_roll: float,
    min_height: float,
) -> Dict[str, Any]:
    # Mandatory state inspection before every high-level command.
    before = get_state(base_url)
    recovery = recover_if_unstable(base_url, before, max_pitch=max_pitch, max_roll=max_roll, min_height=min_height)
    if recovery is not None:
        return recovery

    payload = {
        "command": command,
        "speed": speed,
        "turn": turn,
        "duration_sec": duration,
        "safety": {
            "stop_on_fall": True,
            "max_pitch_deg": max_pitch,
            "max_roll_deg": max_roll,
        },
    }
    result = request_json(base_url, "POST", "/command", payload=payload, timeout=max(5.0, duration + 3.0))

    # Verify after motion and recover immediately if the command destabilized the robot.
    state_after = result.get("state") if isinstance(result, dict) else None
    if isinstance(state_after, dict) and is_unstable(state_after, max_pitch=max_pitch, max_roll=max_roll, min_height=min_height):
        result = {
            "command_result": result,
            "post_command_safety_intervention": recover_if_unstable(
                base_url,
                state_after,
                max_pitch=max_pitch,
                max_roll=max_roll,
                min_height=min_height,
            ),
        }
    return result


def follow_start(base_url: str, config: Dict[str, Any], max_pitch: float, max_roll: float, min_height: float) -> Dict[str, Any]:
    before = get_state(base_url)
    recovery = recover_if_unstable(base_url, before, max_pitch=max_pitch, max_roll=max_roll, min_height=min_height)
    if recovery is not None:
        return recovery
    return request_json(base_url, "POST", "/vision/follow/start", payload=config)


def follow_stop(base_url: str) -> Dict[str, Any]:
    return request_json(base_url, "POST", "/vision/follow/stop")


def follow_status(base_url: str) -> Dict[str, Any]:
    return request_json(base_url, "GET", "/vision/follow/status")


def capture_frame(base_url: str, output_path: str) -> Dict[str, Any]:
    data, content_type = request_bytes(base_url, "GET", "/vision/frame")
    if not data:
        raise BridgeError("Camera frame endpoint returned no bytes")
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, "wb") as fh:
        fh.write(data)
    return {
        "frame_path": os.path.abspath(output_path),
        "bytes": len(data),
        "content_type": content_type,
    }


def sense(base_url: str, frame_path: Optional[str] = None) -> Dict[str, Any]:
    """Collect the embodied sensor snapshot: body state + vision + follower + optional camera frame."""
    result: Dict[str, Any] = {
        "health": get_health(base_url),
        "body_state": get_state(base_url),
        "vision_state": request_json(base_url, "GET", "/vision/state"),
        "detections": request_json(base_url, "GET", "/vision/detections"),
        "follower": follow_status(base_url),
    }
    if frame_path:
        result["camera_frame"] = capture_frame(base_url, frame_path)
    return result


def effective_min_height(base_url: str, configured_min_height: Optional[float]) -> float:
    if configured_min_height is not None:
        return configured_min_height
    try:
        mode = get_health(base_url).get("sim_mode")
    except BridgeError:
        mode = None
    # Real MuJoCo Open Duck Mini v2 has a lower body/world-frame Z than the
    # kinematic mock. Keep a separate threshold so stable real-mode poses are
    # not mistaken for falls.
    if mode == "real":
        return 0.10
    return 0.25


def validate_high_level_command(command: str) -> None:
    lowered = command.lower()
    if lowered not in ALLOWED_COMMANDS:
        raise BridgeError(f"Refusing command {command!r}. Allowed high-level commands: {sorted(ALLOWED_COMMANDS)}")
    if any(hint in lowered for hint in FORBIDDEN_HINTS):
        raise BridgeError("Refusing possible raw joint/motor/servo control. Use only high-level bridge commands.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Safe high-level Duck Agent Bridge API client")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help=f"Bridge base URL (default: {DEFAULT_BASE_URL})")
    parser.add_argument("--max-pitch", type=float, default=35.0, help="Pitch safety threshold in degrees")
    parser.add_argument("--max-roll", type=float, default=35.0, help="Roll safety threshold in degrees")
    parser.add_argument("--min-height", type=float, default=None, help="Minimum safe body height in meters; default is mode-aware (mock/webcam 0.25, real 0.10)")
    sub = parser.add_subparsers(dest="action", required=True)

    sub.add_parser("health", help="GET /health")
    sub.add_parser("state", help="GET /state")
    sub.add_parser("stop", help="POST /stop")
    sub.add_parser("reset", help="POST /reset")

    cmd = sub.add_parser("command", help="Send a safe high-level motion command after state inspection")
    cmd.add_argument("command", choices=sorted(ALLOWED_COMMANDS))
    cmd.add_argument("--speed", type=float, default=0.25)
    cmd.add_argument("--turn", type=float, default=0.0)
    cmd.add_argument("--duration", type=float, default=1.0)

    sub.add_parser("walk-square", help="Run the built-in high-level square-walk scenario after state inspection")

    fs = sub.add_parser("follow-start", help="Start vision-guided follower after state inspection")
    fs.add_argument("--target-label", default=None)
    fs.add_argument("--target-id", type=int, default=None)
    fs.add_argument("--max-speed", type=float, default=None)
    fs.add_argument("--max-yaw", type=float, default=None)

    sub.add_parser("follow-stop", help="Stop vision-guided follower")
    sub.add_parser("follow-status", help="Get follower status")
    sub.add_parser("vision-state", help="Get vision pipeline state")
    sub.add_parser("detections", help="Get current vision detections")
    frame = sub.add_parser("frame", help="Save the current camera frame from GET /vision/frame")
    frame.add_argument("--output", default="/tmp/duck_camera_frame.jpg", help="Output JPEG path")
    sense_parser = sub.add_parser("sense", help="Collect body state, vision telemetry, detections, follower status, and optional frame")
    sense_parser.add_argument("--frame-output", default=None, help="If set, also save a camera JPEG to this path")
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    min_height = effective_min_height(args.base_url, args.min_height)
    try:
        if args.action == "health":
            result = get_health(args.base_url)
        elif args.action == "state":
            result = get_state(args.base_url)
        elif args.action == "stop":
            result = stop(args.base_url)
        elif args.action == "reset":
            result = reset(args.base_url)
        elif args.action == "command":
            validate_high_level_command(args.command)
            result = post_command(
                args.base_url,
                command=args.command,
                speed=args.speed,
                turn=args.turn,
                duration=args.duration,
                max_pitch=args.max_pitch,
                max_roll=args.max_roll,
                min_height=min_height,
            )
        elif args.action == "walk-square":
            before = get_state(args.base_url)
            recovery = recover_if_unstable(args.base_url, before, args.max_pitch, args.max_roll, min_height)
            if recovery is not None:
                result = recovery
            else:
                result = request_json(args.base_url, "POST", "/scenario/walk-square", timeout=30.0)
                # The built-in route has safety tracking; check final state too.
                after = get_state(args.base_url)
                post_recovery = recover_if_unstable(args.base_url, after, args.max_pitch, args.max_roll, min_height)
                if post_recovery is not None:
                    result = {"scenario_result": result, "post_scenario_safety_intervention": post_recovery}
        elif args.action == "follow-start":
            config = {
                key: value
                for key, value in {
                    "target_label": args.target_label,
                    "target_id": args.target_id,
                    "max_speed": args.max_speed,
                    "max_yaw": args.max_yaw,
                }.items()
                if value is not None
            }
            result = follow_start(args.base_url, config, args.max_pitch, args.max_roll, min_height)
        elif args.action == "follow-stop":
            result = follow_stop(args.base_url)
        elif args.action == "follow-status":
            result = follow_status(args.base_url)
        elif args.action == "vision-state":
            result = request_json(args.base_url, "GET", "/vision/state")
        elif args.action == "detections":
            result = request_json(args.base_url, "GET", "/vision/detections")
        elif args.action == "frame":
            result = capture_frame(args.base_url, args.output)
        elif args.action == "sense":
            result = sense(args.base_url, args.frame_output)
        else:
            raise BridgeError(f"Unknown action: {args.action}")
    except BridgeError as exc:
        print(_json_dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 2

    print(_json_dumps({"ok": True, "result": result}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
