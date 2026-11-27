"""The telemetry reader against a fake game server over a real socket on 127.0.0.1 (PLAN §12
stage 6): a normal stream, and every failure ending in a clean retry or a clean stop, never an
exception out of the reader and never a busy loop. All data is synthetic.

Copyright (c) 2026 archelium (support@archelium.com) for the parts marked "From CSR" below,
used under the MIT License (see dashboard/THIRD_PARTY_NOTICES): `wait_for`, and the ideas of
several tests, come from CSR's tests (commit ba6dad0), each marked where it sits. The rest of
this file is this project's own.

Every test is short: the game may be running on this PC while the suite runs.
"""
import json
import threading
import time
import unittest

import scdash_testlib as lib
import test_telemetry_fake as fake

from scdash import telemetry as tm
from scdash import telemetry_h2 as h2

FAST = ((5.0, 0.2), (None, 0.4))          # a quick retry ladder for tests


# From CSR tests/test_tlm_recorder.py lines 18-24 (`wait_for`). Changed: the monotonic clock
# and a step argument.
def wait_for(cond, timeout=5.0, step=0.02):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if cond():
            return True
        time.sleep(step)
    return cond()


class ThreadErrors:
    """Collects exceptions raised in any thread while active."""

    def __enter__(self):
        self.errors = []
        self._old = threading.excepthook
        threading.excepthook = lambda args: self.errors.append(args.exc_value)
        return self

    def __exit__(self, *exc):
        threading.excepthook = self._old


class ReaderCase(unittest.TestCase):
    def setUp(self):
        self.schema = fake.make_schema()
        self.errs = ThreadErrors().__enter__()
        self.readers = []

    def tearDown(self):
        for r in self.readers:
            r.stop()
            self.assertTrue(r.join(5), "reader thread did not end")
        self.errs.__exit__()
        self.assertEqual(self.errs.errors, [], "an exception escaped a thread")

    def reader(self, port, **kw):
        kw.setdefault("retry_steps", FAST)
        kw.setdefault("read_timeout", 0.2)
        r = tm.TelemetryReader(schema=kw.pop("schema", self.schema), port=port, **kw)
        self.readers.append(r)
        return r

    def assertOnlyStreamPath(self, srv):
        self.assertTrue(srv.paths, "the server saw no request")
        self.assertEqual(set(srv.paths), {h2.STREAM_PATH})


