# `dashboard/`

A small local dashboard for a second monitor: it will read Star Citizen's own log file while the
game runs and show the current location, the next step of the plan, the numbers needed for the job
in hand, timers and alerts. It only reads files. It never touches the game.

**What exists now: the log reader (stage 1 of the plan).** It reads a game log and prints a short,
readable account of the session in your local time: the joystick check (is the AB6 base joystick 1
and the MTQ throttle joystick 2?), where you went, ships, quantum jumps, contracts, refinery
orders, trades, deaths, and how the session ended. There is no background service and no page yet.

Run these from the repo's root folder (Python 3, nothing to install):

```sh
python dashboard/scdash.py timeline                           # the current Game.log
python dashboard/scdash.py timeline "26 Nov 26 (15 11 12)"    # an older session, by part of its name
python dashboard/scdash.py timeline --list --since 2026-11-26 # the sessions since a date
python dashboard/scdash.py timeline --json                    # the same as data
python -m unittest discover -s dashboard/tests                # the tests
```

`timeline` finds the game folder from where this repo sits inside it. In a copy of the repo
somewhere else, add `--live <path to the LIVE folder>` or give the log file's path.

Your own play data (plan, saved state, session records) will live in `dashboard/data/`, which is
never committed: this repo is public. The code that came from another open-source project is
credited in `THIRD_PARTY_NOTICES`. The design for the whole dashboard is `PLAN.md` in this folder.

Back to the [project README](../README.md).
