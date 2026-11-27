"""The protobuf decoder against hostile bytes, and the schema loader against a synthetic program
file that holds descriptors (PLAN §12 stage 6). The real program file is read too when this
repo sits in a game install (read-only with full sharing, the schema cache in a temporary
folder), which is safe while the game runs.

Copyright (c) 2026 archelium (support@archelium.com) for the parts marked "From CSR" below,
used under the MIT License (see dashboard/THIRD_PARTY_NOTICES): the ideas of several tests come
from CSR's tests/test_tlm_core.py and tests/tlm_helpers.py (commit ba6dad0), each marked where
it sits. The rest of this file is this project's own.
"""
import base64
import hashlib
import json
import os
import random
import struct
import time
import unittest

import scdash_testlib as lib
import test_telemetry_fake as fake

from scdash import telemetry as tm
from scdash import telemetry_proto as proto
from scdash import telemetry_readings as rd


class HostileBytesTest(unittest.TestCase):
    def setUp(self):
        self.schema = fake.make_schema()
        self.good = fake.snapshot(self.schema, n=3, event="ACTOR_SPAWN")

    def bad(self, data, type_name=fake.RESPONSE):
        self.assertIsNone(self.schema.decode_safe(type_name, data), data[:40])

    def test_malformed_wire_data(self):
        self.bad(b"\x08" + b"\xff" * 11)                       # varint longer than 10 bytes
        self.bad(b"\x08\xff\xff")                               # varint cut off
        self.bad(b"\x08" + b"\xff" * 9 + b"\x7f")              # over 64 bits
        self.bad(b"\x1a\xff\xff\xff\xff\x0f" + b"x" * 10)     # length far past the end
        self.bad(b"\x1a\x05abc")                                # length past the end
        self.bad(b"\x0b")                                       # wire type 3 (group start)
        self.bad(b"\x0c")                                       # wire type 4
        self.bad(b"\x0e\x00")                                   # wire type 6
        self.bad(b"\x00\x01")                                   # field number 0
        self.bad(b"\x0d\x00\x00")                               # fixed32 cut off
        self.bad(b"\x09" + b"\x00" * 7)                         # fixed64 cut off
        self.bad(self.good[:-1] + b"\x80")                     # cut inside the last varint

    def test_depth_and_item_caps(self):
        node = fake.mdesc("Node", [fake.fdesc("child", 1, proto.T_MESSAGE, "Node"),
                                   fake.fdesc("v", 2, proto.T_UINT32)])
        schema = proto.Schema.from_blobs([("sc/game/telemetry/v1/x.proto",
                                           fake.file_desc("sc/game/telemetry/v1/x.proto", [node]))])
        name = fake.PKG + ".Node"
        msg = b""
        for _ in range(proto.MAX_DEPTH + 5):
            msg = fake.ld(1, msg)
        self.assertIsNone(schema.decode_safe(name, msg))
        ok = b""
        for _ in range(10):
            ok = fake.ld(1, ok)
        self.assertIsNotNone(schema.decode_safe(name, ok))
        t0 = time.perf_counter()
        many = b"\x10\x01" * (proto.MAX_ITEMS + 10)
        self.assertIsNone(schema.decode_safe(name, many))
        self.assertLess(time.perf_counter() - t0, 2.0)

    def test_packed_values(self):
        schema = self.schema
        vit = fake.PKG + ".ActorVitals"
        good = fake.key(11, 2) + fake.vint(8) + struct.pack("<ff", 1.5, 2.5)
        self.assertEqual(schema.decode(vit, good)["readings"], [1.5, 2.5])
        self.assertIsNone(schema.decode_safe(vit, fake.key(11, 2) + fake.vint(7) + b"\x00" * 7))
        unpacked = fake.key(11, 5) + struct.pack("<f", 3.0) + fake.key(11, 5) + struct.pack("<f", 4.0)
        self.assertEqual(schema.decode(vit, unpacked)["readings"], [3.0, 4.0])

    def test_odd_but_well_formed_values(self):
        s = self.schema
        inst = fake.PKG + ".VehicleFlightInstruments"
        nan = fake.key(1, 5) + struct.pack("<f", float("nan"))
        inf = fake.key(2, 5) + struct.pack("<f", float("inf"))
        self.assertEqual(s.decode(inst, nan + inf), {"speed": None, "hydrogen_fuel": None})
        wrong_wire = fake.key(1, 0) + fake.vint(5)              # speed sent as a varint
        self.assertEqual(s.decode(inst, wrong_wire), {"#1": [5]})
        unknown = fake.key(99, 0) + fake.vint(7) + fake.ld(98, b"abc")
        self.assertEqual(s.decode(inst, unknown), {"#99": [7], "#98": ["616263"]})
        st = fake.PKG + ".ActorState"
        neg = fake.key(4, 0) + fake.vint(-5)
        self.assertEqual(s.decode(st, neg)["uec_balance"], -5)
        self.assertEqual(s.decode(st, fake.key(1, 0) + fake.vint(42))["locomotion"], 42)
        bad_utf8 = fake.ld(3, b"\xff\xfeseat")
        self.assertEqual(s.decode(st, bad_utf8)["seat_name"], "��seat")
        long = fake.ld(3, b"x" * 5000)
        self.assertEqual(len(s.decode(st, long)["seat_name"]), proto.MAX_TEXT)
        self.assertEqual(s.decode(fake.PKG + ".NoSuchMessage", fake.key(1, 0) + b"\x01"), {"#1": [1]})

    def test_fuzz_never_raises_or_hangs(self):
        rnd = random.Random(20261127)
        t0 = time.perf_counter()
        samples = []
        for i in range(3000):
            b = bytearray(self.good)
            for _ in range(rnd.randint(1, 6)):
                op = rnd.random()
                pos = rnd.randrange(len(b)) if b else 0
                if op < 0.5 and b:
                    b[pos] = rnd.getrandbits(8)
                elif op < 0.7:
                    b[pos:pos] = bytes(rnd.getrandbits(8) for _ in range(rnd.randint(1, 8)))
                elif op < 0.9:
                    del b[pos:pos + rnd.randint(1, 20)]
                else:
                    b = b[:pos]
            samples.append(bytes(b))
        samples += [bytes(rnd.getrandbits(8) for _ in range(rnd.randint(0, 1500))) for _ in range(1500)]
        readings = rd.Readings(self.schema, fake.RESPONSE)
        ok = 0
        for b in samples:
            d = self.schema.decode_safe(fake.RESPONSE, b)
            self.assertTrue(d is None or isinstance(d, dict))
            if d is not None:
                ok += 1
                out = readings.build(d)              # the table must cope with any decoded shape
                json.dumps(out)                       # and give plain, serializable data
                self.assertNotIn("events", out["other"])
        self.assertGreater(ok, 100)
        self.assertLess(time.perf_counter() - t0, 30)


