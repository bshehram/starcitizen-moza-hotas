"""The local web server: the page, the event streams, a health check, and the request guard.

It listens on 127.0.0.1 only (PLAN §8). What it serves is fixed: the three files of the page and
the routes registered in code. No part of a request is ever used to open a file.

The guard runs before anything else, for every request:

- **Host.** Every request, reads included, must carry exactly one `Host` header that is
  `127.0.0.1:<port>` or `localhost:<port>`, and an origin-form target ("/..."). Without that check
  a web page that points its own domain name at 127.0.0.1 could read the state and the stream.
- **Sec-Fetch-Site.** A browser says where a request comes from; anything it sends other than
  `same-origin` or `none` (a typed address) is refused, on every route.
- **Deadline.** The request head (and a changing request's body) must arrive within
  `REQUEST_TIMEOUT` seconds in all, however slowly it trickles in; the connection is cut after.
- **Changing requests** (`CHANGE`) also need the token in the `X-SCDash-Token` header, an `Origin`
  of this server, and a JSON object as the body (`Content-Type: application/json`, a
  `Content-Length` of ASCII digits, at most 64 KB). The page gets the token inside the HTML this
  server serves; no endpoint hands it out, and it never travels in a URL.
- **Private reads** (`PRIVATE`, for stage 4b's terminal output) need the token header and a
  `Sec-Fetch-Site: same-origin` that must be present. The page reads such a stream with `fetch()`
  (`openPrivateStream()` in app.js), since an EventSource cannot send headers.

Every registration names its guard; there is no default. A later stage adds an endpoint with one
call, and the guard comes with it:

    server.route("POST", "/api/timers", handler, CHANGE)       # handler(request) -> (status, obj)
    server.stream("/api/terminal/out", Hub(max_clients=1), PRIVATE)

The event streams (PLAN §5): plain HTTP/1.0, one thread per page, a `retry:` value first, the
current payload at once, then each new one merged to at most two sends a second, a comment line
every 15 seconds, and a cap on connected pages per stream (each `Hub` has its own). A closed page
is noticed by the next failed write or, within a second, by peeking at its socket.

Ideas taken (not code) from sc-log-tracker's server (PLAN §5): the Host check on every request,
a custom header on writes, no address reuse on Windows, and peeking at a page's socket.
"""
import hmac
import html
import http.server
import json
import os
import re
import select
import socket
import socketserver
import threading
import time
from urllib.parse import parse_qs, urlsplit

from . import config
from .winutil import exclusive_address

PROGRAM = "scdash"
TOKEN_HEADER = "X-SCDash-Token"

# The page's files: request path -> (file in web/, content type). Nothing else is ever opened.
FILES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/style.css": ("style.css", "text/css; charset=utf-8"),
}

COMMON_HEADERS = (
    ("Cache-Control", "no-store"),
    ("X-Content-Type-Options", "nosniff"),
    ("Referrer-Policy", "no-referrer"),
    ("X-Frame-Options", "DENY"),
    ("Cross-Origin-Resource-Policy", "same-origin"),
)
PAGE_CSP = ("default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
            "connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'")
METHODS = ("GET", "HEAD", "POST", "PUT", "DELETE", "PATCH", "OPTIONS")
FETCH_SITES = ("same-origin", "none")        # the only Sec-Fetch-Site values any route accepts
LENGTH_RE = re.compile(r"[0-9]{1,9}")        # ASCII digits only: str.isdigit() takes "²" too


class Guard:
    """What a route asks of a request beyond the checks every request gets (Host, Sec-Fetch-Site,
    the deadline)."""

    def __init__(self, name, token_header=False, same_origin=False, origin=False, json_body=False):
        self.name = name
        self.token_header = token_header      # the token in the X-SCDash-Token header
        self.same_origin = same_origin        # Sec-Fetch-Site: same-origin must be present
        self.origin = origin                  # Origin must be this server
        self.json_body = json_body            # a JSON object body, application/json

    def __repr__(self):
        return "Guard(%s)" % self.name


