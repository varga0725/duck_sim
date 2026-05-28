# Codebase Structure

**Analysis Date:** 2026-05-28

## Directory Layout

```
duck_sim/
├── docs/                        # System specifications, checklists, and contracts
├── duck_agent_sim/              # Main Python source package
│   ├── agent/                   # LLM/AI Agent adaptors (Gemini Live, Hermes, OpenClaw)
│   ├── bridge/                  # FastAPI REST routes and WebSocket telemetries
│   ├── hardware/                # Stub hardware interfaces
│   ├── models/                  # Trained ONNX locomotion policy files
│   ├── runtime/                 # Application lifecycles and Shared Memory IPC
│   ├── scenarios/               # Local test routines (walk square, recovery)
│   ├── simulator/               # Kinematics, MuJoCo interfaces, safety observers
│   └── vision/                  # Cameras, YOLO object detectors, and centroid trackers
├── external/                    # Submodule folder (clones Open_Duck_Playground)
├── frontend/                    # React + Vite dashboard web application
├── scripts/                     # Shell scripts for setup and execution
└── tests/                       # Test suites covering all layers
```

## Directory Purposes

**docs/**
- Purpose: System-level documentation, safety checklists, sensor camera contracts, and audits.
- Key files: `onnx_rl_policy_contract.md`, `stability_safety_rules.md`, `sensor_frame_camera_contract.md`.

**duck_agent_sim/agent/**
- Purpose: Adapting simulation API to remote intelligent agents.
- Key files: `gemini_live_client.py` (live voice/video streaming client), `hermes_client.py` (Hermes connection).

**duck_agent_sim/bridge/**
- Purpose: FastAPI web endpoints.
- Key files: `api.py` (REST routes for controls/commands), `websocket.py` (10Hz state broadcasting server).

**duck_agent_sim/simulator/**
- Purpose: Coordinates waddle-kinematics and physical simulation.
- Key files: `duck_sim.py` (core simulators), `safety.py` (fall limits and stability checks), `legacy_dynamics.py` (dynamics migration helpers), `spatial_world_model.py` (coordinate trackers).

**duck_agent_sim/vision/**
- Purpose: Real-time image capture and target tracking.
- Key files: `camera.py` (OpenCV webcam/file capture), `yolo_detector.py` (YOLOv8/v11 inference), `tracker.py` (Centroid tracking).

**frontend/**
- Purpose: Interactive React Dashboard UI.
- Subdirectories: `src/components/`, `src/assets/`.

**tests/**
- Purpose: Tests verifying FastAPI routers, schemas, physical constraints, safety trips, and YOLO detections.

## Key File Locations

**Entry Points:**
- `duck_agent_sim/main.py` - FastAPI app initialization and context lifespans.
- `frontend/src/main.tsx` - Frontend UI bootloader.

**Configuration:**
- `duck_agent_sim/config.py` - Environment loader and parser.
- `pyproject.toml` - Dependency lock, linters, and pytest specifications.
- `.env.example` - Template config for API keys.

**Core Logic:**
- `duck_agent_sim/services.py` - Application context lifecycle singleton.
- `duck_agent_sim/schemas.py` - Data models (RobotCommand, RobotState).

## Naming Conventions

**Files:**
- snake_case.py: Python source modules.
- test_*.py: Python test files.
- PascalCase.tsx: React component files.

**Directories:**
- snake_case: All Python package subfolders.
- kebab-case: Miscellaneous folders (e.g., `duck-agent-sim.egg-info`).

## Where to Add New Code

**New REST endpoint:**
- Add schema definition: `duck_agent_sim/schemas.py`
- Add route handler: `duck_agent_sim/bridge/api.py`
- Test cases: `tests/test_api.py`

**New Physical Controller / Gait logic:**
- Logic file: `duck_agent_sim/simulator/`
- Register properties: `duck_agent_sim/config.py`
- Add test: `tests/` matching domain name

---

*Structure analysis: 2026-05-28*
*Update when directory structure changes*
