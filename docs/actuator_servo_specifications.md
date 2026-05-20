# Open Duck Mini v2 aktuátor / szervó specifikációk és szimulációs paraméterek

Állapot: forrásból kinyert műszaki jegyzet, 2026-05-20.

## Források

- `external/Open_Duck_Playground/playground/open_duck_mini_v2/xmls/open_duck_mini_v2.xml`
  - fő robot XML; effektív aktuátorok és STS3215 default paraméterek.
- `external/Open_Duck_Playground/playground/open_duck_mini_v2/xmls/scene_flat_terrain.xml`
  - real módban betöltött scene; `home` keyframe `qpos`/`ctrl` értékek.
- `external/Open_Duck_Playground/playground/open_duck_mini_v2/xmls/open_duck_mini_v2_backlash.xml`
  - alternatív backlash modell; a jelenlegi bridge nem ezt tölti be real módban.
- `external/Open_Duck_Playground/playground/open_duck_mini_v2/xmls/joints_properties.xml`
  - külön joints_properties fragment; jelenleg eltér az összefűzött fő XML-ben található értékektől.
- `duck_agent_sim/simulator/duck_sim.py`
  - mock és real szimulátor, ONNX policy alkalmazása, sebességkorlát, vezérlési ciklus.
- `duck_agent_sim/simulator/command_mapper.py`
  - high-level parancs -> `ControlIntent(linear_x, linear_y, yaw)` mapping.
- `duck_agent_sim/schemas.py`
  - command schema, command-limit és safety-limit tartományok.
- `duck_agent_sim/vision/follower.py`
  - vizuális servo/follower PID-jellegű paraméterek.
- `README.md`
  - bridge architektúra és real MuJoCo/ONNX vezérlési leírás.

## Rövid összefoglaló

A real MuJoCo modellben 14 darab aktuált szabadsági fok van. Mindegyik aktuátor MuJoCo `<position>` típusú pozíció aktuátor, `class="sts3215"`, azonos joint névvel és `inheritrange="1"` beállítással. Ez azt jelenti, hogy a vezérlő bemenetének `ctrlrange` tartománya az adott joint mechanikai `range` értékéből öröklődik.

A futó `RealDuckSimulator` real módban a `scene_flat_terrain.xml` scene-t tölti be, amely az `open_duck_mini_v2.xml` robot XML-t include-olja. A bridge real módban 500 Hz MuJoCo physics stepet használ (`timestep = 0.002 s`), 50 Hz vezérlési ciklussal (`decimation = 10`, azaz 0.020 s). ONNX policy esetén a policy kimenete a home pózhoz képest pozíciócél-deltaként kerül alkalmazásra.

## Effektív STS3215 actuator default paraméterek

Az `open_duck_mini_v2.xml` effektív `sts3215` default értékei:

```xml
<default class="sts3215">
  <geom contype="0" conaffinity="0"/>
  <joint damping="0.56" frictionloss="0.068" armature="0.027"/>
  <position kp="13.37" kv="0.0" forcerange="-3.23 3.23"/>
</default>
```

Kompilált MuJoCo modellben ellenőrizve:

- actuator típus: position actuator mind a 14 aktuátornál
- `gainprm[0] = kp = 13.37`
- `biasprm = [0, -13.37, -0.0]`, azaz MuJoCo position servo formában `force = kp * (ctrl - qpos) - kv * qvel`, itt `kv = 0`
- `forcerange = [-3.23, 3.23]`
- joint paraméterek minden aktuált hinge jointnál:
  - `damping = 0.56`
  - `frictionloss = 0.068`
  - `armature = 0.027`

Megjegyzés: ugyanebben a fő XML-ben van egy `open_duck_mini_v2` default is `joint frictionloss="0.1" armature="0.005"` és `position kp="50" dampratio="1"` értékekkel, de az aktuált jointok és aktuátorok explicit `class="sts3215"` osztályt használnak, ezért a fenti STS3215 paraméterek a relevánsak.

## Actuator / joint mapping és tartományok

Minden aktuátor neve megegyezik a hozzá tartozó joint nevével. A `ctrlrange` az `inheritrange="1"` miatt a joint range-ből származik. A szögek radiánban vannak a MuJoCo XML-ben; a táblázat tartalmaz fokos átszámítást is.

