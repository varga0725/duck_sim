# Open Duck Mini v2 & Backend Szimulációs Rendszer: Teljes Feature Dokumentáció

Ez a dokumentum az **Open Duck Mini v2** robot szimulációs híd (Duck Agent Bridge) backend architektúrájának és funkcionalitásának átfogó leírása. A rendszer célja, hogy magas szintű parancsfelületet (REST/WebSockets) biztosítson autonóm AI ágensek (pl. OpenClaw, Hermes vagy egyéni LLM felügyelők) számára a robot vezérléséhez, stabilizálásához, érzékeléséhez és interaktív hangalapú irányításához.

---

## 1. Szimulációs Módok (Simulation Modes)

A rendszer három különböző üzemmódot támogat a `DUCK_SIM_MODE` környezeti változó beállításától függően:

### A. Mock Mód (`DUCK_SIM_MODE=mock`)
* **Leírás**: Egy teljesen kinematikus, determinisztikus szimuláció, amely nem igényel fizikai motor (MuJoCo) vagy ONNX neurális hálós függőségeket.
* **Működés**:
  - A robot mozgását előre definiált trigonometrikus egyenletekkel szimulálja (waddle/bounce effektusok).
  - Alapértelmezett stabil kezdőmagasság Z = `0.41 m`.
  - A lábkontaktok kinematikusan váltakoznak mozgás közben.
  - Tartalmaz egy beépített biztonsági teszt-triggert: ha a sebesség meghaladja a `0.8`-at és a parancs időtartama hosszabb, mint `5.0` másodperc, a rendszer szándékosan instabil (elesett) állapotot szimulál.
* **Cél**: Ideális gyors API-integrációs tesztekhez, biztonsági preflight ágensek ellenőrzéséhez, valamint folyamatos integrációs (CI) környezetekhez.

### B. Real MuJoCo Mód (`DUCK_SIM_MODE=real`)
* **Leírás**: Teljes fizikai szimuláció a MuJoCo motor és a `scene_flat_terrain.xml` környezeti modell segítségével.
* **Működés**:
  - A fizikai motor 500 Hz-en fut (`timestep = 0.002 s`).
  - A magas szintű parancsok feldolgozása és a vezérlőhurok (policy/oscillator) 50 Hz-en fut (`decimation = 10` lépésenként).
  - **ONNX Locomotion Policy**: Ha a `DUCK_ONNX_MODEL_PATH` be van állítva (alapértelmezetten a `BEST_WALK_ONNX_2.onnx` modell), a rendszer egy 101 elemű observation vektorból 14 motor célértéket generál. A kimeneti akciókat $\pm 0.25$ rad skálázási tényezővel alkalmazza a home keyframe púpjához képest, slew-rate korlátozással (`5.24 rad/s` szögsebesség-limit).
  - **Kinematic Waddle Oscillator**: Ha nincs ONNX modell konfigurálva, egy szabályos láblendítő és csípőbillegtető kinematikus oszcillátor hajtja meg a lábakat az organikus és élethű mozgás érdekében.
  - A talpkontaktusok a MuJoCo fizikai ütközésvizsgálatából származnak (`foot_assembly` és `foot_assembly_2` body-k kontaktusa a padlóval).

### C. Webcam Mód (`DUCK_SIM_MODE=webcam`)
* **Leírás**: Hibrid üzemmód, ahol a robot fizikai állapota a kinematikus Mock Mód szabályait követi, de a kamera és észlelési pipeline a host gép valódi webkamerájából veszi a videó képeket.

---

## 2. 500Hz-es Aktív Törzs-Stabilizáció és Magasságzár

Real MuJoCo módban a lábak talajjal való ütközései hatalmas felborító forgatónyomatékot és destabilizációt okozhatnak. A 100%-os stabilitás érdekében a rendszer egy **500Hz-es aktív giroszkópos szabályozási és magasságzár réteget** futtat közvetlenül a MuJoCo fizikai loopban (`_stabilize_torso()` a `LegacyDynamicsController` segítségével):

* **Aktív Magasságzár (Z-Forcing)**: A robot törzsének magasságát minden fizikai lépésben rögzítjük `0.15 m` magasságon, megakadályozva, hogy a robot összeessen vagy kontrollálhatatlanul lebegni kezdjen.
* **Törzsdőlési Korlátok (Roll/Pitch Overwrite)**: A törzs Roll dőlését maximum $\pm 6.0$ fokra, a Pitch dőlését maximum $\pm 4.0$ fokra szorítjuk be.
* **Szoftveres Giroszkópos Csillapítás**: A törzs dőlési szögsebességét minden egyes fizikai lépésben nullázzuk (`qvel[3] = 0.0` és `qvel[4] = 0.0`). Ez azonnal elnyeli az eleséshez vezető oszcillációkat.
* **Kinematikus Yaw Követés**: Az irányszög (yaw) integrálását kinematikusan és közvetlenül a 500Hz-es ciklusban végezzük a magas szintű parancsok alapján. Ez teljesen kiküszöböli a fizikai ütközésekből eredő nem kívánt forgási csúszást (yaw drift).
* **Eredmény**: A robot soha nem dől el, miközben az ONNX és kinematikus járás által keltett finom, természetes kamerabillegés teljesen megmarad.

