# Phase 2 Robotics Dynamics Plan

Phase 2 is planning-only until reviewed and approved. Do not change locomotion, ONNX policy behavior, MuJoCo dynamics, or HAL code as part of this document.

## 1. Current Locomotion / Dynamics Problem

The real MuJoCo backend currently preserves visible walking behavior through kinematic shortcuts rather than physically generated locomotion:

- `qpos` forcing:
  - `_stabilize_torso()` writes base orientation quaternion directly into `data.qpos[3:7]`.
  - It also writes base height directly through `data.qpos[2] = 0.15`.
- Torso stabilization hack:
  - Roll/pitch are clamped to small limits and written back as a synthetic upright quaternion.
  - Base roll/pitch angular velocities are zeroed with `data.qvel[3] = 0.0` and `data.qvel[4] = 0.0`.
- Fake base translation:
  - Commanded velocity is written into `data.qvel[0:2]`.
  - Base position is manually integrated with `data.qpos[0] += global_vx * 0.002` and `data.qpos[1] += global_vy * 0.002`.
- Friction/contact bypass:
  - Translation is produced even if foot contact/friction would not physically support the motion.
  - Contacts are observed for telemetry/policy input, but not required to generate base displacement.

Why this blocks sim-to-real:
- Real hardware cannot directly set floating-base position/orientation.
- Balance cannot be validated when torso attitude and height are forcibly corrected.
- Contact forces, friction, foot placement, actuator limits, and falls are hidden by the base override.
- Any policy tuned under this model may fail when the shortcut is removed because the dynamics it relied on never existed.

## 2. Current Control Flow

Current runtime after Phase 1:

```text
REST / WebSocket / Gemini / Voice / Follower
    ↓
QueueManager or set_desired_control()
    ↓
Desired linear/yaw command targets
    ↓
RealDuckSimulator physics thread
    ↓
50 Hz control update inside 500 Hz MuJoCo loop
    ↓
ONNX policy or waddle oscillator
    ↓
_stabilize_torso() kinematic base forcing
    ↓
mujoco.mj_step()
    ↓
double-buffered state publication
```

Important current components:

- ONNX policy:
  - `_apply_onnx_inference()` builds observations from IMU sensors, command targets, joint positions/velocities, previous actions, motor targets, contacts, and imitation phase.
  - It maps policy output to motor targets and writes `data.ctrl[:] = self.motor_targets`.
- Waddle oscillator:
  - `_apply_waddle_oscillator()` generates deterministic joint target oscillations when no ONNX policy is active.
  - It writes position targets directly into `data.ctrl[:]`.
- Command intent path:
  - `set_desired_control()` updates target linear velocity, lateral velocity, yaw rate, last command, and safety config.
  - It does not step physics.
- MuJoCo stepping loop:
  - `_physics_loop()` runs at 500 Hz with `SimulationClock`.
  - Every 10 ticks it updates smoothed command velocity and runs ONNX/waddle control.
  - Every tick it calls `_stabilize_torso()` before `mujoco.mj_step()`.
- Fake stabilization location:
  - `_stabilize_torso()` is the primary kinematic-cheating concentration point.
  - `reset()` also steps MuJoCo during reset settling, but that is a reset/init behavior, not locomotion.

## 3. Proposed Phase 2 Migration Strategy

No full rewrite. Phase 2 should introduce a parallel, feature-flagged dynamic control path and gradually remove kinematic shortcuts only when validation proves stability.

Recommended feature flag:

```text
DUCK_DYNAMICS_MODE=legacy|hybrid|dynamic
```

- `legacy`:
  - Current Phase 1 behavior.
  - Keeps kinematic base stabilization and translation.
  - Default until validation says otherwise.
- `hybrid`:
  - Joint targets still come from ONNX/waddle.
  - Base translation forcing is disabled first.
  - Torso height/orientation forcing is reduced or converted to soft control.
  - Used for incremental tuning and regression comparison.
- `dynamic`:
  - No base qpos translation.
  - No torso orientation overwrite.
  - Movement must come from actuator commands, MuJoCo contacts, and controller output.

Migration sequence:

1. Add instrumentation before behavior changes:
   - Base qpos/qvel writes count.
   - Torso correction magnitude.
   - Contact duty factor.
   - COM height, roll/pitch, fall reason, actuator command saturation.
2. Extract current fake stabilization into a named legacy module/function:
   - Keep behavior identical in `legacy`.
   - Make all direct base writes explicit and easy to disable.
3. Introduce controller interfaces:
   - `GaitController`: desired command + state -> joint targets.
   - `JointController`: joint targets + measured joints -> actuator commands.
   - `BalanceController`: IMU/contact state -> torso/hip/ankle corrections.
