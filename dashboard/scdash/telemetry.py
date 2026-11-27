"""The game's telemetry stream as an optional second source (PLAN §3, §5, §12 stage 6).

Copyright (c) 2026 archelium (support@archelium.com) for the parts marked "From CSR" below,
used under the MIT License (see dashboard/THIRD_PARTY_NOTICES). Everything else in this file is
this project's own.

What the service (stage 6 wiring) uses:

    reader = TelemetryReader(game_running=...)   # nothing is read or connected yet
    reader.start()                        # a background thread; returns at once
    reader.set_port(port)                 # from port_from_log_line(), on a startup-block line
    snap, age = reader.latest()           # the newest fresh snapshot and its age, or (None, ...)
    events = reader.take_events()         # stream events since the last call
    reader.connected, reader.status()     # for `status`
    reader.stop()                         # returns at once; join(timeout) to wait

**A source of its own.** Everything this file hands out carries `"source": "telemetry"`, and
an event's kind is `telemetry.<NAME>` (`telemetry.ACTOR_ENTER_SEAT`), so it can never be taken
for a log event. Snapshots and events are live readings: they never go through the log's
`State.apply`, they are never replayed by `replay`, and they are never written to the session
records as if the log had said them (PLAN §5).

Safety (PLAN §8), enforced below this file in telemetry_h2.py: the reader connects only to
127.0.0.1, can send only the one request for the read-only stream, caps what it accepts, and
times out. It never switches the stream on: that is the user's step. It never writes outside
dashboard/data/; the program file is only read, with full sharing, only by `load_schema`, and
only while the game runs or once the file has not changed for a minute.

Nothing about the live stream's behavior has been seen on this PC. The rate (about 15 to 18
snapshots a second), the stream being silent until the character spawns, and two clients being
able to read at once are other tools' notes [ref: CSR docs/telemetry/NOTES.md, PLAN §3].
"""
import base64
import json
import os
import re
import struct
import threading
import time
from collections import deque
from datetime import datetime, timezone

from . import config
from . import telemetry_h2 as h2
from . import telemetry_proto as proto
from . import telemetry_readings as readings_mod
from .telemetry_h2 import DEFAULT_PORT, LOOPBACK, STREAM_PATH  # noqa: F401  (re-exported)

SOURCE = readings_mod.SOURCE
TELEMETRY_DIR = config.DATA_DIR / "telemetry"           # git-ignored: schema cache and captures
SCHEMA_CACHE = TELEMETRY_DIR / "schema.json"

# Retry ladder (PLAN §12 stage 6): every 5 s for the first minute of failures, every 10 s until
# three minutes, then once a minute. A connection that brought snapshots resets it.
RETRY_STEPS = ((60.0, 5.0), (180.0, 10.0), (None, 60.0))
# From CSR sc_telemetry.py lines 699-707 (the recorder's timings): connect timeout 2 s,
# silence before a reconnect. Changed: the silence limit is 30 s instead of 15, and the read
# timeout is 1 s, the time stop() and the silence check can take at most.
# On this PC a connect to a loopback port where nothing listens is refused only after about
# 2 s (Windows retries the SYN) [seen 2026-11-27], so what `status` counts as a refusal is in
# practice this 2 s timeout running out.
CONNECT_TIMEOUT_S = 2.0
READ_TIMEOUT_S = 1.0
SILENT_S = 30.0
STALE_S = 3.0              # a snapshot older than this is not handed out as current
IDLE_S = 10.0              # how often a reader told the game is not running asks again
# Caps on what one snapshot may make the reader do (real snapshots: 3 top-level fields, an
# events part of 4 bytes [CSR's captures, decoded here]). Breaking one drops the connection.
MAX_TOP_FIELDS = 16
MAX_EVENTS_BYTES = 2048
EVENT_KEEP = 64            # raw events parts kept between take_events() calls
MAX_EVENTS_PER_CALL = 64
EVENT_ITEMS = 64           # decode budget for one events part
# From CSR sc_stats.py line 1452 (`_TLM_SERVICE_LINES`): the game says whether it started the
# telemetry service in its startup block, within the first 1,500 lines. Unchanged.
STARTUP_LINES = 1500
CAPTURE_MAGIC = b"SCDTLM1\n"
CAPTURE_MAX_BYTES = 64 << 20


