# Duck Agent Simulation MVP

An elegant, high-level API Bridge that connects AI Agents (e.g., OpenClaw, Hermes, or custom LLM supervisors) to a simulated **Open Duck Mini v2** robot. 

Built using FastAPI, WebSockets, and Pydantic, the project coordinates high-level movement commands, monitors body safety constraints, and streams real-time physical telemetry. It supports both a deterministic kinematic **Mock Simulator** (requiring no physics dependencies) and a scaffolding for wrapping the **Real MuJoCo physics controller** from the `Open_Duck_Playground` library.

---

## 1. What This Project Is & Is Not

### What This Project Is
- **An AI Agent Control Interface**: Allows LLM agents to command the duck robot using structured business/movement language (e.g., `walk_forward`, `turn_left`, `stop`, `reset`) rather than micro-controlling joint-level servo angles.
- **A Robotics API Bridge**: Exposes REST and WebSocket endpoints for low-latency command ingestion and telemetry broadcasting.
- **A Safe Kinematic Playground**: Embodies safety limits (tilt bounds, fall limits, height collapse) and automatically halts target velocities when stability thresholds are breached.
- **A Sim-to-Real Gateway**: Serves as a direct proxy interface that can be plugged into a MuJoCo training sandbox or a physical BDX droid replica down the road.

### What This Project Is NOT
- **A direct motor controller**: It does not hallunicated 50Hz joint angles or directly output raw pulse-width modulation (PWM) signals to physical hardware. Low-level gait planning and stabilization is deferred to trained ONNX policies.
- **A physical robot wrapper**: Designed strictly for simulation and virtualization. No active microcontrollers, serial connections, or GPIO pins are targeted in this code.

---

## 2. System Architecture

```text
┌──────────────────────────────────────────┐
│        AI Agent / OpenClaw / Jarvis      │
│  (Interprets state, plans high-level path)│
└────────────────────┬─────────────────────┘
                     │
                     │ JSON command (REST or WebSocket)
                     ↓
┌──────────────────────────────────────────┐
│          Duck Agent Bridge API           │
│           (FastAPI + WebSockets)         │
└────────────────────┬─────────────────────┘
                     │
                     │ validates & maps command
                     ↓
┌──────────────────────────────────────────┐
│             Command Mapper               │
│     Translates commands to linear/yaw    │
└────────────────────┬─────────────────────┘
                     │
                     │ ControlIntent (linear_x, yaw)
                     ↓
┌──────────────────────────────────────────┐
│        Duck Simulator Coordinator        │
│    (Coordinates Mock or Real MuJoCo sim) │
└──────────┬────────────────────┬──────────┘
           │                    │
      [Mock Mode]          [Real Mode]
           │                    │
           ↓                    ↓
┌────────────────────┐ ┌────────────────────┐
│ Mock Kinematics    │ │ MuJoCo Physics Sim │
│ Waddling Motion    │ │ Open Duck Mini XML │
│ Alternate Contact  │ │ ONNX Gait Policy   │
└──────────┬─────────┘ └────────┬───────────┘
           │                    │
           └─────────┬──────────┘
                     │
                     │ RobotState (pos, orient, contact)
                     ↓
┌──────────────────────────────────────────┐
│           State Observer & Safety        │
│   (Checks roll, pitch, height bounds)    │
└────────────────────┬─────────────────────┘
                     │
                     │ enforces auto-stop if fallen
                     ↓
┌──────────────────────────────────────────┐
│           Telemetry Feed (10Hz)          │
│       WebSocket Stream state feedback    │
└──────────────────────────────────────────┘
```

---

## 3. Installation & Setup

Ensure you have Python 3.10+ installed.

### Automated Workspace Setup
The project comes with a helper shell script that automatically clones the `apirrone/Open_Duck_Playground` repository and prepares the local Python environment:

```bash
bash scripts/setup_open_duck.sh
```

### Manual Installation
If you prefer to configure the environment manually:

```bash
# 1. Clone the submodule dependency
mkdir -p external
git clone https://github.com/apirrone/Open_Duck_Playground external/Open_Duck_Playground

# 2. Set up a local Python virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 3. Install package with dev dependencies
pip install -e ".[dev]"
```

---

## 4. Running the Simulation

### A. Mock Simulation Mode (Default)
In mock mode, the simulator executes a deterministic kinematic waddle-simulation that moves coordinates, alters roll/pitch swaying, and alternates foot contacts to emulate realistic walking.

```bash
export DUCK_SIM_MODE=mock
bash scripts/run_bridge.sh
```

### B. Real MuJoCo Simulation Mode
To run with real MuJoCo physics, ensure you have MuJoCo installed and configured an ONNX locomotion policy:

```bash
export DUCK_SIM_MODE=real
export DUCK_ONNX_MODEL_PATH=/path/to/policy.onnx
bash scripts/run_bridge.sh
```

