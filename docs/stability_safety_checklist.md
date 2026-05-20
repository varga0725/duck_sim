# Open Duck Mini v2 stabilitási és reset ellenőrző checklist

Ez a checklist a részletes szabálydokumentum rövid, futtatás előtti/utáni ellenőrző listája.

Kapcsolódó dokumentum: `docs/stability_safety_rules.md`

## Alapszabály

- [ ] Csak magas szintű Duck Agent Bridge API parancsokat használok.
- [ ] Nem adok ki nyers joint/motor/servo/PWM/`data.ctrl`/`qpos`/`qvel` vezérlést.
- [ ] Mozgás, scenario vagy follower előtt mindig állapotot ellenőrzök.

## Preflight minden mozgás/follow/scenario előtt

- [ ] Munkakönyvtár: `/Users/vargaferenc/Desktop/duck_sim`.
- [ ] Bridge health ellenőrizve: `python3 scripts/duck_bridge_tool.py health`.
- [ ] Robot state ellenőrizve: `python3 scripts/duck_bridge_tool.py state`.
- [ ] `state.stability.status == "stable"`, vagy ha nem stabil, a `state.stability.reasons` oklistát kezelem és nem indítok mozgást.
- [ ] `fallen == false`.
- [ ] `status != "fallen"`.
- [ ] `abs(roll_deg) < 35.0`.
- [ ] `abs(pitch_deg) < 35.0`.
- [ ] Z magasság megfelelő:
  - [ ] mock/webcam belső fallen threshold: `state.stability.min_body_height_m == 0.15`, agent preflight: `state.stability.agent_preflight_min_body_height_m == 0.25`
  - [ ] real belső fallen threshold: `state.stability.min_body_height_m == 0.08`, agent preflight: `state.stability.agent_preflight_min_body_height_m == 0.10`
- [ ] Kontaktok nem jeleznek nyilvánvaló összeesést.
- [ ] `safety.stop_on_fall == true`.
- [ ] A tervezett parancs a megengedett listából való: `walk_forward`, `walk_backward`, `turn_left`, `turn_right`, `stop`, `reset`, `look_around`.

## Ha instabil vagy fallen

- [ ] Nem küldök további mozgásparancsot.
- [ ] Stop: `python3 scripts/duck_bridge_tool.py stop`.
- [ ] Reset: `python3 scripts/duck_bridge_tool.py reset`.
- [ ] Visszaellenőrzés: `python3 scripts/duck_bridge_tool.py state`.
- [ ] Ha reset után is instabil, nem folytatom a vezérlést; diagnosztika szükséges.

## Post-command ellenőrzés

- [ ] A parancs response `state` mezőjét ellenőriztem.
- [ ] Nem lett `fallen=true`.
- [ ] `status` nem `fallen`.
- [ ] Roll/pitch továbbra is küszöb alatt van.
- [ ] Z magasság nem esett a mód szerinti limit alá.
- [ ] Ha a parancs destabilizált, stop+reset megtörtént.

## Reset utáni diagnosztika, ha továbbra is instabil

- [ ] `health.sim_mode` ellenőrizve (`mock`, `webcam`, `real`).
- [ ] Nincs portütközés vagy rossz bridge processz a `8765` porton.
- [ ] Real módban a `home` pose és a `home.ctrl` stabilitása ellenőrizendő.
- [ ] Real módban foot/floor contact nevek és contact maskok ellenőrizendők.
- [ ] Real módban ONNX policy/action mapping csak body technical contract alapján módosítható.
- [ ] macOS real viewer esetén `mjpython` használata szükséges.
