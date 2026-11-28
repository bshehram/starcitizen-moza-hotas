# `dashboard/`

A small local dashboard for a second monitor: it will read Star Citizen's own log file while the
game runs and show the current location, the next step of the plan, the numbers needed for the job
in hand, timers and alerts. It only reads files. It never touches the game.

**What exists now: the log reader (stage 1 of the plan), the background service (stage 2) and the
page with its views and the rig reference (stage 3).** The log reader prints a short, readable
account of a session in your local time: the joystick check (are both the AB6 base and the MTQ
throttle connected? a different order in the list is only a note), where you went, ships, quantum
jumps, contracts, refinery orders, trades, deaths, and how the session ended. The service follows
the game's log while you play, works out which view fits the moment, the alerts and timers, and
what your plan file says, and serves the page at http://127.0.0.1:47826/. `open` shows that page in
a window of its own (see "The dashboard's own window" below); any browser tab at that address
works too. Starting by itself at sign-in, and opening the window by itself when the game starts,
come in a later stage.

**What the page shows.** Across the top, the status strip: the time, the game's state, the joystick
check as a clear pass or fail, the session's length, where you are and your ship. Under it, one
view at a time, chosen by the dashboard from what the game's log says and from the plan: Preflight
at the main menu (red when the stick base or the throttle is missing), Travel during a quantum
jump, Mining, Salvage, Combat, Cargo or Mission by the contract, the run's leg or the ship,
Refinery and Selling at the plan's places, Now otherwise, and Idle when no game runs. Alerts run
across the top of the view (at most three, the rest counted on one line); timers are inside the
views; the latest events are at the bottom.

**With the mouse, at the desk.** The cells at the right end of the status strip: *Live* (the
dashboard chooses), the menu button, and *Rig reference*. The menu picks a view by hand (it stays
until the situation changes, or until *Back to Live*), and adds or removes a quick timer (type a
name if you like, then a duration). A click the service could not take is said at the bottom
right. Nothing needs the keyboard, and the page never takes focus by itself.

**Rig reference.** *Rig reference* opens the MOZA stick and throttle: eight pages (grip front, grip
side, base; keypad, dials, levers, right module, left module) and Find. Each page is the
manufacturer's diagram, its buttons numbered, beside the list of what each control does. Point at
a row to see its button ringed on the diagram, or the other way round; click either to see the
control's job in every mode. The mode filter (All, Flight, Mining, Salvage) opens on the mode the
dashboard thinks you are in: under Mining or Salvage the controls that change job are cyan and the
ones that do nothing there are gray. Find lists every control; type a button number or a word to
narrow it. The reference stays open until you click *Live*.

Run these from the repo's root folder (Python 3, nothing to install):

```sh
python dashboard/scdash.py timeline                           # the current Game.log
python dashboard/scdash.py timeline "26 Nov 26 (15 11 12)"    # an older session, by part of its name
python dashboard/scdash.py timeline --list --since 2026-11-26 # the sessions since a date
python dashboard/scdash.py timeline --json                    # the same as data
python -m unittest discover -s dashboard/tests                # the tests (about five minutes)
```

The service:

```sh
python dashboard/scdash.py start      # starts it in the background (no window) and waits until it answers
python dashboard/scdash.py status     # is it running, is the game seen, its memory and CPU, the view and the plan
python dashboard/scdash.py stop       # stops it; it stays stopped until the next `start`
python dashboard/scdash.py run        # the same in the foreground, until Ctrl+C
python dashboard/scdash.py replay "26 Nov 26 (15 11 12)"   # a past session, at speed, on port 47827
python dashboard/scdash.py replay "26 Nov 26 (15 11 12)" --plan dashboard/plan.example.json   # with a plan
```

A replay never reads your own plan: it has none unless `--plan` names a file, which it copies into
its own temporary folder.

Repeating a command is safe: a second `start` finds the running one, a second `stop` says it is not
running. With no game running it only looks for the game every 10 seconds. It only reads the game's
files, listens on this PC alone (127.0.0.1), and runs below normal priority. To change a setting
(the port, for example), copy `config.example.json` to `data/config.json` and edit that copy; every
setting is explained in the example.

## The dashboard's own window

```sh
python dashboard/scdash.py open              # starts the service if needed, then opens the window
python dashboard/scdash.py open --portrait   # the same, shaped for a monitor stood on its end
python dashboard/scdash.py shortcut          # writes dashboard/SC Dashboard.lnk, which runs `open`
python dashboard/scdash.py shortcut --desktop   # ... and puts a copy on your Desktop
```