4. Add `hybrid` mode:
   - Disable direct x/y qpos integration.
   - Keep conservative torso fallback initially.
   - Measure whether contacts and joint targets create any physical displacement.
5. Convert torso correction from qpos overwrite to PD correction:
   - Use IMU roll/pitch and angular velocity.
   - Apply corrective joint/torque targets rather than floating-base writes.
6. Add `dynamic` mode:
   - Remove base qpos/qvel overrides.
   - Movement must emerge from contacts and actuator commands.
7. Only after dynamic mode is stable, consider HAL design.

Rollback strategy:
- `DUCK_DYNAMICS_MODE=legacy` must restore Phase 1 behavior.
- Keep legacy and dynamic paths side-by-side until dynamic passes standing, walking, turning, stopping, fall, and recovery validation.
- Do not delete legacy code in the first Phase 2 implementation PR.

## 4. Target Robotics Architecture

```text
Command Intent
    ↓
Policy / Gait Generator
    ↓
Joint Targets
    ↓
PD / Torque Controller
    ↓
MuJoCo Dynamics
    ↓
Contact Forces
    ↓
State Publication
```

Target behavior:
- Command intent remains high-level linear/yaw desire from Phase 1.
- ONNX policy or gait generator outputs target joint angles, not base pose.
- Joint-level controller converts targets into actuator commands.
- Balance controller modifies joint targets/torques based on IMU and contacts.
- MuJoCo generates base motion through dynamics and contact forces.
- State publication remains double-buffered and API-compatible.

## 5. Required Controllers

Torso PD stabilization:
- Inputs: roll, pitch, angular velocity, desired torso attitude.
- Outputs: corrective hip/ankle/torso-related joint commands or torque offsets.
- Must not write floating-base qpos/qvel.

Joint-level PD controller:
- Inputs: target joint angles, measured joint positions, measured joint velocities.
- Outputs: actuator commands compatible with the MuJoCo actuator model.
- Must enforce ctrlrange, rate limits, and saturation telemetry.

IMU feedback:
- Inputs: gyro, accelerometer, torso orientation/up vector.
- Used by torso PD and fall detection.
- Must tolerate unavailable sensor fields in mock/webcam modes.

Contact-aware balance logic:
- Inputs: left/right contact state, contact duration, foot velocity, base COM estimate.
- Outputs: stance/swing phase weighting and corrective ankle/hip gains.
- Should avoid applying aggressive corrections when both feet are airborne.

Fall detection:
- Keep existing safety thresholds as public contract.
- Add internal dynamic-mode diagnostics: roll/pitch rate, body height, no-contact duration, actuator saturation.

Recovery behavior:
- Phase 2 recovery target is safe stop/reset parity, not autonomous get-up.
- Reset may continue using MuJoCo reset/keyframe behavior.
- Walking commands while fallen remain rejected or trigger recovery through existing safety preflight.

## 6. Validation Strategy

Before any dynamics removal:
- Run Phase 1 validation set and confirm no command/runtime regression.
- Run pending environment validation:
  - `pytest -q tests/test_gemini_live_client.py` with `pytest-asyncio`.
  - `pytest -q tests/test_vision.py::test_detect_real_projected_capsule_cylinder` with `mujoco`.
  - Headless real simulator smoke from `docs/phase1_environment_validation_pending.md`.

Dynamic validation scenarios:
- Standing stability:
  - Real/headless simulator holds upright for a fixed duration without qpos torso forcing in `hybrid`/`dynamic`.
  - Roll/pitch/body height stay inside safety bounds.
- Forward motion without qpos translation:
  - Disable direct x/y qpos integration.
  - Verify any forward displacement comes from actuator/contact dynamics.
  - Record displacement, foot contacts, slips, falls, and actuator saturation.
- Turn-in-place:
  - Disable direct yaw/base angular-rate forcing in dynamic mode.
  - Verify yaw changes only through contact dynamics and actuator commands.
- Stop behavior:
  - Command stop from motion.
  - Verify target velocities decay, actuator commands settle, and body remains stable.
- Fall scenario:
  - Force tilt or unstable initial pose.
  - Verify safety classification and command rejection/recovery still work.
- Reset recovery:
  - Reset returns to stable state and republishes clean telemetry.
- Headless MuJoCo smoke:
  - Start real simulator with `DUCK_HEADLESS=true`.
  - Verify `/health`, `/state`, `/sensors/state`, `/command`, `/stop`, `/reset`.
