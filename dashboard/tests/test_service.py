"""The service, in process (PLAN §6, §7, §13 "Service"): atomic writes, the settings, session
summaries (on a quit, on a crash, on a new session in the same file, never twice), a restart
mid-session arriving at the same state, the clock kept out of the state, state.json at most every
10 seconds and only on change, unmapped.json, the bounded service log, errors carried over, and
the whole life cycle with the web server.

Every test has its own data folder, log and port; none touches dashboard/data/ or the real log."""
import json
import os
import re
import subprocess
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

import scdash_testlib as lib
import test_service_helpers as h
from scdash import config, service, timeline, winutil
from scdash.names import LocationNames
from scdash.records import parse_ts
from scdash.service import Service


class Probe:
    def __init__(self, running=True):
        self.on = running
        self.calls = 0

    def running(self):
        self.calls += 1
        return self.on


class Clock:
    def __init__(self, t):
        self.t = t

    def now(self):
        return self.t

    def anchor(self):
        return {"rate": 1.0, "real": 0, "virtual": 0}


class Mono:
    def __init__(self, t=1000.0):
        self.t = t

    def __call__(self):
        return self.t


def settings(**kw):
    s = {k: (dict(v) if isinstance(v, dict) else v) for k, v in config.DEFAULTS.items()}
    s.update(process_check_seconds=0.001, port=0)
    s.update(kw)
    return s


class Case(unittest.TestCase):
    def setUp(self):
        self.inst = h.Instance()
        self.services = []

    def tearDown(self):
        for svc in self.services:
            svc.close()
        self.inst.cleanup()

    def make(self, running=True, names=lib.NAMES, clock=None, **kw):
        svc = Service(self.inst.data, self.inst.log, settings(**kw), probe=Probe(running), names=names,
                      clock=clock or Clock(time.time()))
        self.services.append(svc)
        return svc

    def drain(self, svc, turns=50):
        for _ in range(turns):
            if not svc.tick():
                break

    def summaries(self):
        d = Path(self.inst.data) / "sessions"
        return sorted(p.name for p in d.glob("*.json")) if d.is_dir() else []


# ---------------------------------------------------------------------------- files

class AtomicWrite(unittest.TestCase):
    def test_write_replace_and_no_leftovers(self):
        with lib.TempDir() as d:
            p = d / "x" / "f.json"
            service.write_json(p, {"a": 1})
            service.write_json(p, {"a": 2})
            self.assertEqual(service.read_json(p), {"a": 2})
            self.assertEqual(sorted(os.listdir(p.parent)), ["f.json"])

    def test_a_failed_write_leaves_the_old_file_whole(self):
        with lib.TempDir() as d:
            p = d / "f.json"
            service.write_json(p, {"old": True})
            with mock.patch.object(service.os, "replace", side_effect=OSError("disk gone")):
                with self.assertRaises(OSError):
                    service.write_json(p, {"new": True})
            self.assertEqual(service.read_json(p), {"old": True})
            self.assertEqual(os.listdir(d), ["f.json"], "the temporary file is removed")

    def test_a_reader_holding_the_file_only_delays_the_rename(self):
        with lib.TempDir() as d:
            p = d / "f.json"
            service.write_json(p, {"n": 1})
            calls = {"n": 0}
            real = os.replace

            def flaky(a, b):
                calls["n"] += 1
                if calls["n"] < 3:
                    raise PermissionError("in use")
                return real(a, b)
            with mock.patch.object(service.os, "replace", side_effect=flaky):
                service.write_json(p, {"n": 2})
            self.assertEqual(service.read_json(p), {"n": 2})

    def test_read_json_of_garbage_is_none(self):
        with lib.TempDir() as d:
            (d / "bad.json").write_text("{not json", encoding="utf-8")
            self.assertIsNone(service.read_json(d / "bad.json"))
            self.assertIsNone(service.read_json(d / "missing.json"))

    def test_lock_names_follow_the_data_folder(self):
        with lib.TempDir() as d:
            a, b = service.lock_name(d / "a"), service.lock_name(d / "b")
            self.assertNotEqual(a, b)
            self.assertEqual(a, service.lock_name(d / "a"))
            self.assertNotEqual(a, service.lock_name(config.DATA_DIR))

    def test_summary_names_sort_by_time(self):
        a = service.summary_name({"start": "2026-02-02T01:00:00.000Z", "build": "1", "session": "x"})
        b = service.summary_name({"start": "2026-11-26T23:11:20.067Z", "build": "13220821", "session": "y"})
        self.assertEqual(b, "2026-11-26T23-11-20Z_13220821.json")
        self.assertLess(a, b)
        self.assertTrue(service.summary_name({"start": None, "build": None, "session": "z"}).startswith("session-"))


