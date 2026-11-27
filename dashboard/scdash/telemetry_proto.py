"""The telemetry stream's message layout: a bounded protobuf decoder, and a schema learned from
the protobuf descriptors compiled into the installed game's program file (PLAN §12 stage 6, §15).

Copyright (c) 2026 archelium (support@archelium.com) for the parts marked "From CSR" below,
used under the MIT License (see dashboard/THIRD_PARTY_NOTICES): the wire decoder, the descriptor
scan, the Schema class and the cached loader come from CSR's sc_telemetry.py (commit ba6dad0).
Everything else in this file is this project's own.

How things are known here:

- **[game]** read from `LIVE\\Bin64\\StarCitizen.exe`, build 4.10.201.48085, on 2026-11-27: the
  program file carries two serialized FileDescriptorProtos for the stream,
  `sc/game/telemetry/v1/types.proto` and `sc/game/telemetry/v1/api.proto`, plus the protobuf
  descriptors of unrelated libraries (OpenTelemetry), which the scan leaves out by file name.
- **[protobuf]** the wire format and descriptor.proto field numbers are Google's published ones.
- Nothing here talks to the game. The program file is opened read-only with read, write and
  delete sharing (`winutil.open_shared`), so while it is being read it can still be renamed away
  or deleted, and its name is free at once [seen 2026-11-27, this PC]. Renaming another file
  *over* it still fails while any handle is open (WinError 5, with or without sharing), so a
  scan is also timed: only while the game runs or once the file has settled (`settled()`). It is
  read in pieces and closed, and nothing is ever written next to it.

No line of hostile input can raise out of `Schema.decode_safe()` or make it loop: every length
is checked against the bytes that are really there, a varint is at most 10 bytes, nesting and the
number of decoded items are capped, and the message size is capped by the caller.
"""
import base64
import hashlib
import json
import math
import os
import re
import struct
import time
from collections import namedtuple

from . import winutil

# The stream's package, service and method [game]. The one request path the client may send
# is built from these in telemetry_h2.py; nothing else in the dashboard names a method.
PACKAGE = "sc.game.telemetry.v1"
SERVICE = PACKAGE + ".GameTelemetryService"
METHOD = "TelemetryStream"

# Only descriptor files whose name starts with this are the game's own telemetry protos [game].
FILE_PREFIX = b"sc/game/telemetry/"

# Bounds (my choices; the real descriptors are 7,390 and 626 bytes [game]).
MAX_DESCRIPTOR = 64 * 1024      # bytes read after a candidate descriptor's start
MAX_DESCRIPTORS = 16            # candidate files kept from one scan
SCAN_PIECE = 1 << 20            # the program file is read 1 MB at a time
SCAN_OVERLAP = 256              # a file name can straddle two pieces
MAX_DEPTH = 32                  # message nesting while decoding (the real schema nests 6 deep)
MAX_DESCRIPTOR_DEPTH = 32       # nested message types in a descriptor (the real ones nest 1 deep)
MAX_ITEMS = 5_000               # decoded values per message: a real snapshot has at most 158
                                # [CSR's two 4.10 captures, decoded here], so about 30 times that
SETTLE_S = 60.0                 # a program file not modified for this long is not being patched
MAX_TEXT = 1024                 # a decoded string is cut to this many characters
MAX_CACHE_BYTES = 2 << 20       # a schema cache file larger than this is not read
CACHE_FORMAT = 1


class DecodeError(ValueError):
    """Bytes that are not a well-formed protobuf message (or not one the limits allow)."""


# --------------------------------------------------------------------------- wire format

# From CSR sc_telemetry.py lines 33-41 (`_varint`). Changed: at most 10 bytes, checked against
# the end of the buffer, and a DecodeError instead of an IndexError or an endless loop.
def read_varint(b, i, end):
    """(value, next index) of the varint at b[i], which must end before `end`."""
    result = shift = 0
    for _ in range(10):
        if i >= end:
            raise DecodeError("varint runs past the end")
        c = b[i]
        i += 1
        result |= (c & 0x7F) << shift
        if c < 0x80:
            if result >> 64:
                raise DecodeError("varint over 64 bits")
            return result, i
        shift += 7
    raise DecodeError("varint longer than 10 bytes")


