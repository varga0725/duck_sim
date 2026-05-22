# Phase 2H Long-Window Reduced-Hack Diagnostics Report

Phase 2H extends the existing moving-window diagnostic harness to 5-second command windows and 2-second stop/recovery windows. It does not change locomotion control behavior, ONNX/waddle behavior, MuJoCo XML, actuator model, HAL, public API schemas, command queue semantics, dynamic mode, or legacy mode.

## 1. Changed Files Summary

- `scripts/diagnostics/phase2d_moving_window_diagnostics.py`
  - Added `--matrix phase2h`.
  - Added the Phase 2H legacy/conservative/reduced/stress matrix.
  - Added `--stop-recovery-sec`.
  - Records post-stop recovery samples after every run.
  - Adds roll, pitch, and body-height drift metrics.
  - Adds stop/recovery stability, contact, fall, and telemetry metrics.

- `docs/phase2h_long_window_reduced_hack_diagnostics_results.json`
  - Machine-readable 5s + 2s recovery real/headless results.

## 2. Diagnostic Methodology

Command:

```bash
PYTHONPATH=. .venv/bin/python scripts/diagnostics/phase2d_moving_window_diagnostics.py \
  --matrix phase2h \
  --duration-sec 5.0 \
  --stop-recovery-sec 2.0 \
  --output docs/phase2h_long_window_reduced_hack_diagnostics_results.json
```

Profile:

```text
repeats: 3 per case
moving window: 5.0 sec
stop/recovery window: 2.0 sec
stable wait after reset: 0.25 sec
sample period: 0.1 sec
command: walk_forward
speed: 0.25
headless real simulator
```

Every repeat performs:

```text
reset
wait stable
walk_forward for 5s
stop
sample recovery for 2s
collect state, queue, telemetry, contact, dynamics diagnostics
```

## 3. Matrix Definition

```text
legacy baseline

hybrid conservative:
  qvel=0.0
  z=1.0
  rp=1.0
  torso=1.0

hybrid reduced:
  qvel=0.0
  z=0.5
  rp=0.5
  torso=0.5

hybrid stress:
  qvel=0.0
  z=0.5
  rp=0.0
  torso=0.0
```

## 4. 5s Moving-Window Results

| Case | Forward avg m | Lateral avg m | Yaw unwrapped avg deg |
| --- | ---: | ---: | ---: |
| legacy | 0.584893 | 0.010256 | 0.001176 |
| hybrid conservative | 0.102155 | 0.057861 | 0.000464 |
| hybrid reduced | 0.103802 | 0.041817 | 0.000830 |
| hybrid stress | 0.004851 | 0.005596 | 0.366141 |

Interpretation:
- Legacy still produces the strongest forward displacement because direct x/y qpos integration remains active.
- Conservative and reduced hybrid both produce about 0.10 m forward motion over 5s without x/y qpos integration or x/y qvel forcing.
- The reduced baseline slightly improves forward displacement and reduces lateral drift versus conservative in this run.
- The stress configuration nearly eliminates useful forward movement and introduces measurable yaw drift.

## 5. Stop/Recovery Results

| Case | Recovery stable | Recovery falls | Recovery roll avg/min/max deg | Recovery pitch avg/min/max deg | Recovery contact both |
| --- | --- | ---: | --- | --- | ---: |
| legacy | true | 0 | -3.087 / -3.463 / -2.498 | 4.001 / 4.001 / 4.001 | 1.000 |
| hybrid conservative | true | 0 | -3.364 / -3.614 / -2.953 | 4.001 / 4.001 / 4.001 | 1.000 |
| hybrid reduced | true | 0 | -3.638 / -3.786 / -3.418 | 4.004 / 4.004 / 4.004 | 1.000 |
| hybrid stress | true | 0 | -4.096 / -4.109 / -4.064 | 5.601 / 5.549 / 5.667 | 1.000 |

Stop/recovery remained stable for all cases in this diagnostic window. The stress case recovers without falling, but holds a worse pitch posture after stop.

## 6. Reduced-Hack Baseline Comparison

| Metric | Conservative | Reduced | Stress |
| --- | ---: | ---: | ---: |
| qpos xy integration count | 0 | 0 | 0 |
| qvel xy forcing count | 0 | 0 | 0 |
| z correction sum | 0.696300 | 0.657309 | 0.478753 |
| RP damping sum | 397.900645 | 309.676349 | 0.000000 |
| torso correction sum | 0.234076 | 0.322525 | 0.000000 |
| forward displacement avg m | 0.102155 | 0.103802 | 0.004851 |
| recovery stable | true | true | true |

