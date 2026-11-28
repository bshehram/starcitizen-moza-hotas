"""The dashboard's command line. Run from the project root:

    python dashboard/scdash.py start                    # the background service; waits until it answers
    python dashboard/scdash.py status [--json]          # running or not, port, game, memory, last event
    python dashboard/scdash.py stop                     # stops it, and it stays stopped until `start`
    python dashboard/scdash.py run                      # the service in the foreground, until Ctrl+C
    python dashboard/scdash.py replay "26 Nov 26 (15 11 12)"   # a past log, at speed, on port 47827
    python dashboard/scdash.py replay <log> --plan dashboard/plan.example.json   # with a plan of its own
    python dashboard/scdash.py timeline [log] [--json] [--list --since 2026-11-26]

Every service command takes `--data <folder>` (default dashboard/data) and, where it makes sense,
`--port`, `--log`, `--live` and `--process`: an instance belongs to its data folder, so tests and
replays run beside the live one. What each command does when repeated is in PLAN.md §6.

`install`, `uninstall` and `open` belong to stage 4 (PLAN.md §12) and do nothing yet.

Import note: this script sits beside the package folder `scdash/`. Python puts the script's own
folder (dashboard/) first on sys.path, and the import system prefers a package directory over a
module file of the same name, so `import scdash` below finds the package, not this file, whether
this is run from the project root, from inside dashboard/, or by the test runner (which adds
dashboard/ to sys.path itself). It needs scdash/__init__.py to exist; without it the folder
would be a namespace package and this file would win.
"""
import argparse
import json
import os
import shutil
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

import scdash
from scdash import config, timeline

if not hasattr(scdash, "__path__"):        # guard: we must have the package, not this script
    raise SystemExit("import scdash found %s instead of the package folder" % scdash.__file__)

PLAN_COPY_MAX = 1 << 20          # `replay --plan`: a larger file is refused (the plan reader takes 256 KB)

STAGE4 = {
    "install": "register the logon task (stage 4, not built yet)",
    "uninstall": "remove the logon task (stage 4, not built yet)",
    "open": "open the dashboard window on the side monitor (stage 4, not built yet)",
}


def main(argv=None):
    ap = argparse.ArgumentParser(prog="scdash", description="Star Citizen side-screen dashboard")
    sub = ap.add_subparsers(dest="command", required=True)

    tl = sub.add_parser("timeline", help="print a compact account of one log, or list the sessions")
    tl.add_argument("log", nargs="?", help="a log file, or a piece of a backup's name (default: LIVE\\Game.log)")
    tl.add_argument("--json", action="store_true", help="the same as data")
    tl.add_argument("--all", action="store_true", help="also the minor events (zones, menus, storage)")
    tl.add_argument("--list", action="store_true", help="list the sessions in logbackups and Game.log")
    tl.add_argument("--since", help="with --list: only sessions started on or after this date (YYYY-MM-DD, local)")
    tl.add_argument("--live", help="the game's LIVE folder (default: found from the repo, or %s)" % config.LIVE_ENV)

    run = sub.add_parser("run", help="run the service in the foreground until Ctrl+C (for development)")
    _instance_args(run)
    run.add_argument("--background", action="store_true",
                     help="how `start` runs it: log to the data folder only, and exit at once after a `stop`")

    st = sub.add_parser("start", help="start the background service and wait until it answers")
    _instance_args(st)
    st.add_argument("--wait", type=float, default=15.0, help="seconds to wait for it to answer (default 15)")

    sp = sub.add_parser("stop", help="stop the service; it stays stopped until `start`")
    sp.add_argument("--data", help="the instance's data folder (default dashboard/data)")
    sp.add_argument("--port", type=_port_arg, help="the port, when there is no run.json")
    sp.add_argument("--wait", type=float, default=15.0, help="seconds to wait for it to end (default 15)")

    ss = sub.add_parser("status", help="is it running, on which port, game seen, memory, last event")
    ss.add_argument("--data", help="the instance's data folder (default dashboard/data)")
    ss.add_argument("--port", type=_port_arg, help="the port, when there is no run.json")
    ss.add_argument("--json", action="store_true", help="the same as data, for scripts")

    rp = sub.add_parser("replay", help="serve the dashboard from a past log, at speed, on a port of its own")
    rp.add_argument("log", help="a log file, or a piece of a backup's name such as \"26 Nov 26 (15 11 12)\"")
    speed = rp.add_mutually_exclusive_group()
    speed.add_argument("--speed", type=float, help="how many times faster than it was played")
    speed.add_argument("--minutes", type=float, default=1.5,
                       help="how long the whole log should take (default 1.5; ignored with --speed)")
    rp.add_argument("--port", type=_port_arg, default=config.REPLAY_PORT, help="default %d" % config.REPLAY_PORT)
    rp.add_argument("--data", help="its data folder (default: a new temporary folder, removed afterwards)")
    rp.add_argument("--keep", action="store_true", help="keep the temporary data folder")
    rp.add_argument("--terminal", action="store_true", help="lay the page out with the terminal region")
    rp.add_argument("--exit-at-end", action="store_true", help="stop when the log has been fed")
    rp.add_argument("--live", help="the game's LIVE folder, to find a backup by name")
    rp.add_argument("--plan", help="a plan.json to replay with (copied into the replay's own folder; "
                                   "for example dashboard/plan.example.json). Without it there is no plan")

    for name, text in STAGE4.items():       # stage 4 fills these in
        sub.add_parser(name, help=text)

    args = ap.parse_args(argv)
    return {"timeline": cmd_timeline, "run": cmd_run, "start": cmd_start, "stop": cmd_stop,
            "status": cmd_status, "replay": cmd_replay}.get(args.command, cmd_stage4)(args)


