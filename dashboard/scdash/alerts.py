"""Alerts and timers (PLAN §4 items 8 and 10, §7), as pure functions of the state, the plan, the
user block and "now" (seconds since the epoch, passed in: nothing here reads the clock).

Alerts are of two sorts:

- **What is true now** (a missing stick base, downed, dead, a stuck hangar queue, monitored
  space down): shown while it holds and the game runs.
- **What just happened** (a refinery order done, a crime against the user, a failed contract):
  each has a lifetime counted from its *event's* time, so rereading a session after a restart
  raises nothing old (PLAN §7).

Preflight: only a missing stick base or throttle is the red alert. Both present in another
order than usual is a pass with a note on the Preflight view, not an alert (PLAN §4 item 2,
corrected 2026-11-27).

Timers come from the plan and from quick timers the user adds. A "work order completed" notice
clears a refinery timer only when the timer's `ready_at` is at or before the notice's time, give
or take a few minutes, and with two orders at one station it clears the earliest that fits
(PLAN §7): an old notice read again after a restart cannot clear a newer timer.
"""
from .names import norm
from .state import clock_facts
from .words import clock, day_clock, duration, iso, local, money

BAD, WARN, OK = "bad", "warn", "ok"
LEVEL_ORDER = {BAD: 0, WARN: 1, OK: 2}
MAX_ALERTS = 6
MAX_TIMERS = 20
CLEAR_TOLERANCE_S = 5 * 60            # "give or take a few minutes" (PLAN §7)
QUICK_SHOWN_AFTER_S = 30 * 60         # a quick timer stays this long after it is ready

# What just happened: notable kind -> (level, label, lifetime in seconds, what to do).
EVENT_ALERTS = {
    "quantum_obstructed": (WARN, "Attention", 120, "Travel somewhere else first to find a clear path"),
    "refinery_done": (OK, "Done", 10 * 60, None),
    "blueprint": (OK, "Received", 5 * 60, None),
    "contract_failed": (WARN, "Contract", 5 * 60, None),
    "contract_withdrawn": (WARN, "Contract", 5 * 60, None),
    "reward": (OK, "Paid", 2 * 60, None),
    "crimestat": (WARN, "Law", 10 * 60, "Security will now engage you"),
    "crime": (WARN, "Law", 5 * 60, None),
    "attacked": (BAD, "Attacked", 5 * 60, "A player started a fight: check your surroundings"),
    "fined": (WARN, "Law", 3 * 60, None),
    "impounded": (WARN, "Law", 10 * 60, None),
    "injury": (WARN, "Injury", 5 * 60, "Treat it in a medical bed"),      # severe or critical only
}
LEFT_ALERTS = {"server crash": (BAD, "Server", 5 * 60, "The server crashed: rejoin from the menu"),
               "kicked for inactivity": (WARN, "Server", 5 * 60, None)}
SHIP_LOST_S = 5 * 60


def _ms(t):
    return int(round(t * 1000)) if t is not None else None


def _alert(aid, level, kind, title, text=None, do=None, t=None, until=None, since=None):
    # `since_ms`: a running duration ("waiting 13 min") is the page's to count from this, never
    # worded here, or the text would freeze between rebuilds (stage 3 review).
    return {"id": aid, "level": level, "kind": kind, "title": title, "text": text, "do": do,
            "t": iso(t), "t_ms": _ms(t), "until_ms": _ms(until), "since_ms": _ms(since)}


def when(t, now, tz=None):
    """'10:24 PM' on the same local day as `now`, else 'Nov 26, 4:21 PM'."""
    if t is None:
        return None
    if local(t, tz).date() == local(now, tz).date():
        return clock(t, tz, seconds=False)
    return day_clock(t, tz)


def preflight_alert(pf):
    """The red alert for a missing device: its title and what to do, from `missing`."""
    missing = " ".join(pf.get("missing") or [])
    ab6, mtq = "AB6" in missing, "MTQ" in missing
    if ab6 and mtq:
        return ("Stick base and throttle not detected",
                "Quit the game. Switch on the AB6 base and check the MTQ's cable; when MOZA Cockpit "
                "shows both, start the game again")
    if mtq:
        return ("Throttle not detected",
                "Quit the game. Check the MTQ throttle's cable; when MOZA Cockpit shows it, start the game again")
    return ("Stick base not detected",
            "Quit the game. Switch on the AB6 base, wait until MOZA Cockpit shows it, then start the game again")


