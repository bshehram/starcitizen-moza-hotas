"""The user's plan (`data/plan.json`, PLAN §10) and what the user entered on the page.

Claude writes `data/plan.json` whole, in the routine that updates the game plan page; the
dashboard only reads it. `PlanStore.refresh()` rereads it when its size or modified time
changes. A missing or invalid file keeps the last good copy and sets a short `notice`.

Everything is bounded: the file's size, every list, every text, every number. An entry that does
not fit the shape is left out (and counted in the notice), never allowed to break the rest.

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


def _text(x, n=MAX_TEXT):
    """A clean, bounded text, or None."""
    if not isinstance(x, str):
        return None
    t = clean_text(x).strip()
    return t[:n] if t else None


def _texts(x, n=MAX_NOTES, size=MAX_TEXT):
    if isinstance(x, str):
        x = [x]
    if not isinstance(x, list):
        return []
    return [t for t in (_text(v, size) for v in x[:n]) if t]


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


NUMBERS = "numbers"                 # the notice's names for what is not an entry of a list
CURRENT_RUN = "current_run"


def _ident(x, fallback):
    if isinstance(x, str) and ID_RE.match(x):
        return x
    return fallback


class _Count:
    def __init__(self):
        self.skipped = {}

    def skip(self, where):
        self.skipped[where] = self.skipped.get(where, 0) + 1


def _material(m, cnt):
    if not isinstance(m, dict) or not _text(m.get("name"), MAX_LABEL):
        cnt.skip("materials")
        return None
    return {"name": _text(m["name"], MAX_LABEL), "need_scu": _val(m.get("need_scu"), cnt),
            "held_scu": _val(m.get("held_scu"), cnt), "min_quality": _val(m.get("min_quality"), cnt, 0, 1000),
            "unit": _text(m.get("unit"), 12) or "SCU"}


def _objective(o, i, cnt):
    if not isinstance(o, dict) or not _text(o.get("title")):
        cnt.skip("objectives")
        return None
    status = o.get("status") if o.get("status") in STATUSES else "planned"
    mats = [x for x in (_material(m, cnt) for m in (o.get("materials") or [])[:MAX_LIST]) if x] \
        if isinstance(o.get("materials"), list) else []
    return {"id": _ident(o.get("id"), "o%d" % (i + 1)), "title": _text(o["title"]), "status": status,
            "next_step": _text(o.get("next_step")), "materials": mats}


def _codes(x):
    if isinstance(x, str):
        x = [x]
    if not isinstance(x, list):
        return []
    return [c for c in (_text(v, 80) for v in x[:8]) if c and " " not in c]


def _leg(g, i, cnt):
    if not isinstance(g, dict) or not (_text(g.get("to")) or _codes(g.get("codes"))):
        cnt.skip("legs")
        return None
    view = g.get("view") if g.get("view") in LEG_VIEWS else None
    return {"index": i, "to": _text(g.get("to")) or _codes(g.get("codes"))[0],
            "codes": _codes(g.get("codes")), "place": _text(g.get("place"), 80),
            "spot": _text(g.get("spot"), 80), "gm": _val(g.get("gm"), cnt, 0, 1e6), "view": view,
            "do": _text(g.get("do")), "arrive": _texts(g.get("arrive"), 6),
            "refine": _texts(g.get("refine"), 8, MAX_LABEL), "leave": _texts(g.get("leave"), 8, MAX_LABEL),
            "method": _text(g.get("method"), MAX_LABEL), "done": g.get("done") is True}


def _target(t, cnt):
    if isinstance(t, str):
        t = {"ore": t}
    if not isinstance(t, dict) or not _text(t.get("ore"), MAX_LABEL):
        cnt.skip("targets")
        return None
    return {"ore": _text(t["ore"], MAX_LABEL), "min_quality": _val(t.get("min_quality"), cnt, 0, 1000),
            "skip_below": _val(t.get("skip_below"), cnt, 0, 1000)}


def _block(d, fields, cnt):
    """A run's activity block: only the named fields, each as text, number or list of texts."""
    if not isinstance(d, dict):
        return None
    out = {}
    for name, kind in fields.items():
        v = d.get(name)
        if kind == "text":
            out[name] = _text(v)
        elif kind == "num":
            out[name] = _val(v, cnt)
        elif kind == "texts":
            out[name] = _texts(v, 8, MAX_LABEL)
        elif isinstance(kind, dict):
            out[name] = _block(v, kind, cnt)
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
    legs = [x for x in (_leg(g, j, cnt) for j, g in enumerate((r.get("legs") or [])[:MAX_LEGS])) if x] \
        if isinstance(r.get("legs"), list) else []
    for j, g in enumerate(legs):
        g["index"] = j
    targets = [x for x in (_target(t, cnt) for t in (r.get("targets") or [])[:6]) if x] \
        if isinstance(r.get("targets"), list) else []
    return {"id": _ident(r.get("id"), "run%d" % (i + 1)), "name": _text(r["name"], MAX_LABEL),
            "kind": r.get("kind") if r.get("kind") in RUN_KINDS else ("mining" if targets else "other"),
            "status": r.get("status") if r.get("status") in STATUSES else "planned",
            "ship": _text(r.get("ship"), MAX_LABEL), "note": _text(r.get("note")),
            "targets": targets, "legs": legs,
            "salvage": _block(r.get("salvage"), SALVAGE, cnt), "trade": _block(r.get("trade"), TRADE, cnt),
            "combat": _block(r.get("combat"), COMBAT, cnt)}


