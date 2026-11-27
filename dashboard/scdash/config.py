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

PORT = 47826                  # stage 2


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
