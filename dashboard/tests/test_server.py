"""The web server and its request guard (PLAN §8, §13 "Server"), in process, on a free port.

Every request is refused unless its Host is this server, reads included; a changing request
also needs the token, a JSON body and this server's Origin; no path from a request opens a file;
the health check does not carry the token; and the event stream merges, keeps alive, caps."""
import json
import logging
import os
import re
import shutil
import socket
import tempfile
import threading
import time
import unittest
from pathlib import Path
from urllib.parse import quote

import scdash_testlib as lib  # noqa: F401  (puts dashboard/ on sys.path)
import test_service_helpers as h
from unittest import mock

from scdash import config, server, winutil
from scdash.server import CHANGE, PRIVATE, READ, Hub, Server
from test_service import make_junction

TOKEN = "test-token-not-secret-0123456789abcdef"


class ServerCase(unittest.TestCase):
    def setUp(self):
        self.hub = Hub("state", min_interval=0.5, keepalive=0.4, retry_ms=1234, max_clients=2)
        self.srv = Server(h.free_port(), TOKEN, page_vars={"terminal": "off", "mode": "live", "instance": "1/x"}, poll_interval=0.05)
        self.calls = []
        self.srv.route("GET", "/api/health", lambda r: (200, {"program": "scdash", "pid": 1, "started": "x"}), READ)
        self.srv.route("POST", "/api/shutdown", self._change, CHANGE)
        self.srv.route("GET", "/api/private", lambda r: (200, {"ok": True}), PRIVATE)
        self.srv.stream("/api/stream", self.hub, READ)
        self.private_hub = Hub("out", min_interval=0.05, keepalive=0.4, retry_ms=1000, max_clients=1)
        self.srv.stream("/api/private-stream", self.private_hub, PRIVATE)
        self.srv.start()
        self.port = self.srv.port
        self.origin = "http://127.0.0.1:%d" % self.port

    def tearDown(self):
        self.srv.stop()

    def _change(self, req):
        self.calls.append(req.json)
        return 200, {"ok": True}

    def post(self, body=None, headers=None, raw=None, host=None):
        hdr = {"Content-Type": "application/json", "Origin": self.origin, server.TOKEN_HEADER: TOKEN}
        hdr.update(headers or {})
        hdr = {k: v for k, v in hdr.items() if v is not None}
        return h.request(self.port, "POST", "/api/shutdown", hdr, raw if raw is not None else (body or {}), host=host)


class HostCheck(ServerCase):
    def test_own_hosts_are_served(self):
        for host in ("127.0.0.1:%d" % self.port, "localhost:%d" % self.port, "LOCALHOST:%d" % self.port):
            status, _, _ = h.request(self.port, "GET", "/api/health", host=host)
            self.assertEqual(status, 200, host)

    def test_foreign_hosts_are_refused_on_every_route(self):
        bad = ["evil.example", "evil.example:%d" % self.port, "127.0.0.1", "127.0.0.1:%d" % (self.port + 1),
               "localhost.:%d" % self.port, "127.0.0.2:%d" % self.port, "user@127.0.0.1:%d" % self.port,
               "[::1]:%d" % self.port, ""]
        for path in ("/", "/app.js", "/style.css", "/api/health", "/api/stream", "/api/private", "/nope"):
            for host in bad:
                status, _, body = h.request(self.port, "GET", path, host=host)
                self.assertEqual(status, 403, (path, host))
                self.assertNotIn(TOKEN.encode(), body)
        status, _, _ = self.post(host="evil.example:%d" % self.port)
        self.assertEqual(status, 403)
        self.assertEqual(self.calls, [])

    def test_missing_or_doubled_host_is_refused(self):
        status, _, _ = h.request(self.port, "GET", "/api/health", host=False)
        self.assertEqual(status, 403)
        own = "127.0.0.1:%d" % self.port
        status, _, _ = h.request(self.port, "GET", "/api/health", headers={"Host": own})   # two Host lines
        self.assertEqual(status, 403)

    def test_absolute_target_is_refused(self):
        status, _, _ = h.request(self.port, "GET", "http://127.0.0.1:%d/api/health" % self.port)
        self.assertIn(status, (400, 404))

    def test_other_methods_are_checked_and_refused(self):
        for m in ("PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"):
            status, _, _ = h.request(self.port, m, "/api/health", host="evil.example")
            self.assertEqual(status, 403, m)
            status, _, _ = h.request(self.port, m, "/api/health")
            self.assertEqual(status, 405, m)
        status, _, _ = h.request(self.port, "POST", "/api/health", body={})
        self.assertEqual(status, 405)
        status, _, _ = h.request(self.port, "GET", "/api/shutdown")
        self.assertEqual(status, 405)


