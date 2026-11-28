"""The local web server: the page, the event streams, a health check, and the request guard.

It listens on 127.0.0.1 only (PLAN §8). What it serves is fixed: the three files of the page and
the routes registered in code. No part of a request is ever used to open a file.

The guard runs before anything else, for every request:

- **Host.** Every request, reads included, must carry exactly one `Host` header that is
  `127.0.0.1:<port>` or `localhost:<port>`, and an origin-form target ("/..."). Without that check
  a web page that points its own domain name at 127.0.0.1 could read the state and the stream.
- **Sec-Fetch-Site and Origin.** A browser says where a request comes from; a `Sec-Fetch-Site`
  other than `same-origin` or `none` (a typed address), or an `Origin` other than this server's,
  is refused on every route. Either header sent twice is refused too. The token header must
  appear exactly once.
- **The head first, then a worker.** One front-end thread reads every new connection's request
  head without blocking, and only a complete head takes one of the `MAX_CONNECTIONS` worker
  slots. Its first byte must come within `FIRST_BYTE_TIMEOUT` (1 s) and all of it within
  `REQUEST_TIMEOUT` (5 s), however slowly it trickles in; it may hold at most `MAX_HEAD` bytes
  (16 KB) and `MAX_HEADER_LINES` (40) header lines, refused (431) the moment it goes over, before
  the rest is read; and its `Host` is checked there already. At most `MAX_WAITING` connections
  wait for their head; over that the oldest is dropped. So connections that send nothing (a
  foreign page's preconnect hints) or huge heads cost a little of one thread and no worker.
- **Deadline.** A changing request's body must arrive within what is left of the same 5 s; a
  watcher thread cuts the connection after.
- **Changing requests** (`CHANGE`) also need the token in the `X-SCDash-Token` header, an `Origin`
  of this server, and a JSON object as the body (exactly one `Content-Type: application/json`, a
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
import http.client
import http.server
import io
import json
import os
import re
import select
import selectors
import socket
import threading
import time
import traceback
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
HEAD_END = re.compile(rb"\n\r?\n")           # the empty line that ends a request head
ACCEPT_BATCH = 16                            # connections taken per turn, before the waiting ones are read
FAULT_REPORT_SECONDS = 60.0                  # a front-end fault that repeats: one log line this often at most


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
                    with self._cond:                # one thread per page counts here
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
    """Cuts a connection whose request (a changing request's body, once a worker has it) has not
    fully arrived within its deadline: 5 s after the connection came in, head included.

    The socket timeout only bounds each read, so a client sending a byte every few seconds could
    hold a worker slot forever. One thread watches the open requests; it sleeps until the
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


# ---------------------------------------------------------------------------- the front end

class _Waiting:
    """A connection whose request head is still arriving."""

    __slots__ = ("sock", "addr", "buf", "nl", "lines", "first_by", "head_by")

    def __init__(self, sock, addr, now):
        self.sock = sock
        self.addr = addr
        self.buf = bytearray()
        self.nl = -1                              # where the request line ends, once it has
        self.lines = 0                            # line breaks so far
        self.first_by = now + config.FIRST_BYTE_TIMEOUT
        self.head_by = now + config.REQUEST_TIMEOUT

    @property
    def due(self):
        return self.head_by if self.buf else min(self.first_by, self.head_by)


class _FrontEnd:
    """The listening socket and every connection whose request head has not fully arrived.

    One thread reads them all without blocking, so a connection that sends nothing, trickles, or
    sends far too much takes no worker. A complete head within its limits and with a right Host
    goes, with whatever followed it, to a thread of its own: at most MAX_CONNECTIONS at once, the
    worker slots. Over that the request gets a 503 here."""

    def __init__(self, app, sock, poll_interval):
        self.app = app
        self.socket = sock                        # the listening socket
        self.poll_interval = poll_interval        # how soon stop() is noticed; each wake-up costs a little
        self._sel = selectors.DefaultSelector()
        self._waiting = {}                        # socket -> _Waiting, oldest first
        self._slots = threading.BoundedSemaphore(config.MAX_CONNECTIONS)
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="scdash-http", daemon=True)
        self._faults = 0                          # failed turns not yet reported
        self._fault_reported = None               # when the last report went to the log
        self._last_fault = ""

    def start(self):
        self._sel.register(self.socket, selectors.EVENT_READ, None)
        self._thread.start()

    def stop(self):
        self._stop.set()
        self._thread.join(5)

    def alive(self):
        return self._thread.is_alive()

    def _run(self):
        try:
            while not self._stop.is_set():
                try:
                    self._turn()
                except Exception:                 # noqa: BLE001 - one connection must not stop the server
                    self._fault()
                    self._stop.wait(0.05)
        finally:
            if self._faults:
                self._fault_summary(time.monotonic())
            for w in list(self._waiting.values()):
                self._drop(w)
            self._sel.close()
            self.socket.close()

    def _fault(self):
        """A failed turn, logged at WARNING so that it shows in the file log: the first in full,
        then at most one line every FAULT_REPORT_SECONDS with how many more came, so a fault that
        repeats every turn is seen and cannot fill the log."""
        now = time.monotonic()
        self._last_fault = traceback.format_exc().rstrip()
        if self._fault_reported is None:
            self._fault_reported = now
            self.app.log_warning("web server front end failed (carrying on):\n%s" % self._last_fault)
            return
        self._faults += 1
        if now - self._fault_reported >= FAULT_REPORT_SECONDS:
            self._fault_summary(now)

    def _fault_summary(self, now):
        self.app.log_warning("web server front end failed %d more time(s) in the last %.0f s; the last: %r"
                             % (self._faults, now - self._fault_reported, (self._last_fault.splitlines() or [""])[-1][:200]))
        self._faults, self._fault_reported = 0, now

    def _turn(self):
        timeout = self.poll_interval
        if self._waiting:
            soonest = min(w.due for w in self._waiting.values())
            timeout = max(0.0, min(timeout, soonest - time.monotonic()))
        accept = False
        for key, _ in self._sel.select(timeout):
            if key.data is None:
                accept = True
            else:
                self._read(key.data)
        if accept:
            self._accept()
        now = time.monotonic()
        for w in [w for w in self._waiting.values() if w.due <= now]:
            self._drop(w)                          # silent for a second, or no whole head in 5 s

    def _accept(self):
        for _ in range(ACCEPT_BATCH):
            try:
                sock, addr = self.socket.accept()
            except (BlockingIOError, InterruptedError):
                return
            except (ConnectionResetError, ConnectionAbortedError):
                continue                           # gone before it was taken
            sock.setblocking(False)
            if len(self._waiting) >= config.MAX_WAITING:
                self._drop(next(iter(self._waiting.values())))      # the oldest
            w = _Waiting(sock, addr, time.monotonic())
            self._waiting[sock] = w
            self._sel.register(sock, selectors.EVENT_READ, w)
            self._read(w)                          # a client's head is often there already

    def _read(self, w):
        try:
            chunk = w.sock.recv(min(config.MAX_HEAD - len(w.buf), 8192))
        except (BlockingIOError, InterruptedError):
            return
        except OSError:
            self._drop(w)
            return
        if not chunk:
            self._drop(w)                          # closed before its head was in
            return
        old = len(w.buf)
        w.buf += chunk
        w.lines += chunk.count(b"\n")
        if w.nl < 0:
            w.nl = w.buf.find(b"\n", old)
        m = HEAD_END.search(w.buf, max(w.nl, old - 2)) if w.nl >= 0 else None
        if m is None:
            if len(w.buf) >= config.MAX_HEAD or w.lines > config.MAX_HEADER_LINES + 1:
                self._refuse(w, 431, "request head too large")
            return
        if w.buf.count(b"\n", 0, m.end()) > config.MAX_HEADER_LINES + 2:    # the request line, the empty one
            self._refuse(w, 431, "request head too large")
            return
        self._hand_on(w, bytes(w.buf[:m.end()]))

    def _hand_on(self, w, head):
        line, _, rest = head.partition(b"\n")
        words = line.split()
        method = words[0] if words else b""
        try:
            hosts = http.client.parse_headers(io.BytesIO(rest)).get_all("Host") or []
        except Exception:                          # noqa: BLE001 - not a head the worker could read either
            hosts = []
        if not self.app.host_ok(hosts):
            self._refuse(w, 403, "wrong host", method)
            return
        if not self._slots.acquire(blocking=False):
            self._refuse(w, 503, "too many requests at once", method)
            return
        self._unwait(w)
        try:
            w.sock.setblocking(True)
            threading.Thread(target=self._work, args=(w.sock, w.addr, bytes(w.buf), w.head_by),
                             name="scdash-request", daemon=True).start()
        except Exception:
            self._slots.release()
            _close(w.sock)
            raise

    def _work(self, sock, addr, data, deadline):
        try:
            Handler(sock, addr, self, data, deadline)
        except Exception:                          # noqa: BLE001
            self.app.log_debug("request error from %s" % (addr,), exc=True)
        finally:
            _close(sock)
            self._slots.release()

    def _refuse(self, w, status, reason, method=b""):
        """Answer here and close, without a worker (the same JSON error a worker would send)."""
        self.app.count("refused")
        body = json.dumps({"error": reason}, separators=(",", ":")).encode("utf-8")
        head = ["HTTP/1.0 %d %s" % (status, http.HTTPStatus(status).phrase), "Server: " + PROGRAM,
                "Content-Type: application/json; charset=utf-8", "Content-Length: %d" % len(body),
                "Connection: close"] + ["%s: %s" % kv for kv in COMMON_HEADERS]
        data = ("\r\n".join(head) + "\r\n\r\n").encode("latin-1") + (b"" if method == b"HEAD" else body)
        try:
            w.sock.send(data)                      # a few hundred bytes: a fresh socket's buffer takes them
        except OSError:
            pass
        _drain(w.sock)
        self._unwait(w)
        _close(w.sock)

    def _unwait(self, w):
        self._waiting.pop(w.sock, None)
        try:
            self._sel.unregister(w.sock)
        except (KeyError, ValueError, OSError):
            pass

    def _drop(self, w):
        self._unwait(w)
        try:
            w.sock.close()
        except OSError:
            pass


