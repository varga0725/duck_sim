# Open Duck Mini v2 test-kinematika

Ez a dokumentum a `duck_sim` projektben használt Open Duck Mini v2 MuJoCo testmodell kinematikai referenciája. A cél az, hogy az agent/bridge réteg ne találgasson joint sorrendet, oldalkonvenciót vagy ONNX akcióindexeket.

## Források

- Robot MJCF: `external/Open_Duck_Playground/playground/open_duck_mini_v2/xmls/open_duck_mini_v2.xml`
- Színtér és `home` keyframe: `external/Open_Duck_Playground/playground/open_duck_mini_v2/xmls/scene_flat_terrain.xml`
- MuJoCo vezérlés/ONNX bekötés: `duck_agent_sim/simulator/duck_sim.py`
- Parancsleképezés: `duck_agent_sim/simulator/command_mapper.py`
- ONNX policy: `duck_agent_sim/models/BEST_WALK_ONNX_2.onnx`

## Frame és koordináta konvenciók

- A modell MuJoCo/MJCF konvenciót használ.
- Világ/frame tengelyek: `+X` előre, `+Y` balra, `+Z` felfelé.
- A `base` test szabadtestként mozog: `floating_base` freejoint.
- A bridge állapot Euler szögei a freejoint quaternionból számított roll/pitch/yaw értékek fokban.
- A lokális magas szintű mozgásparancsok `ControlIntent` mezői:
  - `linear_x`: előre/hátra sebesség a robot lokális X tengelyén.
  - `linear_y`: oldalirányú sebesség, jelenleg parancsból 0.
  - `yaw`: z tengely körüli forgási sebesség, pozitív = balra fordulás.
- Az MJCF-ben a hinge jointok nem adnak explicit `axis` attribútumot, ezért MuJoCo alapértelmezés szerint lokális `[0, 0, 1]` tengelyt használ. A tényleges világirány a jointot hordozó child body aktuális orientációjától függ; a táblázatban a `world @home` oszlop a home pose-ban számított irányt mutatja.

## Body/link hierarchia

Robot-only hierarchia az `open_duck_mini_v2.xml` alapján:

```text
world
└── base                         freejoint: floating_base, start pos 0 0 0.22 az XML-ben
    └── trunk_assembly
        ├── hip_roll_assembly                         joint: left_hip_yaw
        │   └── left_roll_to_pitch_assembly           joint: left_hip_roll
        │       └── knee_and_ankle_assembly           joint: left_hip_pitch
        │           └── knee_and_ankle_assembly_2     joint: left_knee
        │               └── foot_assembly             joint: left_ankle
        │                   └── site: left_foot
        ├── neck_pitch_assembly                       joint: neck_pitch
        │   └── head_pitch_to_yaw                     joint: head_pitch
        │       └── neck_yaw_assembly                 joint: head_yaw
        │           └── head_assembly                 joint: head_roll
        │               ├── site: head
        │               └── camera: fpv
        └── hip_roll_assembly_2                       joint: right_hip_yaw
            └── right_roll_to_pitch_assembly          joint: right_hip_roll
                └── knee_and_ankle_assembly_3         joint: right_hip_pitch
                    └── knee_and_ankle_assembly_4     joint: right_knee
                        └── foot_assembly_2           joint: right_ankle
                            └── site: right_foot
```

A `scene_flat_terrain.xml` ezen felül a világhoz kötött környezeti body-kat ad hozzá: `floor`, `wall_front`, `wall_left`, `wall_right`, `wall_back`, `table`, `chair`, valamint `sports_ball` egy külön freejointtal. Ezek nem részei a robot aktuátor/joint sorrendjének.

## Site-ok, kamerák és szenzorok

Robot site-ok és kamerák:

| elem | body | szerep / pozíció és orientáció |
|---|---|---|
| `imu` (site) | `base` | IMU szenzorok rögzítési pontja |
| `trunk` (site) | `trunk_assembly` | törzs referencia site |
| `left_foot` (site) | `foot_assembly` | bal láb/foot frame |
| `right_foot` (site) | `foot_assembly_2` | jobb láb/foot frame |
| `head` (site) | `head_assembly` | fej referencia site |
| `fpv` (camera) | `head_assembly` | Belső nézetes FPV kamera. Pozíció a fejhez képest: `[0.08, 0.0, 0.05]` m, local quaternion: `[0.70710678, 0.0, 0.0, -0.70710678]` (xyaxes: `0 -1 0 1 0 0`), vertical fovy: `45.0` fok. |

MJCF szenzorok:

- `gyro`, `local_linvel`, `accelerometer`
- `upvector`, `forwardvector`, `global_linvel`, `global_angvel`, `position`, `orientation`
- `right_foot_global_linvel`, `left_foot_global_linvel`
- `left_foot_upvector`, `right_foot_upvector`
- `left_foot_pos`, `right_foot_pos`