# From CSR sc_telemetry.py lines 44-61 (`wire_fields`). Changed: works on offsets inside one
# buffer (no copies), checks every length against what is left, rejects field number 0 and the
# group wire types, and raises DecodeError for anything malformed.
def iter_fields(b, start=0, end=None):
    """(field number, wire type, value) per field of the message in b[start:end].

    Wire type 0 gives the int, 1 and 5 the start index of the 8 or 4 bytes, and 2 a
    (start, end) pair of the payload."""
    i = start
    end = len(b) if end is None else end
    while i < end:
        key, i = read_varint(b, i, end)
        no, wt = key >> 3, key & 7
        if no == 0 or no > 0x1FFFFFFF:
            raise DecodeError("bad field number")
        if wt == 0:
            v, i = read_varint(b, i, end)
        elif wt == 1:
            if i + 8 > end:
                raise DecodeError("fixed64 runs past the end")
            v, i = i, i + 8
        elif wt == 2:
            ln, i = read_varint(b, i, end)
            if ln > end - i:
                raise DecodeError("length runs past the end")
            v, i = (i, i + ln), i + ln
        elif wt == 5:
            if i + 4 > end:
                raise DecodeError("fixed32 runs past the end")
            v, i = i, i + 4
        else:
            raise DecodeError("wire type %d" % wt)
        yield no, wt, v


def _text(b, span):
    s, e = span
    return bytes(b[s:e]).decode("utf-8", "replace")


# --------------------------------------------------------------------------- schema

# From CSR sc_telemetry.py lines 66-73: protobuf's FieldDescriptorProto.Type numbers
# [protobuf]. Unchanged values.
T_DOUBLE, T_FLOAT, T_INT64, T_UINT64, T_INT32 = 1, 2, 3, 4, 5
T_FIXED64, T_FIXED32, T_BOOL, T_STRING, T_GROUP = 6, 7, 8, 9, 10
T_MESSAGE, T_BYTES, T_UINT32, T_ENUM = 11, 12, 13, 14
T_SFIXED32, T_SFIXED64, T_SINT32, T_SINT64 = 15, 16, 17, 18
TYPE_NAMES = {T_DOUBLE: "double", T_FLOAT: "float", T_INT64: "int64", T_UINT64: "uint64",
              T_INT32: "int32", T_FIXED64: "fixed64", T_FIXED32: "fixed32", T_BOOL: "bool",
              T_STRING: "string", T_GROUP: "group", T_MESSAGE: "message", T_BYTES: "bytes",
              T_UINT32: "uint32", T_ENUM: "enum", T_SFIXED32: "sfixed32",
              T_SFIXED64: "sfixed64", T_SINT32: "sint32", T_SINT64: "sint64"}
VARINT_TYPES = {T_INT64, T_UINT64, T_INT32, T_BOOL, T_UINT32, T_ENUM, T_SINT32, T_SINT64}
FIXED32_TYPES = {T_FLOAT, T_FIXED32, T_SFIXED32}
FIXED64_TYPES = {T_DOUBLE, T_FIXED64, T_SFIXED64}
LEN_TYPES = {T_STRING, T_BYTES, T_MESSAGE}
LABEL_REPEATED = 3

# One field of a message. `optional` is proto3's explicit presence (FieldDescriptorProto
# field 17); `oneof` the index of its oneof, or None.
Field = namedtuple("Field", "name number type type_name repeated optional oneof")
# One method of a service.
Method = namedtuple("Method", "name input output client_streaming server_streaming")


def enum_prefix(enum_name):
    """The value prefix protobuf's style guide gives an enum: AnnunciatorState ->
    ANNUNCIATOR_STATE_ (my own rule; CSR strips the longest common prefix instead)."""
    return re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", enum_name).upper() + "_"