| # | Actuator name | Joint | Típus | Joint / ctrl range [rad] | Joint / ctrl range [deg] | Home ctrl [rad] |
|---:|---|---|---|---:|---:|---:|
| 0 | `left_hip_yaw` | `left_hip_yaw` | position | -0.523599 .. 0.523599 | -30.0 .. 30.0 | 0.002 |
| 1 | `left_hip_roll` | `left_hip_roll` | position | -0.436332 .. 0.436332 | -25.0 .. 25.0 | 0.053 |
| 2 | `left_hip_pitch` | `left_hip_pitch` | position | -1.221730 .. 0.523599 | -70.0 .. 30.0 | -0.630 |
| 3 | `left_knee` | `left_knee` | position | -1.570796 .. 1.570796 | -90.0 .. 90.0 | 1.368 |
| 4 | `left_ankle` | `left_ankle` | position | -1.570796 .. 1.570796 | -90.0 .. 90.0 | -0.784 |
| 5 | `neck_pitch` | `neck_pitch` | position | -0.349066 .. 1.134464 | -20.0 .. 65.0 | 0.000 |
| 6 | `head_pitch` | `head_pitch` | position | -0.785398 .. 0.785398 | -45.0 .. 45.0 | 0.000 |
| 7 | `head_yaw` | `head_yaw` | position | -2.792527 .. 2.792527 | -160.0 .. 160.0 | 0.000 |
| 8 | `head_roll` | `head_roll` | position | -0.523599 .. 0.523599 | -30.0 .. 30.0 | 0.000 |
| 9 | `right_hip_yaw` | `right_hip_yaw` | position | -0.523599 .. 0.523599 | -30.0 .. 30.0 | -0.003 |
| 10 | `right_hip_roll` | `right_hip_roll` | position | -0.436332 .. 0.436332 | -25.0 .. 25.0 | -0.065 |
| 11 | `right_hip_pitch` | `right_hip_pitch` | position | -0.523599 .. 1.221730 | -30.0 .. 70.0 | 0.635 |
| 12 | `right_knee` | `right_knee` | position | -1.570796 .. 1.570796 | -90.0 .. 90.0 | 1.379 |
| 13 | `right_ankle` | `right_ankle` | position | -1.570796 .. 1.570796 | -90.0 .. 90.0 | -0.796 |

## Közös aktuátor paraméterek

| Paraméter | Érték | Forrás / megjegyzés |
|---|---:|---|
| Control mode | MuJoCo `position` actuator | mind a 14 aktuátor `<position class="sts3215" .../>` |
| `kp` | 13.37 | STS3215 actuator default |
| `kv` | 0.0 | STS3215 actuator default |
| Max torque / force | -3.23 .. 3.23 | `forcerange`; hinge jointnál gyakorlatilag nyomatéktartományként értelmezhető a MuJoCo aktuátorban |
| Joint damping | 0.56 | STS3215 joint default |
| Joint frictionloss | 0.068 | STS3215 joint default |
| Joint armature | 0.027 | STS3215 joint default |
| Actuator ctrlrange | joint range | `inheritrange="1"` minden aktuátoron |
| Gear | TODO / nincs explicit | az XML-ben nincs actuator `gear`; MuJoCo defaultot használ |
| Explicit actuator dynamics delay | TODO / nincs explicit az XML-ben | `dyntype=none` a kompilált modellben |
| Max motor velocity | 5.24 rad/s | real ONNX vezérlési rétegben alkalmazott célpozíció slew-rate limit |
| Célpozíció max változás 50 Hz ciklusonként | 0.1048 rad / 0.020 s | `5.24 * 0.002 * 10` |
| ONNX action scale | 0.25 rad | `motor_targets = default_actuator + action * 0.25` |

## Real MuJoCo / ONNX vezérlési lánc

A bridge nem közvetlenül nyers joint parancsokat vár az API-n. A nyilvános API high-level parancsokat fogad, amelyeket a `command_mapper.py` `ControlIntent` sebességcélokká alakít:

- `walk_forward`: `linear_x = speed`, `yaw = turn`
- `walk_backward`: `linear_x = -0.6 * speed`, `yaw = turn`
- `turn_left`: `linear_x = 0.2 * speed`, `yaw = max(abs(turn), 0.4)`
- `turn_right`: `linear_x = 0.2 * speed`, `yaw = -max(abs(turn), 0.4)`
- `stop`, `reset`, `look_around`: zéró lineáris és yaw cél

Real módban a `RealDuckSimulator` ezeket a high-level sebességcélokat simított belső célokká alakítja:

