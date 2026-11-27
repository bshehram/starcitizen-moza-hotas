"""The `timeline` command: a compact, readable account of one log, and a list of past sessions.

All times print in the user's local time (this computer's zone unless a `tz` is passed), with
American month-first dates. Nothing here writes anywhere: it reads the log and prints.
"""
import json
import os
import re
from pathlib import Path

from . import config
from .events import session_id
from .names import LocationNames
from .pipeline import read_whole
from .records import parse_ts
from .winutil import open_shared
from .words import clock, day, duration, local, money, ship_class

TS_RE = re.compile(rb"<(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3})Z>")
QUIT_MARK = b"<SystemQuit>"
TAIL_BYTES = 64 * 1024        # <SystemQuit> was within the last 714 bytes of every 2026-11 log [seen]


def load_names():
    return LocationNames.load(config.LOCATIONS_FILE)


def is_session_log(path):
    """A `PSOCacheGen ...log` is a launcher shader-cache run, not a session [seen: one, dated
    2026-11-05]. Its first line has the same form as a session's, so only the name tells."""
    return not Path(path).name.startswith("PSOCacheGen")


def run(path, names=None):
    """Read one whole log. Returns (reader, summary)."""
    if not is_session_log(path):
        raise SystemExit("%s is a launcher shader-cache run, not a game session" % Path(path).name)
    reader = read_whole(path, names if names is not None else load_names())
    return reader, reader.summary(complete=not _is_live(path, reader))


def _is_live(path, reader):
    """Game.log whose session has not quit may still be running; a backup never is."""
    return Path(path).name == "Game.log" and reader.state.session["ended"] is None


# ---------------------------------------------------------------------------- text

def _lines_to_show(lines, show_all):
    shown = [x for x in lines if show_all or x["level"] != "minor"]
    out = []
    i = 0
    while i < len(shown):
        x = shown[i]
        nxt = shown[i + 1] if i + 1 < len(shown) else None
        # "Left the server" and "Quit the game" a moment later read as one thing
        if x["kind"] == "disconnected" and nxt and nxt["kind"] == "quit" and nxt["t"] - x["t"] < 10:
            out.append(dict(x, text="Left the server and quit the game"))
            i += 2
            continue
        out.append(x)
        i += 1
    return out


def render_text(reader, summary, tz=None, show_all=False):
    st = reader.state
    s = st.session
    out = []
    if s["id"] is None:
        return "No session in this log (it is empty, or not a game log).\n"
    out.append("Session   %s" % s["id"])
    if s["start"] is not None:
        out.append("Started   %s %s (%s)    game %s" % (
            day(s["start"], tz), clock(s["start"], tz), local(s["start"], tz).tzname(),
            s["version"] or "version not logged"))
    shards = st.server["shards"]
    out.append("Server    %s" % (", ".join(shards) if shards else "none joined"))
    if st.joysticks:
        out.append("Sticks    " + "  ".join("%d %s" % (j["index"] + 1, j["name"]) for j in st.joysticks))
    else:
        out.append("Sticks    none logged")
    pf = st.preflight
    out.append("          %s: %s" % ({True: "PASS", False: "FAIL", None: "UNKNOWN"}[pf["ok"]], pf["text"]))
    if st.profile:
        out.append("Profile   %s loaded at %s" % (st.profile["name"], clock(st.profile["t"], tz)))
    out.append("")
    for x in _lines_to_show(reader.all_lines, show_all):
        mark = "!" if x["level"] == "alert" else " "
        out.append("%s %11s  %s" % (mark, clock(x["t"], tz), x["text"]))
    out.append("")
    out.extend(render_summary(summary, st, tz))
    return "\n".join(out) + "\n"


