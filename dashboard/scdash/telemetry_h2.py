"""A minimal gRPC client over cleartext HTTP/2 that can call one method: the game's read-only
telemetry stream (PLAN §8, §12 stage 6).

Copyright (c) 2026 archelium (support@archelium.com) for the parts marked "From CSR" below,
used under the MIT License (see dashboard/THIRD_PARTY_NOTICES): the frame and HPACK helpers and
the stream client come from CSR's sc_telemetry.py (commit ba6dad0). Everything else in this
file is this project's own.

Rules this file keeps, and why (PLAN §8):

- **One method, forever, enforced where the bytes leave.** The request's header block is built
  once, at import, from STREAM_PATH. Every byte this client sends goes through
  `GrpcStream._write()`, which parses what it is given and refuses any frame this client has no
  business sending: a HEADERS frame that is not exactly that block, a second request, any DATA
  but the one empty request. The socket is private (`__sock`), no function here takes a path, a
  method or a host, and only `telemetry.py` imports this module (tests check all three).
- **Loopback only.** It connects to 127.0.0.1 and nowhere else; only the port can vary.
- **Every byte is untrusted, and the caps are sized to the real stream**, about 700 bytes per
  snapshot, 15 to 18 snapshots and about 13 KB a second [ref: CSR's captures, decoded here]:
  frames over 16 KB, header blocks over 16 KB, messages over 32 KB, more than 512 KB, 100
  messages, 500 frames or 500 socket reads in one second, a flood of pings or settings,
  compressed messages and server push all end the connection with a ProtocolError. Nothing here
  waits without a timeout. Text the server chose never leaves this file: only numbers do
  (a grpc-status, a GOAWAY or reset code).

How the game's side behaves is second-hand: the game runs gRPC C++ 1.49.2 (its include path is
in the program file [game]), and other tools report it streams 14 to 18 snapshots a second
[ref: CSR's docs/telemetry/NOTES.md]. Nothing here has met the real server.
"""
import re
import socket
import struct
import threading
import time

# The one request path [game: the program file holds exactly this string, and its descriptor
# declares TelemetryStream as the service's only method in build 4.10.201]. Never add another.
#
# Why this matters in this build already, not only in 5.0 [game, read 2026-11-27, first found by
# the stage 6 reviewer]: the program file's string table holds 12 other local gRPC paths besides
# this one, 11 methods of /sc.game.editor.vqlengine.v1.VqlEngineService (BrowseTagPath,
# CompleteVQL, DescribeDomains, FindLocations, GetManual, GetRecord, GetStatus, GetTagName, Query,
# SearchTags, Validate) and /sc.game.editor.mightybridge.v1.MightyBridgeService/MightyStream
# (with editor pause and resume commands nearby). Whether the game serves any of them on the
# telemetry port is unknown. 5.0 test builds add methods that make the game act [ref: CSR's
# 5.0 schema notes]. This client can ask for nothing but the stream.
STREAM_PATH = "/sc.game.telemetry.v1.GameTelemetryService/TelemetryStream"

LOOPBACK = "127.0.0.1"
DEFAULT_PORT = 2942              # [game] the program file's default for grpc.client.server.address

MAX_FRAME = 16384                # HTTP/2's default SETTINGS_MAX_FRAME_SIZE; advertised below
MAX_HEADER_BLOCK = 16 * 1024     # a response header block is about 100 bytes
MAX_MESSAGE = 32 * 1024          # 45 times the 700-byte snapshot, room for 5.0's additions
WINDOW = 256 * 1024              # flow-control window offered to the game, per stream and connection
RECV_SIZE = 65536
MAX_BYTES_PER_S = 512 * 1024     # 40 times the 13 KB a second expected
MAX_MESSAGES_PER_S = 100         # 5 times the 20 a second the default 50 ms interval gives
MAX_FRAMES_PER_S = 500
MAX_READS_PER_S = 500            # socket reads: a server trickling bytes cannot spin the reader
MAX_PINGS_PER_S = 10
MAX_SETTINGS_PER_S = 10
USER_AGENT = "scdash-telemetry"