class Settings(unittest.TestCase):
    def test_defaults_file_and_overrides(self):
        with lib.TempDir() as d:
            s, notes = config.load_settings(d)
            self.assertEqual(s["port"], config.PORT)
            self.assertEqual(notes, [])
            (d / "config.json").write_text(json.dumps({
                "_about": "a comment", "port": 50001, "poll_seconds": "fast", "nonsense": 1,
                "terminal": {"enabled": True}, "max_pages": True}), encoding="utf-8")
            s, notes = config.load_settings(d, {"port": 50002, "live": None})
            self.assertEqual(s["port"], 50002)
            self.assertEqual(s["poll_seconds"], config.DEFAULTS["poll_seconds"])
            self.assertEqual(s["max_pages"], config.DEFAULTS["max_pages"])
            self.assertTrue(s["terminal"]["enabled"])
            self.assertEqual(len(notes), 3, notes)
            (d / "config.json").write_text("[1, 2", encoding="utf-8")
            s, notes = config.load_settings(d)
            self.assertEqual(s["port"], config.PORT)
            self.assertEqual(len(notes), 1)

    def test_bad_ports_are_ignored(self):
        with lib.TempDir() as d:
            for bad in (0, 70000, -5, 1.5):
                (d / "config.json").write_text(json.dumps({"port": bad}), encoding="utf-8")
                s, notes = config.load_settings(d)
                self.assertEqual(s["port"], config.PORT, bad)

    def test_example_documents_every_key(self):
        ex = json.loads(config.EXAMPLE_CONFIG.read_text(encoding="utf-8"))
        keys = {k for k in ex if not k.startswith("_")}
        self.assertEqual(keys, set(config.DEFAULTS))
        for k, v in config.DEFAULTS.items():
            self.assertIn("_" + k, ex, "no explanation for %r" % k)
            self.assertEqual(ex[k], v, k)
        with lib.TempDir() as d:
            (d / "config.json").write_text(config.EXAMPLE_CONFIG.read_text(encoding="utf-8"), encoding="utf-8")
            s, notes = config.load_settings(d)
            self.assertEqual(notes, [])
            self.assertEqual(s, config.DEFAULTS)


# ---------------------------------------------------------------------------- summaries

class Summaries(Case):
    def test_no_game_reads_the_last_log_once_and_writes_its_summary_once(self):
        self.inst.write_log(h.log_bytes())
        svc = self.make(running=False)
        svc.start_reading()
        self.assertEqual(self.summaries(), ["2026-11-26T23-11-20Z_13220821.json"])
        sm = service.read_json(self.inst.data / "sessions" / self.summaries()[0])
        self.assertEqual(sm["ended"]["how"], "quit")
        first = (self.inst.data / "sessions" / self.summaries()[0]).stat().st_mtime_ns
        payload = json.loads(svc.hub.latest)
        self.assertFalse(payload["service"]["game_running"])
        self.assertIsNotNone(payload["clock"]["session_end"])
        # a restart with no game: the same summary is not written again
        svc2 = self.make(running=False)
        svc2.start_reading()
        self.assertEqual(len(self.summaries()), 1)
        self.assertEqual((self.inst.data / "sessions" / self.summaries()[0]).stat().st_mtime_ns, first)
        self.assertEqual(svc2.summaries_written, 0)

    def test_crash_the_process_goes_away_without_a_quit_line(self):
        self.inst.write_log(h.without_quit(h.log_bytes()))
        svc = self.make(running=True)
        svc.start_reading()
        self.drain(svc)
        self.assertEqual(self.summaries(), [], "a running game has no summary")
        svc.probe.on = False                      # the game crashed: no quit line, the process is gone
        svc._next_probe = 0.0                     # look now (Windows' monotonic clock moves in 15 ms steps)
        svc.tick()
        self.assertEqual(len(self.summaries()), 1)
        sm = service.read_json(self.inst.data / "sessions" / self.summaries()[0])
        self.assertEqual(sm["ended"]["how"], "no quit line (crash or kill)")
        self.assertIsNotNone(sm["end"])
        svc.tick()
        svc.tick()
        self.assertEqual(svc.summaries_written, 1)
        # a later start (no game) does not write it again
        svc2 = self.make(running=False)
        svc2.start_reading()
        self.assertEqual(len(self.summaries()), 1)

    def test_a_new_session_in_the_same_file_ends_the_old_one(self):
        self.inst.write_log(h.log_bytes(0.5))
        svc = self.make(running=True)
        svc.start_reading()
        self.drain(svc)
        self.inst.write_log(lib.sample_bytes("courier.log"))       # the game relaunched: new first line
        self.drain(svc)
        names = self.summaries()
        self.assertEqual(len(names), 1)
        sm = service.read_json(self.inst.data / "sessions" / names[0])
        self.assertEqual(sm["session"], "Build(13220821) 26 Nov 26 (15 11 12)")
        self.assertEqual(sm["ended"]["how"], "no quit line (crash or kill)")
        self.assertEqual(svc.reader.state.session["id"], "Build(13220821) 21 Nov 26 (05 19 29)")

    def test_old_summaries_are_pruned(self):
        svc = self.make(running=False, sessions_keep=2)
        for i in range(4):
            svc.write_summary({"session": "s%d" % i, "build": "1", "start": "2026-11-0%dT00:00:00.000Z" % (i + 1),
                               "ended": {"how": "quit"}}, "test")
        self.assertEqual(self.summaries(), ["2026-11-03T00-00-00Z_1.json", "2026-11-04T00-00-00Z_1.json"])

    def test_running_or_empty_sessions_are_not_written(self):
        svc = self.make(running=False)
        self.assertFalse(svc.write_summary({"session": "x", "ended": {"how": "running"}}, "test"))
        self.assertFalse(svc.write_summary({"session": None, "ended": {"how": "quit"}}, "test"))
        self.assertEqual(self.summaries(), [])