def render_summary(sm, st, tz=None):
    n = st.names
    out = ["Summary"]
    dur = sm["duration_s"]
    out.append("  Duration    %s (in the game world %s)" % (duration(dur), duration(sm["in_game_s"])))
    e = sm["ended"]
    if e["how"] == "quit":
        out.append("  Ended       quit at %s" % clock(st.session["ended"]["t"], tz))
    elif e["how"] == "running":
        out.append("  Ended       not yet: no quit line so far (the game may still be running)")
    else:
        out.append("  Ended       the log stops at %s with no quit line: the game crashed or was killed"
                   % (clock(parse_iso(e["t"]), tz) if e["t"] else "?"))
    if sm["left_server"]:
        out.append("  Server      " + "; ".join(
            "%s %s" % (clock(parse_iso(x["t"]), tz), x["what"]) for x in sm["left_server"]))
    places, last = [], None
    for p in sm["places"]:
        if p["place"] != last:                     # two codes for one place count once
            places.append(p["name"])
            last = p["place"]
    out.append("  Places      " + (" -> ".join(places) if places else "none logged"))
    ships = []
    for sh in sm["ships"]:
        label = sh["name"] or (ship_class(sh["class"]) if sh["class"] else "a ship")
        ships.append("%s [%s]" % (label, sh["status"]))
    out.append("  Ships       " + (", ".join(ships) if ships else "none"))
    jumps = sm["jumps"]
    if jumps:
        arrived = sum(1 for j in jumps if j["arrived"])
        out.append("  Quantum     %d target%s, %d arrival%s logged" % (
            len(jumps), "s" if len(jumps) != 1 else "", arrived, "s" if arrived != 1 else ""))
    if sm["contracts"]:
        out.append("  Contracts   " + "; ".join(
            "%s (%s)" % (c["title"] or c["internal"] or "untitled", c["status"] or "unknown")
            for c in sm["contracts"]))
    else:
        out.append("  Contracts   none")
    if sm["notices"]:
        out.append("  Notices     " + "; ".join(
            "%s (%s)" % (x["text"], clock(parse_iso(x["t"]), tz)) for x in sm["notices"]))
    tr = sm["trade"]
    priced = [r for r in tr if r["price"] is not None]
    parts = []
    if priced:
        parts.append("%d with a price: spent %s, earned %s aUEC" % (
            len(priced), money(sm["trade_totals"]["spent"]), money(sm["trade_totals"]["earned"])))
    refinery = sum(1 for r in tr if r["kind"] == "refinery_sell")
    if refinery:
        parts.append("ore sold to a refinery %d time%s (amount not logged)" % (refinery, "s" if refinery > 1 else ""))
    failed = sum(1 for r in tr if r["result"] not in (None, "Success"))
    if failed:
        parts.append("%d did not go through" % failed)
    out.append("  Trade       " + ("; ".join(parts) if parts else "none"))
    if sm["deaths"]:
        out.append("  Deaths      " + "; ".join(
            "%s (%s%s)" % (clock(parse_iso(d["t"]), tz), d["cause"],
                           ", %d items left on the body" % d["items_lost"] if d["items_lost"] else "")
            for d in sm["deaths"]))
    else:
        out.append("  Deaths      none")
    if sm["unreadable"]:
        out.append("  Unreadable  %d line%s skipped" % (sm["unreadable"], "s" if sm["unreadable"] != 1 else ""))
    if sm["recoveries"]:
        out.append("  Recovered   " + "; ".join(
            "%s (%s, up again at %s with no respawn)" % (clock(parse_iso(r["t"]), tz), r["cause"],
                                                         clock(parse_iso(r["up"]), tz))
            for r in sm["recoveries"]))
    if sm["ships_lost"]:
        out.append("  Ships lost  " + "; ".join(
            "%s %s (%s)" % (clock(parse_iso(x["t"]), tz), x["class"], x["reason"]) for x in sm["ships_lost"]))
    if sm["screenshots"]:
        out.append("  Screenshots %d" % sm["screenshots"])
    if sm["unmapped"]:
        out.append("  Unnamed     %s" % ", ".join(sm["unmapped"]))
    return out


def parse_iso(s):
    return parse_ts(s[:23]) if s else None


