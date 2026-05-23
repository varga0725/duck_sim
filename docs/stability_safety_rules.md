# Open Duck Mini v2 stabilitási, fallen-detection és reset szabályok

Ez a dokumentum a Duck Agent Bridge biztonságos üzemeltetési és diagnosztikai szabályait rögzíti a `/Users/vargaferenc/Desktop/duck_sim` projektben. A dokumentum célja, hogy minden robotirányító agent ugyanazt a stabilitási modellt, fallen/unstable detektálást és stop+reset protokollt kövesse.

Kötelező vezérlési szabály: az agent kizárólag magas szintű Duck Agent Bridge API parancsokat használhat. Tilos nyers joint, motor, PWM, servo, actuator, `data.ctrl`, `qpos` vagy `qvel` parancsot kiadni futó robotnak. A `qpos`/`qvel` ebben a dokumentumban csak belső MuJoCo állapotként és diagnosztikai fogalomként szerepel.

## Rövid összefoglaló

- Biztonságos vezérlési felület: `GET /state`, `POST /command`, `POST /stop`, `POST /reset`, illetve a `scripts/duck_bridge_tool.py` wrapper.
- Ajánlott agent-eszköz: `python3 scripts/duck_bridge_tool.py ...`, mert preflight állapotellenőrzést végez, és instabil/fallen állapotban stop+reset helyreállítást indít.
- Stabil állapot: `fallen=false`, `status` nem `fallen`, roll/pitch küszöb alatt, Z magasság nem esett össze, kontaktok a módnak és mozgásfázisnak megfelelőek.
- A publikus `RobotState.stability` contract géppel olvasható formában publikálja a stabilitási státuszt (`stable`, `unstable`, `fallen`), okkódokat és a használt safety thresholdokat.
- Ha a robot elesett vagy instabil: azonnal stop, majd reset; az eredetileg kért mozgást nem szabad ugyanabban a lépésben tovább erőltetni.

## Érintett fájlok és források

- `duck_agent_sim/schemas.py`: parancs- és állapotsémák (`RobotCommand`, `SafetyConfig`, `RobotState`, `FeetContact`).
- `duck_agent_sim/simulator/safety.py`: fallen logika (`is_fallen`, `should_auto_stop`).
- `duck_agent_sim/simulator/duck_sim.py`: mock és real sim reset/stop/apply_command/state update logika.
- `duck_agent_sim/bridge/api.py`: REST endpointok (`/state`, `/command`, `/stop`, `/reset`, `/scenario/walk-square`).
- `scripts/duck_bridge_tool.py`: agent-safe CLI wrapper, preflight + post-command safety recovery.
- `external/Open_Duck_Playground/playground/open_duck_mini_v2/xmls/scene_flat_terrain.xml`: real MuJoCo home keyframe és terrain contact/friction beállítások.

## 1. Stabil kezdőállapot és reset állapot

### Mock mód

A mock szimulátor resetje stabil, kinematikus kezdőállapotot állít be:

- robot: `open_duck_mini_v2`
- status: `idle`
- sim_time: `0.0`
- position: `(0.0, 0.0, 0.41)`
- orientation: roll `0.0°`, pitch `0.0°`, yaw `0.0°`
- feet_contact: left `true`, right `true`
- fallen: `false`
- last_command: `reset`

Stop után mock módban:

- status: `stopped`
- last_command: `stop`
- roll/pitch nullázva
- mindkét láb kontakt `true`
- pozíció megmarad, Z stabilan `0.41` körül van

Mock módban mozgás közben a szimulátor szándékosan waddle/bounce mozgást modellez:

- roll körülbelül ±6°
- pitch körülbelül pár fokos előredőlés/rezgés
- Z körülbelül `0.41 ± 0.015 m`
- lábkontaktok váltakozhatnak; egy-egy láb átmeneti elemelkedése normális lehet

### Real MuJoCo mód