A real MuJoCo szimulátor ONNX observationben ténylegesen a `gyro` és `accelerometer` szenzort olvassa, a kontaktot pedig `check_contact("foot_assembly", "floor")` és `check_contact("foot_assembly_2", "floor")` alapján számolja.

## Joint és aktuátor sorrend

Az aktuátor sorrend az XML `<actuator>` blokkjának sorrendje. A real szimulátorban ez azonos a `self.actuator_names = [self.model.actuator(k).name for k in range(self.model.nu)]` sorrenddel, és ezt használja az ONNX observation és output mapping is.

| # | joint / actuator | child body | parent body | axis local | axis world @home | limit rad | limit deg | home rad | qpos adr | dof adr |
|---:|---|---|---|---|---|---:|---:|---:|---:|---:|
| 0 | `left_hip_yaw` | `hip_roll_assembly` | `trunk_assembly` | `[0,0,1]` | `[-0.000,+0.000,+1.000]` | `[-0.523599, 0.523599]` | `[-30.0, 30.0]` | `0.002` | 7 | 6 |
| 1 | `left_hip_roll` | `left_roll_to_pitch_assembly` | `hip_roll_assembly` | `[0,0,1]` | `[-1.000,-0.002,-0.000]` | `[-0.436332, 0.436332]` | `[-25.0, 25.0]` | `0.053` | 8 | 7 |
| 2 | `left_hip_pitch` | `knee_and_ankle_assembly` | `left_roll_to_pitch_assembly` | `[0,0,1]` | `[+0.002,-0.999,+0.053]` | `[-1.221730, 0.523599]` | `[-70.0, 30.0]` | `-0.630` | 9 | 8 |
| 3 | `left_knee` | `knee_and_ankle_assembly_2` | `knee_and_ankle_assembly` | `[0,0,1]` | `[+0.002,-0.999,+0.053]` | `[-1.570796, 1.570796]` | `[-90.0, 90.0]` | `1.368` | 10 | 9 |
| 4 | `left_ankle` | `foot_assembly` | `knee_and_ankle_assembly_2` | `[0,0,1]` | `[+0.002,-0.999,+0.053]` | `[-1.570796, 1.570796]` | `[-90.0, 90.0]` | `-0.784` | 11 | 10 |
| 5 | `neck_pitch` | `neck_pitch_assembly` | `trunk_assembly` | `[0,0,1]` | `[-0.000,-1.000,-0.000]` | `[-0.349066, 1.134464]` | `[-20.0, 65.0]` | `0.000` | 12 | 11 |
| 6 | `head_pitch` | `head_pitch_to_yaw` | `neck_pitch_assembly` | `[0,0,1]` | `[-0.000,-1.000,+0.000]` | `[-0.785398, 0.785398]` | `[-45.0, 45.0]` | `0.000` | 13 | 12 |
| 7 | `head_yaw` | `neck_yaw_assembly` | `head_pitch_to_yaw` | `[0,0,1]` | `[-0.000,+0.000,+1.000]` | `[-2.792527, 2.792527]` | `[-160.0, 160.0]` | `0.000` | 14 | 13 |
| 8 | `head_roll` | `head_assembly` | `neck_yaw_assembly` | `[0,0,1]` | `[-1.000,-0.000,-0.000]` | `[-0.523599, 0.523599]` | `[-30.0, 30.0]` | `0.000` | 15 | 14 |
| 9 | `right_hip_yaw` | `hip_roll_assembly_2` | `trunk_assembly` | `[0,0,1]` | `[-0.000,+0.000,+1.000]` | `[-0.523599, 0.523599]` | `[-30.0, 30.0]` | `-0.003` | 16 | 15 |
| 10 | `right_hip_roll` | `right_roll_to_pitch_assembly` | `hip_roll_assembly_2` | `[0,0,1]` | `[-1.000,+0.003,-0.000]` | `[-0.436332, 0.436332]` | `[-25.0, 25.0]` | `-0.065` | 17 | 16 |
| 11 | `right_hip_pitch` | `knee_and_ankle_assembly_3` | `right_roll_to_pitch_assembly` | `[0,0,1]` | `[+0.003,+0.998,+0.065]` | `[-0.523599, 1.221730]` | `[-30.0, 70.0]` | `0.635` | 18 | 17 |
| 12 | `right_knee` | `knee_and_ankle_assembly_4` | `knee_and_ankle_assembly_3` | `[0,0,1]` | `[-0.003,-0.998,-0.065]` | `[-1.570796, 1.570796]` | `[-90.0, 90.0]` | `1.379` | 19 | 18 |
| 13 | `right_ankle` | `foot_assembly_2` | `knee_and_ankle_assembly_4` | `[0,0,1]` | `[-0.003,-0.998,-0.065]` | `[-1.570796, 1.570796]` | `[-90.0, 90.0]` | `-0.796` | 20 | 19 |

Megjegyzések:

