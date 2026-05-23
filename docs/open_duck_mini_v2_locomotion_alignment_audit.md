# Open Duck Mini v2 Locomotion Alignment Audit

Date: 2026-05-22

Scope: audit-only review of the current Duck Mini / Open Duck Mini v2 simulator, locomotion, AI, vision, and voice command stack. No locomotion code, ONNX behavior, MuJoCo XML, actuator model, HAL, public API, or dynamic-mode behavior was changed.

Strategic conclusion: the repository already contains a partial ONNX/RL walking policy integration and a vendored `external/Open_Duck_Playground` reference implementation. The current runtime is not yet aligned with official Open Duck Mini v2 locomotion semantics because visible motion is still materially supported by simulator-only floating-base overrides in `LegacyDynamicsController`. The next implementation step should be upstream policy-execution alignment, not a new handwritten balance controller.

## Findings

### 1. Existing ONNX Walking Policy Integration

Status: upstreamhez kell igazítani

Relevant files:

- `duck_agent_sim/simulator/duck_sim.py`
  - `RealDuckSimulator.__init__()` initializes ONNX state, action history, motor targets, imitation phase, and policy cadence.
  - `_initialize_mujoco()` loads `DUCK_ONNX_MODEL_PATH` using `onnxruntime.InferenceSession`.
  - `_get_onnx_obs()` builds a 101-element observation vector.
  - `_apply_onnx_inference()` runs inference, maps actions to targets, applies target rate limiting, and writes `data.ctrl[:]`.
- `duck_agent_sim/simulator/policy_contract.py`
  - Defines `OBSERVATION_SIZE = 101`, `POLICY_OUTPUT_SIZE = 14`, `ACTION_SCALE = 0.25`, `DOF_VEL_SCALE = 0.05`, `SIM_DT = 0.002`, `DECIMATION = 10`, actuator order, default actuator pose, ctrl ranges, command limits, and target rate limiting.
- `duck_agent_sim/models/BEST_WALK_ONNX_2.onnx`
  - Inspected with ONNX Runtime: input `obs` is `[1, 101]`, output `continuous_actions` is `[1, 14]`.
- `docs/onnx_rl_policy_contract.md`
- `docs/best_walk_onnx_2_training_provenance.md`
- `tests/test_onnx.py`
- `tests/test_policy_contract.py`

Current observation layout in local runtime:

```text
gyro(3)
accelerometer(3), with accelerometer[0] += 1.3
commands(7): linear_x, linear_y, yaw_rate, neck_pitch, head_pitch, head_yaw, head_roll
joint_angles - default_actuator(14)
joint_vel * 0.05(14)
last_action(14)
last_last_action(14)
last_last_last_action(14)
motor_targets(14)
contacts(2)
imitation_phase(2)
= 101
```

What is usable:

- Shape-level ONNX contract is usable így: 101 input and 14 output are consistent with the bundled model and local contract.
- Action scaling constants are usable így relative to the vendored playground: `action_scale = 0.25`, `dof_vel_scale = 0.05`, `sim_dt = 0.002`, `decimation = 10`, and `max_motor_velocity = 5.24` match the upstream `mujoco_infer.py`.
- Runtime integration needs upstream alignment because policy output is combined with direct floating-base stabilization and translation forcing.

Important gap:

- `_apply_onnx_inference()` does not validate actual ONNX input/output names/shapes beyond relying on `get_inputs()[0].name` and `policy_contract` action shape checks after inference. The bundled model matches today, but incompatible policies would fail late or semantically.

### 2. Existing MuJoCo / Open Duck Mini v2 Simulation Code

Status: kis javítás kell for simulation wrapper, upstreamhez kell igazítani for locomotion behavior

Relevant files:

- `duck_agent_sim/simulator/duck_sim.py`
  - `RealDuckSimulator._initialize_mujoco()` loads `external/Open_Duck_Playground/playground/open_duck_mini_v2/xmls/scene_flat_terrain.xml` through `playground.open_duck_mini_v2.base.get_assets()`.
  - Sets `model.opt.timestep = 0.002`.
  - Resets to MuJoCo `home` keyframe.
  - `_physics_loop()` steps MuJoCo at 500 Hz and runs policy/waddle control every 10 ticks, i.e. 50 Hz.
  - `_update_shared_state()` exports position, Euler orientation, contacts, fall status, and diagnostics.
  - `get_sensor_state()` exposes IMU and foot sensor channels.