def default_exe():
    """LIVE\\Bin64\\StarCitizen.exe, or None when the repo is not inside a game install."""
    live = config.default_live()
    return str(live / "Bin64" / "StarCitizen.exe") if live else None


def retry_delay(failing_for, steps=RETRY_STEPS):
    """Seconds to wait before the next attempt, after `failing_for` seconds of failures."""
    for until, delay in steps:
        if until is None or failing_for < until:
            return delay
    return steps[-1][1]


# --------------------------------------------------------------------------- the log line

# The whole record: the time prefix, at least one level part, an optional tag, then the
# service's own bracketed name, then only the address. Text anywhere else in a line (inside a
# notice, say) cannot match, and neither can a continuation piece of a multi-line record, which
# has a time prefix but no level part (PLAN §3, *Reading the lines*).
_PORT_RE = re.compile(
    rb"<[^>\r\n]{1,40}>[ \t]+(?:\[(?!sc\.game\.)[^\]\r\n]{1,40}\][ \t]*)+(?:<[^>\r\n]{1,80}>[ \t]*)?"
    rb"\[sc\.game\.telemetry\.v1\.GameTelemetryService\]:[ \t]*"
    rb"(127\.0\.0\.1|localhost|0\.0\.0\.0):(\d{1,5})[ \t]*\r?\n?")


def port_from_log_line(line):
    """The port in a log record that announces the stream's address, else None.

    Contract: call it only on lines of the log's startup block, the first STARTUP_LINES lines
    of a session, where the game reports the services it started (From CSR: sc_stats.py lines
    1449-1452 look for the service's markers within the first 1,500 lines). The caller enforces
    that.

    The record's shape is second-hand: CSR's sc_stats.py looks for the text
    "[sc.game.telemetry.v1.GameTelemetryService]:" and the brief for this stage gives the
    address after it; no log on this PC has one, because the stream has never been on. So the
    match is strict: time prefix, at least one level part, at most one tag, the bracketed
    service name, the address, end of line. 0.0.0.0 (all interfaces, which include loopback) is accepted too, my
    reading: the program file lets the address be set (grpc.client.server.address [game]). Any
    other host gives None, since the reader connects to 127.0.0.1 only. Takes bytes or text."""
    if isinstance(line, str):
        line = line.encode("utf-8", "replace")
    if not isinstance(line, (bytes, bytearray)) or len(line) > 1024:
        return None
    m = _PORT_RE.fullmatch(bytes(line))
    if not m:
        return None
    port = int(m.group(2))
    return port if 0 < port < 65536 else None


class _Breach(Exception):
    """A snapshot broke one of the reader's caps: the connection is dropped."""


# --------------------------------------------------------------------------- the reader

