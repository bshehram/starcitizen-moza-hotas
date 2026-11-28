# MOZA HOTAS - Star Citizen Binding Profile (`MOZA.xml`)

This folder holds a custom Star Citizen control-mapping profile for a **MOZA** flight setup.
This document explains, in detail, **what every bound control does**, **how the XML profile format works**, and **how to keep the keybind reference database up to date**.

- **Profile file:** [`MOZA.xml`](MOZA.xml) - the actual bindings loaded by the game.
- **Master action catalog:** [`reference/SC_KEYBINDS_DATABASE_v4.10.md`](reference/SC_KEYBINDS_DATABASE_v4.10.md) - every action the installed game build defines (1,104 entries across 50 actionmaps), grouped by its **true actionmap**, with the in-game label, description and the game's default keyboard/joystick/gamepad bindings. Read straight out of the game's own `Data.p4k`. Versioned to the SC patch it was read from (**4.10** - build `4.10.201.48085`, the Alpha 4.10.3 line).
- **Game-data tool:** [`tools/gamedata.py`](tools/gamedata.py) - `check` pre-flights `MOZA.xml` against the installed build (unknown actions, wrong actionmaps, un-overridden game defaults); `catalog` regenerates the catalog above. See [Refreshing the keybind database](#7-refreshing-the-keybind-database) and [§10](#10-authoritative-actionmaps---local-sources--validation).
- **Fleet:** the ships this profile is tuned for, and which controls matter on each, are in [§11](#11-fleet---what-each-ship-uses).
- **Device diagrams:** `diagrams/MOZA_AB6.png`, `diagrams/MOZA_MHG.png`, `diagrams/MOZA_MTQ.png` - the manufacturer button-number maps these bindings are based on. **Do not delete these** - they're the source art for the reference cards below.
- **Button-reference cards:** [`cards/MOZA_MHG_AB6_ref.png`](cards/MOZA_MHG_AB6_ref.png) (js1: grip 1-29 **+** base 49-62, combined) and [`cards/MOZA_MTQ_ref.png`](cards/MOZA_MTQ_ref.png) (js2 throttle 1-65) - printable **US-Letter landscape (11×8.5)** "cheat sheets": each manufacturer diagram is split into its sub-views and stacked large in the left ~60%, beside a **button# → function** lookup table in the right ~40%. The `.svg` next to each PNG is its editable source. See [Regenerating the button-reference cards](#8-regenerating-the-button-reference-cards) (§8).
- **Card generator:** [`tools/regen_cards.py`](tools/regen_cards.py) - rebuilds both cards from the manufacturer diagrams + the binding tables embedded in it. Re-run after any binding change.
- **All tooling is Python 3** and runs on Windows, macOS or Linux; one-time setup is `python -m pip install -r tools/requirements.txt`. The tools were PowerShell until 2026-11-23. Only the game-data tools (`gamedata.py`, `validate_actionmaps.py`) need the game installed (§10); the cards and the XML can be worked on from any machine.
- **Session brief:** [`STARCITIZEN.md`](STARCITIZEN.md) - the user's standing brief for starting a new Claude session here (they type `@STARCITIZEN.md`). It covers how to ramp up, their working preferences, what needs approval, and the recurring asks, including the gameplay work (logs, screenshots, mining and crafting plans, the game plan page) that this document doesn't cover. It holds standing preferences and routines only; current state lives in memory and on the game plan page.

> Every action name, actionmap and in-game label below was re-checked against the game's own `defaultProfile.xml` / `global.ini` for build `4.10.201.48085` (2026-11-20); the "what it does" text is from earlier starbinder-era descriptions plus community references. Where the inline comments in `MOZA.xml` are imprecise or wrong, this file says so in a **⚠ Note**.

### Folder layout

The root holds the files the workflow needs front-and-center — the profile, plus the public-repo `README.md`/`LICENSE`, this doc and the session brief `STARCITIZEN.md`; everything else is filed by role. **`MOZA.xml` must stay in this folder** - it's the path Star Citizen loads control profiles from (subfolders are ignored by the game, so they're safe for our own files).

```
mappings/
├─ MOZA.xml                  ← the profile the game loads (keep in root)
├─ README.md                 ← human-facing entry point (links only to other README.md files)
├─ CLAUDE.md                 ← this document - the full Claude-facing reference (keep in root)
├─ STARCITIZEN.md            ← the user's session brief for Claude: ramp-up, preferences, recurring asks
├─ LICENSE                   ← MIT
├─ .gitignore
├─ dashboard/                ← side-screen dashboard, being built in stages (the plan and its status are in PLAN.md)
│   └─ PLAN.md (starts with where the build stands) · README.md · CLAUDE.md · scdash.py (`timeline`, `run`, `start`, `stop`, `status`, `replay`) · scdash/ · web/ · design/ · reference/ · tests/
├─ diagrams/                 ← manufacturer button-number maps (source art - do not delete)
│   └─ MOZA_AB6.png · MOZA_MHG.png · MOZA_MTQ.png · README.md · CLAUDE.md
├─ cards/                    ← generated button-reference cheat sheets (PNG + editable SVG)
│   └─ MOZA_MHG_AB6_ref.{png,svg} · MOZA_MTQ_ref.{png,svg} · README.md · CLAUDE.md
├─ reference/                ← bulk reference material
│   └─ SC_KEYBINDS_DATABASE_v4.10.md · MOZA_BINDINGS.html · README.md · CLAUDE.md
└─ tools/                    ← regeneration + validation scripts (run from the project root)
    └─ gamedata.py · validate_actionmaps.py · regen_cards.py · requirements.txt · README.md · CLAUDE.md
```

> **Docs convention.** Every folder has a `README.md` (human-facing) and a `CLAUDE.md` (working
> notes for whoever Claude is editing that folder). The rule for both: **`README.md` files link
> only to other `README.md` files** (so the human docs stay self-contained and never send a
> reader into a Claude doc), while **`CLAUDE.md` files may link to each other and to README
> files.** Keep that rule when editing either. The root `STARCITIZEN.md` counts as a Claude doc:
> it may link to `CLAUDE.md`, and README files mention it without linking to it.

---

## 1. Hardware setup

| Game device | Physical hardware | Button range | Axes used |
| --- | --- | --- | --- |
| **`js1`** (joystick instance 1) | **MOZA MHG** flight-stick grip mounted on the **MOZA AB6 FFB** base | Grip = **1–29**, Base = **49–62** | `js1_x` (roll), `js1_y` (pitch), `js1_rotz` (yaw / twist), plus `js1_slider1`/`js1_slider2` (the AB6 "Slider"/"Dial" lever analog halves - present but **unbound**) |
| **`js2`** (joystick instance 2) | **MOZA MTQ** Throttle Panel (Mission Throttle Quadrant) | **1–65** (44–48 unused/absent) | `js2_roty` (throttle forward), `js2_slider2` / `js2_slider1` (FLAPS / SPEEDBRAKE levers), `js2_x` / `js2_y` (mini-stick); unbound: `js2_rotx` (the forward axis's twin) and the reverse-thrust pair `js2_rotz` / `js2_z` (reverse is the MHG stick press since 2026-11-26, and since 2026-11-27 the device no longer outputs that pair: §1.1) |

The MHG grip and the AB6 base report as **one** DirectInput device (`js1`): grip buttons are numbered 1–29, the base's own buttons continue at 49–62 (there is a 30–48 gap with no physical buttons). The MTQ throttle is a **separate** device (`js2`).

> **⚑ Scope - ships only:** This MOZA rig is used **only when piloting a ship**. On foot / first-person / interaction **and when driving ground vehicles** the user plays on an **Xbox controller** instead - never the MOZA gear. So this profile deliberately binds **only ship/seat contexts**; there are **no `player` / `spectator` / `player_choice` (on-foot) or `vehicle_*` (ground) bindings**, and none should be added. The only entries in those maps are **clears** of game defaults that would otherwise stay live on the stick (see *Cleared game defaults* in §4). The Xbox controller runs on the game's **stock gamepad layout** - there is no custom gamepad file to maintain.

Product GUIDs as written in the profile:
- `js1` → `MOZA AB6 FFB Base  {1002346E-0000-0000-0000-504944564944}`
- `js2` → `MOZA MTQ Throttle Panel  {1101346E-0000-0000-0000-504944564944}`

> **Why instance numbers matter:** `js1`/`js2` are assigned by the order the game enumerates USB devices. If Windows re-enumerates them (USB port change, hub, reconnect order), `js1` and `js2` can **swap**, and every binding in this file will point at the wrong stick. If your bindings suddenly land on the wrong device, that's the cause - re-plug in the original order, or swap the `instance="1"`/`instance="2"` Product lines. *(Qualified on 2026-11-27: the order of the `Connected joystickN` lines in `Game.log` is not by itself the instance order. See the note below.)*
>
> **⚠ There is a third "joystick" on this PC - the keyboard.** The **Razer Huntsman V3 Pro** (an analog keyboard) exposes a DirectInput game controller, `Joystick (Razer Huntsman V3 Pro)  {02A61532-…}`. Normally the game enumerates AB6 = joystick 1, MTQ = joystick 2, Razer = joystick 3 and it is harmless. But in twelve logged launches (2026-02-02, 02-04, 03-08, 03-15 twice, 04-03, 06-24, 06-25 twice, 08-22, 08-23 and 11-24 at 11:34 AM; counted by the dashboard's log reader over all 409 logs on 2026-11-27, where this note used to know only the two August ones) the **AB6 was not detected at launch** (an FFB base that is powered off or still booting does not enumerate) and the **Razer keyboard took slot 1** - every `js1_` binding then pointed at the keyboard and the stick was dead. Check with `Connected joystick0/1/2` near the top of `…\LIVE\Game.log`, or run `python dashboard/scdash.py timeline`, whose header lists the joysticks in order with a PASS or FAIL. **The order of those lines is not the whole story (2026-11-27, 12:57 PM launch):** the log listed the keyboard first, the throttle second and the AB6 **third** (`joystick0` = Razer, `joystick1` = MTQ, `joystick2` = AB6), and the user, sitting in the Golem that session, reported that **the AB6 and the MTQ both worked fine**. So with all three devices present, a different order in the log did not move the stick off `js1`. Likely reason, not yet confirmed: the game's saved profile pins each instance to a device by its `Product` GUID (`…\Profiles\default\actionmaps.xml` listed instance 1 = AB6, 2 = MTQ, 3 = Razer before that launch). The game did **not** rewrite that file when the session ended at 2:12 PM (its timestamp stayed at 7:27 AM; it is rewritten after a profile is loaded, and none was), so it still lists the same three and the question stays open. A way to settle it: load `MOZA.xml` in a session whose log lists the devices in another order, quit, and read which device the file then gives instance 1. What is still a real failure is the AB6 **missing** from the list. An earlier version of this note, written an hour before the user's report, stated as fact that `js1_` pointed at the keyboard in that session: that was an inference from the log and it was wrong. Fix: make sure the AB6 is powered and seen by MOZA Cockpit **before** starting the game, then restart the game; turning off the keyboard's controller/gamepad mode in Razer Synapse would remove the risk entirely. Device IDs were re-verified after the Nov-2026 MOZA Cockpit update: AB6 = `VID_346E PID_1002`, MTQ = `VID_346E PID_1101`, DirectInput names unchanged - the Product GUIDs above still match.

### 1.1 Device-side settings (MOZA Cockpit)

The profile depends on a few settings that live **on the devices**, not in `MOZA.xml`. As of MOZA Cockpit **1.5.48** only the **AB6 base has presets** - the MHG grip and the MTQ throttle have none - so their settings can't be restored from a preset, and a Cockpit or firmware update can change them without warning. **Check this table after every MOZA update.** *Seen* = what the user's Cockpit screenshots showed on 2026-11-20 (firmware AB6 1.1.6.2 · MHG 1.1.1.11 · MTQ 1.1.1.30). On 2026-11-26 a screenshot showed Cockpit updated to **2.0.0.111**. MTQ firmware was still 1.1.1.30, and the MTQ settings below were unchanged: Reverse Thrust, Throttle Input Sync on, Speedbrake Split Mapping, Flaps Axis Mode. **After the Windows reinstall of 2026-11-27** (MOZA Cockpit installed fresh; its title bar reads **1.1.5.48**, an older release than the 2.0.0.111 of the day before and probably the one this document calls 1.5.48; MTQ firmware still 1.1.1.30), the user's screenshot of the *Throttle Detent Setup* dialog that evening showed: Limit Output Mode on **Reverse Thrust**, "the extra reverse-thrust axes Z and RZ have been Enabled", Speedbrake on Split Mapping, Flaps on Axis Mode, and the dialog's neutral band at about 11 % to 15 % of lever travel, the same Rev idle and Idle marks as on 2026-11-26. The user had set the detent mode and done the Idle calibration themselves just before. In the shot the levers stood at 29.6 % of travel and read X = Y = 11227 with Z = RZ = 0, which is what that position should give (about 17 % forward throttle). The user then confirmed the detent rests at 13 % and that they calibrated with a 2 % buffer on each side of it (Idle about 15 %, Rev idle about 11 %), and that they adjusted the MHG settings as well (their report; the mini-stick mode was not seen in a screenshot). Not shown: the reading with the levers resting in the detent, which should be 0 on all four. Not reported yet: the AB6 Spring (Cockpit's presets were not backed up, so "Star Citizen (Green)" may need making again).

| Device → page | Setting | Needed | Why | Seen 2026-11-20 |
| --- | --- | --- | --- | --- |
| MHG → Basic Settings → Grip Settings | **Mode 1** (the mini-stick's active mode) | **Button Mapping** | The top mini-stick must emit **buttons 25-29** - the four strafe directions and, on the press, **reverse** are bound to them (strafe since 2026-11-23, reverse since 2026-11-26; the press was the decoupled toggle in between, and before that the stick held the target-acquisition cluster). In **Axis Mode** it emits the RX/RY axes (`js1_rotx` / `js1_roty`, unbound) and **no buttons**, so those five bindings go dead. | Found on **Axis Mode**; **fixed the same day** - now Button Mapping (both modes) ✔ |
| MHG → Grip Settings | **Press stick to switch mode** | **Off** | Otherwise pressing the mini-stick (button 29 = reverse) flips it between the two modes in flight. | Found **On**; **fixed the same day** - now Off ✔ |
| MHG → Yaw Axis Settings | Enable Yaw Axis Output | On | Twist = `js1_rotz` = yaw. | On ✔ |
| MTQ → Settings → Throttle Detent Settings → *Axis Detent Settings* | **Limit Output Mode** | **Disabled** (since 2026-11-27) | With the lever's range calibrated between the two detents (next row), *Disabled* gives one forward axis that is 0 at the idle detent and full at the forward detent, which is what the user wanted once reverse had moved to the MHG stick press: no need to push past the forward detent for full power. The other modes: *Reverse Thrust* (the rig's setting from 2026-11-20 to 2026-11-27: the ~13 % of travel behind the idle detent became its own axis pair, **Z** / **RZ**, which held a proportional reverse until 2026-11-26 and nothing after) and *Button* (detent buttons 32–35 / 41 / 42 - the pre-2026-11 setup, reverse on button 34, all-or-nothing). An earlier version of this row warned against *Disabled* because it puts the forward axis's zero at the bottom of the calibrated range: with the range ending at the rear stop that meant thrust at the idle detent, and with the range starting at the idle detent it is exactly right. | 2026-11-20: found on Button, switched to Reverse Thrust ✔. **2026-11-27: set to Disabled by the user** (their report: "for throttle detent settings i just chose the disable option"; not seen in a screenshot) |
| MTQ → Settings → **Panel Axis Calibration** (the *Dual Throttle Calibration* dialog) | Lever range | Swept **only between the idle detent and the forward detent** during the countdown | The calibration records the lowest and highest positions the levers pass through. Kept between the two detents, it makes the idle detent 0 % and the forward detent 100 %, so the whole power band sits between them and travel outside them adds nothing. Swept through the full travel (rear stop to front stop, the factory way) the forward detent is only about 75 % throttle. **If the ship ever creeps forward with the lever resting in the idle detent** (the detent has slack; it crept once before, when zero was calibrated exactly on it), redo the calibration starting a few mm forward of the idle detent. SC can't fix that itself: its axis options are center-symmetric (see the throttle comment in `MOZA.xml`). | **2026-11-27: done by the user** ✔ (their report: "i just swept it back and forth during calibration within the detent space so it would think that is the entire 0-100 range"; they said it did the trick, and a 7-minute session followed at 6:13 PM, which I take to be the test flight). The readings at the two detents were not seen. |
| MTQ → Throttle Detent Settings | **Idle** / **Rev idle** marks | Not used since 2026-11-27 | They exist only in *Reverse Thrust* mode. History, in case that mode comes back: "Idle" is where forward throttle starts and "Rev idle" is where reverse starts (calibrated at the rear stop, the reverse zone has zero size and Z / RZ stay 0). The detent rests at 13 % of full travel; the working marks were Idle at ~15 % and Rev idle at ~11 %, a 2 % buffer each side, which stopped the forward creep seen with Idle exactly on the detent. | 2026-11-20: first calibrated ✔. 2026-11-26: redone at ~15 % / ~11 % ✔ (in Cockpit 2.0.0.111, resting in the detent, X, Y, Z and RZ all read 0). 2026-11-27: redone the same way after the Windows reinstall, then retired the same evening. |
| MTQ → Settings | Throttle Input Sync | On | The two throttle bodies report as one synced pair; only `js2_roty` is bound. | On ✔ |
| MTQ → Settings | Flaps | **Axis Mode** (or any mode that outputs the axis) | Its axis (`js2_slider2`) is mining laser power. Axis Mode drops the detent buttons 36-40, which are unbound anyway. | Axis Mode ✔ |
| MTQ → Settings | Speedbrake | **Split Mapping** (or any mode that outputs the axis) | Its axis (`js2_slider1`) is salvage beam spacing; the DOWN / ARMED clicks (43 / 31) are unbound. | Split Mapping ✔ |
| MTQ → Settings | Signal Hold Time | 20 ms is fine unless clicks get lost | Length of the pulse an encoder click sends (speed limiter, accel limiter, zoom dial). Cockpit's own hint says to raise it if the game misses signals. | 20 ms |
| AB6 → Panel Settings | Slider Axis Mode (Left / Right) | either | Both base levers are unbound. In **Button Mapping** they emit only buttons 57-62 and no axis. | Button Mapping / Button Mapping ✔ |
| AB6 → Basic Settings | Spring | above zero | The base's own Spring is what centers the stick in a game that sends no force-feedback effects. | Integrated FFB · Spring 75 % ✔ (preset "Star Citizen (Green)") |

> **How the MHG finding was read:** the repo's own `diagrams/MOZA_MHG.png` (captured June 2026) shows buttons **25-29** as a hat around the top-center thumb control. The 2026-11-20 screenshot of the same page shows that control as an analog stick with live RX / RY values and **no 25-29 at all** - the signature of Axis Mode. To fix: set Mode 1 to **Button Mapping** (the swap button between the two mode boxes exchanges them), then switch **Press stick to switch mode** off. The Button Number diagram should then show 25-29 around the top stick again. *(Done 2026-11-20: a follow-up screenshot shows both modes on Button Mapping, the switch off, and 25-29 back on the diagram.)*

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
| `<ActionMaps>` | Root. `profileName` is the name shown in-game. The `version`/`optionsVersion`/`rebindVersion` attributes are CIG's schema version stamps - leave them as the game wrote them. |
| `<CustomisationUIHeader>` | Metadata for the profile picker (`label`, `description`) and the `<devices>` list declaring which joystick instances this profile expects. |
| `<options>` | Per-device options. The `Product="…GUID…"` string binds an instance number to a specific physical device. Child tags hold per-axis options such as **axis inversion** (e.g. `<flight_move_pitch invert="0"/>` - set `invert="1"` to flip pitch). |
| `<modifiers>` | Optional custom input modifiers; empty here. |
| `<actionmap>` | A group of related actions (a "context"). `name` must match a CIG-defined action map (e.g. `spaceship_movement`, `spaceship_weapons`). |
| `<action>` | A single bindable game action. `name` must be a real CIG action (e.g. `v_pitch`). See the master catalog for valid names. |
| `<rebind>` | The actual binding. `input="…"` is the physical control. Optional `activationMode="…"` changes press behavior. |

### 2.2 The `input=` naming convention

Format: **`<device><axis|button>`**

- **Device prefix:** `js1_`, `js2_`, … (joysticks), `kb1_` (keyboard), `mo1_` (mouse), `gp1_` (gamepad).
- **Buttons:** `js1_button5` → button index 5 on `js1` (indices match the manufacturer diagrams). Hat directions and 3-position slider/lever positions each register as their **own** button index.
- **Axes:** `js1_x`, `js1_y`, `js1_z`, `js1_rotx`, `js1_roty`, `js1_rotz`, `js1_slider1`. On a typical stick `x`=roll, `y`=pitch, `rotz`=twist/yaw. On the MTQ the levers expose as `roty`/etc. (the configurator labels them Dial / RX / RY / Slider).
- To **clear** a binding, bind the action to the device prefix followed by a single space: **`input="js1_ "`** for a joystick default (CIG's own `layout_all_blank.xml` clears joystick binds in exactly this form). A clear is how you remove a **game default** you don't want - see §2.5.

### 2.3 `activationMode` (and other `<rebind>` options)

`activationMode` controls how the press is interpreted. Used in this profile:

- **`hold`** - the action is active only while the control is held. **No binding sets it explicitly** - `v_view_look_behind` (MHG pinky button) already behaves this way natively (rear view while held, snaps back on release), so its binding is left bare. Add `activationMode="hold"` only if a control's default ever proves wrong.
- **`delayed_press`** - fires once the control has been held ~0.25 s. **Two bindings set it explicitly:** `v_atc_loading_area_request` on the MTQ "ALT" key (`js2_button8`) - its stock mode is `tap`, the same as `v_atc_request` on that key, so without the override one press would fire both requests - and, since 2026-11-26, `v_jettison_volatile_cargo` on MTQ A1 (`js2_button1`), where the user wanted a hold so a brush of the key can't dump cargo. (LAMP on A4 carried one briefly on 2026-11-26 and was put back.)

Every action has a **stock activation mode** (the *Activation* column of the catalog). Two actions can share one key with no attributes at all when their stock modes differ - `tap` fires only on a release inside 0.25 s, `delayed_press` only after a 0.25 s hold - which is how the "AP" key carries *dock* (tap) and *autoland* (hold).

Other modes the game supports (not all used here): `press` (fire once on press), `tap`, `double_tap`, `hold_toggle`, `smart_toggle`. A `<rebind>` can also carry `multiTap="2"` (require N taps) and other attributes - only add these if you know you need them.

### 2.4 Same button in multiple action maps

A physical button can appear in several action maps because **only one action map is active for a given context/operator mode at a time**. For example `js1_button1` is the trigger for *Fire Guns* (`spaceship_weapons`), *Fire Mining Laser* (`spaceship_mining`), and *Fire Focused Salvage Beam* (`spaceship_salvage`) - the trigger does the right thing depending on which operator mode the seat is in. This is intentional and is how a small number of physical controls drive flight, mining, and salvage. See [Operator-mode reuse](#5-operator-mode-reuse-mining--salvage).

### 2.5 Game defaults stay live under a custom profile ("ghost" bindings)

Loading `MOZA.xml` does **not** start from a blank slate. The game first applies its own stock layout (`defaultProfile.xml`) and then lays this file's `<rebind>`s on top. Stock **joystick** bindings are written as bare `button12` / `x` / `slider1` and land on **joystick 1 (`js1`)**. So any action this file does not mention keeps its stock `js1` binding - and if that button is one this profile uses for something else, **one press fires both**.

- **An action holds exactly one joystick input, across all joystick instances.** Rebinding an action (to `js1` *or* `js2`) replaces its stock joystick binding. If a profile gives one action two `<rebind>` lines, the game keeps the **last** and silently loses the other. **Proven by the game's export after the 2026-11-26 load:**
  - `v_strafe_back` listed `js2_rotz` then `js1_button29`. The game kept only the button, and the throttle's reverse axis went dead.
  - `v_autoland` listed `js2_button10` then a `js1_ ` clear. The game kept only the clear, and Autoland went dead.
  - An earlier note here claimed a slot per joystick instance, on the strength of CIG's `layout_all_blank.xml` clearing `js1_ `, `js2_ ` and `js3_ ` in turn on every action. That reading was wrong: the three clears just overwrite one slot one after another.
  - So a clear next to a rebind is never needed, and is harmful if it comes second. `gamedata.py check` reports any action with more than one rebind as `MULTI-BIND`.
  - Each **device type** has its own slot (keyboard, mouse, gamepad, joystick). The stock keyboard binding of an action (`S` on `v_strafe_back`) stays live beside the joystick one.
- **Loading a profile is an overlay on what the game already holds, not a reset.** An action the file does not mention keeps its current binding, and that includes bindings from an *earlier version of this profile*. After the 2026-11-26 rework was loaded, the export still held nine bindings the new file had dropped: the old tap *Pin Selected Target* on `js2_button57` and the eight wing target-cycle actions on `js1_button49–56`, each double-firing with a new binding. `validate_actionmaps.py` lists these as `LEFTOVER`. To remove one, clear it in the game's Keybindings menu, or delete its `<action>` block from `…\Profiles\default\actionmaps.xml` with the game closed (how the nine were removed on 2026-11-26; a backup sits next to the file).
- An action this file never mentions keeps the stock one. The export in `Profiles\default\actionmaps.xml` can't show you these: it lists only what *differs* from stock, which is also why a binding identical to stock (`v_pitch` = `js1_y`, the trigger = mining-laser fire) is missing from it.
- `python tools/gamedata.py check` lists every un-overridden stock joystick binding as a `GHOST` and flags the ones sitting on an input this profile also binds.

Per the game data, this is how the stock *Landing System (Toggle)* came to share a button with the sub-target hat (found 2026-11-20; the overlap was read from the files, not observed in flight). The ghosts that mattered are cleared in §4 (*Cleared game defaults*); the ones deliberately left alone are listed there too.

---

## 3. Physical control reference

Button indices come directly from the MOZA configurator diagrams (`diagrams/MOZA_AB6.png`, `diagrams/MOZA_MHG.png`, `diagrams/MOZA_MTQ.png`).

### 3.1 `js1` - MHG grip (1–29)

| # | Physical control | # | Physical control |
| --- | --- | --- | --- |
| 1 | Main index **trigger** (blade) | 16 | Right hat - **center press** |
| 2 | Top-left face thumb button | 17 | Lower/front thumb hat - **up** |
| 3 | Lower side button (pinky side) | 18 | Lower hat - **right** |
| 4 | Upper thumb button | 19 | Lower hat - **down** |
| 5 | Lower-center face thumb button | 20 | Lower hat - **left** |
| 6 | Trigger **second stage** (front of trigger) | 21 | Lower hat - **center press** |
| 7 | Left thumb hat - **up** | 22 | Upper thumb **rocker - up** |
| 8 | Left thumb hat - **right** (near knurled wheel press) | 23 | Upper rocker - **down** |
| 9 | Left thumb hat - **down** | 24 | Upper rocker - **center** |
| 10 | Left thumb hat - **left** | 25 | Top coolie/POV hat - **up** |
| 11 | Left thumb hat - **center press** | 26 | Top coolie hat - **right** |
| 12 | Right hat - **up** | 27 | Top coolie hat - **down** |
| 13 | Right hat - **right** | 28 | Top coolie hat - **left** |
| 14 | Right hat - **down** | 29 | Top coolie hat - **center press** |
| 15 | Right hat - **left** | | |

### 3.2 `js1` - AB6 base (49–62)

| # | Physical control | # | Physical control |
| --- | --- | --- | --- |
| 49 | Left wing button 1 (top) | 56 | Right wing button 4 (bottom) |
| 50 | Left wing button 2 | 57 | Left **"Slider"** lever - top |
| 51 | Left wing button 3 | 58 | Left "Slider" lever - middle |
| 52 | Left wing button 4 (bottom) | 59 | Left "Slider" lever - bottom |
| 53 | Right wing button 1 (top) | 60 | Right **"Dial"** lever - top |
| 54 | Right wing button 2 | 61 | Right "Dial" lever - middle |
| 55 | Right wing button 3 | 62 | Right "Dial" lever - bottom |

> **Buttons 25–29 are the MHG's top mini-stick, not a fixed hat.** The "top coolie hat" in these tables is the round thumb control at the top-center of the grip head. It only reports as buttons 25–29 (4 directions + press) while MOZA Cockpit has it in **Button Mapping** mode; in **Axis Mode** it reports two analog axes and no buttons. See §1.1.

> **Wing buttons (49–56)** are plain **momentary pushbuttons** (physically labeled 1–4 per wing): 49–52 = **left** wing, 53–56 = **right** wing. Since 2026-11-26 they are the always-live **power panel** (§4 *Power management*).
>
> ⚠ **Note (corrected):** The left **"Slider"** (57/58/59) and right **"Dial"** (60/61/62) are **mixed-mode levers**, *not* button-only as an earlier version of this doc claimed. Each emits **both** its 3 detent buttons (57 = top/100 … 59 = bottom/0; 60 = top/full … 62 = bottom/0) **and** a continuous **analog axis** - the js1 slider-family `js1_slider1` / `js1_slider2` (which lever maps to which needs `joy.cpl` confirmation, the same counter-intuitive name↔number mapping seen on the MTQ). Both are **maintained** (stay where you leave them), so they suit set-and-hold analog values, not momentary actions. They are currently **UNBOUND** in this combat profile (see §6 for why). **Which of the two they emit is a MOZA Cockpit setting** (AB6 → Panel Settings → *Slider Axis Mode*, one dropdown per lever): on 2026-11-20 both were set to **Button Mapping** - buttons 57–62 only, no axis (§1.1). Switch a lever to an axis mode before giving it an analog job.

### 3.3 `js2` - MTQ throttle (1–65)

| # | Physical control | # | Physical control |
| --- | --- | --- | --- |
| 1 | Keypad **A1** | 25 | Lower-strip **toggle A** (metal 2-pos) - up |
| 2 | Keypad **A2** | 26 | Lower-strip **toggle A** (metal 2-pos) - down |
| 3 | Keypad **A3** | 27 | Lower-strip **toggle B** (metal 2-pos) - up |
| 4 | Keypad **A4** | 28 | Lower-strip **toggle B** (metal 2-pos) - down |
| 5 | Keypad **"NAV"** (mid-col top) | 29 | Lower-strip **toggle C** (gear-style plastic lever) - up |
| 6 | Keypad **"HDG"** (right-col top) | 30 | Lower-strip **toggle C** (gear-style plastic lever) - down |
| 7 | Keypad **"SPD"** (mid-col middle) | 36–40 | **FLAPS slider** (right, mixed buttons+axis): 40 rest "0" … 36 "FULL" - see slider note |
| 8 | Keypad **"ALT"** (right-col middle) | 31 / 43 | **SPEEDBRAKE slider** (far-left, mixed buttons+axis): 43 rest "DOWN", 31 "ARMED" - see slider note. *(32–35 / 41 / 42 = main-throttle detent buttons, sent only in MOZA's Button detent mode - see §1.1)* |
| 9 | Keypad **"FD"** (mid-col bottom) | 49/50/51 | Right Module **3-position switch** - 49 rest, 50 latched-forward, 51 momentary-back |
| 10 | Keypad **"AP"** (right-col bottom) | | |
| 11 | Upper round encoder - CCW/left | 52–56 | Right Module **"WPN" hat** (smaller, 4-way + press): 56↑ 55↓ 53→ 54← 52=press |
| 12 | Upper encoder - CW/right | 57–61 | Right Module **"COM" hat** (larger, 4-way + press): 61↑ 60↓ 58→ 59← 57=press |
| 13 | Upper encoder - center press | 62 | Left Module **analog mini-stick press** (stick axes `js2_x`/`js2_y`, center 32767) |
| 14 | Lower encoder - CCW/left | 63 | **Throttle-lever dial** - forward/CW click (incremental encoder; pairs with 64) |
| 15 | Lower encoder - CW/right | 64 | **Throttle-lever dial** - back/CCW click (incremental encoder; pairs with 63) |
| 16 | Lower encoder - center press | 65 | Left Module face button |
| 17–21 | **Rotary mode-selector knob** - 5 detents physically engraved **1–5** (17 = pos 1/full CCW … 21 = pos 5/full CW); rests on one | | |
| 22/23/24 | 3-position rocker (23 L / 22 C / 24 R) | | |

**Axes** (confirmed in `joy.cpl`): the **throttle is a synced pair of bodies** reporting as **X Rotation + Y Rotation** = `js2_rotx` + `js2_roty`; the throttle is bound on `js2_roty` (`v_strafe_forward`) and its twin `js2_rotx` is left alone. With MOZA's **Reverse Thrust** detent mode on (§1.1) the lever travel behind the idle detent reports as a second pair, **Z + Z Rotation** = `js2_z` + `js2_rotz` (MOZA's names). Both are unbound since the evening of 2026-11-26: reverse is the MHG stick press (`js1_button29` on `v_strafe_back`, §6 item 24). From 2026-11-20 until then `js2_rotz` was a proportional reverse. Raw readings seen in MOZA Cockpit on 2026-11-20, before the idle calibration: rear stop 0, lower (idle) detent ≈ 8400, forward detent ≈ 51600, front stop 65535 - so with the lever's range calibrated over its full travel the forward detent sat at roughly 75 % throttle. **Since 2026-11-27 the range is calibrated between the two detents and the detent mode is *Disabled* (§1.1, §6 item 25):** `js2_roty` runs from 0 at the idle detent to full at the forward detent, and the Z / RZ pair is not output. The **Left Module mini-stick** = `js2_x` (camera yaw) / `js2_y` (camera pitch) drives **camera look**. The two side sliders are the slider-family axes: **FLAPS** (far right) = joy.cpl's **"Slider"** axis = `js2_slider2`, and **SPEEDBRAKE** (far left) = joy.cpl's **"Dial"** axis = `js2_slider1` - both set in MOZA Cockpit to output their axis (§1.1), now bound to mining-power / salvage-spacing (see slider note). *(The joy.cpl name↔SC number is counter-intuitive - "Slider"→slider2, "Dial"→slider1 - confirmed via SC's in-game binder, not guessable from joy.cpl.)*

> **Throttle-lever dial (buttons 63/64):** a **detented thumb dial on the throttle lever**, *not* two Left-Module face buttons as an earlier version of this doc claimed. It is an **incremental rotary encoder** - each forward/CW click pulses button **63**, each back/CCW click pulses button **64** (a momentary pulse per click, no held/latched state). It is therefore only suited to **increment/decrement** pairs - it can't cleanly hold or toggle. It is **buttons-only** (no axis); the configurator's analog **"Dial"** axis is a *different* control - `joy.cpl` confirmed that axis is the **SPEEDBRAKE slider**, not this wheel (an earlier version of this doc guessed the Dial axis was this wheel - wrong). Note the "increment/decrement only" caveat is soft - a single deliberate click *does* fire a toggle once (ESP worked fine on it); it's just that *rolling* the wheel flips a toggle repeatedly, which is why ESP was moved off to A4. 63/64 drive `v_view_dynamic_zoom_rel_*`, which works in the **cockpit**; the 3rd-person `v_view_zoom_*` pair that once rode along on the same clicks was removed as dead. The other three zoom pairs (`zoom_*` / `spectate_*` / `pc_*`) are on-foot/spectator/interaction and can't fire from a pilot seat (rig is **vehicle-only**, see §1). The `view_fov`+camview experiment was **removed** - 3rd-person FoV zoom needs a *held* modifier (kb F4), and a momentary dial click can't hold anything (confirmed: stacking `view_fov` + `view_enable_camview_mode` on one click did nothing). So the dial does **cockpit zoom only**; 3rd-person FoV zoom stays on the keyboard (or a MOZA Pithouse macro that emits "hold F4 + tap NumPad±" per click). Buttons 63/64 firing is **confirmed in joy.cpl**. *(Buttons 62 and 65 are still believed to be the Left-Module mini-stick press and a face button respectively - re-verify if you find otherwise.)*

> **Side sliders - FLAPS (right) & SPEEDBRAKE (left):** two smooth-action levers. What each emits is a MOZA Cockpit setting (MTQ → Settings → *Flaps* / *Speedbrake*, §1.1); the profile only needs their **analog axes** (joy.cpl's **"Slider"** and **"Dial"**). In the June 2026 software both ran in a buttons-**and**-axis "mixed mode", which is what the detent numbers below describe. On 2026-11-20 FLAPS was set to **Axis Mode** (axis only - the detent buttons 36–40 are not emitted) and SPEEDBRAKE to **Split Mapping** (the 43 / 31 clicks plus the axis).
> - **FLAPS** (right): 5 engraved detents - **"0"** = button **40** (rest) · **"1"** = 39 · **"2"** = 38 · **"3"** = 37 · **"FULL"** = 36 - plus a smooth axis across the full throw.
> - **SPEEDBRAKE** (far left): rests at button **43** (engraved **"DOWN"**); a gentle nudge to the single click hits button **31** (**"ARMED"**); past that it slides smoothly to the bottom with **no further buttons** - just the axis down to 0.
>
> Both levers stay where you leave them (**maintained**, not self-centering), so they suit **set-and-hold analog values**, *not* momentary actions. **Now bound and confirmed in-ship (Golem + Salvation):** **FLAPS ("Slider" axis = `js2_slider2`) → mining laser power** (`v_mining_throttle`; rest ≈ 20% laser floor → FULL = 100%, no invert) and **SPEEDBRAKE ("Dial" axis = `js2_slider1`) → salvage beam spacing** (`v_salvage_beam_spacing_abs`; auto-mapped, no range to set) - both **modal** (active only in Mining / Salvage operator mode, so no flight/combat conflict). The **X/Y-Rotation** axes are the synced throttle pair, *not* these sliders. *(Buttons 32–35 and 41 / 42 are the main-throttle **detent buttons**, sent only while MOZA's Limit Output Mode is *Button*: observed on 2026-11-20 in that mode, the levers at rest lit **33 + 35**, pulled fully back they lit **32 + 34**, and 41 / 42 sit at the forward detent; 32 / 33 / 41 belong to the left body and 34 / 35 / 42 to the right, lighting in pairs because the bodies are synced. Until 2026-11 reverse was bound to button 34. The rig now runs in *Reverse Thrust* mode, where none of these are sent and reverse is the `js2_rotz` axis - §1.1.)*

> **Keypad labels (physical):** All keypad soft buttons (1–10) are **momentary press**. Left column = **A1–A4** (buttons 1–4). The mid+right 2×3 grid is engraved with MCP-style autopilot labels - **NAV** (5) · **HDG** (6) / **SPD** (7) · **ALT** (8) / **FD** (9) · **AP** (10) - repurposed to SC functions (see §4). The rotary knob's detents are engraved **1–5**.

> ⚠ **Note:** Buttons **44–48** are not present/labeled on the MTQ diagram - don't bind to them. The **rotary mode-selector knob does emit numbered buttons**: its five detents are **17–21** (see the row above). *(An earlier version of this doc wrongly described 17–21 as a "thumb directional hat" and claimed the rotary emits no buttons - both were incorrect; the diagram shows the knob's detents numbered 17–21.)*

---

## 4. Complete binding reference

Every binding currently in `MOZA.xml`, grouped by action map, with the official in-game label and what it does. **Input** = the XML `input=` value; **Control** = where that is on the hardware. The file holds **120 bindings + 10 cleared game defaults across 21 actionmaps**, one `<rebind>` per action (the clears have their own table at the end of this section).

> **Labels are the exact strings the 4.10 Keybindings menu shows** (from `global.ini`), so you can find an action in-game by searching for it. Two are worth knowing because the game's wording is unhelpful: `v_starmap` is listed simply as *Map*, and the game labels **both** `v_lights_on` and `v_lights_off` *Headlights (Enable)* - a CIG label slip; the tables below keep "Off" for the second one.

### Power management - `spaceship_power`

| Input | Control | Action → In-game label | What it does |
| --- | --- | --- | --- |
| `js1_button49` | AB6 left wing 1 (top) | `v_power_toggle_weapons` → *Toggle Power - Weapons* | Cuts/restores weapon power. Only meaningful in SCM (weapons are stowed in NAV). |
| `js1_button50` | AB6 left wing 2 | `v_power_toggle_thrusters` → *Toggle Power - Thrusters* | Cuts/restores power to propulsion. Off = can't maneuver, lower engine signature (cold running). |
| `js1_button51` | AB6 left wing 3 | `v_power_toggle_shields` → *Toggle Power - Shields* | Cuts/restores shields. Re-enabling incurs a boot delay; shields are offline in NAV mode regardless. |
| `js1_button52` | AB6 left wing 4 (bottom) | `v_engineering_assignment_reset` → *Reset Assignments* | **Reset** the power assignment to balanced/even. |
| `js1_button53` | AB6 right wing 1 (top) | `v_engineering_assignment_weapons_increase` → *Weapons - Increase (Tap)* | Tap power toward **weapons**. Mirrors the weapons toggle on the left wing. |
| `js1_button54` | AB6 right wing 2 | `v_engineering_assignment_engine_increase` → *Engines - Increase (Tap)* | Tap power toward **engines** (thrusters). |
| `js1_button55` | AB6 right wing 3 | `v_engineering_assignment_shields_increase` → *Shields - Increase (Tap)* | Tap power toward **shields**. |
| `js1_button56` | AB6 right wing 4 (bottom) | `v_engineering_assignment_shields_max` → *Shields - Set to Max (Hold)* | **Hold** to put all power into shields (burst-tank; returns on release). Stock mode `hold`. |
| `js2_button23` | MTQ 3-pos rocker **left** | `v_power_set_off` → *Set Power Off* | Dedicated master power **OFF** (always off, not a toggle). |

> **Power panel (AB6 wings `js1_button49–56`, since 2026-11-26):** the user's layout. The **left wing** holds the power **toggles** (weapons / thrusters / shields, top to bottom) and the assignment **reset**; the **right wing** mirrors it with the assignment **taps** (weapons + / engines + / shields +) and **hold = shields to max**. `spaceship_power` is always live, so the eight wing buttons carry **nothing else** in any mode: the combat target-cycle bank that sat there was deleted (the user never used it; general cycling is on the COM hat and the MHG hats), and the Mining / Salvage banks moved to the MHG right hat (§6 item 22). Before this, the toggles were on MTQ keypad A1–A3 and the pips on the "WPN" hat, which now carries shield faces. No decrease binds - reset rebalances. **⚠ Action-map note:** `v_engineering_assignment_*` are placed in **`spaceship_power`** (the catalog confirms); if a button does nothing in-game, the action map is the suspect.

> **Master power rocker (`js2_button22/23/24`, bottom-center 3-position):** **left (23)** = master power **OFF** (`v_power_set_off`); **right (24)** = Flight Ready / power **ON** (`v_flightready`, in `spaceship_general`); **center (22)** = resting position, intentionally unbound. Keypad A1 is the mining **jettison** (hold), A2 / A3 fire the salvage beams left / right, and A4 toggles LAMP night-vision (see Mining, Salvage and Mode switching & LAMP).

### Ship systems & utilities - `spaceship_general`

| Input | Control | Action → In-game label | What it does |
| --- | --- | --- | --- |
| `js2_button24` | MTQ 3-pos rocker (right) | `v_flightready` → *Flight / Systems Ready* | One-press full startup: power + avionics + engines + shields to flight-ready. Toggle - press again to spin down. |
| `js2_button25` | MTQ **toggle A** up | `v_unlock_all_doors` + `v_open_all_doors` | **Both** actions share this throw: unlocks **and** opens all doors/ramps - "open up the ship". |
| `js2_button26` | MTQ **toggle A** down | `v_lock_all_doors` + `v_close_all_doors` | **Both** share this throw: closes **and** locks everything - "seal the ship". |

### Lights - `lights_controller`

| Input | Control | Action → In-game label | What it does |
| --- | --- | --- | --- |
| `js2_button27` | MTQ **toggle B** up | `v_lights_on` → *Headlights (Enable)* | Forces exterior/interior lights **on** (discrete). |
| `js2_button28` | MTQ **toggle B** down | `v_lights_off` → *Headlights Off* | Forces lights **off** (run dark - visual only, not EM/IR stealth). |

### Flight & movement - `spaceship_movement`

| Input | Control | Action → In-game label | What it does |
| --- | --- | --- | --- |
| `js1_y` | MHG pitch axis | `v_pitch` → *Pitch* | Nose up/down. Pull back = nose up (the non-inverted default; no `invert` is set now - add `<flight_move_pitch invert="1"/>` in the js1 `<options>` to flip). Usually the fastest rotation axis. |
| `js1_x` | MHG roll axis | `v_roll` → *Roll* | Bank left/right. Roll-onto-target + pitch is the core aiming technique. |
| `js1_rotz` | MHG twist | `v_yaw` → *Yaw* | Nose left/right via grip twist. Usually the slowest axis. |
| `js1_button25` | MHG top mini-stick ↑ | `v_strafe_up` → *Strafe up (abs.)* | Translate straight up (no rotation). Digital thrust. **Moved here from the MTQ "COM" hat on 2026-11-23** (swapped with the target-acquisition cluster - see §6 item 20). Needs the mini-stick in Button Mapping mode (§1.1). |
| `js1_button27` | MHG top mini-stick ↓ | `v_strafe_down` → *Strafe down (abs.)* | Translate straight down. |
| `js1_button26` | MHG top mini-stick → | `v_strafe_right` → *Strafe right (abs.)* | Translate right without yawing. |
| `js1_button28` | MHG top mini-stick ← | `v_strafe_left` → *Strafe left (abs.)* | Translate left without yawing. |
| `js2_roty` | MTQ throttle lever (RY) | `v_strafe_forward` → *Throttle - Increase* | Main forward throttle axis. Behavior (absolute vs relative) depends on the cruise/throttle-mode toggle below. |
| `js1_button29` | MHG top mini-stick - **press** | `v_strafe_back` → *Throttle - Decrease* | **Hold for full reverse.** The user's choice on the evening of 2026-11-26: the throttle lever rests in its idle detent and the press reverses when needed, so the lever never has to be pulled through the detent lock. A button on this action is all-or-nothing. It reversed fine in this form on the first 2026-11-26 load (§6 item 23); loaded again that evening and **confirmed in flight by the user** (§6 item 24). **Must stay the only rebind on this action:** the game keeps one joystick input per action (§2.5), so the MTQ's reverse axis `js2_rotz`, which made reverse proportional from 2026-11-20, is unbound (§6 item 24). Clicking the stick in while strafing (25–28) also fires it - push the directions without pressing. Needs the mini-stick in Button Mapping mode (§1.1). |
| `js2_button51` | MTQ Right Module switch - **momentary back** | `v_space_brake` → *Spacebrake* | Active full-stop on all axes (the "handbrake"). Hold to brake; springs back to rest (49) = `v_vtol_off`, an idempotent SET that's harmless to re-fire on every brake release. Rest (49) = VTOL off, forward-latch (50) = VTOL on (see VTOL rows below). |
| `js2_button65` | MTQ Left Module face button | `v_afterburner` → *Boost* | Boost - burst of extra acceleration from a depletable pool; also overrides proximity assist while held. |
| `js2_button9` | MTQ keypad **"FD"** (mid-bottom) | `v_toggle_jump_request` → *Jump Drive - Request Jump* | Engages **inter-system jump-point** travel (e.g. Stanton↔Pyro) - distinct from in-system quantum. Sits **directly below the quantum key** (7) → travel column. Moved off `js1_button56` (AB6 right wing 4, now free). |
| `js2_button5` | MTQ keypad **"NAV"** (mid-top) | `v_master_mode_cycle` → *Cycle Master Mode (Short Press)* | Toggles **SCM** (combat: weapons/shields) ↔ **NAV** (travel: quantum, higher speed, weapons offline). Physical "NAV" label matches. |
| `js2_button12` | MTQ upper encoder CW | `v_ifcs_speed_limiter_increment` → *Speed Limiter - Step Up (tap)* | Raises the SCM speed cap. |
| `js2_button11` | MTQ upper encoder CCW | `v_ifcs_speed_limiter_decrement` → *Speed Limiter - Step Down (tap)* | Lowers the speed cap - fly slow/precise; tighter turns. |
| `js2_button13` | MTQ upper encoder **center press** | `v_ifcs_speed_limiter_toggle` → *Speed Limiter - Enable / Disable* | Switches the speed cap on/off. Self-contained dial: turn 11/12 to set the cap, push 13 to engage/release it (instant full-speed sprint or back to capped). |
| `js2_button15` | MTQ lower encoder CW | `v_accel_range_increment` → *Acceleration Limiter - Step Up (tap)* | Raises the acceleration (G-force) cap - snappier, harsher Gs. |
| `js2_button14` | MTQ lower encoder CCW | `v_accel_range_decrement` → *Acceleration Limiter - Step Down (tap)* | Lowers the G-force cap - smoother, safer from blackout. |
| `js2_button16` | MTQ lower encoder **center press** | `v_ifcs_toggle_gforce_safety` → *G-Force Safety On/Off (Toggle / Hold)* | G-Safe - caps maneuvers to stop the pilot blacking out; off = full performance, blackout risk. Self-contained dial: turn 14/15 to set the accel/G cap, push 16 to toggle the safety that governs it. **Moved here from `js1_button51`.** |
| `js2_button57` | MTQ "COM" hat - **press, tap** | `v_ifcs_vector_decoupling_toggle` → *Enable / Disable decoupled mode* | Coupled ↔ decoupled. **Moved here 2026-11-26**: the user wanted it on the throttle, and its MHG stick-press spot became full reverse. Stock mode `tap`; a **hold** on the same press is *Pin Selected Target (Hold)* (see *Targeting*), so neither needs an attribute. It sat on keypad A4 for an hour first, but the user uses LAMP there far more. Earlier spots: MHG stick press `js1_button29` (2026-11-23 to 11-26), this same COM hat press before that, AB6 left wing 1 `js1_button49`. Kept **off** the MTQ 3-pos switch (49/50) - its rest re-fires on every brake (would force-recouple). |
| `js2_button8` | MTQ keypad **"ALT"** (right-mid) - **tap** | `v_atc_request` → *Request Landing* | Hails ATC for a pad/hangar; opens doors/forcefields when in range. **Swapped onto "ALT" from "AP"/10.** Moved off `js1_button53` (now free). Stock mode `tap`, so a quick press. |
| `js2_button8` | MTQ keypad **"ALT"** - **hold** (~0.25 s) | `v_atc_loading_area_request` → *Request Cargo Loading* | Hails for a cargo-loading slot (Golem OX hauling). **Re-added 2026-11** for the cargo fleet (it had been removed in June as never used). Carries `activationMode="delayed_press"` - the one explicit activation mode in the file - because its stock mode is also `tap`. |
| `js2_button29` | MTQ **toggle C** up (gear lever) | `v_retract_landing_system` → *Landing System (Retract)* | Gear **up**. Gear-shaped plastic lever - its position mirrors gear state. |
| `js2_button30` | MTQ **toggle C** down (gear lever) | `v_deploy_landing_system` → *Landing System (Deploy)* | Gear **down**. Lever down = gear down (aircraft convention). |
| `js2_button10` | MTQ keypad **"AP"** (right-bottom) - **hold** (~0.25 s) | `v_autoland` → *Autoland* | Autopilot lands on an ATC-assigned pad when gear is down and you're close. **Swapped onto "AP" from "ALT"/8.** Stock mode is `delayed_press`, so it needs a short **hold** - a quick tap is the docking action (see *Quantum travel, navigation & docking*). Gear toggle is now **only** on the gear lever (29/30); the stock `js1_button12` gear toggle is cleared (see *Cleared game defaults*). This one rebind also replaces the stock Autoland on `js1_button12` (the right hat UP), because an action has a single joystick binding. A `js1_ ` clear added beside it on 2026-11-26 wiped the binding (the last rebind wins) and was removed the same day (§2.5). |
| `js2_button50` | MTQ Right Module switch - **forward-latch** | `v_vtol_on` → *Enable VTOL* | Engages VTOL thrust mode (rotates/redirects thrusters for vertical lift) on VTOL-capable ships. Flick the switch forward; it stays latched. |
| `js2_button49` | MTQ Right Module switch - **rest/default** | `v_vtol_off` → *Disable VTOL* | Disengages VTOL. As a discrete idempotent SET it re-fires on every space-brake release (51 springs back through 49) with no ill effect, so the switch position always reflects true VTOL state. Moved here off the COM-hat press (`js2_button57`, now *Pin Selected Target*). |

### Quantum travel, navigation & docking - `spaceship_quantum`, `spaceship_hud`, `spaceship_docking`

| Input | Control | Action → In-game label | What it does |
| --- | --- | --- | --- |
| `js2_button7` | MTQ keypad **"SPD"** (mid-middle) - **hold** | `v_toggle_qdrive_engagement` → *Engage Quantum Drive (Hold)* | Spools & engages the quantum drive for **in-system** travel (needs NAV mode + an aligned marker). Stock mode is `delayed_press` - **hold** ~0.25 s. Press again to drop out. (Physical "SPD"/speed label - loose quantum match.) |
| `js2_button6` | MTQ keypad **"HDG"** (right-top) | `v_starmap` → *Map* | Opens the 3D star map (mobiGlas) to pick a quantum destination. (Physical "HDG"/heading label - loose nav match.) |
| `js2_button10` | MTQ keypad **"AP"** - **tap** | `v_toggle_docking_request` → *Docking (Initiate)* | Starts / cancels docking at a docking port, and undocks (the label changes with state). **Added 2026-11 for the Liberator**'s docking collar; the Wiki API also lists docking collars on the Perseus, Ironclad Assault and Corsair (fleet since 2026-11-23, §11). Shares the key with *Autoland* purely by stock activation modes (`tap` here, `delayed_press` there). Does nothing on ships that can't dock. Replaces the 4.8-era `v_invoke_docking` / `v_toggle_docking_mode`, which no longer exist. |

### Mode switching & LAMP - `seat_general`

| Input | Control | Action → In-game label | What it does |
| --- | --- | --- | --- |
| `js1_button4` | MHG upper thumb button | `v_toggle_missile_mode` → *Toggle Missile Operator Mode* | Switches the seat between **gun** and **missile** operator interfaces. |
| `js2_button17` | MTQ mode knob - detent 1 (full CCW) | `v_set_guns_mode` → *Set Guns Operator Mode* | Sets the seat to **Guns** operator mode. **Default park position** for the knob (combat-ready). |
| `js2_button18` | MTQ mode knob - detent 2 | `v_set_missile_mode` → *Set Missile Operator Mode* | Sets **Missile** operator mode. Overlaps the quick gun↔missile toggle on `js1_button4` (deliberate set vs fast flip). |
| `js2_button19` | MTQ mode knob - detent 3 (center) | `v_set_scan_mode` → *Set Scanning Operator Mode* | Selects the **Scanning** operator mode (radar/ping). |
| `js2_button20` | MTQ mode knob - detent 4 | `v_set_mining_mode` → *Set Mining Operator Mode* | Selects the **Mining** operator mode (mining-capable ships only). |
| `js2_button21` | MTQ mode knob - detent 5 (full CW) | `v_set_salvage_mode` → *Set Salvage Operator Mode* | Selects the **Salvage** operator mode (salvage-capable ships only). |
| `js2_button4` | MTQ keypad **"A4"** | `v_light_amplification_toggle` → *Light Amplification Toggle* | Toggles canopy night-vision (Light Amplification). LAMP-equipped ships only. Used often, so A4 is LAMP alone (a tap/hold share with decoupling was tried and dropped on 2026-11-26). Back on A4 after **ESP was unbound** - ESP and proximity assist are left **enabled-by-default** (in settings) and never toggled. The earlier LAMP-on/off pairing with the lights switch (27/28) was dropped - 27/28 are lights-only. |
| `js1_button3` | MHG lower side button (pinky) | `v_view_look_behind` → *Look behind* | **Hold** for a rear-view camera (check your six); keeps full stick/flight control (only the camera swings rear) and snaps back on release. **⚠ Lives in `seat_general`, not `spaceship_view`** - despite the `v_view_` prefix, CIG files look-behind under "seats & operator modes" (the catalog confirms; a first attempt in `spaceship_view` silently did nothing). **Confirmed working in cockpit view.** Replaced `v_view_freelook_mode` (a genuine `spaceship_view` action), which detached the view and felt like losing control when this pinky button was held unconsciously. *Cockpit-only:* SC has no 3rd-person look-behind action - in external view, orbit the camera with the MTQ mini-stick instead. |

> ⚠ **Note:** These five sit on the **rotary mode-selector knob** (detents 17–21), each directly **setting** one operator mode (`v_set_*_mode` are discrete activators, not "sub-modes" of a cycle). Operator modes are separate from Master Modes (SCM/NAV, cycled on `js2_button5`). Because the knob is a **maintained selector**, its physical position may not match the actual operator mode after seat entry or another mode change - turn off-and-back onto a detent to re-assert it. **Flight** and **Quantum** operator modes are intentionally *not* on the knob: Guns mode covers combat-flight, and quantum travel is handled by NAV master mode + QD-engage (`js2_button7`), so dedicated detents for them were redundant.

### Targeting - `spaceship_targeting`, `spaceship_targeting_advanced`

| Input | Control | Action → In-game label | What it does |
| --- | --- | --- | --- |
| `js1_button11` | MHG left hat center press | `v_target_lock_selected` → *Lock Selected Target* | Hard-**locks** the selected contact (enables lead pips + missile lock). |
| `js1_button5` | MHG lower-center face button | `v_target_under_reticle` → *Lock Target Under Reticle* | Locks whatever is under the crosshair - "target what I'm aiming at". |
| `js1_button8` | MHG left hat → | `v_target_cycle_hostile_fwd` → *Cycle Lock - Hostiles - Forward* | Cycles forward through hostiles only. |
| `js1_button10` | MHG left hat ← | `v_target_cycle_hostile_back` → *Cycle Lock - Hostiles - Back* | Cycles backward through hostiles only. |
| `js1_button12` | MHG right hat ↑ | `v_target_cycle_subitem_fwd` → *Cycle Lock - Sub-Target - Forward* | Cycles **sub-targets** (components) of the locked ship - focus-fire thrusters/weapons/power plant to disable. Moved to the stick (off MTQ keypad 9). **Mining:** module slot 1. **Salvage:** focus all heads (since 2026-11-26). |
| `js1_button14` | MHG right hat ↓ | `v_target_cycle_subitem_back` → *Cycle Lock - Sub-Target - Back* | Sub-target **back** - completes the ↑/↓ pair with button 12. **Mining:** module slot 3. **Salvage:** flip the beam axis. |
| `js1_button13` | MHG right hat → | `v_target_cycle_attacker_fwd` → *Cycle Lock - Attackers - Forward* | Locks whoever is **currently attacking you** - snap to the active threat in a furball. Moved to the stick (off MTQ keypad 10). **Mining:** module slot 2. **Salvage:** focus the right head. |
| `js1_button15` | MHG right hat ← | `v_target_cycle_attacker_back` → *Cycle Lock - Attackers - Back* | Attacker **back** - completes the →/← pair with button 13. **Mining:** nothing. **Salvage:** focus the left head. |
| `js2_button61` | MTQ "COM" hat ↑ | `v_target_cycle_all_fwd` → *Cycle Lock - All - Forward* | Cycles **all** contacts in scanner range (not just hostiles) forward. **Moved here from the MHG top mini-stick on 2026-11-23** (swapped with strafe - see §6 item 20). |
| `js2_button60` | MTQ "COM" hat ↓ | `v_target_cycle_all_back` → *Cycle Lock - All - Back* | Cycles all contacts back. |
| `js2_button58` | MTQ "COM" hat → | `v_target_cycle_hostile_reset` → *Cycle Lock - Hostiles - Reset to Closest* | **Snap-lock the closest hostile** - the best panic-target button in a furball. |
| `js2_button59` | MTQ "COM" hat ← | `v_target_cycle_pinned_fwd` → *Cycle Lock - Pinned - Forward* | Cycles through **pinned** targets. |
| `js2_button57` | MTQ "COM" hat - **press, hold** (~0.25 s) | `v_target_pin_selected_hold` → *Pin Selected Target (Hold)* | **Pins** the current target so you can cycle back to it (COM hat ←). Since 2026-11-26 the game's own hold version of pin (stock `delayed_press`): a **tap** on this press is the decoupled toggle. In `spaceship_targeting`, not `_advanced` (see the note below). |

> **The MHG right hat is a multi-mode bank (since 2026-11-26):** sub-target / attacker cycling in combat; in **Mining** / **Salvage** operator mode the same five inputs become those modes' banks (see *Mining* / *Salvage*). Safe because targeting maps go inactive in mining/salvage - the same gating the left hat relies on (hostile cycle in combat, salvage beams in salvage). The AB6 wings that used to do this job are now the always-live power panel, and their combat target-cycle set was deleted.

> **Targeting layout:** the **left hat** (lock + hostile cycle) and **right hat** (sub-target/attacker cycle ↑↓/→← + gimbal press) carry the core combat targeting; the MTQ **"COM" hat** adds an **acquisition cluster** - cycle-all, closest-hostile snap, and pin/cycle-pinned - complementing rather than duplicating the hats. (That cluster sat on the MHG top mini-stick until 2026-11-23, when it swapped places with strafe because it was rarely used.) Since 2026-11-26 the hat **press** is a **tap** for the decoupled toggle and a **hold** to pin. **✅ Action-map (resolved):** pin (`v_target_pin_selected`, now its hold twin `v_target_pin_selected_hold`) lives in `spaceship_targeting` (alongside `v_target_lock_selected`), **not** `spaceship_targeting_advanced` - the game's own exported `actionmaps.xml` *drops* pin from the *advanced* map (so pinning did nothing there), confirming it belongs with the basic lock action (see §10).

### Radar & scanning - `spaceship_radar`, `spaceship_scanning`

| Input | Control | Action → In-game label | What it does |
| --- | --- | --- | --- |
| `js1_button20` | MHG lower hat ← | `v_invoke_ping` → *Activate Ping (Hold & Release)* | Active radar ping - reveals/marks contacts by their cross-section (also gives away your position). |
| `js1_button18` | MHG lower hat → | `v_scanning_trigger_scan` → *Activate Scanning* | **Hold** to scan the target under the reticle for detailed info (requires Scan operator mode). |
| `js1_button17` | MHG lower hat ↑ | `v_inc_scan_focus_level` → *Increase Scanning Angle* | Narrows the scan cone - stronger/longer-range read on one target. **Salvage:** vehicle tractor distance + (trial, see *Salvage*). |
| `js1_button19` | MHG lower hat ↓ | `v_dec_scan_focus_level` → *Decrease Scanning Angle* | Widens the scan cone - sweep a broader area. **Salvage:** vehicle tractor distance − (trial). |

### Weapons - `spaceship_weapons`

| Input | Control | Action → In-game label | What it does |
| --- | --- | --- | --- |
| `js1_button1` | MHG main trigger | `v_weapon_preset_fire_guns0` → *Weapon Presets - Fire Guns Group 1* | Fires **weapon group 1**. |
| `js1_button6` | MHG trigger stage 2 | `v_weapon_preset_fire_guns1` → *Weapon Presets - Fire Guns Group 2* | Fires **weapon group 2**. |
| `js1_button22` | MHG upper rocker ↑ | `v_weapon_preset_next` → *Weapon Presets - Next* | Cycles weapon grouping/preset forward. |
| `js1_button23` | MHG upper rocker ↓ | `v_weapon_preset_prev` → *Weapon Presets - Previous* | Cycles weapon grouping/preset backward. |
| `js1_button24` | MHG upper rocker center | `v_weapon_aim_type_cycle` → *Aim Mode - Cycle* | Cycles gimbal aim mode (fixed-style / gimbal assist / manual gimbal). |
| `js1_button16` | MHG right hat center press | `v_weapon_gimbals_state_toggle` → *Gimbal State - Toggle Locked / Unlocked* | Quick on/off of gimbal lock (locked = tighter convergence). **Salvage:** reset the salvage gimbal (since 2026-11-26). |

> ⚠ **Note:** `fire_guns0` / `fire_guns1` are **weapon group 1 / group 2**, *not* "trigger stage 1 / stage 2" (the XML comments previously implied the latter and have been corrected). The `0`/`1` suffix is the weapon group, independent of which physical trigger stage you put it on. (Here group 2 is conveniently on the trigger's 2nd stage, `js1_button6`.) Until you actually split your guns into two groups in the MFD, group 2 may have nothing to fire.

> **The trigger also fires the *selected* weapon preset (a stock default left in place on purpose).** The game's stock layout binds `v_weapon_preset_attack` → *Weapon Preset - Fire* to joystick button 1, and this file doesn't override it, so `js1_button1` fires **the currently selected preset *and* guns group 1**. With the default selection (group 1) the two are the same thing. It is what gives the rocker's *Weapon Presets - Next / Previous* (22/23) something to act on: step the selection to group 2 and a half-pull fires everything; on a ship with EMP / quantum-jammer presets it lets the trigger fire those. For strict "stage 1 = group 1 only, stage 2 = group 2 only", clear it with `<action name="v_weapon_preset_attack"><rebind input="js1_ "/></action>` in `spaceship_weapons` - but then 22/23 do nothing in gun mode. **M80 setup:** in the weapons MFD put the 2x S5 in group 1 and the 2x S4 in group 2 (or split by weapon type) so the two trigger stages mean something.

### Missiles - `spaceship_missiles`

| Input | Control | Action → In-game label | What it does |
| --- | --- | --- | --- |
| `js1_button2` | MHG top-left face button | `v_weapon_toggle_launch_missile` → *Launch Missiles (Tap)* | Arms/launches the selected missile. **Hold** to build a stronger lock before release. |
| `js1_button22` | MHG upper rocker ↑ | `v_weapon_cycle_missile_fwd` → *Cycle Next Missile Type* | Next missile type (in missile mode). Shares the button with *Weapon Preset Next*. |
| `js1_button23` | MHG upper rocker ↓ | `v_weapon_cycle_missile_back` → *Cycle Previous Missile Type* | Previous missile type. Shares the button with *Weapon Preset Prev*. |

> The rocker (22/23) does double duty: **weapon presets** in gun mode, **missile types** in missile mode - the active operator mode decides which.

### Countermeasures & shield faces - `spaceship_defensive`

| Input | Control | Action → In-game label | What it does |
| --- | --- | --- | --- |
| `js1_button7` | MHG left hat ↑ | `v_weapon_countermeasure_decoy_launch` → *Decoy - Launch Burst (tap), Set and Launch Burst (hold)* | Flares - lure **seeker-guided** (IR/cross-section) missiles. Burst them as a missile closes. |
| `js1_button9` | MHG left hat ↓ | `v_weapon_countermeasure_noise_launch` → *Noise - Deploy (Tap)* | Chaff - a sensor-interference cloud that breaks **radar/scan locks**. |
| `js2_button56` | MTQ "WPN" hat ↑ | `v_shield_raise_level_forward` → *Shield raise level front* | Raise the **front** shield face. **Trial since 2026-11-26**, see the note below. |
| `js2_button55` | MTQ "WPN" hat ↓ | `v_shield_raise_level_back` → *Shield raise level back* | Raise the **rear** face. |
| `js2_button54` | MTQ "WPN" hat ← | `v_shield_raise_level_left` → *Shield raise level left* | Raise the **left** face. |
| `js2_button53` | MTQ "WPN" hat → | `v_shield_raise_level_right` → *Shield raise level right* | Raise the **right** face. |
| `js2_button52` | MTQ "WPN" hat - **press** | `v_shield_reset_level` → *Shield reset levels* | Reset the faces to even. |

> **Shield faces on the "WPN" hat (since 2026-11-26, trial).** `v_shield_raise_level_*` only does anything on ships with **Size 3 *Quadrant* shields** - in this fleet the Liberator, Perseus, Ironclad Assault and Corsair **[ref]**. On bubble-shield ships (M80, Hyūn, Golem, Salvation, Pisces) the hat is a no-op. The hat was freed when the power pips moved to the AB6 wings. History: shield faceting sat here once before and was removed because every fighter flown at the time had bubble shields, so it looked broken (§6 item 14). All stock mode `press`, no attributes. **Not yet tried in-ship** in 4.10: test it in the Corsair first, and check on the crewed ships whether the pilot seat owns the faces. Top / bottom faces (`v_shield_raise_level_up` / `_down`) are not bound - a quadrant shield has four faces.

### View & camera - `spaceship_view`

| Input | Control | Action → In-game label | What it does |
| --- | --- | --- | --- |
| `js2_button62` | MTQ Left Module mini-stick - **press** | `v_view_cycle_fwd` → *Cycle camera view* | Cycle cockpit ↔ external/chase views. **⚠ Cleanup:** the `view_restore_defaults` that used to be shotgunned on this press was **removed** - the game *drops* it from `spaceship_view` (it did nothing), and the cockpit recenter-on-cycle is `v_view_cycle_fwd`'s own behavior. (It's only accepted in `view_director_mode` = the cinematic/Director camera, unused in this combat profile.) Moved off the MHG coolie press (`js1_button29`). |
| `js2_x` | MTQ Left Module mini-stick - **X axis** | `v_view_yaw` → *Look left / right* | Analog camera yaw. Stick centers at 32767 = neutral (no off-center calibration needed). |
| `js2_y` | MTQ Left Module mini-stick - **Y axis** | `v_view_pitch` → *Look up / down* | Analog camera pitch. Add `invert` in `<options>` if it feels reversed. Both moved off the MHG top coolie hat (25/26/27/28, now strafe). |
| `js1_button21` | MHG lower hat center press | `v_ads_toggle` → *Precision Targeting - Toggle On / Off* | Cockpit zoom/"ADS" view (in-ship binoculars-style zoom) - the reliable in-cockpit zoom. |
| `js2_button63` | MTQ throttle dial - fwd/CW click | `v_view_dynamic_zoom_rel_in` → *Dynamic Zoom In (rel.)* | Zoom **in** - dynamic FOV zoom, works in the **cockpit**. (Dropped the dead 3rd-person `v_view_zoom_in` that used to fire alongside it.) No 3rd-person FoV zoom here - that needs a *held* modifier (kb F4) a dial click can't do; use the keyboard or a Pithouse macro. |
| `js2_button64` | MTQ throttle dial - back/CCW click | `v_view_dynamic_zoom_rel_out` → *Dynamic Zoom Out (rel.)* | Zoom **out** - same; dropped the dead 3rd-person `v_view_zoom_out`. For 3rd-person FoV zoom, use the keyboard (F4 + NumPad±) or a Pithouse macro. |

### Mining - `spaceship_mining`

These reuse MHG controls; active only in **Mining** operator mode.

| Input | Control | Action → In-game label | What it does |
| --- | --- | --- | --- |
| `js1_button1` | MHG trigger | `v_toggle_mining_laser_fire` → *Fire Mining Laser (Toggle)* | Fire/extract with the mining laser (reuses the gun trigger). |
| `js1_button22` | MHG rocker ↑ | `v_increase_mining_throttle` → *Increase Mining Laser Power* | Raise laser power toward the fracture window. |
| `js1_button23` | MHG rocker ↓ | `v_decrease_mining_throttle` → *Decrease Mining Laser Power* | Lower laser power. |
| `js2_slider2` *(FLAPS)* | MTQ FLAPS slider - **axis** ("Slider") | `v_mining_throttle` → *Increase / Decrease Mining Laser Power* | **Absolute** laser power on the maintained FLAPS lever - hold it in the green fracture window. Supersedes the ± rocker above. **Confirmed in Golem:** rest (up) = ~20% charge (the laser's minimum floor), FULL (down) = 100% - direction correct, **no invert needed**. |
| `js1_button24` | MHG upper rocker **center** | `v_toggle_mining_laser_type` → *Switch Mining Laser (Toggle)* | Switches the laser between **fracture** and **extraction** (the in-game hint reads *Laser Type (Fracture)* / *Laser Type (Extract)*). Puts every mining-laser control on the one rocker: ↑/↓ = power, push = mode. **Moved off `js1_button4` on 2026-11-21:** that button is also *Toggle Missile Operator Mode* in `seat_general`, which stays live in Mining mode, and the user could not get the laser mode to switch there (§6 item 18). |
| `js1_button12` | MHG right hat ↑ | `v_mining_use_consumable1` → *Activate Mining Module (Slot 1)* | Activate fitted mining module, slot 1 (e.g. Surge/OptiMax). Since 2026-11-26 (was AB6 left wing 1). |
| `js1_button13` | MHG right hat → | `v_mining_use_consumable2` → *Activate Mining Module (Slot 2)* | Module slot 2. |
| `js1_button14` | MHG right hat ↓ | `v_mining_use_consumable3` → *Activate Mining Module (Slot 3)* | Module slot 3. |
| `js2_button1` | MTQ keypad **A1** - **hold** (~0.25 s) | `v_jettison_volatile_cargo` → *Jettison Cargo* | Emergency dump of unstable cargo (e.g. Quantanium about to detonate). **Alone on A1** in every actionmap since 2026-11-26 (it used to share an AB6 wing with the salvage axis flip, so a wrong-mode press on the Hyūn could dump ore). Stock mode `press`; `activationMode="delayed_press"` is the user's choice, so a brush of the key can't dump the load. Never tried in-ship. |

> **Golem note:** reference data (the Star Citizen Wiki API extract for 4.10.3 and CIG's Golem Q&A) gives the Golem's bespoke laser **2 module slots**, so *Slot 3* (right hat ↓, `js1_button14`) has nothing to fire on it - harmless, and still correct for 3-slot heads on other mining ships. Not checked in-ship.
>
> **Mining bank on the MHG right hat (since 2026-11-26):** ↑ / → / ↓ = module slots 1 / 2 / 3, so the throttle hand can stay on the FLAPS lever holding laser power. The same hat is sub-target / attacker cycling in combat and head focus in salvage. A stray right-hat flick in Mining mode spends a charge of an active module. Jettison is a hold on MTQ A1. The MHG rocker (22/23) doubles as mining-power ± here, and its center press (24) switches fracture ↔ extraction. *Toggle Laser Beam (High / low)* (`v_mining_use_permanent_modifier`) is unbound and unknown; right hat ← is free in Mining mode if it proves useful. **Removed earlier:** the old `v_toggle_mining_mode` placeholder (was on `js1_button18`) - it was in the wrong action map (`seat_general`, not `spaceship_mining`), shared the scan trigger, and duplicated the mode knob's `v_set_mining_mode`.

### Salvage - `spaceship_salvage`

These reuse MHG controls; active only in **Salvage** operator mode.

| Input | Control | Action → In-game label | What it does |
| --- | --- | --- | --- |
| `js1_button1` | MHG trigger | `v_salvage_toggle_fire_focused` → *Toggle Fire Focused* | Toggle the focused salvage beam(s) on/off. |
| `js1_button6` | MHG trigger stage 2 | `v_salvage_toggle_gimbal_mode` → *Salvage Mode Gimbal (Toggle)* | Toggle salvage beam gimbal mode. |
| `js1_button10` | MHG left hat ← | `v_salvage_toggle_fire_disintegrate` → *Toggle Fire Disintegrate* | Fire the disintegrate beam (break down material). |
| `js1_button8` | MHG left hat → | `v_salvage_toggle_fire_fracture` → *Toggle Fire Fracture* | Fire the fracture beam (crack structures into salvageable pieces). |
| `js1_button11` | MHG left hat center press | `v_salvage_cycle_modifiers_focused` → *Cycle Focused Salvage Modifiers* | Cycle the mode/modifier of focused beam(s) (e.g. scraper vs tractor). |
| `js2_slider1` *(SPEEDBRAKE)* | MTQ SPEEDBRAKE slider - **axis** ("Dial") | `v_salvage_beam_spacing_abs` → *Absolute Beam Spacing* | **Absolute** beam gap on the maintained SPEEDBRAKE lever - set to match the panel and leave it. **Confirmed in Salvation:** sweeping the lever opens/closes the gap across full travel (auto-mapped, no range to set). |
| `js1_button22` | MHG rocker ↑ | `v_salvage_increase_beam_spacing` → *Increase Beam Spacing* | Step the gap **wider** (fine-trim on top of the SPEEDBRAKE axis). |
| `js1_button23` | MHG rocker ↓ | `v_salvage_decrease_beam_spacing` → *Decrease Beam Spacing* | Step the gap **narrower**. |
| `js1_button24` | MHG upper rocker **center** | `v_salvage_cycle_modifiers_structural` → *Cycle Structural Salvage Modes* | Cycles the **structural salvage field** between its modes - the game's HUD names them *Fracture Field*, *Disintegration Field* and *Suction*. The same press is the mining laser's fracture ↔ extraction switch, so the rocker center is the "tool mode" button in both modes. **Moved off AB6 right wing 4 (`js1_button56`) on 2026-11-22** for the Gatac Hyun (§6 item 19). Hull **scraping** is not one of these modes: it is the salvage heads, fired with the trigger. |
| `js1_button12` | MHG right hat ↑ | `v_salvage_focus_all_heads` → *Focus all salvage heads* | Focus **all** heads. Since 2026-11-26 (the bank was on the AB6 wings). |
| `js1_button15` | MHG right hat ← | `v_salvage_focus_left` → *Focus left salvage head* | Focus **left** head only. |
| `js1_button13` | MHG right hat → | `v_salvage_focus_right` → *Focus right salvage head* | Focus **right** head only. |
| `js1_button14` | MHG right hat ↓ | `v_salvage_toggle_beam_spacing_axis` → *Salvage Beam Axis (Toggle)* | Toggle beams parallel **horizontal ↔ vertical**. |
| `js1_button16` | MHG right hat - **press** | `v_salvage_reset_gimbal` → *Salvage Mode Gimbal Reset* | Reset the salvage gimbal to center. |
| `js2_button2` | MTQ keypad **A2** | `v_salvage_toggle_fire_left` → *Toggle Fire Left* | Toggle-fire the **left** beam (regardless of focus). Stock mode `smart_toggle`. Alone on A2. |
| `js2_button3` | MTQ keypad **A3** | `v_salvage_toggle_fire_right` → *Toggle Fire Right* | Toggle-fire the **right** beam. Alone on A3. |
| `js1_button17` | MHG lower hat ↑ | `tractor_beam_vehicle_increase_distance` → *Tractor Beam Vehicle- Increase Distance* | **Trial (2026-11-26):** push an object held by the vehicle tractor beam further out - for the Golem OX, whose tractor turret hangs off a *salvage* controller in the game files. Scan mode keeps scan angle + on this input. Unverified in-ship (§6 item 15). |
| `js1_button19` | MHG lower hat ↓ | `tractor_beam_vehicle_decrease_distance` → *Tractor Beam Vehicle - Decrease Distance* | **Trial:** pull the held object closer. Scan mode keeps scan angle −. |

> **Salvage bank on the MHG right hat (since 2026-11-26):** ↑ focus all · ← / → focus left / right · ↓ flip the beam axis · press = gimbal reset, with fire left / right on MTQ A2 / A3. Head focus now sits on the same hand as the left hat's fracture / disintegrate fire and modifier cycle. The bank used to be on the AB6 wings, which are now the always-live power panel. The MHG rocker is the salvage tool cluster: ↑/↓ (22/23) step the beam spacing, complementing the SPEEDBRAKE absolute axis, and the center press (24) cycles the structural field's mode. None of the bank's functions has been confirmed in-ship in its new place (nor was it on the wings).

### Cleared game defaults - `spaceship_movement`, `player_choice`, `vehicle_general`, `vehicle_driver`

These ten entries bind **nothing**. Each is `<rebind input="js1_ "/>`, which removes a stock joystick binding that would otherwise stay live on `js1` underneath this profile (the mechanism is in §2.5). They were identified from the 4.10 `defaultProfile.xml` with `tools/gamedata.py check` on 2026-11-20; the game accepted all ten on the first 4.10.3 load (each is listed as `js1_ ` in its export, §10.3). Their in-flight effect has not been checked one by one. A clear only belongs on an action the profile does **not** bind: an eleventh, placed beside the *Autoland* binding on 2026-11-26, replaced that binding and was removed (§2.5).

| Cleared action → In-game label | Actionmap | Stock `js1` input | What that input is on this rig | Why it is cleared |
| --- | --- | --- | --- | --- |
| `v_toggle_landing_system` → *Landing System (Toggle)* | `spaceship_movement` | `js1_button12` (tap) | MHG right hat ↑ = sub-target forward | Every sub-target tap also toggled the landing gear and left the gear lever (29/30) out of sync. |
| `pc_interaction_mode` → *Interaction Mode* | `player_choice` | `js1_button6` (hold) | MHG trigger stage 2 = fire group 2 / salvage gimbal | A full trigger pull also held interaction mode. Interaction is done on the Xbox controller / keyboard. |
| `v_horn` → *Horn* | `vehicle_general` | `js1_button8` | MHG left hat → | Ground vehicles are driven on the Xbox controller. |
| `v_view_yaw` → *Look left / right* | `vehicle_general` | `js1_x` | stick X (roll) | Same - stops the stick swinging the camera in a ground vehicle. |
| `v_view_pitch` → *Look up / down* | `vehicle_general` | `js1_y` | stick Y (pitch) | Same. |
| `v_move` → *Drive Forward / Backward* | `vehicle_driver` | `js1_slider1` | an AB6 base lever axis (maintained) | Whatever that axis reports is a constant drive input. With the levers in Button Mapping mode (as on 2026-11-20, §1.1) the axis is idle, so this was a latent risk rather than a live one - it would bite the moment a lever is switched to an axis mode. |
| `v_yaw` → *Yaw Left / Right (Axis / HOTAS)* | `vehicle_driver` | `js1_x` | stick X | Stops the stick steering the rover. The ship's `v_yaw` in `spaceship_movement` is a separate entry and untouched. |
| `v_pitch` → *Pitch Up / Down (Axis / HOTAS)* | `vehicle_driver` | `js1_y` | stick Y | Same. The ship's `v_pitch` is untouched. |
| `v_brake` → *Brake* | `vehicle_driver` | `js1_button7` (hold) | MHG left hat ↑ | Same. |
| `v_boost` → *Boost* | `vehicle_driver` | `js1_button8` | MHG left hat → | Same. |

**Stock joystick defaults deliberately left in place** (still reported as `GHOST` by the check - that is expected):

| Stock default | `js1` input | Why it stays |
| --- | --- | --- |
| `turret_movement` / `turret_pitch`, `turret_yaw` | `js1_y`, `js1_x` | Wanted - the stick aims a turret when you sit in one. |
| `spaceship_weapons` / `v_weapon_preset_attack` | `js1_button1` | Lets the trigger fire the selected weapon preset - see the Weapons note. |
| `tractor_beam` / `tractor_beam_increase_distance`, `_decrease_distance` | `js1_button3`, `js1_button4` | Only acts while a tractor beam is held; the pinky and thumb buttons do nothing useful there anyway. |
| `player_choice` / `pc_select`, `pc_focus` | `js1_button1`, `js1_button7` | Only act once interaction mode is already open, which the stick can no longer do. |
| `default`, `spectator`, `mining` (UI navigation, respawn/ready, spectator camera, on-foot mining tool) | `js1_button1-7`, `js1_x/y`, `js1_hat1_*` | Menu / spectator / on-foot contexts - not live while flying. |

---

## 5. Operator-mode reuse (mining & salvage)

The MHG trigger and hats are deliberately **shared** across flight, mining, and salvage. Which action fires depends on the seat's **operator mode** (set via the `v_set_*_mode` detents on the MTQ rotary mode-selector knob, or `v_toggle_missile_mode`):

| Physical control | Flight/SCM | Mining mode | Salvage mode |
| --- | --- | --- | --- |
| `js1_button1` (trigger) | Fire Guns Group 1 | Fire Mining Laser | Fire Focused Salvage Beam |
| `js1_button6` (trigger 2) | Fire Guns Group 2 | - | Toggle Salvage Gimbal |
| `js1_button22/23` (rocker) | Weapon/missile cycle | Mining power ± | Beam spacing ± |
| `js1_button24` (rocker center) | Aim-type cycle | Fracture ↔ extraction | Structural field mode (fracture / disintegration / suction) |
| `js1_button8/10` (left hat ←/→) | Cycle hostiles | - | Fire Fracture / Disintegrate |
| `js1_button11` (left hat press) | Lock target | - | Cycle salvage modifiers |
| `js1_button12–15` (right hat directions) | Sub-target / attacker cycle | Modules 1–3 (↑ → ↓) | Focus all / right / left, beam axis |
| `js1_button16` (right hat press) | Gimbal lock toggle | - | Gimbal reset |
| `js1_button17/19` (lower hat ↑/↓) | Scan angle ± (Scan mode) | - | Vehicle tractor distance ± (trial) |
| `js2_button1–3` (MTQ A1–A3) | - | Jettison (A1, hold) | Fire left / right (A2 / A3) |

This is normal and intended - only one of these action maps is "live" at a time. **The reuse is safe only because these maps are operator-gated** (weapons/missiles/mining/salvage/targeting are never simultaneously live). Always-active maps (power, defensive, movement, view, **and `seat_general`**) are deliberately **not** reused this way - that's why the AB6-wing power panel, the WPN-hat shield faces and the left-hat countermeasures are single-purpose. `seat_general` (missile-mode toggle, look-behind, the mode knob) is live in *every* operator mode; the one past breach of this rule was the mining-laser switch sharing `js1_button4` with the missile-mode toggle (§6 item 18).

---

## 6. Issues & recommendations found in `MOZA.xml`

1. **✅ Fixed - `v_toggle_mining_mode_fracture` (`js1_button18`) was invalid** (not a real action). Swapped to `v_toggle_mining_mode` as a placeholder; proper mining wiring is deferred. *(See Mining table + note.)*
2. **✅ Fixed - `fire_guns0` / `fire_guns1` comments corrected** - they're weapon **groups 1/2**, not trigger stages. The bindings themselves were always fine. *(See Weapons note.)*
3. **✅ Fixed - `v_toggle_jump_request` comment clarified** as inter-system jump-point travel (distinct from in-system quantum, `v_toggle_qdrive_engagement`). Binding unchanged.
4. **Doubled door bindings** (`js2_button25` = unlock+open, `js2_button26` = lock+close) fire two actions per press by design. Intended as "open up / seal up" buttons - just be aware both fire.
5. **✅ Combat + multi-mode pass (js1 + WPN hat) - superseded 2026-11-26 by item 22** (power moved to the AB6 wings, the banks to the MHG right hat, shield faces to the WPN hat): the **power-pip triangle moved to the MTQ "WPN" hat** (`js2_button52–56`), **replacing the shield-faceting** that only worked on Size-3-shield ships (see *Countermeasures*) - pips work on every ship. The freed **AB6 wings (`js1_button49–56`) are now a multi-mode bank**: secondary target-acquisition in combat, mining modules + jettison in Mining, focus/fire/gimbal/axis/structural in Salvage. The **MHG rocker (22/23)** also gains stepped salvage beam-spacing. **MHG grip fully bound (1–29).** Earlier work: coolie hat (25–29) = target acquisition, right hat ↓/← (14/15) = sub-target/attacker back. Removed the dead `v_toggle_mining_mode` placeholder. *(In-game verifies: `v_engineering_assignment_*` and `v_target_pin_selected` action maps - see §4 notes.)*
6. **✅ Fixed - AB6 levers are mixed-mode, not button-only:** an earlier doc claimed the "Slider"/"Dial" levers (57–62) were 3-position button-only "not an analog axis." They are **mixed-mode** (3 detent buttons **plus** an analog axis, `js1_slider1`/`js1_slider2`). Corrected in §1 and §3.2. *(2026-11: which of the two they emit turned out to be a per-lever MOZA Cockpit setting - both were found on Button Mapping, i.e. buttons only; see §1.1.)*
7. **Only remaining free js1 hardware = the two AB6 levers (57–62), deliberately unbound:** maintained set-and-hold levers suit neither momentary combat actions nor the wing power panel (a held detent would fight the pip taps). Reserved for a future **modal/analog** use (e.g. a multi-role analog value) - confirm which axis is `js1_slider1` vs `js1_slider2` in `joy.cpl` first. **MTQ (js2)** remains essentially full (only the rocker center 22, slider detents 31/36-40/43, and the throttle axes `js2_rotx`, `js2_rotz` and `js2_z` are intentional gaps).
8. **Device-instance fragility:** see the warning in §1 - keep USB enumeration order stable so `js1`/`js2` don't swap.
9. **✅ Actionmap-correctness review (vs the game's own export):** validated every binding against `…\Profiles\default\actionmaps.xml` (the game's normalized export) using [`tools/validate_actionmaps.py`](tools/validate_actionmaps.py) - the game **drops** any action placed in the wrong map, so its export is an authoritative oracle (and the catalog's *keyword category* is **not** the actionmap). Two issues fixed: **`v_target_pin_selected`** moved `spaceship_targeting_advanced`→**`spaceship_targeting`** (the game dropped pin from the *advanced* map, so pinning a target did nothing), and **`view_restore_defaults` removed** (it sat in `spaceship_view`, where the game drops it - it was dead; the cockpit recenter-on-cycle is `v_view_cycle_fwd`'s own behavior). Every other bound action sits in the actionmap the game files it under. Authoritative local sources + the re-check workflow are in **§10**. *(A separate experiment - driving advanced-camera FoV from the throttle dial - was abandoned: `view_enable_camview_mode` engages the sticky cinematic/Director camera, the wrong tool for in-flight zoom; the dial's existing `v_view_dynamic_zoom_rel_*` cockpit zoom is the ceiling.)*

10. **✅ Alpha 4.10.3 review (2026-11-20, build `4.10.201.48085`) - validated against the game's own files.** With starbinder gone (domain expired), every binding was checked against `defaultProfile.xml` extracted from `Data.p4k` by the new [`tools/gamedata.py`](tools/gamedata.py). Result: **all 119 existing bindings are valid in this build and sit in the correct actionmap** - no action was renamed or moved under the profile. (Renames that did *not* affect it: `v_ifcs_toggle_gravity_compensation` → `v_ifcs_gravity_compensation_toggle`; `v_invoke_docking` / `v_toggle_docking_mode` → `v_toggle_docking_request`.)
11. **✅ Fixed - stock joystick defaults were still live under the profile (§2.5).** The check exposed something the export-based validator structurally can't: game defaults on `js1` that the profile never overrode. Two overlapped single-purpose buttons and were cleared - *Landing System (Toggle)* on the sub-target hat (`js1_button12`) and *Interaction Mode* on trigger stage 2 (`js1_button6`). Eight more (the ground-vehicle driving set) were cleared so the rig is inert in ground vehicles such as the Ursa, which are driven on the Xbox controller. Full list, and the defaults deliberately kept, in §4 *Cleared game defaults*. **Not yet flight-tested.**
12. **✅ Fleet tuning (§11):** added *Docking (Initiate)* on a tap of "AP" for the Liberator's docking collar, and brought back *Request Cargo Loading* as a hold on "ALT" for C2 / Golem OX hauling. No existing binding moved.
13. **✅ Fixed - `MOZA_BINDINGS.html` had keypad 8/10 backwards** (it missed the June ATC↔Autoland swap). Corrected with the new tap/hold functions.
14. **Open - shield faces on the S3-shield ships.** The Liberator carries Size 3 shields (confirmed in the game files). Since the 2026-11-23 rebuy, the Wiki API also lists S3 *Quadrant* shields on the **Perseus** (2x), **Ironclad Assault** (4x) and **Corsair** (1x) **[ref]**. So four ships in the fleet, not one, are where `v_shield_raise_level_*` could do anything (the C2, which also had them, left on 2026-11-22). They stay unbound: there is no free hat in an always-active map, and the power-pip triangle already covers shield strength. Revisit if face management turns out to matter on any of the four. Check first whether the pilot seat controls the faces on the crewed ships. **Update 2026-11-26:** bound on the freed "WPN" hat as a trial (item 22); still untested in-ship.
15. **Open - Golem OX tractor beam.** The OX has a deployable tractor turret and, in the game files, a *salvage* controller, so its tractor may run through Salvage operator mode (trigger = *Toggle Fire Focused*). `tractor_beam_vehicle_increase/decrease_distance` (in `spaceship_salvage`) are unbound on the rig - mouse wheel / gamepad shoulders only. Check in-ship which mode drives it before binding; the MHG right hat ↑/↓ (12/14) is the natural spot if targeting is inactive in that mode. **Update 2026-11-26:** trial binding on the MHG lower hat ↑/↓ in Salvage mode (item 22); test it in the OX.

16. **✅ Reverse throttle is now proportional (2026-11-20; superseded on the evening of 2026-11-26, when reverse went to the stick press alone and the axis was unbound - item 24).** Reverse used to be the rear-detent **button** `js2_button34`, so crossing the idle detent meant instant full reverse. MOZA Cockpit 1.5.48's *Throttle Detent Setup* has a **Reverse Thrust** mode that turns the travel behind the idle detent into its own axis (Z / RZ); `v_strafe_back` now sits on `js2_rotz`. The device steps and the calibration trap ("rev idle" goes just behind the detent, **not** at the rear stop) are in §1.1. Axis behavior was confirmed in MOZA Cockpit (0 at the detent, 65535 at the stop); a first flight the same day (Avenger Titan) had it working with no invert - the fallback is in the §4 row. This supersedes the old "reverse is binary by necessity" note: that was true of the software of the time, which had no way to give the rear travel its own axis.

17. **⚠ Game option with a backwards label - "Defaults → Flight → Decoupled On" (found 2026-11-20, build `4.10.201.48085`).** Tested by the user across three launches: with the menu on **Yes** the ship spawned **coupled**; on **No** it spawned **decoupled**. The stored value is honest - `IFCS_Setting_CoupledEnabled` in `…\user\client\0\Profiles\default\attributes.xml`, where `1` = coupled (the game's default, so the entry is simply absent) and `0` = decoupled. The user wants to start **coupled**: menu on *Yes*, no `…CoupledEnabled = 0` line in the file. Two things learned about that file: the game drops an entry once it equals the default, so a missing setting is not readable from it; and hand-edits made with the game closed are picked up at the next launch. Re-check the label's sense after a patch before trusting either reading.

18. **✅ Fixed - the mining fracture/extract switch shared a button with an always-live action (2026-11-21).** `v_toggle_mining_laser_type` (*Switch Mining Laser (Toggle)*, the fracture ↔ extraction switch - the game's own hint strings are *Laser Type (Fracture / Extract)*) sat on `js1_button4` together with `v_toggle_missile_mode`. That second action is in `seat_general`, which is not operator-gated, so in Mining mode one press fired both. The user reported they could not get the laser mode to switch in the Golem. The switch now lives on the MHG upper rocker **center** (`js1_button24`), whose only other binding is *Aim Mode - Cycle* in the operator-gated `spaceship_weapons`. `js1_button4` is now missile-mode toggle only. The doc had also mis-described the action as "switch laser heads/modules". `gamedata.py check` passes (131 OK, no new ghost on button 24); **not yet tried in-ship**.

19. **✅ Salvage "mode" press moved to the rocker center for the Gatac Hyun (2026-11-22).** The user asked for the button that switches the mining laser between fracture and extraction to also switch salvage between scraping and fracturing, for a trial of the **Gatac Hyūn** (mining + salvage hybrid, *Flight ready* in 4.10.3 per the wiki). What was found:
    - **[game]** The game has no single "scraping ↔ fracturing" switch. Hull scraping is the salvage **heads** (trigger = *Toggle Fire Focused*). Fracturing and disintegrating belong to a separate **structural salvage** tool whose HUD strings call its modes *Fracture Field*, *Disintegration Field* and *Suction*; *Cycle Structural Salvage Modes* cycles them. Its fire actions were already bound: *Toggle Fire Fracture* = left hat → (`js1_button8`), *Toggle Fire Disintegrate* = left hat ← (`js1_button10`).
    - **[ref]** The wiki's port list gives the Hyun two salvage arms with S2 Baler heads, each carrying a hardware-locked Abrade scraper module, plus an `S1SalvageDisintegrationArea`, the same layout as the Salvation. Guides describe right mouse (*Cycle Tool Mode*, `v_salvage_cycle_modifiers_focused`) as swapping scraper attachments, not switching to fracture. With one locked module per head it likely has nothing to cycle on the Hyun. It stays on left-hat press (`js1_button11`).
    - **Change:** `v_salvage_cycle_modifiers_structural` moved from AB6 right wing 4 (`js1_button56`) to the rocker center (`js1_button24`), the mining fracture/extract button. Wing 4 is now free in Salvage mode. `gamedata.py check` passes (131 OK, no ghost on 24 or 56). The Hyun's vehicle definition in `Data.p4k` could not be read (not plain zstd, the same for the Salvation's in this build), so its exact structural tool is unconfirmed. **Not yet tried in-ship.** If the rocker center does nothing on the Hyun, check whether the structural tool must be focused first (*Focus Fracture tool*, `v_salvage_focus_fracture`, unbound).

20. **✅ Strafe and target acquisition swapped places (2026-11-23).** The user found the target-acquisition cluster on the MHG top mini-stick (js1 25–29) "barely used". Strafing and the decoupled toggle, which sat on the MTQ "COM" hat (js2 57–61), felt like they belonged on the stick. The two clusters swapped direction for direction:
    - **MHG mini-stick:** ↑ 25 strafe up · ↓ 27 strafe down · → 26 strafe right · ← 28 strafe left · press 29 decoupled toggle.
    - **MTQ "COM" hat:** ↑ 61 cycle all fwd · ↓ 60 cycle all back · → 58 closest hostile · ← 59 cycle pinned fwd · press 57 pin target. *Pin Selected Target* stays in `spaceship_targeting`.
    - Both clusters are in always-live (`spaceship_movement`) or combat-only (`spaceship_targeting*`) maps and no other binding used these ten buttons, so nothing doubles up.
    - `gamedata.py check` passes: 131 OK, 0 unknown, 0 wrong-map, no ghost on js1 25–29 or js2 57–61.
    - Strafing now depends on the mini-stick being in **Button Mapping** mode (§1.1).
    - Clicking the stick in while strafing toggles decoupled mode.
    - **Not yet flown, and not yet loaded in-game** (run `validate_actionmaps.py` after the next load).
    - *Update 2026-11-26 (item 21):* the stick press 29 is now full reverse, and the decoupled toggle went back to the MTQ "COM" hat press (tap; hold = pin).

21. **✅ Full reverse on the MHG stick press; decoupled back on the MTQ "COM" hat press (2026-11-26). The two-rebind reverse described here failed on load - see item 23.** The user asked for three things:
    - **Reverse on button 29.** The user wanted **both**: full reverse instantly on the stick press, and the proportional reverse on the throttle lever behind the detent (item 16).
      - The first commit wrongly moved the axis off, on the old belief that an action holds one joystick input. The game files disprove that: `layout_all_blank.xml` clears js1, js2 and js3 separately on every action (§2.5).
      - `v_strafe_back` now carries **two rebinds**: `js2_rotz` (proportional) and `js1_button29` (held = full).
      - The game offers no separate "full reverse" action. The only other reverse-related action, *Throttle - Forward / Back Invert*, flips a half-axis instead.
      - The user's complaint about the axis was really the forward creep below.
    - **Decoupled toggle onto the throttle unit,** "near the ESP or wherever you recommend". The MTQ has no free buttons (item 7), so it shares a press:
      - **First try: keypad A4** (tap = decoupled, hold = LAMP with `delayed_press`). **Rejected by the user** within the hour: they use LAMP far more than decoupling and want A4 to be LAMP alone. Lesson: LAMP is a frequently used control on this rig.
      - **Final: the "COM" hat press** (`js2_button57`), decoupled's home before 2026-11-23. **Tap = decoupled** (stock `tap`). **Hold = pin target** through the game's own hold action `v_target_pin_selected_hold` (stock `delayed_press`, in `spaceship_targeting`), which replaces the tap version `v_target_pin_selected`. No attributes needed - the same split as the "AP" key (dock / autoland).
      - Other options offered: the SPD key's free tap (hold = quantum), or an AB6 base lever as a coupled / decoupled switch using `v_ifcs_vector_decoupling_on` / `_off`.
    - **Forward creep at idle.** The user reported the ship sometimes inching forward with the throttle resting in the idle detent. That is the **forward** axis (`js2_roty`) reading a hair above zero in the detent's slack. It is fixed on the device, not in the profile: redo the MTQ **Idle** calibration a few mm forward of the detent (§1.1). **Done the same day:** Idle at ~15 % of travel, with the detent resting at ~13 %. An SC-side deadzone can't help, because SC's axis options are center-symmetric and would act at mid-throw.
    - `gamedata.py check` passes: 131 OK, 0 unknown, 0 wrong-map, no ghost on `js1_button29`, `js2_button4` or `js2_button57`.
    - **Not yet loaded in-game or flown.** After loading, run `validate_actionmaps.py` and check the export:
      - `v_strafe_back` should be listed with **both** `js2_rotz` and `js1_button29`. If only one survives, the game does limit an action to one joystick input after all, and this needs rethinking.
      - The decoupled toggle and `v_target_pin_selected_hold` should both be on `js2_button57`, and LAMP on `js2_button4` with no activation mode.

22. **✅ AB6 wings became a power panel; mining / salvage banks moved to the MHG right hat (2026-11-26).**
    - **The user's decisions:**
      - Left wing 49–51 = power toggles weapons / thrusters / shields (from MTQ A1–A3), 52 = assignment reset.
      - Right wing 53–55 = assignment taps weapons / engines / shields, mirroring the left wing, and 56 = shields to max (hold). These four came off the MTQ "WPN" hat.
      - The eight combat target-cycle bindings on the wings were deleted. The user never used them; general cycling is on the COM hat and the MHG hats.
    - **The consequence:** `spaceship_power` is always live, so the wings could no longer double as the Mining (49–52) and Salvage (49–55) banks. One press would have fired both, e.g. module 2 would also have cut thruster power.
    - **The plan:** written by a separate Fable 5.2 session at the user's request, checked here against the catalog and the game-data tool, then approved by the user.
      - Mining and salvage banks go to the **MHG right hat** (12–16), whose combat role is unchanged. Reason: when mining, the throttle hand is on the FLAPS lever, and head focus joins the left hat's salvage fire on the stick hand.
      - The alternative, the banks on the MTQ "WPN" hat, was offered and declined.
      - Jettison is alone on MTQ **A1**; salvage fire left / right are on **A2 / A3**.
      - Shield faces go on the freed "WPN" hat (item 14). The vehicle tractor distance is a trial on the MHG lower hat ↑/↓ in Salvage mode (item 15).
    - **Extras the user chose:**
      - Jettison needs a hold (`delayed_press`).
      - A `js1_ ` clear on *Autoland*: its stock js1 hold sits on right hat ↑, which the plan made busier. **Removed the same day (item 23):** it replaced the Autoland binding.
      - The tractor trial above.
    - **Counts:** 121 bindings + 11 clears across 21 actionmaps. `gamedata.py check`: 130 OK, 0 unknown, 0 wrong-map. No ghost on js1 12–19 or 49–56; the ghost list is otherwise unchanged.
    - **Not yet loaded in-game or flown.** After loading, `validate_actionmaps.py` should show:
      - the eight power actions on js1 49–56;
      - shield faces on js2 52–56;
      - jettison on `js2_button1` with `delayed_press`;
      - `v_autoland` with both `js2_button10` and `js1_ ` (wrong - it kept only the clear, item 23).
    - **Things to test in-ship:**
      - shield faces (Corsair first);
      - the OX tractor in Salvage mode;
      - module activation on the right hat (Golem);
      - the salvage bank (Salvation / Hyūn).

23. **✅ Fixed - the first load of the 2026-11-26 rework lost two bindings and left nine old ones behind (2026-11-26).**
    - **What the user saw:** after loading the profile, the throttle no longer reversed behind the idle detent. The stick press (29) reversed fine, and so did the AB6 wing power panel.
    - **Cause 1 - one joystick input per action (§2.5).** The game's export after the load held only the *last* rebind of each two-rebind action:
      - `v_strafe_back` = `js1_button29` only. The `js2_rotz` axis was gone.
      - `v_autoland` = the `js1_ ` clear only. The "AP" hold was gone; the user had not noticed yet.
    - **Cause 2 - loading is an overlay (§2.5).** Nine bindings deleted from the file earlier that day were still in the export:
      - the tap *Pin Selected Target* on `js2_button57`, so a tap of the COM hat press toggled decoupled **and** pinned;
      - the eight wing target-cycle actions on `js1_button49–56`, each firing together with a power-panel button.
    - **Why the tooling missed it:** `validate_actionmaps.py` compared actionmaps only, never inputs. `gamedata.py check` did not look at rebind counts.
    - **Fixes:**
      - `v_strafe_back` is `js2_rotz` alone again (proportional reverse, as flown 2026-11-20).
      - The `js1_ ` clear on `v_autoland` is removed. The js2 rebind already replaces the stock js1 default.
      - **Stick-press full reverse is now a trial on a different action:** `v_strafe_longitudinal` (*Throttle - Forward / Back*) on `js1_button29`, with `<flight_strafe_longitudinal invert="1"/>` in the js1 `<options>` so the button's full deflection points backward.
        - Unverified. Whether a button drives this axis action, and whether the invert applies to a button, are both guesses.
        - If the press thrusts forward or does nothing, remove both lines.
        - Other routes considered: MOZA Cockpit 2.0.0.111 shows no button-to-keyboard mapping in its install files (the action's keyboard slot, stock `S`, is separate and free). *Throttle - Forward / Back Invert* only flips the throttle half-axis while held, so it is not an instant full reverse.
      - The nine leftovers were deleted from `…\Profiles\default\actionmaps.xml` with the game closed. Backup: `actionmaps.xml.before-leftover-cleanup-2026-11-26.bak` in the same folder.
      - `gamedata.py check` gained `MULTI-BIND`. `validate_actionmaps.py` gained `INPUT-DIFF` and `LEFTOVER` (§10).
    - **State:** `gamedata.py check` gives 131 OK, 0 unknown, 0 wrong-map, 0 multi-bind. The validator against the cleaned export gives 0 leftovers and 2 input-diffs (`v_strafe_back`, `v_autoland`), which is the game still holding the bad load.
    - **Reloaded and validated the same day (1:09 PM):** `validate_actionmaps.py` gives 128 OK, 0 mismatch, 0 input-diff, 0 leftover, and the usual 3 stock-equal `NOT-IN-EXPORT`. The export lists `v_strafe_back` = `js2_rotz`, `v_autoland` = `js2_button10` and `v_strafe_longitudinal` = `js1_button29`.
      - The game wrote `<flight_strafe_longitudinal invert="1"/>` under **both** joystick instances, as it already did with `flight_view_pitch`. So a per-instance option in the file ends up on every joystick. Harmless here: nothing on js2 is bound to that action.
      - That session was the first after the USB re-wire (stick base and throttle moved to other ports, no hubs). The game still enumerated AB6 = joystick 1, MTQ = joystick 2, Razer keyboard = 3.
    - **Flown 2026-11-26 (Golem, New Babbage → ARC-L4 → MIC-L2), the user's report:** the throttle's reverse behind the detent works. The stick press does **not** reverse (item 24). Autoland on the "AP" hold and the rest of the rework were not reported.

24. **✅ Reverse is the MHG stick press alone; the throttle's reverse axis is unbound (2026-11-26).**
    - **The user's flight report that afternoon:** after the corrected reload, the press on `v_strafe_longitudinal` does nothing for reverse. Reverse works only on the throttle lever.
    - **Why [game]:** in `defaultProfile.xml`, `v_strafe_longitudinal` has no `onPress` / `onRelease` (it is axis-only), so a button bound to it never fires. `v_strafe_back` is the only reverse action with press / release triggers, and it holds one joystick input, the throttle axis (§2.5).
    - **The user's decision that evening:** `v_strafe_back` goes to the stick press (`js1_button29`), held for full reverse, and the throttle's reverse axis `js2_rotz` is left unbound. Their reasons: the lever can rest in the idle detent, and they never have to pull it through the detent lock, which they found annoying. This is the arrangement that reversed fine on the first 2026-11-26 load (item 23).
    - **Removed from `MOZA.xml`:** the `v_strafe_longitudinal` binding and its `<flight_strafe_longitudinal invert="1"/>` option. The game's saved profile still held both from the last load. With the user's OK and the game closed, they were deleted from `…\Profiles\default\actionmaps.xml` that evening: the `<action>` block and the option line under each joystick instance. Backup: `actionmaps.xml.before-reverse-cleanup-2026-11-26.bak` in the same folder.
    - **State:** `gamedata.py check` gives 130 OK, 0 unknown, 0 wrong-map, 0 multi-bind. `validate_actionmaps.py` gives 126 OK, 0 leftover and one input difference (`v_strafe_back`: the game still holds `js2_rotz`), which loading the profile clears. That was the state when it was written.
    - **Loaded and validated the same evening.** `Game.log` shows `MOZA.xml loaded` at 6:29 PM. After the 8:29 PM quit, `validate_actionmaps.py` gives 127 OK, 0 mismatch, 0 input-diff, 0 leftover and the usual 3 stock-equal `NOT-IN-EXPORT`. The export lists `v_strafe_back` = `js1_button29`. The session flew the Corsair (New Babbage → ARC-L1 → Wala → New Babbage) and the Golem (New Babbage → Wala → MIC-L5). 
    - **Confirmed in flight (user, 2026-11-26 night):** "pressing the coolie hat button goes in reverse now".
    - **Options weighed on the way, none of them bound:**
      - *Throttle - Forward / Back Invert* (`v_strafe_longitudinal_invert`, press / release, unbound) on the press. Its description reads "Inverts Strafe Longitudinal Absolute Axis Half (Neutral - Backward)", so while held it should make the throttle's forward travel act as reverse: reverse at whatever the lever is set to, nothing at idle. Whether it acts on a throttle bound to `v_strafe_forward` is unknown. **Rejected by the user (2026-11-26), untried:** they don't want the forward throttle turned into reverse.
      - A helper program that turns button 29 into the keyboard `S` key while held. `S` is the stock keyboard binding of `v_strafe_back`, and the keyboard slot is separate from the joystick one (§2.5). It needs software running beside the game; nothing is installed.
      - Give the press another job, or leave it empty. Anything on it also fires when the stick is clicked in while strafing.
    - **Spacebrake on the press: considered and dropped the same day.** The user first chose it, then decided the MTQ switch's spring-return position (`js2_button51`) is the best place for the brake. The edit was reverted before any commit. Don't suggest moving the brake again.
    - **Further candidates put to the user for the press (2026-11-26), not taken:** *Boost* (`v_afterburner`; it would leave the MTQ face button `js2_button65` free), *Enable / Disable Target Padlock (Toggle, Hold)* (`v_look_ahead_start_target_tracking`, unbound, untried), or nothing.

25. **✅ The throttle's power band is between its two detents (2026-11-27, a device change; no binding changed).**
    - **What the user wanted:** with reverse on the MHG stick press (item 24) the lever never goes behind the idle detent. So they asked for the forward throttle to run only between the detents: zero resting in the idle detent, full power at the forward detent, without pushing past it. Before, the forward detent gave about 75 % and the last quarter lay beyond it.
    - **What they did in MOZA Cockpit (their report):**
      - ran MTQ → *Panel Axis Calibration* (the *Dual Throttle Calibration* dialog, which records the range the levers are swept through during a countdown) and swept only between the two detents;
      - then set *Throttle Detent Settings → Limit Output Mode* to **Disabled**.
      - "That did the trick." §1.1 has the rows.
    - **How it got there:** I had suggested sweeping from the rear stop to the forward detent and keeping *Reverse Thrust* mode with new Idle and Rev idle marks. The user's way is simpler: with the range starting at the idle detent there is nothing behind it to set aside, so the detent mode can be off.
    - **Nothing in `MOZA.xml` changed but its comments.** `v_strafe_forward` is still `js2_roty`, and `gamedata.py check` still gives 130 OK.
    - **State:** set on the device, by the user's report. Flown, as far as I can tell, in the 7-minute session at 6:13 PM that day. The readings at the two detents were not seen in a screenshot. The cards and the binding sheet were updated.
    - **Watch for forward creep at idle.** Zero is now exactly on the idle detent, which has slack; on 2026-11-20 the same placement let the ship inch forward now and then. The fix would be to redo the calibration starting a few mm forward of the detent.
    - **Fallback that was not needed:** a response curve on the throttle axis in the profile's `<options>` block. Untested; SC's axis options are symmetric about the middle of an axis, so it might also have added a dead band above idle.
    - **Also seen that evening:** the *Throttle Detent Setup* dialog showed X = Y = 11227 with the levers at 29.6 % of travel, and the same figure in a later screenshot with them at 13.0 %. So those two readouts do not always refresh: don't read a live value off a still of that dialog.

---

## 7. Refreshing the keybind database

The master catalog is **patch-specific**. When a new Star Citizen version ships, regenerate it and
re-check the profile - both come from the same tool, read the installed game's own files, and need no
internet.

### Easy way (two commands)

From the project root:

```sh
python tools/gamedata.py check        # every binding still a real action in the right actionmap? any new ghost defaults?
python tools/gamedata.py catalog    # rewrite reference/SC_KEYBINDS_DATABASE_v<major.minor>.md, remove the old snapshot
```

`catalog` names the file after the build's branch version (`sc-alpha-4.10.0` → `v4.10`), so hotfixes
inside one patch line overwrite the same file. **After it runs, update the version referenced at the
top of this `CLAUDE.md`, in the folder-layout block, in §9, in `README.md` and in the two `reference/`
docs** if the name changed.

Requires Python 3 and a zstd decoder - built into Python 3.14+, otherwise `python -m pip install zstandard` (it's in `tools/requirements.txt`). Run from a clone outside the game folder (e.g. on a Mac), the tool can't find `Data.p4k` by itself; pass `--p4k <path>`.

### How it works (for future Claude)

1. **Where the data is.** `…\StarCitizen\LIVE\Data.p4k` is a ZIP64 archive (~160 GB, ~1.4 million
   entries) whose entries use CIG's compression method 100 = zstd. The tool reads only the central
   directory at the end of the file, finds two entries by name, and decompresses just those:
   - `Data\Libs\Config\defaultProfile.xml` - every action, its actionmap, its default
     keyboard / mouse / joystick / gamepad bindings and activation mode. Stored as **CryXmlB** (CIG's
     binary XML), which the tool decodes.
   - `Data\Localization\english\global.ini` - `key=value` text; resolves the `@ui_…` label and
     description references.
2. **Version.** Read from `…\LIVE\build_manifest.id` (JSON: `Branch`, `Version`,
   `RequestedP4ChangeNum`, `BuildDateStamp`). The manifest does **not** contain the marketing patch
   number - build `4.10.201.48085` on branch `sc-alpha-4.10.0` is what the launcher calls Alpha 4.10.3.
3. **Render.** One Markdown table per actionmap, in the game's own order.
4. **Other useful entries in the same archive** (not used by the tool, handy for research):
   `Data\Libs\Config\Mappings\layout_*.xml` are CIG's stock device layouts in the same format as
   `MOZA.xml` (`layout_all_blank.xml` shows the clear syntax), and
   `Data\Scripts\Entities\Vehicles\Implementations\Xml\<ship>.xml` lists each ship's hardpoints - how
   the **[game]** facts in §11 were read.

### Why not starbinder any more

Up to Alpha 4.8 the catalog was downloaded from <https://starbinder.space/>. On 2026-11-20 that
domain was serving a registrar "registration has expired" page, and the author's repository
(<https://github.com/ZOMGbies/starbinder>) had not been pushed to since 2026-05-13. The game files are
the better source anyway: starbinder gave a curated label list grouped by *keyword category*, never the
actionmap or the default bindings - which is exactly the information the stock-default overlaps in §2.5
were hiding in.

---

## 8. Regenerating the button-reference cards

The two cards - `MOZA_MHG_AB6_ref.png` (js1) and `MOZA_MTQ_ref.png` (js2) - are **printable cheat sheets** sized to fill a **US-Letter sheet in landscape** (11×8.5, ratio 1.294). Each is a **60 / 40 split**: the left ~60% holds the manufacturer diagram **split into its sub-views and stacked** (the two small views side by side on top, the one big view below); the right ~40% holds a **button# → function** lookup table in two columns. They're rebuilt by one committed script - [`tools/regen_cards.py`](tools/regen_cards.py) - with **no hand-placement of numbers** anywhere (the numbers ride along inside the manufacturer art; see §8.2).

| Card | Device | Top-left band (two views side by side) | Bottom-left band (one big view) |
| --- | --- | --- | --- |
| `MOZA_MHG_AB6_ref` | js1 - grip 1-29 + base 49-62 | MHG grip front (head + hats) · MHG grip side | AB6 base (smaller - far fewer buttons) |
| `MOZA_MTQ_ref` | js2 - throttle 1-65 + axes | Right Module · Left Module | Throttle panel (the button-dense view) |

### 8.1 Rebuild them (one command)

From the project root:

```sh
python tools/regen_cards.py
```

It writes the four card files into `cards/` - `MOZA_MHG_AB6_ref.png/.svg` and `MOZA_MTQ_ref.png/.svg` - overwriting the previous versions. The `.svg` is the editable source (self-contained: each recolored sub-view is embedded as a base64 PNG, so the SVG needs no sidecar files). **Print at "Fit to page" / 100%, landscape** - the image is already the page aspect, so it fills the sheet. **Requirements:** Python 3.8+ with **Pillow**, and **Chrome, Edge or Chromium** (used headless to rasterize SVG → PNG at 2×, ≈330 DPI). The script finds the browser on Windows, macOS and Linux; set `CARD_BROWSER=<path>` to choose one.

### 8.2 How a card is built (split diagrams + table, composited in SVG)

1. **Diagram layer - comes straight from the manufacturer PNG, never edited by hand.** `diagrams/MOZA_AB6.png` / `MOZA_MHG.png` / `MOZA_MTQ.png` already show every button numbered with a leader line. The script does **not** move, add, or relabel a single number - they're the manufacturer's own numbers riding along inside the image. Three helpers process them:
   - **`get_sub_diagram`** crops a **sub-rectangle** out of a source PNG so each packed view - throttle panel, Right/Left Module, grip head, grip side, base - is shown big on its own. The crop boxes (`x0, y0, x1, y1` in source pixels) are listed in the script header; re-verify only if MOZA ships new device art.
   - It then recolors the crop to white-background line work. Recolor math = **grayscale → invert → levels stretch** (Pillow `point`): `out = -k·luma + k·(1−black)`, `k = 1/(white−black)`, tuned `black=0.45`, `white=0.85` (navy bg → white, faint line-art → crisp dark).
   - **`add_diagram_stack`** lays the sub-views into the left ~60% as a column of **bands**: each band gets a height share (`HFrac`, equal by default) and holds one or more images placed **side by side**, each owning a cell = `Frac` of the zone width, fit/centered (optional caption under it). Resize a view by changing its `Frac` - e.g. the AB6 base's `Frac` is kept below the grips' so it reads smaller.
2. **Table layer - the part you edit.** Five Python lists - `AB6`, `MHG_L`/`MHG_R`, `MTQ_L`/`MTQ_R` - hold one dict per row. `add_row` / `new_card` draw each as a dark number badge + function text with alternating row shading, and `render_png` rasterizes via headless Chrome. The combined card's right column is `MHG_R + AB6`.

> **Source of truth is `MOZA.xml`, not these lists.** The lists are a hand-maintained *view* of the bindings. Nothing cross-checks them against the XML, so when you change a binding you must edit both (see §8.3).

### 8.3 Updating after you change a binding

1. Edit [`MOZA.xml`](MOZA.xml) as usual (and its inline comment / §4 of this doc).
2. Open `tools/regen_cards.py`, find the row whose `Label` is that **button number**, and edit its fields:

| Field | Meaning | Example |
| --- | --- | --- |
| `'Label'` | The number printed on the diagram (or an axis name / a range like `57-59`). **Must match the diagram.** | `'52'`, `'Slider'`, `'31-43'` |
| `'Primary'` | The main (combat / default) function - what the button does in flight. | `'Target: lock closest attacker'` |
| `'Hint'` | *(optional)* grayed parenthetical naming **where** the control is. Used heavily on the MTQ. | `'WPN hat up'`, `'keypad A1'` |
| `'Variants'` | *(optional)* the operator-mode alternates for that **same physical button**, built with `V('<tag>', '<text>', color)`. Keep `<text>` short (see note below). | `[V('Mine:', 'module 1', C_MINE), V('Salv:', 'focus all', C_SALV)]` |
| `'Unbound': True` | *(optional)* renders the row grayed (rest positions, reserved levers, absent axes). | rocker center `22`, levers `57-62` |
| `'Header'` | A row that is actually a section header inside a column (no badge). | `{'Header': 'AXES'}` |

3. Re-run the rebuild command (§8.1).

The mode-tag colors are fixed: **`Mine:`** = amber `C_MINE`, **`Salv:`** = teal `C_SALV`, **`Msl:`/notes** = gray `C_NOTE`. These encode the [operator-mode reuse](#5-operator-mode-reuse-mining--salvage) - one physical control doing a different job per mode.

> **Labels here are abbreviated.** Because the 40% columns are narrow, primary/variant/header text is deliberately **terser than `MOZA.xml`** (headers are just `PANEL BUTTONS 1-30`; variants are `Salv: gap +`, not `Salvage Beam Spacing Increase`). Same bindings, shorter wording - keep new lines short or they overflow the column.

> **You rarely touch anything else.** Button numbers and leader lines are baked into the diagram art, so adding/removing a binding is a one-row text edit. You only touch `get_sub_diagram`'s crop boxes / levels or swap the `MOZA_<device>.png` source if **MOZA ships a new device diagram** with a different layout.

### 8.4 Layout knobs & gotchas (for whoever maintains the script)

- **Per-card layout** lives in each `new_card({...})` call: `F` (global font scale - the narrow 40% table forces **1.18 / 1.15**), `CanvasW`/`CanvasH` (held at the 1.294 page ratio, rendered 2×), `Stack` (`X`, `W`, `Gap`, and `Rows` - the diagram bands, each `{'Imgs': [{'D', 'Frac', 'VA', 'Caption'}]}`), and `Cols` (the two table columns, each `{'X', 'W', 'Rows'}`). Want bigger diagrams? widen `Stack['W']` and shrink the columns / `F`.
- **Rendering.** `render_png` runs the browser with an argument list (no shell quoting), passes the SVG as a `file://` URI (`Path.as_uri()` percent-encodes the spaces in `…\Program Files\…`), screenshots into a temp folder, then moves the PNG into `cards/`. An isolated temp `--user-data-dir` keeps the headless run from colliding with a Chrome that's already open. Chrome writes "NNN bytes written…" to stderr even on success, so stderr is discarded and success is judged by the PNG existing.
- **Fonts.** The SVG asks for *Segoe UI*, then *Arial*. On a Mac it renders in Arial, which runs slightly wider - look at the PNG for clipped table text after regenerating there.
- **Rounding.** `rnd` / `r1` round half-to-even, the rule the original PowerShell (.NET `Math.Round`) used, so the port reproduces its geometry exactly. Verified 2026-11-23: the SVG markup matched the PowerShell output byte for byte apart from the embedded images, and the PNGs differed by at most 2/255 per pixel.
- SVGs are written UTF-8 **without BOM**.

---

## 9. Reference links

- **Local master catalog:** [`reference/SC_KEYBINDS_DATABASE_v4.10.md`](reference/SC_KEYBINDS_DATABASE_v4.10.md)
- **Star Citizen wiki - Controls:** <https://starcitizen.tools/Guide:Controls>
- **Master Modes / IFCS:** <https://starcitizen.tools/Flight_system>
- **ESP (Enhanced Stick Precision):** <https://starcitizen.tools/ESP>
- **Star Citizen Wiki API** - per-ship game-data extract, the source of the **[ref]** facts in §11: `https://api.star-citizen.wiki/api/v2/vehicles/<slug>` (e.g. `anvl-liberator`, `orig-m80`, `drak-golem`)
- **starbinder** - dead (domain expired, see §7); listed for history only: <https://starbinder.space/>

---

## 10. Authoritative actionmaps - local sources & validation

Every `<action>` in `MOZA.xml` must sit inside the **actionmap CIG defined for it**. Put it in the
wrong map and the game **silently drops the binding** - no error, it just does nothing. (This bit a
camera experiment: `view_fov_*` / `view_enable_camview_mode` placed in `spaceship_view` did nothing -
they belong to `view_director_mode`, not `spaceship_view`.)

### 10.1 Where the authoritative mapping lives (all local)

| Source | What it gives | Notes |
| --- | --- | --- |
| **`Data.p4k` → `Data\Libs\Config\defaultProfile.xml`** | The **complete** action→actionmap list for the installed build, with every default binding and activation mode. | **Ground truth.** [`tools/gamedata.py`](tools/gamedata.py) reads it directly in about a second (§7); the catalog in `reference/` is its rendered form - each section heading there *is* the actionmap. Available before you ever launch the game. |
| **Game export** `…\StarCitizen\LIVE\user\client\0\Profiles\default\actionmaps.xml` | The game's **normalized copy of the currently-loaded profile** - every *accepted*, non-default binding filed under its true actionmap, plus the device each joystick instance resolved to. | **Proof of acceptance.** Only as fresh as the last in-game profile load - check its timestamp. Its `<options … Product=…>` lines also record which physical device was `js1`/`js2` in that session (§1). |

> **The same action name can exist in more than one actionmap.** `v_pitch`, `v_yaw`, `v_view_yaw`,
> `v_view_pitch`, `v_flightready`, the door actions and `v_starmap` each have a ship copy and a
> ground-vehicle copy. They are separate bindings - a rebind or clear under one map does not touch the other.

### 10.2 Why the game export doubles as a validator

When you load a profile (Options → Keybindings → Load, or `pp_rebindkeys MOZA.xml`), the game rewrites
that export. Two behaviors make it a free correctness check:

1. It files each **accepted** action under the actionmap it really belongs to.
2. It **drops** any action whose actionmap is wrong, or whose binding it otherwise rejects.

So an action **missing** from the export after a load is either:

- a **default** (the game omits bindings equal to SC defaults - e.g. `v_pitch`=`js1_y`, trigger→mining-laser fire) - **benign**, or
- **dropped** (wrong map / rejected binding) - **a bug to fix**.

An action present under a **different** actionmap than `MOZA.xml` uses is an outright **mismatch**.

What the export **cannot** show is a stock default the profile never touched - it lists only what
*differs* from stock. That blind spot is why §2.5's overlaps went unseen; `gamedata.py check` covers it.

The export also shows two things about the **inputs** (both learned on 2026-11-26, §6 item 23):

- An action in the export with a **different input** than `MOZA.xml` means the game replaced or lost
  the binding - for example the second of two rebinds on one action winning.
- An action in the export that `MOZA.xml` **does not declare** is a leftover from an earlier load. The
  game keeps it, and it still fires.

### 10.3 Run the checks

Two steps, in this order:

```sh
# 1) BEFORE launching (no game launch needed) - from the project root:
python tools/gamedata.py check

# 2) AFTER loading MOZA.xml in-game (Keybindings > Load, or console: pp_rebindkeys MOZA.xml)
#    AND quitting the game (it writes the export on exit):
python tools/validate_actionmaps.py
```

- **`gamedata.py check`** reports `UNKNOWN` (no such action in this build), `WRONG-MAP` (the game will
  drop it), `MULTI-BIND` (more than one rebind on an action; the game keeps only the last) and
  `GHOST` (an un-overridden stock joystick binding, §2.5). Non-zero exit on any
  UNKNOWN / WRONG-MAP / MULTI-BIND. The expected `GHOST` list is the "deliberately left in place"
  table in §4 - anything new there after a patch deserves a look.
- **`validate_actionmaps.py`** reports, per action against the export:
  - `OK` - same actionmap and same input;
  - `MISMATCH` - filed under a different actionmap;
  - `INPUT-DIFF` - same actionmap, different input (lost or replaced, or the profile was edited
    since the last load);
  - `LEFTOVER` - a joystick binding in the export that `MOZA.xml` does not declare;
  - `NOT-IN-EXPORT` - not listed (equal to stock, or dropped).

  Non-zero exit on `MISMATCH`, `INPUT-DIFF` or `LEFTOVER`. A **cleared** default (`js1_ `) differs
  from stock, so it should be listed in the export after a load - one that shows up as
  `NOT-IN-EXPORT` means the game did not take the clear.

Workflow when adding/moving a binding: look the action up in the catalog (its section heading is the
actionmap) → edit `MOZA.xml` → `gamedata.py check` → load it in-game → quit → `validate_actionmaps.py`.
When a binding is **removed** from `MOZA.xml`, expect a `LEFTOVER` for it and clear it in the game. The
export check is what caught `v_target_pin_selected` and `view_restore_defaults`; the game-data check is
what caught the stock *Landing System (Toggle)* and *Interaction Mode* overlaps.

> **State on 2026-11-20:** both steps pass. Step 1: 131 entries OK, 0 unknown, 0 wrong-map. Step 2,
> after `MOZA.xml` was loaded in a 4.10.3 session: 128 OK, 0 mismatch, and the only 3 `NOT-IN-EXPORT`
> are the known stock-equal bindings (`v_pitch`, mining-laser fire, salvage focused fire). The export
> lists all 10 clears as `js1_ `, `v_strafe_back` on `js2_rotz`, and *Request Cargo Loading* with its
> `delayed_press` mode. That session enumerated AB6 = joystick 1, MTQ = 2, Razer keyboard = 3.
>
> **State on 2026-11-26:** both steps pass. Step 1: 131 OK, 0 unknown, 0 wrong-map, 0 multi-bind.
> Step 2, after the corrected profile was reloaded at 1:09 PM: 128 OK, 0 mismatch, 0 input-diff,
> 0 leftover, and the same 3 stock-equal `NOT-IN-EXPORT` (§6 item 23). Flown that afternoon (§6 items 23 and 24).
>
> **State on 2026-11-26, evening:** `MOZA.xml` changed after that load: reverse moved to the stick
> press alone and the failed trial came out (§6 item 24). Step 1 passes (130 OK). Step 2 reports an
> input difference on `v_strafe_back` until the profile is
> loaded again. The trial's leftover was deleted from the saved profile with the game closed.
>
> **State on 2026-11-26, night:** both steps pass again. The profile was loaded at 6:29 PM. Step 2
> after the 8:29 PM quit: 127 OK, 0 mismatch, 0 input-diff, 0 leftover, and the same 3 stock-equal
> `NOT-IN-EXPORT`. The export lists `v_strafe_back` = `js1_button29`. That session enumerated
> AB6 = joystick 1, MTQ = 2, Razer keyboard = 3. Flown (Corsair, Golem); the user confirmed the
> stick press reverses (§6 item 24).

---

## 11. Fleet - what each ship uses

The profile is tuned for this fleet. Current lineup **2026-11-23** (eleven ships), after a last
melt-and-rebuy on the final IAE 2956 sale day: the F8C Lightning left; the **Gatac Hyūn** and the four
2956 Best in Show ships joined - **Perseus, Ironclad Assault, M80, Corsair**, bought as the *2956 Best in
Show Complete Pack* (the M80 was already in the fleet). Earlier changes: set 2026-11-20; on 2026-11-22
the Avenger Titan and C2 Hercules left and the C8R Pisces Rescue joined.

Facts marked **[game]** were read directly from each ship's definition inside `Data.p4k` for build
`4.10.201.48085`. Facts marked **[ref]** come from the Star Citizen Wiki API's `4.10.3-LIVE` extract
(`4.10.3-LIVE.13165946` for the 2026-11-23 additions) or CIG's own Q&A posts and were **not** checked
in-ship - treat them as likely, not proven. The Wiki API's `mounting_positions` field is the quickest
read of a ship's guns, turrets, racks and tool arms; its `propulsion.thrust_capacity.vtol` is non-zero
exactly on the ships known to have VTOL (Liberator, Golem, Golem OX), so it is used as the VTOL test.

| Ship | Role in the fleet | Systems that matter for the rig |
| --- | --- | --- |
| **Anvil Liberator** | Mothership / home base - carries the others. | Pilot + gunner seats and **no pilot guns**: 4x S4 missile racks, one manned S5 turret, two S3 remote turrets **[game]**. 2x **S3** shields, 4 **VTOL** thrusters, a **docking collar**, front + rear ramps, vehicle-bay door, landing-pad doors, elevator doors **[game]**. Shield type *Quadrant* **[ref]**. |
| **Origin M80** | Combat. Now the Best in Show pledge (from the Complete Pack). | Single seat. 2x S5 + 2x S4 guns, 4 missile racks, 2x S2 shields, no VTOL **[game]**. Shield type *Bubble* **[ref]**. |
| **RSI Perseus** | *Not stated yet* (CIG role: Heavy Gunship). Joined 2026-11-23. | Crew of 6, **no pilot guns**. Two manned S8 turrets (2x S8 Medusa cannons + 2x S3 Gatlings each), two remote S3 turrets run from the co-pilot and gunner seats, 6 automatic point-defense turrets, 2 torpedo racks (10x S5 each; the API names no seat for them), 2x **S3** shields (*Quadrant*), **VTOL**, 96 SCU, docking collars **[ref]**. |
| **Drake Ironclad Assault** | *Not stated yet* (CIG role: Heavy Dropship). Joined 2026-11-23. | Crew of 7-8, **no pilot guns**. Three manned turrets (bottom: 4x S5 Gatlings; left / right: 2x S3 repeaters each), five remote turrets, 2 missile racks (5x S5 each; no seat named), 4x **S3** shields (*Quadrant*), **VTOL**, **1,440 SCU**, docking collar **[ref]**. |
| **Drake Corsair** | *Not stated yet* (CIG role: Expedition). Joined 2026-11-23. | Crew of 4. **6 pilot guns** - 2x S5 + 4x S4 cannons - plus two manned side turrets (2x S2 each) and a tail turret (2x S2) run from the co-pilot seat, 4 missile racks (8x S3), 1x **S3** shield (*Quadrant*), no VTOL, 72 SCU, docking collar listed **[ref]**. |
| **Gatac Hyūn** | Mining + salvage hybrid (the user's 2026-11-22 trial, §6 item 19). Joined 2026-11-23. | Single seat. 4x S3 gimballed repeaters, 1 missile rack (8x S2), 2x S2 shields (*Bubble*), no VTOL. Mining arm with the stock S1 **Arbor MH1** laser (117-2,340 power, **1 module slot**; the second socket under it is a ventilation attachment, not a module) on a swappable mount, ore stored in **four pods totaling 32 SCU** (no separate cargo grid listed), two salvage arms with S2 Baler heads (Abrade scraper module each), a disintegration intake, and an S2 radar slot **[ref]**. |
| **Drake Golem** | Mining - for profit and crafting materials. | Single seat. Mining arm, 2x S1 guns, 2x S1 missile racks, 1x S1 shield, **VTOL** (rotating nacelles) **[game]**. Laser has **2** module slots **[ref]**. |
| **Drake Golem OX** | Light cargo runs. | Golem airframe with a cargo grid, a deployable turret and a *salvage* controller instead of the mining arm **[game]**; the turret carries a tractor beam **[ref]**. **VTOL**. |
| **RSI Salvation** | Salvage - gathers RMC so repairs aboard the Liberator don't have to be bought. | Single seat. Two salvage arms plus a disintegration field, 2x S1 guns, 2x S1 shields, no missile racks, no VTOL **[game]**. |
| **RSI Ursa Medivac** | Ground / medical. | Driver + passenger seats, turret mount, ramp + side door **[game]**. Driven on the **Xbox controller** - the rig is deliberately inert in it (§4 *Cleared game defaults*). |
| **Anvil C8R Pisces Rescue** | Medical and courier - the fleet's flying med bed. | Single seat. **T3** med bed, 2x S1 gimballed guns, 2x S1 missile racks, 1x S1 shield (*Bubble*), no VTOL thrusters, no cargo grid (~0.8 SCU internal storage), quantum drive **[ref]**. |

### 11.1 How the controls line up

One row per ship (the table was turned on its side on 2026-11-23, when the fleet grew to eleven).
Columns: **VTOL** = the MTQ VTOL switch (`js2` 49 / 50) · **Trigger** = guns on `js1` 1 / 6 ·
**Missiles** = knob detent 2 + `js1` 2 / 4 / 22 / 23 · **Mining** = knob 4, FLAPS axis, right-hat modules ·
**Salvage** = knob 5, SPEEDBRAKE axis, right-hat bank + A2/A3 fire · **Dock** = "AP" tap · **Cargo** = the cargo grid
that "ALT" hold (*Request Cargo Loading*) serves · **S3 faces** = Size 3 *Quadrant* shields, the only
kind `v_shield_raise_level_*` acts on (on the "WPN" hat since 2026-11-26, a trial - §6 items 14, 22).

| Ship | VTOL | Trigger | Missiles | Mining | Salvage | Dock | Cargo | S3 faces |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Liberator | yes | turrets only | yes | - | - | yes | 400 SCU | yes |
| M80 | - | yes | yes | - | - | - | 2 SCU | - |
| Perseus | yes | turrets only | torpedoes - seat unchecked | - | - | listed [ref] | 96 SCU | yes |
| Ironclad Assault | yes | turrets only | racks - seat unchecked | - | - | listed [ref] | 1,440 SCU | yes |
| Corsair | - | yes | yes | - | - | listed [ref] | 72 SCU | yes |
| Hyūn | - | yes | yes | yes | yes | - | - (32 SCU ore pods) | - |
| Golem | yes | yes | yes | yes | - | - | - | - |
| Golem OX | yes | yes | yes | - | tractor? | - | 64 SCU | - |
| Salvation | - | yes | - | - | yes | - | 6 SCU | - |
| C8R Pisces | - | yes | yes | - | - | - | - | - |

**On every ship:** the AB6-wing power panel, countermeasures, targeting, doors, lights, gear.
The Ursa Medivac is left out of this table: it is driven on the Xbox controller.
Cargo figures are the Wiki API's `cargo_capacity` **[ref]**.

Per-ship notes:

- **Liberator - doors.** MTQ toggle A up fires *Unlock All Doors* + *Open All Doors*. On this ship that
  is both ramps, the vehicle-bay door and the pad and elevator doors **[game]**, and CIG's IAE 2956 Q&A
  says opening the front or rear garage doors **vents that space** **[ref]**. Don't flip it in vacuum
  with people or loose vehicles inside.
- **Liberator - services and stowage.** CIG's IAE 2956 Q&A says repair / refuel / rearm is currently
  limited to the **internal garages**, with external pads to follow **[ref]**. Stowage is settled: the
  user confirmed on 2026-11-20 that every ship they carry fits (Golem, Golem OX, Salvation in the
  garage, M80 on the top rear pad), and on 2026-11-21 that the C8R Pisces rides inside too - not an
  open question.
- **Shield faces.** The Liberator, Perseus, Ironclad Assault and Corsair all carry S3 *Quadrant*
  shields **[ref]**; their faces are on the MTQ "WPN" hat since 2026-11-26, untested (§6 items 14, 22).
- **M80 - guns.** Split the weapon groups in the MFD (S5 pair = group 1, S4 pair = group 2) so trigger
  stage 1 / stage 2 mean something - see the Weapons note in §4. CIG's DefenseCon 2956 Q&A says the S5
  pair deploys from the hull when powered on **[ref]**, so there is nothing to bind for that.
- **Corsair - guns.** The same S5 + S4 split as the M80 (2x S5 + 4x S4 cannons): S5 pair = group 1,
  S4s = group 2. Its side and tail turrets are crew seats.
- **Perseus and Ironclad Assault - pilot seat.** Neither has pilot guns, so from the pilot seat the
  trigger and gun-group stages do nothing; the stick and MTQ fly the ship and run power, targeting,
  countermeasures and doors. Which seat fires the Perseus's torpedoes and the Ironclad Assault's
  missile racks is not in the API data - check in-ship before relying on missile mode there. In a
  turret seat the stick aims through the stock turret defaults left in place (§4), as on the Liberator.
- **Hyūn - one seat, both tools.** Knob detent 4 (Mining) and 5 (Salvage) both apply. The rocker
  center (`js1_button24`) is the tool-mode press in both: fracture ↔ extraction on the laser,
  structural-field mode in salvage (§6 item 19). Not yet flown with the rig.
- **Hyūn - modules.** The stock Arbor MH1 has one module slot, so only the MHG right hat ↑ (slot 1)
  does anything, and only with an *active* module fitted. A two-slot laser (Helix I or Impact I) would
  bring right hat → (slot 2) into play. No binding change either way.
- **Golem - modules.** Only slots 1 and 2 exist on its laser **[ref]**; right hat ↓ (slot 3) does nothing.
- **Golem OX - tractor.** Trial binding since 2026-11-26: MHG lower hat ↑/↓ = tractor distance in Salvage mode (knob 5). Unverified - §6 items 15, 22.
- **Salvation.** Fully covered and the only ship besides the Golem whose slider axis was confirmed
  in-ship (June 2026, Alpha 4.8).
- **Golem OX - cargo.** *Request Cargo Loading* is a hold on "ALT"; a tap is still *Request Landing*.

---

*Last reviewed for Star Citizen Alpha 4.10.3 - build `4.10.201.48085` (2026-11-20). Update the version stamp and the catalog file when you refresh the database.*