def _drain(sock, limit=64 * 1024):
    """Read and drop what the client has already sent (up to `limit`): closing a socket with
    unread bytes resets the connection, and the client could lose the answer."""
    got = 0
    while got < limit:
        try:
            b = sock.recv(min(65536, limit - got))
        except OSError:                            # BlockingIOError: nothing more there now
            return
        if not b:
            return
        got += len(b)


def _close(sock):
    try:
        sock.shutdown(socket.SHUT_WR)
    except OSError:
        pass
    try:
        sock.close()
    except OSError:
        pass


class _Prefixed(io.RawIOBase):
    """What the front end already read from the socket, then the socket itself: the worker reads
    the request as if straight from the socket."""

    def __init__(self, sock, data):
        self._sock = sock
        self._data = memoryview(data)

    def readable(self):
        return True

    def readinto(self, b):
        if self._data:
            n = min(len(b), len(self._data))
            b[:n] = self._data[:n]
            self._data = self._data[n:]
            return n
        return self._sock.recv_into(b)


class _SocketWriter(io.BufferedIOBase):
    """Writes straight to the socket (what socketserver gives a handler with no write buffer)."""

    def __init__(self, sock):
        self._sock = sock

    def writable(self):
        return True

    def write(self, b):
        self._sock.sendall(b)
        with memoryview(b) as view:
            return view.nbytes