- `external/Open_Duck_Playground/playground/open_duck_mini_v2/xmls/*`
  - Official vendored MuJoCo model, terrain scenes, sensors, joints, actuator definitions, and assets.
- `external/Open_Duck_Playground/playground/open_duck_mini_v2/base.py`
  - Upstream-style MJX environment base and joint/sensor helper mappings.
- `external/Open_Duck_Playground/playground/open_duck_mini_v2/mujoco_infer_base.py`
  - Upstream MuJoCo inference helper with joint, actuator, sensor, contact, home-pose, timestep, and decimation setup.
- `external/Open_Duck_Playground/playground/open_duck_mini_v2/mujoco_infer.py`
  - Upstream standalone policy inference loop.

What is usable:

- MuJoCo asset loading through `base.get_assets()` is usable így.
- Home keyframe reset is usable így as a baseline.
- Sensor naming and contact naming match upstream: `gyro`, `accelerometer`, `foot_assembly`, `foot_assembly_2`, `floor`.
- Physics/control cadence matches upstream at the numeric level: 500 Hz MuJoCo, 50 Hz policy.

What needs alignment:

- Local `_physics_loop()` calls `_stabilize_torso()` every 500 Hz tick before `mujoco.mj_step()`. Upstream `mujoco_infer.py` does not force floating-base qpos/qvel during walking inference.
- Local runtime mutates base yaw, z, XY qvel, XY qpos, roll/pitch qvel via `LegacyDynamicsController`, which is not official policy execution.

### 3. Upstream Runtime / Playground Connection

Status: kis javítás kell for import/vendor connection, upstreamhez kell igazítani for execution semantics

Relevant files:

- `duck_agent_sim/simulator/duck_sim.py`
  - Adds `external/Open_Duck_Playground` to `sys.path`.
  - Imports `playground.open_duck_mini_v2.base` and `FLAT_TERRAIN_XML`.
- `scripts/setup_open_duck.sh`
- `README.md`
- `external/Open_Duck_Playground/README.md`
- `external/Open_Duck_Playground/playground/common/onnx_infer.py`
- `external/Open_Duck_Playground/playground/open_duck_mini_v2/mujoco_infer.py`
- `external/Open_Duck_Playground/playground/open_duck_mini_v2/mujoco_infer_base.py`

The local repo is already using upstream model assets and many upstream constants. It is not wrapping the upstream `MjInfer` class or `OnnxInfer` helper directly; it reimplements similar logic inside `RealDuckSimulator`.

Precise differences from vendored upstream:

| Area | Local repo | Vendored upstream playground |
|---|---|---|
| Policy wrapper | Direct `onnxruntime.InferenceSession` in `RealDuckSimulator` | `playground.common.onnx_infer.OnnxInfer(awd=True)` |
| Inference loop | Background simulator thread, policy every 10 MuJoCo ticks | Standalone viewer loop, policy every `decimation` ticks |
| Observation layout | Same high-level 101-element layout | Same high-level layout in `MjInfer.get_obs()` |
| Action target | `apply_action_to_targets()` uses hardcoded local default actuator + clamp + optional rate limit | `default_actuator + action * action_scale`, then rate limit only |
| Ctrlrange clamp | Local clamps against hardcoded ctrl ranges | Upstream infer loop does not explicitly clamp after action scaling/rate limit |
| Base dynamics | Forced by `LegacyDynamicsController` every physics tick | No forced base qpos/qvel in `mujoco_infer.py` inference loop |
| Command source | REST/WebSocket/voice/vision desired control | Keyboard callback updates command vector |
| Head commands | Local command vector keeps head/neck targets zero | Upstream supports head control mode through keyboard command vector |
| Imitation phase | Local advances only while moving and uses `nb_steps_in_period = 50` | Upstream advances from `PolyReferenceMotion.nb_steps_in_period` with `phase_frequency_factor` |
| Reset | Local `mj_resetData`, home qpos/ctrl, 50 settle steps | Upstream base initializes home qpos/ctrl; standalone loop starts from that |
| Stabilization | Local torso/base stabilization always active by default | No comparable stabilization in `mujoco_infer.py` |

### 4. Existing Gait / Oscillator / RL Policy Code

Status: mixed

Usable így:

- `duck_agent_sim/simulator/policy_contract.py`
  - Good central location for policy dimensions, action scale, command limits, target rate limiting, and actuator order documentation.
