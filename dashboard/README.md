# `dashboard/`

A small local dashboard for a second monitor: it will read Star Citizen's own log file while the
game runs and show the current location, the next step of the plan, the numbers needed for the job
in hand, timers and alerts. It only reads files. It never touches the game.

**What exists now: the log reader (stage 1 of the plan) and the background service with a first
page (stage 2).** The log reader prints a short, readable account of a session in your local time:
the joystick check (are both the AB6 base and the MTQ throttle connected? a different order in the
list is only a note), where you went,
ships, quantum jumps, contracts, refinery orders, trades, deaths, and how the session ended. The
service follows the game's log while you play and serves a page at http://127.0.0.1:47826/: the
time, the session's length, the game's state, the joystick check as a clear pass or fail, where
you are, your ship, alerts, and the latest events. Open that address in any browser tab; the
dashboard's own window comes later.

**Also built, but not on the page yet: the logic behind the views (stage 3).** The service already
works out which view fits the moment (mining, travel, preflight and the rest), the alerts and
timers, and what your plan file says, and sends it all to the page; the page will draw it in the
next part of stage 3. It also serves the rig reference's data and diagrams, and takes four changes
from the page: pick a view by hand, go back to the live choice, add a quick timer, remove one.
Starting by itself at sign-in and opening its own window come in later stages.

Run these from the repo's root folder (Python 3, nothing to install):

```sh
python dashboard/scdash.py timeline                           # the current Game.log
python dashboard/scdash.py timeline "26 Nov 26 (15 11 12)"    # an older session, by part of its name
python dashboard/scdash.py timeline --list --since 2026-11-26 # the sessions since a date
python dashboard/scdash.py timeline --json                    # the same as data
python -m unittest discover -s dashboard/tests                # the tests (about three minutes)
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

## Setting up on a fresh Windows install

The dashboard is not finished, so this list is short. It will grow as later stages add autostart,
the window and the Claude terminal. Every step is safe to repeat.

1. **Python 3.12 or newer**, with `python` on your PATH. The dashboard needs nothing else: it
   uses the standard library only. (The other tools in this repo need
   `python -m pip install -r tools/requirements.txt`.)
2. **The repo in its place inside the game folder:**
   `...\StarCitizen\LIVE\user\client\0\controls\mappings`. If you fetch it again, use
   `gh repo clone bshehram/starcitizen-moza-hotas` or the HTTPS address.
3. **Check it:** run the tests command above from the repo's root folder. Everything should pass.
   Two privacy tests are skipped until the game has written a log.
4. **Optional, for the telemetry readouts in a later stage:** the game only serves its local
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