def build_alerts(state, now, game_running, tz=None):
    """(alerts, next change in seconds or None). Alerts sorted red, amber, green, newest first."""
    out = []
    nxt = []
    s = state.session
    live = bool(game_running) and s["game"] in ("menu", "in_game")

    # What is true now.
    pf = state.preflight
    if live and pf.get("ok") is False:
        title, do = preflight_alert(pf)
        first = next((j for j in state.joysticks if j["index"] == 0), None)
        text = ("Joystick 1 is %s: every stick binding points at it." % first["name"]) if first else None
        out.append(_alert("preflight:%s" % s["id"], BAD, "Preflight failed", title, text, do, t=s["start"]))
    h = state.health
    if live and h["status"] == "downed":
        out.append(_alert("downed:%s" % h["t"], BAD, "Downed", "You are incapacitated",
                          _downed_text(state, now, tz), "Wait for a medic, or respawn at your regen point", t=h["t"]))
    elif live and h["status"] == "dead":
        out.append(_alert("dead:%s" % h["t"], BAD, "Dead", "You died",
                          "Gear left on the body at %s. A respawn confirms it." % when(h["t"], now, tz),
                          "Respawn at your regeneration point", t=h["t"]))
    q = state.hangar["queue"]
    if live and q is not None:
        facts = clock_facts(state, now)
        if facts["hangar_stuck"]:
            out.append(_alert("hangar:%s" % q["joined"], WARN, "Attention", "Hangar queue stuck",
                              "The estimate was %s." % duration(q["wait_s"]),
                              "Cancel at the hangar terminal and request again", t=q["joined"],
                              since=q["joined"]))
        elif q.get("wait_s"):
            nxt.append(q["joined"] + 2 * q["wait_s"])
    z = state.zone
    if live and z.get("monitored_down") and z.get("t") is not None:
        out.append(_alert("comms:%s" % z["t"], WARN, "Law", "Monitored space down",
                          "The game says monitored space is down here.", None, t=z["t"]))

    # What just happened, each for its lifetime from the event's own time.
    seen = {}
    for x in state.notable:
        spec = EVENT_ALERTS.get(x["kind"])
        if spec is None or (x["kind"] == "injury" and not x["text"].startswith(("Severe", "Critical"))):
            continue
        level, kind, life, do = spec
        until = x["t"] + life
        if now >= until:
            continue
        aid = "%s:%d" % (x["kind"], _ms(x["t"]))
        seen[aid] = seen.get(aid, 0) + 1
        if seen[aid] > 1:
            aid += ".%d" % seen[aid]
        title = x["text"]
        text = None
        if x["kind"] == "refinery_done":
            r = next((r for r in state.refinery if r["t"] == x["t"]), None)
            if r is not None:
                title = "Work order complete" if r["count"] == 1 else "%d work orders complete" % r["count"]
                text = "At %s" % r["station"]
        out.append(_alert(aid, level, kind, title, text, do, t=x["t"], until=until))
        nxt.append(until)
    for x in state.left_server:
        spec = LEFT_ALERTS.get(x["what"])
        if spec is None or now >= x["t"] + spec[2]:
            continue
        level, kind, life, do = spec
        title = "The server crashed" if x["what"] == "server crash" else "Kicked for inactivity"
        out.append(_alert("left:%d" % _ms(x["t"]), level, kind, title, None, do, t=x["t"], until=x["t"] + life))
        nxt.append(x["t"] + life)
    for x in state.ships_lost:
        until = x["t"] + SHIP_LOST_S
        if now >= until or x.get("reason") == "GameRules":
            continue
        v = state.vehicles.get(x["vehicle_id"]) or {}
        name = v.get("name") or state._class_word(x["class"])
        how = "self-destructed" if x.get("reason") == "SelfDestruct" else "destroyed"
        out.append(_alert("lost:%s:%d" % (x["vehicle_id"], _ms(x["t"])), WARN, "Ship lost",
                          "Your %s was %s" % (name, how), None, None, t=x["t"], until=until))
        nxt.append(until)

    out.sort(key=lambda a: (LEVEL_ORDER[a["level"]], -(a["t_ms"] or 0)))
    nxt = [t for t in nxt if t > now]
    return out[:MAX_ALERTS], (min(nxt) if nxt else None)


def _downed_text(state, now, tz):
    where = None
    loc = state.location
    if loc and loc["left"] is None:
        where = state.names.name(loc["code"])
    elif state.body:
        where = state.names.name(state.body["name"])
    t = state.health["t"]
    text = "%s at %s" % (("Near %s" % where) if where else "Downed", when(t, now, tz))
    lost = next((x for x in reversed(state.ships_lost) if t is not None and 0 <= t - x["t"] <= 120), None)
    if lost:
        v = state.vehicles.get(lost["vehicle_id"]) or {}
        text += ", after the %s was destroyed" % (v.get("name") or state._class_word(lost["class"]))
    return text + "."


