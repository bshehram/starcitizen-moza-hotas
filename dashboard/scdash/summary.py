"""The compact record of one session: what `timeline` prints at the end, and what stage 2 writes
to data/sessions/ when a session ends (PLAN §4, item 11).

It holds no player's name: not the user's handle, not other players' (PLAN §8). The handle and
player id live in `State.me`, which this never touches; and every other player's name the
session saw (killers, ship channel owners, actors) is replaced in every text by "another
player", so a contract title or an objective cannot carry one either.
"""
from .words import iso

SPEND = ("buy", "commodity_buy", "rental")
EARN = ("sell", "commodity_sell")


def build_summary(state, complete=False, last_line_t=None):
    """`complete`: the log is known to be finished (a backup, or a new session has begun in the
    same file). A finished log with no quit line ended in a crash or a kill, at its last line
    (`last_line_t`, the time of the last timed line, which can be later than the last event); an
    unfinished one is still running as far as the log can tell."""
    s = state.session
    n = state.names
    if s["ended"]:
        end_t = s["ended"]["t"]
    else:
        known = [t for t in (s["last_t"], last_line_t) if t is not None]
        end_t = max(known) if known else None
    if s["ended"]:
        ended = {"how": "quit", "t": iso(s["ended"]["t"]), "reason": s["ended"]["reason"]}
    elif complete:
        ended = {"how": "no quit line (crash or kill)", "t": iso(end_t), "reason": None}
    else:
        ended = {"how": "running", "t": None, "reason": None}
    in_game = s["in_game_s"]
    if s["in_game_since"] is not None and end_t is not None:       # still in the world at the end
        in_game += max(0.0, end_t - s["in_game_since"])

    def place(code):
        return {"code": code, "name": n.name(code), "place": n.place(code)}

    trade = []
    spent = earned = 0.0
    for r in state.trade:
        ok = r["result"] in (None, "Success")
        trade.append({"t": iso(r["t"]), "kind": r["kind"], "shop": r["shop"], "item": r["item"],
                      "price": r["price"], "quantity": r["quantity"], "result": r["result"]})
        if ok and r["price"] is not None:
            if r["kind"] in SPEND:
                spent += r["price"]
            elif r["kind"] in EARN:
                earned += r["price"]

    ships = []
    for vid, v in state.vehicles.items():
        ships.append({"vehicle_id": vid, "name": v["name"], "class": v["class"],
                      "retrieved": iso(v["retrieved"]), "hangar": v["hangar"], "status": v["status"]})

    return state.scrub({
        "schema": 1,
        "session": s["id"],
        "build": s["build"],
        "version": s["version"],
        "start": iso(s["start"]),
        "start_local": s["local"],
        "end": iso(end_t),
        "duration_s": round(end_t - s["start"], 1) if (end_t is not None and s["start"] is not None) else None,
        "in_game_s": round(in_game, 1),
        "world_entries": s["spawns"],
        "ended": ended,
        "preflight": {"ok": state.preflight["ok"], "text": state.preflight["text"],
                      "joysticks": [j["name"] for j in state.joysticks]},
        "profile_loaded": state.profile["name"] if state.profile else None,
        "servers": list(state.server["shards"]),
        "left_server": [{"t": iso(x["t"]), "what": x["what"], "cause": x["cause"],
                         "reason": x["reason"]} for x in state.left_server],
        "places": [dict(place(p["code"]), t=iso(p["t"]), how=p["how"]) for p in state.places],
        "ships": ships,
        "jumps": [{"t": iso(j["selected"]), "target": place(j["target"]), "from": j["start"],
                   "fuel": j["fuel"], "arrived": iso(j["arrived"]), "closed_by": j["closed_by"]}
                  for j in state.jumps],
        "contracts": [{"mission_id": c["mission_id"], "title": c["title"], "status": c["status"],
                       "accepted": iso(c["accepted"]), "ended": iso(c["ended"]),
                       "end_reason": c["end_reason"], "internal": c["internal"], "giver": c["giver"],
                       "objective": c["objective"]} for c in state.contracts.values()],
        "notices": [{"t": iso(x["t"]), "kind": x["kind"], "text": x["text"]} for x in state.notable],
        "hangar_waits": [{"joined": iso(w["joined"]), "ready": iso(w["ready"]), "estimate_s": w["wait_s"],
                          "ended": w.get("ended")} for w in state.hangar["waits"]],
        "refinery": [{"t": iso(r["t"]), "count": r["count"], "station": r["station"]} for r in state.refinery],
        "blueprints": [{"t": iso(b["t"]), "name": b["name"]} for b in state.blueprints],
        "trade": trade,
        "trade_totals": {"spent": round(spent, 2), "earned": round(earned, 2)},
        "deaths": [{"t": iso(d["t"]), "respawn": iso(d["respawn"]), "cause": d["cause"],
                    "items_lost": d["items_lost"]} for d in state.deaths],
        "recoveries": [{"t": iso(r["t"]), "up": iso(r["up"]), "cause": r["cause"],
                        "items_lost": r["items_lost"], "treated": iso(r.get("treated"))}
                       for r in state.recoveries],
        "ships_lost": [{"t": iso(x["t"]), "vehicle_id": x["vehicle_id"], "class": x["class"],
                        "reason": x["reason"]} for x in state.ships_lost],
        "health_at_end": state.health["status"],
        "screenshots": len(state.screenshots),
        "unreadable": s["unreadable"],
        "unmapped": state.unmapped(),
    })
