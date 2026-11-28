"""`replay` (PLAN §6, §12 stage 2): a past log served at speed on a port and in a data folder of
its own, never touching the live instance or dashboard/data/.

A live instance here is a test instance (its own temporary folder and port), so the real one is
never involved either."""
import json
import os
import re
import subprocess
import sys
import time
import unittest
from pathlib import Path

import scdash_testlib as lib
import test_service_helpers as h
from scdash import config, service
from test_service import make_junction

LIVE_FILES = ("run.json", "state.json", "service.log", "service.log.1", "unmapped.json", "stopped.json",
              "config.json", "sessions", "replay")


def live_data_snapshot():
    """What a replay could write in dashboard/data/: presence and modification time of each."""
    out = {}
    for name in LIVE_FILES:
        p = config.DATA_DIR / name
        out[name] = p.stat().st_mtime_ns if p.exists() else None
        if p.is_dir():
            out[name + "/"] = sorted((q.name, q.stat().st_mtime_ns) for q in p.iterdir())
    return out


class Replay(unittest.TestCase):
    def setUp(self):
        self.inst = h.Instance()
        self.procs = []

    def tearDown(self):
        for p in self.procs:
            if p.poll() is None:
                p.kill()
            p.communicate(timeout=10)
        self.inst.cleanup()

    def replay(self, *args, capture=True):
        out = subprocess.PIPE if capture else subprocess.DEVNULL
        p = subprocess.Popen([sys.executable, str(h.SCRIPT), "replay"] + [str(a) for a in args], cwd=str(h.REPO),
                             stdout=out, stderr=out, text=True, encoding="utf-8", errors="replace")
        self.procs.append(p)
        return p

    def test_replay_unfolds_and_leaves_the_live_side_alone(self):
        live_before = live_data_snapshot()
        # A "live" test instance, running beside the replay.
        self.inst.write_log(h.log_bytes())
        r = h.cli("start", *self.inst.args(process="nosuchgame.exe"))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        live_run = service.read_json(self.inst.data / "run.json")
        live_log_lines = (self.inst.data / "service.log").read_text(encoding="utf-8").count("\n")

        data = self.inst.dir / "replay-data"
        port = h.free_port()
        p = self.replay(h.RUN_A, "--minutes", "0.12", "--port", port, "--data", data, "--exit-at-end")
        seen = []
        end = time.monotonic() + 30
        while p.poll() is None and time.monotonic() < end:
            try:
                st = h.state(port)
            except (service.NotListening, OSError, ValueError):
                st = None                               # not up yet, or shutting down
            if st:
                seen.append((st["state"]["session"]["events"], st["service"]["game_running"],
                             st["state"]["session"]["game"]))
            time.sleep(0.2)
        out, err = p.communicate(timeout=30)
        self.assertEqual(p.returncode, 0, out + err)
        events = [s[0] for s in seen]
        self.assertGreaterEqual(len(set(events)), 3, "the session unfolds over several states: %s" % events)
        self.assertEqual(events, sorted(events), "events only grow")
        self.assertIn("in_game", [s[2] for s in seen])
        # its own data folder has the session's summary
        sessions = list((data / "sessions").glob("*.json"))
        self.assertEqual(len(sessions), 1)
        self.assertEqual(service.read_json(sessions[0])["ended"]["how"], "quit")
        self.assertFalse((data / "run.json").exists())
        # the live test instance did not notice
        info = service.instance_info(service.Paths(self.inst.data), self.inst.port)
        self.assertTrue(info["healthy"])
        self.assertEqual(service.read_json(self.inst.data / "run.json"), live_run)
        self.assertEqual((self.inst.data / "service.log").read_text(encoding="utf-8").count("\n"), live_log_lines)
        # and dashboard/data/ is as it was
        self.assertEqual(live_data_snapshot(), live_before)

    def test_page_while_replaying(self):
        data = self.inst.dir / "replay-data"
        port = h.free_port()
        p = self.replay(h.RUN_A, "--minutes", "1", "--port", port, "--data", data, "--terminal", capture=False)
        try:
            self.assertTrue(h.wait_until(lambda: service.probe_health(port)[0] == "scdash", 20))
            status, _, body = h.request(port, "GET", "/")
            self.assertEqual(status, 200)
            self.assertIn(b'data-mode="replay"', body)
            self.assertIn(b'data-terminal="on"', body)
            st = h.wait_until(lambda: h.state(port), 10)
            self.assertEqual(st["service"]["mode"], "replay")
            self.assertGreater(st["clock"]["rate"], 1)
            self.assertEqual(st["service"]["replay"]["source"], "run_a.log")
            run = service.read_json(data / "run.json")
            self.assertTrue(service.ask_to_stop({"port": port, "run": run}, "test"))
            p.wait(20)
            self.assertEqual(p.returncode, 0)
        finally:
            if p.poll() is None:
                p.kill()

    def test_the_source_log_is_not_held_open(self):
        src = self.inst.dir / "Game.log"                    # stands for the live log during play
        src.write_bytes(h.RUN_A.read_bytes())
        data = self.inst.dir / "replay-data"
        port = h.free_port()
        p = self.replay(src, "--minutes", "1", "--port", port, "--data", data, capture=False)
        try:
            self.assertTrue(h.wait_until(lambda: service.probe_health(port)[0] == "scdash", 20))
            self.assertTrue((data / "replay" / "source.log").exists(), "it feeds from its own copy")
            moved = src.with_name("Game-moved.log")
            src.rename(moved)                               # fails on Windows if anything holds it open
            moved.unlink()
            run = service.read_json(data / "run.json")
            self.assertTrue(service.ask_to_stop({"port": port, "run": run}, "test"))
            p.wait(20)
        finally:
            if p.poll() is None:
                p.kill()

    def test_temporary_folder_is_removed(self):
        port = h.free_port()
        p = self.replay(h.RUN_A, "--speed", "5000", "--port", port, "--exit-at-end")
        out, err = p.communicate(timeout=60)
        self.assertEqual(p.returncode, 0, out + err)
        m = re.search(r"data (.+?) \(temporary\)", out)
        self.assertIsNotNone(m, out)
        self.assertFalse(Path(m.group(1)).exists())

    def test_refuses_the_live_port_and_the_live_data_folder(self):
        r = h.cli("replay", h.RUN_A, "--port", config.PORT)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("live port", r.stdout + r.stderr)
        before = live_data_snapshot()
        r = h.cli("replay", h.RUN_A, "--port", h.free_port(), "--data", config.DATA_DIR)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("live data folder", r.stdout + r.stderr)
        r = h.cli("replay", h.RUN_A, "--port", h.free_port(), "--data", config.DATA_DIR / "sub")
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(live_data_snapshot(), before)

    def test_refuses_to_write_through_a_junction(self):
        data = self.inst.dir / "replay-data"
        data.mkdir()
        outside = self.inst.dir / "outside"
        outside.mkdir()
        if not make_junction(data / "replay", outside):
            self.skipTest("no junction could be made here")
        r = h.cli("replay", h.RUN_A, "--port", h.free_port(), "--data", data, "--speed", "5000", "--exit-at-end")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("junction", r.stdout + r.stderr)
        self.assertEqual(os.listdir(outside), [], "nothing written through it")

    def test_not_a_session_log(self):
        with lib.TempDir() as d:
            p = d / "PSOCacheGen 1.log"
            p.write_bytes(lib.sample_bytes("run_a.log"))
            r = h.cli("replay", p, "--port", h.free_port())
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("shader-cache", r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
