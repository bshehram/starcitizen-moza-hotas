"""The dashboard's own window: what `scdash.py open` starts (PLAN §6, §11 "Opening the window",
§12 stage 4).

The page is shown in a Chromium browser's app mode (Edge first, Chrome as the fallback): a window
with no tabs, address bar or toolbar. It runs from a profile folder of its own,
`%LOCALAPPDATA%\\scdash\\browser`, for two reasons (PLAN §10, §11): without it the launch is handed
to the browser the user already runs and the placement switches are dropped, and the switches that
keep a new profile from going online by itself apply to it alone.

- **One display** (the case until the side monitor is connected): a normal window centered on the
  primary display, sized so that the page inside gets 1920x1080 CSS pixels (1080x1920 with
  `portrait`), or as much as the display's work area allows. What the window's own frame adds
  around the page (`FRAME`) is an estimate [unverified: check `innerWidth` and `innerHeight` in
  the window, PLAN §14].
- **A second display:** a point well inside it and `--start-fullscreen`, so the window fills it in
  whichever way it stands; its bounds are read from Windows each time, never stored. Whether
  Chromium reads `--window-position` in physical or in scaled pixels is not known (PLAN §14 item
  2), so the point is chosen to lie inside the display under both readings when it can
  [unverified: no second display yet].

Nothing here decides whether to open: that is `cmd_open` in scdash.py (a window already open, the
service running). Nothing here ends, signals or looks inside a process.
"""
import os
import shutil
import subprocess
from pathlib import Path

from . import winutil

LANDSCAPE = (1920, 1080)          # the side monitor's pixel size (PLAN §11)
PORTRAIT = (1080, 1920)
# What the app window adds around its page, in CSS pixels: the left and right borders, and the
# title bar plus the bottom border. An estimate for Edge on Windows 11 [unverified].
FRAME = (16, 39)
SIDE_SIZES = {(1920, 1080), (1080, 1920)}   # a second display of this size is taken for the side monitor
INSIDE_MARGIN = 100               # "well inside": the point is at least this far from the display's edges

# Every launch: no first-run pages, and nothing that goes online by itself (PLAN §8, §11).
QUIET = ("--no-first-run", "--no-default-browser-check", "--disable-background-networking",
         "--disable-component-update", "--disable-sync")

# A page that was open when the service went away reconnects by itself: its stream retries after
# the server's `retry:` (3 s), and the page opens a new one 5 s after an HTTP error (web/app.js).
# `open` waits until the service has been up this long before it decides a window is needed.
RECONNECT_SECONDS = 8.0

EDGE, CHROME = "msedge.exe", "chrome.exe"
INSTALL_FOLDERS = {EDGE: r"Microsoft\Edge\Application", CHROME: r"Google\Chrome\Application"}
ON_PATH = ("msedge", "chrome", "microsoft-edge", "google-chrome", "chromium", "chromium-browser")

PROFILE_SHOWN = r"%LOCALAPPDATA%\scdash\browser"   # how docs and messages write the default


def profile_dir(setting=None):
    """The window's browser profile folder: the setting when there is one (environment variables
    in it are expanded), else %LOCALAPPDATA%\\scdash\\browser. Never inside the repo or the game
    folder: the browser writes there for as long as the window is open (PLAN §10)."""
    if setting:
        return Path(os.path.expandvars(str(setting))).expanduser().resolve()
    base = os.environ.get("LOCALAPPDATA")
    if base:
        return Path(base) / "scdash" / "browser"
    return Path.home() / ".scdash" / "browser"


def profile_in_use(profile):
    """Is a browser running from this profile folder now? Chromium keeps a file named `lockfile`
    in it for as long as it runs, opened delete-on-close, so the file goes when the browser ends,
    however it ends [seen 2026-11-28: present while the window's Edge ran, and opening it without
    delete sharing was refused]. Only its presence is looked at: opening it could get in the way
    of a browser starting at that moment. Elsewhere Chromium's lock is a link, `SingletonLock`."""
    p = Path(profile)
    if winutil.IS_WINDOWS:
        return (p / "lockfile").exists()
    return os.path.lexists(p / "SingletonLock")