READ = Guard("read")
CHANGE = Guard("change", token_header=True, origin=True, json_body=True)
PRIVATE = Guard("private read", token_header=True, same_origin=True)


class Refused(Exception):
    def __init__(self, status, reason):
        super().__init__(reason)
        self.status = status
        self.reason = reason


class Request:
    """What a route handler gets."""

    def __init__(self, method, path, query, headers, body, client):
        self.method = method
        self.path = path
        self.query = query        # {name: [values]}
        self.headers = headers
        self.json = body          # the parsed JSON object, for CHANGE routes; else None
        self.client = client


# ---------------------------------------------------------------------------- event streams

class Hub:
    """One event stream: the latest payload, and every page connected to it.

    `publish(text)` replaces the payload (a JSON string with no line breaks); each page gets the
    newest one, at most once per `min_interval` seconds, so a burst is merged into its last
    state. A page that connects gets the current payload at once. `max_clients` caps this stream
    alone, so one stream's reconnects cannot crowd out another's pages."""

    def __init__(self, event="state", min_interval=0.5, keepalive=15.0, retry_ms=3000, max_clients=4):
        self.event = event
        self.min_interval = min_interval
        self.keepalive = keepalive
        self.retry_ms = retry_ms
        self.max_clients = max_clients
        self._cond = threading.Condition()
        self._payload = None
        self._version = 0
        self._clients = 0
        self._closed = False
        self.sent = 0                          # messages written, all pages together (for tests)

    @property
    def clients(self):
        return self._clients

    @property
    def latest(self):
        return self._payload

    @property
    def version(self):
        return self._version

    def publish(self, text):
        if "\n" in text or "\r" in text:
            raise ValueError("an event payload must be one line")
        with self._cond:
            self._payload = text
            self._version += 1
            self._cond.notify_all()

    def close(self):
        with self._cond:
            self._closed = True
            self._cond.notify_all()

    def _join(self):
        with self._cond:
            if self._closed:
                raise Refused(503, "shutting down")
            if self._clients >= self.max_clients:
                raise Refused(503, "too many pages connected")
            self._clients += 1

    def _leave(self):
        with self._cond:
            self._clients -= 1

    def serve(self, handler):
        """Runs in the page's own request thread until the page goes away or the hub closes."""
        self._join()
        try:
            handler.send_response(200)
            handler.send_header("Content-Type", "text/event-stream; charset=utf-8")
            for k, v in COMMON_HEADERS:
                handler.send_header(k, v)
            handler.end_headers()
            w = handler.wfile
            w.write(b"retry: %d\n\n" % self.retry_ms)
            w.flush()
            sock = handler.connection
            last_v, last_send = 0, 0.0
            last_write = time.monotonic()
            while True:
                with self._cond:
                    now = time.monotonic()
                    due = self._version != last_v and now - last_send >= self.min_interval
                    if not due and not self._closed:
                        wait = 1.0
                        if self._version != last_v:
                            wait = min(wait, self.min_interval - (now - last_send))
                        self._cond.wait(max(0.01, min(wait, self.keepalive - (now - last_write))))
                        now = time.monotonic()
                        due = self._version != last_v and now - last_send >= self.min_interval
                    if self._closed:
                        return
                    payload, v = (self._payload, self._version) if due else (None, None)
                if payload is not None:
                    w.write(b"id: %d\nevent: %s\ndata: %s\n\n" % (v, self.event.encode(), payload.encode("utf-8")))
                    w.flush()
                    self.sent += 1
                    last_v, last_send, last_write = v, now, now
                elif now - last_write >= self.keepalive:
                    w.write(b": keepalive\n\n")
                    w.flush()
                    last_write = now
                if _peer_closed(sock):
                    return
        except OSError:
            return                              # the page went away mid-write: nothing to do
        finally:
            self._leave()