# From CSR sc_telemetry.py lines 325-327: frame types and flags [RFC 9113]. Changed: the
# CONTINUATION, PRIORITY and PUSH_PROMISE types are named too, BIG_WINDOW is replaced by WINDOW.
DATA, HEADERS, PRIORITY, RST_STREAM, SETTINGS, PUSH_PROMISE = 0, 1, 2, 3, 4, 5
PING, GOAWAY, WINDOW_UPDATE, CONTINUATION = 6, 7, 8, 9
F_END_STREAM, F_ACK, F_END_HEADERS, F_PADDED, F_PRIORITY = 0x1, 0x1, 0x4, 0x8, 0x20
S_ENABLE_PUSH, S_INITIAL_WINDOW_SIZE, S_MAX_FRAME_SIZE, S_MAX_HEADER_LIST_SIZE = 2, 4, 5, 6
PREFACE = b"PRI * HTTP/2.0\r\n\r\nSM\r\n\r\n"

# Rate counters, one per kind.
_R_FRAMES, _R_BYTES, _R_PINGS, _R_SETTINGS, _R_READS, _R_MESSAGES = range(6)
_RATE_CAPS = (MAX_FRAMES_PER_S, MAX_BYTES_PER_S, MAX_PINGS_PER_S, MAX_SETTINGS_PER_S,
              MAX_READS_PER_S, MAX_MESSAGES_PER_S)


class StreamClosed(Exception):
    """The stream is over: the game closed it, reset it, or the socket failed. `reason` is a
    short text of this file's own words and numbers, never text the server sent."""

    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


class ProtocolError(StreamClosed):
    """The other side broke HTTP/2 or gRPC, or sent more than this client accepts."""


class SendRefused(StreamClosed):
    """This program tried to send something other than the one request. Never the server's
    doing: it means a code path that must not exist."""


# From CSR sc_telemetry.py lines 330-331 (`_frame`). Changed: the length is checked.
def frame(ftype, flags, stream, payload=b""):
    """One HTTP/2 frame: 3-byte length, type, flags, 4-byte stream id, payload."""
    if len(payload) > MAX_FRAME:
        raise ValueError("frame too large")
    return struct.pack(">I", len(payload))[1:] + bytes([ftype, flags]) + struct.pack(">I", stream) + payload


# From CSR sc_telemetry.py lines 334-344 (`_hpack_int`), unchanged: an HPACK integer [RFC 7541].
def hpack_int(value, prefix_bits, first):
    cap = (1 << prefix_bits) - 1
    if value < cap:
        return bytes([first | value])
    out = [first | cap]
    value -= cap
    while value >= 128:
        out.append((value & 0x7F) | 0x80)
        value >>= 7
    out.append(value)
    return bytes(out)


# From CSR sc_telemetry.py lines 347-349 (`_hpack_str`), unchanged: a literal string, no Huffman.
def hpack_str(s):
    b = s.encode("ascii")
    return hpack_int(len(b), 7, 0) + b


# From CSR sc_telemetry.py lines 352-360 (`_request_headers`). Changed: split into two blocks
# built once, at import, from the constants: the path part and the rest. Only the authority
# between them depends on the port, an int. No compression is asked for, and the user agent
# names this project. Literal fields without indexing, no Huffman, static-table names.
_PATH_BLOCK = bytes([0x83, 0x86]) + hpack_int(4, 4, 0) + hpack_str(STREAM_PATH)   # POST, http, :path
_TAIL_BLOCK = (hpack_int(31, 4, 0) + hpack_str("application/grpc")
               + b"".join(b"\x00" + hpack_str(k) + hpack_str(v) for k, v in (
                   ("te", "trailers"), ("grpc-accept-encoding", "identity"),
                   ("user-agent", USER_AGENT))))
_EMPTY_REQUEST = b"\x00\x00\x00\x00\x00"       # no compression, length 0
_SETTINGS = b"".join(struct.pack(">HI", k, v) for k, v in (
    (S_ENABLE_PUSH, 0), (S_INITIAL_WINDOW_SIZE, WINDOW),
    (S_MAX_FRAME_SIZE, MAX_FRAME), (S_MAX_HEADER_LIST_SIZE, MAX_HEADER_BLOCK)))


def _authority(port):
    if not isinstance(port, int) or isinstance(port, bool) or not 0 < port < 65536:
        raise ValueError("bad port")
    return hpack_int(1, 4, 0) + hpack_str("%s:%d" % (LOOPBACK, port))


