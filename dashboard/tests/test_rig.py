"""The rig reference (dashboard/web/rig/) and the printed cards against what they are made from, and
the card tables against the profile.

tools/regen_cards.py writes rig.json and the eight view images in the same run that makes the printed
cards. This test reads that script with `ast` (it is never run for these checks, so neither Pillow nor
a browser is needed), MOZA.xml with ElementTree, the action catalog in reference/ as text, root
CLAUDE.md as text, the card SVGs with ElementTree and the PNGs with its own decoder, and checks:

  - the card tables against MOZA.xml: every joystick input the profile binds has a card row, every
    row not marked unbound names an input the profile binds (an unbound row none), and every row
    names the actions its wording describes, which must be the ones bound on its input in each mode;
  - the printed cards (cards/*.svg) against the tables, text by text;
  - every row, mode, device, view, status and disc in rig.json against the sources, worked out here
    again on its own, and the list of row ids against the list pinned below;
  - the images themselves: each PNG decodes, has the size and pixel hash rig.json gives it, shows no
    sample reading, and every disc still carries the name that was verified by eye (FINGERPRINTS);
  - every sentence a status or a mode rests on occurs exactly once in root CLAUDE.md or MOZA.xml, in
    the place the entry names, and the strips' statuses in reference/controls.hand.json agree;
  - with Pillow installed: rig.json and every PNG are byte for byte what the generator makes today.

When a source changed and the folder was not rewritten the fix is always the same:
    python tools/regen_cards.py --dashboard-only
(and the full `python tools/regen_cards.py` when a card row changed, for cards/).
"""
import ast
import datetime
import hashlib
import importlib.util
import json
import re
import struct
import unittest
import xml.etree.ElementTree as ET
import zlib
from collections import deque
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CARD_SCRIPT = ROOT / "tools" / "regen_cards.py"
RIG = ROOT / "dashboard" / "web" / "rig"
CARDS_DIR = ROOT / "cards"
DIAGRAMS = ROOT / "diagrams"
HAND = ROOT / "dashboard" / "reference" / "controls.hand.json"
PROFILE = ROOT / "MOZA.xml"
CLAUDE = ROOT / "CLAUDE.md"
CATALOG_DIR = ROOT / "reference"

TABLES = ("AB6", "MHG_L", "MHG_R", "MTQ_L", "MTQ_R")
SOURCES = TABLES + ("CARDS", "MODES", "LIVE_MODES", "MAPS", "STATUS", "STATUS_WORDS", "MODE_WORDS", "CARD_ART", "VIEWS",
                    "READINGS", "DISCS", "DISC_FINDER", "RIG_ART", "FINGERPRINTS")
SCHEMA = 2
REGEN = "rig reference is stale; run: python tools/regen_cards.py --dashboard-only"
REVERIFY = ("re-verify the disc names by eye: python tools/regen_cards.py --sheets <a folder outside the repo> "
            "writes a contact sheet per view; read every tile, fix DISCS where a name is wrong, then paste the "
            "output of python tools/regen_cards.py --fingerprints into FINGERPRINTS")

# The rows, by id, in card order. Pinned: a row taken out of the card tables and rig.json together
# (or one added) fails here until this list is changed on purpose.
ROW_IDS = (
    "js1-1 js1-2 js1-3 js1-4 js1-5 js1-6 js1-7 js1-8 js1-9 js1-10 js1-11 js1-12 js1-13 js1-14 js1-15 "
    "js1-x js1-y js1-rz js1-16 js1-17 js1-18 js1-19 js1-20 js1-21 js1-22 js1-23 js1-24 js1-25 js1-26 "
    "js1-27 js1-28 js1-29 js1-49 js1-50 js1-51 js1-52 js1-53 js1-54 js1-55 js1-56 js1-57-59 js1-60-62 "
    "js2-1 js2-2 js2-3 js2-4 js2-5 js2-6 js2-7 js2-8 js2-9 js2-10 js2-11 js2-12 js2-13 js2-14 js2-15 "
    "js2-16 js2-17 js2-18 js2-19 js2-20 js2-21 js2-22 js2-23 js2-24 js2-25 js2-26 js2-27 js2-28 js2-29 "
    "js2-30 js2-31-43 js2-49 js2-50 js2-51 js2-56 js2-55 js2-54 js2-53 js2-52 js2-61 js2-60 js2-59 "
    "js2-58 js2-57 js2-62 js2-63 js2-64 js2-65 js2-ry js2-z-rz js2-slider js2-dial js2-x-y js2-rx").split()

# MOZA's sample readings painted out of the screen art, pinned like the rows: a reading dropped from
# READINGS would otherwise come back on screen with the data regenerated to match.
READING_NAMES = ("Dial reading 65535", "RX reading 0", "RY reading 0", "Slider reading 65535", "Dial level bar, lit",
                 "Slider level bar, lit", "mini-stick reading 0, top", "mini-stick reading 0, left",
                 "mini-stick X reading 32767", "mini-stick Y reading 32767")
FIRST_DAY = "2026-11-27"          # the rig files' first day; `generated` cannot be earlier, nor after today

# The service hands these files out as they are, so they stay small. On 2026-11-28 the largest image
# was 15 KB and rig.json 90 KB; the limits leave room for more rows, not for a change of format (an
# 8-bit or upscaled image would cross them).
MAX_IMAGE = 40 * 1024
MAX_JSON = 160 * 1024
STATUSES = ("flown", "unverified", "trial")
DOUBT = {"flown": 0, None: 1, "unverified": 2, "trial": 3}
VALUES = ("primary", "variant", "none", "unknown")


# ---------------------------------------------------------------------------------------- sources
def read_script():
    """The module-level literals of regen_cards.py, read with ast. A V(tag, text, color) call is
    evaluated the way the script defines V. Also returns the script's rig code (see rig_code)."""
    text = CARD_SCRIPT.read_text(encoding="utf-8")
    tree = ast.parse(text)
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
            tag, text_, color = (ev(a) for a in n.args)
            return {"Tag": tag, "Text": text_, "Color": color}
        raise ValueError("not a literal, line %d" % getattr(n, "lineno", 0))

    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            name = node.targets[0].id
            try:
                env[name] = ev(node.value)
            except ValueError:
                if name in SOURCES:           # the data this test checks must stay plain literals
                    raise
    missing = [n for n in SOURCES + ("SOURCES", "RIG_SCHEMA") if n not in env]
    if missing:
        raise AssertionError("regen_cards.py no longer defines %s" % ", ".join(missing))
    env["_rig_code"] = rig_code(text)
    return env


def rig_code(text):
    """The script's lines from the "dashboard rig reference" heading to `def main`, as
    regen_cards.rig_code() takes them."""
    lines = text.split("\n")
    a = next(i for i, ln in enumerate(lines) if ln.startswith("# ====") and ln.endswith(" dashboard rig reference"))
    b = next(i for i, ln in enumerate(lines) if ln.startswith("def main("))
    return "\n".join(lines[a:b])


def digest(obj):
    """The same short hash regen_cards.digest() writes into _meta."""
    raw = json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:12]


def norm(text):
    """Text as a quote is matched against a file: ** and ` dropped, white space collapsed."""
    return re.sub(r"\s+", " ", text.replace("*", "").replace("`", "")).strip()


