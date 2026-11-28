# Actions in the rig reference: what is bound and what is not

The implementer's brief for one feature of the dashboard's Rig reference section
([`../../PLAN.md`](../../PLAN.md) §4 item 20). Written 2026-11-28 by the feature's designer, and
revised the same morning after the user answered its three questions (§11). A Worker builds from
this file; a reviewer checks the build against it.

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
- **Every named action of the game**, in every group (the user: "scope i think should be
  everything honestly"). On foot, in ground vehicles and in menus the user plays on a gamepad and
  the rig binds nothing, by design ([`../../../CLAUDE.md`](../../../CLAUDE.md) §1). Those groups
  are in the list, marked as such. This is a view of the whole game, not a plan to bind them.
- Read from **the installed game's files**. No web site, no community database, no API.
- **Kept current by the dashboard's service itself, when it starts** (the user: "i want the
  service to refresh it by itself and not rely on a claude session running externally"; and "it
  only needs to refresh itself when it first starts up").
- For a ship action that is not bound, **which controls of the rig have room for it**, as far as
  the rig's own tables know. The user decides what to bind next from this.

It is not a binding editor. Nothing on the page changes `MOZA.xml`. It does not advise what to
bind.

## 2. Where it stands

- **Designed and mocked up, not built.** The mockup runs on real data and was captured in both
  orientations, terminal region on and off (§9). The user saw the first round's captures: "those
  images look ok". No real pointer has touched it and it has not been seen on the 15.6 inch
  panel.
- **The user's three answers are in** (§11) and this brief is written to them.
- **Build order:** stage A (the builder and its command), stage B (the service's start-up step),
  stage C (the page). §12 has the three briefs.

## 3. The facts it rests on

| Fact | How it is known |
| --- | --- |
| The game defines 1,104 actions in 50 actionmaps. Each actionmap carries the name the Keybindings menu shows for it (`UILabel`: "Flight - Movement", "Vehicles - Weapons", "On Foot - All"...), non-empty for 40 of the 50. 753 actions have a name of their own in the English text (794 carry a name key; 41 of those resolve to nothing); the other 351 are not shown in the game's menu. | [game] `defaultProfile.xml` and `global.ini` in `Data.p4k`, build 4.10.201.48085, read 2026-11-28 with `tools/gamedata.py`'s loader. |
| The actionmap's second attribute, `UICategory` (FLIGHT, ON FOOT, Vehicle, CAMERA), is empty for the seat, turret and lights maps. It cannot decide what belongs to a ship. | [game], same read. |
| `MOZA.xml` named 131 actions: 119 bound, 12 cleared. All 119 bound ones are in ship actionmaps. | [seen 2026-11-28, 11:19 AM, after that morning's binding change; an hour earlier it was 120 and 10] |
| Named actions by where they belong: 431 in the 24 ship actionmaps (119 bound, 308 not bound, 3 cleared, 1 with the game's joystick default still live, *Weapon Preset - Fire*); 58 in the turret and camera maps (2 live defaults, the turret's pitch and yaw); 264 on foot, in ground vehicles, menus and spectator (0 bound). 16 actions without a menu name also touch the stick (a cleared or live default), so 769 are listed. | [game] + `MOZA.xml`, the mockup's generator, 11:19 AM. |
| An action holds one joystick input. A rebind in the profile replaces the game's joystick default; an action the profile never names keeps that default, live on joystick 1. | [ref] root `CLAUDE.md` §2.5, proven there by the game's export. |
| An action with no activation mode and no press, hold or release trigger in the game's file is axis-only: a button bound to it never fires. | [game] for the attribute; [ref] root `CLAUDE.md` §6 item 24 for the effect (one flight report, `v_strafe_longitudinal`). |
| `rig.json` says, for 18 actionmaps, in which operator modes the map is live, dead or not known, and for each of the 96 controls what it does in each mode, with `"unknown"` cells. Six controls have nothing bound: the two base levers, the power rocker's rest position, the lever detents, and two throttle axes. | [seen] `dashboard/web/rig/rig.json` schema 2, 2026-11-28; [`../../RIG.md`](../../RIG.md). |
| Reading the two game files takes 0.31 s (wall and CPU). With today's loader the process peaks at 524 MB, because it holds the archive's whole central directory, which is 454 MB. Reading that directory in 8 MB pieces finds the same two entries in the same 0.31 s with a peak of 58 MB. `defaultProfile.xml` is 184 KB unpacked and `global.ini` 10.7 MB; both are zstd-packed. | [seen 2026-11-28, 11:14 AM, this PC, the file cache warm, three runs. Not measured: a cold cache, and with the game loading at the same moment.] |
| This PC's Python is 3.12.10. It has no `compression.zstd` (that is in 3.14 and later). The `zstandard` package, 0.25.0, is installed; `tools/requirements.txt` lists it. | [seen 2026-11-28] |
| The page already receives the running game's version: `state.session.version` is the log's `FileVersion:` line, the same string as `Version` in the game's `build_manifest.id`. | [seen] `scdash/state.py`, `tests/samples/*.log`. |
| The service serves from `web/rig/` exactly `rig.json` and the images; each file at most 1 MiB. It refuses changes until the log has been read once (`_first_read_done`). It knows the repo's root (`config.REPO_ROOT`) and the game's `LIVE` folder. | [seen] `scdash/server.py`, `scdash/service.py`, `scdash/config.py`. |
| `tools/regen_cards.py`'s `read_catalog()` splits the catalog's Markdown rows on `\|` and skips a row that does not give six cells. No name holds a pipe today. | [seen] the code; [game] the count. The reason the new table is not built on the Markdown catalog. |

**Not checked:** whether an action without a menu name can be bound through the profile file;
what `smart_toggle`, `hold_toggle` and `all` do exactly (the page shows those names unworded);
which Python the logon task starts the service with, and whether that one has `zstandard`.

## 4. The design in one page

- **One builder, two ways to run it.** `python tools/gamedata.py actions` reads the game's files,
  `MOZA.xml` and `rig.json` and writes the list. The dashboard's service runs that same command
  as a child process, as one step of its start-up, when the list is missing or was built from
  other inputs. A session and the tests run it by hand.
- **The list lives in the service's data folder,** `dashboard/data/rig/actions.json`,
  git-ignored. There is no tracked copy: one file, one truth.
- **A normal start costs five file stats.** A rebuild happens only after a game patch, a binding
  change, a change of the rig data or of the builder. It runs after the service is up, in a
  child process with a time limit, so it cannot delay the log or the page.
- **A failure keeps the last good list** and the page says what failed.
- **Page:** the Find page gets a two-way switch, **Controls** (the 96, as today) and **Actions**
  (the game's list). Actions has a rail of the game's groups in three parts: in a ship, other
  seats and cameras, and on the gamepad (collapsed at first). Rows read like control rows the
  other way around: the action's name first, the control's number in the badge.
- **From an action to a control:** an opened ship action that is not bound shows "Room": the
  controls with nothing bound, and the controls that are idle in the modes the action's group is
  live in. A click on one opens that control on its diagram page.
- **From a word to an action:** typing "esp" on Controls finds no control and then lists the
  game's actions that match.
- **Honesty:** every fact carries its source; where the rig's tables do not know, the page says
  "not known" and never "free".

## 5. The data

### 5.1 The builder and its command

`tools/gamedata.py` gets a third command beside `check` and `catalog`.

```
python tools/gamedata.py actions            write dashboard/data/rig/actions.json
python tools/gamedata.py actions --check    build in memory, say what would change, write nothing; exit 1 if it would change
        --p4k <Data.p4k>   --mapping <MOZA.xml>   --rig <rig.json>   --out <file>
```

- **Why there** (the designer's decision): it is the tool that reads the game's own control
  definitions. `check` already decides "bound", "cleared" and "game default still live" (its
  GHOST lines). **Both commands must use one function for that**, so the console report and the
  page cannot disagree. `check`'s output stays as it is, byte for byte.
- **A pure core.** `build_actions(game, profile, rig, previous)` takes the parsed game part, the
  profile's bindings, `rig.json` as a dict and the existing list (or none), and returns the
  document. It opens no file. The command and the tests wrap it. This is what lets the tests run
  without the game.
- **The archive's directory is read in pieces.** Today `read_central_directory()` returns all
  454 MB of it. Change the loader to walk it in pieces of `CD_CHUNK` (8 MB) with an overlap, and
  stop when both entries are found, so the process stays near 60 MB (§3). `check` and `catalog`
  get the same loader and print what they printed before.
- **Exit codes, so the service can say what failed without parsing text:** 0 written or
  unchanged; 1 `--check` found a difference; 2 `Data.p4k` not found and no existing list to keep
  the game part of; 3 no zstd decoder; 4 `rig.json` missing or not schema 2; 5 the profile could
  not be read; 6 anything else. The last line on stderr says it in words.
- **Without the game** (a clone on another machine, or the archive locked): the builder keeps
  the game part of the existing list (every action's game fields, the groups, `_meta.build`,
  `_meta.activation`) and rebuilds the profile and rig parts. It says so on the console and sets
  `_meta.game_read` to false. With no existing list and no game: exit 2.
- **Writing:** through a temporary file in the same folder and a rename, retried for about two
  seconds while a reader holds the old file, as `regen_cards.py`'s `write_atomic` does. UTF-8,
  LF, one action per line (the mockup's `dump()` shows the layout). A run that changes nothing
  leaves the file and its `generated` date alone. Temporary files a killed run left are swept at
  the next run.
- `tools/regen_cards.py` is not touched. It does not call the builder.

### 5.2 What is listed, and how it is sorted

1. **Every action that has a name in the game's menu, in every actionmap.** An action with no
   menu name is listed only when it touches the stick: the profile names it, or its game
   joystick default is live. The rest are counted (`hidden`).
2. **Groups are the game's own**, one per actionmap, in the game's order, named by the
   actionmap's `UILabel` ("Flight - Movement"). An actionmap without one keeps its internal name
   and `unnamed: true`. Four actionmaps share the name "On Foot - All"; the page tells them apart
   by adding the internal name (§6.2).
3. **Where a group belongs** (`SCOPE` in the builder; the mockup's `build.py` has the full
   table). It no longer decides what is listed. It decides which part of the rail a group is in,
   how its rows are marked, and whether "Room" is worked out:
   - `ship`, the pilot's seat: `seat_general`, `spaceship_general`, `vehicle_mfd`,
     `spaceship_view`, `spaceship_movement`, `spaceship_quantum`, `spaceship_docking`,
     `spaceship_targeting`, `spaceship_targeting_advanced`, `spaceship_target_hailing`,
     `spaceship_radar`, `spaceship_scanning`, `spaceship_mining`, `spaceship_salvage`,
     `spaceship_weapons`, `spaceship_missiles`, `spaceship_defensive`, `spaceship_auto_weapons`,
     `spaceship_power`, `spaceship_hud`, `lights_controller`, `vehicle_mobiglas`, `stopwatch`,
     `IFCS_controls`.
   - `seat`, other seats and the camera: `turret_movement`, `turret_advanced`,
     `view_director_mode`.
   - `off`, everything else: on foot, E.V.A., ground vehicles, menus, spectator, tools. Played on
     the gamepad; the rig binds nothing there by design.
   - An actionmap of the game that is in none of the three is `new`: shown with the `seat`
     groups, tagged, named in `_meta.unsorted`, and the builder prints a warning. A patch that
     adds an actionmap is therefore seen at once.

### 5.3 The file: `dashboard/data/rig/actions.json`, schema 1

About 155 KB today. Top level: `_meta`, `scopes`, `groups`.

**`_meta`**

| Field | Type | Meaning | How it is known |
| --- | --- | --- | --- |
| `schema` | int | 1. | Builder. |
| `generated` | `YYYY-MM-DD` | The day a hash last moved. | Builder. |
| `generated_by`, `doc` | string | "tools/gamedata.py actions (do not edit by hand)"; `dashboard/RIG.md`. | Builder. |
| `build` | object | `{version, branch, change, date}` of the build the game part was read from, e.g. `{"version": "4.10.201.48085", "branch": "sc-alpha-4.10.0", "change": "13220821", "date": "Wed Nov 18 2026"}`. | [game] `build_manifest.id`. |
| `game_read` | bool | True when this run read the game's files; false when it kept the game part of the list before it. | Builder. |
| `previous` | object or null | `{version}` of the build the list was made for before this one; null when there was no earlier list. | The existing list (§5.5). |
| `removed` | list | Actions the earlier build's list held and this build does not have: `[{group, id, label, state}]`. Empty normally. | The existing list and [game]. |
| `sources` | object | In words, how each kind of fact is known: `game`, `profile`, `rig`, `scope`. The page shows `game` as the source line's tooltip. | Builder text. |
| `states` | object | The meaning of `bound`, `unbound`, `stock`, `cleared`, one sentence each. | Builder text. |
| `activation` | object | The game's own activation modes: `{name: {press, hold, release, taps, press_after, release_within, words}}`. `words` is one line for the modes whose behavior is understood (`tap`, `press`, `delayed_press` and its kin, `double_tap`, `hold`), with the game's own timings in it ("held for 0.25 s, then it fires once"); an empty string for the rest. | [game] the `ActivationModes` element; the wording [ref] root `CLAUDE.md` §2.3. |
| `hash` | object | 12 hex digits each: `game` (the actionmaps and actions as parsed), `profile` (`MOZA.xml`'s bindings as parsed), `rig` (the parts of `rig.json` used: `maps`, and each row's id, inputs, buttons, unbound flag and modes), `tables` (`SCOPE` and the texts), `code` (the builder's code, the way `rig.json` hashes its own). | Builder. |
| `counts` | object | `groups`, and per scope and in total: `groups`, `actions`, `named`, `listed`, `bound`, `unbound` (listed and not bound), `stock`, `cleared`, `hidden` (no menu name, not listed), `new`. **Define `unbound` over listed actions**; the mockup's file counts hidden ones in it, which is wrong. | Builder. |
| `unsorted` | list of string | Actionmaps not in `SCOPE`. Empty normally. | Builder. |
| `problems` | list | What `check` reports as UNKNOWN, WRONG-MAP or MULTI-BIND, and a bound input no row of `rig.json` carries, as data: `[{kind: "unknown" or "wrong-map" or "multi-bind" or "no-row", map, action, inputs, defined_in?}]`. Empty normally. After a patch that renames a bound action, this is how the page says so. | `MOZA.xml` against [game] and `rig.json`. |

**`scopes[]`**: `{id, name}` for `ship` ("In a ship"), `seat` ("Other seats and cameras"), `new`
("New in this build, not sorted yet"), `off` ("On foot, ground, menus"), in that order.

**`groups[]`**, one per actionmap, in the game's order (all 50, also those with nothing listed):

| Field | Type | Meaning | How it is known |
| --- | --- | --- | --- |
| `id` | string | The actionmap's name: what goes in `<actionmap name="...">`. | [game] |
| `name` | string | The game's menu name for it; the id when it has none (`unnamed: true`). | [game] |
| `scope` | string | `ship`, `seat`, `off` or `new`. | `SCOPE`. |
| `counts` | object | As in `_meta.counts`, for this group. | Builder. |
| `modes` | object or null | `{live, dead, unknown}`: lists of operator mode ids, copied from `rig.json`'s `maps`. **Null when `rig.json` has no entry for the actionmap** (it has entries only for the maps `MOZA.xml` binds in). Absent on `off` groups. | `rig.json`, which rests on quoted sentences of the docs. |
| `room` | object | Which controls could carry an action of this group (§5.4). **Absent on `off` groups:** no room is looked for where the rig binds nothing by design. | `rig.json`. |
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
| `row` | string or absent | `bound` only: the id of the `rig.json` row that carries the input. Absent when no row does: the list is still written, with a `no-row` entry in `_meta.problems` (the two files are out of step; `regen_cards.py` puts it right). | `rig.json`. |
| `stock` | object | `stock` only: `{input, row?, with?}`: the game's joystick default as it lands on joystick 1 (`js1_button1`), the rig row that sends it (absent when the rig has none, e.g. `js1_hat1_up`), and the `map/action` names the profile binds to the same input. | [game], `rig.json`, `MOZA.xml`. |
| `cleared` | object or absent | `cleared` only: `{input, row?}`: the game default that was removed. | [game], `rig.json`. |
| `new` | `true` or absent | Not in the earlier build's list (§5.5). | The existing list. |
| `hidden` | `true` or absent | No name in the game's menu. | [game] |

Examples, from the mockup's file (2026-11-28, before that morning's binding change):

```json
{"id": "v_ifcs_toggle_esp", "label": "E.S.P. - Toggle On / Off (Press)", "act": "smart_toggle", "kind": "button", "state": "unbound"}
{"id": "v_autoland", "label": "Autoland", "desc": "Activate Autoland", "act": "delayed_press", "kind": "button", "keys": {"kb": ["n"], "pad": ["dpad_down"], "js": ["button12"]}, "state": "bound", "input": "js2_button10", "row": "js2-10"}
{"id": "v_toggle_landing_system", "label": "Landing System (Toggle)", "act": "tap", "kind": "button", "keys": {"kb": ["n"], "pad": ["dpad_down"], "js": ["button12"]}, "state": "cleared", "cleared": {"input": "js1_button12", "row": "js1-12"}}
{"id": "v_weapon_preset_attack", "label": "Weapon Preset - Fire", "act": "all", "kind": "button", "keys": {"mouse": ["mouse1"], "pad": ["triggerr_btn"], "js": ["button1"]}, "state": "stock", "stock": {"input": "js1_button1", "row": "js1-1", "with": ["spaceship_weapons/v_weapon_preset_fire_guns0", "spaceship_mining/v_toggle_mining_laser_fire", "spaceship_salvage/v_salvage_toggle_fire_focused"]}}
{"id": "v_pitch", "label": "Pitch", "act": "", "kind": "axis", "keys": {"pad": ["thumbry"], "js": ["y"]}, "state": "bound", "input": "js1_y", "row": "js1-y"}
{"id": "moveforward", "label": "Move Forward", "act": "press+release", "kind": "button", "keys": {"kb": ["w"]}, "state": "unbound"}
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

Computed per group, from `rig.json` alone, in the builder (so it is tested in Python and the
page only draws it). `buttons` are rows with button numbers, `axes` rows without. **Not computed
for `off` groups.**

Let *live* be the modes the group is live in and *unknown* the modes the docs leave open
(`groups[].modes`). For each row of `rig.json`:

1. `unbound: true`: **free**. Nothing is bound to it in any mode.
2. The group has no known live mode (`modes` is null, or `live` is empty): stop here. Only rule 1
   applies, `room.known` is false, and `maybe` stays empty. This is the case for every actionmap
   the rig data knows nothing about: the MFDs, target hailing, the stop watch, the turret and
   camera maps, and any `new` one.
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
sentence "The rig's tables do not say in which operator modes this group is live". An `off`
group gets "Not looked for" (§6.4).

**Deliberately left out:** sharing a press between a tap and a hold. The rig does it three times
(root `CLAUDE.md` §2.3), and it would be the only way to add an always-live action without moving
one. But `rig.json` does not say which controls are momentary: an encoder click cannot be held, a
lever position is held always. A list of "open halves" would include those. And a share changes
how a key the user already uses feels, which is their decision. If it is wanted later, `rig.json`
first needs a physical kind per control.

### 5.5 Staying current: one step of the service's start-up

The user, 2026-11-28: "i want the service to refresh it by itself and not rely on a claude
session running externally", and then: "it only needs to refresh itself when it first starts up,
which is a small CPU penalty as it checks to make sure it has latest and correct bindings and
all that, which is a good thing i think as part of its start up routine".

So the service checks the list **once, at start**, and nothing watches for changes while it
runs. A new module, `scdash/actions.py`, holds the step; it uses the standard library only.

**What it checks.** Five files: the game's `build_manifest.id`, the profile
(`config.REPO_ROOT / "MOZA.xml"`), the rig data (`web/rig/rig.json`), the builder
(`tools/gamedata.py`) and the list itself (`data/rig/actions.json`). Beside the list sits a small
record of the last check, `data/rig/actions.state.json`:

```json
{"schema": 1, "checked": "2026-11-28T19:19:05Z", "result": "built", "code": 0, "took_ms": 640,
 "list": {"size": 153201, "mtime_ns": 1795979945000000000, "build": "4.10.201.48085", "generated": "2026-11-28"},
 "inputs": {"manifest": [431, 1795900000000000000], "profile": [41872, 1795979000000000000],
            "rig": [91544, 1795978000000000000], "builder": [24310, 1795970000000000000]}}
```

(each input as size and modification time; no path is stored).

**The rule.**

1. The record exists with schema 1, the list is there with the recorded size and time, and each
   of the four inputs has its recorded size and time: **keep the list**. A normal start ends
   here, after five stats and one read of a file under 1 KB.
2. Anything else (no record, no list, any size or time different): **build**, by running the
   builder as a child process (below).
3. Then write the record: the result, the exit code, the time it took, and the sizes and times
   as they are now. After a failure the `list` part still describes the list that is on disk,
   if there is one, and the inputs are recorded as they were at the last success, so the next
   start tries again.

A file whose time changed and whose content did not (a fresh checkout) costs one build, under a
second. That is accepted in place of hashing four files at every start.

**How the build runs.**

- **When:** after the HTTP server is listening and the log has been read once
  (`_first_read_done`), so it cannot delay the first request or the first read. If the first
  read has not finished 30 s after start, the step runs anyway.
- **Where:** a daemon thread (`scdash-actions`) does the stats and waits for the child. It never
  holds the service's lock while it waits; it takes it only to store the small result.
- **The child:** `[sys.executable, <REPO_ROOT>/tools/gamedata.py, "actions", "--p4k",
  <LIVE>/Data.p4k, "--mapping", <REPO_ROOT>/MOZA.xml, "--rig", <web>/rig/rig.json, "--out",
  <data>/rig/actions.json]`, no shell, `stdin` closed, `stdout` and `stderr` to pipes of which
  the last 2 KB are kept for the service's log, `CREATE_NO_WINDOW` and
  `BELOW_NORMAL_PRIORITY_CLASS` on Windows, the repo root as its folder. Not `python -I`: the
  zstd package may be in the user's site folder.
- **Why a child and not the service's own code:** the read's memory (about 60 MB, 524 MB if the
  directory were not read in pieces) never enters the service; a time limit can end it; its
  parsing does not hold the service's interpreter; and the service itself imports nothing
  outside the standard library.
- **Bounded:** `ACTIONS_BUILD_SECONDS` = 30 in `config.py`; past it the child is killed and the
  result is `timeout`. One build per start, never a retry loop. A stop of the service kills a
  running child and does not wait for it longer than the stop's own bound.
- **Read-only toward the game:** the child opens `Data.p4k` and `build_manifest.id` for reading
  and writes only under `data/rig/`.
- **Measured** (§3): 0.31 s for the game read on a warm cache, 58 MB with the directory read in
  pieces. **The Worker measures the whole child** (wall time and peak working set, from the
  service's side) four ways: warm and cold cache (cold: the first run after a restart of
  Windows), game not running and game running in the PU. Targets: under 3 s and under 100 MB in
  all four. The figures go into `dashboard/CLAUDE.md` with their date. If the cold run with the
  game loading is over 3 s, say so in the report: the 30 s limit still holds.

**The zstd decoder.** Both game files are zstd-packed. The service stays standard-library; the
child needs a decoder: `compression.zstd` on Python 3.14 and later, else the `zstandard`
package. This PC's Python is 3.12.10 with `zstandard` installed **[seen]**. With neither, the
child exits 3 and the page says "Python has no zstd decoder (install the zstandard package)".
The Worker checks that the interpreter the service is started with can import one, and says
which in the report. A decoder written in Python was considered and rejected (§13).

**What the service tells the page.** The message's `service` block gains `actions`:

```json
{"state": "ready", "rev": 2, "has_list": true, "build": "4.10.201.48085", "generated": "2026-11-28", "reason": null}
```

| Field | Values |
| --- | --- |
| `state` | `checking` (start-up, the step has not finished), `building` (the child is running), `ready` (kept or built), `failed` (the build failed or timed out). |
| `rev` | An integer that goes up each time the list on disk was replaced. The page fetches the list again when it differs from the `rev` it fetched under. |
| `has_list` | Whether a list is on disk (after a failure: the last good one). |
| `build`, `generated` | The list's own, from the record; null without a list. |
| `reason` | With `failed`, one of a fixed set of words: `no-game`, `no-zstd`, `no-rig`, `no-profile`, `no-builder`, `timeout`, `error`. The page turns each into a sentence. **No path and no text of the child reaches the page;** its last lines go to the service's log. |

A change of this block makes one message go out, like any other change. `STATE.md` gets the block.

**What is new in a patch.** When the installed build differs from the build in the existing
list, the builder compares: a named action listed now that the old list did not have in the same
group gets `new: true`; one the old list had and the game no longer has goes to `_meta.removed`;
`_meta.previous` names the old build. A later run on the same build keeps `previous`, `removed`
and the `new` flags from the existing list (they cannot be recomputed). With no existing list,
or one of another schema, there is no `previous` and no flag. The flags last until the next
build change.

**What "at start only" means in practice.** The service starts at logon. A game patch installed
while the PC stays on is picked up at the next start of the service, not before. Until then the
page says so: it compares `state.session.version` (the running game, from the log) with the
list's build, and when they differ it shows "The game is now build X. This list was read from
build Y. It is checked again when the dashboard's service next starts." The same holds for a
binding change made while the service runs: after `python tools/regen_cards.py`, restart the
service (`python dashboard/scdash.py stop`, then `start`); the page reloads itself when the
service does. A session may instead run `python tools/gamedata.py actions` by hand, which writes
the same file; the page then shows it after its next reload.

### 5.6 Serving

`scdash/server.py`: `/rig/actions.json` is served from the data folder
(`<data>/rig/actions.json`), as JSON, with every rule `rig.json` has (a plain file, one hard
link, the size limit, read from disk at each request). **Its entry is in the table whether or
not the file exists when the server is made**, because the start-up step may write it a moment
later; a request before that gets a 404. `data/rig/actions.state.json` is never served.
`config.MAX_RIG_FILE_BYTES` (1 MiB) is enough; its comment says `rig.json` is 12 KB, which is
stale (about 90 KB): correct it.

## 6. The page

All of it is inside the Find page of the Rig reference (`web/app.js`, the `rig*` code;
`web/style.css`). The user: "yes agree inside of Find is perfect". The head (tabs, key, mode
filter) does not change.

The list is fetched the first time the Actions list or a bridge (§6.5) needs it
(`cache: "no-cache"`), and again when `service.actions.rev` has changed since; never before, and
nothing here runs on the tick.

### 6.1 Find's bar

```
[ search box, as today ] [ CONTROLS 96 | ACTIONS 753 ]                 hint, right-aligned
```

- A two-button switch (`.seg`), 50 px high like the search box, 18 px capitals, the count in
  lighter weight after each name; the pressed one cyan with a 3 px cyan line under it, the same
  pressed look as the mode filter. `aria-pressed` on both. Counts: the rig's rows, and every
  named action of the game (`counts.total.named`). Until the list is loaded the second count is
  left out.
- The hint reads "Click a row to see it on its diagram" on Controls and "Click an action to open
  it" on Actions. The search box's placeholder: "A number or a word" and "A word, or a button
  number".
- The choice is kept while the reference stays mounted, with the page, filter and open row
  (§ "The rig reference" in [`../../CLAUDE.md`](../../CLAUDE.md)). The typed text is kept across
  the switch.

### 6.2 The Actions list

```
[ALL 431][▮ BOUND 119][┄ NOT BOUND 308][GAME DEFAULT LIVE 1][CLEARED 3]      Game files · build 4.10.201.48085
┌ rail ───────────────────────┐ ┌ list ────────────────────────────────────────────┐
│ IN A SHIP · BOUND / ALL     │ │ FLIGHT - MOVEMENT  26 OF 103 BOUND   Live in every operator mode │
│ All ship groups   119 / 431 │ │ BOUND · 26                                        │
│ Vehicles - Seats…   8 / 28  │ │ [ Y ] Pitch  Stick · Stick forward / back         │
│ Flight - Movement  26 / 103 │ │ [10 ] Autoland [HOLD] Throttle · AP key        ✓  │
│ …                           │ │ NOT BOUND · 75                                    │
│ OTHER SEATS AND CAMERAS     │ │ [ – ] E.S.P. - Toggle On / Off (Press)            │
│ ON THE GAMEPAD, NOT THE RIG │ │ [ – ] Toggle VTOL  Keyboard K                     │
│ On foot, ground, menus  280 │ │                                                   │
│ ⌄ Show its 15 groups        │ │                                                   │
└─────────────────────────────┘ └───────────────────────────────────────────────────┘
```

**It opens on "All ship groups", key All,** the first time. After that it keeps what was chosen.

**The state keys** (`.akey`, 40 px high, joined like the mode filter): All, Bound, Not bound,
Game default live, Cleared, and "New in this build" only when the count is not zero. Bound and
Not bound carry a small swatch of their badge (22 x 14 px: filled, and dashed outline). One is
pressed at a time; it filters the list. **The counts are for what is in view:** the chosen group
or part, or the matches when text is typed.

**The source line**, right of the keys: "Game files · build 4.10.201.48085", 18 px condensed,
quiet. Its tooltip is `_meta.sources.game` and the day the list was built. The other states of
this line and the notices under the keys are in §6.6.

**The rail** (`.rail`), the game's groups, left: 348 px wide (330 in portrait; 420 and 380 with
the terminal off), its own scroll, a hairline on its right. Three parts, each under a caption:

1. "In a ship · bound / all": "All ship groups", then every `ship` group that lists an action,
   in the game's order (21 today).
2. "Other seats and cameras": the `seat` groups, and any `new` one with a "New" tag.
3. "On the gamepad, not the rig": one entry, "On foot, ground, menus", with the number of
   actions there (280 today), and under it a quiet line with a chevron, "Show its 15 groups".
   **The 15 groups are folded away at first.** A click on that line unfolds them (and it then
   reads "Hide its 15 groups"); choosing one of them, or typing in the search box, unfolds them
   too. The fold is kept like the rest of the section's state.

- An entry (`.rail__b`) is 30 px high (34 and 36 with the terminal off), 18 px condensed: the
  name, cut with an ellipsis and whole in its tooltip, and a count right-aligned in tabular
  figures: "26 / 103" (bound of all listed) in parts 1 and 2, the number of actions alone in
  part 3, where nothing is bound by design. In parts 1 and 2 a 2 px bar along the entry's foot
  is filled to the bound share (`--fill`, set from script with `style.setProperty`, the page's
  rule for meters). The chosen one: white, a 3 px cyan line at its left, its count and bar cyan.
  `aria-current`.
- **Groups that share a menu name show the internal name after it:** "On Foot - All · player",
  "On Foot - All · prone". A group with no menu name shows its internal name alone ("mining").
- With text typed, the first caption reads "Matches", each count is the number of matches in
  that group, groups with none are dimmed, part 3 is unfolded, and the list shows the matches of
  every group in all three parts.
- Under the Mining or Salvage filter, a `ship` group the docs call dead in that mode is dimmed
  (its name in the third text color). Unknown or unrecorded is never dimmed. Under Flight a
  group is dimmed only when it is dead in all three of combat, missile and scan.
- The chosen entry is kept in sight when the rail scrolls. With part 3 folded the rail has 30
  lines. With the terminal on it holds about 21 of them in landscape and about 23 in portrait,
  and scrolls; in portrait with the terminal off it holds all 30. Unfolded it has 45 and scrolls
  in every layout **[seen in the captures; the unfolded rail with the terminal off was not
  looked at]**.

**The list**, right, in the page's `.rows` / `.rows__scroll` with the "More below" tag.

- Per group a heading (`.find__sec`): the game's name (with the internal name where it is
  shared), then a count in cyan, then at the right a line in plain case. It wraps under the name
  when the list is narrow.
  - `ship`, `seat`, `new`: "26 of 103 bound", and the modes line: "Live in every operator mode",
    "Live in Mining", "Live in Combat · not known: Missile, Scan", "Operator modes not known"
    (no live mode on record), or "Operator modes not recorded" (`modes` null).
  - `off`: "78 actions", with " · 2 touch the stick" when some do, and the line "On the gamepad:
    the rig binds nothing here".
- Then one section per state that has rows, each with a caption and its count. In a `ship` or
  `seat` group, in this order: "Bound · 26", "Not bound · 75", "Game default still live",
  "Game default cleared · 2" (Flight - Movement's figures; a section with no row is left out).
  In an `off` group the two that touch the stick come first: "Game default
  cleared", "Game default still live", then "Not bound". Rows keep the game's order inside a
  section.
- One column of rows; two from a list width of 1040 px (a container query on the list, so the
  terminal's state needs no rule of its own). The page's own rule gives Find's lists two or three
  columns; an action's name is longer than a control's job, so this list overrides it.
- "All ship groups" shows every `ship` group, one after another. "On foot, ground, menus" shows
  every `off` group, after one paragraph: "On foot, E.V.A., ground vehicles, menus and spectator
  are played on the gamepad: the rig binds nothing there, by design. They are listed so the
  whole game is in one place: 280 actions in 15 groups. 38 of them touch the stick: 9 game
  defaults the profile clears and 29 it leaves live."

### 6.3 An action's row

The page's own row (`li.rr`), with these parts:

| State | Badge (`.rr__n`) | Name | Hint (`.rr__h`) | Mark |
| --- | --- | --- | --- | --- |
| bound | The control's label as the diagram prints it ("57", "RY", "Slider"), the page's filled badge. | The game's label. | The device and where the control is: "Throttle · AP key". | The control's flown, unverified or trial mark for this job (below). |
| not bound, in a ship or seat group | An en dash in a dashed outline, the look an unbound control has today. | The game's label, in the normal text color: these rows are the point of the list. | The game's keyboard or mouse default when it has one: "Keyboard C", "Mouse 3". Nothing otherwise. | none |
| not bound, in an `off` group | The same dash, its outline in the quieter line color. | The game's label in the second text color: readable, and plainly not a candidate. | As above. | none |
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

**Room**, for an action that is not bound.

- **In an `off` group:** one quiet sentence and nothing else: "Not looked for. The rig is used
  only in ships; this group is played on the gamepad."
- **Otherwise** use `room.axes` when the action's `kind` is `axis`, else `room.buttons`, and say
  "axis" or "button" accordingly.
  - The sentence: "This group is live in every operator mode, so a control has to do nothing in
    all five." or "This group is live in Mining mode." (with " (not known: Missile, Scan)" when
    the group has unknown modes) or, when `room.known` is false, "The rig's tables do not say in
    which operator modes this group is live, so only a control with nothing bound is sure."
  - "17 idle there": the free rows that are bound elsewhere, as chips. For an always-live group
    the line reads "Idle: No bound button is idle in every mode", quiet. Left out when
    `room.known` is false.
  - "4 unbound": the free rows with nothing bound, one chip per line, each with the row's own
    text after it ("Left "Slider" lever, reserved", "Power rocker at rest", "Reverse thrust
    axes, not output by the device"), because that text is why the control is empty.
  - "3 not known": the `maybe` rows, each followed by "in Mining" (its doubtful modes).

A chip (`.rchip`): 30 px high, the control's label in a filled box, then where it is; its tooltip
is the device, the page and the control's job. In the Room lines chips are grouped by device,
with the device's name as a small caption before each run, always (a bound action's one chip
needs none: its row's hint names the device). A click on a chip goes to that control's page with
the row open, exactly as a click on a Find row does today.

A bound action's row also goes there when its chip is clicked. The row itself only opens.

### 6.5 The bridge from Controls

On the Controls list, when text is typed and the list is loaded or can be loaded: after the
control matches (or after "Nothing on the rig matches ..."), a heading in the lead style, "The
game's actions · 4 match · 4 not bound", with a "Show in Actions" button at its right, and up to
eight matching action rows under it, each with its group's name first in the hint. `ship` and
`seat` matches come before `off` ones. "Show in Actions" switches the list and keeps the text.
Typing "esp" is the case to try: no control, four actions.

Search on Actions: every word must occur in the action's label, internal name, description,
group name, or, when bound, its control's label, place and group. A number therefore finds the
actions bound to that button. It searches all three parts of the rail.

### 6.6 States to build

The list's own states, from `service.actions` (§5.5) and the fetch:

| `service.actions` | The list | What is shown |
| --- | --- | --- |
| `checking` or `building` | none yet (`has_list` false) | In the list's place: "Reading the game's actions…". The Controls list works. |
| `checking` or `building` | one on disk | That list, and the source line reads "Checking against the game's files…". When `rev` changes the list is fetched again and redrawn, keeping the group, key, text and open row where they still exist. |
| `ready` | fetched, schema 1 | The list; "Game files · build X". |
| `failed` | one on disk | The list, the source line amber with a triangle, "Not checked · build X", and a notice under the keys: "The list could not be checked when the dashboard started: *sentence*. This is the list read from build X on *date*." |
| `failed` | none | In the list's place, a pane: "The game's actions could not be read", the sentence, and "It is tried again when the dashboard's service next starts." No button: the page cannot start the step. |
| any | the fetch failed, or the file is not schema 1 | The same pane with "the list could not be loaded" and the page's "Try again" button, which fetches again. |
| `service.actions` absent (an older service) | whatever the fetch gives | As `ready` or as the failed fetch. |

The sentences for `reason`: `no-game` "Data.p4k was not found"; `no-zstd` "Python has no zstd
decoder (install the zstandard package)"; `no-rig` "the rig reference's data is missing or of
another version"; `no-profile` "MOZA.xml could not be read"; `no-builder` "tools/gamedata.py was
not found"; `timeout` "reading the game's files took longer than 30 seconds and was stopped";
`error` "the reader failed; the service's log has the detail".

Other states:

| State | What is shown |
| --- | --- |
| The running game is another build than the list (`state.session.version` is a non-empty string and differs from `_meta.build.version`) | The source line amber with a triangle, "Out of date · build Y", and the notice: "The game is now build X. This list was read from build Y: actions may have been added, renamed or removed since. It is checked again when the dashboard's service next starts." The list is still shown. |
| `_meta.problems` not empty | One red notice per problem under the keys, with the octagon: "MOZA.xml binds js2 button9 to spaceship_movement / v_x, which this build of the game does not have. That binding is dead." For `no-row`: "... which the rig reference has no control for: its data is older than the profile." |
| `_meta.game_read` false | The source line reads "Game files · build X · kept" and its tooltip says the game's files were not read at the last build. |
| A group with nothing in the chosen state | "Nothing in this group is cleared", in the page's empty-result style. |
| No match | "No action of the game matches "zzzz"". |
| `_meta.unsorted` not empty | The `new` groups are in the rail's second part, tagged "New"; no banner. |
| `_meta.removed` not empty | A quiet line at the foot of "All ship groups": "Gone since build X: N actions", their labels in its tooltip. |
| The longest names | "Vehicles - Multi Function Displays (MFDs)" and "Quick Keys, Interactions, and Inner Thought" in the rail (cut, tooltip); "Y Offset Negative / Spectator Freecam Focal Point Backward" as a row (cut, whole when opened). |
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
| No `Data.p4k`, a list on disk | The game part is kept, the rest rebuilt, `game_read` false; exit 0. |
| No `Data.p4k`, no list | Exit 2; the service reports `failed`, `no-game`; the page's pane. |
| No zstd decoder | Exit 3; `failed`, `no-zstd`; the last good list stays. |
| `rig.json` missing or not schema 2 | Exit 4; `failed`, `no-rig`; the last good list stays. |
| The profile cannot be read | Exit 5; `failed`, `no-profile`; the last good list stays. |
| A bound input with no rig row | Written, with a `no-row` problem; the page shows the action with its input in the outlined badge and a red notice. |
| The profile names an action the game does not have | Written, with a `problems` entry; the page shows it in red; `check` still exits non-zero as today. |
| The child runs past 30 s | Killed; `failed`, `timeout`; the last good list stays (the child writes through a temporary file, so a kill leaves no half-written list). |
| The child cannot be started, or `tools/gamedata.py` is not there | `failed`, `no-builder` or `error`. |
| The record `actions.state.json` is damaged | Treated as absent: one build. |
| The list on disk is damaged or another schema | The record does not match it, so one build; if that fails, the page's failed-fetch pane. |
| The list is held by a reader while it is replaced | Retried for about two seconds, as `write_atomic` does. |
| The service is stopped while the child runs | The child is killed; the stop is not held up. |
| An action row names a rig row the page's `rig.json` does not have | The row is drawn with its input ("js2 button57") in the outlined badge and no chip; nothing throws. |

## 8. Rules that are easy to break

- **One function decides bound, cleared and live default**, for `check` and for the list.
- **The service imports nothing new.** `scdash/actions.py` uses the standard library; the game's
  files are read only in the child.
- **The step never runs on the main loop's thread, never holds the service's lock while the
  child runs, and never runs twice in one start.**
- **Nothing is written outside `data/rig/`,** and nothing at all toward the game.
- **No path and no child output in the message to the page:** fixed reason words only.
- **The page computes no "room".** It draws `room`. A row id it cannot find is left out.
- **Never the word "free" for a `maybe`,** never a room list when `room.known` is false except
  the unbound controls, and no room at all for an `off` group.
- **An `off` row is never styled as a candidate,** and the text never suggests binding it.
- **Every text from the list goes in as a text node.** Action names come from the game's files;
  treat them as hostile anyway.
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

- `build.py`: the prototype builder. **The reference for the shapes and for the room rule.**
  Known differences from this brief: `keys.kbm` instead of `kb` and `mouse`; `counts.unbound`
  counts hidden actions; `room` is present on `off` groups; it loads the whole directory; no
  `hash.code`, `removed`, `game_read`, `hidden` count, `no-row` problem, `new` logic or no-game
  path; `scopes[].listed` is a leftover.
- `index.html`, `mock.js`, `actions.css`, `page.css`, `actions.json`, `rig.js`.
- `shoot.py`: headless Edge with a profile of its own in the temp folder, the page as a file,
  no port, no window. 23 screens, each at 1920 x 1080 and 1080 x 1920, terminal on and off:
  92 captures in `shots/`.

**Two rounds.** Screens `01` to `23` were captured before the user's answers, with the pilot
seat as the scope: their rail's third part is one line, their switch says "Actions 431", and
their counts are from before that morning's binding change (120 bound). Screens `30` to `33`
were captured after, with every named action: `30_everything` (the default view, part 3 folded),
`31_off_open` (part 3 unfolded, all gamepad groups), `32_off_group` (one gamepad group, an
action opened), `33_q_wave` (a search that only matches an emote).

Looked at by the designer: first round `01_movement_L-on`, `03_open_esp_L-on`,
`03_open_esp_P-on`, `04_open_mining_L-off`, `05_open_bound_L-on`, `06_all_groups_P-off`,
`08_off_L-on`, `08_off_P-off`, `10_controls_q_esp_L-on`, `20_demo_stale_L-on`; second round
`30_everything_P-off`, `31_off_open_L-on`, `31_off_open_P-on`. **Captured but not looked at:**
the rest, among them `32`, `33`, the Mining filter (`23`), the axis action (`13`), targeting
with "not known" chips (`14`) and the "new" and "problem" demos (`21`, `22`). **Not mocked up:**
the states of §6.6's first table (reading, checking, not checked, could not be read), the
"Hide its 15 groups" wording, and the narrow layout. The three `demo` screens use invented
states; everything else is the real data of that morning.

## 10. Tests

`dashboard/tests/test_actions.py` (the builder), `test_actions_step.py` (the service's step),
`test_server.py`, `test_page_rig.py`, `test_page_static.py`. Each of these must be able to
fail; name the mutation that proves it in the report. No test depends on a tracked list: there
is none.

**The builder, without the game** (always run), on a small game part kept in
`tests/samples/actions_game.json` (invented: a few groups of each scope, named and unnamed
actions, axis-only ones, joystick defaults) with a built profile and a built `rig.json`:

1. States: a bound action is `bound` with the profile's input and mode; a cleared one `cleared`
   with the default that was removed; an unnamed one with a joystick default `stock`; the rest
   `unbound`. A second rebind on one action makes a `multi-bind` problem and the last one wins.
2. What is listed: every named action of every scope, `off` included; an unnamed action only
   when it is not `unbound`.
3. Counts add up: per group, per scope and in total, `listed = bound + unbound + stock +
   cleared`, `named + hidden-or-listed-unnamed = actions`.
4. The room rule, one case per rule of §5.4: an unbound row; a row live in the group's mode; a
   row unknown everywhere against an always-live group (busy) and against a one-mode group
   (maybe); a row idle in the group's modes (free); a group with no known mode (`known` false,
   `maybe` empty); no `room` on an `off` group.
5. `row` is the rig row that lists the input; a bound input no row lists gives a `no-row`
   problem and still a list.
6. An actionmap not in `SCOPE` is `new` and in `_meta.unsorted`.
7. The patch path: an old list for build A, a game part for build B with one action added and
   one removed gives `previous`, one `new`, one `removed`; a second run on B keeps all three.
8. The no-game path: with no game part given and an existing list, the result has the same game
   fields, `game_read` false, and the new profile's states.
9. Deterministic: two builds of the same inputs give the same bytes; a build over its own output
   rewrites nothing.
10. On the real `MOZA.xml` and `rig.json` of the checkout with the sample game part: every
    `<action>` of the profile the sample knows comes out with its input.

**The builder, with the game** (skipped with a printed line when `Data.p4k` is not there):

11. A full build into a temporary folder succeeds, has no `unsorted` and no `problems`, and
    every `<action>` of `MOZA.xml` is in it, in its actionmap's group, with its input.
12. `gamedata.py actions --check` against that build exits 0, and 1 after a binding is changed
    in a copy of the profile.
13. `check`'s output on the real profile is the same before and after the refactor (keep the
    old output with the test and compare the lines).
14. The loader never asks the archive for more than `CD_CHUNK` bytes of the directory in one
    read (a file object that records its reads), and `check` and `catalog` still find both
    entries.

**The service's step** (`scdash/actions.py`, with a stand-in for the child: a small script the
test passes in place of `tools/gamedata.py`):

15. Record and list as recorded, inputs unchanged: no child is started, state `ready`.
16. No record; no list; an input's size changed; an input's time changed; the list's size
    changed: each starts exactly one child.
17. A child that exits 0 and writes a list: `ready`, `rev` one higher, the record written with
    the new sizes and times.
18. A child that exits 2, 3, 4, 5, 6: `failed` with the matching reason, the old list byte for
    byte as it was, `has_list` true, the record's inputs unchanged so the next start builds.
19. A child that sleeps past the limit (the limit set to 1 s in the test) is killed, `timeout`,
    and no child process is left behind.
20. A stop of the service while the child runs ends the child and returns within the stop's
    bound.
21. The step starts only after the first read, or after its 30 s; the routes answer while a
    slow child runs (a request during the child's sleep gets its answer).
22. The message carries `service.actions`, and nothing in it holds a path or the child's text
    (a child that prints a path and the user name on stderr; search the message for both).
23. A damaged record is treated as absent.

**The server:** `/rig/actions.json` is a 404 before the file exists and is served with the JSON
type and the common headers after it appears, with no restart; `/rig/actions.state.json` is a
404 always; the name rule still refuses `other.json`.

**The page** (the browser tests' `Scene`, with a list built from the sample game part):

- the switch shows both counts and the Actions list; it opens on "All ship groups";
- the keys filter and count what is in view;
- the rail's counts equal the file's; part 3 is folded at first, unfolds on a click, on choosing
  one of its groups and on typing;
- two groups with one menu name show their internal names;
- a bound action's badge is its rig row's label and its chip opens that row's page;
- an opened unbound action of an always-live group shows the unbound chips and "No bound button
  is idle in every mode"; a `maybe` row is under "not known" and never under "idle";
- an opened `off` action shows "Not looked for" and no chip;
- typing "esp" on Controls shows the bridge;
- each row of §6.6's first table: `checking` without a list, `building` with one, `ready`,
  `failed` with a list (the notice and the sentence for each reason), `failed` without;
- a `rev` that goes up makes the page fetch again and keeps the chosen group;
- a `state.session.version` other than the list's build shows the out-of-date notice;
- a list of schema 2 shows the failed-fetch pane and leaves Controls working;
- nothing under 18 px and no inline style in any of these states (the measuring the rig
  captures already do).

**How it will be attacked.** A reviewer should try first: a label with markup in it; `rig.json`
and the list from different commits; a profile with an action in the wrong map and one bound
twice; an actionmap the scope table does not know; a group whose every mode is unknown; the
record edited so it matches a list that is damaged; a child that writes a huge list (over
1 MiB), that never exits, that exits 0 without writing; two services started at once on one
data folder; `Data.p4k` replaced by a 10-byte file; and whether any test still passes with the
room rule's step 4 removed, with the kill at the time limit removed, or with the step moved
onto the main thread.

## 11. The user's decisions

Answered on 2026-11-28, at about 11:15 AM, with a follow-up a few minutes later.

| # | Question | The user's answer | What was recommended, and what the answer costs |
| --- | --- | --- | --- |
| 1 | After a game patch, who refreshes the list? | **The service, by itself, when it starts:** "i want the service to refresh it by itself and not rely on a claude session running externally". Then: "it only needs to refresh itself when it first starts up, which is a small CPU penalty as it checks to make sure it has latest and correct bindings and all that, which is a good thing i think as part of its start up routine". | Recommended: a session does it in the patch routine. The answer costs a child process at start (only when something changed), the zstd package where Python is older than 3.14, and one consequence: a patch installed while the PC stays on is picked up at the service's next start, and the page says so until then (§5.5). |
| 2 | Which groups are in the list? | **Everything:** "scope i think should be everything honestly". | Recommended: the pilot's seat in full and the rest only where it touches the stick. The answer makes the list 769 rows instead of 527; the gamepad groups are folded away at first and marked as outside what the rig binds (§6.2). |
| 3 | Where does it live? | **Inside Find:** "yes agree inside of Find is perfect". | As recommended. |

They also said of the first round's captures: "those images look ok".

Decisions the designer made, open to change: the builder's place (`gamedata.py`); the list in
the data folder with no tracked copy; a child process for the build; stats, not hashes, to
decide at start; the room rule; no room for gamepad groups; no tap / hold suggestions; "New in
this build" flags; device names in every hint; the game's labels unworded.

## 12. Stages

Three Workers, one after the other. None commits. A and B are split because they touch
different files and each fills one context.

### Stage A: the builder and its command

- **Goal:** `build_actions()` and `python tools/gamedata.py actions` with `--check`, `--rig`,
  `--out` and the exit codes; the loader that reads the directory in pieces; the list's schema in
  `dashboard/RIG.md`; tests 1 to 14.
- **Read first:** this file §3, §5.1 to §5.4, §5.5 "What is new in a patch", §7, §8, §10;
  `tools/gamedata.py`; the mockup's `build.py`; [`../../RIG.md`](../../RIG.md);
  `tools/regen_cards.py` `write_atomic`, `rig_code`, `canon` (to reuse the method, not to edit).
- **Owns:** `tools/gamedata.py`; `dashboard/tests/test_actions.py` and
  `tests/samples/actions_game.json`; a new section "actions.json" in `dashboard/RIG.md`; the
  lines in `tools/README.md` and `tools/CLAUDE.md` that name the new command; root `CLAUDE.md`
  §7 and §10.3 (ask the lead first: other agents edit that file).
- **Does not touch:** `MOZA.xml`, `rig.json`, `tools/regen_cards.py`, anything under
  `dashboard/scdash/` or `dashboard/web/`.
- **Done when:** the suite passes; a build into a scratch folder gives the counts of §3 or the
  report says why they moved; `--check` exits 0 on it and 1 after a binding is changed in a
  scratch copy of the profile; `gamedata.py check` and `catalog` print what they printed before;
  the process's peak working set for `actions` is under 100 MB, measured and reported.
- **Report:** the counts, the peak and time measured, the mutations each test caught, what
  differs from this brief and why.

### Stage B: the service's start-up step

- **Goal:** §5.5 and §5.6: `scdash/actions.py`, its place in the service's start, the record,
  `service.actions` in the message, `/rig/actions.json` from the data folder; tests 15 to 23 and
  the server's; the four measurements; the text for `dashboard/STATE.md` (the block) and
  `dashboard/CLAUDE.md` (module map, what the step costs, how to rerun it).
- **Read first:** this file §3, §4, §5.5, §5.6, §7, §8, §10; `scdash/service.py` around
  `_first_read_done`, the start and the stop; `scdash/server.py` `rig_files()` and the file
  table; `scdash/config.py`; [`../../PLAN.md`](../../PLAN.md) §8 and §9 for the service's rules
  and budgets.
- **Owns:** `dashboard/scdash/actions.py` (new); the start, stop and message parts of
  `scdash/service.py` that the step needs; the `/rig/` part of `scdash/server.py`;
  `ACTIONS_BUILD_SECONDS` and the comment fix in `scdash/config.py`;
  `tests/test_actions_step.py`, the new cases in `tests/test_server.py`.
- **Does not touch:** `tools/gamedata.py` beyond reporting a fault in it to the lead; the page.
- **Done when:** the suite passes; with the record matching, a start runs no child (seen in the
  service's log); after `touch MOZA.xml` a start runs one, and the list is replaced only if its
  content changed; with `--p4k` pointed at nothing and a list on disk the page's message says
  `ready` and the list says `game_read` false; with no list, `failed` and `no-game`; the four
  measurements are in the report; the interpreter the service runs under was checked for a zstd
  decoder.
- **Report:** the measurements with their conditions, the mutations caught, which Python the
  service runs under, anything in the service's rules the step strains.

### Stage C: the page

- **Goal:** §6, in `web/app.js` and `web/style.css`, with the page tests, captures of every
  state of §6.6 in both orientations with the terminal on and off, and the doc text for
  `dashboard/CLAUDE.md` ("The rig reference").
- **Read first:** this file §4, §6 to §8, §10; the mockup's `actions.css` and the captures named
  in §9; `web/app.js` from "the rig reference" to `RENDERERS`; the `rig` rules of
  `web/style.css`; `dashboard/data/handoff/session4/views-rig/cap_rig.py` for the capture
  method.
- **Owns:** the rig section of `web/app.js` and of `web/style.css`; `tests/test_page_rig.py`,
  the rig cases of `tests/test_page_static.py` and `tests/test_page_browser.py`.
- **Does not touch:** the data, the service, the head of the reference, the live views.
- **Done when:** the page tests pass; the captures exist and were looked at; the measuring finds
  no type under 18 px, no inline style and no overflow of the view in any captured state; the
  Controls list behaves as before with the list missing.
- **Report:** the captures to look at first, what was not built as written and why, what no real
  pointer has touched.

## 13. Considered and rejected

- **Refreshing while the service runs** (watching the build file, or building again when the
  log shows a new game version). The designer's first draft of the service's refresh; the user
  chose start-up only, in the words quoted in §11. If the wait after a patch turns out to
  matter, the smallest addition is one more run of the same step when a new game session's
  version differs from the list's build.
- **A tracked copy of the list in `web/rig/`,** with the service's copy beside it. Two files
  that can disagree, a 155 KB generated file changing in git at every binding change and patch,
  and nothing gained on a PC that has the game.
- **Building inside the service's own process,** on a thread. The read's memory would enter the
  service, a stall could not be ended, and the zstd package would become something the service
  itself imports.
- **A zstd decoder written in Python,** so no package is needed. Several hundred lines to write
  and prove correct, slow on the 10.7 MB text file, for a decoder that Python 3.14 brings and
  that is already installed here.
- **Hashing the inputs at every start.** Exact, but it reads four files where five stats do,
  and a needless build costs under a second.
- **Building the list from the Markdown catalog** in `reference/`. It is a rendering for people;
  its reader in `regen_cards.py` drops a row with a pipe in it; and the user asked for the
  game's files.
- **Putting it in `build_reference.py`.** A full run loads the game's record database: a minute
  and 520 MB for a list that needs a second.
- **A ninth tab.** The tab row is full at 1140 px and at 1920 px **[seen 2026-11-28, captures of
  the built page]**; the user chose Find.
- **The pilot's seat only,** with the rest counted. The designer's first scope; the user chose
  everything.
- **Listing the 351 actions without a menu name.** They cannot be found in the game's menu, and
  whether the profile can bind them is not known.
- **Interleaving bound and not bound in the game's order.** The user asked to see "clearly"
  which is which; two sections per group do that, and the keys reduce it to one.
- **Rewording the game's labels for the screen,** as the Controls rows are. 753 hand-written
  lines to keep true after every patch, and the label is what the game's menu shows.
- **Tap / hold sharing suggestions.** §5.4.
- **A hand-kept note per action** ("left unbound on purpose: ESP stays on in the settings").
  Useful, but it is a second place for what root `CLAUDE.md` §4 and §6 already say. A
  suggestion for later, if the user wants the reasons on the page.
