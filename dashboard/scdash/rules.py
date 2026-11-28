"""Which view to show (PLAN §11): a small table of rules, the first row that fits wins.

A pure function of the state, the plan, the user's hand pick and whether the game process is
running; it never reads the clock. `choose()` answers with the view, the rule that picked it, a
plain reason, and the *context*: a short key naming what the rule saw (this jump, this leg of
this run, this contract, this ship). A view picked by hand is kept while the context is the same
and dropped the moment it changes ("a view picked by hand stays until the context next changes",
PLAN §4): the service stores the pick with the context it was made in (`pick()`), and forgets it
when `choose()` says `pick_dropped`.

The log does not say which operator mode the seat is in, so these rows are the best signal for
the activity there is (PLAN §11). Tune them here, in `RULES`.
"""
import hashlib

from .plan import REFERENCE, VIEWS, current_run

# An open quantum target older than this, in event time, is an intention that was dropped:
# targets outnumber arrivals about 1.4 to 1 [ref, PLAN §3]. 20 minutes covers a long jump with a
# hangar queue before it [my reasoning].
STALE_TARGET_S = 20 * 60
LEG_WINDOW = 2              # how far ahead of the last leg reached an arrival may match (one skipped)


class Facts:
    """What the rules look at, read once from the state and the plan."""

    def __init__(self, state, plan, game_running):
        self.state = state
        s = state.session
        self.live = bool(game_running) and s["game"] != "ended"
        self.game = s["game"]
        self.health = state.health["status"]
        q = state.quantum
        last = s["last_t"] or 0
        self.jump = q if (q and q["closed"] is None and q["arrived"] is None
                          and last - q["selected"] <= STALE_TARGET_S) else None
        self.run = current_run(plan)
        self.progress = run_progress(state, self.run)
        loc = state.location
        self.here = state.names.place(loc["code"]) if loc and loc["left"] is None else None
        self.sell = [x for x in (plan or {}).get("sell") or []
                     if self.here and x.get("where") and _same_place(state, x["where"], self.here)]
        cs = state.current_contracts()
        self.contract = cs[0] if cs else None
        self.combat_contract = next((c for c in cs if c["view"] == "combat"), None)
        sh = state.ship
        info = state.ship_info() if sh else None
        self.ship = sh
        self.ship_info = info
        seated = bool(sh and sh["own"] and sh["aboard"] and sh["seated"] is not False)
        self.ship_job = (info or {}).get("job") if seated else None
        self.on_foot = not seated


def _same_place(state, text, place):
    n = state.names
    p = n.find_place(text)
    return p is not None and p == place


def leg_places(state, leg):
    """Every place key a plan leg can mean: its codes (from either family), its `place`, its
    `to` read as a name."""
    n = state.names
    out = set()
    for code in leg.get("codes") or []:
        p = n.place(code)
        if p:
            out.add(p)
    if leg.get("place"):
        out.add(leg["place"])
    p = n.find_place(leg.get("to"))
    if p:
        out.add(p)
    return out


def run_progress(state, run):
    """How far the session has come along the run's legs.

    Legs are reached in order: walking the places the log shows (quantum arrivals and inventory
    locations, in time), a place moves the run on when it is one of the next LEG_WINDOW legs
    after the last one reached, so a start at the run's last stop does not count as its end.
    Legs the plan marks `done` (Claude marks them after a session) are passed already.

    Returns {"reached": index or None, "at": index the user is at now or None, "heading": index
    of the leg the open quantum target goes to or None, "now": the leg shown as current, "done":
    sorted list of indices}.
    """
    out = {"reached": None, "at": None, "heading": None, "now": None, "done": []}
    if not run or not run.get("legs"):
        return out
    legs = run["legs"]
    places = [leg_places(state, g) for g in legs]
    p = max([g["index"] for g in legs if g.get("done")], default=-1)
    seen = p
    names = state.names
    for visit in state.places:
        pl = names.place(visit["code"])
        for j in range(max(seen, 0), min(len(legs), seen + 1 + LEG_WINDOW)):
            if pl in places[j]:
                seen = j
                break
    out["reached"] = seen if seen >= 0 else None
    loc = state.location
    here = names.place(loc["code"]) if loc and loc["left"] is None else None
    if seen >= 0 and here is not None and here in places[seen]:
        out["at"] = seen
    q = state.quantum
    if q and q["closed"] is None and q["arrived"] is None:
        tp = names.place(q["target"])
        for j in range(max(seen, 0), min(len(legs), seen + 1 + LEG_WINDOW)):
            if tp in places[j] and j != out["at"]:
                out["heading"] = j
                break
    if out["heading"] is not None:
        out["now"] = out["heading"]
    elif out["at"] is not None:
        out["now"] = out["at"]
    elif seen + 1 < len(legs):
        out["now"] = seen + 1
    done = {g["index"] for g in legs if g.get("done")}
    if out["now"] is not None:
        done.update(range(0, out["now"]))
    elif seen >= 0:
        done.update(range(0, seen + 1))
    out["done"] = sorted(done)
    return out


# ---------------------------------------------------------------------------- the table

def _contract_view(f):
    c = f.contract
    return c["view"] or "mission"


def _downed_view(f):
    # PLAN §11 says Now with the alert on top; the chosen mockup draws a downing in a fight on
    # the Combat view, the alert across it (design/avionics, #downed). So: Combat when a combat
    # contract is active, otherwise Now. The alert is on top either way.
    return "combat" if f.combat_contract else "now"