class TelemetryReader:
    """Reads the stream in a background thread; decodes the newest snapshot when asked.

    The thread keeps only the newest raw message, plus the raw events part of any snapshot that
    carries events (they arrive on one snapshot only, so dropping the others would lose them),
    at most EVENT_KEEP of them, each at most MAX_EVENTS_BYTES. `latest()` decodes in the
    caller's thread, at most once per new snapshot, so 15 or more snapshots a second cost a
    buffer swap and a walk of at most MAX_TOP_FIELDS top-level fields each.

    `game_running`, when given, is called from the reader's own thread, so it must be safe to
    call from any thread. It is asked before each attempt and every IDLE_S while connected;
    False means no connection and no reading of the program file.

    The retry-and-silence loop follows CSR's Recorder (sc_telemetry.py lines 754-946: the
    `game_running` callable, 769; `stop` closing the open stream from the calling thread,
    804-815; the refusal timing in `_cycle`, 887-946; the silence check in `_read`, 985-999).
    From CSR, rewritten: no recording, no channel or lock file, a three-step retry ladder,
    decode on demand, caps on events and top-level fields, staleness, per-run stop events so
    that start() after stop() never blocks, and every state change under one lock."""

    def __init__(self, exe_path=None, cache_path=None, port=None, game_running=None,
                 schema=None, silent_s=SILENT_S, retry_steps=RETRY_STEPS,
                 read_timeout=READ_TIMEOUT_S, connect_timeout=CONNECT_TIMEOUT_S,
                 stale_s=STALE_S, settle_s=proto.SETTLE_S, clock=time.monotonic, wall=time.time):
        self.exe_path = exe_path if exe_path is not None else default_exe()
        self.cache_path = str(cache_path if cache_path is not None else SCHEMA_CACHE)
        self.game_running = game_running
        self.silent_s = silent_s
        self.retry_steps = retry_steps
        self.read_timeout = read_timeout
        self.connect_timeout = connect_timeout
        self.stale_s = stale_s
        self.settle_s = settle_s
        self.clock, self.wall = clock, wall
        self._lock = threading.Lock()
        self._life = threading.Lock()
        self._thread = None
        self._run_ev = None          # (stop event, wake event) of the current run
        self._stream = None
        self._connecting = None      # a stream still connecting, so stop() can close it
        self._port = None
        self._schema = schema        # given (tests) or loaded by the thread
        self._schema_key = None
        self._schema_tried = False
        self._schema_how = "given" if schema is not None else ""
        self._fixed_schema = schema is not None
        self._compiled = None        # (schema, response type, Readings, events field no, events type)
        self._raw = None             # newest raw snapshot, its receive time and sequence number
        self._raw_t = 0.0
        self._seq = 0
        self._cache = None           # (seq, result, receive time) of the last good decode
        self._failed_seq = None      # seq of a newest snapshot that failed to decode
        self._events_raw = deque(maxlen=EVENT_KEEP)   # (wall time, raw EventsFrame bytes)
        self._st = {"source": SOURCE, "state": "stopped", "reason": "", "port": DEFAULT_PORT,
                    "bytes": 0, "snapshots": 0, "decode_errors": 0, "protocol_errors": 0,
                    "connects": 0, "reconnects": 0, "refusals": 0, "events": 0,
                    "events_dropped": 0, "schema": "", "schema_how": "", "missing_readings": []}
        if port is not None:
            self.set_port(port)

    # -- the interface -----------------------------------------------------

    def start(self):
        """Start the background thread, if it is not running. Never blocks."""
        with self._life:
            if self._thread is not None and self._thread.is_alive() and not self._run_ev[0].is_set():
                return
            old = self._thread
            ev = (threading.Event(), threading.Event())
            self._run_ev = ev
            self._thread = threading.Thread(target=self._run, args=(ev, old),
                                            name="scdash-telemetry", daemon=True)
            self._set(state="starting", reason="")
            self._thread.start()

    def stop(self):
        """Ask the thread to stop and close any open connection. Never blocks: the thread
        ends within about one read timeout. Safe at any moment, any number of times."""
        with self._life:
            ev = self._run_ev
            if ev is not None:
                ev[0].set()
                ev[1].set()
        with self._lock:
            streams = (self._stream, self._connecting)
        for stream in streams:
            if stream is not None:
                stream.close()               # also ends a connect still in progress

    def join(self, timeout=None):
        """Wait for a stopped thread to end (for shutdown and tests). True when it has."""
        t = self._thread
        if t is not None and t is not threading.current_thread():
            t.join(timeout)
            return not t.is_alive()
        return True

    def wake(self):
        """Try to connect now instead of waiting out the retry delay."""
        ev = self._run_ev
        if ev is not None:
            ev[1].set()

    def set_port(self, port):
        """Use this port from now on (from the game's log line). Ignored unless 1-65535."""
        if isinstance(port, int) and not isinstance(port, bool) and 0 < port < 65536:
            with self._lock:
                changed = port != self._port
                self._port = port
                self._st["port"] = port
            if changed:
                self.wake()

    @property
    def connected(self):
        with self._lock:
            return self._stream is not None

    def latest(self, allow_stale=False):
        """(snapshot, age in seconds) of the newest snapshot.

        The snapshot is None when the stream is not connected, has sent nothing, or its newest
        snapshot is older than `stale_s` (a stream connected but silent): a caller that only
        checks for None can never show old values as current. The age is given whenever there
        is a snapshot at all. `allow_stale=True` hands out an old one too, marked
        `"stale": True`, for diagnostics.

        The snapshot is {"source": "telemetry", "stale", "readings", "withheld", "other",
        "schema"}; treat it as read-only, the same object is handed out until a newer one."""
        with self._lock:
            raw, t, seq, cache, compiled = self._raw, self._raw_t, self._seq, self._cache, self._compiled
            failed = self._failed_seq == seq
        if raw is None or compiled is None:
            return None, None
        age = max(0.0, self.clock() - t)
        stale = age > self.stale_s
        if stale and not allow_stale:
            return None, age
        if cache is not None and cache[0] == seq:
            out = cache[1]
        else:
            # A message that failed once is not decoded again on the next call.
            out = None if failed else self._decode(raw, compiled)
            if out is None:
                with self._lock:
                    if self._raw is raw:
                        self._failed_seq = seq
                if cache is None:
                    return None, age
                out, t = cache[1], cache[2]
                age = max(0.0, self.clock() - t)
                stale = age > self.stale_s
                if stale and not allow_stale:
                    return None, age
            else:
                with self._lock:
                    if self._raw is raw:           # still the newest: keep it for the next call
                        self._cache = (seq, out, t)
        if out.get("stale") != stale:
            out = dict(out, stale=stale)
        return out, age

    def _decode(self, raw, compiled):
        schema, resp, rdg, _, _ = compiled
        decoded = schema.decode_safe(resp, raw)
        out = None
        if decoded is not None:
            try:
                out = rdg.build(decoded)
            except Exception:                      # the table must never take the caller down
                out = None
        if out is None:
            with self._lock:
                self._st["decode_errors"] += 1
            return None
        out.pop("events", None)                    # events come from take_events()
        out["schema"] = schema.hash
        out["stale"] = False
        return out

    def take_events(self):
        """Events since the last call, oldest first, at most MAX_EVENTS_PER_CALL, each
        {"source": "telemetry", "kind": "telemetry.ACTOR_ENTER_SEAT", "name": "ACTOR_ENTER_SEAT",
        "t": <epoch seconds>}. At most MAX_EVENTS_PER_SNAPSHOT per snapshot; the rest are
        counted in status()["events_dropped"]."""
        with self._lock:
            items = list(self._events_raw)
            self._events_raw.clear()
            compiled = self._compiled
        out = []
        if compiled is None:
            return out
        schema, etype = compiled[0], compiled[4]
        dropped = 0
        for t, raw in items:
            d = schema.decode_safe(etype, raw, EVENT_ITEMS) if etype else None
            if d is None:
                dropped += 1
                continue
            names = readings_mod.events_of({"events": d})
            total = d.get("events") if isinstance(d.get("events"), list) else []
            dropped += max(0, len(total) - len(names))
            for name in names:
                if len(out) >= MAX_EVENTS_PER_CALL:
                    dropped += 1
                    continue
                out.append({"source": SOURCE, "kind": "%s.%s" % (SOURCE, name), "name": name, "t": t})
        if dropped:
            with self._lock:
                self._st["events_dropped"] += dropped
        return out

    def status(self):
        """Counters and state for `status`: no reading value and no text the game sent, so
        nothing private and nothing the server chose."""
        with self._lock:
            st = dict(self._st)
            st["missing_readings"] = list(st["missing_readings"])
            st["connected"] = self._stream is not None
            st["age"] = round(self.clock() - self._raw_t, 3) if self._raw is not None else None
        return st

    # -- internals ---------------------------------------------------------

    def _set(self, **kw):
        with self._lock:
            self._st.update(kw)

    def _run(self, ev, old):
        stop, wake = ev
        if old is not None:
            old.join()                         # a previous run is still closing: wait here
        failing_since = None
        while not stop.is_set():
            try:
                kind = self._cycle(stop)
            except Exception as e:             # nothing may kill the thread
                kind = "fail"
                self._set(state="waiting", reason="internal error: %s" % type(e).__name__)
            now = self.clock()
            if kind == "ok":                   # snapshots came: the ladder starts again
                failing_since = None
                delay = retry_delay(0, self.retry_steps)
            elif kind == "fail":               # refused, silent, garbage: climb the ladder
                if failing_since is None:
                    failing_since = now
                delay = retry_delay(now - failing_since, self.retry_steps)
            elif kind == "idle":               # the game is not running
                failing_since = None
                delay = IDLE_S
            else:                              # "no-schema": nothing to try until it changes
                delay = self.retry_steps[-1][1]
            if stop.is_set():
                break
            wake.wait(delay)
            wake.clear()
        with self._lock:
            if self._run_ev is ev:
                self._st["state"] = "stopped"
                self._raw = None
                self._cache = None

    def _ensure_schema(self, running):
        """True when a schema with the stream method is loaded. The program file is scanned
        only while the game runs or once it has settled (not modified for `settle_s`)."""
        if not self._fixed_schema:
            try:
                key = proto.exe_key(self.exe_path) if self.exe_path else None
            except OSError:
                key = None
            stale = key is not None and key != self._schema_key
            if stale or (self._schema is None and key != self._schema_tried):
                allow = running is True or proto.settled(key, self.wall(), self.settle_s)
                self._set(state="loading", reason="")
                try:
                    schema, how = proto.load_schema(self.exe_path or "", self.cache_path, allow)
                except Exception:                  # load_schema does not raise; belt and braces
                    schema, how = None, "none"
                if how == "unsettled":
                    self._set(state="no-schema", reason="the program file changed; waiting for it to settle")
                    return False
                self._schema_tried = key           # a file with no descriptors is not rescanned
                self._schema, self._schema_key, self._schema_how = schema, key, how
                self._compiled = None
        if self._schema is None:
            self._set(state="no-schema", reason="no telemetry descriptors in the program file or cache")
            return False
        if self._compiled is None:
            resp = self._schema.stream_response_type()
            if resp is None:
                self._set(state="no-schema", reason="this build does not declare the stream method",
                          schema=self._schema.hash, schema_how=self._schema_how)
                return False
            rdg = readings_mod.Readings(self._schema, resp)
            ef = next((f for f in self._schema.messages[resp].values()
                       if f.name == readings_mod.EVENTS_PATH[0] and f.type == proto.T_MESSAGE
                       and not f.repeated), None)
            with self._lock:
                self._compiled = (self._schema, resp, rdg, ef.number if ef else None,
                                  ef.type_name if ef else None)
                self._st.update(schema=self._schema.hash, schema_how=self._schema_how,
                                missing_readings=list(rdg.missing))
        return True

    def _cycle(self, stop):
        """One attempt: "ok" (snapshots came), "fail", "idle" or "no-schema"."""
        running = None
        if self.game_running is not None:
            try:
                running = self.game_running()
            except Exception:
                running = None
            if running is False:
                self._set(state="idle", reason="game not running")
                return "idle"
        if not self._ensure_schema(running):
            return "no-schema"
        with self._lock:
            port = self._port or DEFAULT_PORT
        self._set(state="waiting", port=port)
        try:
            stream = h2.GrpcStream(port, connect_timeout=self.connect_timeout,
                                   read_timeout=self.read_timeout, connect=False)
        except (OSError, ValueError):
            self._set(reason="no socket")
            return "fail"
        with self._lock:
            if stop.is_set():
                stream.close()
                return "fail"
            self._connecting = stream
        try:
            stream.connect()
        except h2.SendRefused as e:
            with self._lock:
                self._connecting = None
                self._st["protocol_errors"] += 1
                self._st["reason"] = "refused to send: %s" % e.reason
            return "fail"
        except (OSError, h2.StreamClosed):
            with self._lock:
                self._connecting = None
                if not stop.is_set():
                    self._st["refusals"] += 1
                    self._st["reason"] = "no answer on port %d (refused or timed out)" % port
            return "fail"
        with self._lock:
            self._connecting = None
            if stop.is_set():
                stream.close()
                return "fail"
            self._stream = stream
            self._st["connects"] += 1
            self._st["reconnects"] = max(0, self._st["connects"] - 1)
            self._st["state"] = "connected"
            self._st["reason"] = ""
        got = 0
        reason = ""
        try:
            got, reason = self._read(stream, stop)
        finally:
            stream.close()
            with self._lock:
                self._stream = None
                self._raw = None                 # live readings only: gone with the stream
                self._cache = None
                self._st["state"] = "waiting"
                self._st["reason"] = reason
        return "ok" if got else "fail"

    def _read(self, stream, stop):
        """Pump the stream until it ends, goes silent, breaks a cap or is stopped.
        Returns (snapshots, reason)."""
        got = 0
        counted = 0
        last_msg = self.clock()
        last_check = last_msg
        ev_no = self._compiled[3]
        while not stop.is_set():
            try:
                msgs = stream.poll()
            except h2.ProtocolError as e:
                with self._lock:
                    self._st["protocol_errors"] += 1
                    self._st["bytes"] += stream.bytes_in - counted
                return got, "protocol error: %s" % e.reason
            except h2.StreamClosed as e:
                with self._lock:
                    self._st["bytes"] += stream.bytes_in - counted
                return got, "stopped" if stop.is_set() else e.reason
            now = self.clock()
            with self._lock:
                self._st["bytes"] += stream.bytes_in - counted
            counted = stream.bytes_in
            try:
                for msg in msgs:
                    if self._take(msg, ev_no, now):
                        got += 1
            except _Breach as e:
                with self._lock:
                    self._st["protocol_errors"] += 1
                return got, "protocol error: %s" % e
            if msgs:
                last_msg = now
            elif now - last_msg >= self.silent_s:
                return got, "silent for %d s" % self.silent_s
            if now - last_check >= IDLE_S and self.game_running is not None:
                last_check = now
                try:
                    if self.game_running() is False:
                        return got, "game not running"
                except Exception:
                    pass
        return got, "stopped"

    def _take(self, msg, ev_no, now):
        """Keep `msg` as the newest snapshot, and its events part if it has one. Walks at most
        MAX_TOP_FIELDS top-level fields; more, or an events part over MAX_EVENTS_BYTES, raises
        _Breach (the connection is dropped). A message malformed at the top level is counted
        and dropped."""
        events = None
        n = 0
        try:
            for no, wt, v in proto.iter_fields(msg):
                n += 1
                if n > MAX_TOP_FIELDS:
                    raise _Breach("too many top-level fields")
                if no == ev_no and wt == 2:
                    if v[1] - v[0] > MAX_EVENTS_BYTES:
                        raise _Breach("events part too large")
                    events = msg[v[0]:v[1]]
        except proto.DecodeError:
            with self._lock:
                self._st["decode_errors"] += 1
            return False
        with self._lock:
            self._raw = msg
            self._raw_t = now
            self._seq += 1
            self._st["snapshots"] += 1
            if self._st["state"] != "streaming":
                self._st["state"] = "streaming"
            if events is not None:
                if len(self._events_raw) == self._events_raw.maxlen:
                    self._st["events_dropped"] += 1
                self._events_raw.append((self.wall(), events))
                self._st["events"] += 1
        return True


