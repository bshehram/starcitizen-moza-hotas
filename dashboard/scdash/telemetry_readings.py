"""A decoded telemetry snapshot -> plain readings with units a view can use directly.

Copyright (c) 2026 archelium (support@archelium.com) for the parts marked "From CSR" below,
used under the MIT License (see dashboard/THIRD_PARTY_NOTICES). Everything else in this file is
this project's own.

TABLE below is the one place that maps the stream's field names to reading names. It is
compiled against the schema read from the installed program file, so:

- a field this build does not declare (a 5.0 field on 4.10, or a field a patch renamed) simply
  gives no reading, and `Readings.missing` lists it for `status`;
- every field the table does not use is kept in `other`, a tree with the stream's own names, so
  that a new patch's fields can be shown without touching the decoder.

How each entry is known. The field paths are **[game]**: read from build 4.10.201's descriptors
on 2026-11-27, except the ones marked 5.0, which come from CSR's notes on a 5.0 test build
(docs/telemetry/schema-ptu-5.0.201.txt) and are absent from this build. Every unit, meaning and
quirk is **[ref]** (CSR's docs/telemetry/NOTES.md, Starglance's docs/FIELDS.md as quoted in
PLAN §3) or my own reading, and none of them has been checked against a cockpit: each entry
carries a note, and `verified` is False for all of them until a real session confirms it.

Proto3 sends no field that holds its default (0, false, ""), so a field missing from a message
that is present means that default, while a missing *message* means "no data". A reading is
left out of `readings` when its message is missing; it is None when a rule says the value means
"none".
"""
import math
from collections import namedtuple

from .telemetry_proto import LEN_TYPES, T_BOOL, T_DOUBLE, T_ENUM, T_FLOAT, T_MESSAGE, T_STRING

# From CSR sc_telemetry.py line 455 (FLOAT_SENTINEL): the game sends about 3.4e38 (FLT_MAX)
# for "no value" [ref]. Unchanged.
FLOAT_SENTINEL = 1e38

# kind: "value" (the field's value), "present" (whether the message is there), "count" (a
# repeated message summed per type: params = (type field, amount field, {type: reading name})).
Entry = namedtuple("Entry", "name field unit rules note kind params")


def _e(name, field, unit, rules=(), note="", kind="value", params=None):
    return Entry(name, field, unit, tuple(rules), note, kind, params)


_CSR = "[ref: CSR NOTES.md]"
_SG = "[ref: Starglance FIELDS.md, via PLAN §3]"
_AVAIL = ("which part of the Availability means on is disputed between tools; this reads "
          "`active` like CSR's live page, Starglance reads `enabled` [ref]. Both parts were true "
          "in every frame of CSR's two 4.10 captures, cruise mode included, so `active` may mean "
          "available rather than engaged: check by toggling it in the cockpit")
_50 = "5.0 test builds only [ref: CSR schema-ptu-5.0.201.txt]; not in build 4.10.201"