class Schema:
    """Messages, enums and services of the stream, from serialized FileDescriptorProtos.

    From CSR sc_telemetry.py lines 119-283 (`Schema`). Changed: fields keep their number,
    repeated-ness, proto3 `optional` and oneof; enum values lose the prefix named after their
    enum rather than the longest common one; a method keeps both streaming flags; descriptors
    are read with the bounded wire decoder, and a malformed one raises DecodeError; decoding
    is bounded (depth, item count, text length) and keeps fields the schema does not know under
    `#<number>`; floats are rounded to float32's precision and non-finite ones become None."""

    def __init__(self):
        self.messages = {}   # full name -> {number: Field}
        self.enums = {}      # full name -> {number: short value name}
        self.services = {}   # full name -> [Method]
        self.files = []      # [{"name", "package", "bytes", "sha256"}]
        self.blobs = []      # [(file name, raw descriptor bytes)], for captures
        self.hash = ""

    # -- building ----------------------------------------------------------

    @classmethod
    def from_blobs(cls, blobs):
        s = cls()
        sha = hashlib.sha256()
        for fname, blob in blobs:
            pkg = s._file(blob)
            s.files.append({"name": fname, "package": pkg, "bytes": len(blob),
                            "sha256": hashlib.sha256(blob).hexdigest()[:16]})
            s.blobs.append((fname, bytes(blob)))
            sha.update(blob)
        s.hash = sha.hexdigest()[:16]
        return s

    def _file(self, b):
        pkg = ""
        fields = list(iter_fields(b))
        for no, wt, v in fields:
            if no == 2 and wt == 2:
                pkg = _text(b, v)
        for no, wt, v in fields:
            if wt != 2:
                continue
            if no == 4:
                self._message(b, v, pkg)
            elif no == 5:
                self._enum(b, v, pkg)
            elif no == 6:
                self._service(b, v, pkg)
        return pkg

    @staticmethod
    def _join(scope, name):
        return scope + "." + name if scope else name

    def _message(self, b, span, scope, depth=0):
        if depth > MAX_DESCRIPTOR_DEPTH:
            raise DecodeError("message types nested too deep")
        name, fields, nested = None, [], []
        for no, wt, v in iter_fields(b, *span):
            if no == 1 and wt == 2:
                name = _text(b, v)
            elif no == 2 and wt == 2:
                fields.append(v)
            elif no in (3, 4) and wt == 2:
                nested.append((no, v))
        if not name:
            raise DecodeError("message without a name")
        full = self._join(scope, name)
        table = self.messages.setdefault(full, {})
        for v in fields:
            f = self._field(b, v)
            if f is not None:
                table[f.number] = f
        for no, v in nested:
            if no == 3:
                self._message(b, v, full, depth + 1)
            else:
                self._enum(b, v, full)

    @staticmethod
    def _field(b, span):
        name, number, label, ftype, tname = None, None, 1, None, ""
        optional, oneof = False, None
        for no, wt, v in iter_fields(b, *span):
            if no == 1 and wt == 2:
                name = _text(b, v)
            elif no == 3 and wt == 0:
                number = v
            elif no == 4 and wt == 0:
                label = v
            elif no == 5 and wt == 0:
                ftype = v
            elif no == 6 and wt == 2:
                tname = _text(b, v).lstrip(".")
            elif no == 9 and wt == 0:
                oneof = v
            elif no == 17 and wt == 0:
                optional = bool(v)
        if not name or not number or ftype not in TYPE_NAMES:
            return None
        return Field(name, number, ftype, tname, label == LABEL_REPEATED, optional, oneof)

    def _enum(self, b, span, scope):
        name, vals = None, {}
        for no, wt, v in iter_fields(b, *span):
            if no == 1 and wt == 2:
                name = _text(b, v)
            elif no == 2 and wt == 2:
                vname, vno = None, 0
                for no2, wt2, v2 in iter_fields(b, *v):
                    if no2 == 1 and wt2 == 2:
                        vname = _text(b, v2)
                    elif no2 == 2 and wt2 == 0:
                        vno = v2 - (1 << 64) if v2 >= 1 << 63 else v2
                if vname:
                    vals[vno] = vname
        if not name:
            raise DecodeError("enum without a name")
        prefix = enum_prefix(name)
        if vals and all(n.startswith(prefix) and len(n) > len(prefix) for n in vals.values()):
            vals = {k: n[len(prefix):] for k, n in vals.items()}
        self.enums[self._join(scope, name)] = vals

    def _service(self, b, span, scope):
        name, methods = None, []
        for no, wt, v in iter_fields(b, *span):
            if no == 1 and wt == 2:
                name = _text(b, v)
            elif no == 2 and wt == 2:
                d = {"cs": False, "ss": False}
                for no2, wt2, v2 in iter_fields(b, *v):
                    if wt2 == 2 and no2 in (1, 2, 3):
                        d[no2] = _text(b, v2).lstrip(".")
                    elif wt2 == 0 and no2 == 5:
                        d["cs"] = bool(v2)
                    elif wt2 == 0 and no2 == 6:
                        d["ss"] = bool(v2)
                if d.get(1):
                    methods.append(Method(d[1], d.get(2, ""), d.get(3, ""), d["cs"], d["ss"]))
        if not name:
            raise DecodeError("service without a name")
        self.services[self._join(scope, name)] = methods

    # -- looking things up -------------------------------------------------

    def method(self, service_name, name):
        """A method this schema declares (a lookup in the descriptors, nothing is called)."""
        for m in self.services.get(service_name, ()):
            if m.name == name:
                return m
        return None

    def stream_response_type(self):
        """The response message of the read-only stream, or None when this build does not
        declare it as a server-streaming method."""
        m = self.method(SERVICE, METHOD)
        if m is None or not m.server_streaming or m.output not in self.messages:
            return None
        return m.output

    def describe(self):
        """The schema as text, one line per service method, message field and enum. From CSR
        sc_telemetry.py lines 210-222 (`dump`): the same layout. Changed: returns the text, shows
        both streaming flags and the proto3 `optional` mark."""
        out = []
        for name in sorted(self.services):
            out.append("service %s" % name)
            for m in self.services[name]:
                out.append("  rpc %s(%s%s) -> %s%s" % (
                    m.name, "stream " if m.client_streaming else "", m.input,
                    "stream " if m.server_streaming else "", m.output))
        for name in sorted(self.messages):
            out.append("message %s" % name)
            for no, f in sorted(self.messages[name].items()):
                kind = f.type_name or TYPE_NAMES.get(f.type, str(f.type))
                if kind.startswith(PACKAGE + "."):
                    kind = kind[len(PACKAGE) + 1:]
                out.append("  %3d %s: %s%s%s" % (no, f.name, "repeated " if f.repeated else "",
                                                 kind, " (optional)" if f.optional else ""))
        for name in sorted(self.enums):
            vals = ", ".join("%s=%d" % (v, k) for k, v in sorted(self.enums[name].items()))
            out.append("enum %s: %s" % (name, vals))
        return "\n".join(out)

    # -- the cache's JSON form ---------------------------------------------

    def to_json(self):
        return {
            "hash": self.hash,
            "files": [dict(f) for f in self.files],
            "blobs": [[n, base64.b64encode(b).decode("ascii")] for n, b in self.blobs],
        }

    @classmethod
    def from_json(cls, d):
        """Rebuilt from the descriptor bytes the cache holds, so a cache can never describe
        anything the descriptors themselves do not. Raises on anything malformed."""
        blobs = []
        for item in d["blobs"]:
            n, b64 = item
            if not isinstance(n, str) or not isinstance(b64, str):
                raise ValueError("bad cache entry")
            blob = base64.b64decode(b64.encode("ascii"), validate=True)
            if len(blob) > MAX_DESCRIPTOR:
                raise ValueError("cached descriptor too large")
            blobs.append((n, blob))
        if not blobs or len(blobs) > MAX_DESCRIPTORS:
            raise ValueError("bad cache")
        s = cls.from_blobs(blobs)
        if s.hash != d.get("hash"):
            raise ValueError("cache hash does not match its descriptors")
        return s

    # -- decoding a message ------------------------------------------------

    def decode_safe(self, type_name, data, max_items=MAX_ITEMS):
        """The message as a dict, or None when the bytes are malformed or need more than
        `max_items` values. Never raises."""
        try:
            return self.decode(type_name, data, max_items)
        except Exception:
            return None

    def decode(self, type_name, data, max_items=MAX_ITEMS):
        """The message as a dict: field name -> value, nested messages as dicts, repeated
        fields as lists, enums as their short value name. Raises DecodeError."""
        budget = [max_items]
        return self._decode(type_name, data, 0, len(data), 0, budget)

    def _decode(self, type_name, b, start, end, depth, budget):
        if depth > MAX_DEPTH:
            raise DecodeError("nested too deep")
        table = self.messages.get(type_name, {})
        out = {}
        for no, wt, v in iter_fields(b, start, end):
            budget[0] -= 1
            if budget[0] < 0:
                raise DecodeError("too many values")
            f = table.get(no)
            if f is not None and f.repeated and wt == 2 and f.type not in LEN_TYPES:
                vals = self._packed(f, b, v, budget)
            elif f is not None and self._wire_matches(f.type, wt):
                vals = [self._value(f, wt, b, v, depth, budget)]
            else:
                # A field this schema does not know, or one whose wire type is not what the
                # schema says: kept raw, so nothing silently disappears.
                out.setdefault("#%d" % no, []).append(self._raw(wt, b, v))
                continue
            if f.repeated:
                out.setdefault(f.name, []).extend(vals)
            else:
                out[f.name] = vals[-1]       # protobuf: the last one wins
        return out

    @staticmethod
    def _wire_matches(t, wt):
        if wt == 0:
            return t in VARINT_TYPES
        if wt == 5:
            return t in FIXED32_TYPES
        if wt == 1:
            return t in FIXED64_TYPES
        return t in LEN_TYPES

    def _packed(self, f, b, span, budget):
        s, e = span
        t = f.type
        if t in FIXED32_TYPES or t in FIXED64_TYPES:
            size = 4 if t in FIXED32_TYPES else 8
            if (e - s) % size:
                raise DecodeError("packed fixed values do not fill their length")
            n = (e - s) // size
            budget[0] -= n
            if budget[0] < 0:
                raise DecodeError("too many values")
            return [self._fixed(t, b, s + k * size) for k in range(n)]
        vals, i = [], s
        while i < e:
            budget[0] -= 1
            if budget[0] < 0:
                raise DecodeError("too many values")
            v, i = read_varint(b, i, e)
            vals.append(self._varint_value(f, v))
        return vals

    def _value(self, f, wt, b, v, depth, budget):
        t = f.type
        if wt == 0:
            return self._varint_value(f, v)
        if wt in (1, 5):
            return self._fixed(t, b, v)
        if t == T_MESSAGE:
            return self._decode(f.type_name, b, v[0], v[1], depth + 1, budget)
        if t == T_STRING:
            return _text(b, v)[:MAX_TEXT]
        return self._bytes(b, v)

    def _varint_value(self, f, v):
        t = f.type
        if t == T_BOOL:
            return v != 0
        if t == T_ENUM:
            v = v - (1 << 64) if v >= 1 << 63 else v
            return self.enums.get(f.type_name, {}).get(v, v)
        if t in (T_INT32, T_INT64):
            return v - (1 << 64) if v >= 1 << 63 else v
        if t in (T_SINT32, T_SINT64):
            return (v >> 1) ^ -(v & 1)
        return v

    @staticmethod
    def _fixed(t, b, i):
        if t == T_FLOAT:
            x = struct.unpack_from("<f", b, i)[0]
            return float("%.7g" % x) if math.isfinite(x) else None
        if t == T_DOUBLE:
            x = struct.unpack_from("<d", b, i)[0]
            return x if math.isfinite(x) else None
        code = {T_FIXED32: "<I", T_SFIXED32: "<i", T_FIXED64: "<Q", T_SFIXED64: "<q"}[t]
        return struct.unpack_from(code, b, i)[0]

    @staticmethod
    def _bytes(b, span):
        s, e = span
        if e - s <= 32:
            return bytes(b[s:e]).hex()
        return "<%d bytes>" % (e - s)

    @staticmethod
    def _raw(wt, b, v):
        if wt == 0:
            return v
        if wt == 5:
            return struct.unpack_from("<I", b, v)[0]
        if wt == 1:
            return struct.unpack_from("<Q", b, v)[0]
        return Schema._bytes(b, v)


