"""The reference tables stage 3 reads, loaded slim and only when something asks (PLAN §9, §10).

The service has to stay under 30 MB and idles near 22 MB. A plain `json.load` of contracts.json
holds 2.3 MB, and that memory stays taken even after a slim copy is made and the big one dropped
[seen 2026-11-27: the private working set did not come back down]. So every table here is read
through a `json` object hook that turns each entry into a small tuple the moment it is parsed,
keeping only the fields the views use: the full table never exists in memory. Measured on
2026-11-27: contracts 0.7 MB this way.

Each table is read on first use and kept: contracts when the first contract appears, ships when
the first ship does, prices only when a view shows a price, ores only for the Mining view. A
missing or unreadable file gives an empty table and the answers say so ("no table"); nothing
here raises.

The lookups follow each table's `_meta.lookup` text exactly; `contract()` quotes the order.
"""
import json
import re
import sys
from pathlib import Path

from . import config
from .names import norm

_I = sys.intern

# Plan and log words for a commodity, against the game's English names in prices.json [mine].
COMMODITY_ALIASES = {"rmc": "Recycled Material Composite", "cm": "Construction Materials",
                     "construction mat": "Construction Materials", "construction mat.": "Construction Materials"}

MAX_CACHE = 300                    # answers kept per kind of lookup
MAX_LOOKUP = 200                   # longest text a pattern lookup is run on (real titles: under 80)


def _s(x):
    return _I(x) if isinstance(x, str) else x


def _load(path, hook=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f, object_hook=hook) if hook else json.load(f)
    except (OSError, ValueError, RecursionError):
        return None


def _remember(cache, key, value):
    if len(cache) >= MAX_CACHE:
        cache.clear()                # rare: a session meets a few dozen contracts and ships
    cache[key] = value
    return value


# ---------------------------------------------------------------------------- contracts

# A contract entry: kind, view, setting, giver, subs, also, type, generator. `also` is a tuple of
# (generator, view, kind) for a contract that more than one generator offers.
_C_FIELDS = ("generator", "giver", "type", "template", "legacy", "sub_of")


def _contracts_hook(d):
    if "generator" in d and "src" not in d and set(d) <= {"generator", "view", "kind"}:
        return (_s(d.get("generator")), _s(d.get("view")), _s(d.get("kind")))          # an `also` row
    if "src" in d and "view" in d and "contracts" not in d and any(k in d for k in _C_FIELDS):
        also = d.get("also")
        also = tuple(a for a in also if isinstance(a, tuple)) if isinstance(also, list) else ()
        subs = d.get("subs")
        return ("C", _s(d.get("kind")), _s(d.get("view")), _s(d.get("setting")), _s(d.get("giver")),
                subs if isinstance(subs, int) else 0, also, _s(d.get("type")), _s(d.get("generator")))
    if "contracts" in d and "src" in d:                                                 # a generator
        return ("G", _s(d.get("kind")), _s(d.get("view")), _s(d.get("setting")), _s(d.get("giver")))
    if "pattern" in d:
        return ("P", d.get("pattern"), _s(d.get("kind")), _s(d.get("view")), _s(d.get("setting")))
    if "src" in d and "view" in d and set(d) <= {"kind", "src", "setting", "view"}:     # a title
        return ("T", _s(d.get("kind")), _s(d.get("view")), _s(d.get("setting")))
    if set(d) == {"name", "src"}:                                                       # a mission type
        return _s(d.get("name"))
    if d and all(isinstance(v, int) for v in d.values()):                               # view counts
        return None
    return d


