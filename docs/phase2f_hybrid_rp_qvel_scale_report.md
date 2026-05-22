# Phase 2F Hybrid Roll/Pitch Qvel Damping Report

Phase 2F adds a hybrid-only roll/pitch angular-velocity damping diagnostic scale. Torso quaternion overwrite remains active. No ONNX/waddle behavior, MuJoCo XML, actuator model, HAL, public API schema, command queue semantics, or dynamic-mode behavior was changed.

## 1. Changed Files Summary

- `duck_agent_sim/config.py`
  - Added `DUCK_HYBRID_RP_QVEL_ZERO_SCALE`.
  - Added `parse_hybrid_rp_qvel_zero_scale()`.
  - Supported values: `1.0`, `0.5`, `0.0`; invalid values fall back to `1.0`.

- `duck_agent_sim/simulator/legacy_dynamics.py`
  - Added `hybrid_rp_qvel_zero_scale`.
  - Applies roll/pitch qvel damping only in `hybrid`.
  - Tracks `qvel_roll_pitch_damping_magnitude_sum/max`.
  - `scale=0.0` skips direct `qvel[3]` / `qvel[4]` zeroing in hybrid.

- `duck_agent_sim/simulator/duck_sim.py`
  - Wires the new config value into the real simulator dynamics controller.

- `scripts/diagnostics/phase2d_moving_window_diagnostics.py`
  - Adds `--matrix phase2f`.
  - Adds `DUCK_HYBRID_RP_QVEL_ZERO_SCALE` env isolation.
  - Emits roll/pitch qvel damping metrics.

- `tests/test_phase2f_hybrid_rp_qvel_scale.py`
  - Adds focused parser, behavior, isolation, and schema tests.

- `docs/phase2f_hybrid_rp_qvel_scale_results.json`
  - Machine-readable Phase 2F real/headless results.

## 2. Behavior Diff

```text
legacy:
  - unchanged
  - ignores DUCK_HYBRID_RP_QVEL_ZERO_SCALE
  - full roll/pitch qvel zeroing remains active

hybrid:
  - qpos x/y integration remains disabled
  - qvel x/y scale remains controlled by DUCK_HYBRID_QVEL_XY_SCALE
  - z forcing remains controlled by DUCK_HYBRID_Z_FORCE_SCALE
  - torso quaternion overwrite remains active
  - qvel[3]/qvel[4] damping is controlled by DUCK_HYBRID_RP_QVEL_ZERO_SCALE
  - scale 1.0: full zeroing
  - scale 0.5: partial damping
  - scale 0.0: no direct roll/pitch qvel zeroing

dynamic:
  - unchanged
  - still legacy-mapped
```

## 3. Diagnostic Matrix

Command:

```bash
PYTHONPATH=. .venv/bin/python scripts/diagnostics/phase2d_moving_window_diagnostics.py --matrix phase2f --output docs/phase2f_hybrid_rp_qvel_scale_results.json
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
hybrid qvel=0.0 z=1.0 rp=1.0
hybrid qvel=0.0 z=1.0 rp=0.5
hybrid qvel=0.0 z=1.0 rp=0.0
hybrid qvel=0.0 z=0.5 rp=1.0
hybrid qvel=0.0 z=0.5 rp=0.5
hybrid qvel=0.0 z=0.5 rp=0.0
```

## 4. Roll/Pitch Stability Comparison

| Case | Roll avg/min/max deg | Pitch avg/min/max deg | RP zero count | RP damping sum/max |
| --- | --- | --- | ---: | --- |
| legacy | 0.174 / -0.432 / 1.096 | 1.995 / -2.563 / 4.012 | 3895 | 366.947 / 0.413 |
| z=1.0 rp=1.0 | 0.104 / -0.898 / 1.474 | 0.852 / -1.847 / 2.886 | 3835 | 254.083 / 0.413 |
| z=1.0 rp=0.5 | 0.066 / -1.038 / 2.050 | 2.500 / -1.337 / 4.009 | 3782 | 202.579 / 0.206 |
| z=1.0 rp=0.0 | -0.005 / -3.838 / 2.571 | 4.046 / 3.443 / 4.122 | 0 | 0.000 / 0.000 |
| z=0.5 rp=1.0 | 0.066 / -0.904 / 1.414 | 0.830 / -1.880 / 2.838 | 3789 | 250.873 / 0.413 |
| z=0.5 rp=0.5 | 0.050 / -1.036 / 2.072 | 2.477 / -1.404 / 4.009 | 3770 | 201.460 / 0.206 |
| z=0.5 rp=0.0 | -0.028 / -3.840 / 2.574 | 4.063 / 3.809 / 4.124 | 0 | 0.000 / 0.000 |

