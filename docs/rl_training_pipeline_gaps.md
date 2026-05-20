# RL training pipeline állapotfelmérés és hiánylista

## Rövid konklúzió

A `duck-agent-sim` felső szintű projekt jelenlegi állapota elsősorban inference/bridge réteg: FastAPI/WebSocket API-t, mock/real MuJoCo szimulátor-kapcsolást, telemetriát, biztonsági logikát és ONNX policy betöltést tartalmaz. Reprodukálható RL training pipeline a felső szintű csomagban nincs: nincs saját PPO konfigurációs fájl, nincs saját training entrypoint, nincs seedelt kísérlet-konfiguráció, nincs checkpoint metadata és nincs dokumentált modell-előállítási folyamat.

A repo alatt viszont van egy külső/vendorizált upstream kód: `external/Open_Duck_Playground`. Ebben található részleges Open Duck Mini v2 training infrastruktúra Brax PPO-val, reward/termination kóddal, domain randomizationnel, terrain XML-ekkel és ONNX exporttal. Ez a külső könyvtár nem teljesen reprodukálható training csomagként van bekötve a bridge projektbe; inkább upstream referencia/forrás, amelyből a bridge a MuJoCo asseteket és az ONNX inference policy-t használja.

## Vizsgált elemek státusza

| Elem | Felső szintű `duck-agent-sim` | `external/Open_Duck_Playground` | Megjegyzés |
|---|---|---|---|
| PPO konfiguráció | Nincs | Részleges | `playground/common/runner.py` a `mujoco_playground.config.locomotion_params.brax_ppo_config("BerkeleyHumanoidJoystickFlatTerrain")` konfigurációt használja, majd `num_timesteps`-et CLI-ből írja felül. Ez nem Open Duck-specifikus, verziózott hyperparam config. |
| Reward function | Nincs training reward | Van | `playground/open_duck_mini_v2/joystick.py` és `standing.py` definiál reward komponenseket; közös reward helper: `playground/common/rewards.py`; imitation reward: `custom_rewards.py`. |
| Termination feltételek | Csak runtime safety/fallen állapot | Van | `joystick.py` és `standing.py`: bukás, ha a gravity/up vector z komponense negatív, illetve NaN `qpos`/`qvel`. |
| Domain randomization | Nincs | Van | `playground/common/randomize.py`: floor friction, dof frictionloss, armature, COM, mass, qpos0, actuator gain/bias randomizáció. |
| Terrain/randomizáció setup | Real sim jelenleg flat XML-t tölt | Részleges | `constants.py` flat/rough/backlash task mappinget tartalmaz, de a checkoutban csak `scene_rough_terrain_backlash.xml` látszik, `scene_rough_terrain.xml` nem. A felső szintű bridge hardcoded módon `FLAT_TERRAIN_XML`-t olvas. |
| Checkpoint export ONNX-be | Csak ONNX betöltés | Van export kód | `playground/common/runner.py` Orbax checkpointot ment és meghívja az `export_onnx`-t; `playground/common/export_onnx.py` TensorFlow/tf2onnx alapú exportot csinál. |
| Training commandok | Nincs saját training command | Van upstream README/runner | Upstream README: `uv run playground/open_duck_mini_v2/runner.py --task flat_terrain_backlash --num_timesteps 300000000`. |
| Külső upstream hivatkozások | README setup Open_Duck_Playground klónozásra | Van | Upstream README hivatkozik Open_Duck_reference_motion_generator-re és kscalelabs/mujoco_playground inspirációra. |

## Bizonyítékok / fontos fájlok

### Felső szintű bridge/inference réteg

- `README.md`
  - A projekt célja agent control API és robotics bridge, nem motor controller.
  - Real MuJoCo módban `DUCK_ONNX_MODEL_PATH=/path/to/policy.onnx` szükséges.
  - A README szerint alap ONNX modell is használható: `duck_agent_sim/models/BEST_WALK_ONNX_2.onnx`.
- `pyproject.toml`
  - Felső szintű dependency-k: FastAPI, Uvicorn, Pydantic, python-dotenv, onnxruntime.
  - Nem tartalmaz JAX/Brax/MuJoCo Playground/TensorFlow training dependency-ket.
- `duck_agent_sim/config.py`
  - `DUCK_ONNX_MODEL_PATH` env varból jön, vagy ha létezik, default modellre mutat: `duck_agent_sim/models/BEST_WALK_ONNX_2.onnx`.
- `duck_agent_sim/simulator/duck_sim.py`
  - Real sim betölti a MuJoCo XML-t és ONNXRuntime `InferenceSession`-t hoz létre.
  - A vezérlési ciklusban ONNX aktív állapotban `_apply_onnx_inference()` fut, különben kinematikus/freejoint+waddle fallback.
  - Training loop, PPO update, reward számítás, checkpoint mentés nincs ebben a rétegben.