---

## 3. Magas Szintű Locomotion Bridge API (REST & WebSockets)

A backend FastAPI-ra épül, és az alábbi funkciókat látja el:

### A. Parancsleképezés (Command Mapping)
A robot kizárólag magas szintű parancsokat fogad a `/command` endpointon:
- `walk_forward`: előrehaladás speed skálázással.
- `walk_backward`: hátramenet csökkentett sebességgel (`-0.6 * speed`).
- `turn_left` / `turn_right`: kanyarodás és kismértékű előrehaladás kombinációja.
- `stop`: azonnali megállás, a waddle időzítési ciklusok nullázása.
- `reset`: a MuJoCo fizika alaphelyzetbe állítása (settle steps), ágensek térképének törlése.

### B. Automatikus Parancskorlátozás (Command Clamping)
A backend a magas szintű parancsok fogadásakor a `POLICY_COMMAND_LIMITS` konstansok alapján automatikusan lekorlátozza a célelmozdulási sebességeket:
- `linear_x` (előre/hátra sebesség): `[-0.15, 0.15]` m/s
- `linear_y` (oldalirányú sebesség): `[-0.20, 0.20]` m/s
- `yaw` (forgási sebesség): `[-1.00, 1.00]` rad/s
Ez garantálja, hogy a robot neurális hálója ne kapjon a betanított tartományon kívüli parancsokat.

### C. Konzervatív Biztonsági Kapuőr (Preflight Guard)
Minden mozgási vagy autonóm követési parancs indítása előtt lefut a preflight állapotellenőrzés:
- Ha elesett állapot (`fallen=true` vagy `status="fallen"`), nem megfelelő Z magasság vagy túl nagy roll/pitch dőlés tapasztalható, a parancs végrehajtása blocked.
- Elesés esetén a rendszer azonnali **Emergency Stop + Reset** helyreállítást futtat.

### D. Részletes Szenzortelemetria (`GET /sensors/state`)
Az endpoint strukturált formában szolgáltatja a robot fizikai szenzorainak nyers állapotát (IMU és lábszenzorok). `mock` és `webcam` módban a szenzorok elérhetősége `available=false`, míg `real` módban közvetlenül a MuJoCo adatfolyamából töltődnek (pl. gyro, accelerometer, local/global velocities, position, orientation, up/forward vectors).

### E. WebSockets Telemetria (`ws://localhost:8765/ws`)
Folyamatos, alacsony késleltetésű **10Hz-es állapot-stream**, amelyen keresztül az ágensek valós időben megkapják a robot koordinátáit, orientációját és elesési állapotát, valamint közvetlenül küldhetnek vissza JSON formátumú irányítási parancsokat.

---

## 4. Vizuális Érzékelés és Követés (Perception & Servoing)

A robot fejébe épített **FPV Kamera** (First-Person View) jelenti az elsődleges szenzort az autonóm navigációhoz:

### A. FPV Kamera Paraméterek
- **Elhelyezkedés**: A fej egységben (`head_assembly`), lokális eltolása a fej középpontjához képest: `[0.08, 0.0, 0.05]` méter.
- **Orientáció**: Pontosan előre néz, lokális quaternion: `[0.70710678, 0.0, 0.0, -0.70710678]` (xyaxes: `0 -1 0 1 0 0`).
- **Látószög (FOV)**: `45.0` fokos vertikális látószög.
- **Képformátum**: 640x480 pixel felbontású RGB frame (átalakítva JPEG formátumra a `/vision/frame` streameléséhez).

### B. Érzékelési Pipeline (YOLOv8n + Centroid Tracker)
A háttérben futó 10Hz-es perception thread folyamatosan futtatja a YOLOv8n neurális hálót. Az észlelésekhez a Centroid Tracker persistent ID-kat rendel, így a robot képes stabilan megkülönböztetni egymástól a látómezőben lévő objektumokat (pl. `person`, `chair`).

### C. Ground-Truth 3D Projection (Valós Idejű 3D Vetítés)
Mivel a gyári YOLOv8n modellt valódi fényképekre tervezték, a szimulált MuJoCo szoba stilizált elemeit (pl. fakockákból álló asztal, szék) önmagában nem észlelné megbízhatóan. 
A probléma megoldására a `YOLODetector` real módban egy **Ground-Truth 3D Projection** modullal egészíti ki a képet:
1. Lekéri a MuJoCo-ból a szék, asztal, labda és ember 3D geometriai csúcspontjait (pl. box corners, sphere vertices).
2. Az FPV kamera belső paramétereit (látószög, fókusztávolság) használva levetíti a 3D pontokat a 2D képsík pixel-koordinátáira.
3. Kiszámítja a pixelcsoportok minimális és maximális határait, és ebből pixel-pontos 2D bounding boxot rajzol.
4. Ezeket az észleléseket `0.99` (99%) konfidenciával augmentálja a YOLO kimenetek közé, így a robot azonnal és megbízhatóan felismeri a célpontokat.

