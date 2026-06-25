# MOZA HOTAS — Star Citizen Binding Profile (`MOZA.xml`)

This folder holds a custom Star Citizen control-mapping profile for a **MOZA** flight setup.
This document explains, in detail, **what every bound control does**, **how the XML profile format works**, and **how to keep the keybind reference database up to date**.

- **Profile file:** [`MOZA.xml`](MOZA.xml) — the actual bindings loaded by the game.
- **Master action catalogue:** [`STARBINDER_KEYBINDS_DATABASE_v4.8.md`](STARBINDER_KEYBINDS_DATABASE_v4.8.md) — every bindable SC action that *exists* (714 of them), with official labels/descriptions, pulled from the database behind <https://starbinder.space/>. Versioned to the SC patch it was captured from (**4.8**).
- **DB refresh tool:** [`refresh_keybinds_db.ps1`](refresh_keybinds_db.ps1) — re-downloads and regenerates the catalogue above for the current game version. See [Refreshing the keybind database](#refreshing-the-keybind-database).
- **Device diagrams:** `MOZA_AB6.png`, `MOZA_MHG.png`, `MOZA_MTQ.png` — the manufacturer button-number maps these bindings are based on.

> Descriptions below were verified against the starbinder master database (the game's own action labels/descriptions) plus community references. Where the inline comments in `MOZA.xml` are imprecise or wrong, this file says so in a **⚠ Note**.

---

## 1. Hardware setup

| Game device | Physical hardware | Button range | Axes used |
| --- | --- | --- | --- |
| **`js1`** (joystick instance 1) | **MOZA MHG** flight-stick grip mounted on the **MOZA AB6 FFB** base | Grip = **1–29**, Base = **49–62** | `js1_x` (roll), `js1_y` (pitch), `js1_rotz` (yaw / twist), plus `js1_slider1`/`js1_slider2` (the AB6 "Slider"/"Dial" lever analog halves — present but **unbound**) |
| **`js2`** (joystick instance 2) | **MOZA MTQ** Throttle Panel (Mission Throttle Quadrant) | **1–65** (44–48 unused/absent) | `js2_roty` (main throttle), plus unused Dial/RX/Slider + module sticks |

The MHG grip and the AB6 base report as **one** DirectInput device (`js1`): grip buttons are numbered 1–29, the base's own buttons continue at 49–62 (there is a 30–48 gap with no physical buttons). The MTQ throttle is a **separate** device (`js2`).

> **⚑ Scope — vehicle only:** This MOZA rig is used **only when piloting a vehicle**. On foot / first-person / interaction the user plays on an **Xbox controller** instead — never the MOZA gear. So this profile deliberately binds **only vehicle/seat contexts**; there are **no `player` / `spectator` / `player_choice` (on-foot) bindings**, and none should be added.

Product GUIDs as written in the profile:
- `js1` → `MOZA AB6 FFB Base  {1002346E-0000-0000-0000-504944564944}`
- `js2` → `MOZA MTQ Throttle Panel  {1101346E-0000-0000-0000-504944564944}`

> **Why instance numbers matter:** `js1`/`js2` are assigned by the order the game enumerates USB devices. If Windows re-enumerates them (USB port change, hub, reconnect order), `js1` and `js2` can **swap**, and every binding in this file will point at the wrong stick. If your bindings suddenly land on the wrong device, that's the cause — re-plug in the original order, or swap the `instance="1"`/`instance="2"` Product lines.

---

## 2. How the `.xml` profile format works

Star Citizen control profiles are XML files placed in:

```
…\StarCitizen\LIVE\user\client\0\controls\mappings\
```

(`LIVE` is the live client; PTU/EPTU have their own parallel folders.) The game does **not** load them automatically. You either:

1. **Export/Import from the game UI:** *Options → Keybindings → Control Profiles → Save control settings* writes a file here; *Load* applies one. **Save it under a different name first** so a game patch resetting defaults doesn't overwrite your work, then load it.
2. **Console command:** open the console (`` ` `` / `~`) and run `pp_rebindkeys MOZA.xml` (the file name, no path) to apply this profile immediately.

### 2.1 Document structure

```xml
<ActionMaps version="1" optionsVersion="2" rebindVersion="2" profileName="MOZA">
  <CustomisationUIHeader label="MOZA" description="MOZA MHG AB6 MTQ" image="">
    <devices>
      <joystick instance="1"/>
      <joystick instance="2"/>
    </devices>
    <categories />
  </CustomisationUIHeader>

  <options type="joystick" instance="1" Product="MOZA AB6 FFB Base  {…GUID…}">
    <flight_move_pitch invert="0"/>
  </options>
  <options type="joystick" instance="2" Product="MOZA MTQ Throttle Panel  {…GUID…}"/>

  <modifiers />

  <actionmap name="spaceship_movement">
    <action name="v_pitch">
      <rebind input="js1_y"/>
    </action>
    …
  </actionmap>
  …
</ActionMaps>
```

| Element | Purpose |
| --- | --- |
| `<ActionMaps>` | Root. `profileName` is the name shown in-game. The `version`/`optionsVersion`/`rebindVersion` attributes are CIG's schema version stamps — leave them as the game wrote them. |
| `<CustomisationUIHeader>` | Metadata for the profile picker (`label`, `description`) and the `<devices>` list declaring which joystick instances this profile expects. |
| `<options>` | Per-device options. The `Product="…GUID…"` string binds an instance number to a specific physical device. Child tags hold per-axis options such as **axis inversion** (e.g. `<flight_move_pitch invert="0"/>` — set `invert="1"` to flip pitch). |
| `<modifiers>` | Optional custom input modifiers; empty here. |
| `<actionmap>` | A group of related actions (a "context"). `name` must match a CIG-defined action map (e.g. `spaceship_movement`, `spaceship_weapons`). |
| `<action>` | A single bindable game action. `name` must be a real CIG action (e.g. `v_pitch`). See the master catalogue for valid names. |
| `<rebind>` | The actual binding. `input="…"` is the physical control. Optional `activationMode="…"` changes press behaviour. |

### 2.2 The `input=` naming convention

Format: **`<device><axis|button>`**

- **Device prefix:** `js1_`, `js2_`, … (joysticks), `kb1_` (keyboard), `mo1_` (mouse), `gp1_` (gamepad).
- **Buttons:** `js1_button5` → button index 5 on `js1` (indices match the manufacturer diagrams). Hat directions and 3-position slider/lever positions each register as their **own** button index.
- **Axes:** `js1_x`, `js1_y`, `js1_z`, `js1_rotx`, `js1_roty`, `js1_rotz`, `js1_slider1`. On a typical stick `x`=roll, `y`=pitch, `rotz`=twist/yaw. On the MTQ the levers expose as `roty`/etc. (the configurator labels them Dial / RX / RY / Slider).
- To **clear** a binding the game writes `input=" "` (a single space).

### 2.3 `activationMode` (and other `<rebind>` options)

`activationMode` controls how the press is interpreted. Used in this profile:

- **`hold`** — the action is active only while the control is held (used here for the look/freelook view controls so the camera pans while held and re-centres on release).

Other modes the game supports (not all used here): `press` (fire once on press), `tap`, `double_tap`, `delayed_press`, `hold_toggle`. A `<rebind>` can also carry `multiTap="2"` (require N taps) and other attributes — only add these if you know you need them.

### 2.4 Same button in multiple action maps

A physical button can appear in several action maps because **only one action map is active for a given context/operator mode at a time**. For example `js1_button1` is the trigger for *Fire Guns* (`spaceship_weapons`), *Fire Mining Laser* (`spaceship_mining`), and *Fire Focused Salvage Beam* (`spaceship_salvage`) — the trigger does the right thing depending on which operator mode the seat is in. This is intentional and is how a small number of physical controls drive flight, mining, and salvage. See [Operator-mode reuse](#5-operator-mode-reuse-mining--salvage).

---

## 3. Physical control reference

Button indices come directly from the MOZA configurator diagrams (`MOZA_AB6.png`, `MOZA_MHG.png`, `MOZA_MTQ.png`).

### 3.1 `js1` — MHG grip (1–29)

| # | Physical control | # | Physical control |
| --- | --- | --- | --- |
| 1 | Main index **trigger** (blade) | 16 | Right hat — **center press** |
| 2 | Top-left face thumb button | 17 | Lower/front thumb hat — **up** |
| 3 | Lower side button (pinky side) | 18 | Lower hat — **right** |
| 4 | Upper thumb button | 19 | Lower hat — **down** |
| 5 | Lower-center face thumb button | 20 | Lower hat — **left** |
| 6 | Trigger **second stage** (front of trigger) | 21 | Lower hat — **center press** |
| 7 | Left thumb hat — **up** | 22 | Upper thumb **rocker — up** |
| 8 | Left thumb hat — **right** (near knurled wheel press) | 23 | Upper rocker — **down** |
| 9 | Left thumb hat — **down** | 24 | Upper rocker — **center** |
| 10 | Left thumb hat — **left** | 25 | Top coolie/POV hat — **up** |
| 11 | Left thumb hat — **center press** | 26 | Top coolie hat — **right** |
| 12 | Right hat — **up** | 27 | Top coolie hat — **down** |
| 13 | Right hat — **right** | 28 | Top coolie hat — **left** |
| 14 | Right hat — **down** | 29 | Top coolie hat — **center press** |
| 15 | Right hat — **left** | | |

### 3.2 `js1` — AB6 base (49–62)

| # | Physical control | # | Physical control |
| --- | --- | --- | --- |
| 49 | Left wing button 1 (top) | 56 | Right wing button 4 (bottom) |
| 50 | Left wing button 2 | 57 | Left **"Slider"** lever — top |
| 51 | Left wing button 3 | 58 | Left "Slider" lever — middle |
| 52 | Left wing button 4 (bottom) | 59 | Left "Slider" lever — bottom |
| 53 | Right wing button 1 (top) | 60 | Right **"Dial"** lever — top |
| 54 | Right wing button 2 | 61 | Right "Dial" lever — middle |
| 55 | Right wing button 3 | 62 | Right "Dial" lever — bottom |

> **Wing buttons (49–56)** are plain **momentary pushbuttons** (physically labelled 1–4 per wing): 49–52 = **left** wing, 53–56 = **right** wing.
>
> ⚠ **Note (corrected):** The left **"Slider"** (57/58/59) and right **"Dial"** (60/61/62) are **mixed-mode levers**, *not* button-only as an earlier version of this doc claimed. Each emits **both** its 3 detent buttons (57 = top/100 … 59 = bottom/0; 60 = top/full … 62 = bottom/0) **and** a continuous **analog axis** — the js1 slider-family `js1_slider1` / `js1_slider2` (which lever maps to which needs `joy.cpl` confirmation, the same counter-intuitive name↔number mapping seen on the MTQ). Both are **maintained** (stay where you leave them), so they suit set-and-hold analog values, not momentary actions. They are currently **UNBOUND** in this combat profile (see §6 for why).

### 3.3 `js2` — MTQ throttle (1–65)

| # | Physical control | # | Physical control |
| --- | --- | --- | --- |
| 1 | Keypad **A1** | 25 | Lower-strip **toggle A** (metal 2-pos) — up |
| 2 | Keypad **A2** | 26 | Lower-strip **toggle A** (metal 2-pos) — down |
| 3 | Keypad **A3** | 27 | Lower-strip **toggle B** (metal 2-pos) — up |
| 4 | Keypad **A4** | 28 | Lower-strip **toggle B** (metal 2-pos) — down |
| 5 | Keypad **"NAV"** (mid-col top) | 29 | Lower-strip **toggle C** (gear-style plastic lever) — up |
| 6 | Keypad **"HDG"** (right-col top) | 30 | Lower-strip **toggle C** (gear-style plastic lever) — down |
| 7 | Keypad **"SPD"** (mid-col middle) | 36–40 | **FLAPS slider** (right, mixed buttons+axis): 40 rest "0" … 36 "FULL" — see slider note |
| 8 | Keypad **"ALT"** (right-col middle) | 31 / 43 | **SPEEDBRAKE slider** (far-left, mixed buttons+axis): 43 rest "DOWN", 31 "ARMED" — see slider note. *(34 = main-throttle reverse detent, separate)* |
| 9 | Keypad **"FD"** (mid-col bottom) | 49/50/51 | Right Module **3-position switch** — 49 rest, 50 latched-forward, 51 momentary-back |
| 10 | Keypad **"AP"** (right-col bottom) | | |
| 11 | Upper round encoder — CCW/left | 52–56 | Right Module **"WPN" hat** (smaller, 4-way + press): 56↑ 55↓ 53→ 54← 52=press |
| 12 | Upper encoder — CW/right | 57–61 | Right Module **"COM" hat** (larger, 4-way + press): 61↑ 60↓ 58→ 59← 57=press |
| 13 | Upper encoder — center press | 62 | Left Module **analog mini-stick press** (stick axes `js2_x`/`js2_y`, center 32767) |
| 14 | Lower encoder — CCW/left | 63 | **Throttle-lever dial** — forward/CW click (incremental encoder; pairs with 64) |
| 15 | Lower encoder — CW/right | 64 | **Throttle-lever dial** — back/CCW click (incremental encoder; pairs with 63) |
| 16 | Lower encoder — center press | 65 | Left Module face button |
| 17–21 | **Rotary mode-selector knob** — 5 detents physically engraved **1–5** (17 = pos 1/full CCW … 21 = pos 5/full CW); rests on one | | |
| 22/23/24 | 3-position rocker (23 L / 22 C / 24 R) | | |

**Axes** (confirmed in `joy.cpl`): the **throttle is a synced pair of bodies** reporting as **X Rotation + Y Rotation** = `js2_rotx` + `js2_roty`; the throttle is bound on `js2_roty` (`v_strafe_forward`) and its twin `js2_rotx` is left alone. The **Left Module mini-stick** = `js2_x` (camera yaw) / `js2_y` (camera pitch) drives **camera look**. The two side sliders are the slider-family axes: **FLAPS** (far right) = joy.cpl's **"Slider"** axis = `js2_slider2`, and **SPEEDBRAKE** (far left) = joy.cpl's **"Dial"** axis = `js2_slider1` — both in MOZA "mixed mode" (buttons **and** axis), now bound to mining-power / salvage-spacing (see slider note). *(The joy.cpl name↔SC number is counter-intuitive — "Slider"→slider2, "Dial"→slider1 — confirmed via SC's in-game binder, not guessable from joy.cpl.)*

> **Throttle-lever dial (buttons 63/64):** a **detented thumb dial on the throttle lever**, *not* two Left-Module face buttons as an earlier version of this doc claimed. It is an **incremental rotary encoder** — each forward/CW click pulses button **63**, each back/CCW click pulses button **64** (a momentary pulse per click, no held/latched state). It is therefore only suited to **increment/decrement** pairs — it can't cleanly hold or toggle. It is **buttons-only** (no axis); the configurator's analog **"Dial"** axis is a *different* control — `joy.cpl` confirmed that axis is the **SPEEDBRAKE slider**, not this wheel (an earlier version of this doc guessed the Dial axis was this wheel — wrong). Note the "increment/decrement only" caveat is soft — a single deliberate click *does* fire a toggle once (ESP worked fine on it); it's just that *rolling* the wheel flips a toggle repeatedly, which is why ESP was moved off to A4. Currently 63/64 **shotgun both vehicle zoom actions** (`v_view_dynamic_zoom_rel_*` + `v_view_zoom_*`) — whichever fires, fires; in practice dynamic zoom works in the **cockpit**, the 3rd-person one is dead. The other three zoom pairs (`zoom_*` / `spectate_*` / `pc_*`) are on-foot/spectator/interaction and can't fire from a pilot seat (rig is **vehicle-only**, see §1). The `view_fov`+camview experiment was **removed** — 3rd-person FoV zoom needs a *held* modifier (kb F4), and a momentary dial click can't hold anything (confirmed: stacking `view_fov` + `view_enable_camview_mode` on one click did nothing). So the dial does **cockpit zoom only**; 3rd-person FoV zoom stays on the keyboard (or a MOZA Pithouse macro that emits "hold F4 + tap NumPad±" per click). Buttons 63/64 firing is **confirmed in joy.cpl**. *(Buttons 62 and 65 are still believed to be the Left-Module mini-stick press and a face button respectively — re-verify if you find otherwise.)*

> **Side sliders — FLAPS (right) & SPEEDBRAKE (left):** two smooth-action levers, each running in MOZA **"mixed mode"** so they emit **both** detent buttons **and** a continuous analog axis (the configurator's **RX** / **Slider** axes).
> - **FLAPS** (right): 5 engraved detents — **"0"** = button **40** (rest) · **"1"** = 39 · **"2"** = 38 · **"3"** = 37 · **"FULL"** = 36 — plus a smooth axis across the full throw.
> - **SPEEDBRAKE** (far left): rests at button **43** (engraved **"DOWN"**); a gentle nudge to the single click hits button **31** (**"ARMED"**); past that it slides smoothly to the bottom with **no further buttons** — just the axis down to 0.
>
> Both levers stay where you leave them (**maintained**, not self-centering), so they suit **set-and-hold analog values**, *not* momentary actions. **Now bound and confirmed in-ship (Golem + Salvation):** **FLAPS ("Slider" axis = `js2_slider2`) → mining laser power** (`v_mining_throttle`; rest ≈ 20% laser floor → FULL = 100%, no invert) and **SPEEDBRAKE ("Dial" axis = `js2_slider1`) → salvage beam spacing** (`v_salvage_beam_spacing_abs`; auto-mapped, no range to set) — both **modal** (active only in Mining / Salvage operator mode, so no flight/combat conflict). The **X/Y-Rotation** axes are the synced throttle pair, *not* these sliders. *(Button 34 is the separate main-throttle reverse detent, already bound to `v_strafe_back`; other indices in the 31–42 block are intermediate/unmapped — don't rely on them.)*

> **Keypad labels (physical):** All keypad soft buttons (1–10) are **momentary press**. Left column = **A1–A4** (buttons 1–4). The mid+right 2×3 grid is engraved with MCP-style autopilot labels — **NAV** (5) · **HDG** (6) / **SPD** (7) · **ALT** (8) / **FD** (9) · **AP** (10) — repurposed to SC functions (see §4). The rotary knob's detents are engraved **1–5**.

> ⚠ **Note:** Buttons **44–48** are not present/labelled on the MTQ diagram — don't bind to them. The **rotary mode-selector knob does emit numbered buttons**: its five detents are **17–21** (see the row above). *(An earlier version of this doc wrongly described 17–21 as a "thumb directional hat" and claimed the rotary emits no buttons — both were incorrect; the diagram shows the knob's detents numbered 17–21.)*

---

## 4. Complete binding reference

Every binding currently in `MOZA.xml`, grouped by action map, with the official in-game label and what it does. **Input** = the XML `input=` value; **Control** = where that is on the hardware.

### Power management — `spaceship_power`

| Input | Control | Action → In-game label | What it does |
| --- | --- | --- | --- |
| `js2_button1` | MTQ keypad A1 | `v_power_toggle_weapons` → *Weapons Power - Toggle* | Cuts/restores weapon power. Only meaningful in SCM (weapons are stowed in NAV). |
| `js2_button2` | MTQ keypad A2 | `v_power_toggle_thrusters` → *Thruster Power - Toggle* | Cuts/restores power to propulsion. Off = can't manoeuvre, lower engine signature (cold running). |
| `js2_button3` | MTQ keypad A3 | `v_power_toggle_shields` → *Shield Power - Toggle* | Cuts/restores shields. Re-enabling incurs a boot delay; shields are offline in NAV mode regardless. |
| `js2_button23` | MTQ 3-pos rocker **left** | `v_power_set_off` → *Vehicle Power - Off* | Dedicated master power **OFF** (always off, not a toggle). |
| `js1_button49` | AB6 left wing 1 (top) | `v_engineering_assignment_weapons_increase` → *Power Allocation - Weapons - Increase* | Tap power toward **weapons**. |
| `js1_button50` | AB6 left wing 2 | `v_engineering_assignment_weapons_decrease` → *Power Allocation - Weapons - Decrease* | Tap power away from weapons. |
| `js1_button51` | AB6 left wing 3 | `v_engineering_assignment_engine_increase` → *Power Allocation - Engines - Increase* | Tap power toward **engines**. |
| `js1_button52` | AB6 left wing 4 (bottom) | `v_engineering_assignment_engine_decrease` → *Power Allocation - Engines - Decrease* | Tap power away from engines. |
| `js1_button53` | AB6 right wing 1 (top) | `v_engineering_assignment_shields_increase` → *Power Allocation - Shields - Increase* | Tap power toward **shields**. |
| `js1_button54` | AB6 right wing 2 | `v_engineering_assignment_shields_decrease` → *Power Allocation - Shields - Decrease* | Tap power away from shields. |
| `js1_button55` | AB6 right wing 3 | `v_engineering_assignment_reset` → *Power Allocation - Reset All* | **Reset** to balanced/even. |
| `js1_button56` | AB6 right wing 4 (bottom) | `v_engineering_assignment_shields_max` → *Power Allocation - Shields - Set to Max (Hold)* | **Hold** to slam all power to shields (burst-tank an incoming hit; returns on release). |

> **Power-pip triangle (AB6 wings `js1_button49–56`):** the base's 8 momentary pushbuttons are the **mid-fight power-triage bank** — left wing = offence/mobility (weapons ±, engines ±), right wing = defence (shields ±, reset, hold-for-max). Shift power toward shields when tanking, weapons when attacking. **⚠ Action-map note:** `v_engineering_assignment_*` are placed in the **`spaceship_power`** action map (the starbinder catalogue groups them with the working `v_power_*` actions under "flight - power"); this is the most likely thing to need an in-game verify — if a pip button does nothing, the action map is the suspect.

> **Master power rocker (`js2_button22/23/24`, bottom-centre 3-position):** **left (23)** = master power **OFF** (`v_power_set_off`); **right (24)** = Flight Ready / power **ON** (`v_flightready`, in `spaceship_general`); **centre (22)** = resting position, intentionally unbound. The keypad buttons A1–A3 toggle weapons / thrusters / shields power; A4 toggles LAMP night-vision (see Mode switching & LAMP).

### Ship systems & utilities — `spaceship_general`

| Input | Control | Action → In-game label | What it does |
| --- | --- | --- | --- |
| `js2_button24` | MTQ 3-pos rocker (right) | `v_flightready` → *Flight/Systems Ready* | One-press full startup: power + avionics + engines + shields to flight-ready. Toggle — press again to spin down. |
| `js2_button25` | MTQ **toggle A** up | `v_unlock_all_doors` + `v_open_all_doors` | **Both** actions share this throw: unlocks **and** opens all doors/ramps — "open up the ship". |
| `js2_button26` | MTQ **toggle A** down | `v_lock_all_doors` + `v_close_all_doors` | **Both** share this throw: closes **and** locks everything — "seal the ship". |

### Lights — `lights_controller`

| Input | Control | Action → In-game label | What it does |
| --- | --- | --- | --- |
| `js2_button27` | MTQ **toggle B** up | `v_lights_on` → *Headlights On* | Forces exterior/interior lights **on** (discrete). |
| `js2_button28` | MTQ **toggle B** down | `v_lights_off` → *Headlights Off* | Forces lights **off** (run dark — visual only, not EM/IR stealth). |

### Flight & movement — `spaceship_movement`

| Input | Control | Action → In-game label | What it does |
| --- | --- | --- | --- |
| `js1_y` | MHG pitch axis | `v_pitch` → *Pitch* | Nose up/down. Pull back = nose up (inverted by default; `invert` set in `<options>`). Usually the fastest rotation axis. |
| `js1_x` | MHG roll axis | `v_roll` → *Roll* | Bank left/right. Roll-onto-target + pitch is the core aiming technique. |
| `js1_rotz` | MHG twist | `v_yaw` → *Yaw* | Nose left/right via grip twist. Usually the slowest axis. |
| `js2_button61` | MTQ "COM" hat ↑ | `v_strafe_up` → *Strafe up* | Translate straight up (no rotation). Digital thrust. |
| `js2_button60` | MTQ "COM" hat ↓ | `v_strafe_down` → *Strafe down* | Translate straight down. |
| `js2_button58` | MTQ "COM" hat → | `v_strafe_right` → *Strafe right* | Translate right without yawing. |
| `js2_button59` | MTQ "COM" hat ← | `v_strafe_left` → *Strafe left* | Translate left without yawing. |
| `js2_roty` | MTQ throttle lever (RY) | `v_strafe_forward` → *Throttle - Increase* | Main forward throttle axis. Behaviour (absolute vs relative) depends on the cruise/throttle-mode toggle below. |
| `js2_button34` | MTQ right-center lever bottom detent | `v_strafe_back` → *Throttle - Decrease* | Reverse / throttle-invert so a one-direction throttle can command backward thrust. |
| `js2_button51` | MTQ Right Module switch — **momentary back** | `v_space_brake` → *Spacebrake* | Active full-stop on all axes (the "handbrake"). Hold to brake; springs back to rest (49) = `v_vtol_off`, an idempotent SET that's harmless to re-fire on every brake release. Rest (49) = VTOL off, forward-latch (50) = VTOL on (see VTOL rows below). |
| `js2_button65` | MTQ Left Module face button | `v_afterburner` → *Boost* | Boost — burst of extra acceleration from a depletable pool; also overrides proximity assist while held. |
| `js2_button9` | MTQ keypad **"FD"** (mid-bottom) | `v_toggle_jump_request` → *Jump Drive - Request Jump* | Engages **inter-system jump-point** travel (e.g. Stanton↔Pyro) — distinct from in-system quantum. Sits **directly below the quantum key** (7) → travel column. Moved off `js1_button56` (AB6 right wing 4, now free). |
| `js2_button5` | MTQ keypad **"NAV"** (mid-top) | `v_master_mode_cycle` → *Master mode cycle* | Toggles **SCM** (combat: weapons/shields) ↔ **NAV** (travel: quantum, higher speed, weapons offline). Physical "NAV" label matches. |
| `js2_button12` | MTQ upper encoder CW | `v_ifcs_speed_limiter_increment` → *Speed Limiter - Step Up* | Raises the SCM speed cap. |
| `js2_button11` | MTQ upper encoder CCW | `v_ifcs_speed_limiter_decrement` → *Speed Limiter - Step Down* | Lowers the speed cap — fly slow/precise; tighter turns. |
| `js2_button13` | MTQ upper encoder **center press** | `v_ifcs_speed_limiter_toggle` → *Speed Limiter - Enable / Disable* | Switches the speed cap on/off. Self-contained dial: turn 11/12 to set the cap, push 13 to engage/release it (instant full-speed sprint or back to capped). |
| `js2_button15` | MTQ lower encoder CW | `v_accel_range_increment` → *Acceleration Limiter - Step Up* | Raises the acceleration (G-force) cap — snappier, harsher Gs. |
| `js2_button14` | MTQ lower encoder CCW | `v_accel_range_decrement` → *Acceleration Limiter - Step Down* | Lowers the G-force cap — smoother, safer from blackout. |
| `js2_button16` | MTQ lower encoder **center press** | `v_ifcs_toggle_gforce_safety` → *G-Force Safety* | G-Safe — caps manoeuvres to stop the pilot blacking out; off = full performance, blackout risk. Self-contained dial: turn 14/15 to set the accel/G cap, push 16 to toggle the safety that governs it. **Moved here from `js1_button51`.** |
| `js2_button57` | MTQ "COM" strafe-hat — **center press** | `v_ifcs_vector_decoupling_toggle` → *Decoupled Mode Toggle* | Coupled ↔ decoupled. Co-located with the strafe directions it complements (decoupled = pure Newtonian translation — the mode you enable to strafe freely). Moved off AB6 left wing 1 (`js1_button49`, now free). Kept **off** the MTQ 3-pos switch (49/50) — its rest re-fires on every brake (would force-recouple); 57 is a plain press, so decoupled survives braking. |
| `js2_button10` | MTQ keypad **"AP"** (right-bottom) | `v_atc_request` → *Request Landing* | Hails ATC for a pad/hangar; opens doors/forcefields when in range. Bottom-right keypad key, next to the door/light/gear toggle strip. Moved off `js1_button53` (now free). *(Cargo-loading request `v_atc_loading_area_request` removed — never used.)* |
| `js2_button29` | MTQ **toggle C** up (gear lever) | `v_retract_landing_system` → *Landing Gear Retract* | Gear **up**. Gear-shaped plastic lever — its position mirrors gear state. |
| `js2_button30` | MTQ **toggle C** down (gear lever) | `v_deploy_landing_system` → *Landing Gear Deploy* | Gear **down**. Lever down = gear down (aircraft convention). |
| `js2_button8` | MTQ keypad **"ALT"** (right-mid) | `v_autoland` → *Autoland* | Autopilot lands on an ATC-assigned pad when gear is down and you're close. Moved from button 10; "ALT" (altitude/approach) label fits. Gear toggle is now **only** on the gear lever (29/30). |
| `js2_button50` | MTQ Right Module switch — **forward-latch** | `v_vtol_on` → *VTOL On* | Engages VTOL thrust mode (rotates/redirects thrusters for vertical lift) on VTOL-capable ships. Flick the switch forward; it stays latched. |
| `js2_button49` | MTQ Right Module switch — **rest/default** | `v_vtol_off` → *VTOL Off* | Disengages VTOL. As a discrete idempotent SET it re-fires on every space-brake release (51 springs back through 49) with no ill effect, so the switch position always reflects true VTOL state. Moved here off the COM-hat press (`js2_button57`, now free). |

### Quantum travel & navigation — `spaceship_quantum`, `spaceship_hud`

| Input | Control | Action → In-game label | What it does |
| --- | --- | --- | --- |
| `js2_button7` | MTQ keypad **"SPD"** (mid-middle) | `v_toggle_qdrive_engagement` → *Engage Quantum Drive* | Spools & engages the quantum drive for **in-system** travel (needs NAV mode + an aligned marker). Press again to drop out. (Physical "SPD"/speed label — loose quantum match.) |
| `js2_button6` | MTQ keypad **"HDG"** (right-top) | `v_starmap` → *Starmap* | Opens the 3D star map (mobiGlas) to pick a quantum destination. (Physical "HDG"/heading label — loose nav match.) |

### Mode switching & LAMP — `seat_general`

| Input | Control | Action → In-game label | What it does |
| --- | --- | --- | --- |
| `js1_button4` | MHG upper thumb button | `v_toggle_missile_mode` → *Missile Mode Toggle* | Switches the seat between **gun** and **missile** operator interfaces. |
| `js2_button17` | MTQ mode knob — detent 1 (full CCW) | `v_set_guns_mode` → *Guns Mode On* | Sets the seat to **Guns** operator mode. **Default park position** for the knob (combat-ready). |
| `js2_button18` | MTQ mode knob — detent 2 | `v_set_missile_mode` → *Missile Mode On* | Sets **Missile** operator mode. Overlaps the quick gun↔missile toggle on `js1_button4` (deliberate set vs fast flip). |
| `js2_button19` | MTQ mode knob — detent 3 (center) | `v_set_scan_mode` → *Scan Mode On* | Selects the **Scanning** operator mode (radar/ping). |
| `js2_button20` | MTQ mode knob — detent 4 | `v_set_mining_mode` → *Mining Mode On* | Selects the **Mining** operator mode (mining-capable ships only). |
| `js2_button21` | MTQ mode knob — detent 5 (full CW) | `v_set_salvage_mode` → *Salvage Mode On* | Selects the **Salvage** operator mode (salvage-capable ships only). |
| `js2_button4` | MTQ keypad **"A4"** | `v_light_amplification_toggle` → *LAMP Toggle* | Toggles canopy night-vision (Light Amplification). LAMP-equipped ships only. Back on A4 after **ESP was unbound** — ESP and proximity assist are now both left **enabled-by-default** (in settings) and never toggled. The earlier LAMP-on/off pairing with the lights switch (27/28) was dropped — 27/28 are lights-only again. |

> ⚠ **Note:** These five sit on the **rotary mode-selector knob** (detents 17–21), each directly **setting** one operator mode (`v_set_*_mode` are discrete activators, not "sub-modes" of a cycle). Operator modes are separate from Master Modes (SCM/NAV, cycled on `js2_button5`). Because the knob is a **maintained selector**, its physical position may not match the actual operator mode after seat entry or another mode change — turn off-and-back onto a detent to re-assert it. **Flight** and **Quantum** operator modes are intentionally *not* on the knob: Guns mode covers combat-flight, and quantum travel is handled by NAV master mode + QD-engage (`js2_button7`), so dedicated detents for them were redundant.

### Targeting — `spaceship_targeting`, `spaceship_targeting_advanced`

| Input | Control | Action → In-game label | What it does |
| --- | --- | --- | --- |
| `js1_button11` | MHG left hat center press | `v_target_lock_selected` → *Lock current target* | Hard-**locks** the selected contact (enables lead pips + missile lock). |
| `js1_button5` | MHG lower-center face button | `v_target_under_reticle` → *Lock target under reticle* | Locks whatever is under the crosshair — "target what I'm aiming at". |
| `js1_button8` | MHG left hat → | `v_target_cycle_hostile_fwd` → *Cycle Lock - Hostiles Forward* | Cycles forward through hostiles only. |
| `js1_button10` | MHG left hat ← | `v_target_cycle_hostile_back` → *Cycle Lock - Hostiles Back* | Cycles backward through hostiles only. |
| `js1_button12` | MHG right hat ↑ | `v_target_cycle_subitem_fwd` → *Cycle Lock - Sub-Target - Forward* | Cycles **sub-targets** (components) of the locked ship — focus-fire thrusters/weapons/power plant to disable. Moved to the stick (off MTQ keypad 9). |
| `js1_button14` | MHG right hat ↓ | `v_target_cycle_subitem_back` → *Cycle Lock - Sub-Target - Back* | Sub-target **back** — completes the ↑/↓ pair with button 12. |
| `js1_button13` | MHG right hat → | `v_target_cycle_attacker_fwd` → *Cycle Lock - Attackers - Forward* | Locks whoever is **currently attacking you** — snap to the active threat in a furball. Moved to the stick (off MTQ keypad 10). |
| `js1_button15` | MHG right hat ← | `v_target_cycle_attacker_back` → *Cycle Lock - Attackers - Back* | Attacker **back** — completes the →/← pair with button 13. |
| `js1_button25` | MHG top coolie hat ↑ | `v_target_cycle_all_fwd` → *Cycle Lock - All - Forward* | Cycles **all** contacts in scanner range (not just hostiles) forward. |
| `js1_button27` | MHG top coolie hat ↓ | `v_target_cycle_all_back` → *Cycle Lock - All - Back* | Cycles all contacts back. |
| `js1_button26` | MHG top coolie hat → | `v_target_cycle_hostile_reset` → *Cycle Lock - Hostiles - Closest* | **Snap-lock the closest hostile** — the best panic-target button in a furball. |
| `js1_button28` | MHG top coolie hat ← | `v_target_cycle_pinned_fwd` → *Cycle Lock - Pinned - Forward* | Cycles through **pinned** targets. |
| `js1_button29` | MHG top coolie hat — **press** | `v_target_pin_selected` → *Pin Target* | **Pins** the current target so you can cycle back to it (coolie ←). |

> **Targeting layout:** the **left hat** (lock + hostile cycle) and **right hat** (sub-target/attacker cycle ↑↓/→← + gimbal press) carry the core combat targeting; the freed **top coolie hat** adds an **acquisition cluster** — cycle-all, closest-hostile snap, and pin/cycle-pinned — complementing rather than duplicating the hats. **⚠ Action-map note:** `v_target_pin_selected` is placed in `spaceship_targeting_advanced` with the cycle actions; if "pin" doesn't bind in-game, try `spaceship_targeting` instead.

### Radar & scanning — `spaceship_radar`, `spaceship_scanning`

| Input | Control | Action → In-game label | What it does |
| --- | --- | --- | --- |
| `js1_button20` | MHG lower hat ← | `v_invoke_ping` → *Activate Ping* | Active radar ping — reveals/marks contacts by their cross-section (also gives away your position). |
| `js1_button18` | MHG lower hat → | `v_scanning_trigger_scan` → *Activate Scanning* | **Hold** to scan the target under the reticle for detailed info (requires Scan operator mode). |
| `js1_button17` | MHG lower hat ↑ | `v_inc_scan_focus_level` → *Increase Scanning Angle* | Narrows the scan cone — stronger/longer-range read on one target. |
| `js1_button19` | MHG lower hat ↓ | `v_dec_scan_focus_level` → *Decrease Scanning Angle* | Widens the scan cone — sweep a broader area. |

### Weapons — `spaceship_weapons`

| Input | Control | Action → In-game label | What it does |
| --- | --- | --- | --- |
| `js1_button1` | MHG main trigger | `v_weapon_preset_fire_guns0` → *Fire Guns Group 1* | Fires **weapon group 1**. |
| `js1_button6` | MHG trigger stage 2 | `v_weapon_preset_fire_guns1` → *Fire Guns Group 2* | Fires **weapon group 2**. |
| `js1_button22` | MHG upper rocker ↑ | `v_weapon_preset_next` → *Weapon Preset - Next* | Cycles weapon grouping/preset forward. |
| `js1_button23` | MHG upper rocker ↓ | `v_weapon_preset_prev` → *Weapon Preset - Previous* | Cycles weapon grouping/preset backward. |
| `js1_button24` | MHG upper rocker center | `v_weapon_aim_type_cycle` → *Weapon Aim Type - Cycle* | Cycles gimbal aim mode (fixed-style / gimbal assist / manual gimbal). |
| `js1_button16` | MHG right hat center press | `v_weapon_gimbals_state_toggle` → *Gimbals State - Toggle* | Quick on/off of gimbal lock (locked = tighter convergence). |

> ⚠ **Note:** `fire_guns0` / `fire_guns1` are **weapon group 1 / group 2**, *not* "trigger stage 1 / stage 2" (the XML comments previously implied the latter and have been corrected). The `0`/`1` suffix is the weapon group, independent of which physical trigger stage you put it on. (Here group 2 is conveniently on the trigger's 2nd stage, `js1_button6`.) Until you actually split your guns into two groups in the MFD, group 2 may have nothing to fire.

### Missiles — `spaceship_missiles`

| Input | Control | Action → In-game label | What it does |
| --- | --- | --- | --- |
| `js1_button2` | MHG top-left face button | `v_weapon_toggle_launch_missile` → *Launch Missiles* | Arms/launches the selected missile. **Hold** to build a stronger lock before release. |
| `js1_button22` | MHG upper rocker ↑ | `v_weapon_cycle_missile_fwd` → *Missile Type - Cycle Next* | Next missile type (in missile mode). Shares the button with *Weapon Preset Next*. |
| `js1_button23` | MHG upper rocker ↓ | `v_weapon_cycle_missile_back` → *Missile Type - Cycle Previous* | Previous missile type. Shares the button with *Weapon Preset Prev*. |

> The rocker (22/23) does double duty: **weapon presets** in gun mode, **missile types** in missile mode — the active operator mode decides which.

### Countermeasures & shields — `spaceship_defensive`

| Input | Control | Action → In-game label | What it does |
| --- | --- | --- | --- |
| `js1_button7` | MHG left hat ↑ | `v_weapon_countermeasure_decoy_launch` → *Decoy* | Flares — lure **seeker-guided** (IR/cross-section) missiles. Burst them as a missile closes. |
| `js1_button9` | MHG left hat ↓ | `v_weapon_countermeasure_noise_launch` → *Noise* | Chaff — a sensor-interference cloud that breaks **radar/scan locks**. |
| `js2_button56` | MTQ "WPN" hat ↑ | `v_shield_raise_level_forward` → *Shield - Raise Level - Front* | Stacks shield power to the **front** facing. |
| `js2_button55` | MTQ "WPN" hat ↓ | `v_shield_raise_level_back` → *Shield - Raise Level - Rear* | Stacks shield power to the **rear** facing. |
| `js2_button54` | MTQ "WPN" hat ← | `v_shield_raise_level_left` → *Shield - Raise Level - Port* | Stacks shield power to the **left/port** facing. |
| `js2_button53` | MTQ "WPN" hat → | `v_shield_raise_level_right` → *Shield - Raise Level - Starboard* | Stacks shield power to the **right/starboard** facing. |
| `js2_button52` | MTQ "WPN" hat — **press** | `v_shield_reset_level` → *Shield - Reset Levels* | Re-equalises all facings. |

> **Shield faceting** maps the hat's physical directions 1:1 (up = front … press = reset) — push toward the threat to angle your strongest shield at it. On single-bubble-shield ships the directional raises do nothing and the reset is harmless. The "WPN" label is repurposed (defensive, not weapons) — consistent with the rest of this profile's relabelling.

### View & camera — `spaceship_view`

| Input | Control | Action → In-game label | What it does |
| --- | --- | --- | --- |
| `js2_button62` | MTQ Left Module mini-stick — **press** | `v_view_cycle_fwd` → *Cycle camera view* | Cycle cockpit ↔ external/chase views. Moved off the MHG coolie press (`js1_button29`). |
| `js1_button3` | MHG lower side button | `v_view_freelook_mode` → *Freelook* | **Hold** to look around the cockpit independently of ship facing. |
| `js2_x` | MTQ Left Module mini-stick — **X axis** | `v_view_yaw` → *Look left/right* | Analog camera yaw. Stick centers at 32767 = neutral (no off-center calibration needed). |
| `js2_y` | MTQ Left Module mini-stick — **Y axis** | `v_view_pitch` → *Look up/down* | Analog camera pitch. Add `invert` in `<options>` if it feels reversed. Both moved off the MHG top coolie hat (25/26/27/28, now free). |
| `js1_button21` | MHG lower hat center press | `v_ads_toggle` → *Vehicle ADS (Toggle)* | Cockpit zoom/"ADS" view (in-ship binoculars-style zoom) — the reliable in-cockpit zoom. |
| `js2_button63` | MTQ throttle dial — fwd/CW click | `v_view_dynamic_zoom_rel_in` + `v_view_zoom_in` | Zoom **in** — dynamic zoom works in the **cockpit**; 3rd-person `v_view_zoom_in` is dead but harmless. **No 3rd-person FoV zoom** — that needs a *held* modifier (kb F4), which a momentary dial click can't do (the `view_fov`+camview attempt was removed). |
| `js2_button64` | MTQ throttle dial — back/CCW click | `v_view_dynamic_zoom_rel_out` + `v_view_zoom_out` | Zoom **out** — same. For 3rd-person FoV zoom, use the keyboard (F4 + NumPad±) or a MOZA Pithouse macro emitting that combo per click. |

### Mining — `spaceship_mining`

These reuse MHG controls; active only in **Mining** operator mode.

| Input | Control | Action → In-game label | What it does |
| --- | --- | --- | --- |
| `js1_button1` | MHG trigger | `v_toggle_mining_laser_fire` → *Fire Mining Laser* | Fire/extract with the mining laser (reuses the gun trigger). |
| `js1_button22` | MHG rocker ↑ | `v_increase_mining_throttle` → *Mining Laser Power - Increase* | Raise laser power toward the fracture window. |
| `js1_button23` | MHG rocker ↓ | `v_decrease_mining_throttle` → *Mining Laser Power - Decrease* | Lower laser power. |
| `js2_slider2` *(FLAPS)* | MTQ FLAPS slider — **axis** ("Slider") | `v_mining_throttle` → *Mining Laser Power - Throttle* | **Absolute** laser power on the maintained FLAPS lever — hold it in the green fracture window. Supersedes the ± rocker above. **Confirmed in Golem:** rest (up) = ~20% charge (the laser's minimum floor), FULL (down) = 100% — direction correct, **no invert needed**. |
| `js1_button4` | MHG upper thumb button | `v_toggle_mining_laser_type` → *Switch Mining Laser* | Switch between fitted mining laser heads/modules. |
| `js1_button18` | MHG lower hat → | `v_toggle_mining_mode` → *Mining Mode Toggle* (placeholder) | Swapped in to replace the invalid `v_toggle_mining_mode_fracture`. See note below. |

> ⚠ **Note (placeholder binding):** The original `v_toggle_mining_mode_fracture` was **not a real action** (it doesn't exist in SC), so it did nothing. It has been swapped for `v_toggle_mining_mode` (*Mining Mode Toggle*) as a stop-gap. **Caveat:** `v_toggle_mining_mode` actually belongs to the `seat_general` action map (not `spaceship_mining`), and button 18 is also the scan trigger — so when wiring mining up properly, re-home it to `seat_general` on a dedicated free button. Modern mining has no separate "fracture sensor"; fracturing is done by driving laser power into the green window with `v_increase_mining_throttle`.

### Salvage — `spaceship_salvage`

These reuse MHG controls; active only in **Salvage** operator mode.

| Input | Control | Action → In-game label | What it does |
| --- | --- | --- | --- |
| `js1_button1` | MHG trigger | `v_salvage_toggle_fire_focused` → *Fire Focused Salvage Beams* | Toggle the focused salvage beam(s) on/off. |
| `js1_button6` | MHG trigger stage 2 | `v_salvage_toggle_gimbal_mode` → *Salvage Mode - Toggle Gimbal* | Toggle salvage beam gimbal mode. |
| `js1_button10` | MHG left hat ← | `v_salvage_toggle_fire_disintegrate` → *Fire Disintegrate Beam* | Fire the disintegrate beam (break down material). |
| `js1_button8` | MHG left hat → | `v_salvage_toggle_fire_fracture` → *Fire Fracture Beam* | Fire the fracture beam (crack structures into salvageable pieces). |
| `js1_button11` | MHG left hat center press | `v_salvage_cycle_modifiers_focused` → *Cycle Focused Salvage Modifiers* | Cycle the mode/modifier of focused beam(s) (e.g. scraper vs tractor). |
| `js2_slider1` *(SPEEDBRAKE)* | MTQ SPEEDBRAKE slider — **axis** ("Dial") | `v_salvage_beam_spacing_abs` → *Salvage Beam Spacing - Absolute* | **Absolute** beam gap on the maintained SPEEDBRAKE lever — set to match the panel and leave it. **Confirmed in Salvation:** sweeping the lever opens/closes the gap across full travel (auto-mapped, no range to set). |

---

## 5. Operator-mode reuse (mining & salvage)

The MHG trigger and hats are deliberately **shared** across flight, mining, and salvage. Which action fires depends on the seat's **operator mode** (set via the `v_set_*_mode` detents on the MTQ rotary mode-selector knob, or `v_toggle_missile_mode`):

| Physical control | Flight/SCM | Mining mode | Salvage mode |
| --- | --- | --- | --- |
| `js1_button1` (trigger) | Fire Guns Group 1 | Fire Mining Laser | Fire Focused Salvage Beam |
| `js1_button6` (trigger 2) | Fire Guns Group 2 | — | Toggle Salvage Gimbal |
| `js1_button4` (thumb btn) | Missile-mode toggle | Switch Mining Laser | — |
| `js1_button22/23` (rocker) | Weapon/missile cycle | Mining power ± | — |
| `js1_button8/10` (left hat ←/→) | Cycle hostiles | — | Fire Fracture / Disintegrate |
| `js1_button11` (left hat press) | Lock target | — | Cycle salvage modifiers |

This is normal and intended — only one of these action maps is "live" at a time.

---

## 6. Issues & recommendations found in `MOZA.xml`

1. **✅ Fixed — `v_toggle_mining_mode_fracture` (`js1_button18`) was invalid** (not a real action). Swapped to `v_toggle_mining_mode` as a placeholder; proper mining wiring is deferred. *(See Mining table + note.)*
2. **✅ Fixed — `fire_guns0` / `fire_guns1` comments corrected** — they're weapon **groups 1/2**, not trigger stages. The bindings themselves were always fine. *(See Weapons note.)*
3. **✅ Fixed — `v_toggle_jump_request` comment clarified** as inter-system jump-point travel (distinct from in-system quantum, `v_toggle_qdrive_engagement`). Binding unchanged.
4. **Doubled door bindings** (`js2_button25` = unlock+open, `js2_button26` = lock+close) fire two actions per press by design. Intended as "open up / seal up" buttons — just be aware both fire.
5. **✅ js1 optimized (combat pass):** the previously-empty stick/base real estate is now filled — **AB6 wings (`js1_button49–56`) = power-pip triangle** (weapons/engines/shields ± + reset + hold-for-max), **MHG top coolie hat (25–29) = target-acquisition cluster** (cycle-all, closest-hostile snap, pin/cycle-pinned), and **MHG right hat ↓/← (14/15)** complete the sub-target/attacker *back* cycles. The MHG grip is now **fully bound** (1–29). *(Two action-map verifies to do in-game: the `v_engineering_assignment_*` pips and `v_target_pin_selected` — see §4 notes.)*
6. **✅ Fixed — AB6 levers are mixed-mode, not button-only:** an earlier doc claimed the "Slider"/"Dial" levers (57–62) were 3-position button-only "not an analog axis." They are **mixed-mode** (3 detent buttons **plus** an analog axis, `js1_slider1`/`js1_slider2`). Corrected in §1 and §3.2.
7. **Only remaining free js1 hardware = the two AB6 levers (57–62), deliberately unbound:** maintained set-and-hold levers suit neither momentary combat actions nor the wing power-pips (a held detent would fight the pip taps). Reserved for a future **modal/analog** use (e.g. a multi-role analog value) — confirm which axis is `js1_slider1` vs `js1_slider2` in `joy.cpl` first. **MTQ (js2)** remains essentially full (only the rocker centre 22, slider detents 31/36-40/43, and throttle-twin `js2_rotx` are intentional gaps).
8. **Device-instance fragility:** see the warning in §1 — keep USB enumeration order stable so `js1`/`js2` don't swap.

---

## 7. Refreshing the keybind database

The master catalogue is **patch-specific**. When a new Star Citizen version ships and starbinder updates, regenerate it.

### Easy way (one command)

From this folder:

```powershell
powershell -ExecutionPolicy Bypass -File .\refresh_keybinds_db.ps1
```

The script auto-detects the version, re-downloads the data, regenerates the Markdown as `STARBINDER_KEYBINDS_DATABASE_v<version>.md`, and deletes the previous snapshot. **After it runs, update the version number referenced at the top of this `CLAUDE.md`** if it changed.

### How it works / manual recipe (for future Claude)

starbinder is a static client-side app; its search box indexes plain JSON the page fetches. The pieces:

1. **Find the data files** — fetch `https://starbinder.space/script.js` and look for `fetch(...)` calls. As of 4.8 it loads:
   - `https://starbinder.space/keybinds.json` — the master DB, an object **keyed by action name** → `{ label, description, keywords[] }`.
   - `https://starbinder.space/localisation.json` — an object keyed by `ui_*` IDs; resolves description references.
   - `https://starbinder.space/mappingProfile.json` — small device-axis index map (minor).
   - (`actionmaps.xml` is referenced but **404s** server-side — it's uploaded by the user in the browser, so ignore it.)
2. **Detect the version** — fetch `https://starbinder.space/` and read the banner text **`UPDATED FOR <x.y>`** (e.g. "UPDATED FOR 4.8").
3. **Resolve descriptions** — a `description` may be empty, literal text, or an `@ui_...` reference. If it starts with `@`, strip the `@` and look the key up in `localisation.json`.
4. **Group & render** — group actions by their **first** `keywords` entry (that's the category), then emit one Markdown table per category.
5. **Name & prune** — save as `STARBINDER_KEYBINDS_DATABASE_v<version>.md` and remove the old versioned file so only the current snapshot stays.

The full implementation lives in [`refresh_keybinds_db.ps1`](refresh_keybinds_db.ps1) — if the site's file names or structure change, update the URLs/parsing there.

> Tooling note: `keybinds.json` and `localisation.json` are plain HTTPS GETs (PowerShell `Invoke-WebRequest`, `curl`, or the WebFetch tool all work). No auth, no API key.

---

## 8. Reference links

- **starbinder keybind reference:** <https://starbinder.space/>
- **Local master catalogue:** [`STARBINDER_KEYBINDS_DATABASE_v4.8.md`](STARBINDER_KEYBINDS_DATABASE_v4.8.md)
- **Star Citizen wiki — Controls:** <https://starcitizen.tools/Guide:Controls>
- **Master Modes / IFCS:** <https://starcitizen.tools/Flight_system>
- **ESP (Enhanced Stick Precision):** <https://starcitizen.tools/ESP>

---

*Last reviewed for Star Citizen Alpha 4.8 (2026-06-24). Update the version stamp and the catalogue file when you refresh the database.*
