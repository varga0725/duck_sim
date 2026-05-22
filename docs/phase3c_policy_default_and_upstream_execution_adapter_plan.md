# Phase 3C - Policy Default Alignment and Upstream Execution Adapter Plan

Phase 3C should prepare the repo to align policy execution with the vendored Open Duck Mini v2 playground without changing locomotion behavior yet. This phase is planning and validation groundwork only unless explicitly expanded.

## Current Mismatches To Address

- Local policy targets use hardcoded `DEFAULT_ACTUATOR` in `policy_contract.py`.
- The loaded MuJoCo model exposes `model.keyframe("home").ctrl`, which is the upstream/runtime source of truth.
- Phase 3A/3B validation can warn when these drift, but runtime still computes targets from the hardcoded default.
- Local policy execution reimplements upstream `mujoco_infer.py` semantics inside `RealDuckSimulator` instead of using a shared adapter.

## Proposed Direction

- Keep `DEFAULT_ACTUATOR` unchanged for now.
- Add a non-mutating comparison utility/report that prints:
  - `DEFAULT_ACTUATOR`,
  - loaded `home.ctrl`,
  - max absolute delta,
  - per-actuator deltas by `ACTUATOR_ORDER`,
  - whether values are within the Phase 3A tolerance.
- Design an upstream-aligned execution adapter interface, but do not switch runtime to it yet.

## Adapter Shape For Later Implementation

The future adapter should own only policy contract mechanics:

```text
MuJoCo model/data + desired command + policy state
-> observation vector
-> ONNX inference
-> motor target scaling/rate limiting
-> data.ctrl target vector
```

It must not own:

- bridge APIs,
- safety preflight,
- queue management,
- vision tracking,
- voice/Gemini routing,
- `LegacyDynamicsController`,
- MuJoCo XML or actuator model changes.

## Safety Rules

- No change to ONNX inference output interpretation in Phase 3C.
- No change to observation layout.
- No change to `DEFAULT_ACTUATOR`.
- No change to `LegacyDynamicsController`.
- No base qpos/qvel forcing changes.
- No dynamic mode behavior changes.

## Tests To Add When Implementing Phase 3C

- A pure report test for `DEFAULT_ACTUATOR` vs `home.ctrl` deltas.
- A test that the report is stable and names all 14 actuators in order.
- A test that missing MuJoCo/Open Duck optional dependencies skip cleanly.
- A test that the proposed adapter interface can be instantiated with mock policy state without stepping MuJoCo.

## Acceptance Criteria

- Engineers can see exactly whether policy defaults drift from the loaded upstream model.
- The future adapter boundary is documented before implementation.
- No runtime locomotion behavior changes occur in this phase.
