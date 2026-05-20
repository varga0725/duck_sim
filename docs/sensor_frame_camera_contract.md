# Open Duck Mini v2 szenzor-, frame-, kamera- és érzékelési szerződés

Ez a dokumentum a `duck_agent_sim` bridge és az alatta használt `external/Open_Duck_Playground` MuJoCo modell alapján rögzíti, hogy milyen szenzoradatokra, frame-ekre, kamera-adatokra és perception/follower telemetriára támaszkodhat a magas szintű Duck Agent Bridge API.

Források:

- `duck_agent_sim/schemas.py`
- `duck_agent_sim/simulator/duck_sim.py`
- `duck_agent_sim/bridge/api.py`
- `duck_agent_sim/vision/*.py`
- `external/Open_Duck_Playground/playground/open_duck_mini_v2/xmls/open_duck_mini_v2.xml`
- futtatott MuJoCo modell-introspekció a lokális `.venv` környezetben

Fontos biztonsági szerződés: az agent és a külső kliens számára a támogatott vezérlési felület a magas szintű bridge API (`/command`, `/stop`, `/reset`, `/scenario/walk-square`, `/vision/follow/*`). Nyers joint-, actuator-, qpos-, qvel-, PWM- vagy motorparancsot nem szabad parancsfelületként kiadni.

## 1. Koordináta- és frame-konvenciók

### 1.1 Bridge `RobotState` frame

A publikus `GET /state` válasz `RobotState` mezői:

- `position`: `(x, y, z)` méterben.
  - Mock módban kinematikus világkoordináta; reset után `(0.0, 0.0, 0.41)`.
  - Real/MuJoCo módban a floating base `qpos[0:3]` alapján képzett világpozíció; reset után a MuJoCo `home` keyframe-ből jön, majd a shared state frissíti.
- `orientation`: roll/pitch/yaw fokban.
  - Real/MuJoCo módban a floating base quaternion `qpos[3:7]` Euler-konverziója.
  - `yaw_deg` 0..360 tartományba normalizált.
- `feet_contact`: bal/jobb talpkontaktus boolean.
- `fallen`: biztonsági monitor által jelzett esés/instabilitás.
- `status`: magas szintű állapot (`idle`, `walking`, `turning`, `stopped`, `fallen`, `resetting`).
- `last_command`: utolsó magas szintű parancs azonosítója.

A publikus állapot nem teszi közzé külön a sebességvektort. Real módban a belső ringbufferben van `velocity = (_current_linear_x, _current_linear_y, _current_yaw_rate)`, de ez jelenleg nem API-mező.

### 1.2 MuJoCo világ- és site-frame-ek

A MuJoCo `frame*` szenzorok jelentése a modellben:

- `framepos`: objektum/site pozíciója világframe-ben.
- `framequat`: objektum/site orientációja világframe-ben quaternionként.
- `framelinvel`: objektum/site lineáris sebessége világframe-ben.
- `frameangvel`: objektum/site szögsebessége világframe-ben.
- `framexaxis` / `framezaxis`: az objektum/site adott lokális tengelyének világframe-beli iránya.

A `gyro`, `accelerometer` és `velocimeter` szenzorok az `imu` site-hoz vannak kötve. A publikus bridge `orientation` nem közvetlenül az `orientation` nevű IMU `framequat` szenzorból jön, hanem a floating base quaternionból számolt roll/pitch/yaw.

## 2. IMU / gyro / accelerometer helye és orientációja

### 2.1 IMU site

MuJoCo XML:

```xml
<site name="imu" pos="-0.08 -0.0 0.05"/>
```

MuJoCo introspekció:

- site: `imu`
- parent body: `base`
- lokális pozíció a `base` bodyhoz képest: `[-0.08, -0.0, 0.05]` m
- lokális quaternion: `[1.0, 0.0, 0.0, 0.0]` (identity)

Következmény:

- Az IMU site a robot `base` bodyjához rögzített.
- Saját lokális orientációja nem forgatott a `base` bodyhoz képest.
- A gyro/accelerometer site-orientációját így a `base` body aktuális világorientációja határozza meg.

### 2.2 IMU-hoz kötött szenzorok

A modell 15 szenzort és összesen 46 `sensordata` komponenst tartalmaz. Az IMU szenzorok:

| index | név | MuJoCo szenzortípus | sensordata cím | dimenzió | objektum |
|---:|---|---|---:|---:|---|
| 0 | `gyro` | `gyro` | 0 | 3 | `site: imu` |
| 1 | `local_linvel` | `velocimeter` | 3 | 3 | `site: imu` |
| 2 | `accelerometer` | `accelerometer` | 6 | 3 | `site: imu` |
| 3 | `upvector` | `framezaxis` | 9 | 3 | `site: imu` |
| 4 | `forwardvector` | `framexaxis` | 12 | 3 | `site: imu` |
| 5 | `global_linvel` | `framelinvel` | 15 | 3 | `site: imu` |
| 6 | `global_angvel` | `frameangvel` | 18 | 3 | `site: imu` |
| 7 | `position` | `framepos` | 21 | 3 | `site: imu` |
| 8 | `orientation` | `framequat` | 24 | 4 | `site: imu` |

Real módban az ONNX policy observation jelenleg közvetlenül használja:

- `gyro = sensordata[gyro_addr:gyro_addr+3]`
- `accelerometer = sensordata[accelerometer_addr:accelerometer_addr+3]`
- `accelerometer[0] += 1.3` offsetkorrekcióval

A `local_linvel`, `upvector`, `forwardvector`, `global_linvel`, `global_angvel`, `position`, `orientation` szenzorok a MuJoCo modellben definiáltak, de a publikus REST state-ben jelenleg nincsenek külön mezőként publikálva.

## 3. Orientation, velocity és position szenzorok frame-jei

### 3.1 Publikus bridge mezők

| publikus mező | forrás mock módban | forrás real módban | frame / egység |
|---|---|---|---|
| `position` | kinematikusan integrált 2D pozíció + z-bounce | floating base `qpos[0:3]` | világframe, méter |
| `orientation.roll_deg` | mock waddle roll | floating base quaternionból | fok, base testorientáció |
| `orientation.pitch_deg` | mock waddle pitch | floating base quaternionból | fok, base testorientáció |
| `orientation.yaw_deg` | integrált yaw | floating base quaternionból, `% 360` | fok, világ Z körüli yaw |
| `feet_contact.left/right` | kinematikus alternáló kontaktus | MuJoCo kontaktusteszt | boolean |

### 3.2 MuJoCo IMU frame-szenzorok

| szenzor | dim | jelentés | frame |
|---|---:|---|---|
| `local_linvel` | 3 | IMU site lineáris sebessége lokális szenzorframe-ben | IMU/base-lokális |
| `global_linvel` | 3 | IMU site lineáris sebessége | világframe |
| `global_angvel` | 3 | IMU site szögsebessége | világframe |
| `position` | 3 | IMU site pozíciója | világframe |
| `orientation` | 4 | IMU site orientációja quaternionként | világframe |
| `upvector` | 3 | IMU lokális Z tengelye világkoordinátában | világframe-beli irányvektor |
| `forwardvector` | 3 | IMU lokális X tengelye világkoordinátában | világframe-beli irányvektor |

Megjegyzés: mivel az `imu` site identity quaternionnal van a `base` bodyra rögzítve, ezek az IMU frame-adatok a base body orientációját követik.

## 4. Foot contact / foot position / foot velocity definíciók

### 4.1 Foot site-ok

MuJoCo introspekció:

| site | parent body path vége | lokális pozíció | lokális quaternion |
|---|---|---|---|
| `left_foot` | `... / foot_assembly` | `[0.0005, -0.036225, 0.01955]` | `[0.70710678, -0.70710678, 0, ~0]` |
| `right_foot` | `... / foot_assembly_2` | `[0.0005, -0.036225, 0.01955]` | `[0.70710678, -0.70710678, 0, ~0]` |

