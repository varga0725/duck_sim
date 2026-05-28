# Architecture

**Analysis Date:** 2026-05-28

## Pattern Overview

**Overall:** FastAPI API Bridge and Robotics Simulator Interface.

**Key Characteristics:**
- Event-driven WebSocket state broadcasting (10Hz telemetry).
- Stateless HTTP REST API for command ingestion.
- Multi-threaded simulator execution (physics loops separated from web server threads).
- IPC via Shared Memory for high-volume frame/detection transport.
- Adaptive Agent Client Interfaces (Gemini Live client, Hermes client, OpenClaw adapter).

## Layers

**API Bridge Layer:**
- Purpose: Exposes HTTP & WebSocket endpoints to remote AI agents and frontend dashboards.
- Contains: Route handlers, connection managers, websocket lifecycles.
- Files: `duck_agent_sim/bridge/api.py`, `duck_agent_sim/bridge/websocket.py`.
- Depends on: Services layer, schemas.
- Used by: AI Agents, Frontend dashboards.

**Simulator Layer:**
- Purpose: Simulates physical duck kinematics or step-by-step MuJoCo physics.
- Contains: Mock kinematic model, Real MuJoCo simulator, ONNX Gait controller, safety checkers, command translators.
- Files: `duck_agent_sim/simulator/duck_sim.py`, `duck_agent_sim/simulator/command_mapper.py`, `duck_agent_sim/simulator/safety.py`.
- Depends on: Schemas, configs, external MuJoCo/ONNX dependencies.
- Used by: Services layer.

**Perception/Vision Layer:**
- Purpose: Captures camera frames, runs YOLO object detection, tracks targets for the follower controller.
- Contains: Camera devices, YOLO models, centroid trackers, vision loops.
- Files: `duck_agent_sim/vision/camera.py`, `duck_agent_sim/vision/yolo_detector.py`, `duck_agent_sim/vision/tracker.py`, `duck_agent_sim/vision/vision_loop.py`.
- Depends on: Simulator layer, OpenCV, ONNX.
- Used by: Follower controller, telemetry stream.

**Agent & Adaptation Layer:**
- Purpose: Adapts the raw APIs for specific high-level AI architectures.
- Contains: WebSocket Gemini Live adapter, Hermes remote client, OpenClaw adapters.
- Files: `duck_agent_sim/agent/gemini_live_client.py`, `duck_agent_sim/agent/hermes_client.py`, `duck_agent_sim/agent/openclaw_adapter.py`.
- Depends on: API Bridge Layer.

## Data Flow

**Ingesting Movement Commands:**
1. AI Agent sends POST to `/command` (or pipes JSON to `/ws`).
2. API Bridge validates input against Pydantic schema `RobotCommand`.
3. Command is translated via `map_command` into linear velocity (X, Y) and rotational velocity (yaw) `ControlIntent`.
4. Simulator schedules the control intent with duration limits.
5. Simulator steps the physics (mock waddling or MuJoCo stepping) on a background thread.
6. Safety module evaluates torso heights, roll/pitch angles, and battery health at every timestep.
7. If stable, the command completes after duration; if unstable, safety halts the robot (auto-stop) and returns status.

**State Management:**
- Double Buffered State: Simulated robot state is managed via `DoubleBufferedState` to avoid read-write race conditions between the simulator thread and web server thread.
- File-based/Env configuration.

## Key Abstractions

**DuckSimulator:**
- Purpose: Abstract base class representing any simulator implementation.
- Concrete Implementations: `MockDuckSimulator` (kinematic waddler), `RealDuckSimulator` (MuJoCo engine + ONNX locomotion policy).

**SimulationClock:**
- Purpose: High-precision fixed-timestep simulation clock.
- File: `duck_agent_sim/simulator/timing.py`.

**SharedTelemetryBus:**
- Purpose: Shared memory structure for inter-process telemetry and frames.
- File: `duck_agent_sim/runtime/shared_telemetry_bus.py`.

## Entry Points

**Main Application Server:**
- Location: `duck_agent_sim/main.py`
- Triggers: Running `bash scripts/run_bridge.sh` or `uvicorn duck_agent_sim.main:app`.
- Responsibilities: Startup AppContext, lifespan management, register routers.

**Scripted Testing Scenarios:**
- Location: `duck_agent_sim/scenarios/` (e.g., `walk_square.py`).

## Error Handling

**Strategy:** Exception bubbling combined with safety recovery modes.
- API validation errors return Pydantic format exceptions (HTTP 422).
- Physical safety triggers (falls, sensor timeout, brownouts) automatically transition the robot state to `"fallen"` and execute safe `stop()` and `reset()` procedures.

---

*Architecture analysis: 2026-05-28*
*Update when major patterns change*