- A `floating_base` freejoint megelőzi az aktuált hinge jointokat a qpos/qvel vektorban: `qpos[0:7]`, `qvel[0:6]`.
- A 14 aktuált joint qpos címei `7..20`, dof címei `6..19`.
- A scene `sports_ball` freejointja roboton kívüli elem, nem része az aktuátorvektornak.

## Joint limitek és home pose

A joint limitek az MJCF `<joint range="min max">` értékei, radiánban. A position aktuátorok `inheritrange="1"` miatt ugyanezeket a tartományokat öröklik `ctrlrange`-ként.

A stabil home pose a `scene_flat_terrain.xml` `home` keyframe-jéből jön:

```text
base position:  [0, 0, 0.15]
base quat:      [1, 0, 0, 0]
actuated qpos / ctrl in actuator order:
  left_hip_yaw    0.002
  left_hip_roll   0.053
  left_hip_pitch -0.630
  left_knee       1.368
  left_ankle     -0.784
  neck_pitch      0.000
  head_pitch      0.000
  head_yaw        0.000
  head_roll       0.000
  right_hip_yaw  -0.003
  right_hip_roll -0.065
  right_hip_pitch 0.635
  right_knee      1.379
  right_ankle    -0.796
```

A mock szimulátor ettől eltérő, absztrakt stabil állapotot használ: `position=(0.0, 0.0, 0.41)`, roll/pitch/yaw = 0, mindkét láb kontaktban. A real MuJoCo útvonalon a home keyframe `z=0.15`.

## Bal/jobb oldal konvenció

- A robot bal oldala a pozitív `Y` irányban van.
- Bal csípő root body: `hip_roll_assembly`, lokális pozíciója a törzshöz képest `y=+0.035`.
- Jobb csípő root body: `hip_roll_assembly_2`, lokális pozíciója a törzshöz képest `y=-0.035`.
- Bal láb site: `left_foot` a `foot_assembly` body-n.
- Jobb láb site: `right_foot` a `foot_assembly_2` body-n.
- A modellben a jobb oldali body-k egy része `_2`, `_3`, `_4` suffixet kapott; ezek nem sorrendi prioritást jelentenek, hanem az Onshape/MJCF export nevei.

## ONNX output és aktuátor sorrend ellenőrzése

Az ONNX policy introspekciója:

```text
input:  obs, shape [1, 101], tensor(float)
output: continuous_actions, shape [1, 14], tensor(float)
```

A `duck_agent_sim/simulator/duck_sim.py` ONNX futtatási útvonala:

```python
action = outputs[0][0]          # shape: 14
self.motor_targets = self.default_actuator + action * 0.25
self.data.ctrl[:] = self.motor_targets
```

Ez azt jelenti, hogy az ONNX `continuous_actions[0..13]` elemei 1:1-ben az aktuátor sorrendre mennek:

| ONNX action index | actuator / joint |
|---:|---|
| 0 | `left_hip_yaw` |
| 1 | `left_hip_roll` |
| 2 | `left_hip_pitch` |
| 3 | `left_knee` |
| 4 | `left_ankle` |
| 5 | `neck_pitch` |
| 6 | `head_pitch` |
| 7 | `head_yaw` |
| 8 | `head_roll` |
| 9 | `right_hip_yaw` |
| 10 | `right_hip_roll` |
| 11 | `right_hip_pitch` |
| 12 | `right_knee` |
| 13 | `right_ankle` |

Az ONNX observation 101 elemű vektorának fő blokkjai:

```text
gyro                         3
accelerometer                 3
commands                      7  [lin_vel_x, lin_vel_y, yaw, neck_pitch, head_pitch, head_yaw, head_roll]
joint_angles - default        14
joint_vel * 0.05              14
last_action                   14
last_last_action              14
last_last_last_action         14
motor_targets                 14
contacts                       2  [left_contact, right_contact]
imitation_phase                2  [cos, sin]
összesen                     101
```

## Biztonsági megjegyzés agent használathoz

A bridge magas szintű parancsokra van tervezve (`walk_forward`, `turn_left`, `stop`, `reset` stb.). Agent oldalról továbbra sem szabad nyers joint szögeket vagy motor targeteket közvetlenül kiadni; ha a robot `fallen=True` vagy instabil, először `stop`, majd szükség szerint `reset` szükséges.

## Rövid ellenőrzési megjegyzés

Ellenőrizve MuJoCo modellbetöltéssel és ONNX Runtime introspekcióval:

- `model.nu == 14`, a 14 aktuátor neve pontosan megegyezik az XML `<actuator>` sorrendjével.
- A position aktuátorok `ctrlrange` értéke megegyezik a joint limitekkel.
- A `home` keyframe `ctrl` vektora ugyanebben a 14 elemű sorrendben van.
- Az ONNX policy output shape-je `[1, 14]`, ezért az output elemek közvetlenül az aktuátor sorrendnek felelnek meg.