class _Contracts:
    def __init__(self, data):
        def pick(name, tag):
            v = data.get(name) if isinstance(data, dict) else None
            if not isinstance(v, dict):
                return {}
            return {k: e for k, e in v.items() if isinstance(e, tuple) and e and e[0] == tag}
        self.contracts = pick("contracts", "C")
        self.generators = pick("generators", "G")
        self.titles = pick("titles", "T")
        types = data.get("types") if isinstance(data, dict) else None
        self.types = {k: v for k, v in (types or {}).items() if isinstance(v, str)}

        def rows(name):
            v = data.get(name) if isinstance(data, dict) else None
            return [e for e in (v or []) if isinstance(e, tuple) and e and e[0] == "P" and isinstance(e[1], str)]
        self.patterns = rows("title_patterns")
        self.rules = rows("rules")
        self._compiled = {}

    def rx(self, pattern):
        c = self._compiled.get(pattern)
        if c is None:
            try:
                c = re.compile(pattern)
            except re.error:
                c = False
            self._compiled[pattern] = c
        return c or None


UNKNOWN_CONTRACT = {"kind": "unknown", "view": "mission", "setting": None, "giver": None,
                    "type": None, "how": "unknown"}
SUB_RE = re.compile(r"^(.+)_(\d{1,3})$")


# ---------------------------------------------------------------------------- the other tables

def _ships_hook(d):
    if "job" in d and "name" in d:                                            # a fleet entry
        return ("F", _s(d.get("name")), _s(d.get("job")), d.get("note"))
    if "name" in d and ("cargo_how" in d or "maker" in d):                    # a vehicle class
        scu = d.get("cargo_scu")
        return ("S", _s(d.get("name")), scu if isinstance(scu, (int, float)) and not isinstance(scu, bool) else None,
                _s(d.get("kind")), _s(d.get("variant")), _s(d.get("maker_code")))
    if d and all(isinstance(v, (int, float)) for v in d.values()):            # cargo grids
        return None
    return d


def _shops_hook(d):
    if "kind" in d and "places" in d and "name" in d:
        return ("H", _s(d.get("kind")), _s(d.get("name")), _s(d.get("place")))
    return d


def _resources_hook(d):
    if "record" in d and "name" in d:
        return _s(d.get("name"))
    return d


def _prices_hook(d):
    if "terminal" in d and ("buy" in d or "sell" in d) and "place" in d:      # one row
        return ("R", _s(d.get("place")), _num(d.get("buy")), _num(d.get("sell")), _s(d.get("date")))
    if "terminal" in d and "type" in d:                                       # a terminal: not used
        return None
    return d


def _ores_hook(d):
    # Keep the rocks' cluster readings, their look-alikes, the quality figures and each spot's
    # rock mix; drop the rest (where else an ore is found, its traces, its element figures).
    if "spot" in d and "share" in d and "rock" in d:                          # an ore's `found` row
        return None
    if "quality_scale" in d:                                                  # composition, traces
        return None
    if "same_spots" in d:
        return ("L", _s(d.get("ore")), d.get("scan"), tuple(_s(x) for x in d.get("same_spots") or ()))
    if "rocks" in d and "chance" in d and "scan" in d:
        return ("Z", d.get("rocks"), d.get("chance"), d.get("scan"),
                tuple(x for x in d.get("lookalikes") or () if isinstance(x, tuple)))
    if "ore" in d and "rock" in d and "share" in d:                           # a spot's rock row
        return ("M", _s(d.get("ore")), _s(d.get("rock")), d.get("share"))
    if "resistance" in d and "instability" in d:                              # element figures
        return None
    return d


def _num(x):
    return x if isinstance(x, (int, float)) and not isinstance(x, bool) else None