Real módban a MuJoCo modell a `home` keyframe-ből indul:

- freejoint base qpos eleje: `x=0`, `y=0`, `z=0.15`
- orientáció kvaternió: `1 0 0 0`
- joint célértékek: a `home.ctrl` és a `home.qpos` actuator részei azonos alapállást adnak
- qvel: reset után `mj_resetData`, majd home qpos/ctrl beállítás és 50 settle lépés

A bridge real reset logikája:

1. `mujoco.mj_resetData(model, data)`
2. `data.qpos[:] = home_key.qpos`
3. `data.ctrl[:] = home_key.ctrl`
4. 50 MuJoCo step a beállás/settle miatt
5. célsebességek nullázása
6. last_command = `reset`
7. kimeneti `RobotState` frissítése

Fontos: real módban a stabil Z magasság a modell koordinátarendszere miatt alacsonyabb (`~0.15 m` home), mint mock módban (`~0.41 m`). Ezért a magasságküszöb módonként eltér.

## 2. Fallen/unstable detektálás

A bridge állapota a `RobotState` mezőkből olvasható:

- `status`: `idle`, `walking`, `turning`, `stopped`, `fallen`, `resetting`
- `position`: `[x, y, z]`
- `orientation`: `roll_deg`, `pitch_deg`, `yaw_deg`
- `feet_contact`: `left`, `right`
- `fallen`: boolean
- `last_command`: utolsó magas szintű parancs

### Kötelező fallen feltételek

A `duck_agent_sim/simulator/safety.py:is_fallen` szerint fallen, ha bármelyik igaz:

1. `state.fallen == true`
2. `abs(roll_deg) > max_roll_deg`
3. `abs(pitch_deg) > max_pitch_deg`
4. `position[2] < height_threshold`

Alap safety küszöbök a sémában:

- `stop_on_fall = true`
- `max_pitch_deg = 35.0`
- `max_roll_deg = 35.0`

Magasságküszöb a simulator safety modulban:

- real mód: `position[2] < 0.08` fallen
- mock/webcam mód: `position[2] < 0.15` fallen

Agent wrapper (`scripts/duck_bridge_tool.py`) konzervatívabb operátori preflight küszöböt használ:

- real mód effective min height: `0.10`
- mock/webcam mód effective min height: `0.25`
- roll/pitch instabil, ha `abs(roll) >= max_roll` vagy `abs(pitch) >= max_pitch`
- instabil, ha `fallen=true` vagy `status == "fallen"`

A wrapper szándékosan szigorúbb, mint a belső safety: agent irányításnál előbb állítson meg és reseteljen, mint hogy a robot a fizikai fallen határig romoljon.

### Contact feltételek

Kontaktok szerepe:

- Mock módban `FeetContact(left,right)` kinematikus jel: álláskor mindkettő true, mozgás közben a waddle fázis miatt egyik láb átmenetileg false lehet.
- Real módban a kontakt `check_contact("foot_assembly", "floor")` és `check_contact("foot_assembly_2", "floor")` MuJoCo contact listából jön.
- Mindkét láb kontaktvesztése, különösen alacsony Z-vel vagy nagy roll/pitch-csel együtt, instabilitási indikátor.

Javasolt agent interpretáció:

- Álló/reset utáni robotnál elvárt: legalább stabil Z, roll/pitch közel 0, és lehetőleg mindkét láb kontakt.
- Mozgás közben egy láb kontaktvesztése lehet normális gait-fázis.
- Mindkét láb kontaktvesztése + Z összeesés vagy roll/pitch küszöbátlépés: fallen/unstable.
- Kontakt önmagában ne írja felül a hivatalos `fallen`, `status`, height, roll, pitch feltételeket; inkább diagnosztikai jelként kezeld.

## 3. Publikus Stability API contract