class NormalStreamTest(ReaderCase):
    def test_readings_at_18_a_second(self):
        msgs = [fake.snapshot(self.schema, n=i) for i in range(18)]
        msgs[5] = fake.snapshot(self.schema, n=5, event="ACTOR_ENTER_SEAT")
        with fake.FakeServer(msgs, rate=18.0) as srv:
            r = self.reader(srv.port)
            r.start()
            self.assertTrue(wait_for(lambda: r.status()["snapshots"] >= 36, 5))
            snap, age = r.latest()
            self.assertIsNotNone(snap)
            self.assertLess(age, 1.0)
            rd = snap["readings"]
            self.assertEqual(rd["balance_auec"], 123456)
            self.assertEqual(rd["vehicle_class"], "TEST_Ship")
            self.assertTrue(rd["in_vehicle"])
            self.assertEqual(rd["locomotion"], "SEATED")
            self.assertEqual(rd["gear"], "RETRACTED")
            self.assertEqual(rd["fuel_hydrogen_frac"], 0.75)
            self.assertIsNone(rd["altitude_m"])               # FLT_MAX means none
            self.assertIsNone(rd["fuel_quantum_frac"])        # 0 means none
            self.assertEqual((rd["decoys"], rd["noise"]), (24, 6))
            self.assertTrue(rd["power_engines"])
            self.assertFalse(rd["power_weapons"])            # not sent = false
            self.assertEqual(rd["warn_prox"], "MAJOR_ON")
            self.assertIsNone(rd["warn_wpn"])                 # not sent: UNSPECIFIED, shown as none
            self.assertGreaterEqual(rd["speed_mps"], 100.0)
            self.assertNotIn("vtol", rd)
            self.assertEqual(snap["withheld"], {"vtol": "DEPLOYED"})
            self.assertEqual(snap["schema"], self.schema.hash)
            self.assertEqual((snap["source"], snap["stale"]), ("telemetry", False))
            # The same snapshot object while nothing newer arrived is fine; a newer one decodes.
            self.assertTrue(wait_for(lambda: r.latest()[0] is not snap, 2))
            events = r.take_events()
            self.assertTrue(events)
            for e in events:
                self.assertEqual((e["source"], e["kind"], e["name"]),
                                 ("telemetry", "telemetry.ACTOR_ENTER_SEAT", "ACTOR_ENTER_SEAT"))
            self.assertEqual(r.take_events(), [])
            st = r.status()
            self.assertEqual(st["state"], "streaming")
            self.assertTrue(st["connected"])
            self.assertEqual(st["decode_errors"], 0)
            self.assertGreater(st["bytes"], 36 * 100)
            self.assertEqual(st["connects"], 1)
            self.assertIn("shield_level", st["missing_readings"])
            r.stop()
            self.assertTrue(r.join(3))
            self.assertEqual(r.latest(), (None, None))       # live readings go with the stream
            self.assertEqual(r.status()["state"], "stopped")
            self.assertOnlyStreamPath(srv)

    def test_decodes_only_when_asked(self):
        calls = []
        real = self.schema.decode_safe
        self.schema.decode_safe = lambda *a: (calls.append(a[0]), real(*a))[1]
        msgs = [fake.snapshot(self.schema, n=i) for i in range(5)]
        with fake.FakeServer(msgs, rate=18.0) as srv:
            r = self.reader(srv.port)
            r.start()
            self.assertTrue(wait_for(lambda: r.status()["snapshots"] >= 18, 5))
            self.assertEqual(calls, [])                      # 18 snapshots, nothing decoded
            r.latest()
            self.assertEqual(len(calls), 1)
            # A hundred asks in a row decode at most once per snapshot that arrived meanwhile.
            a, sa = len(calls), r.status()["snapshots"]
            for _ in range(100):
                r.latest()
            b, sb = len(calls), r.status()["snapshots"]
            self.assertLessEqual(b - a, sb - sa + 1)

    def test_rate_is_about_what_the_server_sends(self):
        msgs = [fake.snapshot(self.schema, n=i) for i in range(4)]
        with fake.FakeServer(msgs, rate=18.0) as srv:
            r = self.reader(srv.port)
            r.start()
            self.assertTrue(wait_for(lambda: r.status()["snapshots"] > 0, 5))
            n0, t0 = r.status()["snapshots"], time.monotonic()
            time.sleep(2.0)
            rate = (r.status()["snapshots"] - n0) / (time.monotonic() - t0)
            self.assertGreater(rate, 14)
            self.assertLess(rate, 22)

    def test_a_new_patch_field_shows_without_code_changes(self):
        schema = fake.make_schema(with_shields=True)
        msgs = [fake.snapshot(schema, extra_vehicle={"shields": {"level": 0.5, "faces": [1.0, 0.25]}})]
        with fake.FakeServer(msgs) as srv:
            r = self.reader(srv.port, schema=schema)
            r.start()
            self.assertTrue(wait_for(lambda: r.latest()[0] is not None, 5))
            snap, _ = r.latest()
            self.assertEqual(snap["readings"]["shield_level"], 0.5)
            self.assertEqual(snap["readings"]["shield_faces"], [1.0, 0.25])
            self.assertNotIn("shield_level", r.status()["missing_readings"])

    def test_on_foot_has_no_ship_readings(self):
        msgs = [fake.snapshot(self.schema, seated=False)]
        with fake.FakeServer(msgs) as srv:
            r = self.reader(srv.port)
            r.start()
            self.assertTrue(wait_for(lambda: r.latest()[0] is not None, 5))
            rd = r.latest()[0]["readings"]
            self.assertFalse(rd["in_vehicle"])
            self.assertNotIn("speed_mps", rd)
            self.assertNotIn("decoys", rd)
            self.assertEqual(rd["locomotion"], "ON_FOOT")


