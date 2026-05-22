# Phase 2D Moving-Window Diagnostics Report

Phase 2D added a repeatable real/headless diagnostic harness and measured actual movement windows across legacy and hybrid qvel scales. No dynamics removal or controller behavior changes were made.

## 1. Changed Files Summary

- `scripts/diagnostics/phase2d_moving_window_diagnostics.py`
  - Runs a real/headless diagnostics matrix in isolated subprocesses.
  - Uses fresh process-level env config for each case.
  - Executes repeated reset -> wait stable -> forward command -> stop windows.
  - Collects command, queue, telemetry, state, contact, and internal dynamics diagnostics.

- `docs/phase2d_moving_window_diagnostics_results.json`
  - Machine-readable output from the Phase 2D diagnostics run.

- `docs/phase2d_moving_window_diagnostics_report.md`
  - Human-readable methodology, metrics, interpretation, risks, and Phase 2E recommendation.

## 2. Diagnostic Methodology

The harness executes each matrix case in a separate Python subprocess so import-time config constants are isolated per run:

```text
DUCK_SIM_MODE=real
DUCK_HEADLESS=true
DUCK_DYNAMICS_MODE=<case mode>
DUCK_HYBRID_QVEL_XY_SCALE=<case scale, if hybrid>
PYTHONPATH=<repo root>
```

Each subprocess starts the FastAPI app with `TestClient`, which starts `AppContext`, the real simulator, the queue manager, the physics thread, and the vision loop through the same lifecycle used by prior real/headless smoke tests.

The script samples `/state` during each command window and reads internal diagnostics from the AppContext-owned simulator and queue manager. Public schemas are not changed.

## 3. Command Profile

```text
repeats: 3 per case
reset before each repeat: yes
stable wait: 0.25 sec
command: walk_forward
speed: 0.25
turn/yaw_rate: 0.0
duration: 2.0 sec
sample period: 0.1 sec
stop after each window: yes
```

Command used:

```bash
PYTHONPATH=. .venv/bin/python scripts/diagnostics/phase2d_moving_window_diagnostics.py --output docs/phase2d_moving_window_diagnostics_results.json
```

## 4. Test Matrix

```text
legacy:
  DUCK_DYNAMICS_MODE=legacy

hybrid scale 1.0:
  DUCK_DYNAMICS_MODE=hybrid
  DUCK_HYBRID_QVEL_XY_SCALE=1.0

hybrid scale 0.5:
  DUCK_DYNAMICS_MODE=hybrid
  DUCK_HYBRID_QVEL_XY_SCALE=0.5

hybrid scale 0.0:
  DUCK_DYNAMICS_MODE=hybrid
  DUCK_HYBRID_QVEL_XY_SCALE=0.0
```

## 5. Metrics Table

| Case | Forward avg m | Lateral avg m | Yaw avg deg | qpos xy count | qvel xy count | qvel mag | Contact duty left/right/both | Actuator sat | Fall reason | Queue stable | Telemetry stable |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | ---: | --- | --- | --- |
| legacy | 0.562044 | 0.000755 | -359.997110 | 3905 | 3905 | 0.150000 | 0.978 / 0.953 / 0.932 | 0.970717 | None | true | true |
| hybrid scale 1.0 | 0.272117 | 0.000708 | -359.997287 | 0 | 3796 | 0.150000 | 0.978 / 0.952 / 0.930 | 0.965413 | None | true | true |
| hybrid scale 0.5 | 0.138740 | 0.001508 | -359.998619 | 0 | 3793 | 0.075000 | 1.000 / 0.980 / 0.980 | 0.959161 | None | true | true |
| hybrid scale 0.0 | 0.060296 | 0.012620 | -0.001387 | 0 | 0 | 0.000000 | 1.000 / 1.000 / 1.000 | 0.968600 | None | true | true |

Notes:
- The yaw values near `-360` are wrap artifacts from public yaw representation crossing `0/360`; the sampled yaw range remained near zero yaw drift.
- No case reported a fall reason.
- No case required safety intervention.
- Queue and telemetry stability remained true across all cases.

## 6. Interpretation

Legacy remains dominated by direct qpos x/y integration:

```text
legacy qpos_xy_integration_count: 3905
legacy forward displacement avg: 0.562044 m
```

Hybrid confirms qpos x/y integration remains disabled:

```text
hybrid qpos_xy_integration_count: 0 for all scales
```

Hybrid displacement scales with qvel forcing:

```text
scale 1.0 -> 0.272117 m forward avg
scale 0.5 -> 0.138740 m forward avg
scale 0.0 -> 0.060296 m forward avg
```

This means qvel x/y forcing still contributes strongly to hybrid movement, but even `scale=0.0` produces small nonzero displacement in the real/headless moving window.

## 7. Contact Dynamics Assessment

Contact dynamics create some useful displacement when qpos x/y integration and qvel x/y forcing are both disabled:

```text
hybrid scale 0.0:
  qpos_xy_integration_count: 0
  qvel_xy_forcing_count: 0
  forward displacement avg: 0.060296 m over 2 sec
```

That movement is much weaker than legacy and hybrid scale `1.0`, but it is not zero. It likely comes from the remaining actuator gait, contact interaction, torso stabilization, and z/roll-pitch stabilization constraints.

## 8. Can qvel Forcing Remain Disabled In Hybrid?

For diagnostics and future tuning, yes: `DUCK_HYBRID_QVEL_XY_SCALE=0.0` can remain available and does not crash, hang, or break telemetry/queue behavior.

For preserving visible locomotion, no: movement drops substantially compared with `scale=1.0` and legacy.

Recommended operating interpretation:
- `legacy`: compatibility and visible locomotion baseline.
- `hybrid scale 1.0`: qpos removal baseline with forced base velocity.
- `hybrid scale 0.5`: reduced forcing diagnostic midpoint.
- `hybrid scale 0.0`: contact/actuator-only diagnostic mode, not yet a locomotion-quality mode.

## 9. Risks

- Torso quaternion overwrite, z forcing, and qvel roll/pitch zeroing are still active, so hybrid is not yet true dynamics.
- `scale=0.0` movement may depend on remaining stabilization hacks and may not survive torso stabilization removal.
- Public yaw wrap makes naive yaw delta misleading near `0/360`; later diagnostics should unwrap yaw.
- The diagnostic script uses internal AppContext access for metrics; it is intentionally not a public API contract.

## 10. Recommendation For Phase 2E

Proceed with another diagnostics-first sprint before removing torso stabilization:

1. Keep `legacy` unchanged.
2. Keep `hybrid scale=0.0` available.
3. Add yaw-unwrapped metrics to the diagnostic harness.
4. Add per-window min/max actuator saturation and correction-rate metrics.
5. In hybrid only, evaluate reducing or disabling z forcing after collecting body-height/contact/fall evidence.
6. Do not remove torso quaternion overwrite until the z-forcing diagnostic is reviewed.
