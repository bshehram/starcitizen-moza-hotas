"""The user's plan (`data/plan.json`, PLAN §10) and what the user entered on the page.

Claude writes `data/plan.json` whole, in the routine that updates the game plan page; the
dashboard only reads it. `PlanStore.refresh()` rereads it when its size or modified time
changes. A missing or invalid file keeps the last good copy and sets a short `notice`.

Everything is bounded: the file's size, every list, every text, every number. An entry that does
not fit the shape is left out, never allowed to break the rest, and what is left out or changed on
the way is counted in the notice: entries of a list (past its cap or of the wrong shape), numbers
out of range, values a list does not allow (a status, kind, view or id), unreadable times, fields
of the wrong type, texts cut to length, a `current_run` that is no run's id. Not counted: control
and bidi characters taken out of a text, and a run id given twice, which gets a "_" added.

Times carry their offset (`2026-11-26T16:21:00-08:00`) and are read with
`datetime.fromisoformat`, converted with `astimezone()` and no argument (`words.parse_time`):
Python's `zoneinfo` has no zone data on Windows without a package (PLAN §10).

The shape, settled in stage 3 (dashboard/plan.example.json has one run of each kind):

    {"schema": 1, "updated": "<time>", "preflight": [text], "notes": [text],
     "refine_method": "Pyrometric Chromalysis",
     "objectives": [{"id", "title", "status", "next_step",
                     "materials": [{"name", "need_scu", "held_scu", "min_quality"}]}],
     "current_run": "<run id>",
     "runs": [{"id", "name", "kind", "status", "ship", "note",
               "targets": [ore name or {"ore", "min_quality", "skip_below"}],      mining
               "salvage": {"goal": {"name", "for", "need_scu", "held_scu"},        salvage
                           "next", "sell_at", "sell": [commodity], "keep": [commodity]},
               "trade": {"commodity", "scu", "buy_at", "buy_price",                cargo
                         "sell_at", "sell_price"},
               "combat": {"ship_note", "note"},                                    combat
               "legs": [{"to", "codes": [code], "place", "spot", "gm", "view", "do",
                         "arrive": [text], "refine": [ore], "leave": [ore], "method", "done"}]}],
     "timers": [{"id", "kind", "label", "location", "ready_at", "started_at"}],
     "sell": [{"what", "scu", "quality", "price", "where", "note"}]}

`run` (one object, as PLAN §10 first drew it) is read as `runs` with one entry. The current run
is `current_run`, else the first run whose status is `in_progress`, else the first not `done`.
"""
import json
import os
import re
from pathlib import Path

from .words import clean_text, day_clock, iso, parse_time

PLAN_NAME = "plan.json"
MAX_BYTES = 256 * 1024
MAX_TEXT = 300
MAX_LABEL = 80
MAX_LIST = 12
MAX_RUNS = 8
MAX_LEGS = 12
MAX_TIMERS = 20
MAX_SELL = 30
MAX_NOTES = 10
MAX_QUICK = 10                       # quick timers the user can add from the page
MAX_NUMBER = 1e9

# What a leg's `view` may name: the activity views and the two plan-led ones (PLAN §11).
LEG_VIEWS = ("mining", "salvage", "combat", "cargo", "mission", "refinery", "selling", "now")
RUN_KINDS = ("mining", "salvage", "cargo", "combat", "mission", "trade", "other")
STATUSES = ("planned", "in_progress", "done", "blocked")
TIMER_KINDS = ("refinery", "other")
VIEWS = ("now", "travel", "mining", "salvage", "combat", "cargo", "mission", "refinery", "selling",
         "preflight", "idle", "reference")
REFERENCE = "reference"              # the rig's reference cards: only a hand pick shows them (PLAN §4)
ID_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,40}$")


def _text(x, n=MAX_TEXT, cnt=None):
    """A clean, bounded text, or None. With `cnt`, what is changed on the way is counted: a value
    given that is not a text (TYPES), and a text cut to its length (CUT)."""
    if not isinstance(x, str):
        if x is not None and cnt is not None:
            cnt.skip(TYPES)
        return None
    t = clean_text(x).strip()
    if not t:
        return None
    if len(t) > n:
        if cnt is not None:
            cnt.skip(CUT)
        return t[:n]
    return t


