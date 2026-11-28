"""One ready-to-draw model per view (PLAN §4, §11; the screens of design/avionics/index.html).

Each model holds exactly what its screen shows, already worded and in display units: local
times, American month-first dates, plain numbers with thousands commas. The page only places
them. Countdowns and clocks come as `*_ms` epoch milliseconds for the page's one-second timer,
so a model does not change every second (the service sends only what changed, PLAN §9).

Nothing here shows what the log cannot know (PLAN §3): no gauge for cargo aboard, salvage
amounts, shields or hull. Held amounts come from the plan and say "as of" its `updated` time.
Prices come from data/reference/prices.json when it exists, always with their date.

Every function takes a `Ctx` (below) and returns a dict. dashboard/STATE.md describes each key.
"""
from . import config
from . import plan as planlib
from .alerts import earned, preflight_alert, when
from .names import norm
from .rules import leg_places
from .words import hours_minutes, money, number, scu, ship_class, signed_percent, week_day

MAX_OBJS = 8                # objectives shown in a contract block (the mockup was drawn for 2 to 5)
MAX_OTHERS = 4
UNVERIFIED = {
    "hauling": "Hauling drop-offs are read from the objective text the game has for them; no "
               "haul is in the project's record of the user's logs yet.",
    "kills": "Ships you destroyed are counted from the killer's id on the destroyed line; no "
             "kill by the user is in the project's record yet.",
    "sell_scu": "A commodity sale's quantity is read as SCU; the log does not print the unit.",
}


class Ctx:
    """What every model may read: the state, the plan, the rule facts, the reference tables,
    `now` and the time zone (None: this computer's), and the timers already built."""

    def __init__(self, state, plan, facts, now, tz=None, timers=None):
        self.state = state
        self.plan = plan
        self.f = facts
        self.ref = state.ref
        self.names = state.names
        self.now = now
        self.tz = tz
        self.timers = timers or []
        self.run = facts.run
        self.progress = facts.progress

    def when(self, t):
        return when(t, self.now, self.tz)

    def ms(self, t):
        return int(round(t * 1000)) if t is not None else None


# ---------------------------------------------------------------------------- shared blocks

def place_words(ctx, code):
    if not code:
        return None
    n = ctx.names
    return {"code": code, "name": n.name(code), "short": n.short(code), "body": n.entry(code).get("body")}


def controls(ctx, mode):
    """The controls strip for an operator mode (controls.json, from the card tables)."""
    c = ctx.ref.controls(mode)
    if not c:
        return None
    title = c["title"] + (" · %s" % c["knob"] if c.get("knob") else "")
    return {"mode": mode, "title": title,
            "items": [{"where": i["where"], "what": i["what"], "status": i["status"]} for i in c["items"]]}


def _objective_order(objs):
    """Pickups before drop-offs (the courier announces the drop-off first [seen]), each by its
    drop index, everything else in the order announced."""
    def key(io):
        i, o = io
        st = o.get("stop") or {}
        rank = {"pickup": 0, "dropoff": 1}.get(st.get("kind"), 0)
        return (rank, st.get("index") if st.get("index") is not None else 99, i)
    return [o for _, o in sorted(enumerate(objs), key=key)]


def current_objective(c):
    """The objective in large type: for a run of stops, the first open pickup, else the first open
    drop-off; otherwise the newest one still open (as the state's `objective`)."""
    objs = c["objectives"]
    live = [o for o in objs if o["state"] == "active"]
    if not live:
        return None
    stops = [o for o in _objective_order(live) if o.get("stop")]
    if stops:
        return stops[0]
    return live[-1]


