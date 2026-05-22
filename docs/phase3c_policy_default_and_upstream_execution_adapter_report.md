# Phase 3C - Policy Default Alignment and Upstream Execution Adapter Report

Phase 3C implements validation/planning groundwork only. It does not change locomotion behavior, ONNX inference, observation layout, MuJoCo XML, actuator model, HAL, dynamic mode behavior, `LegacyDynamicsController`, or runtime policy execution.

## Added

- `duck_agent_sim/simulator/policy_default_report.py`
  - Compares hardcoded `DEFAULT_ACTUATOR` against a loaded `home.ctrl` vector.
  - Reports max absolute delta and per-actuator deltas by actuator name/order.
- `duck_agent_sim/simulator/upstream_policy_adapter.py`
  - Adds a non-runtime adapter boundary scaffold for future upstream-aligned policy execution.
  - Does not run ONNX, build observations, write `data.ctrl`, or step MuJoCo.
- `tests/test_phase3c_policy_default_alignment.py`
  - Covers exact matches, per-actuator drift, stable report dict shape, invalid shape handling, optional MuJoCo dependency skipping, and adapter scaffold instantiation.

## Verification

Executed:

```bash
pytest -q tests/test_phase3c_policy_default_alignment.py
```

Result:

```text
5 passed, 1 skipped
```

Executed broader check:

```bash
pytest -q \
  tests/test_phase3c_policy_default_alignment.py \
  tests/test_phase3b_command_clamp.py \
  tests/test_policy_contract.py \
  tests/test_onnx.py \
  tests/test_policy_contract_validator.py \
  tests/test_follower.py
```

Result:

```text
40 passed, 4 skipped
```

## Remaining Work

- Decide whether a later phase should derive policy defaults from `model.keyframe("home").ctrl`.
- Move observation construction and action scaling behind the adapter only after explicit approval.
- Keep `LegacyDynamicsController` unchanged until upstream policy execution can be validated without simulator-only base forcing.
