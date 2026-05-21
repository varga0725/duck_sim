# Phase 1 Final Verification Addendum

## Changed Files Detail

## Dirty Vision File Classification

### `duck_agent_sim/vision/camera.py`
- Observed diff: copies MuJoCo `MjData` under simulator lock and renders outside the simulator lock.
- Classification: should be moved to a separate vision/performance commit.
- Phase 1 requirement status: not required for command queue, AppContext lifecycle, double-buffer state publication, or command ingress hardening.
- Backward compatibility risk: medium. It changes real-mode camera rendering synchronization behavior and should be validated with MuJoCo installed.

### `duck_agent_sim/vision/tracker.py`
- Observed diff: adds `max_disappeared` tracking retention and delayed deregistration for vanished tracks.
- Classification: should be moved to a separate perception/tracking behavior commit.
- Phase 1 requirement status: not required for runtime command hardening.
- Backward compatibility risk: medium. It changes tracking ID lifetime semantics and affects vision/follower behavior.

### `duck_agent_sim/simulator/queue_manager.py`
- Purpose: Replaces ad hoc command execution with a bounded single-worker control-plane queue.
- Key changes: `CommandRequest`, `QueueManager.submit_command()`, `cancel_active_command()`, `shutdown()`, queue telemetry, priority stop/reset draining, executor fallback refusal.
- Plane: Control plane.
- Compatibility risk: Simulators without `execute_command_async()` now fail fast instead of silently using a thread executor.

### `duck_agent_sim/simulator/timing.py`
- Purpose: Introduces centralized fixed-step timing authority.
- Key changes: `SimulationClock`, `ClockTelemetry`, drift and overrun tracking.
- Plane: Data plane / timing.
- Compatibility risk: Low. It changes loop pacing internals but not public API schemas.

### `duck_agent_sim/simulator/control_plane.py`
- Purpose: Defines the approved control-plane intent publication model.
- Key changes: `DesiredMotionState`, `ZERO_CONTROL`, `command_duration()`.
- Plane: Control plane boundary.
- Compatibility risk: Low. New internal module only.

### `duck_agent_sim/simulator/double_buffered_state.py`
- Purpose: Provides copy-isolated state snapshot publication for telemetry/API readers.
- Key changes: `DoubleBufferedState.get_read_state()`, `update_write_state()`, `swap()`.
- Plane: State plane.
- Compatibility risk: Low. Callers still receive Pydantic-compatible `RobotState`; object identity is no longer shared.

### `duck_agent_sim/simulator/duck_sim.py`
- Purpose: Separates command intent from simulator-owned stepping/timing while preserving legacy simulator APIs.
- Key changes: Mock simulator background timing loop, `set_desired_control()`, `execute_command_async()`, real simulator `SimulationClock` pacing, double-buffer publication in mock/real state updates.
- Plane: Data plane, state plane, compatibility.
- Compatibility risk: Medium. `apply_command()` remains available, but production queue paths now wait around intent publication rather than directly stepping in the caller.

### `duck_agent_sim/bridge/api.py`
- Purpose: Routes REST command ingress and safety recovery through the queue when AppContext owns the active simulator.
- Key changes: async `/command`, `/stop`, `/reset`, `/scenario/walk-square`, follower start preflight; `_submit_robot_command()`, `_submit_stop()`, `_submit_reset()`.
- Plane: API / control plane.
- Compatibility risk: Low to medium. Legacy monkeypatched tests retain fallback behavior when AppContext is intentionally bypassed.

### `duck_agent_sim/bridge/websocket.py`
- Purpose: Routes WebSocket command ingestion through `QueueManager`.
- Key changes: command payload handling now calls `queue_manager.submit_command()`.
- Plane: API / control plane.
- Compatibility risk: Low. Existing acknowledgement shape is preserved.

### `duck_agent_sim/vision/follower.py`
- Purpose: Prevent follower from stepping or directly stopping simulator physics.
- Key changes: follower publishes `set_desired_control()` for tracking/search commands and zero-control stop intent for shutdown/deadman.
- Plane: Control plane.
- Compatibility risk: Medium for unmanaged simulators; follower now requires the active simulator compatibility object to expose `set_desired_control()`.

