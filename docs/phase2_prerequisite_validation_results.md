# Phase 2 Prerequisite Validation Results

Phase 2 implementation remains blocked until this validation set is reviewed and accepted. No locomotion, dynamics, ONNX policy, or HAL behavior was changed during this pass.

## Environment

- Repository: `/Users/vargaferenc/Desktop/duck_sim`
- Date: 2026-05-21
- Runtime for real/headless simulator checks: `.venv`
- Required real simulator path: `PYTHONPATH=.`
- Real simulator mode: `DUCK_SIM_MODE=real`
- Headless mode: `DUCK_HEADLESS=true`

The `.venv` environment is the accepted runtime for real MuJoCo smoke checks because it contains `mujoco_playground` from the local `external/` playground setup.

## Gemini Async Validation

Command:

```bash
pytest -q tests/test_gemini_live_client.py
```

Result:

```text
10 passed
```

Status: GREEN.

Notes:
- `pytest-asyncio` and `sounddevice` are installed in the validation environment.
- The existing Gemini tests are unit tests using mocked credentials, WebSocket, audio streams, and controller/runtime dependencies.
- Live Gemini API credentials are not required for this test set.

## MuJoCo Targeted Projection Validation

Command:

```bash
pytest -q tests/test_vision.py::test_detect_real_projected_capsule_cylinder
```

Result:

```text
1 passed
```

Status: GREEN.

Notes:
- `mujoco`, `jax`, `ml-collections`, and `mujoco-mjx` are installed.
- This validates the real projected capsule/cylinder vision path with MuJoCo available.

## Headless Real Simulator Pytest Smoke

Command:

```bash
DUCK_SIM_MODE=real DUCK_HEADLESS=true PYTHONPATH=. .venv/bin/pytest -q tests/test_api.py::test_api_health tests/test_api.py::test_api_state tests/test_sensors_state.py
```

Result:

```text
5 passed
```

Status: GREEN.

Validated endpoints:
- `/health`
- `/state`
- `/sensors/state`

## Explicit Endpoint Smoke

Command:

```bash
DUCK_SIM_MODE=real DUCK_HEADLESS=true PYTHONPATH=. .venv/bin/python - <<'PY'
import sys
from fastapi.testclient import TestClient
from duck_agent_sim.main import app

try:
    with TestClient(app) as c:
        checks = [
            ("GET", "/health", None),
            ("GET", "/state", None),
            ("GET", "/sensors/state", None),
            ("POST", "/command", {"command": "walk_forward", "duration_sec": 0.1}),
            ("POST", "/stop", {}),
            ("POST", "/reset", {}),
        ]
        for method, path, payload in checks:
            if method == "GET":
                r = c.get(path)
            else:
                r = c.post(path, json=payload)
            extra = ""
            if path == "/command" and r.status_code == 200:
                extra = f" accepted={r.json().get('accepted')}"
            print(f"{path}: {r.status_code}{extra}")
            r.raise_for_status()
    print("clean AppContext shutdown")
    print("SMOKE_OK")
except BaseException as exc:
    print("SMOKE_FAIL", type(exc).__name__, repr(exc), file=sys.stderr)
    raise
PY
printf 'exit_code=%s\n' $?
```

Final result:

```text
/health: 200
/state: 200
/sensors/state: 200
/command: 200 accepted=True
/stop: 200
/reset: 200
clean AppContext shutdown
SMOKE_OK
exit_code=0
```

Status: GREEN.

Resolution:
- The prior smoke caveat was an abnormal interpreter exit after successful AppContext shutdown.
- Root cause was native MuJoCo renderer lifecycle cleanup: `CameraDevice.close()` released webcam resources but did not close the MuJoCo renderer.
- Fix: `CameraDevice.close()` now closes `_renderer` and clears it before releasing webcam resources.

## Final Status

```text
Gemini async validation: GREEN
MuJoCo targeted projection validation: GREEN
Headless real simulator pytest smoke: GREEN
Explicit endpoint smoke: GREEN
Locomotion/dynamics/ONNX/HAL changes: NONE
Phase 2 implementation: still blocked pending explicit approval
```