# --------------------------------------------------------------------------- captures

def capture(seconds=60.0, port=DEFAULT_PORT, out_dir=None, schema=None, exe_path=None,
            cache_path=None, max_bytes=CAPTURE_MAX_BYTES, stop=None, read_timeout=READ_TIMEOUT_S):
    """Record every raw message of a running stream to a file in dashboard/data/telemetry/,
    for later study. Opens a connection of its own (two clients can read at once [ref: CSR]).
    Blocks for up to `seconds`; call it only while the game runs (without a `schema` it reads
    the program file, which is allowed then).

    `port` must be an int from 1 to 65535; leave it out for the default (2942, or pass the port
    the log announced). Anything else (True, None, "2942", 0) raises ValueError.

    Ends after `seconds`, at `max_bytes`, when `stop` (a threading.Event) is set, or when the
    stream ends. Never raises for a stream that is not there; returns {"path", "messages",
    "bytes", "seconds", "reason"} with path None when nothing was written. The file holds the
    user's balance, so it stays in data/ (git-ignored).

    The file: CAPTURE_MAGIC, a 4-byte length and a JSON header (UTC start, port, schema hash
    and the descriptor files themselves, so a capture can be decoded after the game is patched),
    then per message a 4-byte length, an 8-byte float of seconds since the start, and the bytes.
    Little-endian. From CSR: the time-and-length record of the raw fixtures CSR's tests read
    (tests/tlm_helpers.py lines 159-169, `read_raw`), the file named for its UTC start time and
    made unique when taken, and the `started_utc` header key (sc_telemetry.py lines 964-977,
    `Recorder._open_file`). The magic, the descriptors in the header and the -n suffix are this
    project's."""
    if not (isinstance(port, int) and not isinstance(port, bool) and 0 < port < 65536):
        raise ValueError("capture: port must be an int from 1 to 65535")
    if schema is None:
        schema, _ = proto.load_schema(exe_path or default_exe() or "", str(cache_path or SCHEMA_CACHE))
    result ={"path": None, "messages": 0, "bytes": 0, "seconds": 0.0, "reason": ""}
    try:
        stream = h2.GrpcStream(port, connect_timeout=CONNECT_TIMEOUT_S, read_timeout=read_timeout)
    except (OSError, h2.StreamClosed, ValueError):
        result["reason"] = "no answer on port %d (refused or timed out)" % port
        return result
    out_dir = str(out_dir or TELEMETRY_DIR)
    started = datetime.now(timezone.utc)
    path = os.path.join(out_dir, "capture-%s.sctlm" % started.strftime("%Y%m%d-%H%M%S"))
    header = {"format": 1, "source": SOURCE, "started_utc": started.replace(microsecond=0).isoformat(),
              "port": port, "path": STREAM_PATH,
              "schema": schema.hash if schema else "",
              "descriptors": [[n, base64.b64encode(b).decode("ascii")] for n, b in
                              (schema.blobs if schema else [])]}
    t0 = time.monotonic()
    fh = None
    try:
        os.makedirs(out_dir, exist_ok=True)
        n = 1
        while os.path.exists(path):
            path = os.path.join(out_dir, "capture-%s-%d.sctlm" % (started.strftime("%Y%m%d-%H%M%S"), n))
            n += 1
        head = json.dumps(header).encode("utf-8")
        head = CAPTURE_MAGIC + struct.pack("<I", len(head)) + head
        if len(head) > max_bytes:
            result["reason"] = "size limit"
            return result
        fh = open(path, "xb")
        fh.write(head)
        result["path"] = path
        written = fh.tell()
        while True:
            if stop is not None and stop.is_set():
                result["reason"] = "stopped"
                break
            if time.monotonic() - t0 >= seconds:
                result["reason"] = "time"
                break
            try:
                msgs = stream.poll()
            except h2.StreamClosed as e:
                result["reason"] = e.reason
                break
            for m in msgs:
                rec = struct.pack("<Id", len(m), time.monotonic() - t0) + m
                if written + len(rec) > max_bytes:
                    result["reason"] = "size limit"
                    break
                fh.write(rec)
                written += len(rec)
                result["messages"] += 1
            if result["reason"]:
                break
        result["bytes"] = written
    except OSError as e:
        result["reason"] = "write failed: %s" % type(e).__name__
    finally:
        stream.close()
        if fh is not None:
            fh.close()
        result["seconds"] = round(time.monotonic() - t0, 3)
    return result