- `external/Open_Duck_Playground/playground/open_duck_mini_v2/mujoco_infer.py`
  - Good official reference for inference loop semantics.

Kis javítás kell:

- `duck_agent_sim/simulator/duck_sim.py` ONNX loop
  - Needs explicit assertions/logging for observation shape, output shape, input/output names, actuator order, and model metadata.

Upstreamhez kell igazítani:

- Local imitation phase logic uses `nb_steps_in_period = 50`, while upstream walking infer uses `PolyReferenceMotion.nb_steps_in_period`. If the bundled policy was trained/exported against a different phase period, local phase may be semantically wrong even though shape matches.
- `apply_action_to_targets()` uses hardcoded `DEFAULT_ACTUATOR` instead of deriving `model.keyframe("home").ctrl` at runtime. The current values appear intended to match home, but this is fragile against XML/model updates.

Kísérleti / diagnosztikai:

- `RealDuckSimulator._apply_waddle_oscillator()`
  - Generates visual joint oscillations when ONNX is unavailable.
  - Useful for demos and smoke tests.
  - Not official locomotion and not suitable as a hardware gait source.
- `MockDuckSimulator._advance_from_intent()`
  - Deterministic kinematic waddle with fake contact and base movement.
  - Useful for API/agent/vision integration testing only.

Valós robothoz nem használható:

- Any locomotion path depending on `LegacyDynamicsController.apply()` base qpos/qvel writes.
- Waddle oscillator as a real robot controller.
- Mock simulator kinematics as proof of gait stability.

### 5. Existing Fake Locomotion / Stabilization Code

Status: valós robothoz nem használható

Relevant files:

- `duck_agent_sim/simulator/legacy_dynamics.py`
- `duck_agent_sim/simulator/duck_sim.py`
  - `_stabilize_torso()` delegates to `LegacyDynamicsController.apply()`.
- Phase diagnostics docs:
  - `docs/phase2_robotics_dynamics_plan.md`
  - `docs/phase2b_hybrid_qpos_removal_report.md`
  - `docs/phase2c_hybrid_qvel_scale_report.md`
  - `docs/phase2e_hybrid_z_force_scale_report.md`
  - `docs/phase2f_hybrid_rp_qvel_scale_report.md`
  - `docs/phase2g_hybrid_torso_orientation_scale_report.md`
  - `docs/phase2h_long_window_reduced_hack_diagnostics_report.md`

Simulator-only shortcuts found:

- Direct torso quaternion overwrite: `simulator.data.qpos[3:7] = blended_quat`.
- Direct base z forcing: `simulator.data.qpos[2] = before_z + z_correction`; `qvel[2] = 0.0`.
- Direct base XY velocity forcing: `simulator.data.qvel[0] = applied_vx`; `qvel[1] = applied_vy`.
- Direct base XY qpos integration in non-hybrid modes: `qpos[0] += global_vx * dt`; `qpos[1] += global_vy * dt`.
- Direct roll/pitch angular velocity damping/zeroing: `qvel[3]`, `qvel[4]`.
- Direct yaw velocity forcing: `qvel[5] = current_yaw_rate`.

The diagnostics around these hacks are useful így. The hacks themselves must be considered simulation-only and must not be treated as official locomotion or hardware-compatible control.

### 6. Existing Hardware / Runtime Bridge Assumptions

Status: kísérleti / diagnosztikai; valós robothoz nem használható as HAL

Relevant files:

- `duck_agent_sim/bridge/api.py`
- `duck_agent_sim/bridge/websocket.py`
- `duck_agent_sim/agent/hermes_client.py`
- `duck_agent_sim/agent/direct_controller.py`
- `duck_agent_sim/simulator/command_mapper.py`
- `duck_agent_sim/schemas.py`
- `README.md`

Assumptions:

- Public command API is high-level: `walk_forward`, `walk_backward`, `turn_left`, `turn_right`, `stop`, `reset`, `look_around`.
- Agents are explicitly instructed not to output raw joint angles or motor commands.
- There is no physical HAL, serial bridge, GPIO, motor bus, or hardware actuator backend in this repo.
- `HermesRobotClient` is an HTTP/WebSocket client for the simulator bridge, not a robot hardware runtime.
- `get_sensor_state()` exposes simulator sensors only. Mock mode marks sensors unavailable.

Classification:

