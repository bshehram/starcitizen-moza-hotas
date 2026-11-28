"""Display names for location codes, from dashboard/reference/locations.json when it exists.

The file's agreed shape:
    {"_meta": {...},
     "locations": {"LOC_RR_S3_L1": {"name": "ARC-L1 Wide Forest Station", "short": "ARC-L1",
                                    "kind": "station", "body": "ArcCorp", "system": "Stanton",
                                    "place": "arc-l1", "src": "game"}}}
Keys are codes exactly as the log prints them, from either family: quantum targets
(`LOC_RR_S3_L1`, `OOC_Stanton_3b_Wala`) and inventory locations (`RR_ARC_L1`,
`Stanton4_NewBabbage`). `place` is the same for every code that means the same place.

A missing or unreadable file gives an empty table: every code is then shown raw.
"""
import json
import re

# Codes made up per mission or per player, which no table can hold [seen 2026-11:
# MISSION_QT_Quantum_Beacon_LongRange_<n> (36 routes), NavPoint_Dynamic_<n>]. Not "unmapped".
DYNAMIC_RE = re.compile(r"^(?:MISSION_QT_|NavPoint_Dynamic_)")
DYNAMIC_NAMES = (("MISSION_QT_", "Mission beacon"), ("NavPoint_Dynamic_", "Nav point"))


_NORM_RE = re.compile(r"[^a-z0-9]+")
MAX_FIND = 200            # find_place() reads no longer text (stage 3 review: 500 cached 60 KB texts)
MAX_FOUND = 500           # its cache


def norm(text):
    """'MIC-L2 Long Forest' -> 'micl2longforest': names as the plan and the log write them."""
    return _NORM_RE.sub("", (text or "").lower())


class LocationNames:
    def __init__(self, table=None, source=None):
        self.table = table or {}
        self.source = source
        self._by_place = None           # place -> (name, short), built on first use (stage 3)
        self._by_name = None            # normalized name or short -> place
        self._found = {}                # find_place() answers, bounded

    @classmethod
    def load(cls, path):
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            table = data.get("locations", {}) if isinstance(data, dict) else {}
            if not isinstance(table, dict):
                table = {}
            return cls({k: v for k, v in table.items() if isinstance(v, dict)}, str(path))
        except (OSError, ValueError):
            return cls({}, None)

    def known(self, code):
        return code in self.table

    @staticmethod
    def dynamic(code):
        return bool(code) and DYNAMIC_RE.match(code) is not None

    def entry(self, code):
        return self.table.get(code) or {}

    def name(self, code):
        """The display name, or the code itself when there is none."""
        if not code:
            return code
        e = self.table.get(code)
        if e and e.get("name"):
            return e["name"]
        for prefix, label in DYNAMIC_NAMES:
            if code.startswith(prefix):
                return label
        return code

    def short(self, code):
        e = self.table.get(code)
        if e and e.get("short"):
            return e["short"]
        return self.name(code)

    def place(self, code):
        """The place key shared by every code for the same place, or the code itself."""
        e = self.table.get(code)
        return (e.get("place") if e else None) or code

    # -- stage 3: places named in words (the plan, objectives, refinery notices) -------------

    def _index(self):
        if self._by_place is not None:
            return
        by_place, by_name, field = {}, {}, set()
        for code, e in self.table.items():
            p = e.get("place")
            if not p:
                continue
            # The first entry with a name wins; a station's quantum code and inventory code
            # carry the same name [seen in locations.json].
            if p not in by_place and e.get("name"):
                by_place[p] = (e.get("name"), e.get("short") or e.get("name"))
            is_field = e.get("kind") == "field"
            for text in (e.get("name"), e.get("short"), code):
                k = norm(text)
                if len(k) < 3:
                    continue
                # 'CRU L5' (the field) and 'CRU-L5' (the station) read the same: the station
                # wins, since that is where a timer or a sale is; a field is named 'CRU-L5 field'.
                if k not in by_name or (by_name[k] in field and not is_field):
                    by_name[k] = p
            if is_field:
                field.add(p)
        self._by_place, self._by_name = by_place, by_name

    def place_name(self, place):
        """The display name of a place key ('mic-l2' -> 'MIC-L2 Long Forest Station')."""
        if not place:
            return None
        self._index()
        e = self._by_place.get(place)
        return e[0] if e else self.name(place)

    def place_short(self, place):
        if not place:
            return None
        self._index()
        e = self._by_place.get(place)
        return e[1] if e else self.short(place)

    def find_place(self, text):
        """The place a text names: a code from either family, a name or a short name in any
        case and punctuation ('MIC-L2', 'mic l2 long forest station'), or a longer text that
        holds one ('TDD New Babbage'). None when nothing fits."""
        if not text or not isinstance(text, str) or len(text) > MAX_FIND:
            return None                 # no place name is that long; and nothing long is kept
        if text in self._found:
            return self._found[text]
        e = self.table.get(text)
        if e and e.get("place"):
            out = e["place"]
        else:
            self._index()
            k = norm(text)
            out = self._by_name.get(k)
            if out is None and len(k) >= 5:
                # The longest known name inside the text, so 'TDD New Babbage' is New Babbage
                # and not a shorter name that happens to sit inside it.
                best = None
                for name, p in self._by_name.items():
                    if len(name) >= 5 and name in k and (best is None or len(name) > len(best[0])):
                        best = (name, p)
                out = best[1] if best else None
        if len(self._found) < MAX_FOUND:
            self._found[text] = out
        return out