Interpretation:
- Disabling roll/pitch qvel zeroing did not cause immediate fall in the 2s window.
- It increased roll range substantially and shifted pitch into a persistent forward-lean region around 4 degrees.
- `rp=0.5` is a smoother middle point than `rp=0.0`, but still changes pitch behavior materially.

## 5. Body Height And Contact Comparison

| Case | Body height avg/min/max m | Contact left/right/both | No-contact avg sec |
| --- | --- | --- | ---: |
| legacy | 0.150071 / 0.150022 / 0.150124 | 0.978 / 0.963 / 0.941 | 0.0 |
| z=1.0 rp=1.0 | 0.150080 / 0.150036 / 0.150123 | 1.000 / 1.000 / 1.000 | 0.0 |
| z=1.0 rp=0.5 | 0.150070 / 0.150028 / 0.150114 | 1.000 / 1.000 / 1.000 | 0.0 |
| z=1.0 rp=0.0 | 0.150061 / 0.150027 / 0.150086 | 1.000 / 1.000 / 1.000 | 0.0 |
| z=0.5 rp=1.0 | 0.150158 / 0.150073 / 0.150244 | 1.000 / 1.000 / 1.000 | 0.0 |
| z=0.5 rp=0.5 | 0.150140 / 0.150050 / 0.150223 | 1.000 / 1.000 / 1.000 | 0.0 |
| z=0.5 rp=0.0 | 0.150120 / 0.150056 / 0.150172 | 1.000 / 1.000 / 1.000 | 0.0 |

Contact and height remain stable in this matrix because z forcing is still `1.0` or `0.5`; z=0.0 was intentionally not used for Phase 2F.

## 6. Movement Comparison

| Case | Forward avg m | Lateral avg m | Yaw unwrapped avg deg |
| --- | ---: | ---: | ---: |
| legacy | 0.558481 | 0.000826 | 0.000857 |
| z=1.0 rp=1.0 | 0.059787 | 0.012561 | -0.002506 |
| z=1.0 rp=0.5 | 0.058742 | 0.010245 | -0.000944 |
| z=1.0 rp=0.0 | 0.211412 | -0.004968 | 0.001271 |
| z=0.5 rp=1.0 | 0.060039 | 0.012381 | -0.001307 |
| z=0.5 rp=0.5 | 0.058337 | 0.009862 | -0.000821 |
| z=0.5 rp=0.0 | 0.208635 | -0.005418 | 0.002288 |

Disabling direct roll/pitch qvel zeroing increased forward displacement in this short diagnostic window, but it also changed posture materially. This is useful evidence, not yet a production locomotion improvement.

## 7. Fall And Safety Events

```text
fall_event_count: 0 for all cases
safety_interventions: 0 for all cases
fall_reason: None for all cases
queue_stable: true for all cases
telemetry_stable: true for all cases
```

## 8. Can Roll/Pitch Qvel Zeroing Be Reduced Or Disabled In Hybrid?

For diagnostics:
- Yes. `DUCK_HYBRID_RP_QVEL_ZERO_SCALE=0.0` runs without crash, queue instability, telemetry instability, falls, or safety interventions in the 2s window.

For production default:
- Not yet. Disabling it changes pitch posture and roll range enough that longer-window and torso-orientation diagnostics are required first.

Recommended hybrid diagnostic baseline:

```text
DUCK_HYBRID_QVEL_XY_SCALE=0.0
DUCK_HYBRID_Z_FORCE_SCALE=1.0 or 0.5
DUCK_HYBRID_RP_QVEL_ZERO_SCALE=0.5
```

Use `rp=0.0` as a stress diagnostic, not a default.

## 9. Rollback Strategy

- Runtime rollback: `DUCK_DYNAMICS_MODE=legacy`.
- Hybrid RP rollback: `DUCK_HYBRID_RP_QVEL_ZERO_SCALE=1.0`.
- Code rollback: revert the Phase 2F commit only; Phase 2A-2E remain separable.

## 10. Recommendation For Phase 2G

Do not introduce PD balance yet.

Recommended next sprint:

1. Keep `legacy` unchanged.
2. Keep `hybrid` qvel/z/rp scales available.
3. Add torso quaternion overwrite scaling diagnostics behind a new hybrid-only flag.
4. Start with conservative matrix values: `qvel=0.0`, `z=1.0`, `rp=0.5`.
5. Use longer windows after the first torso-orientation diagnostic pass if no fall events occur.
