"""Make test samples from real log lines, with every personal value replaced by an invented one.

    python dashboard/tests/sanitize.py <log> --lines 1-30,3473-3480 [--grep REGEX] [--after N] > sample.log

A log line can carry the user's handle, the Windows user name, the PC's name, the account id,
the character and player ids, session ids, server addresses and other players' names (PLAN §8).
This replaces all of them, and every other id too:

- player names (the user's and anyone else's, learned from the whole log) -> Pilot_Example,
  OtherPilot_1, ...;
- the Windows user name and the PC name -> exampleuser, EXAMPLE-PC;
- the account id -> 1000001;
- every GUID -> an invented one, the same one each time (except the all-zero GUID and the
  joystick product GUIDs, which are public: root CLAUDE.md §1);
- every number of 9 digits or more (entity, player, shop, location ids) -> an invented one, the
  same one each time, so the lines still refer to each other;
- long hex strings (session ids) -> invented ones;
- IPv4 addresses -> 192.0.2.x (the documentation range); server shard names -> invented.

It then checks its own output for every value it learned and refuses to print if one is left.
Read the result yourself before committing it: a new kind of line can carry a new kind of value.
Standard library only; run it from the project root.
"""
import argparse
import itertools
import re
import sys

ZERO_GUID = "00000000-0000-0000-0000-000000000000"
GUID_RE = re.compile(r"(?<![0-9A-Fa-f])[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}(?![0-9A-Fa-f])")
PUBLIC_GUID_TAIL = "-0000-0000-0000-504944564944"          # DirectInput product GUIDs
LONGNUM_RE = re.compile(r"(?<![0-9A-Za-z.\-])(?!0+(?![0-9]))\d{9,}(?![0-9A-Za-z\-])")
HEX_RE = re.compile(r"\b[0-9a-f]{16,}\b")
IP_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
SHARD_RE = re.compile(r"\bpub_[a-z0-9]+_\d+_\d+\b")

# Every context a player name was found in, in the 69 logs of 2026-11 [seen 2026-11-27: the
# user's handle in all its contexts, then other players' names in the same ones]. Each starts
# with fixed text, so a scan over a whole log is fast. tests/test_privacy.py uses this list too.
NAME_CONTEXTS = [
    r"Handle\[([^\]]+)\]",
    r"killer '([^']+)'",
    r"Actor '([^']+)'",
    r"Player\[([^\]\s,]+)\]",
    r"Player \[([^\]\s]+)\]",
    r"player \[([^\]\s]+)\]",
    r"Player '([^']+)' \[",
    r"player '([^']+)' ",
    r"Player: ([^\s\[,]+)[ \[]",
    r"Player ([^\s\[]+)\[\d",
    r" for '([^']+)' ?\[",
    r" by '([^']+)' \[",
    r"\] '([^']+)' \[\d+\] (?:placing|placed)",
    r"on entity '([^']+)'\. Can",
    r"nickname=\"([^\"]+)\"",
    r" - name (\S+) - state",
    r"LandingArea: (\S+)'s",
    r"User\[([^,\]]+),",
    r"User: ([^,\s]+), Client: ([^,\s]+),",
    r"channel '[^']* : ([^']+)'",
    r" for (\S+) \[\d+\] to track",
    r"Player - ([^\[\s]+)\[",
    r"CommunicationFinished\[([^\]]+)\]",
    r"For Client: (\S+)",
    r"\[CEALobby::\w+\] (\S+) (?:Requesting|Changing)",
    r"<Actor Position Divergence> \[([^\]]+)\]",
    r"child id = \d+ name = (\S+) to unblock",
    r"localClient \[([^\]]+)\]",
]
NAME_PATTERNS = [re.compile(p) for p in NAME_CONTEXTS]
USER_RE = re.compile(r"username (\S+) signedIn")
HOST_RE = re.compile(r"<Hostname> Name: ([^,]+), Hostname: (\S+)")
ACCOUNT_RE = re.compile(r"accountId (\d+)")
NOT_NAMES = {"invalid", "null", "0", "", "player", "vehicle", "location", "unknown", "none"}
ENTITY_RE = re.compile(r"_\d{6,}$")     # an entity ('AEGS_Avenger_Titan_944...'), not a player


def is_name(value):
    """Could this captured text be a player's name? Handles have no spaces, and entity names end
    in their long id."""
    v = value.strip()
    return (len(v) >= 3 and v.lower() not in NOT_NAMES and not v.isdigit()
            and not re.search(r"\s", v) and not ENTITY_RE.search(v)
            and not v.startswith("Team_"))     # "local player [Team_GameServices][Haptic]"


