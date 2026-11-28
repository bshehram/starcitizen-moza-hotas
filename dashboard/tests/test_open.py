"""`open` and `shortcut` (PLAN §6, §11 "Opening the window", §12 stage 4).

No test starts a real browser or shows a window: every `open` is given a stand-in "browser" (a
small script behind a .cmd file, named with --browser) that records the command line it was
started with and exits. Every instance has a temporary data folder, a free port and a log of its
own, and is stopped through its shutdown endpoint (test_service_helpers.Instance); the window's
profile folder is a temporary one too, so the user's own dashboard window is never looked at.
Every `open` passes --main, so the tests do not depend on how many displays are connected; the
second display's placement is tested on made-up display lists."""
import contextlib
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

import scdash_testlib as lib
import test_service_helpers as h
from scdash import config, service, window, winutil
from test_server import Stream

FAST = {"process_check_seconds": 2.0, "poll_seconds": 0.25, "state_save_seconds": 2.0}
LAND = "--window-size=%d,%d" % (1920 + window.FRAME[0], 1080 + window.FRAME[1])
PORT_ = "--window-size=%d,%d" % (1080 + window.FRAME[0], 1920 + window.FRAME[1])

FAKE_BROWSER = r'''
import ctypes, json, os, sys, time
here = os.path.dirname(os.path.abspath(__file__))
out = os.path.join(here, "calls")
os.makedirs(out, exist_ok=True)
below = None
if os.name == "nt":
    k = ctypes.WinDLL("kernel32")
    k.GetCurrentProcess.restype = ctypes.c_void_p
    k.GetPriorityClass.argtypes = [ctypes.c_void_p]
    below = k.GetPriorityClass(k.GetCurrentProcess()) == 0x4000
name = "%d-%d.json" % (time.time_ns(), os.getpid())
with open(os.path.join(out, name + ".part"), "w", encoding="utf-8") as f:
    json.dump({"argv": sys.argv[1:], "cwd": os.getcwd(), "below_normal": below}, f)
os.replace(os.path.join(out, name + ".part"), os.path.join(out, name))
'''


class FakeBrowser:
    """A stand-in browser: records each command line it is started with, then exits."""

    def __init__(self, folder):
        self.dir = Path(folder) / "fakebrowser"
        self.dir.mkdir(parents=True)
        script = self.dir / "fakebrowser.py"
        script.write_text(FAKE_BROWSER, encoding="utf-8")
        if winutil.IS_WINDOWS:
            self.program = self.dir / "fakebrowser.cmd"
            self.program.write_text('@"%s" "%s" %%*\r\n' % (sys.executable, script), encoding="ascii")
        else:
            self.program = self.dir / "fakebrowser"
            self.program.write_text('#!/bin/sh\nexec "%s" "%s" "$@"\n' % (sys.executable, script))
            os.chmod(self.program, 0o755)

    def calls(self):
        folder = self.dir / "calls"
        if not folder.is_dir():
            return []
        return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(folder.glob("*.json"))]

    def wait_calls(self, n, seconds=15.0):
        h.wait_until(lambda: len(self.calls()) >= n, seconds, 0.1)
        return self.calls()


def work_area_allows(size):
    """Does the primary display's work area hold a window of this size (scaled units)?"""
    mons = winutil.monitors()
    prim = next((m for m in mons if m["primary"]), None)
    if prim is None:
        return True
    l, t, r, b = prim["work"]
    s = prim["scale"]
    return (r - l) / s >= size[0] and (b - t) / s >= size[1]