The reduced baseline is the best next diagnostic configuration: it cuts z and roll/pitch damping while retaining enough torso correction to avoid the stress-mode yaw/pitch degradation.

## 7. Drift And Stability Analysis

| Case | Roll drift avg deg | Pitch drift avg deg | Height drift avg m |
| --- | ---: | ---: | ---: |
| legacy | -3.183 | 6.563 | -0.0000369 |
| hybrid conservative | -4.080 | 5.760 | -0.0000297 |
| hybrid reduced | -5.163 | 5.276 | -0.0000541 |
| hybrid stress | -4.770 | 1.329 | -0.0000024 |

Notes:
- Reduced hybrid has larger roll drift than conservative but lower pitch drift.
- Stress has low pitch drift only because it starts and stays in a more forward-leaning pitch envelope.
- No measured drift caused a fall, command failure, queue instability, or telemetry instability.

## 8. Contact And Height Analysis

| Case | Body height avg/min/max m | Contact left/right/both | No-contact avg sec |
| --- | --- | --- | ---: |
| legacy | 0.150060 / 0.150022 / 0.150119 | 0.992 / 0.982 / 0.974 | 0.0 |
| hybrid conservative | 0.150063 / 0.150032 / 0.150121 | 1.000 / 1.000 / 1.000 | 0.0 |
| hybrid reduced | 0.150117 / 0.150060 / 0.150228 | 1.000 / 1.000 / 1.000 | 0.0 |
| hybrid stress | 0.150073 / 0.149978 / 0.150124 | 0.992 / 0.991 / 0.986 | 0.0 |

The reduced baseline maintains continuous contact and bounded height over 5s. Stress shows slightly weaker contact quality but still no no-contact interval in the sampled window.

## 9. Actuator Saturation Analysis

| Case | Actuator saturation avg/min/max |
| --- | --- |
| legacy | 0.949873 / 0.917828 / 0.996479 |
| hybrid conservative | 0.950368 / 0.919672 / 0.984518 |
| hybrid reduced | 0.950532 / 0.919251 / 0.980657 |
| hybrid stress | 0.953065 / 0.918730 / 0.993741 |

Reduced hybrid does not increase actuator saturation relative to conservative. Stress raises average and max saturation slightly while producing much weaker movement.

## 10. Fall And Safety Events

```text
fall_event_count: 0 for all cases
safety_interventions: 0 for all cases
fall_reason: None for all cases
queue_stable: true for all cases
telemetry_stable: true for all cases
stop_recovery_stable: true for all cases
```

## 11. Is Reduced-Hack Hybrid Stable Enough For Controller Planning?

Yes, for planning and scaffold design.

The reduced-hack baseline:
- runs 5s without crash or hang
- keeps queue and telemetry stable
- produces no fall or safety intervention
- keeps qpos x/y integration disabled
- keeps qvel x/y forcing disabled
- maintains contact and bounded height
- completes stop/recovery without falling

It is not yet a production walking controller. Forward motion remains weak and posture drift remains visible. Those are design inputs for Phase 2I, not failures.

## 12. Rollback Strategy

- Runtime rollback: `DUCK_DYNAMICS_MODE=legacy`.
- Diagnostic baseline rollback:

```text
DUCK_HYBRID_Z_FORCE_SCALE=1.0
DUCK_HYBRID_RP_QVEL_ZERO_SCALE=1.0
DUCK_HYBRID_TORSO_ORIENTATION_SCALE=1.0
```

- Code rollback: revert the Phase 2H commit only; Phase 2A-2G remain separable.

## 13. Recommendation For Phase 2I

Do not change `dynamic` mode yet.

Recommended next sprint:

1. Keep `legacy` unchanged.
2. Keep the reduced-hack hybrid baseline available:

```text
DUCK_HYBRID_QVEL_XY_SCALE=0.0
DUCK_HYBRID_Z_FORCE_SCALE=0.5
DUCK_HYBRID_RP_QVEL_ZERO_SCALE=0.5
DUCK_HYBRID_TORSO_ORIENTATION_SCALE=0.5
```

3. Add a controller-planning document or scaffold for measured balance objectives before implementing torque-level PD.
4. Use the Phase 2H results as the baseline acceptance target for any future balance controller: it must improve posture/yaw/contact without reintroducing qpos x/y or qvel x/y fake movement.
