"""The rig reference (dashboard/web/rig/) against the card tables it is generated from.

tools/regen_cards.py writes rig.json and the six diagram images in the same run that makes the
printed cards. This test reads that script with `ast` (it is never run, so no Pillow and no
browser are needed) and fails when a card row, the card texts, the diagram views, the source art
or the status marks in reference/controls.hand.json changed and the folder was not rewritten.
The fix is always the same:  python tools/regen_cards.py --dashboard-only
"""
import ast
import datetime
import hashlib
import json
import re
import struct
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CARD_SCRIPT = ROOT / "tools" / "regen_cards.py"
RIG = ROOT / "dashboard" / "web" / "rig"
DIAGRAMS = ROOT / "diagrams"
HAND = ROOT / "dashboard" / "reference" / "controls.hand.json"

TABLES = ("AB6", "MHG_L", "MHG_R", "MTQ_L", "MTQ_R")
SOURCES = TABLES + ("CARDS", "MODES", "VIEWS", "RIG_ART")
REGEN = "rig reference is stale; run: python tools/regen_cards.py --dashboard-only"

# The service hands these files out as they are, so they stay small. On 2026-11-27 the largest
# image was 22 KB and rig.json 12 KB; the limits leave room for a few more rows, not for a
# change of format (an 8-bit or upscaled image would cross them).
MAX_IMAGE = 40 * 1024
MAX_JSON = 24 * 1024
STATUS_RANK = {"flown": 0, "unverified": 1, "trial": 2}


def read_script():
    """The module-level literals of regen_cards.py (tables, CARDS, MODES, VIEWS, RIG_ART), read
    with ast. A V(tag, text, color) call is evaluated the way the script defines V."""
    tree = ast.parse(CARD_SCRIPT.read_text(encoding="utf-8"))
    env = {}

    def ev(n):
        if isinstance(n, ast.Constant):
            return n.value
        if isinstance(n, (ast.List, ast.Tuple)):
            return [ev(x) for x in n.elts]
        if isinstance(n, ast.Dict) and None not in n.keys:
            return {ev(k): ev(v) for k, v in zip(n.keys, n.values)}
        if isinstance(n, ast.Name) and n.id in env:
            return env[n.id]
        if (isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "V"
                and len(n.args) == 3 and not n.keywords):
            tag, text, color = (ev(a) for a in n.args)
            return {"Tag": tag, "Text": text, "Color": color}
        raise ValueError("not a literal, line %d" % getattr(n, "lineno", 0))

    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            name = node.targets[0].id
            try:
                env[name] = ev(node.value)
            except ValueError:
                if name in SOURCES:           # the data this test checks must stay plain literals
                    raise
    missing = [n for n in SOURCES if n not in env]
    if missing:
        raise AssertionError("regen_cards.py no longer defines %s" % ", ".join(missing))
    return env


def digest(obj):
    """The same short hash regen_cards.digest() writes into _meta."""
    raw = json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:12]


def parse_buttons(spec):
    out = set()
    for part in spec.split(","):
        lo, _, hi = part.strip().partition("-")
        out.update(range(int(lo), int(hi or lo) + 1))
    return out


def label_numbers(label):
    m = re.fullmatch(r"(\d+)(?:-(\d+))?", label)
    return set(range(int(m.group(1)), int(m.group(2) or m.group(1)) + 1)) if m else None


def card_rows(src, card):
    return [r for t in card["Tables"] for r in src[t] if "Label" in r]


def expected_marks(src):
    """The status marks controls.hand.json gives, keyed (device, label, mode or None), worked out
    here on its own: a mark goes on the variant of the item's operator mode when the row has one,
    otherwise on the primary; the more doubtful of two marks wins."""
    if not HAND.is_file():
        return {}
    hand = json.loads(HAND.read_text(encoding="utf-8"))
    tag_of = {m["Mode"]: m["Tag"] for m in src["MODES"]}
    rows = {c["Device"]: {r["Label"]: r for r in card_rows(src, c)} for c in src["CARDS"]}
    marks = {}
    for _, m in sorted((hand.get("modes") or {}).items()):
        for it in m.get("items") or []:
            status = it.get("status")
            if not status:
                continue
            variant = it.get("variant", m.get("variant"))
            for ref in it.get("controls") or []:
                dev, _, label = ref.partition(" ")
                row = rows.get(dev, {}).get(label)
                if row is None:
                    continue
                tag = tag_of.get(variant)
                on_variant = tag is not None and any(v["Tag"] == tag for v in row.get("Variants") or [])
                key = (dev, label, variant if on_variant else None)
                if key not in marks or STATUS_RANK.get(status, 9) > STATUS_RANK.get(marks[key], 9):
                    marks[key] = status
    return marks