A `GET /state` válasz `RobotState` objektuma most tartalmaz egy `stability` mezőt is. Ez nem váltja ki a régi `fallen`, `status`, `position`, `orientation` és `feet_contact` mezőket; azok továbbra is stabil API részek. A `stability` mező ezekből készített, géppel olvasható összegzés.

Példa stabil mock állapotra:

```json
{
  "stability": {
    "status": "stable",
    "reasons": [],
    "min_body_height_m": 0.15,
    "internal_fallen_min_body_height_m": 0.15,
    "agent_preflight_min_body_height_m": 0.25,
    "freshness_sec": null,
    "thresholds": {
      "max_roll_deg": 35.0,
      "max_pitch_deg": 35.0,
      "min_body_height_m": 0.15,
      "agent_preflight_min_body_height_m": 0.25,
      "state_freshness_timeout_sec": null,
      "require_feet_contact": false
    }
  }
}
```

### `stability.status`

- `stable`: nincs ismert stability/safety ok.
- `unstable`: nem belső fallen, de agent preflight, kontakt vagy freshness guard sérül. Ilyenkor az agent ne indítson mozgást automatikusan.
- `fallen`: a belső fallen safety feltételek valamelyike teljesül.

### `stability.reasons` okkódok

Belső fallen okok (`status="fallen"`):

- `fallen_flag`: `RobotState.fallen == true`.
- `fallen_status`: `RobotState.status == "fallen"`.
- `roll_exceeds_max`: `abs(orientation.roll_deg) > thresholds.max_roll_deg`.
- `pitch_exceeds_max`: `abs(orientation.pitch_deg) > thresholds.max_pitch_deg`.
- `body_height_below_min`: `position[2] < thresholds.min_body_height_m`.

Unstable / preflight okok (`status="unstable"`, ha nincs fallen ok):

- `body_height_below_agent_preflight_min`: a robot a belső fallen magasság felett van, de az agent preflight guard alatt.
- `no_feet_contact`: kontaktusértékelésnél egyik láb sem érintkezik.
- `state_stale`: explicit freshness értékelésnél az állapot idősebb a megadott timeoutnál.

### Publikált thresholdok

- `thresholds.max_roll_deg`, `thresholds.max_pitch_deg`: a használt dőlésküszöbök.
- `thresholds.min_body_height_m` és `min_body_height_m`: az effektív belső fallen magasságküszöb. Alapértelmezés: real `0.08 m`, mock/webcam `0.15 m`.
- `thresholds.agent_preflight_min_body_height_m` és `agent_preflight_min_body_height_m`: a konzervatív agent guard. Alapértelmezés: real `0.10 m`, mock/webcam `0.25 m`.
- `SafetyConfig.min_body_height_m`: opcionális parancs/safety override a belső fallen magasságküszöbre. Ha `null`, a mód szerinti alapérték érvényes.

Fontos architekturális különbség: a belső fallen threshold (`min_body_height_m`) azt jelzi, mikor minősül a robot elesettnek a safety monitor szerint. Az agent preflight guard (`agent_preflight_min_body_height_m`) szigorúbb operátori korlát; alatta az agent már ne indítson mozgást, de ez önmagában még nem feltétlenül `fallen`.

## 4. Stop + reset protokoll

Minden mozgás vagy autonóm követés előtt állapotot kell olvasni. A preferált út:

```bash
cd /Users/vargaferenc/Desktop/duck_sim
python3 scripts/duck_bridge_tool.py state
```

Majd magas szintű parancs csak akkor adható, ha a robot stabil:

```bash
python3 scripts/duck_bridge_tool.py command walk_forward --speed 0.25 --duration 1.0
```

A `duck_bridge_tool.py command ...` automatikusan:

1. `GET /state` preflight ellenőrzést futtat
2. ellenőrzi: `fallen`, `status`, roll, pitch, Z
3. instabil állapotban `POST /stop`, majd `POST /reset`
4. instabil preflight esetén nem hajtja végre az eredetileg kért mozgást
5. stabil preflight esetén elküldi a magas szintű `/command` kérést
6. parancs után ellenőrzi a visszaadott állapotot
7. ha a parancs destabilizált, azonnal stop+reset helyreállítást végez

