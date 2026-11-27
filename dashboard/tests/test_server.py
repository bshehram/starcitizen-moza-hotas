"""The web server and its request guard (PLAN §8, §13 "Server"), in process, on a free port.

Every request is refused unless its Host is this server, reads included; a changing request
also needs the token, a JSON body and this server's Origin; no path from a request opens a file;
the health check does not carry the token; and the event stream merges, keeps alive, caps."""
import json
import socket
import threading
import time
import unittest

import scdash_testlib as lib  # noqa: F401  (puts dashboard/ on sys.path)
import test_service_helpers as h
from unittest import mock

from scdash import config, server, winutil
from scdash.server import CHANGE, PRIVATE, READ, Hub, Server

TOKEN = "test-token-not-secret-0123456789abcdef"


class ServerCase(unittest.TestCase):
    def setUp(self):
        self.hub = Hub("state", min_interval=0.5, keepalive=0.4, retry_ms=1234, max_clients=2)
        self.srv = Server(h.free_port(), TOKEN, page_vars={"terminal": "off", "mode": "live"}, poll_interval=0.05)
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

    def test_stop_ends_the_streams(self):
        c = Stream(self.port)
        self.assertTrue(h.wait_until(lambda: self.hub.clients == 1, 3))
        self.srv.stop()
        self.assertTrue(h.wait_until(lambda: c.closed, 5))
        c.close()
        self.srv = Server(h.free_port(), TOKEN)          # tearDown stops something harmless


if __name__ == "__main__":
    unittest.main()