# ---------------------------------------------------------------------------- restart, clock

class Restart(Case):
    def test_restart_mid_session_arrives_at_the_same_state(self):
        part1 = h.log_bytes(0.45)
        whole = h.log_bytes(1.0)
        self.inst.write_log(part1)
        live = self.make(running=True)          # watched live: part 1, then the rest as it was written
        live.start_reading()
        self.drain(live)
        first = json.loads(live.hub.latest)["state"]
        self.inst.write_log(whole[len(part1):], "ab")
        self.drain(live)
        restarted = self.make(running=True)     # started again later: reads the log from the top
        restarted.start_reading()
        self.drain(restarted)
        a = json.loads(live.hub.latest)["state"]
        b = json.loads(restarted.hub.latest)["state"]
        self.assertNotEqual(first, a)
        self.assertEqual(a, b)
        self.assertEqual(self.summaries(), [], "the game still runs: no summary")

    def test_hangar_stuck_comes_from_the_service_clock(self):
        data = h.log_bytes()
        at = data.find(b"Your place: 2")
        cut = data.find(b"\n", at) + 1
        self.inst.write_log(data[:cut])
        joined = parse_ts("2026-11-26T23:17:10.584")
        clock = Clock(joined + 100)
        svc = self.make(running=True, clock=clock)
        svc.start_reading()
        self.drain(svc)
        self.assertFalse(json.loads(svc.hub.latest)["flags"]["hangar_stuck"])
        self.assertIsNotNone(svc.reader.state.hangar["queue"], "the queue is open in this cut")
        state_before = svc.reader.state.to_dict()
        clock.t = joined + 401                  # past twice the 200 s estimate
        svc.tick()
        self.assertTrue(json.loads(svc.hub.latest)["flags"]["hangar_stuck"])
        self.assertEqual(svc.reader.state.to_dict(), state_before, "the clock never changes the state")


class StateFile(Case):
    def test_saved_at_most_every_10_seconds_and_only_on_change(self):
        part1 = h.log_bytes(0.3)
        self.inst.write_log(part1)
        svc = self.make(running=True, state_save_seconds=10.0)
        mono = svc.mono = Mono(1000.0)
        svc.start_reading()
        self.drain(svc)
        saved = lambda: service.read_json(self.inst.data / "state.json")   # noqa: E731
        self.assertIsNotNone(saved(), "the first state is saved")
        events0 = saved()["state"]["session"]["events"]
        self.inst.write_log(h.log_bytes(0.6)[len(part1):], "ab")
        mono.t = 1003.0
        self.drain(svc)
        self.assertEqual(saved()["state"]["session"]["events"], events0, "not again within 10 s")
        mono.t = 1010.5
        svc.tick()
        events1 = saved()["state"]["session"]["events"]
        self.assertGreater(events1, events0)
        stamp = (self.inst.data / "state.json").stat().st_mtime_ns
        mono.t = 1030.0
        svc.tick()
        svc.tick()
        self.assertEqual((self.inst.data / "state.json").stat().st_mtime_ns, stamp, "no change, no write")
        self.assertEqual(saved()["user"], {})
        self.assertNotIn("me", saved()["state"], "the saved state is the public one")

    def test_published_state_is_the_public_one(self):
        self.inst.write_log(h.log_bytes())
        svc = self.make(running=False)
        svc.start_reading()
        text = svc.hub.latest
        self.assertNotIn("Pilot_Example", text, "the sample's handle")
        self.assertNotIn('"me"', text)
        self.assertNotIn(svc.token or "no-token", text)

    def test_unmapped_codes_are_recorded_once(self):
        self.inst.write_log(h.log_bytes())
        svc = self.make(running=False, names=LocationNames({}))
        svc.start_reading()
        um = service.read_json(self.inst.data / "unmapped.json")
        codes = set(um["locations"])
        self.assertIn("Stanton4_NewBabbage", codes)
        svc2 = self.make(running=False, names=LocationNames({}))
        svc2.start_reading()
        self.assertEqual(set(service.read_json(self.inst.data / "unmapped.json")["locations"]), codes)


class Robust(Case):
    def test_service_log_is_bounded(self):
        svc = self.make(running=False, log_max_bytes=4000, log_backups=1)
        for i in range(2000):
            svc.log.info("line %d %s", i, "x" * 60)
        svc.close()
        files = sorted(p.name for p in self.inst.data.glob("service.log*"))
        self.assertEqual(files, ["service.log", "service.log.1"])
        for f in files:
            self.assertLess((self.inst.data / f).stat().st_size, 4200)

    def test_a_failing_probe_is_logged_and_assumed_running(self):
        self.inst.write_log(h.without_quit(h.log_bytes()))
        svc = self.make(running=True)

        def boom():
            raise OSError("snapshot failed")
        svc.probe.running = boom
        svc.start_reading()
        svc._next_probe = 0.0
        svc.tick()
        self.assertTrue(svc.game_running, "never end a session on a guess")
        self.assertGreaterEqual(svc.errors, 1)
        self.assertEqual(self.summaries(), [])

    def test_the_loop_survives_errors(self):
        self.inst.write_log(h.log_bytes(0.5))
        svc = self.make(running=True, poll_seconds=0.05)
        real = svc.reader.poll
        fails = {"n": 0}

        def flaky(budget=None):
            if fails["n"] < 3:
                fails["n"] += 1
                raise RuntimeError("poll broke")
            return real(budget)
        svc.reader.poll = flaky
        t = threading.Thread(target=svc.run)
        t.start()
        try:
            port = h.wait_until(lambda: (service.read_json(svc.paths.run) or {}).get("port"), 10)
            self.assertTrue(port)
            self.assertTrue(h.wait_until(lambda: (h.state(port) or {}).get("state", {}).get("session", {}).get("events"), 10))
            self.assertEqual(svc.errors, 3)
            self.assertEqual(len([ln for ln in svc.paths.log.read_text(encoding="utf-8").splitlines()
                                  if "error in the main loop" in ln]), 1, "a repeated error is logged once")
        finally:
            svc.request_stop()
            t.join(15)
        self.assertFalse(t.is_alive())