def _port_arg(text):
    lo, hi = config.BOUNDS["port"]
    try:
        v = int(text)
    except ValueError:
        raise argparse.ArgumentTypeError("not a number: %r" % text) from None
    if not lo <= v <= hi:
        raise argparse.ArgumentTypeError("a port from %d to %d" % (lo, hi))
    return v


def _instance_args(p):
    p.add_argument("--data", help="the instance's data folder (default dashboard/data)")
    p.add_argument("--port", type=_port_arg, help="the port (default: data/config.json, else %d)" % config.PORT)
    p.add_argument("--log", help="the log to follow (default: LIVE\\Game.log)")
    p.add_argument("--live", help="the game's LIVE folder (default: data/config.json, else found from the repo)")
    p.add_argument("--process", help="the game's process name (default StarCitizen.exe)")


def _resolve(args):
    """(Paths, settings, notes, log path) for a service command."""
    from scdash.service import Paths
    paths = Paths(args.data if args.data else config.DATA_DIR)
    overrides = {"port": getattr(args, "port", None), "game_process": getattr(args, "process", None),
                 "live": getattr(args, "live", None)}
    settings, notes = config.load_settings(paths.data, overrides)
    log = getattr(args, "log", None)
    if log:
        log = Path(log).resolve()
    else:
        live = Path(settings["live"]) if settings["live"] else config.default_live()
        log = config.game_log(live) if live else None
    return paths, settings, notes, log


# ---------------------------------------------------------------------------- run, start, stop, status

def cmd_run(args):
    from scdash import service
    paths, settings, notes, log = _resolve(args)
    if not args.background:
        info = service.instance_info(paths, settings["port"])
        if info["healthy"]:
            print("Already running (pid %d, http://127.0.0.1:%d/): not starting another."
                  % (info["run"]["pid"], info["port"]))
            return service.EXIT_RUNNING
    svc = service.Service(paths.data, log, settings, background=args.background, notes=notes,
                          console=not args.background)
    code = svc.run()
    if not args.background and svc.refusal:
        why = svc.refusal
        if why[0] == "lock":
            print("Not started: another instance holds the lock for %s." % paths.data)
        elif why[0] == "port":
            print("Not started: %s." % why[2])
    return code


def _forward(args, paths):
    out = ["--data", str(paths.data)]
    for flag, val in (("--port", args.port), ("--live", args.live), ("--process", args.process)):
        if val is not None:
            out += [flag, str(val)]
    if args.log:
        out += ["--log", str(Path(args.log).resolve())]
    return out


def _wait_healthy(paths, port, seconds):
    from scdash import service
    end = time.monotonic() + seconds
    while True:
        info = service.instance_info(paths, port)
        if info["healthy"] or time.monotonic() >= end:
            return info
        time.sleep(0.25)