def request_headers(port):
    """The request's header block for 127.0.0.1:<port>."""
    return _PATH_BLOCK + _authority(port) + _TAIL_BLOCK


def path_in_block(raw):
    """The :path of a header block in this client's own format, or None."""
    if not raw.startswith(b"\x83\x86\x04") or len(raw) < 4 or raw[3] & 0x80:
        return None
    ln, i = raw[3] & 0x7F, 4
    if ln == 0x7F:                   # a multi-byte HPACK length
        ln, shift = 0x7F, 0
        while i < len(raw):
            b = raw[i]
            i += 1
            ln += (b & 0x7F) << shift
            shift += 7
            if b < 0x80:
                break
    return bytes(raw[i:i + ln]).decode("ascii", "replace")


_STATUS_RE = re.compile(rb"grpc-status[\x01\x02](\d{1,2})")


def _grpc_status(raw):
    """The grpc-status code of a trailer block when it is sent as a plain literal, else None.
    Only the number is taken: the rest of the block is the server's own text."""
    m = _STATUS_RE.search(raw)
    return int(m.group(1)) if m else None


class GrpcStream:
    """One call of the telemetry stream on 127.0.0.1:<port>. `poll()` waits up to
    `read_timeout` for bytes and returns the complete gRPC messages that arrived.

    From CSR sc_telemetry.py lines 363-450 (`GrpcStream`). Changed: the host is fixed to
    127.0.0.1 and the request to the block built from STREAM_PATH; every send passes the
    `_write` check; the socket is private and always has a timeout; connecting can be split from
    construction so another thread can end it; the generator `messages()` became `poll()`,
    which returns a list; buffers are bytearrays bounded by the frame and message caps; a
    256 KB window is offered and topped up as data is read, instead of 2 GB; HEADERS and
    CONTINUATION blocks are tracked and capped; DATA before the response headers, push promises,
    bad padding, bad SETTINGS and PING sizes, and floods are protocol errors; the end of the
    stream is reported once, after the messages that came with it."""

    def __init__(self, port, connect_timeout=2.0, read_timeout=1.0, max_message=MAX_MESSAGE,
                 connect=True):
        """With connect=False only the socket is made; call connect() next. That lets another
        thread close() a stream that is still connecting: on Windows a refused connection to
        a loopback port takes about 2 s [seen 2026-11-27], and close() ends it at once."""
        _authority(port)                 # validates the port
        self.port = port
        self.max_message = max_message
        self.connect_timeout = connect_timeout
        self.read_timeout = read_timeout
        self.bytes_in = 0
        self._buf = bytearray()
        self._grpc = bytearray()
        self._unacked = 0
        self._headers_seen = False
        self._in_headers = False
        self._header_bytes = 0
        self._end = None
        self._closed = False
        self._close_lock = threading.Lock()
        self._sent_preface = self._sent_headers = self._sent_request = False
        self._rate_t = time.monotonic()
        self._rate = [0] * len(_RATE_CAPS)
        self.__sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.__sock.settimeout(connect_timeout)
        if connect:
            self.connect()

    def connect(self):
        """Connect to 127.0.0.1:<port> and send the one request. Raises OSError (refused,
        timed out, closed by another thread) or StreamClosed; the stream is closed then."""
        try:
            if self._closed:
                raise StreamClosed("closed")
            self.__sock.connect((LOOPBACK, self.port))
            if self.__sock.getpeername()[0] != LOOPBACK:
                raise StreamClosed("not loopback")
            self.__sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            self._write(PREFACE
                        + frame(SETTINGS, 0, 0, _SETTINGS)
                        + frame(WINDOW_UPDATE, 0, 0, struct.pack(">I", WINDOW - 65535))
                        + frame(HEADERS, F_END_HEADERS, 1, request_headers(self.port))
                        + frame(DATA, F_END_STREAM, 1, _EMPTY_REQUEST))
            self.__sock.settimeout(self.read_timeout)
        except BaseException:
            self.close()
            raise

    def close(self):
        """Safe from any thread, any number of times. Ends a poll() blocked in another thread."""
        with self._close_lock:
            if self._closed:
                return
            self._closed = True
        try:
            self.__sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        try:
            self.__sock.close()
        except OSError:
            pass

    # -- the one way out ---------------------------------------------------

    def _write(self, data):
        """Send `data`, after checking every frame in it against what this client may send.
        This is the only place in the dashboard that writes to the telemetry socket."""
        try:
            self._check_outgoing(bytes(data))
        except SendRefused:
            self.close()
            raise
        try:
            self.__sock.sendall(data)
        except OSError:
            raise StreamClosed("send failed")

    def _check_outgoing(self, data):
        i = 0
        if data.startswith(PREFACE):
            if self._sent_preface:
                raise SendRefused("a second preface")
            self._sent_preface = True
            i = len(PREFACE)
        elif not self._sent_preface:
            raise SendRefused("bytes before the preface")
        while i < len(data):
            if len(data) - i < 9:
                raise SendRefused("a partial frame")
            ln = int.from_bytes(data[i:i + 3], "big")
            ftype, flags = data[i + 3], data[i + 4]
            sid = int.from_bytes(data[i + 5:i + 9], "big")
            payload = data[i + 9:i + 9 + ln]
            if len(payload) != ln:
                raise SendRefused("a partial frame")
            i += 9 + ln
            if ftype == HEADERS:
                # The one allowed header block, written out here as literals instead of taken
                # from the module's constants: rebinding STREAM_PATH, _PATH_BLOCK or _TAIL_BLOCK
                # at run time cannot make this check approve another request. Only the port
                # (digits, checked) varies; the host is part of the literal.
                port = self.port
                if not isinstance(port, int) or isinstance(port, bool) or not 0 < port < 65536:
                    raise SendRefused("bad port")
                auth = b"127.0.0.1:" + str(port).encode("ascii")
                want = (b"\x83\x86\x04\x3a/sc.game.telemetry.v1.GameTelemetryService/TelemetryStream"
                        + b"\x01" + bytes([len(auth)]) + auth
                        + b"\x0f\x10\x10application/grpc\x00\x02te\x08trailers"
                        + b"\x00\x14grpc-accept-encoding\x08identity"
                        + b"\x00\x0auser-agent\x10scdash-telemetry")
                if self._sent_headers or sid != 1 or flags != F_END_HEADERS or payload != want:
                    raise SendRefused("a request other than the stream")
                self._sent_headers = True
            elif ftype == DATA:
                if (self._sent_request or not self._sent_headers or sid != 1
                        or flags != F_END_STREAM or payload != b"\x00\x00\x00\x00\x00"):
                    raise SendRefused("data other than the empty request")
                self._sent_request = True
            elif ftype == SETTINGS:
                ours = (b"\x00\x02\x00\x00\x00\x00\x00\x04\x00\x04\x00\x00"
                        b"\x00\x05\x00\x00\x40\x00\x00\x06\x00\x00\x40\x00")
                if sid != 0 or not (payload == ours and flags == 0 or payload == b"" and flags == F_ACK):
                    raise SendRefused("other settings")
            elif ftype == WINDOW_UPDATE:
                if sid not in (0, 1) or ln != 4 or flags:
                    raise SendRefused("a bad window update")
            elif ftype == PING:
                if sid != 0 or ln != 8 or flags != F_ACK:
                    raise SendRefused("a ping that is not an answer")
            else:
                raise SendRefused("frame type %d" % ftype)

    # -- reading -----------------------------------------------------------

    def _count(self, kind, n=1):
        now = time.monotonic()
        if now - self._rate_t >= 1.0:
            self._rate_t = now
            self._rate = [0] * len(_RATE_CAPS)
        self._rate[kind] += n
        if self._rate[kind] > _RATE_CAPS[kind]:
            raise ProtocolError("flood")

    def poll(self):
        """Complete gRPC messages that arrived within one read timeout (maybe none).
        Raises StreamClosed (or ProtocolError) when the stream is over."""
        if self._end is not None:
            raise StreamClosed(self._end)
        if self._closed:
            raise StreamClosed("closed")
        try:
            chunk = self.__sock.recv(RECV_SIZE)
        except socket.timeout:
            return []
        except OSError:
            raise StreamClosed("closed" if self._closed else "socket error")
        if not chunk:
            raise StreamClosed("closed by the game")
        self.bytes_in += len(chunk)
        self._count(_R_BYTES, len(chunk))
        self._count(_R_READS)
        self._buf += chunk
        msgs = []
        while len(self._buf) >= 9 and self._end is None:
            ln = int.from_bytes(self._buf[:3], "big")
            if ln > MAX_FRAME:
                raise ProtocolError("frame too large")
            if len(self._buf) < 9 + ln:
                break
            ftype, flags = self._buf[3], self._buf[4]
            sid = int.from_bytes(self._buf[5:9], "big") & 0x7FFFFFFF
            payload = bytes(self._buf[9:9 + ln])
            del self._buf[:9 + ln]
            self._count(_R_FRAMES)
            self._frame_in(ftype, flags, sid, payload, msgs)
        if self._end is not None and not msgs:
            raise StreamClosed(self._end)
        return msgs

    def _frame_in(self, ftype, flags, sid, payload, msgs):
        ln = len(payload)
        if self._in_headers and ftype != CONTINUATION:
            raise ProtocolError("header block interrupted")
        if ftype == DATA:
            self._data(flags, sid, payload, msgs)
        elif ftype == HEADERS:
            if sid != 1:
                raise ProtocolError("headers on another stream")
            self._header_bytes = ln
            if ln > MAX_HEADER_BLOCK:
                raise ProtocolError("header block too large")
            self._headers_seen = True
            if not flags & F_END_HEADERS:
                self._in_headers = True
            if flags & F_END_STREAM:
                # Trailers, or a trailers-only answer such as "unimplemented" (12).
                code = _grpc_status(payload)
                self._end = ("ended by the game (grpc-status %d)" % code if code is not None
                             else "ended by the game (no readable grpc-status)")
        elif ftype == CONTINUATION:
            if not self._in_headers or sid != 1:
                raise ProtocolError("stray continuation")
            self._header_bytes += ln
            if self._header_bytes > MAX_HEADER_BLOCK:
                raise ProtocolError("header block too large")
            if flags & F_END_HEADERS:
                self._in_headers = False
        elif ftype == SETTINGS:
            if sid != 0:
                raise ProtocolError("settings on a stream")
            self._count(_R_SETTINGS)
            if flags & F_ACK:
                if ln:
                    raise ProtocolError("settings ack with a payload")
            else:
                if ln % 6:
                    raise ProtocolError("bad settings length")
                self._write(frame(SETTINGS, F_ACK, 0))
        elif ftype == PING:
            if ln != 8 or sid != 0:
                raise ProtocolError("bad ping")
            if not flags & F_ACK:
                self._count(_R_PINGS)
                self._write(frame(PING, F_ACK, 0, payload))
        elif ftype == GOAWAY:
            code = int.from_bytes(payload[4:8], "big") if ln >= 8 else -1
            self._end = "the game ended the connection (GOAWAY %d)" % code
        elif ftype == RST_STREAM:
            if sid == 1:
                code = int.from_bytes(payload[:4], "big") if ln >= 4 else -1
                self._end = "stream reset by the game (code %d)" % code
        elif ftype == PUSH_PROMISE:
            raise ProtocolError("push promise")
        # PRIORITY, WINDOW_UPDATE and unknown frame types are ignored, as RFC 9113 allows.

    def _data(self, flags, sid, payload, msgs):
        ln = len(payload)
        # Flow control counts the whole payload, padding included [RFC 9113 §6.9.1].
        self._unacked += ln
        if self._unacked >= WINDOW // 2:
            inc = struct.pack(">I", self._unacked)
            self._write(frame(WINDOW_UPDATE, 0, 0, inc) + frame(WINDOW_UPDATE, 0, 1, inc))
            self._unacked = 0
        if sid != 1:
            return
        if not self._headers_seen:
            raise ProtocolError("data before headers")
        if flags & F_PADDED:
            if not ln or payload[0] >= ln:
                raise ProtocolError("bad padding")
            payload = payload[1:ln - payload[0]]
        self._grpc += payload
        while len(self._grpc) >= 5:
            if self._grpc[0] != 0:
                raise ProtocolError("compressed or unknown gRPC message flag")
            mlen = int.from_bytes(self._grpc[1:5], "big")
            if mlen > self.max_message:
                raise ProtocolError("message too large")
            if len(self._grpc) < 5 + mlen:
                break
            self._count(_R_MESSAGES)
            msgs.append(bytes(self._grpc[5:5 + mlen]))
            del self._grpc[:5 + mlen]
        if flags & F_END_STREAM:
            self._end = "stream ended by the game"
