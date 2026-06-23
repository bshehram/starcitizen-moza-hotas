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
| **`js1`** (joystick instance 1) | **MOZA MHG** flight-stick grip mounted on the **MOZA AB6 FFB** base | Grip = **1–29**, Base = **49–62** | `js1_x` (roll), `js1_y` (pitch), `js1_rotz` (yaw / twist) |
| **`js2`** (joystick instance 2) | **MOZA MTQ** Throttle Panel (Mission Throttle Quadrant) | **1–65** (44–48 unused/absent) | `js2_roty` (main throttle), plus unused Dial/RX/Slider + module sticks |

The MHG grip and the AB6 base report as **one** DirectInput device (`js1`): grip buttons are numbered 1–29, the base's own buttons continue at 49–62 (there is a 30–48 gap with no physical buttons). The MTQ throttle is a **separate** device (`js2`).

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

> The left "Slider" and right "Dial" are **3-position levers** — each position is its own button (57/58/59 and 60/61/62), not an analog axis.

### 3.3 `js2` — MTQ throttle (1–65)

| # | Physical control | # | Physical control |
| --- | --- | --- | --- |
| 1 | Keypad **A1** | 25 | Lower-strip rocker A — up |
| 2 | Keypad **A2** | 26 | Lower-strip rocker A — down |
| 3 | Keypad **A3** | 27 | Lower-strip rocker B — up |
| 4 | Keypad **A4** | 28 | Lower-strip rocker B — down |
| 5 | Keypad mid-col top | 29 | Lower-strip toggle C — up |
| 6 | Keypad right-col top | 30 | Lower-strip toggle C — down |
| 7 | Keypad mid-col middle | 31–43 | **Throttle-lever gate detents** (one button per notch) |
| 8 | Keypad right-col middle | 34 | …right-center lever, bottom detent |
| 9 | Keypad mid-col bottom | 49/50/51 | Right Module 3-position slider |
| 10 | Keypad right-col bottom | 51 | …slider left/pos-1 |
| 11 | Upper round encoder — CCW/left | 52–56 | Right Module upper 8-way hat |
| 12 | Upper encoder — CW/right | 57–61 | Right Module lower 4-way hat |
| 13 | Upper encoder — center press | 62 | Left Module top thumb button |
| 14 | Lower encoder — CCW/left | 63 | Left Module face button |
| 15 | Lower encoder — CW/right | 64 | Left Module face button |
| 16 | Lower encoder — center press | 65 | Left Module face button |
| 17–21 | Thumb directional hat | | |
| 22/23/24 | 3-position rocker (23 L / 22 C / 24 R) | | |

**Axes:** `js2_roty` is used as the **main throttle** (`v_strafe_forward`). The configurator also exposes Dial, RX, RY, Slider bars and the two module mini-sticks (X/Y) — these are **not currently bound**.

> ⚠ **Note:** Buttons **44–48** are not present/labelled on the MTQ diagram, and the 9-position rotary selector dial does not emit numbered buttons in the diagram. Don't bind to 44–48.

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

> **Master power rocker (`js2_button22/23/24`, bottom-centre 3-position):** **left (23)** = master power **OFF** (`v_power_set_off`); **right (24)** = Flight Ready / power **ON** (`v_flightready`, in `spaceship_general`); **centre (22)** = resting position, intentionally unbound. The keypad buttons A1–A3 toggle weapons / thrusters / shields power; A4 toggles VTOL (see Flight & movement).

### Ship systems & utilities — `spaceship_general`

| Input | Control | Action → In-game label | What it does |
| --- | --- | --- | --- |
| `js2_button24` | MTQ 3-pos rocker (right) | `v_flightready` → *Flight/Systems Ready* | One-press full startup: power + avionics + engines + shields to flight-ready. Toggle — press again to spin down. |
| `js2_button25` | MTQ lower-strip rocker A up | `v_unlock_all_doors` + `v_open_all_doors` | **Both** actions share this button: one press unlocks **and** opens all doors/ramps. |
| `js2_button26` | MTQ lower-strip rocker A down | `v_lock_all_doors` + `v_close_all_doors` | **Both** share this button: one press closes **and** locks everything — "seal the ship". |
| `js2_button27` | MTQ lower-strip rocker B up | `v_unlock_all_ports` | Unlocks external item ports so components/weapons can be removed with a tractor tool. |
| `js2_button28` | MTQ lower-strip rocker B down | `v_lock_all_ports` | Re-locks all item ports after servicing. |