def find_browser(name=None):
    """The browser program to start, or None.

    `name` (the `--browser` option or the `window.browser` setting): a path to the program, or a
    program name such as "chrome.exe", looked up under App Paths and then on PATH. A name that is
    not found is not replaced by another browser: the user asked for that one.

    Without a name: Edge, then Chrome, each where it registered itself under App Paths (the place
    Microsoft documents for a program's location), then in its usual install folder; last, PATH.
    """
    if name:
        text = os.path.expandvars(str(name)).strip().strip('"')
        p = Path(text).expanduser()
        if p.is_file():
            return p.resolve()
        if "\\" in text or "/" in text:
            return None                                   # a path, and nothing is there
        for cand in ((text,) if text.lower().endswith(".exe") else (text, text + ".exe")):
            hit = winutil.app_path(cand) or shutil.which(cand)
            if hit and Path(hit).is_file():
                return Path(hit)
        return None
    for exe in (EDGE, CHROME):
        hit = winutil.app_path(exe)
        if hit and Path(hit).is_file():
            return Path(hit)
        for var in ("ProgramFiles(x86)", "ProgramFiles", "LOCALAPPDATA"):
            root = os.environ.get(var)
            if root and (Path(root) / INSTALL_FOLDERS[exe] / exe).is_file():
                return Path(root) / INSTALL_FOLDERS[exe] / exe
    for prog in ON_PATH:
        hit = shutil.which(prog)
        if hit:
            return Path(hit)
    return None


def browser_label(path):
    """A short name for messages: "Edge", "Chrome" or the program's own name."""
    stem = Path(path).stem.lower()
    return {"msedge": "Edge", "chrome": "Chrome"}.get(stem, Path(path).name)


# ---------------------------------------------------------------------------- where it opens

def _size(rect):
    return (rect[2] - rect[0], rect[3] - rect[1])


def _pick_side(others):
    """The side monitor among the displays that are not the primary: one of the side monitor's
    size if there is one, else the first Windows lists."""
    return next((m for m in others if _size(m["bounds"]) in SIDE_SIZES), others[0])


def _scaled_rect(m, prim):
    """The display's rectangle in the browser's scaled units, as far as it can be worked out: the
    primary scaled about the origin, another display placed against the edge of the primary it
    lies beyond, at its own scale [estimate]."""
    l, t, r, b = m["bounds"]
    s = m["scale"] or 1.0
    if prim is None or m is prim:
        return (l / s, t / s, r / s, b / s)
    pl, pt, pr, pb = prim["bounds"]
    ps = prim["scale"] or 1.0
    w, h = (r - l) / s, (b - t) / s
    if l >= pr:
        x0 = pr / ps + (l - pr) / s
    elif r <= pl:
        x0 = pl / ps - (pl - r) / s - w
    else:
        x0 = pl / ps + (l - pl) / ps
    if t >= pb:
        y0 = pb / ps + (t - pb) / s
    elif b <= pt:
        y0 = pt / ps - (pt - b) / s - h
    else:
        y0 = pt / ps + (t - pt) / ps
    return (x0, y0, x0 + w, y0 + h)


def inside_point(m, prim):
    """A point well inside display `m` whether the browser reads it in physical pixels or in its
    scaled units: the middle of the overlap of the two readings when they overlap by more than
    the margin each way, else the middle of the scaled one (Chromium is DPI-aware) [unverified]."""
    phys = m["bounds"]
    dip = _scaled_rect(m, prim)
    l, t = max(phys[0], dip[0]), max(phys[1], dip[1])
    r, b = min(phys[2], dip[2]), min(phys[3], dip[3])
    if r - l > 2 * INSIDE_MARGIN and b - t > 2 * INSIDE_MARGIN:
        return (int((l + r) / 2), int((t + b) / 2))
    return (int((dip[0] + dip[2]) / 2), int((dip[1] + dip[3]) / 2))


