# Phase 2A Dynamics Scaffold Report

Phase 2A implemented feature-flag scaffolding and diagnostics only. It does not remove qpos forcing, torso stabilization, ONNX behavior, waddle behavior, MuJoCo XML parameters, actuator behavior, public REST schemas, WebSocket schemas, or HAL boundaries.

## Changed Files

- `duck_agent_sim/config.py`
  - Added `DUCK_DYNAMICS_MODE=legacy|hybrid|dynamic` parsing.
  - Default is `legacy`.
  - Invalid or empty values fall back to `legacy`.

- `duck_agent_sim/simulator/legacy_dynamics.py`
  - Added `LegacyDynamicsController`.
  - Added `LegacyDynamicsDiagnostics`.
  - Extracted the existing fake dynamics write pattern into an explicit legacy dynamics path.
  - Records correction counters and runtime measurements without changing control outputs.

- `duck_agent_sim/simulator/duck_sim.py`
  - Real simulator now owns `_dynamics_mode` and `_legacy_dynamics`.
  - `_stabilize_torso()` delegates to the legacy dynamics controller.
  - `hybrid` and `dynamic` currently preserve legacy behavior and only label diagnostics.
  - Internal ringbuffer snapshots include a `dynamics` diagnostics object. Public API schemas are unchanged.

- `tests/test_phase2a_dynamics.py`
  - Added feature-flag parsing tests.
  - Added default legacy-mode test.
  - Added exact legacy fake-write behavior test.
  - Added instrumentation counter test.
  - Added public schema stability test.

## Dynamics Mode Architecture Diff

Old Phase 1 real simulator flow:

```text
Physics Loop
  -> control smoothing / ONNX or waddle
  -> _stabilize_torso()
       -> direct torso quaternion overwrite
       -> direct z clamp
       -> direct qvel x/y assignment
       -> direct qpos x/y integration
       -> direct qvel roll/pitch zeroing
  -> mj_step()
  -> state publication
```

Phase 2A flow:

```text
Physics Loop
  -> control smoothing / ONNX or waddle
  -> _stabilize_torso()
       -> LegacyDynamicsController.apply()
            -> same legacy fake dynamics writes
            -> diagnostics counters and measurements
  -> mj_step()
  -> state publication
```

Mode behavior in Phase 2A:

```text
legacy  -> legacy writes + diagnostics
hybrid  -> legacy writes + diagnostics, behavior changes deferred
dynamic -> legacy writes + diagnostics, behavior changes deferred
```

This keeps rollback immediate and prevents accidental locomotion regression before Phase 2B.

## Instrumentation

The legacy dynamics controller records:

- `qpos_xy_integration_count`
- `qpos_z_forcing_count`
- `torso_quaternion_overwrite_count`
- `qvel_xy_forcing_count`
- `qvel_roll_pitch_zeroing_count`
- `correction_magnitude_sum`
- `correction_magnitude_max`
- `contact_duty_factor.left`
- `contact_duty_factor.right`
- `contact_duty_factor.both`
- `last_roll_deg`
- `last_pitch_deg`
- `last_body_height_m`
- `last_actuator_saturation`
- `last_fall_reason`

Sample diagnostics from the focused unit test:

```text
mode: legacy
qpos_xy_integration_count: 1
qpos_z_forcing_count: 1
torso_quaternion_overwrite_count: 1
qvel_xy_forcing_count: 1
qvel_roll_pitch_zeroing_count: 1
contact_duty_factor: {left: 1.0, right: 0.0, both: 0.0}
last_roll_deg: 0.0
last_pitch_deg: 0.0
last_body_height_m: 0.15
last_actuator_saturation: 0.75
last_fall_reason: null
```

## Legacy Behavior Proof

The Phase 2A behavior test verifies the exact legacy fake-write outputs for a deterministic fake simulator:

- x qpos integrates as `global_vx * 0.002`.
- y qpos integrates as `global_vy * 0.002`.
- z qpos is forced to `0.15`.
- torso quaternion is overwritten to the stabilized yaw/roll/pitch quaternion.
- qvel x/y are forced from command velocity.
- qvel z is forced to `0.0`.
- qvel roll/pitch are forced to `0.0`.
- qvel yaw is forced from command yaw rate.

Public schema test verifies no `dynamics` or `dynamics_mode` fields were added to `RobotState`, `CommandResponse`, or `HealthResponse`.

## Test Results

```bash
pytest -q tests/test_phase2a_dynamics.py
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

## Rollback Strategy

- Runtime rollback: set `DUCK_DYNAMICS_MODE=legacy`.
- Code rollback: revert the Phase 2A commit; behavior returns to inline `_stabilize_torso()` implementation.
- Operational rollback risk is low because Phase 2A preserves the same writes and timing cadence.

## Regression Risks

- Diagnostics are internal only, but ringbuffer memory payloads are slightly larger.
- The legacy helper is called under the existing simulator lock; this preserves behavior but keeps the old lock scope.
- `hybrid` and `dynamic` names exist but intentionally do not change behavior yet. Operators must not interpret those modes as real dynamics modes until Phase 2B/2C.

## Phase 2B Recommendation

Proceed to Phase 2B only after reviewing this scaffold. Recommended next stage:

1. Keep `legacy` unchanged.
2. In `hybrid`, disable only direct x/y qpos integration behind the feature flag.
3. Keep torso stabilization initially active in `hybrid`.
4. Compare displacement, contact duty factor, correction magnitude, roll/pitch/body height, and actuator saturation against `legacy`.
5. Treat weak or missing forward movement as diagnostic output, not as failure.