### 4.2 Foot position és velocity MuJoCo szenzorok

| index | név | MuJoCo szenzortípus | sensordata cím | dimenzió | objektum |
|---:|---|---|---:|---:|---|
| 9 | `right_foot_global_linvel` | `framelinvel` | 28 | 3 | `site: right_foot` |
| 10 | `left_foot_global_linvel` | `framelinvel` | 31 | 3 | `site: left_foot` |
| 11 | `left_foot_upvector` | `framexaxis` | 34 | 3 | `site: left_foot` |
| 12 | `right_foot_upvector` | `framexaxis` | 37 | 3 | `site: right_foot` |
| 13 | `left_foot_pos` | `framepos` | 40 | 3 | `site: left_foot` |
| 14 | `right_foot_pos` | `framepos` | 43 | 3 | `site: right_foot` |

A foot position és foot velocity szenzorok világframe-ben értendők, mert `framepos` és `framelinvel` típusúak.

Megjegyzés: a `left_foot_upvector` és `right_foot_upvector` név ellenére a típus `framexaxis`, tehát a site lokális X tengelyének világframe-beli irányát adja, nem `framezaxis`-t. Ezt dokumentációs/névadási eltérésként kell kezelni.

### 4.3 Publikus foot contact definíció

Mock módban:

- mozgás közben a waddle roll alapján alternál:
  - `left_foot_touch = (roll_waddle >= -1.0)`
  - `right_foot_touch = (roll_waddle <= 1.0)`
- álló helyzetben mindkét láb kontaktusban van.
- esésnél mindkét kontaktus `false`.

Real/MuJoCo módban:

- `left_contact = check_contact("foot_assembly", "floor")`
- `right_contact = check_contact("foot_assembly_2", "floor")`
- a `check_contact` végigiterál a MuJoCo `data.contact` listán, és azt vizsgálja, hogy a két body-hoz tartozó geometriák között van-e aktív kontaktus.

Következmény: a publikus `feet_contact.left/right` nem a `left_foot_pos` vagy `right_foot_pos` szenzor z-koordinátájából számolt threshold, hanem explicit kontaktuspár-vizsgálat real módban, illetve mock waddle állapot mock módban.

## 5. Kamera intrinsics/extrinsics

### 5.1 Képkocka szerződés

A `/vision/frame` endpoint JPEG-et ad vissza.

Aktív frame méret:

- real MuJoCo render: 640x480 RGB frame a `mujoco.Renderer(..., height=480, width=640)` alapján.
- webcam mód: OpenCV `VideoCapture(0)` 640x480 célfelbontással; BGR -> RGB konverzió után kerül a pipeline-ba.
- mock mód: generált 640x480 RGB frame.

A `/vision/frame` implementáció a background `FrameBuffer` legfrissebb frame-jét preferálja, hogy macOS-en ne legyen több konkurens webcam olvasó. A JPEG encoding előtt RGB -> BGR OpenCV konverzió történik.

### 5.2 Real MuJoCo FPV kamera extrinsics

MuJoCo XML:

```xml
<camera name="fpv" pos="0.08 0 0.05" xyaxes="0 -1 0 1 0 0" mode="fixed"/>
```

MuJoCo introspekció:

- kamera: `fpv`
- parent body: `head_assembly`
- lokális pozíció a `head_assembly` bodyhoz képest: `[0.08, 0.0, 0.05]` m
- lokális quaternion: `[0.70710678, 0.0, -0.0, -0.70710678]`
- `fovy`: `45.0` fok
- `ipd`: `0.068` m
- fixed camera

Az XML `xyaxes` jelentése: a kamera lokális X és Y tengelye van megadva. Itt:

- camera local X axis: `[0, -1, 0]`
- camera local Y axis: `[1, 0, 0]`
- a lokális Z/nézési tengelyt MuJoCo ezekből származtatja.