RULES = [
    # (rule, test, view, why)
    ("no_game", lambda f: not f.live, "idle",
     lambda f: "The game is not running"),
    ("menu", lambda f: f.game in ("menu", "not_running"), "preflight",
     lambda f: "The game is starting or at the main menu"),
    ("downed", lambda f: f.health in ("downed", "dead"), _downed_view,
     lambda f: "Downed" if f.health == "downed" else "Died"),
    ("travel", lambda f: f.jump is not None, "travel",
     lambda f: "Quantum target chosen, not arrived yet"),
    ("leg", lambda f: f.progress["at"] is not None and f.run["legs"][f.progress["at"]]["view"],
     lambda f: f.run["legs"][f.progress["at"]]["view"],
     lambda f: "At leg %d of %s: %s" % (f.progress["at"] + 1, f.run["name"], f.run["legs"][f.progress["at"]]["to"])),
    ("sell", lambda f: bool(f.sell), "selling",
     lambda f: "The plan has a sell list for this place"),
    ("contract", lambda f: f.contract is not None, _contract_view,
     lambda f: "Active contract: %s (%s)" % (f.contract["title"] or f.contract["internal"] or "untitled",
                                             f.contract["kind"] or "unknown kind")),
    ("ship", lambda f: f.ship_job in ("mining", "salvage", "cargo", "combat"), lambda f: f.ship_job,
     lambda f: "In the %s, a %s ship" % ((f.ship_info or {}).get("name") or f.ship["name"], f.ship_job)),
    ("else", lambda f: True, "now",
     lambda f: "Nothing more specific in the log"),
]


def _context(rule, f):
    """The key a hand pick is kept under: the rule and the one thing it looked at."""
    s = f.state
    if rule == "no_game":
        return "idle:%s" % s.session["id"]
    if rule == "menu":
        return "menu:%s:%s" % (s.session["id"], s.session["spawns"])
    if rule == "downed":
        return "health:%s:%s" % (f.health, s.health["t"])
    if rule == "travel":
        return "travel:%s" % f.jump["offset"]
    if rule == "leg":
        return "leg:%s:%d" % (f.run["id"], f.progress["at"])
    if rule == "sell":
        return "sell:%s" % f.here
    if rule == "contract":
        return "contract:%s" % (f.contract["mission_id"] or f.contract["title"])
    if rule == "ship":
        return "ship:%s" % (f.ship["vehicle_id"] or f.ship["name"])
    # The place alone: walking between zones of one place, or opening the storage screen, moves
    # the location's time but is no change of context (stage 3 review).
    return "now:%s" % f.here


MAX_CONTEXT = 120


def _short(ctx):
    """A context fits the user block whole (200 characters): a long one keeps its start and a
    hash of the rest, so a pick made on it still matches (stage 3 review)."""
    if len(ctx) <= MAX_CONTEXT:
        return ctx
    return "%s#%s" % (ctx[:80], hashlib.sha1(ctx.encode("utf-8", "replace")).hexdigest()[:16])


def auto(state, plan, game_running):
    """(rule, view, why, context, facts): the first row of RULES that fits."""
    f = Facts(state, plan, game_running)
    for rule, test, view, why in RULES:
        if test(f):
            v = view(f) if callable(view) else view
            if v not in VIEWS or v == REFERENCE:
                v = "now"
            return rule, v, why(f), _short(_context(rule, f)), f
    raise AssertionError("the last rule always fits")


def suggested_mode(view, f):
    """The mode the reference cards open on: mining or salvage when that is what the user is at
    (the view the rules chose, else the ship's one job), flight otherwise (PLAN §4 item 18)."""
    if view in ("mining", "salvage"):
        return view
    if f.live and f.ship_job in ("mining", "salvage"):
        return f.ship_job
    return "flight"


def choose(state, plan, pick=None, game_running=True):
    """The view to show: {"name", "rule", "why", "context", "auto", "mode", "picked",
    "pick_dropped"}. `pick` is the user's hand pick as `pick()` made it, or None.

    The reference cards are the one pick a change of context does not drop: they stay until
    the user picks Live again (the service then removes the pick). `auto` still says what the
    rules would show, so the page can go back to it."""
    rule, view, why, ctx, f = auto(state, plan, game_running)
    out = {"name": view, "rule": rule, "why": why, "context": ctx, "auto": view,
           "mode": suggested_mode(view, f), "picked": False, "pick_dropped": False}
    if pick and pick.get("view") == REFERENCE:
        out.update(name=REFERENCE, picked=True, why="The reference cards, picked by hand (the rules would show %s)" % view)
    elif pick:
        if pick.get("context") == ctx and pick.get("view") in VIEWS:
            out.update(name=pick["view"], picked=True, why="Picked by hand (until this changes: %s)" % why)
        else:
            out["pick_dropped"] = True
    return out, f


LIVE = "live"                          # the pick that ends a hand pick: back to the rules


def pick(state, plan, view, game_running=True, at=None):
    """The record the service saves in the user block when the user picks a view by hand:
    {"view", "context", "at"}. None for "live" (save no pick: the rules choose again) and for a
    name that is not a view."""
    if view == LIVE or view not in VIEWS:
        return None
    if view == REFERENCE:
        return {"view": REFERENCE, "context": REFERENCE, "at": at}
    _, _, _, ctx, _ = auto(state, plan, game_running)
    return {"view": view, "context": ctx, "at": at}
