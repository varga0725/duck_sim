# Phase 2E Hybrid Z-Force Scale Report

Phase 2E adds a hybrid-only z-force diagnostic scale and extends the moving-window diagnostics harness with yaw unwrapping, richer window statistics, z-correction metrics, no-contact duration, and fall/safety timestamps. No torso quaternion overwrite, qvel roll/pitch zeroing, ONNX/waddle behavior, MuJoCo XML, actuator model, HAL, public REST/WebSocket schema, command queue semantics, or dynamic-mode behavior was changed.

## 1. Changed Files Summary

- `duck_agent_sim/config.py`
  - Added `DUCK_HYBRID_Z_FORCE_SCALE`.
  - Added `parse_hybrid_z_force_scale()`.
  - Supported values: `1.0`, `0.5`, `0.0`.
  - Invalid values fall back to `1.0`.

- `duck_agent_sim/simulator/legacy_dynamics.py`
  - Added `hybrid_z_force_scale` to `LegacyDynamicsController`.
  - Applies z-force scaling only when `mode == "hybrid"`.
  - Tracks `qpos_z_correction_magnitude_sum` and `qpos_z_correction_magnitude_max`.
  - `scale=0.0` skips direct qpos[2]/qvel[2] forcing in hybrid.

- `duck_agent_sim/simulator/duck_sim.py`
  - Wires `DUCK_HYBRID_Z_FORCE_SCALE` into the real simulator dynamics controller.

- `scripts/diagnostics/phase2d_moving_window_diagnostics.py`
  - Adds `--matrix phase2e`.
  - Adds z-force scale to the matrix/env isolation.
  - Adds yaw-unwrapped displacement.
  - Adds roll/pitch/body-height min/max/avg.
  - Adds actuator saturation min/max/avg.
  - Adds correction-rate metrics.
  - Adds z forcing count and z correction magnitude.
  - Adds no-contact duration and fall/safety timestamps.

- `tests/test_phase2e_hybrid_z_force_scale.py`
  - Adds focused Phase 2E unit tests.

- `docs/phase2e_hybrid_z_force_scale_results.json`
  - Machine-readable Phase 2E diagnostic matrix results.

## 2. Behavior Diff

```text
legacy:
  - unchanged
  - ignores DUCK_HYBRID_Z_FORCE_SCALE
  - full qpos[2] forcing remains active

hybrid:
  - qpos x/y integration remains disabled
  - qvel x/y remains controlled by DUCK_HYBRID_QVEL_XY_SCALE
  - qpos[2] forcing is scaled by DUCK_HYBRID_Z_FORCE_SCALE
  - scale 1.0: current Phase 2D hybrid behavior
  - scale 0.5: partial correction toward 0.15m
  - scale 0.0: no direct qpos[2] forcing and no direct qvel[2] zeroing
  - torso quaternion overwrite remains active
  - qvel roll/pitch zeroing remains active
  - ONNX/waddle unchanged

dynamic:
  - unchanged
  - still legacy-mapped
  - ignores DUCK_HYBRID_Z_FORCE_SCALE
```

## 3. Diagnostic Matrix

Command:

```bash
PYTHONPATH=. .venv/bin/python scripts/diagnostics/phase2d_moving_window_diagnostics.py --matrix phase2e --output docs/phase2e_hybrid_z_force_scale_results.json
```

Profile:

```text
repeats: 3 per case
duration: 2.0 sec
stable wait: 0.25 sec
sample period: 0.1 sec
command: walk_forward
speed: 0.25
headless real simulator
```

Matrix:

```text
legacy baseline
hybrid qvel=0.0 z=1.0
hybrid qvel=0.0 z=0.5
hybrid qvel=0.0 z=0.0
hybrid qvel=1.0 z=1.0
hybrid qvel=1.0 z=0.5
hybrid qvel=1.0 z=0.0
```

## 4. Legacy vs Hybrid Comparison

