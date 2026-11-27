"""Test helpers for the telemetry reader: synthetic descriptors, a minimal protobuf encoder, and
a fake HTTP/2 gRPC server that plays the game's side over a real socket on 127.0.0.1.

Copyright (c) 2026 archelium (support@archelium.com) for the parts marked "From CSR" below,
used under the MIT License (see dashboard/THIRD_PARTY_NOTICES): the varint encoder, the
descriptor builders, the fake server's one-plan-per-connection design, its response and trailer
blocks and `free_port` come from CSR's tests/tlm_helpers.py (commit ba6dad0). The generic
encoder `encode`, the server's failure modes and the request decoder are this project's own.

Everything here is synthetic. The message layout copies the field names and numbers that build
4.10.201's program file declares (read 2026-11-27), so the tests look like the real stream; the
values are invented. The few self-tests at the bottom check the helpers themselves.

**No test may connect to the real game's port.** The game can be running while the suite runs,
so importing this module wraps GrpcStream.connect with a check that refuses port 2942 in this
test process.
"""
import random
import socket
import struct
import threading
import time
import unittest

import scdash_testlib  # noqa: F401  (puts dashboard/ on sys.path)

from scdash import telemetry_h2 as h2
from scdash import telemetry_proto as proto

PKG = "sc.game.telemetry.v1"
GAME_PORT = 2942


def _guarded_connect(self, _real=h2.GrpcStream.connect):
    if self.port == GAME_PORT:
        raise AssertionError("a test tried to connect to the game's telemetry port")
    return _real(self)


if not getattr(h2.GrpcStream.connect, "_test_guard", False):
    _guarded_connect._test_guard = True
    h2.GrpcStream.connect = _guarded_connect

# --------------------------------------------------------------------------- protobuf encoding


# From CSR tests/tlm_helpers.py lines 16-27 (`enc_varint`), unchanged.
def vint(n):
    if n < 0:
        n += 1 << 64
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        if n:
            out.append(b | 0x80)
        else:
            out.append(b)
            return bytes(out)


# From CSR tests/tlm_helpers.py lines 30-37 (`enc_field`). Changed: split into key, ld and vi.
def key(no, wt):
    return vint((no << 3) | wt)


def ld(no, payload):
    if isinstance(payload, str):
        payload = payload.encode("utf-8")
    return key(no, 2) + vint(len(payload)) + payload


def vi(no, value):
    return key(no, 0) + vint(value)


# --------------------------------------------------------------------------- descriptors

T = proto


# From CSR tests/tlm_helpers.py lines 53-84 (`_field`, `_msg`, `_enum`, `_file`): descriptor
# builders. Changed: proto3 optional and oneofs, nested types, oneof declarations, dependencies,
# the syntax field, and a service builder (`sdesc`, after the service made inline in CSR's
# make_descriptor, lines 136-138).
def fdesc(name, number, ftype, type_name="", repeated=False, optional=None):
    b = ld(1, name) + vi(3, number) + vi(4, 3 if repeated else 1) + vi(5, ftype)
    if type_name:
        b += ld(6, "." + PKG + "." + type_name)
    if optional is not None:
        b += vi(9, optional) + vi(17, 1)
    return b


def mdesc(name, fields, nested=(), enums=(), oneofs=()):
    b = ld(1, name)
    for f in fields:
        b += ld(2, f)
    for n in nested:
        b += ld(3, n)
    for e in enums:
        b += ld(4, e)
    for o in oneofs:
        b += ld(8, ld(1, o))
    return b


def edesc(name, values):
    b = ld(1, name)
    for vname, num in values:
        b += ld(2, ld(1, vname) + vi(2, num))
    return b


def sdesc(name, methods):
    b = ld(1, name)
    for mname, inp, out, server_streaming in methods:
        m = ld(1, mname) + ld(2, "." + PKG + "." + inp) + ld(3, "." + PKG + "." + out)
        if server_streaming:
            m += vi(6, 1)
        b += ld(2, m)
    return b