class LifeCycle(Case):
    def test_run_serves_then_shuts_down_cleanly(self):
        self.inst.write_log(h.log_bytes())
        svc = self.make(running=False)
        t = threading.Thread(target=svc.run)
        t.start()
        try:
            run = h.wait_until(lambda: service.read_json(svc.paths.run), 10)
            self.assertTrue(service.valid_run(run))
            kind, health = service.probe_health(run["port"])
            self.assertEqual(kind, "scdash")
            self.assertEqual(health, {"program": "scdash", "pid": os.getpid(), "started": run["started"]})
            self.assertNotIn(run["token"], json.dumps(health))
            info = service.instance_info(svc.paths)
            self.assertTrue(info["healthy"])
            self.assertTrue(h.wait_until(lambda: (h.state(run["port"]) or {}).get("state"), 5))
            st = h.status(run["port"])
            self.assertEqual(st["log"]["status"], "idle")
            self.assertIn("private_ws", st["memory"])
            status, _ =service.http_call(run["port"], "POST", "/api/shutdown", body={}, token="wrong")
            self.assertEqual(status, 403)
            self.assertTrue(t.is_alive(), "a wrong token stops nothing")
            self.assertTrue(service.ask_to_stop(info, "test"))
            t.join(15)
            self.assertFalse(t.is_alive())
            self.assertFalse(svc.paths.run.exists(), "run.json removed on a clean stop")
            self.assertFalse(svc.paths.lock().held_elsewhere())
            self.assertIn("stopped", svc.paths.log.read_text(encoding="utf-8"))
        finally:
            svc.request_stop()
            t.join(15)

    def test_a_second_instance_for_the_same_folder_refuses(self):
        self.inst.write_log(h.log_bytes())
        a = self.make(running=False)
        t = threading.Thread(target=a.run)
        t.start()
        try:
            h.wait_until(lambda: service.read_json(a.paths.run), 10)
            b = self.make(running=False)
            self.assertEqual(b.run(), service.EXIT_RUNNING)
            self.assertEqual(b.refusal, ("lock",))
        finally:
            a.request_stop()
            t.join(15)

    def test_background_start_after_stop_exits_at_once(self):
        service.write_json(service.Paths(self.inst.data).stopped, {"stopped": "now"})
        svc = Service(self.inst.data, self.inst.log, settings(), probe=Probe(False), names=lib.NAMES,
                      background=True)
        self.services.append(svc)
        self.assertEqual(svc.run(), service.EXIT_OK)
        self.assertEqual(svc.refusal, ("stopped",))
        self.assertFalse(svc.paths.run.exists())


# ---------------------------------------------------------------------------- review round 1

FIRST = b'<2026-11-26T23:11:20.067Z> BackupNameAttachment=" Build(13220821) 26 Nov 26 (15 11 12)"  -- used by backup system\n'
HOSTILE = "‮evil‬\x1b[31mRED\x1b[0m\x07bell⁦x⁩\x85c1\x00nul"
UNSAFE = re.compile("[\x00-\x08\x0b-\x1f\x7f-\x9f؜‎‏‪-‮⁦-⁩]")


def hostile_log():
    lines = [FIRST,
             ('<2026-11-26T23:11:27.074Z> - Connected joystick0: MOZA AB6 FFB Base %s  {1002346E-0000-0000-0000-504944564944}\n'
              % HOSTILE).encode("utf-8"),
             ('<2026-11-26T23:13:41.588Z> [Notice] <SHUDEvent_OnNotification> Added notification "Contract Accepted:  '
              'CARGO %s RUN: " [15] to queue. New queue size: 1, MissionId: [e0000002-0000-4000-8000-000000000002], '
              'ObjectiveId: [] [Team_CoreGameplayFeatures][Missions][Comms]\n' % HOSTILE).encode("utf-8"),
             ('<2026-11-26T23:13:42.588Z> [Notice] <SHUDEvent_OnNotification> Added notification "New Objective: '
              'Deliver %s now: " [16] to queue. New queue size: 2, MissionId: [e0000002-0000-4000-8000-000000000002], '
              'ObjectiveId: [x] [Team_CoreGameplayFeatures][Missions][Comms]\n' % HOSTILE).encode("utf-8")]
    return b"".join(lines)


