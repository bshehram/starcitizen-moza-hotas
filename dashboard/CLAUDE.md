# `dashboard/` — working notes for Claude

**Stages 1 and 2 exist, and stage 3 up to the page** ([`PLAN.md`](PLAN.md) §12): stage 1 reads
`Game.log` and turns it into events, a state and a printed timeline; stage 2 is the background
service, its local web server and a first page (the status strip, alerts and the event feed in
design direction B, with a "Now" placeholder where stage 3's views go). **Stage 3's logic** (events
for the other activities, the plan loader, alerts, timers, the view rules and a model per view,
behind `board.build`) **is wired into the service** since 2026-11-28: the service builds the board
from the state, `data/plan.json` and the user block, sends it as `board` in every message, takes
four changes from the page (pick a view, back to Live, add and remove a quick timer), records
unmapped contracts, and serves the rig reference's files from `web/rig/` ("Stage 3 in the
service" below; the message and the endpoints are in [`STATE.md`](STATE.md)'s last section).
**The page still has no views:** it draws stage 2's strip and feed and ignores `board`.
**Stage 4's window half exists** since 2026-11-28: `open` shows the page in Edge's app mode (and
starts the service first if needed), and `shortcut` writes a `.lnk` that runs it through
`pythonw` for the taskbar ("Stage 4: the window" below). There is no autostart (the logon task)
and no terminal yet. A plain browser tab at `http://127.0.0.1:<port>/` is still a full client
(see "A browser tab instead of the window" below).
The human-facing page is [`README.md`](README.md).

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
| `scdash.py` | Command line, run from the project root: `run`, `start`, `stop`, `status`, `replay`, `timeline`, `open`, `shortcut`; `install`, `uninstall` are stage 4 stubs that do nothing. `start` and `open` share `_ensure_running()`. `HAS_CONSOLE` is read at import, before `__main__` points missing streams at the null device; `_Out` sends `open`'s messages to the console, or (none, under pythonw) to a message box and `data/service.log`. |
| `scdash/config.py` | Paths (LIVE found from the repo's place, or `SCDASH_LIVE`), read sizes, caps, the expected joysticks; the service settings `DEFAULTS` (with `window.browser` and `window.profile` for `open`) and `load_settings(data_dir, overrides)`; stage 3's service constants (plan look, catch-up, the lock waits of a change and of the last save, the last save's write, user ops, the user block's other keys, the largest data file read, the damaged copies kept, error repeats, rig file bounds). |
| `scdash/winutil.py` | Windows-only calls, each with a fallback: `open_shared()`, `InstanceLock` (named mutex), `process_list()`/`process_table()` (pid, name and creation time from one `NtQuerySystemInformation` call, no handle to any process; Toolhelp as the fallback), `process_created()`, `below_normal_priority()`, `exclusive_address()`, `own_memory()`; for stage 4 `monitors()` (bounds, work area, primary, scale, in physical pixels, read on a per-monitor-DPI-aware thread), `app_path()` (App Paths in the registry), `message_box()`, `desktop_folder()`, `write_shortcut()` / `read_shortcut()` (the shell's ShellLink COM object through ctypes, no PowerShell). |
| `scdash/window.py` | Stage 4's window: `find_browser()` (a named one, else Edge, then Chrome: App Paths, install folder, PATH), `profile_dir()`, `profile_in_use()` (Chromium's `lockfile` in the profile folder), `placement(monitors, portrait, main)` (pure: a centered window on the main screen, or a point inside the second display and full screen), `command()` (the exact command line), `launch()` (below normal, out of the caller's job, no console window), `describe()`. |
| `make_icon.py`, `scdash.ico` | The shortcut's icon and its generator (Pillow, which only this script imports): the ink-blue ground, the panes' corner brackets and a cyan segmented meter, each size drawn on its own pixel grid. |
| `scdash/server.py` | The web server: `Server` (its file table `files`: the page's three `FILES` plus `rig_files()`, built once; registered routes), the request guard (`READ`, `CHANGE`, `PRIVATE`), `Hub` (one event stream, with its own cap), `json_text()` / `encodable()` / `scrub()` (JSON that always encodes and parses; `scrub` and `_finite` stop at `MAX_DEPTH` = 64 levels, deeper becomes null, so neither can raise `RecursionError`), `json_depth_over()` (a depth check without recursion, for values read from a file), `_plain()` (no junction, link or other reparse point, and a file with a single name), `error_key()` / `remember()` (a repeating fault logged once). |
| `scdash/service.py` | The service: `Service` (life cycle, main loop, data files; stage 3: the plan look, the board, the four changing routes, the user block and its late merge, the saves as snapshots, unmapped contracts), `user_block_from_file()` (the block as stored, bounded), `apply_user_op()`, `visible()` (a label's test), `shown_path()` (paths in `status`), clocks and the replay feeder, and the helpers the commands use to talk to an instance (`instance_info`, `probe_health`, `launch_background`). |
| `scdash/telemetry*.py` | Stage 6's telemetry reader, written by another agent. Not wired into the service. |
| `web/` | The page: `index.html`, `app.js`, `style.css`. No framework, nothing from outside. |
| `config.example.json` | Every setting with its default and an explanation; copied to `data/config.json` to change one. |
| `scdash/tail.py` | `Follower`: each poll opens the log, compares its first line, reads past the saved offset in pieces of at most 1 MB, closes it. Holds a partial last line; cuts lines over 64 KB. Part adapted from CSR. |
| `scdash/records.py` | Line to `Record`: fixed-width time, level part, tag; joins continuation pieces; the one cheap table lookup that drops most lines. Part adapted from CSR. |
| `scdash/events.py` | Record to typed event, one kind per marker; the key table; `EventParser`; `session_id()`. Several line patterns and the notice cleaning adapted from CSR. |
| `scdash/state.py` | Events to state (`State.apply`, `build_state`), `clock_facts(state, now)`. Part adapted from CSR. |
| `scdash/names.py` | `LocationNames`: display names from `reference/locations.json` (owned by another agent), raw code when unknown. |
| `reference/` | Generic game data, generated by `reference/build_reference.py` from the installed game's files (`--check` says whether it is current; a run takes about a minute and peaks near 520 MB, so not while the game runs). `<name>.json` is output only, `<name>.hand.json` is the only place anything is typed. Tables: `locations` (codes, names, positions), `resources`, `ores`, `refineries` (yields, and `places` with a refinery), `controls` (per operator mode, from the card tables), `ships` (classes as the log prints them, cargo, the fleet's jobs), `contracts` (kind, view and on-foot or in-ship per contract; **`_meta.lookup` is the order a reader must follow**), `shops` (kind, and a place only when the name is unique to one). Prices are built too but live in the git-ignored `data/reference/prices.json`; only `--fetch` goes online. Loaded sizes after `json.load`: ships 1.1 MB, contracts 2.3 MB (1.2 MB slimmed), shops 0.3 MB, prices 1.0 MB. `scdash/refdata.py` loads the second-round tables, each when first needed. |
| `SURVEY.md` | What salvage, hauling, combat and missions leave in the log, with how each item is known, and the checks to run on new sessions. Stage 3's events come from it. |
| `scdash/refdata.py` | `RefData`: loaders for the second-round reference tables, each read when first needed and kept slim (contracts by the lookup order in `_meta.lookup`, ships, shops, resources, controls, ores, refineries, and prices when the git-ignored file exists). About 2.5 MB in all. |
| `scdash/law.py` | The shapes of the law and comms notices that can name a player (read from the game's own text), the game's crime names, and the rule for what may be learned as a handle: handle-shaped, not a word of the game, not on a short stoplist. |
| `scdash/plan.py` | `PlanStore(path).refresh()` and `normalize()`: `data/plan.json` read with bounds on everything, the last good copy kept, and a short notice that counts what was left out. `clean_user()` for the user block. `plan.example.json` has one run of each kind. |
| `scdash/rules.py` | The view rules as a table (`RULES`, first fit wins), the hand pick and the context that keeps or drops it, and the "reference" pick, which nothing drops. |
| `scdash/alerts.py` | Alerts (held while their condition holds, or timed from their event's own time) and timers (the plan's and the user's quick ones; a completion notice clears the earliest refinery timer it can belong to). |
| `scdash/views.py` | One ready-to-draw model per view, already worded and in display units. |
| `scdash/board.py` | **Stage 3's entry point:** `board.build(state, plans, user, now, game_running, tz=None)` returns the chosen view and why, its model, the strip, alerts, timers, the plan notice and the unmapped contracts. Pure, no clock, scrubbed, every text bounded; a part that fails is left empty and named in `problems`. `pick()`, `add_quick_timer()` and `remove_quick_timer()` make what the service saves in the user block. **[`STATE.md`](STATE.md) describes the payload exactly, with what is unverified:** the page is built from it. Called by the service (`Service._update_board`). |
| `web/rig/` | The rig reference section's data and diagram images, written by `../tools/regen_cards.py` (root [`../CLAUDE.md`](../CLAUDE.md) §8.5). `tests/test_rig.py` fails until they are regenerated after a card change. Served under `/rig/` by the folder's own contents (`server.rig_files()`): **a new or renamed image needs a restart of the service**. Not shown by the page yet. |
| `scdash/words.py` | Local time, durations, money, ship class names, `fit` and `compatible` (channel name against class; Mk forms normalized), `clean_text`/`clean_all` (control and bidi characters out). |
| `scdash/summary.py` | `build_summary(state, complete, last_line_t)`: the compact session record for `data/sessions/`. No player names. |
| `scdash/pipeline.py` | `LogReader`: follower -> records -> events -> state. What the stage 2 service drives. `read_whole()`. |
| `scdash/timeline.py` | The `timeline` text and JSON, and the session list (`--list`). |
| `THIRD_PARTY_NOTICES` | CSR's MIT license and what was adapted where. `tests/test_credit.py` keeps it honest: a file with a "From CSR" mark must be listed, and a listed file must carry the copyright line. |
| `tests/` | `unittest` suite, sanitized samples in `tests/samples/` (kept byte-exact by their `.gitattributes`), `sanitize.py` to make new ones. Stage 2's are `test_server.py`, `test_service.py`, `test_cli.py`, `test_replay.py`, with `test_service_helpers.py` (helpers, no tests); stage 3's wiring is `test_wiring.py` (and `RigFiles`, `RigFolderRule` in `test_server.py`); stage 4's window is `test_open.py` (a stand-in browser behind a `.cmd` records its command line; no real browser is started). |

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
its first line looks like a session's. `tests/test_reference.py` belongs to the agent that builds
`reference/`.

The suite takes about 3 min (520 tests in 182 s on 2026-11-28, with the game running). Stage 1's part is about 10 s
(the 100 MB flood test, which `SCDASH_FLOOD_MB` makes smaller, and the privacy test, which learns
names and ids from the newest local logs for up to 4 s); stage 2's process tests start and stop
real background instances (`test_cli.py` about 65 s, `test_replay.py` about 17 s, stage 4's
`test_open.py` about 35 s); stage 3's
`test_wiring.py` takes about 16 s (81 tests after the wiring review's two fix rounds, 2026-11-28). With 64 GB (since 2026-11-28) the suite needs no
`SCDASH_FLOOD_MB` while the game runs; on a PC short of memory, set `SCDASH_FLOOD_MB=5`.

The service (stage 2):

```sh
python dashboard/scdash.py start            # background (pythonw, no window); waits until it answers
python dashboard/scdash.py status [--json]  # pid, port, game seen, log offset, memory, CPU, pages
python dashboard/scdash.py stop             # stops it and writes data/stopped.json; `start` removes it
python dashboard/scdash.py run              # foreground until Ctrl+C, logging to the console too
python dashboard/scdash.py replay "26 Nov 26 (15 11 12)" [--minutes 1.5 | --speed 40] [--terminal]
python dashboard/scdash.py replay <log> --plan dashboard/plan.example.json   # with a plan of its own
python dashboard/scdash.py open [--portrait] [--main] [--browser <program>]   # the window (stage 4)
python dashboard/scdash.py shortcut [--desktop] [--folder <dir>]   # SC Dashboard.lnk, running `open` via pythonw
```

Every service command takes `--data <folder>` (default `dashboard/data`); `run` and `start` also
`--port`, `--log`, `--live` and `--process`. An instance belongs to its data folder: the mutex name
is a hash of the folder, so tests and replays run beside the live one. Tests always pass a
temporary folder, a free port and a log of their own, and never touch `dashboard/data`, port 47826
or the real `Game.log`. `replay` refuses the live port and any folder inside `dashboard/data`, uses
port 47827 and a temporary folder by default (removed afterwards unless `--keep` or `--data`), and
writes the past log into `<data>/replay/Game.log` as its clock reaches each line, so the normal
follower reads it. **A replay never reads `data/plan.json`:** `--plan <file>` copies a plan
(refused over 1 MB, never through a link) to `<data>/replay/plan.json` and the board uses that;
without `--plan` a copy left there by an earlier replay is removed, so there is no plan. The board
runs on the replay's clock.

## Interfaces from stage 1 (what the service calls)

- `LogReader(path, names, opener=open_shared)`:
  - `.poll(budget=None)` once a second returns `'missing'`, `'waiting'`, `'idle'` or `'read'`.
  - `.state` is the current `State`.
  - `.take_lines()` gives the feed lines new or changed since the last call, each once.
    **They are the lines as read, other players' names included: never send them to the page,
    write them to a file or log them as they are.** The service uses the call only as a signal
    that something changed; the page's feed comes from `State.to_dict(private=False)`, which is
    scrubbed (stage 3 review).
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
  has seen replaced by "another player" in every text (contract titles included). The user's own
  handle is replaced by "you" the same way. `private=True`
  keeps them and adds `me` (handle, player id), for memory only. `build_summary` scrubs the same
  way. Either way, and in everything `timeline` and `status` print or dump, no text carries a C0 or C1
  control character or a bidi control (U+202A-202E, U+2066-2069, U+200E/200F/061C):
  `words.clean_text` takes them out where text leaves the state, so nothing in the log can steer a
  console or reorder the page's words.
- `State.unmapped()`: location codes with no name, for `data/unmapped.json`.
- `clock_facts(state, now)`: everything that needs "now" (session length, time in the world,
  hangar queue waited and stuck). The state itself never reads the clock; a test walks the source
  of records, events, state, summary, words and names for clock calls.
- `State.apply(event)` is for log events only. The telemetry source (stage 6) gets an entry point
  of its own, so that it cannot move the session's last-event time or event count.
- **No line can stop or stall the reader.** A line that cannot be read becomes an `unreadable`
  event, counted in `state.session["unreadable"]` (for `status`); a failure while applying an
  event is counted there too. A time outside 2015-2099, and a number that is not finite or longer
  than 30 characters, also make a line unreadable. The follower settles its offset before handing
  lines on. `to_dict()` carries the count as `session.unreadable`, and `status` reads it there.
- **The preflight check** (`state.preflight`: `ok`, `text`, `order` "usual" or "differs",
  `missing`). The preflight check passes when the AB6 and the MTQ both appear in the
  `Connected joystick` lines, in any order: a different order is a note, not an alert. The
  keyboard, MTQ, AB6 order worked on 2026-11-27 by the user's report, reason unconfirmed. It fails
  red only when either device is missing, as in the twelve AB6-missing launches in logbackups. The
  page builds the alert's title and instruction from `missing` (stick base, throttle, or both) and
  shows a different order as "PASS other order" in the strip.
- Stage 3 slots: `state.plan`, `state.timers`, `state.alerts`, `state.view` exist and are empty.

Every event is a frozen dataclass with `session` (the backup name the game gives the log) and
`offset` (byte offset of its first line): together its identity. `Event.to_dict()` and
`events.event_from_dict()` round-trip.

## Stage 2: the service, the server, the page

**Life cycle** (`Service.run()`, the docstring of `service.py` has it in full):

1. `run --background` with `data/stopped.json` present exits 0 at once: a `stop` stays stopped
   until `start` removes the marker (PLAN §6). A foreground `run` ignores the marker.
2. The named mutex (`Local\scdash-<hash of the data folder>`) or exit 1. The OS drops it when the
   holder dies, so a crash never blocks a start; a stale `run.json` decides nothing.
3. Something answering on 127.0.0.1:<port> before the bind, or a failed bind: exit 2, with the
   health answer saying whether it is another dashboard or a foreign program. The pre-bind check
   matters: a program bound to 0.0.0.0 does not stop an exclusive bind to 127.0.0.1 [seen].
4. Below-normal priority, stale temporary files of a dead instance swept, a new token,
   `run.json` (pid, port, start time, token, and the process's own creation time), the server.
5. The `user` block of `state.json` is read before anything is saved over it. A `state.json`
   that cannot be opened (held without sharing, or a folder in its place) is never saved over
   until it has been read: one warning, and a new try every `state_save_seconds` and before each
   save. One that opens but is damaged (not UTF-8, not JSON, nested deeper than `json` reads,
   not an object, or over 32 MB) is moved aside first (stage 3 section). No game: read the last
   log once, write its summary if it has none. Game running: read from the top (a restart
   arrives at the same state). **Nothing in this step ends the service:** a read or write that
   fails is logged (`error in the first read`) and redone by `tick()`: the last log's read on
   the next turn, a summary (kept in a bounded queue) and the state save after
   `state_save_seconds`.
6. The loop: game running, poll the log every second (16 MB per turn while catching up); always,
   look for the process every 10 s. Process gone: read the rest, `finish()`, write the summary
   (a crash is only visible this way). A summary's file name is its start time and build, and an
   existing file is never rewritten, so no summary is written twice, across restarts too.
7. Shutdown: changes from the page refused (503) from the moment the stop is asked for, the
   front end stopped, the last state saved under the lock (so after a change already in flight;
   each wait bounded at 30 s: stage 3 section), `run.json` removed (only if it is ours), mutex
   released.

Exit codes: 0 done, 1 another instance holds the lock, 2 the port is taken, 3 a setup failure,
4 the web server's front-end thread has ended.

- A failed save of `state.json` or of a summary is not a setup failure: those are retried.
- `run.json` is different, because without it no command can find the instance, read its
  token or stop it. Its write is retried every 2 s, and after 20 s the service logs why and
  exits with 3. Until then `status` and `stop` see a held lock and nothing to talk to.
- The main loop looks at the front-end thread every turn, and at least every 10 s. When it
  is gone the service shuts down in the usual way and exits with 4, so the next start or the
  scheduled relaunch brings up one that works.

`start` launches the background process through `service.launch_background()` (pythonw,
detached, out of the caller's job); in stage 4 `start` goes through the scheduled task there.

**run.json is trusted only as far as the live process confirms it.** Healthy means the named
mutex is held *and* the health answer carries run.json's pid and start time. The mutex is the
truth: with nobody holding it, whatever answers on the port is not ours, even a program that
repeats run.json's answer. `status` reports it as another program, and no command sends it a
token (`stop` removes the stale run.json). A run.json without `created` matches no process.
When the lock is held but nothing answers,
`status` checks run.json's process: a live python(w).exe created at the recorded time (to the
millisecond, both read from one snapshot of the process table) is "ours, not answering" (hung,
suspended or busy), and `stop` and `start` refuse to act on it. No handle is ever opened to another
process, and nothing in scdash ever signals, suspends or ends one; a test scans the source for
both. The tests end only processes they started, through their Popen handles, and stop `start`ed
instances through the shutdown endpoint; one that will not stop fails the test.

**Settings** are bounded on both sides (`config.BOUNDS`); a value outside is a mistake and takes
the default with a note in the log. `replay` copies the past log into its own folder first
(`<data>/replay/source.log`) and feeds from the copy, so replaying the live `Game.log` never holds
it open.

**Files in the data folder**, all written to a temporary file (`.scdash-tmp-<pid>-<hex>-<name>.tmp`,
a prefix only the service uses, swept at start when its writer is gone) and renamed: `run.json`, `stopped.json`, `state.json` (the public
state plus the `user` block: the quick timers and the view picked by hand; loaded at start, saved
at most every 10 s and only on change, and at once after a change from the page),
`unmapped.json` (`locations`: codes with no name, at most 2,000; `contracts`: contracts the
contract table could not place, at most 500, keyed by a hash of contract, generator and title;
both merged across sessions, the oldest first seen going first), `state.damaged.json` and
`unmapped.damaged.json` (a damaged file moved aside; later ones `state.damaged-2.json` to `-5`,
the first copy never replaced),
`sessions/<start>_<build>.json` (newest 500 kept; an undated `session-<hash>` name counts by its
file time), `service.log` (1 MB, one rotated copy), `config.json` (the user's, read only),
`plan.json` (Claude's, read only, PLAN §10). Every JSON file goes through `server.json_text()`,
so no text it holds can make it unsaveable (a lone surrogate becomes U+FFFD, a NaN null).

**Nothing is written through a link.** No write, sweep or prune goes through a junction or
symbolic link below the data folder: `service.link_on_the_way()` checks each part of a path with
`lstat`, following nothing. Such a write is skipped and logged once, and the service runs on.
`service.log` itself is checked (it is appended in place), and `replay` refuses a linked
`replay/` folder or file. The start-up sweep takes only names `atomic_write` makes: an ASCII pid
of 1 to 10 digits, 8 lower-case hex digits, an ASCII file name. A hard link is not covered by
these writes: it is not a reparse point. (The rig files served from `web/rig/` do exclude hard
links: stage 3 section.)

**The request guard** (`server.py`): every request needs exactly one `Host` of
`127.0.0.1:<port>` or `localhost:<port>` and an origin-form target, reads included; a
`Sec-Fetch-Site` other than `same-origin` or `none` is refused on every route. `CHANGE` routes
also need `X-SCDash-Token`, an `Origin` of this server, exactly one `Content-Type:
application/json`, a `Content-Length` of ASCII digits (at most 64 KB) and a JSON object (one
nested too deep is a 400). `PRIVATE` routes and streams need the token
header and a `Sec-Fetch-Site: same-origin` that must be present; the token is never accepted in a
URL. Every `route()` and `stream()` call names its guard (no default), and `route()` refuses a
non-GET route without the token, so a later stage cannot register an unguarded endpoint by
mistake. The token reaches the page only inside the served HTML (`<meta name="scdash-token">`);
`/api/health` carries the program's name, pid and start time and nothing else. The page has a
strict Content-Security-Policy (no inline script or style).

**A connection takes a worker only with a complete head** (`_FrontEnd` in `server.py`, since
the fix round of 2026-11-27). One thread with `selectors` reads every new connection's head
without blocking:

- the first byte within 1 s and the whole head within 5 s;
- at most 16 KB and 40 header lines, refused with 431 the moment it goes over, before the rest
  is read;
- `Host` checked there (403);
- only then one of the 16 worker slots, or a 503 when all are busy;
- at most 64 connections waiting for their head, the oldest dropped beyond that.

The worker still runs the whole guard itself, and a changing request's body must arrive within
what is left of the 5 s (a watcher thread cuts it). A failed front-end turn is logged at
WARNING: the first in full, then at most one line a minute with a count. The `requests` and
`refused` counters are bumped under a lock.

Endpoints: `GET /` (`/app.js`, `/style.css`), `GET /rig/rig.json` and `/rig/<name>.png` (stage
3), `GET /api/health`, `GET /api/status`, `GET /api/state` (the last payload), `GET /api/stream`,
`POST /api/shutdown`, and stage 3's four `CHANGE` routes `POST /api/view`, `/api/view/live`,
`/api/timers/add`, `/api/timers/remove`. [`STATE.md`](STATE.md)'s last section has each one's
body, answer and error codes. At most 16 requests at once (once their head is in), 64
connections waiting for a head, 5 s to send one. The shutdown reason is logged through `repr()`,
cut at 80 characters.

**What the page gets** (one JSON line per event-stream message, `event: state`): `service` (mode,
pid, game running and since, log found, replay info, terminal on), `clock` (`rate`, `real`,
`virtual`: the page's now is `virtual + (Date.now() - real) * rate`, which is the system clock in
live mode and the replay clock in a replay; `session_end` once the game is not running), `flags`
(clock-dependent facts the service computes: `hangar_stuck`), `state` (`to_dict(private=False)`),
and since stage 3 `board` (`board.build`'s payload, never null; [`STATE.md`](STATE.md)).
Sent only when it differs from the last one, merged to at most two a second, `retry: 3000`, a
comment line every 15 s, at most 4 pages; a closed page is noticed within a second by peeking at
its socket. Nothing half-read goes out while the service catches up on a large log (stage 3
section below).

**Where later stages hook in:**

- Stage 3, the page: views in `web/app.js` `renderView()` (and the view region in `index.html`),
  drawn from `board` alone ([`STATE.md`](STATE.md)); alerts from `board.alerts` only (drop the
  page's own preflight, downed and hangar alerts); the switcher and the reference section, which
  load `/rig/rig.json` and the images it names. Changes go through `window.scdash.post()`, which
  resolves to the JSON answer for errors too. The service side of stage 3 is done (below): a new
  changing endpoint goes in `Service._register()` behind `CHANGE` and through `_locked_change()`,
which gives it the lock, the 503s and the save before the answer.
  The page reloads itself when the payload's `service.pid` or `service.started` changes, so it
  never posts with a dead token.
- Stage 4: `open` and `shortcut` exist ("Stage 4: the window" below). Still to come: the
  `install` and `uninstall` commands in `scdash.py`; `start` (and so `open`) through the task in
  `launch_background()`; `run.json` records `python` for the moved-interpreter check; the service
  opening and closing the window by itself.
- Stage 4b: a `Hub` of its own (`max_clients=1`) registered with
  `server.stream(path, hub, PRIVATE)` for the terminal's output, read on the page with
  `window.scdash.openPrivateStream(path, onData)` (fetch with the token header over the
  close-delimited response, reconnecting by itself), and a `CHANGE` route for keystrokes; the
  `terminal.enabled` setting already lays the page out with the region (`data-terminal` on
  `<html>`).

**The page** (direction B, "Avionics"; the chosen mockup is tracked in `design/avionics/`, and the
working folder with all three directions and their captures is the git-ignored `data/design/`): the strip (time and date, state,
joystick pass or fail with a quiet "other order" note, session, location, ship), alerts across the
top of the view, a "Now" placeholder, the feed (major and alert lines, 4 in landscape and 6 in
portrait; minor ones stay out, `SHOW_MINOR` in `app.js`), and the terminal region when the setting
is on. Nothing below 18 px; texts that can come from the log carry `unicode-bidi: isolate`. One
event stream, one one-second timer, only changed text redrawn. When the stream has been gone 2 s,
the red banner takes the strip's place (its figures are stale then) and the rest is dimmed; it
covers nothing else.

**The follower across a real game launch** (PLAN §8, §12 stage 2) was proved with the stage 1
follower on 2026-11-27 at 12:57 PM, and with the service itself that evening: it followed a
first launch that began with no `Game.log` at all, and a second launch at 6:13 PM where the game
emptied the log in place under the same file id and the backup appeared at the old session's
full size (PLAN §8 has the figures and the lines). The service logs what the proof needs to `data/service.log`: `log facts (...)` lines with the log's size, file
id, volume, created and modified times and first line, at start, when the game appears and ends,
when the log is emptied and when a new session begins; `the session ... ends in the same file,
read to offset N`; `a new session starts in the log at offset 0: first line ... (was ...)`; and
30 s and 120 s after the game appears, `newest backup (...)`, which compares the newest backup's
first line and size with the session that ended in place and says `same size, rotation
undisturbed` when they match. To run it: `start` with the game closed, launch the game from the
launcher, stay at least two minutes, quit, wait ten seconds, then read those lines.

### Measured (stage 2, 2026-11-27, game not running) [seen]

Taken from the real service started with `start` (pythonw, below-normal priority), through its
own `/api/status`: `cpu_s` is `os.times()` user plus system, memory is `GetProcessMemoryInfo`.
Windows' own counters (`Win32_PerfFormattedData_PerfProc_Process`) gave the same private working
set to the kilobyte. Each run used a temporary data folder, a free port and a stand-in "game"
process (a renamed copy of `PING.EXE`). Scripts were scratch files.

| What | Measured | Budget (PLAN §9) |
| --- | --- | --- |
| Idle, no game, one page connected, 10 min | 0.47 s CPU = **0.078%** of one core; **23.4 MB** private working set, 35.0 MB working set, 25.2 MB committed | effectively zero; 30 MB |
| Game "running": the afternoon log of 2026-11-26 written at its real pace (766 KB, 47 events, 30 state sends in the window), one page, 10 min | 0.69 s = **0.115%** of one core; **21.6 MB** private working set, 33.2 MB working set | 0.2%; 30 MB |
| Replay of that session in 2 min (about 43x) | **0.46%** of one core over the replay; 24.4 MB private working set at peak | none set |
| 100 MB of junk appended twice to a followed log | first flood 21.3 -> 24.3 MB (a one-time step: the 1 MB read pieces), second 24.3 -> 24.3 MB; peak working set 37.9 MB; about 1 s CPU and under 1 s each | must not grow |

**After the fix round of 2026-11-27 (evening), by the builder and again by the reviewer
[seen]:**

| What | Before | After |
| --- | --- | --- |
| Idle, one page connected, 5 min | 0.067% of one core, 22.2 MB | 0.060%, 23.2 MB (the gap is noise: every version landed on 21.5, 22.2 or 23.1 MB across runs) |
| Connections sending 6.5 MB request heads for 10 s | 2 connections: 8.2 s of CPU, and a 10 MB step that stayed | 16 connections: 1.3 s of CPU, memory flat |
| A foreign page's preconnect flood (64 waiting, plus the stream) | the real page and a separate client got 3 of 16 answers | 16 of 16, and the stream stayed up |
| 300 idle connections | threads 3 to 19 and back | no thread added; at most 64 wait, each dropped after a second |
| 3,000 dropped or refused connections | - | threads 3 to 3, handles 175 to 175 |

One limit left as it is: under a local flood of about 290 connections a second, a client that
waits 200 ms before sending its head was pushed out of the waiting list 14 times in 41. Clients
that send at once, as browsers and the command line do, always got through.

Most of the idle cost is the process check (about 5 ms every 10 s, see below); the rest is the
server's half-second poll and one wake-up a second per connected page. Not yet measured: the same
with the real game running, and the window (stage 4).

### Learned in stage 2 (2026-11-27, this PC) [seen]

- **A refused connect to 127.0.0.1 takes about 2 s on Windows** (4 s to `localhost`, which tries
  ::1 first). A listener accepts at once, so every probe connects with a 0.5 s timeout and reads a
  timeout as "nothing there"; the HTTP answer then gets 3 s.
- **A program bound to 0.0.0.0:<port> does not stop an exclusive bind to 127.0.0.1:<port>**, so
  `run` first checks whether anything answers on the port. Two binds to 127.0.0.1 are refused
  (10048), with or without the other side asking for address reuse.
- **A Toolhelp process snapshot costs about 5 ms** with about 270 processes: 2.9 ms for the
  snapshot, the rest walking it through ctypes. The `NtQuerySystemInformation` table that
  replaced it costs 2.6 ms (3.9 ms for Toolhelp in the same run, 266 processes), with the same pids
  and names and creation times equal to `GetProcessTimes` to 100 ns.
- **Windows' monotonic clock moves in steps of about 15.6 ms**: a test that sets a 1 ms interval
  and checks at once sees no time pass (tests set `Service._next_probe = 0` instead).
- **The page's Content-Security-Policy forbids inline `style` attributes.** The mockup's hidden
  icon sprite (`style="position:absolute"`) took a line of height and pushed the feed off the
  bottom until it got a class. Its meters (`style="--v:.62"`) will need
  `element.style.setProperty("--v", ...)` in stage 3, which the policy allows.
- **Headless Edge:** `--virtual-time-budget` never finishes while an event stream is open. A plain
  `--screenshot` works, because the server sends the current state the moment the page connects.
  Add `--force-prefers-reduced-motion` to see an alert without its 160 ms fade (the stylesheet
  honors reduced motion).
- **`start`'s detached process outlives the shell that started it** (DETACHED_PROCESS plus
  CREATE_BREAKAWAY_FROM_JOB, falling back without breakaway if a job forbids it). Under pythonw the
  standard streams are None; `scdash.py` points them at the null device first.

## Stage 3 in the service (2026-11-28)

Built in the third session, finished, measured and replayed in the fourth, then reviewed (the
wiring review, findings A to K, 2026-11-28) and fixed the same day; the findings are named where
they changed something below. What the page gets and can ask for is in [`STATE.md`](STATE.md)'s
last section; this is how the service does it.

**The board.** `_publish()` calls `_update_board(now)`, which calls `board.build(state, plans,
user_data, now, game_running)` only when `_board_due(now)`: the inputs signature
`_board_inputs()` changed, or `now` reached the last payload's `next_change_ms`. A payload with no
`next_change_ms` (one that failed) is retried in 60 s, not before. `board.build` is guarded: if it
raises, `fallback_board()` goes out (problem `"service: <type>"`, the keys of any other payload),
and the error is logged once. A payload that `json` cannot write (a set in it: a fault in
`board.build`) is replaced by the fallback board in `_publish()` the same way and built again in
60 s (the wiring review's finding H: the page got no message at all).
`problems` are logged once per distinct set (at most 100 sets). The loop's wait ends at the next
change, converted through the clock's `rate` (the replay clock; none when it is frozen).

- **`_board_inputs()` is complete.** It is (`_resets`, session id, `events`, `unreadable`,
  `_plan_version`, `_user_version`, game running). Read from the code: the state changes only in
  `State.apply`, which counts every event in `events` or `unreadable` (a failure while applying is
  counted in `unreadable` by the reader), and in a reset, which `_resets` counts; names are
  learned only inside `apply`; the reference tables and the location names never change while
  the service runs; `user_data` changes only through `_change_user` and `_load_user`, which bump
  `_user_version`. Shown by `test_wiring.BoardInputs` [seen 2026-11-28]: all 16 sample logs fed in
  random pieces with the clock moving, a plan, a quick timer and a pick on the way and the game
  ending, and at every turn the board was not rebuilt, a board built afresh was the same payload.
  Not an input, and unverified: a change of the PC's time zone, which changes the worded times
  only at the next rebuild.

**The plan.** `_refresh_plan()` runs in `_after_read`, at most every `PLAN_CHECK_SECONDS` (1 s): once
a second while the game runs, every loop turn (about 10 s) when not, so it adds no wake-up. A true
`PlanStore.refresh()` bumps `_plan_version` and logs the notice. `Service(plan_path=)` points it
elsewhere (`replay --plan`).

**The user block** (`user_data`, saved in `state.json`). Changes are operations, `("view", pick
or None)`, `("add", timer)`, `("remove", "quick:<id>")`, applied by `apply_user_op()` through
`_change_user()`, which bumps `_user_version` and asks for a save on this turn.

- **Read before anything is saved over it.** `_load_user()` runs at the first read, then every
  `state_save_seconds` and before each save until it has worked. `_read_data_file()` tells four
  cases apart: no file (a new block); a file that cannot be opened now (held without sharing, a
  folder in its place: one warning, tried again); a damaged file; a JSON object. Damaged means
  not UTF-8, not JSON, nested deeper than `json.loads` takes (about 2,900 levels on Python 3.12),
  not an object, or over `MAX_DATA_FILE_BYTES` (32 MB). A UTF-8 byte-order mark is not damage:
  both files are read as `utf-8-sig`, as `plan.json` is (Windows PowerShell 5.1 saves with one).
  A damaged file is renamed beside it (`_move_aside`, never through a link) and the block starts
  empty: to `state.damaged.json`, or, when that copy exists, to the first free
  `state.damaged-<n>.json` up to `MAX_DAMAGED_COPIES` (5). The first copy is never replaced: it
  is the one most likely to hold what the user entered (the review's second round: a second
  damage replaced it). With all five taken, the last is replaced, and the log says so. While the
  rename fails, nothing is saved over the file.
  The block is marked read only after it has been taken, and `_load_user` never raises (a fault
  is logged and the block stays unread), so a file is never saved over unread. Before the fix
  round (the wiring review's finding A), a value nested about 2,000 deep raised `RecursionError`
  in `scrub` after the block was marked read: the user's timers and pick were saved over, and the
  first read ended before the last log was read.
- **What is kept from the file** (`user_block_from_file()`):
  - `timers` as `plan.clean_user` reads them (at most 10, each with a label, a ready time and a
    unique id), stored under the ids the page is shown: a doubled `q1` becomes `q1-2`, an odd id
    gets a new one, so removing by the shown id always finds the timer (finding B). A timer the
    board cannot show (no label or no ready time) is dropped.
  - `view`: the pick as `clean_user` takes it, else none.
  - Any other key, kept for a later stage, only if its name is a text of at most 64 characters
    and its value nests at most `MAX_USER_EXTRA_DEPTH` (16) deep, and all such keys together are
    at most `MAX_USER_EXTRA_KEYS` (32) and `MAX_USER_EXTRA_BYTES` (16 KB) of JSON (finding D: a
    20 MB key was rewritten at every save).
  - What is left out is named in one warning per load, and the bounded block replaces the
    file's at the next save. The block goes through `scrub()`, so a lone surrogate typed into
    the file becomes U+FFFD. [seen 2026-11-28 on a running instance with a temporary data
    folder: a key nested 20 deep, a 70-character name and a 20 KB value were left out in one log
    line, an unshowable timer and an unusable pick were dropped, and `q1`, `q1`, `bad id!` were
    shown and stored as `q1`, `q1-2`, `q2`.]
- **Saved at once after a change** (it is the only record, PLAN §7), **except while saves are
  failing**: then only the loop tries again, every `state_save_seconds` (`_save_due`). Before,
  each change retried the save under the lock; a file held without delete sharing costs a save
  about 2 s of `atomic_write` retries, so changes made one after another waited on each other,
  three long enough for a 503 [read from the code; the fix is tested in `TheLock`].
- **A `state.json` read late is merged, not overwritten.** While it cannot be read, the ops are
  also kept (`_user_ops`, at most `MAX_USER_OPS` = 100; past that the oldest are dropped, a known
  limit) and replayed in order over the file's block when it can be, keeping its other keys. So
  Live and a removal record their op even when the block held now has nothing to drop: the
  file may hold it (their answer's `had_pick` and `removed` describe the block held now).
- **A pick is dropped** when the payload says `pick_dropped` (`_update_board` deletes it and builds
  once more), never while catching up, and never for the reference pick (the board never says so
  for one).

**The four changing routes** (`_api_view`, `_api_live`, `_api_timer_add`, `_api_timer_remove`,
registered in `_register()` behind `CHANGE`). Each checks its body exactly (`body_fields`: an
unknown or missing field is a 400), then runs in `_locked_change()`:

1. The main loop's lock (an `RLock`), taken with a `CHANGE_LOCK_SECONDS` = 5 s timeout, else 503.
2. Under it, two more 503s: `_closing` (a stop asked for; set by `_halt()` and in `_run`'s
   `finally`: finding F, a change answered 200 at the stop could be lost) and `_first_read_done`
   still false (below, finding G).
3. The change, then `_after_change()`, which rebuilds and publishes (nothing while catching up)
   and takes the snapshot of what `state.json` is to hold (`_take_snapshot`). So the answer and
   the next message already show it.
4. The lock released, `_write_snapshot()` writes the snapshot, and only then does the answer go
   out: a 200 means on disk, outside the exceptions in [`STATE.md`](STATE.md).
5. `_wake` set (below: it runs no turn).

- **Saves are snapshots, written outside the lock** (finding E: each change wrote and fsynced
  under the lock, so with a 1.5 s save six changes sent at once took 1.5 to 6 s, two got a 503,
  and the loop stalled 5.8 s). `_take_snapshot()`, under the lock, numbers each snapshot; the
  objects it refers to are never changed in place afterwards (each change makes a new user block,
  each message a new state). `_write_snapshot(seq)`, under `_save_lock` (one writer at a time),
  writes the newest snapshot unless one at least as new is on disk already, so changes made
  together share one write and an older snapshot is never written after a newer one. `tick()`
  and `start_reading()` write their saves the same way, after releasing the lock. An answer
  waits for at most the write in flight and its own. [The builder's measurement with a mocked
  1.5 s save: six changes at once all answered 200 within 3.0 s, and the loop's longest turn was
  0.0 s; `SlowDisk`, which also covers the loop's own save.] Writes still made under the lock,
  all rare: `unmapped.json` (when something new is first seen), a session summary, `run.json`,
  and a damaged file's rename. A change can wait behind one: 2.7 s behind a mocked 3 s write of
  `unmapped.json` (the review's second round, `r2_bounds.py`).
- **A failed write does not change the answer.** The change is made, kept in memory and sent,
  and written when a save next succeeds; `STATE.md` says so beside the endpoint table.
- **The last save** (`_last_save_at_stop()`): `_closing` set, the lock taken (waiting up to
  `SHUTDOWN_LOCK_SECONDS`, 30 s, for a change in flight to finish; past that the last save is
  skipped and logged, and the change saves itself), the last snapshot taken, then written after
  any write in flight. Before, the final save ran without the lock and could write an older
  state after a change was answered 200 [`StopAndChanges`]. The write runs in a thread of its
  own, joined for at most `SHUTDOWN_SAVE_SECONDS` (30 s): a write that never returns is logged
  and left behind, and the stop goes on (the review's second round: the wait on `_save_lock` had
  no bound). The rename-based write leaves `state.json` as it was if it is cut off at the exit.
- **A change runs no turn of the loop** (`_wait()`, finding I): `_wake` only makes the wait
  recompute its deadline (a new quick timer can come due sooner), and the next turn comes at its
  usual time; the change has published and saved already. Before, every change ran a whole turn
  with a poll of the log: about 260 turns a second under a flood of changes. A stop still ends
  the wait at once [`LoopTurns`].
- **A page's connection cannot hold the lock up** [seen 2026-11-28, `TheLock`]: publishing only
  swaps the Hub's payload; each page writes in its own thread, outside the Hub's lock. A page that
  read nothing had its thread stuck in a write after about 53 KB, and 40 changes in a row each
  answered in under a second while another page got every new message.
- **What runs under the lock:** the main loop's turn (a read of up to 16 MB while catching up,
  the process check, building and sending the message, taking a snapshot) and each change. The
  longest holds are the loop's own: `_read_to_end()` when the game exits, and the last log's read
  at start with no game, both read the rest of a log in one turn. A change that waits more than
  5 s for them gets a 503 (in practice only behind a log of hundreds of MB; not measured). A slow
  disk no longer does it.
- **A quick timer's label:** lone surrogates are taken out at the endpoint (like control
  characters); nothing but spaces left is a 400; then it needs one visible character
  (`visible()`: a Unicode category L, N, P or S), so a label of zero-width, format, tag or
  combining characters only is a 400 too (finding C).

**Catching up.** While `_read` is busy (a read used its whole budget), `_tick` sends nothing for
`CATCH_UP_PUBLISH_SECONDS` (2 s), then one half-read message every 2 s, so a restart mid-session
cannot flash an old Dead or Downed alert; `start_reading()` sends nothing while the game runs (the
first tick does). Picks get a 503 meanwhile (their context is not known yet). **A read that raises
ends the catch-up** (`_busy_since` cleared, then the loop logs it and waits a second): left set,
it refused every pick and held back every change for as long as reads failed. A read that fails
every turn leaves the page with what it had; changes from the page still go out.

**The first read** (`_first_read_done`, finding G). It is set in the first turn whose read
reached the end of the log, right after the read (game running; after a restart mid-session, the
end of the whole catch-up), after the last log's read at start (no game), or when a read raises
(with no game, once the next turn's retry raises too). Set right after the read, it holds
whatever a later step of the turn does: the review's second round had `_flags` raise on every
turn, which kept every change at 503 for good; nothing can be published in between, because the
turn holds the lock. So neither a failing log nor a failing later step locks the page out. Until then the
four changing routes answer 503 "still reading the log: try again in a moment". Before, a change
in that window published a board built on an empty state, and a pick made then was dropped the
moment the read came in. The window is between `server.start()` and the end of the first read:
milliseconds with a small log [`FirstRead`].

**Unmapped contracts.** `_note_unmapped(state, board)` merges the board's `unmapped_contracts`
into `data/unmapped.json` under `contracts` (keyed by `contract_key()`, texts cut to 300, at most
`MAX_UNMAPPED_CONTRACTS` = 500, the oldest first seen dropped), beside `locations` (at most
`MAX_UNMAPPED` = 2,000). Like `state.json`, the file is never saved over unread (finding J: it was
marked read before a read that failed, and the next write replaced every earlier session's
entries). `_load_unmapped()` reads it once, when something new is first seen, through
`_read_data_file()`: a missing file is a new one; one that cannot be opened now is warned about
once, the new entries wait in memory (`_unmapped_dirty`) and the read is tried again with the next
message and at least every `state_save_seconds` (`_after_read`); a damaged one is moved aside to
`unmapped.damaged.json`. A write that fails is logged and retried the same way. An entry read back
keeps only its own fields, each a cleaned text of at most 300 characters, and the whole file goes
through the state's name scrubber (`State.scrub`) each time it is written, so a player's name
learned after an entry was first seen is hidden there too. [read from the code; tested in
`UnmappedFile`. Seen 2026-11-28 on a running instance: an `unmapped.json` holding `[1, 2]` was left
as it was, because that session had nothing new to note.]

**The rig files.** `server.rig_files(web_dir)` lists `web/rig/` once, when the `Server` is made:
`rig.json`, and every `[a-z0-9_]{1,48}\.png` that is a plain file (`_plain()`: no junction, link
or other reparse point, the folder itself neither, and for a file a single name: a hard link is
not served, finding K, since its data can be any file on the volume, `data/run.json` with the
token included) of at most `MAX_RIG_FILE_BYTES` (1 MB), at most `MAX_RIG_IMAGES` (64) by name,
the folder's first `RIG_SCAN_MAX` (10,000) entries looked at. What is left out is logged once. The
table is then fixed: a request
path is only looked up in it, and each request checks the same rule again (`_plain()` on the
folder and the file, and the size) before it opens the file, so a folder swapped for a junction
after the start is not followed. **A card regeneration that adds or renames an image needs a
restart** (`stop`, `start`); a changed file under a name already served is read fresh.

**Text that cannot be encoded.** Every JSON text the service writes or sends goes through
`server.json_text()` (`write_json`, the message, the server's answers): a lone surrogate becomes
U+FFFD and a NaN or infinity null, so nothing from a plan, `state.json`, `unmapped.json` or a
request body can make the message, a file or an answer fail (stage 3 review: `"\ud800"` in
`plan.json` raised `UnicodeEncodeError` at the first encode, after which the page got nothing and
`state.json` was never saved again). `Hub.publish()` passes its text through `encodable()` too,
`status()` through `scrub()`, and `service.log` is written with `errors="backslashreplace"`. The
other half of the fix, taking them out where text enters (`words.clean_text`, `plan._text`), is
the stage 3 fix round's.

**The service's own log** (the two faults of the last stage 2 review). `server.error_key()` names
a fault by its type and the file and line it was raised at; `server.remember()` keeps when each
was last logged in full. `Service._error()` logs a kind in full once, then again at most every
`ERROR_FULL_AGAIN_SECONDS` (an hour), counting repeats in between (a line at 10, 100, 1,000 and
every 10,000). The front end logs a fault of a kind not logged in the last hour at once, after
flushing any count it holds, and flushes its count on a timer in `_run`.

**`status`** gained `board` (view, auto, rule, why, picked, builds, next change, problems), `plan`
(path, loaded, notice, updated, run), `user` (read, quick timers, pick), `reference_tables` and
`session.withheld` (notices of a shape that may name a player, not read); the text form prints
View, Plan, Notice and Problems, and the withheld count when it is not 0. Every path in it goes
through `shown_path()`, the user's profile folder written as `%USERPROFILE%`: the interpreter's
full path carried the Windows user name (the review's privacy check). [seen 2026-11-28: `python`
and `data_dir` both began with `%USERPROFILE%` on a temporary instance.]

**`start` returns before the first read is done.** It waits for a healthy instance (the health
check and `run.json`), and the server answers before `start_reading()` has read the last log,
written its summary and logged the plan's notice [seen 2026-11-28: 7 log lines when `start`
returned, 9 at the first message, none more in the next 10 s]. A test or script that reads
`service.log` or the state right after `start` waits for `/api/state` to answer first
(`test_replay` was failing now and then on exactly this). A change sent before then gets a 503
("still reading the log").

### Measured (stage 3 wiring, 2026-11-28) [seen]

Taken the way stage 2's were (`/api/status`'s `cpu_s` and private working set), **with the game
running on the PC** and other agents' test suites running at times, so the CPU figures are noisy.
"Before" is `main` at `0b513d5` exported to a scratch folder (stage 2's service, stage 3's logic
not called); "after" is this tree. The scripts are in the git-ignored
`data/handoff/session4/wiring/` (`replay_run.py`, `rig_mem.py`) and `data/handoff/review/fix-stage2/`
(`measure_idle.py`).

| What | Before | After | Budget (PLAN §9) |
| --- | --- | --- | --- |
| Idle, no game for the instance, one page connected, 300 s (both at once) | 0.39 s CPU = 0.130% of one core; 24.4 -> 24.3 MB private | 0.25 s = 0.083%; 24.2 -> 24.1 MB | effectively zero; 30 MB |
| Replay of the 5:20 PM session of 2026-11-27 (744 KB, 46 min) at 20x, one page, both at once | 0.46% of one core over 138 s; 23.8 MB at start, 25.1 peak | 0.59%; 24.5 MB at start, 26.8 peak, 26.0 at the end (the Mining view's tables loaded) | none set |
| Replay of the 7:14 PM session of 2026-11-27 (687 KB, 55 min) at 20x, one page, beside another replay | - | 0.35% of one core over 167 s; 24.5 MB at start, 26.6 peak, 25.9 at the end | none set |
| Every rig file (7, 89 KB) asked for 1,000 times, 7,000 requests in 28 s | - | 23.6 -> 23.9 MB, the same 5 s later; 9.2 s of CPU in all (1.3 ms a request) | must not grow |
| `board.build` on the 7:14 PM session's end state (`build_cost.py`) | - | first build 25 to 27 ms (loads the ships table), then 0.13 to 0.6 ms; with `plan.example.json` 0.4 to 0.6 ms. `to_dict` and its JSON, which every message has always paid, cost 1.3 to 2.7 ms | - |

The board adds little: a build is cheaper than the state's own serialization, and it runs only
when an input changed. The Mining view's first build loads the ores, refineries and controls
tables (8 to 19 ms once, by the third session's builder; about 1 MB, the replay's 1.7 MB higher
peak). Still to measure: a whole session with the game running and the real page drawing the
views (stage 3's page, stage 5).

### Replayed through the service (2026-11-28) [seen]

Each real log of 2026-11-27 and 2026-11-28 replayed with `scdash.py replay` at 20x, the board's
view read from the event stream as a page gets it (`replay_run.py`), compared with the board
built over the same log in one process (`data/handoff/real_session_views.py`):

| Session (backup in `logbackups`) | The views the page got, in order | In one process |
| --- | --- | --- |
| 5:20 PM, 2026-11-27 (744 KB) | preflight, now, mining, travel, mining, idle | the same |
| The same, `--plan dashboard/plan.example.json` | the same; every board had the plan loaded, its current run and 2 timers | the same views, 2 timers |
| 6:13 PM, 2026-11-27 (365 KB) | preflight, now, idle | the same |
| 7:14 PM, 2026-11-27 (687 KB) | preflight, now, mining, travel, mining, travel, mining, now, idle | the same, with preflight between the last now and idle: the disconnect and the quit are in the same second (8:10:20 PM), so the stream's merge to two messages a second drops it at any speed |
| 6:19 AM, 2026-11-28 (162 KB) | preflight, idle | the same |

At 20x the shortest view (31 s of log time) lasted about 1.5 s on the page. Every message parsed
as strict JSON, no board had a problem, the service logged no error, and each replay was
stopped through its shutdown endpoint with exit 0 (no `--exit-at-end`, which can end the server
before the last message is read). Stage 3's "done when" also names Refinery, Combat, Cargo and
Salvage: no rule chose any of them in these sessions (no contract rule fired, and Refinery comes
from a plan leg; the example plan's legs name other places), so those are judged on the built
samples and on the user's next sessions.

## Stage 4: the window (`open`, `shortcut`), 2026-11-28

The `open` half of stage 4 (PLAN §6, §11 "Opening the window", §12 stage 4). The logon task
(`install`, `uninstall`) is not part of it.

**`open`** (`cmd_open` in `scdash.py`, the mechanics in `scdash/window.py`):

1. Finds the browser first, so nothing is started when there is nothing to show it in: `--browser`,
   else the `window.browser` setting (a path, or a name looked up under App Paths and on PATH; a
   named browser that is missing is an error, not a reason to use another), else Edge, then
   Chrome: App Paths (HKCU, then HKLM), their install folders, PATH. On this PC App Paths gives
   `C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe` [seen].
2. Makes sure the service answers, through `_ensure_running()`, the code `start` uses (it clears a
   stop marker too, as `start` does).
3. Decides whether a window is open. `pages` from `/api/status` alone cannot tell the window from
   a browser tab, so it is combined with the window's profile folder: Chromium keeps `lockfile`
   in it while it runs, opened delete-on-close [seen 2026-11-28: present while the user's
   hand-made Edge window ran; Python's `open()` was refused, `open_shared()` was not, so the
   holder has delete access]. Only its presence is tested (opening it could race a starting
   browser).
   - Profile in use and a page connected: "already open", exit 0, nothing started.
   - Profile in use, no page, the service up less than `RECONNECT_SECONDS` (8 s): waits for the old
     page to reconnect (its stream retries after 3 s, `app.js` after 5 s), as PLAN §11 asks.
     Then "already open", or it opens one (the launch is handed to the running browser, whose
     placement switches are then dropped).
   - A page connected but the profile not in use: a tab elsewhere; the window opens anyway and
     the output says so (and warns at `max_pages`).
4. Places the window (`window.placement()`, displays read from Windows each time) and starts the
   browser below normal priority (the whole browser tree inherits it, so it yields to the game),
   out of the caller's job, with `CREATE_NO_WINDOW`, working folder the home folder. It does not
   wait for the browser. One `INFO open: started ...` line goes to `data/service.log`.

**The exact command line** (Edge on this PC, one display at 3840x2160 and 100 %, taskbar 48 px):

```
msedge.exe --user-data-dir=%LOCALAPPDATA%\scdash\browser --app=http://127.0.0.1:47826/
           --window-position=952,496 --window-size=1936,1119 --no-first-run
           --no-default-browser-check --disable-background-networking
           --disable-component-update --disable-sync
```

(the profile path is passed expanded). With `--portrait`: `--window-position=1372,76
--window-size=1096,1959`. With a second display: `--window-position=<a point inside it>
--start-fullscreen` and no size. Never `--kiosk`.

- **One display:** the window is the page's size plus `window.FRAME` = (16, 39), centered in the
  primary's work area, in the browser's scaled units (physical / scale). When the work area is
  smaller, the window is capped to it and the output says so. `FRAME` is an estimate of Edge's
  app-window borders and title bar on Windows 11 **[unverified]**.
- **A second display:** a non-primary display of 1920x1080 or 1080x1920 if there is one, else the
  first. Whether Chromium reads `--window-position` in physical or scaled pixels is still open
  (PLAN §14 item 2), so `inside_point()` takes the middle of the overlap of both readings (the
  scaled one estimated by placing the display against the primary's edge at its own scale), and
  the scaled one alone when they do not overlap. With a main screen at 100 %, as on this PC,
  both readings are the same. `--main` keeps a window on the main screen. **[unverified: no
  second display until the side monitor is connected]**
- **No console** (pythonw from the shortcut): `_Out` puts a problem in a message box and in
  `data/service.log` (`ERROR open: ...`, never through a link), and "already open" in a message
  box; progress is not shown. The box is `MB_SETFOREGROUND`: the user started the command.

**`shortcut`** writes `dashboard/SC Dashboard.lnk` (`--folder` elsewhere, `--desktop` also on
the Desktop, from `SHGetKnownFolderPath`): target `pythonw.exe` beside the running Python,
arguments `"<repo>\dashboard\scdash.py" open`, working folder the repo root, a description, and
`dashboard/scdash.ico`. Written through the ShellLink COM object (`winutil.write_shortcut`); a
`.lnk` holds absolute paths (the Windows user name among them), so `*.lnk` is git-ignored and
`test_privacy` would catch one that is not. The user's hand-made Desktop shortcut (Edge app mode
pointed straight at port 47826, same profile folder) is replaced by the orchestrator, not by a
test: no test writes to the Desktop or to `dashboard/`.

**Decisions to confirm** (made in this slice): a tab does not count as the window (the profile
test above); the reconnect wait; the window below normal priority; `--main`; the custom icon
rather than Edge's (`make_icon.py`); "already open" from the shortcut is a message box, not
bringing the window to the front (that would need finding the window by its title; not done).

**Unverified until checked by hand or with the side monitor:**

- `FRAME`: whether the page gets exactly 1920x1080 (check `innerWidth`, `innerHeight` with F12 in
  the window and adjust `window.FRAME`).
- Everything about the second display: placement, full screen in both orientations, and whether
  a full-screen window follows a rotation made while it is open (PLAN §11).
- Focus while the game is in front; the window's real memory (PLAN §9); what still goes online
  with the window open (PLAN §8).
- Pinning the shortcut to the taskbar, and the message box under pythonw (the tests patch it).

**Left in stage 4:** the logon task (`install`, `uninstall`, `start` through `schtasks /Run`);
the service opening the window when the game starts and closing the one it opened a few minutes
after the game exits (PLAN §6, §15; it must close only a window it opened itself, by process id
and start time, PLAN §8); the second-display checks above.

### A browser tab instead of the window

The user uses a plain tab on the main screen until the side monitor arrives (2026-11-28). Nothing
in the server or the page assumes the app window: a typed address or a bookmark sends
`Sec-Fetch-Site: none`, which every route accepts, and the page sizes itself from the viewport
(`100vw` by `100vh`, orientation media queries). What differs [read from the code and the
browsers' documented behavior, not tried in a tab yet]:

- **A link to the dashboard clicked on another site** (an artifact page, a document) sends
  `Sec-Fetch-Site: cross-site` and gets a 403 JSON answer: the guard refuses it on every route.
  Open it by typing the address or from a bookmark. Letting a top-level navigation to `/` through
  would be a change to the reviewed guard: a decision, not made here.
- **Tabs count against `max_pages` (4).** Each open dashboard tab holds one stream; a fifth gets a
  503 and the "No connection" banner, retrying every 5 s. Chromium also allows about six
  connections per address across all tabs of a profile, so many dashboard tabs can stall even
  the page's own requests.
- **A tab in the background is throttled** (timers to once a second, and to once a minute after
  five minutes hidden; Edge's sleeping tabs can freeze it). The clocks are computed from
  `Date.now()`, so they are right again the moment the tab is shown, and the stream reconnects by
  itself if the browser dropped it. Exempting `127.0.0.1` from sleeping tabs in Edge's settings
  avoids the freeze.
- **The viewport is smaller than the screen** by the browser's own bars (about 130 px of
  1080), and the user's extensions run in the page and can read it, token included (PLAN §9).
  The views stage should capture its screens at a tab's size too.

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
  ms before `Spawned!`. Of 44 respawns, 4 logged no place within a minute (my guess: a respawn in
  a ship's medical bed in space) and 2 came less than a minute before the log ended.
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
