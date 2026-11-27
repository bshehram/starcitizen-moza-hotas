# Side-screen dashboard: implementation plan

**Status: planned, not built.** Written 2026-11-26.

This file is the brief for the Claude session that builds the dashboard. The user starts that
session with `@STARCITIZEN.md` and asks for the dashboard to be built from this plan. It says what
to build, why each constraint exists, what is already known and what still has to be checked, and
how to tell that each stage is done. It does not repeat the project's own rules: read
[`../STARCITIZEN.md`](../STARCITIZEN.md) and [`../CLAUDE.md`](../CLAUDE.md) first, and follow them
where this plan is silent.

Each fact below carries how it is known, the same way the rest of the project does:

- **[seen]** read from the user's own game logs or files on this PC.
- **[ref]** from documentation or a community source, with the source named. Second-hand.
- **[verify]** my reasoning or an open question. Check it before relying on it.

## 1. What this is

A small background program that reads Star Citizen's own log file while the user plays and shows
what matters right now on a second monitor: where they are, what the plan says to do next, the
numbers they need for the job in hand, timers, and alerts.

The side monitor is a 15.6-inch 1920x1080 screen **without touch**. The user's hands are on a
stick and throttle, so nobody operates the dashboard during play. It has to run itself: pick the
right view from what the log shows, and be readable at a glance from a seat away.

## 2. What the user asked for

| Their words | What it means here |
| --- | --- |
| "a dashboard or something for star citizen" on a second screen | A glance-only display that follows the game by itself. |
| "an html thing in a browser" | A web page, fed by a small Python script. Agreed with the user. |
| "run from within this project in a sub folder that way we keep everything in git" | Code, docs and generic game reference data live in `dashboard/` in this repo. The user's own play data stays in a git-ignored folder, because the repo is public (agreed with the user). |
| "make sure its a service" | It starts by itself, runs in the background, and never runs twice. §6. |
| "idempotent" | Every command can be repeated with the same end result, and the same log always produces the same state. §7. |
| "safe to run" | It cannot harm the game, the PC, the account or the user's privacy. §8. |
| "performant as much as possible" | Memory is tight on this PC while the game runs, and adding RAM is not an option. Every megabyte and every wake-up is a cost. §9. |

## 3. What it can and cannot know

The game exposes no live data feed. Everything comes from files.