def contract_block(ctx, c, compact=False):
    """A contract as every view draws it: giver, reward (only when the log printed one), title,
    the objectives as a checklist with the current one marked, "Objective k of n"."""
    if c is None:
        return None
    cur = current_objective(c)
    shown = [o for o in _objective_order(c["objectives"]) if o["state"] != "withdrawn"]
    items, k = [], None
    nxt = False
    for o in shown:
        if o is cur:
            st = "now"
            k = len(items) + 1
            nxt = True
        elif o["state"] == "complete":
            st = "done"
        elif o["state"] == "failed":
            st = "failed"
        elif nxt:
            st, nxt = "next", False
        else:
            st = "later"
        stop = o.get("stop") or None
        items.append({"text": o["text"], "state": st, "optional": bool(o.get("optional")),
                      "stop": _stop_words(stop) if stop else None})
    # A window that always holds the current row, with what is cut on each side counted (the
    # first form cut the list before counting, and could cut the current row: stage 3 review).
    limit = 3 if compact else MAX_OBJS
    n = len(items)
    start = 0
    if n > limit:
        at = (k - 1) if k else 0
        start = max(0, min(at - (limit - 1) // 2, n - limit))
    shown_items = items[start:start + limit]
    return {"id": c["mission_id"] or ("title:" + (c["title"] or "")),
            "title": c["title"] or c["internal"] or "Untitled contract",
            "giver": c["giver_name"], "kind": c["kind"], "kind_name": c["type_name"] or (c["kind"] or "").capitalize() or None,
            "view": c["view"], "setting": c["setting"], "status": c["status"],
            "reward": money(c["reward"]) if c.get("reward") is not None else None,
            "objectives": shown_items, "before": start, "after": max(0, n - start - limit),
            "more": n - len(shown_items),
            "count": "Objective %d of %d" % (k, len(shown)) if k and len(shown) > 1 else None,
            "current": cur["text"] if cur else None,
            "unmapped": c["unmapped"]}


def _stop_words(st):
    amount = None
    if st.get("total") is not None:
        amount = "%s/%s %s" % (number(st["amount"]), number(st["total"]), st["unit"])
    return {"kind": st["kind"], "index": st.get("index"), "item": st.get("item"), "place": st.get("place"),
            "amount": amount, "verified": st.get("verified")}


def law_block(ctx):
    z = ctx.state.zone
    marks = []
    if z.get("monitored_down"):
        marks.append({"on": False, "icon": "eye", "text": "Monitored space down"})
    elif z.get("monitored") is not None:
        marks.append({"on": bool(z["monitored"]), "icon": "eye",
                      "text": "Monitored space" if z["monitored"] else "Not monitored"})
    if z.get("armistice") is not None:
        marks.append({"on": bool(z["armistice"]), "icon": "noshield",
                      "text": "Armistice zone: combat prohibited" if z["armistice"] else "No armistice: weapons free"})
    return {"jurisdiction": "%s jurisdiction" % z["jurisdiction"] if z.get("jurisdiction") else None,
            "marks": marks}


def materials_block(ctx, names_wanted=None):
    """Needed against held, from the plan's current objective (held is only as fresh as the
    plan's `updated`, PLAN §10)."""
    plan = ctx.plan
    obj = planlib.current_objective(plan)
    if not obj or not obj["materials"]:
        return None
    want = {norm(n) for n in names_wanted} if names_wanted else None
    items = []
    for m in obj["materials"]:
        if want is not None and norm(m["name"]) not in want:
            continue
        need, held = m["need_scu"], m["held_scu"]
        fill = (min(1.0, held / need) if need else None) if held is not None else None
        ok = held is not None and need is not None and held >= need
        short = round(need - held, 2) if (need is not None and held is not None and not ok) else None
        items.append({"name": m["name"], "held": scu(held), "need": scu(need), "unit": m["unit"],
                      "fill": round(fill, 3) if fill is not None else None, "ok": ok,
                      "short": scu(short), "note": "Covered" if ok else ("%s to go" % scu(short) if short else None),
                      "min_quality": number(m["min_quality"]) if m["min_quality"] is not None else None,
                      "_short": short})
    if not items:
        return None
    worst = max((x for x in items if x["_short"]), key=lambda x: x["_short"], default=None)
    for x in items:
        del x["_short"]
    t = plan.get("updated_t")
    return {"asof": "held as of %s" % ctx.when(t) if t else "held as the plan says (no update time)",
            "items": items,
            "first": "%s first: it is %s SCU short." % (worst["name"], worst["short"]) if worst else None}


def soonest_timer(ctx, where=None):
    for t in ctx.timers:
        if t["state"] == "running" and (where is None or t["where"] == where):
            return t
    return None


def _ship_name(ctx):
    sh = ctx.state.ship
    if not sh:
        return None
    info = ctx.f.ship_info or {}
    return info.get("name") or sh["name"] or ship_class(sh["class"])


def strip(ctx, view):
    """The status strip's words for this moment (the page adds the clock and counts up the
    session from `session_since_ms`)."""
    st = ctx.state
    s = st.session
    f = ctx.f
    if not f.live:
        state, tone = "No game running", "off"
    elif view == "preflight" and st.preflight.get("ok") is False:
        state, tone = "Preflight failed", "bad"
    elif st.health["status"] == "downed":
        state, tone = "Downed", "bad"
    elif st.health["status"] == "dead":
        state, tone = "Dead", "bad"
    elif f.jump is not None:
        # The log has the target and the arrival, not the moment the drive spools: honest words.
        state, tone = "Quantum travel", "quantum"
    elif s["game"] == "menu":
        state, tone = "Main menu", "live"
    elif s["game"] == "not_running":
        state, tone = "Game starting", "live"
    else:
        state, tone = "In game", "live"
    if f.live and s["start"] is not None:
        session = {"label": "Session", "since_ms": ctx.ms(s["start"]), "text": None}
    elif s["start"] is not None:
        session = {"label": "Last played", "since_ms": None, "text": week_day(s["start"], ctx.tz)}
    else:
        session = {"label": "Session", "since_ms": None, "text": "none yet"}
    if f.jump is not None:
        where = {"icon": "jump", "text": "To %s" % ctx.names.short(f.jump["target"])}
    elif s["game"] == "menu" and f.live:
        where = {"icon": "pin", "text": "Main menu"}
    elif st.location:
        loc = st.location
        name = ctx.names.name(loc["code"])
        where = {"icon": "pin", "text": name if loc["left"] is None else "Left %s" % ctx.names.short(loc["code"])}
    elif st.body:
        where = {"icon": "pin", "text": "Near %s" % ctx.names.name(st.body["name"])}
    else:
        where = {"icon": "pin", "text": None}
    name = _ship_name(ctx)
    sh = st.ship
    if f.live and s["game"] == "in_game" and (not sh or not sh["aboard"] or sh["seated"] is False):
        ship = {"icon": "walk", "text": "On foot"}       # out of the seat: the log says no more
    elif name and sh and sh["aboard"]:
        ship = {"icon": "ship", "text": name}
    elif name:
        ship = {"icon": "ship", "text": name}
    else:
        ship = {"icon": "ship", "text": "No ship"}
    return {"state": state, "tone": tone, "session": session, "where": where, "ship": ship}


# ---------------------------------------------------------------------------- the views

def now_view(ctx):
    plan = ctx.plan
    obj = planlib.current_objective(plan)
    steps = []
    for o in (plan or {}).get("objectives") or []:
        st = "done" if o["status"] == "done" else ("now" if o is obj else "later")
        steps.append({"text": o["title"], "state": st})
    here = None
    if ctx.f.here:
        for r in (plan or {}).get("runs") or []:
            for g in r["legs"]:
                if ctx.f.here in leg_places(ctx.state, g) and g.get("do"):
                    here = {"place": ctx.names.place_name(ctx.f.here), "do": g["do"], "run": r["name"]}
                    break
            if here:
                break
    cs = ctx.state.current_contracts()
    t = soonest_timer(ctx)
    loc = ctx.state.location
    return {"view": "now",
            "next": (obj or {}).get("next_step"),
            "steps": steps[:8],
            "timer": t,
            "materials": materials_block(ctx),
            "here": here,
            "contract": contract_block(ctx, cs[0], compact=True) if cs else None,
            "notes": list((plan or {}).get("notes") or []),
            "location": place_words(ctx, loc["code"]) if loc and loc["left"] is None else None}


def _leg_list(ctx):
    run = ctx.run
    if not run:
        return []
    done = set(ctx.progress["done"])
    out = []
    for g in run["legs"]:
        i = g["index"]
        st = "now" if i == ctx.progress["now"] else ("done" if i in done else "later")
        out.append({"place": g["to"], "why": g.get("do"), "state": st, "gm": number(g["gm"], 1) if g.get("gm") else None})
    return out


def _arrive_list(ctx, leg):
    """What to do on arrival: the leg's own list, else what its view needs first."""
    if leg is None:
        return []
    if leg.get("arrive"):
        return list(leg["arrive"])
    out = []
    view = leg.get("view")
    mode = {"mining": "mining", "salvage": "salvage", "combat": "combat"}.get(view)
    c = ctx.ref.controls(mode) if mode else None
    if c and c.get("knob"):
        out.append("Turn the mode knob to %s (%s)." % (view.capitalize(), c["knob"]))
    if view == "mining":
        targets = _targets(ctx)
        ref = ctx.ref.mining([t["ore"] for t in targets], _spot(ctx, leg))
        reads = ["%s reads %s" % (o["ore"], number(o["reads"][0]["scan"])) for o in ref["ores"] if o.get("reads")]
        if reads:
            out.append(", ".join(reads) + ".")
        takes = sorted({t["min_quality"] for t in targets if t.get("min_quality")})
        if takes:
            out.append("Take rocks at %s and up." % number(takes[0]))
    elif view == "refinery":
        if leg.get("refine"):
            out.append("Refine %s." % _and(leg["refine"]))
        if leg.get("leave"):
            out.append("Leave out %s." % _and(leg["leave"]))
    elif view == "selling":
        sell = [x["what"] for x in (ctx.plan or {}).get("sell") or [] if x.get("where")
                and ctx.names.find_place(x["where"]) in leg_places(ctx.state, leg)]
        if sell:
            out.append("Sell %s." % _and(sell))
    if leg.get("do") and not out:
        out.append(leg["do"])
    return out[:6]


def _and(words):
    words = list(words)
    if len(words) <= 1:
        return "".join(words)
    return ", ".join(words[:-1]) + " and " + words[-1]


def travel_view(ctx):
    q = ctx.f.jump or ctx.state.quantum
    leg = None
    if ctx.run and ctx.progress["heading"] is not None:
        leg = ctx.run["legs"][ctx.progress["heading"]]
    dest = None
    if q:
        n = ctx.names
        e = n.entry(q["target"])
        sub = []
        if leg and norm(leg["to"]) not in (norm(n.short(q["target"])), norm(n.name(q["target"]))):
            sub.append(leg["to"])
        elif e.get("body") and e.get("kind"):
            sub.append("%s near %s" % (e["kind"].capitalize(), e["body"]) if e["kind"] != "planet" else e["body"])
        if leg:
            sub.append("leg %d of %d" % (leg["index"] + 1, len(ctx.run["legs"])))
        dest = {"short": n.short(q["target"]), "name": n.name(q["target"]), "code": q["target"],
                "sub": " · ".join(sub) or None}
    return {"view": "travel",
            "dest": dest,
            "since_ms": ctx.ms(q["selected"]) if q else None,
            "since_text": "since %s" % ctx.when(q["selected"]) if q else None,
            "clock_label": "Since the target was set",
            "from": q.get("start") if q else None,
            "fuel": money(q["fuel"]) if q and q.get("fuel") is not None else None,
            "obstructed": bool(q and q.get("obstructed")),
            "run": ctx.run["name"] if ctx.run else None,
            "legs": _leg_list(ctx),
            "arrive": _arrive_list(ctx, leg),
            "timer": soonest_timer(ctx),
            "controls": controls(ctx, "travel")}


def _targets(ctx):
    """The run's target ores, each with the quality to take a rock at: its own, else the plan
    objective's material of the same name."""
    run = ctx.run
    targets = [dict(t) for t in (run or {}).get("targets") or []]
    obj = planlib.current_objective(ctx.plan)
    mats = {norm(m["name"]): m for m in (obj or {}).get("materials") or []}
    for t in targets:
        if t.get("min_quality") is None and norm(t["ore"]) in mats:
            t["min_quality"] = mats[norm(t["ore"])]["min_quality"]
    if not targets and mats:
        targets = [{"ore": m["name"], "min_quality": m["min_quality"], "skip_below": None} for m in mats.values()]
    return targets


def _spot(ctx, leg):
    if leg and leg.get("spot"):
        return leg["spot"]
    places = sorted(leg_places(ctx.state, leg)) if leg else []
    if not places and ctx.f.here:
        places = [ctx.f.here]
    for p in places:
        s = ctx.ref.mining_spot(p)
        if s:
            return s
    return None


def _current_leg(ctx):
    if not ctx.run:
        return None
    i = ctx.progress["at"]
    if i is None:
        i = ctx.progress["now"]
    return ctx.run["legs"][i] if i is not None else None


def mining_view(ctx):
    leg = _current_leg(ctx)
    targets = _targets(ctx)
    spot = _spot(ctx, leg)
    planned = bool(targets)
    if not targets and spot:
        # No plan names the targets (the Golem's seat chose this view): what spawns here, the
        # most common first, with no quality rule.
        targets = [{"ore": o, "min_quality": None, "skip_below": None} for o in ctx.ref.spot_ores(spot)]
    ref = ctx.ref.mining([t["ore"] for t in targets], spot)
    tmap = {norm(t["ore"]): t for t in targets}
    spot_name = ref["spot_name"] or (leg["to"] if leg else None)
    ores, alike = [], []
    for o in ref["ores"]:
        t = tmap.get(norm(o["ore"]), {})
        take = t.get("min_quality")
        skip = t.get("skip_below") if t.get("skip_below") is not None else take
        reads = []
        for i, r in enumerate(o.get("reads") or []):
            reads.append({"rocks": r["rocks"], "rocks_text": "%d rocks" % r["rocks"], "scan": number(r["scan"]),
                          "chance": r["chance"], "chance_text": "%d%%" % round((r["chance"] or 0) * 100),
                          "top": i == 0})
            for a in r["alike_here"]:
                alike.append({"ore": o["ore"], "alike": a["ore"], "scan": number(a["scan"]), "rocks": r["rocks"]})
        tier = o.get("tier")
        if o.get("share") is not None:
            tier_text = "%s · %d%% of rocks here" % (tier, round(o["share"] * 100))
        elif ref["spot_known"]:
            tier_text = "%s · not in this spot's rock mix" % tier if tier else "Not in this spot's rock mix"
        else:
            tier_text = tier
        ores.append({"name": o["ore"], "known": o.get("known", False), "tier_text": tier_text,
                     "take": "%s+" % number(take) if take is not None else None,
                     "skip": number(skip) if skip is not None else None, "reads": reads[:4]})
    if not ores:
        alike_text = None
    elif alike:
        alike_text = "Within 1%% here: %s." % "; ".join(
            "%s %s reads like %s at %d rocks" % (a["alike"], a["scan"], a["ore"], a["rocks"]) for a in alike[:4])
    elif ref["spot_known"]:
        alike_text = "None within 1%% at %s." % spot_name
    else:
        alike_text = "Spot not in the ore table: look-alikes unknown."
    body = None
    if leg:
        e = {}
        for code in leg.get("codes") or []:
            e = ctx.names.entry(code)
            if e:
                break
        body = e.get("body")
    where = ", ".join(x for x in (spot_name, body) if x)
    if ctx.run:
        where = (where + " · " if where else "") + "plan: %s" % ctx.run["name"]
    return {"view": "mining",
            "where": where or None,
            "spot": spot, "spot_known": ref["spot_known"],
            "ores_from": "plan" if planned else ("spot" if ores else None),
            "ores": ores,
            "goal": materials_block(ctx, [t["ore"] for t in targets]) if planned else materials_block(ctx),
            "alike": alike_text,
            "refine": _refine_rows(ctx, [o["name"] for o in ores]),
            "contract": _contract_of_view(ctx, "mining"),
            "controls": controls(ctx, "mining")}


def _refine_rows(ctx, ores):
    """Where to refine each ore with the bonus: the plan's refinery legs first, else the best
    station the yield table knows."""
    if not ores:
        return None
    method = _method(ctx, None)
    legs = [g for g in (ctx.run or {}).get("legs") or [] if g.get("view") == "refinery"]
    rows = []
    for ore in ores:
        found = None
        for g in legs:
            if g.get("refine") and norm(ore) not in {norm(x) for x in g["refine"]}:
                continue
            for p in leg_places(ctx.state, g):
                y = ctx.ref.yield_bonus(p, ore)
                if y is not None:
                    found = (p, y[0], y[1])
                    break
            if found:
                break
        if found is None:
            b = ctx.ref.best_refinery(ore)
            found = (b[0], b[2], b[3]) if b else None
        if found:
            rows.append({"ore": ore, "at": ctx.names.place_name(found[0]) or found[0],
                         "bonus": signed_percent(found[1]), "positive": found[1] > 0, "date": found[2]})
    return {"method": method["name"] if method else None, "rows": rows} if rows else None


def _method(ctx, leg):
    name = (leg or {}).get("method") or (ctx.plan or {}).get("refine_method") or "Pyrometric Chromalysis"
    m = ctx.ref.method(name)
    return m or {"name": name, "detail": None}


def _contract_of_view(ctx, view):
    c = next((c for c in ctx.state.current_contracts() if c["view"] == view), None)
    return contract_block(ctx, c) if c else None


def salvage_view(ctx):
    run = ctx.run if ctx.run and ctx.run.get("salvage") else None
    sv = (run or {}).get("salvage") or {}
    goal = sv.get("goal") or {}
    plan = ctx.plan or {}
    g = None
    if goal.get("name"):
        need, held = goal.get("need_scu"), goal.get("held_scu")
        to_go = round(need - held, 2) if need is not None and held is not None and need > held else None
        t = plan.get("updated_t")
        sub = []
        if held is not None:
            sub.append("Held as of %s" % ctx.when(t) if t else "Held as the plan says")
        if to_go:
            sub.append("%s SCU to go" % scu(to_go))
        g = {"title": "%s%s" % (goal["name"], " for %s" % goal["for"] if goal.get("for") else ""),
             "held": scu(held), "need": scu(need), "unit": "SCU",
             "fill": round(min(1.0, held / need), 3) if need and held is not None else None,
             "sub": " · ".join(sub) or None, "_to_go": to_go}
    info = ctx.f.ship_info or {}
    hold = None
    if info.get("cargo_scu"):
        sub = None
        if g and g["_to_go"]:
            n = -(-g["_to_go"] // info["cargo_scu"])
            sub = "About %d full hold%s to go" % (n, "s" if n != 1 else "")
        hold = {"title": "%s hold" % info["name"], "scu": scu(info["cargo_scu"]), "sub": sub}
    if g:
        del g["_to_go"]
    sell = None
    if sv.get("sell_at"):
        place = ctx.names.find_place(sv["sell_at"])
        rows, dates = [], []
        for what, note in [(x, "keep for repairs" if goal.get("for") == "repairs" else "keep") for x in sv.get("keep") or []] + \
                [(x, "sell") for x in sv.get("sell") or []]:
            p = ctx.ref.price(what, place) if place else None
            if p and p["date"]:
                dates.append(p["date"])
            rows.append({"what": what, "note": note, "price": money(p["sell"]) if p and p["sell"] is not None else None})
        sell = {"title": "Sell at %s" % (ctx.names.place_name(place) if place else sv["sell_at"]), "rows": rows,
                "foot": "aUEC per SCU · UEX, %s" % _date_words(max(dates)) if dates else None}
    leg = _current_leg(ctx)
    return {"view": "salvage",
            "where": (leg or {}).get("to") or _here_name(ctx),
            "goal": g, "hold": hold,
            "next": sv.get("next") or (leg or {}).get("do"),
            "contract": _contract_of_view(ctx, "salvage"),
            "sell": sell,
            "controls": controls(ctx, "salvage")}


def _date_words(d):
    """'2026-11-26' -> 'Nov 26' (a price row's date, already a calendar day)."""
    try:
        y, m, day = (int(x) for x in d.split("-"))
        return "%s %d" % (("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")[m - 1], day)
    except (ValueError, IndexError, AttributeError):
        return d


def _here_name(ctx):
    loc = ctx.state.location
    if loc and loc["left"] is None:
        return ctx.names.name(loc["code"])
    if ctx.state.body:
        return "Near %s" % ctx.names.name(ctx.state.body["name"])
    return None


def combat_view(ctx):
    st = ctx.state
    cs = st.current_contracts()
    c = next((x for x in cs if x["view"] == "combat"), None)
    on_foot = (c is not None and c["setting"] == "foot") or ctx.f.on_foot
    downed = st.health["status"] in ("downed", "dead")
    name = _ship_name(ctx)
    run = ctx.run if ctx.run and ctx.run.get("combat") else None
    cb = (run or {}).get("combat") or {}
    lost = st.ships_lost[-1] if st.ships_lost else None
    if downed and lost and st.health["t"] is not None and 0 <= st.health["t"] - lost["t"] <= 300:
        v = st.vehicles.get(lost["vehicle_id"]) or {}
        where = "No ship · %s destroyed %s" % (v.get("name") or st._class_word(lost["class"]), ctx.when(lost["t"]))
    elif on_foot:
        here = _here_name(ctx)
        where = "On foot" + (" · %s" % here if here else "")
    else:
        where = "Pilot seat" + (" · %s" % name if name else "")
    tally = dict(st.tally)
    tally["kills_verified"] = False
    left = st.ship_left
    ship_left = None
    if on_foot and left:
        where_left = ctx.names.name(left["code"]) if left.get("code") else (
            ctx.names.name(left["body"]) if left.get("body") else None)
        ship_left = {"name": left["name"], "where": where_left, "when": ctx.when(left["t"])}
    health = None
    if st.health["injuries"]:
        i = st.health["injuries"][-1]
        health = "%s injury: %s, tier %d" % (i["severity"], i["part"].lower(), i["tier"])
    elif st.health["status"] != "ok":
        health = {"downed": "Downed", "dead": "Dead"}.get(st.health["status"], st.health["status"])
    return {"view": "combat",
            "on_foot": bool(on_foot), "downed": downed,
            "where": where,
            "ship": None if on_foot else ({"name": name, "note": cb.get("ship_note")} if name else None),
            "tally": None if on_foot else tally,
            "contract": contract_block(ctx, c) if c else None,
            "law": law_block(ctx),
            "ship_left": ship_left,
            "health": health,
            "controls": None if on_foot else controls(ctx, "combat"),
            "telemetry": None}


def cargo_view(ctx):
    st = ctx.state
    c = next((x for x in st.current_contracts() if x["view"] == "cargo"), None)
    stops = []
    if c:
        for o in _objective_order(c["objectives"]):
            s = o.get("stop")
            if not s:
                continue
            stops.append({"kind": s["kind"], "index": s.get("index"), "place": s.get("place"),
                          "item": s.get("item"), "scu": s["total"] if s.get("unit") == "SCU" else None,
                          "boxes": s["total"] if s.get("unit") == "boxes" else None,
                          "delivered": s.get("amount"), "state": "done" if o["state"] == "complete" else o["state"],
                          "verified": bool(s.get("verified"))})
    cur = current_objective(c) if c else None
    this_stop = None
    if cur and cur.get("stop"):
        s = cur["stop"]
        here = ctx.f.here
        at = ctx.names.find_place(s.get("place")) if s.get("place") else None
        if s.get("unit") == "SCU" and s.get("total") is not None:
            big, unit = scu(s["total"] - (s.get("amount") or 0)), "SCU off" if s["kind"] == "dropoff" else "SCU on"
        else:
            big, unit = s.get("item") or "Cargo", "to drop off" if s["kind"] == "dropoff" else "to pick up"
        place = s.get("place")
        this_stop = {"big": big, "unit": unit, "kind": s["kind"], "here": bool(at and here and at == here),
                     "sub": ", ".join(x for x in ((s.get("commodity") if s.get("unit") == "SCU" else None),
                                                  "at %s" % place if place else None) if x) or None,
                     "verified": bool(s.get("verified"))}
    total = None
    scus = [x["scu"] for x in stops if x["kind"] == "dropoff" and x["scu"] is not None]
    if scus:
        n = len([x for x in stops if x["kind"] == "dropoff"])
        total = {"big": scu(sum(scus)), "unit": "SCU", "sub": "in %d stop%s" % (n, "s" if n != 1 else "")}
    elif stops:
        pk = sum(1 for x in stops if x["kind"] == "pickup")
        dp = sum(1 for x in stops if x["kind"] == "dropoff")
        total = {"big": str(len(stops)), "unit": "stops",
                 "sub": ", ".join(x for x in ("%d pickup%s" % (pk, "s" if pk != 1 else "") if pk else None,
                                              "%d drop-off%s" % (dp, "s" if dp != 1 else "") if dp else None) if x)}
    info = ctx.f.ship_info or {}
    grid = None
    if info.get("cargo_scu"):
        need = sum(scus) if scus else None
        if need is None:
            sub = "cargo grid"
        elif need <= info["cargo_scu"]:
            sub = "room to spare" if need < info["cargo_scu"] else "exactly full"
        else:
            sub = "%s SCU more than the grid" % scu(need - info["cargo_scu"])
        grid = {"title": "%s grid" % info["name"], "big": scu(info["cargo_scu"]), "unit": "SCU", "sub": sub}
    keys = None
    cc = ctx.ref.controls("cargo")
    if cc and cc["items"]:
        keys = [cc["items"][0]]
    head = None
    if c:
        kind = c["type_name"] or (c["kind"] or "Contract").capitalize()
        com = next((x["item"] for x in stops if x["scu"] is not None and x["item"]), None)
        head = "%s%s · %d stop%s" % (kind, " %s" % com if com else "", len(stops), "s" if len(stops) != 1 else "") \
            if stops else kind
    trade = _trade_block(ctx)
    if head is None and trade:
        head = "Trade run"
    unverified = []
    if any(x["kind"] == "dropoff" and not x["verified"] for x in stops):
        unverified.append(UNVERIFIED["hauling"])
    e = earned(st)
    return {"view": "cargo",
            "head": head,
            "this_stop": this_stop, "contract_total": total, "grid": grid,
            "keys": keys,
            "contract": contract_block(ctx, c) if c else None,
            "stops": stops,
            "trade": trade,
            "earned": {"big": "+%s" % money(e), "unit": "aUEC"} if e else None,
            "controls": controls(ctx, "cargo"),
            "unverified": unverified}


def _trade_block(ctx):
    """What was bought this session, and what the plan says about selling it."""
    st = ctx.state
    buy = next((r for r in reversed(st.trade) if r["kind"] == "commodity_buy" and r["result"] in (None, "Success")), None)
    tr = ((ctx.run or {}).get("trade") or {}) if ctx.run else {}
    if buy is None and not tr.get("commodity"):
        return None
    out = {"bought": None, "sell": None}
    if buy is not None:
        info = st.shop_info(buy)
        what = buy.get("commodity") or tr.get("commodity") or "a commodity"
        q = "%s SCU of %s" % (scu(buy["scu"]), what) if buy.get("scu") is not None else what
        out["bought"] = "Bought %s%s, %s/SCU." % (q, " at %s" % info["place_name"] if info["place_name"] else "",
                                                 money(buy["per_scu"])) if buy.get("per_scu") else \
            "Bought %s for %s aUEC." % (q, money(buy["price"]))
    if tr.get("sell_at"):
        place = ctx.names.find_place(tr["sell_at"])
        where = ctx.names.place_name(place) if place else tr["sell_at"]
        price = tr.get("sell_price")
        p = ctx.ref.price(tr.get("commodity") or (buy or {}).get("commodity"), place) if place else None
        parts = ["Sell at %s" % where]
        if price is not None:
            parts.append("the plan says %s/SCU" % money(price))
            amount = (buy or {}).get("scu") or tr.get("scu")
            cost = (buy or {}).get("per_scu") or tr.get("buy_price")
            if amount and cost is not None:
                parts.append("about %s" % _signed_money(amount * (price - cost)))
        if p and p.get("sell") is not None:
            parts.append("UEX %s/SCU on %s" % (money(p["sell"]), _date_words(p["date"])))
        out["sell"] = ": ".join([parts[0], ", ".join(parts[1:])]) + "." if len(parts) > 1 else parts[0] + "."
    return out


def _signed_money(x):
    return ("+" if x >= 0 else "-") + money(abs(x))


def mission_view(ctx):
    cs = ctx.state.current_contracts()
    c = cs[0] if cs else None
    go = None
    if c:
        cur = current_objective(c)
        stop = (cur or {}).get("stop") or {}
        leg = _current_leg(ctx)
        if stop.get("place"):
            go = {"place": stop["place"], "sub": "From the objective"}
        elif leg and leg.get("do"):
            go = {"place": leg["to"], "sub": leg["do"]}
        else:
            go = {"place": None, "sub": "Marker set by the contract"}
    others = [{"title": x["title"] or x["internal"] or "Untitled contract", "giver": x["giver_name"],
               "objective": x["objective"]} for x in cs[1:]]
    return {"view": "mission",
            "contract": contract_block(ctx, c) if c else None,
            "go_next": go,
            "others": {"count": len(others), "items": others[:MAX_OTHERS]}}


def refinery_view(ctx):
    st = ctx.state
    leg = _current_leg(ctx)
    here = ctx.f.here
    if here is None and leg:
        here = next(iter(sorted(leg_places(st, leg))), None)
    method = _method(ctx, leg)
    targets = [t["ore"] for t in _targets(ctx)]
    refine_list = (leg or {}).get("refine") or []
    leave_list = (leg or {}).get("leave") or []
    refine, leave = [], []
    for ore in refine_list or targets:
        y = ctx.ref.yield_bonus(here, ore) if here else None
        refine.append({"ore": ore, "bonus": signed_percent(y[0]) if y else None, "positive": bool(y and y[0] > 0),
                       "date": y[1] if y else None})
    for ore in leave_list:
        b = None
        for g in (ctx.run or {}).get("legs") or []:
            if g is leg or g.get("view") != "refinery" or norm(ore) not in {norm(x) for x in g.get("refine") or []}:
                continue
            for p in leg_places(st, g):
                y = ctx.ref.yield_bonus(p, ore)
                if y is not None:
                    b = (p, y[0])
                    break
            if b:
                break
        leave.append({"ore": ore, "why": "refine at %s (%s)" % (ctx.names.place_name(b[0]), signed_percent(b[1])) if b else None})
    name = ctx.names.place_name(here) if here else None
    timers = [t for t in ctx.timers if t["kind"] == "refinery" and here and ctx.names.find_place(t["where"] or "") == here]
    done = [{"text": "%s at %s" % ("Work order complete" if r["count"] == 1 else "%d work orders complete" % r["count"],
                                   ctx.when(r["t"])), "count": r["count"]}
            for r in st.refinery if here and ctx.names.find_place(r["station"]) == here]
    sold = any(r["kind"] == "refinery_sell" and r.get("at") and st.names.place(r["at"]) == here for r in st.trade)
    return {"view": "refinery",
            "station": {"name": name, "short": ctx.names.place_short(here) if here else None},
            "method": {"name": method["name"], "detail": method.get("detail")},
            "refine": refine, "leave": leave,
            "timers": timers, "done_here": done[-5:],
            "sold_ore": sold,
            "note": (leg or {}).get("do")}


def selling_view(ctx):
    st = ctx.state
    here = ctx.f.here
    rows, dates = [], []
    total = 0.0
    for x in (ctx.plan or {}).get("sell") or []:
        if not (here and x.get("where") and ctx.names.find_place(x["where"]) == here):
            continue
        p = ctx.ref.price(x["what"], here)
        if p and p.get("date"):
            dates.append(p["date"])
        value = x["scu"] * x["price"] if x.get("scu") is not None and x.get("price") is not None else None
        if value:
            total += value
        rows.append({"what": x["what"], "scu": scu(x["scu"]), "quality": number(x["quality"]) if x.get("quality") is not None else None,
                     "price": money(x["price"]) if x.get("price") is not None else None,
                     "uex": money(p["sell"]) if p and p.get("sell") is not None else None,
                     "value": money(value) if value else None, "note": x.get("note")})
    sold = []
    for r in st.trade:
        if r["kind"] in ("commodity_sell", "sell") and r.get("at") and st.names.place(r["at"]) == here:
            what = r.get("commodity") or r.get("item") or "a commodity"
            q = "%s SCU of %s" % (scu(r["scu"]), what) if r.get("scu") is not None else what
            sold.append({"text": "Sold %s for %s aUEC" % (q, money(r["price"])), "time": ctx.when(r["t"])})
    return {"view": "selling",
            "where": ctx.names.place_name(here) if here else None,
            "rows": rows,
            "total": "%s aUEC" % money(total) if total else None,
            "sold": sold[-6:],
            "prices_from": "UEX, %s" % _date_words(max(dates)) if dates else None,
            "unverified": [UNVERIFIED["sell_scu"]] if any(r["kind"] == "commodity_sell" for r in st.trade) else []}


ROLE = {"AB6": "stick base", "MTQ": "throttle"}


def preflight_view(ctx):
    st = ctx.state
    pf = st.preflight
    expected = config.EXPECTED_JOYSTICKS
    devices = []
    for j in st.joysticks:
        w = next((w for w in expected if j["name"].strip().lower() == w["name"].lower()
                  or (j.get("guid") or "").upper().startswith(w["guid_prefix"])), None)
        if w:
            role, mark, mark_text = ROLE.get(w["label"], w["label"]), "ok", "Found"
        else:
            low = j["name"].lower()
            role = "keyboard" if ("keyboard" in low or "huntsman" in low) else "other device"
            mark, mark_text = "info", ""
        devices.append({"slot": "Joystick %d" % (j["index"] + 1), "name": j["name"], "role": role,
                        "mark": mark, "mark_text": mark_text})
    for name in pf.get("missing") or []:
        w = next((w for w in expected if w["name"] == name), None)
        devices.append({"slot": "Not found", "name": name, "role": ROLE.get(w["label"], "") if w else "",
                        "mark": "bad", "mark_text": "Missing"})
    if pf.get("ok") is False:
        title, do = preflight_alert(pf)
        missing = " ".join(pf.get("missing") or [])
        first = next((d for d in devices if d["slot"] == "Joystick 1"), None)
        if "AB6" in missing and first:
            who = "The keyboard" if first["role"] == "keyboard" else first["name"]
            why = "%s took joystick 1. Every stick binding points at it." % who
        elif "AB6" in missing:
            why = "No joystick was listed at all."
        else:
            why = "The throttle is not in the list: its bindings do nothing."
        verdict, kicker = "fail", "Preflight failed"
    elif pf.get("ok") is True:
        title, do, why = "Stick base and throttle connected", None, None
        verdict, kicker = "pass", "Preflight passed"
    else:
        title, do, why = "Waiting for the joystick list", None, None
        verdict, kicker = "waiting", "Preflight"
    note = "Listed in a different order than usual; this has worked." if pf.get("ok") and pf.get("order") == "differs" else None
    prof = st.profile
    return {"view": "preflight",
            "verdict": verdict, "kicker": kicker, "title": title, "why": why, "note": note,
            "devices": devices, "do": do,
            "plan_notes": list((ctx.plan or {}).get("preflight") or []),
            "profile": "%s loaded at %s" % (prof["name"], ctx.when(prof["t"])) if prof else None}


def idle_view(ctx):
    st = ctx.state
    s = st.session
    last = None
    facts = []
    lists = []
    if s["start"] is not None:
        end = (s["ended"] or {}).get("t") or s["last_t"]
        last = "Last session %s · %s to %s" % (week_day(s["start"], ctx.tz), ctx.when(s["start"]),
                                                ctx.when(end) if end else "?")
        played = (end - s["start"]) if end else None
        places = []
        for p in st.places:
            name = st.names.place_name(st.names.place(p["code"])) or st.names.name(p["code"])
            if not places or places[-1] != name:
                places.append(name)
        done = sum(1 for c in st.contracts.values() if c["status"] == "complete")
        sales = sum(r["price"] for r in st.trade if r["kind"] in ("sell", "commodity_sell")
                    and r["price"] is not None and r["result"] in (None, "Success"))
        facts = [{"value": hours_minutes(played) or "?", "label": "played"},
                 {"value": str(len(set(places))), "label": "places"},
                 {"value": str(done), "label": "contracts done"},
                 {"value": money(sales), "label": "aUEC from sales"},
                 {"value": str(len(st.deaths)), "label": "deaths"}]
        if places:
            lists.append({"label": "Places", "text": ", ".join(places[:8]), "ok": False})
        ships = []
        for v in st.vehicles.values():
            n = v.get("name") or (st.ref.ship(v.get("class")) or {}).get("name") or (ship_class(v["class"]) if v.get("class") else None)
            if n and n not in ships:
                ships.append(n)
        if ships:
            lists.append({"label": "Ships", "text": ", ".join(ships[:6]), "ok": False})
    waiting = [t for t in ctx.timers if t["state"] in ("ready", "done")]
    if waiting:
        lists.append({"label": "Waiting", "ok": True, "text": "; ".join(
            "%s%s: %s" % (t["label"], " at %s" % t["where_short"] if t.get("where_short") else "", t["text"])
            for t in waiting[:3])})
    obj = planlib.current_objective(ctx.plan)
    run = ctx.run
    nxt = (obj or {}).get("next_step") or ("%s: %s" % (run["name"], run["note"]) if run and run.get("note") else None)
    return {"view": "idle",
            "title": "Nothing running",
            "last": last,
            "facts": facts,
            "next": nxt,
            "notes": list((ctx.plan or {}).get("preflight") or []),
            "lists": lists}


def reference_view(ctx, mode="flight", auto="now"):
    """The rig's reference cards (PLAN §4 item 18). The cards themselves are a static file the
    page loads; this says only which mode to open them on and what the rules would show."""
    return {"view": "reference", "mode": mode, "auto": auto}


MODELS = {"now": now_view, "travel": travel_view, "mining": mining_view, "salvage": salvage_view,
          "combat": combat_view, "cargo": cargo_view, "mission": mission_view, "refinery": refinery_view,
          "selling": selling_view, "preflight": preflight_view, "idle": idle_view}


def model(ctx, view, chosen=None):
    if view == "reference":
        chosen = chosen or {}
        return reference_view(ctx, chosen.get("mode", "flight"), chosen.get("auto", "now"))
    return MODELS.get(view, now_view)(ctx)