def strings(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for k, v in obj.items():
            yield from strings(k)
            yield from strings(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            yield from strings(v)


class HostileText(Case):
    def test_no_control_or_bidi_character_leaves_the_state(self):
        self.inst.write_log(hostile_log())
        svc = self.make(running=False)
        svc.start_reading()
        st = svc.reader.state
        self.assertTrue(any("evil" in x["text"] for x in st.to_dict()["feed"]), "the hostile text did arrive")
        for d in (st.to_dict(), st.to_dict(private=True), svc.reader.summary(complete=True),
                  json.loads(svc.hub.latest)):
            bad = [x for x in strings(d) if UNSAFE.search(x)]
            self.assertEqual(bad, [])
        sm = service.read_json(self.inst.data / "sessions" / self.summaries()[0])
        self.assertEqual([x for x in strings(sm) if UNSAFE.search(x)], [])

    def test_timeline_prints_none_either(self):
        self.inst.write_log(hostile_log())
        reader, summary = timeline.run(self.inst.log, lib.NAMES)
        text = timeline.render_text(reader, summary, show_all=True)
        self.assertIn("evil", text)
        self.assertIsNone(UNSAFE.search(text.replace("\n", "")))
        out = timeline.dumps(timeline.render_json(reader, summary, show_all=True))
        self.assertIsNone(UNSAFE.search(out.replace("\n", "")))
        self.assertNotIn("\\u001b", out)


class UnreadableCount(Case):
    def test_unreadable_is_in_the_session_block_and_status(self):
        import test_robust
        self.inst.write_log(FIRST + test_robust.BAD_FLOAT + test_robust.BAD_PRICE)
        svc = self.make(running=False)
        svc.start_reading()
        n = svc.reader.state.session["unreadable"]
        self.assertEqual(n, 2)
        self.assertEqual(svc.reader.state.to_dict()["session"]["unreadable"], n)
        self.assertEqual(svc.status()["session"]["unreadable"], n)


class UserBlock(Case):
    def test_what_the_user_entered_survives_a_restart(self):
        self.inst.write_log(h.log_bytes())
        self.inst.data.mkdir(parents=True, exist_ok=True)
        service.write_json(self.inst.data / "state.json", {"schema": 1, "user": {"timers": [{"label": "kept"}]},
                                                           "state": {}})
        svc = self.make(running=False, state_save_seconds=2.0)
        svc.start_reading()
        svc._save_state()
        self.assertEqual(service.read_json(self.inst.data / "state.json")["user"], {"timers": [{"label": "kept"}]})
        svc2 = self.make(running=False)                         # and again after another restart
        svc2.start_reading()
        self.assertEqual(svc2.user_data, {"timers": [{"label": "kept"}]})


class Leftovers(Case):
    def test_stale_temporary_files_are_swept_and_live_ones_kept(self):
        d = self.inst.data
        d.mkdir(parents=True, exist_ok=True)
        dead = d / ".scdash-tmp-4-deadbeef-state.json.tmp"       # pid 4 is the System process, never ours
        dead2 = d / ".scdash-tmp-999999999-0badf00d-run.json.tmp"  # no such process
        mine = d / (".scdash-tmp-%d-cafef00d-stopped.json.tmp" % os.getpid())
        other = d / ".x.999999999.0badf00d.tmp"                  # a user's file in the old form: kept
        for f in (dead, dead2, mine, other):
            f.write_text("x", encoding="utf-8")
        removed = service.sweep_temp_files(d)
        self.assertFalse(dead2.exists())
        self.assertTrue(mine.exists(), "a live writer's file stays")
        self.assertTrue(other.exists(), "only our own form is touched")
        self.assertEqual(removed, 1 + (0 if dead.exists() else 1))

    def test_sweep_runs_at_start(self):
        self.inst.write_log(h.log_bytes())
        d = self.inst.data
        d.mkdir(parents=True, exist_ok=True)
        stale = d / ".scdash-tmp-999999999-0badf00d-state.json.tmp"
        stale.write_text("half", encoding="utf-8")
        svc = self.make(running=False)
        t = threading.Thread(target=svc.run)
        t.start()
        try:
            self.assertTrue(h.wait_until(lambda: service.read_json(svc.paths.run), 10))
            self.assertFalse(stale.exists())
        finally:
            svc.request_stop()
            t.join(15)

    def test_pruning_counts_undated_summaries_too(self):
        svc = self.make(running=False, sessions_keep=2)
        d = self.inst.data / "sessions"
        d.mkdir(parents=True, exist_ok=True)
        old = d / "session-0123456789ab_x.json"
        old.write_text("{}", encoding="utf-8")
        os.utime(old, (1000000000, 1000000000))                  # 2001: older than everything
        for i in range(2):
            svc.write_summary({"session": "s%d" % i, "build": "1", "start": "2026-11-0%dT00:00:00.000Z" % (i + 1),
                               "ended": {"how": "quit"}}, "test")
        self.assertFalse(old.exists(), "the oldest file goes, whatever its name")
        self.assertEqual(len(self.summaries()), 2)


# ---------------------------------------------------------------------------- review round 2

def run_in_thread(svc):
    """svc.run() in a thread of this test; the exit code lands in the returned dict."""
    out = {}
    t = threading.Thread(target=lambda: out.setdefault("code", svc.run()))
    t.start()
    return t, out


def answers(port):
    try:
        return h.state(port)
    except (service.NotListening, OSError, ValueError):
        return None


def make_junction(link, target):
    """A directory junction (a symbolic link off Windows), or False when none can be made."""
    if winutil.IS_WINDOWS:
        r = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)], capture_output=True)
        return r.returncode == 0 and link.is_dir()
    os.symlink(target, link, target_is_directory=True)
    return True