class ChangingRequests(ServerCase):
    def test_the_proper_request_works(self):
        status, _, _ = self.post({"reason": "test"})
        self.assertEqual(status, 200)
        self.assertEqual(self.calls, [{"reason": "test"}])

    def test_localhost_origin_works_too(self):
        status, _, _ = self.post(headers={"Origin": "http://localhost:%d" % self.port})
        self.assertEqual(status, 200)

    def test_token_missing_or_wrong(self):
        for tok in (None, "", "wrong", TOKEN + "x", TOKEN[:-1], TOKEN.upper()):
            status, _, _ = self.post(headers={server.TOKEN_HEADER: tok})
            self.assertEqual(status, 403, tok)
        self.assertEqual(self.calls, [])

    def test_token_in_the_query_is_not_enough(self):
        hdr = {"Content-Type": "application/json", "Origin": self.origin}
        status, _, _ = h.request(self.port, "POST", "/api/shutdown?token=" + TOKEN, hdr, {})
        self.assertEqual(status, 403)

    def test_origin_missing_foreign_or_null(self):
        for origin in (None, "http://evil.example", "null", "http://127.0.0.1:%d" % (self.port + 1),
                       "https://127.0.0.1:%d" % self.port, "http://127.0.0.1"):
            status, _, _ = self.post(headers={"Origin": origin})
            self.assertEqual(status, 403, origin)
        status, _, _ = self.post(headers={"Sec-Fetch-Site": "cross-site"})
        self.assertEqual(status, 403)
        self.assertEqual(self.calls, [])

    def test_body_must_be_json(self):
        status, _, _ = self.post(headers={"Content-Type": "text/plain"})
        self.assertEqual(status, 415)
        status, _, _ = self.post(headers={"Content-Type": "application/x-www-form-urlencoded"}, raw=b"a=1")
        self.assertEqual(status, 415)
        status, _, _ = self.post(raw=b"not json")
        self.assertEqual(status, 400)
        status, _, _ = self.post(raw=b"[1, 2]")
        self.assertEqual(status, 400)
        status, _, _ = self.post(raw=b"\xff\xfe")
        self.assertEqual(status, 400)
        self.assertEqual(self.calls, [])

    def test_length_must_be_ascii_digits(self):
        hdr = "POST /api/shutdown HTTP/1.0\r\nHost: 127.0.0.1:%d\r\nContent-Type: application/json\r\n" \
              "Origin: %s\r\n%s: %s\r\n" % (self.port, self.origin, server.TOKEN_HEADER, TOKEN)
        for length in ("\u00b2", "\u0662", "+2", "-1", "2 2", "0x2", "1e1"):
            raw = (hdr + "Content-Length: " + length + "\r\n\r\n{}").encode("utf-8")
            status, _, _ = h.raw_request(self.port, raw)
            self.assertEqual(status, 411, repr(length))
        self.assertEqual(self.calls, [])

    def test_length_required_and_bounded(self):
        hdr = "POST /api/shutdown HTTP/1.0\r\nHost: 127.0.0.1:%d\r\nContent-Type: application/json\r\n" \
              "Origin: %s\r\n%s: %s\r\n" % (self.port, self.origin, server.TOKEN_HEADER, TOKEN)
        status, _, _ = h.raw_request(self.port, (hdr + "\r\n{}").encode())
        self.assertEqual(status, 411)
        status, _, _ = h.raw_request(self.port, (hdr + "Content-Length: 99999999\r\n\r\n{}").encode())
        self.assertEqual(status, 413)
        self.assertEqual(self.calls, [])

    def test_a_route_registered_later_gets_the_same_guard(self):
        got = []
        self.srv.route("POST", "/api/later", lambda r: (got.append(r.json) or (200, {})), CHANGE)
        hdr = {"Content-Type": "application/json", "Origin": self.origin}
        status, _, _ = h.request(self.port, "POST", "/api/later", hdr, {})
        self.assertEqual(status, 403)
        hdr[server.TOKEN_HEADER] = TOKEN
        status, _, _ = h.request(self.port, "POST", "/api/later", hdr, {"x": 1})
        self.assertEqual(status, 200)
        self.assertEqual(got, [{"x": 1}])

    def test_a_changing_route_cannot_be_registered_without_the_token(self):
        with self.assertRaises(ValueError):
            self.srv.route("POST", "/api/oops", lambda r: (200, {}), READ)
        with self.assertRaises(ValueError):
            self.srv.route("GET", "/api/oops", lambda r: (200, {}), CHANGE)

    def test_private_read_needs_the_token_header_and_same_origin(self):
        ok = {server.TOKEN_HEADER: TOKEN, "Sec-Fetch-Site": "same-origin"}
        status, _, _ = h.request(self.port, "GET", "/api/private", ok)
        self.assertEqual(status, 200)
        for hdr in ({}, {server.TOKEN_HEADER: TOKEN}, {"Sec-Fetch-Site": "same-origin"},
                    {server.TOKEN_HEADER: "wrong", "Sec-Fetch-Site": "same-origin"},
                    {server.TOKEN_HEADER: TOKEN, "Sec-Fetch-Site": "none"},
                    {server.TOKEN_HEADER: TOKEN, "Sec-Fetch-Site": "cross-site"}):
            status, _, _ = h.request(self.port, "GET", "/api/private", hdr)
            self.assertEqual(status, 403, hdr)
        status, _, _ = h.request(self.port, "GET", "/api/private?token=" + TOKEN, {"Sec-Fetch-Site": "same-origin"})
        self.assertEqual(status, 403, "a token in the URL is not accepted")
        status, _, _ = h.request(self.port, "GET", "/api/private", ok, host="evil.example")
        self.assertEqual(status, 403)

    def test_doubled_token_or_foreign_origin_is_refused(self):
        head = "GET /api/private HTTP/1.0\r\nHost: 127.0.0.1:%d\r\nSec-Fetch-Site: same-origin\r\n" % self.port
        two = head + "%s: wrong\r\n%s: %s\r\n\r\n" % (server.TOKEN_HEADER, server.TOKEN_HEADER, TOKEN)
        self.assertEqual(h.raw_request(self.port, two.encode())[0], 403)
        one = head + "%s: %s\r\nOrigin: http://evil.example\r\n\r\n" % (server.TOKEN_HEADER, TOKEN)
        self.assertEqual(h.raw_request(self.port, one.encode())[0], 403)
        own = head + "%s: %s\r\nOrigin: %s\r\n\r\n" % (server.TOKEN_HEADER, TOKEN, self.origin)
        self.assertEqual(h.raw_request(self.port, own.encode())[0], 200)
        status, _, _ = h.request(self.port, "GET", "/api/health", {"Origin": "http://evil.example"})
        self.assertEqual(status, 403)

    def test_every_registration_names_its_guard(self):
        with self.assertRaises(TypeError):
            self.srv.stream("/api/oops", Hub())               # no default guard
        with self.assertRaises(TypeError):
            self.srv.route("GET", "/api/oops", lambda r: (200, {}))
        with self.assertRaises(TypeError):
            self.srv.route("GET", "/api/oops", lambda r: (200, {}), None)


