"""Paths and defaults.

The repo sits in the game's own folder, at LIVE\\user\\client\\0\\controls\\mappings, so LIVE is
found from this file's location: four folders above the repo root (the same rule as
tools/gamedata.py). A clone outside a game install (the repo's tools are also used from a Mac)
has no LIVE there; set the environment variable SCDASH_LIVE, or pass --live, to point at one.
"""
import os
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent          # dashboard/scdash
DASHBOARD_DIR = PACKAGE_DIR.parent                     # dashboard
REPO_ROOT = DASHBOARD_DIR.parent                       # the mappings folder
DATA_DIR = DASHBOARD_DIR / "data"                      # git-ignored: the only place private data goes
REFERENCE_DIR = DASHBOARD_DIR / "reference"            # generic game data, committed
LOCATIONS_FILE = REFERENCE_DIR / "locations.json"
SESSIONS_DIR = DATA_DIR / "sessions"                   # session summaries (written from stage 2 on)
UNMAPPED_FILE = DATA_DIR / "unmapped.json"             # location codes with no known name (stage 2)

LIVE_ENV = "SCDASH_LIVE"

# Reading the log (PLAN §8, §9).
POLL_SECONDS = 1.0            # the service polls once a second
READ_PIECE = 1 << 20          # read at most 1 MB at a time, so a flood cannot grow memory
HEAD_BYTES = 4096             # enough to hold the log's first line (about 100 bytes in practice)
MAX_LINE = 64 * 1024          # a longer line is cut to this; the longest seen in 2026-11 was 1,181 bytes

# State sizes (bounded everything, PLAN §8).
FEED_LEN = 50
MAX_CONTRACTS = 30
MAX_OBJECTIVES = 20
MAX_PLACES = 100
MAX_TRADES = 200
MAX_LIST = 100                # refinery notices, blueprints, screenshots, deaths, jumps

# Preflight (root CLAUDE.md §1): the AB6 base must be joystick 1 and the MTQ joystick 2.
# The game numbers them from 0 in `Connected joystick<n>`, so joystick0 is the game's js1.
# Matched on the device name or on the first part of its GUID (USB VID/PID), either is enough.
EXPECTED_JOYSTICKS = (
    {"label": "AB6", "name": "MOZA AB6 FFB Base", "guid_prefix": "1002346E"},
    {"label": "MTQ", "name": "MOZA MTQ Throttle Panel", "guid_prefix": "1101346E"},
)

PORT = 47826                  # the live service (PLAN §15)
REPLAY_PORT = 47827           # `replay`, so it never meets the live instance

# ---------------------------------------------------------------------------- the service
# Local settings live in data/config.json (git-ignored); dashboard/config.example.json documents
# every key. A key missing from the file takes its default here; a key with the wrong type is
# ignored with a note in the service log. Keys starting with "_" are comments.

CONFIG_NAME = "config.json"
EXAMPLE_CONFIG = DASHBOARD_DIR / "config.example.json"
WEB_DIR = DASHBOARD_DIR / "web"

DEFAULTS = {
    "port": PORT,                       # 127.0.0.1:<port>
    "live": None,                       # the game's LIVE folder; None: found from the repo's place
    "game_process": "StarCitizen.exe",  # the program whose presence means "the game is running"
    "poll_seconds": POLL_SECONDS,       # log poll while the game runs
    "process_check_seconds": 10.0,      # how often to look for the game process
    "state_save_seconds": 10.0,         # data/state.json at most this often, and only on change
    "push_min_seconds": 0.5,            # at most two state sends a second to each page
    "keepalive_seconds": 15.0,          # a comment line on each event stream this often
    "retry_ms": 3000,                   # how soon a page reconnects after losing the stream
    "max_pages": 4,                     # event streams at once (a browser allows 6 connections)
    "log_max_bytes": 1_000_000,         # data/service.log, rotated at this size
    "log_backups": 1,                   # rotated copies kept (service.log.1)
    "sessions_keep": 500,               # session summaries kept in data/sessions/
    "terminal": {"enabled": False},     # the Claude terminal panel (stage 4b); in stage 2 a placeholder
}