class OpenCase(unittest.TestCase):
    def setUp(self):
        self.inst = h.Instance()
        self.inst.data.mkdir(parents=True)
        self.profile = self.inst.dir / "profile"
        self.write_config(profile=str(self.profile))
        self.fake = FakeBrowser(self.inst.dir)
        self.streams = []
        self.inst.write_log(h.log_bytes())

    def tearDown(self):
        for s in self.streams:
            s.close()
        self.inst.cleanup()

    def write_config(self, **window_settings):
        cfg = dict(FAST, port=self.inst.port)
        if window_settings:
            cfg["window"] = window_settings
        service.write_json(self.inst.data / "config.json", cfg)

    def open(self, *extra, env=None, timeout=60):
        e = dict(os.environ)
        e.pop(config.LIVE_ENV, None)
        e.update(env or {})
        cmd = [sys.executable, str(h.SCRIPT), "open"] + [str(a) for a in self.inst.args(process="nosuchgame_%d.exe" % os.getpid())]
        cmd += ["--browser", str(self.fake.program), "--main"] + [str(a) for a in extra]
        return subprocess.run(cmd, cwd=str(h.REPO), capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=timeout, env=e)

    def start(self):
        r = h.cli("start", *self.inst.args(process="nosuchgame_%d.exe" % os.getpid()))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return self.info()["run"]["pid"]

    def info(self):
        return service.instance_info(service.Paths(self.inst.data), self.inst.port)

    def hold_profile(self):
        """What the window's own browser leaves while it runs: the profile's lock file."""
        self.profile.mkdir(parents=True, exist_ok=True)
        (self.profile / "lockfile").write_bytes(b"")

    def connect_page(self):
        s = Stream(self.inst.port)
        self.streams.append(s)
        self.assertTrue(h.wait_until(lambda: (h.status(self.inst.port) or {}).get("pages") == len(self.streams), 10))
        return s

    def service_log(self):
        p = self.inst.data / "service.log"
        return p.read_text(encoding="utf-8") if p.exists() else ""


class Opening(OpenCase):
    def test_a_stopped_service_is_started_and_the_window_opened(self):
        lad = self.inst.dir / "localappdata"
        self.write_config()                                  # no profile setting: the default one
        self.assertFalse(self.info()["healthy"])
        r = self.open(env={"LOCALAPPDATA": str(lad)})
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("Started: pid", r.stdout)
        self.assertTrue(self.info()["healthy"], "open started the service")
        calls = self.fake.wait_calls(1)
        self.assertEqual(len(calls), 1, r.stdout)
        argv = calls[0]["argv"]
        self.assertEqual(argv[0], "--user-data-dir=%s" % (lad / "scdash" / "browser"))
        self.assertEqual(argv[1], "--app=http://127.0.0.1:%d/" % self.inst.port)
        for switch in window.QUIET:
            self.assertIn(switch, argv)
        self.assertNotIn("--start-fullscreen", argv)
        self.assertFalse([a for a in argv if a.startswith("--kiosk")])
        if work_area_allows((1936, 1119)):
            self.assertIn(LAND, argv)
        pos = [a for a in argv if a.startswith("--window-position=")]
        self.assertEqual(len(pos), 1, argv)
        x, y = (int(v) for v in pos[0].split("=", 1)[1].split(","))
        self.assertTrue(x >= 0 and y >= 0, pos)
        if winutil.IS_WINDOWS:
            self.assertTrue(calls[0]["below_normal"], "the browser starts below normal priority")
        self.assertIn("Opened the dashboard window", r.stdout)
        self.assertIn("INFO open: started fakebrowser.cmd" if winutil.IS_WINDOWS else "INFO open: started",
                      self.service_log())

    def test_a_running_service_is_not_started_twice_and_portrait_is_taller(self):
        pid = self.start()
        r = self.open("--portrait")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("Already running: pid %d" % pid, r.stdout)
        self.assertEqual(self.info()["run"]["pid"], pid)
        self.assertEqual(self.service_log().count("listening on"), 1)
        argv = self.fake.wait_calls(1)[0]["argv"]
        self.assertEqual(argv[0], "--user-data-dir=%s" % self.profile)
        if work_area_allows((1096, 1959)):
            self.assertIn(PORT_, argv)
        self.assertNotIn(LAND, argv)

    def test_a_second_open_with_the_window_open_opens_nothing(self):
        self.start()
        self.hold_profile()
        self.connect_page()
        r = self.open()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("already open", r.stdout)
        time.sleep(1.0)
        self.assertEqual(self.fake.calls(), [], "no browser started")

    def test_a_page_in_another_browser_does_not_stop_the_window(self):
        """A connected page while the window's own browser is not running is a tab elsewhere."""
        self.start()
        self.connect_page()
        r = self.open()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("1 page already connected", r.stdout)
        self.assertEqual(len(self.fake.wait_calls(1)), 1)

    def test_a_window_open_from_before_the_start_is_given_time_to_reconnect(self):
        self.hold_profile()

        def page_comes_back():
            if h.wait_until(lambda: self.info()["healthy"], 20, 0.1):
                time.sleep(1.5)                              # the page's own retry
                self.streams.append(Stream(self.inst.port))
        t = threading.Thread(target=page_comes_back, daemon=True)
        t.start()
        r = self.open()
        t.join(30)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("Started: pid", r.stdout)
        self.assertIn("already open", r.stdout)
        time.sleep(1.0)
        self.assertEqual(self.fake.calls(), [])

    def test_a_window_that_does_not_reconnect_is_opened_after_the_wait(self):
        self.hold_profile()
        t0 = time.monotonic()
        r = self.open()
        took = time.monotonic() - t0
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("Waiting a few seconds", r.stdout)
        self.assertGreater(took, window.RECONNECT_SECONDS - 2)
        self.assertEqual(len(self.fake.wait_calls(1)), 1)

    def test_a_browser_that_is_not_there_is_a_plain_failure(self):
        missing = self.inst.dir / "nowhere" / "browser.exe"
        e = dict(os.environ)
        e.pop(config.LIVE_ENV, None)
        cmd = [sys.executable, str(h.SCRIPT), "open"] + [str(a) for a in self.inst.args()] + ["--browser", str(missing)]
        r = subprocess.run(cmd, cwd=str(h.REPO), capture_output=True, text=True, encoding="utf-8", timeout=60, env=e)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("was not found", r.stdout)
        self.assertFalse(self.info()["healthy"], "no service is started when there is nothing to show it in")
        self.assertIn("ERROR open: The browser", self.service_log())

    def test_the_window_browser_setting_is_used(self):
        self.write_config(profile=str(self.profile), browser=str(self.fake.program))
        self.start()
        e = dict(os.environ)
        e.pop(config.LIVE_ENV, None)
        cmd = [sys.executable, str(h.SCRIPT), "open", "--data", str(self.inst.data), "--main"]
        r = subprocess.run(cmd, cwd=str(h.REPO), capture_output=True, text=True, encoding="utf-8", timeout=60, env=e)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(len(self.fake.wait_calls(1)), 1)