def png_size(path):
    data = path.read_bytes()[:26]
    if data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR":
        raise AssertionError("%s is not a PNG" % path.name)
    return struct.unpack(">II", data[16:24])


class RigReferenceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.src = read_script()
        path = RIG / "rig.json"
        if not path.is_file():
            raise AssertionError("dashboard/web/rig/rig.json is missing; " + REGEN)
        cls.doc = json.loads(path.read_text(encoding="utf-8"))
        cls.views = {v["Id"]: v for v in cls.src["VIEWS"]}

    def test_rows_match_the_card_tables(self):
        mode_of = {m["Tag"]: m["Mode"] for m in self.src["MODES"] if m["Tag"]}
        for card in self.src["CARDS"]:
            dev = card["Device"]
            expected = {}
            for r in card_rows(self.src, card):
                self.assertNotIn(r["Label"], expected, "%s %s is twice on the card" % (dev, r["Label"]))
                row = {"label": r["Label"], "primary": r["Primary"]}
                if r.get("Hint"):
                    row["hint"] = r["Hint"]
                if r.get("Unbound"):
                    row["unbound"] = True
                if r.get("Variants"):
                    for v in r["Variants"]:
                        self.assertIn(v["Tag"], mode_of, "variant tag %r is not in MODES" % v["Tag"])
                    row["variants"] = [{"mode": mode_of[v["Tag"]], "text": v["Text"]} for v in r["Variants"]]
                expected[r["Label"]] = row
            actual = {}
            for v in self.doc["views"]:
                if v["device"] != dev:
                    continue
                for r in v["rows"]:
                    self.assertNotIn(r["label"], actual, "%s %s is in rig.json twice" % (dev, r["label"]))
                    row = {k: x for k, x in r.items() if k not in ("status", "drawn_on")}
                    if "variants" in row:
                        row["variants"] = [{k: x for k, x in var.items() if k != "status"} for var in row["variants"]]
                    actual[r["label"]] = row
            self.assertEqual(actual, expected, "%s: rig.json rows differ from the card tables; %s" % (dev, REGEN))
            # Within a view the rows keep the card's order.
            order = {r["Label"]: i for i, r in enumerate(card_rows(self.src, card))}
            for v in self.doc["views"]:
                if v["device"] == dev:
                    idx = [order[r["label"]] for r in v["rows"]]
                    self.assertEqual(idx, sorted(idx), "%s rows out of card order; %s" % (v["id"], REGEN))

    def test_every_row_is_placed_in_a_view_that_draws_it(self):
        self.assertEqual([v["id"] for v in self.doc["views"]], [v["Id"] for v in self.src["VIEWS"]], REGEN)
        devices = {c["Device"] for c in self.src["CARDS"]}
        claimed = {}
        for v in self.src["VIEWS"]:
            self.assertIn(v["Device"], devices)
            for n in parse_buttons(v["Buttons"]) if v.get("Buttons") else ():
                self.assertNotIn((v["Device"], n), claimed, "button %s %d is in two views" % (v["Device"], n))
                claimed[(v["Device"], n)] = v["Id"]
        placed = 0
        for v in self.doc["views"]:
            src = self.views[v["id"]]
            self.assertEqual(v["device"], src["Device"])
            self.assertEqual(v.get("buttons"), src.get("Buttons"), REGEN)
            for r in v["rows"]:
                placed += 1
                nums = label_numbers(r["label"])
                if nums is None:
                    self.assertIn("Axes", src, "axis row %s is not in an axes view" % r["label"])
                    drawn = src["Axes"].get(r["label"])
                    self.assertEqual(r.get("drawn_on"), drawn, REGEN)
                    if drawn:
                        self.assertEqual(self.views[drawn]["Device"], src["Device"])
                        self.assertTrue(self.views[drawn]["File"], "%s is drawn on a view with no image" % r["label"])
                else:
                    self.assertTrue(src.get("Buttons"), "button row %s in a view without buttons" % r["label"])
                    self.assertLessEqual(nums, parse_buttons(src["Buttons"]),
                                         "%s %s is placed in %s, which does not draw it" % (v["device"], r["label"], v["id"]))
                    self.assertNotIn("drawn_on", r)
        total = sum(len(card_rows(self.src, c)) for c in self.src["CARDS"])
        self.assertEqual(placed, total, "rows missing from the views; " + REGEN)
        self.assertEqual(self.doc["_meta"]["counts"], {"rows": total, "views": len(self.src["VIEWS"])}, REGEN)

    def test_images_exist_with_the_stated_size(self):
        for v in self.doc["views"]:
            src = self.views[v["id"]]
            if not src["File"]:
                self.assertNotIn("image", v)
                continue
            self.assertEqual(v.get("image"), v["id"] + ".png", REGEN)
            path = RIG / v["image"]
            self.assertTrue(path.is_file(), "%s is missing; %s" % (v["image"], REGEN))
            w, h = png_size(path)
            self.assertEqual((w, h), (v["w"], v["h"]), "%s size differs from rig.json; %s" % (v["image"], REGEN))
            x0, y0, x1, y1 = src["Box"]
            # Trimmed to the art, never scaled up past the crop of the manufacturer's diagram.
            self.assertLessEqual(w, x1 - x0, v["image"])
            self.assertLessEqual(h, y1 - y0, v["image"])

    def test_meta_matches_the_current_sources(self):
        meta = self.doc["_meta"]
        self.assertEqual(meta["hash"]["tables"], digest({n: self.src[n] for n in SOURCES}),
                         "the card tables, CARDS, MODES, VIEWS or RIG_ART changed since rig.json was written; " + REGEN)
        files = sorted({v["File"] for v in self.src["VIEWS"] if v["File"]})
        art = {f: hashlib.sha256((DIAGRAMS / f).read_bytes()).hexdigest()[:12] for f in files}
        self.assertEqual(meta["hash"]["diagrams"], art, "a diagram in diagrams/ changed; " + REGEN)
        marks = sorted([d, l, m or "", s] for (d, l, m), s in expected_marks(self.src).items())
        self.assertEqual(meta["hash"]["marks"], digest(marks),
                         "the status marks in reference/controls.hand.json changed; " + REGEN)
        datetime.date.fromisoformat(meta["generated"])

    def test_status_marks_land_on_the_right_function(self):
        actual = {}
        for v in self.doc["views"]:
            for r in v["rows"]:
                if r.get("status"):
                    actual[(v["device"], r["label"], None)] = r["status"]
                for var in r.get("variants") or []:
                    if var.get("status"):
                        actual[(v["device"], r["label"], var["mode"])] = var["status"]
        self.assertEqual(actual, expected_marks(self.src), REGEN)
        self.assertLessEqual(set(actual.values()), set(STATUS_RANK))

    def test_the_folder_holds_only_the_named_files_within_size(self):
        named = {"rig.json"} | {v["image"] for v in self.doc["views"] if v.get("image")}
        present = {p.name for p in RIG.iterdir()}
        self.assertEqual(present, named, "dashboard/web/rig/ holds files rig.json does not name")
        for name in named:
            size = (RIG / name).stat().st_size
            limit = MAX_JSON if name.endswith(".json") else MAX_IMAGE
            self.assertGreaterEqual(size, 1, name)
            self.assertLessEqual(size, limit, "%s is %d bytes, over %d" % (name, size, limit))

    def test_no_local_path_in_rig_json(self):
        text = (RIG / "rig.json").read_text(encoding="utf-8")
        self.assertIsNone(re.search(r"[A-Za-z]:[\\/]|[\\/]Users[\\/]|[\\/]home[\\/]", text), "a local path in rig.json")


if __name__ == "__main__":
    unittest.main()
