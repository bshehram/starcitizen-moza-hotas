"""The page (stage 3) in a real browser: headless Edge, driven over the DevTools protocol, showing a
real service instance that follows a sample log.

What is checked: every view the service can send has a renderer and draws; no text on the page is
under 18 px (computed, in every view, landscape and portrait, terminal region on and off); text
from the log or the plan is never parsed as markup; picking a view by hand, going back to Live,
adding and removing a quick timer work with real pointer events; a refused change is shown, not
swallowed.

The instance is the real service (`scdash.py run --background`) with a temporary data folder, a
free port, a stand-in game process (test_service_helpers.FakeGame) and a sample log whose times
are moved to just before now, so the board sees a session in progress. Edge runs with a profile
folder of its own and is closed through the DevTools protocol, then through the handle this test
holds. Skipped when Edge is not installed (the repo is public; set SCDASH_EDGE to its path).

The helpers here (`Edge`, `shift_log`, `Scene`) are also what the page's capture scripts use."""
import base64
import json
import os
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path

import scdash_testlib as lib
import test_service_helpers as H
from scdash import plan as P

EDGE_PATHS = (r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
              r"C:\Program Files\Microsoft\Edge\Application\msedge.exe")
FLOOR_PX = 18                     # PLAN §11: nothing under 18 px
SETTLE = 0.6                      # s: longer than app.js MOVED_MS, so the next test click is taken
TARGETS = ((1920, 1080), (1080, 1920))


def find_edge():
    env = os.environ.get("SCDASH_EDGE")
    if env and os.path.isfile(env):
        return env
    for p in EDGE_PATHS:
        if os.path.isfile(p):
            return p
    return None


# ---------------------------------------------------------------- a minimal DevTools client