# ---------------------------------------------------------------------------- placement, no processes

def mon(left, top, w, h, scale=1.0, primary=False, taskbar=0):
    return {"bounds": (left, top, left + w, top + h), "work": (left, top, left + w, top + h - taskbar),
            "primary": primary, "scale": scale}


class Placement(unittest.TestCase):
    def test_one_display_centers_a_window_for_the_side_monitors_size(self):
        p = window.placement([mon(0, 0, 3840, 2160, primary=True, taskbar=48)])
        self.assertEqual(p["where"], "main")
        self.assertFalse(p["fullscreen"])
        self.assertEqual(p["size"], (1936, 1119))
        self.assertEqual(p["page"], (1920, 1080))
        self.assertEqual(p["position"], ((3840 - 1936) // 2, (2112 - 1119) // 2))
        self.assertFalse(p["capped"])
        q = window.placement([mon(0, 0, 3840, 2160, primary=True, taskbar=48)], portrait=True)
        self.assertEqual(q["size"], (1096, 1959))
        self.assertEqual(q["page"], (1080, 1920))
        self.assertEqual(q["position"], ((3840 - 1096) // 2, (2112 - 1959) // 2))

    def test_a_small_or_scaled_display_caps_the_window_at_its_work_area(self):
        p = window.placement([mon(0, 0, 1920, 1080, scale=1.25, primary=True, taskbar=48)])
        self.assertTrue(p["capped"])
        self.assertEqual(p["size"], (1536, 825))             # 1920 / 1.25, 1032 / 1.25
        self.assertEqual(p["page"], (1536 - window.FRAME[0], 825 - window.FRAME[1]))
        self.assertEqual(p["position"], (0, 0))
        q = window.placement([mon(0, 0, 3840, 2160, scale=1.5, primary=True, taskbar=72)], portrait=True)
        self.assertEqual(q["size"], (1096, 1392))            # 2088 / 1.5 = 1392 tall at most
        self.assertTrue(q["capped"])

    def test_a_second_display_gets_the_window_full_screen(self):
        side = mon(3840, 0, 1920, 1080)
        p = window.placement([mon(0, 0, 3840, 2160, scale=1.5, primary=True), side], portrait=True)
        self.assertEqual(p["where"], "side")
        self.assertTrue(p["fullscreen"])
        self.assertIsNone(p["size"])
        self.assertEqual(p["display"], (1920, 1080))
        x, y = p["position"]
        # Inside the display whether read in physical pixels (3840-5760) or scaled ones (2560-4480).
        self.assertTrue(3840 + window.INSIDE_MARGIN <= x <= 4480 - window.INSIDE_MARGIN, x)
        self.assertTrue(window.INSIDE_MARGIN <= y <= 1080 - window.INSIDE_MARGIN, y)

    def test_a_display_to_the_left_or_turned_to_portrait(self):
        p = window.placement([mon(0, 0, 1920, 1080, primary=True), mon(-1920, 0, 1920, 1080)])
        self.assertEqual(p["position"], (-960, 540))
        q = window.placement([mon(0, 0, 2560, 1440, primary=True), mon(2560, -300, 1080, 1920)])
        self.assertEqual(q["display"], (1080, 1920))
        x, y = q["position"]
        self.assertTrue(2560 < x < 3640 and -300 < y < 1620, q["position"])

    def test_the_side_monitors_size_is_preferred_and_main_keeps_a_window(self):
        three = [mon(0, 0, 2560, 1440, primary=True), mon(2560, 0, 2560, 1440), mon(5120, 0, 1080, 1920)]
        self.assertEqual(window.placement(three)["display"], (1080, 1920))
        p = window.placement([mon(0, 0, 3840, 2160, primary=True), mon(3840, 0, 1920, 1080)], main=True)
        self.assertEqual(p["where"], "main")
        self.assertEqual(p["size"], (1936, 1119))

    def test_nothing_known_about_the_display(self):
        p = window.placement([])
        self.assertIsNone(p["position"])
        self.assertEqual(p["size"], (1936, 1119))

    def test_the_command_line(self):
        place = window.placement([mon(0, 0, 3840, 2160, primary=True)])
        cmd = window.command(Path("C:/b/msedge.exe"), Path("C:/p"), "http://127.0.0.1:47826/", place)
        self.assertEqual(cmd[:4], [str(Path("C:/b/msedge.exe")), "--user-data-dir=%s" % Path("C:/p"),
                                   "--app=http://127.0.0.1:47826/", "--window-position=952,520"])
        self.assertEqual(cmd[4], "--window-size=1936,1119")
        self.assertEqual(cmd[5:], list(window.QUIET))
        side = window.placement([mon(0, 0, 1920, 1080, primary=True), mon(1920, 0, 1920, 1080)])
        cmd = window.command("msedge.exe", "p", "http://127.0.0.1:1/", side)
        self.assertIn("--start-fullscreen", cmd)
        self.assertIn("--window-position=2880,540", cmd)
        self.assertFalse([a for a in cmd if a.startswith(("--window-size", "--kiosk"))])
        self.assertEqual(set(window.QUIET), {"--no-first-run", "--no-default-browser-check",
                                             "--disable-background-networking", "--disable-component-update",
                                             "--disable-sync"})


class Browser(unittest.TestCase):
    def test_a_named_browser(self):
        with lib.TempDir() as d:
            exe = d / "mybrowser.exe"
            exe.write_bytes(b"")
            self.assertEqual(window.find_browser(str(exe)), exe.resolve())
            self.assertIsNone(window.find_browser(str(d / "missing.exe")))
            self.assertIsNone(window.find_browser("nosuchbrowser-%d" % os.getpid()))

    @unittest.skipUnless(winutil.IS_WINDOWS, "App Paths is a Windows registry key")
    def test_edge_then_chrome_by_default(self):
        found = window.find_browser()
        if found is None:
            self.skipTest("neither Edge nor Chrome is installed")
        self.assertIn(found.name.lower(), ("msedge.exe", "chrome.exe"))
        edge = winutil.app_path("msedge.exe")
        if edge and Path(edge).is_file():
            self.assertEqual(found, Path(edge), "Edge comes first")
        self.assertEqual(window.browser_label(found), "Edge" if found.name.lower() == "msedge.exe" else "Chrome")
        self.assertIsNone(winutil.app_path("nosuchprogram-%d.exe" % os.getpid()))

    def test_the_profile_folder(self):
        with lib.TempDir() as d:
            with mock.patch.dict(os.environ, {"LOCALAPPDATA": str(d)}):
                self.assertEqual(window.profile_dir(None), d / "scdash" / "browser")
                self.assertEqual(window.profile_dir("%LOCALAPPDATA%\\other" if winutil.IS_WINDOWS else "$LOCALAPPDATA/other"),
                                 (d / "other").resolve())
            prof = d / "browser"
            self.assertFalse(window.profile_in_use(prof))
            prof.mkdir()
            self.assertFalse(window.profile_in_use(prof))
            (prof / ("lockfile" if winutil.IS_WINDOWS else "SingletonLock")).write_bytes(b"")
            self.assertTrue(window.profile_in_use(prof))
        self.assertEqual(window.PROFILE_SHOWN, r"%LOCALAPPDATA%\scdash\browser")


# ---------------------------------------------------------------------------- no console

def load_cli():
    spec = importlib.util.spec_from_file_location("scdash_cli_under_test", str(h.SCRIPT))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class NoConsole(unittest.TestCase):
    """Run from the shortcut, `open` has no console: what the user must see goes into a message
    box, and a problem into the service's log as well."""

    def test_problems_go_to_a_message_box_and_the_log(self):
        cli = load_cli()
        with lib.TempDir() as d:
            paths = service.Paths(d / "data")
            with mock.patch.object(winutil, "message_box") as box:
                out = cli._Out(paths, console=False)
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    self.assertEqual(out.fail("no browser"), 1)
                    self.assertEqual(out.tell("already open"), 0)
                    out.say("Started: pid 1")
                self.assertEqual(buf.getvalue(), "", "nothing printed")
                self.assertEqual(box.call_args_list, [mock.call(cli.TITLE, "no browser", error=True),
                                                      mock.call(cli.TITLE, "already open", error=False)])
            text = paths.log.read_text(encoding="utf-8")
            self.assertIn(" ERROR open: no browser", text)
            self.assertNotIn("already open", text)
            self.assertNotIn("Started", text)
            with mock.patch.object(winutil, "message_box") as box:
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    cli._Out(paths, console=True).fail("again")
                self.assertEqual(box.call_count, 0)
                self.assertIn("again", buf.getvalue())


# ---------------------------------------------------------------------------- shortcut, icon

@unittest.skipUnless(winutil.IS_WINDOWS, "a .lnk is a Windows file")
class Shortcut(unittest.TestCase):
    def test_the_shortcut_runs_open_through_pythonw(self):
        with lib.TempDir() as d:
            r = h.cli("shortcut", "--folder", d)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            path = d / "SC Dashboard.lnk"
            self.assertTrue(path.is_file(), r.stdout)
            lnk = winutil.read_shortcut(path)
            pyw = Path(sys.executable).with_name("pythonw.exe")
            if pyw.is_file():
                self.assertEqual(os.path.normcase(lnk["target"]), os.path.normcase(str(pyw)))
            self.assertEqual(lnk["arguments"], '"%s" open' % h.SCRIPT.resolve())
            self.assertEqual(os.path.normcase(lnk["workdir"]), os.path.normcase(str(h.REPO.resolve())))
            self.assertEqual(os.path.normcase(lnk["icon"][0]), os.path.normcase(str(lib.DASHBOARD / "scdash.ico")))
            self.assertTrue(lnk["description"])

    def test_a_shortcut_in_the_repo_is_never_committed(self):
        if shutil.which("git") is None:
            self.skipTest("no git")
        r = subprocess.run(["git", "check-ignore", "-q", "dashboard/SC Dashboard.lnk"], cwd=str(h.REPO),
                           capture_output=True, timeout=30)
        if r.returncode == 128:
            # git answers 128 when this copy is not a checkout at all (an export, a zip): then
            # nothing here can be committed, and there is no ignore rule to ask about.
            self.skipTest("not a git checkout")
        self.assertEqual(r.returncode, 0, "dashboard/SC Dashboard.lnk is not git-ignored")


class Icon(unittest.TestCase):
    def test_the_icon_has_the_sizes_windows_asks_for(self):
        data = (lib.DASHBOARD / "scdash.ico").read_bytes()
        reserved, kind, count = (int.from_bytes(data[i:i + 2], "little") for i in (0, 2, 4))
        self.assertEqual((reserved, kind), (0, 1), "an ICO file")
        sizes = {data[6 + 16 * i] or 256 for i in range(count)}
        self.assertTrue({16, 24, 32, 48, 256} <= sizes, sizes)
        self.assertTrue((lib.DASHBOARD / "make_icon.py").is_file(), "the icon's generator is kept beside it")


if __name__ == "__main__":
    unittest.main()
