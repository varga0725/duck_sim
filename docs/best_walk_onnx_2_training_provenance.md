# BEST_WALK_ONNX_2.onnx training provenance és PPO skeleton terv

## Rövid konklúzió

A `duck_agent_sim/models/BEST_WALK_ONNX_2.onnx` jelenlegi repóbeli eredeti training provenance-e nem áll rendelkezésre teljesen reprodukálható formában. A modell bináris artifactként került be a git történetbe, mellette nincs model card, checkpoint azonosító, seed, teljes PPO hyperparam snapshot, training log, eval metrika vagy export command napló.

A repóban viszont van egy részleges upstream training referencia: `external/Open_Duck_Playground`. Ez tartalmaz Open Duck Mini v2 Brax PPO runner-t, reward/termination kódot, domain randomizationt, terrain task mappinget és TensorFlow/tf2onnx exportot. Ez alapján készíthető minimális reprodukálható skeleton, de a jelenlegi ONNX pontos előállítása nem bizonyítható.

## Azonosított ONNX artifact

- Fájl: `duck_agent_sim/models/BEST_WALK_ONNX_2.onnx`
- Méret: `884177` byte
- SHA-256: `3c606f9381a1710cc8fecdb7442787dcbfce3ee9bc02a6f1224774ab2b3a1067`
- Git bevezető commit: `9b63c184d6c000338e45e3fa6a67022889b4aa83`
- Commit üzenet: `feat: integrate FPV vision, realistic room, active search, and 500Hz gyro torso stabilization`
- ONNX input: `obs`, shape `[1, 101]`, type `tensor(float)`
- ONNX output: `continuous_actions`, shape `[1, 14]`, type `tensor(float)`
- ONNX producer: `tf2onnx 1.16.1 15c810`
- ONNX opset: default domain `11`, `ai.onnx.ml` `2`
- ONNX metadata: üres `custom_metadata_map`, üres metadata props
- Graph: `tf2onnx`, 14 node, 10 initializer
- Policy MLP initializer shape-ek alapján: `101 -> 512 -> 256 -> 128 -> 28`, a végén `tanh(loc)` miatt 14 action jön ki a 28 policy paraméterből.

Következmény: az ONNX-ből bizonyítható az exportált inference szerződés és a hálózat architektúrája, de nem bizonyítható a checkpoint step, training run ID, reward skála snapshot, terrain XML hash, reference motion hash vagy seed.

## Keresett provenance elemek státusza

| Elem | Státusz | Bizonyíték / megjegyzés |
|---|---|---|
| Eredeti PPO config | Részleges upstream referencia, nem artifact-specifikus | `external/Open_Duck_Playground/playground/common/runner.py` a `mujoco_playground.config.locomotion_params.brax_ppo_config("BerkeleyHumanoidJoystickFlatTerrain")` configot használja, majd `num_timesteps` CLI override-ot állít. Nincs mentett Open Duck-specifikus YAML/JSON config a modell mellé. |
| Checkpoint azonosító | Nem található | A runner Orbax checkpoint path formátuma: `<output_dir>/<YYYY_MM_DD_HHMMSS>_<current_step>`, de a `BEST_WALK_ONNX_2.onnx` mellé nincs ilyen path, step vagy checkpoint hash rögzítve. |
| Reward definíció | Részleges upstream referencia | `external/Open_Duck_Playground/playground/open_duck_mini_v2/joystick.py` definiálja a `tracking_lin_vel`, `tracking_ang_vel`, `torques`, `action_rate`, `stand_still`, `alive`, `imitation` rewardokat. Nem bizonyított, hogy a konkrét ONNX pontosan ezzel a checkout állapottal készült. |
| Termination definíció | Részleges upstream referencia | `joystick.py`: `fall_termination = self.get_gravity(data)[-1] < 0.0`, plusz NaN qpos/qvel. |
| Domain randomization | Részleges upstream referencia | `external/Open_Duck_Playground/playground/common/randomize.py`: floor friction, dof frictionloss, armature, torso COM, body mass, torso added mass, qpos0, actuator gain/bias randomizáció. |
| Terrain setup | Részleges / inkonzisztens | `constants.py` task mapping: `flat_terrain`, `rough_terrain`, `flat_terrain_backlash`, `rough_terrain_backlash`. A README aktuális példája `flat_terrain_backlash`; a bridge runtime hardcoded módon flat terrain XML-t használ. |
| ONNX export parancs/script | Script van, konkrét command nincs | `external/Open_Duck_Playground/playground/common/export_onnx.py` tf2onnx exportot végez opset 11-gyel. A runner minden `policy_params_fn` callbacknél exportál `<timestamp>_<step>.onnx` fájlt. A konkrét `BEST_WALK_ONNX_2.onnx` átnevezésének / kiválasztásának commandja nincs rögzítve. |
| Dependency/environment | Részleges upstream referencia | `external/Open_Duck_Playground/pyproject.toml`: Python `>=3.11`, `jax[cuda12]>=0.5.0`, `jaxlib>=0.5.0`, `tensorflow>=2.18.0`, `tf2onnx>=1.16.1`, `onnxruntime>=1.20.1`, `playground>=0.0.3`, stb. Nincs lockfile/hardware baseline rögzítve. |