# --------------------------------------------------------------------------- the program file

# The start of a FileDescriptorProto: field 1 (its file name) with a one-byte length, then the
# name itself. The length byte must equal the name's length; that check is done below.
_NAME_RE = re.compile(rb"\x0a([\x05-\x7f])(" + re.escape(FILE_PREFIX) + rb"[!-~]{1,110}?\.proto)")

# Top-level FileDescriptorProto fields and the wire type each must have [protobuf].
_FILE_FIELDS = {1: 2, 2: 2, 3: 2, 4: 2, 5: 2, 6: 2, 7: 2, 8: 2, 9: 2, 10: None, 11: None,
                12: 2, 14: 0, 15: 2}


def _printable(b, span):
    s, e = span
    return all(0x20 <= c < 0x7F for c in b[s:e])


def descriptor_length(b, name):
    """How many bytes at the start of `b` are the FileDescriptorProto named `name`.

    The descriptor is followed by unrelated bytes in the program file, so the walk stops at the
    first top-level field that is not a plausible next field: an unknown number, a wrong wire
    type, a field number lower than the one before (protoc writes them in order), a second
    name, a string that is not printable, or a message that does not itself parse. Returns 0
    when even the name does not fit. (My own rule; CSR walked while numbers stayed 1-12.)"""
    i, last, n = 0, 0, len(b)
    probe = Schema()
    while i < n:
        try:
            key, j = read_varint(b, i, n)
            no, wt = key >> 3, key & 7
            want = _FILE_FIELDS.get(no, -1)
            if want == -1 or no < last or (no == 1 and last == 1) or (last == 0 and no != 1):
                break
            if want is not None and wt != want:
                break
            if wt == 0:
                _, j = read_varint(b, j, n)
            elif wt == 2:
                ln, j = read_varint(b, j, n)
                if ln > n - j:
                    break
                span = (j, j + ln)
                if no in (1, 2, 3, 12) and not _printable(b, span):
                    break
                if no == 1 and bytes(b[span[0]:span[1]]) != name:
                    break
                if no == 4:
                    probe._message(b, span, "")
                elif no == 5:
                    probe._enum(b, span, "")
                elif no == 6:
                    probe._service(b, span, "")
                elif no in (7, 8, 9):
                    for _ in iter_fields(b, *span):
                        pass
                j += ln
            else:
                break
        except DecodeError:
            break
        i, last = j, no
    return i if last else 0


