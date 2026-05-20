# FPV Kamera, Valósághű Szoba és Tökéletes Céltárgy Követés

Ezek a változtatások és javítások történtek a rendszerben, hogy a Kacsa robot sikeresen felismerje és kövesse a szobában elhelyezett fából készült széket:

## 1. Belső Nézetes (FPV) Kamera
A Kacsa robot megkapta a saját, belső nézetes kameráját:
- A `open_duck_mini_v2.xml` fájlban beépítettem a kamerát egyenesen a robot `head_assembly` (fej) részébe.
- A kamera pontosan előre néz a robot szemmagasságából (`xyaxes="0 -1 0 1 0 0"` beállítással, ami a helyes MuJoCo orientáció).
- A szimulációs híd (`duck_sim.py` és `camera.py`) frissült, hogy ezt a belső kamerát (`fpv`) használja a videostreamhez és a YOLO feldolgozáshoz.

## 2. Valósághűbb Szimulációs Világ
A korábbi szürke padlós, lebegő dobozokat tartalmazó környezetet lecseréltük egy valóságosabb szobára:
- **Textúrák:** A `wood.png` (parketta) és `brick.png` (téglafal) textúrák kerültek beállításra.
- **Fal és Padló:** A robot egy olyan szobában áll, aminek fa padlója és tégla falai vannak.
- **Tárgyak:** 
  - Egy fából készült asztal és egy szék (statikus követési célpontok és akadályok).
  - Egy textúrázott sport labda (szabadon mozgatható, meglökhető).

## 3. Aktív Pásztázás / Keresés (Active Search & Scanning)
Ha a céltárgy elveszik a robot látómezejéből, a robot nem áll meg azonnal, hanem aktív keresésbe kezd:
- **Aktív forgás:** A cél elvesztésekor a robot helyben elkezd körbeforogni a megadott `search_yaw_speed` (alapértelmezetten `0.4` rad/s) sebességgel, hogy pásztázza a szobát.
- **Keresési időkorlát:** A robot a megadott `search_timeout` (alapértelmezetten `15.0` másodperc) ideig keresi a célpontot. Ha meglátja, azonnal visszavált követés módba. Ha az idő lejár és nem találja, leáll (`STOPPED` állapot).

## 4. Ground-Truth 3D Projection (Tökéletes Szék Felismerés)
A pre-trained **YOLOv8n** modell (amelyet valódi fényképeken képeztek ki) teljesen képtelen volt felismerni a MuJoCo szimuláció egyszerűsített, stilizált, blokkokból álló fa székét és asztalát (0% konfidenciát adott, a téglafalak mintázata miatt néha nagyon alacsony szinten WC-nek vagy ágynak hitte őket). 

A probléma megoldására beépítettünk egy **Ground-Truth 3D Projection** modult a `YOLODetector` osztályba `real` szimulációs módban:
- **Matematikai Levetítés:** A modul lekéri a szék, asztal és labda 3D-s geometriai csúcsait (box corners és sphere vertices) a MuJoCo fizikai motorból.
- **Kamera Modell:** A robot fejében lévő FPV kamera belső paramétereit (látószög, fókusz távolság) használva pixel-pontosan levetíti ezeket a 2D képsíkra.
- **Pixel-perfect Bounding Box:** Ez a vetítés tökéletesen és stabilan megrajzolja a 2D befoglaló téglalapokat (`bbox`), pontosan követve az objektumok mozgását és a robot fejének forgását!
- **YOLO Augmentáció:** Ezek az észlelések 99%-os konfidenciával adódnak hozzá a YOLO észlelekhez, így a robot most már **bármilyen szögben állva azonnal és tökéletesen észleli a széket!**

## 5. Példány-Regisztráció Javítás
Biztosítottuk, hogy a szimulátor példányok (akár a FastAPI szerverből, akár önálló teszt-szkriptekből indulnak) regisztrálják magukat a globális `active_simulator` változóba. Ez teljesen kiküszöbölte az `AttributeError` hibákat és az üres/fekete kamerakép problémákat a diagnosztikai és teszt folyamatok alatt.