## Upstream training referencia részletei

### Training entrypoint

Forrás: `external/Open_Duck_Playground/playground/open_duck_mini_v2/runner.py`

- Default env: `joystick`
- Default task: `flat_terrain`
- Default output dir: `checkpoints`
- Default timesteps: `150000000`
- Restore támogatás: `--restore_checkpoint_path`
- Randomizer: `randomize.domain_randomize`
- Observation size: `env.observation_size["state"][0]`

README-ben szereplő aktuális példa:

```bash
uv run playground/open_duck_mini_v2/runner.py --task flat_terrain_backlash --num_timesteps 300000000
```

### PPO runner

Forrás: `external/Open_Duck_Playground/playground/common/runner.py`

- PPO import: `brax.training.agents.ppo`
- Env wrapper: `mujoco_playground.wrapper.wrap_for_brax_training`
- PPO base config: `locomotion_params.brax_ppo_config("BerkeleyHumanoidJoystickFlatTerrain")`
- Network factory: `ppo_networks.make_ppo_networks`, ha a config tartalmaz `network_factory` blokkot
- Training param override: `self.ppo_training_params["num_timesteps"] = self.num_timesteps`
- Callbackek:
  - `progress_fn=self.progress_callback`
  - `policy_params_fn=self.policy_params_fn`
- Checkpoint: Orbax `PyTreeCheckpointer`, path: `<output_dir>/<timestamp>_<current_step>`
- Export: `export_onnx(params, action_size, ppo_params, obs_size, output_path=<output_dir>/<timestamp>_<current_step>.onnx)`

Hiány: a tényleges `ppo_training_params` kimenete nincs model artifact mellé mentve, ezért a külső `mujoco_playground` package pontos verziója és configja nélkül nem reprodukálható.

### Reward és termination referencia

Forrás: `external/Open_Duck_Playground/playground/open_duck_mini_v2/joystick.py`

Default environment config:

```yaml
ctrl_dt: 0.02
sim_dt: 0.002
episode_length: 1000
action_repeat: 1
action_scale: 0.25
dof_vel_scale: 0.05
history_len: 0
soft_joint_pos_limit_factor: 0.95
max_motor_velocity: 5.24
USE_IMITATION_REWARD: true
USE_MOTOR_SPEED_LIMITS: true
```

Reward skálák:

```yaml
tracking_lin_vel: 2.5
tracking_ang_vel: 6.0
torques: -0.001
action_rate: -0.5
stand_still: -0.2
alive: 20.0
imitation: 1.0
tracking_sigma: 0.01
```

Reward komponensek:

- `reward_tracking_lin_vel(info["command"], local_linvel, tracking_sigma)`
- `reward_tracking_ang_vel(info["command"], gyro, tracking_sigma)`
- `cost_torques(data.actuator_force)`
- `cost_action_rate(action, info["last_act"])`
- `reward_alive()`
- `reward_imitation(...)`
- `cost_stand_still(...)`

Reward összegzés:

```python
rewards = {k: v * self._config.reward_config.scales[k] for k, v in rewards.items()}
reward = jp.clip(sum(rewards.values()) * self.dt, 0.0, 10000.0)
```

Termination:

```python
fall_termination = self.get_gravity(data)[-1] < 0.0
done = fall_termination | jp.isnan(data.qpos).any() | jp.isnan(data.qvel).any()
```

Command sampling:

