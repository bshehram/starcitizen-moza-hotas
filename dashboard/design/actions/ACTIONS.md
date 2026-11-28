# Actions in the rig reference: what is bound and what is not

The implementer's brief for one feature of the dashboard's Rig reference section
([`../../PLAN.md`](../../PLAN.md) §4 item 20). Written 2026-11-28 by the feature's designer.
A Worker builds from this file; a reviewer checks the build against it.

Marks, as everywhere in this project: **[game]** read from the installed game's files,
**[seen]** read from files or captures on this PC with the date, **[ref]** from the project's
docs, **[verify]** reasoning or an open point. "The user" is the repo's owner.

## 1. What it is for, and what it is not

The user, 2026-11-28, about the Rig reference's Find page: "it would be better i think if it
also showed logically and clearly which bindings we do have bound and which ones exist that we
have not bound (like ESP and Decoupled, etc) and if we can make it pull the available bindings
from existing game files so its always updated with the latest patch in the game, thats better
than relying on third party websites databases or APIs".

So:

- A list of **the game's own actions**, grouped the way the game's Keybindings menu groups them,
  each marked **bound** (and to which control of the rig) or **not bound**.
- Read from **the installed game's files**. No web site, no community database, no API.
- For an action that is not bound, **which controls of the rig have room for it**, as far as the
  rig's own tables know. The user decides what to bind next from this.

It is not a binding editor. Nothing on the page changes `MOZA.xml`. It does not advise what to
bind. It does not list on-foot emotes: the rig is used only in ships ([`../../../CLAUDE.md`](../../../CLAUDE.md) §1).

## 2. Where it stands

- **Designed and mocked up, not built.** The mockup runs on real data and was captured in both
  orientations, terminal region on and off (§9). No real pointer has touched it and it has not
  been seen on the 15.6 inch panel.
- **Waiting on the user:** the three questions in §11. The defaults there are what this brief
  describes; build them unless the lead says otherwise.
- **Build order:** stage A (the data) first, then stage B (the page). §12 has both briefs.

## 3. The facts it rests on

| Fact | How it is known |
| --- | --- |
| The game defines 1,104 actions in 50 actionmaps. Each actionmap carries the name the Keybindings menu shows for it (`UILabel`: "Flight - Movement", "Vehicles - Weapons", "On Foot - All"...), non-empty for 40 of the 50. 753 actions have a name of their own in the English text (794 carry a name key; 41 of those resolve to nothing); the other 351 are not shown in the game's menu. | [game] `defaultProfile.xml` and `global.ini` in `Data.p4k`, build 4.10.201.48085, read 2026-11-28 with `tools/gamedata.py`'s loader. |
| The actionmap's second attribute, `UICategory` (FLIGHT, ON FOOT, Vehicle, CAMERA), is empty for the seat, turret and lights maps. It cannot decide what belongs to a ship. | [game], same read. |
| `MOZA.xml` named 130 actions that day: 120 bound, 10 cleared. All 120 bound ones are in ship actionmaps. | [seen 2026-11-28, about 11:15 AM; a binding change was in progress, so expect 119 or so] |
| Of the 431 named actions in the 24 ship actionmaps: 120 bound, 309 not bound, 1 cleared (*Landing System (Toggle)*), 1 with the game's joystick default still live (*Weapon Preset - Fire*). 77 more ship actions have no menu name. | [game] + `MOZA.xml`, the mockup's generator. |
| An action holds one joystick input. A rebind in the profile replaces the game's joystick default; an action the profile never names keeps that default, live on joystick 1. | [ref] root `CLAUDE.md` §2.5, proven there by the game's export. |
| An action with no activation mode and no press, hold or release trigger in the game's file is axis-only: a button bound to it never fires. 59 of the listed actions are like that. | [game] for the attribute; [ref] root `CLAUDE.md` §6 item 24 for the effect (one flight report, `v_strafe_longitudinal`). |
| `rig.json` says, for 18 actionmaps, in which operator modes the map is live, dead or not known, and for each of the 96 controls what it does in each mode, with `"unknown"` cells. Six controls have nothing bound: the two base levers, the power rocker's rest position, the lever detents, and two throttle axes. | [seen] `dashboard/web/rig/rig.json` schema 2, 2026-11-28; [`../../RIG.md`](../../RIG.md). |
| The page already receives the running game's version: `state.session.version` is the log's `FileVersion:` line, the same string as `Version` in the game's `build_manifest.id`. | [seen] `scdash/state.py`, `tests/samples/*.log`. |
| The service serves from `web/rig/` exactly `rig.json` and the images; each file at most 1 MiB. | [seen] `scdash/server.py` (`RIG_DATA`, `rig_files()`), `config.MAX_RIG_FILE_BYTES`. |
| `tools/regen_cards.py`'s `read_catalog()` splits the catalog's Markdown rows on `\|` and skips a row that does not give six cells. No name holds a pipe today. | [seen] the code; [game] the count. The reason the new table is not built on the Markdown catalog. |

**Not checked:** whether an action without a menu name can be bound through the profile file;
what `smart_toggle`, `hold_toggle` and `all` do exactly (the page shows those names unworded).

## 4. The design in one page

- **Data:** a new command, `python tools/gamedata.py actions`, writes
  `dashboard/web/rig/actions.json` from the game's files, `MOZA.xml` and `rig.json`.
  `tools/regen_cards.py` runs it at the end of its dashboard step, so a binding change still
  needs one command. After a game patch it is one more line in the patch routine.