def file_desc(name, messages=(), enums=(), services=(), deps=()):
    b = ld(1, name) + ld(2, PKG)
    for d in deps:
        b += ld(3, d)
    for m in messages:
        b += ld(4, m)
    for e in enums:
        b += ld(5, e)
    for s in services:
        b += ld(6, s)
    return b + ld(12, "proto3")


def _enum(name, prefix, values):
    return edesc(name, [(prefix + v, i) for i, v in enumerate(values)])


def types_proto(with_shields=False):
    """A subset of build 4.10.201's types.proto, same names and numbers; `with_shields` adds
    a 5.0-style field (VehicleState 10 shields) for the "new patch" tests."""
    F = fdesc
    msgs = [
        mdesc("Availability", [F("enabled", 1, T.T_BOOL), F("active", 2, T.T_BOOL)]),
        mdesc("Gauge", [F("current", 1, T.T_FLOAT), F("max", 2, T.T_FLOAT)]),
        mdesc("VehicleFlightSettings", [
            F("ifcs_coupled", 1, T.T_MESSAGE, "Availability"),
            F("ifcs_esp", 2, T.T_MESSAGE, "Availability"),
            F("ifcs_g_safe", 4, T.T_MESSAGE, "Availability"),
            F("ifcs_speed_limiter", 7, T.T_MESSAGE, "Availability"),
            F("flight_light_amplification", 19, T.T_BOOL)]),
        mdesc("VehicleFlightState", [
            F("is_landed", 1, T.T_BOOL),
            F("gear", 2, T.T_ENUM, "VehicleComponentDeploymentState", optional=0),
            F("vtol", 3, T.T_ENUM, "VehicleComponentDeploymentState", optional=1)],
            oneofs=("_gear", "_vtol")),
        mdesc("VehicleFlight", [F("state", 1, T.T_MESSAGE, "VehicleFlightState"),
                                F("settings", 2, T.T_MESSAGE, "VehicleFlightSettings"),
                                F("instruments", 3, T.T_MESSAGE, "VehicleFlightInstruments")]),
        mdesc("VehicleFlightInstruments", [
            F("speed", 1, T.T_FLOAT), F("hydrogen_fuel", 2, T.T_FLOAT),
            F("quantum_fuel", 3, T.T_FLOAT),
            F("g_meter", 4, T.T_MESSAGE, "Gauge", optional=0),
            F("altitude", 6, T.T_FLOAT), F("heading", 10, T.T_FLOAT)], oneofs=("_g_meter",)),
        mdesc("VehiclePowerState", [F(n, i + 1, T.T_BOOL) for i, n in enumerate(
            ("powerplants", "engines", "weapons", "coolers", "life_support",
             "gravity_generators", "sensors", "shield_generators", "shield_emitters"))]),
        mdesc("VehicleAnnunciator",
              [F(n, i + 1, T.T_ENUM, "VehicleAnnunciator.AnnunciatorState") for i, n in enumerate(
                  ("pwr", "wpn", "thr", "shld", "cool", "qdrv", "radr", "prox", "hit", "misl"))],
              enums=[_enum("AnnunciatorState", "ANNUNCIATOR_STATE_",
                           ("UNSPECIFIED", "NOMINAL", "OFF", "MINOR_FLASHING", "MINOR_ON",
                            "MAJOR_FLASHING", "MAJOR_ON"))]),
        mdesc("VehicleState", [
            F("name", 1, T.T_STRING), F("class_name", 2, T.T_STRING),
            F("manufacturer", 3, T.T_STRING), F("type", 4, T.T_ENUM, "VehicleType"),
            F("lights_enabled", 5, T.T_BOOL),
            F("annunciators", 7, T.T_MESSAGE, "VehicleAnnunciator", optional=0),
            F("flight", 8, T.T_MESSAGE, "VehicleFlight", optional=1),
            F("power", 9, T.T_MESSAGE, "VehiclePowerState", optional=2)]
            + ([F("shields", 10, T.T_MESSAGE, "VehicleShields", optional=3)] if with_shields else []),
            oneofs=("_annunciators", "_flight", "_power") + (("_shields",) if with_shields else ())),
        mdesc("VehicleFrame", [F("state", 2, T.T_MESSAGE, "VehicleState")]),
        mdesc("Countermeasures", [
            F("type", 1, T.T_ENUM, "Countermeasures.CountermeasureType"),
            F("amount", 2, T.T_UINT32)],
            enums=[_enum("CountermeasureType", "COUNTERMEASURE_TYPE_", ("UNSPECIFIED", "DECOY", "NOISE"))]),
        mdesc("WeaponsFrame", [F("preset_index", 2, T.T_UINT32), F("preset_name", 3, T.T_STRING),
                               F("countermeasures", 5, T.T_MESSAGE, "Countermeasures", repeated=True)]),
        mdesc("GameEvent", [F("type", 1, T.T_ENUM, "GameEvent.GameEventType")],
              enums=[_enum("GameEventType", "GAME_EVENT_TYPE_",
                           ("UNSPECIFIED", "ACTOR_SPAWN", "ACTOR_DEAD", "ACTOR_ENTER_SEAT",
                            "ACTOR_LEAVE_SEAT", "ACTOR_RESPAWN", "ACTOR_DOWNED"))]),
        mdesc("EventsFrame", [F("events", 1, T.T_MESSAGE, "GameEvent", repeated=True)]),
        mdesc("ActorState", [F("locomotion", 1, T.T_ENUM, "ActorLocomotionState"),
                             F("seat_name", 3, T.T_STRING), F("uec_balance", 4, T.T_INT64)]),
        mdesc("ActorVitals", [F("health", 1, T.T_MESSAGE, "Gauge"),
                              F("readings", 11, T.T_FLOAT, repeated=True)]),
        mdesc("ActorFrame", [F("vitals", 1, T.T_MESSAGE, "ActorVitals"),
                             F("state", 2, T.T_MESSAGE, "ActorState")]),
    ]
    if with_shields:
        msgs.append(mdesc("VehicleShields", [F("level", 1, T.T_FLOAT),
                                             F("faces", 2, T.T_FLOAT, repeated=True)]))
    enums = [
        _enum("VehicleComponentDeploymentState", "VEHICLE_COMPONENT_DEPLOYMENT_STATE_",
              ("UNSPECIFIED", "RETRACTED", "DEPLOYING", "DEPLOYED", "RETRACTING")),
        _enum("VehicleType", "VEHICLE_TYPE_", ("UNSPECIFIED", "SPACESHIP", "GROUND", "GRAVLEV", "BOAT")),
        _enum("ActorLocomotionState", "ACTOR_LOCOMOTION_STATE_", ("UNSPECIFIED", "ON_FOOT", "EVA", "SEATED")),
    ]
    return file_desc("sc/game/telemetry/v1/types.proto", msgs, enums)