def claude_block(text, where):
    """The part of root CLAUDE.md a quote's In names: "§6" (section 6), "§2.4" (its subsection 2.4),
    "§6 item 20" (item 20 of section 6) or "§4 Mining" (the subsection of section 4 whose heading
    starts with "Mining"). Raises AssertionError when there is no such place."""
    m = re.fullmatch(r"§(\d+)(?:\.(\d+))?(?: item (\d+)| (.+))?", where)
    if not m:
        raise AssertionError("not a place in CLAUDE.md: %r" % where)
    lines = text.split("\n")
    sec = next((i for i, ln in enumerate(lines) if ln.startswith("## %s. " % m.group(1))), None)
    if sec is None:
        raise AssertionError("CLAUDE.md has no section %s" % m.group(1))
    end = next((i for i in range(sec + 1, len(lines)) if lines[i].startswith("## ")), len(lines))
    a, b = sec, end
    if m.group(2) or m.group(4):
        want = ("### %s.%s" % (m.group(1), m.group(2))) if m.group(2) else "### " + m.group(4)
        a = next((i for i in range(sec, end) if norm(lines[i]).startswith(norm(want))), None)
        if a is None:
            raise AssertionError("CLAUDE.md has no %r in section %s" % (want, m.group(1)))
        b = next((i for i in range(a + 1, end) if lines[i].startswith("### ")), end)
    elif m.group(3):
        a = next((i for i in range(sec, end) if re.match(r"%s\. " % m.group(3), lines[i])), None)
        if a is None:
            raise AssertionError("CLAUDE.md section %s has no item %s" % (m.group(1), m.group(3)))
        b = next((i for i in range(a + 1, end) if re.match(r"\d+\. ", lines[i])), end)
    return norm("\n".join(lines[a:b]))


def xml_comment_with(text, marker, quote):
    """The comments of MOZA.xml that hold quote and marker."""
    return [c for c in re.findall(r"<!--(.*?)-->", text, re.S) if norm(quote) in norm(c) and marker in c]


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


def row_inputs(dev, r):
    nums = label_numbers(r["Label"])
    return ["%s_button%d" % (dev, n) for n in sorted(nums)] if nums else list(r.get("Inputs") or [])


def row_id(dev, label):
    return dev + "-" + re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")


def read_profile():
    root = ET.parse(str(PROFILE)).getroot()
    binds, named = [], set()
    for am in root.iter("actionmap"):
        for a in am.findall("action"):
            named.add((am.get("name"), a.get("name")))
            for r in a.findall("rebind"):
                inp = r.get("input") or ""
                if re.fullmatch(r"[a-z]+\d+_\s*", inp):
                    continue
                binds.append((am.get("name"), a.get("name"), inp, r.get("activationMode")))
    return binds, named


def catalog_file():
    found = sorted(CATALOG_DIR.glob("SC_KEYBINDS_DATABASE_v*.md"),
                   key=lambda p: [int(x) for x in re.findall(r"\d+", p.stem)])
    return found[-1]


def read_catalog():
    out, amap = {}, None
    for line in catalog_file().read_text(encoding="utf-8").splitlines():
        m = re.match(r"## (\S+)\s*$", line)
        if m:
            amap = m.group(1)
            continue
        m = re.match(r"\| `([^`]+)` \|(.*)\|\s*$", line)
        if m and amap:
            cells = [c.strip() for c in m.group(2).split("|")]
            if len(cells) == 6:
                out[(amap, m.group(1))] = {"label": cells[0], "joystick": cells[3], "activation": cells[5]}
    return out