class SchemaTest(unittest.TestCase):
    # From CSR tests/test_tlm_core.py lines 26-59 (DecodeTests: nested messages and enums,
    # negative ints, packed floats, the enum prefix, the JSON round trip): the ideas.
    def test_what_the_descriptors_declare(self):
        s = fake.make_schema(other_methods=True)
        self.assertEqual(s.stream_response_type(), fake.RESPONSE)
        methods = {m.name: m for m in s.services[fake.PKG + ".GameTelemetryService"]}
        self.assertTrue(methods["TelemetryStream"].server_streaming)
        self.assertFalse(methods["TriggerGameAction"].server_streaming)
        fs = {f.name: f for f in s.messages[fake.PKG + ".VehicleFlightState"].values()}
        self.assertTrue(fs["gear"].optional)
        self.assertFalse(fs["is_landed"].optional)
        self.assertEqual(s.enums[fake.PKG + ".VehicleAnnunciator.AnnunciatorState"][6], "MAJOR_ON")
        self.assertEqual(s.enums[fake.PKG + ".GameEvent.GameEventType"][3], "ACTOR_ENTER_SEAT")
        self.assertTrue(s.messages[fake.PKG + ".WeaponsFrame"][5].repeated)
        self.assertIn("rpc TelemetryStream(", s.describe())

    def test_no_stream_method_means_no_response_type(self):
        self.assertIsNone(fake.make_schema(streaming=False).stream_response_type())
        self.assertIsNone(proto.Schema().stream_response_type())

    def test_enum_prefix(self):
        self.assertEqual(proto.enum_prefix("AnnunciatorState"), "ANNUNCIATOR_STATE_")
        self.assertEqual(proto.enum_prefix("VehicleComponentDeploymentState"),
                         "VEHICLE_COMPONENT_DEPLOYMENT_STATE_")
        e = fake.edesc("Odd", [("ODD_A", 0), ("OTHER", 1)])        # not all prefixed: kept whole
        s = proto.Schema.from_blobs([("sc/game/telemetry/v1/e.proto",
                                      fake.file_desc("sc/game/telemetry/v1/e.proto", enums=[e]))])
        self.assertEqual(s.enums[fake.PKG + ".Odd"], {0: "ODD_A", 1: "OTHER"})

    def test_json_round_trip_and_tampering(self):
        s = fake.make_schema()
        again = proto.Schema.from_json(json.loads(json.dumps(s.to_json())))
        self.assertEqual(again.hash, s.hash)
        self.assertEqual(again.messages, s.messages)
        d = s.to_json()
        d["hash"] = "0" * 16
        with self.assertRaises(ValueError):
            proto.Schema.from_json(d)