def api_proto(other_methods=False, streaming=True):
    """api.proto. `other_methods` adds the two action methods CSR's notes give for a 5.0 test
    build (TriggerGameAction, ListTriggerableActions), as "a server that offers other methods"."""
    F = fdesc
    msgs = [mdesc("TelemetryStreamRequest", []),
            mdesc("TelemetryStreamResponse", [
                F("vehicle", 3, T.T_MESSAGE, "VehicleFrame"),
                F("weapons", 4, T.T_MESSAGE, "WeaponsFrame"),
                F("events", 5, T.T_MESSAGE, "EventsFrame"),
                F("actor", 6, T.T_MESSAGE, "ActorFrame")])]
    methods = [("TelemetryStream", "TelemetryStreamRequest", "TelemetryStreamResponse", streaming)]
    if other_methods:
        msgs += [mdesc("TriggerGameActionRequest", [F("action_name", 1, T.T_STRING)]),
                 mdesc("TriggerGameActionResponse", [F("message", 2, T.T_STRING)])]
        methods += [("TriggerGameAction", "TriggerGameActionRequest", "TriggerGameActionResponse", False),
                    ("ListTriggerableActions", "TelemetryStreamRequest", "TriggerGameActionResponse", False)]
    return file_desc("sc/game/telemetry/v1/api.proto", msgs,
                     services=[sdesc("GameTelemetryService", methods)],
                     deps=["sc/game/telemetry/v1/types.proto"])


