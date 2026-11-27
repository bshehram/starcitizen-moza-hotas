"""Privacy (PLAN §8, §13): no file that git would publish under dashboard/ holds a personal value
from the local game logs: any player's name (the user's or anyone else's), the Windows user
name, the PC name, the account id, player and character ids, server shard names, session ids or
server addresses.

The values are learned at run time from every log of the newest builds it can read within a
few seconds (newest first), using every context a name was found in (`sanitize.NAME_CONTEXTS`).
They are never printed: a failure names the kind of value and the file, not the value. The test
skips when there is no local game log (a clone on another machine)."""
import os
import re
import subprocess
import time
import unittest
from pathlib import Path

import scdash_testlib as lib
import sanitize
from scdash import config

BUDGET_S = 4.0                     # learning stops after this long; the newest logs come first
NAMES = [re.compile(p.encode("utf-8")) for p in sanitize.NAME_CONTEXTS]
IDS = {
    "windows user": [rb"username (\S+) signedIn"],
    "pc name": [rb"<Hostname> Name: ([^,\r\n]+), Hostname: ([^\s\]]+)"],
    "account id": [rb"accountId (\d+)"],
    "player or character id": [rb"geid (\d+)", rb"playerGEID=(\d+)", rb"PlayerId\[(\d+)\]",
                               rb"playerId\[(\d+)\]", rb"Local client node \[(\d+)\]"],
    "shard": [rb"shard\[([^\]]+)\]"],
    "session id": [rb"session=([0-9a-f]{16,})", rb"@session:\s+'([^']+)'"],
    "server address": [rb"address\[([\d.]+)\]", rb"remoteAddr=([\d.]+):", rb"localAddr=([\d.]+):"],
}
IDS = {k: [re.compile(p) for p in v] for k, v in IDS.items()}
NOT_SECRET = {"0.0.0.0", "127.0.0.1"}


def logs(live):
    d = config.backups_dir(live)
    found = []
    if d.is_dir():
        found = sorted(d.glob("Game Build*.log"), key=lambda p: p.stat().st_mtime, reverse=True)
    gl = config.game_log(live)
    return ([gl] if gl.exists() else []) + found


def identifiers():
    """{kind: set of values}, or None without local logs."""
    live = config.default_live()
    if live is None:
        return None
    found = {"player name": set()}
    found.update({k: set() for k in IDS})
    start, read = time.monotonic(), 0
    for path in logs(live):
        if time.monotonic() - start > BUDGET_S:
            break
        try:
            if path.stat().st_size > 32 * 1024 * 1024:
                continue                        # the old error floods hold nothing new, and slowly
            data = path.read_bytes()
        except OSError:
            continue
        read += 1
        for rx in NAMES:
            for m in rx.finditer(data):
                for g in m.groups():
                    v = (g or b"").decode("utf-8", "replace").strip()
                    if sanitize.is_name(v):
                        found["player name"].add(v)
        for kind, rxs in IDS.items():
            for rx in rxs:
                for m in rx.finditer(data):
                    for g in m.groups():
                        v = (g or b"").decode("utf-8", "replace").strip()
                        if len(v) >= 3 and v not in NOT_SECRET and v.strip("0.") != "":
                            found[kind].add(v)
    if not read:
        return None
    found["windows user"].update(v for v in (os.environ.get("USERNAME"), Path.home().name) if v)
    found["pc name"].update(v for v in (os.environ.get("COMPUTERNAME"),) if v)
    return found


def publishable_files():
    """Tracked files plus untracked ones git does not ignore, under dashboard/."""
    root = lib.DASHBOARD.parent
    try:
        out = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z", "--", "dashboard"],
                             cwd=str(root), capture_output=True, check=True, timeout=60).stdout
        return [root / p for p in out.decode("utf-8").split("\0") if p]
    except (OSError, subprocess.SubprocessError):
        return [p for p in lib.DASHBOARD.rglob("*") if p.is_file()
                and "data" not in p.relative_to(lib.DASHBOARD).parts[:1] and "__pycache__" not in p.parts]


def matcher(kind, values):
    """One pattern per kind: numbers must stand alone, names must be whole words."""
    alts = b"|".join(re.escape(v.encode("utf-8")) for v in sorted(values, key=len, reverse=True))
    if kind in ("account id", "player or character id"):
        return re.compile(rb"(?<!\d)(?:" + alts + rb")(?!\d)")
    return re.compile(rb"(?<![A-Za-z0-9_])(?:" + alts + rb")(?![A-Za-z0-9_])", re.I)


class PrivacyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ids = identifiers()

    def test_no_identifier_in_publishable_files(self):
        if self.ids is None:
            self.skipTest("no local game log to read identifiers from")
        checks = [(kind, matcher(kind, vs)) for kind, vs in self.ids.items() if vs]
        files = publishable_files()
        self.assertTrue(any(p.name == "scdash.py" for p in files), "file list looks wrong")
        hits = []
        for path in files:
            try:
                data = path.read_bytes()
            except OSError:
                continue
            for kind, rx in checks:
                if rx.search(data):
                    hits.append("%s in %s" % (kind, path.relative_to(lib.DASHBOARD.parent).as_posix()))
        self.assertEqual(hits, [], "personal values found (values not shown)")

    def test_identifiers_were_found(self):
        if self.ids is None:
            self.skipTest("no local game log")
        for kind in ("player name", "player or character id", "shard", "session id", "server address"):
            self.assertTrue(self.ids[kind], "could not read any %s: the test would be blind" % kind)
        self.assertGreater(len(self.ids["player name"]), 20, "too few names learned: contexts broken?")


class SanitizerTest(unittest.TestCase):
    def test_every_name_context_is_replaced(self):
        lines = [
            '<2026-11-26T23:11:39.902Z> [Notice] <Legacy login response> [CIG-net] User Login Success - Handle[Zed_Invented] - Time[1]',
            '<2026-11-26T23:13:40.877Z> [Notice] <Actor Position Divergence> [Quill_Invented] [AI 0] diverging 7.6m',
            '<2026-11-26T23:13:40.877Z> [Error] <Trying to QT when not in Idle> Location: X, User: Vex_Invented, Client: Zed_Invented, Current State: 10,',
            '<2026-11-26T23:13:40.877Z> [Notice] <CEntity::OnOwnerRemoved - unblock removal> Moving zone hosted child id = 204741593437 name = Moss_Invented to unblock removal',
        ]
        san = sanitize.Sanitizer()
        san.learn("\n".join(lines))
        out = "\n".join(san.line(x) for x in lines)
        for name in ("Zed_Invented", "Quill_Invented", "Vex_Invented", "Moss_Invented"):
            self.assertNotIn(name, out)
        self.assertEqual(san.leftovers(out), [])


if __name__ == "__main__":
    unittest.main()