```yaml
lin_vel_x: [-0.15, 0.15]
lin_vel_y: [-0.2, 0.2]
ang_vel_yaw: [-1.0, 1.0]
neck_pitch_range: [-0.34, 1.1]
head_pitch_range: [-0.78, 0.78]
head_yaw_range: [-1.5, 1.5]
head_roll_range: [-0.5, 0.5]
zero_command_probability: 0.1
resample_after_steps: 500
```

Noise / delay / push referencia:

```yaml
noise_level: 1.0
action_delay_steps: [0, 3]
imu_delay_steps: [0, 3]
noise_scales:
  hip_pos: 0.03
  knee_pos: 0.05
  ankle_pos: 0.08
  joint_vel: 2.5
  gravity: 0.1
  linvel: 0.1
  gyro: 0.1
  accelerometer: 0.05
push:
  enable: true
  interval_seconds: [5.0, 10.0]
  magnitude: [0.1, 1.0]
```

### Domain randomization referencia

Forrás: `external/Open_Duck_Playground/playground/common/randomize.py`

```yaml
floor_friction: [0.5, 1.0]
dof_frictionloss_scale: [0.9, 1.1]
dof_armature_scale: [1.0, 1.05]
torso_com_jitter_xyz: [-0.05, 0.05]
body_mass_scale: [0.9, 1.1]
torso_added_mass: [-0.1, 0.1]
qpos0_joint_jitter: [-0.03, 0.03]
actuator_kp_scale: [0.9, 1.1]
actuator_bias_tracks_scaled_kp: true
```

### Terrain/task mapping referencia

Forrás: `external/Open_Duck_Playground/playground/open_duck_mini_v2/constants.py`

```yaml
flat_terrain: external/Open_Duck_Playground/playground/open_duck_mini_v2/xmls/scene_flat_terrain.xml
rough_terrain: external/Open_Duck_Playground/playground/open_duck_mini_v2/xmls/scene_rough_terrain.xml
flat_terrain_backlash: external/Open_Duck_Playground/playground/open_duck_mini_v2/xmls/scene_flat_terrain_backlash.xml
rough_terrain_backlash: external/Open_Duck_Playground/playground/open_duck_mini_v2/xmls/scene_rough_terrain_backlash.xml
```

Megjegyzés: a forrásdokumentum szerint a checkoutban terrain/asset mapping inkonzisztenciák vannak; ezt implementáció előtt külön rendezni kell. A `BEST_WALK_ONNX_2.onnx` outputja 14 action, míg a joystick training referencia state-je 10 láb-actuator körül épül; a bridge és deployment szerződés dokumentációját ezért együtt kell kezelni a skeleton véglegesítésekor.

### ONNX export referencia

Forrás: `external/Open_Duck_Playground/playground/common/export_onnx.py`

- Input signature: `tf.TensorSpec(shape=(1, obs_size), dtype=tf.float32, name="obs")`
- Output name: `continuous_actions`
- Export opset: `11`
- Export backend: TensorFlow Keras model -> `tf2onnx.convert.from_keras`
- Preprocess: `inputs = (inputs - mean) / std`, ahol `mean = params[0].mean["state"]`, `std = params[0].std["state"]`
- Output: `tf.tanh(loc)`, ahol a policy logits két részre splitelődik: `loc, _ = tf.split(logits, 2, axis=-1)`
- Mellékhatás: az `output_path` mellett mindig ír egy `ONNX.onnx` fájlt is.

## Minimális reprodukálható PPO training skeleton terv

Mivel a konkrét artifact provenance hiányzik, a javasolt irány egy explicit, verziózott skeleton létrehozása. Cél: ne azt állítsa, hogy reprodukálja a jelenlegi `BEST_WALK_ONNX_2.onnx`-et, hanem hogy a következő Open Duck Mini v2 policy-k már reprodukálhatóan készüljenek.

### Javasolt fájlstruktúra

```text
training/
  README.md
  configs/
    open_duck_mini_v2_joystick_flat_backlash.yaml
  scripts/
    train_open_duck_mini_v2.py
    export_checkpoint_to_onnx.py
    validate_onnx_policy.py
  metadata/
    BEST_WALK_ONNX_2.model.yaml
  artifacts/
    README.md
docs/
  best_walk_onnx_2_training_provenance.md
  rl_training_reproduction.md
```

### `training/configs/open_duck_mini_v2_joystick_flat_backlash.yaml` minimális tartalom