# ---------------------------------------------------------------------------------------- PNG
def read_png(path):
    """A PNG decoded with the standard library: (w, h, color type, data). Palette images: data =
    (palette index per pixel, [(r, g, b, a)] per entry); 8-bit RGBA: data = the RGBA bytes. Raises
    AssertionError on anything else or on a broken file (signature, CRC, IEND, short or extra data)."""
    data = path.read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise AssertionError("%s is not a PNG" % path.name)
    pos, chunks = 8, []
    while True:
        if pos + 12 > len(data):
            raise AssertionError("%s is cut short" % path.name)
        n, kind = struct.unpack(">I4s", data[pos:pos + 8])
        body, crc = data[pos + 8:pos + 8 + n], data[pos + 8 + n:pos + 12 + n]
        if len(body) != n or len(crc) != 4 or zlib.crc32(kind + body) & 0xFFFFFFFF != struct.unpack(">I", crc)[0]:
            raise AssertionError("%s: chunk %r is cut short or damaged" % (path.name, kind))
        chunks.append((kind, body))
        pos += 12 + n
        if kind == b"IEND":
            break
    if pos != len(data):
        raise AssertionError("%s has data after IEND" % path.name)
    head = dict(chunks)
    w, h, depth, ctype, _comp, _filt, interlace = struct.unpack(">IIBBBBB", head[b"IHDR"])
    if interlace or not ((ctype == 3 and depth in (1, 2, 4, 8)) or (ctype == 6 and depth == 8)):
        raise AssertionError("%s is not a non-interlaced palette or 8-bit RGBA PNG" % path.name)
    try:
        raw = zlib.decompress(b"".join(b for k, b in chunks if k == b"IDAT"))
    except zlib.error as e:
        raise AssertionError("%s: image data does not decompress (%s)" % (path.name, e))
    bpp_bits = depth * (4 if ctype == 6 else 1)
    stride, bpp = (w * bpp_bits + 7) // 8, max(1, bpp_bits // 8)
    if len(raw) != h * (stride + 1):
        raise AssertionError("%s: image data is %d bytes, not %d" % (path.name, len(raw), h * (stride + 1)))
    prev, rows = bytes(stride), []
    for y in range(h):
        f, line = raw[y * (stride + 1)], raw[y * (stride + 1) + 1:(y + 1) * (stride + 1)]
        if f == 0:
            cur = bytes(line)
        elif f == 2:
            cur = bytes((x + p) & 255 for x, p in zip(line, prev))
        elif f in (1, 3, 4):
            cur = bytearray(line)
            for i in range(stride):
                a = cur[i - bpp] if i >= bpp else 0
                if f == 1:
                    cur[i] = (cur[i] + a) & 255
                elif f == 3:
                    cur[i] = (cur[i] + (a + prev[i]) // 2) & 255
                else:
                    b, c = prev[i], (prev[i - bpp] if i >= bpp else 0)
                    pr = a + b - c
                    pa, pb, pc = abs(pr - a), abs(pr - b), abs(pr - c)
                    cur[i] = (cur[i] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 255
            cur = bytes(cur)
        else:
            raise AssertionError("%s: unknown filter %d" % (path.name, f))
        rows.append(cur)
        prev = cur
    if ctype == 6:
        return w, h, 6, b"".join(rows)
    plte, trns = head[b"PLTE"], head.get(b"tRNS", b"")
    pal = [(plte[i], plte[i + 1], plte[i + 2], trns[i // 3] if i // 3 < len(trns) else 255)
           for i in range(0, len(plte), 3)]
    per, mask, idx = 8 // depth, (1 << depth) - 1, []
    for line in rows:
        row = []
        for byte in line:
            for k in range(per):
                row.append((byte >> (8 - depth * (k + 1))) & mask)
        idx.extend(row[:w])
    if max(idx) >= len(pal):
        raise AssertionError("%s uses a palette entry it does not have" % path.name)
    return w, h, 3, (idx, pal)


def pixel_hash(w, h, idx, pal):
    """The same hash regen_cards.pixel_hash() writes: the pixels as RGBA, with the size."""
    rgba = bytes(c for i in idx for c in pal[i])
    return hashlib.sha256(b"%dx%d:" % (w, h) + rgba).hexdigest()[:16]


def fingerprint(w, rgba, box):
    """regen_cards.fingerprint(): a short hash of an RGBA image's pixels inside box."""
    x0, y0, x1, y1 = box
    crop = b"".join(rgba[(y * w + x0) * 4:(y * w + x1) * 4] for y in range(y0, y1))
    return hashlib.sha256(b"%dx%d:" % (x1 - x0, y1 - y0) + crop).hexdigest()[:10]


# ------------------------------------------------------------------- the disc finder, on bitsets
def _mask(levels, w, h, lo):
    rows = []
    for y in range(h):
        r = 0
        for x, t in enumerate(levels[y * w:(y + 1) * w]):
            if t >= lo:
                r |= 1 << x
        rows.append(r)
    return rows


def _dilate(rows, k, w):
    full, h = (1 << w) - 1, len(rows)
    hor = []
    for r in rows:
        o = r
        for s in range(1, k + 1):
            o |= (r << s) | (r >> s)
        hor.append(o & full)
    out = []
    for y in range(h):
        o = 0
        for yy in range(max(0, y - k), min(h, y + k + 1)):
            o |= hor[yy]
        out.append(o)
    return out


def _erode(rows, k, w):
    full, h = (1 << w) - 1, len(rows)
    hor = []
    for r in rows:
        o = r
        for s in range(1, k + 1):
            o &= ((r << s) & full) & (r >> s)
        hor.append(o)
    out = []
    for y in range(h):
        o = full
        for dy in range(-k, k + 1):
            o &= hor[y + dy] if 0 <= y + dy < h else 0
        out.append(o)
    return out


def _fill(rows, w):
    full, h = (1 << w) - 1, len(rows)
    inv = [(~r) & full for r in rows]
    edge = 1 | (1 << (w - 1))
    out = [inv[y] if y in (0, h - 1) else inv[y] & edge for y in range(h)]
    changed = True
    while changed:
        changed = False
        for y in range(h):
            o = out[y]
            n = (o | (o << 1) | (o >> 1) | (out[y - 1] if y else 0) | (out[y + 1] if y < h - 1 else 0)) & inv[y]
            if n != o:
                out[y], changed = n, True
    return [(~o) & full for o in out]


def find_discs(levels, w, h, f):
    """The number discs of an image, as regen_cards.find_discs() finds them (DISC_FINDER = f)."""
    m = _mask(levels, w, h, f["Level"])
    m = _erode(_dilate(m, f["Close"], w), f["Close"], w)
    m = _fill(m, w)
    m = _dilate(_erode(m, f["Open"], w), f["Open"], w)
    seen, found = set(), []
    for y in range(h):
        for x in range(w):
            if not (m[y] >> x & 1) or (x, y) in seen:
                continue
            seen.add((x, y))
            q, pts = deque([(x, y)]), []
            while q:
                cx, cy = q.popleft()
                pts.append((cx, cy))
                for nx, ny in ((cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)):
                    if 0 <= nx < w and 0 <= ny < h and (nx, ny) not in seen and m[ny] >> nx & 1:
                        seen.add((nx, ny))
                        q.append((nx, ny))
            xs, ys = [p[0] for p in pts], [p[1] for p in pts]
            bx, by, bw, bh = min(xs), min(ys), max(xs) - min(xs) + 1, max(ys) - min(ys) + 1
            lo, hi = f["Size"]
            if lo <= bw <= hi and lo <= bh <= hi and f["Aspect"][0] <= bw / bh <= f["Aspect"][1] \
                    and len(pts) >= f["Fill"] * bw * bh:
                dark = [py for px_, py in pts if levels[py * w + px_] <= f["Dark"]]
                cx, cy, rr = bx + bw / 2, by + bh / 2, max(bw, bh) / 2 + f["Round"]
                box = any((px_ + 0.5 - cx) ** 2 + (py + 0.5 - cy) ** 2 > rr * rr for px_, py in pts)
                found.append((bx, by, bw, bh, max(dark) - min(dark) + 1 if dark else 0, box))
    return sorted(found, key=lambda d: (d[1], d[0]))


def jnum(n):
    return int(n) if float(n).is_integer() else n


# ---------------------------------------------------------------------------------------- tests
class RigReferenceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.src = read_script()
        path = RIG / "rig.json"
        if not path.is_file():
            raise AssertionError("dashboard/web/rig/rig.json is missing; " + REGEN)
        cls.doc = json.loads(path.read_text(encoding="utf-8"))
        cls.binds, cls.named = read_profile()
        cls.catalog = read_catalog()
        cls.views = {v["Id"]: v for v in cls.src["VIEWS"]}
        cls.rows = {r["id"]: r for r in cls.doc["rows"]}
        cls.modes = [m["Mode"] for m in cls.src["MODES"]]
        cls.mode_of = {m["Tag"]: m["Mode"] for m in cls.src["MODES"] if m["Tag"]}
        cls.pngs = {}
        for v in cls.doc.get("views", []):
            p = RIG / v.get("image", "")
            if p.is_file():
                try:
                    cls.pngs[v["id"]] = read_png(p)
                except AssertionError as e:
                    cls.pngs[v["id"]] = e
        cls.claude = CLAUDE.read_text(encoding="utf-8")
        cls.claude_norm = norm(cls.claude)
        cls.xml_text = PROFILE.read_text(encoding="utf-8")

    def png(self, view_id):
        got = self.pngs.get(view_id)
        if isinstance(got, Exception):
            self.fail("%s; %s" % (got, REGEN))
        self.assertIsNotNone(got, "%s has no image; %s" % (view_id, REGEN))
        self.assertEqual(got[2], 3, "a rig image is a palette PNG")
        return got[0], got[1], got[3][0], got[3][1]

    def levels(self, view_id):
        w, h, idx, pal = self.png(view_id)
        n = self.src["RIG_ART"]["Levels"]
        return [round(pal[i][3] * (n - 1) / 255) for i in idx]

    def check_quote(self, q_file, where, text):
        """A quote occurs exactly once in its file and sits in the place it names."""
        if q_file == "CLAUDE.md":
            self.assertEqual(self.claude_norm.count(norm(text)), 1,
                             "the quote must occur exactly once in root CLAUDE.md: %s" % text)
            self.assertIn(norm(text), claude_block(self.claude, where), "the quote is not in %s: %s" % (where, text))
        else:
            self.assertEqual(q_file, "MOZA.xml")
            self.assertEqual(norm(self.xml_text).count(norm(text)), 1, "the quote must occur once in MOZA.xml: %s" % text)
            self.assertEqual(len(xml_comment_with(self.xml_text, where, text)), 1,
                             "the quote is not in the MOZA.xml comment %r: %s" % (where, text))
        self.assertRegex(norm(text), r"[.!?][)\"]?$", "a quote is a whole sentence (it ends one): %s" % text)
        i = self.claude_norm.find(norm(text)) if q_file == "CLAUDE.md" else -1
        if i > 0:
            self.assertIn(self.claude_norm[i - 1], " |>-", "a quote is a whole sentence (it starts one): %s" % text)

    # ------------------------------------------------------------------ the card tables vs MOZA.xml
    def test_card_tables_against_the_profile(self):
        """Every joystick input MOZA.xml binds has a card row; every row not marked unbound names an
        input the profile binds; an unbound row names none. Read from the tables, not from rig.json."""
        bound = {b[2] for b in self.binds}
        named = {}
        for card in self.src["CARDS"]:
            dev = card["Device"]
            for r in card_rows(self.src, card):
                inputs = row_inputs(dev, r)
                with self.subTest(row="%s %s" % (dev, r["Label"])):
                    self.assertTrue(inputs, "the row names no input")
                    if label_numbers(r["Label"]):
                        self.assertNotIn("Inputs", r, "a button row with Inputs")
                    for i in inputs:
                        self.assertRegex(i, r"^%s_" % dev)
                        self.assertNotIn(i, named, "%s is on two card rows" % i)
                        named[i] = r["Label"]
                    hit = sorted(set(inputs) & bound)
                    if r.get("Unbound"):
                        self.assertEqual(hit, [], "marked unbound, but MOZA.xml binds %s" % hit)
                    else:
                        self.assertTrue(hit, "has a function, but MOZA.xml binds none of %s" % inputs)
        for inp in sorted(bound):
            with self.subTest(input=inp):
                self.assertIn(inp, named, "MOZA.xml binds %s, which no card row names" % inp)

    def test_each_row_names_the_actions_bound_to_it(self):
        """A row's wording is about the actions it names (Actions, and VariantActions per card
        variant); MOZA.xml must bind exactly those on its inputs, in the maps of those modes. Catches
        two actions swapped in the profile under unchanged card wording."""
        maps = self.src["MAPS"]
        for card in self.src["CARDS"]:
            dev = card["Device"]
            for r in card_rows(self.src, card):
                with self.subTest(row="%s %s" % (dev, r["Label"])):
                    vmodes = [self.mode_of[v["Tag"]] for v in r.get("Variants") or []]
                    self.assertIn("Actions", r, "every row names its actions (none: [])")
                    self.assertEqual(sorted(r.get("VariantActions") or {}), sorted(vmodes))
                    inputs = row_inputs(dev, r)
                    on = [(amap, action) for amap, action, inp, _ in self.binds if inp in inputs]
                    want = {}
                    for amap, action in on:
                        spec = maps[amap]
                        gated = spec["Live"][0] if len(spec["Live"]) == 1 and not spec["Unknown"] else None
                        want.setdefault(gated if gated in vmodes else "primary", []).append(action)
                    said = {"primary": r["Actions"]}
                    said.update(r.get("VariantActions") or {})
                    self.assertEqual({k: sorted(v) for k, v in said.items() if v},
                                     {k: sorted(v) for k, v in want.items()},
                                     "the card's actions differ from what MOZA.xml binds on %s" % ", ".join(inputs))
                    if r.get("Jobs"):
                        self.assertEqual(sorted(a for j in r["Jobs"] for a in j["Actions"]), sorted(r["Actions"]))

    def test_the_printed_cards_say_what_the_tables_say(self):
        """cards/*.svg hold every row as <text>: the badge label, the primary with its hint, the
        variants, the column headings, between the card's title, subheading, captions and legend.
        Catches a card row edited and only --dashboard-only run."""
        captions = {v["Caption"] for v in self.src["CARD_ART"] if v["Caption"]}
        cols = {"MOZA_MHG_AB6_ref": [["MHG_L"], ["MHG_R", "AB6"]], "MOZA_MTQ_ref": [["MTQ_L"], ["MTQ_R"]]}
        for card in self.src["CARDS"]:
            with self.subTest(card=card["Name"]):
                svg = CARDS_DIR / (card["Name"] + ".svg")
                self.assertTrue(svg.is_file(), "%s is missing" % svg.name)
                texts = ["".join(t.itertext()) for t in ET.parse(str(svg)).getroot().iter("{http://www.w3.org/2000/svg}text")]
                self.assertEqual(texts[:2], [card["Title"], card["Sub"]], "the card's heading")
                self.assertEqual(texts[-1], card["Legend"], "the card's footer")
                body = [t for t in texts[2:-1] if t not in captions]
                expected = []
                self.assertEqual(sum(cols[card["Name"]], []), card["Tables"])
                for col in cols[card["Name"]]:
                    for r in (row for t in col for row in self.src[t]):
                        if "Header" in r:
                            expected.append(r["Header"])
                            continue
                        expected.append(r["Label"])
                        expected.append(r["Primary"] + ("  (%s)" % r["Hint"] if r.get("Hint") else ""))
                        if r.get("Variants"):
                            expected.append("     ".join("%s %s" % (v["Tag"], v["Text"]) for v in r["Variants"]))
                self.assertEqual(body, expected, "cards/%s.svg is stale: run python tools/regen_cards.py" % card["Name"])

    # ------------------------------------------------------------------ meta
    def test_meta_matches_the_current_sources(self):
        meta = self.doc["_meta"]
        self.assertEqual(meta["schema"], SCHEMA, REGEN)
        self.assertEqual(self.src["RIG_SCHEMA"], SCHEMA)
        self.assertEqual(list(self.src["SOURCES"]), list(SOURCES), "regen_cards.SOURCES changed; update this test")
        h = meta["hash"]
        self.assertEqual(sorted(h), ["catalog", "code", "diagrams", "profile", "tables"])
        self.assertEqual(h["tables"], digest({n: self.src[n] for n in SOURCES}),
                         "the card tables or the literals after them changed since rig.json was written; " + REGEN)
        self.assertEqual(h["code"], digest(self.src["_rig_code"]),
                         "the code that makes the rig files changed; " + REGEN)
        files = sorted({v["File"] for v in self.src["VIEWS"]})
        art = {f: hashlib.sha256((DIAGRAMS / f).read_bytes()).hexdigest()[:12] for f in files}
        self.assertEqual(h["diagrams"], art, "a diagram in diagrams/ changed; " + REGEN)
        self.assertEqual(h["profile"], digest(sorted([list(b) for b in self.binds], key=str)),
                         "the bindings in MOZA.xml changed; " + REGEN)
        used = sorted([k[0], k[1], e["label"], e["joystick"], e["activation"]]
                      for k, e in self.catalog.items() if k[0] in self.src["MAPS"])
        self.assertEqual(h["catalog"], digest(used), "the action catalog changed; " + REGEN)
        self.assertEqual(meta["catalog"], "reference/" + catalog_file().name, REGEN)
        day = datetime.date.fromisoformat(meta["generated"])
        self.assertTrue(datetime.date.fromisoformat(FIRST_DAY) <= day <= datetime.date.today(),
                        "generated %s is not a day the files can have been made on" % day)
        self.assertEqual(set(meta["status"]), set(STATUSES) | {"missing"})
        counts = meta["counts"]
        self.assertEqual(counts["rows"], len(self.doc["rows"]))
        self.assertEqual(counts["rows"], len(ROW_IDS))
        self.assertEqual(counts["views"], len(self.doc["views"]))
        self.assertEqual(counts["discs"], sum(1 for r in self.doc["rows"] for d in r["discs"] if d["n"] is not None))
        self.assertEqual(counts["discs"], sum(len(v["buttons"]) for v in self.doc["views"]))

    # ------------------------------------------------------------------ rows
    def test_rows_match_the_card_tables(self):
        expected_ids = []
        for card in self.src["CARDS"]:
            dev = card["Device"]
            for r in card_rows(self.src, card):
                rid = row_id(dev, r["Label"])
                expected_ids.append(rid)
                with self.subTest(row=rid):
                    self.assertIn(rid, self.rows, REGEN)
                    row = self.rows[rid]
                    nums = label_numbers(r["Label"])
                    self.assertEqual((row["device"], row["label"]), (dev, r["Label"]))
                    self.assertEqual(row["buttons"], sorted(nums) if nums else [])
                    self.assertTrue(all(type(b) is int for b in row["buttons"]))
                    self.assertEqual(row["inputs"], row_inputs(dev, r))
                    self.assertEqual(row["text"], r["Screen"], REGEN)
                    self.assertEqual(row["where"], r["Where"], REGEN)
                    self.assertEqual(row["group"], r["Group"], REGEN)
                    self.assertRegex(row["group"], r"^[A-Za-z][A-Za-z -]*[A-Za-z]$")
                    self.assertEqual(row.get("unbound", False), bool(r.get("Unbound")))
                    card_w = {"primary": r["Primary"]}
                    if r.get("Hint"):
                        card_w["hint"] = r["Hint"]
                    self.assertEqual(row["card"], card_w, REGEN)
                    vs = [{"mode": self.mode_of[v["Tag"]], "text": r["ScreenVariants"][self.mode_of[v["Tag"]]],
                           "card": v["Text"]} for v in r.get("Variants") or []]
                    got = [{k: x for k, x in v.items() if k in ("mode", "text", "card")} for v in row.get("variants", [])]
                    self.assertEqual(got, vs, REGEN)
                    self.assertEqual(sorted(r.get("ScreenVariants") or {}), sorted(v["mode"] for v in vs))
                    words = [row["text"], row["where"]] + [v["text"] for v in vs] + [j["text"] for j in row.get("jobs", [])]
                    for w in words:
                        self.assertNotRegex(w, r"(?i)\b(trial|unverified|flown)\b", "a status word in the screen wording")
                    if r.get("Jobs"):
                        self.assertEqual([(j["press"], j["text"], j["actions"]) for j in row["jobs"]],
                                         [(j["Press"], j["Screen"], j["Actions"]) for j in r["Jobs"]], REGEN)
                        maps = self.src["MAPS"]
                        for j in row["jobs"]:
                            jm = [maps[a["map"]] for a in row["actions"] if a["action"] in j["actions"] and not a.get("stock")]
                            self.assertTrue(jm, "a job with no MOZA.xml action")
                            self.assertEqual(j["modes"], {m: "live" if any(m in x["Live"] for x in jm) else
                                                          "unknown" if any(m in x["Unknown"] for x in jm) else "none"
                                                          for m in self.modes}, REGEN)
                    else:
                        self.assertNotIn("jobs", row)
        self.assertEqual([r["id"] for r in self.doc["rows"]], expected_ids, "rows missing, extra or out of card order; " + REGEN)
        self.assertEqual(len(set(expected_ids)), len(expected_ids), "two rows with one id")
        self.assertEqual(expected_ids, ROW_IDS, "the card rows are not the ones pinned in ROW_IDS (a row added or "
                                                "taken out: change ROW_IDS on purpose)")
        for rid in expected_ids:
            self.assertRegex(rid, r"^js\d+-[a-z0-9]+(-[a-z0-9]+)*$")

    def test_every_row_is_on_the_view_that_draws_it(self):
        claimed = {}
        for v in self.src["VIEWS"]:
            for n in parse_buttons(v["Buttons"]):
                self.assertNotIn((v["Device"], n), claimed, "button %s %d is claimed by two views" % (v["Device"], n))
                claimed[(v["Device"], n)] = v["Id"]
        for row in self.doc["rows"]:
            with self.subTest(row=row["id"]):
                if row["buttons"]:
                    homes = {claimed.get((row["device"], n)) for n in row["buttons"]}
                    self.assertEqual(homes, {row["view"]}, REGEN)
                    self.assertTrue(row["drawn"])
                else:
                    homes = [v["Id"] for v in self.src["VIEWS"] if v["Device"] == row["device"] and row["label"] in v["Axes"]]
                    self.assertEqual(homes, [row["view"]], "an axis row needs exactly one home view; " + REGEN)
                    self.assertEqual(row["drawn"], self.views[row["view"]]["Axes"][row["label"]] is not None)
                self.assertEqual(self.views[row["view"]]["Device"], row["device"])

    # ------------------------------------------------------------------ modes
    def expected_actions(self, row_src, dev):
        """The actions on a row's inputs, worked out from MOZA.xml, the catalog and MAPS."""
        maps = self.src["MAPS"]
        vmodes = [self.mode_of[v["Tag"]] for v in row_src.get("Variants") or []]
        out = []
        for inp in row_inputs(dev, row_src):
            here = []
            for amap, action, i, mode in self.binds:
                if i == inp:
                    e = self.catalog[(amap, action)]
                    here.append({"map": amap, "action": action, "label": e["label"], "activation": mode or e["activation"] or None})
            for (amap, action), e in sorted(self.catalog.items()):
                if amap in maps and e["joystick"] and (amap, action) not in self.named \
                        and re.fullmatch(r"[a-z]+\d*(?:_[a-z]+)?", e["joystick"]) and "js1_" + e["joystick"] == inp:
                    here.append({"map": amap, "action": action, "label": e["label"], "activation": e["activation"] or None, "stock": True})
            for a in here:
                spec = maps[a["map"]]
                gated = spec["Live"][0] if len(spec["Live"]) == 1 and not spec["Unknown"] else None
                out.append(dict({"part": gated if gated in vmodes else "primary"}, **a))
        return out

    def test_modes_knob_and_page_filters(self):
        knob = {}
        for amap, action, inp, _ in self.binds:
            knob.setdefault(action, []).append(inp)
        got = self.doc["modes"]
        self.assertEqual([m["id"] for m in got], self.modes, REGEN)
        for m, src in zip(got, self.src["MODES"]):
            with self.subTest(mode=m["id"]):
                self.assertEqual((m["name"], m["operator"], m["tag"]), (src["Name"], src["Operator"], src["Tag"]), REGEN)
                self.assertEqual(len(knob.get(src["Set"], [])), 1, "%s is not on one input in MOZA.xml" % src["Set"])
                dev, _, n = knob[src["Set"]][0].partition("_button")
                self.assertEqual(m["knob"], {"device": dev, "button": int(n), "detent": src["Detent"],
                                             "row": "%s-%s" % (dev, n)}, REGEN)
                self.assertTrue(self.rows[m["knob"]["row"]]["card"]["hint"].endswith("knob detent %d" % src["Detent"]),
                                "the card row of the knob detent says another detent")
        lm = self.doc["live_modes"]
        self.assertEqual(lm, self.src["LIVE_MODES"], REGEN)
        self.assertEqual(set(lm), {"flight", "mining", "salvage"}, "dashboard/STATE.md: view.mode is flight, mining or salvage")
        for k, v in lm.items():
            self.assertTrue(v and set(v) <= set(self.modes) and len(set(v)) == len(v), k)
        self.assertEqual(lm["flight"][0], "combat", "the Flight filter's own mode is combat (guns)")
        self.assertEqual(sorted(m for v in lm.values() for m in v), sorted(self.modes), "every mode is under one filter")

    def test_maps_say_where_each_actionmap_is_live(self):
        maps = self.src["MAPS"]
        for amap, action, inp, _ in self.binds:
            self.assertIn(amap, maps, "MOZA.xml binds %s/%s; MAPS has no %s" % (amap, action, amap))
        self.assertEqual(sorted(self.doc["maps"]), sorted(maps), REGEN)
        for name, spec in maps.items():
            with self.subTest(map=name):
                live, unknown = spec["Live"], spec["Unknown"]
                self.assertFalse(set(live) & set(unknown))
                self.assertLessEqual(set(live) | set(unknown), set(self.modes))
                dead = [m for m in self.modes if m not in live and m not in unknown]
                got = self.doc["maps"][name]
                self.assertEqual((got["live"], got["unknown"], got["dead"]), (live, unknown, dead), REGEN)
                self.assertEqual(got["why"], [{"file": q["File"], "ref": q["In"], "text": q["Text"]} for q in spec["Why"]], REGEN)
                self.assertEqual(got.get("note"), spec.get("Note"), REGEN)
                if live or dead:
                    self.assertTrue(spec["Why"], "a map said to be live or dead somewhere must cite why")
                words = self.src["MODE_WORDS"]
                for mode in live + dead:
                    kind = "live" if mode in live else "dead"
                    self.assertTrue(any(re.search(words[mode], q["Text"]) or re.search(words[kind], q["Text"])
                                        for q in spec["Why"]),
                                    "no quote names %s mode, or says why the map is %s everywhere" % (mode, kind))
                if unknown:
                    self.assertTrue(spec.get("Note"), "an unknown cell says why in Note")
                for q in spec["Why"]:
                    self.check_quote(q["File"], q["In"], q["Text"])

    def test_each_row_says_what_it_does_in_each_mode(self):
        maps = self.src["MAPS"]
        for card in self.src["CARDS"]:
            dev = card["Device"]
            for r in card_rows(self.src, card):
                rid = row_id(dev, r["Label"])
                row = self.rows[rid]
                with self.subTest(row=rid):
                    acts = self.expected_actions(r, dev)
                    self.assertEqual(row["actions"], acts, REGEN)
                    prim = [a for a in acts if a["part"] == "primary" and maps[a["map"]]["Live"]]
                    for i, a1 in enumerate(prim):
                        for a2 in prim[i + 1:]:
                            self.assertTrue(set(maps[a1["map"]]["Live"]) & set(maps[a2["map"]]["Live"]),
                                            "%s and %s act in different modes under one primary: the card needs a variant"
                                            % (a1["action"], a2["action"]))
                    vmodes = [self.mode_of[v["Tag"]] for v in r.get("Variants") or []]
                    expected = {}
                    for m in self.modes:
                        live = {a["part"] for a in acts if m in maps[a["map"]]["Live"]}
                        unknown = {a["part"] for a in acts if m in maps[a["map"]]["Unknown"]}
                        self.assertLessEqual(len(live), 1, "two jobs live in %s mode on one press" % m)
                        expected[m] = ("variant" if m in live else "primary") if live else ("unknown" if unknown else "none")
                    self.assertEqual(row["modes"], expected, REGEN)
                    self.assertEqual(list(row["modes"]), self.modes)
                    self.assertLessEqual(set(row["modes"].values()), set(VALUES))
                    for m in vmodes:
                        self.assertEqual(row["modes"][m], "variant", "the %s variant does not act in %s mode" % (m, m))
                    if row.get("unbound"):
                        self.assertEqual(set(row["modes"].values()), {"none"})

    # ------------------------------------------------------------------ statuses
    def test_statuses_come_from_STATUS_and_cite_the_docs(self):
        table = {}
        for s in self.src["STATUS"]:
            key = (s["Control"], s["Part"], s.get("Press"))
            with self.subTest(status=key):
                self.assertNotIn(key, table, "twice in STATUS")
                self.assertIn(s["Status"], STATUSES)
                self.assertNotIn("Said", s, "a status rests on root CLAUDE.md, not on a report kept here")
                self.assertTrue(s.get("Quote"), "a status quotes the docs")
                for q in s["Quote"]:
                    self.check_quote("CLAUDE.md", q["In"], q["Text"])
                self.assertTrue(any(re.search(self.src["STATUS_WORDS"][s["Status"]], q["Text"]) for q in s["Quote"]),
                                "none of the quotes says %s" % s["Status"])
                for other in STATUSES:
                    if other != s["Status"] and other == "trial":
                        self.assertFalse(any(re.search(self.src["STATUS_WORDS"]["trial"], q["Text"]) for q in s["Quote"]),
                                         "a quote calls it a trial, the status says %s" % s["Status"])
                if s.get("When"):
                    self.assertTrue(any(s["When"] in claude_block(self.claude, q["In"]) for q in s["Quote"]),
                                    "When is not in the place a quote sits: %s" % s["When"])
            table[key] = s

        def expect(e, s):
            want = (s["Status"], "; ".join(dict.fromkeys(q["In"] for q in s["Quote"])), s.get("When")) if s else (None, None, None)
            self.assertEqual((e.get("status"), e.get("status_ref"), e.get("status_when")), want, REGEN)

        used = set()
        for row in self.doc["rows"]:
            control = "%s %s" % (row["device"], row["label"])
            with self.subTest(row=row["id"]):
                if row.get("jobs"):
                    whole = table.get((control, None, None))
                    if whole:
                        used.add((control, None, None))
                    for j in row["jobs"]:
                        s = table.get((control, None, j["press"]))
                        if s:
                            used.add((control, None, j["press"]))
                        expect(j, s or whole)
                    worst = max((j.get("status") for j in row["jobs"]), key=lambda x: DOUBT[x])
                    self.assertEqual(row.get("status"), worst, "a row's status is the more doubtful of its jobs'")
                    if whole:
                        expect(row, whole)
                    else:
                        self.assertNotIn("status_ref", row)
                else:
                    s = table.get((control, None, None))
                    if s:
                        used.add((control, None, None))
                    expect(row, s)
                for v in row.get("variants", []):
                    s = table.get((control, v["mode"], None))
                    if s:
                        used.add((control, v["mode"], None))
                    expect(v, s)
                if row.get("unbound"):
                    self.assertNotIn("status", row)
        self.assertEqual(set(table) - used, set(), "STATUS entries that match no function on the cards")
        n = {}
        for row in self.doc["rows"]:
            for s in [row.get("status")] + [v.get("status") for v in row.get("variants", [])]:
                n[s or "none"] = n.get(s or "none", 0) + 1
        self.assertEqual(self.doc["_meta"]["counts"]["status"], dict(sorted(n.items())), REGEN)

    def test_the_strips_agree_with_the_rig(self):
        """reference/controls.hand.json marks the controls the activity strips show; each mark (or its
        absence) is the rig's status for the same function, so the two cannot drift apart."""
        hand = json.loads(HAND.read_text(encoding="utf-8"))
        by_ref = {"%s %s" % (r["device"], r["label"]): r for r in self.doc["rows"]}
        for mode, m in sorted(hand["modes"].items()):
            for it in m["items"]:
                variant = it.get("variant", m.get("variant"))
                for ref in it["controls"]:
                    with self.subTest(strip=mode, control=ref, where=it["where"]):
                        row = by_ref[ref]
                        var = next((v for v in row.get("variants", []) if v["mode"] == variant), None)
                        if var is not None:
                            self.assertNotIn("press", it)
                            got = [var.get("status")]
                        elif it.get("press"):
                            got = [j.get("status") for j in row.get("jobs", []) if j["press"] == it["press"]]
                            self.assertEqual(len(got), 1, "%s has no %s job" % (ref, it["press"]))
                        elif row.get("jobs"):
                            got = sorted({j.get("status") for j in row["jobs"]}, key=str)
                        else:
                            got = [row.get("status")]
                        self.assertEqual(got, [it.get("status")],
                                         "the strip says %r, the rig %r (STATUS in tools/regen_cards.py)" % (it.get("status"), got))

    # ------------------------------------------------------------------ devices and views
    def test_devices_and_views(self):
        devs = [c["Device"] for c in self.src["CARDS"]]
        self.assertEqual([d["id"] for d in self.doc["devices"]], devs, REGEN)
        for d, c in zip(self.doc["devices"], self.src["CARDS"]):
            self.assertEqual((d["name"], d["product"], d["title"], d["sub"], d["legend"]),
                             (c["Screen"], c["Product"], c["Title"], c["Sub"], c["Legend"]), REGEN)
            self.assertNotIn("notes", d, "notes are per view")
            self.assertEqual(d["views"], [v["Id"] for v in self.src["VIEWS"] if v["Device"] == c["Device"]], REGEN)
            for note in c["Notes"]:
                self.assertRegex(note["Text"], r"^[A-Z].*\.$", "a note is one or more whole sentences")
                self.assertNotRegex(note["Text"], r"(Msl|Mine|Salv):", "the tag key stays on the card")
                self.assertTrue(note["Views"])
                for vid in note["Views"]:
                    self.assertEqual(self.views[vid]["Device"], c["Device"], "a note on another device's view")
        self.assertEqual([v["id"] for v in self.doc["views"]], [v["Id"] for v in self.src["VIEWS"]], REGEN)
        self.assertEqual(len(self.doc["views"]), 8)
        titles = [v["title"] for v in self.doc["views"]]
        self.assertEqual(len(set(titles)), len(titles), "two views with one title")
        for v in self.doc["views"]:
            src = self.views[v["id"]]
            with self.subTest(view=v["id"]):
                self.assertRegex(v["id"], r"^[a-z0-9_]+$", "the service serves only such names")
                self.assertEqual((v["device"], v["title"], v["caption"]), (src["Device"], src["Title"], src["Caption"]), REGEN)
                self.assertEqual(v["buttons"], sorted(parse_buttons(src["Buttons"])), REGEN)
                self.assertEqual(v["rows"], [r["id"] for r in self.doc["rows"] if r["view"] == v["id"]], REGEN)
                self.assertTrue(v["rows"])
                notes = [n["Text"] for c in self.src["CARDS"] for n in c["Notes"] if v["id"] in n["Views"]]
                self.assertEqual(v["notes"], notes, REGEN)

    def test_images_are_the_ones_rig_json_names(self):
        for v in self.doc["views"]:
            src = self.views[v["id"]]
            with self.subTest(view=v["id"]):
                self.assertEqual(v["image"], v["id"] + ".png", REGEN)
                w, h, idx, pal = self.png(v["id"])
                self.assertEqual((w, h), (v["w"], v["h"]), "%s size differs from rig.json; %s" % (v["image"], REGEN))
                self.assertEqual(pixel_hash(w, h, idx, pal), v["hash"],
                                 "%s is not the image rig.json was written with; %s" % (v["image"], REGEN))
                color = self.src["RIG_ART"]["Color"]
                rgb = tuple(int(color[i:i + 2], 16) for i in (1, 3, 5))
                self.assertEqual({p[:3] for p in pal}, {rgb}, "one color in opacity steps")
                x0, y0, x1, y1 = src["Box"]
                bx0, by0, bx1, by1 = v["source"]["box"]
                self.assertEqual(v["source"]["diagram"] + ".png", src["File"])
                self.assertEqual((bx1 - bx0, by1 - by0), (w, h))
                # trimmed to the art, never scaled: the image is a part of the view's crop
                self.assertTrue(x0 <= bx0 and y0 <= by0 and bx1 <= x1 and by1 <= y1, "the image is not inside its crop")

    def test_the_folder_holds_only_the_named_files_within_size(self):
        named = {"rig.json", ".gitattributes"} | {v["image"] for v in self.doc["views"]}
        present = {p.name for p in RIG.iterdir()}
        self.assertEqual(present, named, "dashboard/web/rig/ holds files rig.json does not name")
        for name in named - {".gitattributes"}:
            size = (RIG / name).stat().st_size
            limit = MAX_JSON if name.endswith(".json") else MAX_IMAGE
            self.assertGreaterEqual(size, 1, name)
            self.assertLessEqual(size, limit, "%s is %d bytes, over %d" % (name, size, limit))
        attrs = [ln.split() for ln in (RIG / ".gitattributes").read_text(encoding="utf-8").splitlines()
                 if ln.strip() and not ln.startswith("#")]
        self.assertIn(["*.json", "text", "eol=lf"], attrs)
        self.assertIn(["*.png", "binary"], attrs)

    # ------------------------------------------------------------------ discs, readings, marks
    def test_discs_are_found_again_in_the_images(self):
        """Every button a view claims has exactly one disc in the image, and no disc is unclaimed;
        each numbered row has a mark per button on its view, and the marks rig.json gives are the
        discs the finder sees in the PNG today (position, size, round or box)."""
        f = self.src["DISC_FINDER"]
        for v in self.doc["views"]:
            src = self.views[v["id"]]
            with self.subTest(view=v["id"]):
                w, h, _, _ = self.png(v["id"])
                found = find_discs(self.levels(v["id"]), w, h, f)
                self.assertEqual(len(found), len(v["buttons"]),
                                 "%d discs in the image, %d buttons claimed" % (len(found), len(v["buttons"])))
                marks = [d for rid in v["rows"] for d in self.rows[rid]["discs"] if d["n"] is not None]
                self.assertEqual(sorted(d["n"] for d in marks), v["buttons"], "a claimed button without its mark; " + REGEN)
                for rid in v["rows"]:
                    row = self.rows[rid]
                    self.assertEqual([d["n"] for d in row["discs"] if d["n"] is not None], row["buttons"],
                                     "%s: a mark per button, in order" % rid)
                got = sorted((d["x"], d["y"], d["w"], d["h"], d["box"]) for d in marks)
                self.assertEqual(got, sorted((jnum(x + bw / 2), jnum(y + bh / 2), bw, bh, box) for x, y, bw, bh, _, box in found),
                                 "the marks in rig.json are not the discs in the image; " + REGEN)
                ox, oy = v["source"]["box"][:2]
                for d in marks:
                    self.assertTrue(all(type(d[k]) is int for k in ("n", "w", "h")) and type(d["box"]) is bool)
                    self.assertTrue(0 <= d["x"] - d["w"] / 2 and d["x"] + d["w"] / 2 <= w)
                    self.assertTrue(0 <= d["y"] - d["h"] / 2 and d["y"] + d["h"] / 2 <= h)
                    px, py = self.src["DISCS"][v["device"]][d["n"]]
                    self.assertLessEqual(abs(px - ox - d["x"]), d["w"] / 2, "button %d is named on another disc" % d["n"])
                    self.assertLessEqual(abs(py - oy - d["y"]), d["h"] / 2, "button %d is named on another disc" % d["n"])
                    sx0, sy0 = ox + d["x"] - d["w"] / 2, oy + d["y"] - d["h"] / 2
                    for o in self.src["VIEWS"]:
                        if o["Id"] != v["id"] and o["File"] == src["File"]:
                            a0, b0, a1, b1 = o["Box"]
                            self.assertFalse(sx0 < a1 and a0 < sx0 + d["w"] and sy0 < b1 and b0 < sy0 + d["h"],
                                             "button %d is also in %s" % (d["n"], o["Id"]))
                self.assertEqual(v["disc_min"], min(min(d[2], d[3]) for d in found), REGEN)
                self.assertEqual(v["digit_min"], min(d[4] for d in found), REGEN)
                self.assertGreater(v["digit_min"], 4)
                self.assertEqual(v["scale_18"], jnum(round(18 / v["disc_min"], 2)), REGEN)
        boxes = sorted("%s %d" % (r["device"], d["n"]) for r in self.doc["rows"] for d in r["discs"] if d["n"] and d["box"])
        self.assertEqual(len(boxes), 15, "the box-shaped marks are the rocker, toggle and switch badges: %s" % boxes)

    def test_each_disc_carries_the_name_verified_by_eye(self):
        """FINGERPRINTS pins, per button number, the source art under the disc that number was read on
        by eye. A name moved to another disc (a DISCS edit), new art or a changed disc finder fails
        here until the names are read again."""
        fps = self.src["FINGERPRINTS"]
        arts = {}
        seen = set()
        for v in self.doc["views"]:
            f = v["source"]["diagram"] + ".png"
            if f not in arts:
                w, h, ctype, rgba = read_png(DIAGRAMS / f)
                self.assertEqual(ctype, 6, "%s is 8-bit RGBA" % f)
                arts[f] = (w, rgba)
            w, rgba = arts[f]
            ox, oy = v["source"]["box"][:2]
            for rid in v["rows"]:
                for d in self.rows[rid]["discs"]:
                    if d["n"] is None:
                        continue
                    box = (int(ox + d["x"] - d["w"] / 2), int(oy + d["y"] - d["h"] / 2),
                           int(ox + d["x"] - d["w"] / 2) + d["w"], int(oy + d["y"] - d["h"] / 2) + d["h"])
                    with self.subTest(button="%s %d" % (v["device"], d["n"])):
                        self.assertEqual(fingerprint(w, rgba, box), fps.get(v["device"], {}).get(d["n"]),
                                         "button %s %d is on a disc other than the one verified by eye; %s"
                                         % (v["device"], d["n"], REVERIFY))
                    seen.add((v["device"], d["n"]))
        self.assertEqual(seen, {(dev, n) for dev, m in fps.items() for n in m}, "FINGERPRINTS names other buttons; " + REVERIFY)

    def test_disc_names_agree_with_where_the_controls_are(self):
        """A hat's or a rocker's discs must lie the way their rows' "where" words say (up above press
        above down, left of press left of right): a second check of the names, by geometry."""
        step = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0), "press": (0, 0), "center": (0, 0)}
        groups = {}
        for r in self.doc["rows"]:
            word = re.sub(r"[^a-z]", "", r["where"].lower().split()[-1])
            if len(r["buttons"]) == 1 and word in step:
                groups.setdefault((r["view"], r["group"]), []).append((step[word], r["discs"][0], r["id"]))
        checked = 0
        for key, items in sorted(groups.items()):
            for (s1, d1, i1) in items:
                for (s2, d2, i2) in items:
                    with self.subTest(group=key, a=i1, b=i2):
                        if s1[1] < s2[1]:
                            self.assertLess(d1["y"], d2["y"], "%s should be above %s" % (i1, i2))
                            checked += 1
                        if s1[0] < s2[0]:
                            self.assertLess(d1["x"], d2["x"], "%s should be left of %s" % (i1, i2))
                            checked += 1
        self.assertGreater(checked, 60)

    def test_sample_readings_are_painted_out(self):
        a = self.src["RIG_ART"]
        lo, hi, n = a["Ground"] * 255, a["Full"] * 255, a["Levels"]
        lut = [round(max(0.0, min(1.0, (t - lo) / (hi - lo))) ** a["Gamma"] * (n - 1)) for t in range(256)]
        hit = set()
        for v in self.doc["views"]:
            w, h, _, _ = self.png(v["id"])
            lv = self.levels(v["id"])
            ox, oy = v["source"]["box"][:2]
            cx0, cy0, cx1, cy1 = self.views[v["id"]]["Box"]
            for k, rd in enumerate(self.src["READINGS"]):
                if rd["File"] != v["source"]["diagram"] + ".png":
                    continue
                if rd["Box"][0] < cx1 and cx0 < rd["Box"][2] and rd["Box"][1] < cy1 and cy0 < rd["Box"][3]:
                    hit.add(k)                    # in this view's crop (the trim may have cut it off)
                x0, y0, x1, y1 = (max(0, rd["Box"][0] - ox), max(0, rd["Box"][1] - oy),
                                  min(w, rd["Box"][2] - ox), min(h, rd["Box"][3] - oy))
                if x0 >= x1 or y0 >= y1:
                    continue
                top = lut[rd["Cap"]] if "Cap" in rd else 0
                worst = max(lv[y * w + x] for y in range(y0, y1) for x in range(x0, x1))
                self.assertLessEqual(worst, top, "%s shows in %s" % (rd["What"], v["id"]))
        self.assertEqual(len(hit), len(self.src["READINGS"]), "a reading box falls in no view's crop")
        self.assertEqual(tuple(rd["What"] for rd in self.src["READINGS"]), READING_NAMES,
                         "READINGS are not the readings pinned in READING_NAMES (one dropped would show again)")

    def test_axis_words(self):
        """An axis row the art draws has a box round each word the art writes for it ("Dial"; "X" and
        "Y"), shrunk to the word's ink; an axis row the art does not draw has no mark."""
        ink_level = self.src["DISC_FINDER"]["Ink"]
        for row in self.doc["rows"]:
            if row["buttons"]:
                continue
            v = next(x for x in self.doc["views"] if x["id"] == row["view"])
            boxes = self.views[v["id"]]["Axes"][row["label"]] or []
            w, h, _, _ = self.png(v["id"])
            lv = self.levels(v["id"])
            ox, oy = v["source"]["box"][:2]
            with self.subTest(row=row["id"]):
                self.assertEqual(row["drawn"], bool(boxes))
                self.assertEqual(len(row["discs"]), len(boxes), REGEN)
                for d, (word, b) in zip(row["discs"], boxes):
                    self.assertIsNone(d["n"])
                    self.assertEqual(d["word"], word, REGEN)
                    self.assertIn(word.lower(), row["label"].lower(), "an axis word is part of the row's label")
                    self.assertIs(d["box"], True)
                    x0, y0, x1, y1 = b[0] - ox, b[1] - oy, b[2] - ox, b[3] - oy
                    ink = [(x, y) for y in range(max(0, y0), min(h, y1)) for x in range(max(0, x0), min(w, x1))
                           if lv[y * w + x] >= ink_level]
                    self.assertTrue(ink, "no word drawn where %s's box is" % row["label"])
                    ix0, iy0 = min(q[0] for q in ink), min(q[1] for q in ink)
                    ix1, iy1 = max(q[0] for q in ink) + 1, max(q[1] for q in ink) + 1
                    self.assertEqual((d["x"], d["y"], d["w"], d["h"]),
                                     (jnum((ix0 + ix1) / 2), jnum((iy0 + iy1) / 2), ix1 - ix0, iy1 - iy0), REGEN)

    # ------------------------------------------------------------------ the generator itself
    def test_the_files_are_what_the_generator_makes_today(self):
        """With Pillow: build everything in memory with the generator's own code and compare it with
        the committed files byte for byte. Closes every hand edit (an extra key, the date, a reformatted
        rig.json, a PNG chunk or a re-encoding). Skipped without Pillow."""
        try:
            import PIL  # noqa: F401
        except ImportError:
            self.skipTest("Pillow is not installed")
        spec = importlib.util.spec_from_file_location("regen_cards_under_test", CARD_SCRIPT)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        try:
            files, _, _ = mod.build_rig()
        except SystemExit as e:
            self.fail("the generator refuses to build the rig files: %s" % e)
        self.assertEqual(sorted(files), sorted(p.name for p in RIG.iterdir() if p.name != ".gitattributes"), REGEN)
        for name, data in sorted(files.items()):
            with self.subTest(file=name):
                if name.endswith(".png"):
                    # by pixels and chunk list, not bytes: another zlib build compresses differently
                    facts = mod.png_facts((RIG / name).read_bytes())
                    self.assertIsNotNone(facts, "%s does not decode" % name)
                    self.assertEqual(facts, mod.png_facts(data),
                                     "%s is not the image the generator makes today (pixels, palette or chunks); %s" % (name, REGEN))
                else:
                    self.assertEqual((RIG / name).read_bytes(), data, "%s is not what the generator makes today; %s" % (name, REGEN))

    def test_the_only_png_names_in_rig_json_are_its_images(self):
        """The service serves every image rig.json names: a string ending .png must be one of them."""
        named = []

        def walk(x):
            if isinstance(x, str) and x.lower().endswith(".png"):
                named.append(x)
            elif isinstance(x, dict):
                for v in x.values():
                    walk(v)
            elif isinstance(x, list):
                for v in x:
                    walk(v)
        walk(self.doc)
        self.assertEqual(sorted(named), sorted(v["image"] for v in self.doc["views"]))
        for name in named:
            self.assertRegex(name, r"^[a-z0-9_]{1,48}\.png$", "the service's name rule")

    def test_no_local_path_or_time_in_rig_json(self):
        text = (RIG / "rig.json").read_text(encoding="utf-8")
        self.assertIsNone(re.search(r"[A-Za-z]:[\\/]|[\\/]Users[\\/]|[\\/]home[\\/]", text), "a local path in rig.json")
        self.assertIsNone(re.search(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}", text), "a timestamp finer than the date")


if __name__ == "__main__":
    unittest.main()