def blobs(with_shields=False, other_methods=False, streaming=True):
    return [("sc/game/telemetry/v1/api.proto", api_proto(other_methods, streaming)),
            ("sc/game/telemetry/v1/types.proto", types_proto(with_shields))]


def make_schema(**kw):
    return proto.Schema.from_blobs(blobs(**kw))


RESPONSE = PKG + ".TelemetryStreamResponse"


def encode(schema, type_name, obj):
    """The protobuf bytes of `obj` (a dict by field name) as message `type_name`."""
    table = {f.name: f for f in schema.messages[type_name].values()}
    out = bytearray()
    for name, value in obj.items():
        f = table[name]
        values = value if f.repeated else [value]
        if f.repeated and f.type not in proto.LEN_TYPES:
            packed = b"".join(_scalar(schema, f, v) for v in values)
            out += key(f.number, 2) + vint(len(packed)) + packed
            continue
        for v in values:
            if f.type == proto.T_MESSAGE:
                out += ld(f.number, encode(schema, f.type_name, v))
            elif f.type in (proto.T_STRING, proto.T_BYTES):
                out += ld(f.number, v)
            elif f.type in proto.FIXED32_TYPES:
                out += key(f.number, 5) + _scalar(schema, f, v)
            elif f.type in proto.FIXED64_TYPES:
                out += key(f.number, 1) + _scalar(schema, f, v)
            else:
                out += key(f.number, 0) + _scalar(schema, f, v)
    return bytes(out)


def _scalar(schema, f, v):
    if f.type == proto.T_FLOAT:
        return struct.pack("<f", v)
    if f.type == proto.T_DOUBLE:
        return struct.pack("<d", v)
    if f.type == proto.T_ENUM and isinstance(v, str):
        v = next(k for k, n in schema.enums[f.type_name].items() if n == v)
    if f.type == proto.T_BOOL:
        v = int(bool(v))
    return vint(v)


def snapshot(schema, n=0, balance=123456, event=None, seated=True, extra_vehicle=None):
    """A synthetic snapshot like the stream's: invented values that change with `n`. The idea
    of a frame builder from CSR tests/tlm_helpers.py lines 227-234 (`actor_frame`); built here
    through the generic encoder."""
    obj = {"actor": {"state": {"locomotion": "SEATED" if seated else "ON_FOOT",
                               "uec_balance": balance},
                     "vitals": {"health": {"current": 100.0, "max": 100.0}}}}
    if seated:
        vehicle = {
            "name": "TEST_Ship_1000", "class_name": "TEST_Ship", "type": "SPACESHIP",
            "annunciators": {"pwr": "NOMINAL", "qdrv": "OFF", "prox": "MAJOR_ON"},
            "flight": {"state": {"gear": "RETRACTED", "vtol": "DEPLOYED"},
                       "settings": {"ifcs_coupled": {"enabled": True, "active": n % 2 == 0},
                                    "ifcs_g_safe": {"enabled": True}},
                       "instruments": {"speed": 100.0 + n, "hydrogen_fuel": 0.75,
                                       "g_meter": {"current": 1.5, "max": 9.0},
                                       "altitude": 3.4028234663852886e38, "heading": 90.0}},
            "power": {"powerplants": True, "engines": True, "shield_generators": True}}
        vehicle.update(extra_vehicle or {})
        obj["vehicle"] = {"state": vehicle}
        obj["weapons"] = {"preset_name": "Default",
                          "countermeasures": [{"type": "DECOY", "amount": 24},
                                              {"type": "NOISE", "amount": 6}]}
    if event:
        obj["events"] = {"events": [{"type": event}]}
    return encode(schema, RESPONSE, obj)


# --------------------------------------------------------------------------- the fake server

# A few HPACK static-table entries [RFC 7541 Appendix A], enough to read the client's request.
STATIC = {1: (":authority", ""), 2: (":method", "GET"), 3: (":method", "POST"), 4: (":path", "/"),
          5: (":path", "/index.html"), 6: (":scheme", "http"), 7: (":scheme", "https"),
          8: (":status", "200"), 31: ("content-type", ""), 58: ("user-agent", "")}
PATHS_SEEN = []          # every :path any fake server was ever asked for, across all tests


