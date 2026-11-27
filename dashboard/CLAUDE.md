# `dashboard/` — working notes for Claude

**Only stage 1 exists** ([`PLAN.md`](PLAN.md) §12): the part that reads `Game.log` and turns it into
events, a state and a printed timeline. There is no service, no web server and no page yet; stages 2
to 7 build on what is here. The human-facing page is [`README.md`](README.md).

Three rules that hold for everything in this folder:

- **The repo is public.** The user's handle, Windows user name, PC name, account id, player id,
  session ids, server addresses and other players' names never go into a tracked file: not code,
  not docs, not test samples. Play data goes in `dashboard/data/`, which git ignores.
  `tests/test_privacy.py` checks every publishable file under `dashboard/`.
- **Read-only toward the game.** Nothing under `LIVE\` outside this folder is written, moved,
  renamed or locked, and `Game.log` is never held open between polls (PLAN §8).
- **Play data stays in `data/`.** It is the only place the program may write private data.

## Module map

| File | What it does |
| --- | --- |
| `scdash.py` | Command line, run from the project root. Stage 1 has one command, `timeline`. |
| `scdash/config.py` | Paths (LIVE found from the repo's place, or `SCDASH_LIVE`), read sizes, caps, the expected joysticks. |
| `scdash/winutil.py` | Windows-only calls with a plain fallback: `open_shared()` opens a file sharing read, write and delete. |
| `scdash/tail.py` | `Follower`: each poll opens the log, compares its first line, reads past the saved offset in pieces of at most 1 MB, closes it. Holds a partial last line; cuts lines over 64 KB. Part adapted from CSR. |
| `scdash/records.py` | Line to `Record`: fixed-width time, level part, tag; joins continuation pieces; the one cheap table lookup that drops most lines. Part adapted from CSR. |
| `scdash/events.py` | Record to typed event, one kind per marker; the key table; `EventParser`; `session_id()`. Several line patterns and the notice cleaning adapted from CSR. |
| `scdash/state.py` | Events to state (`State.apply`, `build_state`), `clock_facts(state, now)`. Part adapted from CSR. |
| `scdash/names.py` | `LocationNames`: display names from `reference/locations.json` (owned by another agent), raw code when unknown. |
| `scdash/words.py` | Local time, durations, money, ship class names, `compatible(channel name, class)`. |
| `scdash/summary.py` | `build_summary(state, complete, last_line_t)`: the compact session record for `data/sessions/`. No player names. |
| `scdash/pipeline.py` | `LogReader`: follower -> records -> events -> state. What the stage 2 service drives. `read_whole()`. |
| `scdash/timeline.py` | The `timeline` text and JSON, and the session list (`--list`). |
| `THIRD_PARTY_NOTICES` | CSR's MIT license and what was adapted where. `tests/test_credit.py` keeps it honest: a file with a "From CSR" mark must be listed, and a listed file must carry the copyright line. |
| `tests/` | `unittest` suite, sanitized samples in `tests/samples/` (kept byte-exact by their `.gitattributes`), `sanitize.py` to make new ones. |

`scdash.py` sits beside the package folder `scdash/`. With `dashboard/` on `sys.path`, `import
scdash` finds the package because a package directory wins over a module file of the same name;
that needs `scdash/__init__.py` to exist. `tests/test_timeline.py` runs the script from the root
and from inside `dashboard/` to prove it.

## Running

```sh
python -m unittest discover -s dashboard/tests          # the whole suite, from the project root
python dashboard/scdash.py timeline                     # the current Game.log
python dashboard/scdash.py timeline "26 Nov 26 (15 11 12)"   # a backup, by a piece of its name
python dashboard/scdash.py timeline <log> --json        # the same as data; --all adds minor lines
python dashboard/scdash.py timeline --list --since 2026-11-26   # sessions: local start, length, how it ended
```

`--list` reads only each file's first 4 KB and last 64 KB (`<SystemQuit>` was always in the last
714 bytes), so it lists all 409 backups in about 0.2 s. A `PSOCacheGen ...log` is skipped by name:
its first line looks like a session's. The suite takes about 10 s: the 100 MB flood test
(`SCDASH_FLOOD_MB` makes it smaller) and the privacy test, which learns names and ids from the
newest local logs for up to 4 s, take most of it. `tests/test_reference.py` belongs to the agent
that builds `reference/`.

## Interfaces stage 2 will call

- `LogReader(path, names, opener=open_shared)`:
  - `.poll(budget=None)` once a second returns `'missing'`, `'waiting'`, `'idle'` or `'read'`.
  - `.state` is the current `State`.
  - `.take_lines()` gives the feed lines new or changed since the last call, each once.
  - `.take_finished()` gives summaries of sessions that ended because a new one began in the
    same file (to write to `data/sessions/`).
  - `.summary(complete)` is the current session's summary. A session that simply stops (a game
    crash) never reaches `take_finished()`: when the game process is gone, stage 2 calls
    `.summary(complete=True)`, which ends the session at the time of its last line.
- **Feed lines** have `id`, `rev`, `t`, `session`, `offset`, `kind`, `level`
  (`alert`/`major`/`minor`) and `text`.
  - `id` is unique within the session and stable across rereads: the event's offset and a small
    index, so a recovery line and its event's own line differ.
  - A line can change after it was handed out: a jump's line gets its route and fuel a
    millisecond later. It then comes out of `take_lines()` again with the same `id` and a higher
    `rev`; the page replaces the line it has.
- `State.to_dict(private=False)`: the state as JSON, with every other player's name the session
  has seen replaced by "another player" in every text (contract titles included). `private=True`
  keeps them and adds `me` (handle, player id), for memory only. `build_summary` scrubs the same
  way.
- `State.unmapped()`: location codes with no name, for `data/unmapped.json`.
- `clock_facts(state, now)`: everything that needs "now" (session length, time in the world,
  hangar queue waited and stuck). The state itself never reads the clock; a test walks the source
  of records, events, state, summary, words and names for clock calls.
- `State.apply(event)` is for log events only. The telemetry source (stage 6) gets an entry point
  of its own, so that it cannot move the session's last-event time or event count.
- **No line can stop or stall the reader.** A line that cannot be read becomes an `unreadable`
  event, counted in `state.session["unreadable"]` (for `status`); a failure while applying an
  event is counted there too. The follower settles its offset before handing lines on.
- Stage 3 slots: `state.plan`, `state.timers`, `state.alerts`, `state.view` exist and are empty.

Every event is a frozen dataclass with `session` (the backup name the game gives the log) and
`offset` (byte offset of its first line): together its identity. `Event.to_dict()` and
`events.event_from_dict()` round-trip.

## Measured (stage 1, game not running, 2026-11-27)

- All 409 files in `logbackups` plus `Game.log` parsed with no exception; the 404 files under
  10 MB (669 MB) took 3.4 s together.
- The largest log (377 MB, an error flood from March 2026): 1.04 s (about 360 MB/s), peak private
  memory 21.5 MB against 16.5 MB before reading. The same peak for every large file from 10 MB to
  377 MB: memory does not grow with the log.
- Importing the package costs about 4.8 MB; loading `locations.json` (3,415 codes then) about
  2.4 MB more. Bare Python was 8.6 MB.
- Random-piece reading equals one pass on all 69 logs of 2026-11 (pieces from 1 to 200,000
  bytes).

## What the logs showed that PLAN.md did not say

Counts are from the 69 logs of 2026-11 (2026-11-05 to Game.log of 2026-11-27), marked [seen];
my own readings are marked as such.

- **Notice counts in PLAN §3 are physical lines.** Each notice is logged up to three times, so
  "272 Contract Accepted" is 39 notices; Contract Complete 13, New Objective 85, Objective Complete
  33, refinery notices 8 single and 1 plural.
- **`Spawned!` also marks the main menu**, at every launch and after every return to the menu. The
  game world is the `Spawned!` after `<Join PU>` (or `ConnectCmd`, for Arena Commander); one while
  already in the world is a respawn, and all 44 of those followed a downing or a death.
- **`SetVehicleSpawningInformations` is split over two lines** too (78 of 80): the second line
  is the hangar size, the first ends with the owner's handle. The continuation rule covers it.
- **A continuation piece is not always the very next line:** once in 2,086 notices a
  `<Vehicle Destroyed>` line sat between the two pieces, and 12 of 191 pieces are 1 ms later.
- **Plotting a route logs route lines too.** "Player Requested Fuel to Quantum Target" (plotting
  only) is followed by `<Calculate Route>` lines, so a route line is never a jump: only "Player
  Selected Quantum Target" is, and route lines fill in the jump they name.
- **A carrier logs its passenger ship's selection.** At 8:11:25 PM on 2026-11-20 the M80 and
  the Liberator carrying it logged the same target in the same millisecond, with route lines for
  both. The state folds them into one jump that belongs to the ship whose channel the user
  joined (`words.compatible`).
- **Downed is not dead.** Of 36 "Incapacitated" notices, 26 were followed by a respawn, 8 by
  normal activity with no respawn, 1 by a quit and 1 by a disconnect. The emergency-services
  notice preceded a respawn 23 times of 23. One item-recovery burst was not the user's (no
  respawn, a jump 2 minutes later). The state closes an incident as a death on respawn, as a
  recovery on activity.
- **"Medical Bed: ... restored" repeats every 120 s** once a bed has been used (34 gaps). After
  a downing it came 7 times; 6 of those had no respawn after it, and once a respawn came 9 s
  later anyway. My reading: the bed ends the downing, but the incident stays open, so a respawn
  soon after is still a death.
- **The place is the landing id.** `Update Inventory Location ... Landing [a] -> [b]`: `b` is the
  place the user is landed at, 0 in flight; walking between New Babbage's city and a
  sub-location changes only the `Location` part. `RequestLocationInventory` names the place and
  also fires when the storage screen opens. Before a respawn, the respawn place is logged a few
  ms before `Spawned!`. 4 of 42 respawns logged no place within a minute (my guess: a respawn in
  a ship's medical bed in space).
- **The storage "Item Count" follows the screen's filter**: 156, 34, 42, 156 within 70 s with
  nothing moved. It is not the stock.
- **`<SystemQuit>` reasons:** "Quit via console command" and "User closed the application" (12
  logs). 68 of 69 logs have one; the other is a 243-line launch that died at once.
- **Disconnect causes** besides PLAN's: 41058 "Player Query failed" (once).
- **Quantum codes** come in more families than two: `NewBabbage_LOC`, `NavPoint_Dynamic_<n>`
  and `MISSION_QT_Quantum_Beacon_LongRange_<n>` (made per mission, never "unmapped"),
  `ObjectContainer_RestStop`, and `rs_ext_...` (gateways and stations). 4 of 83 arrival lines
  named a ship other than the one that chose the target.
- **`PlayerPilot: 1` on a `<FatalCollision>` line** makes it the user's crash: all 4 of 2026-11
  were the user's own ship. Whether the game ever logs it for someone else's ship with a player
  at the controls is unverified.
- **The game writes U+FFFD itself** in some text ("Jurisdiction:�Hurston Dynamics"); strict
  decoding never failed.
- **A self-destruct's "killer" can be another player's name** (the user's own Pisces, 2026-11-23).
- **Player names appear in at least 28 contexts** (`tests/sanitize.py` `NAME_CONTEXTS`), for
  example `<Actor Position Divergence> [<name>]` and `User: <name>, Client: <name>`.
- **The preflight check fails on 12 logs in `logbackups`**, each with the AB6 missing from the list:
  2026-02-02, 02-04, 03-08, 03-15 (twice), 04-03, 06-24, 06-25 (twice), 08-22, 08-23, 11-24. In
  February to April the keyboard did not enumerate at all, so the MTQ became joystick 1.
- **`LOC_RR_*` quantum codes are the station's marker.** A mining run to "ARC-L4" arrives at the
  marker named for the station; the field is thousands of km further.

## Making test samples

Samples are real lines with every personal value and every id replaced. Use
`tests/sanitize.py` (learns names from every context in `NAME_CONTEXTS` and ids from the whole
log, replaces them consistently, refuses to print if a learned value is left), then **read every
line yourself** before committing: a new kind of line can carry a new kind of value, and a new
context goes into `NAME_CONTEXTS`, which the privacy test uses too. Keep samples small. After a
game patch, regenerate the samples from fresh logs and run the suite: markers do vanish or change
between patches.