class WS:
    """A WebSocket client, just enough for the DevTools protocol (text frames, no extensions)."""

    def __init__(self, url):
        assert url.startswith("ws://")
        hostport, _, path = url[5:].partition("/")
        host, _, port = hostport.partition(":")
        self.s = socket.create_connection((host, int(port)), timeout=30)
        key = base64.b64encode(os.urandom(16)).decode()
        self.s.sendall(("GET /%s HTTP/1.1\r\nHost: %s\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                        "Sec-WebSocket-Key: %s\r\nSec-WebSocket-Version: 13\r\n\r\n" % (path, hostport, key)).encode())
        buf = b""
        while b"\r\n\r\n" not in buf:
            buf += self.s.recv(4096)
        head, _, self.rest = buf.partition(b"\r\n\r\n")
        assert b" 101 " in head.split(b"\r\n")[0], head

    def _read(self, n):
        while len(self.rest) < n:
            b = self.s.recv(1 << 16)
            if not b:
                raise ConnectionError("closed")
            self.rest += b
        out, self.rest = self.rest[:n], self.rest[n:]
        return out

    def send(self, text):
        data = text.encode()
        hdr = bytearray([0x81])
        n = len(data)
        if n < 126:
            hdr.append(0x80 | n)
        elif n < 65536:
            hdr.append(0x80 | 126)
            hdr += struct.pack(">H", n)
        else:
            hdr.append(0x80 | 127)
            hdr += struct.pack(">Q", n)
        mask = os.urandom(4)
        hdr += mask
        self.s.sendall(bytes(hdr) + bytes(b ^ mask[i % 4] for i, b in enumerate(data)))

    def recv(self):
        msg = b""
        while True:
            b0, b1 = self._read(2)
            op, n = b0 & 0x0F, b1 & 0x7F
            if n == 126:
                n = struct.unpack(">H", self._read(2))[0]
            elif n == 127:
                n = struct.unpack(">Q", self._read(8))[0]
            payload = self._read(n)
            if op == 8:
                raise ConnectionError("ws closed")
            if op in (9, 10):
                continue
            msg += payload
            if b0 & 0x80:
                return msg.decode("utf-8", "replace")

    def close(self):
        try:
            self.s.close()
        except OSError:
            pass


class Target:
    def __init__(self, ws_url):
        self.ws = WS(ws_url)
        self.n = 0
        self.events = []

    def call(self, method, params=None, timeout=30):
        self.n += 1
        mid = self.n
        self.ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
        self.ws.s.settimeout(timeout)
        while True:
            m = json.loads(self.ws.recv())
            if m.get("id") == mid:
                if "error" in m:
                    raise RuntimeError("%s: %s" % (method, m["error"]))
                return m.get("result", {})
            self.events.append(m)

    def take_events(self, method):
        out = [e for e in self.events if e.get("method") == method]
        self.events = [e for e in self.events if e.get("method") != method]
        return out

    def pump(self, seconds=0.05):
        """Read whatever events arrive in `seconds` (the protocol pushes them unasked)."""
        self.ws.s.settimeout(seconds)
        try:
            while True:
                self.events.append(json.loads(self.ws.recv()))
        except (socket.timeout, TimeoutError):
            pass
        finally:
            self.ws.s.settimeout(30)

    def js(self, expr, timeout=30):
        r = self.call("Runtime.evaluate", {"expression": expr, "returnByValue": True, "awaitPromise": True},
                      timeout=timeout)
        if "exceptionDetails" in r:
            raise RuntimeError("page script failed: %s" % (r["exceptionDetails"].get("exception", {}).get("description")
                                                            or r["exceptionDetails"].get("text")))
        return r.get("result", {}).get("value")

    def wait(self, expr, timeout=15.0, step=0.1):
        end = time.monotonic() + timeout
        while True:
            v = self.js(expr)
            if v or time.monotonic() >= end:
                return v
            time.sleep(step)

    def size(self, w, h):
        self.call("Emulation.setDeviceMetricsOverride", {"width": w, "height": h, "deviceScaleFactor": 1, "mobile": False})
        time.sleep(0.15)

    def screenshot(self, path):
        data = self.call("Page.captureScreenshot", {"format": "png"}, timeout=60)["data"]
        Path(path).write_bytes(base64.b64decode(data))

    def center(self, selector):
        r = self.js("(() => { const e = document.querySelector(%s); if (!e) return null; const r = e.getBoundingClientRect();"
                    " return r.width && r.height ? [r.x + r.width / 2, r.y + r.height / 2] : null; })()" % json.dumps(selector))
        if not r:
            raise AssertionError("nothing to click at %s" % selector)
        return r

    def click(self, selector):
        """A real pointer click: move, press and release at the element's center."""
        x, y = self.center(selector)
        for kind in ("mouseMoved", "mousePressed", "mouseReleased"):
            self.call("Input.dispatchMouseEvent", {"type": kind, "x": x, "y": y, "button": "left",
                                                   "buttons": 1 if kind == "mousePressed" else 0, "clickCount": 1})

    def type_text(self, text):
        self.call("Input.insertText", {"text": text})

    def close(self):
        self.ws.close()


class Edge:
    """Headless Edge with a profile folder of its own; closed through the protocol, then through
    the handle we hold. Only ever one at a time."""

    def __init__(self, edge, extra=()):
        self.prof = Path(tempfile.mkdtemp(prefix="scdash-edge-"))
        args = [edge, "--headless=new", "--remote-debugging-port=0", "--user-data-dir=%s" % self.prof,
                "--no-first-run", "--no-default-browser-check", "--disable-extensions",
                "--disable-background-networking", "--disable-component-update", "--disable-sync",
                "--force-prefers-reduced-motion", "--hide-scrollbars", "--window-size=1920,1080"] + list(extra) + ["about:blank"]
        self.proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        f = self.prof / "DevToolsActivePort"
        H.wait_until(lambda: f.exists() and f.read_text().strip().count("\n") >= 1, 30)
        port, path = f.read_text().split("\n")[:2]
        self.port = int(port)
        self.browser = Target("ws://127.0.0.1:%d%s" % (self.port, path.strip()))

    def new_page(self, url):
        r = self.browser.call("Target.createTarget", {"url": "about:blank"})
        tid = r["targetId"]
        for _ in range(100):
            for t in self._list():
                if t.get("id") == tid and t.get("webSocketDebuggerUrl"):
                    page = Target(t["webSocketDebuggerUrl"])
                    page.call("Page.enable")
                    page.call("Runtime.enable")
                    page.size(1920, 1080)
                    page.call("Page.navigate", {"url": url})
                    return page
            time.sleep(0.05)
        raise RuntimeError("no page target")

    def _list(self):
        import http.client
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        c.request("GET", "/json/list")
        d = c.getresponse().read()
        c.close()
        return json.loads(d)

    def close(self):
        try:
            self.browser.call("Browser.close", timeout=5)
        except Exception:                              # noqa: BLE001
            pass
        try:
            self.proc.wait(15)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait(10)
        H.remove_tree(self.prof)


# ---------------------------------------------------------------- scenes: a sample log moved to now

def iso_ms(t):
    ms = int(round(t * 1000))
    return datetime.fromtimestamp(ms // 1000, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.") + "%03dZ" % (ms % 1000)


def parse_stamp(s):
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc).timestamp()


def shift_log(data, end_at, until=None, append=b""):
    """The log's lines up to the time `until` (ISO, the log's own times; None: all of them, quit
    line excepted), with every time moved so the last kept line is at `end_at` (epoch seconds).
    `append` is more lines in the log's own times, moved by the same amount. Returns (bytes, delta)."""
    def stamp(ln):
        if ln.startswith(b"<") and b">" in ln[:40]:
            try:
                return parse_stamp(ln[1:ln.index(b">")].decode("ascii"))
            except ValueError:
                return None
        return None

    at = data.find(b"<SystemQuit>")
    if until is None and at >= 0:
        data = data[:data.rfind(b"\n", 0, at) + 1]
    limit = parse_stamp(until) if until and until != "all" else None
    keep = []
    for ln in data.split(b"\n"):
        t = stamp(ln)
        if limit is not None and t is not None and t > limit:
            break
        keep.append(ln)
    keep += append.split(b"\n") if append else []
    times = [t for t in (stamp(ln) for ln in keep) if t is not None]
    delta = end_at - max(times)
    out = []
    for ln in keep:
        t = stamp(ln)
        if t is not None:
            ln = b"<" + iso_ms(t + delta).encode("ascii") + ln[ln.index(b">"):]
        out.append(ln)
    text = b"\n".join(x for x in out if x.strip()) + b"\n"
    return text, delta


def shift_plan(plan, delta):
    """A plan with each of its times (an ISO string with an offset) moved by `delta` seconds."""
    def move(v):
        if isinstance(v, str) and len(v) >= 19 and v[4] == "-" and v[10] == "T":
            try:
                t = datetime.fromisoformat(v).timestamp() + delta
                return datetime.fromtimestamp(t, timezone.utc).isoformat().replace("+00:00", "Z")
            except ValueError:
                return v
        if isinstance(v, dict):
            return {k: move(x) for k, x in v.items()}
        if isinstance(v, list):
            return [move(x) for x in v]
        return v
    return move(plan)


# The test plan of tests/test_views.py (RUN_A), for samples/run_a.log, with notes, a sell list and
# more materials.
RUN_A_PLAN = {
    "updated": "2026-11-26T15:00:00-08:00",
    "preflight": ["Switch on the AB6 base before you start the game"],
    "notes": ["Tungsten first, then the OX hauls the lots home"],
    "objectives": [{"id": "ore", "title": "Ore for the drives", "status": "in_progress",
                    "next_step": "Run A: Tungsten at ARC-L4",
                    "materials": [{"name": "Tungsten", "need_scu": 2.22, "held_scu": 0.4, "min_quality": 600},
                                  {"name": "Beryl", "need_scu": 2.22, "held_scu": 0.84, "min_quality": 700}]},
                   {"id": "rmc", "title": "RMC for repairs aboard the carrier", "status": "planned"}],
    "current_run": "run-a",
    "runs": [{"id": "run-a", "name": "Run A", "kind": "mining", "status": "in_progress", "targets": ["Tungsten"],
              "legs": [{"to": "ARC-L4 field", "codes": ["LOC_RR_S3_L4"], "view": "mining", "do": "Mine Tungsten"},
                       {"to": "MIC-L2", "codes": ["LOC_RR_S4_L2", "RR_MIC_L2"], "view": "refinery", "refine": ["Tungsten"]},
                       {"to": "New Babbage", "codes": ["NewBabbage_LOC", "Stanton4_NewBabbage"], "view": "cargo",
                        "do": "Haul the lots home"}]}],
    "timers": [{"id": "old", "kind": "refinery", "label": "Tungsten", "location": "MIC-L2",
                "started_at": "2026-11-26T15:40:00-08:00", "ready_at": "2026-11-26T16:20:00-08:00"},
               {"id": "new", "kind": "refinery", "label": "Beryl", "location": "MIC-L2 Long Forest Station",
                "started_at": "2026-11-26T16:00:00-08:00", "ready_at": "2026-11-26T18:00:00-08:00"}],
}


class Scene:
    """A real service instance (`run --background`) following a sample log moved to just before
    now, with a plan and settings of its own and a stand-in game process. Stopped through its
    shutdown endpoint; its folder removed."""

    def __init__(self, sample, until=None, plan=None, terminal=False, append=b"", lead=20.0, game=True):
        self.with_game = game
        self.inst = H.Instance()
        self.inst.data.mkdir(parents=True)
        raw = lib.sample_bytes(sample) if isinstance(sample, str) else sample
        log, self.delta = shift_log(raw, time.time() - lead, until, append)
        self.inst.write_log(log)
        if plan is not None:
            (self.inst.data / "plan.json").write_text(json.dumps(shift_plan(plan, self.delta)), encoding="utf-8")
        (self.inst.data / "config.json").write_text(json.dumps({"terminal": {"enabled": bool(terminal)}}), encoding="utf-8")
        self.game = H.FakeGame(self.inst.dir)

    def start(self):
        if self.with_game:
            self.game.start()
        self.inst.spawn(process=self.game.name)
        H.wait_until(lambda: H.state(self.inst.port) is not None, 20)
        return self

    @property
    def url(self):
        return "http://127.0.0.1:%d/" % self.inst.port

    @property
    def port(self):
        return self.inst.port

    def stop(self):
        try:
            H.end_instance(self.inst.data, self.inst.procs)
        finally:
            if self.with_game:
                self.game.stop()                       # its program file is in the folder
            if not H.remove_tree(self.inst.dir):
                raise AssertionError("could not remove %s" % self.inst.dir)


# The script run in the page to find text under the floor: every element that holds text of its
# own (and every ::before / ::after with content), drawn on the page, outside the terminal region
# (whose type is sized for the keyboard, PLAN §11).
SMALL_TYPE = r"""
(() => {
  const out = [];
  const floor = %d;
  for (const el of document.querySelectorAll("body *")) {
    if (el.closest("svg") || el.closest(".term")) continue;
    if (!el.getClientRects().length) continue;
    const own = Array.from(el.childNodes).some((n) => n.nodeType === 3 && n.textContent.trim());
    if (own) {
      const fs = parseFloat(getComputedStyle(el).fontSize);
      if (fs < floor) out.push(fs + "px " + el.tagName + "." + el.className + ": " + el.textContent.trim().slice(0, 40));
    }
    for (const pse of ["::before", "::after"]) {
      const ps = getComputedStyle(el, pse);
      const c = ps.content;
      if (c && c !== "none" && c !== "normal" && c !== '""' && ps.display !== "none") {
        const fs = parseFloat(ps.fontSize);
        if (fs < floor) out.push(fs + "px " + el.tagName + "." + el.className + pse + " " + c);
      }
    }
  }
  return out;
})()
""" % FLOOR_PX


def view_names():
    names = list(P.VIEWS)
    if P.REFERENCE not in names:
        names.append(P.REFERENCE)
    return names


@unittest.skipUnless(find_edge() and sys.platform == "win32", "needs Edge on Windows (set SCDASH_EDGE)")
class PageInTheBrowser(unittest.TestCase):
    """One service and one browser for all the checks: run_a.log stopped on the arrival at MIC-L2
    (the run's second leg: the Refinery view), with the plan written for it."""

    @classmethod
    def setUpClass(cls):
        notes = ["<img src=x id=pwn onerror=\"document.title='pwned'\"> & <b id=pwn2>bold</b> \u202e reversed"]
        plan = dict(RUN_A_PLAN, notes=notes + RUN_A_PLAN["notes"])
        cls.scene = Scene("run_a.log", until="2026-11-27T00:03:10.000Z", plan=plan, terminal=True).start()
        cls.edge = None
        try:
            cls.edge = Edge(find_edge())
            cls.page = cls.edge.new_page(cls.scene.url)
            ok = cls.page.wait("document.getElementById('view-host') && !document.getElementById('view-wait')", 20)
            if not ok:
                raise AssertionError("the page drew nothing")
        except Exception:
            cls.tearDownClass()
            raise

    @classmethod
    def tearDownClass(cls):
        try:
            if getattr(cls, "page", None):
                cls.page.close()
            if cls.edge:
                cls.edge.close()
        finally:
            cls.scene.stop()

    def tearDown(self):
        self.page.call("Fetch.disable")
        self.post("/api/view/live", {})
        self.page.js("document.documentElement.dataset.terminal = 'on'")
        self.page.size(1920, 1080)

    # helpers
    def post(self, path, body):
        return self.page.js("window.scdash.post(%s, %s)" % (json.dumps(path), json.dumps(body)))

    def shown(self):
        return self.page.js("document.getElementById('view-host').className")

    def pick(self, name):
        a = self.post("/api/view", {"view": name})
        self.assertTrue(a.get("ok"), a)
        self.assertTrue(self.page.wait("document.getElementById('view-host').className === 'v v--%s'" % name, 10),
                        "the page did not draw %s (it shows %s)" % (name, self.shown()))

    # the checks
    def test_every_view_the_service_can_send_has_a_renderer_and_draws(self):
        drawn = self.page.js("window.scdash.views")
        self.assertEqual(sorted(drawn), sorted(view_names()))
        for name in view_names():
            self.pick(name)
            blocks = self.page.js("document.querySelectorAll('#view-host > .blk').length")
            self.assertGreater(blocks, 0, name)
            # the view fits its region: nothing scrolls out of sight
            over = self.page.js("(() => { const v = document.getElementById('view'); return [v.scrollHeight - v.clientHeight, v.scrollWidth - v.clientWidth]; })()")
            self.assertLessEqual(max(over), 1, "%s overflows its region by %s" % (name, over))

    def test_no_text_under_18_px_in_any_view_either_way_up_terminal_on_and_off(self):
        problems = []
        self.page.js("document.getElementById('sw-more').click()")       # the panel is part of the page too
        for name in view_names():
            self.pick(name)
            for w, h in TARGETS:
                for term in ("on", "off"):
                    self.page.size(w, h)
                    self.page.js("document.documentElement.dataset.terminal = %s" % json.dumps(term))
                    time.sleep(0.1)
                    for x in self.page.js(SMALL_TYPE):
                        problems.append("%s %dx%d terminal %s: %s" % (name, w, h, term, x))
        self.page.js("document.getElementById('sw-more').click()")
        self.assertEqual(problems, [])

    def test_text_from_the_plan_is_text_never_markup(self):
        self.pick("now")
        self.assertIsNone(self.page.js("document.getElementById('pwn') && 'img'"))
        self.assertIsNone(self.page.js("document.getElementById('pwn2') && 'b'"))
        self.assertNotEqual(self.page.js("document.title"), "pwned")
        self.assertTrue(self.page.js("document.getElementById('view-host').textContent.includes('<img src=x id=pwn')"))

    def test_pick_a_view_go_back_to_live_add_and_remove_a_timer_with_the_pointer(self):
        p = self.page
        auto = self.shown()
        p.click("#sw-more")
        self.assertTrue(p.wait("!document.getElementById('panel').hidden", 5))
        p.click('#picks .pick[data-view="mining"]')
        self.assertTrue(p.wait("document.getElementById('view-host').className === 'v v--mining'", 10))
        self.assertTrue(p.wait("!document.getElementById('pickbar').hidden", 5))
        self.assertEqual(p.js("document.getElementById('sw-live').getAttribute('aria-pressed')"), "false")
        time.sleep(SETTLE)
        p.click("#pickbar-live")
        self.assertTrue(p.wait("document.getElementById('view-host').className === %s" % json.dumps(auto), 10))
        self.assertTrue(p.wait("document.getElementById('pickbar').hidden", 5))
        time.sleep(SETTLE)
        # the rig reference, and back with the switcher's Live cell
        p.click("#sw-rig")
        self.assertTrue(p.wait("document.getElementById('view-host').className === 'v v--reference'", 10))
        self.assertEqual(p.js("document.getElementById('sw-rig').getAttribute('aria-pressed')"), "true")
        time.sleep(SETTLE)
        p.click("#sw-live")
        self.assertTrue(p.wait("document.getElementById('view-host').className === %s" % json.dumps(auto), 10))
        time.sleep(SETTLE)
        # a quick timer: named, added, shown, removed
        p.click("#sw-more")
        self.assertTrue(p.wait("!document.getElementById('panel').hidden", 5))
        p.click("#q-label")
        p.type_text("Tea break")
        p.click("#qmins .qmin")
        self.assertTrue(p.wait("Array.from(document.querySelectorAll('#qlist .qrow__name')).some((n) => n.textContent === 'Tea break')", 10))
        self.assertEqual(p.js("document.getElementById('q-label').value"), "")
        time.sleep(SETTLE)
        p.click("#qlist .qdel")
        self.assertTrue(p.wait("!document.querySelector('#qlist .qrow')", 10))
        p.click("#sw-more")
        self.assertTrue(p.wait("document.getElementById('panel').hidden", 5))

    def test_a_refused_change_is_shown_and_changes_nothing(self):
        p = self.page
        auto = self.shown()
        p.call("Fetch.enable", {"patterns": [{"urlPattern": "*/api/view*", "requestStage": "Request"}]})
        p.click("#sw-more")
        p.wait("!document.getElementById('panel').hidden", 5)
        p.click('#picks .pick[data-view="combat"]')
        paused = self._paused()
        body = base64.b64encode(b'{"error": "still reading the log: pick again in a moment"}').decode()
        p.call("Fetch.fulfillRequest", {"requestId": paused, "responseCode": 503, "body": body,
                                        "responseHeaders": [{"name": "Content-Type", "value": "application/json"}]})
        self.assertTrue(p.wait("!document.getElementById('toast').hidden && document.getElementById('toast').textContent.includes('Not taken')", 5))
        self.assertIn("busy", p.js("document.getElementById('toast').textContent"))
        self.assertEqual(self.shown(), auto)
        self.assertIsNone(p.js("document.querySelector('[aria-busy]') && 'busy'"))
        # no answer at all
        p.click('#picks .pick[data-view="combat"]')
        paused = self._paused()
        p.call("Fetch.failRequest", {"requestId": paused, "errorReason": "ConnectionRefused"})
        self.assertTrue(p.wait("document.getElementById('toast').textContent.includes('did not answer')", 5))
        self.assertEqual(self.shown(), auto)
        p.call("Fetch.disable")
        p.click("#toast")
        self.assertTrue(p.wait("document.getElementById('toast').hidden", 5))

    def _paused(self):
        end = time.monotonic() + 10
        while time.monotonic() < end:
            self.page.pump(0.1)
            ev = self.page.take_events("Fetch.requestPaused")
            if ev:
                return ev[0]["params"]["requestId"]
        raise AssertionError("the request was not sent")


@unittest.skipUnless(find_edge() and sys.platform == "win32", "needs Edge on Windows (set SCDASH_EDGE)")
class StickBaseMissingInTheBrowser(unittest.TestCase):
    """samples/preflight_fail.log (the keyboard took joystick 1, no AB6) at the main menu: the page
    goes red. The Preflight view is the failure drawn in full (the alert is not repeated above it);
    any other view carries the red alert across its top."""

    @classmethod
    def setUpClass(cls):
        cls.scene = Scene("preflight_fail.log").start()
        cls.edge = None
        try:
            cls.edge = Edge(find_edge())
            cls.page = cls.edge.new_page(cls.scene.url)
            cls.page.wait("document.getElementById('view-host') && !document.getElementById('view-wait')", 20)
        except Exception:
            cls.tearDownClass()
            raise

    @classmethod
    def tearDownClass(cls):
        try:
            if getattr(cls, "page", None):
                cls.page.close()
            if cls.edge:
                cls.edge.close()
        finally:
            cls.scene.stop()

    def test_the_red_screen_and_the_red_alert(self):
        p = self.page
        self.assertTrue(p.wait("document.getElementById('view-host').className === 'v v--preflight'", 10))
        self.assertTrue(p.js("document.getElementById('app').classList.contains('is-fail')"))
        self.assertEqual(p.js("document.querySelector('.fail__kicker').textContent"), "Preflight failed")
        self.assertIn("Stick base", p.js("document.querySelector('.fail__title').textContent"))
        self.assertEqual(p.js("document.getElementById('s-sticks').textContent"), "Fail")
        self.assertEqual(p.js("document.getElementById('s-state').textContent"), "Preflight failed")
        self.assertEqual(p.js("document.querySelector('.dev--bad .dev__name b').textContent"), "MOZA AB6 FFB Base")
        a = p.js("window.scdash.post('/api/view', {view: 'now'})")
        self.assertTrue(a.get("ok"), a)
        self.assertTrue(p.wait("document.getElementById('view-host').className === 'v v--now'", 10))
        alert = p.js("(() => { const a = document.querySelector('#alerts .alert--bad'); return a && [a.querySelector('.alert__kind').firstChild.textContent, a.querySelector('.alert__title').textContent]; })()")
        self.assertEqual(alert, ["Preflight failed", "Stick base not detected"])
        self.assertFalse(p.js("document.getElementById('app').classList.contains('is-fail')"))
        p.js("window.scdash.post('/api/view/live', {})")
        self.assertTrue(p.wait("document.getElementById('view-host').className === 'v v--preflight'", 10))


if __name__ == "__main__":
    unittest.main()