def read_capture(capture_file, max_message=h2.MAX_MESSAGE):
    """(header, [(seconds, raw message)]) from a capture file. A cut-off last record is left
    out (From CSR: `read_recording`, sc_telemetry.py lines 653-671, keeps what came before a
    cut-off end, the idea only); a file that is not a capture raises ValueError."""
    with open(capture_file, "rb") as fh:
        data = fh.read()
    if not data.startswith(CAPTURE_MAGIC) or len(data) < len(CAPTURE_MAGIC) + 4:
        raise ValueError("not a telemetry capture")
    i = len(CAPTURE_MAGIC)
    hl = struct.unpack_from("<I", data, i)[0]
    i += 4
    if hl > len(data) - i or hl > 4 << 20:
        raise ValueError("damaged capture header")
    header = json.loads(data[i:i + hl].decode("utf-8"))
    i += hl
    out = []
    while i + 12 <= len(data):
        ln, t = struct.unpack_from("<Id", data, i)
        if ln > max_message or i + 12 + ln > len(data):
            break
        out.append((t, data[i + 12:i + 12 + ln]))
        i += 12 + ln
    return header, out


def schema_of_capture(header):
    """The Schema a capture was recorded with, from the descriptors in its header."""
    blobs = [(n, base64.b64decode(b64.encode("ascii"), validate=True))
             for n, b64 in header.get("descriptors", [])]
    return proto.Schema.from_blobs(blobs) if blobs else None