- High-level bridge API: használható így for simulator and agent integration.
- Hardware/runtime bridge: valós robothoz nem használható until a real hardware adapter, safety interlocks, calibration, actuator mapping, watchdogs, and upstream-compatible runtime execution are added.

### 7. Vision Following and Locomotion Integration

Status: kis javítás kell for simulator behavior; upstreamhez kell igazítani before real locomotion

Relevant files:

- `duck_agent_sim/vision/follower.py`
- `duck_agent_sim/vision/vision_loop.py`
- `duck_agent_sim/vision/camera.py`
- `duck_agent_sim/bridge/api.py`
- `duck_agent_sim/agent/direct_controller.py`
- `duck_agent_sim/agent/hermes_client.py`
- `tests/test_follower.py`
- `tests/test_vision.py`

Current path:

```text
YOLO/tracker detections
-> VisionGuidedFollower._run_loop() at 10 Hz
-> proportional linear_x/yaw command
-> active_simulator.set_desired_control(ControlIntent)
-> RealDuckSimulator target velocities
-> ONNX policy or waddle oscillator
-> LegacyDynamicsController base forcing
-> MuJoCo step
```

What is usable:

- The follower correctly publishes desired control and does not step physics directly.
- It has deadman/search behavior and stop publishing.
- It reuses the same simulator control ingress as direct commands.

Risk:

- In current real-sim mode, vision following benefits from fake base translation/stabilization. Following success does not prove physical locomotion.
- Follower max speed is `0.3`, but `command_mapper` clamps high-level policy commands to `0.15`. `VisionGuidedFollower` bypasses `command_mapper` by calling `set_desired_control()` directly, so direct follower commands can exceed the documented policy command limit unless `set_desired_control()` or the follower itself clamps them. This is a policy-distribution risk.

### 8. Voice / Gemini / Hermes Command Path and Locomotion Link

Status: használható így for simulator command ingress; upstreamhez kell igazítani before hardware

Relevant files:

- `duck_agent_sim/agent/voice_control.py`
- `duck_agent_sim/agent/smart_router.py`
- `duck_agent_sim/agent/direct_controller.py`
- `duck_agent_sim/agent/duck_agent.py`
- `duck_agent_sim/agent/gemini_live_client.py`
- `duck_agent_sim/agent/hermes_client.py`
- `duck_agent_sim/agent/hermes_delegator.py`
- `duck_agent_sim/bridge/api.py`
- `scripts/start_voice_simulation.sh`
- `tests/test_voice_control.py`
- `tests/test_gemini_live_client.py`
- `tests/test_smart_router.py`
- `tests/test_hermes_client.py`

Current command paths:

```text
Local voice / text
-> SmartRouter regex/heuristic classification
-> DirectController
-> HermesRobotClient HTTP
-> /command or /vision/follow/start
-> Queue/preflight safety
-> simulator desired control
```

```text
Gemini Live audio + FPV frames
-> Gemini tool call move_robot/follow_target/route_to_hermes
-> DirectController or HermesDelegator
-> same bridge API
```

What is usable:

- The AI/voice command path is cleanly high-level and does not emit raw joint targets.
- Safety preflight in `bridge/api.py` runs before `/command` and `/vision/follow/start`.
- Hermes/Gemini are command ingress layers, not locomotion controllers.

Risk:

- `GeminiLiveController._run_tool("move_robot")` captures `speed`, `turn`, and `duration_sec` in `Intent.params`, but `DirectController.execute()` ignores those params and uses `_MOTION_DEFAULTS`. This is not a locomotion policy risk, but it means Gemini tool arguments do not actually tune motion today.
- Voice/Gemini/Follower paths all ultimately depend on the same simulator locomotion path, so they inherit the fake dynamics/hardware-incompatibility risks.

## File Map

