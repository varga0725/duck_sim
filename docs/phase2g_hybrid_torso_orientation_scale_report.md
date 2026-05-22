# Phase 2G Hybrid Torso Orientation Scaling Report

Phase 2G adds a hybrid-only diagnostic scale for direct torso quaternion overwrite. This remains diagnostics-first: no PD balance controller, ONNX/waddle behavior, MuJoCo XML, actuator model, HAL, public API schema, command queue semantics, dynamic-mode behavior, or legacy default behavior was changed.

## 1. Changed Files Summary

- `duck_agent_sim/config.py`
  - Added `DUCK_HYBRID_TORSO_ORIENTATION_SCALE`.
  - Added `parse_hybrid_torso_orientation_scale()`.
  - Supported values: `1.0`, `0.5`, `0.0`; invalid values fall back to `1.0`.

- `duck_agent_sim/simulator/legacy_dynamics.py`
  - Added `hybrid_torso_orientation_scale`.
  - Applies torso quaternion correction scaling only in `hybrid`.
  - Uses normalized quaternion interpolation between the current torso orientation and the existing stabilized target orientation.
  - Tracks `torso_orientation_correction_magnitude_sum/max`.
  - `scale=0.0` skips direct torso quaternion overwrite in hybrid.

- `duck_agent_sim/simulator/duck_sim.py`
  - Wires the new config value into the real simulator dynamics controller.

- `scripts/diagnostics/phase2d_moving_window_diagnostics.py`
  - Adds `--matrix phase2g`.
  - Adds `DUCK_HYBRID_TORSO_ORIENTATION_SCALE` env isolation.
  - Emits torso overwrite count and torso correction magnitude metrics.

- `tests/test_phase2g_hybrid_torso_orientation_scale.py`
  - Adds focused parser, behavior, isolation, and schema tests.

- `docs/phase2g_hybrid_torso_orientation_scale_results.json`
  - Machine-readable Phase 2G real/headless results.

## 2. Behavior Diff

```text
legacy:
  - unchanged
  - ignores DUCK_HYBRID_TORSO_ORIENTATION_SCALE
  - full torso quaternion overwrite remains active

hybrid:
  - qpos x/y integration remains disabled
  - qvel x/y scale remains controlled by DUCK_HYBRID_QVEL_XY_SCALE
  - z forcing remains controlled by DUCK_HYBRID_Z_FORCE_SCALE
  - roll/pitch qvel damping remains controlled by DUCK_HYBRID_RP_QVEL_ZERO_SCALE
  - torso quaternion correction is controlled by DUCK_HYBRID_TORSO_ORIENTATION_SCALE
  - scale 1.0: full current Phase 2F overwrite
  - scale 0.5: partial normalized correction toward the stabilized target
  - scale 0.0: no direct torso quaternion overwrite

dynamic:
  - unchanged
  - still legacy-mapped
```

## 3. Diagnostic Matrix

Command:

```bash
PYTHONPATH=. .venv/bin/python scripts/diagnostics/phase2d_moving_window_diagnostics.py --matrix phase2g --output docs/phase2g_hybrid_torso_orientation_scale_results.json
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
hybrid qvel=0.0 z=1.0 rp=0.5 torso=1.0
hybrid qvel=0.0 z=1.0 rp=0.5 torso=0.5
hybrid qvel=0.0 z=1.0 rp=0.5 torso=0.0
hybrid qvel=0.0 z=0.5 rp=0.5 torso=1.0
hybrid qvel=0.0 z=0.5 rp=0.5 torso=0.5
hybrid qvel=0.0 z=0.5 rp=0.5 torso=0.0
```

## 4. Roll/Pitch Stability Comparison

| Case | Roll avg/min/max deg | Pitch avg/min/max deg |
| --- | --- | --- |
| legacy | 0.173 / -0.410 / 1.113 | 2.034 / -2.568 / 4.015 |
| z=1.0 torso=1.0 | 0.052 / -1.038 / 2.057 | 2.490 / -1.462 / 4.009 |
| z=1.0 torso=0.5 | 0.061 / -1.037 / 2.064 | 2.488 / -1.407 / 4.019 |
| z=1.0 torso=0.0 | 0.080 / -0.927 / 2.079 | 2.834 / -1.376 / 5.215 |
| z=0.5 torso=1.0 | 0.053 / -1.044 / 2.085 | 2.488 / -1.400 / 4.008 |
| z=0.5 torso=0.5 | 0.062 / -1.036 / 2.067 | 2.468 / -1.405 / 4.019 |
| z=0.5 torso=0.0 | 0.090 / -0.921 / 2.040 | 2.792 / -1.365 / 5.204 |

Interpretation:
- `torso=0.5` tracks close to `torso=1.0` in this short window.
- `torso=0.0` does not cause immediate fall, but it increases maximum pitch from about 4.0 deg to about 5.2 deg.
- The posture shift is visible even while `rp=0.5` and z forcing remain active.

## 5. Body Height And Contact Comparison