### `duck_agent_sim/services.py`
- Purpose: Adds explicit lifecycle-managed runtime ownership while preserving `active_simulator`.
- Key changes: `SimulatorProxy`, `ServiceRegistry`, `AppContext`, simulator and queue startup/shutdown.
- Plane: Compatibility / lifecycle.
- Compatibility risk: Medium. Lazy proxy fallback remains for legacy imports, but production startup should use AppContext.

### Other Modified Files
- `duck_agent_sim/main.py`: wires AppContext startup/shutdown through FastAPI lifespan.
- `duck_agent_sim/simulator/instance.py`: exports the compatibility proxy.
- `duck_agent_sim/vision/camera.py`, `duck_agent_sim/vision/tracker.py`: existing dirty changes remain in the worktree; no additional production command ingress was introduced in this verification pass.
- `duck_agent_sim/agent/gemini_live_client.py`, `duck_agent_sim/agent/voice_control.py`: Gemini/voice path remains HTTP/API based through `DirectController`/`HermesRobotClient`; no direct simulator mutation was added.
- Tests updated/added: `tests/test_hardening.py`, `tests/test_api.py`, `tests/test_follower.py`, `tests/test_safety_preflight_enforcement.py`, `tests/test_sensors_state.py`, `tests/test_vision.py`, `tests/test_voice_control.py`.

## Command Bypass Audit

Production command ingress:
- REST `/command`: routes through `_submit_robot_command()` -> `QueueManager.submit_command()` when AppContext owns active simulator.
- REST `/stop`: routes through `_submit_stop()` -> `QueueManager.submit_command(RobotCommand(command="stop"))`.
- REST `/reset`: routes through `_submit_reset()` -> `QueueManager.submit_command(RobotCommand(command="reset"))`.
- REST `/scenario/walk-square`: each step routes through `_submit_robot_command()`; safety recovery routes through queued stop/reset.
- Safety recovery: uses `_submit_stop()` then `_submit_reset()`, queued under AppContext ownership.
- WebSocket command ingestion: routes through `QueueManager.submit_command()`.
- Gemini/tool path: `GeminiLiveController._run_tool()` -> `DirectController` -> `HermesRobotClient` -> REST `/command`, `/reset`, or follower endpoints; therefore production motion commands enter the REST queue path.
- Voice path: `DuckAgent` direct route uses the same `DirectController`/REST client path.
- Follower control path: publishes desired control via `active_simulator.set_desired_control()`; it no longer calls `active_simulator.step()` or direct simulator stop.

Result:
- AppContext-owned production runtime command ingress routes through `QueueManager` or publishes intent through `set_desired_control()`.
- No production path directly calls simulator `step()` for command execution.
- No `QueueManager` path uses `run_in_executor` for simulator command execution.

Compatibility exceptions:
- `duck_agent_sim/bridge/api.py` keeps fallback calls to `active_simulator.apply_command()`, `.stop()`, and `.reset()` only when the API module has been monkeypatched or AppContext does not own the active simulator. This preserves legacy tests and unmanaged local usage; it is not the AppContext production path.
- `duck_agent_sim/agent/scripted_agent.py` still calls a passed simulator's `apply_command()` directly. It is used by local scenario scripts, not the FastAPI/WebSocket/Gemini production ingress path.

## Verification Commands

Passed:
- `pytest -q tests/test_hardening.py tests/test_api.py tests/test_safety_preflight_enforcement.py tests/test_sensors_state.py tests/test_follower.py`
  - Result: 32 passed.

Static audit:
- `rg -n "active_simulator\\.(stop|reset|apply_command|step)|\\.apply_command\\(|run_in_executor|set_desired_control|submit_command" duck_agent_sim`
  - Production ingress routes are queued or intent-publishing.
  - Remaining direct `apply_command()` use is legacy scripted-agent utility or compatibility fallback.
  - Remaining `run_in_executor` calls are audio/playback/transcription related, not simulator command execution.

## Phase 1 Status

Phase 1 is closeable for the AppContext production runtime after this verification pass, subject to the already documented environment-dependent validations:
- Gemini async tests need an active async pytest plugin.
- Real MuJoCo projection/physics smoke needs `mujoco` installed.
