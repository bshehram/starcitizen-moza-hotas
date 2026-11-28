"""Events to state, as a pure function.

Copyright (c) 2026 archelium (support@archelium.com) for the parts marked "From CSR" below,
used under the MIT License (see dashboard/THIRD_PARTY_NOTICES). Everything else in this file is
this project's own.

The state is a fold over the events of one log: `build_state(events, names)`, or `State.apply`
one event at a time. It never looks at the wall clock and never asks where an event came from
(the log today, the telemetry stream in stage 6). Anything that needs "now" (how long a queue has
waited, how long the session has run) is a function that takes the time as an argument:
`clock_facts(state, now)`. The same events give the same state, whether they were read in one
pass, in pieces, or again after a restart.

Started from CSR's `LogState` (sc_livelog.py, commit ba6dad0, lines 128-434) as PLAN §5 says:
contracts by mission id, objectives by objective id, the quantum target with its route and fuel,
and a capped place history. Changed on the way in: it takes events, not lines; it has no
fall-back to the wall clock (CSR used time.time() for untimed lines, which breaks PLAN §7); it
keeps one contract per mission id (the game announces a contract again after a relog, seen in
7 logs of 2026-11); and it adds the session, ships, hangar queue, refinery, trade, deaths and the
joystick preflight check.

`apply()` is for log events only. It returns the feed lines the event produced or changed (dicts
with plain words; an empty list for events not worth a line); the state keeps the last 50. Each
line has an `id` unique within the session and stable across rereads (the event's offset and a
small index), and a `rev` that grows when the line's text is changed later (a jump's route and
fuel arrive a millisecond after the target). The timeline collects them all.

Other players' names: the state keeps those it sees (killers, ship channel owners, actors, and in
stage 3 the players the law notices name) in a private set, and `to_dict()` and
`build_summary()` replace any of them found in a text with "another player", whatever text it
is (a contract title, an objective).

Stage 3 added (dashboard/SURVEY.md): failed and withdrawn contracts and objectives, the law
notices and pay; pickups and drop-offs read from objective texts; the session's tally of ships
destroyed, crippled and lost, counted once per vehicle at its highest level; a death taken from
the body item; and, from the reference tables (refdata.py), each contract's kind, view, setting
and giver, the ship's job and cargo grid, and each shop's kind and place. What the page needs
beyond the state (the view, its model, alerts, timers) is board.build(); the state's own
`plan`, `timers`, `alerts` and `view` slots stay empty.
"""
import re
from array import array
from bisect import bisect_left, bisect_right
from collections import deque

from . import config
from . import law
from . import refdata
from .names import LocationNames
from .words import clean_all, clean_text, compatible, duration, fit, iso, money, scu, ship_class

ALERT, MAJOR, MINOR = "alert", "major", "minor"

# How an <EndMission> CompletionType reads [seen: Complete 13 and Abandon 7 of 20 in 2026-11].
# `Fail` and `Deactivate` come from other tools [ref: SURVEY.md §1, unverified here]; a
# withdrawn contract is "Deactivate" in the line and "Withdrawn" in its notice. Any other type is
# kept as its own lower-case word.
END_STATUS = {"complete": "complete", "abandon": "abandoned", "fail": "failed", "failed": "failed",
              "deactivate": "withdrawn", "withdrawn": "withdrawn"}
ENDED = {"complete", "abandoned", "failed", "withdrawn"}

# Objective texts that name a stop (SURVEY.md §2). Courier pickups and drop-offs are seen in the
# user's logs (samples/courier.log); the hauling manifest is in the game's text and other tools'
# parsers only [ref], so a stop read from it is marked unverified.
COLLECT_RE = re.compile(r"^(?:Collect|Pick ?up|Retrieve)\s+(.+?)\s+[Ff]rom\s+(.+)$")
DELIVER_RE = re.compile(r"^Deliver\s+(.+?)\s+[Tt]o\s+(.+)$")
HAUL_RE = re.compile(r"^Deliver\s+(\d{1,7})\s*/\s*(\d{1,7})\s+(SCU|Cargo Box(?:es)?|Boxes|Box)"
                     r"(?:\s+of\s+(.+?))?\s+to\s+(.+)$", re.I)
OBJECTIVE_ID_RE = re.compile(r"^(pickup|dropoff)_[0-9A-Fa-f]{8}-[0-9A-Fa-f-]{27}_(\d{1,3})")
QUANTITY_RE = re.compile(r"^\s*([\d.]{1,20})\s*([A-Za-z]*)\s*$")

# The tally's vehicle levels [ref: CSR: level 1 is crippled (a soft death), 2 destroyed].
CRIPPLED, DESTROYED = 1, 2
TALLY_KEEP = 100                                     # vehicles remembered for the tally
BURST_GAP = 2.0                                      # seconds between items of one recovery burst

GAME_STATES = ("not_running", "menu", "in_game", "ended")

# Things a downed or dead player cannot do. While downed or dead, one of these means the user is
# up again without a respawn [seen 2026-11, 36 "Incapacitated" notices: 26 followed by a respawn,
# 8 by one of these with no respawn, 2 by leaving the server; one item-loss burst was followed by
# a quantum target two minutes later and no respawn, so those items were not the user's (CSR
# warned of bursts for a body nearby). The emergency-services notice preceded a respawn 23 times
# of 23.]
ACTIVE_KINDS = {"quantum_target", "seat_left", "channel_joined", "ship_retrieved", "shop_buy",
                "shop_sell", "hangar_queue", "commodity_sell", "commodity_buy", "rental",
                "refinery_sell"}

# Names that are not anyone's, when a killer or an actor is logged [my reasoning]; "you" is the
# word the law notices put where the user is ("... against you").
NOT_A_NAME = {"", "unknown", "none", "null", "invalid", "you", "another", "player"}   # never "another another player"
OTHER_PLAYER = "another player"
YOU = "you"                                         # the user's own handle, in public output
MAX_OTHERS = 1000          # other players' names remembered at once (a real session meets dozens)
MAX_NAME = 100             # a capture longer than this is not a handle
NOT_REDACTED = {"names", "ref", "me", "_others", "_others_re", "_forgotten_rx", "_forgot_order",
                "_forgot_sorted", "_kept_lower", "forget_hook", "_forgot_counts", "_kept_counts"}
# Forgotten names still hidden in output, as 8-byte hashes (Python's own string hash: the table
# lives in this process only): 50,000 cost 0.8 MB with the sorted copy. Past that the oldest go.
MAX_FORGOTTEN = 50000
# Lookups per "-" part of a run in _hide_forgotten: a part makes at most one per number of parts
# the names held have, so no run is cut short while they have at most 8 different numbers of
# parts (real handles have 1 to 3; round 4 of the stage 3 review: at 4, names of 1 to 5 parts made
# a nameless run of 80 parts be hidden from part 77).
HIDE_BUDGET = 8
# A run of a text that may hold a handle: the characters law.HANDLE_RE accepts, so a name learned
# with a leading, trailing or doubled "-" is found again once forgotten (stage 3 review, round 3:
# the old run, word parts joined by single hyphens, could not match those).
_RUN_RE = re.compile("[%s]+" % law.HANDLE_CHARS)
_PUNCT = ".,;:!?()[]{}\"'"


def _fold(ch):
    """A character as the names pattern keys it: one character that re.I takes as equal to it, the
    same for all the characters re.I takes as equal. Lower case of upper case where both stay one
    character, so long s, dotless i, the final sigma and the Kelvin sign key as "s", "i", "σ" and
    "k" (stage 3 review, round 4: kept "bos" cut "boſ-x" to "another player-x"); else lower case
    (ß); else the first character of it (U+0130 to "i", which re.I matches too). So two names
    that differ only in case share one branch, and the longer is still tried first: with a branch
    per case, a kept "Bob_Q" matched inside a kept "bob_q-Smith" and left "another player-Smith"
    (stage 3 review, round 3)."""
    up = ch.upper()
    if len(up) == 1:
        low = up.lower()
        if len(low) == 1:
            return low
    low = ch.lower()
    return low if len(low) == 1 else low[:1]


def _key(name):
    """A name as the names pattern keys it (_fold, character by character)."""
    return name.lower() if name.isascii() else "".join(map(_fold, name))


def _parts(name):
    """How many "-" parts a name has ('Bob_Q-Smith' 2, '-Lead' 2, 'Dbl--Hy' 3)."""
    return name.count("-") + 1


class _Redactor:
    """A pattern with its own replacement, where `redact` expects a pattern."""

    def __init__(self, rx, fn):
        self.rx, self.fn = rx, fn

    def sub(self, _repl, text):
        return self.rx.sub(self.fn, text)


def name_regex(names):
    """One pattern for many names, as a trie (so a thousand names cost the length of the longest
    at each place, not a thousand tries), whole words only, without regard to case. None for no
    names."""
    trie = {}
    for name in names:
        node = trie
        # One branch for every case of a character (_fold); re.I matches each of them.
        for ch in _key(name):
            node = node.setdefault(ch, {})
        node[""] = {}

    def build(node):
        alts = [re.escape(ch) + build(sub) for ch, sub in sorted(node.items()) if ch]
        if not alts:
            return ""
        body = alts[0] if len(alts) == 1 and "" not in node else "(?:%s)" % "|".join(alts)
        return body + "?" if "" in node and alts else body
    if not trie:
        return None
    return re.compile(r"(?<![A-Za-z0-9_])%s(?![A-Za-z0-9_])" % build(trie), re.I)


def redact(rx, x):
    """Replace the names `rx` matches with "another player" in every text inside `x`, changing
    the containers in place (dict values, list and deque items, set members); a text or tuple
    comes back new."""
    if isinstance(x, str):
        return rx.sub(OTHER_PLAYER, x)
    if isinstance(x, dict):
        for k, v in list(x.items()):
            nv = redact(rx, v)
            if nv is not v:
                x[k] = nv
        return x
    if isinstance(x, (list, deque)):
        for i, v in enumerate(x):
            nv = redact(rx, v)
            if nv is not v:
                x[i] = nv
        return x
    if isinstance(x, tuple):
        return tuple(redact(rx, v) for v in x)
    if isinstance(x, set):
        new = {redact(rx, v) for v in x}
        x.clear()
        x.update(new)
        return x
    return x


