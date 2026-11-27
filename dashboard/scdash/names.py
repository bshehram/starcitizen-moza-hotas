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


class LocationNames:
    def __init__(self, table=None, source=None):
        self.table = table or {}
        self.source = source

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