def cmd_start(args):
    from scdash import service
    paths, settings, notes, log = _resolve(args)
    port = settings["port"]
    if paths.stopped.exists():
        try:
            paths.stopped.unlink()
            print("Removed the stop marker: automatic starts work again.")
        except OSError as e:
            print("Could not remove the stop marker %s (%s)." % (paths.stopped, e))
            return 1
    info = service.instance_info(paths, port)
    if info["healthy"]:
        print("Already running: pid %d, http://127.0.0.1:%d/" % (info["run"]["pid"], info["port"]))
        return 0
    if info["lock_held"]:
        info = _wait_healthy(paths, port, args.wait)
        if info["healthy"]:
            print("Already running: pid %d, http://127.0.0.1:%d/" % (info["run"]["pid"], info["port"]))
            return 0
        print("An instance holds the lock for %s but does not answer; not starting another. "
              "See %s." % (paths.data, paths.log))
        return 1
    proc = service.launch_background(_forward(args, paths))
    end = time.monotonic() + args.wait
    while time.monotonic() < end:
        code = proc.poll()
        if code is not None:
            if code == service.EXIT_RUNNING:
                info = _wait_healthy(paths, port, max(1.0, end - time.monotonic()))
                if info["healthy"]:
                    print("Already running: pid %d, http://127.0.0.1:%d/" % (info["run"]["pid"], info["port"]))
                    return 0
            if code == service.EXIT_PORT:
                kind, why = service.probe_health(port)
                if kind == "scdash":
                    print("Not started: another dashboard instance (pid %s, another data folder) is using port %d."
                          % (why.get("pid"), port))
                else:
                    print("Not started: port %d is taken by another program, not this dashboard (%s). "
                          "Set \"port\" in %s to another number." % (port, why or "it answered", paths.config))
                return service.EXIT_PORT
            print("Not started: the service exited with code %d. See %s." % (code, paths.log))
            return code or 1
        info = service.instance_info(paths, port)
        if info["healthy"]:
            print("Started: pid %d, http://127.0.0.1:%d/" % (info["run"]["pid"], info["port"]))
            return 0
        time.sleep(0.2)
    print("Started (pid %d), but it did not answer within %.0f s. See %s." % (proc.pid, args.wait, paths.log))
    return 1


def cmd_stop(args):
    from scdash import service
    from scdash.words import iso
    paths, settings, notes, log = _resolve(args)
    service.write_json(paths.stopped, {
        "stopped": iso(time.time()),
        "about": "Written by `scdash stop`. A background start that finds this file exits at once, "
                 "so a stop stays stopped; `scdash start` removes it."})
    info = service.instance_info(paths, settings["port"])
    if info["healthy"]:
        pid = info["run"]["pid"]
        try:
            asked = service.ask_to_stop(info)
        except (service.NotListening, OSError):
            asked = False
        if not asked:
            print("Could not ask the instance (pid %d) to stop." % pid)
            return 1
        end = time.monotonic() + args.wait
        while time.monotonic() < end:
            if not paths.lock().held_elsewhere() and not service.instance_info(paths, info["port"])["healthy"]:
                print("Stopped (pid %d). It stays stopped until `start`." % pid)
                return 0
            time.sleep(0.2)
        print("Asked the instance (pid %d) to stop, but it is still running after %.0f s." % (pid, args.wait))
        return 1
    if info["lock_held"]:
        print("An instance holds the lock for %s but does not answer; not stopped. See %s."
              % (paths.data, paths.log))
        return 1
    if info["run"]:
        try:
            paths.run.unlink()
        except OSError:
            pass
        print("Not running (removed a stale run.json left by pid %d). It stays stopped until `start`."
              % info["run"]["pid"])
        return 0
    print("Not running. It stays stopped until `start`.")
    return 0