| Case | Forward avg m | Lateral avg m | Yaw unwrapped avg deg | qpos z count | qvel xy count | Contact left/right/both | Safety | Fall |
| --- | ---: | ---: | ---: | ---: | ---: | --- | ---: | ---: |
| legacy | 0.562739 | 0.000752 | 0.002859 | 3859 | 3859 | 0.978 / 0.953 / 0.931 | 0 | 0 |
| hybrid qvel=1.0 z=1.0 | 0.272124 | 0.000741 | 0.002659 | 3820 | 3820 | 0.978 / 0.953 / 0.931 | 0 | 0 |
| hybrid qvel=1.0 z=0.5 | 0.271231 | 0.000809 | 0.002565 | 3819 | 3819 | 0.978 / 0.952 / 0.930 | 0 | 0 |
| hybrid qvel=1.0 z=0.0 | 0.277960 | -0.000009 | 0.008241 | 0 | 3775 | 0.549 / 0.771 / 0.321 | 0 | 0 |

Interpretation:
- With qvel x/y forcing still active, reducing or disabling z forcing does not remove forward displacement over this short window.
- Disabling z forcing raises body height and sharply reduces both-foot contact duty.
- No falls or safety interventions occurred.

## 5. qvel=0.0 + z-force Comparison

| Case | Forward avg m | Lateral avg m | Body height avg/min/max | Contact left/right/both | z correction sum/max | Safety | Fall |
| --- | ---: | ---: | --- | --- | --- | ---: | ---: |
| hybrid qvel=0.0 z=1.0 | 0.059935 | 0.012904 | 0.150081 / 0.150037 / 0.150123 | 1.000 / 1.000 / 1.000 | 0.358450 / 0.013297 | 0 | 0 |
| hybrid qvel=0.0 z=0.5 | 0.060001 | 0.012525 | 0.150159 / 0.150073 / 0.150245 | 1.000 / 1.000 / 1.000 | 0.358554 / 0.006648 | 0 | 0 |
| hybrid qvel=0.0 z=0.0 | -0.036222 | 0.006465 | 0.166641 / 0.161834 / 0.172166 | 0.684 / 0.716 / 0.406 | 0.000000 / 0.000000 | 0 | 0 |

Interpretation:
- With qvel x/y forcing disabled, full and half z forcing produce similar small positive forward displacement.
- Disabling z forcing reverses the average forward displacement in this short run and substantially reduces contact duty.
- The body floats higher without z forcing, indicating the direct z clamp is masking an important height/contact condition.

## 6. Roll/Pitch/Body Height

| Case | Roll avg/min/max deg | Pitch avg/min/max deg | Body height avg/min/max m |
| --- | --- | --- | --- |
| legacy | 0.175 / -0.423 / 1.105 | 2.079 / -2.570 / 4.013 | 0.150067 / 0.150022 / 0.150124 |
| hybrid qvel=0.0 z=1.0 | 0.101 / -0.927 / 1.468 | 0.852 / -1.871 / 2.880 | 0.150081 / 0.150037 / 0.150123 |
| hybrid qvel=0.0 z=0.5 | 0.100 / -0.896 / 1.463 | 0.833 / -1.862 / 2.863 | 0.150159 / 0.150073 / 0.150245 |
| hybrid qvel=0.0 z=0.0 | 0.015 / -0.700 / 0.752 | -1.643 / -2.319 / -1.043 | 0.166641 / 0.161834 / 0.172166 |
| hybrid qvel=1.0 z=0.0 | -0.777 / -1.530 / -0.045 | 0.158 / -2.921 / 2.500 | 0.165688 / 0.158183 / 0.171437 |

## 7. Yaw-Unwrapped Metrics

Yaw wrap artifacts are removed in the Phase 2E harness. All cases stayed near zero yaw drift:

