# Phase 3B - Command Clamp Consistency and Contract Warning Plan

Phase 3B addresses the safest real mismatch found by Phase 3A: producers that bypass `map_command()` can send desired controls outside the ONNX policy command range. This phase also adds non-blocking policy contract warnings at startup. It must not change locomotion internals, ONNX inference, observation layout, MuJoCo XML, actuator model, HAL, dynamic mode behavior, or `LegacyDynamicsController`.

## Exact Phase 3A Mismatch

- REST `/command` goes through `map_command()` and is clamped to `POLICY_COMMAND_LIMITS`.
- `VisionGuidedFollower` publishes directly through `active_simulator.set_desired_control()`.
- Follower defaults can produce `linear_x = 0.3`, while the policy limit is `linear_x <= 0.15`.
- Gemini/voice direct motion uses `DirectController` defaults through `/command`, so it is clamped today; however Gemini tool `speed`, `turn`, and `duration_sec` args are currently ignored by `DirectController`.

## Proposed Clamp Location

- Clamp at the simulator/control boundary inside both simulator implementations' `set_desired_control()` methods.
- Rationale: every current and future direct producer is protected, including follower, scripts, tests, or future AI tools that publish `ControlIntent` directly.
- Preserve public command semantics as much as possible: callers may request higher desired control, but the simulator stores and executes the policy-safe clamped values.
- Do not change `map_command()` behavior; it remains the REST command clamp.

## Public Behavior Risk

- Follower forward speed may become slower because `linear_x` is capped at `0.15` instead of its current default `0.3`.
- Search yaw remains within current `yaw` policy limits and should not change.
- Public REST `/command` behavior should not change because it is already clamped.
- Gemini/voice direct move behavior should not change in this phase because it already routes through `/command` defaults.

## Implementation Tests

- Add tests that direct `set_desired_control(ControlIntent(linear_x=0.3, ...))` stores/publishes a clamped `linear_x = 0.15`.
- Add equivalent tests for both mock and real simulator boundary logic without requiring a live MuJoCo loop where possible.
- Update follower validation expectations so follower-produced desired controls are no longer outside policy limits after boundary clamp.
- Add tests for a pure helper if introduced, covering `linear_x`, `linear_y`, and `yaw` clamping.
- Keep existing REST command clamp tests.

## Non-Blocking Startup Contract Warnings

- Add optional startup-time validation in `RealDuckSimulator._initialize_mujoco()` after ONNX session and MuJoCo model/mapping are available.
- Use `policy_contract_validator` to check ONNX metadata, MuJoCo actuator mapping, and cadence.
- Log warnings only; do not raise, fail startup, change controls, or disable ONNX.
- If optional validation itself errors because dependencies or metadata are unavailable, log a warning and continue.

## Warning-Only Items

- MuJoCo `home.ctrl` vs `DEFAULT_ACTUATOR` remains warning-only.
- Upstream reference comparison remains warning-only.
- Gemini tool argument mismatch remains documented only; do not map tool args into `DirectController` in Phase 3B.
- Policy default derivation from `home.ctrl` remains planning-only; do not change `DEFAULT_ACTUATOR`.

## Rollback Strategy

- Revert the boundary clamp helper/import and the two `set_desired_control()` call-site changes to restore previous direct desired-control behavior.
- Remove startup warning calls if they produce noisy logs or dependency-specific issues.
- Tests added in this phase should make rollback obvious by isolating clamp behavior and warning-only behavior from locomotion execution.

## Must Not Change

- No ONNX inference behavior or model loading semantics beyond warnings.
- No observation vector layout or values.
- No MuJoCo XML, actuator model, or motor target mapping.
- No `LegacyDynamicsController` changes.
- No custom PD, torque-level, gait-controller, HAL, or dynamic-mode behavior changes.