```python
current += (target - current) * 0.15
```

Ez a command-smoothing réteg 50 Hz-en fut. ONNX policy aktív állapotban az observation tartalmazza többek között a parancsvektort, joint szögeket, joint sebességeket, korábbi actionöket, motor targeteket, lábkontaktokat és imitációs fázist. A policy outputja:

```python
motor_targets = default_actuator + action * 0.25
```

Ezután a célpozíciók sebességkorlátozva vannak:

```python
max_motor_velocity = 5.24  # rad/s
sim_dt = 0.002
decimation = 10
motor_targets = clip(prev_target ± max_motor_velocity * sim_dt * decimation)
```

Végül:

```python
data.ctrl[:] = motor_targets
```

### Real mode időzítés

| Paraméter | Érték |
|---|---:|
| Physics timestep | 0.002 s / 500 Hz |
| Control decimation | 10 physics step |
| Control frequency | 50 Hz |
| State update | 50 Hz a physics loopban; README szerint WebSocket telemetria 10 Hz |
| Deadman timeout | 2.0 s parancs nélkül real loopban a target sebességek nullázódnak |
| `apply_command` polling / alvás | 0.05 s-os ciklusokkal várja ki a `duration_sec` időt |

## Mock mód paraméterek

A mock szimulátor nem használja a MuJoCo aktuátorokat és nem modellez explicit szervónyomatékot. A lépésidő ott `dt = 0.05 s`, és kinematikus testmozgást szimulál:

- reset pozíció: `(0.0, 0.0, 0.41)`
- moving esetén waddle frequency: `8.0 rad/s`
- roll waddle: `6.0 deg * sin(phase)`
- pitch waddle: `3.0 deg * cos(2*phase) + 2.0 deg`
- z bounce: `0.41 + 0.015 * sin(2*phase)`
- extrém trigger: `speed > 0.8` és `duration_sec > 5.0` esetén fallen állapotot injektál

Ez hasznos API- és safety-tesztekhez, de nem tekintendő aktuátor/servo fizikai specifikációnak.

## Backlash modell

A jelenlegi real bridge a `FLAT_TERRAIN_XML = scene_flat_terrain.xml` útvonalat tölti be, amely az `open_duck_mini_v2.xml` fájlt include-olja. Van külön backlash variáns is:

- `scene_flat_terrain_backlash.xml`
- `open_duck_mini_v2_backlash.xml`

A backlash variánsban a láb aktuált jointjai mellett dummy backlash jointok jelennek meg:

- `left_hip_yaw_backlash`, `left_hip_roll_backlash`, `left_hip_pitch_backlash`, `left_knee_backlash`, `left_ankle_backlash`
- `right_hip_yaw_backlash`, `right_hip_roll_backlash`, `right_hip_pitch_backlash`, `right_knee_backlash`, `right_ankle_backlash`

Backlash default:

```xml
<joint damping="0.01" frictionloss="0" armature="0.01" limited="true"
       range="-0.008726646259971648 0.008726646259971648"/>
```

Ez ±0.5° holtjátékot jelent. Fontos: a backlash XML-ben a fej/nyak jointokhoz nem látszik külön backlash dummy joint; a felsorolt dummy backlash jointok a két láb öt-öt aktuált jointját követik.

A backlash XML STS3215 actuator defaultja eltér a sima XML-től:

- `kp = 17.11`
- `kv = 0.0`
- `forcerange = [-3.23, 3.23]`
- `damping = 0.56`, `frictionloss = 0.068`, `armature = 0.027`

A külön `joints_properties.xml` fragment még régebbi / alternatív értékeket tartalmaz:

- `kp = 17.8`
- `forcerange = [-3.35, 3.35]`
- `damping = 0.60`, `frictionloss = 0.052`, `armature = 0.028`

Ezért dokumentációs szempontból az effektív, betöltött `open_duck_mini_v2.xml` értékeket kell elsődlegesnek tekinteni, és a fragmentet / backlash XML-t verzióeltérésként kell kezelni.

## Vizuális follower / servo paraméterek

A vision-guided follower nem joint-level servo, hanem high-level sebesség/yaw servo, amely a detektált cél bbox hibájából `ControlIntent`-et állít elő, majd `active_simulator.step(...)` hívással adja át a szimulátornak.

Alapértékek:

| Paraméter | Érték |
|---|---:|
| Loop period | 0.1 s / 10 Hz |
| `target_label` | `person` |
| `follow_height` | 200 px |
| `height_tolerance` | 20 px |
| `center_deadzone` | 30 px |
| `deadman_timeout` | 1.0 s |
| `K_p_yaw` | 0.003 |
| `K_p_speed` | 0.002 |
| `max_speed` | 0.3 |
| backward speed clamp | -0.15 |
| `max_yaw` | 0.8 |
| yaw smoothing alpha | 0.3 |

## Saturációk, késleltetések, limitek

### API command schema

A public bridge API parancsainak Pydantic limitjei:

- `speed`: 0.0 .. 1.0, default 0.25
- `turn`: -1.0 .. 1.0, default 0.0
- `duration_sec`: 0.1 .. 10.0, default 1.0
- safety:
  - `stop_on_fall`: default true
  - `max_pitch_deg`: 0.0 .. 90.0, default 35.0
  - `max_roll_deg`: 0.0 .. 90.0, default 35.0

### MuJoCo / actuator saturáció

- Position actuator command tartomány: az aktuált joint range-ek, `inheritrange="1"`.
- Force / torque clamp: `forcerange = [-3.23, 3.23]` minden STS3215 aktuátoron.
- ONNX célpozíció slew-rate limit: legfeljebb 5.24 rad/s, azaz 0.1048 rad / 50 Hz control tick.
- ONNX action scale: ±0.25 rad skálázás a policy output egységére nézve, mielőtt a slew-rate limit klippeli.

### Késleltetések / simítások

- Real control-loop smoothing: 50 Hz-en `alpha = 0.15` target velocity low-pass jelleggel.
- Real deadman timeout: 2.0 s parancs nélkül célsebességek nullázása.
- Follower deadman timeout: 1.0 s célvesztés után stop.
- Follower yaw smoothing: exponential smoothing `yaw_smoothed = 0.3 * prev_yaw + 0.7 * yaw_target`.
- Training / playground `standing.py` noise config tartalmaz `action_min_delay = 0`, `action_max_delay = 3`, `imu_min_delay = 0`, `imu_max_delay = 3` env step értékeket, de ez a jelenlegi bridge real runtime kódjában nem aktív késleltetésként jelenik meg.

## Nyitott kérdések / TODO

1. TODO: Fizikai STS3215 szervó adatlap alapján ellenőrizni kell, hogy a MuJoCo `forcerange = ±3.23` pontosan milyen hardveres nyomatékegységnek / áttételnek felel meg. A modell hinge actuatornál nyomatékként használja, de nincs dokumentálva gear ratio vagy motor elektromos modell.
2. TODO: Az XML-ben nincs explicit actuator `gear`. Meg kell erősíteni, hogy MuJoCo default `gear=1` szándékos-e, vagy hiányzó robot-specifikus áttétel.
3. TODO: A `joints_properties.xml`, `open_duck_mini_v2.xml` és `open_duck_mini_v2_backlash.xml` eltérő STS3215 paramétereket tartalmaz. El kell dönteni, melyik a forrásigazság, és a fragmentet érdemes-e szinkronizálni a ténylegesen include-olt fő XML-lel.
4. TODO: Az ONNX policy output tartománya nincs dokumentálva a modell fájl mellett. Az `action_scale = 0.25` alapján feltételezhető normalizált action, de a pontos tanítási/export kontraktust dokumentálni kell.
5. TODO: Fej/nyak aktuátorokhoz a bridge ONNX parancsvektorban van hely (`neck_pitch`, `head_pitch`, `head_yaw`, `head_roll`), de a jelenlegi real bridge `_get_onnx_obs` fix 0.0 head targeteket ad. Dönteni kell, hogy ezek aktívan vezérelhetők legyenek-e.
6. TODO: A mock mód és real mód testmagassága eltér (`0.41` mock reset vs `0.15` real home keyframe). Dokumentálni kell, hogy ez szándékos absztrakció vagy összehangolandó érték.
7. TODO: A backlash modell nincs bekötve a jelenlegi `RealDuckSimulator` default útvonalába. Ha realisztikusabb szervó holtjáték kell, konfigurálhatóvá kell tenni a `FLAT_TERRAIN_BACKLASH_XML` betöltését.
8. TODO: A README 10 Hz WebSocket telemetriát említ, míg a real physics loop 50 Hz-en frissíti a belső state-et. A WebSocket broadcast tényleges frekvenciáját külön ellenőrizni és dokumentálni kell.