def cmd_status(args):
    from scdash import service
    from scdash.words import clean_all, clock, day_clock, duration
    paths, settings, notes, log = _resolve(args)
    info = service.instance_info(paths, args.port or settings["port"])
    st = service.instance_status(info)
    out = {"running": bool(info["healthy"]), "port": info["port"], "data_dir": str(paths.data),
           "pid": info["run"]["pid"] if info["healthy"] else None,
           "stop_marker": paths.stopped.exists(), "lock_held": bool(info["lock_held"]),
           "port_user": info["port_user"], "port_note": info["port_note"], "hung": bool(info["hung"]),
           "stale_run_json": bool(info["run"] and not info["healthy"] and not info["hung"]), "status": st}
    # The session id is the log's first line, and the rest came over the wire: no control or bidi
    # character from either reaches the console, or a script reading --json.
    out = clean_all(out)
    st = out["status"]
    if args.json:
        print(json.dumps(out, indent=2, ensure_ascii=False))
        return 0
    if info["hung"]:
        print("Running but not answering: pid %d, port %d (data %s). It is this dashboard's own process, "
              "hung, suspended or busy; `stop` cannot reach it, and `start` will not start a second one."
              % (info["run"]["pid"], info["port"], paths.data))
        if out["stop_marker"]:
            print("  Note      a stop marker is present.")
        return 0
    if not info["healthy"]:
        print("Not running (data %s)." % paths.data)
        if info["lock_held"]:
            print("  An instance holds the lock but does not answer on port %d." % info["port"])
        if info["port_user"] == "foreign":
            print("  Port %d is used by another program: %s." % (info["port"], out["port_note"]))
        elif info["port_user"] == "scdash":
            print("  Port %d is used by another dashboard instance (pid %s)." % (info["port"], info["health"]["pid"]))
        if out["stale_run_json"]:
            print("  run.json is stale (left by pid %d)." % info["run"]["pid"])
        if out["stop_marker"]:
            print("  Stopped on purpose: automatic starts exit until `start`.")
        return 0
    s = st or {}
    mem = s.get("memory") or {}
    game = s.get("game") or {}
    sess = s.get("session") or {}
    lg = s.get("log") or {}
    print("Running: pid %d, http://127.0.0.1:%d/, up %s (%s mode)" % (
        info["run"]["pid"], info["port"], duration(s.get("uptime_s")), s.get("mode", "?")))
    if game.get("running"):
        print("  Game      running%s" % (" since %s" % _clock_iso(game["since"], clock) if game.get("since") else ""))
    else:
        print("  Game      not running%s" % (" (last seen %s)" % _clock_iso(game["last_seen"], clock)
                                             if game.get("last_seen") else ""))
    print("  Log       %s (%s, at byte %s)" % (lg.get("path"), lg.get("status"), lg.get("offset")))
    print("  Session   %s, %s events, last at %s" % (
        sess.get("id"), sess.get("events"), _clock_iso(sess.get("last_event"), clock) or "-"))
    if sess.get("unreadable"):
        print("  Unreadable lines skipped: %d" % sess["unreadable"])
    if sess.get("withheld"):
        print("  Notices withheld (a shape that may name a player, not read): %d" % sess["withheld"])
    mb = lambda v: "%.1f MB" % (v / 1e6) if v else "?"   # noqa: E731
    print("  Memory    %s private working set, %s working set, %s committed" % (
        mb(mem.get("private_ws")), mb(mem.get("working_set")), mb(mem.get("private"))))
    print("  CPU       %.1f s in all; below-normal priority: %s" % (s.get("cpu_s", 0), "yes" if s.get("below_normal_priority") else "no"))
    print("  Pages     %s connected; %s state sends; %s errors caught" % (
        s.get("pages"), s.get("publishes"), s.get("errors")))
    b = s.get("board") or {}
    if b.get("view"):
        how = "picked by hand; the rules would show %s" % b.get("auto") if b.get("picked") else "rule %s" % b.get("rule")
        nxt = _clock_iso(b.get("next_change"), day_clock) if b.get("next_change") else None
        print("  View      %s (%s)%s" % (b["view"], how, "; changes by itself at %s" % nxt if nxt else ""))
    pl = s.get("plan") or {}
    if pl:
        if pl.get("loaded"):
            print("  Plan      loaded%s%s" % ("; run %s" % pl["run"] if pl.get("run") else "",
                                           "; updated %s" % _clock_iso(pl["updated"], day_clock) if pl.get("updated") else ""))
        else:
            print("  Plan      none")
        if pl.get("notice"):
            print("  Notice    %s" % pl["notice"])
    if b:
        probs = b.get("problem_list") or []
        print("  Problems  %d%s" % (b.get("problems") or 0, ": %s" % "; ".join(probs) if probs else ""))
    if out["stop_marker"]:
        print("  Note      a stop marker is present, though it runs (a manual `run`?)")
    return 0


def _clock_iso(text, clock):
    if not text:
        return None
    t = datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()
    return clock(t)


