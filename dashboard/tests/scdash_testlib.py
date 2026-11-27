"""Shared helpers for the dashboard tests. Puts dashboard/ on sys.path so `import scdash` finds
the package (see the note in dashboard/scdash.py)."""
import io
import sys
import tempfile
from pathlib import Path

TESTS = Path(__file__).resolve().parent
DASHBOARD = TESTS.parent
SAMPLES = TESTS / "samples"
if str(DASHBOARD) not in sys.path:
    sys.path.insert(0, str(DASHBOARD))

from scdash.names import LocationNames  # noqa: E402

# A small names table of our own, so tests do not depend on reference/locations.json.
NAMES = LocationNames({
    "LOC_RR_S3_L4": {"name": "ARC-L4 Faint Glen Station", "short": "ARC-L4", "kind": "station", "place": "arc-l4"},
    "LOC_RR_S4_L2": {"name": "MIC-L2 Long Forest Station", "short": "MIC-L2", "kind": "station", "place": "mic-l2"},
    "RR_MIC_L2": {"name": "MIC-L2 Long Forest Station", "short": "MIC-L2", "kind": "station", "place": "mic-l2"},
    "Stanton4_NewBabbage": {"name": "New Babbage", "short": "New Babbage", "kind": "landing zone", "place": "new-babbage"},
    "NewBabbage_LOC": {"name": "New Babbage", "short": "New Babbage", "kind": "landing zone", "place": "new-babbage"},
})


def sample_path(name):
    return SAMPLES / name


def sample_bytes(name):
    return (SAMPLES / name).read_bytes()


class TempDir:
    """A temporary folder that is removed afterwards (context manager)."""

    def __enter__(self):
        self._td = tempfile.TemporaryDirectory(prefix="scdash-test-")
        return Path(self._td.name)

    def __exit__(self, *exc):
        self._td.cleanup()


class MemoryLog:
    """A log file held in memory, for driving the follower fast: `opener` is what Follower takes.
    `data` can grow, shrink or be replaced between polls like the real file."""

    def __init__(self, data=b""):
        self.data = bytearray(data)
        self.opens = 0

    def opener(self, path):
        self.opens += 1
        return io.BytesIO(bytes(self.data))


def write(path, data, mode="wb"):
    """Write and close: a reader in this process sees the bytes at once (no fsync needed)."""
    with open(path, mode) as f:
        f.write(data)