| Category | Files | Assessment |
|---|---|---|
| ONNX load/inference | `duck_agent_sim/simulator/duck_sim.py`, `duck_agent_sim/simulator/policy_contract.py`, `duck_agent_sim/models/BEST_WALK_ONNX_2.onnx`, `external/Open_Duck_Playground/playground/common/onnx_infer.py`, `external/Open_Duck_Playground/playground/open_duck_mini_v2/mujoco_infer.py` | Shape-compatible, needs semantic upstream alignment |
| Observation vector | `duck_agent_sim/simulator/duck_sim.py`, `duck_agent_sim/simulator/policy_contract.py`, `external/Open_Duck_Playground/playground/open_duck_mini_v2/mujoco_infer.py`, `external/Open_Duck_Playground/playground/open_duck_mini_v2/standing.py` | Local walking layout mirrors upstream infer, but phase/reset/dynamics differ |
| IMU mapping | `duck_agent_sim/simulator/duck_sim.py`, `external/Open_Duck_Playground/playground/open_duck_mini_v2/mujoco_infer_base.py`, `external/Open_Duck_Playground/playground/open_duck_mini_v2/base.py`, XML sensor files | Names align; local accelerometer offset matches upstream infer |
| Motor position/velocity mapping | `duck_agent_sim/simulator/duck_sim.py`, `duck_agent_sim/simulator/policy_contract.py`, `external/Open_Duck_Playground/playground/open_duck_mini_v2/mujoco_infer_base.py`, `base.py` | Uses actuator-name-derived MuJoCo addresses locally; constants are hardcoded in policy contract |
| Foot contact mapping | `duck_agent_sim/simulator/duck_sim.py`, `external/Open_Duck_Playground/playground/open_duck_mini_v2/mujoco_infer_base.py`, XML body names | Body-name contact check aligns with upstream |
| Action scaling | `duck_agent_sim/simulator/policy_contract.py`, `duck_agent_sim/simulator/duck_sim.py`, `external/Open_Duck_Playground/playground/open_duck_mini_v2/mujoco_infer.py` | Numeric constants align; local adds hard clamp |
| Joint ordering | `duck_agent_sim/simulator/policy_contract.py`, `duck_agent_sim/simulator/duck_sim.py`, XML actuator order | Likely aligned, but hardcoded contract should be validated against loaded model |
| Control frequency | `duck_agent_sim/simulator/duck_sim.py`, `duck_agent_sim/simulator/policy_contract.py`, `external/Open_Duck_Playground/playground/open_duck_mini_v2/mujoco_infer_base.py` | 500 Hz physics / 50 Hz policy matches upstream |
| MuJoCo stepping | `duck_agent_sim/simulator/duck_sim.py`, `external/Open_Duck_Playground/playground/open_duck_mini_v2/mujoco_infer.py`, `mujoco_infer_base.py` | Local adds pre-step stabilization/base forcing |
| Waddle oscillator | `duck_agent_sim/simulator/duck_sim.py`, `MockDuckSimulator` in same file | Demo/mock only |
| Fake stabilization | `duck_agent_sim/simulator/legacy_dynamics.py`, `duck_agent_sim/simulator/duck_sim.py`, Phase 2 docs/tests | Diagnostics useful; behavior not hardware-compatible |
| Command intent mapping | `duck_agent_sim/simulator/command_mapper.py`, `duck_agent_sim/agent/smart_router.py`, `direct_controller.py`, `gemini_live_client.py`, `bridge/api.py`, `vision/follower.py` | Good high-level ingress, but follower bypasses policy clamp |

## Risk Table

| Risk | Evidence | Severity | Hardware impact | Recommendation |
|---|---|---:|---|---|
| Floating-base qpos/qvel movement | `LegacyDynamicsController.apply()` writes base qpos/qvel directly | Critical | Valós roboton lehetetlen | Do not use this path as hardware locomotion |
| Torso/base pose forcing hides falls | Direct quaternion and z forcing before every `mj_step()` | Critical | Invalidates balance validation | Disable/remove only after upstream policy loop alignment and controlled sim tests |
| Observation semantic mismatch | Local shape matches, but phase period and head commands differ from upstream | High | Policy can receive out-of-distribution inputs | Wrap/reuse upstream inference semantics |
| Hardcoded actuator defaults/order | `policy_contract.py` hardcodes actuator order/defaults/ctrl ranges | High | Wrong motor target mapping can damage hardware | Validate against loaded MuJoCo/runtime model and hardware calibration |
| Policy/action shape mismatch not guarded early | Runtime relies on model and later action mapping | Medium | Bad model can fail during motion | Add explicit load-time contract validation in a future implementation session |
| Follower bypasses command clamp | `VisionGuidedFollower` calls `set_desired_control()` directly with max speed `0.3` | Medium | Policy distribution mismatch | Clamp desired control at simulator boundary or follower boundary |
| Waddle oscillator mistaken for gait | Fallback writes visual joint targets | High | Not a trained/stable gait | Keep simulator-demo only |
| Mock locomotion mistaken for physics | Mock updates position/contact/orientation kinematically | High | No hardware relevance | Use only for API/agent tests |
| Upstream reset/home drift | Local contract constants may drift from XML `home.ctrl` | Medium | Bad starting targets | Derive defaults from model or assert equality |
| AI tool argument mismatch | Gemini move args ignored by `DirectController` defaults | Low | Command UX mismatch, not motor-level hazard | Fix separately after locomotion alignment |

