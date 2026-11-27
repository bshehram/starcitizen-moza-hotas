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
you are, your ship, alerts, and the latest events. The views (mining, travel and the rest), starting
by itself at sign-in and opening its own window come in later stages.

Run these from the repo's root folder (Python 3, nothing to install):

```sh
python dashboard/scdash.py timeline                           # the current Game.log
python dashboard/scdash.py timeline "26 Nov 26 (15 11 12)"    # an older session, by part of its name
python dashboard/scdash.py timeline --list --since 2026-11-26 # the sessions since a date
python dashboard/scdash.py timeline --json                    # the same as data
python -m unittest discover -s dashboard/tests                # the tests (about 90 seconds)
```

The service:

```sh
python dashboard/scdash.py start      # starts it in the background (no window) and waits until it answers
python dashboard/scdash.py status     # is it running, is the game seen, its memory and CPU
python dashboard/scdash.py stop       # stops it; it stays stopped until the next `start`
python dashboard/scdash.py run        # the same in the foreground, until Ctrl+C
python dashboard/scdash.py replay "26 Nov 26 (15 11 12)"   # a past session, at speed, on port 47827
```

Repeating a command is safe: a second `start` finds the running one, a second `stop` says it is not
running. With no game running it only looks for the game every 10 seconds. It only reads the game's
files, listens on this PC alone (127.0.0.1), and runs below normal priority. To change a setting
(the port, for example), copy `config.example.json` to `data/config.json` and edit that copy; every
setting is explained in the example.

`timeline` finds the game folder from where this repo sits inside it. In a copy of the repo
somewhere else, add `--live <path to the LIVE folder>` or give the log file's path.

Your own play data (settings, saved state, session records, the service's log, later the plan)
lives in `dashboard/data/`, which is never committed: this repo is public. The code that came from another open-source project is
credited in `THIRD_PARTY_NOTICES`. The design for the whole dashboard is `PLAN.md` in this folder.

Back to the [project README](../README.md).