**Can know, from `LIVE\Game.log` [seen]:** the markers below are in the user's logs. Memory note
`sc-game-log-reading` has the full list with caveats; derive the real patterns from recent files
in `LIVE\logbackups\`, not from the wording here.

| Event | Marker in the log |
| --- | --- |
| Joysticks found at launch, in order | `Connected joystick0: <name> {GUID}` |
| Session start, and its backup name | first line `BackupNameAttachment=" Build(<n>) <date> (<HH MM SS>)"`, then `Log started on ...` |
| Entered the game world | `[CSessionManager::OnClientSpawned] Spawned!` |
| Quantum target chosen | `<Player Selected Quantum Target - Local> ... selected point <CODE>` |
| Route start and fuel estimate | `<Calculate Route> ... Projected Start Location is <name> for route to destination <CODE>` and `... fuel estimate <n>` |
| Quantum arrival | `<Quantum Drive Arrived - Arrived at Final Destination>` |
| Arrival at a station or landing zone | `RequestLocationInventory Location[<name>]`, `Update Inventory Location` |
| Ship retrieved | `SetVehicleSpawningInformations - VehicleEntityId: [<id>]` |
| Ship name | notice `You have joined channel '<Ship name> : <handle>'` |
| Left the pilot seat, with ship class | `<Vehicle Control Flow> ... ClearDriver ... '<CLASS>_<id>'` |
| HUD notices | `<SHUDEvent_OnNotification> Added notification "<text>"`: jurisdiction, armistice, monitored space, hangar queue and "Hangar Request Completed", "A Refinery Work Order has been Completed at <station>", "destination is obstructed", medical bed, "Regeneration - Location", "Local Emergency Services" |
| Blueprint received | `Received Blueprint` |
| Ship destroyed | `<Vehicle Destroyed> Vehicle '<CLASS>_<id>' ... reason [<r>] ... killer '<name>'` (other players' ships appear too: match the entity id) |
| Death and lost items | `[ActorState] Dead`, one `ItemRecoveryEntitlement` line per item |
| Shop purchases and sales | `SendShopBuyRequest` / `SendShopSellRequest` (shop, price, item) and `ShopFlowResponse ... result[...]` |
| Ore sold to a refinery | `OnRefineryRequest ... SShopRefineryRequest ... shopName[SCShop_RefineryAdmin_ORE]` |
| Storage item count | `Freight Inventory Grid InventoryDataRequest Successful ... Item Count:[<n>]` |
| Mining gadget placed, with the rock's ore | `placed 'Mining_Gadget_<name>_<id>' on entity 'MineableRock_<kind>_<ore>_<id>'` |
| Which planet or moon, every 10 minutes | `PHYSICS INSTANCE STATS` block, the `planet cells:` line with a non-zero count |
| Screenshot taken | `ScreenShot: ScreenShots/<name>.jpg` |
| Session end and why | `<Channel Disconnected> cause=<n>`: 30016 the user quit, 30028 inactivity kick. 30010 also appears between the menu and the game and is not an end. |

Location codes look regular **[verify against `global.ini`]**: `LOC_RR_S3_L4` was ARC-L4 and
`LOC_RR_S4_L2` was MIC-L2, so `S1`-`S4` look like Hurston, Crusader, ArcCorp and microTech. Some
names mislead: Stanton's Nyx Gateway is `RR_JP_StantonMagnus`.

**Can know, from other files:** new Game Bar captures in `%USERPROFILE%\Videos\Captures` (name and
time only), and the plan data Claude maintains (§10).

**Cannot know [seen]:** speed, fuel, shields, cargo, what was mined, sale amounts, or the start of
a refinery order. The log only records a refinery order when it completes. Show nothing for these;
a gap is better than a guess.

## 4. Features

### First version

1. **Status strip, always visible.** Local time, session length, game state (not running, menu, in
   game, ended), current location, current ship.
2. **Preflight check at launch.** A large pass or fail for the joystick order: the AB6 must be
   joystick 1 and the MTQ joystick 2. When the stick base is not detected, the keyboard takes its
   slot and every binding lands on the wrong device ([`../CLAUDE.md`](../CLAUDE.md) §1). This has
   cost the user sessions, so it gets the loudest alert on the page. Also shows the plan's
   "before you fly" notes.
3. **Now view.** Objectives in order, the next step, needed against held for each material,
   pending orders and timers, and what there is to do at the current location.
4. **Travel view.** Destination, the legs of the current run with the finished ones marked, and
   what to do on arrival.
5. **Mining view.** For the run's target ores: the scan numbers for each cluster size in large
   type, the quality figure to take a rock at and the one to skip, look-alike readings for that
   spot, and where to refine with the bonus.
6. **Refinery view.** Which lines to refine and which to leave out, the method the user prefers,
   and the timers.
7. **Selling view.** The sell list with prices, when the plan has one for the current location.
8. **Alerts.** Red: joystick order wrong, downed or dead. Amber: hangar queue stuck past twice its
   estimate, quantum destination obstructed. Green: refinery order completed, blueprint received.
9. **Event feed.** The last 50 events in plain words with local times.
10. **Timers.** From the plan data, plus quick timers added from the page when the user is at
    their desk. A "work order completed" notice clears the matching refinery timer.
11. **Session summary.** When a session ends, a compact record is written to
    `data/sessions/`: duration, places, ships, notices, purchases, deaths. Claude's "check the
    logs" routine can read that instead of parsing the raw log again.
12. **`timeline` command.** Prints the same compact timeline for any log file. It replaces the
    scratch scripts sessions keep rewriting.
13. **`replay` command.** Feeds a past log through the dashboard at speed, so it can be built,
    tested and shown without the game running.

**Views switch by themselves.** A small table of rules maps the state to a view (§11). A view
picked by hand stays until the context next changes.

### Later, each only if the user asks

- Switching views from the keyboard while the game has focus, through a system-wide hotkey
  registered by the service. The hotkey is taken away from every other program, so choose
  combinations the game does not use (check the keyboard column of the action catalog) and ask
  the user first.
- A device watch that flags a stick or throttle dropping off USB.
- A controls view per operator mode, from the same tables the reference cards use.
- Switching views from the stick base's two unbound levers. The page cannot read them: the browser
  exposes at most 32 buttons per device and these are numbered 57 to 62 **[ref: Chromium source,
  §14]**. The service would have to read the stick itself through DirectInput.
- Contract tracking, once the markers for accepting and completing a contract are confirmed.

## 5. Shape

```
dashboard/
  PLAN.md  README.md  CLAUDE.md
  scdash.py            command-line entry point, run from the project root
  scdash/              the program: Python standard library only
    config.py          paths and defaults
    tail.py            log follower
    events.py          log line -> event
    state.py           events -> state (a pure function)
    server.py          local web server and event stream
    service.py         main loop, single instance, lifecycle
    winutil.py         the Windows-only calls, each with a harmless fallback elsewhere
  web/                 index.html, app.js, style.css: no outside resources
  reference/           generic game data, committed (§10)
  tests/               unit tests and sanitized log samples
  data/                git-ignored: the user's plan data, config, state, session records, logs
