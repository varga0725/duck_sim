# Phase 2B Hybrid XY Qpos Removal Plan

Phase 2B is a narrow dynamics migration step. The only approved behavior change is disabling direct base `qpos[0]` / `qpos[1]` integration in `hybrid` mode. `legacy` must remain Phase 1/Phase 2A compatible. `dynamic` remains behaviorally unchanged until a later approved phase.

## 1. Exact Behavior Split

```text
legacy:
  - unchanged Phase 1/Phase 2A behavior
  - qpos x/y integration remains active
  - torso stabilization remains active
  - qvel x/y forcing remains active
  - z forcing remains active
  - torso quaternion overwrite remains active
  - roll/pitch qvel zeroing remains active
  - ONNX/waddle behavior unchanged

hybrid:
  - disable direct qpos[0]/qpos[1] integration only
  - keep qvel x/y forcing for now if needed for diagnostics
  - keep z forcing
  - keep torso quaternion overwrite
  - keep roll/pitch qvel zeroing
  - keep ONNX/waddle behavior unchanged
  - keep MuJoCo stepping ownership unchanged
  - weak or missing forward movement is diagnostic output, not failure

dynamic:
  - no behavior change yet
  - still mapped to legacy behavior until a later approved phase
```

Implementation target:
- Extend `LegacyDynamicsController.apply()` with an explicit behavior branch controlled by `mode`.
- For `mode == "hybrid"`, skip only the lines equivalent to:

```python
data.qpos[0] += global_vx * fixed_dt_sec
data.qpos[1] += global_vy * fixed_dt_sec
```

- For `mode == "legacy"` and `mode == "dynamic"` in Phase 2B, preserve the Phase 2A write pattern exactly.

## 2. Diagnostics Comparison

Phase 2B validation must compare `legacy` vs `hybrid` using the same command profile and runtime duration where practical.

Required comparison fields:
- forward displacement
- yaw displacement
- contact duty factor
- slip / no-contact behavior
- correction magnitude
- roll/pitch/body height
- actuator saturation
- fall reason
- qpos x/y integration count

Expected counter result:

```text
legacy qpos_xy_integration_count > 0
hybrid qpos_xy_integration_count == 0
```

Recommended diagnostic interpretation:
- If `hybrid` forward displacement is weak or near zero, classify it as expected diagnostic evidence that legacy locomotion relied on direct base translation.
- Do not compensate by adding a new qpos write, friction bypass, torso hack, or actuator shortcut.
- Record displacement delta and contact duty factor so Phase 2C can decide whether torque/controller tuning is required.

## 3. Acceptance Criteria

Hybrid mode passes Phase 2B if:
- app starts
- no crash or hang
- command queue still works
- telemetry/state publication still works
- public REST/WebSocket schemas remain unchanged
- `legacy` remains identical to Phase 2A
- `hybrid` disables direct x/y qpos integration
- `hybrid` still records diagnostics
- weak or missing physical forward movement is recorded as diagnostic output, not treated as failure

Legacy mode passes Phase 2B if:
- existing Phase 1/Phase 2A tests still pass
- `qpos_xy_integration_count > 0` during a moving command
- position integration behavior matches the Phase 2A legacy behavior test
- no public API schema changes are introduced

Dynamic mode passes Phase 2B if:
- behavior remains mapped to Phase 2A legacy behavior
- no dynamic-only controller path is introduced
- no dynamic-only qpos/qvel removal is implemented

## 4. Strict Constraints

Do not:
- remove torso stabilization yet
- remove z forcing yet
- remove qvel roll/pitch zeroing yet
- remove qvel x/y forcing yet
- change ONNX policy behavior
- change waddle oscillator behavior
- change MuJoCo XML
- change actuator model
- add HAL
- change command queue semantics
- change physics loop ownership
- break public APIs
- add new fake compensation for lost forward motion

## 5. Tests To Add

Planned tests:
- default mode still `legacy`
- `legacy` still performs x/y qpos integration
- `hybrid` does not perform x/y qpos integration
- `hybrid` still records diagnostics
- `dynamic` remains behaviorally mapped to legacy for Phase 2B
- public API schemas unchanged
- Phase 1/Phase 2A regression tests still pass

Suggested focused command set:

```bash
pytest -q tests/test_phase2a_dynamics.py
pytest -q tests/test_phase2b_hybrid_dynamics.py
pytest -q tests/test_hardening.py tests/test_api.py tests/test_safety_preflight_enforcement.py tests/test_sensors_state.py tests/test_follower.py
```

Optional real/headless diagnostic smoke after unit tests:

```bash
DUCK_SIM_MODE=real DUCK_HEADLESS=true DUCK_DYNAMICS_MODE=legacy PYTHONPATH=. .venv/bin/pytest -q tests/test_api.py::test_api_health tests/test_api.py::test_api_state tests/test_sensors_state.py
DUCK_SIM_MODE=real DUCK_HEADLESS=true DUCK_DYNAMICS_MODE=hybrid PYTHONPATH=. .venv/bin/pytest -q tests/test_api.py::test_api_health tests/test_api.py::test_api_state tests/test_sensors_state.py
```

## 6. Rollback Strategy

- Runtime rollback: set `DUCK_DYNAMICS_MODE=legacy`.
- Code rollback: revert the Phase 2B commit only; Phase 2A scaffold remains intact.
- Operational fallback: if `hybrid` reveals no forward movement or unstable contact behavior, keep production/default deployments on `legacy` while using `hybrid` diagnostics for controller planning.

## 7. Phase 2C Gate

Phase 2C should not begin until Phase 2B reports:
- measured `legacy` vs `hybrid` displacement delta
- measured contact duty factor under `hybrid`
- measured correction magnitude under `hybrid`
- confirmation that `legacy` is unchanged
- confirmation that no public schema or command queue behavior changed