- `duck_agent_sim/models/BEST_WALK_ONNX_2.onnx`
  - Egy kész inference artifact van jelen, de nincs hozzá metadata: melyik commitból, milyen hyperparaméterekkel, seedekkel, reward skálákkal és training adatokkal készült.

### Külső upstream training referencia

- `external/Open_Duck_Playground/README.md`
  - Training command: `uv run playground/<robot>/runner.py`.
  - Aktuális példa: `uv run playground/open_duck_mini_v2/runner.py --task flat_terrain_backlash --num_timesteps 300000000`.
  - Imitation rewardhoz külső referencia motion generator kell: `github.com/apirrone/Open_Duck_reference_motion_generator`; output: `polynomial_coefficients.pkl` a robot `data/` könyvtárába.
- `external/Open_Duck_Playground/pyproject.toml`
  - Training stack: `jax[cuda12]`, `jaxlib`, `tensorflow`, `tf2onnx`, `onnxruntime`, `playground`, stb.
- `external/Open_Duck_Playground/playground/common/runner.py`
  - Brax PPO import: `from brax.training.agents.ppo import networks as ppo_networks, train as ppo`.
  - PPO config: `locomotion_params.brax_ppo_config("BerkeleyHumanoidJoystickFlatTerrain")`.
  - `randomization_fn=self.randomizer`, `progress_fn`, `policy_params_fn`, `restore_checkpoint_path` átadása.
  - Checkpoint mentés Orbaxszal és ONNX export minden `policy_params_fn` híváskor.
- `external/Open_Duck_Playground/playground/open_duck_mini_v2/runner.py`
  - Env választás: `joystick` vagy `standing`.
  - Task default: `flat_terrain`; output default: `checkpoints`; timesteps default: `150000000`; restore checkpoint path támogatott.
  - `self.randomizer = randomize.domain_randomize`.
- `external/Open_Duck_Playground/playground/open_duck_mini_v2/joystick.py`
  - Reward skálák: tracking linear/angular velocity, torque penalty, action rate penalty, stand still penalty, alive reward, imitation reward.
  - Noise/action delay/IMU delay konfigurációk vannak.
  - Push perturbation config van.
  - Termination: fall vagy NaN állapot.
  - Command sampling: lineáris x/y sebesség, yaw, head/neck range-ek random mintavétele.
- `external/Open_Duck_Playground/playground/common/randomize.py`
  - Domain randomization: floor friction, dof frictionloss, armature, torso COM, body mass, torso extra mass, qpos0, actuator gain/bias.
- `external/Open_Duck_Playground/playground/common/export_onnx.py`
  - JAX policy paraméterekből TensorFlow MLP-t épít, weight transfert csinál, majd `tf2onnx.convert.from_keras(..., opset=11)`.
- `external/Open_Duck_Playground/playground/open_duck_mini_v2/constants.py`
  - Task mapping: `flat_terrain`, `rough_terrain`, `flat_terrain_backlash`, `rough_terrain_backlash`.
  - Megfigyelt probléma: a checkoutban `scene_rough_terrain.xml` nem található, miközben a constants hivatkozik rá; csak `scene_rough_terrain_backlash.xml` van jelen.

## Részletes hiányok a reprodukálható traininghez

### 1. Saját, verziózott training konfiguráció

Hiányzik egy Open Duck-specifikus config, amely explicit tartalmazza legalább:

- PPO hyperparaméterek: batch size, num environments, unroll length, num minibatches, learning rate, entropy cost, discount/gamma, GAE lambda, clipping epsilon, network hidden sizes, activation, normalization.
- Training horizon: `num_timesteps`, eval frequency, checkpoint frequency.
- Random seedek: training seed, eval seed, domain randomization seed policy.
- Environment config snapshot: `ctrl_dt`, `sim_dt`, `episode_length`, `action_scale`, motor speed limit, observation history length.
- Reward skálák teljes listája és indoklása.

Jelenleg az upstream runner a BerkeleyHumanoidJoystickFlatTerrain PPO configját használja bázisként. Ez működhet indulásnak, de nem reprodukálható Open Duck Mini policy spec.

### 2. Training artifact provenance

A `duck_agent_sim/models/BEST_WALK_ONNX_2.onnx` mellé kellene:

- model card vagy metadata JSON/YAML,
- upstream commit SHA,
- training command,
- env/task neve,
- PPO hyperparaméterek,
- reward config,
- domain randomization config,
- terrain XML neve/hash-e,
- reference motion file hash-e,
- checkpoint step,
- eval metrikák,
- export script verziója,
- ONNX opset és input/output shape.

Enélkül az ONNX modell inference-re használható, de nem reprodukálható.

### 3. Reward és termination dokumentáció

A reward kód megvan upstreamben, de nincs bridge-szintű dokumentáció arról, hogy a használt ONNX modell pontosan melyik reward összeállítással készült. Dokumentálni kell:

- joystick vs standing env,
- imitation reward be/ki kapcsolása,
- `polynomial_coefficients.pkl` eredete,
- reward skálák,
- reward clipping (`jp.clip(sum(rewards.values()) * dt, 0.0, 10000.0)`),
- termination logika,
- command resampling és episode reset policy.

