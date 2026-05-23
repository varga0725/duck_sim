# BEST_WALK_ONNX_2.onnx RL policy observation/action contract

Ez a dokumentum a `duck_agent_sim/models/BEST_WALK_ONNX_2.onnx` modell futtatási szerződését írja le a repóban található kód alapján.

Fő források:

- ONNX runtime introspekció: `obs [1,101] -> continuous_actions [1,14]`
- Deployment / eredeti futtató: `external/Open_Duck_Playground/playground/open_duck_mini_v2/mujoco_infer.py`
- Deployment / bridge implementáció: `duck_agent_sim/simulator/duck_sim.py`
- MuJoCo modell és aktuátor metadata: `external/Open_Duck_Playground/playground/open_duck_mini_v2/xmls/scene_flat_terrain.xml`, betöltve MuJoCo-val
- Tréning környezethez közeli forrás: `external/Open_Duck_Playground/playground/open_duck_mini_v2/standing.py`

Megjegyzés: a `standing.py` `_get_obs()` függvénye a jelenlegi állapotában nem pontosan a 101 elemű deployment observationt adja vissza; a 101 elemű szerződés a tényleges ONNX modellből és a `mujoco_infer.py` / `duck_sim.py` deployment kódból vezethető vissza.

## ONNX I/O

- Input neve: `obs`
- Input dtype: `tensor(float)` / float32 ajánlott
- Input shape: `[1, 101]`
- Output neve: `continuous_actions`
- Output dtype: `tensor(float)`
- Output shape: `[1, 14]`

A kódban az input tipikusan így kerül átadásra:

```python
outputs = session.run(None, {input_name: [obs]})
action = outputs[0][0]
```

ahol `obs` egy 101 hosszú 1D `np.float32` vektor.

## Observation vektor: 101 elem, pontos sorrend

Indexelés: 0-alapú, zárt intervallumokkal (`start..end`).

| Index | Méret | Mező | Jelentés / forrás | Normalizáció / skála |
|---:|---:|---|---|---|
| 0..2 | 3 | `gyro` | IMU gyro szenzor: `data.sensordata[gyro_addr:gyro_addr+3]` | Nincs explicit skála deploymentben |
| 3..5 | 3 | `accelerometer` | IMU accelerometer szenzor | Deploymentben `accelerometer[0] += 1.3`; más komponensek változatlanok |
| 6..12 | 7 | `commands` | `[lin_vel_x, lin_vel_y, yaw_rate, neck_pitch, head_pitch, head_yaw, head_roll]` | Nincs skála; közvetlen command értékek |
| 13..26 | 14 | `joint_angles - default_actuator` | Aktuátor joint pozíciók home/default ctrlhez képest | Relatív pozíció radianban; `default_actuator` levonva |
| 27..40 | 14 | `joint_vel * dof_vel_scale` | Aktuátor joint sebességek | `dof_vel_scale = 0.05` |
| 41..54 | 14 | `last_action` | Előző policy output, nyers action | Nincs skála; nem target pozíció |
| 55..68 | 14 | `last_last_action` | Két ciklussal korábbi policy output | Nincs skála |
| 69..82 | 14 | `last_last_last_action` | Három ciklussal korábbi policy output | Nincs skála |
| 83..96 | 14 | `motor_targets` | Előző / aktuális motor target pozíció vektor | Abszolút target pozíció radianban; nincs `default_actuator` levonás |
| 97..98 | 2 | `contacts` | `[left_foot_contact, right_foot_contact]` | Boolból float: `0.0` vagy `1.0` |
| 99..100 | 2 | `imitation_phase` | `[cos(phase), sin(phase)]` járásfázis | Egységkör; álláskor `[1.0, 0.0]` a bridge-ben |

Ellenőrző összegzés:

`3 + 3 + 7 + 14 + 14 + 14 + 14 + 14 + 14 + 2 + 2 = 101`

### Commands részletei

`commands = [lin_vel_x, lin_vel_y, yaw_rate, neck_pitch, head_pitch, head_yaw, head_roll]`

Eredeti `mujoco_infer.py` konstansok:

- `lin_vel_x`: `[-0.15, 0.15]`
- `lin_vel_y`: `[-0.2, 0.2]`
- `yaw_rate`: `[-1.0, 1.0]`
- `neck_pitch`: `[-0.34, 1.1]`
- `head_pitch`: `[-0.78, 0.78]`
- `head_yaw`: `[-1.5, 1.5]` a deployment viewerben; `standing.py` configban `[-2.7, 2.7]`
- `head_roll`: `[-0.5, 0.5]`

A jelenlegi bridge (`duck_sim.py`) ONNX observationje a head/neck commandokat nullázza:

```python
commands = [current_linear_x, current_linear_y, current_yaw_rate, 0.0, 0.0, 0.0, 0.0]
```

A bridge továbbá a velocity commandokat 50 Hz-en low-pass szűri:

```python
current += (target - current) * 0.15
```

TODO / UNKNOWN:

- Nincs egyértelmű bizonyíték arra, hogy a `BEST_WALK_ONNX_2.onnx` pontosan melyik command tartományon lett tanítva. A legjobb forrás a `mujoco_infer.py` fenti konstansai.
- **Megoldva**: A bridge `RobotCommand` parancsküldő rétege és a szimulátor most már expliciten és automatikusan lekorlátozza (clamp) a célelmozdulás parancsokat a policy eredeti command limitjeire a `POLICY_COMMAND_LIMITS` (`linear_x`: `[-0.15, 0.15]`, `linear_y`: `[-0.2, 0.2]`, `yaw`: `[-1.0, 1.0]`) alapján.
- `head_yaw` tartományban eltérés van: deployment viewer `[-1.5, 1.5]`, tréning config `[-2.7, 2.7]`. A konkrét ONNX tréningkonfiguráció nincs a repóban bizonyítva.

### Szenzor normalizáció, zaj, delay

Deployment (`mujoco_infer.py`, `duck_sim.py`):

- `gyro`: nincs explicit normalizáció, nincs zaj hozzáadva.
- `accelerometer`: nincs skála, de az X komponenshez `+1.3` offset kerül.
- `joint_angles`: `joint_angles - default_actuator`.
- `joint_vel`: `joint_vel * 0.05`.
- `contacts`: bool kontakt értékek.
- `last_action*`: nyers policy action history, nem skálázott target.
- `motor_targets`: abszolút target pozíció history/aktuális érték, radian.

Training-szerű `standing.py` configban látható zaj/delay értékek:

- `noise_config.level = 1.0`
- action delay: `0..3` env step
- IMU delay: `0..3` env step
- gyro noise scale: `0.05`
- accelerometer noise scale: `0.005`
- gravity noise scale: `0.1`
- joint velocity noise scale: `2.5`
- joint position noise skálák: hip `0.03`, knee `0.05`, ankle `0.08` rad

TODO / UNKNOWN:

- Az ONNX modell exportált graphja nem tartalmazza ezeket a normalizációkat külön input preprocessként; a deployment kód felel az observation összeállításért.
- Nem bizonyított, hogy a konkrét `BEST_WALK_ONNX_2.onnx` tréningjén a `standing.py` jelenlegi zaj/delay beállításai voltak-e érvényben.
- A deploymentben nincs action delay historyből mintavétel; az action history csak observationként szerepel. A `standing.py` training step viszont `action_history` delayt használhatott.

## Aktuátor / joint sorrend

A 14 elemű joint/action/motor target vektor minden 14-es blokkban azonos sorrendű. MuJoCo modellből visszafejtve:

| Index | Aktuátor / joint | Home `default_actuator` ctrl [rad] | Ctrl range [rad] |
|---:|---|---:|---:|
| 0 | `left_hip_yaw` | 0.002 | [-0.523599, 0.523599] |
| 1 | `left_hip_roll` | 0.053 | [-0.436332, 0.436332] |
| 2 | `left_hip_pitch` | -0.630 | [-1.221730, 0.523599] |
| 3 | `left_knee` | 1.368 | [-1.570796, 1.570796] |
| 4 | `left_ankle` | -0.784 | [-1.570796, 1.570796] |
| 5 | `neck_pitch` | 0.000 | [-0.349066, 1.134464] |
| 6 | `head_pitch` | 0.000 | [-0.785398, 0.785398] |
| 7 | `head_yaw` | 0.000 | [-2.792527, 2.792527] |
| 8 | `head_roll` | 0.000 | [-0.523599, 0.523599] |
| 9 | `right_hip_yaw` | -0.003 | [-0.523599, 0.523599] |
| 10 | `right_hip_roll` | -0.065 | [-0.436332, 0.436332] |
| 11 | `right_hip_pitch` | 0.635 | [-0.523599, 1.221730] |
| 12 | `right_knee` | 1.379 | [-1.570796, 1.570796] |
| 13 | `right_ankle` | -0.796 | [-1.570796, 1.570796] |

Ugyanez a sorrend használandó itt:

- observation `joint_angles - default_actuator` blokk: index 13..26
- observation `joint_vel * 0.05` blokk: index 27..40
- observation `last_action` blokk: index 41..54
- observation `last_last_action` blokk: index 55..68
- observation `last_last_last_action` blokk: index 69..82
- observation `motor_targets` blokk: index 83..96
- output `continuous_actions[0..13]`

## Action output értelmezése

A policy outputja 14 elemű continuous action:

```python
motor_targets = default_actuator + action * action_scale
```

ahol:

- `action_scale = 0.25`
- `default_actuator` a fenti home ctrl vektor
- `motor_targets` pozíció target radianban, közvetlenül `data.ctrl[:]`-be írva

Tehát például:

- `action[i] = 0.0` -> target az adott joint home/default pozíciója
- `action[i] = +1.0` -> target `default_actuator[i] + 0.25 rad`
- `action[i] = -1.0` -> target `default_actuator[i] - 0.25 rad`

### Action clipping / limitálás

Deploymentben nincs látható explicit clipping a policy outputra közvetlenül. Van viszont motor target sebesség-limit:

```python
max_motor_velocity = 5.24  # rad/s
sim_dt = 0.002
decimation = 10
max_delta_per_policy_step = 5.24 * (0.002 * 10) = 0.1048 rad
motor_targets = clip(motor_targets,
    prev_motor_targets - 0.1048,
    prev_motor_targets + 0.1048)
```

A MuJoCo aktuátoroknak van ctrl range-e a fenti táblázat szerint. TODO / UNKNOWN:

- A kódban nincs explicit `np.clip(motor_targets, actuator_ctrlrange_low, actuator_ctrlrange_high)`; nem ebből a dokumentumból bizonyított, hogy MuJoCo runtime pontosan hogyan enforce-olja az actuator ctrlrange-et ebben a betöltésben.
- Az ONNX graphon belüli output activation / tanh megléte nincs ebben a dokumentumban visszafejtve. A futtató kód nyers continuous outputként kezeli.

## Control frequency

A források konzisztensen ezt használják:

- MuJoCo physics timestep: `sim_dt = 0.002 s` -> 500 Hz
- Policy/control timestep: `ctrl_dt = 0.02 s` -> 50 Hz
- Decimation: `10` physics step / policy step

Források:

- `standing.py`: `ctrl_dt=0.02`, `sim_dt=0.002`
- `mujoco_infer_base.py`: `sim_dt = 0.002`, `decimation = 10`
- `duck_sim.py`: komment és implementáció: 10 physics stepenként ONNX inference / control update

## Command space és bridge mapping

Eredeti deployment viewer command range (`mujoco_infer.py`):

- forward/backward `lin_vel_x`: `[-0.15, 0.15]`
- lateral `lin_vel_y`: `[-0.2, 0.2]`
- yaw rate: `[-1.0, 1.0]`

Jelenlegi bridge high-level mapping (`duck_agent_sim/simulator/command_mapper.py`):

- `walk_forward`: `linear_x = speed`, `linear_y = 0`, `yaw = turn`
- `walk_backward`: `linear_x = -speed * 0.6`, `linear_y = 0`, `yaw = turn`
- `turn_left`: `linear_x = speed * 0.2`, `yaw = max(abs(turn), 0.4)`
- `turn_right`: `linear_x = speed * 0.2`, `yaw = -max(abs(turn), 0.4)`
- `stop`, `reset`, `look_around`: zero command

Schema range (`duck_agent_sim/schemas.py`):

- `speed`: `0.0..1.0`, default `0.25`
- `turn`: `-1.0..1.0`, default `0.0`
- `duration_sec`: `0.1..10.0`

TODO / UNKNOWN:

- A bridge mapping sebességei nincsenek lekorlátozva a `mujoco_infer.py` eredeti `[-0.15, 0.15]` / `[-0.2, 0.2]` tartományaira.
- A modell valós tréning command distributionje nincs biztosan dokumentálva a repóban; a kommentelt `standing.py` command range és a deployment viewer range eltérhetett a végleges exporttól.

## Minimális kompatibilis inference pszeudókód

```python
obs = np.concatenate([
    gyro,                                      # 3
    accelerometer_with_x_plus_1_3,             # 3
    [vx, vy, yaw_rate, neck, head_pitch, head_yaw, head_roll],  # 7
    joint_pos[actuator_order] - default_actuator,               # 14
    joint_vel[actuator_order] * 0.05,                            # 14
    last_action,                              # 14
    last_last_action,                         # 14
    last_last_last_action,                    # 14
    motor_targets,                            # 14
    [left_contact, right_contact],            # 2
    [phase_cos, phase_sin],                   # 2
]).astype(np.float32)

assert obs.shape == (101,)
action = session.run(None, {"obs": [obs]})[0][0]  # shape (14,)
raw_targets = default_actuator + action * 0.25
motor_targets = rate_limit(raw_targets, prev_motor_targets, max_delta=0.1048)
data.ctrl[:] = motor_targets
```

## Nyitott kérdések / TODO-k

- TODO: A konkrét ONNX exporthoz tartozó tréning checkpoint/config azonosítása, ha elérhető máshol.
- TODO: ONNX graph részletes vizsgálata, hogy van-e output tanh/clamp vagy csak lineáris continuous action fej.
- TODO: A policy eredeti command range-ének megerősítése a modellhez tartozó training logból vagy configból.
- **Megoldva**: A bridge command mapping le van szűkítve és clampelve a policy command tartományaira a szimulátor szintjén.
- TODO: A MuJoCo actuator ctrlrange enforcement explicit tesztelése vagy kódbeli clipping hozzáadása, ha szükséges.