class FailureTest(ReaderCase):
    def _retries_cleanly(self, mode, reason_part, min_connects=2, protocol=False, **srv_kw):
        msgs = [fake.snapshot(self.schema)]
        with fake.FakeServer(msgs, modes=(mode,), **srv_kw) as srv:
            r = self.reader(srv.port, silent_s=0.6)
            c0 = time.process_time()
            r.start()
            ok = wait_for(lambda: srv.connections >= min_connects, 6)
            cpu = time.process_time() - c0
            st = r.status()
            self.assertTrue(ok, "no retry after %s: %s" % (mode, st))
            self.assertNotEqual(st["state"], "stopped")
            if protocol:
                self.assertGreaterEqual(st["protocol_errors"], 1)
            self.assertLess(cpu, 1.5, "busy loop? %.2f s of CPU" % cpu)
            self.assertTrue(wait_for(lambda: reason_part in r.status()["reason"]
                                     or reason_part in repr(r.status()), 4), r.status())
            if mode not in ("garbage", "refuse"):
                self.assertOnlyStreamPath(srv)
        return r

    def test_refused_connection_retries_on_the_ladder(self):
        # Windows takes about 2 s to refuse a connection to a closed loopback port (it retries
        # the SYN), so the connect timeout is what bounds an attempt here.
        port = fake.free_port()
        r = self.reader(port, connect_timeout=0.3)
        c0 = time.process_time()
        r.start()
        self.assertTrue(wait_for(lambda: r.status()["refusals"] >= 2, 5))
        time.sleep(1.0)
        st = r.status()
        self.assertEqual(st["state"], "waiting")
        self.assertIn("no answer", st["reason"])
        # At most one try per 0.2 s delay plus 0.3 s timeout: never a tight loop.
        self.assertLessEqual(st["refusals"], 12)
        self.assertLess(time.process_time() - c0, 0.5)
        self.assertFalse(r.connected)
        self.assertEqual(r.latest(), (None, None))

    def test_stream_that_stops_mid_message(self):
        msgs = [fake.snapshot(self.schema, n=i) for i in range(3)]
        with fake.FakeServer(msgs, modes=("cut", "normal")) as srv:
            r = self.reader(srv.port)
            r.start()
            self.assertTrue(wait_for(lambda: srv.connections >= 2 and r.latest()[0] is not None, 6))
            self.assertGreaterEqual(r.status()["connects"], 2)
            self.assertGreaterEqual(r.status()["reconnects"], 1)
            self.assertOnlyStreamPath(srv)

    def test_garbage_bytes(self):
        self._retries_cleanly("garbage", "", protocol=False)

    def test_oversized_message(self):
        self._retries_cleanly("oversized", "message too large", protocol=True)

    # From CSR tests/test_tlm_recorder.py lines 262-272 (`test_silent_past_limit_reconnects`): the idea.
    def test_silent_server_is_dropped_and_retried(self):
        r = self._retries_cleanly("silent", "silent")
        self.assertEqual(r.status()["snapshots"], 0)

    def test_server_dripping_bytes_counts_as_silent(self):
        self._retries_cleanly("drip", "silent")

    def test_server_trickling_bytes_cannot_spin_the_reader(self):
        self._retries_cleanly("trickle", "flood", protocol=True)

    def test_trailers_only_answer_keeps_only_the_status_code(self):
        r = self._retries_cleanly("trailers", "grpc-status 12")
        self.assertNotIn("EVIL", json.dumps(r.status()))

    def test_retry_waits_between_attempts(self):
        # A server that accepts and closes at once. With the real ladder (5 s first), 2 s give
        # one connection; with the test ladder (0.2 s), at most one per 0.2 s. A zero wait
        # made over a thousand in this time.
        with fake.FakeServer([fake.snapshot(self.schema)], modes=("refuse",)) as srv:
            r = self.reader(srv.port, retry_steps=tm.RETRY_STEPS)
            r.start()
            time.sleep(2.0)
            self.assertEqual(srv.connections, 1)
            r.stop()
            r.join(3)
        with fake.FakeServer([fake.snapshot(self.schema)], modes=("refuse",)) as srv:
            r = self.reader(srv.port)
            r.start()
            time.sleep(2.0)
            self.assertGreaterEqual(srv.connections, 2)
            self.assertLessEqual(srv.connections, 12)

    def test_status_carries_no_values(self):
        msgs = [fake.snapshot(self.schema, balance=987654321)]
        with fake.FakeServer(msgs) as srv:
            r = self.reader(srv.port)
            r.start()
            self.assertTrue(wait_for(lambda: r.latest()[0] is not None, 5))
            self.assertEqual(r.latest()[0]["readings"]["balance_auec"], 987654321)
            text = json.dumps(r.status())
            for private in ("987654321", "TEST_Ship"):
                self.assertNotIn(private, text)

    def test_ping_flood(self):
        self._retries_cleanly("pingflood", "flood", protocol=True)

    def test_goaway(self):
        self._retries_cleanly("goaway", "GOAWAY")

    def test_frame_over_16_kb(self):
        self._retries_cleanly("bigframe", "frame too large", protocol=True)

    def test_server_push(self):
        self._retries_cleanly("push", "push promise", protocol=True)

    def test_data_before_headers(self):
        self._retries_cleanly("nodheaders", "data before headers", protocol=True)

    def test_compressed_message(self):
        self._retries_cleanly("compressed", "compressed", protocol=True)

    def test_connection_closed_at_once(self):
        self._retries_cleanly("refuse", "")

    def test_server_that_offers_other_methods(self):
        schema = fake.make_schema(other_methods=True)
        self.assertEqual(len(schema.services[fake.PKG + ".GameTelemetryService"]), 3)
        with fake.FakeServer([fake.snapshot(schema)]) as srv:
            r = self.reader(srv.port, schema=schema)
            r.start()
            self.assertTrue(wait_for(lambda: r.latest()[0] is not None, 5))
            r.stop()
            r.join(3)
            self.assertOnlyStreamPath(srv)

    # From CSR tests/test_tlm_recorder.py lines 183-194 (`test_no_schema`): the idea.
    def test_build_without_the_stream_method_never_connects(self):
        schema = fake.make_schema(streaming=False)
        with fake.FakeServer([fake.snapshot(schema)]) as srv:
            r = self.reader(srv.port, schema=schema)
            r.start()
            self.assertTrue(wait_for(lambda: r.status()["state"] == "no-schema", 3))
            time.sleep(0.5)
            self.assertEqual(srv.connections, 0)

    # From CSR tests/test_tlm_recorder.py lines 208-219 (`test_idle_when_game_not_running`): the idea.
    def test_game_not_running_means_no_connection(self):
        with fake.FakeServer([fake.snapshot(self.schema)]) as srv:
            r = self.reader(srv.port, game_running=lambda: False)
            r.start()
            self.assertTrue(wait_for(lambda: r.status()["state"] == "idle", 3))
            time.sleep(0.5)
            self.assertEqual(srv.connections, 0)

    # From CSR tests/test_tlm_recorder.py lines 220-238 (`test_loop_survives_errors`): the idea.
    def test_game_running_check_that_raises_is_ignored(self):
        def boom():
            raise RuntimeError("no process list")
        with fake.FakeServer([fake.snapshot(self.schema)]) as srv:
            r = self.reader(srv.port, game_running=boom)
            r.start()
            self.assertTrue(wait_for(lambda: r.latest()[0] is not None, 5))


