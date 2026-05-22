# Phase 2B Hybrid Qpos Removal Report

Phase 2B implemented only the approved hybrid-mode behavior change: direct base `qpos[0]` / `qpos[1]` integration is skipped when `DUCK_DYNAMICS_MODE=hybrid`. `legacy` preserves Phase 2A behavior. `dynamic` remains mapped to legacy behavior for now.

## 1. Changed Files Summary

- `duck_agent_sim/simulator/legacy_dynamics.py`
  - Added a mode branch around the direct x/y base-position integration writes.
  - `hybrid` skips only `qpos[0] += global_vx * fixed_dt_sec` and `qpos[1] += global_vy * fixed_dt_sec`.
  - `legacy` and `dynamic` still execute the Phase 2A direct x/y integration path.
  - `qpos_xy_integration_count` now increments only when the direct x/y qpos integration write actually runs.

- `tests/test_phase2b_hybrid_dynamics.py`
  - Verifies legacy still performs x/y qpos integration.
  - Verifies hybrid skips only x/y qpos integration.
  - Verifies hybrid still records diagnostics.
  - Verifies dynamic remains mapped to legacy behavior for Phase 2B.
  - Verifies public API schemas remain unchanged.

- `docs/phase2b_hybrid_qpos_removal_report.md`
  - Documents behavior split, diagnostics comparison, validation results, rollback, risks, and Phase 2C recommendation.

## 2. Exact Behavior Diff

```text
legacy:
  - unchanged from Phase 2A
  - qpos x/y integration active
  - torso quaternion overwrite active
  - z forcing active
  - qvel x/y forcing active
  - qvel roll/pitch zeroing active
  - ONNX/waddle behavior unchanged

hybrid:
  - direct qpos[0]/qpos[1] integration disabled
  - torso quaternion overwrite still active
  - z forcing still active
  - qvel x/y forcing still active
  - qvel roll/pitch zeroing still active
  - ONNX/waddle behavior unchanged
  - no new compensation was added for missing movement

dynamic:
  - still mapped to legacy behavior
  - no dynamic controller path introduced
  - no dynamic-only qpos/qvel removal implemented
```

Only skipped hybrid writes:

```python
data.qpos[0] += global_vx * fixed_dt_sec
data.qpos[1] += global_vy * fixed_dt_sec
```

## 3. Diagnostics Comparison

Deterministic diagnostic comparison from the focused controller harness:

```text
legacy:
  forward_displacement: 0.0004999999600000005
  yaw_displacement: 0.0004
  qpos_xy_integration_count: 1
  contact_duty_factor: {left: 1.0, right: 0.0, both: 0.0}
  correction_magnitude_sum: 1.5837890649337003
  roll/pitch/body_height: 0.0 / 0.0 / 0.15
  actuator_saturation: 0.75
  fall_reason: None

hybrid:
  forward_displacement: 0.0
  yaw_displacement: 0.0004
  qpos_xy_integration_count: 0
  contact_duty_factor: {left: 1.0, right: 0.0, both: 0.0}
  correction_magnitude_sum: 1.5837865650161955
  roll/pitch/body_height: 0.0 / 0.0 / 0.15
  actuator_saturation: 0.75
  fall_reason: None
```

Required counter result:

```text
legacy qpos_xy_integration_count > 0
hybrid qpos_xy_integration_count == 0
```

Status: satisfied.

Interpretation:
- Hybrid weak or missing forward movement is expected diagnostic evidence that the prior visible locomotion depended on direct base translation.
- This is not treated as a Phase 2B failure.
- No replacement hack, friction bypass, torso compensation, actuator shortcut, or controller rewrite was introduced.

## 4. Test Results

```bash
pytest -q tests/test_phase2a_dynamics.py
```

```text
5 passed
```

```bash
pytest -q tests/test_phase2b_hybrid_dynamics.py
```

```text
5 passed
```

```bash
pytest -q tests/test_hardening.py tests/test_api.py tests/test_safety_preflight_enforcement.py tests/test_sensors_state.py tests/test_follower.py
```

```text
32 passed
```

## 5. Real/Headless Smoke Results

Legacy mode:

```bash
DUCK_SIM_MODE=real DUCK_HEADLESS=true DUCK_DYNAMICS_MODE=legacy PYTHONPATH=. .venv/bin/pytest -q tests/test_api.py::test_api_health tests/test_api.py::test_api_state tests/test_sensors_state.py
```

```text
5 passed, 1 warning
```

Hybrid mode:

```bash
DUCK_SIM_MODE=real DUCK_HEADLESS=true DUCK_DYNAMICS_MODE=hybrid PYTHONPATH=. .venv/bin/pytest -q tests/test_api.py::test_api_health tests/test_api.py::test_api_state tests/test_sensors_state.py
```

```text
5 passed, 1 warning
```

Warning:
- `jaxopt` deprecation warning from the `.venv` dependency stack.

## 6. Rollback Strategy

- Runtime rollback: set `DUCK_DYNAMICS_MODE=legacy`.
- Code rollback: revert the Phase 2B commit only; Phase 2A scaffold remains intact.
- Operational fallback: keep production/default deployments on `legacy` and use `hybrid` only for diagnostics until Phase 2C is approved.

## 7. Regression Risks

- Hybrid forward displacement may be weak or zero because direct x/y base translation is disabled.
- qvel x/y forcing remains active, so hybrid is not yet real dynamics.
- Torso and height stabilization remain active, so fall behavior is still masked relative to true dynamics.
- Dynamic mode name exists but still maps to legacy behavior; it must not be interpreted as a real dynamic-control path yet.

## 8. Recommendation For Phase 2C

Proceed only after Phase 2B review. Recommended Phase 2C scope:

1. Keep `legacy` unchanged.
2. Keep `hybrid` qpos x/y integration disabled.
3. Introduce measured comparison over a real/headless moving command window.
4. Evaluate whether qvel x/y forcing can be reduced or disabled in `hybrid`.
5. Do not remove torso stabilization until hybrid qvel/contact diagnostics are understood.