```yaml
robot: open_duck_mini_v2
env: joystick
task: flat_terrain_backlash
seed: 0
num_timesteps: 300000000

upstream:
  repo_path: external/Open_Duck_Playground
  expected_commit: null
  runner: playground/open_duck_mini_v2/runner.py
  base_ppo_config_provider: mujoco_playground.config.locomotion_params.brax_ppo_config
  base_ppo_config_name: BerkeleyHumanoidJoystickFlatTerrain

environment:
  ctrl_dt: 0.02
  sim_dt: 0.002
  episode_length: 1000
  action_repeat: 1
  action_scale: 0.25
  dof_vel_scale: 0.05
  history_len: 0
  soft_joint_pos_limit_factor: 0.95
  max_motor_velocity: 5.24

commands:
  lin_vel_x: [-0.15, 0.15]
  lin_vel_y: [-0.2, 0.2]
  ang_vel_yaw: [-1.0, 1.0]
  neck_pitch_range: [-0.34, 1.1]
  head_pitch_range: [-0.78, 0.78]
  head_yaw_range: [-1.5, 1.5]
  head_roll_range: [-0.5, 0.5]
  zero_command_probability: 0.1
  resample_after_steps: 500

reward_scales:
  tracking_lin_vel: 2.5
  tracking_ang_vel: 6.0
  torques: -0.001
  action_rate: -0.5
  stand_still: -0.2
  alive: 20.0
  imitation: 1.0
  tracking_sigma: 0.01

termination:
  fall_if_gravity_z_lt: 0.0
  terminate_on_nan_qpos: true
  terminate_on_nan_qvel: true

noise:
  level: 1.0
  action_delay_steps: [0, 3]
  imu_delay_steps: [0, 3]
  scales:
    hip_pos: 0.03
    knee_pos: 0.05
    ankle_pos: 0.08
    joint_vel: 2.5
    gravity: 0.1
    linvel: 0.1
    gyro: 0.1
    accelerometer: 0.05

push:
  enable: true
  interval_seconds: [5.0, 10.0]
  magnitude: [0.1, 1.0]

domain_randomization:
  floor_friction: [0.5, 1.0]
  dof_frictionloss_scale: [0.9, 1.1]
  dof_armature_scale: [1.0, 1.05]
  torso_com_jitter_xyz: [-0.05, 0.05]
  body_mass_scale: [0.9, 1.1]
  torso_added_mass: [-0.1, 0.1]
  qpos0_joint_jitter: [-0.03, 0.03]
  actuator_kp_scale: [0.9, 1.1]

reference_motion:
  enabled: true
  file: external/Open_Duck_Playground/playground/open_duck_mini_v2/data/polynomial_coefficients.pkl
  generator_repo: https://github.com/apirrone/Open_Duck_reference_motion_generator
  file_sha256: null

terrain:
  xml: external/Open_Duck_Playground/playground/open_duck_mini_v2/xmls/scene_flat_terrain_backlash.xml
  xml_sha256: null

onnx_export:
  opset: 11
  input_name: obs
  input_shape: [1, 101]
  output_name: continuous_actions
  output_shape: [1, 14]
```

### Training script feladata

`training/scripts/train_open_duck_mini_v2.py`:

1. Betölti a YAML configot.
2. Rögzíti a következőket egy run könyvtárba:
   - git commit SHA-k: top-level repo és `external/Open_Duck_Playground`
   - `uv.lock` vagy dependency freeze
   - config copy
   - terrain XML SHA-256
   - reference motion SHA-256
   - hostname / GPU / Python verzió / CUDA/JAX verzió
3. Meghívja az upstream runner-t vagy közvetlenül a `BaseRunner`-t explicit paraméterekkel.
4. Ment minden checkpointot determinisztikus layout alá:

```text
training/runs/<run_id>/
  config.yaml
  environment.txt
  checkpoints/<step>/
  exports/policy_<step>.onnx
  metrics/tensorboard/...
  metadata/run.yaml
```

### Export script feladata

`training/scripts/export_checkpoint_to_onnx.py`:

1. Bemenet: checkpoint path, config path, output path.
2. Betölti az Orbax checkpointot.
3. Meghívja az export logikát úgy, hogy ne írjon mellékhatásként extra `ONNX.onnx` fájlt.
4. Rögzíti az export metadata-t:
   - checkpoint path és hash
   - obs/action shape
   - tf2onnx verzió
   - opset
   - normalizáció mean/std jelenléte
   - exportált ONNX SHA-256

