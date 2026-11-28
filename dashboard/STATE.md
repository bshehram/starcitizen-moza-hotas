# What the page receives in stage 3

*The contract between the logic (`scdash/board.py` and the modules behind it) and the page
(`web/`). The page builder works from this file alone, so every key is here: its type, when it
is null or empty, and an invented example per view. Written 2026-11-27 with the code; change both
together.*

## Where it comes from

```python
from scdash import board
payload = board.build(state, plans, user, now, game_running, tz=None)
```

- `state`: the `LogReader`'s `State`.
- `plans`: a `plan.PlanStore` over `data/plan.json` (or a plan dict, or None).
- `user`: the `user` block of `data/state.json`, where the service keeps quick timers and the view
  picked by hand.
- `now`: seconds since the epoch, from the service's clock (the replay clock in a replay).
- `game_running`: whether the game process is running. The log alone cannot tell, because a
  crash leaves no line.

The payload is a pure function of those. It reads no clock. It changes with `now` only at the
moment `next_change_ms` names (the next local midnight is always among those moments, because
"10:24 PM" becomes "Nov 26, 10:24 PM" then), so rebuild it when the state changed or when that
moment has passed, never every second. Countdowns and clocks are drawn by the page from the
`*_ms` values and its own one-second timer: no text in the payload counts up or down.

A `now` that is not a finite number from 1971 to 2099 does not raise: the last event's time
stands in for it and `problems` names `"now: not a usable time"`.

Every text has been through the state's scrubber: another player's name reads "another player",
the user's handle "you", and no control or bidirectional character is left (PLAN §8). Every text
is at most 300 characters (`board.MAX_TEXT`; longer ones end in "…"). Every list is bounded.

The service sends it as `board`, beside the stage 2 message parts (`service`, `clock`, `flags`,
`state`): the last section, "The message and the endpoints", has the whole message and the four
changes the page can ask for. The page (`web/app.js`, since 2026-11-28) takes its alerts from
`board.alerts` only: they hold the preflight, downed and hangar alerts the stage 2 page built by
itself. `state.alerts`, `state.timers`, `state.plan` and `state.view` stay empty.

## Conventions

| Kind of value | Form |
| --- | --- |
| A time to count from or to | `*_ms`: integer, milliseconds since the epoch (UTC). |
| A time to show | `*_text` or inside a worded string: local time, `"10:24 PM"` on the same local day as `now`, else `"Nov 26, 4:21 PM"`. Dates are month first. |
| A time for the record | `t`, `ready_at`, `cleared_at`, `updated`: ISO 8601 UTC with milliseconds, `"2026-11-27T00:20:00.000Z"`. |
| A figure to show | A string, already worded: `"11,655"`, `"2.66"`, `"+8%"`, `"218,400"`. Never format these again. |
| A fraction for a meter | `fill`: a number from 0 to 1 (set with `style.setProperty("--v", fill)`, PLAN §11). |
| Nothing known | `null` for a value or a block, `[]` for a list. A block that is null is not drawn: no empty box, no zero. |
| A tone | `"bad"` (red, octagon), `"warn"` (amber, triangle), `"ok"` (green, check), as the mockup's `alert--bad`, `alert--warn` and the check icon. |
| A checklist state | `"done"`, `"now"`, `"next"`, `"later"`, `"failed"`: `obj--done`, `obj--now`, `obj--next`, the plain `obj`, and a failed row. Legs and steps use `"done"`, `"now"`, `"later"`. |

## Top level

| Key | Type | Notes |
| --- | --- | --- |
| `schema` | int | 1. |
| `view` | object | Which view and why (below). Never null. |
| `model` | object | The view's model; `model.view` names it. Never null. |
| `strip` | object or null | The status strip's words. Null only if it could not be built (see `problems`). |
| `alerts` | list of alert | At most 6, red first, then amber, then green, newest first within each. |
| `timers` | list of timer | At most 20: running (soonest first), then ready, then done. The user's quick timers always have room (at most `plan.MAX_QUICK`); the plan's fill the rest. |
| `plan` | object | The plan's state (below). Never null. |
| `unmapped_contracts` | list | Contracts the reference table could not place: `{"contract", "generator", "title"}`, any of them null. For `data/unmapped.json`; the page need not show them. |
| `next_change_ms` | int or null | When the payload next changes without a new event: an alert expiring, a timer coming due, a quick timer dropping out, or the next local midnight. Null only when even midnight cannot be told (the payload that failed to build). |
| `problems` | list of strings | Parts that failed and were left empty, such as `"model: KeyError"`, `"now: not a usable time"`, or `"build: KeyError"` when the whole payload fell back to an empty Now view. Empty normally. The service logs them; the page can ignore them. |

### `view`

| Key | Type | Notes |
| --- | --- | --- |
| `name` | string | The view to draw: `now`, `travel`, `mining`, `salvage`, `combat`, `cargo`, `mission`, `refinery`, `selling`, `preflight`, `idle`, or `reference` (only by hand, below). |
| `rule` | string | The row of the rules table that chose `auto` (`no_game`, `menu`, `downed`, `travel`, `leg`, `sell`, `contract`, `ship`, `else`; `error` if the payload failed). |
| `why` | string | A plain reason, such as `"At leg 2 of Run A: MIC-L2"`. |
| `context` | string | The key a hand pick is kept under: the rule and its subject (this jump, this leg, this contract, this ship, this place), at most 120 characters (a longer one keeps its start and a hash). Informational for the page. |
| `auto` | string | The view the rules chose; equals `name` unless a hand pick is shown. Never `reference`. |
| `mode` | string | The mode the reference cards open on: `mining` or `salvage` when the rules chose that view (or, while the game runs, the seated ship has that one job), else `flight`. Present on every view. |
| `picked` | bool | True when `name` is the user's hand pick. |
| `pick_dropped` | bool | True when a hand pick was given but the context has changed: the service should forget it. Never true for a `reference` pick. |

**Picking by hand.** The service saves `board.pick(state, plans, name, game_running, now)` as
the user block's `view` and removes it when `pick_dropped` says so. A pick of a view stays while
the context is the same: walking between zones of one place or opening the storage screen is no
change; a new jump, leg, contract, ship, place or session is. `board.pick(..., "live")` returns
None: save None, and the rules choose again.

**The reference view** is the rig's button-reference cards. No rule chooses it; only a hand pick
does, and a change of context, a restart of the service or the end of the session never drops it.
It stays until the user picks Live. Alerts and timers are built as on any view, and `view.auto`
says what the rules would show, so the page can offer the way back. Its model is
`{"view": "reference", "mode": "mining", "auto": "mining"}`: the cards themselves are a static
file the page loads; `mode` is the tab to open them on. That file (`/rig/rig.json`, schema 2, and
the eight images it names) is described field by field in [`RIG.md`](RIG.md).