def _texts(x, cnt=None, where="notes", n=MAX_NOTES, size=MAX_TEXT):
    """A list of clean, bounded texts (one text is a list of one). With `cnt`: the entries past
    `n` and the ones that are not a text are counted under `where`, a list that is not one under
    TYPES."""
    if x is None:
        return []
    if isinstance(x, str):
        x = [x]
    if not isinstance(x, list):
        if cnt is not None:
            cnt.skip(TYPES)
        return []
    if cnt is not None and len(x) > n:
        cnt.skip(where, len(x) - n)
    out = []
    for v in x[:n]:
        if not isinstance(v, str):
            if cnt is not None:
                cnt.skip(where)
            continue
        t = _text(v, size, cnt)
        if t:
            out.append(t)
    return out


def _num(x, lo=0.0, hi=MAX_NUMBER):
    if isinstance(x, bool) or not isinstance(x, (int, float)):
        return None
    try:
        x = float(x)                    # 10**400 is a valid JSON number and no float (review)
    except OverflowError:
        return None
    if x != x or not lo <= x <= hi:
        return None
    return x


def _val(x, cnt, lo=0.0, hi=MAX_NUMBER):
    """A number the plan gives, or None. One that is given but out of range or not a number is
    counted for the notice (it was dropped silently: stage 3 review, round 2)."""
    if x is None:
        return None
    v = _num(x, lo, hi)
    if v is None:
        cnt.skip(NUMBERS)
    return v


# The notice's names for what is not an entry of a list (stage 3 review, rounds 2 and 3: every
# value the loader drops or changes is counted, by kind).
NUMBERS = "numbers"                 # out of range or not a number
CURRENT_RUN = "current_run"         # not the id of a run
VALUES = "values"                   # a status, kind or view not in its list, an id of the wrong form
TIMES = "times"                     # a time that cannot be read
TYPES = "types"                     # a field of the wrong type (a list where text goes, ...)
CUT = "cut"                         # a text over its length, cut
KEYS = "keys"                       # a key the shape does not have (misspelled, unknown, `run` beside `runs`)

# The keys each part of a plan may have; a key that starts with "_" is a comment ("_about").
TOP_KEYS = frozenset(("schema", "updated", "preflight", "notes", "refine_method", "objectives", "runs",
                      "run", "current_run", "timers", "sell"))
RUN_KEYS = frozenset(("id", "name", "kind", "status", "ship", "note", "targets", "legs", "salvage",
                      "trade", "combat"))
LEG_KEYS = frozenset(("to", "codes", "place", "spot", "gm", "view", "do", "arrive", "refine", "leave",
                      "method", "done"))
TARGET_KEYS = frozenset(("ore", "min_quality", "skip_below"))
OBJECTIVE_KEYS = frozenset(("id", "title", "status", "next_step", "materials"))
MATERIAL_KEYS = frozenset(("name", "need_scu", "held_scu", "min_quality", "unit"))
TIMER_KEYS = frozenset(("id", "kind", "label", "location", "ready_at", "started_at"))
SELL_KEYS = frozenset(("what", "ore", "scu", "quality", "price", "where", "note"))


def _extra(d, allowed, cnt):
    """Count the keys of `d` the shape does not have ("GM" for "gm", a misspelled field): each
    is left out, and was silently (stage 3 review, round 4)."""
    n = sum(1 for k in d if k not in allowed and not (isinstance(k, str) and k.startswith("_")))
    if n:
        cnt.skip(KEYS, n)


def _ident(x, fallback, cnt=None):
    if isinstance(x, str) and ID_RE.match(x):
        return x
    if x is not None and cnt is not None:
        cnt.skip(VALUES)
    return fallback


def _choice(x, allowed, default, cnt):
    """`x` when it is one of `allowed`, else `default`; one given and not allowed is counted."""
    if x is None:
        return default
    if isinstance(x, str) and x in allowed:
        return x
    cnt.skip(VALUES)
    return default


def _time(x, cnt):
    """A time the plan gives (words.parse_time), or None; one given and unreadable is counted."""
    if x is None:
        return None
    if not isinstance(x, str):
        cnt.skip(TYPES)
        return None
    t = parse_time(x)
    if t is None:
        cnt.skip(TIMES)
    return t