# Every number's allowed range, both ends included. A value outside it is a mistake in the file:
# it takes the default, with a note in the log. (A tiny poll would spin the loop; a zero log size
# or zero backups would stop the log from ever rotating.)
BOUNDS = {
    "port": (1024, 65535),
    "poll_seconds": (0.25, 10.0),
    "process_check_seconds": (2.0, 300.0),
    "state_save_seconds": (2.0, 3600.0),
    "push_min_seconds": (0.1, 10.0),
    "keepalive_seconds": (2.0, 120.0),
    "retry_ms": (500, 60000),
    "max_pages": (1, 5),
    "log_max_bytes": (50_000, 50_000_000),
    "log_backups": (1, 10),
    "sessions_keep": (10, 100_000),
}

# Not settings: internal bounds.
MAX_BODY = 64 * 1024                 # largest request body the server reads
MAX_CONNECTIONS = 16                 # requests being served at once, event streams included
REQUEST_TIMEOUT = 5.0                # seconds a request's head (and body) may take to arrive, in all
READ_BUDGET = 16 << 20               # bytes read per loop turn while catching up on a big log
MAX_UNMAPPED = 2000                  # codes kept in data/unmapped.json


def load_settings(data_dir, overrides=None):
    """The settings: defaults, then data_dir/config.json, then `overrides` (command-line flags).
    Returns (settings, notes): `notes` are plain-words problems with the file, for the log."""
    import json
    s = {k: (dict(v) if isinstance(v, dict) else v) for k, v in DEFAULTS.items()}
    notes = []
    path = Path(data_dir) / CONFIG_NAME
    raw = None
    if path.exists():
        try:
            with open(path, encoding="utf-8") as f:
                raw = json.load(f)
        except (OSError, ValueError) as e:
            notes.append("%s could not be read (%s); using the defaults" % (CONFIG_NAME, e.__class__.__name__))
        if raw is not None and not isinstance(raw, dict):
            notes.append("%s is not a JSON object; using the defaults" % CONFIG_NAME)
            raw = None
    for k, v in (raw or {}).items():
        if k.startswith("_"):
            continue
        if k not in DEFAULTS:
            notes.append("unknown setting %r ignored" % k)
            continue
        ok, val = _check(k, DEFAULTS[k], v)
        if ok:
            s[k] = val
        else:
            notes.append("setting %r has the wrong type or is out of range; using %r" % (k, DEFAULTS[k]))
    for k, v in (overrides or {}).items():
        if v is None:
            continue
        if k in BOUNDS and not _check(k, DEFAULTS[k], v)[0]:
            notes.append("%s %r is out of range; using %r" % (k, v, s[k]))
            continue
        s[k] = v
    return s, notes


def _check(key, default, value):
    if isinstance(default, dict):
        if not isinstance(value, dict):
            return False, None
        out = dict(default)
        for k, v in value.items():
            if k.startswith("_"):
                continue
            if k in default:
                ok, val = _check(key + "." + k, default[k], v)
                if not ok:
                    return False, None
                out[k] = val
        return True, out
    if default is None:                              # a path: a string or null
        return (value is None or isinstance(value, str)), value
    if isinstance(default, bool):
        return isinstance(value, bool), value
    if isinstance(default, int):
        if isinstance(value, bool) or not isinstance(value, int):
            return False, None
        lo, hi = BOUNDS.get(key, (0, 2 ** 31))
        return (lo <= value <= hi), value
    if isinstance(default, float):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return False, None
        lo, hi = BOUNDS.get(key, (1e-9, 1e9))
        value = float(value)
        return (lo <= value <= hi), value
    if isinstance(default, str):
        return isinstance(value, str) and bool(value), value
    return False, None


def default_live():
    """LIVE from the environment, else from the repo's place in the game install, else None."""
    env = os.environ.get(LIVE_ENV)
    if env:
        return Path(env)
    parents = REPO_ROOT.parents
    if len(parents) > 4:
        live = parents[4]
        if (live / "Game.log").exists() or (live / "logbackups").is_dir():
            return live
    return None


def game_log(live):
    return Path(live) / "Game.log"


def backups_dir(live):
    return Path(live) / "logbackups"