The rules, first that fits (`scdash/rules.py`, `RULES`): no game running → `idle`; starting or at
the main menu → `preflight`; downed or dead → `combat` when a combat contract is active (the
mockup's `#downed` screen), else `now`, with the red alert on top either way; a quantum target
chosen and not arrived (and less than 20 minutes old by event time) → `travel`; at a leg of the
plan's current run → that leg's `view`; at a place the plan has a sell list for → `selling`; an
active contract → its view from the contract table (`combat`, `cargo`, `salvage`, `mining`, or
`mission` for any other kind, known or not); in the pilot seat of a ship with one job → that job;
anything else → `now`.

### `strip`

```json
{"state": "In game", "tone": "live",
 "session": {"label": "Session", "since_ms": 1795734680067, "text": null},
 "where": {"icon": "pin", "text": "CRU-L1 Ambitious Dream Station"},
 "ship": {"icon": "ship", "text": "Drake Golem"}}
```

| Key | Notes |
| --- | --- |
| `state` | `"In game"`, `"Quantum travel"`, `"Main menu"`, `"Game starting"`, `"Preflight failed"`, `"Downed"`, `"Dead"`, `"No game running"`. |
| `tone` | `live`, `quantum`, `bad`, `off`: the mockup's `state--live`, `state--quantum`, `state--bad`, `state--off`. |
| `session` | `label` "Session" with `since_ms` (count up from it, `h:mm`), or `label` "Last played" with `text` such as `"Thu, Nov 26"`. With no session at all: `text` "none yet". |
| `where` | `icon` `pin` or `jump`; `text`: the place, `"To ARC-L4"` while travelling, `"Main menu"`, `"Left New Babbage"`, `"Near microTech"`, or null when the log has said nothing yet. |
| `ship` | `icon` `ship` or `walk`; `text`: the ship's display name, `"On foot"` out of the seat in the game world, or `"No ship"`. |

### Alert

```json
{"id": "refinery_done:1795738891157", "level": "ok", "kind": "Done",
 "title": "Work order complete", "text": "At MIC-L2 Long Forest Station", "do": null,
 "t": "2026-11-27T00:21:31.157Z", "t_ms": 1795738891157, "until_ms": 1795739491157}
```

| Key | Notes |
| --- | --- |
| `id` | Stable across rebuilds and rereads: use it as the element's key. |
| `level` | `bad`, `warn` or `ok`. |
| `kind` | The small label above the title: "Preflight failed", "Downed", "Dead", "Attention", "Attacked", "Law", "Contract", "Ship lost", "Server", "Injury", "Done", "Received", "Paid". |
| `title` | The large line. |
| `text` | A second line, or null. |
| `do` | What to do, or null. |
| `t`, `t_ms` | When it happened (the event's own time). |
| `until_ms` | When it expires, or null for one that lasts while its condition holds. |
| `since_ms` | On every alert; null except on the hangar alert, where it is when the user joined the queue. The text gives the estimate ("The estimate was 2 min 00 s."); the page counts the wait up from `since_ms`. |

What raises one (`scdash/alerts.py`). While the game runs and the condition holds: a missing
stick base or throttle (red; a different order is not an alert, see Preflight), downed (red),
dead (red), the hangar queue past twice its estimate (amber), monitored space down (amber). For
a fixed time after the event, counted from the event's time so that a reread raises nothing old:
quantum destination obstructed (amber, 2 min), a crime against the user (red, 5 min), CrimeStat
up (amber, 10 min), a crime committed, a fine (amber, 5 and 3 min), a vehicle impounded (amber,
10 min), a contract failed or withdrawn (amber, 5 min), a severe or critical injury (amber,
5 min), a ship lost (amber, 5 min), a server crash (red) or an inactivity kick (amber, 5 min), a
work order complete (green, 10 min), a blueprint (green, 5 min), pay (green, 2 min).

### Timer

```json
{"id": "plan:t1", "source": "plan", "kind": "refinery", "label": "Agricium and Tungsten",
 "where": "MIC-L1 Shallow Frontier Station", "where_short": "MIC-L1", "state": "running",
 "text": "Ready 10:24 PM", "ready_at": "2026-11-27T06:24:00.000Z", "ready_ms": 1795760640000,
 "ready_text": "10:24 PM", "started_ms": 1795750800000, "cleared_at": null}
```

| Key | Notes |
| --- | --- |
| `id` | `plan:<id>` or `quick:<id>`. A quick timer is removed through the service by this id. |
| `source` | `plan` (from `plan.json`) or `quick` (added on the page). |
| `kind` | `refinery`, `other` or `quick`. |
| `label` | The timer's name. |
| `where`, `where_short` | The place in full and short, or the plan's own words when the name table does not know it; null for none. |
| `state` | `running` (count down to `ready_ms`), `ready` (its time has passed), `done` (a "work order completed" notice cleared it). |
| `text` | `"Ready 10:24 PM"`, `"Ready since 4:20 PM"`, `"Work order complete at 4:21 PM"`. |
| `ready_ms`, `ready_text`, `ready_at` | When it is due. |
| `started_ms` | When it started, for a meter's fill, or null (no meter then). |
| `cleared_at` | When the notice cleared it, or null. |

A notice clears a refinery timer only when its station matches and the timer's ready time is at
or before the notice plus five minutes; with two at one station it clears the earliest (PLAN §7).
The station matches only when the two names are the same place after normalizing (spaces, case,
accents): "MIC-L1" does not match "MIC-L1 Shallow Frontier Station" unless the name table makes
them one place. A quick timer drops out of the list 30 minutes after it is due.

### `plan`

| Key | Notes |
| --- | --- |
| `loaded` | Whether a plan is in use (the last good copy counts). |
| `notice` | A short text when something is wrong, such as `"plan.json: left out because they do not fit the shape: current_run (not a run id), 1 text (cut to length), 1 key (not in the plan's shape), 1 entry in legs, 2 numbers (out of range or not a number), 1 time (not readable), 1 value (a status, kind, view or id the shape does not allow)"` (every value left out or changed on the way is counted, by kind; a key the shape does not have, a misspelled one and `run` given beside `runs` count as keys, an empty location code and a `schema` other than 1 count too, and a key that starts with `_` is a comment), `"plan.json is not valid JSON (line 3); showing the last good copy (updated Nov 26, 5:30 PM)"`, `"plan.json cannot be read now (PermissionError)"` (tried again on the next refresh) or `"there is no plan.json yet"`; null when all is well. Show it small. Its time is in the computer's zone, not `tz`. |
| `updated`, `updated_text` | The plan's own `updated` time, or null. |
| `run`, `run_kind` | The current run's name and kind, or null. |

## Blocks the views share

**Contract** (`contract`, and the `contract` of other views):

```json
{"id": "e0000005-0000-4000-8000-000000000005", "title": "ENTRY LVL. COURIER NEEDED IN STANTON",
 "giver": "FTL Courier", "kind": "delivery", "kind_name": "Courier", "view": "cargo",
 "setting": null, "status": "active", "reward": null,
 "objectives": [
   {"text": "Collect Data Probe From HUR-L1 Green Glade Station", "state": "done", "optional": false,
    "stop": {"kind": "pickup", "index": 0, "item": "Data Probe", "place": "HUR-L1 Green Glade Station",
             "amount": null, "verified": true}},
   {"text": "Deliver Data Probe To HUR-L3 Thundering Express Station", "state": "now", "optional": false,
    "stop": {"kind": "dropoff", "index": 0, "item": "Data Probe", "place": "HUR-L3 Thundering Express Station",
             "amount": null, "verified": true}}],
 "before": 0, "after": 0, "more": 0, "count": "Objective 2 of 2",
 "current": "Deliver Data Probe To HUR-L3 Thundering Express Station", "unmapped": false}
```

`giver`: from the contract table, else the generator's name in words, else null. `kind_name`:
the game's mission type ("Courier", "Mercenary", "Hauling"), else the kind. `setting`: `foot`,
`ship`, `vehicle` or null (not settled). `status`: `active`, `complete`, `failed`, `withdrawn`,
`abandoned`. `reward`: aUEC, only when the log printed "Awarded <n> aUEC" (legacy contracts
only), else null: show no reward then. `objectives`: pickups before drop-offs, a window of at
most 8 (3 in the Now view's compact block) that always holds the current row, centered on it
where it can be; `before` and `after` count the rows cut above and below it, `more` both
together. `count` ("Objective k of n") counts every objective not withdrawn, cut or not; it is null when there is one
objective or none is open. `current`: the objective for large type, or null. `stop.amount`:
`"0/8 SCU"` for a haul, null for a courier. `stop.verified`: false for the hauling shape, which
no log has shown yet.

**Controls** (`controls`): `{"mode", "title", "items": [{"where", "what", "status"}]}`, from
`reference/controls.json`. `title` such as `"Mining mode · knob detent 4"`. `status`: null,
`"flown"`, `"unverified"` or `"trial"` (mark the last two quietly). Null when the view has none.

**Law** (`law`): `{"jurisdiction": "UEE jurisdiction" or null, "marks": [{"on", "icon", "text"}]}`;
`icon` `eye` (monitored space) or `noshield` (armistice). `on` true draws `mark--on`.

**Materials** (`materials`, `goal` in Mining): `{"asof": "held as of Nov 26, 4:12 PM", "items":
[{"name", "held", "need", "unit", "fill", "ok", "short", "note", "min_quality"}], "first"}`.
`note` is "Covered" or "1.38 to go". `first` names the material most short, or null. Held figures
are only as fresh as the plan's `updated` time: always print `asof` beside them.

## The views, one model each

Examples are invented or from the sanitized samples; lists are cut where marked `…`.

### `now`

| Key | Notes |
| --- | --- |
| `next` | The plan's next step (its current objective's `next_step`), or null. |
| `steps` | The plan's objectives: `{"text", "state"}` with `done`, `now`, `later`. |
| `timer` | The soonest running timer (a timer object), or null. |
| `materials` | A materials block, or null. |
| `here` | `{"place", "do", "run"}`: what the plan says to do at the current place, or null. |
| `contract` | The most recently active contract, compact, or null. |
| `notes` | The plan's notes. |
| `location` | `{"code", "name", "short", "body"}` of the current place, or null. |

```json
{"view": "now", "next": "Run B: mine Agricium and Beryl at CRU-L5",
 "steps": [{"text": "High-quality ore for two quantum drives", "state": "now"},
           {"text": "RMC for repairs aboard the carrier", "state": "later"},
           {"text": "Tungsten from ARC-L4", "state": "done"}],
 "timer": {"id": "plan:t1", "label": "Agricium and Tungsten", "where_short": "MIC-L1", "state": "running",
           "text": "Ready 10:24 PM", "ready_ms": 1795760640000, "started_ms": 1795750800000, "…": "…"},
 "materials": {"asof": "held as of 5:30 PM",
               "items": [{"name": "Tungsten", "held": "2.66", "need": "2.22", "unit": "SCU", "fill": 1.0,
                          "ok": true, "short": null, "note": "Covered", "min_quality": "600"},
                         {"name": "Agricium", "held": "1.9", "need": "5.52", "unit": "SCU", "fill": 0.344,
                          "ok": false, "short": "3.62", "note": "3.62 to go", "min_quality": "600"}],
               "first": "Agricium first: it is 3.62 SCU short."},
 "here": null, "contract": null, "notes": ["Free text shown on the Now view"], "location": null}
```

### `travel`

| Key | Notes |
| --- | --- |
| `dest` | `{"short": "ARC-L4", "name", "code", "sub"}` (show `short` large, `name` below); `sub` such as `"ARC-L4 field · leg 1 of 3"`, or null. Null only when no target is known (a hand pick). |
| `since_ms`, `since_text` | When the target was set; `clock_label` is the words for that clock ("Since the target was set": the log has no moment the drive spools). |
| `from` | The route's start as the game names it, or null. |
| `fuel` | The route's fuel estimate, worded, or null. |
| `obstructed` | True when the game said the destination is obstructed. |
| `run` | The current run's name, or null. |
| `legs` | `{"place", "why", "state", "gm"}` for every leg of the run; `gm` the distance in Gm, worded, or null. |
| `arrive` | What to do on arrival: the leg's own list, else what its view needs first. |
| `timer` | The soonest running timer, or null (the mockup's timer line). |
| `controls` | The travel controls. |

```json
{"view": "travel",
 "dest": {"short": "ARC-L4", "name": "ARC-L4 Faint Glen Station", "code": "LOC_RR_S3_L4",
          "sub": "ARC-L4 field · leg 1 of 3"},
 "since_ms": 1795735144767, "since_text": "since 3:19 PM", "clock_label": "Since the target was set",
 "from": "New Babbage", "fuel": "153,453", "obstructed": false, "run": "Run A",
 "legs": [{"place": "ARC-L4 field", "why": "Mine Tungsten", "state": "now", "gm": null},
          {"place": "MIC-L2", "why": null, "state": "later", "gm": null},
          {"place": "New Babbage", "why": "Haul the lots home", "state": "later", "gm": null}],
 "arrive": ["Turn the mode knob to Mining (knob detent 4).", "Tungsten reads 11,610.", "Take rocks at 600 and up."],
 "timer": {"label": "Tungsten", "where_short": "MIC-L2", "state": "running", "ready_ms": 1795738800000, "…": "…"},
 "controls": {"mode": "travel", "title": "Travel", "items": [{"where": "NAV key", "what": "Master mode SCM / NAV", "status": null}, "…"]}}
```

### `mining`

| Key | Notes |
| --- | --- |
| `where` | `"CRU L5, Crusader · plan: Run B"`, or null. |
| `spot`, `spot_known` | The ore table's spot key and whether it knows it. |
| `ores_from` | `"plan"` (the run's targets), `"spot"` (no plan names targets: the most common ores at this spot, with no take or skip figures), or null (no ores to show). |
| `ores` | One per target ore: `name`, `known` (false: not in the ore table), `tier_text` (`"Uncommon · 28% of rocks here"`, `"Rare · not in this spot's rock mix"`, or null for an ore the table does not know at a spot it does not know), `take` (`"600+"`) and `skip` (`"600"`), either null, and `reads`: `{"rocks", "rocks_text", "scan", "chance", "chance_text", "top"}` per cluster size, the most likely first (`top`). The scan figures are the largest type on the screen. |
| `goal` | A materials block for the target ores, or null. |
| `alike` | One sentence about look-alikes at this spot, or null. |
| `refine` | `{"method", "rows": [{"ore", "at", "bonus", "positive", "date"}]}`, or null. The bonus is crowd-reported: show its date. |
| `contract` | A mining contract, or null. |
| `controls` | Mining mode. |

```json
{"view": "mining", "where": "CRU L5, Crusader · plan: Run B", "spot": "cru-l5-field", "spot_known": true,
 "ores_from": "plan",
 "ores": [{"name": "Agricium", "known": true, "tier_text": "Uncommon · 28% of rocks here", "take": "600+", "skip": "600",
           "reads": [{"rocks": 3, "rocks_text": "3 rocks", "scan": "11,655", "chance": 0.6, "chance_text": "60%", "top": true},
                     {"rocks": 4, "rocks_text": "4 rocks", "scan": "15,540", "chance": 0.3, "chance_text": "30%", "top": false},
                     {"rocks": 5, "rocks_text": "5 rocks", "scan": "19,425", "chance": 0.1, "chance_text": "10%", "top": false}]},
          {"name": "Beryl", "known": true, "tier_text": "Rare · 18% of rocks here", "take": "700+", "skip": "700", "reads": ["…"]}],
 "goal": {"asof": "held as of Nov 26, 5:30 PM", "items": ["…"], "first": "Agricium first: it is 3.62 SCU short."},
 "alike": "None within 1% at CRU L5.",
 "refine": {"method": "Pyrometric Chromalysis",
            "rows": [{"ore": "Agricium", "at": "MIC-L1 Shallow Frontier Station", "bonus": "+8%", "positive": true, "date": "2026-10-19"},
                     {"ore": "Beryl", "at": "CRU-L1 Ambitious Dream Station", "bonus": "+7%", "positive": true, "date": "2026-11-17"}]},
 "contract": null,
 "controls": {"mode": "mining", "title": "Mining mode · knob detent 4",
              "items": [{"where": "FLAPS lever", "what": "Mining laser power", "status": "flown"}, "…"]}}
```

### `salvage`

| Key | Notes |
| --- | --- |
| `where` | The leg's place or the current place, or null. |
| `goal` | `{"title": "RMC for repairs", "held", "need", "unit", "fill", "sub"}` from the run's salvage goal, or null. The log cannot see what is scraped: held is the plan's. |
| `hold` | `{"title": "RSI Salvation hold", "scu", "sub"}` from the ship's cargo grid, or null (no ship, or no grid figure). |
| `next` | The plan's next step for the salvage, or null. |
| `contract` | A salvage contract, or null. |
| `sell` | `{"title", "rows": [{"what", "note", "price"}], "foot"}`, or null without a sell point. `price` is null without `prices.json`; `foot` names the source and date, null when no price was found. |
| `controls` | Salvage mode. |

```json
{"view": "salvage", "where": "CRU-L4 Shallow Fields Station",
 "goal": {"title": "RMC for repairs", "held": "4.5", "need": "12", "unit": "SCU", "fill": 0.375,
          "sub": "Held as of Nov 26, 5:30 PM · 7.5 SCU to go"},
 "hold": {"title": "RSI Salvation hold", "scu": "6", "sub": "About 2 full holds to go"},
 "next": "Scrape the hull, then use the fracture field.", "contract": null,
 "sell": {"title": "Sell at CRU-L1 Ambitious Dream Station",
          "rows": [{"what": "RMC", "note": "keep for repairs", "price": "9,750"},
                   {"what": "Construction Materials", "note": "sell", "price": "2,480"}],
          "foot": "aUEC per SCU · UEX, Nov 26"},
 "controls": {"mode": "salvage", "title": "Salvage mode · knob detent 5", "items": ["…"]}}
```

### `combat`, in a ship

| Key | Notes |
| --- | --- |
| `on_foot` | false here. |
| `downed` | True when downed or dead (the red alert is on top; draw the mockup's `#downed`). |
| `where` | `"Pilot seat · Origin M80"`, or `"No ship · Origin M80 destroyed 8:21 PM"` after a loss. |
| `ship` | `{"name", "note"}`; `note` from the plan's combat block, such as `"Trigger: S5 pair · stage 2: S4 pair"`, or null. |
| `tally` | `{"destroyed", "crippled", "lost", "downed", "kills_verified"}`: integers for this session. `kills_verified` is false: the user's kills are read from the killer's id, which no log has shown yet. |
| `contract` | A combat contract, or null: a fight needs no contract. |
| `law` | A law block. |
| `health` | `"Severe injury: torso, tier 1"`, `"Downed"`, `"Dead"`, or null. |
| `controls` | Combat (guns) mode. |
| `telemetry` | Always null until stage 6 wires the stream in: draw no countermeasure or power figures. |
| `ship_left` | null here. |

```json
{"view": "combat", "on_foot": false, "downed": false, "where": "Pilot seat · Origin M80",
 "ship": {"name": "Origin M80", "note": null},
 "tally": {"destroyed": 2, "crippled": 0, "lost": 0, "downed": 0, "kills_verified": false},
 "contract": {"title": "Terrorist Rel Hosk to be Neutralized", "giver": "InterSec Defense Solutions",
              "kind": "combat", "kind_name": "Mercenary", "setting": "ship", "status": "active", "reward": null,
              "objectives": [{"text": "Neutralize Rel Hosk", "state": "now", "optional": false, "stop": null}],
              "count": null, "current": "Neutralize Rel Hosk", "…": "…"},
 "law": {"jurisdiction": "UEE jurisdiction", "marks": [{"on": true, "icon": "eye", "text": "Monitored space"}]},
 "ship_left": null, "health": null,
 "controls": {"mode": "combat", "title": "Combat, guns mode · knob detent 1", "items": ["…"]}, "telemetry": null}
```

### `combat`, on foot

The same model with `on_foot` true: `ship`, `tally` and `controls` are null (the rig is not in
use on foot), and `ship_left` says where the ship was left: `{"name", "where", "when"}`, `where`
null when the log named no place. The log records no kills on foot: show no tally.

```json
{"view": "combat", "on_foot": true, "downed": false, "where": "On foot", "ship": null, "tally": null,
 "contract": {"title": "Defend Ruin Station from Outlaws", "giver": "Citizens for Prosperity", "setting": "foot",
              "objectives": [{"text": "Draw out Kade Ross by eliminating enough hostile forces", "state": "done"},
                             {"text": "Neutralize Kade Ross", "state": "now"}],
              "count": "Objective 2 of 2", "…": "…"},
 "law": {"jurisdiction": null, "marks": [{"on": true, "icon": "eye", "text": "Monitored space"}]},
 "ship_left": {"name": "Origin M80", "where": null, "when": "8:31 PM"},
 "health": "Moderate injury: left arm, tier 2", "controls": null, "telemetry": null}
```

### `cargo`

| Key | Notes |
| --- | --- |
| `head` | `"Hauling Quartz · 2 stops"`, `"Courier · 2 stops"`, `"Trade run"`, or null. |
| `this_stop` | `{"big", "unit", "kind", "here", "sub", "verified"}`: the current stop, `big` the SCU left to move (`"8"` with `unit` `"SCU off"` or `"SCU on"`) or the item for a courier (`"Data Probe"` with `"to pick up"` or `"to drop off"`); `here` true when the user is at it; null with no stop. |
| `contract_total` | `{"big": "24", "unit": "SCU", "sub": "in 2 stops"}`, or for a courier `{"big": "2", "unit": "stops", "sub": "1 pickup, 1 drop-off"}`, or null. |
| `grid` | `{"title": "Drake Golem OX grid", "big": "64", "unit": "SCU", "sub"}` with `sub` `"room to spare"`, `"exactly full"`, `"8 SCU more than the grid"` or `"cargo grid"`; null without a grid figure. |
| `keys` | A list of one controls item, for landing and loading requests at a stop, or null. |
| `contract` | A cargo contract, or null. |
| `stops` | `{"kind", "index", "place", "item", "scu", "boxes", "delivered", "state", "verified"}`, pickups first. A haul logs no pickups. |
| `trade` | `{"bought", "sell"}`, two sentences or nulls, from this session's last commodity purchase and the plan's trade, or null. |
| `earned` | `{"big": "+46,250", "unit": "aUEC"}`: sales and pay the log shows this session, or null when none. |
| `controls` | Landing and loading. |
| `unverified` | Sentences to show small when the view leans on an unverified shape (a haul). |

No figure for what is aboard: the log cannot see cargo (PLAN §3).

```json
{"view": "cargo", "head": "Hauling Quartz · 2 stops",
 "this_stop": {"big": "8", "unit": "SCU off", "kind": "dropoff", "here": false, "sub": "Quartz, at Orison", "verified": false},
 "contract_total": {"big": "24", "unit": "SCU", "sub": "in 2 stops"},
 "grid": {"title": "Drake Golem OX grid", "big": "64", "unit": "SCU", "sub": "room to spare"},
 "keys": [{"where": "ALT key (tap / hold)", "what": "Landing req / hold: cargo", "status": null}],
 "contract": {"title": "Opportunity for Independent Cargo Hauler", "giver": "Covalex Independent Contractors", "…": "…"},
 "stops": [{"kind": "dropoff", "index": 0, "place": "CRU-L1 Ambitious Dream Station", "item": "Quartz", "scu": 16,
            "boxes": null, "delivered": 16, "state": "done", "verified": false},
           {"kind": "dropoff", "index": 1, "place": "Orison", "item": "Quartz", "scu": 8,
            "boxes": null, "delivered": 0, "state": "active", "verified": false}],
 "trade": {"bought": "Bought 30 SCU of Medical Supplies at New Babbage, 1,830/SCU.",
           "sell": "Sell at Orison: the plan says 2,140/SCU, about +9,300."},
 "earned": null, "controls": {"mode": "cargo", "title": "Landing and loading", "items": ["…"]},
 "unverified": ["Hauling drop-offs are read from the objective text the game has for them; no haul is in the project's record of the user's logs yet."]}
```

### `mission`

| Key | Notes |
| --- | --- |
| `contract` | The most recently active contract, full, or null. |
| `go_next` | `{"place", "sub"}`: the current objective's place, else the plan leg's, else `place` null with `sub` "Marker set by the contract"; null without a contract. |
| `others` | `{"count", "items": [{"title", "giver", "objective"}]}`: the other active contracts, at most 4 listed. |

```json
{"view": "mission",
 "contract": {"title": "A Very Unusual Job", "giver": "Example", "kind": "unknown", "kind_name": "Unknown",
              "objectives": [{"text": "Go to the marker", "state": "later"},
                             {"text": "Find the lost data pad and bring it back", "state": "now"}],
              "count": "Objective 2 of 2", "unmapped": true, "…": "…"},
 "go_next": {"place": null, "sub": "Marker set by the contract"},
 "others": {"count": 0, "items": []}}
```

### `refinery`

| Key | Notes |
| --- | --- |
| `station` | `{"name", "short"}`, nulls when no place is known. |
| `method` | `{"name": "Pyrometric Chromalysis", "detail"}`: the leg's, else the plan's, else the user's preferred method. The game has no figure for a method's cost or time. |
| `refine` | `{"ore", "bonus", "positive", "date"}` for the ores to refine here (the leg's list, else the run's targets); `bonus` null when no report exists. |
| `leave` | `{"ore", "why"}` for the ores to leave out; `why` such as `"refine at MIC-L1 Shallow Frontier Station (+8%)"`, or null. |
| `timers` | The refinery timers at this station. |
| `done_here` | `{"text", "count"}`: completion notices here this session, at most 5. |
| `sold_ore` | True when ore was sold to this refinery this session (the log does not say what or how much). |
| `note` | The leg's `do`, or null. |

```json
{"view": "refinery", "station": {"name": "MIC-L2 Long Forest Station", "short": "MIC-L2"},
 "method": {"name": "Pyrometric Chromalysis", "detail": "High Yield // High Cost // Slightly Fast"},
 "refine": [{"ore": "Tungsten", "bonus": "+9%", "positive": true, "date": "2026-10-16"}], "leave": [],
 "timers": [{"label": "Tungsten", "state": "running", "text": "Ready 4:20 PM", "…": "…"}],
 "done_here": [], "sold_ore": false, "note": null}
```

### `selling`

| Key | Notes |
| --- | --- |
| `where` | The place, or null. |
| `rows` | `{"what", "scu", "quality", "price", "uex", "value", "note"}` for the plan's sell list here: `price` the plan's, `uex` the terminal price from `prices.json` (null without it), `value` scu times the plan's price. |
| `total` | `"222,895 aUEC"`, or null. |
| `sold` | `{"text", "time"}`: sales logged at this place this session, at most 6. |
| `prices_from` | `"UEX, Nov 27"`, or null without prices. |
| `unverified` | The note on sale quantities when a commodity sale is listed. |

```json
{"view": "selling", "where": "New Babbage",
 "rows": [{"what": "Taranite", "scu": "7.8", "quality": "310", "price": "28,000", "uex": "27,500", "value": "218,400", "note": null},
          {"what": "Quartz", "scu": "3.1", "quality": null, "price": "1,450", "uex": "1,600", "value": "4,495", "note": "low lots only"}],
 "total": "222,895 aUEC", "sold": [], "prices_from": "UEX, Nov 26", "unverified": []}
```

### `preflight`

| Key | Notes |
| --- | --- |
| `verdict` | `pass`, `fail` or `waiting` (no joystick lines yet). |
| `kicker`, `title`, `why` | The words of the head: `"Preflight failed"`, `"Stick base not detected"`, `"The keyboard took joystick 1. Every stick binding points at it."`; `why` null on a pass. |
| `note` | `"Listed in a different order than usual; this has worked."` when both devices are there in another order (a pass: no alert), else null. |
| `devices` | `{"slot", "name", "role", "mark", "mark_text"}`: every listed joystick, then each missing device with `slot` "Not found". `role`: `stick base`, `throttle`, `keyboard`, `other device`. `mark`: `ok` (found), `bad` (missing), `info` (anything else: not wrong, since the order does not matter). |
| `do` | What to do on a failure, or null. |
| `plan_notes` | The plan's "before you fly" lines. |
| `profile` | `"MOZA.xml loaded at 3:12 PM"`, or null. |

```json
{"view": "preflight", "verdict": "fail", "kicker": "Preflight failed", "title": "Stick base not detected",
 "why": "The keyboard took joystick 1. Every stick binding points at it.", "note": null,
 "devices": [{"slot": "Joystick 1", "name": "Joystick (Razer Huntsman V3 Pro)", "role": "keyboard", "mark": "info", "mark_text": ""},
             {"slot": "Joystick 2", "name": "MOZA MTQ Throttle Panel", "role": "throttle", "mark": "ok", "mark_text": "Found"},
             {"slot": "Not found", "name": "MOZA AB6 FFB Base", "role": "stick base", "mark": "bad", "mark_text": "Missing"}],
 "do": "Quit the game. Switch on the AB6 base, wait until MOZA Cockpit shows it, then start the game again",
 "plan_notes": ["Switch on the AB6 base before you start the game"], "profile": null}
```

### `idle`

| Key | Notes |
| --- | --- |
| `title` | "Nothing running". |
| `last` | `"Last session Thu, Nov 26 · 3:11 PM to 4:37 PM"`, or null with no session. |
| `facts` | `{"value", "label"}`: played, places, contracts done, aUEC from sales, deaths; empty with no session. |
| `next` | The plan's next step, or null. |
| `notes` | The plan's "before you fly" lines (draw them with the warning icon). |
| `lists` | `{"label", "text", "ok"}`: Places, Ships, and Waiting (ready or done timers, `ok` true). |

```json
{"view": "idle", "title": "Nothing running", "last": "Last session Thu, Nov 26 · 3:11 PM to 4:37 PM",
 "facts": [{"value": "1:26", "label": "played"}, {"value": "3", "label": "places"}, {"value": "0", "label": "contracts done"},
           {"value": "0", "label": "aUEC from sales"}, {"value": "0", "label": "deaths"}],
 "next": "Run A: Tungsten at ARC-L4", "notes": [],
 "lists": [{"label": "Places", "text": "New Babbage, ARC-L4 Faint Glen Station, MIC-L2 Long Forest Station, New Babbage", "ok": false},
           {"label": "Ships", "text": "Drake Golem, Drake Golem OX", "ok": false},
           {"label": "Waiting", "text": "Tungsten at MIC-L2: Work order complete at 4:21 PM", "ok": true}]}
```

### `reference`

| Key | Notes |
| --- | --- |
| `mode` | `flight`, `mining` or `salvage`: the cards' tab to open on (`view.mode`). |
| `auto` | The view the rules would show (`view.auto`), for the way back. |

```json
{"view": "reference", "mode": "salvage", "auto": "salvage"}
```

The strip, alerts and timers are built as on every other view.

A model the rules did not choose (a hand pick of a view with nothing to show) has the same keys
with nulls and empty lists. A model that failed to build is `{"view": "<name>", "unavailable":
true}`: draw the view's frame with nothing in it.

## Limits the log cannot push past

A line is data: whatever it holds, reading it takes a bounded time and the state keeps a bounded
amount.

- A record's text is cut to 2,048 characters before any pattern sees it, and a marker's fields
  (contract names, titles, places) to 200. Every pattern on a line is bounded or linear; a
  60 KB line of any shape is read in a few milliseconds.
- A contract marker line whose fields run past 200 characters records no contract at all: the
  cut takes off the field's closing bracket, so the line no longer reads as a marker. A title
  over 200 characters from a notice is not looked up in the contract table (that contract
  stays unmapped), and a place text over 200 characters is not looked up in the name table.
- At most 30 contracts are kept (`config.MAX_CONTRACTS`): ended ones go first, then inactive
  ones, then the oldest; the newest is never dropped.
- **Other players' names.** A name is cleaned of control and bidi characters before it is
  stored. Up to 1,000 are kept; past that the oldest 500 are forgotten, but only after every
  text the state still holds has had them replaced by "another player", with one pattern of all
  the names, so a handle is replaced whole (names that differ only in case, or in letters the
  pattern takes as equal such as a long s and an s, share the pattern, so a kept "Bob_Q" never
  cuts a kept "bob_q-Smith" in two). The reader's lines lose them too: the lines waiting for
  `take_lines()` at once, its list of every line (`timeline`) when the list is next read. When a
  new session starts in the same file (the game emptied it, or a session line inside it), the
  old session's lines still held by the reader are scrubbed with the old session's names before
  its state is replaced. A forgotten name met later in a text that teaches nothing is still
  hidden in output while it is among the last 50,000 forgotten (kept as 8-byte hashes, 0.8 MB at
  most), when it is made of the characters a handle can have (letters, digits, `_` and `-`, a
  `-` anywhere, leading, trailing or doubled included). That lookup runs only after more than
  1,000 names were met, costs a time linear in the text, and makes at most 8 lookups per `-`
  part plus 64 for a run (`state.HIDE_BUDGET`); a run that would need more is replaced whole from
  that point. A part makes at most one lookup per number of `-` parts the names held have, so
  that happens only when they have more than 8 different numbers of parts, which takes a name of
  9 parts or more. A name met again is learned again.
- **Notices and contracts that can name a player** (the game's shapes are listed in
  `scdash/law.py`: the law, comms, parties and groups, the party and friend toasts, money sent
  between players, service beacons and their contracts, player bounties; none of them but the
  ship channel's is seen in a log). The state words each known shape without the other party's
  name: "Crime committed: Trespassing against someone", "Attacked: another player committed
  Battery (First Degree) against you", "Victim: someone", "Another player has joined the party
  or group", "A party member disconnected", "Another player wants to send you money", "Your
  service provider has arrived", "A rescue beacon from another player", "Another player
  accepted your rescue beacon", "Friend Request: another player". A known shape is never taken
  for a tutorial tip, so it is always a feed line.
  - **Contracts.** A service beacon's objectives name the player who set it, and a player
    bounty's title and objectives name the player hunted. In such a contract (known by its kind,
    its marker names or its title, `law.player_contract()`) an objective of a known shape is
    worded without the name and the name is learned: a beacon's in its own words ("Rescue the
    player who set the beacon", "Escort the player who set the beacon until the contract is
    completed"), a player bounty's as "the target" ("Locate the target", "Neutralize the
    target"). An objective of any other shape reads "An objective the dashboard does not show
    (it may name a player)" and is counted in `withheld`, unless it is one of the game's own
    nameless objectives ("Stay at Current Location."). A player bounty's title reads "Apprehend
    Suspect: another player" or "Escapee Bounty Assignment: another player". The player
    contracts are the service beacons (kind "service beacon", their mission titles, the markers
    ReviveBeacon, BeaconContractGenerator, ServiceBeacon…) and the player bounties of generator
    NorthRock_PVP (template PVP_KillPlayerBounty, their titles, the Bounty Hunters Guild's
    Suspect Apprehension and Fugitive Recovery certifications among them); the Guild's other
    certifications and bounties have NPC targets and are not. In a contract the log has not
    placed (no title, no marker: one accepted in an earlier launch), an objective of a known
    shape whose slot could be a handle reads "… the target" and nothing is learned; when the
    contract is placed later, its objectives are worded again from their text as read: as a
    player contract's, or as written for any other kind. In a contract of another kind nothing
    changes.
  - A crime's name is shown only when it is made of the words of the game's crime names, else
    "a crime".
  - A notice of one of these families in a shape no pattern reads is never shown as written: it
    reads as its family's neutral text, "A law notice the dashboard does not show (it may name a
    player)", "A comms notice …", "A party or group notice …", "A money transfer notice …" or
    "A service beacon notice …", and is counted in the state's `session.withheld` (the
    summary's `withheld`): above zero, the game logs a shape the dashboard should learn. Every
    text under a known toast title is of the title's family. A tip-shaped one ("Topic: a long
    sentence", whose topic carries the family's cue) is never shown, as every tip, and is counted
    apart in `session.withheld_tips` (the summary's `withheld_tips`).
  - A notice whose whole text is one word that can be a handle reads "A one-word notice the
    dashboard does not show (it may be a player's name)" and is counted in `withheld` (the
    game's `hud_law_InfractionWarning` is "%ls", and what it holds is not known).
  - The game's own texts of these families that name nobody ("You have left the party.",
    "Party Disbanded: Leader Disbanded Party", "Your Rescue Beacon has been accepted. Assistance
    is on the way.") are shown as they are and not counted: `law.NAMELESS_TEXTS` holds 81 of
    them under 87 `global.ini` keys.
  - A word is learned as a name only from a name slot of a recognized shape, when it can be a
    handle (letters, digits, `_`, `-`, 3 to 60, at least one letter) and is no word of a place,
    jurisdiction, maker, ship, commodity, shop or contract giver in the reference tables, no
    plural of one ("Drakes"), and not on a short stoplist ("the", "your", "player", "security",
    "officer", "captain", "turret"…): a victim of more than one word is never learned. A word the
    parser can only guess at (a shape it does not read) must also be no word of the game's
    notices (`scdash/notice_words.txt`, 3,189 words read from `global.ini`: "Share",
    "Contract", "Beacon", "Request").

Known limits, not fixed:

- A player whose handle is a common word ("Long", "Forest"), learned from another kind of line
  (a killer, a channel owner), has that word replaced in other texts too: "MIC-L2 Long Forest"
  can read "MIC-L2 another player Forest". The scrubber errs toward hiding. From law and comms
  notices such a word is never learned.
- A one-word NPC victim that is no game word, no plural of one and no role on the stoplist may
  be learned as a name, with the same effect.
- A forgotten name that is not made of handle characters (a killer's name with a space, a dot
  or an accent) is taken out of every text held when it is forgotten, but not out of a text met
  later. Real handles are made of handle characters.
- Two names that overlap in one text ("Bob-Smith" and "Smith-Jones" in "Bob-Smith-Jones") are
  replaced as far as the first goes: "another player-Jones" (the pattern replaces the longest
  name at the leftmost place, as a word would be).
- A notice of a family with no cue the parser knows (an invented "<name> Hurston", "<name>'s
  Hangar") is shown as written: the families are only as complete as the game text read.
- The shapes of the objectives a player bounty uses are not in the game's text: the generic
  bounty objectives ("Locate <target>", "Neutralize <target>", "Locate and neutralize
  <target>") are assumed, and any other objective of such a contract is withheld.
- An alert counted from its event's time shows while `now` is before that time (a clock behind
  the log's); a reread still raises nothing old.

## What is unverified, and how it is marked

None of these line shapes is in the project's record of the user's logs; each is in the game's
own text, or read by other tools (dashboard/SURVEY.md). The code marks each where it is defined,
the tests on them say "unverified" in their names, and their samples are `tests/samples/built_*.log`.
Lean on them lightly in the design.

| What | Where it shows | Marked in the payload |
| --- | --- | --- |
| Hauling drop-offs ("Deliver 0/177 SCU of … to …"), and the per-drop index | Cargo `stops`, `this_stop`, `contract_total` | `verified: false` on each stop; `cargo.unverified` |
| The user's kills (killer id on `<Vehicle Destroyed>`; crippled at level 1) | Combat `tally.destroyed`, `tally.crippled` | `tally.kills_verified: false` |
| Contract failed or withdrawn notices, `CompletionType[Fail]` and `[Deactivate]` | Alerts, contract `status` | none; the words are the game's |
| Objective failed or withdrawn | Contract objectives, `state: "failed"` | none |
| The law notices: CrimeStat, crime committed, a crime against the user, fined, impounded, monitored space down | Alerts, Combat `law` | none |
| Pay ("Awarded <n> aUEC") | Contract `reward`, Cargo `earned`, alerts | none |
| A commodity sale's quantity read as SCU (the line prints no unit; the one sample's box data does not fit) | Selling `sold`, the feed | `selling.unverified` |
| A death read from the body item, which starts a burst of its own (gear lost alone is no death) | Deaths, the Dead alert | none |

Also from the reference tables, each with its own caveats there: a contract's kind when its
contract name is not in the table (generator, title and rules steps), a ship's cargo grid (some
from a cargo-grid record tied by name), refinery bonuses and prices (crowd-reported, dated).

## Additions to the state (`State.to_dict()`)

New keys, all scrubbed like the rest: `tally` (`destroyed`, `crippled`, `lost`, `downed`), `law`
(`{"t", "kind", "text", ...}`: `crime`, `crimestat`, `attacked`, `fined`, `impounded`), `rewards`
(`{"t", "amount", "mission_id"}`), `ship_left` (`{"name", "vehicle_id", "class", "t", "code",
"body", "where"}` or null), `unmapped_contracts`. Contracts gain `kind`, `view`, `setting`,
`giver_name`, `type_name`, `lookup` (which step of the table's lookup answered), `unmapped`,
`touched` and `reward`; their objectives gain `done` and `stop`. `ship` gains `info` (`class`,
`name`, `job`, `note`, `fleet`, `cargo_scu`, `kind`, `variant`, or null). Trade rows gain `at`
(the inventory location before the line), `shop_info` (`kind`, `name`, `place`, `place_name`,
`place_from`), and for commodities `commodity`, `scu`, `per_scu` (purchases) and `scu_verified`.
`zone` gains `monitored_down` and `t`; `monitored_down` is reset on a return to the menu, a
server join and a disconnect. An open quantum target is closed by a return to the menu, a
disconnect, a server join and a respawn, so it no longer brings the Travel view back.
`session` gains `withheld` and `withheld_tips` (the counts under "Limits" above). `server` is
`{joined, count}`: when the last server was joined and how many were. The shard names (`shard`,
`shards`), which say which servers the user was on, are in the private form only
(`to_dict(private=True)`); the feed line reads "Joining a server", and the summary's `servers`
(in `data/sessions/`) is the count. `timeline` still prints the shard names (a local console
tool).

## The message and the endpoints

*Added 2026-11-28 with the service's wiring (`scdash/service.py`, `scdash/server.py`), and
corrected after its review's fix round the same day. Read from the code and checked by
`tests/test_wiring.py`, `tests/test_server.py` and three real sessions replayed through the
service; every answer quoted in the endpoint table below was also seen from a running instance
(a temporary data folder, a free port, a sample log, 2026-11-28), except the 503s, whose windows
are too short to hit by hand: those are read from the code and checked by `test_wiring`
(`FirstRead`, `StopAndChanges`, `LockAndCatchUp`).*

### The message

One event-stream message (`event: state`, one JSON line) on `GET /api/stream`, and the same text
on `GET /api/state`:

```json
{"service": {"mode": "live", "pid": 4242, "started": "2026-11-26T23:05:00.000Z", "game_running": true,
             "game_since": "2026-11-26T23:11:20.000Z", "log_found": true, "replay": null, "terminal": false},
 "clock": {"rate": 1.0, "real": 0, "virtual": 0, "session_end": null},
 "flags": {"hangar_stuck": false},
 "state": {"schema": 1, "session": {"…": "…"}, "feed": ["…"], "…": "…"},
 "board": {"schema": 1, "view": {"name": "mining", "…": "…"}, "model": {"…": "…"}, "…": "…"}}
```

| Key | What it is |
| --- | --- |
| `service` | `mode` (`live` or `replay`), `pid` and `started` (which instance sent it: the page reloads itself when they change, because a restarted service has a new token), `game_running`, `game_since`, `log_found`, `replay` (null live; in a replay `{"source", "speed", "from", "to", "done"}`), `terminal` (the terminal region is laid out). |
| `clock` | The page's "now" is `virtual + (Date.now() - real) * rate`: the system clock live (`rate` 1, `real` and `virtual` 0), the replay's clock in a replay (`rate` 0 once the replay is over). `session_end`: milliseconds, once the game is not running, else null. |
| `flags` | Facts that need the clock and are not in the board: `hangar_stuck`. |
| `state` | `State.to_dict(private=False)`: the stage 2 state, with the stage 3 additions above. The page reads two parts of it, below. |
| `board` | The payload this file describes, **never null**. If `board.build` itself raised (it is documented never to), or returned something JSON cannot hold, it is the failed payload's shape, with the same keys as any other: an empty Now view, `view.rule` `"error"`, `strip` null, `timers` and `alerts` empty, and `problems` `["service: <exception type>"]`; the service builds it again a minute later, not before. |

**What the page reads from `state`** (everything else it draws comes from `board`):

- `state.feed`: the session's last 50 feed lines (`config.FEED_LEN`), oldest first, each
  `{"id", "rev", "t", "session", "offset", "kind", "level", "text"}`. `id` is unique in the
  session and stable across rereads; `rev` goes up when a line already sent changes (a jump's
  line gets its route and fuel a moment later): replace the line drawn under that `id`. `t` is
  ISO 8601 UTC with milliseconds; `level` is `alert`, `major` or `minor` (the page leaves minor
  lines out); `kind` is the event's kind, which picks the line's icon; `text` is scrubbed like
  every other text.
- `state.preflight`: `{"ok", "text", "order", "missing"}`. `ok` is true (the AB6 and the MTQ are
  both listed), false (one is missing) or null (no joystick lines yet); `order` is `"usual"`,
  `"differs"` (both there in another order: a pass, shown as a quiet "other order") or null;
  `missing` lists the missing devices' names. The strip's Pass or Fail comes from `ok`; the red
  alert and the Preflight view come from `board`.

When a message is sent:

- Only when its text differs from the last one, and merged to at most two a second per page
  (`push_min_seconds`). `retry: 3000` comes first, at most 4 pages on
  the stream at once (`max_pages`). A fifth gets a 503, which an EventSource does not retry by
  itself: `app.js` tries again every 5 s. Every open tab on the dashboard holds one of the four,
  and a browser allows about six connections to one address across all its tabs.
- **A keepalive event, not a comment** (since 2026-11-28): `event: keepalive` with the interval in
  seconds as its data (`data: 15`, the `keepalive_seconds` setting), right after `retry:` and then
  whenever nothing was written for that long; it adds no write while states flow. A page that
  hears neither a state nor a keepalive for two intervals plus 3 s (33 s) counts the service as
  gone, a hung one with the stream still open included: the offline banner, then a new stream.
- The board is built again only when one of its inputs changed (an event applied to the state, a
  session that ended in the same file, `plan.json`'s plan or notice, the user block, whether the
  game runs) or when the service's clock has reached the last payload's `next_change_ms`. Bytes
  read that make no event change nothing.
- `plan.json` is looked at once a second while the game runs and about every 10 s when it does
  not (one `stat`; it is read only when its size or time changed).
- **Nothing half-read.** While the service catches up on a large log (a restart in the middle of
  a session), no message goes out for the first 2 s, then one every 2 s at most: an alert that
  ended long ago (a downing) must not flash up. A catch-up that long needs a log of a few hundred
  MB, and its messages every 2 s are half-read ones. With the game running, the first message
  comes after the first read (no game: after the last log has been read once), so a page never
  gets an empty state from a restarted service, and the four changing routes answer 503 until
  then (below), so no change can publish a board built on nothing.
- **Every text encodes and every number parses.** A lone surrogate from a plan, `state.json` or a
  request body (`"\ud800"` is valid JSON) is sent as U+FFFD, and a number that is not finite as
  null, so the browser's `JSON.parse` never fails on a message. The same holds for every answer
  below and every file the service writes.

### The endpoints

Every request needs exactly one `Host` of `127.0.0.1:<port>` or `localhost:<port>`, and a
`Sec-Fetch-Site` other than `same-origin` or `none` is refused on every route. A **changing**
request also needs the `X-SCDash-Token` header (the page has the token in
`<meta name="scdash-token">`; it is never accepted in a URL), an `Origin` of this server, exactly
one `Content-Type: application/json`, a `Content-Length` of ASCII digits, and a body that is a
JSON object with exactly the listed fields (an unknown or a missing one is a 400).

| Method and path | Body | Answer (200) |
| --- | --- | --- |
| `GET /`, `/app.js`, `/style.css` | - | The page; the HTML carries the token and the Content-Security-Policy below. |
| `GET /rig/rig.json` | - | The rig reference's data (`application/json`), written by `tools/regen_cards.py`. |
| `GET /rig/<name>.png` | - | A diagram, for each view's `image` in `rig.json`. Take the names from `rig.json`; do not write them into the page. |
| `GET /api/health` | - | `{"program": "scdash", "pid", "started"}` and nothing else. |
| `GET /api/status` | - | The instance's figures (what `scdash.py status --json` prints under `status`), with `session` `{id, game, last_event, events, unreadable, withheld, withheld_tips}` (`withheld`: notices and objectives of a shape that may name a player, not read; `withheld_tips`: tip-shaped ones, never shown), `board` `{view, auto, rule, why, picked, builds, next_change, problems, problem_list}`, `plan` `{path, loaded, notice, updated, run}`, `user` `{read, quick_timers, pick}` and `reference_tables`. Every path in it (`data_dir`, `python`, `log.path`, `plan.path`) shows the user's profile folder as `%USERPROFILE%`, which keeps the Windows user name out. |
| `GET /api/state` | - | The last message, or 503 `{"error": "no state yet"}` before the first one. |
| `GET /api/stream` | - | The event stream above. |
| `POST /api/view` | `{"view": "<name>"}`, one of `now`, `travel`, `mining`, `salvage`, `combat`, `cargo`, `mission`, `refinery`, `selling`, `preflight`, `idle`, `reference` | `{"ok": true, "view": {"name", "auto", "picked"}}`. Any other name is a 400 that lists the twelve. **503** `{"error": "still reading the log: pick again in a moment"}` while the service is catching up on a large log: a pick is kept under the context it was made in, and on a half-read state it would be dropped at once. |
| `POST /api/view/live` | `{}` | `{"ok": true, "had_pick": <bool>, "view": {...}}`: the hand pick (the reference cards included) is forgotten and the rules choose again. `had_pick` says whether the user block held now had a pick; while `state.json` is unread, the change is recorded anyway and applies to the file's pick once it is read, so `false` then does not mean nothing will be dropped. |
| `POST /api/timers/add` | `{"label": "<1 to 60 characters>", "minutes": <0.5 to 1440>}` (a number; `true` is not one) | `{"ok": true, "timer": {"id", "label", "ready_at"}, "view": {...}}`. The `id` is `quick:q<ms>`, or `quick:q<ms>-<n>` when that one is taken: keep the one the answer or the payload gives. Lone surrogates are taken out of the label, and control and bidi characters too (the answer's `label` is the cleaned one). 400 `"label must be a text of 1 to 60 characters"` for one longer, empty or only spaces (before or after the surrogates go); 400 `"label must have at least one visible character"` for one with no letter, digit, punctuation or symbol (only zero-width characters, a soft hyphen, tag characters or a combining mark alone, for example). At most 10 quick timers: the oldest goes. |
| `POST /api/timers/remove` | `{"id": "quick:<id>"}`, the `id` the payload's timer carries (`quick:` and 1 to 48 of `A-Z a-z 0-9 _ . : -`, else a 400) | `{"ok": true, "removed": <bool>, "view": {...}}`. Removing one that is not there is no error. `removed` says whether the user block held now had it; while `state.json` is unread, the removal is recorded anyway and applies to the file's timers once it is read. |
| `POST /api/shutdown` | `{"reason": "<text>"}` (optional) | `{"ok": true, "pid"}`; the service stops. For the commands, not the page. |

**The four changing routes can also answer 503**, each as `{"error": "<reason>"}`, and each means
"nothing was changed: try again in a moment":

| Reason | When |
| --- | --- |
| `still reading the log: try again in a moment` | Before the service's first read of the log has reached its end (with the game running, the first message comes then; after a restart mid-session that can be the whole catch-up). A change made on an empty state would publish a board built on nothing. A first read that fails counts as done (with no game, once its retry on the next turn fails too), and so does one that reached the end in a turn that failed afterwards, so a failing log or a failing later step never locks the page out. |
| `shutting down` | Once a stop has been asked for (`stop`, the shutdown endpoint, a signal). A change already being made then is finished and is in the last save (unless that save's write does not end within 30 s: the stop does not wait longer). |
| `busy reading the log: try again in a moment` | The service's main loop held its lock for more than 5 s: it reads the rest of a log in one turn when the game exits, and the last log at start with no game. Only a log of hundreds of MB takes that long (not measured). |
| `still reading the log: pick again in a moment` | `/api/view` only, while catching up (the row above). |

`view` in an answer is the view the page will be shown after the change: the next message
carries the change already, and normally `state.json` has it on disk before the answer goes
out. The answer waits for that write (and for one already in flight), but the write is made
outside the main loop's lock, so a slow save of `state.json` delays answers and never the loop or
another change's turn under the lock. Rarer writes still run under the lock (`unmapped.json` when
something new is first seen, a session summary): a change can wait behind one (2.7 s behind a
mocked 3 s write, the review's second round), and past 5 s it gets the "busy" 503.

**A 200 does not always mean on disk.** It means the change was made: it is kept in memory and
in the next message, and it is written when a save next succeeds. Three cases where it is not on
disk yet when the answer goes out:

- **While the service catches up on a large log**, after its first read: the board is rebuilt,
  the message sent and the file saved once it has caught up (or with the next half-read message
  2 s later), so the answer's `view` can be the one before.
- **When saves of `state.json` fail** (the file held by another program, a full disk), the
  change's own write included: the answer is 200 all the same, and the loop tries the save again
  every 10 s (`state_save_seconds`) until one succeeds; a change made while saves are failing
  does not try a write of its own.
- **While `state.json` cannot be read yet** (held without sharing, a folder in its place, or
  damaged and not yet moved aside): it is never saved over unread. The change is in the next
  message and is recorded (the last 100 changes), then applied, in order, on top of what the file
  holds once it can be read, and saved.

**Errors.** Every error answer is `{"error": "<reason>"}`:

| Status | When |
| --- | --- |
| 400 | A bad target; a body cut short, not JSON, nested too deeply, not an object; a field missing, unknown or out of range (the reason names it); a timer label with no visible character. |
| 403 | A wrong or doubled `Host`; a `Sec-Fetch-Site` from another site; a wrong, doubled or (on a change) missing `Origin`; the token missing, doubled or wrong. |
| 404 | No such path (a request path is only looked up in a fixed table: no file outside it can be reached). |
| 405 | A method the path does not take (`HEAD` included). |
| 411 | No `Content-Length`, or one that is not ASCII digits. |
| 413 | A body over 64 KB. |
| 415 | No `Content-Type: application/json`, or two of them. |
| 431 | A request head over 16 KB or 40 header lines. |
| 503 | Busy or not ready: 16 requests at once; 4 pages on the stream; `/api/state` before the first message; on a changing route, the four reasons in the table above (before the first read, shutting down, the lock held over 5 s, a pick while catching up). Try again. |
| 500 | A fault in the handler (logged). |

**From the page.** `window.scdash.post(path, body)` sends a changing request with the token and
resolves to the parsed JSON answer **whatever the status**: check `answer.ok` (or
`answer.error`), not whether the promise was fulfilled. It rejects only when no answer came
within 8 s (`REQUEST_SECONDS` in `app.js`; the service may be gone, and the stream's banner shows
that too) or the answer was not JSON. The page's own changes use `request()`, the call under it,
which resolves to `{status, answer}` so that a refusal can be worded by its status (503, 403,
400).

**The content policy** sent with the page: `default-src 'none'; script-src 'self'; style-src
'self'; img-src 'self' data:; connect-src 'self'; base-uri 'none'; form-action 'none';
frame-ancestors 'none'`. So the page may load `/rig/*.png` and fetch `/rig/rig.json` from the
server itself, and nothing from anywhere else; no inline script or `style` attribute (set a meter
with `element.style.setProperty("--v", fill)`). Proved in headless Edge on 2026-11-28: both
images loaded, `rig.json` fetched, and an image and a fetch from another origin were blocked
with a policy violation each.

**The rig files** are the ones in `web/rig/` when the service started: `rig.json`, and each
image named in lower-case ASCII letters, digits and underscores with `.png`, a plain file of at
most 1 MB (64 images at most). A plain file is not a junction, a symbolic link or any other
reparse point, and has a single name: a hard link is not served either, at the start or at a
request. A file changed under the same name is served fresh at once; a new or renamed image is
served only after the service is restarted (`stop`, then `start`).