```text
legacy:                    0.002859 deg avg
hybrid qvel=0.0 z=1.0:    -0.001879 deg avg
hybrid qvel=0.0 z=0.5:    -0.001438 deg avg
hybrid qvel=0.0 z=0.0:    -0.000116 deg avg
hybrid qvel=1.0 z=1.0:     0.002659 deg avg
hybrid qvel=1.0 z=0.5:     0.002565 deg avg
hybrid qvel=1.0 z=0.0:     0.008241 deg avg
```

## 8. Actuator Saturation

Window actuator saturation remained high but bounded:

```text
legacy avg/min/max:                 0.951 / 0.916 / 0.994
hybrid qvel=0.0 z=1.0 avg/min/max: 0.948 / 0.920 / 0.986
hybrid qvel=0.0 z=0.5 avg/min/max: 0.949 / 0.920 / 0.984
hybrid qvel=0.0 z=0.0 avg/min/max: 0.953 / 0.916 / 1.000
hybrid qvel=1.0 z=0.0 avg/min/max: 0.953 / 0.915 / 0.991
```

## 9. Contact Duty And No-Contact Duration

No sampled window had full no-contact duration:

```text
no_contact_duration_sec avg: 0.0 for all cases
```

However, both-foot contact duty dropped substantially when z forcing was disabled:

```text
hybrid qvel=0.0 z=1.0 both contact: 1.000
hybrid qvel=0.0 z=0.5 both contact: 1.000
hybrid qvel=0.0 z=0.0 both contact: 0.406
hybrid qvel=1.0 z=0.0 both contact: 0.321
```

## 10. Fall And Safety Events

```text
fall_event_count: 0 for all cases
safety_interventions: 0 for all cases
fall_reason: None for all cases
queue_stable: true for all cases
telemetry_stable: true for all cases
```

## 11. Interpretation

Z forcing is not required to prevent immediate collapse over a 2-second headless window while torso quaternion overwrite and qvel roll/pitch zeroing remain active.

Z forcing is still strongly shaping contact quality:
- At z scale `1.0` and `0.5`, both-foot contact remains nearly continuous in qvel=0.0 mode.
- At z scale `0.0`, body height rises to about `0.166m`, and both-foot contact duty drops to about `0.406`.
- With qvel=0.0, disabling z forcing changes small positive forward movement into slight negative average x displacement.

This means z forcing can be disabled diagnostically, but it should not be removed as a production default yet.

## 12. Can Z Forcing Be Reduced Or Disabled In Hybrid?

For diagnostics:
- Yes. `DUCK_HYBRID_Z_FORCE_SCALE=0.0` runs without crash, hang, fall, or telemetry/queue instability.

For locomotion quality:
- Not yet. Contact duty and displacement degrade when qvel=0.0 and z forcing is disabled.

Recommended hybrid defaults remain:

```text
DUCK_HYBRID_QVEL_XY_SCALE=1.0 or 0.5 for movement diagnostics
DUCK_HYBRID_Z_FORCE_SCALE=1.0 for stability baseline
```

Use `DUCK_HYBRID_Z_FORCE_SCALE=0.0` only as a contact/height diagnostic mode until torso stabilization and balance controls are addressed.

## 13. Rollback Strategy

- Runtime rollback: `DUCK_DYNAMICS_MODE=legacy`.
- Hybrid z rollback: `DUCK_HYBRID_Z_FORCE_SCALE=1.0`.
- Code rollback: revert the Phase 2E commit only; Phase 2A-2D scaffolding remains separable.

## 14. Recommendation For Phase 2F

Do not remove torso quaternion overwrite yet.

Recommended next sprint:

1. Keep `legacy` unchanged.
2. Keep `hybrid` diagnostics available for qvel and z scales.
3. Add torso quaternion overwrite scaling/disable diagnostics behind `DUCK_HYBRID_TORSO_ORIENTATION_SCALE`.
4. Keep qvel roll/pitch zeroing active initially while testing torso orientation scale.
5. Use the same moving-window harness with yaw-unwrapped metrics, contact duty, height, roll/pitch, and fall timestamps.