class StartUpSurvives(Case):
    """A read or a save that fails at start-up is logged and tried again later, the way tick()
    does it. It used to end the service (exit 3), which a scheduled relaunch every five minutes
    would make a crash loop."""

    def test_state_json_planted_as_a_folder(self):
        self.inst.write_log(h.log_bytes())
        (self.inst.data / "state.json").mkdir(parents=True)
        svc = self.make(running=False)
        t, out = run_in_thread(svc)
        try:
            port = h.wait_until(lambda: (service.read_json(svc.paths.run) or {}).get("port"), 10)
            self.assertTrue(port, "run.json written")
            self.assertTrue(h.wait_until(lambda: (answers(port) or {}).get("state"), 5), "the page gets its state")
            time.sleep(0.5)
            self.assertTrue(t.is_alive(), "still running")
            self.assertEqual(len(self.summaries()), 1, "the rest of the first read was done")
        finally:
            svc.request_stop()
            t.join(15)
        self.assertEqual(out.get("code"), service.EXIT_OK)
        self.assertTrue((self.inst.data / "state.json").is_dir(), "left as it was")
        self.assertIn("cannot be read now", svc.paths.log.read_text(encoding="utf-8"))

    @unittest.skipUnless(winutil.IS_WINDOWS, "a file held with no sharing is Windows behavior")
    def test_state_json_held_with_no_sharing_across_start_up(self):
        import ctypes
        from ctypes import wintypes
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
                                    wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
        k32.CreateFileW.restype = wintypes.HANDLE
        k32.CloseHandle.argtypes = [wintypes.HANDLE]
        self.inst.write_log(h.log_bytes())
        self.inst.data.mkdir(parents=True)
        p = self.inst.data / "state.json"
        service.write_json(p, {"schema": 1, "user": {"timers": [{"label": "kept"}]}, "state": None})
        # Our own file, opened by this test with no sharing at all (a backup tool's way): neither
        # read nor replaced while the handle is held.
        handle = k32.CreateFileW(str(p), 0x80000000, 0, None, 3, 0x80, None)
        self.assertNotEqual(handle, wintypes.HANDLE(-1).value)
        svc = self.make(running=False, state_save_seconds=0.5)
        t, out = run_in_thread(svc)
        try:
            try:
                port = h.wait_until(lambda: (service.read_json(svc.paths.run) or {}).get("port"), 10)
                self.assertTrue(h.wait_until(lambda: (answers(port) or {}).get("state"), 5))
                time.sleep(1.0)
                self.assertTrue(t.is_alive(), "still running while the file is held")
            finally:
                k32.CloseHandle(handle)
            self.assertTrue(h.wait_until(lambda: (service.read_json(p) or {}).get("state"), 10),
                            "saved once it could be")
            self.assertEqual(service.read_json(p)["user"], {"timers": [{"label": "kept"}]},
                             "what the user entered was read first, never saved over")
            self.assertTrue(t.is_alive())
        finally:
            svc.request_stop()
            t.join(15)
        self.assertEqual(out.get("code"), service.EXIT_OK)

    def test_a_summary_that_cannot_be_written_now_is_written_later(self):
        self.inst.write_log(h.log_bytes())
        self.inst.data.mkdir(parents=True)
        blocker = self.inst.data / "sessions"
        blocker.write_text("a file where the folder goes", encoding="utf-8")
        svc = self.make(running=False)
        svc.start_reading()                                 # the write fails: logged, not raised
        self.assertGreaterEqual(svc.errors, 1)
        self.assertIsNotNone(svc.hub.latest, "the page got its state all the same")
        blocker.unlink()
        svc._next_summary_try = 0.0
        svc.tick()
        self.assertEqual(self.summaries(), ["2026-11-26T23-11-20Z_13220821.json"])
        self.assertEqual(svc.summaries_written, 1)

    def test_run_json_that_cannot_be_written_for_a_moment_is_written_later(self):
        self.inst.write_log(h.log_bytes())
        (self.inst.data / "run.json").mkdir(parents=True)
        with mock.patch.object(config, "RUN_JSON_RETRY_SECONDS", 0.2, create=True):
            svc = self.make(running=False)
            t, out = run_in_thread(svc)
            try:
                self.assertTrue(h.wait_until(lambda: svc.server is not None and svc.server.port, 10))
                self.assertTrue(h.wait_until(lambda: answers(svc.server.port), 5), "it serves all the same")
                (self.inst.data / "run.json").rmdir()
                run = h.wait_until(lambda: service.read_json(svc.paths.run), 10)
                self.assertTrue(service.valid_run(run), "written on a later try")
                self.assertTrue(service.instance_info(svc.paths)["healthy"])
            finally:
                svc.request_stop()
                t.join(15)
        self.assertEqual(out.get("code"), service.EXIT_OK)

    def test_an_instance_no_command_can_find_stops_with_exit_3(self):
        """Fix round 2: with run.json unwritable for good, no command can find the instance, read
        its token or stop it. After a short window of tries it stops, with exit 3 and the reason."""
        self.inst.write_log(h.log_bytes())
        (self.inst.data / "run.json").mkdir(parents=True)
        with mock.patch.object(config, "RUN_JSON_RETRY_SECONDS", 0.2, create=True), \
                mock.patch.object(config, "RUN_JSON_GIVE_UP_SECONDS", 1.5, create=True):
            svc = self.make(running=False)
            t, out = run_in_thread(svc)
            try:
                t.join(8)
                self.assertFalse(t.is_alive(), "it stopped by itself")
            finally:
                svc.request_stop()
                t.join(15)
        self.assertEqual(out.get("code"), service.EXIT_SETUP)
        self.assertFalse(svc.paths.lock().held_elsewhere(), "the lock is free for the next start")
        log = svc.paths.log.read_text(encoding="utf-8")
        self.assertIn("run.json could not be written", log)
        self.assertIn("error in writing run.json", log, "the failure itself is in the log too")