```

Data flows one way: `Game.log` -> follower -> events -> state -> page. The state is always a pure
function of the log read so far plus the plan data. That one property gives most of the
idempotence in §7.

**Standard library only**, so there is nothing to install and nothing extra in memory. The repo's
tools must stay usable on a Mac ([`../tools/CLAUDE.md`](../tools/CLAUDE.md)), so keep every
Windows-only call in `winutil.py`: the parser, `timeline` and the tests then run anywhere.

**The event stream on `http.server` [ref, §14].** Keep the server's default HTTP/1.0 responses:
HTTP/1.1 would need an exact length on every response. Each connected page holds one thread. A
closed page is only noticed when a write fails, so send a comment line every 15 seconds and catch
the connection errors. Send a `retry:` value so the page reconnects quickly, and cap the number of
connected pages: the browser allows six connections to one address.

## 6. The service

"Service" here means a per-user background process, not a Windows service in the Service Control
Manager sense. A real Windows service is the wrong tool **[ref: Microsoft's service
documentation, §14]**: creating one needs administrator rights, it runs in a separate session
that cannot show a window on the user's desktop, and under the system account it does not see the
user's own settings. The project also asks the user before anything that needs admin rights.

- **Process:** `pythonw.exe dashboard\scdash.py run --background`. No console window. Under
  `pythonw` the standard output streams can be missing, so everything is logged to a file.
- **Starts by itself:** a Task Scheduler task registered from an XML file **[ref, §14]**:
  - The logon trigger names the user's own account. That is the only form a non-admin may
    register. `schtasks /Create /SC ONLOGON` means "any user" and is refused with "Access is
    denied".
  - `InteractiveToken`, so it runs inside the user's desktop session and can open a window.
  - `ExecutionTimeLimit` `PT0S`. Without it Windows stops the task after 72 hours.
  - `DisallowStartIfOnBatteries` and `StopIfGoingOnBatteries` both false. Both default to true.
  - `MultipleInstancesPolicy` `IgnoreNew`, and a `WorkingDirectory` set to the project root. The
    default working directory is System32.
  - A five-minute repetition on the trigger. With `IgnoreNew` it does nothing while the service
    is alive, and relaunches it within five minutes if it has died.
  - If registration is still refused without elevation, fall back to a shortcut in the user's
    Startup folder and say so. Never elevate.
- **Stays up by itself:** do not count on the task's `RestartOnFailure`. Field reports say it
  does not fire after a crash or a kill. The main loop catches its own errors, logs them and
  carries on, and the repeating trigger is the backstop.
- **Idles cheaply:** with no game running it does nothing but look for the game process every 10
  seconds.
- **Follows the game:** when the game starts it begins reading the log, and can open the
  dashboard window on the side monitor. When the game has been closed for a few minutes it can
  close the window it opened, to give the memory back. Both are settings (§15).
- **Single instance:** a named mutex is the lock. Binding the port is not enough: Python's
  `http.server` sets `SO_REUSEADDR`, and on Windows that lets a second process bind the same port
  **[seen: local test, 2026-11-26]**. So the listening socket also sets
  `allow_reuse_address = False` and `SO_EXCLUSIVEADDRUSE`, which the same test showed refuses a
  second bind. The scheduler's `IgnoreNew` only stops copies the scheduler itself starts, so the
  mutex has to cover a manual `start` as well. `data/run.json` records the process id, port,
  start time and a random token. A health endpoint returns the program's name and that token, so
  a foreign program on the port is never mistaken for the service.

| Command | What it does | When repeated |
| --- | --- | --- |
| `run` | Runs in the foreground until Ctrl+C. For development. | Refuses if an instance is healthy. |
| `start` | Starts the background process and waits until it answers. | Already running: says so, exits 0. |
| `stop` | Asks the instance to shut down, using the token. | Not running: says so, exits 0. |
| `status` | State, uptime, port, game seen or not, memory in use, last event. `--json` for scripts. | Read-only. |
| `open` | Opens the dashboard window on the side monitor. | A page is already connected: does nothing. |
| `install` | Registers the logon task. | Replaces the same single task. |
| `uninstall` | Removes it. | Nothing to remove: exits 0. |
| `timeline [log]` | Prints the compact timeline of a log. | Read-only. |
| `replay <log>` | Serves the dashboard from a past log on a separate port, with its own data folder. | Never touches the live instance. |

Registering the logon task changes how Windows starts. The user asked for a service, so it is part
of this build, but tell them before running `install` and show them `uninstall`.

`install` runs `schtasks /Create /TN <name> /XML <file> /F`, which creates the task or overwrites
it. `schtasks /Delete /TN <name> /F` exits 1 when there is no task **[seen: local test by the
research agent]**, so `uninstall` treats that as success. After installing, read the task back
with `schtasks /Query /TN <name> /XML` and compare it with what was intended.

## 7. Idempotence

- **Commands:** the table above. Starting twice gives one instance; stopping twice is not an
  error.
- **State from the log:** each event is identified by the session and the byte offset of its
  line. Reading a log in one pass, in pieces of any size, or again after a restart gives the same
  state. Nothing is counted twice.
- **Restart mid-session:** the service reads the current log from the top and arrives at the same
  state as if it had watched live.
- **Files it writes:** written to a temporary file and then renamed into place, so a crash never
  leaves half a file. Only `data/` is ever written.
- **Plan data:** Claude rewrites `data/plan.json` whole each time. The dashboard never edits it.
- **Install:** `install` after `install` leaves one task, and `uninstall` puts things back as
  they were.

## 8. Safety

**The game.**

- Read-only, always. Nothing under `LIVE\` is ever written, moved or locked.
- It stays outside the game process: no memory reading, no injection, no overlay in the game
  window, no input sent to the game. It never opens a handle to `StarCitizen.exe`; it only looks
  for the name in the process list. The game runs with Easy Anti-Cheat, and this is the line that
  keeps a tool on the right side of it **[verify, research pending in §14]**.
- **The log must never be held open.** At each launch the game copies the old `Game.log` into
  `logbackups\` and starts `Game.log` again **[seen 2026-11-26: each backup's creation time is the
  next launch's start, and it has its own file id]**. Whether it truncates the file in place or
  deletes and recreates it is **[verify]**. A reader that holds the file open without allowing
  deletion could block the second case, and Python's own `open()` does not allow it on Windows.
  So open the file through `CreateFileW` with read, write and delete sharing, read the new bytes,
  and close it again on every poll. Then prove it: run the follower across a real game launch and
  confirm the backup appears and the new log starts.
- A session is identified by the first line of the log (`BackupNameAttachment=...`). When that
  line changes or the file gets shorter, start a new session from offset 0.

**The PC.**

- No administrator rights, at install or at run time.
- The server binds to `127.0.0.1` only, so nothing else on the network can reach it.
- It makes no outbound connections, and the page loads nothing from the internet: system fonts,
  no CDN.
- It serves a fixed list of its own files. No path from a request is ever used to open a file.
- Requests that change anything (timers, forced view, shutdown) need the token in a custom header
  and a JSON body, and the `Host` header must be the local address. Together these stop another
  web page in the user's browser from driving the dashboard.
- Bounded everything: line length, feed length, session records kept, its own log size.
- It runs at below-normal priority, so it yields to the game.
- It only ever closes a browser window it opened itself, identified by process id and start time.

**Privacy.** The repo is public.

- The user's handle appears in log lines (channel names, hangar names). It stays in memory and in
  `data/`, and never goes into a tracked file.
- `dashboard/data/` is git-ignored. Test samples use an invented handle.
- Before each commit, search the staged changes for the real handle. A test can do this too,
  reading the handle from the local config and skipping when there is none.
- `data/plan.json` holds the user's progress and is never committed. `plan.example.json` shows
  the schema with invented content.

## 9. Performance

Budgets to measure against, not promises. Record the measured figures in `dashboard/CLAUDE.md`.

| What | Budget |
| --- | --- |
| Service memory | 30 MB or less |
| Service CPU, game running | 0.2% of one core or less, averaged over 10 minutes |
| Service CPU, no game | effectively zero: one process check every 10 seconds |
| Reading a whole 5 MB log at startup | 1 second or less |
| Dashboard window, whole browser process tree | 250 MB or less. Expect 100 to 200 MB **[ref: an estimate from measurements of the same engine, §14; measure it]** |

How to stay inside them:

- **Read only what is new.** Check the log's size once a second with `os.stat`, then read just
  the appended bytes. Never reread the file.
- **Filter before matching.** One compiled pattern decides whether a line matters at all. Most
  lines are discarded after that single test.
- **Push, never poll.** The page holds one event stream open. The server sends the state only
  when it changes, and merges bursts into at most two sends a second. The state is a few
  kilobytes.
- **A page that does almost nothing.** No framework, no web fonts, no images, no animation. One
  one-second timer drives the clocks and countdowns. Only the parts that changed are redrawn.
- **Write to disk rarely.** The state file is saved at most every 10 seconds, and only when
  something changed.
- **Clocks from the system time.** Each tick computes the time from the clock instead of counting
  ticks, so a page that was paused or slowed is right again the moment it is visible.
- **Give memory back.** The window can close itself a few minutes after the game exits.

If the window goes over budget, measure with the browser's own task manager (Shift+Esc) before
changing anything. Showing the page in the browser the user already has open would cost roughly
one page less **[ref]**, but the placement switches are then ignored and their extensions run in
the page. The research turned up no way to show an HTML page in tens of megabytes.

## 10. Data

**`data/plan.json`: the user's plan, local only.** Claude writes it in the same routine that
updates the game plan page, so the page, memory and the dashboard always agree. The dashboard
rereads it when its modified time changes. If it is missing or invalid, the dashboard keeps the
last good copy and shows a small notice.

```json
{
  "updated": "2026-11-26T17:30:00-08:00",
  "preflight": ["Load the MOZA profile in the Keybindings menu"],
  "objectives": [
    {
      "id": "drive-ore",
      "title": "High-quality ore for the Agni and the Huracan",
      "status": "in_progress",
      "next_step": "Run B: mine Agricium and Beryl at CRU-L5",
      "materials": [
        {"name": "Tungsten", "need_scu": 2.22, "held_scu": 2.66, "min_quality": 600}
      ]
    }
  ],
  "run": {
    "name": "Run B",
    "targets": ["Agricium", "Beryl"],
    "legs": [
      {"to": "CRU-L5 field", "codes": ["LOC_RR_S2_L5"], "gm": 40.8, "view": "mining",
       "do": "Mine Agricium and Beryl"},
      {"to": "CRU-L1", "codes": ["LOC_RR_S2_L1"], "gm": 18.3, "view": "refinery",
       "do": "Refine the Beryl only"}
    ]
  },
  "timers": [
    {"id": "t1", "kind": "refinery", "label": "Tungsten order", "location": "MIC-L2",
     "ready_at": "2026-11-26T16:21:00-08:00"}
  ],
  "sell": [
    {"ore": "Taranite", "scu": 7.8, "quality": 310, "price": 28000, "where": "TDD New Babbage"}
  ],
  "notes": ["Free text shown on the Now view"]
}
```

The location codes in this example are guesses from the pattern in §3. Use the codes the log
actually prints.

**`reference/`: generic game data, committed.** Nothing here is personal. Every file carries its
source and date, and marks each figure as read from the game's files or taken from a community
source, as [`../CLAUDE.md`](../CLAUDE.md) §11 does. Build them from the memory notes
`sc-4103-gameplay-facts`, `sc-ore-quality-mechanics` and `goal-drive-ore-agni-huracan`:

- `locations.json`: log code -> display name, kind (station, field, landing zone, gateway), body.
- `ores.json`: scan value per rock, cluster sizes, the fixed quality figures, look-alikes.
- `refineries.json`: yield bonus by station and ore. Player-reported, so dated.

An unknown location code is shown raw and added to `data/unmapped.json`, so the table can grow
from real play.

**`data/state.json`, `data/sessions/`, `data/run.json`, `data/service.log`:** the service's own
files, all local, all bounded.

## 11. The page

- One page, designed for 1920x1080 at arm's length and beyond: large type, high contrast, a dark
  theme, few things per view. If it cannot be read in two seconds, it has too much on it.
- Layout: the status strip across the top, the current view in the main area, alerts and timers
  down the side, the feed at the bottom.
- Numbers the user acts on (scan values, quality figures, countdowns) get the largest type.
- Times are local. American spelling and month-first dates, as everywhere in this project.
- No sound: browsers block it until someone clicks the page.

**Opening the window [ref, §14].** Use the browser's app mode with a profile folder of its own:

```
msedge.exe --user-data-dir=<dashboard\data\browser> --app=http://127.0.0.1:<port>/
           --window-position=<x>,<y> --start-fullscreen --no-first-run