class RefData:
    """The reference tables, each read on first use. `folder` is dashboard/reference by default;
    `prices` is the git-ignored dashboard/data/reference/prices.json (absent: no prices)."""

    def __init__(self, folder=None, prices=None):
        self.folder = Path(folder) if folder else config.REFERENCE_DIR
        self.prices_path = Path(prices) if prices else config.DATA_DIR / "reference" / "prices.json"
        self._contracts = None
        self._ships = None
        self._fleet = None
        self._ships_lower = None
        self._shops = None
        self._resources = None
        self._controls = None
        self._refineries = None
        self._prices = None
        self._prices_lower = None
        self._ores = None
        self._words = None
        self._words_for = None
        self._cache = {"contract": {}, "ship": {}, "mining": {}}
        self.loaded = []                  # which tables were read, in order (for status and tests)

    def _note(self, name, ok):
        self.loaded.append(name if ok else name + " (missing)")

    # -- contracts ---------------------------------------------------------------------------

    def _contract_table(self):
        if self._contracts is None:
            data = _load(self.folder / "contracts.json", _contracts_hook)
            self._contracts = _Contracts(data if isinstance(data, dict) else {})
            self._note("contracts", isinstance(data, dict))
        return self._contracts

    def contract(self, contract=None, generator=None, title=None):
        """Kind, view, setting (foot, ship, vehicle or None), giver and mission type of a contract,
        and `how` it was found, following contracts.json `_meta.lookup` in its order:

        1. contracts[contract]; if missing and the name ends in `_<n>`, the entry without it when
           that entry has `subs` greater than n (a sub-contract is logged as <name>_<index>);
           when the entry has `also` and the generator is one of those, that one;
        2. generators[generator] when it has a view (all its contracts agree);
        3. titles[title], then the first title pattern that matches;
        4. the first rule whose pattern matches the contract, else the generator;
        5. kind "unknown", view "mission": the caller lists it for data/unmapped.json.
        """
        key = (contract, generator, title)
        hit = self._cache["contract"].get(key)
        if hit is not None:
            return hit
        # The title patterns and the rules are regular expressions, some of them quadratic on long
        # text: none is run on a text longer than any real one (a 32 KB name took 3.5 s, stage 3
        # review). The exact lookups by name still are.
        if title and len(title) > MAX_LOOKUP:
            title = None
        t = self._contract_table()
        info = None
        if contract:
            e, how = t.contracts.get(contract), "contract"
            if e is None:
                m = SUB_RE.match(contract)
                if m:
                    base = t.contracts.get(m.group(1))
                    if base is not None and base[5] > int(m.group(2)):
                        e, how = base, "sub-contract"
            if e is not None:
                info = {"kind": e[1], "view": e[2], "setting": e[3], "giver": e[4], "type": e[7], "how": how}
                if e[6] and generator and generator != e[8]:
                    for g, view, kind in e[6]:
                        if g == generator:
                            gen = t.generators.get(generator)
                            info.update(view=view or info["view"], kind=kind or info["kind"],
                                        giver=(gen[4] if gen else None) or info["giver"], how=how + ", also")
                            break
        if info is None and generator:
            g = t.generators.get(generator)
            if g is not None and g[2]:
                info = {"kind": g[1], "view": g[2], "setting": g[3], "giver": g[4], "type": None, "how": "generator"}
        if info is None and title:
            ti = t.titles.get(title)
            if ti is not None:
                info = {"kind": ti[1], "view": ti[2], "setting": ti[3], "giver": None, "type": None, "how": "title"}
            else:
                for _, pattern, kind, view, setting in t.patterns:
                    rx = t.rx(pattern)
                    if rx is not None and rx.search(title):
                        info = {"kind": kind, "view": view, "setting": setting, "giver": None, "type": None,
                                "how": "title pattern"}
                        break
        c_rule = contract if contract and len(contract) <= MAX_LOOKUP else None
        g_rule = generator if generator and len(generator) <= MAX_LOOKUP else None
        if info is None and (c_rule or g_rule):
            for _, pattern, kind, view, setting in t.rules:
                rx = t.rx(pattern)
                if rx is None:
                    continue
                if (c_rule and rx.search(c_rule)) or (g_rule and rx.search(g_rule)):
                    info = {"kind": kind, "view": view, "setting": setting, "giver": None, "type": None, "how": "rule"}
                    break
        if info is None:
            info = dict(UNKNOWN_CONTRACT)          # step 5: only this goes to data/unmapped.json
        info["view"] = info.get("view") or "mission"
        if not info.get("giver") and generator:
            g = t.generators.get(generator)
            info["giver"] = g[4] if g is not None and g[4] else None
        info["type_name"] = t.types.get(info.get("type")) if info.get("type") else None
        info["unmapped"] = info["how"] == "unknown"
        return _remember(self._cache["contract"], key, info)

    # -- ships -------------------------------------------------------------------------------

    def _ship_table(self):
        if self._ships is None:
            data = _load(self.folder / "ships.json", _ships_hook)
            ok = isinstance(data, dict)
            ships = data.get("ships") if ok else None
            fleet = data.get("fleet") if ok else None
            self._ships = {k: v for k, v in (ships or {}).items() if isinstance(v, tuple) and v[0] == "S"}
            self._fleet = {k: v for k, v in (fleet or {}).items() if isinstance(v, tuple) and v[0] == "F"}
            self._note("ships", ok)
        return self._ships

    def ship(self, cls=None, name=None):
        """A vehicle's display name, job (mining, salvage, cargo, combat or None: the fleet's, from
        ships.hand.json), cargo grid in SCU (None when the records do not settle it), whether it
        is in the user's fleet, and its class. By class as the log prints it (exact, then without
        regard to case, as ships.json says), else by the ship channel's name for a fleet ship."""
        key = (cls, name)
        hit = self._cache["ship"].get(key)
        if hit is not None:
            return hit or None
        ships = self._ship_table()
        found = None
        if cls:
            if cls in ships:
                found = cls
            else:
                if self._ships_lower is None:
                    self._ships_lower = {k.lower(): k for k in ships}
                found = self._ships_lower.get(cls.lower())
        if found is None and name:
            n = norm(name)
            found = next((k for k, f in self._fleet.items() if norm(f[1]) == n), None)
        if found is None:
            _remember(self._cache["ship"], key, {})
            return None
        s = ships.get(found)
        f = self._fleet.get(found)
        out = {"class": found, "name": (f[1] if f else None) or (s[1] if s else None) or name,
               "job": f[2] if f else None, "note": f[3] if f else None, "fleet": f is not None,
               "cargo_scu": s[2] if s else None, "kind": s[3] if s else None,
               "variant": s[4] if s else None}
        return _remember(self._cache["ship"], key, out)

    def is_vehicle(self, cls):
        """Is this class a ship or vehicle a pilot flies (and not a sentry or other thing that a
        <Vehicle Destroyed> line also names)? Its class must start with a maker code [ref: CSR
        counts a victim only then]: one the log's classes use, or the maker code ships.json gives
        it. ships.json alone is not enough: it lists 'Orbital_Sentry_SecurityNetwork' as a ship
        (a turret by Broad & Rabiee) [seen in the table]."""
        if not cls:
            return False
        from .words import MAKERS
        prefix = cls.partition("_")[0]
        if prefix in MAKERS:
            return True
        self._ship_table()
        s = self._ships.get(cls)
        return bool(s and s[5] and prefix.upper() == s[5].upper())

    # -- shops, resources --------------------------------------------------------------------

    def shop(self, name):
        """A shop's kind and display name, and its place when the name belongs to one place only
        (shops.json: a name shared across a chain has no place; the caller takes it from the last
        inventory location in the log). A name ending in "-<digits>" is also looked up without it."""
        if not name:
            return None
        e = self._shop_table().get(name)
        if e is None:
            base = re.sub(r"-\d+$", "", name)
            e = self._shops.get(base) if base != name else None
        if e is None:
            return None
        return {"kind": e[1], "name": e[2], "place": e[3]}

    def resource(self, rid):
        """The English name of a commodity from the resource id in a sale or purchase line."""
        if not rid:
            return None
        return self._resource_table().get(rid.lower())

    def _shop_table(self):
        if self._shops is None:
            data = _load(self.folder / "shops.json", _shops_hook)
            shops = data.get("shops") if isinstance(data, dict) else None
            self._shops = {k: v for k, v in (shops or {}).items() if isinstance(v, tuple) and v[0] == "H"}
            self._note("shops", isinstance(data, dict))
        return self._shops

    def _resource_table(self):
        if self._resources is None:
            data = _load(self.folder / "resources.json", _resources_hook)
            res = data.get("resources") if isinstance(data, dict) else None
            self._resources = {k.lower(): v for k, v in (res or {}).items() if isinstance(v, str)}
            self._note("resources", isinstance(data, dict))
        return self._resources

    # -- the game's own words ------------------------------------------------------------------

    def game_words(self, names=None):
        """Every word of a place (the names table `names`), maker, ship, commodity, shop and
        contract giver the tables hold, lower case, with the law module's own (crimes,
        jurisdictions, a stoplist): what a word in a crime or comms notice can be other than a
        player's handle (law.learnable). Built once per names table, on the first such notice;
        about 0.5 MB."""
        if self._words is not None and self._words_for is names:
            return self._words
        from . import law
        from .words import MAKERS
        out = law.fixed_words()
        for code, v in MAKERS.items():
            out.update(law.words_of(code))
            out.update(law.words_of(v))
        for cls, s in self._ship_table().items():
            out.update(law.words_of(cls))
            out.update(law.words_of(s[1]))
        for f in self._fleet.values():
            out.update(law.words_of(f[1]))
        for v in self._resource_table().values():
            out.update(law.words_of(v))
        for k, v in self._shop_table().items():
            out.update(law.words_of(k))
            out.update(law.words_of(v[2]))
        t = self._contract_table()
        for e in list(t.contracts.values()) + list(t.generators.values()):
            out.update(law.words_of(e[4]))
        for v in t.types.values():
            out.update(law.words_of(v))
        for e in (getattr(names, "table", None) or {}).values():
            for key in ("name", "short", "body", "system"):
                out.update(law.words_of(e.get(key)))
        self._words, self._words_for = frozenset(out), names
        return self._words

    # -- controls, refineries ----------------------------------------------------------------

    def controls(self, mode):
        """The controls strip for an operator mode (mining, salvage, combat, cargo, travel), from
        controls.json: a title and the items in order, each with where it is, what it does and
        its status (flown, unverified, trial or None)."""
        if self._controls is None:
            data = _load(self.folder / "controls.json")
            modes = data.get("modes") if isinstance(data, dict) else None
            out = {}
            for m, v in (modes or {}).items():
                if not isinstance(v, dict):
                    continue
                knob = v.get("knob") if isinstance(v.get("knob"), dict) else None
                items = []
                for it in v.get("items") or []:
                    if isinstance(it, dict) and it.get("where") and it.get("text"):
                        items.append({"where": it["where"], "what": it["text"], "status": it.get("status")})
                out[m] = {"title": v.get("title") or m.title(), "knob": knob.get("hint") if knob else None,
                          "items": items[:12]}
            self._controls = out
            self._note("controls", isinstance(data, dict))
        return self._controls.get(mode)

    def _refinery_table(self):
        if self._refineries is None:
            data = _load(self.folder / "refineries.json")
            ok = isinstance(data, dict)
            methods, stations, places = {}, {}, {}
            for k, v in ((data or {}).get("methods") or {}).items() if ok else ():
                if isinstance(v, dict) and v.get("name"):
                    methods[k] = {"name": v["name"], "detail": v.get("detail"), "yield": v.get("yield"),
                                  "speed": v.get("speed")}
            for p, v in ((data or {}).get("stations") or {}).items() if ok else ():
                if not isinstance(v, dict):
                    continue
                y = {}
                for ore, reports in (v.get("yields") or {}).items():
                    r = reports[0] if isinstance(reports, list) and reports and isinstance(reports[0], dict) else None
                    if r and isinstance(r.get("bonus"), (int, float)):
                        y[_I(ore)] = (r["bonus"], r.get("date"), r.get("source"))
                stations[p] = {"name": v.get("name"), "yields": y}
            for p, v in ((data or {}).get("places") or {}).items() if ok else ():
                if isinstance(v, dict):
                    places[p] = {"name": v.get("name"), "short": v.get("short")}
            self._refineries = {"methods": methods, "stations": stations, "places": places}
            self._note("refineries", ok)
        return self._refineries

    def method(self, name):
        """A refining method by its display name ('Pyrometric Chromalysis') or record key."""
        if not name:
            return None
        ms = self._refinery_table()["methods"]
        if name in ms:
            return ms[name]
        n = norm(name)
        return next((m for m in ms.values() if norm(m["name"]) == n), None)

    def yield_bonus(self, place, ore):
        """(bonus in percent, date, source) for an ore at a station's place, newest report, or None."""
        st = self._refinery_table()["stations"].get(place)
        if not st or not ore:
            return None
        y = st["yields"].get(ore)
        if y is None:
            n = norm(ore)
            y = next((v for k, v in st["yields"].items() if norm(k) == n), None)
        return y

    def best_refinery(self, ore, places=None):
        """The station with the highest yield bonus for an ore: (place, name, bonus, date), or None.
        `places` limits the choice (a plan's refinery legs)."""
        best = None
        for p, st in self._refinery_table()["stations"].items():
            if places is not None and p not in places:
                continue
            y = self.yield_bonus(p, ore)
            if y is not None and (best is None or y[0] > best[2]):
                best = (p, st["name"], y[0], y[1])
        return best

    def has_refinery(self, place):
        return place in self._refinery_table()["places"]

    # -- prices ------------------------------------------------------------------------------

    def _price_table(self):
        if self._prices is None:
            data = _load(self.prices_path, _prices_hook)
            com = data.get("commodities") if isinstance(data, dict) else None
            out = {}
            for name, v in (com or {}).items():
                if isinstance(v, dict) and isinstance(v.get("rows"), list):
                    out[_I(name)] = tuple(r for r in v["rows"] if isinstance(r, tuple) and r and r[0] == "R")
            self._prices = out
            self._prices_lower = {k.lower(): k for k in out}
            self._note("prices", isinstance(data, dict))
        return self._prices

    def prices_available(self):
        return bool(self._price_table())

    def commodity_name(self, text):
        """The prices table's name for a commodity as a plan or the log writes it."""
        if not text:
            return None
        table = self._price_table()
        if text in table:
            return text
        low = text.strip().lower()
        if low in COMMODITY_ALIASES:
            return COMMODITY_ALIASES[low]
        return self._prices_lower.get(low) or self._prices_lower.get(re.sub(r"\s*\((ore|raw)\)$", "", low))

    def price(self, commodity, place):
        """What a terminal at `place` pays (`sell`) and charges (`buy`) per SCU for a commodity,
        with the date of the row: {'sell', 'buy', 'date'}, or None. Crowd-reported (UEX), so
        always shown with its date. Several terminals at one place: the best of each."""
        name = self.commodity_name(commodity)
        if not name or not place:
            return None
        rows = [r for r in self._price_table().get(name, ()) if r[1] == place]
        if not rows:
            return None
        sells = [r for r in rows if r[3] is not None]
        buys = [r for r in rows if r[2] is not None]
        sell = max(sells, key=lambda r: r[3]) if sells else None
        buy = min(buys, key=lambda r: r[2]) if buys else None
        dates = [r[4] for r in (sell, buy) if r is not None and r[4]]
        return {"commodity": name, "sell": sell[3] if sell else None, "buy": buy[2] if buy else None,
                "date": max(dates) if dates else None}

    # -- ores --------------------------------------------------------------------------------

    def _ore_table(self):
        if self._ores is None:
            data = _load(self.folder / "ores.json", _ores_hook)
            ok = isinstance(data, dict)
            self._ores = {"ores": (data or {}).get("ores") or {} if ok else {},
                          "spots": (data or {}).get("spots") or {} if ok else {}}
            self._note("ores", ok)
        return self._ores

    def mining(self, ores, spot):
        """For each target ore at a mining spot (an ores.json spot key, such as 'cru-l5-field'):
        its tier, its share of the rocks there, the ship scan readings per cluster size with their
        chance, the quality figures a lot snaps to, and the look-alikes that also spawn there.
        Cached per (ores, spot): the Mining view asks for the same figures twice a second."""
        key = (tuple(ores), spot)
        hit = self._cache["mining"].get(key)
        if hit is not None:
            return hit
        t = self._ore_table()
        sp = t["spots"].get(spot) if spot else None
        mix = {}
        if isinstance(sp, dict):
            for setting_rows in (sp.get("rocks") or {}).get("ship") or []:
                if isinstance(setting_rows, tuple) and setting_rows[0] == "M":
                    mix[setting_rows[1]] = (setting_rows[2], setting_rows[3])
        out = []
        for ore in ores:
            o = t["ores"].get(ore)
            if o is None:
                n = norm(ore)
                ore_key = next((k for k in t["ores"] if norm(k) == n), None)
                o = t["ores"].get(ore_key) if ore_key else None
                ore = ore_key or ore
            if not isinstance(o, dict):
                out.append({"ore": ore, "known": False})
                continue
            rock_name, share = mix.get(ore, (None, None))
            rocks = o.get("rocks") or {}
            rock = rocks.get(rock_name) if rock_name else None
            if rock is None:                     # not at this spot: the asteroid rock, else any ship rock
                rock = next((r for r in rocks.values() if isinstance(r, dict) and r.get("mode") == "ship"
                             and r.get("setting") == "asteroid"), None) or \
                    next((r for r in rocks.values() if isinstance(r, dict) and r.get("mode") == "ship"), None)
            reads = []
            for cl in (rock or {}).get("clusters") or []:
                for z in (cl.get("sizes") if isinstance(cl, dict) else None) or []:
                    if isinstance(z, tuple) and z[0] == "Z":
                        alike = [{"ore": a[1], "scan": a[2]} for a in z[4] if spot and spot in a[3]]
                        reads.append({"rocks": z[1], "chance": z[2], "scan": z[3], "alike_here": alike})
                break                            # the first cluster preset is the rock's own
            q = o.get("quality") if isinstance(o.get("quality"), dict) else {}
            out.append({"ore": ore, "known": True, "tier": o.get("tier"), "share": share,
                        "here": share is not None, "reads": reads,
                        "values": [v for v in q.get("values") or [] if isinstance(v, (int, float))]})
        result = {"spot": spot, "spot_name": sp.get("name") if isinstance(sp, dict) else None,
                  "spot_known": isinstance(sp, dict), "ores": out}
        return _remember(self._cache["mining"], key, result)

    def spot_ores(self, spot, n=4):
        """The ship-mineable ores at a spot, the most common first (for a Mining view with no
        plan to name its targets)."""
        sp = self._ore_table()["spots"].get(spot) if spot else None
        rows = [r for r in ((sp or {}).get("rocks") or {}).get("ship") or [] if isinstance(r, tuple) and r[0] == "M"]
        rows.sort(key=lambda r: -(r[3] or 0))
        out = []
        for r in rows:
            if r[1] not in out:
                out.append(r[1])
        return out[:n]

    def mining_spot(self, place):
        """The ores.json spot for a place: the place itself, or its asteroid field ('cru-l5' ->
        'cru-l5-field': a leg to an L-point names the station's code, PLAN §10)."""
        if not place:
            return None
        spots = self._ore_table()["spots"]
        for cand in (place, place + "-field", re.sub(r"-field$", "", place)):
            if cand in spots:
                return cand
        return None


_SHARED = None


def shared():
    """The process's one RefData over dashboard/reference (what the state uses by default)."""
    global _SHARED
    if _SHARED is None:
        _SHARED = RefData()
    return _SHARED