def _open_exe(exe_path):
    """The program file, opened read-only, sharing read, write and delete (PLAN §8)."""
    return winutil.open_shared(exe_path)


def _read_full(fh, n):
    """Up to n bytes: an unbuffered file may return fewer per read."""
    out = bytearray()
    while len(out) < n:
        b = fh.read(n - len(out))
        if not b:
            break
        out += b
    return bytes(out)


def scan_descriptors(exe_path, piece=SCAN_PIECE):
    """[(file name, descriptor bytes)] for each telemetry proto file in the program file.

    From CSR sc_telemetry.py lines 85-116 (`descriptor_blobs`). Changed: the file is opened with
    full sharing and read in pieces of `piece` bytes instead of being mapped whole; each
    candidate is read with one bounded seek; where a descriptor ends is decided by
    `descriptor_length`; the same file name found twice keeps the larger descriptor; the scan
    stops at 4 * MAX_DESCRIPTORS candidates. Raises OSError if the file cannot be read."""
    found = {}
    hits = []
    with _open_exe(exe_path) as fh:
        pos, tail = 0, b""
        full = False
        while not full:
            chunk = _read_full(fh, piece)
            if not chunk:
                break
            buf = tail + chunk
            base = pos - len(tail)
            for m in _NAME_RE.finditer(buf):
                if m.group(1)[0] == len(m.group(2)):
                    off = base + m.start()
                    if off not in hits:
                        hits.append(off)
                        if len(hits) >= 4 * MAX_DESCRIPTORS:
                            full = True
                            break
            tail = buf[-SCAN_OVERLAP:]
            pos += len(chunk)
        for off in hits:
            fh.seek(off)
            b = _read_full(fh, MAX_DESCRIPTOR)
            m = _NAME_RE.match(b)
            if not m:
                continue
            name = m.group(2)
            ln = descriptor_length(b, name)
            if ln and len(found.get(name, b"")) < ln:
                found[name] = b[:ln]
            if len(found) >= MAX_DESCRIPTORS:
                break
    return [(n.decode("ascii"), blob) for n, blob in sorted(found.items())]


