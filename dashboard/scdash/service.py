"""The service: the main loop and the life cycle (PLAN §6, §7, §8).

One `Service` follows one log for one data folder and serves one port. Everything it is pointed
at is an argument (the data folder, the log, the port, the name of the game's process, the
clock), so the tests and `replay` run beside the live instance without touching it. The lock is
a named mutex whose name follows the data folder.

Life cycle (`run()`):

1. A background start (`run --background`) that finds the `stop` marker in the data folder exits
   at once: a deliberate stop stays stopped (PLAN §6).
2. Take the lock. Held by another process: refuse (exit 1). The OS drops a lock when its holder
   dies, so a crashed instance never blocks a start, and a stale `run.json` decides nothing.
3. Something already answering on the port (a program bound to all interfaces would not stop our
   bind to 127.0.0.1) or a failed bind: the port is taken. Its health answer says whether it is
   another dashboard or a foreign program; either way, exit 2.
4. Below-normal priority, a new token, the server started, `run.json` written. An instance no
   command can find (run.json still unwritten after RUN_JSON_GIVE_UP_SECONDS of tries) stops
   with exit 3 rather than stay up where nothing can talk to it or stop it.
5. With no game running, read the last log once (the page shows the last session) and write its
   summary if it has none yet. With a game running, read the current log from the top: a restart
   arrives at the same state as watching live (PLAN §7). A read or a write that fails here does
   not end the service: it is logged and tried again on a later turn, as in the loop (a
   scheduled relaunch every five minutes would otherwise make it a crash loop).
6. The loop. Game running: poll the log once a second. Always: look for the game's process every
   10 seconds. When it appears, follow the log; when it goes, read the rest, end the session
   (a crash leaves no quit line, so only the process going away says it is over) and write its
   summary. A summary is written once: its file name comes from the session, and an existing
   file is never rewritten.
7. Shutdown (the endpoint, Ctrl+C): last state saved, `run.json` removed, lock released.

Stage 3 (the board, PLAN §11, dashboard/STATE.md): each turn looks at `data/plan.json` (one stat,
at most once a second), and `board.build()` is called only when one of its inputs changed (the
state, the plan, the user block, whether the game runs) or the service's clock has reached the
last payload's `next_change_ms`; the payload goes out as `board` beside the stage 2 parts. While
the reader catches up on a large log, nothing half-read goes out (an old alert must not flash up
again after a restart), at most one message every CATCH_UP_PUBLISH_SECONDS on a very long one.
The page changes the user block (a view picked by hand, quick timers) through four CHANGE routes;
the main loop and those requests share one lock, so the state is never read half-applied.

Every error inside the loop is caught, logged (repeats counted, not repeated) and passed over.
Two things end it instead, each with an error in the log: run.json that cannot be written (exit
3, above), and the web server's front-end thread gone (exit 4): with no server nothing can reach
the instance, and the next start, or the scheduled relaunch, brings up one that works.

The clock is read here and only here, and handed to what needs it (`clock_facts`, `board.build`);
the state never reads it (PLAN §7). Every file is written to a temporary file and renamed into
place, and never through a junction or a symbolic link below the data folder (`link_on_the_way`).
"""
import hashlib
import http.client
import json
import logging
import logging.handlers
import math
import os
import re
import secrets
import signal
import socket
import stat
import subprocess
import sys
import threading
import time
import traceback
import unicodedata
from collections import OrderedDict
from pathlib import Path

from . import __version__, board as boardlib, config, refdata, winutil
from .names import LocationNames
from .pipeline import LogReader
from .plan import MAX_QUICK, PlanStore, VIEWS as VIEW_NAMES
from .records import parse_ts
from .server import (CHANGE, PROGRAM, READ, SURROGATES, TOKEN_HEADER, Hub, Server, error_key, json_depth_over,
                     json_text, remember, scrub)
from .state import clock_facts
from .words import clean_all, clean_text, iso

EXIT_OK, EXIT_RUNNING, EXIT_PORT, EXIT_SETUP, EXIT_SERVER = 0, 1, 2, 3, 4

SCRIPT = config.DASHBOARD_DIR / "scdash.py"
TS_RE = re.compile(rb"^<(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3})Z>")


# ---------------------------------------------------------------------------- files

class Paths:
    """The files of one data folder."""

    def __init__(self, data_dir):
        self.data = Path(data_dir).resolve()
        self.run = self.data / "run.json"
        self.stopped = self.data / "stopped.json"
        self.state = self.data / "state.json"
        self.plan = self.data / config.PLAN_NAME             # written by Claude, only read here
        self.unmapped = self.data / "unmapped.json"
        self.sessions = self.data / "sessions"
        self.log = self.data / "service.log"
        self.config = self.data / config.CONFIG_NAME
        self.lockfile = self.data / "service.lock"            # the lock off Windows only

    def lock(self):
        return winutil.InstanceLock(lock_name(self.data), str(self.lockfile))


def lock_name(data_dir):
    """The mutex name for a data folder: one instance per folder."""
    key = os.path.normcase(str(Path(data_dir).resolve())).encode("utf-8")
    return "scdash-" + hashlib.sha256(key).hexdigest()[:24]


TEMP_PREFIX = ".scdash-tmp-"                      # atomic_write's temporary files, and only theirs
_UNREADABLE = object()                            # Service._read_data_file: the file cannot be read now
_DAMAGED = object()                               # ... it was read and is not a JSON object