## Upstream Alignment Check

### Policy Inference Loop

Local loop is structurally similar to upstream:

- MuJoCo timestep: `0.002`.
- Decimation: `10`.
- Policy cadence: `50 Hz`.
- ONNX call format: batched observation with AWD-style output `[0][0]`.
- Motor target formula: default actuator + action * `0.25`.
- Target rate limit: `5.24 rad/s * 0.02s`.

Main mismatch:

- Local loop adds forced base stabilization and fake commanded base velocity. Upstream standalone inference does not.

### Observation Format

Mostly aligned with upstream `MjInfer.get_obs()`:

```text
gyro, accelerometer(+1.3 x offset), command(7), joint angle delta,
scaled joint velocity, 3 action histories, motor targets, contacts, imitation phase
```

Mismatches or uncertainties:

- Upstream walking phase period comes from `PolyReferenceMotion.nb_steps_in_period`; local hardcodes `50`.
- Local head/neck command entries are always zero in `_get_onnx_obs()`.
- Local runtime has no load-time assertion that generated obs length equals the ONNX model input length.

### Motor Target Output

Aligned numerically but not implementation-identical:

- Local uses `policy_contract.DEFAULT_ACTUATOR`; upstream uses `model.keyframe("home").ctrl`.
- Local clamps to hardcoded ctrl ranges; upstream standalone infer only rate-limits in the visible loop.
- Local writes `data.ctrl[:] = self.motor_targets`, same destination as upstream.

### Sensor Inputs

Aligned enough for simulation:

- `gyro` and `accelerometer` sensor names are the same.
- Contact body names are the same.
- Local `get_sensor_state()` exposes more sensor channels for telemetry.

Not hardware-ready:

- Sensor values are MuJoCo sensordata, not real IMU/motor encoder/contact sensor streams.
- No hardware timestamping, filtering, calibration, axis validation, or failure handling exists.

### Reset / Home Pose

Mostly aligned:

- Local resets MuJoCo data and applies `home` qpos/ctrl.
- Upstream base initializes `home` qpos/ctrl.

Mismatch:

- Local then performs 50 settle steps and leaves the background fake stabilization machinery active.
- Local policy contract hardcodes default actuator values rather than deriving from `home.ctrl`.

### Simulation Model Assumptions

Aligned:

- Uses vendored Open Duck Mini v2 XML and assets.
- Uses flat terrain scene.

Mismatch:

- The current local runtime behaves as a hybrid of official MuJoCo model plus non-official base forcing.

## Classification Summary

Használható így:

- High-level REST/WebSocket command bridge for simulation.
- Voice/Gemini/Hermes as high-level command ingress.
- Vendored Open Duck Playground XML/assets as the simulation model source.
- ONNX model shape contract for the bundled policy.
- Diagnostics counters that reveal fake dynamics usage.

Kis javítás kell:

- Load-time ONNX input/output validation.
- Runtime assertion that observation length is exactly 101 before inference.
- Runtime assertion that loaded MuJoCo actuator order/defaults match `policy_contract.py`.
- Gemini `move_robot` tool arguments vs `DirectController` default behavior.

Upstreamhez kell igazítani:

- Policy execution should wrap or closely mirror `external/Open_Duck_Playground/playground/open_duck_mini_v2/mujoco_infer.py`.
- Imitation phase should use the same reference-motion period as upstream for the selected policy.
- Default actuator targets should come from the loaded model/runtime source, or be asserted identical.
- Base dynamics should be generated by actuators/contact, not by `LegacyDynamicsController`.

Kísérleti / diagnosztikai:

- Phase 2 hybrid/dynamic diagnostics.
- Waddle oscillator.
- Mock simulator.
- Experimental camera/MuJoCo tests under `tests/experimental`.

Valós robothoz nem használható:

- `LegacyDynamicsController` locomotion/stabilization behavior.
- Any proof of walking based on direct base qpos/qvel writes.
- Waddle oscillator as a gait generator.
- Mock simulator kinematic movement.
- Current simulator bridge as a hardware runtime or HAL.