def _peer_closed(sock):
    """Has the page closed its end? A readable socket with nothing to read is a closed one."""
    try:
        r, _, _ = select.select([sock], [], [], 0)
        if not r:
            return False
        return sock.recv(1, socket.MSG_PEEK) == b""
    except (OSError, ValueError):
        return True


# ---------------------------------------------------------------------------- the deadline

class _Deadlines:
    """Cuts a connection whose request head (and body) has not fully arrived within its deadline.

    The socket timeout only bounds each read, so a client sending a byte every few seconds could
    hold a request slot forever. One thread watches the open requests; it sleeps until the
    earliest deadline and not at all while nothing is pending."""

    def __init__(self):
        self._cond = threading.Condition()
        self._pending = {}                      # handler -> deadline (monotonic)
        self._closed = False
        self._thread = threading.Thread(target=self._run, name="scdash-deadlines", daemon=True)
        self._thread.start()

    def watch(self, handler, seconds):
        with self._cond:
            self._pending[handler] = time.monotonic() + seconds
            self._cond.notify()

    def done(self, handler):
        with self._cond:
            self._pending.pop(handler, None)

    def close(self):
        with self._cond:
            self._closed = True
            self._cond.notify()

    def _run(self):
        while True:
            with self._cond:
                if self._closed:
                    return
                if not self._pending:
                    self._cond.wait()
                    continue
                now = time.monotonic()
                late = [h for h, t in self._pending.items() if t <= now]
                for h in late:
                    del self._pending[h]
                if not late:
                    self._cond.wait(min(self._pending.values()) - now)
                    continue
            for h in late:
                h.expired = True
                try:
                    h.connection.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass


# ---------------------------------------------------------------------------- the server

class _HTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    allow_reuse_address = False          # Windows lets a second process bind a port under SO_REUSEADDR
    daemon_threads = True
    block_on_close = False
    request_queue_size = 16

    def __init__(self, addr, handler, app):
        self.app = app
        self._slots = threading.BoundedSemaphore(config.MAX_CONNECTIONS)
        super().__init__(addr, handler)

    def server_bind(self):
        exclusive_address(self.socket)
        self.socket.bind(self.server_address)
        self.server_address = self.socket.getsockname()
        self.server_name, self.server_port = self.server_address[:2]

    def process_request(self, request, client_address):
        if not self._slots.acquire(blocking=False):
            self.shutdown_request(request)        # over the cap: close it at once
            return
        try:
            super().process_request(request, client_address)
        except Exception:
            self._slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._slots.release()

    def handle_error(self, request, client_address):
        self.app.log_debug("request error from %s" % (client_address,), exc=True)