class Sanitizer:
    def __init__(self):
        self.handle = None
        self.names = {}          # real name -> invented
        self.users = set()
        self.hosts = set()
        self.accounts = set()
        self._guids = {}
        self._nums = {}
        self._hex = {}
        self._ips = {}
        self._shards = {}
        self._other = itertools.count(1)

    def learn(self, text):
        """Learn the personal values from a whole log (or several)."""
        m = re.search(r"User Login Success - Handle\[([^\]]+)\]", text)
        if m:
            self.handle = m.group(1)
            self.names.setdefault(m.group(1), "Pilot_Example")
        for rx in NAME_PATTERNS:
            for m in rx.finditer(text):
                for g in m.groups():
                    name = (g or "").strip()
                    if is_name(name) and name not in self.names:
                        self.names[name] = "OtherPilot_%d" % next(self._other)
        self.users.update(USER_RE.findall(text))
        for a, b in HOST_RE.findall(text):
            self.hosts.update({a.strip(), b.strip()})
        self.accounts.update(ACCOUNT_RE.findall(text))

    def _map(self, table, key, make):
        if key not in table:
            table[key] = make(len(table) + 1)
        return table[key]

    def line(self, s):
        for name in sorted(self.names, key=len, reverse=True):
            s = re.sub(r"(?<![A-Za-z0-9_])%s(?![A-Za-z0-9_])" % re.escape(name), self.names[name], s)
        for u in self.users:
            s = re.sub(r"(?<![A-Za-z0-9_])%s(?![A-Za-z0-9_])" % re.escape(u), "exampleuser", s)
        for h in self.hosts:
            s = re.sub(r"(?<![A-Za-z0-9_])%s(?![A-Za-z0-9_])" % re.escape(h), "EXAMPLE-PC", s)
        for a in self.accounts:
            s = re.sub(r"(?<!\d)%s(?!\d)" % re.escape(a), "1000001", s)

        def guid(m):
            g = m.group(0)
            if g == ZERO_GUID or g.upper().endswith(PUBLIC_GUID_TAIL):
                return g
            return self._map(self._guids, g.lower(), lambda k: "%08x-0000-4000-8000-%012x" % (0xe0000000 + k, k))
        s = GUID_RE.sub(guid, s)
        s = SHARD_RE.sub(lambda m: self._map(self._shards, m.group(0), lambda k: "pub_example_00000000_%03d" % k), s)
        s = IP_RE.sub(lambda m: self._map(self._ips, m.group(0), lambda k: "192.0.2.%d" % k), s)
        s = HEX_RE.sub(lambda m: self._map(self._hex, m.group(0), lambda k: "%032x" % (0xabc000 + k)), s)
        s = LONGNUM_RE.sub(lambda m: self._map(self._nums, m.group(0), lambda k: str(900000000000 + k)), s)
        return s

    def leftovers(self, text):
        """Learned personal values still present in `text` (should be none)."""
        left = []
        for v in list(self.names) + list(self.users) + list(self.hosts):
            if re.search(r"(?<![A-Za-z0-9_])%s(?![A-Za-z0-9_])" % re.escape(v), text):
                left.append(v)
        for a in self.accounts:
            if re.search(r"(?<!\d)%s(?!\d)" % re.escape(a), text):
                left.append(a)
        for n in self._nums:
            if n in text:
                left.append(n)
        return left


def parse_ranges(spec):
    out = []
    for part in (spec or "").split(","):
        if part.strip():
            a, _, b = part.partition("-")
            out.append((int(a), int(b or a)))
    return out


def select(lines, ranges, greps, after):
    keep = set()
    for a, b in ranges:
        keep.update(range(a - 1, min(b, len(lines))))
    for rx in greps:
        for i, l in enumerate(lines):
            if rx.search(l):
                keep.update(range(i, min(i + 1 + after, len(lines))))
    return [lines[i] for i in sorted(keep)]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("log")
    ap.add_argument("--lines", help="1-based line ranges, e.g. 1-30,3473-3480")
    ap.add_argument("--grep", action="append", default=[], help="keep lines matching this regex")
    ap.add_argument("--after", type=int, default=0, help="with --grep: also keep N lines after each match")
    ap.add_argument("--learn", action="append", default=[], help="more logs to learn names from")
    args = ap.parse_args(argv)
    raw = open(args.log, "rb").read().decode("utf-8", "replace")
    san = Sanitizer()
    san.learn(raw)
    for extra in args.learn:
        san.learn(open(extra, "rb").read().decode("utf-8", "replace"))
    lines = raw.split("\n")
    picked = select(lines, parse_ranges(args.lines), [re.compile(g) for g in args.grep], args.after)
    out = "\n".join(san.line(l) for l in picked)
    left = san.leftovers(out)
    if left:
        sys.exit("refusing: %d learned personal value(s) still present; extend the sanitizer" % len(left))
    sys.stdout.buffer.write(out.encode("utf-8"))
    if picked and not out.endswith("\n"):
        sys.stdout.buffer.write(b"\n")


if __name__ == "__main__":
    main()