| Case | Body height avg/min/max m | Contact left/right/both | No-contact avg sec |
| --- | --- | --- | ---: |
| legacy | 0.150069 / 0.150022 / 0.150120 | 0.978 / 0.955 / 0.933 | 0.0 |
| z=1.0 torso=1.0 | 0.150071 / 0.150027 / 0.150114 | 1.000 / 1.000 / 1.000 | 0.0 |
| z=1.0 torso=0.5 | 0.150071 / 0.150025 / 0.150115 | 1.000 / 1.000 / 1.000 | 0.0 |
| z=1.0 torso=0.0 | 0.150069 / 0.150025 / 0.150114 | 0.996 / 0.984 / 0.980 | 0.0 |
| z=0.5 torso=1.0 | 0.150138 / 0.150049 / 0.150227 | 1.000 / 1.000 / 1.000 | 0.0 |
| z=0.5 torso=0.5 | 0.150142 / 0.150060 / 0.150229 | 1.000 / 1.000 / 1.000 | 0.0 |
| z=0.5 torso=0.0 | 0.150136 / 0.150038 / 0.150228 | 0.996 / 0.984 / 0.980 | 0.0 |

Height remains bounded because z forcing is still `1.0` or `0.5`. Contact quality degrades slightly when torso overwrite is fully disabled.

## 6. Movement Comparison

| Case | Forward avg m | Lateral avg m | Yaw unwrapped avg deg |
| --- | ---: | ---: | ---: |
| legacy | 0.560434 | 0.000735 | 0.002306 |
| z=1.0 torso=1.0 | 0.058178 | 0.010487 | -0.001311 |
| z=1.0 torso=0.5 | 0.058314 | 0.010141 | -0.002446 |
| z=1.0 torso=0.0 | 0.058003 | 0.010918 | -0.356525 |
| z=0.5 torso=1.0 | 0.058383 | 0.010447 | -0.000595 |
| z=0.5 torso=0.5 | 0.057933 | 0.009896 | -0.002254 |
| z=0.5 torso=0.0 | 0.056822 | 0.011243 | -0.337694 |

Disabling torso overwrite does not improve forward movement in this baseline. It adds yaw drift while forward displacement remains near the same low contact-driven range.

## 7. Torso Orientation Correction Metrics

| Case | Torso overwrite count | Torso correction sum/max |
| --- | ---: | --- |
| legacy | 3917 | 0.207086 / 0.000222 |
| z=1.0 torso=1.0 | 3879 | 0.176519 / 0.000222 |
| z=1.0 torso=0.5 | 3783 | 0.175598 / 0.000111 |
| z=1.0 torso=0.0 | 0 | 0.000000 / 0.000000 |
| z=0.5 torso=1.0 | 3820 | 0.177850 / 0.000222 |
| z=0.5 torso=0.5 | 3773 | 0.174096 / 0.000111 |
| z=0.5 torso=0.0 | 0 | 0.000000 / 0.000000 |

The count and max correction metrics confirm the feature flag behavior:

```text
torso=1.0 -> overwrite count > 0, full max correction
torso=0.5 -> overwrite count > 0, half max correction
torso=0.0 -> overwrite count == 0, correction magnitude == 0
```

## 8. Fall And Safety Events

```text
fall_event_count: 0 for all cases
safety_interventions: 0 for all cases
fall_reason: None for all cases
queue_stable: true for all cases
telemetry_stable: true for all cases
```

## 9. Can Torso Quaternion Overwrite Be Reduced Or Disabled In Hybrid?

For diagnostics:
- Yes. `DUCK_HYBRID_TORSO_ORIENTATION_SCALE=0.5` and `0.0` run without crash, queue instability, telemetry instability, falls, or safety interventions in the 2s window.

For production default:
- Not yet. `torso=0.0` increases pitch envelope and introduces yaw drift without improving forward movement.
- `torso=0.5` is the safer next diagnostic baseline because it preserves short-window movement/contact behavior while reducing the direct quaternion correction magnitude.

Recommended next diagnostic baseline:

```text
DUCK_HYBRID_QVEL_XY_SCALE=0.0
DUCK_HYBRID_Z_FORCE_SCALE=0.5
DUCK_HYBRID_RP_QVEL_ZERO_SCALE=0.5
DUCK_HYBRID_TORSO_ORIENTATION_SCALE=0.5
```

## 10. Rollback Strategy

- Runtime rollback: `DUCK_DYNAMICS_MODE=legacy`.
- Hybrid torso rollback: `DUCK_HYBRID_TORSO_ORIENTATION_SCALE=1.0`.
- Code rollback: revert the Phase 2G commit only; Phase 2A-2F remain separable.

## 11. Recommendation For Phase 2H

Do not introduce PD balance yet.

Recommended next sprint:

1. Keep `legacy` unchanged.
2. Keep `dynamic` legacy-mapped.
3. Use the reduced-hack hybrid baseline: `qvel=0.0`, `z=0.5`, `rp=0.5`, `torso=0.5`.
4. Run longer 5s moving-window diagnostics and optional stop/recovery windows.
5. Only after longer-window stability is characterized, plan the first non-fake balance controller scaffold.