### Lights — `lights_controller`

| Input | Control | Action → In-game label | What it does |
| --- | --- | --- | --- |
| `js2_button29` | MTQ lower-strip toggle C up | `v_lights_on` → *Headlights On* | Forces exterior/interior lights **on** (discrete, not a toggle). |
| `js2_button30` | MTQ lower-strip toggle C down | `v_lights_off` → *Headlights Off* | Forces lights **off** (run dark — visual only, not EM/IR stealth). |

### Flight & movement — `spaceship_movement`

| Input | Control | Action → In-game label | What it does |
| --- | --- | --- | --- |
| `js1_y` | MHG pitch axis | `v_pitch` → *Pitch* | Nose up/down. Pull back = nose up (inverted by default; `invert` set in `<options>`). Usually the fastest rotation axis. |
| `js1_x` | MHG roll axis | `v_roll` → *Roll* | Bank left/right. Roll-onto-target + pitch is the core aiming technique. |
| `js1_rotz` | MHG twist | `v_yaw` → *Yaw* | Nose left/right via grip twist. Usually the slowest axis. |
| `js1_button12` | MHG right hat ↑ | `v_strafe_up` → *Strafe up* | Translate straight up (no rotation). Digital thrust. |
| `js1_button14` | MHG right hat ↓ | `v_strafe_down` → *Strafe down* | Translate straight down. |
| `js1_button13` | MHG right hat → | `v_strafe_right` → *Strafe right* | Translate right without yawing. |
| `js1_button15` | MHG right hat ← | `v_strafe_left` → *Strafe left* | Translate left without yawing. |
| `js2_roty` | MTQ throttle lever (RY) | `v_strafe_forward` → *Throttle - Increase* | Main forward throttle axis. Behaviour (absolute vs relative) depends on the cruise/throttle-mode toggle below. |
| `js2_button34` | MTQ right-center lever bottom detent | `v_strafe_back` → *Throttle - Decrease* | Reverse / throttle-invert so a one-direction throttle can command backward thrust. |
| `js2_button51` | MTQ Right Module slider pos-1 | `v_space_brake` → *Spacebrake* | Active full-stop on all axes (the "handbrake"). Usually held; essential in decoupled mode. |
| `js2_button65` | MTQ Left Module face button | `v_afterburner` → *Boost* | Boost — burst of extra acceleration from a depletable pool; also overrides proximity assist while held. |
| `js2_button8` | MTQ keypad right-mid | `v_ifcs_throttle_swap_mode` → *Throttle - Cruise Mode - Toggle* | Swaps throttle between **absolute/cruise** (holds a set speed hands-free) and **relative** (commands acceleration). |
| `js1_button56` | MHG/AB6 right wing 4 | `v_toggle_jump_request` → *Jump Drive - Request Jump* | Engages **inter-system jump-point** travel (e.g. Stanton↔Pyro) — distinct from in-system quantum. |
| `js2_button5` | MTQ keypad mid-top | `v_master_mode_cycle` → *Master mode cycle* | Toggles **SCM** (combat: weapons/shields) ↔ **NAV** (travel: quantum, higher speed, weapons offline). |
| `js2_button12` | MTQ upper encoder CW | `v_ifcs_speed_limiter_increment` → *Speed Limiter - Step Up* | Raises the SCM speed cap. |
| `js2_button11` | MTQ upper encoder CCW | `v_ifcs_speed_limiter_decrement` → *Speed Limiter - Step Down* | Lowers the speed cap — fly slow/precise; tighter turns. |
| `js2_button15` | MTQ lower encoder CW | `v_accel_range_increment` → *Acceleration Limiter - Step Up* | Raises the acceleration (G-force) cap — snappier, harsher Gs. |
| `js2_button14` | MTQ lower encoder CCW | `v_accel_range_decrement` → *Acceleration Limiter - Step Down* | Lowers the G-force cap — smoother, safer from blackout. |
| `js1_button49` | AB6 left wing 1 | `v_ifcs_vector_decoupling_toggle` → *Decoupled Mode Toggle* | Coupled (auto counter-thrust, atmospheric feel) ↔ decoupled (Newtonian drift). |
| `js1_button50` | AB6 left wing 2 | `v_ifcs_toggle_esp` → *ESP Toggle* | Enhanced Stick Precision — softens input near a target to reduce overshoot (joystick aim assist). |
| `js1_button51` | AB6 left wing 3 | `v_ifcs_toggle_gforce_safety` → *G-Force Safety* | G-Safe — caps manoeuvres to stop the pilot blacking out; off = full performance, blackout risk. |
| `js1_button52` | AB6 left wing 4 | `v_ifcs_proximity_assist_toggle` → *Proximity Assist* | Auto-dampens thrust near surfaces for safer slow flying/landings. Boost overrides it. |
| `js1_button53` | AB6 right wing 1 | `v_atc_request` → *Request Landing* | Hails ATC for a pad/hangar; opens doors/forcefields when in range. |
| `js1_button54` | AB6 right wing 2 | `v_atc_loading_area_request` → *Request Cargo Loading* | Requests a cargo/loading area (freight) separate from a standard landing pad. |
| `js2_button9` | MTQ keypad mid-bottom | `v_toggle_landing_system` → *Landing Gear Toggle* | Deploys/retracts gear and engages landing mode/HUD. |
| `js2_button10` | MTQ keypad right-bottom | `v_autoland` → *Autoland* | Autopilot lands on an ATC-assigned pad when gear is down and you're close. |
| `js2_button4` | MTQ keypad A4 | `v_vtol_toggle` → *VTOL Toggle* | Toggles VTOL thrust mode (rotates/redirects thrusters for vertical lift) on VTOL-capable ships. |

