# Phase 1 Environment Validation Pending

Phase 1 implementation is closed for the AppContext-owned production runtime, but full environment validation remains yellow until the checks below run in an environment with the required dependencies.

## Gemini Async Validation

Missing / required dependency:
- `pytest-asyncio`

Command:

```bash
pytest -q tests/test_gemini_live_client.py
```

Expected pass criteria:
- All Gemini Live controller unit tests pass without unsupported async test warnings.
- Tool execution tests validate `move_robot`, `follow_target`, and `route_to_hermes` mapping behavior.
- Audio interruption/mic-gating tests pass deterministically without opening a live Gemini session.

Credentials:
- Live API credentials should not be required for the existing unit tests.
- Tests should continue to mock `GEMINI_API_KEY`, WebSocket, DirectController, HermesDelegator, and audio streams.

Unit vs integration split:
- Unit: setup payload construction, API key resolution, local tool mapping, receive-loop interruption handling, mic-gating behavior.
- Integration: any real Gemini WebSocket session, real microphone/speaker devices, live camera streaming, or live bridge calls. These should be marked separately and skipped by default in CI unless credentials/devices are provided.

## MuJoCo Validation

Missing dependency:
- `mujoco`

Targeted projection test:

```bash
pytest -q tests/test_vision.py::test_detect_real_projected_capsule_cylinder
```

Required headless real simulator smoke:

```bash
DUCK_SIM_MODE=real DUCK_HEADLESS=true pytest -q tests/test_api.py::test_api_health tests/test_sensors_state.py
```

Expected pass criteria:
- Real projected capsule/cylinder detection test passes with MuJoCo installed.
- Headless real simulator starts without a viewer window.
- `/health` responds successfully in real mode.
- `/sensors/state` returns explicit availability/null markers or real sensor values without crashing.
- Real simulator can publish state through the double buffer while the physics loop remains continuously clocked.

Phase 2 gate:
- Phase 2 dynamics work must not begin before MuJoCo/headless real simulator validation is either passing or formally tracked in an issue with owner, environment, and acceptance criteria.
- No locomotion/dynamics changes are allowed as part of resolving these Phase 1 validation items.
