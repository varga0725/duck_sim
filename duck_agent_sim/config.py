import os
from typing import Literal
from dotenv import load_dotenv

# Load .env file if present
load_dotenv()

# Simulation mode: "mock", "real", or "webcam"
DUCK_SIM_MODE = os.getenv("DUCK_SIM_MODE", "mock").lower()
if DUCK_SIM_MODE not in ("mock", "real", "webcam"):
    DUCK_SIM_MODE = "mock"

DynamicsMode = Literal["legacy", "hybrid", "dynamic"]


def parse_duck_dynamics_mode(value: str | None) -> DynamicsMode:
    mode = (value or "legacy").strip().lower()
    if mode in ("legacy", "hybrid", "dynamic"):
        return mode
    return "legacy"


def parse_hybrid_qvel_xy_scale(value: str | None) -> float:
    try:
        scale = float(value) if value is not None else 1.0
    except (TypeError, ValueError):
        return 1.0
    if scale in (0.0, 0.5, 1.0):
        return scale
    return 1.0


def parse_hybrid_z_force_scale(value: str | None) -> float:
    try:
        scale = float(value) if value is not None else 1.0
    except (TypeError, ValueError):
        return 1.0
    if scale in (0.0, 0.5, 1.0):
        return scale
    return 1.0


def parse_hybrid_rp_qvel_zero_scale(value: str | None) -> float:
    try:
        scale = float(value) if value is not None else 1.0
    except (TypeError, ValueError):
        return 1.0
    if scale in (0.0, 0.5, 1.0):
        return scale
    return 1.0


def parse_hybrid_torso_orientation_scale(value: str | None) -> float:
    try:
        scale = float(value) if value is not None else 1.0
    except (TypeError, ValueError):
        return 1.0
    if scale in (0.0, 0.5, 1.0):
        return scale
    return 1.0


# Dynamics migration mode. Phase 2A is instrumentation/scaffold only.
DUCK_DYNAMICS_MODE: DynamicsMode = parse_duck_dynamics_mode(os.getenv("DUCK_DYNAMICS_MODE"))
DUCK_HYBRID_QVEL_XY_SCALE = parse_hybrid_qvel_xy_scale(os.getenv("DUCK_HYBRID_QVEL_XY_SCALE"))
DUCK_HYBRID_Z_FORCE_SCALE = parse_hybrid_z_force_scale(os.getenv("DUCK_HYBRID_Z_FORCE_SCALE"))
DUCK_HYBRID_RP_QVEL_ZERO_SCALE = parse_hybrid_rp_qvel_zero_scale(os.getenv("DUCK_HYBRID_RP_QVEL_ZERO_SCALE"))
DUCK_HYBRID_TORSO_ORIENTATION_SCALE = parse_hybrid_torso_orientation_scale(
    os.getenv("DUCK_HYBRID_TORSO_ORIENTATION_SCALE")
)
DUCK_POLICY_CONTRACT_WARNINGS = os.getenv("DUCK_POLICY_CONTRACT_WARNINGS", "").strip().lower() in (
    "1",
    "true",
    "yes",
    "on",
)

# ONNX model path for real MuJoCo inference
_default_model = os.path.join(os.path.dirname(__file__), "models", "BEST_WALK_ONNX_2.onnx")
DUCK_ONNX_MODEL_PATH = os.getenv("DUCK_ONNX_MODEL_PATH", "")
if not DUCK_ONNX_MODEL_PATH and os.path.exists(_default_model):
    DUCK_ONNX_MODEL_PATH = _default_model

# Server host and port
BRIDGE_HOST = os.getenv("BRIDGE_HOST", "127.0.0.1")
BRIDGE_PORT = int(os.getenv("BRIDGE_PORT", "8765"))

# Simulation timestep (dt) for step calculations
SIM_DT = float(os.getenv("SIM_DT", "0.05"))