class State:
    """The dashboard's state for one log. Feed it events in file order with `apply`.

    `ref` is the reference tables (refdata.RefData); the process's shared one by default. They
    give contracts their kind and view, ships their job and cargo grid, shops their kind and
    place, and commodities their names: generic game data, the same on every reread."""

    def __init__(self, names=None, ref=None):
        self.names = names if names is not None else LocationNames()
        self.ref = ref if ref is not None else refdata.shared()
        # Called with the names of each forgetting pass, after the state's own texts lost them
        # (the reader holds every feed line for `timeline` and takes them out of those too).
        self.forget_hook = None
        self.reset()

    # ------------------------------------------------------------------ life cycle

    def reset(self, session=None):
        self.session = {"id": session, "start": None, "local": None, "build": None,
                        "version": None, "game": "not_running", "world": None,
                        "ended": None, "last_t": None, "events": 0, "spawns": 0,
                        "in_game_since": None, "in_game_s": 0.0, "unreadable": 0, "withheld": 0,
                        "withheld_tips": 0}
        self._others = {}                                     # other players' names: never shown;
        self._others_re = None                                # a dict as an ordered set, oldest first
        self._forgotten_rx = None
        self.forgotten = 0                                    # how many times names were forgotten
        self._forgot_order = array("q")                       # hashes of forgotten names, oldest first
        self._forgot_sorted = array("q")                      # the same, sorted for lookups
        self._forgot_counts = set()                           # "-" parts counts of forgotten names
        self._kept_lower = None                               # the names known, lower case (scrub)
        self._kept_counts = ()                                # the same of the names known
        self._pending_world = None
        self.me = {"handle": None, "player_id": None}         # memory only (PLAN §8)
        self.server = {"shard": None, "joined": None, "shards": []}
        self.joysticks = []
        self.preflight = {"ok": None, "text": "no joysticks logged yet", "order": None, "missing": []}
        self._joy_final = False
        self.profile = None
        self.location = None
        self.places = []
        self.body = None
        self.near = None
        self.zone = {"jurisdiction": None, "armistice": None, "monitored": None, "monitored_down": None,
                     "t": None}
        self.ship = None
        self.vehicles = {}
        self.quantum = None
        self.jumps = []
        self.contracts = {}                                   # mission id -> contract, in order
        self.hangar = {"queue": None, "ready": None, "waits": []}
        self.refinery = []
        self.trade = []
        self.blueprints = []
        self.health = {"status": "ok", "t": None, "injuries": []}
        self._incident = None
        self.deaths = []
        self.recoveries = []
        self._extra_lines = []                      # feed lines not tied to the event's own kind
        self.ships_lost = []
        self.screenshots = []
        self.storage = None
        self.left_server = []
        self.notable = []
        self.fabricator = []
        self.feed = deque(maxlen=config.FEED_LEN)
        self.codes = set()
        self._loc_ids = {}                                    # landing id -> location code
        self._landing = None
        self._last_disconnect = None
        self._storage_seen = {}
        # Stage 3: the session's tally, its run-ins with the law, pay, where the ship was left.
        self.tally = {"destroyed": 0, "crippled": 0, "lost": 0, "downed": 0}
        self._tally = {}                                      # vehicle id -> its highest level
        self.law = []
        self.rewards = []
        self.ship_left = None
        self._burst = None                                    # the item-recovery burst being read
        self._last_inv = None                                 # the last inventory location code
        # Stage 3 fills these from the plan data; kept here so the shape does not change.
        self.plan = None
        self.timers = []
        self.alerts = []
        self.view = None

    def apply(self, ev):
        """Apply one log event. Returns the feed lines it produced or changed (a list).

        For log events only: a second source (the telemetry stream, stage 6) gets an entry point
        of its own, so that it cannot move the session's last-event time or event count."""
        if ev.kind == "unreadable":                  # counted, and nothing else changes
            self.session["unreadable"] += 1
            return []
        if ev.kind == "session_start":
            self.reset(ev.session)
        elif ev.session != self.session["id"] and self.session["id"] is not None and ev.session:
            # A log that does not begin with its first line (a fragment): adopt its session.
            self.reset(ev.session)
        if self.session["id"] is None:
            self.session["id"] = ev.session
        self.session["last_t"] = ev.t
        self.session["events"] += 1
        if ev.kind != "joystick" and self.joysticks and not self._joy_final:
            self._joy_final = True
            self._check_joysticks()
        self._extra_lines = lines = []
        if self._incident is not None and ev.kind in ACTIVE_KINDS and ev.t - self._incident["t"] > 5:
            self._recovered(ev)
        handler = getattr(self, "_on_" + ev.kind, None)
        out = handler(ev) if handler else None
        if out is not None:
            level, text = out
            line = self._line(ev, ev.kind, level, text)
            lines.append(line)
            if ev.kind == "quantum_target" and self.quantum and self.quantum["offset"] == ev.offset:
                self.quantum["_line"] = line          # the route and fuel fill it in later
        k = 0
        for line in lines:                            # ids: the offset and the order within it
            if "id" not in line:
                line["id"] = "%d.%d" % (ev.offset, k)
                k += 1
        return lines

    def _line(self, ev, kind, level, text):
        line = {"t": ev.t, "session": ev.session, "offset": ev.offset, "kind": kind,
                "level": level, "text": text, "rev": 0}
        self.feed.append(line)
        return line

    # ------------------------------------------------------------------ helpers

    def _place(self, code):
        return self.names.name(code) if code else "somewhere unknown"

    def _mine(self, name):
        """Is this name the user's? Before the login line (a log fragment) any name counts."""
        h = self.me["handle"]
        n = clean_text(name or "").strip()
        mine = h is None or n.lower() == h.lower()
        if not mine:
            self._other(n)
        return mine

    def _other(self, name):
        """Remember another player's name, privately, so no text of ours ever shows it.

        The name is kept as the scrubber will meet it: cleaned the way every text is cleaned
        before it is scrubbed (a name with U+202E inside matched no cleaned text, and leaked:
        stage 3 review). The set is bounded (MAX_OTHERS) and fails closed: see `_forget`."""
        name = clean_text(name or "").strip()
        if not name or name.lower() in NOT_A_NAME or not 3 <= len(name) <= MAX_NAME:
            return
        h = self.me["handle"]
        if h is not None and name.lower() == h.lower():
            return
        if name in self._others:
            del self._others[name]                 # seen again: the newest, last to be forgotten
            self._others[name] = None
            return
        self._others[name] = None
        self._others_re = None
        if len(self._others) > MAX_OTHERS:
            self._forget(list(self._others)[:MAX_OTHERS // 2])

    def _forget(self, names):
        """Forget the oldest names, and first take each of them out of every text the state
        holds, so a forgotten name can never show up again in anything kept from before. The walk
        goes over all of the state's own containers (not a list of them), so one added later is
        covered too. Names are forgotten half the set at a time, so a flood of names costs one
        walk per MAX_OTHERS // 2 of them. A forgotten name met again is learned again.

        The walk's pattern holds the names kept and the user's handle too, and leaves those as
        they are: a pattern of the forgotten names alone matched "Bob" inside a kept "Bob-Smith"
        and left "another player-Smith" (stage 3 review, round 2). Matching longest first, a
        handle is always replaced whole or not at all. The forgotten names stay hidden in
        output as hashes (`_hide_forgotten`)."""
        gone = set(names)
        h = self.me["handle"]
        keep = {_key(n) for n in self._others if n not in gone} | ({_key(h)} if h else set())
        rx = name_regex(list(self._others) + ([h] if h else []))
        if rx is not None:
            def swap(m, keep=keep):
                return m.group(0) if _key(m.group(0)) in keep else OTHER_PLAYER
            fn = _Redactor(rx, swap)
            for key, value in self.__dict__.items():
                if key not in NOT_REDACTED:
                    redact(fn, value)
            self._forgotten_rx = fn
            self.forgotten += 1
        for n in names:
            self._others.pop(n, None)
        self._others_re = None
        order = self._forgot_order
        order.extend(hash(n.lower()) for n in names)
        if len(order) > MAX_FORGOTTEN:
            del order[:len(order) - MAX_FORGOTTEN]
        self._forgot_sorted = array("q", sorted(order))
        self._forgot_counts.update(_parts(n) for n in names)  # at most MAX_NAME + 1 values
        if self.forget_hook is not None:
            self.forget_hook(list(names))

    def redact_held(self, obj):
        """Take the names forgotten last out of a container held outside the state (the reader's
        lines waiting for `take_lines`). The reader calls it when `forgotten` changes."""
        if self._forgotten_rx is not None:
            redact(self._forgotten_rx, obj)

    def redact_names(self, obj, names):
        """Replace `names` (forgotten ones, collected by `forget_hook`) with "another player" in
        every text inside `obj`, in place, with one pattern that also holds the names known now
        and leaves those whole for the scrubber, as `_forget` does. The reader uses it on its list
        of every feed line once, when the list is read, instead of at every forgetting pass: a
        walk per pass made `timeline` quadratic in the number of names (stage 3 review, round 3:
        20,000 names took 2.1 s)."""
        if not names:
            return obj
        h = self.me["handle"]
        keep = {_key(n) for n in self._others} | ({_key(h)} if h else set())
        rx = name_regex(list(names) + list(self._others) + ([h] if h else []))

        def swap(m, keep=keep):
            return m.group(0) if _key(m.group(0)) in keep else OTHER_PLAYER
        return redact(_Redactor(rx, swap), obj)

    def _hide_forgotten(self, text, kept, counts):
        """A forgotten name met later in a text that teaches nothing (a contract title naming a
        player forgotten long ago) is still hidden: every run of handle characters in the text is
        looked up among the hashes of the names forgotten, longest first across its "-" parts. A
        span that is a name still known (`kept`, lower case) is left whole for the scrubber, so
        neither pass can cut a handle in two. Only after a flood of names (MAX_OTHERS): a normal
        session pays nothing.

        Bounded (stage 3 review, round 3: every span of every run was joined and looked up, so a
        2,000-character "a-a-a-..." took 1.8 s): from each part, a span is tried only with a number
        of parts that some name forgotten or known has (`counts`, ascending; most often 1 and 2)
        and only when it is 3 to MAX_NAME characters long, and it is a slice of the run, not a
        join. A run of n parts may make at most HIDE_BUDGET * n + 64 lookups; past that the rest of
        the run is replaced whole (fail closed: hidden, never cut). A part makes at most one
        lookup per number in `counts`, so a run is cut short only when the names held (forgotten
        or known) have more than HIDE_BUDGET (8) different numbers of parts, which takes names of
        9 parts or more (stage 3 review, round 4: the old budget of 4 hid nameless runs of 40
        parts once names of 1 to 6 parts were held)."""
        table = self._forgot_sorted
        size = len(table)
        top = counts[-1] if counts else 0

        def gone(low):
            k = hash(low)
            i = bisect_left(table, k)
            return i < size and table[i] == k

        def run(m):
            s = m.group(0)
            if len(s) < 3:
                return s
            low = s.lower()                       # ASCII only: the same length as `s`
            if "-" not in s:                      # one part: most words
                if len(s) > MAX_NAME or low in kept or not gone(low):
                    return s
                return OTHER_PLAYER
            starts, ends, at = [], [], 0
            for piece in s.split("-"):
                starts.append(at)
                at += len(piece)
                ends.append(at)
                at += 1
            n = len(starts)
            budget = HIDE_BUDGET * n + 64
            out, i = [], 0
            while i < n:
                a = starts[i]
                hit = None
                # the counts that fit: no more parts than are left, no longer than MAX_NAME
                most = min(n, i + top, bisect_right(ends, a + MAX_NAME)) - i
                for x in range(bisect_right(counts, most) - 1, -1, -1):
                    j = i + counts[x]
                    b = ends[j - 1]
                    if b - a < 3:
                        break                     # shorter still for every smaller count
                    budget -= 1
                    if budget < 0:                # crafted names: hide the rest of the run whole
                        out.append(OTHER_PLAYER)
                        return "-".join(out)
                    k = low[a:b]
                    if k in kept:
                        hit = s[a:b]
                    elif gone(k):
                        hit = OTHER_PLAYER
                    else:
                        continue
                    out.append(hit)
                    i = j
                    break
                if hit is None:
                    out.append(s[a:ends[i]])
                    i += 1
            return "-".join(out)
        return _RUN_RE.sub(run, text)

    def scrub(self, obj):
        """`obj` (JSON-like) with every other player's name seen in this session replaced by
        "another player", and the user's own handle by "you", in every text, whatever it is and
        wherever it came from. Control and bidi characters are taken out of every text too
        (`words.clean_text`), so nothing the log says can steer a screen or a console."""
        handle = self.me["handle"]
        if not self._others and not handle and not self._forgot_sorted:
            return clean_all(obj)
        mine = handle.lower() if handle else None
        if self._others_re is None:
            self._others_re = name_regex(list(self._others) + ([handle] if handle else []))
            self._kept_lower = None
        rx = self._others_re
        if self._forgot_sorted:
            if self._kept_lower is None:
                self._kept_lower = {n.lower() for n in self._others} | ({mine} if mine else set())
                self._kept_counts = {_parts(n) for n in self._kept_lower}
            kept = self._kept_lower
            counts = sorted(self._forgot_counts | set(self._kept_counts))

            def hide(s):
                return self._hide_forgotten(s, kept, counts)
        else:
            hide = None

        def name_for(m):
            return YOU if m.group(0).lower() == mine else OTHER_PLAYER

        def walk(x):
            if isinstance(x, str):
                s = clean_text(x)
                if hide:                            # first: it leaves known names whole
                    s = hide(s)
                return rx.sub(name_for, s) if rx is not None else s
            if isinstance(x, dict):
                return {clean_text(k) if isinstance(k, str) else k: walk(v) for k, v in x.items()}
            if isinstance(x, (list, tuple)):
                return [walk(v) for v in x]
            return x
        return walk(obj)

    def _vehicle(self, vid, cls=None):
        if vid is None:
            return None
        v = self.vehicles.get(vid)
        if v is None:
            v = {"class": cls, "name": None, "retrieved": None, "hangar": None,
                 "status": "seen", "t": None}
            self.vehicles[vid] = v
            if len(self.vehicles) > 50:
                del self.vehicles[next(iter(self.vehicles))]
        if cls and not v["class"]:
            v["class"] = cls
        return v

    def _ship_word(self, vid, cls=None):
        v = self.vehicles.get(vid) if vid else None
        if v and v.get("name"):
            return v["name"]
        return ship_class(cls or (v or {}).get("class"))

    def _cap(self, lst, n=config.MAX_LIST):
        del lst[:-n]

    def _note(self, ev, kind, text):
        self.notable.append({"t": ev.t, "kind": kind, "text": text})
        self._cap(self.notable)

    def _close_stint(self, t):
        s = self.session
        if s["game"] == "in_game" and s["in_game_since"] is not None:
            s["in_game_s"] += max(0.0, t - s["in_game_since"])
        s["in_game_since"] = None

    # ------------------------------------------------------------------ session

    def _on_session_start(self, ev):
        s = self.session
        s.update(id=ev.name, start=ev.t, local=ev.local, build=ev.build, game="menu")
        return MAJOR, "Game started (build %s)" % (ev.build or "?")

    def _on_game_version(self, ev):
        self.session["version"] = ev.version

    def _on_joystick(self, ev):
        self.joysticks = [j for j in self.joysticks if j["index"] != ev.index]
        self.joysticks.append({"index": ev.index, "name": ev.name, "guid": ev.guid})
        self.joysticks.sort(key=lambda j: j["index"])
        if self._joy_final or not self._joy_missing():
            self._check_joysticks()        # a pass can be told at once; a failure waits (see apply)
        return MINOR, "Joystick %d: %s" % (ev.index + 1, ev.name)

    def _joy_missing(self):
        return [w for w in config.EXPECTED_JOYSTICKS
                if not any(_is_device(j, w) for j in self.joysticks)]

    def _check_joysticks(self):
        """The preflight check (PLAN §4, item 2): both the AB6 base and the MTQ throttle must be
        connected. Their order in the `Connected joystick<n>` lines does not matter.

        - Either one missing is a failure, the red alert. When the AB6 is missing, the keyboard or
          the MTQ takes the first slot and the stick does not work [seen: 12 launches in
          logbackups with the AB6 missing, root CLAUDE.md §1].
        - Both present in another order is a pass, with a note. On 2026-11-27 (the 12:57 PM
          launch) the lines listed the keyboard, the MTQ, then the AB6, and the user, in the
          Golem, reported that both the AB6 and the MTQ worked [the user's report]. Why the order
          does not matter is unconfirmed; perhaps the saved profile ties each joystick instance
          to its device by product id. The earlier rule, "AB6 joystick 1 and MTQ joystick 2",
          was an inference never tested with every device present, and raised a false alarm.

        A verdict is shown at once when both are listed; a failure only once the joystick lines
        have had their moment (the first other event after them)."""
        expected = config.EXPECTED_JOYSTICKS
        where = {w["label"]: next((j["index"] for j in self.joysticks if _is_device(j, w)), None)
                 for w in expected}
        missing = [w for w in expected if where[w["label"]] is None]
        usual = all(where[w["label"]] == i for i, w in enumerate(expected))
        order = "usual" if usual else "differs"
        if missing:
            first = next((j for j in self.joysticks if j["index"] == 0), None)
            text = "%s not connected; joystick 1 is %s" % (
                " and ".join(w["label"] for w in missing), first["name"] if first else "not listed")
            self.preflight = {"ok": False, "text": text, "order": order,
                              "missing": [w["name"] for w in missing]}
        elif usual:
            self.preflight = {"ok": True, "text": "AB6 is joystick 1 and MTQ joystick 2, as usual",
                              "order": order, "missing": []}
        else:
            places = ", ".join("%s is joystick %d" % (w["label"], where[w["label"]] + 1) for w in expected)
            self.preflight = {"ok": True, "order": order, "missing": [],
                              "text": "AB6 and MTQ both connected; listed in a different order than usual "
                                      "(%s), which has worked" % places}

    def _on_login(self, ev):
        handle = clean_text(ev.handle).strip()      # as the scrubber meets it in cleaned text
        self.me["handle"] = handle
        self._others.pop(handle, None)
        self._others_re = None                      # the scrubber now knows the handle too
        return MINOR, "Logged in"

    def _on_character(self, ev):
        if ev.current or self.me["player_id"] is None:
            self.me["player_id"] = ev.player_id

    def _on_profile_loaded(self, ev):
        self.profile = {"name": ev.name, "t": ev.t}
        return MAJOR, "Control profile %s loaded" % ev.name

    def _on_front_end(self, ev):
        s = self.session
        was = s["game"]
        self._close_stint(ev.t)
        self._close_queue(ev.t, "back to the menu")
        self._close_jump(ev.t, "back to the menu")
        self._leave_zone(ev.t)
        self._pending_world = None
        s["game"] = "menu"
        s["world"] = None
        if ev.reason == "ProcessBootRequest":
            return MINOR, "Main menu"
        if was == "in_game" or ev.reason == "OnLobbyPostGameUnload":
            return MINOR, "Back at the main menu"
        return None

    def _close_jump(self, t, why):
        """A quantum target still open when the user leaves the world (the menu, a disconnect, a
        new server, a respawn) is over: else it would bring Travel back on the next server
        (stage 3 review)."""
        q = self.quantum
        if q and q["closed"] is None:
            q["closed"], q["closed_by"] = t, why

    def _leave_zone(self, t):
        """Out of the world: "Monitored Space Down" was about where the user was. Without a
        "Restored" notice it would stay down for good (stage 3 review)."""
        if self.zone.get("monitored_down"):
            self.zone.update(monitored_down=None, t=t)

    def _on_join_server(self, ev):
        self._close_jump(ev.t, "joined a server")
        self._leave_zone(ev.t)
        self._pending_world = "pu"
        self.server["shard"] = ev.shard
        self.server["joined"] = ev.t
        if ev.shard and ev.shard not in self.server["shards"]:
            self.server["shards"].append(ev.shard)
        # The shard's name says which server the user was on: kept in the private form only, so
        # not in the feed line either (stage 3 review of the wiring).
        return MINOR, "Joining a server"

    def _on_connecting(self, ev):
        if self._pending_world is None:
            self._pending_world = "other"         # Arena Commander and the like: no <Join PU>
        return None

    def _on_spawned(self, ev):
        s = self.session
        if s["game"] == "in_game":
            return self._respawn(ev)
        if self._pending_world is not None:
            s["game"] = "in_game"
            s["world"] = self._pending_world
            s["in_game_since"] = ev.t
            s["spawns"] += 1
            self._pending_world = None
            if self.health["status"] != "ok":          # a fresh entry into the world
                self.health = {"status": "ok", "t": ev.t, "injuries": []}
            if s["world"] == "pu":
                return MAJOR, "In the game world"
            return MAJOR, "In a game mode outside the universe (no server join logged)"
        return None                                # the menu's own spawn

    def _on_disconnected(self, ev):
        if ev.cause == 30010:                      # "Nub destroyed": between menu and game, not an end
            return None
        last = self._last_disconnect
        self._last_disconnect = (ev.t, ev.cause, ev.reason)
        if last and last[1] == ev.cause and last[2] == ev.reason and ev.t - last[0] < 2.0:
            return None                            # the twin line of the one just read
        what = disconnect_kind(ev.cause, ev.reason)
        self.left_server.append({"t": ev.t, "cause": ev.cause, "reason": ev.reason, "what": what})
        self._cap(self.left_server)
        self._close_stint(ev.t)
        self._close_queue(ev.t, "left the server")
        self._close_jump(ev.t, "left the server")
        self._leave_zone(ev.t)
        self._close_incident(ev.t)
        if self.session["game"] == "in_game":
            self.session["game"] = "menu"
        level = ALERT if what in ("server crash", "kicked for inactivity") else MAJOR
        return level, {"left": "Left the server", "menu": "Left to the main menu",
                       "server crash": "The server crashed: back to the menu",
                       "kicked for inactivity": "Kicked for inactivity"}.get(
                           what, "Disconnected (%s)" % ev.reason)

    def _on_quit(self, ev):
        self._close_stint(ev.t)
        self._close_queue(ev.t, "quit")
        self._close_incident(ev.t)
        self.session["game"] = "ended"
        self.session["ended"] = {"t": ev.t, "how": "quit", "cause": ev.cause, "reason": ev.reason}
        return MAJOR, "Quit the game"

    # ------------------------------------------------------------------ places

    def _arrive(self, ev, code, how, docked, loc_id=None):
        loc = self.location
        if loc and loc["code"] == code and loc["docked"] == docked and loc["left"] is None:
            return None
        self.location = {"code": code, "how": how, "t": ev.t, "docked": docked,
                         "id": loc_id, "left": None}
        self.codes.add(code)
        # From CSR sc_livelog.py lines 199-204: a place joins the capped history when it differs
        # from the last one. Changed: codes are kept, not names.
        if not self.places or self.places[-1]["code"] != code:
            self.places.append({"code": code, "t": ev.t, "how": how})
            self._cap(self.places, config.MAX_PLACES)
        q = self.quantum
        if q and q["closed"] is None and docked:
            q["closed"], q["closed_by"] = ev.t, "docked"
        if how == "quantum":
            return MAJOR, "Arrived at %s" % self._place(code)
        return MAJOR, "At %s" % self._place(code)

    # `Update Inventory Location ... Landing [a] -> [b]. Location [c] -> [d]` [seen 2026-11]: `b`
    # is the place the user is landed at, 0 when not landed (it becomes 0 on leaving a station or
    # a city, and stays 0 in flight); `d` is a zone inside it and changes when walking from New
    # Babbage's city to a sub-location while `b` stays the same. So the landing id is the place,
    # and `RequestLocationInventory`, logged just after, names it.
    def _on_inventory_location(self, ev):
        self._landing = ev.landing_to
        loc = self.location
        if ev.landing_to == "0":
            if loc and loc["docked"] and loc["left"] is None:
                loc["left"] = ev.t
                return MAJOR, "Left %s" % self._place(loc["code"])
            return None
        code = self._loc_ids.get(ev.landing_to)
        if code:
            self._last_inv = code
        if loc and loc["docked"] and loc["left"] is None and (
                loc["id"] == ev.landing_to or (code and self.names.place(code) == self.names.place(loc["code"]))):
            loc["t"], loc["id"] = ev.t, ev.landing_to   # still here: moved inside it, or confirmed
            return None
        if code:
            return self._arrive(ev, code, "inventory", True, ev.landing_to)
        return None

    def _on_location_inventory(self, ev):
        self.codes.add(ev.code)
        self._last_inv = ev.code                  # where a shared shop name is (shops.json lookup)
        if self._landing and self._landing != "0" and self._landing not in self._loc_ids:
            self._loc_ids[self._landing] = ev.code
        loc = self.location
        if loc and loc["code"] == ev.code and loc["docked"] and loc["left"] is None:
            return None                                # the storage screen opened, or a refresh
        return self._arrive(ev, ev.code, "inventory", True, self._landing)

    def _on_planet_cells(self, ev):
        b = self.body
        if b and int(b["t"]) == int(ev.t) and b["cells"] >= ev.cells:
            return None                            # same stats block: keep the body with most cells
        changed = not b or b["name"] != ev.body
        self.body = {"name": ev.body, "cells": ev.cells, "t": ev.t}
        self.codes.add(ev.body)
        if changed:
            return MINOR, "Near %s (physics stats)" % self._place(ev.body)
        return None

    def _on_terrain_loaded(self, ev):
        self.near = {"name": ev.body, "t": ev.t}

    def _on_jurisdiction(self, ev):
        self.zone.update(jurisdiction=ev.name, t=ev.t)
        return MINOR, "Entered %s jurisdiction" % ev.name

    def _on_armistice(self, ev):
        self.zone.update(armistice=ev.inside, t=ev.t)
        return MINOR, "Entering the armistice zone" if ev.inside else "Leaving the armistice zone"

    def _on_monitored(self, ev):
        self.zone.update(monitored=ev.inside, t=ev.t)
        return MINOR, "Entered monitored space" if ev.inside else "Left monitored space"

    def _on_monitored_down(self, ev):
        # "Monitored Space Down": the comm array that reports crimes here is offline [game text;
        # unverified in a log]. Not the same as leaving monitored space.
        self.zone.update(monitored_down=ev.down, t=ev.t)
        if ev.down:
            self._note(ev, "monitored_down", "Monitored space down")
            return MAJOR, "Monitored space down"
        return MINOR, "Monitored space restored"

    # ------------------------------------------------------------------ quantum travel

    # From CSR sc_livelog.py lines 219-232: a selected target starts a new travel and the route
    # line adds the fuel estimate. Changed: only a selection starts a travel, never a route line
    # (plotting a route logs route lines too: CSR's "a route for another code is a new target"
    # made 15 travels in 9 logs of 2026-11 that were never selected); the vehicle is kept, so an
    # arrival line for someone else's ship is not taken for the user's (PLAN §3); and the route's
    # start is kept too.
    def _on_quantum_target(self, ev):
        q = self.quantum
        if q and q["target"] == ev.code and q["vehicle_id"] != ev.vehicle_id and ev.t - q["selected"] < 1.0:
            # Two ships log the same selection at once: a ship and the carrier it sits in [seen:
            # an M80 and the Liberator carrying it, 2026-11-20 8:11:25 PM, the same millisecond].
            # One travel, which belongs to the ship the user boarded: the class that fits its name
            # best (an exact fit beats a shorter class the name merely contains).
            if self._fit(ev.vehicle_class) > self._fit(q["vehicle_class"]):
                old = q["vehicle_id"]
                q["vehicle_id"], q["vehicle_class"] = ev.vehicle_id, ev.vehicle_class
                v = self._vehicle(ev.vehicle_id, ev.vehicle_class)
                sh = self.ship
                if sh and sh["own"] and old is not None and sh["vehicle_id"] == old:
                    ov = self.vehicles.get(old)
                    if ov is not None and ov["name"] == sh["name"]:
                        ov["name"] = None               # it was given the wrong ship's name
                    sh["vehicle_id"], sh["class"] = ev.vehicle_id, ev.vehicle_class
                    if v is not None and not v["name"]:
                        v["name"] = sh["name"]
                else:
                    self._ship_seen(ev, ev.vehicle_id, ev.vehicle_class)
            return None
        v = self._vehicle(ev.vehicle_id, ev.vehicle_class)
        if v is not None and v["status"] == "seen":
            v["status"] = "flown"
        sh = self.ship
        if not (sh and sh["own"] and sh["aboard"] and sh["name"] and not self._flies(ev.vehicle_class)):
            self._ship_seen(ev, ev.vehicle_id, ev.vehicle_class)   # else: perhaps a carrier's line
        return self._new_jump(ev, ev.code, ev.vehicle_id, ev.vehicle_class)

    def _flies(self, cls):
        """Does this vehicle class fit the ship the user boarded (by its channel name)?"""
        return self._fit(cls) > 0

    def _fit(self, cls):
        """How well a class fits the boarded ship's name: 2 exactly, 1 roughly, 0 not."""
        sh = self.ship
        if not (sh and sh["own"] and sh["aboard"] and cls):
            return 0
        return fit(sh["name"], cls)

    def _new_jump(self, ev, code, vid, cls):
        q = self.quantum
        if q and q["closed"] is None and q["arrived"] is None:
            q["closed"], q["closed_by"] = ev.t, "new target"
        self.codes.add(code)
        q = {"target": code, "vehicle_id": vid, "vehicle_class": cls, "selected": ev.t,
             "offset": ev.offset, "start": None, "fuel": None, "obstructed": None,
             "arrived": None, "closed": None, "closed_by": None}
        self.quantum = q
        self.jumps.append(q)
        self._cap(self.jumps)
        return MAJOR, self._jump_text(q)

    def _jump_text(self, q):
        text = "Quantum target: %s" % self._place(q["target"])
        if q["start"]:
            text += ", from %s" % q["start"]
        if q["fuel"] is not None:
            text += ", fuel estimate %s" % money(q["fuel"])
        return text

    def _update_jump_line(self):
        """The jump's feed line, changed in place and handed out again with the same id."""
        line = self.quantum.get("_line")
        if line is not None:
            text = self._jump_text(self.quantum)
            if text != line["text"]:
                line["text"] = text
                line["rev"] += 1
                self._extra_lines.append(line)

    def _route_for_jump(self, ev):
        q = self.quantum
        return q if (q and q["target"] == ev.code and q["arrived"] is None and
                     (q["vehicle_id"] is None or ev.vehicle_id == q["vehicle_id"])) else None

    def _on_route_start(self, ev):
        q = self._route_for_jump(ev)
        if q:
            q["start"] = ev.start
            self._update_jump_line()

    def _on_route_fuel(self, ev):
        q = self._route_for_jump(ev)                # a route plotted for anything else is ignored
        if q:
            q["fuel"] = ev.fuel
            self._update_jump_line()
        return None

    def _on_quantum_obstructed(self, ev):
        if self.quantum and self.quantum["closed"] is None:
            self.quantum["obstructed"] = ev.t
        self._note(ev, "quantum_obstructed", "Quantum destination obstructed")
        return MAJOR, "Quantum destination obstructed"

    def _on_quantum_arrived(self, ev):
        q = self.quantum
        if q is None or q["arrived"] is not None or ev.vehicle_id is None:
            return None                            # no travel to close
        mine = ev.vehicle_id == q["vehicle_id"] or (q["vehicle_id"] is None and ev.vehicle_id in self.vehicles)
        if not mine:
            return None                            # another ship's arrival [seen: 5 of 83 lines]
        q["arrived"] = ev.t
        if q["closed"] is None:
            q["closed"], q["closed_by"] = ev.t, "arrival"
        return self._arrive(ev, q["target"], "quantum", False)

    # ------------------------------------------------------------------ ships

    def _ship_seen(self, ev, vid, cls):
        """A line names the vehicle the user flies. The ship channel notice gives the ship's
        name but no id, so the boarded ship takes the first vehicle seen that fits its name. A
        record the user has left, or whose name does not fit the class, is never filled in
        [seen 2026-11-20: a left 'RSI Ursa Medivac' record took the Liberator's class]."""
        if not vid:
            return
        v = self.vehicles.get(vid)
        sh = self.ship
        if sh and sh["vehicle_id"] == vid:
            if cls and not sh["class"]:
                sh["class"] = cls
            return
        if sh and sh["own"] and sh["aboard"] and sh["vehicle_id"] is None and (
                cls is None or compatible(sh["name"], cls)):
            sh["vehicle_id"], sh["class"] = vid, cls or sh["class"]
            if v is not None and sh["name"] and not v["name"]:
                v["name"] = sh["name"]
            return
        # Another vehicle: the channel notice is often missing [ref], so the line is the evidence.
        self.ship = {"name": (v or {}).get("name") or ship_class(cls), "vehicle_id": vid,
                     "class": cls, "aboard": True, "seated": None, "t": ev.t, "own": True}

    def _on_ship_retrieved(self, ev):
        v = self._vehicle(ev.vehicle_id)
        v.update(retrieved=ev.t, hangar=ev.hangar, status="retrieved", t=ev.t)
        what = self._ship_word(ev.vehicle_id) if (v["name"] or v["class"]) else "Ship"
        return MAJOR, "%s retrieved%s" % (what, " (%s)" % ev.hangar if ev.hangar else "")

    def _on_channel_joined(self, ev):
        if not self._mine(ev.owner):
            self.ship = {"name": ev.name, "vehicle_id": None, "class": None, "aboard": True,
                         "seated": None, "t": ev.t, "own": False}
            return MINOR, "Aboard another player's %s" % ev.name
        self.ship = {"name": ev.name, "vehicle_id": None, "class": None, "aboard": True,
                     "seated": None, "t": ev.t, "own": True}
        # The ship just retrieved is the one boarded, if it has no name yet (my reasoning: a
        # retrieval is followed by boarding that ship; 10 minutes covers a hangar queue).
        recent = max(((vid, v) for vid, v in self.vehicles.items() if v["retrieved"] is not None),
                     key=lambda kv: kv[1]["retrieved"], default=None)
        if recent and ev.t - recent[1]["retrieved"] < 600 and recent[1]["name"] in (None, ev.name) \
                and (recent[1]["class"] is None or compatible(ev.name, recent[1]["class"])):
            vid, v = recent
            v["name"] = ev.name
            self.ship["vehicle_id"], self.ship["class"] = vid, v["class"]
        return MAJOR, "Boarded the %s" % ev.name

    def _on_channel_left(self, ev):
        self._mine(ev.owner)                       # remembers another player's name, if it is one
        sh = self.ship
        if sh and sh["name"] == ev.name:
            sh["aboard"] = False
            return MINOR, "Left the %s" % ev.name
        return None

    def _on_seat_left(self, ev):
        self._vehicle(ev.vehicle_id, ev.vehicle_class)
        self._ship_seen(ev, ev.vehicle_id, ev.vehicle_class)
        if self.ship and self.ship["vehicle_id"] == ev.vehicle_id:
            self.ship["seated"] = False
        q = self.quantum
        if q and q["closed"] is None:
            q["closed"], q["closed_by"] = ev.t, "left seat"
        if self.ship and self.ship["vehicle_id"] == ev.vehicle_id and self.ship["own"]:
            # Where the ship was left, for the on-foot view: the place the user is at, else the
            # planet or moon in range (the log has nothing closer, PLAN §3).
            loc = self.location
            self.ship_left = {"name": self._ship_word(ev.vehicle_id, ev.vehicle_class),
                              "vehicle_id": ev.vehicle_id, "class": ev.vehicle_class, "t": ev.t,
                              "code": loc["code"] if loc and loc["left"] is None else None,
                              "body": (self.body or self.near or {}).get("name")}
        return MAJOR, "Left the pilot seat of the %s" % self._ship_word(ev.vehicle_id, ev.vehicle_class)

    def _on_stowed(self, ev):
        v = self.vehicles.get(ev.vehicle_id)
        if v is None:
            return None                            # every hangar around logs its stows [seen]
        v["status"], v["t"] = "stowed", ev.t
        return MINOR, "Your %s was stowed" % self._ship_word(ev.vehicle_id)

    def _on_vehicle_destroyed(self, ev):
        self._mine(ev.killer)                      # remembers another player's name, if it is one
        pid = self.me["player_id"]
        own = ev.vehicle_id in self.vehicles or (pid is not None and ev.owner_id == pid)
        if not own:
            if self._count_kill(ev, pid):
                what = "destroyed" if ev.level_to >= DESTROYED else "crippled"
                ship = self._class_word(ev.vehicle_class)
                return MAJOR, "You %s %s %s" % (what, "an" if ship[:1] in "AEIOUaeiou" else "a", ship)
            if ev.reason == "GameRules":
                return MINOR, "Removed nearby: %s" % self._class_word(ev.vehicle_class)
            return MINOR, "Destroyed nearby: %s" % self._class_word(ev.vehicle_class)
        v = self._vehicle(ev.vehicle_id, ev.vehicle_class)
        v["status"], v["t"] = "destroyed", ev.t
        self.ships_lost.append({"t": ev.t, "vehicle_id": ev.vehicle_id, "class": ev.vehicle_class,
                                "reason": ev.reason})
        self._cap(self.ships_lost)
        if ev.reason != "GameRules" and ev.level_to >= DESTROYED and self._tally_level(ev, "lost"):
            self.tally["lost"] += 1
        how = {"SelfDestruct": "self-destructed", "Ejection": "abandoned (ejection)",
               "Collision": "destroyed in a collision"}.get(ev.reason, "destroyed (%s)" % ev.reason)
        return MAJOR, "Your %s was %s" % (self._ship_word(ev.vehicle_id, ev.vehicle_class), how)

    def _class_word(self, cls):
        s = self.ref.ship(cls)
        return (s or {}).get("name") or ship_class(cls)

    def _tally_level(self, ev, side):
        """Count a vehicle once, at the highest level it reaches (SURVEY.md §4: one line per
        damage-state change, 0 -> 1 crippled and 1 -> 2 destroyed). True when this line raises it."""
        seen = self._tally.get(ev.vehicle_id)
        if seen is not None and seen["level"] >= ev.level_to:
            return False
        if seen is None:
            self._tally[ev.vehicle_id] = seen = {"level": 0, "side": side, "class": ev.vehicle_class, "t": ev.t}
            if len(self._tally) > TALLY_KEEP:
                del self._tally[next(iter(self._tally))]
        was = seen["level"]
        seen.update(level=ev.level_to, t=ev.t)
        if side == "kill" and was == CRIPPLED:
            self.tally["crippled"] -= 1            # it was counted crippled; now it is destroyed
        return True

    def _count_kill(self, ev, pid):
        """A ship the user destroyed or crippled: the killer's id is the user's player id, and
        the ship is not the user's (SURVEY.md §4, CSR's rule) [unverified: no kill by the user is in
        the project's record]. Never on a self-destruct, whose killer can be anyone [seen]; never
        a wreck the game removes by its own rules (reason GameRules, the salvage drones [seen]);
        only a ship or vehicle class, since sentries are logged the same way [ref]."""
        if pid is None or ev.killer_id != pid or ev.owner_id == pid:
            return False
        if ev.reason in ("SelfDestruct", "GameRules") or ev.level_to < CRIPPLED:
            return False
        if not self.ref.is_vehicle(ev.vehicle_class):
            return False
        if not self._tally_level(ev, "kill"):
            return False
        self.tally["destroyed" if ev.level_to >= DESTROYED else "crippled"] += 1
        return True

    def _on_fatal_collision(self, ev):
        # `PlayerPilot: 1` alone makes it the user's crash: all 4 lines of 2026-11 were the user's
        # own ship [seen]. Whether the game ever logs this line for someone else's ship with a
        # player at the controls is unverified.
        if ev.vehicle_id not in self.vehicles and not ev.player_pilot:
            return None
        self._open_incident(ev, "crash")
        return ALERT, "Crashed the %s" % self._ship_word(ev.vehicle_id, ev.vehicle_class)

    # ------------------------------------------------------------------ health

    def _open_incident(self, ev, cause):
        if self._incident is None:
            self._incident = {"t": ev.t, "cause": cause, "items_lost": 0, "_last_item": None}
        return self._incident

    def _on_thrown_out(self, ev):
        if not self._mine(ev.actor):
            return None
        self._open_incident(ev, "ship destroyed")
        return MINOR, "Thrown out of the destroyed %s" % ship_class(ev.vehicle_class)

    def _on_incapacitated(self, ev):
        self._open_incident(ev, "downed")
        if self.health["status"] == "ok":
            self.health.update(status="downed", t=ev.t)
            self.tally["downed"] += 1
        return ALERT, "Downed (incapacitated)"

    def _on_emergency(self, ev):
        self._open_incident(ev, "downed")
        if self.health["status"] == "ok":
            self.health.update(status="downed", t=ev.t)
            self.tally["downed"] += 1
            return ALERT, "Downed: emergency services on the way"
        return None

    def _on_injury(self, ev):
        self.health["injuries"].append({"severity": ev.severity, "part": ev.part, "tier": ev.tier,
                                        "t": ev.t})
        self._cap(self.health["injuries"], 20)
        self._note(ev, "injury", "%s injury, %s, tier %d" % (ev.severity, ev.part, ev.tier))
        return ALERT if ev.severity in ("Severe", "Critical") else MAJOR, \
            "%s injury: %s, tier %d" % (ev.severity, ev.part.lower(), ev.tier)

    def _on_item_lost(self, ev):
        # A death is the body item, not the burst (SURVEY.md §5): the first line of the user's
        # own burst is always 'body_01_noMagicPocket' [seen: markers.log, courier.log], and a
        # burst for a corpse nearby starts with gear instead [ref: star-citizen-live, 4.7-4.8].
        # So a burst counts only when it starts with a body; its other items are counted with it.
        # A body item always starts a burst of its own: a gear burst from another body just
        # before must not swallow the user's death (stage 3 review).
        is_body = ev.item_class.lower().startswith("body_")
        b = self._burst
        if b is None or is_body or ev.t - b["t"] > BURST_GAP:
            self._burst = b = {"t": ev.t, "body": is_body}
        b["t"] = ev.t
        if not b["body"]:
            return None                            # not the user's body: someone else's gear
        inc = self._open_incident(ev, "died")
        last = inc["_last_item"]
        inc["items_lost"] += 1
        inc["_last_item"] = ev.t
        if self.health["status"] != "dead":
            self.health.update(status="dead", t=ev.t)
        if last is None:                           # the body line, one per death
            return ALERT, "Died: gear left on the body (a respawn confirms it)"
        return None

    def _recovered(self, ev):
        """Up again with no respawn: the incident was not a death (see ACTIVE_KINDS)."""
        inc, self._incident = self._incident, None
        self.recoveries.append({"t": inc["t"], "up": ev.t, "cause": inc["cause"],
                                "items_lost": inc["items_lost"], "treated": inc.get("treated")})
        self._cap(self.recoveries)
        self.health = {"status": "ok", "t": ev.t, "injuries": self.health["injuries"]}
        self._extra_lines.append(self._line(ev, "recovered", MINOR, "Up again, no respawn (so not a death)"))

    def _close_incident(self, t):
        """Leaving the server or quitting with an incident still open. Treated in a medical bed
        counts as a recovery; otherwise the log cannot tell, so it is noted and closed, neither a
        death nor a recovery [seen once: downed, then a disconnect 31 s later, 2026-11-23]."""
        inc, self._incident = self._incident, None
        if inc is None:
            return
        if inc.get("treated"):
            self.recoveries.append({"t": inc["t"], "up": inc["treated"], "cause": inc["cause"],
                                    "items_lost": inc["items_lost"], "treated": inc["treated"]})
            self._cap(self.recoveries)
        else:
            self.notable.append({"t": t, "kind": "left_while_downed",
                                 "text": "Left the server while %s (no respawn logged)" % inc["cause"]})
            self._cap(self.notable)

    def _respawn(self, ev):
        inc = self._incident
        self._incident = None
        death = {"t": inc["t"] if inc else ev.t, "respawn": ev.t,
                 "cause": inc["cause"] if inc else "unknown",
                 "items_lost": inc["items_lost"] if inc else 0}
        self.deaths.append(death)
        self._cap(self.deaths)
        self.health = {"status": "ok", "t": ev.t, "injuries": []}
        self._close_queue(ev.t, "respawned")
        self._close_jump(ev.t, "respawned")
        # The respawn place is logged a few milliseconds BEFORE `Spawned!` (Update Inventory
        # Location, then RequestLocationInventory) [seen in the samples and every respawn]. Keep a
        # place set after the incident began; forget one from before it (where the user died).
        loc = self.location
        since = inc["t"] if inc else ev.t - 5
        if loc is not None and loc["t"] < since:
            self.location = None
        return MAJOR, "Respawned"

    def _on_medical_bed(self, ev):
        # "The bed has restored your health". It repeats every 120 s once a bed has been used
        # [seen: 34 gaps of 120 s], so on its own it says little. After a downing it is the best
        # sign the user was treated [seen 2026-11: 7 downings were followed by one; 6 of them had
        # no respawn after it, and the user acted normally or quit; once a respawn still came 9 s
        # later]. My reading: the downing ends here; the incident stays open, so a respawn soon
        # after is still a death, and activity or a quit closes it as a recovery.
        self.health["injuries"] = []
        inc = self._incident
        if inc is not None and self.health["status"] == "downed":
            inc["treated"] = ev.t
            self.health.update(status="ok", t=ev.t)
            return MAJOR, "Treated in a medical bed"
        return None

    def _on_regen_set(self, ev):
        self._note(ev, "regen_set", "Regeneration point set")
        return MAJOR, "Regeneration point set here"

    # ------------------------------------------------------------------ contracts

    # From CSR sc_livelog.py lines 296-299 (`_contract_for`): an objective belongs to the
    # contract with its mission id, else to the newest active one. Changed: a mission id this log
    # has not announced gets a record of its own (contracts carry over between launches) rather
    # than being pinned on another contract.
    def _contract_for(self, mid):
        if mid:
            return self.contracts.get(mid) or self._contract(mid, None, None)
        return next((c for c in reversed(list(self.contracts.values())) if c["status"] == "active"), None)

    def _contract(self, mid, title, t):
        key = mid or ("title:" + title if title else None)
        if key is None:
            return None
        c = self.contracts.get(key)
        if c is None and title:
            c = next((x for x in reversed(list(self.contracts.values()))
                      if x["title"] == title and x["mission_id"] is None), None)
        if c is None:
            c = {"mission_id": mid, "title": title, "status": None, "accepted": None,
                 "ended": None, "end_reason": None, "giver": None, "internal": None,
                 "objectives": [], "objective": None, "t": t,
                 # stage 3: from reference/contracts.json (see _classify), and what the log adds
                 "kind": None, "view": None, "setting": None, "giver_name": None, "type_name": None,
                 "lookup": None, "unmapped": False, "touched": t, "reward": None}
            self.contracts[key] = c
            self._trim_contracts(key)
            self._classify(c)
        return c

    def _trim_contracts(self, keep):
        """At the cap, drop an ended contract first, oldest first; then one not known to be
        active; then the oldest active one. Never `keep`, the one just created (the first form
        dropped it, since it is not active yet when it is made: stage 3 review)."""
        while len(self.contracts) > config.MAX_CONTRACTS:
            order = [k for k in self.contracts if k != keep]
            old = next((k for k in order if self.contracts[k]["status"] in ENDED), None) or \
                next((k for k in order if self.contracts[k]["status"] != "active"), None) or order[0]
            del self.contracts[old]

    def _classify(self, c):
        """Kind, view, setting (on foot or in a ship) and giver from reference/contracts.json, in
        the order its `_meta.lookup` gives: the marker's contract name, its generator, the title.
        Asked again whenever one of those three arrives; the answers are cached."""
        info = self.ref.contract(c["internal"], c["giver"], c["title"])
        c.update(kind=info["kind"], view=info["view"], setting=info["setting"],
                 giver_name=info["giver"] or _generator_words(c["giver"]), type_name=info["type_name"],
                 lookup=info["how"], unmapped=bool(info["unmapped"]))
        if c.get("_raw"):
            self._look_again(c)

    def _look_again(self, c):
        """A contract the log had not placed is placed now (its title or marker came): its
        objectives stored meanwhile are worded again from their text as read (`_raw`, kept on the
        contract, never output): a player contract's as such contracts' are (the name learned
        now), an NPC contract's as written (stage 3 review, round 5)."""
        player = law.player_contract(c)
        if player is None:
            return
        pairs = c.pop("_raw")
        objs = c["objectives"]
        for o, raw in pairs:
            if not any(x is o for x in objs):
                continue
            text = raw if player is False else self._objective_words(c, raw, player)
            if text != o["text"]:
                o["text"] = text
                o["stop"] = _stop(text, o["id"])
        if objs:
            live = [x for x in objs if x["state"] == "active"]
            c["objective"] = (live or objs)[-1]["text"]

    def _touch(self, c, t):
        if c is not None and (c["touched"] is None or t >= c["touched"]):
            c["touched"] = t

    # From CSR sc_livelog.py lines 405-425 (the contract notices). Changed: a contract announced
    # again (same mission id) is updated, not added a second time; a failed or withdrawn contract
    # (stage 3, SURVEY.md §1) has handlers of this project's own below.
    def _on_contract_accepted(self, ev):
        title = self._title_words(ev.title)
        c = self._contract(ev.mission_id, title, ev.t)
        again = c["accepted"] is not None
        if c["title"] != title:
            c["title"] = title
            self._classify(c)
        if c["status"] in (None, "active"):
            c["status"] = "active"
        if c["accepted"] is None:
            c["accepted"] = ev.t
        self._touch(c, ev.t)
        if again:
            return MINOR, "Contract still active: %s" % title
        return MAJOR, "Contract accepted: %s" % title

    def _on_contract_complete(self, ev):
        title = self._title_words(ev.title)
        c = self._contract(ev.mission_id, title, ev.t)
        if not c["title"]:
            c["title"] = title
            self._classify(c)
        if c["status"] != "complete":
            c["status"] = "complete"
            c["ended"] = c["ended"] or ev.t
        # A drop-off gets no "Objective Complete" of its own: the contract completing is the
        # delivery [seen: courier.log, all four completed couriers; SURVEY.md §2 for hauls].
        for o in c["objectives"]:
            if o["state"] == "active" and (o.get("stop") or {}).get("kind") == "dropoff":
                o["state"] = "complete"
        return MAJOR, "Contract complete: %s" % title

    def _contract_end_notice(self, ev, status):
        """"Contract Failed:" or "Contract Withdrawn:" [game text, unverified in a log]. Its
        `<EndMission>` line can come first or after; the contract is announced once."""
        title = self._title_words(ev.title)
        c = self._contract(ev.mission_id, title, ev.t)
        if not c["title"]:
            c["title"] = title
            self._classify(c)
        if c["status"] == status:
            return None                            # its <EndMission> line said so already
        if c["status"] in (None, "active"):
            c["status"] = status
            c["ended"] = c["ended"] or ev.t
        self._note(ev, "contract_" + status, "Contract %s: %s" % (status, title))
        return MAJOR, "Contract %s: %s" % (status, title)

    def _on_contract_failed(self, ev):
        return self._contract_end_notice(ev, "failed")

    def _on_contract_withdrawn(self, ev):
        return self._contract_end_notice(ev, "withdrawn")

    # From CSR sc_livelog.py lines 301-324 (`_objective`): an objective is found by its id, else
    # by its text, and the contract's current objective is the newest one still open. Changed:
    # the hauling "drops" CSR tracks are left out of this adaptation; stage 3 reads pickups,
    # drop-offs and the hauling manifest with this project's own `_stop()` below.
    def _objective(self, ev, state):
        c = self._contract_for(ev.mission_id)
        if not c:
            return None
        text = ev.text
        optional = text.upper().startswith("OPTIONAL:")
        if optional:
            text = text[len("OPTIONAL:"):].strip()
        plain = text
        player = law.player_contract(c)
        text = self._objective_words(c, text, player)
        shown = ev.text if text == plain else ("OPTIONAL: " if optional else "") + text
        objs = c["objectives"]
        o = (next((o for o in objs if ev.objective_id and o["id"] == ev.objective_id), None)
             or next((o for o in objs if o["text"] == text), None))
        if o is None:
            o = {"id": ev.objective_id, "text": text, "optional": optional, "state": state, "t": ev.t,
                 "done": None, "stop": None}
            objs.append(o)
            del objs[:-config.MAX_OBJECTIVES]
        if o["text"] != text or o.get("stop") is None:
            o["stop"] = _stop(text, ev.objective_id or o["id"])
        o.update(text=text, state=state)
        if player is None:
            # not placed yet: the text as read, for when its title or marker comes (_look_again)
            raw = [pair for pair in c.get("_raw") or () if pair[0] is not o and any(x is pair[0] for x in objs)]
            c["_raw"] = raw + [[o, plain]]
        if state != "active" and o.get("done") is None:
            o["done"] = ev.t
        if c["status"] is None and state == "active":
            c["status"] = "active"                 # a contract from an earlier launch, still running
        live = [x for x in objs if x["state"] == "active"]
        c["objective"] = (live or objs)[-1]["text"]
        self._touch(c, ev.t)
        return c, shown

    def _objective_words(self, c, text, player):
        """An objective as the state keeps it. In a contract that names a player in its objectives
        (`player`, law.player_contract: "beacon" or "bounty"), one of a known shape is worded
        without the name, which is learned (a beacon's words for a beacon, "the target" for a
        bounty), and one of any other shape is not shown (counted in `withheld`) unless it is one
        of the game's nameless objectives. In a contract not placed (None), a known shape whose
        slot could be a handle is worded "the target" and nothing is learned (round 5: one-word
        NPC names were learned as players); the contract's placement looks at it again. In a
        contract known to be of another kind (False), nothing changes (round 4: "Rescue <player>"
        reached the page)."""
        if player is False:
            return text
        shape = law.player_objective(text)
        if shape is not None:
            words, slot, who, neutral = shape
            if player:
                if who:
                    self._learn(slot)
                return words if player == "beacon" else neutral
            if not who or law.learnable(slot, self.ref.game_words(self.names)):
                return neutral
            return text
        if player and text not in law.NAMELESS_OBJECTIVES:
            self.session["withheld"] += 1
            return law.WITHHELD_OBJECTIVE
        return text

    def _title_words(self, title):
        """A contract title as the state keeps it: a player bounty's title worded without the
        player, whose name is learned when it is one word (law.PLAYER_TITLES)."""
        found = law.player_title(title) if title else None
        if found is None:
            return title
        words, slot = found
        self._learn(slot)                         # learnable() takes one word only
        return words

    def _on_objective_new(self, ev):
        c = self._objective(ev, "active")
        return (MINOR, "New objective: %s" % c[1]) if c else None

    def _on_objective_complete(self, ev):
        c = self._objective(ev, "complete")
        return (MINOR, "Objective complete: %s" % c[1]) if c else None

    def _on_objective_failed(self, ev):
        # Not the contract's end: a patrol's optional objective can fail and the contract still
        # complete [ref: QuantumWake, SURVEY.md §1].
        c = self._objective(ev, "failed")
        return (MAJOR, "Objective failed: %s" % c[1]) if c else None

    def _on_objective_withdrawn(self, ev):
        c = self._objective(ev, "withdrawn")
        return (MINOR, "Objective withdrawn: %s" % c[1]) if c else None

    # From CSR sc_livelog.py lines 241-247 (<EndMission>): the authoritative end of a contract;
    # an abandon raises no HUD notice. Changed: a mission this log never announced gets a record
    # of its own, since contracts carry over between launches; a failure or withdrawal already
    # announced by its notice is not announced again.
    def _on_mission_ended(self, ev):
        c = self.contracts.get(ev.mission_id) or self._contract(ev.mission_id, None, ev.t)
        kind = ev.completion.strip().lower()
        status = END_STATUS.get(kind, kind or "ended")
        told = c["status"] == status
        if c["status"] in (None, "active"):
            c["status"] = status
        c["ended"] = c["ended"] or ev.t
        c["end_reason"] = ev.reason
        title = c["title"] or c["internal"] or "a contract from an earlier launch"
        if status == "complete":
            return None if c["accepted"] is not None and c["title"] else (MAJOR, "Contract ended: %s" % title)
        if told and status in ("failed", "withdrawn"):
            return None                            # its notice said so already
        if status in ("failed", "withdrawn") and c["status"] == status:
            self._note(ev, "contract_" + status, "Contract %s: %s" % (status, title))
        return MAJOR, "Contract %s: %s" % (status, title)

    def _on_mission_marker(self, ev):
        c = self._contract(ev.mission_id, None, ev.t)
        if (c["giver"], c["internal"]) != (ev.giver, ev.contract):
            c["giver"], c["internal"] = ev.giver, ev.contract
            self._classify(c)
        self._touch(c, ev.t)

    def _on_reward(self, ev):
        # "Awarded <n> aUEC": only legacy contracts log their pay [ref: QuantumWake, SURVEY.md §2].
        c = self.contracts.get(ev.mission_id) if ev.mission_id else None
        if c is None:                              # the contract that just completed, if any
            c = next((x for x in reversed(list(self.contracts.values()))
                      if x["status"] == "complete" and x["ended"] is not None and 0 <= ev.t - x["ended"] < 60), None)
        if c is not None:
            c["reward"] = ev.amount
        self.rewards.append({"t": ev.t, "amount": ev.amount, "mission_id": c["mission_id"] if c else None})
        self._cap(self.rewards)
        self._note(ev, "reward", "Awarded %s aUEC" % money(ev.amount))
        return MAJOR, "Awarded %s aUEC" % money(ev.amount)

    # ------------------------------------------------------------------ the law (stage 3)

    def _law(self, ev, kind, text, note=True, **extra):
        row = {"t": ev.t, "kind": kind, "text": text}
        row.update(extra)
        self.law.append(row)
        self._cap(self.law)
        if note:
            self._note(ev, kind, text)

    def _on_crimestat(self, ev):
        # "Decreased" has no text in global.ini [game] but a tool matches it [ref]: kept, not raised.
        text = "CrimeStat rating increased" if ev.up else "CrimeStat rating decreased"
        self._law(ev, "crimestat", text, note=ev.up, up=ev.up)
        return (ALERT if ev.up else MINOR), text

    def _learn(self, word, guess=False):
        """Learn a word from a notice as another player's name, only if it can be a handle and is
        no word of the game (law.learnable): the victim of a crime is as often a security force or
        a civilian ("Hurston Security" made the jurisdiction read "another player Dynamics":
        stage 3 review, round 2). A `guess` (a candidate of a shape the parser does not read) must
        also be no word of the game's notices (law.guessable: "Share is unavailable ..." taught
        "Share", round 4). The notice's own text never holds it."""
        if not word:
            return
        w = (law.guessable if guess else law.learnable)(word, self.ref.game_words(self.names))
        if w:
            self._other(w)

    def _on_crime(self, ev):
        # The victim can be anyone, so it is never worded; a victim of one word that can be a
        # handle is learned, so another text naming the same player hides it too.
        victim = (ev.victim or "").split()
        if len(victim) == 1:
            self._learn(victim[0])
        crime = law.crime_name(ev.crime) or "a crime"
        text = "Crime committed: %s%s" % (crime, " against someone" if victim else "")
        self._law(ev, "crime", text, crime=crime)
        return MAJOR, text

    def _on_crime_against_you(self, ev):
        # The charge notice's first slot is a player (law.py): worded as "another player" here,
        # and learned under the same rule.
        self._learn(ev.attacker)
        crime = law.crime_name(ev.crime) or "a crime"
        text = "Attacked: another player committed %s against you" % crime
        self._law(ev, "attacked", text, crime=crime)
        return ALERT, text

    def _on_fined(self, ev):
        text = "Fined %s UEC" % money(ev.amount)
        self._law(ev, "fined", text, amount=ev.amount)
        return MAJOR, text

    def _on_impounded(self, ev):
        text = "Vehicle impounded%s" % (": %s" % ev.vehicle if ev.vehicle else "")
        self._law(ev, "impounded", text, vehicle=ev.vehicle or None)
        return ALERT, text

    # ------------------------------------------------------------------ hangar, refinery, trade

    def _on_hangar_queue(self, ev):
        h = self.hangar
        q = h["queue"]
        if q is None:
            h["queue"] = q = {"joined": ev.t, "place": ev.place, "wait_s": ev.wait_s, "t": ev.t}
        else:
            q.update(place=ev.place, wait_s=ev.wait_s, t=ev.t)
        if ev.place is not None and ev.wait_s is not None:
            text = "Hangar queue: place %d, up to %s" % (ev.place, duration(ev.wait_s))
        else:
            text = "Joined the hangar queue"
        return MAJOR, text

    def _on_hangar_ready(self, ev):
        h = self.hangar
        q, h["queue"] = h["queue"], None
        h["ready"] = ev.t
        if q:
            h["waits"].append({"joined": q["joined"], "ready": ev.t, "wait_s": q["wait_s"],
                               "ended": None})
            self._cap(h["waits"], 20)
            return MAJOR, "Hangar ready after %s" % duration(ev.t - q["joined"])
        return MAJOR, "Hangar ready"

    def _close_queue(self, t, why):
        """A queue the user is no longer in: a respawn, the menu, leaving the server, a quit."""
        h = self.hangar
        q, h["queue"] = h["queue"], None
        if q:
            h["waits"].append({"joined": q["joined"], "ready": None, "wait_s": q["wait_s"], "ended": why})
            self._cap(h["waits"], 20)

    def _on_refinery_done(self, ev):
        self.refinery.append({"t": ev.t, "count": ev.count, "station": ev.station})
        self._cap(self.refinery)
        what = "Refinery order" if ev.count == 1 else "%d refinery orders" % ev.count
        self._note(ev, "refinery_done", "%s completed at %s" % (what, ev.station))
        return MAJOR, "%s completed at %s" % (what, ev.station)

    def _trade(self, ev, kind, shop, item, price, quantity=None, extra=None):
        # `at`: the last inventory location before the line, which says where a shop name shared
        # across a chain is (shops.json; PLAN §3's trap list) [ref: CSR, QuantumWake].
        row = {"t": ev.t, "offset": ev.offset, "kind": kind, "shop": shop, "item": item,
               "price": price, "quantity": quantity, "result": None, "at": self._last_inv}
        if extra:
            row.update(extra)
        self.trade.append(row)
        self._cap(self.trade, config.MAX_TRADES)
        return row

    def shop_info(self, row):
        """A trade row's shop: kind, display name, and its place (shops.json's when the name is at
        one place only, else the place of the last inventory location before the line)."""
        s = self.ref.shop(row.get("shop")) or {}
        place = s.get("place")
        how = "table" if place else None
        if not place and row.get("at"):
            place, how = self.names.place(row["at"]), "last inventory location"
        return {"kind": s.get("kind"), "name": s.get("name") or row.get("shop"), "place": place,
                "place_name": self.names.place_name(place) if place else None, "place_from": how}

    def _where(self, shop):
        info = self.shop_info({"shop": shop, "at": self._last_inv})
        if info["place_name"]:
            return " at %s" % info["place_name"]
        return ""

    def _on_shop_buy(self, ev):
        self._trade(ev, "buy", ev.shop, ev.item, ev.price, ev.quantity)
        return MAJOR, "Bought %s%s for %s aUEC" % (
            ev.item, " x%d" % ev.quantity if ev.quantity and ev.quantity > 1 else "", money(ev.price))

    def _on_shop_sell(self, ev):
        self._trade(ev, "sell", ev.shop, ev.item, ev.price, ev.quantity)
        return MAJOR, "Sold %s%s for %s aUEC" % (
            ev.item, " x%d" % ev.quantity if ev.quantity and ev.quantity > 1 else "", money(ev.price))

    def _on_shop_result(self, ev):
        for row in reversed(self.trade[-10:]):
            if row["result"] is None and ev.t - row["t"] < 120 and \
                    (ev.shop is None or row["shop"] == ev.shop):
                row["result"] = ev.result
                if ev.result != "Success":
                    return MAJOR, "%s did not go through (%s)" % (
                        {"buy": "Purchase", "sell": "Sale"}.get(row["kind"], "Transaction"), ev.result)
                return None
        return None

    # Commodity quantities (SURVEY.md §0.2). The buy line says its unit, hundredths of an SCU:
    # `quantity[3200.000000 cSCU]` for 25,025 aUEC at `shopPricePerCentiSCU[7.82]`, which is
    # 32 SCU at 782 a SCU [seen: markers.log, the figures agree]. The sell line prints a bare
    # number, `quantity[9]`, read as SCU as other tools do [ref: SC-Game-log-Parser]; unverified:
    # the one sample's box data lists a single 2 SCU box beside it, which does not fit 9 SCU.
    def _on_commodity_sell(self, ev):
        name = self.ref.resource(ev.resource_id)
        amount, unit = _quantity(ev.quantity)
        scu_ = amount if unit in ("", "SCU") else (amount / 100.0 if unit == "cSCU" and amount is not None else None)
        self._trade(ev, "commodity_sell", ev.shop, ev.resource_id, ev.amount, ev.quantity,
                    {"box": ev.box, "commodity": name, "scu": scu_, "scu_verified": unit == "cSCU"})
        what = "%s SCU of %s" % (scu(scu_), name or "a commodity") if scu_ is not None else (name or "a commodity")
        return MAJOR, "Sold %s for %s aUEC%s" % (what, money(ev.amount), self._where(ev.shop))

    def _on_commodity_buy(self, ev):
        name = self.ref.resource(ev.resource_id)
        amount, unit = _quantity(ev.quantity)
        scu_ = (amount / 100.0 if unit == "cSCU" else amount if unit in ("", "SCU") else None) if amount is not None else None
        per = ev.price / scu_ if scu_ else None
        self._trade(ev, "commodity_buy", ev.shop, ev.resource_id, ev.price, ev.quantity,
                    {"commodity": name, "scu": scu_, "per_scu": per, "scu_verified": unit == "cSCU"})
        what = "%s SCU of %s" % (scu(scu_), name or "a commodity") if scu_ is not None else (name or "a commodity")
        return MAJOR, "Bought %s for %s aUEC%s" % (what, money(ev.price), self._where(ev.shop))

    def _on_refinery_sell(self, ev):
        self._trade(ev, "refinery_sell", ev.shop, None, None)
        return MAJOR, "Sold ore to the refinery (what and for how much is not logged)"

    def _on_rental(self, ev):
        self._trade(ev, "rental", ev.shop, ev.item, ev.price)
        return MAJOR, "Rented %s for %s aUEC" % (ev.item, money(ev.price))

    def _on_storage_count(self, ev):
        # The count is what the freight elevator screen lists at that moment, which follows the
        # screen's filter: 156, 34, 42, 156 within 70 s with nothing moved [seen 2026-11-26
        # 5:45 PM log]. So it is not the stock; the largest count seen is the best hint.
        code = self._loc_ids.get(ev.location_id)
        prev = self._storage_seen.get(ev.location_id)
        self._storage_seen[ev.location_id] = ev.count
        top = max(ev.count, (self.storage or {}).get("max", 0)
                  if self.storage and self.storage["location_id"] == ev.location_id else 0)
        self.storage = {"location_id": ev.location_id, "code": code, "count": ev.count,
                        "max": top, "t": ev.t}
        if prev == ev.count:
            return None
        where = self._place(code) if code else "this location"
        return MINOR, "Storage screen at %s lists %d items" % (where, ev.count)

    def _on_fabricator_opened(self, ev):
        self.fabricator.append(ev.t)
        self._cap(self.fabricator)
        return MINOR, "Fabricator screen opened"

    def _on_blueprint(self, ev):
        self.blueprints.append({"t": ev.t, "name": ev.name})
        self._cap(self.blueprints)
        self._note(ev, "blueprint", "Blueprint received: %s" % ev.name)
        return MAJOR, "Blueprint received: %s" % ev.name

    def _on_gadget_placed(self, ev):
        gadget = ev.gadget.replace("Mining_Gadget_", "").replace("_", " ")
        if ev.rock:
            ore = ev.rock.rsplit("_", 1)[-1]
            return MINOR, "Placed a %s gadget on a %s rock" % (gadget, ore)
        return MINOR, "Placed a %s gadget loose (not on a rock)" % gadget

    def _on_screenshot(self, ev):
        self.screenshots.append({"t": ev.t, "name": ev.name})
        self._cap(self.screenshots)
        return MINOR, "Screenshot %s" % ev.name

    def _on_notice(self, ev):
        withheld = bool(getattr(ev, "withheld", ""))
        for name in getattr(ev, "names", ()) or ():    # a notice worded without a name
            self._learn(name, guess=withheld)
        if ev.hint:
            if withheld:
                # A tip-shaped notice of a family: never shown, as every tip, and counted apart, so
                # `withheld` stays a count of feed lines (stage 3 review, round 4: the rescue
                # beacon's toast landed here uncounted).
                self.session["withheld_tips"] += 1
            return None
        if withheld:
            # A notice of a family that can name a player, in a shape the parser does not read:
            # shown as the family's neutral text, and counted so `status` can show that shapes
            # are being missed (stage 3 review, round 3).
            self.session["withheld"] += 1
        elif law.HANDLE_RE.match(ev.text) and law.guessable(ev.text, self.ref.game_words(self.names)):
            # A notice that is one word that can be a handle (hud_law_InfractionWarning is "%ls",
            # what fills it is not known): not shown, and counted (round 4). Nothing is learned.
            self.session["withheld"] += 1
            return MINOR, law.ONE_WORD_WITHHELD
        return MINOR, ev.text

    # ------------------------------------------------------------------ output

    def unmapped(self):
        """Location codes seen that the names table does not know (for data/unmapped.json)."""
        return sorted(c for c in self.codes if not self.names.known(c) and not self.names.dynamic(c))

    def unmapped_contracts(self):
        """Contracts that reference/contracts.json could not place (its lookup's step 5: kind
        unknown, Mission view), for data/unmapped.json beside the location codes."""
        out, seen = [], set()
        for c in self.contracts.values():
            key = (c["internal"], c["giver"], c["title"])
            if c["unmapped"] and key not in seen:
                seen.add(key)
                out.append({"contract": c["internal"], "generator": c["giver"], "title": c["title"]})
        return out

    def ship_info(self, ship=None):
        """The reference facts for a ship record (the current one by default): display name, job,
        cargo grid in SCU, fleet or not. None when neither its class nor its name is known."""
        sh = ship if ship is not None else self.ship
        if not sh:
            return None
        return self.ref.ship(sh.get("class"), sh.get("name"))

    def current_contracts(self):
        """Active contracts, the most recently touched first (the log does not say which one the
        user is tracking, PLAN §4)."""
        act = [c for c in self.contracts.values() if c["status"] == "active"]
        return sorted(act, key=lambda c: c["touched"] or c["t"] or 0, reverse=True)

    def to_dict(self, private=False):
        """The state as JSON-ready data. With private=False (what is shown or saved), other
        players' names are replaced in every text; private=True keeps them and adds `me` (the
        handle and player id), for memory only. Either way no text carries a control or bidi
        character."""
        n = self.names

        def place(code):
            if not code:
                return None
            e = n.entry(code)
            return {"code": code, "name": n.name(code), "short": n.short(code),
                    "kind": e.get("kind"), "body": e.get("body"), "place": n.place(code)}

        s = self.session
        loc = self.location
        q = self.quantum
        d = {
            "schema": 1,
            "session": {"id": s["id"], "start": iso(s["start"]), "local": s["local"],
                        "build": s["build"], "version": s["version"], "game": s["game"],
                        "world": s["world"], "ended": _times(s["ended"]),
                        "last_event": iso(s["last_t"]), "events": s["events"],
                        "spawns": s["spawns"], "in_game_s": round(s["in_game_s"], 1),
                        "in_game_since": iso(s["in_game_since"]), "unreadable": s["unreadable"],
                        "withheld": s["withheld"], "withheld_tips": s["withheld_tips"]},
            # The shard names (which servers the user was on) are in the private form only.
            "server": {"joined": iso(self.server["joined"]), "count": len(self.server["shards"])},
            "joysticks": [dict(j, number=j["index"] + 1) for j in self.joysticks],
            "preflight": dict(self.preflight),
            "profile": _times(self.profile),
            "location": dict(place(loc["code"]), how=loc["how"], t=iso(loc["t"]),
                             docked=loc["docked"], left=iso(loc["left"])) if loc else None,
            "places": [dict(place(p["code"]), t=iso(p["t"]), how=p["how"]) for p in self.places],
            "body": dict(place(self.body["name"]), t=iso(self.body["t"])) if self.body else None,
            "zone": _times(self.zone),
            "ship": dict(_times(self.ship), info=self.ship_info()) if self.ship else None,
            "vehicles": {vid: _times(v) for vid, v in self.vehicles.items()},
            "quantum": _jump(q, place) if q else None,
            "jumps": [_jump(j, place) for j in self.jumps],
            "contracts": [_contract_out(c) for c in self.contracts.values()],
            "hangar": {"queue": _times(self.hangar["queue"]), "ready": iso(self.hangar["ready"]),
                       "waits": [_times(w) for w in self.hangar["waits"]]},
            "refinery": [_times(r) for r in self.refinery],
            "trade": [dict(_times(r), shop_info=self.shop_info(r)) for r in self.trade],
            # Stage 3: the session's tally, law, pay, where the ship was left, and the contracts
            # the reference table could not place.
            "tally": dict(self.tally),
            "law": [_times(x) for x in self.law],
            "rewards": [_times(x) for x in self.rewards],
            "ship_left": dict(_times(self.ship_left), where=self._place(self.ship_left["code"])
                              if self.ship_left["code"] else (self._place(self.ship_left["body"])
                                                              if self.ship_left["body"] else None))
            if self.ship_left else None,
            "unmapped_contracts": self.unmapped_contracts(),
            "blueprints": [_times(b) for b in self.blueprints],
            "health": {"status": self.health["status"], "t": iso(self.health["t"]),
                       "injuries": [_times(i) for i in self.health["injuries"]]},
            "deaths": [_times(x) for x in self.deaths],
            "recoveries": [_times(x) for x in self.recoveries],
            "ships_lost": [_times(x) for x in self.ships_lost],
            "screenshots": [_times(x) for x in self.screenshots],
            "storage": _times(self.storage),
            "left_server": [_times(x) for x in self.left_server],
            "notable": [_times(x) for x in self.notable],
            "feed": [dict(x, t=iso(x["t"])) for x in self.feed],
            "unmapped": self.unmapped(),
            # Stage 3: the plan data, timers, alerts and the view. Empty in stage 1.
            "plan": self.plan, "timers": list(self.timers), "alerts": list(self.alerts),
            "view": self.view,
        }
        if private:
            d["me"] = dict(self.me)
            d["server"].update(shard=self.server["shard"], shards=list(self.server["shards"]))
            return clean_all(d)
        return self.scrub(d)


# ---------------------------------------------------------------------- module helpers

TIME_KEYS = {"t", "joined", "ready", "retrieved", "selected", "arrived", "closed", "obstructed",
             "accepted", "ended", "respawn", "up", "treated", "touched", "done"}


def _times(d):
    if d is None:
        return None
    return {k: (iso(v) if k in TIME_KEYS and isinstance(v, (int, float)) and not isinstance(v, bool) else v)
            for k, v in d.items() if not k.startswith("_")}


def _jump(q, place):
    out = _times(q)
    out["target"] = place(q["target"])
    return out


def _contract_out(c):
    out = _times(c)                                # leaves out "_raw", the objectives as read
    out["objectives"] = [_times(o) for o in c["objectives"]]
    return out


def _generator_words(g):
    """A generator name the table does not know, in words ('Example_Generator' -> 'Example')."""
    if not g:
        return None
    words = re.sub(r"_?Generator$", "", g).replace("_", " ").strip()
    return words or None


def _quantity(text):
    """'3200.000000 cSCU' -> (3200.0, 'cSCU'); '9' -> (9.0, ''); junk -> (None, None)."""
    m = QUANTITY_RE.match(text or "")
    if not m:
        return None, None
    try:
        x = float(m.group(1))
    except ValueError:
        return None, None
    return (x, m.group(2)) if x == x and x < 1e9 else (None, None)


def _stop(text, objective_id):
    """A pickup or drop-off read from an objective's text and id (SURVEY.md §2), or None.

    - Courier [seen: courier.log]: "Collect Data Probe From HUR-L1 Green Glade Station" with id
      `pickup_<guid>_0`, "Deliver Data Probe To HUR-L3 Thundering Express Station" with
      `dropoff_<guid>_0`.
    - Hauling [game text, ref: CSR, QuantumWake, SC-Game-log-Parser; unverified]: "Deliver 0/177
      SCU of Potassium to Ruin Station above Pyro VI", or "Deliver 0/12 Cargo Boxes to <place>",
      with `dropoff_<guid>_<drop index>`.
    """
    kind, index = None, None
    m = OBJECTIVE_ID_RE.match(objective_id or "")
    if m:
        kind, index = m.group(1), int(m.group(2))
    h = HAUL_RE.match(text)
    if h:
        unit = "SCU" if h.group(3).upper() == "SCU" else "boxes"
        return {"kind": kind or "dropoff", "index": index, "item": h.group(4), "commodity": h.group(4),
                "place": h.group(5).strip(), "amount": int(h.group(1)), "total": int(h.group(2)),
                "unit": unit, "shape": "hauling", "verified": False}
    c = COLLECT_RE.match(text)
    if c and kind in (None, "pickup"):
        return {"kind": "pickup", "index": index, "item": c.group(1), "commodity": None,
                "place": c.group(2).strip(), "amount": None, "total": None, "unit": None,
                "shape": "courier", "verified": True}
    d = DELIVER_RE.match(text)
    if d and kind in (None, "dropoff"):
        return {"kind": "dropoff", "index": index, "item": d.group(1), "commodity": None,
                "place": d.group(2).strip(), "amount": None, "total": None, "unit": None,
                "shape": "courier", "verified": True}
    if kind:                                  # an id says pickup or drop-off, the text says no more
        return {"kind": kind, "index": index, "item": None, "commodity": None, "place": None,
                "amount": None, "total": None, "unit": None, "shape": "id only", "verified": False}
    return None


def _is_device(j, want):
    if j.get("name", "").strip().lower() == want["name"].lower():
        return True
    return bool(j.get("guid")) and j["guid"].upper().startswith(want["guid_prefix"])


def disconnect_kind(cause, reason):
    """What a `<Channel Disconnected>` cause means [seen 2026-11, PLAN §3]."""
    r = (reason or "").lower()
    if cause == 30016 and "exittomenu" in r:
        return "menu"
    if cause == 30016:
        return "left"                              # a quit when <SystemQuit> follows, else the menu
    if cause == 30028:
        return "kicked for inactivity"
    if cause == 30013:
        return "server crash"
    return "disconnected"


def build_state(events, names=None):
    """The pure function: the state after these events, in order."""
    st = State(names)
    for ev in events:
        st.apply(ev)
    return st


def clock_facts(state, now):
    """What needs "now", which the state itself never reads. `now` is seconds since the epoch.

    Stage 3 builds its timers and alerts on this. The hangar queue counts as stuck once it has
    waited twice its estimate (PLAN §4)."""
    s = state.session
    in_game = s["in_game_s"]
    if s["game"] == "in_game" and s["in_game_since"] is not None:
        in_game += max(0.0, now - s["in_game_since"])
    q = state.hangar["queue"]
    waited = (now - q["joined"]) if q else None
    stuck = bool(q and q["wait_s"] and waited > 2 * q["wait_s"])
    return {"session_s": (now - s["start"]) if s["start"] is not None else None,
            "in_game_s": in_game,
            "hangar_waited_s": waited,
            "hangar_stuck": stuck}