class FetchSite(ServerCase):
    def test_only_same_origin_or_none_is_accepted_on_every_route(self):
        for site, want in (("same-origin", 200), ("none", 200), ("same-site", 403), ("cross-site", 403),
                           ("CROSS-SITE", 403), ("bogus", 403)):
            status, _, _ = h.request(self.port, "GET", "/api/health", {"Sec-Fetch-Site": site})
            self.assertEqual(status, want, site)
            status, _, _ = h.request(self.port, "GET", "/", {"Sec-Fetch-Site": site})
            self.assertEqual(status, want, site)
        status, _, _ = self.post(headers={"Sec-Fetch-Site": "same-site"})
        self.assertEqual(status, 403)


class Deadline(ServerCase):
    def test_a_trickling_request_head_is_cut_and_frees_its_slot(self):
        with mock.patch.object(config, "REQUEST_TIMEOUT", 1.5):
            slow = []
            for _ in range(config.MAX_CONNECTIONS):             # every request slot taken
                s = socket.create_connection(("127.0.0.1", self.port), timeout=10)
                s.sendall(b"GET /api/health HTTP/1.0\r\n")
                slow.append(s)
            t0 = time.monotonic()
            try:
                for _ in range(4):                               # one byte every 0.5 s: no read times out
                    time.sleep(0.5)
                    for s in slow:
                        try:
                            s.sendall(b"X")
                        except OSError:
                            pass
                got = h.wait_until(lambda: h.request(self.port, "GET", "/api/health")[0] == 200, 8, 0.2)
                self.assertTrue(got, "the health check gets through once the deadline cut the slow ones")
                self.assertLess(time.monotonic() - t0, 6)
                for s in slow:                                   # the server closed them
                    s.settimeout(3)
                    try:
                        self.assertEqual(s.recv(100), b"")
                    except (ConnectionResetError, ConnectionAbortedError):
                        pass
            finally:
                for s in slow:
                    s.close()


class HeadLimits(ServerCase):
    """Review round 2: a request head is capped at 16 KB and 40 header lines, refused as soon as
    it goes over, before the rest of it is read (the standard library alone takes 100 lines of
    64 KB, and two clients sending that cost 8 s of CPU in 10 s and 10 MB that stayed)."""

    def head(self, extra):
        return ("GET /api/health HTTP/1.0\r\nHost: 127.0.0.1:%d\r\n%s\r\n" % (self.port, extra)).encode("latin-1")

    def test_a_head_over_16_kb_is_refused(self):
        status, _, body = h.raw_request(self.port, self.head("X-Big: %s\r\n" % ("a" * 17000)))
        self.assertEqual(status, 431)
        self.assertIn(b"too large", body)
        self.assertEqual(self.srv.requests, 0, "no route ran")

    def test_more_than_40_header_lines_are_refused(self):
        many = "".join("X-H%d: v\r\n" % i for i in range(40))     # with Host, 41 header lines
        status, _, _ = h.raw_request(self.port, self.head(many))
        self.assertEqual(status, 431)
        self.assertEqual(self.srv.requests, 0)

    def test_a_head_within_the_limits_is_served(self):
        lines = "".join("X-H%d: v\r\n" % i for i in range(39))     # with Host, 40 header lines
        self.assertEqual(h.raw_request(self.port, self.head(lines))[0], 200)
        self.assertEqual(h.raw_request(self.port, self.head("X-Big: %s\r\n" % ("a" * 16000)))[0], 200)

    def test_a_huge_head_is_cut_off_early(self):
        line = b"X-A: " + b"a" * 65000 + b"\r\n"
        data = b"GET /api/health HTTP/1.0\r\nHost: 127.0.0.1:%d\r\n" % self.port + line * 99 + b"\r\n"
        sent, err = 0, None
        with socket.create_connection(("127.0.0.1", self.port), timeout=10) as s:
            try:
                for i in range(0, len(data), 65536):              # 6.5 MB, the way the stdlib allows
                    s.sendall(data[i:i + 65536])
                    sent += 65536
            except OSError as e:
                err = e
        self.assertIsNotNone(err, "the server stopped reading long before 6.5 MB")
        self.assertLess(sent, 2 << 20)
        self.assertEqual(self.srv.requests, 0)


class WaitingConnections(ServerCase):
    """Review round 2: a connection takes one of the 16 worker slots only once its whole head is
    in, within its limits and with a right Host. One that sends nothing is dropped after a second;
    at most MAX_WAITING wait, and over that the oldest goes."""

    def idle(self, n):
        out = []
        for _ in range(n):
            out.append(socket.create_connection(("127.0.0.1", self.port), timeout=10))
        return out

    def closed_by_server(self, s, within):
        s.settimeout(within)
        try:
            return s.recv(100) == b""
        except (ConnectionResetError, ConnectionAbortedError):
            return True
        except socket.timeout:
            return False

    def test_idle_connections_take_no_worker_slot(self):
        idle = self.idle(40)                                    # more than the 16 slots
        try:
            time.sleep(0.2)
            t0 = time.monotonic()
            status, _, _ = h.request(self.port, "GET", "/api/health")
            self.assertEqual(status, 200)
            self.assertLess(time.monotonic() - t0, 0.8, "served at once, not after a deadline")
            t0 = time.monotonic()
            self.assertTrue(all(self.closed_by_server(s, 3) for s in idle), "silent ones are dropped")
            self.assertLess(time.monotonic() - t0, 2.5, "within about a second")
        finally:
            for s in idle:
                s.close()

    def test_over_the_cap_the_oldest_waiting_connection_is_dropped(self):
        with mock.patch.object(config, "MAX_WAITING", 8, create=True), \
                mock.patch.object(config, "FIRST_BYTE_TIMEOUT", 20.0, create=True):
            conns = []
            try:
                for _ in range(12):
                    conns.extend(self.idle(1))
                    time.sleep(0.05)                            # in a known order
                self.assertTrue(all(self.closed_by_server(s, 2) for s in conns[:4]), "the 4 oldest went")
                self.assertFalse(any(self.closed_by_server(s, 0.3) for s in conns[4:]), "the 8 newest wait")
                self.assertEqual(h.request(self.port, "GET", "/api/health")[0], 200)
            finally:
                for s in conns:
                    s.close()

    def test_a_wrong_host_is_refused_before_it_takes_a_slot(self):
        busy = []
        head = ("POST /api/shutdown HTTP/1.0\r\nHost: 127.0.0.1:%d\r\nContent-Type: application/json\r\n"
                "Origin: %s\r\n%s: %s\r\nContent-Length: 50\r\n\r\n" % (self.port, self.origin, server.TOKEN_HEADER, TOKEN))
        try:
            for _ in range(config.MAX_CONNECTIONS):            # each worker waits for a body that never comes
                s = socket.create_connection(("127.0.0.1", self.port), timeout=10)
                s.sendall(head.encode())
                busy.append(s)
            time.sleep(0.3)
            t0 = time.monotonic()
            status, _, body = h.request(self.port, "GET", "/api/health", host="evil.example")
            self.assertEqual(status, 403, "refused at once, though no worker is free")
            self.assertIn(b"wrong host", body)
            self.assertEqual(h.request(self.port, "GET", "/api/health")[0], 503, "a right one: busy, said so")
            self.assertLess(time.monotonic() - t0, 1.0)
        finally:
            for s in busy:
                s.close()
        self.assertTrue(h.wait_until(lambda: h.request(self.port, "GET", "/api/health")[0] == 200, 5),
                        "the slots come back when those connections go")
        self.assertEqual(self.calls, [])