### D. Autonóm Követő és Aktív Pásztázás (Vision Guided Follower)
A `/vision/follow/start` paranccsal indítható el az autonóm követés.
* **Proporcionális Szabályozó (P-Controller)**:
  - **Forgás (Yaw)**: Ha a célpont vízszintes eltérése (`error_x`) meghaladja a `30 px` deadzone-t, proporcionális kanyarodást indít: `yaw_target = -K_p_yaw * error_x` (ahol `K_p_yaw = 0.003`, maximum `0.8` rad/s, exponenciális szűrővel simítva).
  - **Sebesség (Speed)**: A célpont 2D bounding box magasságát (`last_target_box_height`) használja távolsági proxyként. Ha a magassági eltérés meghaladja a `20 px` toleranciát, előre vagy hátra indul: `speed_target = K_p_speed * error_h` (ahol `K_p_speed = 0.002`, előre max `0.3` m/s, hátra max `-0.15` m/s). Kanyarodáskor a sebesség 40%-ra csökken.
* **Aktív Pásztázás (Active Scanning)**: Ha a célpont eltűnik:
  1. A robot a céltartomány utolsó ismert iránya alapján helyben forogni kezd (`search_yaw_speed = 0.4` rad/s), és aktívan pásztázza a szobát.
  2. Ha a `search_timeout` (alapértelmezetten `15.0` másodperc) lejárta előtt meglátja a célpontot, a követés azonnal folytatódik.
  3. Ha az idő lejár és nem találja meg, a robot megáll (`STOPPED` állapot).

---

## 5. Spatial World Model (Térképészet és Landmarks)

A robot egy belső **2D Occupancy Grid (foglaltsági rács)** térképet és egy **Szemantikus Landmark Memóriát** tart fenn a környezet feltérképezéséhez:

* **Térkép Paraméterek**: A rács `100x100` cellás, a felbontása `0.05 m` (5 cm per cella), a színtér közepe a szimulált világ originjére van igazítva. A cellaérték `0` a szabad, `1` a foglalt (falak, akadályok) területre.
* **Szemantikus Landmarkok**: A YOLO és 3D vetítés alapján felismert objektumok globális 3D pozícióit (`[x, y, z]` méterben) a robot elmenti a landmark memóriába. Az egymást követő észlelések zajait egy **EMA (Exponential Moving Average)** szűrő simítja ki, így a szék vagy labda becsült pozíciója folyamatosan stabilizálódik.
* **Végpontok**: A `GET /map` visszaadja a teljes rácsmátrixot és a landmarkok listáját, a `POST /map/reset` pedig kiüríti a térképet.

---

## 6. Magyar Hangvezérlés és Multi-Modális Beszéd (Speech Stack)

A robot egy fejlett, magyar nyelvű beszéd-interakciós réteggel rendelkezik, amely a `scripts/start_voice_simulation.sh` segítségével futtatható:

* **Dual Speech Recognition Engine (Kettős Beszédfelismerés)**:
  - **Online Google Web Speech API**: Az elsődleges hangfelismerő motor `hu-HU` támogatással. Közel 100%-os pontosságú magyar tranzakciókat tesz lehetővé CPU terhelés és késleltetés nélkül.
  - **Offline OpenAI Whisper Engine**: Ha nincs internetkapcsolat, a rendszer automatikusan átvált a helyi Whisper motorra (pl. `--model base`, `--model small`), így a hangvezérlés teljesen offline környezetben is működőképes marad.
* **Gyorsított Mikrofon Ingress (Instant Listening)**: A háttérzaj kalibrációja csak az indításkor fut le egyszer, megszüntetve a korábbi 1 másodperces hangfelvételi fagyásokat a ciklusok között.
* **Regex-alapú Biztonsági Szűrő**: A magyar nyelvű kifejezések elemzésekor a tiltó és leállító szavak (pl. *"ne kövesd"*, *"állj meg"*) abszolút prioritást élveznek, kizárva a szavak átfedéséből eredő téves indításokat.
* **macOS Tünde TTS (Text-to-Speech)**: A robot visszajelzései a macOS prémium minőségű beépített magyar női hangján (**Tünde**) szólalnak meg a gép hangszóróján. A beszédhangok cache-elése a `.hermes/cache/duck_robot` mappában történik.
* **Interaktív Spoken Loop**: Ha a Hermes ágens aktív, a felhasználó mikrofonba mondott kérdéseit (pl. *"Látsz valamilyen széket a szobában?"*) a hangvezérlő továbbítja az ágensnek. Az ágens válaszát a rendszer nem csak kiírja, hanem hangosan fel is olvassa a MacBook hangszóróján keresztül, megteremtve a folyamatos párbeszédet a robottal.
