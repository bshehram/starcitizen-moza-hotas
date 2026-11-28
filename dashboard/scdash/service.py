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

Every error inside the loop is caught, logged (repeats counted, not repeated) and passed over.
Two things end it instead, each with an error in the log: run.json that cannot be written (exit
3, above), and the web server's front-end thread gone (exit 4): with no server nothing can reach
the instance, and the next start, or the scheduled relaunch, brings up one that works.

The clock is read here and only here, and handed to what needs it (`clock_facts`); the state
never reads it (PLAN §7). Every file is written to a temporary file and renamed into place, and
never through a junction or a symbolic link below the data folder (`link_on_the_way`).
"""
import hashlib
import http.client
import json
import logging
import logging.handlers
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
from pathlib import Path

from . import __version__, config, winutil
from .names import LocationNames
from .pipeline import LogReader
from .records import parse_ts
from .server import CHANGE, PROGRAM, READ, TOKEN_HEADER, Hub, Server
from .state import clock_facts
from .words import clean_all, iso

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
    atomic_write(path, json.dumps(obj, indent=indent, ensure_ascii=False) + "\n")


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
                 exit_when_done=False, console=False):
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
        self.mono = time.monotonic        # the interval clock (tests replace it)
        self._stop = threading.Event()
        self._dirty = True
        self._last_text = None
        self._last_state = None
        self._unsaved = False
        self._last_save = float("-inf")
        self._flags_last = None
        self._next_probe = 0.0
        self._backup_checks = []
        self._old_session = None
        self._last_error = None
        self._error_repeats = 0
        self._unmapped = {}
        self._finalized = None           # the session id whose end was handled
        self._user_loaded = False        # state.json's user block read (or there is none)
        self._user_warned = False
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
            fh = logging.handlers.RotatingFileHandler(
                str(self.paths.log), maxBytes=int(self.settings["log_max_bytes"]),
                backupCount=int(self.settings["log_backups"]), encoding="utf-8")
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
        self.errors += 1
        text = traceback.format_exc()
        if text == self._last_error:
            self._error_repeats += 1
            n = self._error_repeats
            if n in (10, 100, 1000) or n % 10000 == 0:
                self.log.error("the same error in %s, %d times now", where, n + 1)
            return
        self._last_error, self._error_repeats = text, 0
        self.log.error("error in %s (carrying on):\n%s", where, text.rstrip())

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
            if self.feeder is not None:
                self.feeder.stop()
            if self.server is not None:
                self.server.stop()
            try:
                self._save_state()
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
            self._stop.set()

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
        self._stop.set()

    def _install_signals(self):
        if threading.current_thread() is not threading.main_thread():
            return
        for name in ("SIGTERM", "SIGBREAK"):
            sig = getattr(signal, name, None)
            if sig is not None:
                try:
                    signal.signal(sig, lambda *_: self._stop.set())
                except (OSError, ValueError):
                    pass

    def _page_vars(self):
        """What the page is served with: its layout, its mode, and which instance served it (pid
        and start), so it can tell from the first stream message on whether the service it talks
        to was restarted and its token is dead."""
        return {"terminal": "on" if self.settings["terminal"]["enabled"] else "off", "mode": self.mode,
                "instance": "%d/%s" % (os.getpid(), self.started_iso)}

    def _register(self, srv):
        """Every endpoint, behind its guard. Stage 3 adds timers and a forced view here (CHANGE),
        stage 4b the terminal (CHANGE for keystrokes, a Hub of its own behind PRIVATE for its output)."""
        srv.route("GET", "/api/health", self._api_health, READ)
        srv.route("GET", "/api/status", self._api_status, READ)
        srv.route("GET", "/api/state", self._api_state, READ)
        srv.stream("/api/stream", self.hub, READ)
        srv.route("POST", "/api/shutdown", self._api_shutdown, CHANGE)

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
        self._stop.set()
        return 200, {"ok": True, "pid": os.getpid()}

    def _api_status(self, req):
        return 200, self.status()

    def status(self):
        """The instance's own figures. The session id is the log's first line, so every text goes
        through `clean_all` (no control or bidi character reaches a console or a script)."""
        st = self.reader.state.session
        shown = (self._last_state or {}).get("session") or {}
        f = self.reader.follower
        t = os.times()
        return clean_all({
            "program": PROGRAM, "version": __version__, "pid": os.getpid(), "started": self.started_iso,
            "uptime_s": round(time.time() - self.started, 1), "mode": self.mode, "port": self.port,
            "data_dir": str(self.paths.data), "python": sys.executable,
            "below_normal_priority": winutil.is_below_normal(),
            "game": {"process": self.settings["game_process"] if self.mode == "live" else None,
                     "running": bool(self.game_running), "since": iso(self.game_since),
                     "last_seen": iso(self.game_last_seen)},
            "log": {"path": str(self.log_path) if self.log_path else None, "status": self.log_status,
                    "offset": f.offset, "sessions_read": f.sessions},
            "session": {"id": st["id"], "game": st["game"], "last_event": iso(st["last_t"]),
                        "events": st["events"], "unreadable": shown.get("unreadable", 0)},
            "memory": winutil.own_memory(), "cpu_s": round(t.user + t.system, 2),
            "pages": self.hub.clients, "publishes": self.publishes,
            "requests": self.server.requests if self.server else 0,
            "refused": self.server.refused if self.server else 0,
            "errors": self.errors, "summaries_written": self.summaries_written,
            "replay": self._replay_block(),
        })

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
                self._stop.wait(self._next_wait())
        except KeyboardInterrupt:
            self.log.info("Ctrl+C")

    def _server_gone(self):
        """Has the web server's front-end thread ended, though nothing stopped it? Then nothing
        can reach this instance, and it must not stay up holding the lock: logged, exit 4, and the
        next start (or the scheduled relaunch) brings up one that works."""
        if self.server is None or self.server.alive():
            return False
        self.log.error("stopping: the web server's thread has ended, so nothing can reach this instance "
                       "(exit %d; the next start brings up one that works)", EXIT_SERVER)
        self._exit_code = EXIT_SERVER
        self._stop.set()
        return True

    def _next_wait(self):
        s = self.settings
        mono = self.mono()
        wait = s["poll_seconds"] if self.game_running else max(0.05, self._next_probe - mono)
        if self._unsaved:
            wait = min(wait, max(0.05, self._last_save + s["state_save_seconds"] - mono))
        if self._backup_checks:
            wait = min(wait, max(0.05, self._backup_checks[0] - mono))
        if self._run_due:
            wait = min(wait, max(0.05, self._next_run_try - mono))
        # The server is looked at every turn: at least every SERVER_CHECK_SECONDS.
        return min(wait, s["process_check_seconds"], config.SERVER_CHECK_SECONDS)

    def start_reading(self):
        """The first look: is the game running? Then read the log once (no game) or from the top.
        First of all, what the user entered on the page comes back from state.json (`_load_user`).
        A read or a write that fails here raises to the loop, which logs it; what is left (the
        last log's read, a summary, the save) is done by a later `tick()`."""
        self._load_user()
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
        self._after_read(self.clock.now())

    def _read_last_log(self):
        self._read_to_end()
        self._end_session("the game is not running")
        self._last_read_due = False

    def _load_user(self):
        """What the user entered on the page, back from state.json. It is the only record of it
        (PLAN §7), so the file is never saved over before it has been read: True once it has (or
        there is none). A file that cannot be opened now (held by another program, or a folder in
        its place) is tried again before each save."""
        if self._user_loaded:
            return True
        try:
            with open(self.paths.state, "rb") as f:
                raw = f.read()
        except FileNotFoundError:
            self._user_loaded = True
            return True
        except OSError as e:
            if not self._user_warned:
                self._user_warned = True
                self.log.warning("%s cannot be read now (%s): nothing is saved over it until it can be",
                                 self.paths.state.name, e.__class__.__name__)
            return False
        try:
            old = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError, RecursionError):
            old = None
            self.log.warning("%s is not JSON: nothing the user entered is in it", self.paths.state.name)
        self._user_loaded = True
        if self._user_warned:
            self.log.info("%s can be read again", self.paths.state.name)
        if isinstance(old, dict) and isinstance(old.get("user"), dict):
            self.user_data = old["user"]
            if self.user_data:
                self.log.info("what the user entered on the page is back from %s", self.paths.state.name)
        return True

    def tick(self):
        """One turn of the loop. Returns True while catching up on a large log (no pause)."""
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
            self._read_last_log()                      # the first read failed: again
        elif self.game_running:
            busy = self._read(config.READ_BUDGET)
        if self._pending and mono >= self._next_summary_try:
            self._flush_summaries()
        if self._backup_checks and mono >= self._backup_checks[0]:
            self._backup_checks.pop(0)
            self._log_backup("a while after the game started")
        self._after_read(now)
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
            self._stop.set()

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
        self._old_session = {"first": f.first_line, "offset": f.offset}
        self.log.info("the session %s ends in the same file, read to offset %d", _show(f.first_line), f.offset)

    # ------------------------------------------------------------------ what the page gets

    def _after_read(self, now):
        flags = self._flags(now)
        if flags != self._flags_last:
            self._flags_last = flags
            self._dirty = True
        if self._dirty:
            self._publish(flags)
        if self._unsaved and self.mono() - self._last_save >= self.settings["state_save_seconds"]:
            self._save_state()

    def _flags(self, now):
        """Facts that depend on the clock (PLAN §7: computed here, never inside the state)."""
        if not self.game_running:
            return {"hangar_stuck": False}
        facts = clock_facts(self.reader.state, now)
        return {"hangar_stuck": bool(facts["hangar_stuck"])}

    def _publish(self, flags):
        self._dirty = False
        state = self.reader.state.to_dict(private=False)
        body = {"service": self._service_block(), "clock": self._clock_block(), "flags": flags, "state": state}
        text = json.dumps(body, separators=(",", ":"), ensure_ascii=False)
        if text == self._last_text:
            return
        self._last_text = text
        self._last_state = state
        self.hub.publish(text)
        self.publishes += 1
        self._unsaved = True
        self._note_unmapped(state)

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
        if self._last_state is None or not self._unsaved:
            return
        self._last_save = self.mono()                  # a save that fails is tried after the same pause
        if not self._load_user():
            return                                     # never over a file whose user block was not read
        if self._write(self.paths.state, {"schema": 1, "saved": iso(time.time()), "mode": self.mode,
                                          "user": self.user_data, "state": self._last_state}, indent=None):
            self._unsaved = False

    def _note_unmapped(self, state):
        codes = state.get("unmapped") or []
        new = [c for c in codes if c not in self._unmapped]
        if not new:
            return
        if not self._unmapped:
            old = read_json(self.paths.unmapped)
            if isinstance(old, dict) and isinstance(old.get("locations"), dict):
                self._unmapped.update({k: v for k, v in old["locations"].items() if isinstance(v, dict)})
            new = [c for c in codes if c not in self._unmapped]
            if not new:
                return
        when = state["session"]["last_event"]
        for c in new:
            self._unmapped[c] = {"first_seen": when, "session": state["session"]["id"]}
        if len(self._unmapped) > config.MAX_UNMAPPED:
            keep = sorted(self._unmapped.items(), key=lambda kv: kv[1].get("first_seen") or "")[-config.MAX_UNMAPPED:]
            self._unmapped = dict(keep)
        self._write(self.paths.unmapped, {"schema": 1, "about": "location codes the names table does not know yet",
                                          "locations": self._unmapped})

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