`open` shows the page in Microsoft Edge's app mode (Google Chrome if Edge is missing): a window
with no tabs, address bar or toolbar, and its own button on the taskbar. If the service is not
running, `open` starts it first, as `start` does (it also clears a stop marker). If the window is
already open, it says so and opens nothing; a page open in an ordinary browser tab does not count,
so the window still opens beside it.

- **With one screen** (until the side monitor is connected), the window opens in the middle of
  the main screen, sized so the page gets 1920x1080 (1080x1920 with `--portrait`), the side
  monitor's own size, or as much as the screen has room for. Move it and resize it as you like.
- **With a second screen connected**, it fills that screen, in whichever way the screen stands
  (F11 leaves full screen, Alt+F4 closes the window). `--main` keeps it a window on the main
  screen instead. This part has not been tried yet: the side monitor was not connected when it
  was written.
- **Another browser:** `--browser chrome.exe` (or the full path to the program), or set it once
  in `data/config.json` under `"window"` (see `config.example.json`). It has to be a Chromium
  browser.

**The shortcut, for the taskbar.** `shortcut` writes `dashboard/SC Dashboard.lnk`. It runs `open`
through `pythonw`, so no console window appears; if something goes wrong (no browser, the
service will not start) you get a message box, and the problem is also written to
`data/service.log`. To pin it to the taskbar, right-click the shortcut, choose **Show more
options**, then **Pin to taskbar** (the same menu has **Pin to Start**); dragging it onto the
taskbar works too. The window then gets a taskbar button of its own while it is open. A shortcut
holds the full paths of Python and of this folder, so it is never committed (`*.lnk` is in the
repo's `.gitignore`): make it again with `shortcut` after Python or the repo moves. Its icon is
`scdash.ico`, made by `make_icon.py` (needs Pillow).

**The window's browser profile.** The window runs from a browser profile of its own, in
`%LOCALAPPDATA%\scdash\browser`, outside this repo and the game folder: it holds the window's own
cache and remembers where you put the window, and nothing in it is shared with your everyday
browser. It is started with the options that stop a new profile from going online by itself
(updates, sync, first-run pages). To remove it, close the dashboard window and delete the folder,
for example in PowerShell:

```powershell
Remove-Item -Recurse -Force "$env:LOCALAPPDATA\scdash\browser"
```

The next `open` makes a fresh one. The window runs below normal priority, so it gives way to the
game, as the service does.

## Setting up on a fresh Windows install

The dashboard is not finished, so this list is short. It will grow as later stages add autostart
and the Claude terminal. Every step is safe to repeat.

1. **Python 3.12 or newer**, with `python` on your PATH. The dashboard needs nothing else: it
   uses the standard library only. (The other tools in this repo need
   `python -m pip install -r tools/requirements.txt`.)
2. **The repo in its place inside the game folder:**
   `...\StarCitizen\LIVE\user\client\0\controls\mappings`. If you fetch it again, use
   `gh repo clone bshehram/starcitizen-moza-hotas` or the HTTPS address.
3. **Check it:** run the tests command above from the repo's root folder. Everything should pass.
   Two privacy tests are skipped until the game has written a log.
4. **The window's shortcut:** `python dashboard/scdash.py shortcut --desktop`, then pin it to the
   taskbar as described in "The dashboard's own window" above. Microsoft Edge comes with Windows,
   so nothing else is needed.
5. **Optional, for the telemetry readouts in a later stage:** the game only serves its local
   telemetry stream when the RSI Launcher was started with one variable set. To set it for your
   Windows user, run `setx GRPC_CLIENT_SERVER_ENABLED true`, then quit the launcher completely
   and start it again. To undo it, run `reg delete HKCU\Environment /v GRPC_CLIENT_SERVER_ENABLED`
   and restart the launcher. Nothing in the dashboard reads the stream yet.

Not needed yet, because those stages are not built: registering the start-at-sign-in task
(`python dashboard/scdash.py install`) and installing Claude Code for the terminal panel.

`timeline` finds the game folder from where this repo sits inside it. In a copy of the repo
somewhere else, add `--live <path to the LIVE folder>` or give the log file's path.

Your own play data (settings, saved state with your quick timers, session records, the service's
log, and the plan in `data/plan.json`, which Claude writes and the dashboard only reads) lives in
`dashboard/data/`, which is never committed: this repo is public. The saved state is never
overwritten before it has been read: if another program holds it, the dashboard waits, and if it
is damaged, the dashboard renames it to `state.damaged.json` and starts afresh, so your timers can
still be recovered from that copy. A later damaged file goes to `state.damaged-2.json` and so on:
the first copy is never replaced. A file saved with a byte-order mark (as Windows PowerShell
does) is read normally. The code that came from another open-source project is
credited in `THIRD_PARTY_NOTICES`. The design for the whole dashboard is `PLAN.md` in this folder.

Back to the [project README](../README.md).