```

- The separate profile folder is required. Without it the launch is handed to the browser that is
  already running, and the placement switches are dropped.
- `<x>,<y>` is any point well inside the side monitor. Full screen then fills that monitor. F11
  leaves full screen and Alt+F4 closes the window.
- Do not use `--kiosk`: it ignores placement and is awkward to leave.
- `--disable-background-networking`, `--disable-component-update` and
  `--no-default-browser-check` are low-risk for a page served from this PC. Leave `--disable-gpu`
  and `--single-process` alone.
- A window that is visible but not focused keeps updating at full rate. One that is minimized or
  fully covered is slowed down, which costs nothing here.
- The game should run in borderless window mode, so a click on the side screen does not minimize
  it.

View rules, kept as a small table in code so they are easy to tune:

| State | View |
| --- | --- |
| No game running | Now, with the last session's summary |
| Game starting or in the menu | Preflight |
| Quantum target chosen, until arrival | Travel |
| Arrived at a leg of the current run | The view that leg names |
| At a place with a sell list | Selling |
| Downed or dead | Now, with the alert on top |
| Anything else in game | Now, for the current location |

## 12. Build order

Commit and push after each stage that works, as the project always does. Each stage ends with a
check that can actually fail.

1. **Parser and state, no server.** `tail.py`, `events.py`, `state.py`, `timeline`, tests.
   *Done when:* `timeline` on the log of 2026-11-26 afternoon reproduces the write-up in memory
   (`sc-4103-gameplay-facts`, "Tungsten Run A"), and feeding a log in random-sized pieces gives
   the same state as feeding it whole.
2. **Service and a minimal page.** `run`, `start`, `stop`, `status`, single instance, the event
   stream, the status strip and the feed, `replay`.
   *Done when:* `start` twice leaves one instance, `stop` twice is clean, `replay` of a past log
   shows the session unfolding, and the follower has been run across a real game launch without
   disturbing the log rotation.
3. **Views and plan data.** The reference files, `plan.json`, the views, the view rules, alerts,
   timers.
   *Done when:* a replay of a mining session shows Preflight, Travel, Mining and Refinery at the
   right moments, and a deliberately wrong joystick order in a test log raises the red alert.
4. **Autostart and the window.** `install`, `uninstall`, `open`, opening on the side monitor,
   closing after the game exits.
   *Done when:* after signing out and back in the service is running, starting the game opens the
   window on the side monitor, and the measured figures are inside the budgets in §9 or the
   overrun is written down with its cause.
5. **A flown session.** The user plays one session with it running.
   *Done when:* its session summary agrees with Claude's own reading of the same log, and the user
   has said what they want changed.
6. **Docs and routines** (§16).

## 13. Tests

Use `unittest` from the standard library, run from the project root.

- Events: one test per marker, on sanitized lines copied from real logs.
- State: the session life cycle, quantum travel, arrivals, a destroyed ship that is not the
  user's, death and respawn.
- Incremental reading: random-sized pieces give the same state as one pass. A partial last line
  is held until its newline arrives.
- Rotation: the log getting shorter, or its first line changing, starts a new session.
- Service: second `start`, `stop` with nothing running, the port already taken by something else.
- Server: a changing request without the token is refused, and so is one with a foreign `Host`.
- Privacy: no tracked file under `dashboard/` contains the handle from the local config.
- Speed: a 5 MB log parses inside the budget.

## 14. To check before relying on it

Research on the first three points was started on 2026-11-26. Findings are second-hand until the
build confirms them on this PC; each names its source.

1. **Answered, autostart [ref].** A non-admin may register a logon trigger only when it names the
   registering user
   ([Microsoft, MS-TSCH](https://learn.microsoft.com/en-us/openspecs/windows_protocols/ms-tsch/d90eccec-83e9-450c-b144-17633c47be9a)),
   and `schtasks /SC ONLOGON` is documented as "any user"
   ([Microsoft, schtasks create](https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/schtasks-create)).
   Task defaults, including the 72-hour limit, are in
   [Microsoft's task settings reference](https://learn.microsoft.com/en-us/windows/win32/taskschd/taskschedulerschema-settingstype-complextype).
   Why a real service does not fit is in
   [Microsoft's notes on interactive services](https://learn.microsoft.com/en-us/windows/win32/services/interactive-services).
   That `RestartOnFailure` does not fire after a crash comes from other projects' issue trackers,
   not from Microsoft. Still open: whether the task's command needs quotes around a path with
   spaces, which file encoding `schtasks /XML` accepts, and whether PowerShell's
   `Register-ScheduledTask -AtLogOn -User <self>` also works without elevation.
2. **Answered, the window [ref].** Placement switches are read only from a browser process's own
   command line, which is why the separate profile folder is needed
   ([Chromium source](https://chromium.googlesource.com/chromium/src/+/main/chrome/browser/ui/browser_window_state.cc),
   [Eric Lawrence on Chromium startup](https://textslashplain.com/2022/06/15/chromium-startup/)).
   Throttling follows visibility, not focus
   ([Chrome's timer throttling notes](https://developer.chrome.com/blog/timer-throttling-in-chrome-88)).
   The 32-button limit is in
   [Chromium's gamepad code](https://chromium.googlesource.com/chromium/src/+/main/device/gamepad/public/cpp/gamepad.h).
   Event stream behavior is in the
   [HTML standard](https://html.spec.whatwg.org/multipage/server-sent-events.html) and
   [Python's `http.server`](https://docs.python.org/3/library/http.server.html). Memory has no
   official figure: two project reports measured the same engine at about 76 MB for a blank page
   and 113 MB for a small app, and a separate profile cost about 75 MB more than a shared one.
   Still open: the window's real memory on this PC, whether `<x>,<y>` are scaled or physical
   pixels when the main monitor uses display scaling, and whether a game in exclusive full screen
   counts as covering the side monitor.
3. What other log-reading tools do, what the publisher has said about them, and whether the game
   keeps taking stick input when another window has focus.
4. Whether the game truncates `Game.log` in place or deletes and recreates it at launch. Compare
   the file id before and after a launch.
5. The markers for accepting and completing a contract, and whether anything is logged when a
   refinery order is confirmed. Look around a known time in a real log.
6. The location code pattern in §3, against `global.ini`.
7. Whether below-normal priority has any drawback for a process that wakes once a second.

## 15. The user's decisions

Use the default unless they say otherwise, and tell them what was chosen.

| Decision | Default |
| --- | --- |
| Start at logon | Yes: they asked for a service |
| Open the window when the game starts | Yes |
| Close the window a few minutes after the game exits | Yes, to give memory back |
| Which monitor | The one that is not the primary |
| Port | 47826 |
| Commit the generic reference data | Yes |
| Keyboard hotkeys for views | Not in the first version |

## 16. When it ships

- `dashboard/README.md` for people and `dashboard/CLAUDE.md` for Claude, following the docs
  convention in [`../CLAUDE.md`](../CLAUDE.md). Replace the stubs that sit there now.
- [`../CLAUDE.md`](../CLAUDE.md): the folder layout, and a short pointer to this folder.
- `../README.md`: one line that the repo also holds the dashboard.
- [`../STARCITIZEN.md`](../STARCITIZEN.md): a row in "Where things live", and in "Check the logs"
  that `timeline` and the session records exist and that `plan.json` is updated together with the
  game plan page.
- Memory: the update routine in `game-plan-artifact` gains the `plan.json` step, and
  `sc-dashboard-project` records what was built and measured.
- Turn this file into a short record of what was decided and why, or delete it once
  `dashboard/CLAUDE.md` covers it.

## 17. Out of scope

- Anything that reads or writes the game's memory, draws over the game, or sends it input.
- Reading the screen (OCR) to recover what the log leaves out.
- Anything served beyond this PC, or any account or online feature.
- Telemetry of any kind.