def atomic_write(path, data):
    """Write to a temporary file beside `path`, then rename it into place: a crash never leaves
    half a file. A rename can meet a reader holding the old file for a moment on Windows: retried."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, str):
        data = data.encode("utf-8")
    tmp = path.with_name("%s%d-%s-%s.tmp" % (TEMP_PREFIX, os.getpid(), secrets.token_hex(4), path.name))
    try:
        with open(tmp, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        for attempt in range(40):
            try:
                os.replace(tmp, path)
                return
            except PermissionError:
                if attempt == 39 or os.path.isdir(path):     # a folder in its place never goes away by waiting
                    raise
                time.sleep(0.05)
    finally:
        try:
            if tmp.exists():
                tmp.unlink()
        except OSError:
            pass


def write_json(path, obj, indent=1):
    """`obj` as JSON, atomically. Never fails on what is in it: `json_text` turns a lone surrogate
    (from a plan, a state file or a request) into U+FFFD and a NaN into null, so state.json, a
    summary or unmapped.json cannot become unsaveable for good (stage 3 review)."""
    atomic_write(path, json_text(obj, indent=indent) + "\n")


def read_json(path):
    """The file's JSON, or None when it is missing or unreadable."""
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def link_on_the_way(root, path, include_self=False):
    """The first junction or symbolic link (any reparse point) below `root` on the way to `path`,
    or None. `root` itself is not looked at (Paths resolves it); `path` itself only with
    `include_self`, for a file opened in place (atomic_write replaces its target, which never
    writes through it). Each part is looked at with lstat, which never follows it, so nothing but
    that name is opened. A path outside `root` is returned as it is: refused."""
    path = Path(path)
    try:
        parts = path.relative_to(root).parts
    except ValueError:
        return path
    if not include_self:
        parts = parts[:-1]
    p = Path(root)
    for part in parts:
        p = p / part
        try:
            st = os.lstat(p)
        except FileNotFoundError:
            return None                           # nothing below exists yet: mkdir makes plain folders
        except OSError:
            return p                              # cannot tell: refused
        if stat.S_ISLNK(st.st_mode) or getattr(st, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
            return p
    return None


# Only the names atomic_write makes: an ASCII pid (Windows' are at most 10 digits), 8 hex digits,
# and the plain ASCII name of one of our files.
TEMP_RE = re.compile(r"\.scdash-tmp-(?P<pid>[1-9][0-9]{0,9})-[0-9a-f]{8}-(?P<name>[0-9A-Za-z._-]{1,100})\.tmp")


def sweep_temp_files(folder):
    """Remove the temporary files `atomic_write` leaves when a process dies between writing and
    renaming: only ours (`.scdash-tmp-<pid>-<hex>-<name>.tmp`, a prefix nothing else uses), and
    only when that process is gone.
    Returns how many were removed."""
    try:
        names = os.listdir(folder)
    except OSError:
        return 0
    removed, plist = 0, None
    for name in names:
        m = TEMP_RE.fullmatch(name)
        if not m:
            continue
        pid = int(m.group("pid"))
        if pid == os.getpid():
            continue
        if plist is None:
            plist = winutil.process_list()
        if winutil.process_name(pid, plist) is not None:
            continue                                  # a live writer (a `stop` writing its marker)
        try:
            os.remove(os.path.join(str(folder), name))
            removed += 1
        except OSError:
            pass
    return removed


def summary_name(sm):
    """A session summary's file name: its start (UTC) and build, so names sort by time."""
    build = re.sub(r"[^0-9A-Za-z]", "", str(sm.get("build") or "")) or "x"
    start = sm.get("start")
    if start and re.match(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d", start):
        stem = start[:19].replace(":", "-") + "Z"
    else:
        stem = "session-" + hashlib.sha1(str(sm.get("session")).encode("utf-8")).hexdigest()[:12]
    return "%s_%s.json" % (stem, build)


def valid_run(obj):
    return (isinstance(obj, dict) and isinstance(obj.get("pid"), int) and isinstance(obj.get("port"), int)
            and isinstance(obj.get("started"), str) and isinstance(obj.get("token"), str))


# ---------------------------------------------------------------------------- clocks and probes

class LiveClock:
    """The system clock. The page computes "now" from its own clock: same PC, same time."""

    def now(self):
        return time.time()

    def anchor(self):
        return {"rate": 1.0, "real": 0, "virtual": 0}


class ReplayClock:
    """A clock that runs `speed` times faster from the replayed log's first time, and stops at
    its last time once the feed is done. The page gets its anchor and computes the same time."""

    def __init__(self, start_t, speed):
        self.start_t = start_t
        self.speed = float(speed)
        self._m0 = time.monotonic()
        self._real0 = time.time()
        self._frozen = None

    def now(self):
        if self._frozen is not None:
            return self._frozen
        return self.start_t + (time.monotonic() - self._m0) * self.speed

    def freeze(self, t=None):
        self._frozen = self.now() if t is None else t

    def anchor(self):
        if self._frozen is not None:
            return {"rate": 0.0, "real": 0, "virtual": round(self._frozen * 1000)}
        return {"rate": self.speed, "real": round(self._real0 * 1000), "virtual": round(self.start_t * 1000)}


class ProcessProbe:
    """Is the game running? By its name in the system's process list; no process is opened."""

    def __init__(self, name):
        self.name = name

    def running(self):
        return winutil.process_running(self.name)


def line_time(line):
    m = TS_RE.match(line)
    if not m:
        return None
    try:
        return parse_ts(m.group(1).decode("ascii"))
    except ValueError:
        return None


def log_span(path):
    """(first time, last time) of a log, from its head and its last 256 KB."""
    with winutil.open_shared(path) as f:
        size = f.seek(0, 2)
        f.seek(0)
        head = f.read(4096)
        f.seek(max(0, size - 256 * 1024))
        tail = f.read()
    first = line_time(head.split(b"\n", 1)[0])
    last = None
    for line in reversed(tail.split(b"\n")):
        last = line_time(line)
        if last is not None:
            break
    return first, last


def copy_log(src, dest):
    """Copy a log as it is now into `dest`, reading it in 1 MB pieces with full sharing and
    closing it at once: a replay of the live Game.log must not hold it open (PLAN §8)."""
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with winutil.open_shared(src) as f, open(dest, "wb") as out:
        while True:
            piece = f.read(1 << 20)
            if not piece:
                break
            out.write(piece)
    return dest


class ReplayFeeder(threading.Thread):
    """Writes a past log into a fresh file of the replay's own, line by line, as the replay clock
    reaches each line's time. The service follows that file the way it follows Game.log, so a
    replay exercises the same reading code. Acts as the replay's "game process": running until
    the whole log has been written. `source` is a copy in the replay's own folder (`copy_log`),
    which the feeder may hold open for as long as the replay runs."""

    def __init__(self, source, dest, clock, logger=None):
        super().__init__(name="scdash-replay", daemon=True)
        self.source = Path(source)
        self.dest = Path(dest)
        self.clock = clock
        self.logger = logger
        self.done = False
        self.bytes_written = 0
        self.lines_written = 0
        self._stop = threading.Event()

    def running(self):
        return not self.done

    def stop(self):
        self._stop.set()

    def run(self):
        last_t = None
        try:
            last_t = self._feed()
        except Exception:                              # noqa: BLE001
            if self.logger:
                self.logger.exception("replay feed failed")
        finally:
            self.clock.freeze(last_t)
            self.done = True

    def _feed(self):
        self.dest.parent.mkdir(parents=True, exist_ok=True)
        last_t = None
        with open(self.source, "rb") as src, open(self.dest, "wb") as out:
            pending = []
            size = 0
            carry = b""

            def flush():
                nonlocal size
                if pending:
                    data = b"".join(pending)
                    out.write(data)
                    out.flush()
                    self.bytes_written += len(data)
                    self.lines_written += len(pending)
                    pending.clear()
                    size = 0

            while not self._stop.is_set():
                chunk = src.read(1 << 20)
                if not chunk:
                    break
                lines = (carry + chunk).split(b"\n")
                carry = lines.pop()
                for line in lines:
                    t = line_time(line)
                    if t is not None:
                        if t > self.clock.now():
                            flush()
                            while not self._stop.is_set():
                                ahead = t - self.clock.now()
                                if ahead <= 0:
                                    break
                                self._stop.wait(min(0.2, ahead / self.clock.speed))
                            if self._stop.is_set():
                                return last_t
                        last_t = t
                    pending.append(line + b"\n")
                    size += len(line) + 1
                    if size > (256 << 10):
                        flush()
            if carry and not self._stop.is_set():
                pending.append(carry)
            flush()
        return last_t


# ---------------------------------------------------------------------------- the user block

# What the page may change (PLAN §7: the user block of state.json is the only record of it). Each
# change is an operation, so that changes made while state.json could not be read yet are applied
# again on top of what the file holds once it can be (`Service._load_user`): neither side is lost.
#   ("view", record or None)   a view picked by hand (board.pick), or none (Live, or dropped)
#   ("add", timer)             a quick timer, as board.add_quick_timer made it
#   ("remove", "quick:<id>")   a quick timer removed

def apply_user_op(user, op):
    """The user block with one operation applied (a new dict; `user` is not changed)."""
    out = dict(user) if isinstance(user, dict) else {}
    kind, value = op
    if kind == "view":
        if value is None:
            out.pop("view", None)
        else:
            out["view"] = value
    elif kind == "add":
        timers = [x for x in out.get("timers") or [] if isinstance(x, dict)] \
            if isinstance(out.get("timers"), list) else []
        if not any(x.get("id") == value.get("id") for x in timers):
            timers.append(value)
        out["timers"] = timers[-MAX_QUICK:]
    elif kind == "remove":
        out = boardlib.remove_quick_timer(out, value)
    return out


def user_block_from_file(raw):
    """The user block as the service keeps it, from what state.json held (any JSON value), and a
    list of what was left out (for one log line). Never raises on what the file held.

    - `timers`: the quick timers the board can show, as `plan.clean_user` reads them (at most
      MAX_QUICK, each with a label, a ready time and a unique id), stored under the very ids the
      page is shown, so that removing by the shown id always finds the timer (the wiring review,
      finding B: a doubled or odd id was renamed on the board and could not be removed). A timer
      the board could never show is left out.
    - `view`: the hand pick as `clean_user` takes it, or none.
    - Any other key is kept for a later stage when its name is a text of at most 64 characters,
      its value nests at most MAX_USER_EXTRA_DEPTH deep, and all such keys together are at most
      MAX_USER_EXTRA_KEYS keys and MAX_USER_EXTRA_BYTES of JSON (findings A and D: a value nested
      2,000 deep wiped the block, and a 20 MB key was rewritten at every save)."""
    from .plan import clean_user
    raw = raw if isinstance(raw, dict) else {}
    left_out = []
    shown = clean_user({"timers": raw.get("timers"), "view": raw.get("view")})
    out = {}
    if shown["timers"]:
        out["timers"] = [{"id": t["id"], "label": t["label"], "added_at": iso(t["added_t"]) if t["added_t"] else None,
                          "ready_at": iso(t["ready_t"])} for t in shown["timers"]]
    given = [x for x in raw.get("timers") or [] if isinstance(x, dict)] if isinstance(raw.get("timers"), list) else []
    if len(given) > len(shown["timers"]):
        left_out.append("%d quick timer(s) the page could not show" % (len(given) - len(shown["timers"])))
    if shown["view"] is not None:
        out["view"] = shown["view"]
    elif raw.get("view") is not None:
        left_out.append("a hand pick the page could not use")
    size, extra = 0, 0
    for k, v in raw.items():
        if k in ("timers", "view"):
            continue
        why = None
        if not isinstance(k, str) or len(k) > 64:
            why = "a key name over 64 characters"
        elif extra >= config.MAX_USER_EXTRA_KEYS:
            why = "more than %d keys" % config.MAX_USER_EXTRA_KEYS
        elif json_depth_over(v, config.MAX_USER_EXTRA_DEPTH):
            why = "nested deeper than %d" % config.MAX_USER_EXTRA_DEPTH
        else:
            n = len(json_text(v))
            if size + n > config.MAX_USER_EXTRA_BYTES:
                why = "over %d KB together" % (config.MAX_USER_EXTRA_BYTES // 1024)
            else:
                size += n
        if why:
            left_out.append("%r (%s)" % (str(k)[:40], why))
            continue
        extra += 1
        out[k] = v
    return scrub(out), left_out


# What a request to a changing route may carry (PLAN §8: every input bounded).
MAX_LABEL_IN = 60                                    # a quick timer's label, as plan.quick_timer keeps it
MINUTES_RANGE = (0.5, 24 * 60.0)                     # a quick timer's length, as plan.quick_timer takes it
# A quick timer's id as the payload gives it: "quick:" and an id of plan.ID_RE's characters, with
# room for the "-2" plan.clean_user adds to a doubled one.
QUICK_ID_RE = re.compile(r"quick:[A-Za-z0-9_.:-]{1,48}")


def shown_path(path):
    """A path as `status` shows it: the user's profile folder (which holds the Windows user name)
    written as %USERPROFILE%. Python itself, a replay's temporary folder and anything under
    AppData sit there."""
    text = str(path)
    home = os.environ.get("USERPROFILE") or os.path.expanduser("~")
    if home and home != "~":
        home = os.path.normpath(home)
        if os.path.normcase(text).startswith(os.path.normcase(home + os.sep)) or \
                os.path.normcase(text) == os.path.normcase(home):
            return "%USERPROFILE%" + text[len(home):]
    return text


def visible(ch):
    """Does `ch` show as something on its own: a letter, a digit, punctuation or a symbol? Not a
    space, a control or format character (zero-width ones, a soft hyphen, tag characters), a
    private-use or unassigned code point, or a combining mark (it only changes the character
    before it)."""
    return unicodedata.category(ch)[0] in "LNPS"


class BadRequest(Exception):
    """A changing request whose body does not fit: 400 with the reason."""


def body_fields(body, required, optional=()):
    """The body's fields, exactly: every required one present, nothing unknown."""
    if not isinstance(body, dict):
        raise BadRequest("the body must be a JSON object")
    unknown = sorted(set(body) - set(required) - set(optional))
    if unknown:
        raise BadRequest("unexpected field %r" % unknown[0][:40])
    missing = [k for k in required if k not in body]
    if missing:
        raise BadRequest("missing field %r" % missing[0])
    return body


def contract_key(c):
    """A short, stable key for an unmapped contract in data/unmapped.json."""
    raw = "\x1f".join(str(c.get(k) or "") for k in ("contract", "generator", "title"))
    return hashlib.sha1(raw.encode("utf-8", "replace")).hexdigest()[:16]


def _text_or_none(x, n=300):
    return clean_text(x)[:n] if isinstance(x, str) else None


def _newest(entries, cap):
    """At most `cap` entries, the most recently first seen kept."""
    if len(entries) <= cap:
        return entries
    return dict(sorted(entries.items(), key=lambda kv: str(kv[1].get("first_seen") or ""))[-cap:])


def fallback_board(plans, err):
    """What the page gets as `board` when board.build itself fails (it is documented never to):
    the shape board.build gives a payload that failed, the fault named in `problems`."""
    return {"schema": boardlib.SCHEMA,
            "view": {"name": "now", "rule": "error", "why": "The payload could not be built", "context": "error",
                     "auto": "now", "mode": "flight", "picked": False, "pick_dropped": False},
            "model": {"view": "now", "unavailable": True}, "strip": None, "alerts": [], "timers": [],
            "plan": {"loaded": plans.plan is not None, "notice": plans.notice, "updated": None, "updated_text": None,
                     "run": None, "run_kind": None},
            "unmapped_contracts": [], "next_change_ms": None,
            "problems": ["service: %s" % err.__class__.__name__]}


# ---------------------------------------------------------------------------- the service

class _Reader(LogReader):
    """The pipeline's reader, telling the service when a session ends in the same file (the log
    emptied or its first line changed) before the reader starts again from offset 0."""

    def __init__(self, *args, on_reset=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._on_reset = on_reset

    def reset(self):
        if self._on_reset is not None:
            try:
                self._on_reset(self)
            except Exception:                          # noqa: BLE001 - logging must not stop the reader
                pass
        super().reset()


class Service:
    def __init__(self, data_dir, log_path, settings=None, mode="live", clock=None, probe=None,
                 names=None, feeder=None, background=False, notes=(), replay_info=None,
                 exit_when_done=False, console=False, plan_path=None):
        self.paths = Paths(data_dir)
        self.settings = settings or config.load_settings(self.paths.data)[0]
        self.notes = list(notes)
        self.mode = mode
        self.log_path = Path(log_path) if log_path else None
        self.port = int(self.settings["port"])
        self.clock = clock or LiveClock()
        self.probe = probe or ProcessProbe(self.settings["game_process"])
        self.feeder = feeder
        self.background = background
        self.replay_info = replay_info
        self.exit_when_done = exit_when_done
        self.names = names if names is not None else LocationNames.load(config.LOCATIONS_FILE)
        self.log = self._make_logger(console)
        self.reader = _Reader(self.log_path or (self.paths.data / "no-log-configured"), self.names,
                              on_reset=self._session_reset)
        s = self.settings
        self.hub = Hub("state", min_interval=s["push_min_seconds"], keepalive=s["keepalive_seconds"],
                       retry_ms=s["retry_ms"], max_clients=s["max_pages"])
        self.server = None
        self.token = None
        self.started = time.time()
        self.started_iso = iso(self.started)
        self.refusal = None              # why run() did not start: ("lock",) / ("port", kind, why)
        self.game_running = None
        self.game_since = None
        self.game_last_seen = None
        self.log_status = None
        self.publishes = 0
        self.errors = 0
        self.summaries_written = 0
        self.user_data = {}              # stage 3: what the user entered on the page (quick timers, a view)
        # Stage 3: the plan (`replay --plan` points it at the replay's own copy), the board.
        self.plans = PlanStore(Path(plan_path) if plan_path else self.paths.plan)
        self.board = None                # the last payload board.build gave (what the page got)
        self.board_builds = 0
        self.mono = time.monotonic        # the interval clock (tests replace it)
        self._stop = threading.Event()
        self._wake = threading.Event()    # set to end the loop's wait early (a stop, a change from the page)
        self._lock = threading.RLock()    # the main loop's turn, or one change from the page
        self._dirty = True
        self._last_text = None
        self._last_state = None
        self._unsaved = False
        self._last_save = float("-inf")
        self._flags_last = None
        self._next_probe = 0.0
        self._backup_checks = []
        self._old_session = None
        self._error_kinds = OrderedDict()  # (where, error_key) -> when last logged in full
        self._error_counts = {}           # the same key -> repeats since then
        self._unmapped = {}
        self._unmapped_contracts = {}
        self._unmapped_loaded = False     # data/unmapped.json read (once, when something new is first seen)
        self._finalized = None           # the session id whose end was handled
        self._user_loaded = False        # state.json's user block read (or there is none)
        self._user_warned = False
        self._user_ops = []              # changes made on the page before the user block could be read
        self._user_version = 0           # bumped by every change of the user block
        self._user_unsaved = False       # the user block changed: saved on the turn, not after 10 s
        self._next_user_try = 0.0
        self._plan_version = 0           # bumped when plan.json's plan or notice changed
        self._next_plan_check = 0.0
        self._resets = 0                 # sessions ended in the same file (a new State)
        self._board_sig = None           # the inputs the last board was built from
        self._board_next_ms = None       # its next_change_ms
        self._problems_logged = set()    # sets of board problems already logged, once each
        self._busy_since = None          # catching up on a large log since (mono), or None
        self._save_now = False           # a change from the page: save state.json on this turn
        self._save_failing = False       # the last save of state.json raised: retried at the loop's pace only
        self._save_lock = threading.Lock()  # one writer of state.json at a time, never under self._lock
        self._snap_seq = 0               # snapshots of state.json taken (under self._lock)
        self._snapshot = None            # the newest: (number, object)
        self._written_seq = 0            # the newest on disk
        self._pending_save = None        # a snapshot the lock's holder is to write once it lets go
        self._first_read_done = False    # the log read once: until then a change is refused (503)
        self._closing = False            # a stop was asked for: changes are refused (503)
        self._error_lock = threading.Lock()  # _error is called from the loop, the changes and the saves
        self._unmapped_dirty = False     # entries in memory not yet in unmapped.json
        self._unmapped_warned = False
        self._next_unmapped_try = 0.0
        self._last_read_due = False      # no game at start: the last log is still to be read once
        self._pending = []               # session summaries not yet written: (summary, why)
        self._next_summary_try = 0.0
        self._run_due = False            # run.json still to be written
        self._next_run_try = 0.0
        self._run_give_up = None         # when an instance nothing can find stops trying
        self._links_logged = set()       # junctions and links already reported
        self._exit_code = EXIT_OK        # what run() returns once the loop ends

    # ------------------------------------------------------------------ logging

    def _make_logger(self, console):
        lg = logging.getLogger("scdash.%s.%x" % (self.mode, id(self)))
        lg.setLevel(logging.DEBUG)
        lg.propagate = False
        try:
            self.paths.data.mkdir(parents=True, exist_ok=True)
            if link_on_the_way(self.paths.data, self.paths.log, include_self=True) is not None:
                # Appending opens the file in place, so a link there would be written through.
                self.notes.append("%s is a junction or a link: nothing is logged to it" % self.paths.log.name)
                raise OSError("service.log is a link")
            # backslashreplace: a line with a code point UTF-8 cannot encode (a lone surrogate)
            # is written with it escaped, instead of being lost to a logging error.
            fh = logging.handlers.RotatingFileHandler(
                str(self.paths.log), maxBytes=int(self.settings["log_max_bytes"]),
                backupCount=int(self.settings["log_backups"]), encoding="utf-8", errors="backslashreplace")
            fh.setLevel(logging.INFO)
            fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
            lg.addHandler(fh)
        except OSError:
            pass
        if console and sys.stderr is not None:
            sh = logging.StreamHandler(sys.stderr)
            sh.setLevel(logging.INFO)
            sh.setFormatter(logging.Formatter("%(asctime)s %(message)s", "%I:%M:%S %p"))
            lg.addHandler(sh)
        return lg

    def close(self):
        for h in list(self.log.handlers):
            try:
                h.close()
            finally:
                self.log.removeHandler(h)

    def _error(self, where):
        """An error caught and passed over. Logged in full the first time its kind is seen (where
        it was caught, the exception's type, and the file and line it was raised at: `error_key`),
        and again at most every ERROR_FULL_AGAIN_SECONDS; repeats in between are counted, with a
        line at 10, 100, 1,000 and every 10,000. A save that failed every 10 s used to log a full
        traceback each time, because each one named a new temporary file (stage 2 review), and
        two errors that took turns were each logged in full every time. Thread-safe: a save is
        written outside the main lock."""
        key = (where,) + error_key()
        with self._error_lock:
            self.errors += 1
            if remember(self._error_kinds, key, time.monotonic(), config.ERROR_FULL_AGAIN_SECONDS,
                        config.MAX_ERROR_KINDS):
                self._error_counts = {k: v for k, v in self._error_counts.items() if k in self._error_kinds}
                self._error_counts[key] = 0
                self.log.error("error in %s (carrying on):\n%s", where, traceback.format_exc().rstrip())
                return
            n = self._error_counts.get(key, 0) + 1
            self._error_counts[key] = n
            if n in (10, 100, 1000) or n % 10000 == 0:
                self.log.error("the same error in %s, %d times now", where, n + 1)

    # ------------------------------------------------------------------ life cycle

    def run(self):
        """The whole life of the service. Returns the process exit code."""
        try:
            return self._run()
        except Exception:                              # noqa: BLE001
            self.log.exception("the service failed")
            return EXIT_SETUP
        finally:
            self.close()

    def _run(self):
        lg = self.log
        lg.info("start: scdash %s, pid %d, mode %s, data %s, log %s, port %d", __version__, os.getpid(),
                self.mode, self.paths.data, self.log_path, self.port)
        for note in self.notes:
            lg.warning("config: %s", note)
        if self.background and self.paths.stopped.exists():
            lg.info("not starting: stopped on purpose (the marker %s; `start` removes it)", self.paths.stopped.name)
            self.refusal = ("stopped",)
            return EXIT_OK
        lock = self.paths.lock()
        if not lock.acquire():
            lg.warning("not starting: another instance holds the lock for this data folder")
            self.refusal = ("lock",)
            return EXIT_RUNNING
        try:
            if winutil.below_normal_priority():
                lg.info("running at below-normal priority")
            swept = sweep_temp_files(self.paths.data)
            if not self._linked(self.paths.sessions, include_self=True):
                swept += sweep_temp_files(self.paths.sessions)
            if swept:
                lg.info("removed %d temporary file(s) a stopped instance left half-written", swept)
            if port_answering(self.port):
                kind, why = probe_health(self.port)
                return self._port_taken(kind, why, None)
            self.token = secrets.token_urlsafe(32)
            self.started = time.time()                # before the server answers health checks
            self.started_iso = iso(self.started)
            self.server = Server(self.port, self.token, page_vars=self._page_vars(), logger=lg)
            self._register(self.server)
            try:
                self.server.start()
            except OSError as e:
                self.server = None
                kind, why = probe_health(self.port)
                return self._port_taken(kind, why, e)
            self.port = self.server.port
            self._write_run()
            lg.info("listening on http://127.0.0.1:%d/", self.port)
            self._install_signals()
            self._loop()
            return self._exit_code
        finally:
            self._closing = True                       # changes get 503 from here on
            if self.feeder is not None:
                self.feeder.stop()
            if self.server is not None:
                self.server.stop()                     # new connections; requests in flight finish
            try:
                self._last_save_at_stop()
            except Exception:                          # noqa: BLE001
                self._error("the last save")
            self._remove_run()
            lock.release()
            lg.info("stopped")

    def _port_taken(self, kind, why, err):
        if kind == "scdash":
            text = "another dashboard instance (pid %s, a different data folder) is using port %d" % (
                why.get("pid"), self.port)
        else:
            text = "port %d is taken by another program, not this dashboard (%s)" % (
                self.port, why or (err.__class__.__name__ if err else "it answers"))
        self.log.error("not starting: %s. Set \"port\" in %s to another number.", text, self.paths.config.name)
        self.refusal = ("port", kind, text)
        return EXIT_PORT

    def _write_run(self):
        """run.json: how the commands find this instance and its token. Until it is written,
        `status` and `stop` see a held lock and nothing they can talk to, and nothing can stop the
        instance. So a write that fails is tried again every RUN_JSON_RETRY_SECONDS (a file held
        for a moment), and after RUN_JSON_GIVE_UP_SECONDS the instance stops with exit 3; the next
        start, or the scheduled relaunch, tries again."""
        now = self.mono()
        if self._run_give_up is None:
            self._run_give_up = now + config.RUN_JSON_GIVE_UP_SECONDS
        self._run_due = True
        self._next_run_try = now + config.RUN_JSON_RETRY_SECONDS
        try:
            written = self._write(self.paths.run, {
                "program": PROGRAM, "version": __version__, "pid": os.getpid(), "port": self.port,
                "started": self.started_iso, "token": self.token, "mode": self.mode,
                "data_dir": str(self.paths.data), "log": str(self.log_path) if self.log_path else None,
                "python": sys.executable, "created": winutil.process_created()})
        except Exception:                              # noqa: BLE001 - tried again from tick()
            self._error("writing run.json")
            written = False
        if written:
            self._run_due = False
            return
        if now >= self._run_give_up:
            self.log.error("stopping: %s could not be written in %.0f s, so no command could find this instance, "
                           "read its token or stop it (exit %d; the next start tries again)",
                           self.paths.run.name, config.RUN_JSON_GIVE_UP_SECONDS, EXIT_SETUP)
            self._exit_code = EXIT_SETUP
            self._halt()

    def _write(self, path, obj, indent=1):
        """write_json for a file in the data folder, never through a junction or a link on the way
        to it (PLAN §8): such a write is skipped (reported once). True when written; a failed
        write raises."""
        if self._linked(path):
            return False
        write_json(path, obj, indent)
        return True

    def _linked(self, path, include_self=False):
        """Is there a junction or a link below the data folder on the way to `path`? Reported once."""
        bad = link_on_the_way(self.paths.data, path, include_self)
        if bad is None:
            return False
        if str(bad) not in self._links_logged:
            self._links_logged.add(str(bad))
            self.log.error("%s is a junction or a link: nothing is written or swept through it (PLAN §8)", bad)
        return True

    def _remove_run(self):
        run = read_json(self.paths.run)
        if valid_run(run) and run["pid"] == os.getpid() and run["started"] == self.started_iso:
            try:
                self.paths.run.unlink()
            except OSError:
                pass

    def request_stop(self):
        self._halt()

    def _halt(self):
        """End the loop: the stop flag, and the loop's wait cut short. From here on a change from
        the page gets a 503 (it could be answered and then lost at the stop: finding F)."""
        self._closing = True
        self._stop.set()
        self._wake.set()

    def _install_signals(self):
        if threading.current_thread() is not threading.main_thread():
            return
        for name in ("SIGTERM", "SIGBREAK"):
            sig = getattr(signal, name, None)
            if sig is not None:
                try:
                    signal.signal(sig, lambda *_: self._halt())
                except (OSError, ValueError):
                    pass

    def _page_vars(self):
        """What the page is served with: its layout, its mode, and which instance served it (pid
        and start), so it can tell from the first stream message on whether the service it talks
        to was restarted and its token is dead."""
        return {"terminal": "on" if self.settings["terminal"]["enabled"] else "off", "mode": self.mode,
                "instance": "%d/%s" % (os.getpid(), self.started_iso)}

    def _register(self, srv):
        """Every endpoint, behind its guard. Stage 3's four changes to the user block are CHANGE
        routes (dashboard/STATE.md, "The message and the endpoints"); stage 4b adds the terminal
        (CHANGE for keystrokes, a Hub of its own behind PRIVATE for its output)."""
        srv.route("GET", "/api/health", self._api_health, READ)
        srv.route("GET", "/api/status", self._api_status, READ)
        srv.route("GET", "/api/state", self._api_state, READ)
        srv.stream("/api/stream", self.hub, READ)
        srv.route("POST", "/api/shutdown", self._api_shutdown, CHANGE)
        srv.route("POST", "/api/view", self._api_view, CHANGE)
        srv.route("POST", "/api/view/live", self._api_live, CHANGE)
        srv.route("POST", "/api/timers/add", self._api_timer_add, CHANGE)
        srv.route("POST", "/api/timers/remove", self._api_timer_remove, CHANGE)

    # ------------------------------------------------------------------ changes from the page

    def _api_view(self, req):
        """Pick a view by hand: {"view": "<name>"}, one of plan.VIEWS ("reference" included)."""
        try:
            name = body_fields(req.json, ("view",))["view"]
            if not isinstance(name, str) or name not in VIEW_NAMES:
                raise BadRequest("view must be one of: %s" % ", ".join(VIEW_NAMES))
        except BadRequest as e:
            return 400, {"error": str(e)}

        def do(now):
            if self._busy_since is not None:
                # A pick is kept under the context it was made in; made on a half-read state, it
                # would be dropped the moment the rest is read.
                return 503, {"error": "still reading the log: pick again in a moment"}
            rec = boardlib.pick(self.reader.state, self.plans, name, bool(self.game_running), now)
            if rec is None:
                return 400, {"error": "not a view that can be picked"}
            self._change_user(("view", rec))
            return 200, {"ok": True}
        return self._locked_change(do)

    def _api_live(self, req):
        """Back to Live: the hand pick (the reference cards included) is forgotten. {}."""
        try:
            body_fields(req.json, ())
        except BadRequest as e:
            return 400, {"error": str(e)}

        def do(now):
            had = self.user_data.get("view") is not None
            if had or not self._user_loaded:
                self._change_user(("view", None))
            return 200, {"ok": True, "had_pick": had}
        return self._locked_change(do)

    def _api_timer_add(self, req):
        """A quick timer: {"label": "<1 to 60 characters>", "minutes": <0.5 to 1440>}."""
        try:
            body = body_fields(req.json, ("label", "minutes"))
            label, minutes = body["label"], body["minutes"]
            if not isinstance(label, str) or not label.strip() or len(label) > MAX_LABEL_IN:
                raise BadRequest("label must be a text of 1 to %d characters" % MAX_LABEL_IN)
            # A lone surrogate ("\ud800" in the body's JSON) is taken out like a control
            # character: it is no character, and kept it would make the saved block and the
            # page's message unencodable (stage 3 review).
            label = SURROGATES.sub("", label)
            if not label.strip():
                raise BadRequest("label must be a text of 1 to %d characters" % MAX_LABEL_IN)
            if not any(visible(ch) for ch in label):
                # Only invisible characters (zero-width ones, a soft hyphen, tag characters, a
                # combining mark alone) would show as an empty timer: the wiring review, finding C.
                raise BadRequest("label must have at least one visible character")
            lo, hi = MINUTES_RANGE
            try:
                m = float(minutes) if isinstance(minutes, (int, float)) and not isinstance(minutes, bool) else None
            except OverflowError:
                m = None
            if m is None or not math.isfinite(m) or not lo <= m <= hi:
                raise BadRequest("minutes must be a number from %g to %g" % (lo, hi))
        except BadRequest as e:
            return 400, {"error": str(e)}

        def do(now):
            new = boardlib.add_quick_timer(self.user_data, label, m, now)
            if new is None:
                return 400, {"error": "the label has no text left once control characters are taken out"}
            timer = new["timers"][-1]
            self._change_user(("add", timer))
            return 200, {"ok": True, "timer": {"id": "quick:" + timer["id"], "label": timer["label"],
                                               "ready_at": timer["ready_at"]}}
        return self._locked_change(do)

    def _api_timer_remove(self, req):
        """Remove a quick timer by the id the payload gives it: {"id": "quick:<id>"}."""
        try:
            tid = body_fields(req.json, ("id",))["id"]
            if not isinstance(tid, str) or not QUICK_ID_RE.fullmatch(tid):
                raise BadRequest("id must be a quick timer's id as the payload gives it (quick:...)")
        except BadRequest as e:
            return 400, {"error": str(e)}

        def do(now):
            timers = self.user_data.get("timers") if isinstance(self.user_data.get("timers"), list) else []
            present = any(isinstance(x, dict) and x.get("id") == tid[6:] for x in timers)
            if present or not self._user_loaded:       # unread: it may be in the file
                self._change_user(("remove", tid))
            return 200, {"ok": True, "removed": present}
        return self._locked_change(do)

    def _locked_change(self, do):
        """One change from the page, under the main loop's lock so the state is never read while
        an event is half applied. `do(now)` returns (status, answer); on 200 the board is rebuilt
        and sent (`_after_change`), and the answer carries the view the page will be shown.

        503 when the change cannot be made now: the log not read once yet (a change on an empty
        state would publish a board built on nothing, and a pick made then is dropped as soon as
        the read comes in: finding G), a stop asked for (finding F), or a main loop holding the
        lock past CHANGE_LOCK_SECONDS (reading the rest of a very large log).

        The user block is saved before the answer goes out, but outside the lock: a snapshot is
        taken under it and written after (`_write_snapshot`, in order, newest first), so a slow
        save of state.json delays the change's own answer and never the loop or another change
        (finding E); the rarer writes made under the lock are listed in `_after_read`. A write
        that fails does not change the answer: the change is made, kept in memory and sent, and
        written when a save next succeeds (the loop tries every state_save_seconds)."""
        if not self._lock.acquire(timeout=config.CHANGE_LOCK_SECONDS):
            return 503, {"error": "busy reading the log: try again in a moment"}
        seq = None
        try:
            if self._closing:
                return 503, {"error": "shutting down"}
            if not self._first_read_done:
                return 503, {"error": "still reading the log: try again in a moment"}
            now = self.clock.now()
            status, answer = do(now)
            if status == 200:
                self._after_change(now)
                v = (self.board or {}).get("view") or {}
                answer = dict(answer, view={"name": v.get("name"), "auto": v.get("auto"),
                                            "picked": bool(v.get("picked"))})
            seq = self._take_pending_save()
        finally:
            self._lock.release()
        if seq:
            self._write_snapshot(seq)
        self._wake.set()                                # the loop recomputes its wait (a new timer's moment)
        return status, answer

    def _change_user(self, op):
        """Change the user block (`apply_user_op`); saved on this turn, not after 10 s: it is the
        only record of what the user entered (PLAN §7). Before state.json could be read, the
        change is also kept, to be applied on top of what the file holds once it can be."""
        self.user_data = apply_user_op(self.user_data, op)
        if not self._user_loaded:
            self._user_ops.append(op)
            del self._user_ops[:-config.MAX_USER_OPS]
        self._user_version += 1
        self._unsaved = True
        self._save_now = True

    def _after_change(self, now):
        """After a change from the page: the board rebuilt and sent, the user block saved. While
        the reader catches up on a large log the loop does it once caught up (nothing half-read
        goes out). While saves of state.json are failing, this one is left to the loop's own
        retry (`_save_due`): a file held by another program costs a save about 2 s of retries,
        and taken under the lock by every change that would have made the page's changes wait
        on each other, three of them long enough for a 503."""
        if self._busy_since is not None:
            return
        try:
            self._after_read(now, page=True, write=False)  # the snapshot is written after the lock
        except Exception:                              # noqa: BLE001 - the change itself is made
            self._error("a change from the page")

    # ------------------------------------------------------------------ endpoints

    def _api_health(self, req):
        return 200, {"program": PROGRAM, "pid": os.getpid(), "started": self.started_iso}

    def _api_state(self, req):
        text = self.hub.latest
        if text is None:
            return 503, {"error": "no state yet"}
        return 200, (text.encode("utf-8"), "application/json; charset=utf-8")

    def _api_shutdown(self, req):
        why = req.json.get("reason") if isinstance(req.json.get("reason"), str) else "a request"
        # repr() keeps the reason on this one line: raw, its line breaks could write lines of their
        # own into the log, the launch check's included.
        self.log.info("shutdown asked for (%s)", repr(why[:80]))
        self._halt()
        return 200, {"ok": True, "pid": os.getpid()}

    def _api_status(self, req):
        return 200, self.status()

    def status(self):
        """The instance's own figures. The session id is the log's first line, so every text goes
        through `clean_all` (no control or bidi character reaches a console or a script), and
        through `scrub` (the plan's notice, a pick's name: no lone surrogate either). Paths are
        shown with the user's profile folder as %USERPROFILE% (`shown_path`): the interpreter's
        full path held the Windows user name (the wiring review, privacy)."""
        st = self.reader.state.session
        shown = (self._last_state or {}).get("session") or {}
        f = self.reader.follower
        t = os.times()
        b = self.board or {}                       # one reference, read once: the loop may replace it
        v = b.get("view") or {}
        problems = [p for p in b.get("problems") or [] if isinstance(p, str)]
        bplan = b.get("plan") or {}
        nxt = b.get("next_change_ms")
        timers = self.user_data.get("timers") if isinstance(self.user_data.get("timers"), list) else []
        pick = self.user_data.get("view") if isinstance(self.user_data.get("view"), dict) else None
        return scrub(clean_all({
            "program": PROGRAM, "version": __version__, "pid": os.getpid(), "started": self.started_iso,
            "uptime_s": round(time.time() - self.started, 1), "mode": self.mode, "port": self.port,
            "data_dir": shown_path(self.paths.data), "python": shown_path(sys.executable),
            "below_normal_priority": winutil.is_below_normal(),
            "game": {"process": self.settings["game_process"] if self.mode == "live" else None,
                     "running": bool(self.game_running), "since": iso(self.game_since),
                     "last_seen": iso(self.game_last_seen)},
            "log": {"path": shown_path(self.log_path) if self.log_path else None, "status": self.log_status,
                    "offset": f.offset, "sessions_read": f.sessions},
            "session": {"id": st["id"], "game": st["game"], "last_event": iso(st["last_t"]),
                        "events": st["events"], "unreadable": shown.get("unreadable", 0),
                        "withheld": shown.get("withheld", 0), "withheld_tips": shown.get("withheld_tips", 0)},
            "memory": winutil.own_memory(), "cpu_s": round(t.user + t.system, 2),
            "pages": self.hub.clients, "publishes": self.publishes,
            "requests": self.server.requests if self.server else 0,
            "refused": self.server.refused if self.server else 0,
            "errors": self.errors, "summaries_written": self.summaries_written,
            "replay": self._replay_block(),
            "board": {"view": v.get("name"), "auto": v.get("auto"), "rule": v.get("rule"), "why": v.get("why"),
                      "picked": bool(v.get("picked")), "builds": self.board_builds,
                      "next_change": iso(nxt / 1000.0) if isinstance(nxt, (int, float)) else None,
                      "problems": len(problems), "problem_list": problems[:10]},
            "plan": {"path": shown_path(self.plans.path), "loaded": self.plans.plan is not None,
                     "notice": self.plans.notice, "updated": bplan.get("updated"), "run": bplan.get("run")},
            "user": {"read": self._user_loaded, "quick_timers": sum(1 for x in timers if isinstance(x, dict)),
                     "pick": pick.get("view") if pick else None},
            "reference_tables": list(refdata.shared().loaded),
        }))

    # ------------------------------------------------------------------ the loop

    def _loop(self):
        try:
            try:
                self.start_reading()
            except Exception:                          # noqa: BLE001 - what failed is tried again by tick()
                self._error("the first read")
                self._stop.wait(1.0)
            while not self._stop.is_set() and not self._server_gone():
                try:
                    busy = self.tick()
                except Exception:                      # noqa: BLE001 - the loop carries on
                    self._error("the main loop")
                    busy = False
                    self._stop.wait(1.0)
                if busy:
                    continue
                self._wait()
        except KeyboardInterrupt:
            self.log.info("Ctrl+C")

    def _wait(self):
        """The pause between turns. A stop ends it; a change from the page (`_wake`) only makes it
        look again at when the next turn is due (a new quick timer can come due sooner), without
        a turn of its own: the change has already published and saved, and a turn per change
        polled the log once per change (the wiring review, finding I: 260 turns a second under a
        flood of changes)."""
        deadline = self.mono() + self._next_wait()
        while not self._stop.is_set():
            left = deadline - self.mono()
            if left <= 0 or not self._wake.wait(left):
                return
            self._wake.clear()
            if self._stop.is_set():
                return
            deadline = min(deadline, self.mono() + self._next_wait())

    def _server_gone(self):
        """Has the web server's front-end thread ended, though nothing stopped it? Then nothing
        can reach this instance, and it must not stay up holding the lock: logged, exit 4, and the
        next start (or the scheduled relaunch) brings up one that works."""
        if self.server is None or self.server.alive():
            return False
        self.log.error("stopping: the web server's thread has ended, so nothing can reach this instance "
                       "(exit %d; the next start brings up one that works)", EXIT_SERVER)
        self._exit_code = EXIT_SERVER
        self._halt()
        return True

    def _next_wait(self):
        s = self.settings
        mono = self.mono()
        wait = s["poll_seconds"] if self.game_running else max(0.05, self._next_probe - mono)
        if self._unsaved:
            wait = min(wait, max(0.05, self._last_save + s["state_save_seconds"] - mono))
        if not self._user_loaded:
            wait = min(wait, max(0.05, self._next_user_try - mono))
        if self._backup_checks:
            wait = min(wait, max(0.05, self._backup_checks[0] - mono))
        nxt = self._board_next_ms
        if nxt is not None:
            # The board changes by itself at that moment (an alert expiring, a timer due): the loop
            # wakes for it. The service's clock runs `rate` times faster in a replay, 0 once frozen.
            rate = self.clock.anchor().get("rate") or 0.0
            if rate > 0:
                wait = min(wait, max(0.05, (nxt / 1000.0 - self.clock.now()) / rate))
        if self._run_due:
            wait = min(wait, max(0.05, self._next_run_try - mono))
        # The server is looked at every turn: at least every SERVER_CHECK_SECONDS.
        return min(wait, s["process_check_seconds"], config.SERVER_CHECK_SECONDS)

    def start_reading(self):
        """The first look: is the game running? Then read the log once (no game) or from the top.
        First of all, what the user entered on the page comes back from state.json (`_load_user`).
        A read or a write that fails here raises to the loop, which logs it; what is left (the
        last log's read, a summary, the save) is done by a later `tick()`.

        With the game running, nothing is sent yet: the first `tick()` reads the log and sends
        the state it arrives at, so a page that connects to a restarted service never gets an
        empty state, or a board built on one (the Preflight view for a moment). Changes from the
        page get a 503 until then (`_first_read_done`)."""
        with self._lock:
            try:
                self._load_user()
            except Exception:                          # noqa: BLE001 - never aborts the first read
                self._error("reading the user block of %s" % self.paths.state.name)
            if self.feeder is not None and not self.feeder.is_alive() and not self.feeder.done:
                self.feeder.start()
            running = self._probe()
            self.game_running = running
            self._log_facts("at start, game %s" % ("running" if running else "not running"))
            if running:
                self.log.info("the game is running: reading the current log from the top")
            else:
                self.log.info("no game running: reading the last log once")
                self._last_read_due = True
            self._next_probe = self.mono() + self.settings["process_check_seconds"]
            self._dirty = True
            if self._last_read_due:
                self._read_last_log()
            self._flush_summaries()
            if not running:
                self._after_read(self.clock.now(), write=False)
                self._first_read_done = True
            seq = self._take_pending_save()
        if seq:
            self._write_snapshot(seq)

    def _read_last_log(self):
        self._read_to_end()
        self._end_session("the game is not running")
        self._last_read_due = False

    def _load_user(self):
        """What the user entered on the page, back from state.json. It is the only record of it
        (PLAN §7), so the file is never saved over before it has been read: True once it has (or
        there is none). A file that cannot be opened now (held by another program, or a folder in
        its place) is tried again every `state_save_seconds` and before each save.

        Changes made on the page before the file could be read are not lost, and neither is what
        the file holds: they are applied again, in order, on top of the file's user block (a
        timer added then is added to the file's timers, a view picked then replaces the file's).

        The block is taken through `user_block_from_file` (bounded, ids as the page shows them),
        and only then is it marked read. A file that does not parse, or is not a JSON object, or
        is over MAX_DATA_FILE_BYTES, is never saved over: it is moved aside first
        (`state.damaged.json`, one copy), and until that works nothing is saved. Never raises: a
        fault while taking the block is logged, the block stays unread, and nothing is saved
        over the file (it is called from the first read and from every save)."""
        if self._user_loaded:
            return True
        try:
            return self._take_user_block()
        except Exception:                              # noqa: BLE001 - see above
            self._error("reading the user block of %s" % self.paths.state.name)
            return False

    def _take_user_block(self):
        old = self._read_data_file(self.paths.state)
        if old is _UNREADABLE:
            if not self._user_warned:
                self._user_warned = True
                self.log.warning("%s cannot be read now: nothing is saved over it until it can be",
                                 self.paths.state.name)
            return False
        if old is _DAMAGED:
            if not self._move_aside(self.paths.state):
                return False                               # not moved: never saved over; tried again
            old = None
        raw = old.get("user") if isinstance(old, dict) else None
        base, left_out = user_block_from_file(raw)
        if left_out:
            self.log.warning("%s's user block: left out %s", self.paths.state.name,
                             "; ".join(left_out[:10]) + ("; ..." if len(left_out) > 10 else ""))
        if self._user_warned:
            self.log.info("%s can be read again", self.paths.state.name)
        if base:
            self.log.info("what the user entered on the page is back from %s", self.paths.state.name)
        ops = self._user_ops
        for op in ops:
            base = apply_user_op(base, op)
        if ops:
            self.log.info("%d change(s) made on the page while %s could not be read are merged into it",
                          len(ops), self.paths.state.name)
            self._save_now = self._unsaved = True        # the merged block is the record now
        if left_out:
            self._unsaved = True                         # the bounded block replaces the file's
        if base or ops or self.user_data or raw:
            self.user_data = base
            self._user_version += 1
        self._user_ops = []
        self._user_loaded = True                         # only now: the file's block is taken
        return True

    def _read_data_file(self, path):
        """A JSON file of the data folder, for a file the service saves over (state.json,
        unmapped.json): its value, None when there is no such file, _UNREADABLE when it cannot be
        read now (held, a folder in its place), or _DAMAGED when it was read and is not a JSON
        object (not UTF-8, not JSON, nested deeper than json can read, or over
        MAX_DATA_FILE_BYTES). A UTF-8 byte-order mark is allowed: Windows PowerShell 5.1 writes
        one (`Set-Content -Encoding UTF8`), and a hand-saved file with it is not damaged (the
        wiring review's second round; plan.json is read the same way). Never raises."""
        try:
            with open(path, "rb") as f:
                data = f.read(config.MAX_DATA_FILE_BYTES + 1)
        except FileNotFoundError:
            return None
        except OSError:
            return _UNREADABLE
        if len(data) > config.MAX_DATA_FILE_BYTES:
            return _DAMAGED
        try:
            obj = json.loads(data.decode("utf-8-sig"))
        except (UnicodeDecodeError, ValueError, RecursionError, MemoryError):
            return _DAMAGED
        return obj if isinstance(obj, dict) else _DAMAGED

    def _move_aside(self, path):
        """A damaged data file (see `_read_data_file`) renamed beside it so that it is never saved
        over and lost: to `<stem>.damaged<suffix>`, or, when that copy exists already, to the
        first free `<stem>.damaged-<n><suffix>` (n = 2 to MAX_DAMAGED_COPIES). The first copy is
        never replaced: it is the one most likely to hold what the user entered before anything
        went wrong (the wiring review's second round: a second damage replaced it). Once every
        name is taken, the last one is replaced, and the log says so. True when the file is out
        of the way. Never through a link."""
        names = ["%s.damaged%s" % (path.stem, path.suffix)] + [
            "%s.damaged-%d%s" % (path.stem, n, path.suffix) for n in range(2, config.MAX_DAMAGED_COPIES + 1)]
        free = [n for n in names if not os.path.lexists(path.with_name(n))]
        dest = path.with_name(free[0] if free else names[-1])
        if self._linked(dest, include_self=True) or self._linked(path, include_self=True):
            return False
        try:
            if free:
                os.rename(path, dest)                  # never over a copy that appeared meanwhile
            else:
                os.replace(path, dest)
        except OSError as e:
            if str(path) not in self._links_logged:
                self._links_logged.add(str(path))
                self.log.error("%s is damaged and could not be moved aside (%s): nothing is saved over it",
                               path.name, e.__class__.__name__)
            return False
        if free:
            self.log.warning("%s could not be read as a JSON object: moved aside to %s; the dashboard starts "
                             "it afresh", path.name, dest.name)
        else:
            self.log.warning("%s could not be read as a JSON object: moved aside to %s, replacing the copy that "
                             "was there (the %d earlier copies are kept); the dashboard starts it afresh",
                             path.name, dest.name, len(names) - 1)
        return True

    def _retry_user_load(self):
        """state.json's user block, tried again every `state_save_seconds` until it is read, so
        what the user entered shows once the file can be opened, though nothing needs saving."""
        if self._user_loaded:
            return
        mono = self.mono()
        if mono < self._next_user_try:
            return
        self._next_user_try = mono + self.settings["state_save_seconds"]
        self._load_user()

    def tick(self):
        """One turn of the loop. Returns True while catching up on a large log (no pause). A
        save the turn decided on is written after the lock is released (`_write_snapshot`)."""
        with self._lock:
            busy = self._tick()
            seq = self._take_pending_save()
        if seq:
            self._write_snapshot(seq)
        return busy

    def _tick(self):
        now = self.clock.now()
        mono = self.mono()
        if mono >= self._next_probe:
            self._next_probe = mono + self.settings["process_check_seconds"]
            running = self._probe()
            if running and not self.game_running:
                self._game_appeared(now)
            elif not running and self.game_running:
                self._game_gone()
        if self._run_due and mono >= self._next_run_try:
            self._write_run()
        busy = False
        if self._last_read_due and not self.game_running:
            try:
                self._read_last_log()                  # the first read failed: again
            except Exception:
                self._first_read_done = True           # as below: never refuse changes for good
                raise
        elif self.game_running:
            try:
                busy = self._read(config.READ_BUDGET)
            except Exception:
                # A read that fails ends the catch-up: whether the reader is still behind is told
                # by the next turn that reads. Left set, the flag would refuse every pick (503) and
                # hold back every change from the page for as long as reads kept failing; for the
                # same reason a failed first read counts as the first read done.
                self._busy_since = None
                self._first_read_done = True
                raise
        if not busy:
            # The log has been read to its end once: changes are taken from here on, whatever a
            # later step of this turn does (the wiring review's second round: `_flags` raising
            # every turn kept every change at 503 for good). Nothing goes out in between: the
            # lock is held until the turn is over.
            self._first_read_done = True
        if self._pending and mono >= self._next_summary_try:
            self._flush_summaries()
        if self._backup_checks and mono >= self._backup_checks[0]:
            self._backup_checks.pop(0)
            self._log_backup("a while after the game started")
        if busy:
            # Catching up on a large log (a restart mid-session): a half-read state is not sent,
            # or an alert that ended an hour ago (a downing) would flash up again for a moment.
            # Only a catch-up longer than CATCH_UP_PUBLISH_SECONDS sends one now and then.
            if self._busy_since is None:
                self._busy_since = mono
            if mono - self._busy_since < config.CATCH_UP_PUBLISH_SECONDS:
                return busy
            self._busy_since = mono
        else:
            self._busy_since = None
        self._after_read(now, write=False)             # a save is written by tick(), after the lock
        return busy

    def _probe(self):
        try:
            running = bool(self.probe.running())
        except Exception:                              # noqa: BLE001 - unknown: assume it runs, never end a session on a guess
            self._error("looking for the game")
            running = True if self.game_running is None else self.game_running
        if running:
            self.game_last_seen = time.time()
        return running

    def _game_appeared(self, now):
        self.game_running = True
        self.game_since = now
        self._finalized = None
        self._last_read_due = False        # following the log now; a session that ends in it is summed up then
        self.log.info("the game process appeared")
        self._log_facts("the game started")
        mono = self.mono()
        self._backup_checks = [mono + 30, mono + 120]
        self._dirty = True

    def _game_gone(self):
        self.log.info("the game process is gone")
        self._read_to_end()
        self._end_session("the game process went away")
        self.game_running = False
        self._log_facts("the game ended")
        self._dirty = True
        if self.mode == "replay" and self.exit_when_done:
            self._halt()

    def _read(self, budget):
        f = self.reader.follower
        before_sessions, before_offset, before_first = f.sessions, f.offset, f.first_line
        status = self.reader.poll(budget=budget)
        if status != self.log_status:
            if status == "missing":
                self.log.info("the log is missing: %s", self.log_path)
            elif status == "waiting" and before_first is not None:
                self._log_facts("the log was emptied (no first line yet)")
        self.log_status = status
        if f.sessions != before_sessions:
            self.log.info("a new session starts in the log at offset 0: first line %s (was %s); read %d bytes so far",
                          _show(f.first_line), _show(before_first), f.offset)
            self._log_facts("new session")
            self._finalized = None
        for sm in self.reader.take_finished():
            self._queue_summary(sm, "a new session began in the same file")
        if self.reader.take_lines() or status == "read":
            self._dirty = True
        read_now = f.offset - (before_offset if f.sessions == before_sessions else 0)
        return status == "read" and read_now >= budget

    def _read_to_end(self):
        while not self._stop.is_set():
            self._read(config.READ_BUDGET)
            if self.log_status != "read":
                break
        self.reader.finish()
        for sm in self.reader.take_finished():
            self._queue_summary(sm, "a new session began in the same file")
        self.reader.take_lines()
        self._dirty = True

    def _end_session(self, why):
        sid = self.reader.state.session["id"]
        if sid is None or sid == self._finalized:
            return
        self._finalized = sid
        self._queue_summary(self.reader.summary(complete=True), why)

    def _queue_summary(self, sm, why):
        """A finished session's summary, taken now and written by `_flush_summaries()`."""
        self._pending.append((sm, why))
        del self._pending[:-20]                        # bounded, should writes fail for a long time

    def _flush_summaries(self):
        """Write the waiting summaries, oldest first. A write that fails is logged and the summary
        kept, to be tried again after a pause: a failed write must neither lose a session nor stop
        the rest of the turn."""
        while self._pending:
            sm, why = self._pending[0]
            try:
                self.write_summary(sm, why)
            except Exception:                          # noqa: BLE001
                self._error("writing a session summary")
                self._next_summary_try = self.mono() + self.settings["state_save_seconds"]
                return
            self._pending.pop(0)

    def _session_reset(self, reader):
        f = reader.follower
        self._resets += 1                              # a new State follows: the board's input changed
        self._old_session = {"first": f.first_line, "offset": f.offset}
        self.log.info("the session %s ends in the same file, read to offset %d", _show(f.first_line), f.offset)

    # ------------------------------------------------------------------ what the page gets

    def _after_read(self, now, page=False, write=True):
        """After a turn's read (or a change from the page, `page`): the plan looked at, the
        message rebuilt and sent if anything changed, state.json saved when due. The save is a
        snapshot taken here, under the lock, and written by `_write_snapshot` outside it: at once
        with `write`, or by the caller once it has released the lock (`tick`, a change,
        `start_reading`), so the save of state.json never holds the lock (the wiring review,
        finding E). Some writes still run under it, all rare: unmapped.json when something new
        is first seen (`_note_unmapped`, here and in `_publish`), a session summary, run.json and
        a damaged file's rename (the review's second round measured a change waiting 2.7 s
        behind a mocked 3 s write of unmapped.json)."""
        self._retry_user_load()
        self._refresh_plan()
        flags = self._flags(now)
        if flags != self._flags_last:
            self._flags_last = flags
            self._dirty = True
        if self._dirty or self._board_due(now):
            self._publish(flags, now)
        if self._unmapped_dirty and not page and self._last_state is not None \
                and self.mono() >= self._next_unmapped_try:
            # Entries waiting for an unmapped.json that could not be read (or written): tried again
            # at the save's pace, though the message may not change.
            self._next_unmapped_try = self.mono() + self.settings["state_save_seconds"]
            self._note_unmapped(self._last_state, self.board)
        if self._unsaved and self._save_due(page):
            self._save_now = False
            seq = self._take_snapshot()
            if seq:
                if write:
                    self._write_snapshot(seq)
                else:
                    self._pending_save = max(self._pending_save or 0, seq)

    def _take_pending_save(self):
        """The snapshot `_after_read` left for the lock's holder to write, or None (under the lock)."""
        seq, self._pending_save = self._pending_save, None
        return seq

    def _take_snapshot(self):
        """Under the lock: what state.json is to hold now, as the next numbered snapshot (its
        number is returned), or None when nothing needs saving, or when the file's user block has
        not been read yet (it is never saved over unread). The objects it refers to are never
        changed in place afterwards (each change makes a new user block, each message a new
        state), so it can be written outside the lock."""
        if self._last_state is None or not self._unsaved:
            return None
        self._last_save = self.mono()                  # a save that fails is tried after the same pause
        if not self._load_user():
            return None
        self._snap_seq += 1
        self._snapshot = (self._snap_seq, {"schema": 1, "saved": iso(time.time()), "mode": self.mode,
                                           "user": self.user_data, "state": self._last_state})
        self._unsaved = False
        return self._snap_seq

    def _write_snapshot(self, seq):
        """Write state.json so that snapshot `seq` is on disk: one writer at a time
        (`_save_lock`), never under the main lock. What is written is the newest snapshot, so
        changes made one after another share one write, and an older one is never written after
        a newer one. True when `seq` is on disk. A write that fails marks the state unsaved again
        and the saves failing: the loop then tries again every state_save_seconds."""
        with self._save_lock:
            if self._written_seq >= seq:
                return True
            n, obj = self._snapshot
            try:
                written = self._write(self.paths.state, obj, indent=None)
            except Exception:                          # noqa: BLE001 - tried again after state_save_seconds
                self._unsaved = self._save_failing = True
                self._error("saving %s" % self.paths.state.name)
                return False
            if not written:                            # a link on the way: skipped, logged once
                self._unsaved = True
                return False
            self._written_seq = n
            self._save_failing = False
            return True

    def _save_due(self, page):
        """Is state.json to be saved now? At once after a change from the page (it is the only
        record of what the user entered, PLAN §7), unless the last save failed: then only the
        loop tries again, every state_save_seconds, so a held file costs the page's requests
        nothing. Otherwise every state_save_seconds."""
        if self._save_now and not self._save_failing:
            return True
        return not page and self.mono() - self._last_save >= self.settings["state_save_seconds"]

    def _refresh_plan(self):
        """data/plan.json, looked at on a loop turn at most every PLAN_CHECK_SECONDS: once a
        second while the game runs, once every 10 s or so without it (the loop's own pace, so it
        adds no wake-up). Each look is one stat; the file is read only when its size or time
        changed. A look that fails is logged and never ends the loop."""
        mono = self.mono()
        if mono < self._next_plan_check:
            return
        self._next_plan_check = mono + config.PLAN_CHECK_SECONDS
        try:
            changed = self.plans.refresh()
        except Exception:                              # noqa: BLE001 - PlanStore never raises; guarded anyway
            self._error("looking at %s" % config.PLAN_NAME)
            return
        if not changed:
            return
        self._plan_version += 1
        if self.plans.notice:
            self.log.info("%s: %s", config.PLAN_NAME, clean_text(self.plans.notice)[:300])
        else:
            self.log.info("%s read", config.PLAN_NAME)

    def _board_inputs(self):
        """What board.build depends on besides the clock: the state (it changes only by an event
        applied, or a new State when a session ends in the same file), the plan, the user block,
        and whether the game runs."""
        s = self.reader.state.session
        return (self._resets, s["id"], s["events"], s["unreadable"], self._plan_version, self._user_version,
                bool(self.game_running))

    def _board_due(self, now):
        """Is the board to be built again: an input changed, or the clock reached the last
        payload's next_change_ms? Never otherwise (it is not rebuilt every second)."""
        if self.board is None or self._board_sig != self._board_inputs():
            return True
        nxt = self._board_next_ms
        return nxt is not None and now * 1000.0 >= nxt

    def _update_board(self, now):
        if not self._board_due(now):
            return
        payload = self._build_board(now)
        view = payload.get("view") or {}
        if view.get("pick_dropped") and self._busy_since is None and self.user_data.get("view") is not None:
            # The context the view was picked in has changed: the pick is forgotten (a "reference"
            # pick never is; board.build never says so for it). Not while a large log is half
            # read: the pick's context comes back once the rest is in.
            old = self.user_data.get("view")
            self.log.info("the view picked by hand (%s) is dropped: its context changed",
                          old.get("view") if isinstance(old, dict) else "?")
            self._change_user(("view", None))
            payload = self._build_board(now)
        self.board = payload
        self._board_sig = self._board_inputs()
        nxt = payload.get("next_change_ms")
        # A payload with no next change is one that failed to build: tried again in a minute.
        self._board_next_ms = nxt if isinstance(nxt, (int, float)) else int(round((now + 60.0) * 1000))
        self._log_problems(payload.get("problems"))

    def _build_board(self, now):
        """board.build, guarded: it is documented never to raise, but a fault there must not end
        the service. The page then gets the shape board.build gives a payload that failed."""
        self.board_builds += 1
        try:
            return boardlib.build(self.reader.state, self.plans, self.user_data, now, bool(self.game_running))
        except Exception as e:                         # noqa: BLE001
            self._error("building the board")
            return fallback_board(self.plans, e)

    def _log_problems(self, problems):
        """The board's problems, logged once per distinct set (not on every build)."""
        key = tuple(sorted({p for p in problems or [] if isinstance(p, str)}))
        if not key or key in self._problems_logged:
            return
        if len(self._problems_logged) >= config.MAX_PROBLEM_SETS:
            if len(self._problems_logged) == config.MAX_PROBLEM_SETS:
                self._problems_logged.add(("(more)",))
                self.log.warning("the board has shown %d different sets of problems; later ones are not logged",
                                 config.MAX_PROBLEM_SETS)
            return
        self._problems_logged.add(key)
        self.log.warning("the board left parts out: %s", "; ".join(repr(p[:120]) for p in key[:10]))

    def _flags(self, now):
        """Facts that depend on the clock (PLAN §7: computed here, never inside the state)."""
        if not self.game_running:
            return {"hangar_stuck": False}
        facts = clock_facts(self.reader.state, now)
        return {"hangar_stuck": bool(facts["hangar_stuck"])}

    def _publish(self, flags, now):
        """The page's message (dashboard/STATE.md, "The message and the endpoints"): the stage 2
        parts and the board, sent only when it differs from the last one."""
        self._dirty = False
        self._update_board(now)
        state = self.reader.state.to_dict(private=False)
        body = {"service": self._service_block(), "clock": self._clock_block(), "flags": flags, "state": state,
                "board": self.board}
        # json_text: whatever the plan or the user block held, the message encodes and parses
        # (a lone surrogate becomes U+FFFD, a NaN null); the Hub checks the encoding once more.
        try:
            text = json_text(body, separators=(",", ":"))
        except Exception as e:                         # noqa: BLE001 - a board json cannot write (finding H)
            # A payload that is not JSON (a set, an object: a fault in board.build) is replaced by
            # the fallback board, as a payload that raised is, and built again in a minute.
            self._error("writing the page's message")
            self.board = fallback_board(self.plans, e)
            self._board_next_ms = int(round((now + 60.0) * 1000))
            body["board"] = self.board
            text = json_text(body, separators=(",", ":"))
        if text == self._last_text:
            return
        self._last_text = text
        self._last_state = state
        self.hub.publish(text)
        self.publishes += 1
        self._unsaved = True
        self._note_unmapped(state, self.board)

    def _service_block(self):
        return {"mode": self.mode, "pid": os.getpid(), "started": self.started_iso,
                "game_running": bool(self.game_running), "game_since": iso(self.game_since),
                "log_found": self.log_status not in ("missing", None),
                "replay": self._replay_block(), "terminal": bool(self.settings["terminal"]["enabled"])}

    def _replay_block(self):
        if self.replay_info is None:
            return None
        out = dict(self.replay_info)
        out["done"] = bool(self.feeder.done) if self.feeder is not None else True
        return out

    def _clock_block(self):
        a = self.clock.anchor()
        end = None
        if not self.game_running:
            s = self.reader.state.session
            if s["ended"]:
                end = s["ended"]["t"]
            else:
                known = [t for t in (s["last_t"], self.reader.parser.last_line_t) if t]
                end = max(known) if known else None
        a["session_end"] = round(end * 1000) if end else None
        return a

    def _save_state(self):
        """state.json saved now if anything changed: the snapshot taken under the lock, written
        after it. True when it is on disk, None when there was nothing to save."""
        with self._lock:
            seq = self._take_snapshot()
        return self._write_snapshot(seq) if seq else None

    def _last_save_at_stop(self):
        """The save at shutdown (the wiring review, finding F). Changes are refused from the
        moment the stop was asked for (`_closing`, 503); one already holding the lock is let
        finish, and the last snapshot is taken under the lock after it, then written after any
        write in flight, so a change answered 200 is never overwritten by an older state.

        Both waits are bounded, so a stop never hangs: the lock by SHUTDOWN_LOCK_SECONDS, and the
        write (which first waits for a write in flight, then makes its own) by
        SHUTDOWN_SAVE_SECONDS. A write that has not ended by then is left to its thread and the
        stop goes on, logged (the wiring review's second round: a write that never returned hung
        the stop). The file is written through a temporary file and a rename, so a write cut
        off at the exit leaves state.json as it was, and the next start sweeps the temporary file."""
        self._closing = True
        if not self._lock.acquire(timeout=config.SHUTDOWN_LOCK_SECONDS):
            self.log.error("the last save is skipped: a change held the lock for %.0f s (it saves itself)",
                           config.SHUTDOWN_LOCK_SECONDS)
            return
        try:
            self._take_snapshot()
        finally:
            self._lock.release()
        if self._snap_seq <= self._written_seq:
            return
        writer = threading.Thread(target=self._write_snapshot, args=(self._snap_seq,), name="scdash-last-save",
                                  daemon=True)
        writer.start()
        writer.join(config.SHUTDOWN_SAVE_SECONDS)
        if writer.is_alive():
            self.log.error("the last save did not end in %.0f s (a write that does not return): stopping without "
                           "waiting for it; %s keeps what it held", config.SHUTDOWN_SAVE_SECONDS,
                           self.paths.state.name)

    def _note_unmapped(self, state, payload=None):
        """data/unmapped.json: location codes the names table does not know (`locations`), and
        contracts the contract table could not place (`contracts`, from the board's
        `unmapped_contracts`, keyed by `contract_key`), merged across sessions, each kept to its
        cap with the oldest first seen going first.

        Like state.json, the file is never saved over unread (the wiring review, finding J): it
        is read once, when something new is first seen; while it cannot be read (held, a folder in
        its place), new entries wait in memory and the read is tried again with the next message;
        a file that is not a JSON object is moved aside (`unmapped.damaged.json`); a missing file
        is simply a new one. Every text is cleaned and bounded (`_text_or_none`) and goes through
        the state's name scrubber when it is written, so a player's name learned after the entry
        was first seen is hidden too."""
        codes = [c for c in state.get("unmapped") or [] if isinstance(c, str)]
        contracts = [c for c in (payload or {}).get("unmapped_contracts") or [] if isinstance(c, dict)]
        when = state["session"]["last_event"]
        sid = state["session"]["id"]
        for c in codes:
            if c not in self._unmapped:
                self._unmapped[c] = {"first_seen": when, "session": sid}
                self._unmapped_dirty = True
        for c in contracts:
            k = contract_key(c)
            if k not in self._unmapped_contracts:
                self._unmapped_contracts[k] = {"contract": _text_or_none(c.get("contract")),
                                               "generator": _text_or_none(c.get("generator")),
                                               "title": _text_or_none(c.get("title")),
                                               "first_seen": when, "session": sid}
                self._unmapped_dirty = True
        if not self._unmapped_dirty or not self._load_unmapped():
            return
        self._unmapped = _newest(self._unmapped, config.MAX_UNMAPPED)
        self._unmapped_contracts = _newest(self._unmapped_contracts, config.MAX_UNMAPPED_CONTRACTS)
        try:
            written = self._write(self.paths.unmapped, self.reader.state.scrub({
                "schema": 1,
                "about": "location codes the names table does not know yet, and contracts the contract table "
                         "could not place (reference/contracts.json's lookup found nothing)",
                "locations": self._unmapped, "contracts": self._unmapped_contracts}))
        except Exception:                              # noqa: BLE001 - kept in memory, tried again
            self._error("saving %s" % self.paths.unmapped.name)
            return
        if written:
            self._unmapped_dirty = False

    def _load_unmapped(self):
        """data/unmapped.json merged into what is in memory, once: True when that is done (or there
        is no file). An entry the file holds keeps its first seen; only its own fields are taken,
        each a cleaned, bounded text."""
        if self._unmapped_loaded:
            return True
        old = self._read_data_file(self.paths.unmapped)
        if old is _UNREADABLE:
            if not self._unmapped_warned:
                self._unmapped_warned = True
                self.log.warning("%s cannot be read now: nothing is saved over it until it can be",
                                 self.paths.unmapped.name)
            return False
        if old is _DAMAGED:
            if not self._move_aside(self.paths.unmapped):
                return False
            old = None
        old = old or {}
        if isinstance(old.get("locations"), dict):
            for k, v in old["locations"].items():
                if isinstance(k, str) and len(k) <= 200 and isinstance(v, dict):
                    self._unmapped[k] = {f: _text_or_none(v.get(f)) for f in ("first_seen", "session")}
        if isinstance(old.get("contracts"), dict):
            for k, v in old["contracts"].items():
                if isinstance(k, str) and len(k) <= 40 and isinstance(v, dict):
                    self._unmapped_contracts[k] = {f: _text_or_none(v.get(f)) for f in
                                                   ("contract", "generator", "title", "first_seen", "session")}
        if self._unmapped_warned:
            self.log.info("%s can be read again", self.paths.unmapped.name)
        self._unmapped_loaded = True
        return True

    # ------------------------------------------------------------------ session summaries

    def write_summary(self, sm, why):
        """Write a finished session's summary once. Returns True when a file was written."""
        if not sm or not sm.get("session") or (sm.get("ended") or {}).get("how") == "running":
            return False
        path = self.paths.sessions / summary_name(sm)
        if self._linked(path) or path.exists():
            return False
        self._write(path, sm)
        self.summaries_written += 1
        self.log.info("session summary written: %s (%s; %s)", path.name, sm["ended"]["how"], why)
        self._prune_sessions()
        return True

    def _prune_sessions(self):
        """Keep the newest `sessions_keep` summaries. Dated names sort by their start; a
        `session-<hash>` name (a log without a first line) sorts by its file's time."""
        keep = max(1, int(self.settings["sessions_keep"]))
        d = self.paths.sessions
        if self._linked(d, include_self=True):
            return

        def when(name):
            if re.match(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T", name):
                return name[:20]
            try:
                return iso(os.stat(d / name).st_mtime).replace(":", "-")[:19] + "Z"
            except OSError:
                return ""
        try:
            names = sorted((p for p in os.listdir(d) if p.endswith(".json")), key=when)
        except OSError:
            return
        for name in names[:-keep]:
            try:
                os.remove(self.paths.sessions / name)
            except OSError:
                pass

    # ------------------------------------------------------------------ the rotation proof

    def _log_facts(self, why):
        """What proves the game's log rotation is undisturbed (PLAN §8, §12 stage 2): the log's
        size, file identity and first line, and where the follower stands."""
        p = self.log_path
        if p is None:
            return
        try:
            st = os.stat(p)
            facts = "size %d, file id %#x, volume %#x, created %s, modified %s" % (
                st.st_size, st.st_ino, st.st_dev, iso(getattr(st, "st_birthtime", st.st_ctime)), iso(st.st_mtime))
        except OSError as e:
            facts = "not readable (%s)" % e.__class__.__name__
        f = self.reader.follower
        self.log.info("log facts (%s): %s; first line %s; follower at offset %d, sessions read %d",
                      why, facts, _show(_first_line(p)), f.offset, f.sessions)
        if why.startswith("the game started") or why == "new session":
            self._log_backup(why)

    def _log_backup(self, why):
        p = self.log_path
        if p is None or self.mode != "live":
            return
        d = p.parent / "logbackups"
        newest = None
        try:
            with os.scandir(d) as it:
                for e in it:
                    if e.name.startswith("Game ") and e.name.endswith(".log"):
                        st = e.stat()
                        born = getattr(st, "st_birthtime", st.st_ctime)
                        if newest is None or born > newest[1]:
                            newest = (e.path, born)
        except OSError:
            return
        if newest is None:
            self.log.info("newest backup (%s): none", why)
            return
        path = newest[0]
        try:
            size = os.stat(path).st_size
        except OSError:
            size = None
        first = _first_line(path)
        text = "newest backup (%s): %s, size %s, created %s, first line %s" % (
            why, os.path.basename(path), size, iso(newest[1]), _show(first))
        old = self._old_session
        if old and old["first"] is not None and first == old["first"]:
            text += "; it is the session that ended in place, which we had read to offset %d: %s" % (
                old["offset"], "same size, rotation undisturbed" if size == old["offset"]
                else "sizes differ (the game wrote more after our last read, or the copy is not done)")
        self.log.info(text)


def _first_line(path):
    try:
        with winutil.open_shared(path) as f:
            head = f.read(512)
    except OSError:
        return None
    nl = head.find(b"\n")
    return (head[:nl] if nl >= 0 else head).rstrip(b"\r")


def _show(line):
    if line is None:
        return "(none)"
    if isinstance(line, bytes):
        line = line.decode("utf-8", "replace")
    return repr(line[:160])


# ---------------------------------------------------------------------------- talking to an instance

class NotListening(Exception):
    pass


def port_answering(port, timeout=0.5):
    """Is something listening on 127.0.0.1:<port>? A listener accepts at once; a refused connect
    on Windows takes about 2 s [seen 2026-11-27], so a short timeout means "nothing there"."""
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=timeout):
            return True
    except OSError:
        return False


def http_call(port, method, path, body=None, token=None, timeout=3.0, origin=True):
    """One request to 127.0.0.1:<port>. Returns (status, bytes). NotListening when nothing is there."""
    try:
        sock = socket.create_connection(("127.0.0.1", port), timeout=0.5)
    except OSError:
        raise NotListening() from None
    sock.settimeout(timeout)
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
    conn.sock = sock
    try:
        headers = {}
        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
            if origin:
                headers["Origin"] = "http://127.0.0.1:%d" % port
        if token:
            headers[TOKEN_HEADER] = token
        conn.request(method, path, body=data, headers=headers)
        resp = conn.getresponse()
        return resp.status, resp.read(1 << 20)
    finally:
        conn.close()


def probe_health(port):
    """Who is on the port? ("none", None), ("scdash", health) or ("foreign", why)."""
    try:
        status, raw = http_call(port, "GET", "/api/health")
    except NotListening:
        return "none", None
    except (OSError, http.client.HTTPException) as e:
        return "foreign", "it does not answer like the dashboard (%s)" % e.__class__.__name__
    if status != 200:
        return "foreign", "it answers HTTP %d to the dashboard's health check" % status
    try:
        obj = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return "foreign", "its answer to the health check is not the dashboard's"
    if isinstance(obj, dict) and obj.get("program") == PROGRAM and isinstance(obj.get("pid"), int) \
            and isinstance(obj.get("started"), str):
        return "scdash", obj
    return "foreign", "its answer to the health check is not the dashboard's"


def instance_info(paths, port=None):
    """What is known about the instance for a data folder, without changing anything."""
    run = read_json(paths.run)
    run = run if valid_run(run) else None
    lock_held = paths.lock().held_elsewhere()
    p = run["port"] if run else (port or config.PORT)
    kind, health = probe_health(p)
    note = health if kind == "foreign" else None
    matches = bool(kind == "scdash" and run and health["pid"] == run["pid"] and health["started"] == run["started"])
    if matches and not lock_held:
        # The mutex is the truth: nobody holds this folder's lock, so no instance of it is alive and
        # whatever answers is not ours, though it repeats run.json's pid and start. No command
        # talks to it as ours, and none sends it run.json's token.
        kind, health, matches = "foreign", None, False
        note = "it repeats this dashboard's health answer, but no instance for this data folder is running"
    healthy = bool(lock_held and matches)
    # Ours but not answering (hung, suspended, busy): the lock is held and run.json's process is
    # alive, a Python process created at the time run.json recorded. Without that time there is
    # no match: a live Python process with that id could be anyone's.
    alive = bool(run and lock_held and not healthy and run_process_alive(run))
    return {"run": run, "lock_held": lock_held, "port": p, "port_user": kind,
            "health": health if kind == "scdash" else None,
            "port_note": note, "healthy": healthy, "hung": alive}


def run_process_alive(run):
    """Is run.json's process still the one that wrote it? Its name must be python(w).exe and its
    creation time must match the one run.json recorded, to the millisecond; both come from one
    snapshot of the process table, which opens no process. A run.json without that time (an
    older one, or off Windows) matches nothing. Read-only: nothing is signalled or ended here, or
    anywhere in scdash."""
    recorded = run.get("created")
    if isinstance(recorded, bool) or not isinstance(recorded, (int, float)):
        return False
    entry = next((e for e in winutil.process_table() if e[0] == run["pid"]), None)
    if entry is None or entry[1].lower() not in winutil.PYTHON_NAMES:
        return False
    return entry[2] is not None and abs(entry[2] - recorded) < 0.001


def instance_status(info):
    """The running instance's own status, or None."""
    if not info["healthy"]:
        return None
    try:
        status, raw = http_call(info["port"], "GET", "/api/status")
        if status == 200:
            return json.loads(raw.decode("utf-8"))
    except (NotListening, OSError, http.client.HTTPException, ValueError):
        pass
    return None


def ask_to_stop(info, reason="the stop command"):
    status, _ = http_call(info["port"], "POST", "/api/shutdown", body={"reason": reason},
                          token=info["run"]["token"])
    return status == 200


def launch_background(args, cwd=config.REPO_ROOT):
    """Start the background process: `pythonw dashboard/scdash.py run --background <args>`.

    The one place that does it. In stage 4, with the logon task installed, `start` goes through
    the task instead (`schtasks /Run`), so the scheduler knows the instance it would otherwise
    start a second copy of (PLAN §6); that switch belongs here. No console window: pythonw has
    none, and the process is detached from the caller's console. Returns the Popen object."""
    exe = Path(sys.executable)
    pyw = exe.with_name("pythonw.exe")
    cmd = [str(pyw if winutil.IS_WINDOWS and pyw.exists() else exe), str(SCRIPT), "run", "--background"] + list(args)
    kw = dict(cwd=str(cwd), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
              close_fds=True)
    if winutil.IS_WINDOWS:
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
        try:
            # Out of the caller's job, so closing the terminal that ran `start` does not end it.
            return subprocess.Popen(cmd, creationflags=flags | subprocess.CREATE_BREAKAWAY_FROM_JOB, **kw)
        except OSError:
            return subprocess.Popen(cmd, creationflags=flags, **kw)
    return subprocess.Popen(cmd, start_new_session=True, **kw)