class CapsTest(ReaderCase):
    """Item by item, a hostile or broken server cannot make the reader use more than a few
    seconds of a core, more than a little memory, or block the caller."""

    def test_events_flood_is_capped(self):
        # 40 empty events per snapshot (under every cap), 50 snapshots a second: at most 16 a
        # snapshot and 64 a call come out, the rest are counted.
        msg = fake.ld(5, fake.ld(1, b"") * 40) + fake.snapshot(self.schema)
        with fake.FakeServer([msg], rate=50.0) as srv:
            r = self.reader(srv.port)
            r.start()
            self.assertTrue(wait_for(lambda: r.status()["snapshots"] >= 60, 5))
            t0 = time.perf_counter()
            events = r.take_events()
            took = time.perf_counter() - t0
            self.assertEqual(len(events), tm.MAX_EVENTS_PER_CALL)
            self.assertLess(took, 0.5)
            self.assertGreater(r.status()["events_dropped"], 0)
            self.assertLessEqual(len(r._events_raw), tm.EVENT_KEEP)

    def test_events_part_over_2_kb_drops_the_connection(self):
        msg = fake.ld(5, fake.ld(1, b"") * 1100) + fake.snapshot(self.schema)
        with fake.FakeServer([msg], rate=18.0) as srv:
            r = self.reader(srv.port)
            r.start()
            self.assertTrue(wait_for(lambda: "events part too large" in r.status()["reason"]
                                     or srv.connections >= 2, 5), r.status())
            self.assertGreaterEqual(r.status()["protocol_errors"], 1)
            self.assertEqual(r.take_events(), [])

    def test_many_top_level_fields_drop_the_connection(self):
        msg = fake.vi(1, 1) * (tm.MAX_TOP_FIELDS + 1)
        with fake.FakeServer([msg], rate=18.0) as srv:
            r = self.reader(srv.port)
            c0 = time.process_time()
            r.start()
            self.assertTrue(wait_for(lambda: r.status()["protocol_errors"] >= 1, 5), r.status())
            self.assertIn("too many top-level fields", r.status()["reason"])
            self.assertLess(time.process_time() - c0, 1.0)

    def test_field_flood_is_dropped_at_once(self):
        # The reviewer's flood: 30 KB messages of 2-byte top-level fields, back to back. The
        # first message breaks the top-level cap.
        msg = fake.vi(1, 1) * 15_000
        with fake.FakeServer([msg], modes=("blast",)) as srv:
            r = self.reader(srv.port)
            c0 = time.process_time()
            r.start()
            self.assertTrue(wait_for(lambda: "too many top-level fields" in r.status()["reason"], 5),
                            r.status())
            self.assertEqual(r.status()["snapshots"], 0)
            r.stop()
            r.join(3)
            self.assertLess(time.process_time() - c0, 2.0)

    def test_nested_field_flood_trips_the_byte_cap(self):
        # The same 2-byte fields inside one top-level field: every cap but bytes a second holds.
        msg = fake.ld(6, fake.vi(1, 1) * 15_000)
        with fake.FakeServer([msg], modes=("blast",)) as srv:
            r = self.reader(srv.port)
            c0, w0 = time.process_time(), time.monotonic()
            r.start()
            self.assertTrue(wait_for(lambda: "flood" in r.status()["reason"], 5), r.status())
            self.assertLess(time.monotonic() - w0, 3.0)
            r.stop()
            r.join(3)
            self.assertLess(time.process_time() - c0, 2.0)
            t0 = time.perf_counter()
            r.latest()                           # nothing kept after the drop: nothing to decode
            self.assertLess(time.perf_counter() - t0, 0.05)

    def test_message_rate_cap(self):
        # Tiny snapshots back to back: far over 100 a second.
        with fake.FakeServer([fake.snapshot(self.schema, seated=False)], modes=("blast",)) as srv:
            r = self.reader(srv.port)
            r.start()
            self.assertTrue(wait_for(lambda: "flood" in r.status()["reason"], 5), r.status())

    def test_message_over_32_kb(self):
        msgs = [fake.vi(1, 1) * 17_000]          # 34 KB
        with fake.FakeServer(msgs, rate=5.0) as srv:
            r = self.reader(srv.port)
            r.start()
            self.assertTrue(wait_for(lambda: "message too large" in r.status()["reason"], 5), r.status())

    def test_latest_goes_stale_while_connected_but_silent(self):
        # From CSR tests/test_tlm_recorder.py lines 239-272 (the silent-stream tests): the idea.
        with fake.FakeServer([fake.snapshot(self.schema)], rate=0.2) as srv:   # one, then 5 s quiet
            r = self.reader(srv.port, stale_s=0.3, silent_s=30)
            r.start()
            self.assertTrue(wait_for(lambda: r.latest()[0] is not None, 5))
            self.assertTrue(r.connected)
            self.assertTrue(wait_for(lambda: r.latest()[0] is None, 2))
            snap, age = r.latest()
            self.assertIsNone(snap)
            self.assertGreater(age, 0.3)
            old, _ = r.latest(allow_stale=True)
            self.assertTrue(old["stale"])
            self.assertTrue(r.connected)


