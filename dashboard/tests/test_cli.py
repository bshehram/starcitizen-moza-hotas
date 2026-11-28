"""The service commands with real processes (PLAN §6, §7, §13 "Service"): `start` twice leaves
one instance, `stop` twice is clean, `run` refuses while an instance is healthy, a stale run.json
does not block a start, a program that is not the dashboard on the port is reported as such (even
one that claims to be it), a stop stays stopped, a service killed mid-session and started again
arrives at the same state and writes no summary twice, and a 100 MB flood does not grow the
running service's memory.

Each test uses a temporary data folder, a free port, a log of its own and a stand-in "game"
process with a made-up name; every process it starts is ended in tearDown."""
import http.server
import json
import os
import socket
import socketserver
import sys
import threading
import time
import unittest

import scdash_testlib as lib  # noqa: F401
import test_service_helpers as h
from scdash import service, winutil
from test_load import junk_block
from test_service import FIRST, UNSAFE, strings

FAST = {"process_check_seconds": 2.0, "poll_seconds": 0.25, "state_save_seconds": 2.0}   # the lowest allowed


class CliCase(unittest.TestCase):
    def setUp(self):
        self.inst = h.Instance()
        self.inst.data.mkdir(parents=True)
        service.write_json(self.inst.data / "config.json", dict(FAST, port=self.inst.port))
        self.servers = []
        self.games = []

    def tearDown(self):
        for g in self.games:
            g.stop()
        for s in self.servers:
            s.shutdown()
            s.server_close()
        self.inst.cleanup()

    def cli(self, *args, **kw):
        return h.cli(*args, **kw)

    def start(self, process="nosuchgame_%d.exe" % os.getpid()):
        return self.cli("start", *self.inst.args(process=process))

    def info(self):
        return service.instance_info(service.Paths(self.inst.data), self.inst.port)

    def game(self):
        g = h.FakeGame(self.inst.dir).start()
        self.games.append(g)
        return g

    def foreign(self, handler):
        srv = socketserver.TCPServer(("127.0.0.1", self.inst.port), handler)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.servers.append(srv)
        return srv


