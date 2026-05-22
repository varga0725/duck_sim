# Phase 3A - Upstream Policy Contract Validation Plan

Phase 3A adds validation around the current ONNX, MuJoCo, policy contract, and command-ingress path without changing locomotion behavior.

## Goals

- Validate the bundled ONNX model contract: input/output names, shapes, and dtypes.
- Validate generated observation vectors: length, dtype, finite numeric values, and command range.
- Validate MuJoCo actuator mapping against `policy_contract.py`: actuator count, order, `home.ctrl`, and ctrl ranges.
- Validate control cadence: `0.002` second MuJoCo timestep, decimation `10`, physics rate `500 Hz`, policy rate `50 Hz`.
- Validate command clamp consistency and record known mismatch risks, especially follower commands that can exceed policy `linear_x` limits.
- Compare local constants against the vendored Open Duck Playground reference files.

## Non-Goals

- No custom PD/balance controller.
- No torque-level controller, custom gait controller, HAL, MuJoCo XML change, actuator model change, dynamic-mode behavior change, observation-layout change, or ONNX inference behavior change.
- No removal or modification of `LegacyDynamicsController`.
- No automatic runtime blocking in this phase; validation reports drift but does not alter simulator execution.

## Implementation

- Add `duck_agent_sim/simulator/policy_contract_validator.py` with pure validation helpers that return structured reports.
- Add tests in `tests/test_policy_contract_validator.py` for ONNX, observation, MuJoCo actuator mapping, cadence, upstream constants, and command range checks.
- Keep MuJoCo-dependent tests skipped when MuJoCo is unavailable.
- Document findings and verification in `docs/phase3a_upstream_policy_contract_validation_report.md`.

## Acceptance Criteria

- The bundled ONNX model validates as `obs [1, 101] -> continuous_actions [1, 14]`, `tensor(float)`.
- Valid observation vectors pass; wrong shape, wrong dtype, NaN, inf, and out-of-range commands fail validation.
- Vendored Open Duck constants match local `ACTION_SCALE`, `DOF_VEL_SCALE`, `SIM_DT`, and `DECIMATION`.
- Real MuJoCo actuator contract validates when optional MuJoCo dependencies are installed.
- Tests explicitly capture that REST command mapping clamps to policy limits while follower-style direct desired control can exceed `linear_x` limits today.