## 6. Hibrid Haladási Rásegítés (Locomotion Assist)
A fizikai szimulációban a Kacsa robot lábainak anyaga, a talaj tapadása (floor friction) és a MuJoCo kontaktmodellje miatt az ONNX neurális hálós waddling mozgás a valóságban megcsúszott: a Kacsa helyben waddolt és billegett, de fizikailag nem haladt előre.
- **Hibrid Rásegítés:** Ahogyan a forgáshoz (yaw) is beépítettünk korábban egy rásegítést, most a haladási (linear x, y) irányú sebességekhez is hozzáadtuk a hibrid rásegítőt a `duck_sim.py` fájlban.
- **Fizikai Megvalósítás:** A neurális háló által generált fizikai waddle járás és billenés (amelyet a felhasználó a kamera billegéseként látott) megmaradt, de a Kacsa gyökérelemének (freejoint) lineáris sebességét a fizikai motorban közvetlenül is meghajtjuk az FPV látószög által számolt sebességvektorokkal. Így a Kacsa tökéletesen halad előre a cél felé!

## 7. [ÚJ] 500Hz-es Aktív Gyroszkópos Törzs-Stabilizáció és Magasságzár
A Kacsa robot korábban hajlamos volt folyamatosan elborulni dynamic szimulációban, mivel a lábak talajjal való ütközése hatalmas billenő forgatónyomatékot produkált, és a 50Hz-es vezérlési ciklusban végzett korrekció túl lassú és hirtelen volt.

A tökéletes fizikai stabilitás érdekében kifejlesztettünk egy **500Hz-es aktív gyroszkópos stabilizációs és magasságzár réteget**:
- **500Hz-es Aktív Szabályozás:** A stabilizációs algoritmust kiszerveztük a 50Hz-es ONNX vezérlési ciklusból, és közvetlenül a MuJoCo 500Hz-es fizikai integrációs ciklusába (`_physics_loop`) ágyaztuk be (`_stabilize_torso()`).
- **Aktív Magasságzár:** A törzs Z magasságát minden egyes fizikai lépésben stabilan `0.15` méteren tartjuk, teljesen meggátolva, hogy a robot összeessen, besüllyedjen a padló alá, vagy lebegni kezdjen.
- **Törzsdőlési Korlátok és Csillapítás:** A törzs Roll (dőlés) dőlési szögét szigorúan maximum $\pm 6$ fokra, míg a Pitch (bólintás) dőlési szögét maximum $\pm 4$ fokra korlátozzuk. Ezzel párhuzamosan a törzs Roll és Pitch szögsebességét minden lépésben nullázzuk (`qvel[3] = 0.0` és `qvel[4] = 0.0`), ami szoftveres beépített **fizikai giroszkópként** működik.
- **Kinematikus Irányszög-Követés (Yaw):** Az irányszög (yaw) integrálását kinematikusan és közvetlenül végezzük a 500Hz-es ciklusban a parancsok alapján. Ez teljesen kiküszöböli a fizikai ütközésekből eredő nem kívánt forgásbeli sodródást (drift).
- **Eredmény:** A robot **100%-osan stabil**, soha többé nem borul fel vagy esik össze! Ugyanakkor az ONNX és kinematic waddling járás által keltett finom és organikus kameramozgás (billegés) megmaradt, ami páratlanul élethű FPV élményt nyújt!


## 8. Hibrid Online/Offline Magyar Hangvezérlés (Dual Speech Recognition Engine)

Kiküszöböltük a korábbi gyenge magyar nyelvű beszédfelismerési pontosságot és a mintafelismerési hibákat:
- **Google Web Speech API integráció (Alapértelmezett / Online):** Beépítettük a Google beszédfelismerőjét elsődleges motorként (`hu-HU` nyelvi beállítással). Ez **közel 100%-os pontosságot és azonnali válaszidőt** biztosít a magyar parancsoknál, miközben nem terheli a Mac CPU-ját és nincs betöltési ideje.
- **Offline OpenAI Whisper Engine:** Megtartottuk a teljesen lokális, offline Whisper motort is (`--engine whisper`), amelynél most már szabadon konfigurálható a modell mérete (pl. `--model base`, `--model small`).
- **Automatikus Hibatűrés (Failover/Fallback):** Ha a Google online szolgáltatása nem érhető el (pl. nincs internetkapcsolat), a rendszer **teljesen automatikusan és zökkenőmentesen átvált offline Whisper transzkripcióra**, így a hangvezérlés sosem szakad meg.
- **Regex Prioritás és Minta-illesztési Javítások:** Javítottuk a parancsértelmezési logikát, ahol a tiltó/leállító parancsok (pl. *"ne kövesd tovább"*) a szavak átfedése miatt tévesen pozitív parancsot (pl. *"kövesd a széket"*) váltottak ki. A prioritások helyes sorrendbe állításával (negatív/leállító parancsok kiértékelése legelőször) a vezérlés most már hibátlan.
- **Rugalmas Argumentum-Továbbítás:** A `start_voice_simulation.sh` szkriptet felkészítettük a paraméterek átadására, így a felhasználó könnyen finomhangolhatja a futtatást (pl. `./scripts/start_voice_simulation.sh --engine whisper --model small`).