def placement(monitors, portrait=False, main=False):
    """Where and how the window opens, from the displays `winutil.monitors()` reports:

    {"where": "side" or "main", "position": (x, y) or None, "size": (w, h) or None (the window,
    frame included), "fullscreen": bool, "page": (w, h) the page should get or None, "capped":
    True when the main display's work area is smaller than the window wanted, "display": the
    display's (w, h) in physical pixels or None, "scale": its scale}.

    A second display is used unless `main` is set; `portrait` then means nothing, because full
    screen takes the display's own shape."""
    prim = next((m for m in monitors if m.get("primary")), monitors[0] if monitors else None)
    others = [m for m in monitors if m is not prim]
    if others and not main:
        m = _pick_side(others)
        return {"where": "side", "position": inside_point(m, prim), "size": None, "fullscreen": True,
                "page": None, "capped": False, "display": _size(m["bounds"]), "scale": m["scale"]}
    want = PORTRAIT if portrait else LANDSCAPE
    win = (want[0] + FRAME[0], want[1] + FRAME[1])
    if prim is None:                                       # nothing known about the display
        return {"where": "main", "position": None, "size": win, "fullscreen": False, "page": want,
                "capped": False, "display": None, "scale": None}
    s = prim["scale"] or 1.0
    l, t, r, b = prim["work"]
    wl, wt, ww, wh = l / s, t / s, (r - l) / s, (b - t) / s
    w, h = min(win[0], int(ww)), min(win[1], int(wh))
    return {"where": "main", "position": (int(wl + (ww - w) / 2), int(wt + (wh - h) / 2)), "size": (w, h),
            "fullscreen": False, "page": (w - FRAME[0], h - FRAME[1]), "capped": (w, h) != win,
            "display": _size(prim["bounds"]), "scale": s}


def command(browser, profile, url, place):
    """The browser's command line (PLAN §11): its own profile, app mode at `url`, the placement,
    and the switches that keep the profile quiet. Never `--kiosk`: it ignores placement and is
    awkward to leave."""
    cmd = [str(browser), "--user-data-dir=%s" % profile, "--app=%s" % url]
    if place.get("position") is not None:
        cmd.append("--window-position=%d,%d" % tuple(place["position"]))
    if place.get("fullscreen"):
        cmd.append("--start-fullscreen")
    elif place.get("size"):
        cmd.append("--window-size=%d,%d" % tuple(place["size"]))
    return cmd + list(QUIET)


def launch(cmd):
    """Start the browser and return at once (the Popen object; never waited on).

    Below normal priority, so the window and every process the browser starts yield to the game
    (a child of a below-normal process starts below normal too, PLAN §6). Out of the caller's job
    and console, so closing the terminal that ran `open` leaves the window alone. No console
    window: a GUI program has none, and `CREATE_NO_WINDOW` keeps a console program (a test's
    stand-in) from showing one. Its working folder is the home folder, not the repo inside the
    game's folder."""
    kw = dict(cwd=str(Path.home()), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
              stderr=subprocess.DEVNULL, close_fds=True)
    if winutil.IS_WINDOWS:
        flags = (subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
                 | subprocess.BELOW_NORMAL_PRIORITY_CLASS)
        try:
            return subprocess.Popen(cmd, creationflags=flags | subprocess.CREATE_BREAKAWAY_FROM_JOB, **kw)
        except OSError:
            return subprocess.Popen(cmd, creationflags=flags, **kw)
    return subprocess.Popen(cmd, start_new_session=True, **kw)


def describe(place, label):
    """One line for the user: where the window went and what the page gets."""
    if place["where"] == "side":
        w, h = place["display"]
        return ("Opened the dashboard window (%s) full screen on the second display (%dx%d), at %d,%d. "
                "F11 leaves full screen, Alt+F4 closes the window." % ((label, w, h) + tuple(place["position"])))
    pw, ph = place["page"]
    where = " at %d,%d" % tuple(place["position"]) if place["position"] else ""
    text = "Opened the dashboard window (%s) on the main screen: a %dx%d window%s, so the page gets about %dx%d." % (
        label, place["size"][0], place["size"][1], where, pw, ph)
    if place["capped"]:
        text += " The screen has no room for more."
    return text
