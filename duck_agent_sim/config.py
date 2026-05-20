import os
from dotenv import load_dotenv

# Load .env file if present
load_dotenv()

# Simulation mode: "mock", "real", or "webcam"
DUCK_SIM_MODE = os.getenv("DUCK_SIM_MODE", "mock").lower()
if DUCK_SIM_MODE not in ("mock", "real", "webcam"):
    DUCK_SIM_MODE = "mock"

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
