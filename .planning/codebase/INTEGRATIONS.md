# External Integrations

**Analysis Date:** 2026-05-28

## APIs & External Services

**Google Gemini Multimodal Live API:**
- What it is used for: Bidirectional real-time audio/video streaming and voice command interpreting.
- Auth: API key configured in `GEMINI_API_KEY` or `GOOGLE_API_KEY` environment variables.
- Integration Method: WebSocket connection to the Gemini Live endpoint, implemented in `duck_agent_sim/agent/gemini_live_client.py`.

**Hermes Developer Agent:**
- What it is used for: Remote agent execution and supervision.
- Auth: HTTP Endpoint configuration via `HERMES_API_URL` environment variable.
- Integration Method: REST calls implemented in `duck_agent_sim/agent/hermes_client.py`.

## Data Storage

**Shared Memory Telemetry IPC:**
- What it is used for: High-performance, low-latency inter-process telemetry and camera frames transfer between the simulator process and perception/AI processes.
- Implementation: Python `multiprocessing.shared_memory` using block name `'duck_robot_sensors'`.
- Client: SharedTelemetryBus located in `duck_agent_sim/runtime/shared_telemetry_bus.py`.

## Authentication & Identity
- No user login / signup features are implemented in this MVP API bridge.

## Monitoring & Observability
- Python Logging: Output to stdout/stderr using standard Python `logging` library.
- Telemetry logging: Log outputs like `bridge_test.log` and simulated coordinate logs.

## CI/CD & Deployment
- Not configured in public services, local execution is the primary pattern.

## Environment Configuration

**Development:**
- Required env vars: `DUCK_SIM_MODE` (mock/real), `GEMINI_API_KEY`.
- Secrets location: `.env` file (gitignored).
- Mock/stub services: Detachable kinematics simulator (`MockDuckSimulator`) when running without MuJoCo or ONNX dependencies.

## Webhooks & Callbacks
- None currently configured.

---

*Integration audit: 2026-05-28*
*Update when adding/removing external services*