# Rules, applied in this order: unspecified_none, empty_none, flt_max_none, zero_none, fraction,
# withhold. Each is a quirk recorded by another tool, or my reading, and unverified.
TABLE = [
    # --- the player -------------------------------------------------------------------
    _e("balance_auec", "actor.state.uec_balance", "aUEC", (), "the wallet " + _CSR),
    _e("locomotion", "actor.state.locomotion", "state", ("unspecified_none",),
       "ON_FOOT, EVA or SEATED; reads ON_FOOT about 5 s after leaving a seat " + _CSR),
    _e("crew_role", "actor.state.crew_role", "state", ("unspecified_none",), "PILOT, GUNNER or CREW"),
    _e("seat", "actor.state.seat_name", "text", ("empty_none",),
       "the seat entity, with its id " + _CSR),
    _e("health", "actor.vitals.health.current", "points (0-100)", (), _CSR),
    _e("oxygen_frac", "actor.vitals.oxygen.current", "fraction", ("fraction",), _CSR),
    _e("hunger", "actor.vitals.hunger.current", "points (0-100)", (), _CSR),
    _e("thirst", "actor.vitals.thirst.current", "points (0-100)", (), _CSR),
    _e("body_temperature_c", "actor.vitals.body_temperature.current", "degrees C", (),
       "my reading: 36.5 in CSR's captures"),
    # --- the ship: identity and state -------------------------------------------------
    _e("in_vehicle", "vehicle", "bool", (),
       "the ship block is there: sent only while seated, 5-6 s after sitting down " + _SG +
       "; PLAN §4 reads taking the seat from it appearing", kind="present"),
    _e("vehicle_class", "vehicle.state.class_name", "text", ("empty_none",),
       "the clean class name, <MAKER>_<Model> " + _CSR),
    _e("vehicle_entity", "vehicle.state.name", "text", ("empty_none",),
       "the class name and entity id, <CLASS>_<id>, as in the log's vehicle lines " + _CSR),
    _e("vehicle_type", "vehicle.state.type", "state", ("unspecified_none",),
       "SPACESHIP, GROUND, GRAVLEV or BOAT"),
    _e("vehicle_manufacturer", "vehicle.state.manufacturer", "text", ("empty_none",),
       "always empty on 4.10 " + _SG),
    _e("lights_on", "vehicle.state.lights_enabled", "bool", (), ""),
    _e("doors_open", "vehicle.state.doors.open_state", "state", ("unspecified_none",),
       "OPENED or CLOSED; never sent in CSR's captures"),
    _e("doors_locked", "vehicle.state.doors.lock_state", "state", ("unspecified_none",),
       "UNLOCKED or LOCKED; never sent in CSR's captures"),
    _e("landed", "vehicle.state.flight.state.is_landed", "bool", (),
       "turns true 2-3 s after contact " + _CSR),
    _e("gear", "vehicle.state.flight.state.gear", "state", ("unspecified_none",),
       "RETRACTED, DEPLOYING, DEPLOYED or RETRACTING"),
    _e("vtol", "vehicle.state.flight.state.vtol", "state", ("unspecified_none", "withhold"),
       "always reads DEPLOYED, even on a ship without VTOL " + _SG + " and CSR's captures; "
       "withheld until a build reports it truthfully (PLAN §4)"),
    # --- flight instruments ---------------------------------------------------------------
    _e("speed_mps", "vehicle.state.flight.instruments.speed", "m/s", (),
       "CSR reads it as m/s (a NAV to SCM drop went 1073 to 766)"),
    _e("fuel_hydrogen_frac", "vehicle.state.flight.instruments.hydrogen_fuel", "fraction",
       ("zero_none", "fraction"),
       "0 to 1; reads 0 (is not sent) with the engines off " + _SG + ", so 0 shows as none: a "
       "truly empty tank shows as none too"),
    _e("fuel_quantum_frac", "vehicle.state.flight.instruments.quantum_fuel", "fraction",
       ("zero_none", "fraction"), "always 0 on 4.10 " + _SG + ", so 0 shows as none"),
    _e("g_force", "vehicle.state.flight.instruments.g_meter.current", "G", (),
       "spikes far past the limit on mode switches and contact " + _CSR),
    _e("g_limit", "vehicle.state.flight.instruments.g_meter.max", "G", (),
       "the ship's limit, changes with flight state " + _CSR),
    _e("boost_engaged", "vehicle.state.flight.instruments.boost.engaged", "bool", (), ""),
    _e("boost_reserves_frac", "vehicle.state.flight.instruments.boost.reserves", "fraction",
       ("fraction",), _CSR),
    _e("boost_critical", "vehicle.state.flight.instruments.boost.critical", "bool", (),
       "true when reserves are near empty " + _CSR),
    _e("altitude_m", "vehicle.state.flight.instruments.altitude", "m", ("flt_max_none",),
       "FLT_MAX with no body below, which shows as none " + _CSR + "; unit my guess"),
    _e("radar_altitude_m", "vehicle.state.flight.instruments.radar_altitude", "m",
       ("flt_max_none",), "as altitude; unit my guess"),
    _e("vertical_speed_mps", "vehicle.state.flight.instruments.vertical_speed_indicator", "m/s",
       (), "unit my guess"),
    _e("heading_deg", "vehicle.state.flight.instruments.heading", "degrees", (),
       "unit my guess (180.0068 in CSR's captures)"),
    # --- flight settings: the rig switches these with no light of its own (PLAN §4) ------
    _e("coupled", "vehicle.state.flight.settings.ifcs_coupled.active", "bool", (), _AVAIL),
    _e("esp", "vehicle.state.flight.settings.ifcs_esp.active", "bool", (), _AVAIL),
    _e("g_safe", "vehicle.state.flight.settings.ifcs_g_safe.active", "bool", (), _AVAIL),
    _e("speed_limiter", "vehicle.state.flight.settings.ifcs_speed_limiter.active", "bool", (),
       _AVAIL),
    _e("light_amplification", "vehicle.state.flight.settings.flight_light_amplification",
       "bool", (), "my reading of the name: the cockpit LAMP"),
] + [
    # --- power on/off flags (the AB6 wing panel) ----------------------------------------
    _e("power_" + f, "vehicle.state.power." + f, "bool", (), "")
    for f in ("powerplants", "engines", "weapons", "coolers", "life_support",
              "gravity_generators", "sensors", "shield_generators", "shield_emitters")
] + [
    # --- the ten warning lights ---------------------------------------------------------
    _e("warn_" + f, "vehicle.state.annunciators." + f, "state", ("unspecified_none",),
       "NOMINAL, OFF, MINOR_FLASHING, MINOR_ON, MAJOR_FLASHING or MAJOR_ON; NAV mode shows as "
       "shld OFF with qdrv NOMINAL " + _CSR)
    for f in ("pwr", "wpn", "thr", "shld", "cool", "qdrv", "radr", "prox", "hit", "misl")
] + [
    # --- weapons --------------------------------------------------------------------------
    _e("countermeasures", "weapons.countermeasures", "count", (),
       "decoys and noise left, per type", kind="count",
       params=("type", "amount", {"DECOY": "decoys", "NOISE": "noise"})),
    _e("weapon_preset", "weapons.preset_name", "text", ("empty_none",), ""),
    # --- 5.0 (absent from this build: compiled away until a patch declares them) ---------
    _e("shield_level", "vehicle.state.shields.level", "unknown", (), _50),
    _e("shield_faces", "vehicle.state.shields.faces", "unknown", (), _50),
    _e("hull_health", "vehicle.state.health", "unknown", (), _50),
    _e("master_mode", "vehicle.state.master_mode.mode", "state", ("unspecified_none",),
       "NAVIGATION, SCM or STEALTH; " + _50),
    _e("master_mode_spooled", "vehicle.state.master_mode.spooled", "bool", (), _50),
]