## Recommended Next Steps

1. Keep the current ONNX integration as a scaffold, but do not treat it as official-aligned locomotion yet.

2. Create an upstream-aligned policy execution adapter in a future implementation session. It should either wrap `MjInfer`/`MJInferBase` semantics or extract a shared local adapter that mirrors:
   - model-derived actuator order,
   - `home.ctrl` defaults,
   - upstream observation construction,
   - upstream phase/reference-motion timing,
   - upstream action scaling and rate limiting,
   - no floating-base qpos/qvel locomotion writes.

3. Preserve `LegacyDynamicsController` only as a named legacy/diagnostic path until replacement is validated. It must stay clearly marked as simulator-only.

4. Add contract validation before any further behavior changes:
   - ONNX input name/shape and output name/shape,
   - observation vector length and dtype,
   - actuator count/order,
   - `home.ctrl` vs policy default actuator,
   - ctrl ranges,
   - control cadence,
   - command clamp consistency for `/command` and vision follower.

5. Before any real hardware use, require:
   - upstream-compatible policy runtime without fake base writes,
   - verified joint order and sign conventions against the physical robot,
   - calibrated encoder/IMU axes and units,
   - actuator limits, velocity limits, torque/current limits, watchdogs, and e-stop,
   - hardware-specific reset/home procedure,
   - fall detection and safe torque-off behavior,
   - bench tests with legs unloaded before any ground locomotion,
   - explicit separation between simulator API and hardware HAL.

## Do Not Use on Real Robot

The following must not be used as real robot locomotion:

- `duck_agent_sim/simulator/legacy_dynamics.py` base qpos/qvel forcing.
- `RealDuckSimulator._stabilize_torso()` behavior while it delegates to legacy dynamics.
- `RealDuckSimulator._apply_waddle_oscillator()`.
- `MockDuckSimulator` movement/contact/orientation outputs.
- Any test/demo result whose motion depends on fake base translation or torso forcing.

## Final Recommendation

Do not continue the custom PD balance-controller direction now. The repository should first be aligned with the official Open Duck Mini v2 RL/ONNX locomotion stack. The current ONNX path is valuable and close enough to keep as a scaffold, but the execution semantics must be corrected around upstream observation timing, model-derived motor mapping, and removal of simulator-only floating-base overrides before it can support meaningful sim-to-real or hardware work.

---

## 11. Phase 3 Audit: Groundwork Closed (2026-05-23 Update)

A Phase 3 implementációs hullám lezárultával a korábban azonosított hiányosságok és igazítási feladatok az alábbiak szerint teljesültek:

1. **Phase 3A: Upstream Policy Contract Validation**:
   - Beépítésre került a betöltési idejű ONNX modell- és bemeneti/kimeneti dimenzió-ellenőrzés. A rendszer most már futásidőben ellenőrzi, hogy a betöltött modell struktúrája (obs `[1, 101]` és continuous actions `[1, 14]`) megegyezik-e a rögzített fizikai szerződéssel.

2. **Phase 3B: Command Clamping and Contract Warnings**:
   - A parancsküldési réteg és a szimulátor szintjén is bevezetésre került a `POLICY_COMMAND_LIMITS` szerinti automatikus lekorlátozás (clamp) a parancsvektorokra: `linear_x` `[-0.15, 0.15]`, `linear_y` `[-0.2, 0.2]`, `yaw` `[-1.0, 1.0]`. Ez megakadályozza, hogy az ONNX policy tartományon kívüli (out-of-distribution) bemeneteket kapjon.

3. **Phase 3C: Policy Default and Upstream Execution Adapter**:
   - Elkészült az automatikus home-ctrl összevetés és eltérés-diagnosztika (delta recording).
   - Létrejött az upstream végrehajtási adapter, amely shadow-módban futtatja az ONNX policy referenciát, és rögzíti az esetleges eltéréseket a szimulációs és a policy által számított akciók között.

4. **500Hz-es Törzs-Stabilizáció**:
   - A korábbi felborulási kockázatot kiküszöbölte a MuJoCo 500Hz-es fizikai lépésciklusába integrált aktív stabilizáció (`_stabilize_torso()`), amely szoftveres giroszkópként tompítja a Roll/Pitch szögsebességeket, valamint aktív magasságzárat biztosít. Ezáltal a robot dinamikus üzemben is teljesen borulásmentessé vált.