def _timer(t, i, cnt):
    ready = parse_time(t.get("ready_at")) if isinstance(t, dict) else None
    if ready is None or not _text(t.get("label"), MAX_LABEL):
        cnt.skip("timers")
        return None
    return {"id": _ident(t.get("id"), "t%d" % (i + 1)),
            "kind": t.get("kind") if t.get("kind") in TIMER_KINDS else "other",
            "label": _text(t["label"], MAX_LABEL), "location": _text(t.get("location"), MAX_LABEL),
            "ready_t": ready, "started_t": parse_time(t.get("started_at"))}


def _sell(s, cnt):
    if not isinstance(s, dict) or not _text(s.get("what") or s.get("ore"), MAX_LABEL):
        cnt.skip("sell")
        return None
    return {"what": _text(s.get("what") or s.get("ore"), MAX_LABEL), "scu": _val(s.get("scu"), cnt),
            "quality": _val(s.get("quality"), cnt, 0, 1000), "price": _val(s.get("price"), cnt),
            "where": _text(s.get("where"), MAX_LABEL), "note": _text(s.get("note"))}


def normalize(raw):
    """(plan, skipped): the plan in its settled shape, and {list name: entries left out}."""
    if not isinstance(raw, dict):
        raise ValueError("not a JSON object")
    cnt = _Count()

    def items(name, n):
        v = raw.get(name)
        if v is None:
            return []
        if not isinstance(v, list):
            cnt.skip(name)
            return []
        if len(v) > n:
            cnt.skipped[name] = cnt.skipped.get(name, 0) + len(v) - n
        return v[:n]

    runs_raw = items("runs", MAX_RUNS)
    if not runs_raw and isinstance(raw.get("run"), dict):
        runs_raw = [raw["run"]]
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
        "updated_t": parse_time(raw.get("updated")),
        "preflight": _texts(raw.get("preflight")),
        "notes": _texts(raw.get("notes")),
        "refine_method": _text(raw.get("refine_method"), MAX_LABEL),
        "objectives": [x for x in (_objective(o, i, cnt) for i, o in enumerate(items("objectives", MAX_LIST))) if x],
        "runs": runs,
        "current_run": raw["current_run"] if isinstance(raw.get("current_run"), str) and raw["current_run"] in ids else None,
        "timers": [x for x in (_timer(t, i, cnt) for i, t in enumerate(items("timers", MAX_TIMERS))) if x],
        "sell": [x for x in (_sell(s, cnt) for s in items("sell", MAX_SELL)) if x],
    }
    return plan, cnt.skipped


def left_out(skipped):
    """'1 entry in legs, 2 numbers (out of range or not a number), current_run (not a run id)'."""
    parts = []
    for k, n in sorted(skipped.items()):
        if k == NUMBERS:
            parts.append("%d number%s (out of range or not a number)" % (n, "" if n == 1 else "s"))
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