# The events list is read by events_of(), not by the table, and is left out of `other`.
EVENTS_PATH = ("events", "events")
MAX_EVENTS_PER_SNAPSHOT = 16     # a real snapshot carries one event at most [CSR's captures]
SOURCE = "telemetry"             # the tag on everything this source produces


def _default(schema, f):
    """Proto3's value for a field that was not sent, or None for a field with presence."""
    if f.repeated:
        return []
    if f.optional or f.type == T_MESSAGE:
        return None
    if f.type == T_BOOL:
        return False
    if f.type == T_STRING:
        return ""
    if f.type == T_ENUM:
        return schema.enums.get(f.type_name, {}).get(0, 0)
    if f.type in LEN_TYPES:
        return ""
    if f.type in (T_FLOAT, T_DOUBLE):
        return 0.0
    return 0


def _apply_rules(value, rules):
    """(value, withheld?) after the entry's rules."""
    if isinstance(value, float) and not math.isfinite(value):
        value = None
    for r in rules:
        if value is None:
            break
        if r == "unspecified_none" and value == "UNSPECIFIED":
            value = None
        elif r == "empty_none" and value == "":
            value = None
        elif r == "flt_max_none" and isinstance(value, (int, float)) and value >= FLOAT_SENTINEL:
            value = None
        elif r == "zero_none" and value == 0:
            value = None
        elif r == "fraction" and isinstance(value, (int, float)) and not -1e-3 <= value <= 1.001:
            value = None
    return value, "withhold" in rules