def _items(x, cnt, where, n):
    """The first `n` entries of a list the plan gives; the rest are counted under `where`, and a
    value that is not a list under TYPES."""
    if x is None:
        return []
    if not isinstance(x, list):
        cnt.skip(TYPES)
        return []
    if len(x) > n:
        cnt.skip(where, len(x) - n)
    return x[:n]


class _Count:
    def __init__(self):
        self.skipped = {}

    def skip(self, where, n=1):
        self.skipped[where] = self.skipped.get(where, 0) + n


def _material(m, cnt):
    if not isinstance(m, dict) or not _text(m.get("name"), MAX_LABEL):
        cnt.skip("materials")
        return None
    _extra(m, MATERIAL_KEYS, cnt)
    return {"name": _text(m["name"], MAX_LABEL, cnt), "need_scu": _val(m.get("need_scu"), cnt),
            "held_scu": _val(m.get("held_scu"), cnt), "min_quality": _val(m.get("min_quality"), cnt, 0, 1000),
            "unit": _text(m.get("unit"), 12, cnt) or "SCU"}


def _objective(o, i, cnt):
    if not isinstance(o, dict) or not _text(o.get("title")):
        cnt.skip("objectives")
        return None
    _extra(o, OBJECTIVE_KEYS, cnt)
    status = _choice(o.get("status"), STATUSES, "planned", cnt)
    mats = [x for x in (_material(m, cnt) for m in _items(o.get("materials"), cnt, "materials", MAX_LIST)) if x]
    return {"id": _ident(o.get("id"), "o%d" % (i + 1), cnt), "title": _text(o["title"], MAX_TEXT, cnt),
            "status": status, "next_step": _text(o.get("next_step"), MAX_TEXT, cnt), "materials": mats}


def _codes(x, cnt=None):
    """Location codes: no spaces, at most 8. With `cnt`, each one left out is counted."""
    if x is None:
        return []
    if isinstance(x, str):
        x = [x]
    if not isinstance(x, list):
        if cnt is not None:
            cnt.skip(TYPES)
        return []
    if cnt is not None and len(x) > 8:
        cnt.skip("codes", len(x) - 8)
    out = []
    for v in x[:8]:
        c = _text(v, 80) if isinstance(v, str) else None
        if c and " " not in c and len(v.strip()) <= 80:
            out.append(c)
        elif cnt is not None:               # an empty code too (round 4)
            cnt.skip("codes")
    return out


def _leg(g, i, cnt):
    if not isinstance(g, dict) or not (_text(g.get("to")) or _codes(g.get("codes"))):
        cnt.skip("legs")
        return None
    _extra(g, LEG_KEYS, cnt)
    codes = _codes(g.get("codes"), cnt)
    if "done" in g and g["done"] is not None and not isinstance(g["done"], bool):
        cnt.skip(TYPES)
    return {"index": i, "to": _text(g.get("to"), MAX_TEXT, cnt) or codes[0],
            "codes": codes, "place": _text(g.get("place"), 80, cnt),
            "spot": _text(g.get("spot"), 80, cnt), "gm": _val(g.get("gm"), cnt, 0, 1e6),
            "view": _choice(g.get("view"), LEG_VIEWS, None, cnt),
            "do": _text(g.get("do"), MAX_TEXT, cnt), "arrive": _texts(g.get("arrive"), cnt, "arrive", 6),
            "refine": _texts(g.get("refine"), cnt, "refine", 8, MAX_LABEL),
            "leave": _texts(g.get("leave"), cnt, "leave", 8, MAX_LABEL),
            "method": _text(g.get("method"), MAX_LABEL, cnt), "done": g.get("done") is True}


def _target(t, cnt):
    if isinstance(t, str):
        t = {"ore": t}
    if not isinstance(t, dict) or not _text(t.get("ore"), MAX_LABEL):
        cnt.skip("targets")
        return None
    _extra(t, TARGET_KEYS, cnt)
    return {"ore": _text(t["ore"], MAX_LABEL, cnt), "min_quality": _val(t.get("min_quality"), cnt, 0, 1000),
            "skip_below": _val(t.get("skip_below"), cnt, 0, 1000)}