---

## 5. API Usage Examples

Once the server is running on `http://localhost:8765`, you can communicate with it using standard tools:

### Health Check
```bash
curl http://localhost:8765/health
```
Response:
```json
{
  "status": "ok",
  "sim_mode": "mock",
  "robot": "open_duck_mini_v2"
}
```

### Get Telemetry / State
```bash
curl http://localhost:8765/state
```
Response:
```json
{
  "robot": "open_duck_mini_v2",
  "status": "idle",
  "sim_time": 12.45,
  "position": [0.72, 0.1, 0.41],
  "orientation": {
    "roll_deg": 2.4,
    "pitch_deg": 6.8,
    "yaw_deg": 41.0
  },
  "feet_contact": {
    "left": true,
    "right": false
  },
  "fallen": false,
  "last_command": "walk_forward"
}
```

### Issue High-Level Command
```bash
curl -X POST http://localhost:8765/command \
  -H "Content-Type: application/json" \
  -d '{
    "command": "walk_forward",
    "speed": 0.25,
    "turn": 0.0,
    "duration_sec": 2.0,
    "safety": {
      "stop_on_fall": true,
      "max_pitch_deg": 35,
      "max_roll_deg": 35
    }
  }'
```

### Stop Robot Immediately
```bash
curl -X POST http://localhost:8765/stop
```

### Reset Robot Coordinates
```bash
curl -X POST http://localhost:8765/reset
```

### Execute walk-square Scenario
```bash
curl -X POST http://localhost:8765/scenario/walk-square
```

---

## 6. Real-Time WebSockets Telemetry

The bridge exposes a WebSocket stream on `ws://localhost:8765/ws`. 
Connecting to this endpoint yields a **10Hz continuous state stream** of the robot telemetry:

```javascript
const ws = new WebSocket("ws://localhost:8765/ws");

ws.onmessage = (event) => {
  const robotState = JSON.parse(event.data);
  console.log("Telemetry Update:", robotState.position, robotState.fallen);
};
```

You can also send real-time commands asynchronously over the same socket by piping JSON commands:
```javascript
ws.send(JSON.stringify({
  "command": "turn_left",
  "speed": 0.3,
  "duration_sec": 1.5
}));
```

---

## 7. Local Scenario & Agent Testing

To verify control behaviors without setting up curl or a web-app, you can run localized deterministic scripted agent routines:

```bash
# Verify basic walking state progressions
uv run python -m duck_agent_sim.scenarios.basic_walk

# Verify square path geometry mapping
uv run python -m duck_agent_sim.scenarios.walk_square

# Verify safety trips (injecting severe roll and testing auto-stops/resets)
uv run python -m duck_agent_sim.scenarios.recover_test
```

Alternatively, test scenarios using the API bridge directly:
```bash
# Make sure run_bridge.sh is running in another window, then run:
bash scripts/run_walk_square.sh
```

---

## 8. Connecting with AI Agents (OpenClaw / Hermes / custom LLM)

First, feed the system instructions located in `duck_agent_sim/agent/openclaw_adapter.py` (constant `SYSTEM_INSTRUCTION`):

> "You are the Duck Robot Control Agent. You control a virtual Open Duck Mini v2 robot in MuJoCo simulation. You may only issue high-level commands through the Duck Agent Bridge API. You must never output raw joint angles or motor commands. Always inspect robot state before issuing a new command. If fallen or unstable, stop and reset."

### Context and Command Builder
The adapter module provides pre-defined functions to shape model contexts and format allowable tool structures:

```python
from duck_agent_sim.agent.openclaw_adapter import build_agent_context, build_allowed_commands

# 1. Transform raw state telemetry into LLM-readable prompt data
prompt_context = build_agent_context(current_state)

# 2. Feed tools declaration schema to the LLM agent
tools = build_allowed_commands()
```

---

## 9. Real MuJoCo Integration

In `RealDuckSimulator` within [duck_sim.py](file:///Users/vargaferenc/Desktop/duck_sim/duck_agent_sim/simulator/duck_sim.py), the simulator is fully integrated with the MuJoCo engine.

The physics-based walks are already active when running in real mode. The implementation includes:
1. **Environment Loading**: Automatically loads the terrains XML from the `Open_Duck_Playground` submodule.
2. **Gait Controller**: Uses the PPO policy model via ONNX runtime (set via `DUCK_ONNX_MODEL_PATH`, a default model is provided in `duck_agent_sim/models/BEST_WALK_ONNX_2.onnx`).
3. **Control Loop**: Automatically maps high-level `linear_x` and `yaw` target velocities to the ONNX policy, applying the resulting joint actions at 50Hz within the 500Hz physics stepping loop.
4. **State Mapping**: Accurately extracts Euler roll/pitch/yaw angles and foot contacts from MuJoCo IMU sensors and contact constraints.