class Readings:
    """TABLE compiled against one schema. `build(decoded)` gives the readings of a snapshot."""

    def __init__(self, schema, response_type, table=TABLE):
        self.schema = schema
        self.response_type = response_type
        self.entries = []      # (entry, [Field per path step])
        self.missing = []      # reading names whose field this build does not declare
        self.info = {}         # reading name -> {"unit", "field", "note", "verified"}
        for e in table:
            steps = self._resolve(e.field)
            if steps is None or not self._fits(e, steps):
                self.missing.append(e.name)
                continue
            self.entries.append((e, steps))
            names = [e.name] if e.kind != "count" else list(e.params[2].values())
            for n in names:
                self.info[n] = {"unit": e.unit, "field": e.field, "note": e.note,
                                "verified": False, "withheld": "withhold" in e.rules}

    def _resolve(self, field):
        msg, steps = self.response_type, []
        for part in field.split("."):
            table = self.schema.messages.get(msg)
            if table is None:
                return None
            f = next((f for f in table.values() if f.name == part), None)
            if f is None:
                return None
            steps.append(f)
            msg = f.type_name
        return steps

    def _fits(self, e, steps):
        last = steps[-1]
        if any(f.repeated for f in steps[:-1]):
            return False
        if e.kind == "present":
            return last.type == T_MESSAGE and not last.repeated
        if e.kind == "count":
            if last.type != T_MESSAGE or not last.repeated:
                return False
            sub = self.schema.messages.get(last.type_name, {})
            names = {f.name for f in sub.values()}
            return e.params[0] in names and e.params[1] in names
        return last.type != T_MESSAGE

    def build(self, decoded):
        """{"source": "telemetry", "readings": {...}, "withheld": {...}, "other": {...},
        "events": [...]}. Live readings only: never history, never fed to the log's
        State.apply, never written to the session records (PLAN §5)."""
        readings, withheld, used = {}, {}, set()
        for e, steps in self.entries:
            node = decoded
            parts = e.field.split(".")
            ok = True
            for part in parts[:-1]:
                node = node.get(part) if isinstance(node, dict) else None
                if not isinstance(node, dict):
                    ok = False
                    break
            if not ok:
                continue
            leaf = parts[-1]
            if e.kind == "present":
                readings[e.name] = isinstance(node.get(leaf), dict)
                continue
            used.add(tuple(parts))
            if e.kind == "count":
                items = node.get(leaf)
                if not isinstance(items, list):
                    continue
                tkey, akey, names = e.params
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    name = names.get(item.get(tkey))
                    amount = item.get(akey, 0)
                    if name and isinstance(amount, int) and not isinstance(amount, bool):
                        readings[name] = readings.get(name, 0) + amount
                continue
            if leaf in node:
                value = node[leaf]
            else:
                value = _default(self.schema, steps[-1])
                if value is None:
                    continue
            value, hold = _apply_rules(value, e.rules)
            (withheld if hold else readings)[e.name] = value
        events = events_of(decoded)
        other = _without(decoded, used | {EVENTS_PATH}, ())
        return {"source": SOURCE, "readings": readings, "withheld": withheld,
                "other": other or {}, "events": events}


def events_of(decoded, limit=MAX_EVENTS_PER_SNAPSHOT):
    """The event type names in a snapshot, e.g. ["ACTOR_ENTER_SEAT"], at most `limit`. From
    CSR sc_telemetry.py lines 508-510 (`frame_events`). Changed: bad shapes are skipped,
    numbers kept as numbers, a cap."""
    node = decoded.get(EVENTS_PATH[0]) if isinstance(decoded, dict) else None
    items = node.get(EVENTS_PATH[1]) if isinstance(node, dict) else None
    out = []
    for e in (items[:limit] if isinstance(items, list) else ()):
        if isinstance(e, dict):
            t = e.get("type", "UNSPECIFIED")
            out.append(t if isinstance(t, (str, int)) else "UNSPECIFIED")
    return out


def _without(node, used, prefix):
    """A copy of the tree without the used leaves, empty messages dropped."""
    if not isinstance(node, dict):
        return node
    out = {}
    for k, v in node.items():
        p = prefix + (k,)
        if p in used:
            continue
        if isinstance(v, dict):
            v = _without(v, used, p)
            if not v:
                continue
        out[k] = v
    return out


# From CSR sc_telemetry.py lines 486-505 (`flatten`). Changed: keeps the events, no sentinel
# cleaning (the rules above do that for the table's fields), and a depth cap.
def flatten(tree, prefix="", out=None, depth=0):
    """{"vehicle.state.shields.level": 0.8, ...}: the `other` tree as dotted paths, for a view
    that lists whatever a new build sends."""
    out = {} if out is None else out
    if depth > 32:
        return out
    if isinstance(tree, dict):
        for k, v in tree.items():
            flatten(v, "%s.%s" % (prefix, k) if prefix else str(k), out, depth + 1)
    elif isinstance(tree, list) and tree and all(isinstance(x, dict) for x in tree):
        for i, x in enumerate(tree):
            flatten(x, "%s[%d]" % (prefix, i), out, depth + 1)
    else:
        out[prefix] = tree
    return out