# ---------------------------------------------------------------------------- timers

def _same_station(state, location, station):
    """Does a timer's location (a code, 'MIC-L2', or a full name) name the station a notice names?"""
    if not location or not station:
        return False
    n = state.names
    a, b = n.find_place(location), n.find_place(station)
    if a and b:
        return a == b
    # No prefix matching: a timer at "M" was cleared by a MIC-L2 notice that way (stage 3
    # review). Unknown to the names table, the two must read the same.
    x, y = norm(location), norm(station)
    return bool(x) and x == y


def build_timers(state, plan, user, now, tz=None):
    """(timers, next change in seconds or None). Running first (soonest first), then ready, then
    done (cleared by a completion notice)."""
    items = []
    for t in (plan or {}).get("timers") or []:
        items.append({"id": "plan:" + t["id"], "source": "plan", "kind": t["kind"], "label": t["label"],
                      "location": t["location"], "ready_t": t["ready_t"], "started_t": t["started_t"],
                      "cleared_t": None})
    for t in (user or {}).get("timers") or []:
        if now - t["ready_t"] > QUICK_SHOWN_AFTER_S:
            continue
        items.append({"id": "quick:" + t["id"], "source": "quick", "kind": "quick", "label": t["label"],
                      "location": None, "ready_t": t["ready_t"], "started_t": t.get("added_t"),
                      "cleared_t": None})
    # PLAN §7: each notice clears at most its count of refinery timers at its station, each one
    # whose ready time is at or before the notice (with a few minutes' tolerance), earliest first.
    refinery = sorted((x for x in items if x["kind"] == "refinery"), key=lambda x: x["ready_t"])
    for n in sorted(state.refinery, key=lambda r: r["t"]):
        for _ in range(max(1, n["count"])):
            fit = [x for x in refinery if x["cleared_t"] is None and x["ready_t"] <= n["t"] + CLEAR_TOLERANCE_S
                   and _same_station(state, x["location"], n["station"])]
            if not fit:
                break
            fit[0]["cleared_t"] = n["t"]
    out, nxt = [], []
    names = state.names
    for x in items:
        place = names.find_place(x["location"]) if x["location"] else None
        where = names.place_name(place) if place else x["location"]
        if x["cleared_t"] is not None:
            st, text = "done", "Work order complete at %s" % when(x["cleared_t"], now, tz)
        elif now >= x["ready_t"]:
            st, text = "ready", "Ready since %s" % when(x["ready_t"], now, tz)
        else:
            st, text = "running", "Ready %s" % when(x["ready_t"], now, tz)
            nxt.append(x["ready_t"])
        if x["source"] == "quick":
            nxt.append(x["ready_t"] + QUICK_SHOWN_AFTER_S)
        out.append({"id": x["id"], "source": x["source"], "kind": x["kind"], "label": x["label"],
                    "where": where, "where_short": names.place_short(place) if place else x["location"],
                    "state": st, "text": text, "ready_at": iso(x["ready_t"]), "ready_ms": _ms(x["ready_t"]),
                    "ready_text": when(x["ready_t"], now, tz),
                    "started_ms": _ms(x["started_t"]) if x["started_t"] and x["started_t"] < x["ready_t"] else None,
                    "cleared_at": iso(x["cleared_t"])})
    rank = {"running": 0, "ready": 1, "done": 2}
    out.sort(key=lambda x: (rank[x["state"]], x["ready_ms"]))
    # The user's quick timers always have room (at most plan.MAX_QUICK); the plan's fill the
    # rest (twenty plan timers used to cut every quick one out: stage 3 review).
    quick = [x for x in out if x["source"] == "quick"]
    planned = [x for x in out if x["source"] != "quick"][:max(0, MAX_TIMERS - len(quick))]
    keep = {id(x) for x in quick + planned}
    out = [x for x in out if id(x) in keep]
    nxt = [t for t in nxt if t > now]
    return out, (min(nxt) if nxt else None)


def earned(state):
    """aUEC the log shows coming in this session: sales and contract pay that are logged."""
    total = 0.0
    for r in state.trade:
        if r["kind"] in ("sell", "commodity_sell") and r["price"] is not None and r["result"] in (None, "Success"):
            total += r["price"]
    total += sum(x["amount"] for x in state.rewards)
    return total


def money_text(x):
    return money(x) if x is not None else None