### Quantum travel & navigation — `spaceship_quantum`, `spaceship_hud`

| Input | Control | Action → In-game label | What it does |
| --- | --- | --- | --- |
| `js2_button7` | MTQ keypad mid-middle | `v_toggle_qdrive_engagement` → *Engage Quantum Drive* | Spools & engages the quantum drive for **in-system** travel (needs NAV mode + an aligned marker). Press again to drop out. |
| `js2_button6` | MTQ keypad right-top | `v_starmap` → *Starmap* | Opens the 3D star map (mobiGlas) to pick a quantum destination. |

### Mode switching & LAMP — `seat_general`

| Input | Control | Action → In-game label | What it does |
| --- | --- | --- | --- |
| `js1_button4` | MHG upper thumb button | `v_toggle_missile_mode` → *Missile Mode Toggle* | Switches the seat between **gun** and **missile** operator interfaces. |
| `js2_button17` | MTQ thumb hat ← | `v_set_flight_mode` → *Flight Mode On* | Jumps the seat straight to the default **Flight** operator mode. |
| `js2_button18` | MTQ thumb hat ↖ | `v_set_quantum_mode` → *Quantum Mode On* | Selects the **Quantum** operator mode (QT targeting/spool UI). |
| `js2_button19` | MTQ thumb hat ↑ | `v_set_scan_mode` → *Scan Mode On* | Selects the **Scanning** operator mode (radar/ping). |
| `js2_button20` | MTQ thumb hat ↗ | `v_set_mining_mode` → *Mining Mode On* | Selects the **Mining** operator mode (mining-capable ships only). |
| `js2_button21` | MTQ thumb hat → | `v_set_salvage_mode` → *Salvage Mode On* | Selects the **Salvage** operator mode (salvage-capable ships only). |
| `js1_button55` | AB6 right wing 3 | `v_light_amplification_toggle` → *LAMP Toggle* | Toggles canopy night-vision (Light Amplification). LAMP-equipped ships only. |
| `js1_button59` | AB6 left "Slider" bottom | `v_light_amplification_off` → *LAMP Off* | Forces LAMP off (discrete). |