### 4. Terrain és task setup tisztázása

A jelenlegi checkoutban több jel arra utal, hogy az asset/task mapping nem tiszta:

- A bridge real sim oldalon `FLAT_TERRAIN_XML`-t tölt, nem paraméterezhető task alapján.
- `constants.py` hivatkozik `scene_rough_terrain.xml`-re, de ez a fájl nem található.
- A README training példa `flat_terrain_backlash` taskot ajánl.
- `scene_flat_terrain.xml` a bridge-ben már nem csak egyszerű plane: falakat, asztalt, széket és labdát is tartalmaz, ami training terrainként gyanúsan eltérhet az upstream baseline-tól.

Szükséges: taskonként rögzített XML-ek, asset hash-ek, és világos, hogy melyik terrainnel készült a modell.

### 5. Checkpoint és ONNX export folyamat keményítése

Az upstream export folyamat létezik, de reprodukálható release pipeline-hoz kellene:

- determinisztikus export command,
- shape ellenőrzés,
- ONNXRuntime smoke test,
- input normalizáció mean/std dokumentálása,
- exportált modell neve/versioning szabálya,
- egyértelmű output path, ne írjon mellékhatásként mindig `ONNX.onnx`-t is,
- bridge kompatibilitási teszt a konkrét ONNX-szel.

### 6. Training és inference környezet szétválasztása

A felső szintű `pyproject.toml` csak inference/bridge dependency-ket tartalmaz. Ez jó runtime szempontból, de hiányzik egy dokumentált training környezet:

- külön `training/` vagy `external` reproducibility README,
- CUDA/JAX verziók,
- GPU/CPU elvárás,
- uv lock vagy constraints a training stackhez,
- expected wall-clock / hardware baseline,
- TensorBoard logdir és checkpoint layout.

## Javasolt fájlok/adatok a teljes reprodukálhatósághoz

Minimális javasolt struktúra:

```text
docs/
  rl_training_pipeline_gaps.md        # ez a felmérés
  rl_training_reproduction.md         # lépésről lépésre futtatható training leírás
training/
  configs/
    open_duck_mini_v2_joystick_flat_backlash.yaml
  scripts/
    train_open_duck_mini_v2.py
    export_checkpoint_to_onnx.py
    validate_onnx_policy.py
  artifacts/
    README.md                         # mit nem commitolunk, hol vannak a nagy checkpointok
  metadata/
    BEST_WALK_ONNX_2.model.yaml       # provenance a jelenlegi ONNX mellé
```

A config minimálisan tartalmazza:

```yaml
robot: open_duck_mini_v2
env: joystick
task: flat_terrain_backlash
num_timesteps: 300000000
ppo:
  source: mujoco_playground.config.locomotion_params.brax_ppo_config
  base_config: BerkeleyHumanoidJoystickFlatTerrain
  overrides: {}
environment:
  ctrl_dt: 0.02
  sim_dt: 0.002
  episode_length: 1000
  action_scale: 0.25
reward_scales:
  tracking_lin_vel: 2.5
  tracking_ang_vel: 6.0
  torques: -0.001
  action_rate: -0.5
  stand_still: -0.2
  alive: 20.0
  imitation: 1.0
domain_randomization:
  floor_friction: [0.5, 1.0]
  dof_frictionloss_scale: [0.9, 1.1]
  armature_scale: [1.0, 1.05]
  torso_com_jitter: [-0.05, 0.05]
  body_mass_scale: [0.9, 1.1]
  torso_added_mass: [-0.1, 0.1]
  actuator_kp_scale: [0.9, 1.1]
reference_motion:
  file: external/Open_Duck_Playground/playground/open_duck_mini_v2/data/polynomial_coefficients.pkl
  generator_repo: https://github.com/apirrone/Open_Duck_reference_motion_generator
onnx_export:
  opset: 11
  output: duck_agent_sim/models/<model-name>.onnx
```

## Következő ajánlott lépések

1. Dönteni kell, hogy a training pipeline a `duck-agent-sim` repo része legyen-e, vagy az `external/Open_Duck_Playground` csak upstream referencia maradjon.
2. A jelenlegi `BEST_WALK_ONNX_2.onnx` mellé vissza kell keresni vagy létre kell hozni a provenance metadata fájlt.
3. A `constants.py` terrain mappinget és az XML checkoutot rendezni kell (`scene_rough_terrain.xml` hiányzik, bridge real sim hardcoded flat XML-t használ).
4. Érdemes létrehozni egy `docs/rl_training_reproduction.md` dokumentumot futtatható commandokkal, de csak akkor, ha a tényleges training környezet és célmodell kiválasztása tisztázott.
5. ONNX export után kötelező legyen legalább egy smoke test: ONNXRuntime betöltés, input shape ellenőrzés, egy lépéses inference, majd bridge-kompatibilitási próba.