class GuardSmallOnes(ServerCase):
    """Review round 2: a doubled Content-Type is refused like every other doubled header, and a
    deeply nested body is a client's mistake (400), not the server's (500)."""

    def test_a_doubled_content_type_is_refused(self):
        raw = ("POST /api/shutdown HTTP/1.0\r\nHost: 127.0.0.1:%d\r\nContent-Type: application/json\r\n"
               "Content-Type: text/plain\r\nOrigin: %s\r\n%s: %s\r\nContent-Length: 2\r\n\r\n{}"
               % (self.port, self.origin, server.TOKEN_HEADER, TOKEN))
        self.assertEqual(h.raw_request(self.port, raw.encode())[0], 415)
        self.assertEqual(self.calls, [])

    def test_a_deeply_nested_body_is_a_400(self):
        body = b'{"a":' + b"[" * 30000 + b"]" * 30000 + b"}"
        status, _, _ = self.post(raw=body)
        self.assertEqual(status, 400)
        self.assertEqual(self.calls, [])


class FrontEndFaults(unittest.TestCase):
    """Fix round 2: a failure in the front end's turn shows in the file log (WARNING, which it
    keeps), the first in full and then a line at most every FAULT_REPORT_SECONDS with a count,
    so a fault that repeats every turn is seen and cannot fill the log."""

    def test_a_repeating_fault_is_logged_at_warning_and_rate_limited(self):
        records = []

        class Grab(logging.Handler):
            def emit(self, record):
                records.append(record)
        lg = logging.getLogger("scdash-test-frontend-%x" % id(self))
        lg.setLevel(logging.DEBUG)
        lg.propagate = False
        lg.addHandler(Grab())
        calls = [0]

        def broken():
            calls[0] += 1
            raise RuntimeError("broken turn")
        with mock.patch.object(server, "FAULT_REPORT_SECONDS", 0.5, create=True):
            srv = Server(h.free_port(), TOKEN, logger=lg, poll_interval=0.05)
            srv.route("GET", "/api/health", lambda r: (200, {}), READ)
            srv.start()
            try:
                fe = srv._httpd
                real = fe._turn
                fe._turn = broken
                time.sleep(1.3)
                fe._turn = real
                self.assertTrue(fe._thread.is_alive(), "an ordinary fault does not end it")
                self.assertEqual(h.request(srv.port, "GET", "/api/health")[0], 200)
            finally:
                srv.stop()
        warnings = [r.getMessage() for r in records if r.levelno >= logging.WARNING]
        self.assertGreater(calls[0], 10, "it failed every turn")
        self.assertIn("broken turn", warnings[0] if warnings else "", "the first, in full")
        self.assertGreaterEqual(len(warnings), 2)
        self.assertLessEqual(len(warnings), 5, "then a line every 0.5 s at most: %d" % len(warnings))
        self.assertRegex(warnings[1], r"failed \d+ more time")


class Counters(unittest.TestCase):
    def test_no_count_is_lost_between_the_front_end_and_the_workers(self):
        """Fix round 2: `refused` is counted in the front end and in every worker. Here reading
        the counter can be interrupted (as in a build without the GIL); an unguarded `+= 1` then
        loses counts, the lock does not."""
        class SlowRead(Server):
            @property
            def refused(self):
                v = self._refused_v
                time.sleep(0.0005)
                return v

            @refused.setter
            def refused(self, v):
                self._refused_v = v
        srv = SlowRead(h.free_port(), TOKEN, poll_interval=0.05)
        srv.route("POST", "/api/x", lambda r: (200, {}), CHANGE)
        srv.start()
        origin = "http://127.0.0.1:%d" % srv.port
        try:
            def client(i):
                for j in range(25):
                    if (i + j) % 2:                              # refused by the front end
                        h.request(srv.port, "GET", "/api/x", host="evil.example")
                    else:                                        # refused by a worker
                        h.request(srv.port, "POST", "/api/x", {"Content-Type": "application/json",
                                                               "Origin": origin, server.TOKEN_HEADER: "wrong"}, {})
            ts = [threading.Thread(target=client, args=(i,)) for i in range(8)]
            for t in ts:
                t.start()
            for t in ts:
                t.join(60)
            self.assertTrue(h.wait_until(lambda: srv.refused >= 200, 3))
            self.assertEqual(srv.refused, 200)
        finally:
            srv.stop()