class LifecycleTest(ReaderCase):
    def test_stop_at_any_moment(self):
        msgs = [fake.snapshot(self.schema, n=i) for i in range(5)]
        with fake.FakeServer(msgs) as srv:
            for delay in (0.0, 0.001, 0.01, 0.05, 0.1, 0.3):
                r = self.reader(srv.port)
                r.start()
                time.sleep(delay)
                t0 = time.monotonic()
                r.stop()
                self.assertLess(time.monotonic() - t0, 0.1, "stop() blocked")
                r.stop()                         # twice is fine
                self.assertTrue(r.join(3))
                self.assertFalse(r.connected)

    def test_stop_ends_a_connect_in_progress(self):
        # A refused loopback connect takes about 2 s on Windows; stop() must not wait for it.
        r = self.reader(fake.free_port(), connect_timeout=5.0)
        r.start()
        self.assertTrue(wait_for(lambda: r._connecting is not None, 3))
        t0 = time.monotonic()
        r.stop()
        self.assertTrue(r.join(1.0))
        self.assertLess(time.monotonic() - t0, 1.0)

    # From CSR tests/test_tlm_recorder.py lines 396-406 (`test_start_after_stop_runs`): the idea.
    def test_start_twice_and_restart_after_stop(self):
        with fake.FakeServer([fake.snapshot(self.schema)]) as srv:
            r = self.reader(srv.port)
            r.start()
            r.start()                            # no second thread
            self.assertTrue(wait_for(lambda: r.latest()[0] is not None, 5))
            self.assertEqual(sum(t.name == "scdash-telemetry" and t.is_alive()
                                 for t in threading.enumerate()), 1)
            r.stop()
            t0 = time.monotonic()
            r.start()                            # right after stop: must not block
            self.assertLess(time.monotonic() - t0, 0.1)
            self.assertTrue(wait_for(lambda: r.latest()[0] is not None, 5))
            self.assertOnlyStreamPath(srv)

    def test_stop_before_start_and_status_when_never_started(self):
        r = self.reader(fake.free_port())
        r.stop()
        self.assertEqual(r.status()["state"], "stopped")
        self.assertEqual(r.latest(), (None, None))
        self.assertEqual(r.take_events(), [])

    def test_set_port_wakes_the_reader(self):
        with fake.FakeServer([fake.snapshot(self.schema)]) as srv:
            r = self.reader(fake.free_port(), retry_steps=((None, 30.0),), connect_timeout=0.3)
            r.start()
            self.assertTrue(wait_for(lambda: r.status()["refusals"] >= 1, 3))
            r.set_port(srv.port)                 # would otherwise wait 30 s
            self.assertTrue(wait_for(lambda: r.latest()[0] is not None, 5))
            self.assertEqual(r.status()["port"], srv.port)

    def test_bad_ports_are_ignored(self):
        r = self.reader(None)
        for bad in (0, 70000, -1, "2942", True, None, 2942.0):
            r.set_port(bad)
        self.assertEqual(r.status()["port"], tm.DEFAULT_PORT)