def _block(d, fields, cnt, where="block"):
    """A run's activity block: only the named fields, each as text, number or list of texts."""
    if d is None:
        return None
    if not isinstance(d, dict):
        cnt.skip(TYPES)
        return None
    _extra(d, fields, cnt)
    out = {}
    for name, kind in fields.items():
        v = d.get(name)
        if kind == "text":
            out[name] = _text(v, MAX_TEXT, cnt)
        elif kind == "num":
            out[name] = _val(v, cnt)
        elif kind == "texts":
            out[name] = _texts(v, cnt, name, 8, MAX_LABEL)
        elif isinstance(kind, dict):
            out[name] = _block(v, kind, cnt, name)
    return out


SALVAGE = {"goal": {"name": "text", "for": "text", "need_scu": "num", "held_scu": "num"},
           "next": "text", "sell_at": "text", "sell": "texts", "keep": "texts"}
TRADE = {"commodity": "text", "scu": "num", "buy_at": "text", "buy_price": "num",
         "sell_at": "text", "sell_price": "num"}
COMBAT = {"ship_note": "text", "note": "text"}


def _run(r, i, cnt):
    if not isinstance(r, dict) or not _text(r.get("name"), MAX_LABEL):
        cnt.skip("runs")
        return None
    _extra(r, RUN_KEYS, cnt)
    legs = [x for x in (_leg(g, j, cnt) for j, g in enumerate(_items(r.get("legs"), cnt, "legs", MAX_LEGS))) if x]
    for j, g in enumerate(legs):
        g["index"] = j
    targets = [x for x in (_target(t, cnt) for t in _items(r.get("targets"), cnt, "targets", 6)) if x]
    return {"id": _ident(r.get("id"), "run%d" % (i + 1), cnt), "name": _text(r["name"], MAX_LABEL, cnt),
            "kind": _choice(r.get("kind"), RUN_KINDS, "mining" if targets else "other", cnt),
            "status": _choice(r.get("status"), STATUSES, "planned", cnt),
            "ship": _text(r.get("ship"), MAX_LABEL, cnt), "note": _text(r.get("note"), MAX_TEXT, cnt),
            "targets": targets, "legs": legs,
            "salvage": _block(r.get("salvage"), SALVAGE, cnt), "trade": _block(r.get("trade"), TRADE, cnt),
            "combat": _block(r.get("combat"), COMBAT, cnt)}


def _timer(t, i, cnt):
    ready = parse_time(t.get("ready_at")) if isinstance(t, dict) else None
    if ready is None or not _text(t.get("label"), MAX_LABEL):
        cnt.skip("timers")
        return None
    _extra(t, TIMER_KEYS, cnt)
    return {"id": _ident(t.get("id"), "t%d" % (i + 1), cnt),
            "kind": _choice(t.get("kind"), TIMER_KINDS, "other", cnt),
            "label": _text(t["label"], MAX_LABEL, cnt), "location": _text(t.get("location"), MAX_LABEL, cnt),
            "ready_t": ready, "started_t": _time(t.get("started_at"), cnt)}


def _sell(s, cnt):
    if not isinstance(s, dict) or not _text(s.get("what") or s.get("ore"), MAX_LABEL):
        cnt.skip("sell")
        return None
    _extra(s, SELL_KEYS, cnt)
    return {"what": _text(s.get("what") or s.get("ore"), MAX_LABEL, cnt), "scu": _val(s.get("scu"), cnt),
            "quality": _val(s.get("quality"), cnt, 0, 1000), "price": _val(s.get("price"), cnt),
            "where": _text(s.get("where"), MAX_LABEL, cnt), "note": _text(s.get("note"), MAX_TEXT, cnt)}