class FilesAndToken(ServerCase):
    def test_page_carries_the_token_and_a_strict_policy(self):
        status, hdr, body = h.request(self.port, "GET", "/")
        self.assertEqual(status, 200)
        self.assertIn(('content="%s"' % TOKEN).encode(), body)
        self.assertIn(b'data-terminal="off"', body)
        self.assertNotIn(b"__SCDASH_", body)
        self.assertIn("default-src 'none'", hdr.get("content-security-policy", ""))
        self.assertIn("frame-ancestors 'none'", hdr.get("content-security-policy", ""))
        self.assertEqual(hdr.get("x-content-type-options"), "nosniff")
        self.assertNotIn("access-control-allow-origin", hdr)

    def test_nothing_but_the_page_carries_the_token(self):
        for path in ("/api/health", "/app.js", "/style.css", "/nope", "/api/stream?x"):
            if path.startswith("/api/stream"):
                continue
            status, hdr, body = h.request(self.port, "GET", path)
            self.assertNotIn(TOKEN.encode(), body, path)
            self.assertNotIn(TOKEN, json.dumps(hdr), path)
        status, _, body = h.request(self.port, "GET", "/api/health")
        self.assertEqual(json.loads(body), {"program": "scdash", "pid": 1, "started": "x"})

    def test_no_path_from_a_request_opens_a_file(self):
        for path in ("/index.html", "/web/index.html", "/../scdash/server.py", "/%2e%2e/scdash.py",
                     "/..%2fscdash.py", "/app.js/../../scdash.py", "//etc/passwd", "/C:/Windows/win.ini",
                     "/scdash.py", "/config.example.json", "/data/run.json", "/style.css%00.html"):
            status, _, body = h.request(self.port, "GET", path)
            self.assertEqual(status, 404, path)
            self.assertNotIn(b"import", body)
        status, hdr, _ = h.request(self.port, "GET", "/app.js?v=1")
        self.assertEqual(status, 200)
        self.assertIn("javascript", hdr["content-type"])

    def test_page_vars_are_escaped(self):
        self.srv.page_vars["mode"] = '"><script>x</script>'
        _, _, body = h.request(self.port, "GET", "/")
        self.assertNotIn(b"<script>x</script>", body)


class RigFiles(ServerCase):
    """The rig reference's data and images (PLAN §4 item 18) are served from what web/rig/ holds
    when the server is made, by a strict name rule: with their types, the same bytes as on disk,
    no token in them, and nothing else under /rig/. The image set changes with the cards, so
    nothing here names an image."""

    @staticmethod
    def expected():
        """web/rig/ by the rule, written out here on its own: rig.json, and lower-case ASCII
        letters, digits and underscores with .png, plain files."""
        out = {}
        for name in os.listdir(config.WEB_DIR / "rig"):
            p = config.WEB_DIR / "rig" / name
            if not p.is_file() or p.is_symlink():
                continue
            if name == "rig.json":
                out["/rig/" + name] = "application/json; charset=utf-8"
            elif re.fullmatch(r"[a-z0-9_]{1,48}\.png", name, re.ASCII):
                out["/rig/" + name] = "image/png"
        return out

    def test_each_is_served_with_its_type(self):
        rig = self.expected()
        self.assertIn("/rig/rig.json", rig)
        self.assertGreaterEqual(sum(1 for c in rig.values() if c == "image/png"), 1)
        self.assertEqual({p for p in self.srv.files if p.startswith("/rig/")}, set(rig))
        self.assertEqual({p for p in server.FILES}, {"/", "/app.js", "/style.css"}, "no image is named in code")
        for path, ctype in rig.items():
            status, hdr, body = h.request(self.port, "GET", path)
            self.assertEqual(status, 200, path)
            self.assertEqual(hdr["content-type"], ctype, path)
            self.assertEqual(body, (config.WEB_DIR / path.lstrip("/")).read_bytes(), path)
            self.assertEqual(hdr.get("x-content-type-options"), "nosniff")
            self.assertEqual(hdr.get("cross-origin-resource-policy"), "same-origin")
            self.assertNotIn(TOKEN.encode(), body)
            self.assertNotIn("content-security-policy", hdr, "the page's policy is on the page alone")
        data = json.loads(h.request(self.port, "GET", "/rig/rig.json")[2])
        self.assertIsInstance(data, dict)
        some_png = sorted(p for p, c in rig.items() if c == "image/png")[0]
        status, hdr, body = h.request(self.port, "GET", some_png, host="evil.example:%d" % self.port)
        self.assertEqual(status, 403, "the Host check holds for them too")
        status, _, _ = h.request(self.port, "GET", "/rig/rig.json", {"Sec-Fetch-Site": "cross-site"})
        self.assertEqual(status, 403, "and a foreign page's fetch")
        self.assertEqual(h.request(self.port, "HEAD", "/rig/rig.json")[0], 405)
        self.assertEqual(h.request(self.port, "POST", "/rig/rig.json", body={})[0], 405)

    def test_every_image_rig_json_names_is_served(self):
        """The cards' generator names the images in rig.json; the server serves them by its name
        rule. An image named otherwise (a hyphen, a capital) would be a 404 on the page."""
        named = set()

        def walk(x):
            if isinstance(x, str) and x.lower().endswith(".png"):
                named.add(x)
            elif isinstance(x, dict):
                for v in x.values():
                    walk(v)
            elif isinstance(x, list):
                for v in x:
                    walk(v)
        walk(json.loads((config.WEB_DIR / "rig" / "rig.json").read_text(encoding="utf-8")))
        self.assertTrue(named, "rig.json names its images")
        for name in sorted(named):
            self.assertIn("/rig/" + name, self.srv.files, "%s: named in rig.json, not served by the rule" % name)

    def test_the_page_policy_allows_images_from_the_server_itself(self):
        _, hdr, _ = h.request(self.port, "GET", "/")
        csp = hdr["content-security-policy"]
        self.assertIn("img-src 'self' data:", csp)
        self.assertIn("connect-src 'self'", csp, "rig.json is read with fetch()")

    def test_nothing_else_under_rig_is_reachable(self):
        tricks = ["/rig", "/rig/", "/rig/.", "/rig/./rig.json", "/rig//rig.json", "/rig/RIG.JSON", "/Rig/rig.json",
                  "/rig/rig.json/", "/rig/rig.json.", "/rig/rig.json%00", "/rig/rig.json%20", "/rig%2frig.json",
                  "/rig%2Frig.json", "/rig/%72ig.json", "/rig\\rig.json", "/rig/..", "/rig/../app.js",
                  "/rig/../index.html", "/rig/../../scdash/server.py", "/rig/..%2f..%2fscdash%2fserver.py",
                  "/rig/%2e%2e/%2e%2e/scdash.py", "/rig/rig.json::$DATA", "/rig/RIG~1.JSO", "/rig/desktop.ini",
                  "/rig/ab6_base.PNG", "/rig/ab6_base.png.json", "/rig/ab6_base", "/rig/no_such_view_here.png",
                  "/rig/*", "/rig/?", "/rig/rig.json?../../scdash.py#x", "/web/rig/rig.json", "/./rig/rig.json"]
        for path in tricks:
            status, hdr, body = h.request(self.port, "GET", path)
            if path == "/rig/rig.json?../../scdash.py#x":
                self.assertEqual(status, 200, "a query is no part of the path")
                self.assertEqual(body, (config.WEB_DIR / "rig" / "rig.json").read_bytes())
                continue
            self.assertEqual(status, 404, path)
            self.assertNotIn(b"import", body, path)
            self.assertNotIn(b"PNG", body, path)