Kézi REST használatnál ugyanez a protokoll kötelező:

1. `GET /state`
2. Ha instabil/fallen: `POST /stop`
3. Ezután `POST /reset`
4. Újra `GET /state`
5. Csak stabil állapot után lehet új, magas szintű mozgást kérni

Nem megengedett:

- Fallen állapotban további `walk_forward`, `turn_left` stb. próbálgatás.
- `stop_on_fall=false` használata agent irányításnál.
- Nyers `qpos`, `qvel`, `data.ctrl`, joint angle vagy motor target kiadása vezérlésként.
- A reset utáni instabil állapot figyelmen kívül hagyása.

## 5. Real/sim mód különbségei

### `DUCK_SIM_MODE=mock`

- Kinematikus, determinisztikus mock.
- Stabil reset Z: `0.41`.
- Safety threshold belül: mock height threshold `0.15`; agent wrapper preflight min height `0.25`.
- Extrém mock parancs (`speed > 0.8` és `duration_sec > 5.0`) szándékosan fallen állapotot okozhat: pitch `48°`, roll `20°`, Z `0.10`, mindkét láb kontakt false.
- Mozgás közben waddle és váltakozó lábkontakt normális.

### `DUCK_SIM_MODE=webcam`

- A testállapot a safe mock logikát követi.
- A `/vision/frame` a host webcamet használja.
- Stabilitási szabályok a mock body-state alapján értendők.
- Webcam/vision instabilitás nem azonos robot fallen állapottal, de autonóm követésnél a follow loopot meg kell állítani, ha a body-state instabil.

### `DUCK_SIM_MODE=real`

- MuJoCo physics + Open Duck Mini v2 XML + opcionális ONNX policy.
- Home Z: `~0.15`.
- Safety threshold belül: real height threshold `0.08`; agent wrapper preflight min height `0.10`.
- Physics loop 500 Hz timestep (`0.002 s`), state update kb. 50 Hz.
- **500Hz-es aktív giroszkópos törzs-stabilizáció és magasságzár**: A törzs fizikai dőlését és magasságát közvetlenül a MuJoCo 500Hz-es fizikai integrációs ciklusában szabályozzuk (`_stabilize_torso()`).
  - **Törzsmagasság-zár**: A Z magasságot minden fizikai lépésben `0.15 m` értéken tartjuk, megelőzve az összeesést vagy a lebegést.
  - **Dőlési korlátok**: A törzs Roll dőlését maximum $\pm 6$ fokra, a Pitch dőlését maximum $\pm 4$ fokra korlátozzuk.
  - **Szögsebesség-csillapítás (Szoftveres Giroszkóp)**: A törzs Roll és Pitch szögsebességét minden lépésben nullázzuk (`qvel[3] = 0.0` és `qvel[4] = 0.0`), ami elnyeli a lépések ütközéseiből származó borító forgatónyomatékot.
  - **Kinematikus Yaw követés**: Az irányszög (yaw) integrálását kinematikusan és közvetlenül végezzük a 500Hz-es ciklusban a parancsok alapján, elkerülve a fizikai driftet.
- Kontaktok valós MuJoCo contactból jönnek.
- Reset után is előfordulhat azonnali instabilitás; ilyen esetben stop+reset után sem szabad mozgást folytatni, amíg a diagnosztika nem tisztázta az okot.
- macOS-on látható MuJoCo viewerhez `mjpython` szükséges; sima python/uvicorn viewer hibát okozhat.

## 6. Contact és friction paraméterek

A flat terrain XML releváns beállításai:

- Floor geom: `contype="1"`, `conaffinity="0"`, `priority="1"`, `friction="0.6"`, `condim="3"`.
- Dinamikus objektumok/falak a jelenetben `contype="1"`, `conaffinity="1"` értékekkel szerepelhetnek.
- Robot default joint paraméterek több helyen: `frictionloss`, `armature`, `damping`, position actuator `kp`, `dampratio` vagy `forcerange`.
- Backlash modellekben ±0.5° backlash joint range szerepelhet.

Diagnosztikai jelentőség:

- Túl alacsony floor friction vagy hibás kontaktpárosítás csúszást, lábkontaktvesztést, yaw/forward mozgási anomáliát okozhat.
- Túl nagy friction/contact damping esetén a policy vagy kinematikai rásegítés nehezen indítja meg a robotot.
- Kontakt ellenőrzés névfüggő: real módban a kód `foot_assembly`, `foot_assembly_2` és `floor` body neveket keres. Néveltérés esetén a kontakt false lehet akkor is, ha vizuálisan érintkezés látszik.

## 7. Ismert reset utáni instabilitási okok

Lehetséges okok és diagnosztikai lépések:

1. Rossz mód vagy rossz bridge folyamat fut
   - Ellenőrizd: `python3 scripts/duck_bridge_tool.py health`
   - Nézd meg a `sim_mode` értéket.
   - Portütközésnél (`address already in use`) előbb a régi bridge-et kell leállítani.

2. Real mód home pose nem stabil a fizikában
   - Ellenőrizd reset után: Z, roll, pitch, feet_contact.
   - Ha Z `0.10` alatt vagy roll/pitch gyorsan nő, ne adj mozgást.
   - Vizsgáld a home keyframe-et, joint defaultokat, actuator ctrl értékeket és 50 settle step utáni állapotot.

3. Kontakt név vagy contact mask eltérés
   - Real módban `check_contact` body neveket használ.
   - Ha mindkét kontakt false stabilnak tűnő állásnál, ellenőrizd a MuJoCo body/geom neveket és floor contact beállításokat.

4. Túl agresszív parancs vagy túl hosszú duration
   - Agent default legyen konzervatív: speed `0.25`, duration `1.0` körül.
   - Kerüld a nagy speed + hosszú duration kombinációt.

5. ONNX policy/action mapping eltérés
   - Ellenőrizd observation vektor sorrendjét, action scale-t, actuator sorrendet, joint címeket és motor target limitet.
   - Real mód policy esetén ne állíts át action mappinget anélkül, hogy külön body technical contract készült volna.

6. Viewer vagy macOS launch probléma
   - Látható MuJoCo passive viewerhez `mjpython` kell.
   - Ha viewer hiba után processz kilép, ne feltételezd, hogy real mód stabilan fut; ellenőrizd health/state alapján.

7. Webcam/vision versenyhelyzet
   - Webcam módban több processz ne olvassa közvetlenül ugyanazt a kamerát.
   - A `/vision/frame` lehetőleg a FrameBuffer legutóbbi frame-jét szolgálja ki.
   - Vision hiba nem robot fallen, de follow loopnál deadman/stop logika szükséges.

8. Hangvezérlés és interaktív beszélgetési biztonsági szűrők
   - **Regex-alapú priorizálás**: A beérkező magyar nyelvű hangparancsok kiértékelésénél a tiltó/leállító parancsok (pl. *"ne kövesd tovább"*, *"állj"*) elsőbbséget élveznek, megakadályozva, hogy a szavak átfedése miatt téves mozgási parancs fusson le.
   - **Google Web Speech API & Whisper Fallback**: Elsődleges a Google online hangfelismerője (`hu-HU`). Internetkapcsolat hiányában a rendszer automatikusan és zökkenőmentesen átvált a lokális Whisper modellre.
   - **Zajszűrés és Kalibráció**: A mikrofon zajszint-kalibrációja csak a legelső indításkor történik meg, kiküszöbölve a korábbi 1.0 másodperces fagyásokat a parancsvételi ciklusok között.
   - **macOS Tünde TTS**: A visszajelzések és a Hermes válaszok felolvasása a macOS beépített magyar női hangján (Tünde - `hu_HU`) történik. Az előállított AIFF audio fájlok a `.hermes/cache/duck_robot` mappában tárolódnak.