class ServerThread(Case):
    def test_the_service_stops_when_its_server_thread_has_died(self):
        """Fix round 2: with the front-end thread gone, nothing can reach the instance, yet it held
        the lock (`status` called it hung, `start` refused). Now it stops with exit 4."""
        self.inst.write_log(h.log_bytes())
        svc = self.make(running=False)
        t, out = run_in_thread(svc)
        try:
            port = h.wait_until(lambda: (service.read_json(svc.paths.run) or {}).get("port"), 10)
            self.assertTrue(h.wait_until(lambda: answers(port), 5))

            def dies():
                raise SystemExit("injected")              # not an Exception: it ends the thread
            svc.server._httpd._turn = dies
            t.join(8)
            self.assertFalse(t.is_alive(), "the main loop noticed and stopped")
        finally:
            svc.request_stop()
            t.join(15)
        self.assertEqual(out.get("code"), service.EXIT_SERVER)
        self.assertFalse(svc.paths.lock().held_elsewhere(), "the lock is free for the next start")
        self.assertFalse(svc.paths.run.exists(), "run.json removed")
        self.assertIn("server's thread has ended", svc.paths.log.read_text(encoding="utf-8"))


class Junctions(Case):
    """Nothing is written, swept or pruned through a junction or a link below the data folder."""

    def test_a_junction_named_sessions_is_never_written_or_swept_through(self):
        self.inst.write_log(h.log_bytes())
        self.inst.data.mkdir(parents=True)
        outside = self.inst.dir / "outside"
        outside.mkdir()
        (outside / ".scdash-tmp-999999999-0badf00d-x.json.tmp").write_text("not ours to sweep", encoding="utf-8")
        (outside / "2001-01-01T00-00-00Z_1.json").write_text("{}", encoding="utf-8")     # not ours to prune
        if not make_junction(self.inst.data / "sessions", outside):
            self.skipTest("no junction could be made here")
        before = sorted(os.listdir(outside))
        svc = self.make(running=False, sessions_keep=1)
        t, out = run_in_thread(svc)
        try:
            port = h.wait_until(lambda: (service.read_json(svc.paths.run) or {}).get("port"), 10)
            self.assertTrue(h.wait_until(lambda: (answers(port) or {}).get("state"), 5))
            time.sleep(0.3)
            self.assertTrue(t.is_alive(), "still running")
        finally:
            svc.request_stop()
            t.join(15)
        self.assertEqual(out.get("code"), service.EXIT_OK)
        self.assertEqual(sorted(os.listdir(outside)), before, "nothing written, swept or pruned out there")
        log = svc.paths.log.read_text(encoding="utf-8")
        self.assertEqual(log.count("is a junction or a link"), 1, "reported once")

    def test_the_check_looks_at_each_part_and_follows_none(self):
        with lib.TempDir() as d:
            (d / "real").mkdir()
            (d / "elsewhere").mkdir()
            if not make_junction(d / "j", d / "elsewhere"):
                self.skipTest("no junction could be made here")
            self.assertIsNone(service.link_on_the_way(d, d / "real" / "a.json"))
            self.assertIsNone(service.link_on_the_way(d, d / "missing" / "deeper" / "a.json"))
            self.assertEqual(service.link_on_the_way(d, d / "j" / "a.json"), d / "j")
            self.assertEqual(service.link_on_the_way(d, d / "j" / "x" / "a.json"), d / "j")
            self.assertIsNone(service.link_on_the_way(d, d / "j"), "a target is replaced, not written through")
            self.assertEqual(service.link_on_the_way(d, d / "j", include_self=True), d / "j")
            self.assertIsNotNone(service.link_on_the_way(d / "real", d / "a.json"), "outside the folder")


class ShutdownReason(Case):
    def test_the_reason_cannot_write_lines_of_its_own_into_the_log(self):
        self.inst.write_log(h.log_bytes())
        svc = self.make(running=False)
        t, out = run_in_thread(svc)
        try:
            run = h.wait_until(lambda: service.read_json(svc.paths.run), 10)
            forged = "x\n2026-11-27 18:00:00,000 INFO newest backup (forged): same size, rotation undisturbed"
            status, _ = service.http_call(run["port"], "POST", "/api/shutdown", body={"reason": forged + "y" * 5000},
                                          token=run["token"])
            self.assertEqual(status, 200)
            t.join(15)
        finally:
            svc.request_stop()
            t.join(15)
        lines = svc.paths.log.read_text(encoding="utf-8").splitlines()
        self.assertFalse(any(ln.startswith("2026-11-27 18:00:00,000") for ln in lines), "no forged line")
        asked = [ln for ln in lines if "shutdown asked for" in ln]
        self.assertEqual(len(asked), 1)
        self.assertIn("\\n2026-11-27", asked[0], "the line break shown, not written")
        self.assertLess(len(asked[0]), 200, "and cut short")