def synthetic_exe(blobs, size=600_000, seed=1):
    """Random bytes with each descriptor placed so its name straddles a 4 KB boundary, decoys
    that must be ignored, and plausible-looking bytes right after each descriptor. From CSR
    tests/tlm_helpers.py lines 172-177 (`exe_bytes`, junk around the blobs): the idea."""
    rnd = random.Random(seed)
    data = bytearray(rnd.getrandbits(8) for _ in range(size))
    decoys = [
        b"\x0a\x22opentelemetry/proto/trace/v1/x.proto" + b"\x12\x05other",
        b"\x0a\x20sc/game/telemetry/v1/types.prot",                    # name cut short
        b"\x1a\x20sc/game/telemetry/v1/types.proto",                   # a dependency, not a name
        b"\x0a\x21sc/game/telemetry/v1/types.proto",                   # length does not match
        b"\xa0\x07sc/game/telemetry/v1/types.proto",                   # a bare string
    ]
    at = 50_000
    for d in decoys:
        data[at:at + len(d)] = d
        at += 9_000
    for k, (name, blob) in enumerate(blobs):
        off = 4096 * (40 + 30 * k) - 10            # the name crosses a piece boundary at 4 KB
        tail = b"\x0a\x05trail\x12\x03pkg" if k == 0 else b"\x08\x01\x10\x02"
        data[off:off + len(blob) + len(tail)] = blob + tail
    return bytes(data)