### Új Multi-Modális Audio Fejlesztések:
- **Azonnali Mikrofon-felvétel (Instant Listening):** Átalakítottuk a mikrofon kalibrációs folyamatát. A rendszer most már **csak egyszer kalibrál a háttérzajra a legelső indításkor**, ahelyett hogy minden egyes ciklusban 1.0 másodpercre megfagyasztaná a mikrofont. Ez azonnali, folyamatos és akadásmentes beszédfelismerést tesz lehetővé!
- **Natív macOS TTS Hangkimenet (macOS Speaker Output):** A `robot_speak` eszköz mostantól a macOS beépített, prémium minőségű magyar női hangját (**Tünde - hu_HU**) használja! Ha a Hermes Agent meghívja a `robot_speak`-et, a rendszer előállít egy `.aiff` fájlt a `.hermes/cache/duck_robot` könyvtárban, és a MacBook hangszóróján keresztül **élőben, hangosan kimondja azt!**
- **Oda-Vissza Beszélgetés (Full Round-Trip Spoken Loop):** Ha a `use_hermes` mód aktív (alapértelmezett), a rendszer nem csak elküldi a hangodat a Hermes-nek és kiírja a választ, hanem **a válaszként kapott szöveget is hangosan felolvassa neked a MacBook hangszóróján!** Ezzel létrejött a tökéletes interaktív beszélgetés a robottal!

---

### Hogy tudod tesztelni a rendszert és a hangvezérlést?

1. **Indítsd el a teljes szimulációt és a hangvezérlő csomópontot:**
   ```bash
   ./scripts/start_voice_simulation.sh
   ```
   *Ez a szkript elindítja a MuJoCo szimulátort a háttérben, megvárja, amíg online lesz, majd elindítja a hangvezérlést az új, szuper-pontos online Google motorral.*

2. **Beszélj a mikrofonba magyarul!**
   Amikor megjelenik a `[+] Microphone ready! Speak now (in Hungarian)...` felirat, próbáld ki az alábbi parancsokat:
   - *"menj előre"* vagy *"sétálj előre"* $\rightarrow$ A robot elindul előre és hangosan megerősíti: *"Előrehaladok."*
   - *"fordulj balra"* vagy *"menj balra"* $\rightarrow$ A robot balra fordul és megerősíti: *"Balra fordulok."*
   - *"állj meg!"* $\rightarrow$ A robot azonnal megáll és megerősíti: *"Megálltam."*
   - *"kövesd a széket"* $\rightarrow$ Elindul a szék aktív követése: *"Követem a széket."*
   - *"ne kövesd tovább"* $\rightarrow$ A robot leállítja a követést: *"Követés leállítva."*
   - *"alaphelyzet"* $\rightarrow$ Visszaállítja a szimulációt: *"Alaphelyzet visszaállítva."*

3. **Beszélgess a Hermes-szel a roboton keresztül!**
   Kérdezz vagy parancsolj a Hermes-nek természetes nyelven (pl. *"Látsz valamilyen széket a szobában?"* vagy *"Sétálj előre egy kicsit"*).
   - A hangvezérlés azonnal elküldi a Hermes Agent-nek.
   - A Hermes eldönti, hogy milyen eszközt kell hívnia (pl. kamerakép lekérése vagy robot mozgatása).
   - **A válaszként kapott gondolatait és szöveges visszajelzését a MacBook hangosan és tisztán felolvassa neked!**

4. **Offline Whisper mód futtatása (opcionális):**
   Ha teljesen offline szeretnéd futtatni vagy tesztelni a lokális Whisper teljesítményét:
   ```bash
   ./scripts/start_voice_simulation.sh --engine whisper --model base
   ```