class StartStop(CliCase):
    def test_start_twice_leaves_one_instance(self):
        self.inst.write_log(h.log_bytes())
        a = self.start()
        self.assertEqual(a.returncode, 0, a.stdout + a.stderr)
        self.assertIn("Started", a.stdout)
        pid = self.info()["run"]["pid"]
        b = self.start()
        self.assertEqual(b.returncode, 0, b.stdout + b.stderr)
        self.assertIn("Already running: pid %d" % pid, b.stdout)
        self.assertTrue(self.info()["healthy"])
        self.assertEqual(self.info()["run"]["pid"], pid)
        same = [p for p, n in winutil.process_list() if n.lower() in ("pythonw.exe", "python.exe") and p == pid]
        self.assertEqual(len(same), 1)
        log = (self.inst.data / "service.log").read_text(encoding="utf-8")
        self.assertEqual(log.count("listening on"), 1)

    def test_two_starts_at_once_leave_one_instance(self):
        self.inst.write_log(h.log_bytes())
        out = []
        ts = [threading.Thread(target=lambda: out.append(self.start())) for _ in range(2)]
        for t in ts:
            t.start()
        for t in ts:
            t.join(60)
        self.assertEqual([r.returncode for r in out], [0, 0], [r.stdout + r.stderr for r in out])
        self.assertTrue(self.info()["healthy"])
        log = (self.inst.data / "service.log").read_text(encoding="utf-8")
        self.assertEqual(log.count("listening on"), 1)

    def test_stop_twice_is_clean(self):
        self.inst.write_log(h.log_bytes())
        self.assertEqual(self.start().returncode, 0)
        pid = self.info()["run"]["pid"]
        a = self.cli("stop", "--data", self.inst.data, "--port", self.inst.port)
        self.assertEqual(a.returncode, 0, a.stdout + a.stderr)
        self.assertIn("Stopped (pid %d)" % pid, a.stdout)
        self.assertTrue(h.wait_until(lambda: winutil.process_name(pid) is None, 10), "the process ended")
        self.assertFalse((self.inst.data / "run.json").exists())
        b = self.cli("stop", "--data", self.inst.data, "--port", self.inst.port)
        self.assertEqual(b.returncode, 0, b.stdout + b.stderr)
        self.assertIn("Not running", b.stdout)

    def test_run_refuses_while_an_instance_is_healthy(self):
        self.inst.write_log(h.log_bytes())
        self.assertEqual(self.start().returncode, 0)
        r = self.cli("run", *self.inst.args(), timeout=30)
        self.assertEqual(r.returncode, service.EXIT_RUNNING, r.stdout + r.stderr)
        self.assertIn("Already running", r.stdout)
        self.assertTrue(self.info()["healthy"])

    def test_a_stale_run_json_does_not_block_a_start(self):
        self.inst.write_log(h.log_bytes())
        service.write_json(self.inst.data / "run.json", {
            "program": "scdash", "pid": 4, "port": self.inst.port, "started": "2026-01-01T00:00:00.000Z",
            "token": "stale-token"})
        st = json.loads(self.cli("status", "--data", self.inst.data, "--json").stdout)
        self.assertFalse(st["running"])
        self.assertTrue(st["stale_run_json"])
        r = self.start()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        run = self.info()["run"]
        self.assertNotEqual(run["token"], "stale-token")
        self.assertTrue(self.info()["healthy"])

    def test_stop_with_a_stale_run_json_removes_it(self):
        service.write_json(self.inst.data / "run.json", {
            "program": "scdash", "pid": 4, "port": self.inst.port, "started": "2026-01-01T00:00:00.000Z",
            "token": "stale-token"})
        r = self.cli("stop", "--data", self.inst.data)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("stale run.json", r.stdout)
        self.assertFalse((self.inst.data / "run.json").exists())

    def test_a_stop_stays_stopped_until_start(self):
        self.inst.write_log(h.log_bytes())
        self.assertEqual(self.start().returncode, 0)
        self.assertEqual(self.cli("stop", "--data", self.inst.data).returncode, 0)
        self.assertTrue((self.inst.data / "stopped.json").exists())
        t0 = time.monotonic()
        r = self.cli("run", "--background", *self.inst.args(), timeout=30)   # what an automatic start runs
        self.assertEqual(r.returncode, 0)
        self.assertLess(time.monotonic() - t0, 10)
        self.assertFalse(self.info()["healthy"])
        self.assertIn("not starting: stopped on purpose", (self.inst.data / "service.log").read_text(encoding="utf-8"))
        r = self.start()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("Removed the stop marker", r.stdout)
        self.assertFalse((self.inst.data / "stopped.json").exists())

    def test_status_json(self):
        self.inst.write_log(h.log_bytes())
        self.assertEqual(self.start().returncode, 0)
        st = json.loads(self.cli("status", "--data", self.inst.data, "--json").stdout)
        self.assertTrue(st["running"])
        s = st["status"]
        for key in ("pid", "uptime_s", "port", "game", "log", "session", "memory", "cpu_s", "pages"):
            self.assertIn(key, s)
        self.assertNotIn("token", json.dumps(st))
        self.assertTrue(s["below_normal_priority"])
        self.assertFalse(s["game"]["running"])
        self.assertEqual(s["session"]["id"], "Build(13220821) 26 Nov 26 (15 11 12)")
        text = self.cli("status", "--data", self.inst.data).stdout
        self.assertIn("Running: pid %d" % st["pid"], text)
        self.assertIn("private working set", text)