class RigFolderRule(unittest.TestCase):
    """The table of rig files is built once, from what a web folder of the test's own holds: a
    strict name rule, plain files only (a junction or a link is not followed, the rule the data
    folder has, PLAN §8), bounded in size and number; and a request never reaches the file
    system for a name the table does not hold."""

    PNG = b"\x89PNG\r\n\x1a\n" + b"\0" * 24

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="scdash-rig-"))
        self.web = self.tmp / "web"
        (self.web / "rig").mkdir(parents=True)
        self.servers = []
        self.warnings = []

    def tearDown(self):
        for s in self.servers:
            s.stop()
        for p in sorted(self.tmp.rglob("*"), key=lambda p: -len(p.parts)):
            if p.is_dir() and (p.is_symlink() or os.path.isjunction(p)):
                os.rmdir(p) if os.path.isjunction(p) else p.unlink()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def put(self, name, data=None, folder=None):
        p = (folder or self.web / "rig") / name
        p.write_bytes(self.PNG if data is None else data)
        return p

    def serve(self):
        lg = logging.getLogger("scdash-test-rig-%x-%d" % (id(self), len(self.servers)))
        lg.setLevel(logging.DEBUG)
        lg.propagate = False
        test = self

        class Grab(logging.Handler):
            def emit(self, record):
                test.warnings.append(record.getMessage())
        lg.addHandler(Grab())
        srv = Server(h.free_port(), TOKEN, web_dir=self.web, logger=lg, poll_interval=0.05).start()
        self.servers.append(srv)
        return srv

    def get(self, srv, path):
        return h.request(srv.port, "GET", path)

    def test_a_dot_file_is_neither_served_nor_reported(self):
        # The generator's own .gitattributes sits in web/rig/. It must not be served, and it must
        # not raise a warning at every start of the service.
        self.put("rig.json", b'{"views": []}')
        self.put("a.png")
        self.put(".gitattributes", b"*.json text eol=lf")
        self.put(".hidden.png")
        srv = self.serve()
        self.assertEqual(self.get(srv, "/rig/a.png")[0], 200)
        for path in ("/rig/.gitattributes", "/rig/.hidden.png"):
            self.assertEqual(self.get(srv, path)[0], 404, path)
        self.assertEqual([w for w in self.warnings if "left out" in w], [], self.warnings)

    def test_the_name_rule(self):
        self.put("rig.json", b'{"views": []}')
        good = ["a.png", "view_2.png", "mtq_axes.png", "x" * 48 + ".png"]
        bad = ["Odd-Name.png", "UPPER.png", "a.PNG", "x.png.bak", "\u00e9t\u00e9.png", "sp ace.png", "notes.txt",
               ".png", "x" * 49 + ".png", "a.b.png", "rig.json.png", "\uff41.png", "desktop.ini"]
        for name in good:
            self.put(name)
        for name in bad:
            try:
                self.put(name)
            except OSError:
                pass                                   # a name this file system will not take
        (self.web / "rig" / "sub").mkdir()
        self.put("c.png", folder=self.web / "rig" / "sub")
        (self.web / "rig" / "dir.png").mkdir()          # a folder with an image's name
        srv = self.serve()
        rig = {p for p in srv.files if p.startswith("/rig/")}
        self.assertEqual(rig, {"/rig/rig.json"} | {"/rig/" + n for n in good})
        for name in good:
            status, hdr, body = self.get(srv, "/rig/" + name)
            self.assertEqual((status, hdr["content-type"], body), (200, "image/png", self.PNG), name)
        for path in ["/rig/" + n for n in bad] + ["/rig/sub/c.png", "/rig/sub", "/rig/dir.png"]:
            for asked in {path, quote(path)}:         # raw where a request line can carry it, and escaped
                if " " in asked or not asked.isascii():
                    continue
                self.assertEqual(self.get(srv, asked)[0], 404, asked)
        self.assertEqual(self.get(srv, "/rig/rig.json")[2], b'{"views": []}')
        self.assertTrue(any("left out" in w and "Odd-Name.png" in w for w in self.warnings), self.warnings)

    def test_bounded_in_size_and_number(self):
        self.put("rig.json", b"{}")
        for i in range(6):
            self.put("v%d.png" % i)
        self.put("big.png", b"x" * 101)
        with mock.patch.object(config, "MAX_RIG_IMAGES", 4), mock.patch.object(config, "MAX_RIG_FILE_BYTES", 100):
            srv = self.serve()
            self.assertEqual({p for p in srv.files if p.endswith(".png")}, {"/rig/v%d.png" % i for i in range(4)},
                             "the first four by name; the one over the size bound left out")
            self.assertEqual(self.get(srv, "/rig/big.png")[0], 404)
            self.assertEqual(self.get(srv, "/rig/v4.png")[0], 404)
            # a file that grows past the bound after the start is not sent
            self.put("v0.png", b"y" * 101)
            self.assertEqual(self.get(srv, "/rig/v0.png")[0], 404)
            self.put("v0.png", b"y" * 100)
            self.assertEqual(self.get(srv, "/rig/v0.png")[2], b"y" * 100, "read fresh: a changed card is served")

    def test_a_name_added_after_the_start_needs_a_restart(self):
        self.put("rig.json", b"{}")
        srv = self.serve()
        self.put("new_view.png")
        self.assertEqual(self.get(srv, "/rig/new_view.png")[0], 404, "the table is fixed at the start")
        again = self.serve()
        self.assertEqual(self.get(again, "/rig/new_view.png")[0], 200)

    def test_a_junction_for_the_folder_is_not_followed(self):
        outside = self.tmp / "outside"
        outside.mkdir()
        self.put("rig.json", b'{"outside": true}', folder=outside)
        self.put("a.png", folder=outside)
        (self.web / "rig").rmdir()
        if not make_junction(self.web / "rig", outside):
            self.skipTest("no junction could be made here")
        srv = self.serve()
        self.assertEqual({p for p in srv.files if p.startswith("/rig/")}, set())
        for path in ("/rig/rig.json", "/rig/a.png"):
            self.assertEqual(self.get(srv, path)[0], 404, path)
        self.assertTrue(any("junction" in w for w in self.warnings), self.warnings)

    def test_a_folder_swapped_for_a_junction_after_the_start_is_not_followed(self):
        self.put("rig.json", b'{"inside": true}')
        self.put("a.png")
        srv = self.serve()
        self.assertEqual(self.get(srv, "/rig/a.png")[0], 200)
        outside = self.tmp / "outside"
        outside.mkdir()
        self.put("rig.json", b'{"outside": true}', folder=outside)
        self.put("a.png", b"\x89PNG outside", folder=outside)
        (self.web / "rig").rename(self.tmp / "rig-moved")
        if not make_junction(self.web / "rig", outside):
            self.skipTest("no junction could be made here")
        for path in ("/rig/rig.json", "/rig/a.png"):
            status, _, body = self.get(srv, path)
            self.assertEqual(status, 404, path)
            self.assertNotIn(b"outside", body)

    def test_a_junction_inside_the_folder_is_not_served(self):
        outside = self.tmp / "outside"
        outside.mkdir()
        self.put("rig.json", b"{}")
        if not make_junction(self.web / "rig" / "j.png", outside):
            self.skipTest("no junction could be made here")
        srv = self.serve()
        self.assertNotIn("/rig/j.png", srv.files)
        self.assertEqual(self.get(srv, "/rig/j.png")[0], 404)

    def test_a_hard_link_is_not_served(self):
        """K: a hard link is no reparse point, and its data can be anywhere on the volume (the data
        folder's run.json, with the token): only a file with a single link is served, at the
        start and on each request."""
        outside = self.tmp / "outside"
        outside.mkdir()
        secret = outside / "run.json"
        secret.write_bytes(b'{"token": "not for a page"}')
        self.put("rig.json", b"{}")
        self.put("a.png")
        try:
            os.link(secret, self.web / "rig" / "hardlink.png")
        except OSError:
            self.skipTest("no hard link could be made here")
        srv = self.serve()
        self.assertNotIn("/rig/hardlink.png", srv.files)
        self.assertEqual(self.get(srv, "/rig/hardlink.png")[0], 404)
        self.assertEqual(self.get(srv, "/rig/a.png")[0], 200)
        self.assertTrue(any("hardlink.png" in w for w in self.warnings), self.warnings)
        for name in ("a.png", "rig.json"):            # a served name replaced by a hard link after the start
            (self.web / "rig" / name).unlink()
            os.link(secret, self.web / "rig" / name)
            status, _, body = self.get(srv, "/rig/" + name)
            self.assertEqual(status, 404, name)
            self.assertNotIn(b"token", body)

    def test_the_scan_of_the_folder_is_bounded(self):
        self.put("rig.json", b"{}")
        for i in range(10):
            self.put("v%d.png" % i)
        with mock.patch.object(server, "RIG_SCAN_MAX", 5):
            srv = self.serve()
        self.assertLessEqual(len([p for p in srv.files if p.startswith("/rig/")]), 5)
        self.assertTrue(any("more than 5 entries" in w for w in self.warnings), self.warnings)

    def test_no_rig_folder_serves_the_page_alone(self):
        (self.web / "rig").rmdir()
        srv = self.serve()
        self.assertEqual(set(srv.files), set(server.FILES))
        self.assertEqual(self.warnings, [])


