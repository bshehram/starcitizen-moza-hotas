"""The dashboard's command line. Run from the project root:

    python dashboard/scdash.py timeline                 # the current Game.log
    python dashboard/scdash.py timeline "26 Nov 26 (15 11 12)"   # a backup, by a piece of its name
    python dashboard/scdash.py timeline <path> --json   # the same as data
    python dashboard/scdash.py timeline --list --since 2026-11-26

Only stage 1 exists: `timeline`. The service commands (run, start, stop, status, ...) come in
stage 2 (dashboard/PLAN.md §6).

Import note: this script sits beside the package folder `scdash/`. Python puts the script's own
folder (dashboard/) first on sys.path, and the import system prefers a package directory over a
module file of the same name, so `import scdash` below finds the package, not this file, whether
this is run from the project root, from inside dashboard/, or by the test runner (which adds
dashboard/ to sys.path itself). It needs scdash/__init__.py to exist; without it the folder
would be a namespace package and this file would win.
"""
import argparse
import sys
from datetime import datetime
from pathlib import Path

import scdash
from scdash import config, timeline

if not hasattr(scdash, "__path__"):        # guard: we must have the package, not this script
    raise SystemExit("import scdash found %s instead of the package folder" % scdash.__file__)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="scdash", description="Star Citizen side-screen dashboard (stage 1)")
    sub = ap.add_subparsers(dest="command", required=True)
    tl = sub.add_parser("timeline", help="print a compact account of one log, or list the sessions")
    tl.add_argument("log", nargs="?", help="a log file, or a piece of a backup's name (default: LIVE\\Game.log)")
    tl.add_argument("--json", action="store_true", help="the same as data")
    tl.add_argument("--all", action="store_true", help="also the minor events (zones, menus, storage)")
    tl.add_argument("--list", action="store_true", help="list the sessions in logbackups and Game.log")
    tl.add_argument("--since", help="with --list: only sessions started on or after this date (YYYY-MM-DD, local)")
    tl.add_argument("--live", help="the game's LIVE folder (default: found from the repo, or %s)" % config.LIVE_ENV)
    args = ap.parse_args(argv)

    if args.command == "timeline":
        return cmd_timeline(args)
    return 2


def cmd_timeline(args):
    live = Path(args.live) if args.live else config.default_live()
    if args.list:
        if live is None:
            raise SystemExit("LIVE folder unknown: pass --live or set %s" % config.LIVE_ENV)
        since = None
        if args.since:
            since = datetime.strptime(args.since, "%Y-%m-%d").astimezone().timestamp()
        rows = timeline.list_sessions(live, since)
        if args.json:
            print(timeline.dumps(timeline.rows_json(rows)))
        else:
            sys.stdout.write(timeline.render_list(rows))
        return 0
    if args.log:
        path = timeline.find_log(args.log, live)
    else:
        if live is None:
            raise SystemExit("LIVE folder unknown: pass a log path, --live, or set %s" % config.LIVE_ENV)
        path = config.game_log(live)
    reader, summary = timeline.run(path)
    if args.json:
        print(timeline.dumps(timeline.render_json(reader, summary, show_all=args.all)))
    else:
        sys.stdout.write(timeline.render_text(reader, summary, show_all=args.all))
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
