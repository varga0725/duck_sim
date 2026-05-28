# Testing Patterns

**Analysis Date:** 2026-05-28

## Test Framework

**Runner:**
- `pytest` (configured via `pyproject.toml`).
- Async support is enabled using plugins `asyncio` and `anyio`.

**Run Commands:**
```bash
pytest                                       # Run all tests
pytest tests/test_api.py                    # Run a single test file
pytest -k "test_safety"                      # Run tests matching a name pattern
```

## Test File Organization

**Location:**
- Located in the root `tests/` directory.
- Experimental tests are segregated in `tests/experimental/` and excluded by default via `norecursedirs` in `pyproject.toml`.

**Naming:**
- Filenames start with `test_` (e.g. `test_safety.py`, `test_api.py`, `test_onnx.py`).

**Structure:**
- Clean division based on system component:
  - `test_api.py`: FastAPI routes, payloads, responses.
  - `test_safety.py`: Stability rules, tilt triggers, fallen states.
  - `test_command_mapper.py`: Translating high-level instructions to linear/yaw forces.
  - `test_vision.py` & `test_vision_ipc.py`: Cameras, YOLO trackers, Shared Memory pipelines.

## Mocking & Mocks

**Patterns:**
- Standard unit testing mocks (`unittest.mock.MagicMock`, `unittest.mock.patch`) are used to isolate dependencies.
- Submodules (like the real MuJoCo viewer or ONNX model loadings) are mock-patched during unit test execution to keep tests fast and runnable on standard CPUs without GPU dependencies.
- Simulators are tested in detachment using `MockDuckSimulator`.

## Common Patterns

**Async Testing:**
- Use `@pytest.mark.asyncio` to test async routes, clients (e.g. websocket endpoints, async command loops).

**Safety Enforcement Verification:**
- Tests like `test_safety.py` actively mock tilt angles (roll/pitch) and heights to ensure the safety observer intervenes when thresholds are breached.

---

*Testing analysis: 2026-05-28*
*Update when test patterns change*
