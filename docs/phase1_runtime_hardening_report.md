# Phase 1 Runtime Hardening Report

## Architecture Diff

Old runtime:
- REST/WebSocket paths called simulator command execution directly or through executor-backed compatibility paths.
- Mock command execution owned duration loops and called `step()` repeatedly.
- Real MuJoCo physics had its own thread, but command execution still waited with scattered wall-clock sleeps.
- API reads depended on mutable simulator state guarded inconsistently by simulator-local locks.
- Runtime ownership was split between `active_simulator` singleton access and partial `AppContext` scaffolding.

New runtime:
- REST/WebSocket command ingress routes through `QueueManager` for the active AppContext simulator.
- `QueueManager` is bounded, single-worker, telemetry-producing, and refuses executor fallback.
- The queue worker publishes desired motion intent via `execute_command_async()` / `set_desired_control()`; it does not call `step()`.
- Mock mode now has a simulator-owned timing loop using `SimulationClock`; real mode uses `SimulationClock` for 500 Hz pacing.
- Physics/data plane remains responsible for stepping, state publication, and timing cadence.
- `DoubleBufferedState` provides copy-isolated read snapshots and atomic publication by swap.
- `active_simulator` remains as a compatibility proxy while AppContext/ServiceRegistry owns the primary simulator and queue.

Compatibility guarantees:
- Existing REST endpoints, WebSocket `/ws`, follower endpoints, camera endpoints, and safety recovery contracts remain present.
- Legacy monkeypatched simulator tests still work through a compatibility dispatcher when the API module active simulator differs from AppContext ownership.
- `step()` remains available for legacy callers, but Phase 1 queue and follower paths no longer use it for physics advancement.

## Runtime Safety Analysis

Race conditions reduced:
- State readers receive copy-isolated snapshots from the read buffer instead of serializing mutable simulator internals.
- Mock and real simulators publish complete `RobotState` snapshots through the double buffer after state updates.

Command determinism:
- A single queue worker owns command sequencing.
- Stop/reset are priority commands: they cancel active command futures, drain pending work, halt desired motion, then execute stop/reset.
- Queue overflow rejects immediately instead of adding unbounded command pressure.

Executor exhaustion mitigation:
- `QueueManager` no longer calls `run_in_executor` for simulator commands.
- Simulators must expose `execute_command_async`; absence is treated as a runtime configuration error.

Physics isolation:
- Queue execution does not own MuJoCo `mj_step`, dt, or simulation pacing.
- Follower publishes desired control intent and does not call `active_simulator.step()`.
- `SimulationClock` centralizes fixed dt pacing and records drift/overrun telemetry.

Remaining Phase 1 risks:
- Some legacy direct `apply_command()` methods remain for scripts/tests; the production API path uses the queue when AppContext owns the active simulator.
- Phase 2 dynamics issues are intentionally untouched: qpos forcing, torso forcing, kinematic base integration, and fake stabilization remain.
- Phase 3 multi-instance GPU/YOLO singleton cleanup is not addressed in this phase.

## Validation Results

Passed:
- `python -m py_compile duck_agent_sim/simulator/queue_manager.py duck_agent_sim/simulator/timing.py duck_agent_sim/simulator/control_plane.py duck_agent_sim/simulator/duck_sim.py duck_agent_sim/bridge/api.py duck_agent_sim/bridge/websocket.py duck_agent_sim/vision/follower.py duck_agent_sim/services.py`
- `pytest -q tests/test_hardening.py tests/test_api.py tests/test_safety_preflight_enforcement.py tests/test_sensors_state.py tests/test_follower.py`
  - Result: 32 passed in 23.94s.
- `pytest -q tests/test_smart_router.py tests/test_vision.py -k 'not real_projected'`
  - Result: 70 passed, 1 deselected in 1.99s.
- Static check:
  - No `QueueManager` executor fallback for simulator command execution.
  - No `active_simulator.step()` call remains in follower runtime.

Known validation limits:
- `tests/test_gemini_live_client.py` contains async tests marked with `pytest.mark.asyncio`, but this environment does not have the asyncio pytest plugin active; collection reports unsupported async tests.
- `tests/test_vision.py::test_detect_real_projected_capsule_cylinder` requires `mujoco`, which is not installed in this environment.

## Migration Impact

Changed Phase 1 files:
- `duck_agent_sim/simulator/queue_manager.py`
- `duck_agent_sim/simulator/timing.py`
- `duck_agent_sim/simulator/control_plane.py`
- `duck_agent_sim/simulator/duck_sim.py`
- `duck_agent_sim/bridge/api.py`
- `duck_agent_sim/bridge/websocket.py`
- `duck_agent_sim/vision/follower.py`
- `duck_agent_sim/services.py`
- `duck_agent_sim/simulator/double_buffered_state.py`
- `tests/test_hardening.py`
- `tests/test_api.py`

Rollback strategy:
- Revert the Phase 1 queue/timing/control-plane files and restore REST/WebSocket direct command dispatch.
- Keep `DoubleBufferedState` isolated if rollback target still benefits from safe read snapshots.
- If rollback is required due to runtime issues, preserve the compatibility proxy so legacy singleton imports continue to resolve.

Regression risks:
- Command completion now waits around desired intent publication rather than direct stepping; tests or scripts relying on direct synchronous stepping timing may observe slightly different intermediate states.
- Follower control now depends on simulator support for `set_desired_control`.
- Stop/reset priority cancellation can cancel pending long-running commands that previously would have completed.

Phase 2 readiness:
- Phase 2 remains blocked until Gemini async tests run in an environment with the proper plugin and real MuJoCo validation runs with dependencies installed.
- Runtime architecture is ready for Phase 2 only after a headless MuJoCo smoke validates continuous stepping, command intent consumption, and double-buffer publication under real physics.
