# Phase 3A - Upstream Policy Contract Validation Report

Phase 3A added validation-only groundwork for Open Duck Mini v2 upstream locomotion alignment. It does not change locomotion behavior, ONNX inference behavior, observation layout, MuJoCo XML, actuator model, HAL, dynamic mode behavior, or `LegacyDynamicsController`.

## Changed Files

- `duck_agent_sim/simulator/policy_contract_validator.py`
  - Adds structured validation reports for ONNX model metadata, observation vectors, command ranges, MuJoCo actuator mapping, control cadence, and vendored upstream constants.
- `tests/test_policy_contract_validator.py`
  - Adds unit coverage for valid and invalid contracts.
  - Keeps MuJoCo-backed checks optional with `pytest.mark.skipif`.
- `docs/phase3a_upstream_policy_contract_validation_plan.md`
  - Captures Phase 3A goals, non-goals, implementation shape, and acceptance criteria.
- `docs/phase3a_upstream_policy_contract_validation_report.md`
  - Records this validation sprint summary.

## Findings Captured By Validation

- Bundled ONNX policy contract is expected to be:
  - input: `obs [1, 101]`, `tensor(float)`
  - output: `continuous_actions [1, 14]`, `tensor(float)`
- Observation validation now detects:
  - wrong vector length,
  - wrong dtype,
  - NaN/inf values,
  - out-of-range command values in the command slice.
- Control cadence validation now checks:
  - `SIM_DT = 0.002`,
  - `DECIMATION = 10`,
  - `500 Hz` physics rate,
  - `50 Hz` policy rate.
- Command validation confirms REST command mapping clamps through `map_command()`.
- Command validation also captures the known follower risk: direct follower-style desired control can produce `linear_x = 0.3`, above the policy limit `0.15`. This phase reports that mismatch only; it does not clamp or change follower behavior.

## Verification

Executed:

```bash
pytest -q tests/test_policy_contract_validator.py
```

Result:

```text
13 passed, 1 skipped
```

Executed broader contract checks:

```bash
pytest -q tests/test_policy_contract.py tests/test_onnx.py tests/test_policy_contract_validator.py
```

Result:

```text
23 passed, 3 skipped
```

MuJoCo-specific actuator validation runs only when MuJoCo and the vendored Open Duck Playground imports are available.

## Remaining Alignment Work

- Decide in a later phase whether follower commands should be clamped at the follower boundary or simulator `set_desired_control()` boundary.
- Decide in a later phase whether policy defaults should be derived from `model.keyframe("home").ctrl` instead of hardcoded `DEFAULT_ACTUATOR`.
- Decide in a later phase whether local policy execution should wrap vendored upstream `MjInfer` semantics directly.