class CaptureTest(ReaderCase):
    def test_capture_writes_every_message_and_replays(self):
        msgs = [fake.snapshot(self.schema, n=i) for i in range(6)]
        with fake.FakeServer(msgs, rate=30.0) as srv, lib.TempDir() as tmp:
            res = tm.capture(seconds=1.0, port=srv.port, out_dir=tmp, schema=self.schema,
                             read_timeout=0.2)
            self.assertEqual(res["reason"], "time")
            self.assertGreaterEqual(res["messages"], 20)
            self.assertTrue(res["path"].startswith(str(tmp)))
            header, records = tm.read_capture(res["path"])
            self.assertEqual(len(records), res["messages"])
            self.assertEqual(header["path"], h2.STREAM_PATH)
            self.assertEqual(records[0][1], msgs[0])
            schema = tm.schema_of_capture(header)
            self.assertEqual(schema.hash, self.schema.hash)
            self.assertOnlyStreamPath(srv)
            # The recording replays through the reader without the game.
            with fake.FakeServer([m for _, m in records], rate=18.0) as srv2:
                r = self.reader(srv2.port, schema=schema)
                r.start()
                self.assertTrue(wait_for(lambda: r.latest()[0] is not None, 5))
                self.assertEqual(r.latest()[0]["readings"]["vehicle_class"], "TEST_Ship")

    def test_capture_with_no_stream(self):
        with lib.TempDir() as tmp:
            res = tm.capture(seconds=0.5, port=fake.free_port(), out_dir=tmp, schema=self.schema)
            self.assertEqual(list(tmp.iterdir()), [])
            self.assertIsNone(res["path"])
            self.assertIn("no answer", res["reason"])

    def test_capture_size_limit(self):
        msgs = [fake.snapshot(self.schema)]
        with fake.FakeServer(msgs, rate=50.0) as srv, lib.TempDir() as tmp:
            res = tm.capture(seconds=5.0, port=srv.port, out_dir=tmp, schema=self.schema,
                             max_bytes=12000, read_timeout=0.2)
            self.assertEqual(res["reason"], "size limit")
            self.assertLessEqual(res["bytes"], 12000)
            self.assertGreater(res["messages"], 0)
            res = tm.capture(seconds=5.0, port=srv.port, out_dir=tmp, schema=self.schema,
                             max_bytes=100, read_timeout=0.2)
            self.assertEqual((res["reason"], res["path"]), ("size limit", None))

    def test_read_capture_refuses_other_files(self):
        with lib.TempDir() as tmp:
            p = tmp / "x.sctlm"
            lib.write(p, b"not a capture")
            with self.assertRaises(ValueError):
                tm.read_capture(p)