def normalize(raw):
    """(plan, skipped): the plan in its settled shape, and {what: how many} of what was left out
    or changed on the way (a list's name for its entries, or one of NUMBERS, CURRENT_RUN, VALUES,
    TIMES, TYPES, CUT)."""
    if not isinstance(raw, dict):
        raise ValueError("not a JSON object")
    cnt = _Count()

    def items(name, n):
        return _items(raw.get(name), cnt, name, n)

    _extra(raw, TOP_KEYS, cnt)
    if raw.get("schema", 1) != 1:
        cnt.skip(VALUES)                 # a schema this loader does not know: read as the first
    runs_raw = items("runs", MAX_RUNS)
    if not runs_raw and isinstance(raw.get("run"), dict):
        runs_raw = [raw["run"]]
    elif "run" in raw:
        cnt.skip(KEYS)                   # `run` beside `runs`, or not an object: left out
    runs = [x for x in (_run(r, i, cnt) for i, r in enumerate(runs_raw)) if x]
    ids = set()
    for r in runs:                       # ids must be unique, or a hand pick could jump runs
        while r["id"] in ids:
            r["id"] += "_"
        ids.add(r["id"])
    cur = raw.get("current_run")
    if cur is not None and not (isinstance(cur, str) and cur in ids):
        cnt.skip(CURRENT_RUN)
    plan = {
        "schema": 1,
        "updated": _text(raw.get("updated"), 40),
        "updated_t": _time(raw.get("updated"), cnt),
        "preflight": _texts(raw.get("preflight"), cnt, "preflight"),
        "notes": _texts(raw.get("notes"), cnt, "notes"),
        "refine_method": _text(raw.get("refine_method"), MAX_LABEL, cnt),
        "objectives": [x for x in (_objective(o, i, cnt) for i, o in enumerate(items("objectives", MAX_LIST))) if x],
        "runs": runs,
        "current_run": raw["current_run"] if isinstance(raw.get("current_run"), str) and raw["current_run"] in ids else None,
        "timers": [x for x in (_timer(t, i, cnt) for i, t in enumerate(items("timers", MAX_TIMERS))) if x],
        "sell": [x for x in (_sell(s, cnt) for s in items("sell", MAX_SELL)) if x],
    }
    return plan, cnt.skipped


_KINDS_WORDED = {
    NUMBERS: ("number", "numbers", "out of range or not a number"),
    VALUES: ("value", "values", "a status, kind, view or id the shape does not allow"),
    TIMES: ("time", "times", "not readable"),
    TYPES: ("field", "fields", "of the wrong type"),
    CUT: ("text", "texts", "cut to length"),
    KEYS: ("key", "keys", "not in the plan's shape"),
}


def left_out(skipped):
    """'1 entry in legs, 2 numbers (out of range or not a number), current_run (not a run id)'."""
    parts = []
    for k, n in sorted(skipped.items()):
        if k in _KINDS_WORDED:
            one, many, why = _KINDS_WORDED[k]
            parts.append("%d %s (%s)" % (n, one if n == 1 else many, why))
        elif k == CURRENT_RUN:
            parts.append("current_run (not a run id)")
        else:
            parts.append("%d entr%s in %s" % (n, "y" if n == 1 else "ies", k))
    return ", ".join(parts)


def current_run(plan):
    """The run the plan is on: `current_run`, else the first in progress, else the first not done."""
    if not plan or not plan.get("runs"):
        return None
    runs = plan["runs"]
    if plan.get("current_run"):
        r = next((r for r in runs if r["id"] == plan["current_run"]), None)
        if r is not None:
            return r
    return next((r for r in runs if r["status"] == "in_progress"), None) or \
        next((r for r in runs if r["status"] != "done"), None)


def current_objective(plan):
    if not plan or not plan.get("objectives"):
        return None
    objs = plan["objectives"]
    return next((o for o in objs if o["status"] == "in_progress"), None) or \
        next((o for o in objs if o["status"] != "done"), None)


