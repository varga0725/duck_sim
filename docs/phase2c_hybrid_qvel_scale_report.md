# Phase 2C Hybrid Qvel XY Scale Report

Phase 2C adds a hybrid-only qvel x/y scaling diagnostic knob. It does not remove torso stabilization, z forcing, torso quaternion overwrite, qvel roll/pitch zeroing, ONNX behavior, waddle behavior, MuJoCo XML, actuator behavior, HAL boundaries, public REST/WebSocket schemas, or command queue ownership.

## 1. Changed Files

- `.gitignore`
  - Added local Ruflo/RuVector runtime artifacts: `ruvector.db`, `agentdb.rvf`, `agentdb.rvf.lock`.

- `duck_agent_sim/config.py`
  - Added `DUCK_HYBRID_QVEL_XY_SCALE`.
  - Added `parse_hybrid_qvel_xy_scale()`.
  - Supported values: `1.0`, `0.5`, `0.0`.
  - Invalid values fall back to `1.0`.

- `duck_agent_sim/simulator/legacy_dynamics.py`
  - Added `hybrid_qvel_xy_scale` to `LegacyDynamicsController`.
  - Applies qvel x/y scaling only when `mode == "hybrid"`.
  - `scale=1.0` preserves Phase 2B hybrid behavior.
  - `scale=0.5` writes half qvel x/y command.
  - `scale=0.0` skips qvel x/y forcing in hybrid.
  - Added `last_qvel_xy_commanded_magnitude` diagnostics.

- `duck_agent_sim/simulator/duck_sim.py`
  - Wires `DUCK_HYBRID_QVEL_XY_SCALE` into the real simulator's legacy dynamics controller.
  - Keeps mock API command response deterministic for scheduled movement state while preserving queue duration waiting.

- `tests/test_phase2c_hybrid_qvel_scale.py`
  - Adds focused tests for parser fallback, hybrid-only scaling, scale `1.0`, `0.5`, `0.0`, Phase 2B hybrid qpos behavior, legacy/dynamic isolation, and public schema stability.

## 2. Behavior Diff

```text
legacy:
  - unchanged
  - qpos x/y integration remains active
  - qvel x/y forcing remains full scale
  - ignores DUCK_HYBRID_QVEL_XY_SCALE

hybrid:
  - qpos x/y integration remains disabled
  - qvel x/y forcing is scaled by DUCK_HYBRID_QVEL_XY_SCALE
  - default scale 1.0 preserves Phase 2B behavior
  - scale 0.0 disables qvel x/y forcing
  - torso stabilization remains active
  - z forcing remains active
  - torso quaternion overwrite remains active
  - qvel roll/pitch zeroing remains active

dynamic:
  - unchanged
  - still legacy-mapped for now
  - ignores DUCK_HYBRID_QVEL_XY_SCALE
```

## 3. Diagnostic Comparison

Deterministic hybrid controller comparison:

```text
DUCK_HYBRID_QVEL_XY_SCALE=1.0
  qvel_xy_forcing_count: 1
  qvel_xy_commanded_magnitude: 0.25
  forward_displacement: 0.0
  yaw_displacement: 0.0004
  contact_duty_factor: {left: 1.0, right: 0.0, both: 0.0}
  roll/pitch/body_height: 0.0 / 0.0 / 0.15
  correction_magnitude_sum: 1.5837865650161955
  actuator_saturation: 0.75
  fall_reason: None
  movement_disappears: True

DUCK_HYBRID_QVEL_XY_SCALE=0.5
  qvel_xy_forcing_count: 1
  qvel_xy_commanded_magnitude: 0.125
  forward_displacement: 0.0
  yaw_displacement: 0.0004
  contact_duty_factor: {left: 1.0, right: 0.0, both: 0.0}
  roll/pitch/body_height: 0.0 / 0.0 / 0.15
  correction_magnitude_sum: 1.5684288639044202
  actuator_saturation: 0.75
  fall_reason: None
  movement_disappears: True

DUCK_HYBRID_QVEL_XY_SCALE=0.0
  qvel_xy_forcing_count: 0
  qvel_xy_commanded_magnitude: 0.0
  forward_displacement: 0.0
  yaw_displacement: 0.0004
  contact_duty_factor: {left: 1.0, right: 0.0, both: 0.0}
  roll/pitch/body_height: 0.0 / 0.0 / 0.15
  correction_magnitude_sum: 1.5632749950405542
  actuator_saturation: 0.75
  fall_reason: None
  movement_disappears: True
```

Interpretation:
- With direct qpos x/y integration already disabled in hybrid, the deterministic harness shows no forward displacement at all three qvel scales.
- Contact dynamics do not create useful displacement in this isolated controller harness.
- Lower qvel scale reduces correction magnitude as expected.
- This is diagnostic evidence, not a failure.

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
pytest -q tests/test_phase2c_hybrid_qvel_scale.py
```

```text
9 passed
```

```bash
pytest -q tests/test_hardening.py tests/test_api.py tests/test_safety_preflight_enforcement.py tests/test_sensors_state.py tests/test_follower.py
```

```text
32 passed
```

## 5. Real/Headless Smoke Results

Scale `1.0`:

```bash
DUCK_SIM_MODE=real DUCK_HEADLESS=true DUCK_DYNAMICS_MODE=hybrid DUCK_HYBRID_QVEL_XY_SCALE=1.0 PYTHONPATH=. .venv/bin/pytest -q tests/test_api.py::test_api_health tests/test_api.py::test_api_state tests/test_sensors_state.py
```

```text
5 passed, 1 warning
```

Scale `0.0`:

```bash
DUCK_SIM_MODE=real DUCK_HEADLESS=true DUCK_DYNAMICS_MODE=hybrid DUCK_HYBRID_QVEL_XY_SCALE=0.0 PYTHONPATH=. .venv/bin/pytest -q tests/test_api.py::test_api_health tests/test_api.py::test_api_state tests/test_sensors_state.py
```

```text
5 passed, 1 warning
```

Warning:
- `jaxopt` deprecation warning from the `.venv` dependency stack.

## 6. Regression Risks

- `scale=0.0` disables qvel x/y forcing in hybrid, so hybrid movement may remain absent or become weaker.
- Hybrid still has torso quaternion overwrite, z forcing, and roll/pitch qvel zeroing, so it is not yet real dynamics.
- Dynamic mode remains legacy-mapped; it must not be treated as production dynamic locomotion.
- Diagnostics remain internal and do not change public API schemas.

## 7. Rollback Strategy

- Runtime rollback: set `DUCK_DYNAMICS_MODE=legacy`.
- Hybrid behavior rollback: set `DUCK_HYBRID_QVEL_XY_SCALE=1.0`.
- Code rollback: revert the Phase 2C commit only; Phase 2B hybrid qpos removal remains separable.

## 8. Recommendation For Next Sprint

Recommended next sprint:

1. Keep `legacy` unchanged.
2. Keep `hybrid` qpos x/y integration disabled.
3. Run real/headless moving-command diagnostic windows for hybrid scales `1.0`, `0.5`, and `0.0`.
4. Decide whether qvel x/y forcing can remain disabled in hybrid.
5. Do not remove torso stabilization until real/headless contact, roll/pitch, and body-height diagnostics are reviewed.