def hpack_decode(block):
    """[(name, value)] of a header block that uses no Huffman coding and no dynamic table."""
    out, i = [], 0

    def integer(prefix):
        nonlocal i
        cap = (1 << prefix) - 1
        v = block[i] & cap
        i += 1
        if v < cap:
            return v
        m = 0
        while True:
            b = block[i]
            i += 1
            v += (b & 0x7F) << m
            m += 7
            if b < 0x80:
                return v

    def string():
        nonlocal i
        huff = block[i] & 0x80
        ln = integer(7)
        s = block[i:i + ln]
        i += ln
        return "<huffman>" if huff else s.decode("ascii", "replace")

    while i < len(block):
        b = block[i]
        if b & 0x80:
            out.append(STATIC.get(integer(7), ("<dynamic>", "")))
            continue
        prefix = 6 if b & 0x40 else 4
        idx = integer(prefix)
        name = STATIC.get(idx, ("<dynamic>", ""))[0] if idx else string()
        out.append((name, string()))
    return out


# From CSR sc_telemetry.py lines 330-331 (`_frame`), unchanged, without the length check that
# telemetry_h2.frame has (the fake must be able to send oversized frames).
def frame(ftype, flags, sid, payload=b""):
    return struct.pack(">I", len(payload))[1:] + bytes([ftype, flags]) + struct.pack(">I", sid) + payload


# From CSR tests/tlm_helpers.py lines 214 and 298: a gRPC message's 5-byte prefix.
def grpc_message(msg):
    return b"\x00" + struct.pack(">I", len(msg)) + msg


def data_frames(msg):
    """One gRPC message as DATA frames of at most 16 KB, as an HTTP/2 server must send it."""
    g = grpc_message(msg)
    return b"".join(frame(h2.DATA, 0, 1, g[i:i + h2.MAX_FRAME]) for i in range(0, len(g), h2.MAX_FRAME))


# From CSR tests/tlm_helpers.py line 212: the response headers start with b"\x88" (:status 200).
# Changed: content-type added.
RESPONSE_HEADERS = b"\x88" + b"\x0f\x10" + bytes([16]) + b"application/grpc"
# From CSR tests/tlm_helpers.py lines 218-219: a trailer block with a plain grpc-status.
# Changed: status 12 (unimplemented), and a grpc-message of text the client must not keep.
TRAILERS = (b"\x00" + bytes([11]) + b"grpc-status" + bytes([2]) + b"12"
            + b"\x00" + bytes([12]) + b"grpc-message" + bytes([40]) + b"EVIL TEXT FROM THE SERVER " + b"x" * 14)