class LoaderTest(unittest.TestCase):
    def setUp(self):
        self.blobs = fake.blobs()
        self.tmp = lib.TempDir()
        self.dir = self.tmp.__enter__()
        self.exe = str(self.dir / "StarCitizen.exe")
        self.cache = str(self.dir / "data" / "telemetry" / "schema.json")
        lib.write(self.exe, synthetic_exe(self.blobs))

    def tearDown(self):
        self.tmp.__exit__()

    # From CSR tests/test_tlm_core.py lines 62-76 (`test_only_game_protos_kept`, the
    # OpenTelemetry decoy that must be left out): the idea; the other decoys are this project's.
    def test_scan_finds_exactly_the_descriptors(self):
        for piece in (4096, 1 << 20):
            found = proto.scan_descriptors(self.exe, piece=piece)
            self.assertEqual(sorted(found), sorted(self.blobs), piece)

    # From CSR tests/test_tlm_core.py lines 78-104 (`test_mmap_closed`, a spy around the
    # opener): the idea.
    def test_scan_reads_in_pieces_shared_and_read_only(self):
        reads, opened = [], []
        real_open = proto._open_exe

        class Spy:
            def __init__(self, fh):
                self.fh = fh

            def read(self, n=-1):
                reads.append(n)
                return self.fh.read(n)

            def __getattr__(self, k):
                return getattr(self.fh, k)

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                self.fh.close()

        def spy_open(file):
            fh = real_open(file)
            opened.append(fh.mode)
            return Spy(fh)

        proto._open_exe = spy_open
        try:
            proto.scan_descriptors(self.exe, piece=65536)
        finally:
            proto._open_exe = real_open
        self.assertEqual(opened, ["rb"])
        self.assertTrue(reads and all(0 < n <= max(65536, proto.MAX_DESCRIPTOR) for n in reads), reads[:5])

    def test_program_file_can_be_moved_and_deleted_while_read(self):
        # The launcher must be able to patch the game while a scan holds the file (PLAN §8).
        # [seen 2026-11-27, this PC] Under a plain open() renaming the file away and deleting it
        # fail (WinError 32); under the shared open both work, and the name is free at once.
        # Renaming another file *over* it fails either way (WinError 5), which is why the
        # reader scans only while the game runs or once the file has settled.
        fh = proto._open_exe(self.exe)
        try:
            fh.read(10)
            os.rename(self.exe, self.exe + ".old")
            os.remove(self.exe + ".old")
        finally:
            fh.close()
        self.assertFalse(os.path.exists(self.exe))
        self.assertFalse(os.path.exists(self.exe + ".old"))

    def test_hit_limit_ends_the_scan(self):
        decoy = b"\x0a\x20sc/game/telemetry/v1/types.proto" + b"\xff" * 8
        data = decoy * (4 * proto.MAX_DESCRIPTORS + 10) + bytes(2_000_000)
        lib.write(self.exe, data)
        reads = []
        real_open = proto._open_exe

        class Spy:
            def __init__(self, fh):
                self.fh = fh

            def read(self, n=-1):
                reads.append(n)
                return self.fh.read(n)

            def seek(self, *a):
                return self.fh.seek(*a)

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                self.fh.close()

        proto._open_exe = lambda f: Spy(real_open(f))
        try:
            proto.scan_descriptors(self.exe, piece=32768)
        finally:
            proto._open_exe = real_open
        # The first piece holds every decoy, so the scan reads no further piece: a whole scan
        # would take 63. Then one bounded read per candidate.
        self.assertEqual(reads.count(32768), 1)
        self.assertEqual(reads.count(proto.MAX_DESCRIPTOR), 4 * proto.MAX_DESCRIPTORS)

    def test_descriptor_length_stops_at_what_follows(self):
        name, blob = self.blobs[1]
        for tail in (b"\x0a\x03abc", b"\x08\x01", b"\x00\x00", b"\x22\x02\xff\xff", b"\xff"):
            self.assertEqual(proto.descriptor_length(blob + tail, name.encode()), len(blob), tail)
        self.assertEqual(proto.descriptor_length(b"\x12\x03abc", name.encode()), 0)

    # From CSR tests/test_tlm_core.py lines 124-148 (LoadSchemaTests): the idea.
    def test_cache_life_cycle(self):
        s, how = proto.load_schema(self.exe, self.cache)
        self.assertEqual(how, "read")
        self.assertEqual(s.stream_response_type(), fake.RESPONSE)
        self.assertTrue(os.path.exists(self.cache))
        self.assertFalse(os.path.exists(self.cache + ".tmp"))
        s2, how = proto.load_schema(self.exe, self.cache)
        self.assertEqual((how, s2.hash), ("cache", s.hash))
        st = os.stat(self.exe)                       # a patch: new modified time
        os.utime(self.exe, ns=(st.st_atime_ns, st.st_mtime_ns + 10_000_000_000))
        self.assertEqual(proto.load_schema(self.exe, self.cache)[1], "read")
        self.assertEqual(proto.load_schema(self.exe, self.cache)[1], "cache")
        os.remove(self.exe)                          # the game uninstalled: the old schema stands
        s3, how = proto.load_schema(self.exe, self.cache)
        self.assertEqual((how, s3.hash), ("stale-cache", s.hash))

    def test_damaged_or_tampered_cache_is_ignored(self):
        proto.load_schema(self.exe, self.cache)
        with open(self.cache, encoding="utf-8") as fh:
            d = json.load(fh)
        d["schema"]["blobs"][0][1] = "AAAA"
        lib.write(self.cache, json.dumps(d).encode("utf-8"))
        self.assertEqual(proto.load_schema(self.exe, self.cache)[1], "read")
        for junk in ("{", "[]", '{"format": 1}', '{"format": 1, "exe": 5, "schema": {}}'):
            lib.write(self.cache, junk.encode())
            self.assertEqual(proto.load_schema(self.exe, self.cache)[1], "read", junk)
        lib.write(self.cache, b" " * (proto.MAX_CACHE_BYTES + 1))
        self.assertEqual(proto.load_schema(self.exe, self.cache)[1], "read")

    def test_cache_nested_too_deep_is_ignored(self):
        proto.load_schema(self.exe, self.cache)
        lib.write(self.cache, b"[" * 100_000)
        self.assertEqual(proto.load_schema(self.exe, self.cache)[1], "read")
        # A descriptor 2,000 types deep whose hash matches: refused, then the file is rescanned.
        inner = fake.mdesc("N", [])
        for _ in range(2000):
            inner = fake.mdesc("N", [], nested=[inner])
        blob = fake.file_desc("sc/game/telemetry/v1/deep.proto", [inner])
        with self.assertRaises(proto.DecodeError):
            proto.Schema.from_blobs([("sc/game/telemetry/v1/deep.proto", blob)])
        with open(self.cache, "w", encoding="utf-8") as fh:
            json.dump({"format": proto.CACHE_FORMAT, "exe": proto.exe_key(self.exe), "schema": {
                "hash": hashlib.sha256(blob).hexdigest()[:16],
                "blobs": [["sc/game/telemetry/v1/deep.proto", base64.b64encode(blob).decode()]]}}, fh)
        s, how = proto.load_schema(self.exe, self.cache)
        self.assertEqual(how, "read")
        self.assertEqual(s.stream_response_type(), fake.RESPONSE)

    def test_deep_descriptor_in_the_program_file(self):
        inner = fake.mdesc("N", [])
        for _ in range(2000):
            inner = fake.mdesc("N", [], nested=[inner])
        deep = fake.file_desc("sc/game/telemetry/v1/types.proto", [inner])
        lib.write(self.exe, synthetic_exe([self.blobs[0], ("sc/game/telemetry/v1/types.proto", deep)]))
        s, how = proto.load_schema(self.exe, self.cache)   # must not raise
        self.assertIn(how, ("read", "none"))

    def test_scan_only_when_allowed(self):
        self.assertEqual(proto.load_schema(self.exe, self.cache, allow_scan=False), (None, "unsettled"))
        self.assertFalse(os.path.exists(self.cache))
        self.assertEqual(proto.load_schema(self.exe, self.cache)[1], "read")
        self.assertEqual(proto.load_schema(self.exe, self.cache, allow_scan=False)[1], "cache")
        key = proto.exe_key(self.exe)
        self.assertFalse(proto.settled(key, now=key["mtime_ns"] / 1e9 + 10))
        self.assertTrue(proto.settled(key, now=key["mtime_ns"] / 1e9 + proto.SETTLE_S))
        self.assertFalse(proto.settled(None))

    def test_reader_waits_for_a_changed_file_to_settle(self):
        calls = []
        real = proto.load_schema
        proto.load_schema = lambda *a: (calls.append(a[2:]), real(*a))[1]
        r = tm.TelemetryReader(exe_path=self.exe, cache_path=self.cache, port=fake.free_port(),
                               connect_timeout=0.2, retry_steps=((None, 0.1),))
        try:
            r.start()                            # the file was just written: not settled
            time.sleep(0.5)
            st = r.status()
            self.assertEqual(st["state"], "no-schema")
            self.assertIn("settle", st["reason"])
            self.assertTrue(calls and all(c == (False,) for c in calls))
            self.assertFalse(os.path.exists(self.cache))
            old = time.time() - 2 * proto.SETTLE_S
            os.utime(self.exe, (old, old))
            r.wake()
            deadline = time.monotonic() + 5
            while r.status()["schema_how"] != "read" and time.monotonic() < deadline:
                time.sleep(0.02)
            self.assertEqual(r.status()["schema_how"], "read")
        finally:
            r.stop()
            r.join(3)
            proto.load_schema = real

    def test_program_file_without_descriptors(self):
        lib.write(self.exe, bytes(200_000))
        self.assertEqual(proto.load_schema(self.exe, self.cache), (None, "none"))
        self.assertFalse(os.path.exists(self.cache))
        self.assertEqual(proto.load_schema(str(self.dir / "missing.exe"), self.cache), (None, "none"))

    def test_reader_loads_the_schema_itself_and_does_not_rescan(self):
        r = tm.TelemetryReader(exe_path=self.exe, cache_path=self.cache, port=fake.free_port(),
                               connect_timeout=0.2, retry_steps=((None, 0.2),),
                               game_running=lambda: True)
        r.start()
        try:
            deadline = time.monotonic() + 5
            while r.status()["schema"] == "" and time.monotonic() < deadline:
                time.sleep(0.02)
            st = r.status()
            self.assertEqual(st["schema"], proto.Schema.from_blobs(self.blobs).hash)
            self.assertEqual(st["schema_how"], "read")
        finally:
            r.stop()
            r.join(3)
        lib.write(self.exe, bytes(1000))             # a file with no descriptors
        os.remove(self.cache)
        calls = []
        real = proto.load_schema
        proto.load_schema = lambda *a: (calls.append(a), real(*a))[1]
        r = tm.TelemetryReader(exe_path=self.exe, cache_path=self.cache, port=fake.free_port(),
                               retry_steps=((None, 0.05),), game_running=lambda: True)
        try:
            r.start()
            time.sleep(0.6)
            self.assertEqual(r.status()["state"], "no-schema")
            self.assertEqual(len(calls), 1)          # not rescanned every retry
        finally:
            r.stop()
            r.join(3)
            proto.load_schema = real


EXE = tm.default_exe()


@unittest.skipUnless(EXE and os.path.isfile(EXE), "no game install around this repo")
class RealProgramFileTest(unittest.TestCase):
    """Read-only: the installed game's program file, scanned in pieces; the cache goes to a
    temporary folder, never next to the game."""

    def test_the_installed_build_declares_the_stream(self):
        with lib.TempDir() as tmp:
            t0 = time.perf_counter()
            s, how = proto.load_schema(EXE, str(tmp / "schema.json"))
            took = time.perf_counter() - t0
        self.assertEqual(how, "read")
        self.assertLess(took, 30)
        self.assertEqual(s.stream_response_type(), proto.SERVICE.rsplit(".", 1)[0] + ".TelemetryStreamResponse")
        self.assertTrue(any(f["name"].startswith("sc/game/telemetry/") for f in s.files))
        # Every reading but the 5.0 ones has its field in this build; a patch that renames one
        # shows up here (and in status()["missing_readings"]).
        readings = rd.Readings(s, s.stream_response_type())
        expected_missing = {e.name for e in rd.TABLE if "5.0" in e.note}
        self.assertLessEqual(set(readings.missing), expected_missing)


if __name__ == "__main__":
    unittest.main()