class PlanStore:
    """`data/plan.json`, reread when it changes. `.plan` is the last good copy (None before the
    first), `.notice` a short text when something is wrong (None when all is well)."""

    def __init__(self, path):
        self.path = Path(path)
        self.plan = None
        self.notice = None
        self._sig = False                # not looked yet (None means: no file)

    def refresh(self):
        """Look at the file; reread it when its size or modified time changed. Returns True when
        the plan or the notice changed. Never raises: an unreadable file is a notice."""
        before = (self.plan, self.notice)
        try:
            st = os.stat(self.path)
            sig = (st.st_size, st.st_mtime_ns)
        except FileNotFoundError:
            sig = None
        except OSError as e:
            # Not recorded: the next look tries again (a file held open a moment must not leave
            # "cannot be read now" until the file next changes: stage 3 review).
            self._sig = False
            self._problem("%s cannot be read now (%s)" % (PLAN_NAME, e.__class__.__name__))
            return (self.plan, self.notice) != before
        if sig == self._sig:
            return False
        if sig is None:
            self._sig = sig
            self._problem("there is no %s yet" % PLAN_NAME if self.plan is None else "%s is gone" % PLAN_NAME)
        elif sig[0] > MAX_BYTES:
            self._sig = sig
            self._problem("%s is larger than %d KB" % (PLAN_NAME, MAX_BYTES // 1024))
        else:
            # The file's signature is recorded only once its content has been judged, good or
            # bad; a read that failed is tried again on the next look.
            self._sig = sig if self._read() else False
        return (self.plan, self.notice) != before

    def _read(self):
        """Read and judge the file. False when it could not be read (try again), True when its
        content was judged, whether it was taken or refused."""
        try:
            with open(self.path, "rb") as f:
                data = f.read(MAX_BYTES + 1)
        except OSError as e:
            self._problem("%s cannot be read now (%s)" % (PLAN_NAME, e.__class__.__name__))
            return False
        if len(data) > MAX_BYTES:
            self._problem("%s is larger than %d KB" % (PLAN_NAME, MAX_BYTES // 1024))
            return True
        try:
            raw = json.loads(data.decode("utf-8-sig"))
        except UnicodeDecodeError:
            self._problem("%s is not UTF-8 text" % PLAN_NAME)
            return True
        except RecursionError:
            self._problem("%s is nested too deeply" % PLAN_NAME)
            return True
        except ValueError as e:
            line = getattr(e, "lineno", None)
            self._problem("%s is not valid JSON%s" % (PLAN_NAME, " (line %d)" % line if line else ""))
            return True
        try:
            plan, skipped = normalize(raw)
        except ValueError:
            self._problem("%s is not a JSON object" % PLAN_NAME)
            return True
        except Exception as e:                     # noqa: BLE001 - a shape we did not think of
            self._problem("%s could not be read into a plan (%s)" % (PLAN_NAME, e.__class__.__name__))
            return True
        self.plan = plan
        if skipped:
            self.notice = _text("%s: left out because they do not fit the shape: %s" % (PLAN_NAME, left_out(skipped)))
        else:
            self.notice = None
        return True

    def _problem(self, what):
        # The time is worded in this computer's zone (the notice is made when the file is read,
        # not per page): STATE.md says so.
        if self.plan is not None:
            when = self.plan.get("updated_t")
            what += "; showing the last good copy%s" % (" (updated %s)" % day_clock(when) if when else "")
        self.notice = _text(what)


# ---------------------------------------------------------------------------- the user block

def quick_timer(label, minutes, now, taken=()):
    """A quick timer the user adds from the page (the service saves it in the `user` block of
    data/state.json, PLAN §7: that file is its only record). None for a bad label or length.
    Its id is unique among `taken` (two added in one millisecond shared one: stage 3 review)."""
    label = _text(label, 60)
    m = _num(minutes, 0.5, 24 * 60)
    if not label or m is None:
        return None
    base = "q%d" % int(now * 1000)
    tid, k = base, 1
    while tid in taken:
        k += 1
        tid = "%s-%d" % (base, k)
    return {"id": tid, "label": label, "added_at": iso(now), "ready_at": iso(now + m * 60)}


def clean_user(user):
    """The `user` block as stage 3 reads it: {"timers": [quick timer], "view": hand pick or None}.
    Whatever else is in it is kept by the service and ignored here."""
    out = {"timers": [], "view": None}
    if not isinstance(user, dict):
        return out
    raw = user.get("timers") if isinstance(user.get("timers"), list) else []
    for q in raw[-5 * MAX_QUICK:]:                 # the newest are at the end; look at a bounded tail
        if not isinstance(q, dict):
            continue
        ready = parse_time(q.get("ready_at"))
        label = _text(q.get("label"), 60)
        if ready is None or not label:
            continue
        out["timers"].append({"id": _ident(q.get("id"), "q%d" % len(out["timers"])), "label": label,
                              "ready_t": ready, "added_t": parse_time(q.get("added_at"))})
    seen = set()
    for q in out["timers"]:                        # ids unique, whatever an older block holds
        tid, k = q["id"], 1
        while tid in seen:
            k += 1
            tid = "%s-%d" % (q["id"], k)
        q["id"] = tid
        seen.add(tid)
    out["timers"] = out["timers"][-MAX_QUICK:]
    v = user.get("view")
    if isinstance(v, dict) and v.get("view") in VIEWS and isinstance(v.get("context"), str) \
            and len(v["context"]) <= 200:
        out["view"] = {"view": v["view"], "context": v["context"], "at": _text(v.get("at"), 40)}
    return out