# ---------------------------------------------------------------------------- replay

def cmd_replay(args):
    from scdash import service
    from scdash.words import iso
    live = Path(args.live) if args.live else config.default_live()
    src = timeline.find_log(args.log, live)
    if not timeline.is_session_log(src):
        raise SystemExit("%s is a launcher shader-cache run, not a game session" % src.name)
    if args.port == config.PORT:
        raise SystemExit("replay never uses the live port %d: pick another with --port" % config.PORT)
    live_data = config.DATA_DIR.resolve()
    temp = args.data is None
    data = Path(tempfile.mkdtemp(prefix="scdash-replay-")) if temp else Path(args.data).resolve()
    if data == live_data or live_data in data.parents:
        raise SystemExit("replay never uses the live data folder %s: pick another with --data" % live_data)
    try:
        for name in ("source.log", "Game.log", "plan.json"):  # opened in place: never through a link (PLAN §8)
            bad = service.link_on_the_way(data, data / "replay" / name, include_self=True)
            if bad is not None:
                raise SystemExit("replay never writes through a junction or a link: %s" % bad)
        # The replay's plan is its own copy, data/replay/plan.json: taken from --plan, or none at
        # all (a copy an earlier replay left in a kept folder is removed). The live plan is never read.
        plan_copy = data / "replay" / "plan.json"
        if args.plan:
            plan_src = Path(args.plan)
            try:
                size = plan_src.stat().st_size
            except OSError as e:
                raise SystemExit("--plan %s cannot be read (%s)" % (plan_src, e.__class__.__name__)) from None
            if size > PLAN_COPY_MAX:
                raise SystemExit("--plan %s is larger than %d KB, more than a plan can be" % (plan_src, PLAN_COPY_MAX // 1024))
            service.atomic_write(plan_copy, plan_src.read_bytes()[:PLAN_COPY_MAX + 1])
        elif plan_copy.exists():
            plan_copy.unlink()
        # A copy in the replay's own folder, taken now: the feed may take minutes, and a live
        # Game.log must never be held open that long (PLAN §8).
        copy = service.copy_log(src, data / "replay" / "source.log")
        first, last = service.log_span(copy)
        if first is None:
            raise SystemExit("%s has no timed first line: not a game log" % src)
        span = (last - first) if last else 0.0
        speed = args.speed if args.speed else max(1.0, span / max(1.0, args.minutes * 60))
        settings, notes = config.load_settings(data, {"port": args.port})
        settings.update(poll_seconds=0.25, process_check_seconds=0.5, state_save_seconds=2.0)
        settings["terminal"] = {"enabled": bool(args.terminal)}
        feed = data / "replay" / "Game.log"
        clock = service.ReplayClock(first, speed)
        feeder = service.ReplayFeeder(copy, feed, clock)
        info = {"source": src.name, "speed": round(speed, 1), "from": iso(first), "to": iso(last)}
        svc = service.Service(data, feed, settings, mode="replay", clock=clock, probe=feeder, feeder=feeder,
                              notes=notes, replay_info=info, exit_when_done=args.exit_at_end, console=True,
                              plan_path=plan_copy)
        feeder.logger = svc.log
        print("Replay of %s (%s of log) at %.1fx%s: http://127.0.0.1:%d/  data %s%s. Ctrl+C to stop." % (
            src.name, _span_words(span), speed, " with the plan %s" % Path(args.plan).name if args.plan else "",
            args.port, data, " (temporary)" if temp and not args.keep else ""))
        sys.stdout.flush()
        code = svc.run()
        if svc.refusal and svc.refusal[0] == "port":
            print("Not started: %s." % svc.refusal[2])
        return code
    finally:
        if temp and not args.keep:
            shutil.rmtree(data, ignore_errors=True)


def _span_words(seconds):
    from scdash.words import duration
    return duration(seconds)


# ---------------------------------------------------------------------------- stage 4, timeline

def cmd_stage4(args):
    print("`%s` comes in stage 4 (dashboard/PLAN.md §12): nothing was done." % args.command)
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
    # Under pythonw there are no standard streams: give them somewhere harmless to go.
    for _name in ("stdout", "stderr"):
        if getattr(sys, _name) is None:
            setattr(sys, _name, open(os.devnull, "w", encoding="utf-8"))
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