class Handler(http.server.BaseHTTPRequestHandler):
    server_version = PROGRAM
    sys_version = ""
    timeout = config.REQUEST_TIMEOUT
    protocol_version = "HTTP/1.0"         # PLAN §5: HTTP/1.1 would need an exact length on everything
    expired = False

    def setup(self):
        super().setup()
        self.server.app.deadlines.watch(self, config.REQUEST_TIMEOUT)

    def finish(self):
        self.server.app.deadlines.done(self)
        try:
            super().finish()
        except OSError:
            pass

    def log_message(self, fmt, *args):     # no stderr: under pythonw there is none
        pass

    def log_error(self, fmt, *args):
        self.server.app.log_debug("http: " + repr((fmt % args)[:300]))

    def send_error(self, code, message=None, explain=None):
        if not self.expired:
            self._reply(code, {"error": message or "error"})

    def _reply(self, status, obj=None, body=None, ctype="application/json; charset=utf-8", extra=()):
        if body is None:
            body = json.dumps(obj if obj is not None else {}, separators=(",", ":")).encode("utf-8")
        try:
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Connection", "close")
            for k, v in COMMON_HEADERS:
                self.send_header(k, v)
            for k, v in extra:
                self.send_header(k, v)
            self.end_headers()
            if getattr(self, "command", None) != "HEAD":
                self.wfile.write(body)
        except OSError:
            pass
        self.close_connection = True

    def _dispatch(self):
        app = self.server.app
        if self.expired:                             # cut by the deadline: the head may be partial
            self.close_connection = True
            return
        try:
            app.check_basics(self)
            target = urlsplit(self.path)
            path = target.path
            route = app.routes.get(path)
            if route is None:
                raise Refused(404, "not found")
            if self.command not in route:
                raise Refused(405, "method not allowed")
            guard, fn = route[self.command]
            req = app.check_guard(self, guard, target)
            app.deadlines.done(self)                 # the whole request is in
            if self.expired:
                self.close_connection = True
                return
            app.requests += 1
            if isinstance(fn, Hub):
                fn.serve(self)
                self.close_connection = True
                return
            status, result = fn(req)
            if isinstance(result, tuple):           # (bytes, content type, extra headers)
                body, ctype = result[0], result[1]
                extra = result[2] if len(result) > 2 else ()
                self._reply(status, body=body, ctype=ctype, extra=extra)
            else:
                self._reply(status, result)
        except Refused as r:
            app.refused += 1
            if not self.expired:
                self._reply(r.status, {"error": r.reason})
        except Exception:                            # noqa: BLE001 - one request must not stop the server
            app.log_debug("handler failed for %s %r" % (self.command, self.path[:200]), exc=True)
            if not self.expired:
                self._reply(500, {"error": "internal error"})


for _m in METHODS:
    setattr(Handler, "do_" + _m, Handler._dispatch)