## 8. Ajánlott operátori parancsok

Bridge állapot:

```bash
cd /Users/vargaferenc/Desktop/duck_sim
python3 scripts/duck_bridge_tool.py health
python3 scripts/duck_bridge_tool.py state
```

Biztonságos stop/reset:

```bash
python3 scripts/duck_bridge_tool.py stop
python3 scripts/duck_bridge_tool.py reset
python3 scripts/duck_bridge_tool.py state
```

Biztonságos rövid mozgás:

```bash
python3 scripts/duck_bridge_tool.py command walk_forward --speed 0.25 --duration 1.0
python3 scripts/duck_bridge_tool.py command turn_left --speed 0.25 --turn 1.0 --duration 1.0
```

Teljes embodied snapshot:

```bash
python3 scripts/duck_bridge_tool.py sense
```

## 9. Ellenőrző checklist

### Preflight minden mozgás/follow/scenario előtt

- [ ] A munkakönyvtár `/Users/vargaferenc/Desktop/duck_sim`.
- [ ] A bridge health ellenőrizve (`/health` vagy `duck_bridge_tool.py health`).
- [ ] A robot state ellenőrizve (`/state` vagy wrapper preflight).
- [ ] `fallen == false`.
- [ ] `status != "fallen"`.
- [ ] `abs(roll_deg) < 35.0`.
- [ ] `abs(pitch_deg) < 35.0`.
- [ ] Z magasság mód szerint elfogadható: mock/webcam agent preflightnál legalább `0.25`, real agent preflightnál legalább `0.10`.
- [ ] Kontaktok nem jeleznek nyilvánvaló összeesést; álló/reset után elvárható legalább stabil kontaktkép.
- [ ] Csak magas szintű parancs szerepel: `walk_forward`, `walk_backward`, `turn_left`, `turn_right`, `stop`, `reset`, `look_around`.
- [ ] `safety.stop_on_fall == true`.

### Ha instabil vagy fallen

- [ ] Ne adj új mozgásparancsot.
- [ ] Állítsd meg: `python3 scripts/duck_bridge_tool.py stop` vagy `POST /stop`.
- [ ] Reseteld: `python3 scripts/duck_bridge_tool.py reset` vagy `POST /reset`.
- [ ] Olvasd vissza az állapotot.
- [ ] Ha reset után is instabil, ne folytasd; diagnosztizáld a módot, Z-t, roll/pitch-et, kontaktokat, bridge processzt és real-mode policy/contact beállításokat.

### Post-command ellenőrzés

- [ ] A parancs response `state` mezője ellenőrizve.
- [ ] Ha a parancs után `fallen=true`, `status="fallen"`, nagy roll/pitch vagy alacsony Z látszik, stop+reset megtörtént.
- [ ] Nem történt nyers joint/motor/qpos/qvel/data.ctrl vezérlés.
- [ ] Follow/scenario parancs után a follower/scenario állapot nem hagy mozgó instabil robotot.

## 10. Döntési fa

1. Kell mozgás vagy autonóm follow?
   - Igen: előbb state preflight.
   - Nem: csak olvasás/diagnosztika engedélyezett.

2. Preflight stabil?
   - Nem: stop + reset, majd állapot visszaolvasás. Az eredeti mozgás nem fut.
   - Igen: magas szintű parancs konzervatív paraméterekkel.

3. Post-command stabil?
   - Nem: azonnali stop + reset.
   - Igen: kész, de következő parancs előtt ismét preflight szükséges.

4. Reset után is instabil?
   - Igen: ne vezéreld tovább; bridge/mód/contact/policy/home pose diagnosztika.
   - Nem: csak új felhasználói vagy workflow lépés alapján folytatható.