- **Page:** the Find page gets a two-way switch, **Controls** (the 96, as today) and **Actions**
  (the game's list). Actions has a rail of the game's groups with "bound / all" counts, state
  keys (All, Bound, Not bound, Game default live, Cleared), and rows that read like control rows
  the other way around: the action's name first, the control's number in the badge.
- **From an action to a control:** an opened action that is not bound shows "Room": the controls
  with nothing bound, and the controls that are idle in the modes the action's group is live in.
  A click on one opens that control on its diagram page.
- **From a word to an action:** typing "esp" on Controls finds no control and then lists the
  game's actions that match, with a button to see them in Actions.
- **Honesty:** every fact carries its source; where the rig's tables do not know, the page says
  "not known" and never "free".

## 5. The data

### 5.1 The generator's place

`tools/gamedata.py` gets a third command beside `check` and `catalog`.

```
python tools/gamedata.py actions            write dashboard/web/rig/actions.json
python tools/gamedata.py actions --check    build in memory, say what would change, write nothing; exit 1 if it would change
        --p4k <Data.p4k>   --mapping <MOZA.xml>   (as for check)
```

Why there, and not in `regen_cards.py` or `build_reference.py` (my decision, open to change):

- It is the tool that reads the game's own control definitions, in about a second. No Markdown in
  between.
- `check` already decides "bound", "cleared" and "game default still live" (its GHOST lines).
  **Both commands must use one function for that**, so the console report and the page cannot
  disagree. Move the logic of `cmd_check` into a function both call; `check`'s output stays as it
  is, byte for byte.
- `build_reference.py` loads the game's whole record database (a minute, 520 MB). This table
  needs two small entries.

`tools/regen_cards.py` calls the same builder at the end of `write_rig()`, after `rig.json` is
written, and prints its one line. So root `CLAUDE.md` §8.3 stays "edit, then
`python tools/regen_cards.py`".

**Without the game** (a clone on another machine): the builder keeps the game part of the
existing `actions.json` (every action's game fields, the groups, `_meta.build`, `_meta.activation`)
and rebuilds the profile and rig parts. It says so on the console ("Data.p4k not found: kept the
game part read from build ..."). With no existing file and no game it stops with a message.
`--check` without the game checks the profile and rig parts only and says that too.

**Writing:** through a temporary file and a rename, as `regen_cards.py`'s `write_atomic` does
(the service or a browser may hold the old file); UTF-8, LF, one action per line so a changed
binding is a one-line diff (the mockup's `dump()` shows the layout). `web/rig/.gitattributes`
already covers `*.json`. A run that changes nothing leaves the file and its `generated` date alone.

### 5.2 What "exists and is not bound" means

Three decisions keep the list useful. All three are tables or rules in the generator.

1. **Scope, by actionmap** (`SCOPE` in the generator; the mockup's `build.py` has the full table):
   - `ship`, the pilot's seat, listed in full: `seat_general`, `spaceship_general`, `vehicle_mfd`,
     `spaceship_view`, `spaceship_movement`, `spaceship_quantum`, `spaceship_docking`,
     `spaceship_targeting`, `spaceship_targeting_advanced`, `spaceship_target_hailing`,
     `spaceship_radar`, `spaceship_scanning`, `spaceship_mining`, `spaceship_salvage`,
     `spaceship_weapons`, `spaceship_missiles`, `spaceship_defensive`, `spaceship_auto_weapons`,
     `spaceship_power`, `spaceship_hud`, `lights_controller`, `vehicle_mobiglas`, `stopwatch`,
     `IFCS_controls`.
   - `seat`, other seats and the camera, listed in full, after the ship groups: `turret_movement`,
     `turret_advanced`, `view_director_mode`.
   - `off`, everything else (on foot, E.V.A., ground vehicles, menus, spectator, tools): **only
     the actions that touch the stick are listed**, which is those the profile clears and those
     whose game joystick default is still live. The rest are counted, not listed.
   - An actionmap of the game that is in none of the three is `new`: listed in full, named in
     `_meta.unsorted`, and the generator prints a warning. A patch that adds an actionmap is
     therefore seen at once and nothing is hidden by default. The test fails while
     `_meta.unsorted` is not empty, which sends the next session to sort it.
2. **Named actions only.** An action with no name in the game's menu is listed only when the
   profile names it or its game joystick default is live. Otherwise it is counted (`hidden`).
3. **Groups are the game's own**, one per actionmap, in the game's order, named by the
   actionmap's `UILabel` ("Flight - Movement"). An actionmap without one keeps its internal name
   and `unnamed: true`.

### 5.3 The file: `dashboard/web/rig/actions.json`, schema 1

About 120 KB. Top level: `_meta`, `scopes`, `groups`.

**`_meta`**

| Field | Type | Meaning | How it is known |
| --- | --- | --- | --- |
| `schema` | int | 1. | Generator. |
| `generated` | `YYYY-MM-DD` | The day a hash last moved. | Generator. |
| `generated_by`, `doc` | string | "tools/gamedata.py actions (do not edit by hand)"; `dashboard/RIG.md`. | Generator. |
| `build` | object | `{version, branch, change, date}` of the build the game part was read from, e.g. `{"version": "4.10.201.48085", "branch": "sc-alpha-4.10.0", "change": "13220821", "date": "Wed Nov 18 2026"}`. | [game] `build_manifest.id`. |
| `previous` | object or null | `{version}` of the build the file was made for before this one; null when there was no earlier file. | The existing file (§5.5). |
| `removed` | list | Actions the earlier build's file listed and this build does not have: `[{group, id, label, state}]`. Empty normally. | The existing file and [game]. |
| `sources` | object | In words, how each kind of fact is known: `game`, `profile`, `rig`, `scope`. The page shows these as the source line's tooltip. | Generator text. |
| `states` | object | The meaning of `bound`, `unbound`, `stock`, `cleared`, one sentence each. | Generator text. |
| `activation` | object | The game's own activation modes: `{name: {press, hold, release, taps, press_after, release_within, words}}`. `words` is one line for the modes whose behavior is understood (`tap`, `press`, `delayed_press` and its kin, `double_tap`, `hold`), with the game's own timings in it ("held for 0.25 s, then it fires once"); an empty string for the rest. | [game] the `ActivationModes` element; the wording [ref] root `CLAUDE.md` §2.3. |
| `hash` | object | 12 hex digits each: `game` (the actionmaps and actions as parsed), `profile` (`MOZA.xml`'s bindings as parsed), `rig` (the parts of `rig.json` used: `maps`, and each row's id, inputs, buttons, unbound flag and modes), `tables` (`SCOPE` and the texts), `code` (the builder's code, the way `rig.json` hashes its own). | Generator. |
| `counts` | object | `groups`, and per scope and in total: `groups`, `actions`, `named`, `listed`, `bound`, `unbound` (listed and not bound), `stock`, `cleared`, `hidden` (no menu name, not listed), `new`. **Define `unbound` over listed actions**; the mockup's file counts hidden ones in it, which is wrong. | Generator. |
| `unsorted` | list of string | Actionmaps not in `SCOPE`. Empty normally. | Generator. |
| `problems` | list | What `check` reports as UNKNOWN, WRONG-MAP or MULTI-BIND, as data: `[{kind: "unknown" or "wrong-map" or "multi-bind", map, action, inputs, defined_in?}]`. Empty normally. After a patch that renames a bound action, this is how the page says so. | `MOZA.xml` against [game]. |

**`scopes[]`**: `{id, name, listed}` for `ship` ("Pilot seat"), `seat` ("Other seats and
cameras"), `new` ("New in this build, not sorted yet"), `off` ("Not for the rig"), in that order.

**`groups[]`**, one per actionmap, in the game's order (all 50, also those with nothing listed):

| Field | Type | Meaning | How it is known |
| --- | --- | --- | --- |
| `id` | string | The actionmap's name: what goes in `<actionmap name="...">`. | [game] |
| `name` | string | The game's menu name for it; the id when it has none (`unnamed: true`). | [game] |
| `scope` | string | `ship`, `seat`, `off` or `new`. | `SCOPE`. |
| `counts` | object | As in `_meta.counts`, for this group. | Generator. |
| `modes` | object or null | `{live, dead, unknown}`: lists of operator mode ids, copied from `rig.json`'s `maps`. **Null when `rig.json` has no entry for the actionmap** (it has entries only for the maps `MOZA.xml` binds in). Absent on `off` groups. | `rig.json`, which rests on quoted sentences of the docs. |
| `room` | object | Which controls could carry an action of this group (§5.4). Absent on `off` groups. | `rig.json`. |
| `actions` | list | The listed actions, in the game's order. | below |

**`groups[].actions[]`**

| Field | Type | Meaning | How it is known |
| --- | --- | --- | --- |
| `id` | string | The action's name: `<action name="...">`. Unique within its group, not across groups (`v_pitch` exists for ships and for ground vehicles). | [game] |
| `label` | string | The game's menu name; the id when it has none (`hidden: true`). | [game] |
| `desc` | string or absent | The game's description, when it has one that is not the label again. | [game] |
| `act` | string | The game's stock activation mode (`tap`, `press`, `delayed_press`, `hold`, `smart_toggle`...), or its trigger flags joined (`press+release`), or `""`. As `gamedata.activation()` gives it. | [game] |
| `kind` | string | `axis` when `act` is empty (no press or release: a button cannot fire it), else `button`. | [game]; the effect [ref]. |
| `keys` | object or absent | The game's stock bindings as its file writes them: `{kb: [...], mouse: [...], pad: [...], js: [...]}`, a key only when non-empty. **Keep keyboard and mouse apart** (the mockup merges them as `kbm` and so writes "Keyboard MOUSE3"). | [game] |
| `state` | string | `bound`, `unbound`, `stock` or `cleared` (`_meta.states`). | `MOZA.xml` and [game], by the function `check` shares. |
| `input` | string | `bound` only: the profile's input, `js2_button57`. | `MOZA.xml`. |
| `mode` | string or absent | `bound` only: the `activationMode` the profile sets, when it sets one. | `MOZA.xml`. |
| `row` | string or absent | `bound` only: the id of the `rig.json` row that carries the input. The generator refuses to write when a bound input has no row (`rig.json` guarantees one). | `rig.json`. |
| `stock` | object | `stock` only: `{input, row?, with?}`: the game's joystick default as it lands on joystick 1 (`js1_button1`), the rig row that sends it (absent when the rig has none, e.g. `js1_hat1_up`), and the `map/action` names the profile binds to the same input. | [game], `rig.json`, `MOZA.xml`. |
| `cleared` | object or absent | `cleared` only: `{input, row?}`: the game default that was removed. | [game], `rig.json`. |
| `new` | `true` or absent | Not in the earlier build's file (§5.5). | The existing file. |
| `hidden` | `true` or absent | No name in the game's menu. | [game] |

Examples, from the mockup's file (2026-11-28):

```json
{"id": "v_ifcs_toggle_esp", "label": "E.S.P. - Toggle On / Off (Press)", "act": "smart_toggle", "kind": "button", "state": "unbound"}
{"id": "v_ifcs_vector_decoupling_toggle", "label": "Enable / Disable decoupled mode", "desc": "Switch between coupled or decoupled mode", "act": "tap", "kind": "button", "keys": {"kb": ["c"], "pad": ["b"]}, "state": "bound", "input": "js2_button57", "row": "js2-57"}
{"id": "v_toggle_landing_system", "label": "Landing System (Toggle)", "act": "tap", "kind": "button", "keys": {"kb": ["n"], "pad": ["dpad_down"], "js": ["button12"]}, "state": "cleared", "cleared": {"input": "js1_button12", "row": "js1-12"}}
{"id": "v_weapon_preset_attack", "label": "Weapon Preset - Fire", "act": "all", "kind": "button", "keys": {"mouse": ["mouse1"], "pad": ["triggerr_btn"], "js": ["button1"]}, "state": "stock", "stock": {"input": "js1_button1", "row": "js1-1", "with": ["spaceship_weapons/v_weapon_preset_fire_guns0", "spaceship_mining/v_toggle_mining_laser_fire", "spaceship_salvage/v_salvage_toggle_fire_focused"]}}
{"id": "v_pitch", "label": "Pitch", "act": "", "kind": "axis", "keys": {"pad": ["thumbry"], "js": ["y"]}, "state": "bound", "input": "js1_y", "row": "js1-y"}
```

A group's head:

```json
{"id": "spaceship_mining", "name": "Vehicles - Mining", "scope": "ship",
 "counts": {"actions": 10, "named": 10, "listed": 10, "bound": 9, "unbound": 1, "stock": 0, "cleared": 0, "hidden": 0, "new": 0},
 "modes": {"live": ["mining"], "dead": ["combat", "missile", "scan", "salvage"], "unknown": []},
 "room": {"known": true,
          "buttons": {"free": ["js1-2", "js1-5", "js1-15", "js1-57-59", "js2-22"], "maybe": [{"row": "js2-7", "modes": ["mining"]}]},
          "axes": {"free": ["js2-z-rz", "js2-dial", "js2-rx"], "maybe": []}}}
```

### 5.4 "Room": which controls could carry an action

Computed per group, from `rig.json` alone, in the generator (so it is tested in Python and the
page only draws it). `buttons` are rows with button numbers, `axes` rows without.

Let *live* be the modes the group is live in and *unknown* the modes the docs leave open
(`groups[].modes`). For each row of `rig.json`:

1. `unbound: true`: **free**. Nothing is bound to it in any mode.
2. The group has no known live mode (`modes` is null, or `live` is empty): stop here. Only rule 1
   applies, `room.known` is false, and `maybe` stays empty. The page says the modes are not
   recorded.
3. The row is `primary` or `variant` in a live mode: busy. Not listed.
4. The row has no `primary` or `variant` cell at all, has `unknown` cells, and every one of them
   is a live mode: busy. It is bound, so it acts somewhere, and wherever it may act the group is
   live. (The star map key against an always-live group.)
5. Otherwise collect the doubt: the live modes where the row is `unknown`, and the group's
   unknown modes where the row is not `none`. No doubt: **free** (idle in every mode the group is
   live in). Some doubt: **maybe**, with those modes named.

What this gave on 2026-11-28: an always-live group (movement, power, view...) has four free
button rows, all with nothing bound (the two base levers, the rocker's rest, the lever detents)
and no bound button that is idle in every mode. *Vehicles - Mining* has 17 bound buttons idle in
Mining mode, the right hat's left direction among them, which is what root `CLAUDE.md` §4 says by
hand. So the answer for ESP is the honest one: the rig has no spare momentary button in every
mode, and the page says exactly that.

**The page must not say more than this.** "Free" on the page is rule 1 or rule 5 with no doubt.
A `maybe` is shown as "not known", with its modes. A group with `room.known` false gets the
sentence "The rig's tables do not say in which operator modes this group is live".

**Deliberately left out:** sharing a press between a tap and a hold. The rig does it three times
(root `CLAUDE.md` §2.3), and it would be the only way to add an always-live action without moving
one. But `rig.json` does not say which controls are momentary: an encoder click cannot be held, a
lever position is held always. A list of "open halves" would include those. And a share changes
how a key the user already uses feels, which is their decision. If it is wanted later, `rig.json`
first needs a physical kind per control.

### 5.5 Staying current after a patch

- **The routine** (root `CLAUDE.md` §7 gains the third line):
  `python tools/gamedata.py check`, `python tools/gamedata.py catalog`,
  `python tools/gamedata.py actions`.
- **What is new in a patch.** When the installed build differs from the build in the existing
  file, the builder compares: an action listed now in a `ship`, `seat` or `new` group that the
  old file did not list in the same group gets `new: true`; one the old file listed and the game
  no longer has goes to `_meta.removed`; `_meta.previous` names the old build. A later run on
  the same build keeps `previous`, `removed` and the `new` flags from the existing file (they
  cannot be recomputed). With no existing file, or one of another schema, there is no `previous`
  and no flag. The flags last until the next build change.
- **The page says when it is out of date.** When `state.session.version` is a non-empty string
  and differs from `_meta.build.version`, the source line turns amber with a triangle and reads
  "Out of date · build 4.10.201.48085", and a notice under the keys says: "The game is now build
  X. This list was read from Y: actions may have been added, renamed or removed since. To
  refresh it: python tools/gamedata.py actions". Nothing else changes: the list is still shown.
- **`--check` in the test suite** when the game is installed (§10).

Whether the service should refresh the file by itself is the user's question 1 (§11). This brief
builds the default: it does not.

### 5.6 Serving

`scdash/server.py`: `RIG_DATA` becomes the two names `rig.json` and `actions.json`, both served as
JSON under `/rig/`, with every rule `rig.json` has today (a plain file, one hard link, the size
limit, the table built once at start). A missing `actions.json` is not an error for the service:
the Controls list works without it. `config.MAX_RIG_FILE_BYTES` (1 MiB) is enough; its comment
says `rig.json` is 12 KB, which is stale (about 90 KB): correct it.

## 6. The page

All of it is inside the Find page of the Rig reference (`web/app.js`, the `rig*` code;
`web/style.css`). The head (tabs, key, mode filter) does not change: its row is full at 1140 px
and at 1920 px **[seen 2026-11-28, captures of the built page]**, which is one reason this is not
a ninth tab. The other: the user asked for it as part of Find, and one search box then covers
both lists.

`actions.json` is fetched the first time the Actions list or a bridge (§6.5) needs it
(`cache: "no-cache"`), never before, and nothing here runs on the tick. A failed fetch or another
schema shows "The game's actions could not be loaded", the reason and a "Try again" button in
place of the list; the Controls list is untouched.

### 6.1 Find's bar

```
[ search box, as today ] [ CONTROLS 96 | ACTIONS 431 ]                 hint, right-aligned
```

- A two-button switch (`.seg`), 50 px high like the search box, 18 px capitals, the count in
  lighter weight after each name; the pressed one cyan with a 3 px cyan line under it, the same
  pressed look as the mode filter. `aria-pressed` on both. Counts: the rig's rows, and the
  named pilot-seat actions (`counts.scopes.ship.listed`).
- The hint reads "Click a row to see it on its diagram" on Controls and "Click an action to open
  it" on Actions. The search box's placeholder: "A number or a word" and "A word, or a button
  number".
- The choice is kept while the reference stays mounted, with the page, filter and open row
  (§ "The rig reference" in [`../../CLAUDE.md`](../../CLAUDE.md)). The typed text is kept across
  the switch.

### 6.2 The Actions list

```
[ALL 431][▮ BOUND 120][┄ NOT BOUND 309][GAME DEFAULT LIVE 1][CLEARED 1]      Game files · build 4.10.201.48085
┌ rail ───────────────────────┐ ┌ list ────────────────────────────────────────────┐
│ PILOT SEAT · BOUND / ALL    │ │ FLIGHT - MOVEMENT  27 OF 103 BOUND   Live in every operator mode │
│ All groups        120 / 431 │ │ BOUND · 27                                        │
│ Vehicles - Seats…   8 / 28  │ │ [ Y ] Pitch  Stick · Stick forward / back         │
│ Flight - Movement  27 / 103 │ │ [57 ] Enable / Disable decoupled mode [TAP] Throttle · COM hat press  ○ │
│ …                           │ │ NOT BOUND · 75                                    │
│ OTHER SEATS AND CAMERAS     │ │ [ – ] E.S.P. - Toggle On / Off (Press)            │
│ NOT FOR THE RIG             │ │ [ – ] Toggle VTOL  Keyboard K                     │
└─────────────────────────────┘ └───────────────────────────────────────────────────┘
```

**The state keys** (`.akey`, 40 px high, joined like the mode filter): All, Bound, Not bound,
Game default live, Cleared, and "New in this build" only when the count is not zero. Bound and
Not bound carry a small swatch of their badge (22 x 14 px: filled, and dashed outline). One is
pressed at a time; it filters the list. The counts are for what is in view: the chosen scope, or
the matches when text is typed.

**The source line**, right of the keys: "Game files · build 4.10.201.48085", 18 px condensed,
quiet. Its tooltip is `_meta.sources.game`. Out of date: §5.5. If `_meta.problems` is not empty,
one red notice per problem under the keys, with the octagon: "MOZA.xml binds js2 button9 to
spaceship_movement / v_x, which this build of the game does not have. That binding is dead."

**The rail** (`.rail`), the game's groups, left: 348 px wide (330 in portrait; 420 and 380 with
the terminal off), its own scroll, a hairline on its right.

- A caption, "Pilot seat · bound / all", then "All groups", then every `ship` group that lists
  an action, in the game's order; a caption "Other seats and cameras" and the `seat` and `new`
  groups; a caption "Not for the rig" and one entry, "On foot, ground, menus", with the number of
  actions listed there.
- An entry (`.rail__b`) is 30 px high (34 and 36 with the terminal off), 18 px condensed: the
  name, cut with an ellipsis and whole in its tooltip, and "27 / 103" right-aligned in tabular
  figures. A 2 px bar along its foot is filled to the bound share (`--fill`, set from script with
  `style.setProperty`, the page's rule for meters). The chosen one: white, a 3 px cyan line at
  its left, its count and bar cyan. `aria-current`.
- With text typed, the caption reads "Matches", each count is the number of matches in that
  group, groups with none are dimmed, and the list shows the matches of every group.
- Under the Mining or Salvage filter, a group the docs call dead in that mode is dimmed (its
  name in the third text color). Unknown or unrecorded is never dimmed. Under Flight a group is
  dimmed only when it is dead in all three of combat, missile and scan.
- The chosen entry is kept in sight when the rail scrolls. At 1920 x 1080 with the terminal on
  the rail holds about 21 of its 29 lines and scrolls; in portrait it holds all of them
  **[seen in the captures]**.

**The list**, right, in the page's `.rows` / `.rows__scroll` with the "More below" tag.

- Per group a heading (`.find__sec`): the game's name, then "27 of 103 bound" in cyan, then at
  the right the modes line in plain case: "Live in every operator mode", "Live in Mining", "Live
  in Combat · not known: Missile, Scan", "Operator modes not known" (no live mode on record), or
  "Operator modes not recorded" (`modes` null). It wraps under the name when the list is narrow.
- Then one section per state that has rows, in this order, each with a caption and its count:
  "Bound · 27", "Not bound · 75", "Game default still live · 1", "Game default cleared · 1".
  Rows keep the game's order inside a section.
- One column of rows; two from a list width of 1040 px (a container query on the list, so the
  terminal's state needs no rule of its own). The page's own rule gives Find's lists two or three
  columns; an action's name is longer than a control's job, so this list overrides it.
- "All groups" shows every pilot-seat group, one after another.
- "On foot, ground, menus" opens with one paragraph: "On foot, E.V.A., ground vehicles, menus
  and spectator: 23 groups, 538 actions. The rig is used only in ships, so only the 38 that touch
  the stick are listed: 9 game defaults the profile clears and 29 it leaves live." Its group
  headings read "Ground Vehicle - Movement · 5 of 20 listed" and have no modes line.

### 6.3 An action's row

The page's own row (`li.rr`), with these parts:

| State | Badge (`.rr__n`) | Name | Hint (`.rr__h`) | Mark |
| --- | --- | --- | --- | --- |
| bound | The control's label as the diagram prints it ("57", "RY", "Slider"), the page's filled badge. | The game's label. | The device and where the control is: "Throttle · COM hat press". | The control's flown, unverified or trial mark for this job (below). |
| not bound | An en dash in a dashed outline, the look an unbound control has today. | The game's label, in the normal text color: these rows are the point of the list. | The game's keyboard or mouse default when it has one: "Keyboard C", "Mouse 3". Nothing otherwise. | none |
| game default live | The label of the control that sends the default, in an outlined (not filled) badge; "js1" when the rig has no such control. | The game's label. | "game default, still live · Stick · Trigger". | none |
| cleared | An x in a quiet outline. | The game's label, in the third text color. | "game default removed · Stick 12 · Right hat ↑". | none |

- **Always name the device in the hint.** "4" is a stick button and a throttle key; the badge
  alone cannot tell them apart.
- Tags after the name, the page's `.rr__tag`: "tap" or "hold" when the control is a tap / hold
  key (`rig.json` `jobs`), "hold" when the profile sets `delayed_press`, "New" in cyan for
  `new`, "no menu name" for `hidden`.
- **The mark of a bound action** is the status of its own job in `rig.json`: the job in `jobs`
  that names the action; else the variant whose mode is the action's `part` in the row's
  `actions`; else the row's status. No status there, no mark.
- The name is one line, cut with an ellipsis, whole in the tooltip and whole when opened.
- Pointing lights the row; nothing else moves.

### 6.4 An opened action

A click opens the row in place (a second click closes it; one open at a time). The opened row
takes the whole width of the list when the list has two columns (`column-span: all`). It adds
lines in the page's `.rr__v` form, a 7.2 em caption column and the text:

| Caption | Text | Source |
| --- | --- | --- |
| What | The game's description, or "The game gives no description" in the quiet color. | [game] |
| Press | The activation mode's name and its wording: "delayed_press: held for 0.25 s, then it fires once"; the name alone when `_meta.activation` has no wording; for `kind: "axis"`: "An axis: the game gives it no press or release, so a button cannot fire it". After it, when the profile sets a mode: " · the profile sets delayed_press". | [game], `MOZA.xml` |
| Game default | "keyboard C · gamepad b · joystick button12", or "none on any device". | [game] |
| Name | `spaceship_movement / v_ifcs_toggle_esp` in the terminal's type face, 18 px: what goes into `MOZA.xml`. | [game] |
| On the rig | Bound, or a game default that is live: the control as a chip (below). For a live default with `stock.with`: "MOZA.xml binds 3 actions to the same input. Both fire where both groups are live." | `rig.json`, `MOZA.xml` |
| Room | Not bound only. One sentence, then up to three lines of chips. | `room` |

**Room**, for an action that is not bound. Use `room.axes` when the action's `kind` is `axis`,
else `room.buttons`; say "axis" or "button" accordingly.

- The sentence: "This group is live in every operator mode, so a control has to do nothing in
  all five." or "This group is live in Mining mode." (with " (not known: Missile, Scan)" when
  the group has unknown modes) or "The rig's tables do not say in which operator modes this
  group is live, so only a control with nothing bound is sure."
- "17 idle there": the free rows that are bound elsewhere, as chips. For an always-live group
  the line reads "Idle: No bound button is idle in every mode", quiet. Left out when `room.known`
  is false.
- "4 unbound": the free rows with nothing bound, one chip per line, each with the row's own text
  after it ("Left "Slider" lever, reserved", "Power rocker at rest", "Reverse thrust axes, not
  output by the device"), because that text is why the control is empty.
- "3 not known": the `maybe` rows, each followed by "in Mining" (its doubtful modes).

A chip (`.rchip`): 30 px high, the control's label in a filled box, then where it is; its tooltip
is the device, the page and the control's job. In the Room lines chips are grouped by device, with the
device's name as a small caption before each run, always (a bound action's one chip needs none:
its row's hint names the device). A click on a chip goes to that control's page with
the row open, exactly as a click on a Find row does today.

A bound action's row also goes there when its chip is clicked. The row itself only opens.

### 6.5 The bridge from Controls

On the Controls list, when text is typed and `actions.json` is loaded or can be loaded: after the
control matches (or after "Nothing on the rig matches ..."), a heading in the lead style, "The
game's actions · 4 match · 4 not bound", with a "Show in Actions" button at its right, and up to
eight matching action rows under it, each with its group's name first in the hint. "Show in
Actions" switches the list and keeps the text. Typing "esp" is the case to try: no control, four
actions.

Search on Actions: every word must occur in the action's label, internal name, description,
group name, or, when bound, its control's label, place and group. A number therefore finds the
actions bound to that button.

### 6.6 States to build

| State | What is shown |
| --- | --- |
| Loading | "Loading the game's actions…" in the list's place. |
| Failed, or schema not 1 | The failure pane (§6), Controls untouched. |
| A group with nothing in the chosen state | "Nothing in this group is cleared", in the page's empty-result style. |
| No match | "No action of the game matches "zzzz"". |
| Out of date, problems | §5.5, §6.2. |
| `_meta.unsorted` not empty | The `new` groups are in the rail under "Other seats and cameras", tagged "New"; no banner. |
| `_meta.removed` not empty | A quiet line at the foot of "All groups": "Gone since build X: N actions", their labels in its tooltip. |
| The longest names | "Vehicles - Multi Function Displays (MFDs)" in the rail (cut, tooltip); "Y Offset Negative / Spectator Freecam Focal Point Backward" as a row (cut, whole when opened). |
| Narrow (the view under 860 px) | The rail goes above the list as a scrolling strip at most five entries high, and the section scrolls as the rest of the reference does there. **Not mocked up**: build it, capture it, and say so in the report. |

### 6.7 Measurements, from the mockup

The mockup's `actions.css` is the reference; every size in it is 18 px or more and it has no
inline style. The numbers that matter:

| Part | Size |
| --- | --- |
| Switch button | 50 px high, 18 px side padding (14 in portrait), 18 px capitals, letter-spacing .1em |
| State key | 40 px high, 14 px side padding (10 in portrait); swatch 22 x 14 px |
| Rail | 348 px (portrait 330; terminal off: landscape 420, portrait 380); entry 30 px (34 / 36 terminal off); bar 2 px |
| Gap rail to list | 16 px (12 portrait, 24 landscape terminal off) |
| List columns | 1; 2 from 1040 px of list width |
| Caption column of an opened row | 7.2 em |
| Chip | 30 px high, label box at least 40 px wide |
| Type | the reference's own tokens: 18 px captions and hints, 21 px row names (26 px with the terminal off), nothing smaller |

Colors are the page's tokens only. No new color: bound is the page's filled badge, not bound its
dashed outline, amber and red appear only with their triangle and octagon and a sentence.

## 7. What happens when something fails

| Failure | Result |
| --- | --- |
| No `Data.p4k`, an existing file | The game part is kept, the rest rebuilt, a line on the console. |
| No `Data.p4k`, no file | The command stops with a message; `regen_cards.py` prints it and goes on (the cards and `rig.json` do not depend on it). |
| `rig.json` missing or not schema 2 | The command stops with a message and writes nothing. |
| A bound input with no rig row | The command stops and names the input: `rig.json` is stale; run `regen_cards.py`. |
| The profile names an action the game does not have | Written, with a `problems` entry; the page shows it in red; `check` still exits non-zero as today. |
| The file is held by the service | Retried for about two seconds, as `write_atomic` does. |
| `actions.json` absent, damaged or another schema | The Actions list shows its failure pane; everything else works. |
| An action row names a rig row the page's `rig.json` does not have (the two files out of step) | The row is drawn with its input ("js2 button57") in the outlined badge and no chip; nothing throws. |

## 8. Rules that are easy to break

- **One function decides bound, cleared and live default**, for `check` and for the table.
- **The page computes no "room".** It draws `room`. A row id it cannot find is left out.
- **Never the word "free" for a `maybe`,** and never a room list when `room.known` is false
  except the unbound controls.
- **Every text from either file goes in as a text node.** Action names come from the game's
  files; treat them as hostile anyway.
- **No inline style, no outside resource, nothing under 18 px, nothing on the tick, no fetch
  before the list is first wanted.**
- **Do not reword the game's labels.** Controls rows have screen wording written by hand; action
  rows show the game's own label, so the user can find it in the game's menu.
- **`check`'s console output does not change.**
- **The mockup is not the implementation.** `mock.js` is a throwaway that draws the head by
  hand and the Controls list plainly. Take the design from this file and `actions.css`.

## 9. The mockup

`dashboard/data/design/actions/` (git-ignored). Real data, the page's own stylesheet (a copy)
plus `actions.css`, one screen per address.

- `build.py`: the prototype generator. **The reference for the shapes and for the room rule.**
  Known differences from this brief: `keys.kbm` instead of `kb` and `mouse`; `counts.unbound`
  counts hidden actions; no `hash.code`, `removed`, `hidden` count, `new` logic or no-game path.
- `index.html`, `mock.js`, `actions.css`, `page.css`, `actions.json`, `rig.js`.
- `shoot.py`: headless Edge with a profile of its own in the temp folder, the page as a file,
  no port, no window. 19 screens, each at 1920 x 1080 and 1080 x 1920, terminal on and off:
  76 captures in `shots/`.

Looked at by the designer (2026-11-28): `01_movement_L-on`, `03_open_esp_L-on`,
`03_open_esp_P-on`, `04_open_mining_L-off`, `05_open_bound_L-on` (the last round),
`06_all_groups_P-off`, `08_off_L-on`, `08_off_P-off`, `10_controls_q_esp_L-on`,
`20_demo_stale_L-on`; all but `05` in the round before the device names went into the hints.
**Captured but not looked at:** the rest, among them the Mining filter (`23`), the axis action
(`13`), targeting with "not known" chips (`14`) and the "new" and "problem" demos (`21`, `22`). The three `demo` screens use invented states (a newer game
build, three actions flagged new, one dead binding); everything else is the real data of that
morning.

## 10. Tests

`dashboard/tests/test_actions.py` (new), `test_server.py`, `test_page_rig.py`,
`test_page_static.py`. Each of these must be able to fail; name the mutation that proves it in
the report.

**The data, without the game** (always run):

1. Every `<action>` of `MOZA.xml` is in the file, in its actionmap's group, `bound` with the same
   input and mode, or `cleared`. A binding changed in a copy of the profile makes it fail.
2. Every `bound` action has a `row`, and that row of `rig.json` lists the input. Every `row`,
   every id in `room` and in `stock` / `cleared` exists in `rig.json`.
3. `hash.profile` and `hash.rig` are what the builder computes from today's files (so a stale
   file fails until regenerated).
4. Counts add up: per group and per scope, `listed = bound + unbound + stock + cleared`; the
   totals are the sums; `_meta.unsorted` and `_meta.problems` are empty.
5. The room rule on built cases, one per rule of §5.4: a made-up `rig.json` with an unbound row,
   a row live in the group's mode, a row unknown everywhere against an always-live group (busy)
   and against a one-mode group (maybe), a row idle in the group's modes (free), a group with no
   known mode (`known` false, `maybe` empty).
6. `room` in the file is what the rule gives from today's `rig.json`, for every group.
7. No `off` group lists an `unbound` action; no listed action without a menu name is `unbound`.
8. The no-game path: with the p4k path pointed at nothing, the builder reproduces the committed
   file byte for byte.
9. The patch path, on built inputs: an old file for build A, a game part for build B with one
   action added and one removed gives `previous`, one `new`, one `removed`; a second run on B
   keeps all three.

**The data, with the game** (skipped with a printed line when `Data.p4k` is not there):

10. `gamedata.py actions --check` exits 0: the committed file is byte for byte what the builder
    makes today.
11. `check`'s output on the real profile is unchanged from before the refactor (keep a copy of
    the old output in the test's notes and compare the lines).

**The service:** `/rig/actions.json` is served with the JSON type and the common headers; a
missing file is a 404 and no warning at start; the name rule still refuses `other.json`.

**The page** (the browser tests' `Scene`): the switch shows both counts and the Actions list;
the keys filter; the rail's counts equal the file's; a bound action's badge is its rig row's
label and its chip opens that row's page; an opened unbound action of an always-live group shows
the unbound chips and the sentence "No bound button is idle in every mode"; a `maybe` row is
under "not known" and never under "idle"; typing "esp" on Controls shows the bridge; a
`state.session.version` other than the file's shows the out-of-date notice; a file of schema 2
shows the failure pane and leaves Controls working; nothing under 18 px and no inline style in
any of these states (the measuring the rig captures already do).

**How it will be attacked.** A reviewer should try first: a label with markup in it; `rig.json`
and `actions.json` from different commits; a profile with an action in the wrong map and one
bound twice; an actionmap the scope table does not know; a group whose every mode is unknown; the
no-game path after a binding change; a 1 MiB file; and whether any test still passes with the
room rule's step 4 removed.

## 11. The user's decisions

| # | Question | Recommendation first | The other options and what they cost | Answer |
| --- | --- | --- | --- | --- |
| 1 | After a game patch, who refreshes the list? | **A session does, as part of the patch routine, and the page says when it is out of date.** One command; the same way the dashboard's other game tables are kept. The patch routine has to run anyway to check `MOZA.xml` against the new build. | *The dashboard refreshes it by itself when it sees a new build.* Always current with no session, which is closest to "always updated". It costs a second, git-ignored copy of the file that the service prefers over the tracked one, a child process started by the service, and the zstd package as something the service needs. | open |
| 2 | Which groups count as "for the rig"? | **The pilot's seat in full (24 actionmaps, 431 named actions); turret seats and the advanced camera in full but after them; everything else only where it touches the stick.** | *Pilot seat only:* shorter, and the two turret defaults that are live on the stick would move to the "not for the rig" list. *Everything the game has:* 753 named actions, 264 of them on foot, in menus and in ground vehicles. | open |
| 3 | Where does it live? | **Inside Find, as a second list** (Controls / Actions). It is what was asked for, one search box covers both, and the tab row has no room left. | *A ninth tab, "Actions".* One click from any page instead of two. It needs the head laid out again at both widths: the tab row is full, and at 1920 px the key already sits under the Find tab in a capture of the built page. | open |

Decisions the designer made, open to change: the generator's place (`gamedata.py`); the room
rule; no tap / hold suggestions; "New in this build" flags; device names in every hint; the
game's labels unworded.

## 12. Stages

Two Workers, one after the other. Neither commits.

### Stage A: the data

- **Goal:** `python tools/gamedata.py actions` and `--check`; `dashboard/web/rig/actions.json`;
  the service serves it; its schema in `dashboard/RIG.md`; tests 1 to 11 and the service's.
- **Read first:** this file §3 to §5, §7, §8, §10; `tools/gamedata.py`; the mockup's `build.py`;
  [`../../RIG.md`](../../RIG.md); `tools/regen_cards.py` `write_atomic`, `write_rig`, `rig_code`,
  `canon`; `scdash/server.py` `rig_files()`.
- **Owns:** `tools/gamedata.py`; `dashboard/web/rig/actions.json`; `dashboard/tests/test_actions.py`;
  the `/rig/` part of `scdash/server.py` and `tests/test_server.py`; a new section "actions.json"
  in `dashboard/RIG.md`; the call in `tools/regen_cards.py` `write_rig()`; the lines in
  `tools/README.md`, `tools/CLAUDE.md`, `dashboard/CLAUDE.md` (module map, "The rig files") and
  root `CLAUDE.md` §7, §8.3, §8.5 and §10.3 that name the new command. Ask the lead before
  touching `regen_cards.py` or root `CLAUDE.md`: other agents edit them.
- **Does not touch:** `MOZA.xml`, `rig.json`, `web/app.js`, `web/style.css`, the cards.
- **Done when:** the suite passes; `gamedata.py actions --check` exits 0 and exits 1 after a
  binding is changed in a scratch copy of the profile; `gamedata.py check` prints what it printed
  before; a second `actions` run rewrites nothing; `curl` to a test instance returns the file;
  the counts in the file match §3 or the report says why they moved.
- **Report:** the counts, the mutations each test caught, what differs from this brief and why.

### Stage B: the page

- **Goal:** §6, in `web/app.js` and `web/style.css`, with the page tests, captures of every state
  of §6.6 in both orientations with the terminal on and off, and the doc text for
  `dashboard/CLAUDE.md` ("The rig reference").
- **Read first:** this file §4, §6 to §8, §10; the mockup's `actions.css` and nine captures named
  in §9; `web/app.js` from "the rig reference" to `RENDERERS`; the `rig` rules of `web/style.css`;
  `dashboard/data/handoff/session4/views-rig/cap_rig.py` for the capture method.
- **Owns:** the rig section of `web/app.js` and of `web/style.css`; `tests/test_page_rig.py`,
  the rig cases of `tests/test_page_static.py` and `tests/test_page_browser.py`.
- **Does not touch:** the data, the service, the head of the reference, the live views.
- **Done when:** the page tests pass; the captures exist and were looked at; the measuring finds
  no type under 18 px, no inline style and no overflow of the view in any captured state; the
  Controls list behaves as before with `actions.json` removed.
- **Report:** the captures to look at first, what was not built as written and why, what no real
  pointer has touched.

## 13. Considered and rejected

- **Building the table from the Markdown catalog** in `reference/`. It is a rendering for people;
  its reader in `regen_cards.py` drops a row with a pipe in it; and the user asked for the
  game's files.
- **Putting it in `build_reference.py`.** A full run loads the game's record database: a minute
  and 520 MB for a table that needs a second.
- **A ninth tab.** §11 question 3.
- **Listing all 1,104 actions.** 351 have no menu name and 538 are outside a ship's seats.
- **Interleaving bound and not bound in the game's order.** The user asked to see "clearly"
  which is which; two sections per group do that, and the keys reduce it to one.
- **Rewording the game's labels for the screen,** as the Controls rows are. 431 hand-written
  lines to keep true after every patch, and the label is what the game's menu shows.
- **Tap / hold sharing suggestions.** §5.4.
- **A hand-kept note per action** ("left unbound on purpose: ESP stays on in the settings").
  Useful, but it is a second place for what root `CLAUDE.md` §4 and §6 already say. A
  suggestion for later, if the user wants the reasons on the page.
- **The service regenerating the file by itself.** §11 question 1: the user's call.
