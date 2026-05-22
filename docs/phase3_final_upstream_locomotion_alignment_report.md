# Phase 3 Final - Upstream Locomotion Alignment Closure Report

Phase 3 closes the Open Duck Mini v2 upstream locomotion alignment groundwork. It prepares the repo for a later upstream policy execution step without replacing the runtime policy path, changing observation layout, changing MuJoCo XML, touching actuator models, adding HAL, modifying dynamic mode behavior, or changing `LegacyDynamicsController`.

## 1. Phase 3 Completion Summary

- Phase 3A added policy contract validation for ONNX metadata, observation vectors, MuJoCo actuator mapping, cadence, command ranges, and vendored upstream constants.
- Phase 3B fixed command clamp consistency at the simulator/control boundary and added non-blocking contract warning infrastructure.
- Phase 3C added `DEFAULT_ACTUATOR` vs `home.ctrl` reporting plus a non-runtime upstream policy adapter scaffold.
- Phase 3 Final added adapter shadow-mode comparison, env-gated startup warnings, Gemini/direct command argument handling, public schema stability tests, and this closure report.

## 2. ONNX contract status

- Bundled policy contract remains:
  - input: `obs [1, 101]`, `tensor(float)`
  - output: `continuous_actions [1, 14]`, `tensor(float)`
- Validation lives in `duck_agent_sim/simulator/policy_contract_validator.py`.
- Startup warning validation can check ONNX metadata when `DUCK_POLICY_CONTRACT_WARNINGS=1`.

## 3. Observation contract status

- Observation layout is unchanged.
- Validation checks flat length `101`, dtype `float32`, finite values, and command vector range.
- No code path changes observation construction or ONNX inference semantics.

## 4. Actuator/default alignment status

- `duck_agent_sim/simulator/policy_default_report.py` reports `DEFAULT_ACTUATOR` vs `home.ctrl` deltas.
- It exposes per-actuator deltas by actuator order and max absolute delta.
- This is reporting only; runtime still uses existing policy target behavior.

## 5. Command clamp consistency status

- REST `/command` still clamps via `map_command()`.
- Direct simulator/control boundary now clamps `set_desired_control()` and `step()` controls to `POLICY_COMMAND_LIMITS`.
- This protects follower, scripted/internal producers, Gemini/voice paths, and future direct intent producers without adding raw joint/motor command paths.
- Public REST/WebSocket schema is unchanged.

## 6. Follower clamp fix / finding

- Phase 3A found follower can produce `linear_x = 0.3` while policy limit is `0.15`.
- Phase 3B fixed this at the simulator/control boundary, not inside follower-specific logic.
- Follower may still request higher intent values, but the approved control boundary stores policy-safe clamped targets.

## 7. Startup warning behavior

- Startup policy contract warnings are gated by:

```text
DUCK_POLICY_CONTRACT_WARNINGS=1
```

- When enabled, real simulator startup logs warning-only validation findings for:
  - ONNX contract,
  - MuJoCo actuator contract,
  - cadence,
  - upstream constant comparison.
- Validation failures are non-blocking and do not disable ONNX or stop simulator startup.
- When unset, runtime warning behavior remains off.

## 8. Upstream adapter shadow-mode status

- `duck_agent_sim/simulator/upstream_policy_adapter.py` now supports shadow comparison.
- It compares:
  - fixed observation shape,
  - action output shape,
  - expected motor targets,
  - max motor target delta,
  - `DEFAULT_ACTUATOR` vs `home.ctrl`,
  - actuator order,
  - phase period mismatch,
  - command vector mismatch.
- It does not write `data.ctrl`, step MuJoCo, replace ONNX runtime, modify legacy dynamics, or affect dynamic mode.

## 9. Gemini/voice command arg status

- Gemini `move_robot` tool arguments are now forwarded through `DirectController` into the high-level `HermesRobotClient.send_command()` call.
- Values are validated using the public `RobotCommand` schema before the bridge call.
- This remains high-level command control only; no raw motor or joint command route is introduced.
- Public API schema is unchanged.

## 10. Warning-only items

- `DEFAULT_ACTUATOR` vs `home.ctrl` drift remains warning/report-only.
- Upstream reference comparison remains warning/report-only.
- Adapter shadow-mode mismatches do not change runtime behavior.
- `LegacyDynamicsController` fake base stabilization remains present and unchanged.

## 11. Do not use on real robot

Still not valid for real robot locomotion:

- `LegacyDynamicsController` floating-base qpos/qvel forcing.
- Waddle oscillator fallback as a hardware gait.
- Mock simulator kinematic movement/contact outputs.
- Current simulator bridge as a hardware HAL.
- Any walking result that depends on simulator-only base pose or velocity writes.

## 12. Recommended Phase 4

Phase 4 should be explicitly approved before implementation and should focus on upstream policy execution parity in simulation:

- Run adapter shadow-mode against live real/headless simulator observations.
- Compare local `RealDuckSimulator` policy path against upstream `mujoco_infer.py` semantics over fixed windows.
- Decide whether to derive policy defaults from `home.ctrl` or keep hardcoded defaults with strict validation.
- Only after parity is measured, plan removal or isolation of simulator-only base forcing.
- Do not start PD balance, HAL, torque control, or real hardware work until upstream policy execution parity is demonstrated.

## Verification

Phase 3 final alignment tests:

```text
pytest -q tests/test_policy_contract.py tests/test_onnx.py tests/test_policy_contract_validator.py tests/test_phase3c_policy_default_alignment.py tests/test_follower.py tests/test_phase3_final_alignment.py tests/test_phase3b_command_clamp.py tests/test_direct_controller.py tests/test_gemini_live_client.py
68 passed, 4 skipped
```

Broader safety check:

```text
pytest -q tests/test_hardening.py tests/test_api.py tests/test_safety_preflight_enforcement.py tests/test_sensors_state.py tests/test_follower.py
32 passed
```

Skipped tests are optional MuJoCo/Open Duck dependency checks where `mujoco_playground` is unavailable in the current environment.