def render_json(reader, summary, tz=None, show_all=False):
    st = reader.state
    return {
        "session": st.session["id"],
        "header": {"start": summary["start"], "version": st.session["version"],
                   "servers": list(st.server["shards"]),
                   "joysticks": [dict(j, number=j["index"] + 1) for j in st.joysticks],
                   "preflight": dict(st.preflight),
                   "profile": st.profile["name"] if st.profile else None},
        "events": [{"id": x["id"], "t": iso_local(x["t"], tz), "utc": x_iso(x["t"]), "level": x["level"],
                    "kind": x["kind"], "text": x["text"], "offset": x["offset"]}
                   for x in _lines_to_show(reader.all_lines, show_all)],
        "summary": summary,
    }


def iso_local(t, tz=None):
    return local(t, tz).isoformat(timespec="seconds")


def x_iso(t):
    from .words import iso
    return iso(t)


# ---------------------------------------------------------------------------- session list

def list_sessions(live, since=None):
    """Every session log in logbackups (and Game.log), from a quick read of each file's head and
    tail: local start, length, how it ended. A `PSOCacheGen ...` file is a launcher shader run,
    not a session, and is skipped [seen: one, 2026-11-05]."""
    rows = []
    d = config.backups_dir(live)
    paths = []
    if d.is_dir():
        paths = [d / name for name in os.listdir(d)
                 if name.startswith("Game ") and name.endswith(".log")]
    gl = config.game_log(live)
    if gl.exists():
        paths.append(gl)
    for p in paths:
        row = _scan(p)
        if row is None:
            continue
        if since is not None and row["start"] is not None and row["start"] < since:
            continue
        rows.append(row)
    rows.sort(key=lambda r: (r["start"] is None, r["start"] or 0))
    return rows


def _scan(path):
    try:
        f = open_shared(path)
    except OSError:
        return None
    try:
        size = os.fstat(f.fileno()).st_size
        head = f.read(4096)
        f.seek(max(0, size - TAIL_BYTES))
        tail = f.read(TAIL_BYTES)
    finally:
        f.close()
    first = head.split(b"\n", 1)[0].rstrip(b"\r")
    if b"BackupNameAttachment=" not in first:
        return None
    m = TS_RE.match(first)
    start = parse_ts(m.group(1).decode()) if m else None
    stamps = TS_RE.findall(tail)
    end = parse_ts(stamps[-1].decode()) if stamps else start
    quit_at = tail.rfind(QUIT_MARK)
    if quit_at >= 0:
        ended = "quit"
    elif path.name == "Game.log":
        ended = "running or crashed"
    else:
        ended = "no quit line (crash or kill)"
    return {"session": session_id(first), "file": path.name, "start": start, "end": end,
            "length_s": (end - start) if (start is not None and end is not None) else None,
            "size": size, "ended": ended, "current": path.name == "Game.log"}


def render_list(rows, tz=None):
    out = ["%-22s %-12s %-9s %-30s %s" % ("Local start", "Length", "Size", "Ended", "Session")]
    for r in rows:
        start = ("%s %s" % (local(r["start"], tz).strftime("%m/%d/%Y"), clock(r["start"], tz, seconds=False))
                 if r["start"] is not None else "?")
        size = r["size"]
        size_s = "%.1f MB" % (size / 1e6) if size >= 1e6 else "%d KB" % (size // 1000)
        out.append("%-22s %-12s %-9s %-30s %s%s" % (
            start, duration(r["length_s"]), size_s, r["ended"], r["session"],
            "  (Game.log)" if r["current"] else ""))
    return "\n".join(out) + "\n"


def rows_json(rows, tz=None):
    return [dict(r, start=iso_local(r["start"], tz) if r["start"] else None,
                 end=iso_local(r["end"], tz) if r["end"] else None) for r in rows]


def find_log(arg, live):
    """A path, or a piece of a backup's name such as '26 Nov 26 (15 11 12)'."""
    p = Path(arg)
    if p.exists():
        return p
    if live is not None:
        d = config.backups_dir(live)
        if d.is_dir():
            hits = sorted(n for n in os.listdir(d) if arg in n and n.startswith("Game "))
            if len(hits) == 1:
                return d / hits[0]
            if len(hits) > 1:
                raise SystemExit("More than one log matches %r:\n  %s" % (arg, "\n  ".join(hits)))
    raise SystemExit("No log found for %r" % arg)


def dumps(obj):
    return json.dumps(obj, indent=2, ensure_ascii=False)