- Regression comparison against Phase 1:
  - Compare API response schemas, command acceptance semantics, queue behavior, telemetry frequency, and safety interventions.
  - Movement metrics may differ in dynamic mode, but public contracts must remain compatible.

## 7. Risks

- Robot may stop walking once fake qpos translation is removed.
- Existing ONNX policy may depend on the stabilization hack and may not generate stable gait under real dynamics.
- Waddle oscillator may move joints visually without producing useful ground reaction forces.
- Gait may require retraining, reward redesign, or significant gain tuning.
- MuJoCo contact/friction parameters may be incorrect for real locomotion.
- PD gains may need iterative tuning and can destabilize the robot.
- Removing torso qpos forcing may expose model mass/inertia/actuator problems.
- Dynamic mode may be slower to validate because failures are physical and coupled.

## 8. Phase 2 Entry Blockers

Phase 2 implementation is blocked until:

- Gemini async validation is resolved or explicitly split into unit/integration tests:
  - `pytest-asyncio` installed or configured.
  - `pytest -q tests/test_gemini_live_client.py` result recorded.
- MuJoCo validation is resolved:
  - `mujoco` installed.
  - `pytest -q tests/test_vision.py::test_detect_real_projected_capsule_cylinder` result recorded.
- Real/headless simulator smoke is completed or formally tracked:
  - `DUCK_SIM_MODE=real DUCK_HEADLESS=true` startup works.
  - Health/state/sensor endpoints respond.
- Main branch remains clean.
- Pending `pending/vision-voice-runtime-changes` branch is not mixed into Phase 2 unless explicitly reviewed.
- No Phase 2 implementation starts until this plan is reviewed and approved.

## 9. Phase 2 Acceptance Criteria

### Legacy Mode

Pass criteria:
- Behavior matches Phase 1 runtime behavior.
- Existing Phase 1 validation tests still pass.
- Public API schemas do not change.
- Queue/control-plane behavior remains unchanged.
- Existing visible walking behavior is preserved.
- `DUCK_DYNAMICS_MODE=legacy` is the immediate rollback path.

Fail criteria:
- Any REST/WebSocket/Gemini/follower command ingress bypasses Phase 1 queue or approved desired-control interface.
- Existing Phase 1 command, telemetry, safety, or follower tests regress.
- Public API response schemas change without an explicit compatibility plan.
- Legacy visible walking behavior is degraded by Phase 2 code.

### Hybrid Mode

Pass criteria:
- Direct x/y base `qpos` translation can be disabled behind the feature flag.
- Torso forcing may remain initially, but its correction magnitude and frequency are measured.
- System does not crash, hang, deadlock, or starve the physics loop.
- State or diagnostic telemetry exposes:
  - displacement
  - roll/pitch
  - body height
  - contact duty factor
  - actuator saturation
  - fall reason
  - qpos/qvel override count
- If physical movement disappears after disabling x/y qpos integration, that is classified as an expected diagnostic result, not an implementation failure.

Fail criteria:
- Hybrid mode silently reintroduces base translation through another hidden qpos/qvel write.
- Missing telemetry makes it impossible to distinguish no-motion, slipping, falling, actuator saturation, or controller instability.
- Hybrid mode crashes or stalls under standing, stop, reset, or short command tests.
- Hybrid changes leak into `legacy` mode.

### Dynamic Mode

Pass criteria:
- No direct base x/y `qpos` integration.
- No torso orientation overwrite.
- No base height forcing.
- Base movement comes only from actuators, MuJoCo dynamics, and contact forces.
- Robot passes:
  - standing stability
  - stop behavior
  - reset recovery
  - fall detection
- Forward walking may initially be weak, slow, or unstable, but instability is measured and reported rather than hidden with new hacks.

Fail criteria:
- Any dynamic-mode code writes floating-base x/y position to create locomotion.
- Any dynamic-mode code overwrites torso orientation or base height to conceal instability.
- Fall detection or reset recovery stops working.
- New stabilization shortcuts reproduce the Phase 1 kinematic cheating under different names.

### Rollback

Pass criteria:
- Setting `DUCK_DYNAMICS_MODE=legacy` restores Phase 1 behavior immediately.
- First Phase 2 implementation PR keeps legacy mode present and tested.
- Dynamic/hybrid code paths are isolated behind the feature flag.

Fail criteria:
- Legacy mode is removed, renamed, or made unreachable during the first Phase 2 implementation PR.
- A failed hybrid/dynamic experiment requires code revert instead of config rollback.
- Phase 2 code changes alter Phase 1 behavior when `DUCK_DYNAMICS_MODE=legacy`.
