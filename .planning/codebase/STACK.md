# Technology Stack

**Analysis Date:** 2026-05-28

## Languages

**Primary:**
- Python >=3.10 - All backend application code, simulators, and scripts.

**Secondary:**
- TypeScript ~6.0.2 - Frontend dashboard application.
- JavaScript - Configuration files (e.g., eslint config) and build scripts.

## Runtime

**Environment:**
- Python 3.10+ (Tested on Python 3.13.13)
- Node.js (for frontend Dashboard development/building)

**Package Manager:**
- Python: `uv` (lockfile `uv.lock` present) or `pip`
- Node.js: `npm` (lockfile `package-lock.json` present in `frontend/`)

## Frameworks

**Core:**
- FastAPI >=0.100.0 - High-level API Bridge connecting AI Agents to the simulator.
- Uvicorn >=0.22.0 - ASGI server for the FastAPI application.
- Pydantic >=2.0.0 - Data validation and settings management.
- React ^19.2.6 - Frontend dashboard library.

**Testing:**
- pytest >=7.0.0 - Backend unit and integration testing.

**Build/Dev:**
- setuptools >=61.0.0 - Python build system.
- Vite ^8.0.12 - Frontend bundling and dev server.
- TypeScript compiler - Static type checking for the frontend.
- Ruff >=0.1.0 - Python linting and formatting.

## Key Dependencies

**Critical:**
- onnxruntime >=1.15.0 - Locomotion policy inference for real MuJoCo mode.
- python-dotenv >=1.0.0 - Local environment configuration loading.
- numpy - Numerical operations and observation mapping.
- SpeechRecognition, openai-whisper (optional/missing) - Voice control.

**Infrastructure:**
- MuJoCo - 3D physics engine for real simulation mode.
- SharedMemory - Multiprocessing shared memory communication for high-performance telemetry/camera frames (IPC).

## Configuration

**Environment:**
- `.env` files parsed via `python-dotenv`.
- Key variables: `DUCK_SIM_MODE`, `DUCK_DYNAMICS_MODE`, `DUCK_ONNX_MODEL_PATH`, `GEMINI_API_KEY`, `GOOGLE_API_KEY`, `HERMES_API_URL`, `BRIDGE_HOST`, `BRIDGE_PORT`, `SIM_DT`.

**Build:**
- `pyproject.toml` - Project specifications, metadata, dependencies, ruff/pytest configurations.
- `frontend/vite.config.ts` - Vite configuration for React development.
- `frontend/tsconfig.json` - TypeScript configuration.

## Platform Requirements

**Development:**
- macOS (tested on macOS), Linux, or Windows.
- Python 3.10+ and Node.js.
- MuJoCo (optional but required for real mode).

**Production:**
- Vercel/Firebase App Hosting (for Frontend).
- Containerized or local server deployment for the FastAPI Python backend.

---

*Stack analysis: 2026-05-28*
*Update after major dependency changes*