def exe_key(exe_path):
    """What identifies one build of the program file: its path, size and modified time."""
    st = os.stat(exe_path)
    return {"path": os.path.normcase(os.path.abspath(exe_path)), "size": st.st_size,
            "mtime_ns": st.st_mtime_ns}


def _read_cache(cache_path):
    try:
        if os.path.getsize(cache_path) > MAX_CACHE_BYTES:
            return None
        with open(cache_path, encoding="utf-8") as fh:
            d = json.load(fh)
        if not isinstance(d, dict) or d.get("format") != CACHE_FORMAT:
            return None
        if not isinstance(d.get("exe"), dict) or not isinstance(d.get("schema"), dict):
            return None
        return d
    except Exception:                    # damaged, nested too deep (RecursionError), anything
        return None


def settled(key, now=None, settle_s=SETTLE_S):
    """True when the program file was last modified at least `settle_s` ago: not being patched.
    My rule: a launcher that patches the file writes it, so its modified time is recent."""
    if key is None:
        return False
    now = time.time() if now is None else now
    return now - key["mtime_ns"] / 1e9 >= settle_s


def _schema_from_cache(saved):
    try:
        return Schema.from_json(saved["schema"])
    except Exception:                    # tampered, damaged, nested too deep: ignored
        return None


def load_schema(exe_path, cache_path, allow_scan=True):
    """(schema or None, how it was got) for the program file at `exe_path`. Never raises.

    `how` is "cache" (the saved schema matched the file's path, size and modified time),
    "read" (the file was scanned and the cache rewritten), "stale-cache" (the file is missing
    or unreadable, so an older cached schema is used), "unsettled" (the file changed and a scan
    was not allowed) or "none".

    `allow_scan`: the caller's say on reading the program file now. The reader allows it only
    while the game is running or once the file has `settled()`, so that a scan (about 0.15 s)
    does not coincide with the launcher patching the game: the shared open lets the file be
    moved or deleted meanwhile, but not replaced by a rename over it.

    From CSR sc_telemetry.py lines 286-320 (`load_schema`). Changed: the key is the file's
    path, size and modified time in nanoseconds; the cache holds the descriptor bytes and is
    rebuilt from them (a tampered or damaged cache is ignored and the file rescanned); the
    cache is size-capped and written atomically; the scan is the piecewise one above; a scan
    can be held off; nothing raises."""
    try:
        cache_path = os.path.abspath(cache_path)
    except Exception:
        return None, "none"
    saved = _read_cache(cache_path)
    try:
        key = exe_key(exe_path)
    except Exception:
        key = None
    if saved is not None and key is not None and saved.get("exe") == key:
        schema = _schema_from_cache(saved)
        if schema is not None:
            return schema, "cache"
        saved = None
    if key is not None:
        if not allow_scan:
            return None, "unsettled"
        try:
            blobs = scan_descriptors(exe_path)
            schema = Schema.from_blobs(blobs) if blobs else None
        except Exception:
            schema = None
        if schema is not None:
            try:
                os.makedirs(os.path.dirname(cache_path), exist_ok=True)
                tmp = cache_path + ".tmp"
                with open(tmp, "w", encoding="utf-8") as fh:
                    json.dump({"format": CACHE_FORMAT, "exe": key, "schema": schema.to_json()}, fh)
                os.replace(tmp, cache_path)
            except Exception:
                pass
            return schema, "read"
    if saved is not None:
        schema = _schema_from_cache(saved)
        if schema is not None:
            return schema, "stale-cache"
    return None, "none"