A camera világ-extrinsics a `head_assembly` aktuális pose-ától is függ; a fenti adatok a fejhez rögzített lokális extrinsics.

### 5.3 Intrinsics

Elérhető/deriválható intrinsics adatok:

- render méret: `width=640`, `height=480`
- vertikális látószög real MuJoCo `fpv` kameránál: `fovy=45.0°`

A kódban nincs explicit kamera-mátrix (`fx`, `fy`, `cx`, `cy`) vagy torzítási modell publikálva. Ha pinhole közelítést kell használni a MuJoCo real kamerára, a jelenlegi adatokból tipikusan származtatható:

- `cy ≈ height / 2 = 240`
- `cx ≈ width / 2 = 320`
- `fy ≈ (height / 2) / tan(fovy / 2)`
- `fx` az aspect ratio és feltételezett square pixels alapján számolható

Ez azonban nincs API-szerződésként rögzítve, ezért lásd a hiányzó adatok listáját.

Webcam módban az intrinsics és extrinsics nincsenek kalibrálva. A host kamera csak 640x480 RGB képforrásként szerepel; fizikai kamera pozíció/orientáció nincs szerződésben.

## 6. Perception/follower telemetria és kapcsolata a magas szintű bridge API-val

### 6.1 Perception pipeline

Induláskor a simulator létrehozza és elindítja a background vision loopot:

```text
CameraDevice -> FrameBuffer -> YOLODetector -> CentroidTracker -> PerceptionState
```

Frekvencia:

- `VisionLoop(..., target_fps=10.0)`
- a dokumentált cél 5-15 FPS, a jelenlegi konstruktorhívás 10 FPS.

Módok:

- `mock`: generált classroom frame + determinisztikus mock detekciók (`chair`, `person`).
- `webcam`: host webcam 640x480 frame, YOLOv8n detektor.
- `real`: MuJoCo `fpv` kamera render, fallback a default/free kamerára, YOLOv8n detektor.

### 6.2 Perception endpointok

`GET /vision/state`:

```json
{
  "num_objects": 2,
  "tracked_ids": [1, 2],
  "labels": ["person", "chair"],
  "vision_fps": 9.6,
  "last_update_sec": 0.082
}
```

Mezők:

- `num_objects`: aktuális detekciók száma.
- `tracked_ids`: aktív tracking ID-k, ahol `tracking_id != -1`.
- `labels`: látható objektumkategóriák halmaza.
- `vision_fps`: rolling perception FPS.
- `last_update_sec`: utolsó perception update óta eltelt idő.

`GET /vision/detections`:

```json
{
  "objects": [
    {
      "label": "person",
      "confidence": 0.93,
      "bbox": [404.0, 170.0, 484.0, 380.0],
      "tracking_id": 2
    }
  ]
}
```

A belső detekció tartalmaz `center` mezőt is, de a REST `/vision/detections` jelenleg csak `label`, `confidence`, `bbox`, `tracking_id` mezőket publikál.

### 6.3 Follower endpointok és állapotgép

`POST /vision/follow/start` elindítja a `VisionGuidedFollower` 10 Hz-es háttér loopját. Ez perception detekciókból képez sebesség- és yaw-parancsot, majd az aktív simulator `step(ControlIntent, dt=0.1, safety=SafetyConfig())` hívásával mozgatja a robotot.

Follower állapotok:

- `SEARCHING`: follower fut, cél keresése indul.
- `TRACKING`: cél megvan, távolsági deadzone-on belül, lineáris sebesség 0, centerezés történhet.
- `FOLLOWING`: cél megvan, bbox magasság alapján előre/hátra mozgás szükséges.
- `LOST`: cél eltűnt, deadman timer fut.
- `STOPPED`: follower leállt vagy deadman timeout után megállította a simulatort.

`GET /vision/follow/status` mezők:

- `active`: fut-e a follower thread.
- `state`: állapotgép mód.
- `target_id`: konfigurált tracker ID szűrő (`-1` = bármely/legjobb címke).
- `active_target_id`: jelenleg követett tracking ID.
- `target_label`: követendő label, alapértelmezés `person`.
- `error_x`: cél középpontjának vízszintes hibája pixelben; pozitív = cél jobbra.
- `error_h`: `follow_height - bbox_height`; pozitív = cél túl kicsi/távol van.
- `last_target_box_height`: utolsó cél bbox magasság pixelben.
- `commanded_linear_x`: follower által kért lineáris x sebesség.
- `commanded_yaw`: follower által kért yaw rate.
- `lost_duration_sec`: célvesztés időtartama.

Vezérlési kapcsolat:

- centerezés: ha `abs(error_x) > center_deadzone`, `yaw_target = -K_p_yaw * error_x`, `[-max_yaw, max_yaw]` közé clampelve.
- távolság: ha `abs(error_h) > height_tolerance`, `linear_x_target = K_p_speed * error_h`; előre max `max_speed`, hátra max `-0.15`.
- agresszív fordulásnál (`abs(error_x) > 2 * center_deadzone`) a lineáris sebesség 40%-ra csökken.
- yaw smoothing: exponenciális szűrő `yaw_smooth_alpha` paraméterrel.
- célvesztés: `deadman_timeout` után `active_simulator.stop()`.

Alapértelmezett follower paraméterek:

| paraméter | érték |
|---|---:|
| `target_label` | `person` |
| `target_id` | `-1` |
| `follow_height` | `200.0` px |
| `height_tolerance` | `20.0` px |
| `center_deadzone` | `30.0` px |
| `deadman_timeout` | `1.0` s |
| `K_p_yaw` | `0.003` |
| `K_p_speed` | `0.002` |
| `max_speed` | `0.3` |
| `max_yaw` | `0.8` |
| `yaw_smooth_alpha` | `0.3` |

## 7. Minden parancs előtt ellenőrizendő állapotmezők

Minden magas szintű mozgás, scenario vagy follower indítás előtt kötelező `GET /state` ellenőrzés, vagy olyan helper használata, amely ezt elvégzi.

Ellenőrizendő mezők:

1. `fallen == false`
   - Ha `true`: azonnali `POST /stop`, majd `POST /reset`; ne induljon mozgás ugyanabban a lépésben.
2. `status != "fallen"`
   - Ha `fallen`: stop + reset.
3. `abs(orientation.roll_deg) <= safety.max_roll_deg`
   - alapértelmezett limit: `35.0°`.
4. `abs(orientation.pitch_deg) <= safety.max_pitch_deg`
   - alapértelmezett limit: `35.0°`.
5. `position[2]` ne legyen összeesett testmagasság.
   - `duck_agent_sim/simulator/safety.py` szerint az esésküszöb real módban `0.08 m`, mock/webcam módban `0.15 m`.
   - mock reset magasság: `0.41 m`.
   - real MuJoCo home/base magasság eltérhet; a stabilitást a safety monitor szerint kell értelmezni.
   - Operátori/agent oldali óvatos preflightnál érdemes ennél magasabb guardot használni, de a kódban rögzített fallen-küszöb a fenti érték.
6. `feet_contact.left/right`
   - nem feltétlenül kell mindkettőnek `true` mozgás közben, mert járás közben váltakozhat; de esésnél vagy instabil állapotnál gyanús, ha mindkettő `false`.
7. `last_command` és `status`
   - ha korábbi follower/scenario futásból maradt mozgó állapot gyanítható, előbb `stop`.

Perception/follower indítás előtt plusz ellenőrzések:

1. `GET /vision/state`
   - `last_update_sec` legyen friss.
   - `vision_fps` legyen nem nulla/reális.
2. `GET /vision/detections`
   - legyen a `target_label`-nek megfelelő detekció, ha azonnali követés szükséges.