> ⚠ **Note:** `v_set_*_mode` actions are **direct selectors**, not "sub-modes" of a cycle. Each jumps straight to that operator mode (the inline XML comments call these "sub-modes" — harmless, but they're discrete activators). Operator modes are separate from Master Modes (NAV/SCM).

### Targeting — `spaceship_targeting`, `spaceship_targeting_advanced`

| Input | Control | Action → In-game label | What it does |
| --- | --- | --- | --- |
| `js1_button11` | MHG left hat center press | `v_target_lock_selected` → *Lock current target* | Hard-**locks** the selected contact (enables lead pips + missile lock). |
| `js1_button5` | MHG lower-center face button | `v_target_under_reticle` → *Lock target under reticle* | Locks whatever is under the crosshair — "target what I'm aiming at". |
| `js1_button8` | MHG left hat → | `v_target_cycle_hostile_fwd` → *Cycle Lock - Hostiles Forward* | Cycles forward through hostiles only. |
| `js1_button10` | MHG left hat ← | `v_target_cycle_hostile_back` → *Cycle Lock - Hostiles Back* | Cycles backward through hostiles only. |

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

### Countermeasures — `spaceship_defensive`

| Input | Control | Action → In-game label | What it does |
| --- | --- | --- | --- |
| `js1_button7` | MHG left hat ↑ | `v_weapon_countermeasure_decoy_launch` → *Decoy* | Flares — lure **seeker-guided** (IR/cross-section) missiles. Burst them as a missile closes. |
| `js1_button9` | MHG left hat ↓ | `v_weapon_countermeasure_noise_launch` → *Noise* | Chaff — a sensor-interference cloud that breaks **radar/scan locks**. |

### View & camera — `spaceship_view`

| Input | Control | Action → In-game label | What it does |
| --- | --- | --- | --- |
| `js1_button29` | MHG top coolie center press | `v_view_cycle_fwd` → *Cycle camera view* | Cycle 1st-person ↔ 3rd-person/chase views. |
| `js1_button3` | MHG lower side button | `v_view_freelook_mode` → *Freelook* | **Hold** to look around the cockpit independently of ship facing. |
| `js1_button25` | MHG top coolie ↑ | `v_view_pitch_up` → *Look up* | Camera look up. `activationMode="hold"`. |
| `js1_button27` | MHG top coolie ↓ | `v_view_pitch_down` → *Look down* | Camera look down. `hold`. |
| `js1_button28` | MHG top coolie ← | `v_view_yaw_left` → *Look left* | Camera look left. `hold`. |
| `js1_button26` | MHG top coolie → | `v_view_yaw_right` → *Look right* | Camera look right. `hold`. |
| `js2_button63` | MTQ Left Module face | `v_view_zoom_in` → *Zoom in (3rd person)* | Zoom camera in. |
| `js2_button64` | MTQ Left Module face | `v_view_zoom_out` → *Zoom out (3rd person)* | Zoom camera out. |
| `js1_button21` | MHG lower hat center press | `v_ads_toggle` → *Vehicle ADS (Toggle)* | Cockpit zoom/"ADS" view (in-ship binoculars-style zoom). |

### On-foot / spectator / interaction zoom — `player`, `spectator`, `player_choice`

| Input | Control | Action → In-game label | What it does |
| --- | --- | --- | --- |
| `js2_button63` | MTQ Left Module face | `zoom_in` / `spectate_zoom_in` / `pc_zoom_in` | Zoom in while on foot, spectating, or in interaction mode. |
| `js2_button64` | MTQ Left Module face | `zoom_out` / `spectate_zoom_out` / `pc_zoom_out` | Zoom out in those same contexts. |

> The same two MTQ buttons (63/64) drive zoom in **four** contexts (ship view, on-foot, spectator, interaction) — each context has its own action map, so there's no conflict.

### Mining — `spaceship_mining`

These reuse MHG controls; active only in **Mining** operator mode.

| Input | Control | Action → In-game label | What it does |
| --- | --- | --- | --- |
| `js1_button1` | MHG trigger | `v_toggle_mining_laser_fire` → *Fire Mining Laser* | Fire/extract with the mining laser (reuses the gun trigger). |
| `js1_button22` | MHG rocker ↑ | `v_increase_mining_throttle` → *Mining Laser Power - Increase* | Raise laser power toward the fracture window. |
| `js1_button23` | MHG rocker ↓ | `v_decrease_mining_throttle` → *Mining Laser Power - Decrease* | Lower laser power. |
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

---

## 5. Operator-mode reuse (mining & salvage)

The MHG trigger and hats are deliberately **shared** across flight, mining, and salvage. Which action fires depends on the seat's **operator mode** (set via the `v_set_*_mode` buttons on the MTQ thumb hat, or `v_toggle_missile_mode`):

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
5. **Unbound hardware you could still use:** AB6 right "Dial" lever (60/61/62) and most of the left "Slider" (57/58), MTQ Right/Left module hats (52–61), MTQ rotary dial, encoder center-presses (13/16), keypad has spares, and the spare analog axes (Dial/RX/Slider + module X/Y). Plenty of room for power-triage (F5–F7), shield-pip controls, MFD navigation, mining/salvage analog beam-spacing, or VOIP.
6. **Device-instance fragility:** see the warning in §1 — keep USB enumeration order stable so `js1`/`js2` don't swap.

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

*Last reviewed for Star Citizen Alpha 4.8 (2026-06-22). Update the version stamp and the catalogue file when you refresh the database.*