# ---------------------------------------------------------------------------- the handler

class Handler(http.server.BaseHTTPRequestHandler):
    server_version = PROGRAM
    sys_version = ""
    timeout = config.REQUEST_TIMEOUT
    protocol_version = "HTTP/1.0"         # PLAN §5: HTTP/1.1 would need an exact length on everything
    expired = False

    def __init__(self, sock, client_address, front, data, deadline):
        self._front_data = data           # the head and whatever came with it, already read
        self._deadline = deadline         # 5 s after the connection came in
        super().__init__(sock, client_address, front)

    def setup(self):
        self.connection = self.request
        self.connection.settimeout(self.timeout)
        self.rfile = io.BufferedReader(_Prefixed(self.connection, self._front_data))
        self.wfile = _SocketWriter(self.connection)
        self.server.app.deadlines.watch(self, max(0.0, self._deadline - time.monotonic()))

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
            app.count("requests")
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
            app.count("refused")
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
        self._count_lock = threading.Lock()   # the counters are bumped from the front end and the workers
        self.deadlines = None
        self._httpd = None                # the front end; `.socket` is the listening socket
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
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            # No SO_REUSEADDR: on Windows it lets a second process bind the same port (PLAN §6).
            exclusive_address(sock)
            sock.bind((self.host, self.port))
            sock.listen(16)
            sock.setblocking(False)
        except OSError:
            sock.close()
            self.deadlines.close()
            raise
        self.port = sock.getsockname()[1]
        self._allowed_hosts = {"127.0.0.1:%d" % self.port, "localhost:%d" % self.port}
        self._httpd = _FrontEnd(self, sock, self.poll_interval)
        self._httpd.start()
        return self

    def stop(self):
        for hub in self.hubs:
            hub.close()
        if self._httpd is not None:
            self._httpd.stop()                    # its thread closes the listening socket on the way out
            self._httpd = None
        if self.deadlines is not None:
            self.deadlines.close()

    def alive(self):
        """Is the front-end thread still serving? False once it has ended, whatever ended it."""
        return self._httpd is not None and self._httpd.alive()

    def count(self, name):
        """Add one to `requests` or `refused`, under a lock: the front end and the workers both
        count, and an unguarded `+= 1` from two threads can lose one."""
        with self._count_lock:
            setattr(self, name, getattr(self, name) + 1)

    @property
    def origins(self):
        return {"http://" + h for h in self._allowed_hosts}

    # The guard ------------------------------------------------------------------------------

    def host_ok(self, hosts):
        """Exactly one Host header, and it is this server (the front end asks before a worker does)."""
        return len(hosts) == 1 and hosts[0].strip().lower() in self._allowed_hosts

    def check_basics(self, h):
        """What every request needs, whatever its route."""
        if not self.host_ok(h.headers.get_all("Host") or []):
            raise Refused(403, "wrong host")
        if not h.path.startswith("/"):
            raise Refused(400, "bad target")
        sites = h.headers.get_all("Sec-Fetch-Site") or []
        if len(sites) > 1 or (sites and sites[0].strip().lower() not in FETCH_SITES):
            raise Refused(403, "not from this page")
        origins = h.headers.get_all("Origin") or []      # absent is fine; if sent, it must be ours
        if len(origins) > 1 or (origins and origins[0].strip().lower() not in self.origins):
            raise Refused(403, "wrong origin")

    def check_guard(self, h, guard, target):
        query = parse_qs(target.query, keep_blank_values=True)
        if guard.token_header:
            tokens = h.headers.get_all(TOKEN_HEADER) or []
            if len(tokens) != 1 or not self._token_ok(tokens[0]):
                raise Refused(403, "token missing, doubled or wrong")
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
            ctypes = h.headers.get_all("Content-Type") or []         # doubled: refused, like every other header
            if len(ctypes) != 1 or ctypes[0].split(";")[0].strip().lower() != "application/json":
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
            except (UnicodeDecodeError, ValueError, RecursionError):     # nested too deep: the client's mistake
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

    def log_warning(self, msg):
        if self.logger is not None:
            self.logger.warning(msg)