class Binding(unittest.TestCase):
    def test_a_second_server_cannot_take_the_port(self):
        a = Server(h.free_port(), TOKEN, poll_interval=0.05).start()
        try:
            b = Server(a.port, TOKEN)
            with self.assertRaises(OSError):
                b.start()
            # nor can a plain socket asking to reuse the address
            s = socket.socket()
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            with self.assertRaises(OSError):
                s.bind(("127.0.0.1", a.port))
            s.close()
        finally:
            a.stop()

    @unittest.skipUnless(winutil.IS_WINDOWS, "SO_EXCLUSIVEADDRUSE is Windows-only")
    def test_listening_socket_is_exclusive(self):
        a = Server(h.free_port(), TOKEN, poll_interval=0.05).start()
        try:
            opt = a._httpd.socket.getsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE)
            self.assertTrue(opt)
            self.assertEqual(a._httpd.socket.getsockname()[0], "127.0.0.1")
        finally:
            a.stop()


class Stream:
    """A raw event-stream client: reads events as they come."""

    def __init__(self, port, path="/api/stream", host=None, extra=""):
        self.sock = socket.create_connection(("127.0.0.1", port), timeout=5)
        head = "GET %s HTTP/1.0\r\nHost: %s\r\n" % (path, host or "127.0.0.1:%d" % port)
        if extra:
            head += extra + "\r\n"
        self.sock.sendall((head + "\r\n").encode())
        self.buf = b""
        self.status = None
        self.events = []        # (time, kind, text)
        self.closed = False
        self._t = threading.Thread(target=self._read, daemon=True)
        self._t.start()

    def _read(self):
        try:
            while True:
                b = self.sock.recv(65536)
                if not b:
                    break
                self.buf += b
                if self.status is None and b"\r\n\r\n" in self.buf:
                    head, _, self.buf = self.buf.partition(b"\r\n\r\n")
                    self.status = int(head.split()[1])
                while self.status is not None and b"\n\n" in self.buf:
                    block, _, self.buf = self.buf.partition(b"\n\n")
                    text = block.decode("utf-8")
                    if text.startswith(":"):
                        self.events.append((time.monotonic(), "comment", text))
                    elif text.startswith("retry:"):
                        self.events.append((time.monotonic(), "retry", text))
                    else:
                        data = [ln[6:] for ln in text.split("\n") if ln.startswith("data: ")]
                        self.events.append((time.monotonic(), "data", data[0] if data else ""))
        except OSError:
            pass
        self.closed = True

    def data(self):
        return [e[2] for e in self.events if e[1] == "data"]

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass


class PrivateStream(ServerCase):
    def test_private_stream_guard_and_its_own_cap(self):
        ok = "%s: %s\r\nSec-Fetch-Site: same-origin" % (server.TOKEN_HEADER, TOKEN)
        self.private_hub.publish('"hello"')
        for extra in ("", "%s: %s" % (server.TOKEN_HEADER, TOKEN), "Sec-Fetch-Site: same-origin"):
            c = Stream(self.port, "/api/private-stream", extra=extra)
            h.wait_until(lambda: c.closed, 3)
            self.assertEqual(c.status, 403, extra)
            c.close()
        a = Stream(self.port, "/api/private-stream", extra=ok)
        states = [Stream(self.port), Stream(self.port)]          # the state stream is full (cap 2)
        try:
            self.assertTrue(h.wait_until(lambda: a.data() == ['"hello"'], 3))
            b = Stream(self.port, "/api/private-stream", extra=ok)
            h.wait_until(lambda: b.closed, 3)
            self.assertEqual(b.status, 503, "a private stream has a cap of its own")
            b.close()
            self.assertTrue(h.wait_until(lambda: self.hub.clients == 2, 3), "the state stream is unaffected")
        finally:
            a.close()
            for c in states:
                c.close()


class EventStream(ServerCase):
    def test_retry_then_current_state_then_merged_updates(self):
        self.hub.publish('{"n":0}')
        c = Stream(self.port)
        try:
            self.assertTrue(h.wait_until(lambda: len(c.data()) >= 1, 5))
            self.assertEqual(c.status, 200)
            self.assertEqual(c.events[0][1], "retry")
            self.assertEqual(c.events[0][2], "retry: 1234")
            self.assertEqual(c.data()[0], '{"n":0}')
            t0 = time.monotonic()
            for i in range(1, 41):                 # a burst: 40 states in about 1 second
                self.hub.publish('{"n":%d}' % i)
                time.sleep(0.025)
            self.assertTrue(h.wait_until(lambda: c.data()[-1] == '{"n":40}', 5), "the last state arrives")
            got = [e for e in c.events if e[1] == "data" and e[0] >= t0]
            span = got[-1][0] - got[0][0] if len(got) > 1 else 0
            self.assertLessEqual(len(got), 2 * span + 3, "at most two sends a second")
            self.assertLess(len(got), 10)
        finally:
            c.close()

    def test_keepalive_comment(self):
        c = Stream(self.port)
        try:
            self.assertTrue(h.wait_until(lambda: any(e[1] == "comment" for e in c.events), 3))
        finally:
            c.close()

    def test_stream_refuses_foreign_host(self):
        c = Stream(self.port, host="evil.example:%d" % self.port)
        try:
            h.wait_until(lambda: c.closed, 3)
            self.assertEqual(c.status, 403)
            self.assertEqual(self.hub.clients, 0)
        finally:
            c.close()

    def test_cap_on_pages_and_a_closed_page_frees_its_place(self):
        a, b = Stream(self.port), Stream(self.port)
        try:
            self.assertTrue(h.wait_until(lambda: self.hub.clients == 2, 3))
            c = Stream(self.port)
            h.wait_until(lambda: c.closed, 3)
            self.assertEqual(c.status, 503)
            c.close()
            a.close()
            self.assertTrue(h.wait_until(lambda: self.hub.clients == 1, 3), "a closed page is noticed")
            d = Stream(self.port)
            self.assertTrue(h.wait_until(lambda: d.status == 200, 3))
            d.close()
        finally:
            a.close()
            b.close()

    def test_payload_must_be_one_line(self):
        with self.assertRaises(ValueError):
            self.hub.publish('{"a":\n1}')

    def test_a_lone_surrogate_cannot_break_a_page_stream(self):
        """Each page's thread encodes the payload; a code point UTF-8 cannot encode would raise
        there on every reconnect, and the page would never get a state (stage 3 review)."""
        self.hub.publish('{"t":"a\ud800b"}')
        self.assertEqual(self.hub.latest, '{"t":"a\ufffdb"}')
        c = Stream(self.port)
        try:
            self.assertTrue(h.wait_until(lambda: c.data(), 3), "the page gets it")
            self.assertEqual(json.loads(c.data()[0]), {"t": "a\ufffdb"})
            self.hub.publish('{"n":2}')
            self.assertTrue(h.wait_until(lambda: c.data()[-1] == '{"n":2}', 3), "and the stream stays up")
        finally:
            c.close()

    def test_answers_are_always_valid_json(self):
        self.srv.route("GET", "/api/odd", lambda r: (200, {"t": "a\ud800", "n": float("nan")}), READ)
        status, hdr, body = h.request(self.port, "GET", "/api/odd")
        self.assertEqual(status, 200)

        def no_constant(name):
            raise ValueError(name)
        self.assertEqual(json.loads(body.decode("utf-8"), parse_constant=no_constant)["n"], None)

    def test_stop_ends_the_streams(self):
        c = Stream(self.port)
        self.assertTrue(h.wait_until(lambda: self.hub.clients == 1, 3))
        self.srv.stop()
        self.assertTrue(h.wait_until(lambda: c.closed, 5))
        c.close()
        self.srv = Server(h.free_port(), TOKEN)          # tearDown stops something harmless


if __name__ == "__main__":
    unittest.main()