class Server:
    """The dashboard's web server. `start()` binds 127.0.0.1:<port> (OSError when the port is
    taken) and serves in a thread of its own; `stop()` ends it."""

    def __init__(self, port, token, web_dir=config.WEB_DIR, page_vars=None, logger=None, poll_interval=0.5):
        self.host = "127.0.0.1"
        self.port = port
        self.token = token
        self.web_dir = web_dir
        self.page_vars = dict(page_vars or {})
        self.logger = logger
        self.poll_interval = poll_interval  # how soon the serving thread notices stop(); each wake-up costs a little
        self.routes = {}                  # path -> {method: (guard, fn or Hub)}
        self.hubs = []
        self.requests = 0
        self.refused = 0
        self.deadlines = None
        self._httpd = None
        self._thread = None
        self._allowed_hosts = set()
        for path in FILES:
            self.route("GET", path, self._file, READ)

    # Registering ----------------------------------------------------------------------------

    def route(self, method, path, fn, guard):
        """Register `fn(request) -> (status, obj)` behind `guard` (required). `obj` is turned
        into JSON, or is a tuple (bytes, content type[, extra headers])."""
        if method not in METHODS:
            raise ValueError(method)
        if not isinstance(guard, Guard):
            raise TypeError("every route names its Guard")
        if method == "GET" and guard.json_body:
            raise ValueError("a GET route cannot take a JSON body")
        if method != "GET" and not guard.token_header:
            raise ValueError("a changing route needs the token: use CHANGE")
        self.routes.setdefault(path, {})[method] = (guard, fn)

    def stream(self, path, hub, guard):
        """Register an event stream (GET) behind `guard` (required: READ for the state, PRIVATE
        for anything only the dashboard's own page may read)."""
        if not isinstance(hub, Hub):
            raise TypeError("a stream needs a Hub")
        self.route("GET", path, hub, guard)
        self.hubs.append(hub)

    # Life -----------------------------------------------------------------------------------

    def start(self):
        self.deadlines = _Deadlines()
        try:
            self._httpd = _HTTPServer((self.host, self.port), Handler, self)
        except OSError:
            self.deadlines.close()
            raise
        self.port = self._httpd.server_port
        self._allowed_hosts = {"127.0.0.1:%d" % self.port, "localhost:%d" % self.port}
        self._thread = threading.Thread(target=self._httpd.serve_forever, kwargs={"poll_interval": self.poll_interval},
                                        name="scdash-http", daemon=True)
        self._thread.start()
        return self

    def stop(self):
        for hub in self.hubs:
            hub.close()
        if self._httpd is not None:
            self._httpd.shutdown()
            self._httpd.server_close()
            self._httpd = None
        if self._thread is not None:
            self._thread.join(5)
            self._thread = None
        if self.deadlines is not None:
            self.deadlines.close()

    @property
    def origins(self):
        return {"http://" + h for h in self._allowed_hosts}

    # The guard ------------------------------------------------------------------------------

    def check_basics(self, h):
        """What every request needs, whatever its route."""
        hosts = h.headers.get_all("Host") or []
        if len(hosts) != 1 or hosts[0].strip().lower() not in self._allowed_hosts:
            raise Refused(403, "wrong host")
        if not h.path.startswith("/"):
            raise Refused(400, "bad target")
        sites = h.headers.get_all("Sec-Fetch-Site") or []
        if len(sites) > 1 or (sites and sites[0].strip().lower() not in FETCH_SITES):
            raise Refused(403, "not from this page")

    def check_guard(self, h, guard, target):
        query = parse_qs(target.query, keep_blank_values=True)
        if guard.token_header and not self._token_ok(h.headers.get(TOKEN_HEADER)):
            raise Refused(403, "token missing or wrong")
        if guard.same_origin and (h.headers.get("Sec-Fetch-Site") or "").strip().lower() != "same-origin":
            raise Refused(403, "not same-origin")
        if guard.origin:
            origins = h.headers.get_all("Origin") or []
            if len(origins) != 1 or origins[0].strip().lower() not in self.origins:
                raise Refused(403, "wrong origin")
            site = h.headers.get("Sec-Fetch-Site")
            if site is not None and site.strip().lower() != "same-origin":
                raise Refused(403, "not same-origin")
        body = None
        if guard.json_body:
            ctype = (h.headers.get("Content-Type") or "").split(";")[0].strip().lower()
            if ctype != "application/json":
                raise Refused(415, "JSON body required")
            lengths = h.headers.get_all("Content-Length") or []
            if len(lengths) != 1 or not LENGTH_RE.fullmatch(lengths[0].strip()):
                raise Refused(411, "length required")
            n = int(lengths[0].strip())
            if n > config.MAX_BODY:
                raise Refused(413, "body too large")
            raw = h.rfile.read(n) if n else b""
            if len(raw) != n:
                raise Refused(400, "body cut short")
            try:
                body = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, ValueError):
                raise Refused(400, "body is not JSON") from None
            if not isinstance(body, dict):
                raise Refused(400, "body must be a JSON object")
        elif h.command not in ("GET", "HEAD"):
            raise Refused(405, "method not allowed")
        return Request(h.command, target.path, query, h.headers, body, h.client_address)

    def _token_ok(self, given):
        if not given or not self.token:
            return False
        return hmac.compare_digest(given.strip().encode("utf-8"), self.token.encode("utf-8"))

    # The page -------------------------------------------------------------------------------

    def _file(self, req):
        name, ctype = FILES[req.path]
        try:
            with open(os.path.join(str(self.web_dir), name), "rb") as f:
                data = f.read()
        except OSError:
            raise Refused(404, "not found") from None
        extra = ()
        if name == "index.html":
            text = data.decode("utf-8")
            values = dict(self.page_vars, TOKEN=self.token)
            for key, val in values.items():
                text = text.replace("__SCDASH_%s__" % key.upper(), html.escape(str(val), quote=True))
            data = text.encode("utf-8")
            extra = (("Content-Security-Policy", PAGE_CSP),)
        return 200, (data, ctype, extra)

    def log_debug(self, msg, exc=False):
        if self.logger is not None:
            self.logger.debug(msg, exc_info=exc)