### Validációs script feladata

`training/scripts/validate_onnx_policy.py`:

Minimum smoke testek:

1. ONNXRuntime betöltés CPU providerrel.
2. Input/output név, shape és dtype ellenőrzés.
3. Zéró input inference: output finite, shape helyes.
4. Véletlen input inference fix seed-del: output finite, `[-1, 1]` tartományban van a tanh miatt.
5. Bridge-kompatibilitási ellenőrzés a `duck_agent_sim/simulator/duck_sim.py` observation/action mappingjével.

### Model metadata fájl

`training/metadata/BEST_WALK_ONNX_2.model.yaml` a jelenlegi modellhez legalább ezt tartalmazza:

```yaml
model_name: BEST_WALK_ONNX_2.onnx
status: legacy_artifact_missing_full_provenance
file: duck_agent_sim/models/BEST_WALK_ONNX_2.onnx
sha256: 3c606f9381a1710cc8fecdb7442787dcbfce3ee9bc02a6f1224774ab2b3a1067
size_bytes: 884177
git_introduced_commit: 9b63c184d6c000338e45e3fa6a67022889b4aa83
onnx:
  producer: tf2onnx 1.16.1 15c810
  opset: 11
  input:
    name: obs
    shape: [1, 101]
    dtype: float32
  output:
    name: continuous_actions
    shape: [1, 14]
    dtype: float32
known_missing:
  - original_training_run_id
  - checkpoint_path
  - checkpoint_step
  - ppo_hyperparameter_snapshot
  - random_seed
  - reward_config_snapshot
  - domain_randomization_snapshot
  - terrain_xml_hash
  - reference_motion_hash
  - eval_metrics
```

## Nyitott kérdések

1. Honnan származik ténylegesen a `BEST_WALK_ONNX_2.onnx`? Lokális training runból, upstream fejlesztőtől, vagy kézzel átnevezett exportból?
2. Van-e meg bárhol a hozzá tartozó Orbax checkpoint könyvtár?
3. Melyik taskkal készült: `flat_terrain`, `flat_terrain_backlash`, `rough_terrain`, vagy más?
4. A 14 action output miatt a modell head/neck aktuátorokat is vezérel-e, vagy a training/deployment mapping eltér a mostani joystick referencia 10 láb-actuatoros részleteitől?
5. A training során be volt-e kapcsolva az imitation reward, és ha igen, pontosan melyik `polynomial_coefficients.pkl` fájlból?
6. Melyik `mujoco_playground` és `playground` package verzióval készült a PPO config?
7. Milyen seedekkel és hány envvel futott a training?
8. Van-e TensorBoard log vagy eval videó/metrika a modellhez?
9. A bridge real simhez használt `scene_flat_terrain.xml` megegyezik-e a training terrainnel, vagy már a szobás/FPV környezethez módosított XML?
10. A következő policy célja legacy kompatibilitás a jelenlegi bridge-csel, vagy tiszta új training/inference szerződés kialakítása?

## Következő implementációs lépések

1. Hozz létre `training/metadata/BEST_WALK_ONNX_2.model.yaml` fájlt a jelenlegi legacy modell bizonyított metadata-jával és a hiányzó mezőkkel.
2. Hozz létre `training/configs/open_duck_mini_v2_joystick_flat_backlash.yaml` skeleton configot a fenti explicit mezőkkel.
3. Írj `training/scripts/validate_onnx_policy.py` smoke testet, és futtasd a jelenlegi `BEST_WALK_ONNX_2.onnx`-en.
4. Válaszd szét a bridge runtime XML-t és a training XML-t; rögzíts minden training XML SHA-256-ot.
5. Fixáld az upstream exportot úgy, hogy ne írjon mindig `ONNX.onnx` mellékfájlt, és mindig generáljon metadata YAML-t.
6. Készíts training run layoutot `training/runs/<run_id>/...` alatt, ahol config, environment, checkpoint, export és metrika együtt archiválódik.
7. Döntsd el, hogy a training pipeline a top-level repo saját `training/` könyvtárába kerül, vagy az `external/Open_Duck_Playground` marad az egyetlen training upstream.
8. Ha előkerül a régi checkpoint/log, egészítsd ki ezt a dokumentumot a tényleges checkpoint step, command, seed, PPO config és eval metrikák alapján.