class FakeServer:
    """The game's side of the stream on 127.0.0.1:<free port>. Each accepted connection plays
    the next mode in `modes` (the last one repeats). From CSR tests/tlm_helpers.py lines 245-311
    (`StreamServer`): one plan per connection with the last repeating, the accept loop with a
    0.2 s timeout and a thread per connection. Changed: the modes below, the request read and
    recorded, the client's frames drained and recorded, shutdown in order.

    blast    headers, then `messages` (cycled) back to back, as fast as the socket takes them

    normal   headers, then `messages` (cycled) at `rate` a second until closed
    cut      headers, one message, half of the next, then the socket is closed
    garbage  random bytes after the request
    oversized  a gRPC message whose length is one over the client's cap
    silent   headers, then nothing (the socket stays open)
    drip     headers, then a message one byte at a time, too slowly ever to finish
    trickle  headers, then a large message one byte per send, as fast as it goes
    trailers a trailers-only answer (grpc-status 12, unimplemented)
    pingflood  a burst of pings
    goaway   a GOAWAY frame
    bigframe a frame longer than 16 KB
    push     a PUSH_PROMISE frame
    nodheaders  DATA before any HEADERS
    compressed  a gRPC message flagged as compressed
    refuse   the connection is closed at once
    """

    def __init__(self, messages=(), rate=18.0, modes=("normal",), max_message=h2.MAX_MESSAGE,
                 record_global=True):
        self.record_global = record_global
        self.messages = list(messages)
        self.rate = rate
        self.modes = list(modes)
        self.max_message = max_message
        self.paths = []
        self.client_frames = []          # (connection index, frame type, flags, stream id)
        self.connections = 0
        self.sent = 0
        self._stop = threading.Event()
        self._threads = []
        self._conns = []
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(8)
        self.sock.settimeout(0.2)
        self.port = self.sock.getsockname()[1]
        self._accept = threading.Thread(target=self._accept_loop, daemon=True)
        self._accept.start()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def close(self):
        self._stop.set()
        try:
            self.sock.close()            # no new connections first, then end the open ones
        except OSError:
            pass
        self._accept.join(2)
        for c in list(self._conns):
            try:
                c.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                c.close()
            except OSError:
                pass
        for t in self._threads:
            t.join(2)

    def _accept_loop(self):
        while not self._stop.is_set():
            try:
                conn, _ = self.sock.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            idx = self.connections
            self.connections += 1
            mode = self.modes[min(idx, len(self.modes) - 1)]
            self._conns.append(conn)
            t = threading.Thread(target=self._serve, args=(conn, idx, mode), daemon=True)
            self._threads.append(t)
            t.start()

    def _recv_exact(self, conn, n):
        buf = b""
        while len(buf) < n:
            chunk = conn.recv(n - len(buf))
            if not chunk:
                raise ConnectionError("client closed")
            buf += chunk
        return buf

    def _read_frame(self, conn, idx):
        hdr = self._recv_exact(conn, 9)
        ln = int.from_bytes(hdr[:3], "big")
        payload = self._recv_exact(conn, ln) if ln else b""
        sid = int.from_bytes(hdr[5:9], "big") & 0x7FFFFFFF
        self.client_frames.append((idx, hdr[3], hdr[4], sid))
        return hdr[3], hdr[4], sid, payload

    def _drain(self, conn, idx):
        try:
            while not self._stop.is_set():
                self._read_frame(conn, idx)
        except (OSError, ConnectionError):
            pass

    def _serve(self, conn, idx, mode):
        try:
            conn.settimeout(5)
            if mode == "refuse":
                conn.close()
                return
            if self._recv_exact(conn, 24) != h2.PREFACE:
                conn.close()
                return
            done = False
            while not done:
                ftype, flags, sid, payload = self._read_frame(conn, idx)
                if ftype == h2.HEADERS:
                    for name, value in hpack_decode(payload):
                        if name == ":path":
                            self.paths.append(value)
                            if self.record_global:
                                PATHS_SEEN.append(value)
                if ftype == h2.DATA and flags & h2.F_END_STREAM:
                    done = True
            conn.settimeout(None)
            threading.Thread(target=self._drain, args=(conn, idx), daemon=True).start()
            conn.sendall(frame(h2.SETTINGS, 0, 0) + frame(h2.SETTINGS, h2.F_ACK, 0))
            getattr(self, "_mode_" + mode)(conn)
        except (OSError, ConnectionError):
            pass
        finally:
            if mode not in ("silent",):
                try:
                    conn.close()
                except OSError:
                    pass

    def _headers(self, conn):
        conn.sendall(frame(h2.HEADERS, h2.F_END_HEADERS, 1, RESPONSE_HEADERS))

    def _mode_normal(self, conn):
        self._headers(conn)
        gap = 1.0 / self.rate
        nxt = time.monotonic()
        k = 0
        while not self._stop.is_set() and self.messages:
            m = self.messages[k % len(self.messages)]
            conn.sendall(data_frames(m))
            self.sent += 1
            k += 1
            nxt += gap
            delay = nxt - time.monotonic()
            if delay > 0:
                self._stop.wait(delay)

    def _mode_cut(self, conn):
        self._headers(conn)
        conn.sendall(frame(h2.DATA, 0, 1, grpc_message(self.messages[0])))
        self.sent += 1
        whole = grpc_message(self.messages[0])
        conn.sendall(frame(h2.DATA, 0, 1, whole[:len(whole) // 2]))
        time.sleep(0.1)
        conn.shutdown(socket.SHUT_RDWR)

    def _mode_garbage(self, conn):
        rnd = random.Random(7)
        conn.sendall(bytes(rnd.getrandbits(8) for _ in range(4096)))
        time.sleep(0.3)

    def _mode_oversized(self, conn):
        self._headers(conn)
        conn.sendall(frame(h2.DATA, 0, 1, b"\x00" + struct.pack(">I", self.max_message + 1) + b"x" * 100))
        time.sleep(0.5)

    def _mode_silent(self, conn):
        self._headers(conn)
        self._stop.wait(30)

    def _mode_drip(self, conn):
        self._headers(conn)
        data = frame(h2.DATA, 0, 1, grpc_message(self.messages[0]))
        for b in data[:-1]:
            if self._stop.is_set():
                return
            conn.sendall(bytes([b]))
            self._stop.wait(0.15)

    def _mode_trickle(self, conn):
        # Valid 16 KB DATA frames of one endless gRPC message, sent a byte at a time.
        self._headers(conn)
        conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        data = frame(h2.DATA, 0, 1, bytes(1) + struct.pack(">I", 200_000) + bytes(15_995))
        more = frame(h2.DATA, 0, 1, bytes(16_000))
        k = 0
        while not self._stop.is_set():
            conn.sendall(data[k:k + 1])
            k += 1
            if k == len(data):
                data, k = more, 0

    def _mode_trailers(self, conn):
        conn.sendall(frame(h2.HEADERS, h2.F_END_HEADERS | h2.F_END_STREAM, 1, TRAILERS))
        time.sleep(0.3)

    def _mode_blast(self, conn):
        self._headers(conn)
        data = b"".join(data_frames(m) for m in self.messages)
        while not self._stop.is_set():
            conn.sendall(data)
            self.sent += len(self.messages)

    def _mode_pingflood(self, conn):
        conn.sendall(b"".join(frame(h2.PING, 0, 0, struct.pack(">Q", i)) for i in range(200)))
        time.sleep(0.5)

    def _mode_goaway(self, conn):
        self._headers(conn)
        conn.sendall(frame(h2.GOAWAY, 0, 0, struct.pack(">II", 1, 0)))
        time.sleep(0.3)

    def _mode_bigframe(self, conn):
        self._headers(conn)
        conn.sendall(struct.pack(">I", 20000)[1:] + bytes([h2.DATA, 0]) + struct.pack(">I", 1) + b"\0" * 20000)
        time.sleep(0.3)

    def _mode_push(self, conn):
        self._headers(conn)
        conn.sendall(frame(h2.PUSH_PROMISE, h2.F_END_HEADERS, 1, struct.pack(">I", 2) + b"\x88"))
        time.sleep(0.3)

    def _mode_nodheaders(self, conn):
        conn.sendall(frame(h2.DATA, 0, 1, grpc_message(self.messages[0])))
        time.sleep(0.3)

    def _mode_compressed(self, conn):
        self._headers(conn)
        m = self.messages[0]
        conn.sendall(frame(h2.DATA, 0, 1, b"\x01" + struct.pack(">I", len(m)) + m))
        time.sleep(0.3)


# From CSR tests/tlm_helpers.py lines 237-242 (`free_port`). Changed: a docstring.
def free_port():
    """A port with nothing listening on it (bound, then closed)."""
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


# --------------------------------------------------------------------------- self-tests

class HelperTest(unittest.TestCase):
    def test_encoder_round_trips_through_the_decoder(self):
        schema = make_schema()
        msg = snapshot(schema, n=4, event="ACTOR_ENTER_SEAT")
        d = schema.decode(RESPONSE, msg)
        self.assertEqual(d["vehicle"]["state"]["class_name"], "TEST_Ship")
        self.assertEqual(d["events"]["events"], [{"type": "ACTOR_ENTER_SEAT"}])
        self.assertEqual(d["actor"]["state"]["uec_balance"], 123456)

    def test_hpack_decoder_reads_the_clients_request(self):
        names = dict(hpack_decode(h2.request_headers(2942)))
        self.assertEqual(names[":path"], h2.STREAM_PATH)
        self.assertEqual(names[":method"], "POST")
        self.assertEqual(names[":authority"], "127.0.0.1:2942")


if __name__ == "__main__":
    unittest.main()