class PortFromLogTest(unittest.TestCase):
    def test_lines(self):
        f = tm.port_from_log_line
        head = "<2026-11-27T17:26:05.541Z> [Notice] <GRPC> "
        svc = "[sc.game.telemetry.v1.GameTelemetryService]: "
        self.assertEqual(f(head + svc + "127.0.0.1:2942"), 2942)
        self.assertEqual(f((head + svc + "127.0.0.1:2942\r\n").encode()), 2942)
        self.assertEqual(f(bytearray((head + svc + "127.0.0.1:50051").encode())), 50051)
        self.assertEqual(f("<2026-11-27T17:26:05.541Z> " + svc + "localhost:3000"), 3000)
        self.assertEqual(f("<2026-11-27T17:26:05.541Z> [SPAM 1][Info] " + svc + "0.0.0.0:2942"), 2942)
        self.assertIsNone(f(head + svc + "192.168.1.5:2942"))
        self.assertIsNone(f(head + svc + "127.0.0.1:70000"))
        self.assertIsNone(f(head + svc + "127.0.0.1:0"))
        self.assertIsNone(f(head + svc + "127.0.0.1:294299"))
        self.assertIsNone(f(head + svc + "127.0.0.1:2942 and more"))
        # Text inside another record cannot set the port.
        self.assertIsNone(f(head.replace("<GRPC>", "<SHUDEvent_OnNotification>")
                            + 'Added notification "' + svc + '127.0.0.1:4444" [3]'))
        self.assertIsNone(f("<2026-11-27T17:26:05.541Z> [Notice] <Chat> someone: " + svc + "127.0.0.1:4444"))
        self.assertIsNone(f(svc + "127.0.0.1:2942"))                        # no time prefix
        self.assertIsNone(f(head + svc + "127.0.0.1:2942" + " " * 2000))    # too long
        self.assertIsNone(f("Service 'sc.game.telemetry.v1.GameTelemetryService' registered"))
        self.assertEqual(tm.STARTUP_LINES, 1500)
        self.assertIsNone(f(b"\xff\xfe garbage \x00"))
        self.assertIsNone(f(None))
        self.assertIsNone(f(12345))

    def test_retry_ladder(self):
        self.assertEqual(tm.retry_delay(0), 5.0)
        self.assertEqual(tm.retry_delay(59), 5.0)
        self.assertEqual(tm.retry_delay(60), 10.0)
        self.assertEqual(tm.retry_delay(179), 10.0)
        self.assertEqual(tm.retry_delay(180), 60.0)
        self.assertEqual(tm.retry_delay(10_000), 60.0)


if __name__ == "__main__":
    unittest.main()
