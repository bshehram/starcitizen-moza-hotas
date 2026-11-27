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

Other players' names: the state keeps those it sees (killers, ship channel owners, actors) in a
private set, and `to_dict()` and `build_summary()` replace any of them found in a text with
"another player", whatever text it is (a contract title, an objective).
"""
import re
from collections import deque

from . import config
from .names import LocationNames
from .words import compatible, duration, fit, iso, money, ship_class

ALERT, MAJOR, MINOR = "alert", "major", "minor"

# How an <EndMission> CompletionType reads [seen: Complete 13 and Abandon 7 of 20 in 2026-11].
# Any other type is kept as its own lower-case word.
END_STATUS = {"complete": "complete", "abandon": "abandoned"}

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

# Names that are not anyone's, when a killer or an actor is logged [my reasoning].
NOT_A_NAME = {"", "unknown", "none", "null", "invalid"}
OTHER_PLAYER = "another player"
YOU = "you"                                         # the user's own handle, in public output


class State:
    """The dashboard's state for one log. Feed it events in file order with `apply`."""

    def __init__(self, names=None):
        self.names = names if names is not None else LocationNames()
        self.reset()

    # ------------------------------------------------------------------ life cycle

    def reset(self, session=None):
        self.session = {"id": session, "start": None, "local": None, "build": None,
                        "version": None, "game": "not_running", "world": None,
                        "ended": None, "last_t": None, "events": 0, "spawns": 0,
                        "in_game_since": None, "in_game_s": 0.0, "unreadable": 0}
        self._others = set()                                  # other players' names: never shown
        self._others_re = None
        self._pending_world = None
        self.me = {"handle": None, "player_id": None}         # memory only (PLAN §8)
        self.server = {"shard": None, "joined": None, "shards": []}
        self.joysticks = []
        self.preflight = {"ok": None, "text": "no joysticks logged yet"}
        self._joy_final = False
        self.profile = None
        self.location = None
        self.places = []
        self.body = None
        self.near = None
        self.zone = {"jurisdiction": None, "armistice": None, "monitored": None}
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
        mine = h is None or (name or "").lower() == h.lower()
        if not mine:
            self._other(name)
        return mine

    def _other(self, name):
        """Remember another player's name, privately, so no text of ours ever shows it."""
        if not name or name.strip().lower() in NOT_A_NAME or len(name) < 3:
            return
        h = self.me["handle"]
        if h is not None and name.lower() == h.lower():
            return
        if name not in self._others:
            self._others.add(name)
            self._others_re = None

    def scrub(self, obj):
        """`obj` (JSON-like) with every other player's name seen in this session replaced by
        "another player", and the user's own handle by "you", in every text, whatever it is and
        wherever it came from."""
        handle = self.me["handle"]
        if not self._others and not handle:
            return obj
        if self._others_re is None:
            names = set(self._others) | ({handle} if handle else set())
            alts = "|".join(re.escape(n) for n in sorted(names, key=len, reverse=True))
            self._others_re = re.compile(r"(?<![A-Za-z0-9_])(?:%s)(?![A-Za-z0-9_])" % alts, re.I)
        rx = self._others_re
        mine = handle.lower() if handle else None

        def name_for(m):
            return YOU if m.group(0).lower() == mine else OTHER_PLAYER

        def walk(x):
            if isinstance(x, str):
                return rx.sub(name_for, x)
            if isinstance(x, dict):
                return {k: walk(v) for k, v in x.items()}
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
        if len(self.joysticks) >= 2:
            self._check_joysticks()
        return MINOR, "Joystick %d: %s" % (ev.index + 1, ev.name)

    def _check_joysticks(self):
        """Root CLAUDE.md §1: the AB6 must be joystick 1 and the MTQ joystick 2 (the game's 0 and 1)."""
        by = {j["index"]: j for j in self.joysticks}
        problems = []
        for i, want in enumerate(config.EXPECTED_JOYSTICKS):
            j = by.get(i)
            if j is None:
                problems.append("joystick %d missing (expected the %s)" % (i + 1, want["label"]))
            elif not _is_device(j, want):
                where = next((k["index"] + 1 for k in self.joysticks if _is_device(k, want)), None)
                problems.append("joystick %d is %s, expected the %s%s" % (
                    i + 1, j["name"], want["label"],
                    " (the %s was not detected)" % want["label"] if where is None
                    else " (it is joystick %d)" % where))
        if problems:
            self.preflight = {"ok": False, "text": "; ".join(problems)}
        else:
            self.preflight = {"ok": True, "text": "AB6 is joystick 1 and MTQ joystick 2"}

    def _on_login(self, ev):
        self.me["handle"] = ev.handle
        self._others.discard(ev.handle)
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
        self._pending_world = None
        s["game"] = "menu"
        s["world"] = None
        if ev.reason == "ProcessBootRequest":
            return MINOR, "Main menu"
        if was == "in_game" or ev.reason == "OnLobbyPostGameUnload":
            return MINOR, "Back at the main menu"
        return None

    def _on_join_server(self, ev):
        self._pending_world = "pu"
        self.server["shard"] = ev.shard
        self.server["joined"] = ev.t
        if ev.shard and ev.shard not in self.server["shards"]:
            self.server["shards"].append(ev.shard)
        return MINOR, "Joining a server (%s)" % (ev.shard or "shard unknown")

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
        if loc and loc["docked"] and loc["left"] is None and (
                loc["id"] == ev.landing_to or (code and self.names.place(code) == self.names.place(loc["code"]))):
            loc["t"], loc["id"] = ev.t, ev.landing_to   # still here: moved inside it, or confirmed
            return None
        if code:
            return self._arrive(ev, code, "inventory", True, ev.landing_to)
        return None

    def _on_location_inventory(self, ev):
        self.codes.add(ev.code)
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
        self.zone["jurisdiction"] = ev.name
        return MINOR, "Entered %s jurisdiction" % ev.name

    def _on_armistice(self, ev):
        self.zone["armistice"] = ev.inside
        return MINOR, "Entering the armistice zone" if ev.inside else "Leaving the armistice zone"

    def _on_monitored(self, ev):
        self.zone["monitored"] = ev.inside
        return MINOR, "Entered monitored space" if ev.inside else "Left monitored space"

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
        return MAJOR, "Left the pilot seat of the %s" % self._ship_word(ev.vehicle_id, ev.vehicle_class)

    def _on_stowed(self, ev):
        v = self.vehicles.get(ev.vehicle_id)
        if v is None:
            return None                            # every hangar around logs its stows [seen]
        v["status"], v["t"] = "stowed", ev.t
        return MINOR, "Your %s was stowed" % self._ship_word(ev.vehicle_id)

    def _on_vehicle_destroyed(self, ev):
        self._mine(ev.killer)                      # remembers another player's name, if it is one
        own = ev.vehicle_id in self.vehicles or (
            self.me["player_id"] is not None and ev.owner_id == self.me["player_id"])
        if not own:
            return MINOR, "Destroyed nearby: %s" % ship_class(ev.vehicle_class)
        v = self._vehicle(ev.vehicle_id, ev.vehicle_class)
        v["status"], v["t"] = "destroyed", ev.t
        self.ships_lost.append({"t": ev.t, "vehicle_id": ev.vehicle_id, "class": ev.vehicle_class,
                                "reason": ev.reason})
        self._cap(self.ships_lost)
        how = {"SelfDestruct": "self-destructed", "Ejection": "abandoned (ejection)",
               "Collision": "destroyed in a collision"}.get(ev.reason, "destroyed (%s)" % ev.reason)
        return MAJOR, "Your %s was %s" % (self._ship_word(ev.vehicle_id, ev.vehicle_class), how)

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
        return ALERT, "Downed (incapacitated)"

    def _on_emergency(self, ev):
        self._open_incident(ev, "downed")
        if self.health["status"] == "ok":
            self.health.update(status="downed", t=ev.t)
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
        inc = self._open_incident(ev, "died")
        last = inc["_last_item"]
        inc["items_lost"] += 1
        inc["_last_item"] = ev.t
        if self.health["status"] != "dead":
            self.health.update(status="dead", t=ev.t)
        if last is None:                           # the first line of a burst, one per item
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
                 "objectives": [], "objective": None, "t": t}
            self.contracts[key] = c
            self._trim_contracts()
        return c

    def _trim_contracts(self):
        while len(self.contracts) > config.MAX_CONTRACTS:
            old = next((k for k, c in self.contracts.items() if c["status"] != "active"),
                       next(iter(self.contracts)))
            del self.contracts[old]

    # From CSR sc_livelog.py lines 405-425 (the contract notices). Changed: a contract announced
    # again (same mission id) is updated, not added a second time; `Contract Failed:` is not
    # handled because the user's logs have none (PLAN §3).
    def _on_contract_accepted(self, ev):
        c = self._contract(ev.mission_id, ev.title, ev.t)
        again = c["accepted"] is not None
        c["title"] = ev.title
        if c["status"] in (None, "active"):
            c["status"] = "active"
        if c["accepted"] is None:
            c["accepted"] = ev.t
        if again:
            return MINOR, "Contract still active: %s" % ev.title
        return MAJOR, "Contract accepted: %s" % ev.title

    def _on_contract_complete(self, ev):
        c = self._contract(ev.mission_id, ev.title, ev.t)
        c["title"] = c["title"] or ev.title
        if c["status"] != "complete":
            c["status"] = "complete"
            c["ended"] = c["ended"] or ev.t
        return MAJOR, "Contract complete: %s" % ev.title

    # From CSR sc_livelog.py lines 301-324 (`_objective`): an objective is found by its id, else
    # by its text, and the contract's current objective is the newest one still open. Changed:
    # the hauling "drops" CSR tracks are left out; only New Objective and Objective Complete are
    # read, the two kinds in the user's logs [seen: 85 and 33 notices].
    def _objective(self, ev, state):
        c = self._contract_for(ev.mission_id)
        if not c:
            return None
        text = ev.text
        optional = text.upper().startswith("OPTIONAL:")
        if optional:
            text = text[len("OPTIONAL:"):].strip()
        objs = c["objectives"]
        o = (next((o for o in objs if ev.objective_id and o["id"] == ev.objective_id), None)
             or next((o for o in objs if o["text"] == text), None))
        if o is None:
            o = {"id": ev.objective_id, "text": text, "optional": optional, "state": state, "t": ev.t}
            objs.append(o)
            del objs[:-config.MAX_OBJECTIVES]
        o.update(text=text, state=state)
        live = [x for x in objs if x["state"] == "active"]
        c["objective"] = (live or objs)[-1]["text"]
        return c

    def _on_objective_new(self, ev):
        c = self._objective(ev, "active")
        return (MINOR, "New objective: %s" % ev.text) if c else None

    def _on_objective_complete(self, ev):
        c = self._objective(ev, "complete")
        return (MINOR, "Objective complete: %s" % ev.text) if c else None

    # From CSR sc_livelog.py lines 241-247 (<EndMission>): the authoritative end of a contract;
    # an abandon raises no HUD notice. Changed: a mission this log never announced gets a record
    # of its own, since contracts carry over between launches.
    def _on_mission_ended(self, ev):
        c = self.contracts.get(ev.mission_id) or self._contract(ev.mission_id, None, ev.t)
        kind = ev.completion.strip().lower()
        status = END_STATUS.get(kind, kind or "ended")
        if c["status"] in (None, "active"):
            c["status"] = status
        c["ended"] = c["ended"] or ev.t
        c["end_reason"] = ev.reason
        title = c["title"] or c["internal"] or "a contract from an earlier launch"
        if status == "complete":
            return None if c["accepted"] is not None and c["title"] else (MAJOR, "Contract ended: %s" % title)
        return MAJOR, "Contract %s: %s" % (status, title)

    def _on_mission_marker(self, ev):
        c = self._contract(ev.mission_id, None, ev.t)
        c["giver"], c["internal"] = ev.giver, ev.contract

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
        row = {"t": ev.t, "offset": ev.offset, "kind": kind, "shop": shop, "item": item,
               "price": price, "quantity": quantity, "result": None}
        if extra:
            row.update(extra)
        self.trade.append(row)
        self._cap(self.trade, config.MAX_TRADES)
        return row

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

    def _on_commodity_sell(self, ev):
        self._trade(ev, "commodity_sell", ev.shop, ev.resource_id, ev.amount, ev.quantity,
                    {"box": ev.box})
        return MAJOR, "Sold a commodity at %s for %s aUEC" % (ev.shop, money(ev.amount))

    def _on_commodity_buy(self, ev):
        self._trade(ev, "commodity_buy", ev.shop, ev.resource_id, ev.price, ev.quantity)
        return MAJOR, "Bought a commodity at %s for %s aUEC (%s)" % (ev.shop, money(ev.price), ev.quantity)

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
        if ev.hint:
            return None
        return MINOR, ev.text

    # ------------------------------------------------------------------ output

    def unmapped(self):
        """Location codes seen that the names table does not know (for data/unmapped.json)."""
        return sorted(c for c in self.codes if not self.names.known(c) and not self.names.dynamic(c))

    def to_dict(self, private=False):
        """The state as JSON-ready data. With private=False (what is shown or saved), other
        players' names are replaced in every text; private=True keeps them and adds `me` (the
        handle and player id), for memory only."""
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
                        "in_game_since": iso(s["in_game_since"])},
            "server": {"shard": self.server["shard"], "joined": iso(self.server["joined"]),
                       "shards": list(self.server["shards"])},
            "joysticks": [dict(j, number=j["index"] + 1) for j in self.joysticks],
            "preflight": dict(self.preflight),
            "profile": _times(self.profile),
            "location": dict(place(loc["code"]), how=loc["how"], t=iso(loc["t"]),
                             docked=loc["docked"], left=iso(loc["left"])) if loc else None,
            "places": [dict(place(p["code"]), t=iso(p["t"]), how=p["how"]) for p in self.places],
            "body": dict(place(self.body["name"]), t=iso(self.body["t"])) if self.body else None,
            "zone": dict(self.zone),
            "ship": _times(self.ship),
            "vehicles": {vid: _times(v) for vid, v in self.vehicles.items()},
            "quantum": _jump(q, place) if q else None,
            "jumps": [_jump(j, place) for j in self.jumps],
            "contracts": [_contract_out(c) for c in self.contracts.values()],
            "hangar": {"queue": _times(self.hangar["queue"]), "ready": iso(self.hangar["ready"]),
                       "waits": [_times(w) for w in self.hangar["waits"]]},
            "refinery": [_times(r) for r in self.refinery],
            "trade": [_times(r) for r in self.trade],
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
            return d
        return self.scrub(d)


# ---------------------------------------------------------------------- module helpers

TIME_KEYS = {"t", "joined", "ready", "retrieved", "selected", "arrived", "closed", "obstructed",
             "accepted", "ended", "respawn", "up", "treated"}


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
    out = _times(c)
    out["objectives"] = [_times(o) for o in c["objectives"]]
    return out


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