class ForeignPort(CliCase):
    def test_a_foreign_program_on_the_port_is_reported(self):
        class Plain(http.server.SimpleHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"hello, not a dashboard")
        self.foreign(Plain)
        self.inst.write_log(h.log_bytes())
        r = self.start()
        self.assertEqual(r.returncode, service.EXIT_PORT, r.stdout + r.stderr)
        self.assertIn("taken by another program", r.stdout)
        self.assertNotIn("Already running", r.stdout)
        st = json.loads(self.cli("status", "--data", self.inst.data, "--port", self.inst.port, "--json").stdout)
        self.assertFalse(st["running"])
        self.assertEqual(st["port_user"], "foreign")
        r = self.cli("run", *self.inst.args(), timeout=30)
        self.assertEqual(r.returncode, service.EXIT_PORT)

    def test_a_program_claiming_to_be_the_dashboard_is_not_mistaken_for_it(self):
        class Liar(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                body = json.dumps({"program": "scdash", "pid": 4, "started": "2026-01-01T00:00:00.000Z"}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
        self.foreign(Liar)
        self.inst.write_log(h.log_bytes())
        r = self.start()
        self.assertEqual(r.returncode, service.EXIT_PORT, r.stdout + r.stderr)
        self.assertNotIn("Already running", r.stdout)
        self.assertFalse(self.info()["healthy"])
        r = self.cli("stop", "--data", self.inst.data, "--port", self.inst.port)
        self.assertEqual(r.returncode, 0)
        self.assertIn("Not running", r.stdout)


class Trust(CliCase):
    """run.json is trusted only as far as the live process confirms it."""

    def test_stop_never_touches_the_process_a_stale_run_json_names(self):
        bystander = self.game()                              # a live process that is not ours
        service.write_json(self.inst.data / "run.json", {
            "program": "scdash", "pid": bystander.proc.pid, "port": self.inst.port,
            "started": "2026-01-01T00:00:00.000Z", "token": "stale-token", "created": 1.0})
        r = self.cli("stop", "--data", self.inst.data)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("stale run.json", r.stdout)
        self.assertIsNone(bystander.proc.poll(), "the process run.json named is still running")
        self.assertTrue(winutil.process_running(bystander.name))

    def test_healthy_needs_both_the_pid_and_the_start_time(self):
        run = {"program": "scdash", "pid": os.getpid(), "port": self.inst.port,
               "started": "2026-11-27T20:00:00.000Z", "token": "t"}
        service.write_json(self.inst.data / "run.json", run)
        answer = {}

        class Health(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                body = json.dumps(answer).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
        self.foreign(Health)
        paths = service.Paths(self.inst.data)
        lock = paths.lock()
        self.assertTrue(lock.acquire())                      # stands for the live instance's own lock
        try:
            for pid, started, want in ((os.getpid(), "2026-11-27T21:00:00.000Z", False),
                                       (os.getpid() + 1, run["started"], False),
                                       (os.getpid(), run["started"], True)):
                answer.clear()
                answer.update(program="scdash", pid=pid, started=started)
                self.assertEqual(service.instance_info(paths, self.inst.port)["healthy"], want, (pid, started))
        finally:
            lock.release()
        # Review round 2: and with nobody holding the lock, the same answer is not ours.
        self.assertFalse(service.instance_info(paths, self.inst.port)["healthy"])

    def test_a_stale_run_json_cannot_be_impersonated(self):
        """With no instance holding this folder's lock, a program on run.json's port that repeats
        the health answer is not ours: status says not running, and stop sends it no token."""
        run = {"program": "scdash", "pid": 4, "port": self.inst.port, "started": "2026-11-27T20:00:00.000Z",
               "token": "the-dead-instance-token", "created": 1.0}
        service.write_json(self.inst.data / "run.json", run)
        seen = []

        class Mimic(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _ok(self, obj):
                body = json.dumps(obj).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                seen.append(("GET", self.path, self.headers.get("X-SCDash-Token")))
                self._ok({"program": "scdash", "pid": run["pid"], "started": run["started"]})

            def do_POST(self):
                seen.append(("POST", self.path, self.headers.get("X-SCDash-Token")))
                self._ok({"ok": True})
        self.foreign(Mimic)
        st = json.loads(self.cli("status", "--data", self.inst.data, "--json").stdout)
        self.assertFalse(st["running"])
        self.assertEqual(st["port_user"], "foreign")
        self.assertIn("Not running", self.cli("status", "--data", self.inst.data).stdout)
        r = self.cli("stop", "--data", self.inst.data, "--wait", "2")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("stale run.json", r.stdout)
        self.assertEqual([x for x in seen if x[0] != "GET"], [], "no shutdown asked of it")
        self.assertEqual([x for x in seen if x[2]], [], "and no token sent to it")

    @unittest.skipUnless(winutil.IS_WINDOWS, "suspends a process through ntdll")
    def test_a_hung_instance_is_reported_as_ours_and_left_alone(self):
        import ctypes
        self.inst.write_log(h.log_bytes())
        proc = self.inst.spawn(process="nosuchgame.exe")      # our child: we hold its handle
        run = service.read_json(self.inst.data / "run.json")
        self.assertIsInstance(run.get("created"), float)
        self.assertEqual(run["pid"], proc.pid)
        ntdll = ctypes.WinDLL("ntdll")
        handle = ctypes.c_void_p(int(proc._handle))           # the handle Popen created it with
        ntdll.NtSuspendProcess(handle)
        try:
            st = json.loads(self.cli("status", "--data", self.inst.data, "--json", timeout=60).stdout)
            self.assertTrue(st["hung"])
            self.assertFalse(st["running"])
            self.assertFalse(st["stale_run_json"])
            text = self.cli("status", "--data", self.inst.data, timeout=60).stdout
            self.assertIn("Running but not answering: pid %d" % run["pid"], text)
            self.assertNotIn("used by another program", text)
            self.assertNotIn("stale", text)
            self.assertEqual(self.cli("stop", "--data", self.inst.data, "--wait", "2", timeout=60).returncode, 1)
            self.assertEqual(self.cli("start", *self.inst.args(process="nosuchgame.exe"), "--wait", "2",
                                      timeout=60).returncode, 1)
            self.assertIsNotNone(winutil.process_name(run["pid"]), "neither command ended it")
        finally:
            ntdll.NtResumeProcess(handle)
        self.assertTrue(h.wait_until(lambda: self.info()["healthy"], 10))


class KillAndRestart(CliCase):
    def test_killed_mid_session_restarts_to_the_same_state_and_writes_no_summary_twice(self):
        whole = h.without_quit(h.log_bytes())               # the game will "crash" at the end
        part1 = whole[:whole.rfind(b"\n", 0, len(whole) // 2) + 1]
        self.inst.write_log(part1)
        game = self.game()
        first = self.inst.spawn(process=game.name)           # a child of the test, so it can crash it
        port = self.inst.port
        self.assertTrue(h.wait_until(lambda: (h.status(port) or {}).get("log", {}).get("offset") == len(part1), 15))
        self.inst.write_log(whole[len(part1):], "ab")
        self.assertTrue(h.wait_until(lambda: (h.status(port) or {}).get("log", {}).get("offset") == len(whole), 15))
        self.assertTrue(h.wait_until(lambda: h.status(port)["game"]["running"], 5))
        before = h.state(port)["state"]
        pid1 = self.inst.crash(first)                        # killed: no clean shutdown
        self.assertTrue((self.inst.data / "run.json").exists(), "a kill leaves run.json behind")
        second = self.inst.spawn(process=game.name)
        self.assertNotEqual(self.info()["run"]["pid"], pid1)
        self.assertTrue(h.wait_until(lambda: (h.status(port) or {}).get("log", {}).get("offset") == len(whole), 15))
        after = h.state(port)["state"]
        self.assertEqual(before, after)
        sessions = self.inst.data / "sessions"
        self.assertEqual(list(sessions.glob("*.json")) if sessions.is_dir() else [], [])
        game.stop()                                          # the game goes away with no quit line
        self.assertTrue(h.wait_until(lambda: sessions.is_dir() and len(list(sessions.glob("*.json"))) == 1, 15))
        sm = service.read_json(next(sessions.glob("*.json")))
        self.assertEqual(sm["ended"]["how"], "no quit line (crash or kill)")
        payload = h.state(port)
        self.assertFalse(payload["service"]["game_running"])
        self.assertIsNotNone(payload["clock"]["session_end"])
        self.inst.crash(second)                              # killed again, then started with no game
        self.assertEqual(self.start().returncode, 0)
        self.assertTrue(h.wait_until(lambda: (h.status(port) or {}).get("log", {}).get("status") == "idle", 15))
        self.assertEqual(len(list(sessions.glob("*.json"))), 1)
        self.assertEqual(h.status(port)["summaries_written"], 0)


class StatusText(CliCase):
    def test_status_prints_no_control_text_from_the_log(self):
        """The session id is the log's first line: escapes in it (a window title, a cleared
        screen, a C1 CSI, a bidi override) reach neither the console nor --json."""
        first = FIRST.replace(b"Build(13220821) ", b"Build(13220821) \x1b]0;OWNED\x07\x1b[2J\xc2\x9b31m\xe2\x80\xaeRED ")
        self.inst.write_log(first + h.log_bytes().split(b"\n", 1)[1])
        self.assertEqual(self.start().returncode, 0)
        text = self.cli("status", "--data", self.inst.data).stdout
        self.assertIn("OWNED", text)
        self.assertIsNone(UNSAFE.search(text.replace("\n", "")), repr(text))
        raw = self.cli("status", "--data", self.inst.data, "--json").stdout
        self.assertIsNone(UNSAFE.search(raw.replace("\n", "")))
        st = json.loads(raw)
        self.assertIn("OWNED", st["status"]["session"]["id"])
        self.assertEqual([x for x in strings(st) if UNSAFE.search(x)], [])


class HeadFlood(CliCase):
    def test_huge_request_heads_cost_little_and_leave_no_memory_behind(self):
        """Review round 2: two local clients without the token sending the largest heads the
        standard library takes (100 lines of 64 KB, 6.5 MB) cost 8.5 s of CPU in 10 s, and 9 MB
        that stayed. Now a head is cut off at 16 KB."""
        self.inst.write_log(h.log_bytes())
        self.assertEqual(self.start().returncode, 0)
        port = self.inst.port
        time.sleep(1.0)
        before = h.status(port)
        line = b"X-A: " + b"a" * 65000 + b"\r\n"
        data = b"GET / HTTP/1.0\r\nHost: 127.0.0.1:%d\r\n" % port + line * 99 + b"\r\n"
        stop = threading.Event()

        def one():
            while not stop.is_set():
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=5) as s:
                        s.sendall(data)
                        while s.recv(65536):
                            pass
                except OSError:
                    pass
        ts = [threading.Thread(target=one) for _ in range(2)]
        for t in ts:
            t.start()
        time.sleep(4.0)
        stop.set()
        for t in ts:
            t.join(15)
        time.sleep(1.0)
        after = h.status(port)
        cpu = after["cpu_s"] - before["cpu_s"]
        heads = (after["requests"] + after["refused"]) - (before["requests"] + before["refused"])
        grow = (after["memory"]["private_ws"] or after["memory"]["working_set"]) - \
            (before["memory"]["private_ws"] or before["memory"]["working_set"])
        sys.stderr.write("\n[4 s of 6.5 MB heads from 2 clients: %d heads, CPU +%.2f s (%.2f ms each), private "
                         "working set %+.1f MB]\n" % (heads, cpu, 1000 * cpu / max(1, heads), grow / 1e6))
        self.assertGreater(heads, 0)
        # Per head, since the cost of a connection flood follows the rate the client keeps up:
        # it was about 16 ms for a 6.5 MB head (8.5 s for 519 of them).
        self.assertLess(cpu / heads, 0.002, "CPU per head")
        self.assertLess(grow, 3e6, "memory grew by %.1f MB" % (grow / 1e6))


class Flood(CliCase):
    def test_a_100_mb_flood_does_not_grow_the_running_service(self):
        mb = int(os.environ.get("SCDASH_FLOOD_MB", "100"))
        head = h.log_bytes(0.3)
        self.inst.write_log(head)
        game = self.game()
        self.assertEqual(self.start(process=game.name).returncode, 0)
        port = self.inst.port
        self.assertTrue(h.wait_until(lambda: (h.status(port) or {}).get("log", {}).get("offset") == len(head), 15))
        time.sleep(1.0)
        before = h.status(port)["memory"]
        events = h.status(port)["session"]["events"]
        block = junk_block(1 << 20)
        with open(self.inst.log, "ab") as f:                 # appended while the service follows the log
            for _ in range(mb):
                f.write(block)
        total = len(head) + mb * len(block)
        t0 = time.monotonic()
        self.assertTrue(h.wait_until(lambda: (h.status(port) or {}).get("log", {}).get("offset") == total, 120, 0.25))
        took = time.monotonic() - t0
        after = h.status(port)["memory"]
        self.assertEqual(h.status(port)["session"]["events"], events, "junk is not an event")
        grow = (after["private_ws"] or after["working_set"]) - (before["private_ws"] or before["working_set"])
        sys.stderr.write("\n[flood %d MB read in %.1f s: private working set %.1f -> %.1f MB, peak working set "
                         "%.1f MB]\n" % (mb, took, (before["private_ws"] or 0) / 1e6, (after["private_ws"] or 0) / 1e6,
                                         (after["peak_working_set"] or 0) / 1e6))
        self.assertLess(grow, 6e6, "memory grew by %.1f MB" % (grow / 1e6))


if __name__ == "__main__":
    unittest.main()