3. `GET /vision/follow/status`
   - ha már `active=true`, ne indíts párhuzamos follower logikát; előbb `follow/stop`, majd új konfigurációval start.

## 8. Hiányzó vagy nem szerződésként rögzített adatok

Az alábbi adatok részben elérhetők belsőleg vagy levezethetők, de jelenleg nincsenek stabil, publikus bridge API-szerződésként dokumentálva/publikálva:

1. Kamera intrinsics teljes mátrixa:
   - `fx`, `fy`, `cx`, `cy`, skew, distortion coefficients.
   - Real MuJoCo módban `fovy=45°` és 640x480 felbontás ismert, de pinhole mátrix nincs explicit API-ban.
2. Webcam intrinsics/extrinsics:
   - nincs kalibrációs adat, torzítási modell vagy robothoz viszonyított transzform.
3. Kamera extrinsics publikus endpointja:
   - real MuJoCo XML-ből ismert a `fpv` lokális extrinsics a `head_assembly` bodyhoz képest, de nincs `/camera/info` vagy hasonló endpoint.
4. Publikus IMU raw stream:
   - `gyro`, `accelerometer`, `local_linvel`, `global_linvel`, `global_angvel`, `position`, `orientation` szenzorok léteznek MuJoCo-ban, de a REST API jelenleg nem adja vissza őket külön.
5. Publikus foot position / foot velocity stream:
   - MuJoCo szenzorok léteznek (`left_foot_pos`, `right_foot_pos`, `*_global_linvel`), de a REST API csak `feet_contact` booleant publikál.
6. Sebességmező a `RobotState`-ben:
   - a feladatban szereplő `velocity` frame jelenleg csak belső `_ringbuffer` snapshotban létezik, nem publikus schema mező.
7. Pontos safety height threshold API-szinten:
   - a parancs safety schema csak roll/pitch limitet tartalmaz; a helper és `is_fallen` logika külön z-height küszöböt is használhat, de ez nem része a `SafetyConfig` schema-nak.
8. Frame névkonvenciók formális leírása:
   - a világframe tengelyirányai és a robot forward/lateral/up tengelyek nincsenek külön REP-szerű dokumentumban rögzítve.
9. Szenzor covariance/noise modell:
   - a MuJoCo szenzorokhoz és perception detekciókhoz nincs publikált zajmodell vagy covariance.
10. Time synchronization:
   - nincs explicit timestamp minden camera frame-hez, detekcióhoz, follower parancshoz és robot state-hez közös clockkal; csak `sim_time`, `last_update_sec` és belső wall-clock alapú loopok vannak.

## 9. Javasolt API-bővítések a szerződés stabilizálására

1. `GET /sensors/state` endpoint:
   - IMU raw: gyro, accelerometer, local/global velocities, framequat.
   - foot raw: foot positions, velocities, up/axis vectors.
   - timestamp/sim_time.
2. `GET /camera/info` endpoint:
   - width, height, fovy, fx/fy/cx/cy, distortion, camera frame neve.
   - real módban `fpv -> head_assembly -> base` transform.
   - webcam módban kalibráció hiánya explicit `calibrated=false` mezővel.
3. `RobotState.velocity` publikus mező:
   - legalább commanded velocity és/vagy estimated base velocity külön jelölve.
4. Safety schema kiegészítés:
   - `min_body_height_m` és opcionális kontaktus/freshness limitek.
5. Perception timestamp mezők:
   - frame timestamp, detection timestamp, follower control timestamp.

## 10. Rövid üzemeltetési checklist

Mozgás vagy follower indítás előtt:

```text
1. /health: status ok, várt sim_mode.
2. /state: fallen=false, status nem fallen, roll/pitch limit alatt, z nem összeesett.
3. Ha instabil: /stop -> /reset, és ne folytasd automatikusan a mozgást.
4. Vision/follower esetén: /vision/state friss, /vision/follow/status nem ütközik meglévő aktív followerrel.
5. Csak magas szintű bridge parancsot használj.
```