class SweepNames(unittest.TestCase):
    def test_the_sweep_takes_only_names_it_writes(self):
        with lib.TempDir() as d:
            odd = [".scdash-tmp-٩٩٩٩٩٩٩٩٩-deadbeef-x.json.tmp",  # Arabic-Indic digits
                   ".scdash-tmp-%s-deadbeef-x.json.tmp" % ("9" * 30),            # no Windows pid is that long
                   ".scdash-tmp-999999999-deadbeef-été.tmp"]           # a name we never write
            for n in odd:
                (d / n).write_text("x", encoding="utf-8")
            ours = d / ".scdash-tmp-999999999-deadbeef-2026-11-26T23-11-20Z_13220821.json.tmp"
            ours.write_text("x", encoding="utf-8")
            self.assertEqual(service.sweep_temp_files(d), 1)
            self.assertFalse(ours.exists())
            for n in odd:
                self.assertTrue((d / n).exists(), n)


class ProcessMatch(unittest.TestCase):
    def test_without_a_creation_time_there_is_no_match(self):
        # This test's own process is a live python.exe, but nothing says it wrote that run.json.
        self.assertFalse(service.run_process_alive({"pid": os.getpid()}))
        self.assertFalse(service.run_process_alive({"pid": os.getpid(), "created": None}))
        if winutil.IS_WINDOWS:
            self.assertTrue(service.run_process_alive({"pid": os.getpid(), "created": winutil.process_created()}))


class StatusText(Case):
    def test_status_carries_no_control_text_from_the_log(self):
        first = FIRST.replace(b"Build(13220821) ", b"Build(13220821) \x1b]0;TITLE\x07\x1b[2J\xc2\x9b31m\xe2\x80\xae")
        self.inst.write_log(first + hostile_log()[len(FIRST):])
        svc = self.make(running=False)
        svc.start_reading()
        st = svc.status()
        self.assertIn("TITLE", st["session"]["id"], "the id is still there")
        self.assertEqual([x for x in strings(st) if UNSAFE.search(x)], [])


class Bounds(unittest.TestCase):
    def test_every_number_is_bounded_on_both_sides(self):
        bad = {"log_backups": 0, "log_max_bytes": 0, "poll_seconds": 0.001, "process_check_seconds": 0.1,
               "state_save_seconds": 0.0, "push_min_seconds": 0.0, "keepalive_seconds": 1e9, "retry_ms": 1,
               "max_pages": 99, "sessions_keep": 0, "port": 80}
        with lib.TempDir() as d:
            (d / "config.json").write_text(json.dumps(bad), encoding="utf-8")
            s, notes = config.load_settings(d)
            for k in bad:
                self.assertEqual(s[k], config.DEFAULTS[k], k)
            self.assertEqual(len(notes), len(bad))
        for k, v in config.DEFAULTS.items():
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                self.assertIn(k, config.BOUNDS, "%s has no bounds" % k)
                lo, hi = config.BOUNDS[k]
                self.assertTrue(lo <= v <= hi, k)

    def test_overrides_are_bounded_too(self):
        with lib.TempDir() as d:
            s, notes = config.load_settings(d, {"port": 5})
            self.assertEqual(s["port"], config.PORT)
            self.assertEqual(len(notes), 1)


class NothingEndsAProcess(unittest.TestCase):
    """Nothing in scdash signals, suspends or ends a process; the one process handle it opens is
    query-only, to one of our own Python processes (PLAN §8)."""

    FORBIDDEN = re.compile(r"os\.kill|killpg|TerminateProcess|NtSuspend|SuspendThread|\.terminate\(|\.kill\(|"
                           r"send_signal|taskkill|raise_signal|DebugActiveProcess|CreateRemoteThread|"
                           r"WriteProcessMemory|ReadProcessMemory")

    def test_no_process_is_ever_signalled(self):
        files = sorted((lib.DASHBOARD / "scdash").glob("*.py")) + [lib.DASHBOARD / "scdash.py"]
        hits = []
        for f in files:
            for i, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
                code = line.split("#", 1)[0]
                if self.FORBIDDEN.search(code):
                    hits.append("%s:%d" % (f.name, i))
        self.assertEqual(hits, [])

    def test_no_process_handle_is_ever_opened(self):
        for f in sorted((lib.DASHBOARD / "scdash").glob("*.py")) + [lib.DASHBOARD / "scdash.py"]:
            self.assertNotIn("OpenProcess", f.read_text(encoding="utf-8"), f.name)

    def test_creation_times_come_from_the_table(self):
        if not service.winutil.IS_WINDOWS:
            self.skipTest("Windows only")
        table = service.winutil.process_table()
        mine = next(c for p, n, c in table if p == os.getpid())
        self.assertIsInstance(mine, float)
        self.assertLess(abs(mine - service.winutil.process_created()), 0.001)
        other = next((p, c) for p, n, c in table if p != os.getpid() and c)
        self.assertEqual(service.winutil.process_created(other[0], table), other[1])


if __name__ == "__main__":
    unittest.main()
