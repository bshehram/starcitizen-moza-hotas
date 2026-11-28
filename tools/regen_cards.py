"""regen_cards.py - the MOZA button-reference cards (split-diagram, print layout).

Produces the TWO reference cards, sized to fill a US-Letter sheet in LANDSCAPE
(11 x 8.5 in, aspect 1.294) for printing in hand:

    cards/MOZA_MHG_AB6_ref.png / .svg   (js1: MHG grip 1-29 + AB6 base 49-62 + stick axes)
    cards/MOZA_MTQ_ref.png     / .svg   (js2: MTQ throttle 1-65 + axes)

and, in the same run, the dashboard's rig reference, from the same tables and art:

    dashboard/web/rig/rig.json          every card row with its screen wording, the operator modes it
                                        works in, its status, the view it is on and the number discs
    dashboard/web/rig/<view>.png        the eight screen views (grip_front, grip_side, base, keypad,
                                        dials, levers, right_module, left_module): light line work on
                                        transparency, MOZA's sample readings painted out

The dashboard files need no browser: `--dashboard-only` writes just those. They are made from this
file, the art in diagrams/, MOZA.xml (which actions sit on each input, in which actionmap) and the
action catalog in reference/ (each action's in-game label and stock activation mode). Every file -
the rig's and the cards' - is made and checked in memory first, and only then written: when the card
tables and MOZA.xml disagree, or a disc's name no longer matches the one verified by eye, the run
stops and writes nothing. Writing puts each file through a temporary file (retried for about two
seconds while a reader holds the old one), leaves alone a file that already holds the same thing, and
writes rig.json last. A write that still fails (a file held for longer) can leave a mixed set behind:
dashboard/tests/test_rig.py catches it, and a rerun repairs it. The same test fails when any of those
inputs changed and the files were not rewritten. The schema of rig.json is in dashboard/RIG.md.

LAYOUT (60 / 40)
  The manufacturer diagrams are COMPOSITES - several views packed into one image
  (MTQ = throttle panel + Right Module + Left Module; MHG = side profile + front
  grip head; AB6 = base). Each composite is SPLIT into its sub-views (cropped from
  the source PNG, see the crop rectangles below) and laid out in the LEFT ~60% of
  the sheet as two stacked bands: the two small sub-views side by side on top, the
  one big sub-view below. The button# -> function table fills the RIGHT ~40% in two
  columns (labels are abbreviated to fit the narrow columns).

PRINTING
  Print "Fit to page" / 100%, landscape. Each card is already the page aspect, so
  it fills the sheet edge to edge. Output is 2x (~330 DPI per card).

EDITING
  The AB6 / MHG_* / MTQ_* tables below are the lookup tables - a hand-kept VIEW of
  the bindings; source of truth is MOZA.xml. When a binding changes, edit the
  matching row here (and MOZA.xml / CLAUDE.md), then re-run. Labels here are
  deliberately terser than MOZA.xml to fit the 40% columns; the row's 'Screen' and
  'Where' fields carry the screen's fuller wording, and 'Actions' / 'VariantActions'
  the MOZA.xml actions the wording is about (the run stops when the profile binds
  others). A status (flown, unverified, trial) goes in STATUS, with the whole
  CLAUDE.md sentences it rests on.

CROP RECTANGLES (x0, y0, x1, y1 in source-PNG pixels) - re-verify if MOZA ships new device
art (sources: AB6 890x691, MHG 1037x822, MTQ 1049x820). The cards' six crops are in
CARD_ART:
  MTQ main   60, 90,612,818     MTQ right 615, 72,1045,486   MTQ left 620,488,1045,818
  MHG front 515, 90,985,575     MHG side  100,168, 460,770   AB6 base 250,110, 785,650
and the screen's eight in VIEWS (the throttle panel cut into keypad, dials and levers).

REQUIREMENTS: Python 3.8+, Pillow (`python -m pip install Pillow`), and Chrome, Edge or
Chromium for the SVG -> PNG render (found automatically on Windows, macOS and Linux;
set CARD_BROWSER=<path> to pick one). `--dashboard-only` needs Pillow alone.
RUN (from the project root):
    python tools/regen_cards.py                    # cards + dashboard rig files
    python tools/regen_cards.py --dashboard-only   # dashboard rig files only, no browser
    python tools/regen_cards.py --sheets FOLDER    # contact sheets of every disc and its name, to read by eye
    python tools/regen_cards.py --fingerprints     # the FINGERPRINTS table for the names as they are now
"""

import ast
import base64
import datetime
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from collections import deque
from pathlib import Path

try:
    from PIL import Image, ImageChops
except ImportError:
    sys.exit('regen_cards: Pillow is required.  Run:  python -m pip install Pillow')

REPO = Path(__file__).resolve().parent.parent
DIAG_DIR = REPO / 'diagrams'
CARD_DIR = REPO / 'cards'
RIG_DIR = REPO / 'dashboard' / 'web' / 'rig'
PROFILE = REPO / 'MOZA.xml'
CATALOG_DIR = REPO / 'reference'

# ---- palette ----
C_TITLE = '#0f1720'; C_SUB = '#5b6b7a'; C_PRIM = '#16202b'; C_VARTXT = '#5b6b7a'; C_HINT = '#8a96a2'
C_BADGE = '#1f2933'; C_BADGE_UNB = '#cdd5dd'
C_RULE = '#d7dee5'; C_ROWALT = '#f4f7fa'
C_MINE = '#9a6a00'; C_SALV = '#0f6e6e'; C_NOTE = '#6b7681'


def esc(s):
    return '' if s is None else str(s).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def V(tag, text, color):
    return {'Tag': tag, 'Text': text, 'Color': color}


def rnd(n):
    """Whole-number round, half to even (the same rule the original .NET Math.Round used)."""
    return round(n)


def r1(n):
    """Round to one decimal place."""
    return round(n * 10) / 10


def num(n):
    """Format a number for SVG: whole numbers without a decimal point."""
    if isinstance(n, float) and n.is_integer():
        return str(int(n))
    return str(n)


def jnum(n):
    """A number for rig.json: whole numbers as integers."""
    return int(n) if float(n).is_integer() else n


PART = '.part'                     # write_atomic's temporary files: '.<name>.<random>.part'


def write_atomic(path, data):
    """Write bytes to path through a temporary file in the same folder, then rename it into place, so
    a reader (the dashboard's server, git, the browser) never sees half a file. On Windows the rename
    fails while another handle holds the old file open (the service reading it, a browser): it is
    retried for about two seconds, as the service's own atomic_write does."""
    path = Path(path)
    fd, tmp = tempfile.mkstemp(prefix='.' + path.name + '.', suffix=PART, dir=str(path.parent))
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        for attempt in range(40):
            try:
                os.replace(tmp, str(path))
                return
            except PermissionError:
                if attempt == 39 or path.is_dir():       # a folder in its place never goes away by waiting
                    raise
                time.sleep(0.05)
    finally:
        if os.path.exists(tmp):
            try:
                os.unlink(tmp)
            except OSError:
                pass


def sweep_parts(folder):
    """Remove the temporary files an interrupted write_atomic left in folder."""
    for p in Path(folder).glob('.*' + PART):
        try:
            p.unlink()
        except OSError:
            pass


def find_browser():
    cands = []
    if os.environ.get('CARD_BROWSER'):
        cands.append(os.environ['CARD_BROWSER'])
    if sys.platform == 'win32':
        bases = [os.environ.get(k) for k in ('ProgramFiles', 'ProgramFiles(x86)', 'LOCALAPPDATA')]
        cands += [os.path.join(b, 'Google', 'Chrome', 'Application', 'chrome.exe') for b in bases if b]
        cands += [os.path.join(b, 'Microsoft', 'Edge', 'Application', 'msedge.exe') for b in bases if b]
    elif sys.platform == 'darwin':
        for app in ('Google Chrome', 'Microsoft Edge', 'Chromium'):
            cands += ['/Applications/%s.app/Contents/MacOS/%s' % (app, app),
                      os.path.expanduser('~/Applications/%s.app/Contents/MacOS/%s' % (app, app))]
    for name in ('google-chrome', 'google-chrome-stable', 'chromium', 'chromium-browser',
                 'microsoft-edge', 'msedge', 'chrome'):
        found = shutil.which(name)
        if found:
            cands.append(found)
    return next((c for c in cands if c and os.path.isfile(c)), None)


# Recolor a manufacturer diagram (or a sub-rect of one) to white-bg line art.
#   grayscale + invert + levels:  out = -k*lum + k*(1-black),  k = 1/(white-black)
def get_sub_diagram(file, box, black=0.45, white=0.85):
    """Crop box = (x0, y0, x1, y1) out of a source diagram and recolor it."""
    src = Image.open(DIAG_DIR / file).convert('RGBA').crop(box)
    k = 1.0 / (white - black)
    tr = k * (1.0 - black)
    lum = src.convert('L')                       # ITU-R 601 luma: 0.299 R + 0.587 G + 0.114 B
    mapped = lum.point(lambda v: max(0, min(255, round((-k * v / 255.0 + tr) * 255))))
    out = Image.new('L', src.size, 255)          # white ground; transparent art blends into it
    out.paste(mapped, mask=src.getchannel('A'))
    buf = io.BytesIO()
    out.save(buf, format='PNG')
    return {'B64': base64.b64encode(buf.getvalue()).decode('ascii'), 'W': src.width, 'H': src.height}


# Lay recolored sub-views into the left part of the card as a stack of BANDS. Each band
# spans the zone width and gets height ~ HFrac (equal by default). A band holds one or
# more images side by side: each owns a cell = Frac of the zone width (cells centered in
# the band), is fit (aspect-preserved) in its cell, and is aligned vertically by VA
# ('t'op / 'c'entre (default) / 'b'ottom) - used to STAGGER a side-by-side pair (one
# high, one low) so they use the band's whitespace. Optional caption under each image.
def add_diagram_stack(sb, rows, zx, zy, zw, zh, row_gap, F):
    cap_h = rnd(20 * F)
    cell_pad = rnd(12 * F)
    avail = zh - (len(rows) - 1) * row_gap
    sum_hf = sum(float(r.get('HFrac') or 1.0) for r in rows)
    y = zy
    for row in rows:
        band_h = avail * (float(row.get('HFrac') or 1.0) / sum_hf)
        sum_frac = sum(float(im['Frac']) for im in row['Imgs'])
        x = zx + (zw - zw * sum_frac) / 2
        for im in row['Imgs']:
            cell_w = zw * float(im['Frac'])
            has_cap = bool(im.get('Caption'))
            area_h = band_h - cap_h if has_cap else band_h
            d = im['D']
            scale = min((cell_w - cell_pad) / d['W'], area_h / d['H'])
            dw, dh = d['W'] * scale, d['H'] * scale
            ix = x + (cell_w - dw) / 2
            va = im.get('VA') or 'c'
            iy = y if va == 't' else (y + (area_h - dh) if va == 'b' else y + (area_h - dh) / 2)
            sb.append("<image xlink:href='data:image/png;base64,%s' x='%s' y='%s' width='%s' height='%s'/>"
                      % (d['B64'], num(r1(ix)), num(r1(iy)), num(r1(dw)), num(r1(dh))))
            if has_cap:
                cy = iy + dh + rnd(17 * F)
                sb.append("<text x='%s' y='%s' font-size='%s' font-weight='600' text-anchor='middle' "
                          "fill='%s' letter-spacing='0.4'>%s</text>"
                          % (num(r1(x + cell_w / 2)), num(r1(cy)), num(rnd(11 * F)), C_SUB, esc(im['Caption'])))
            x += cell_w
        y += band_h + row_gap


# Append one table row at (x, y). F = font/size scale. Returns the height consumed.
def add_row(sb, x, y, col_w, row, idx, F):
    label = str(row['Label'])
    unb = bool(row.get('Unbound'))
    variants = row.get('Variants') or []
    row_h = rnd(44 * F) if variants else rnd(27 * F)
    pad = rnd(6 * F)
    if idx % 2 == 1:
        sb.append("<rect x='%s' y='%s' width='%s' height='%s' fill='%s'/>"
                  % (num(x - pad), num(y), num(col_w), num(row_h), C_ROWALT))
    badge_h = rnd(20 * F)
    badge_w = rnd((14 + len(label) * 7.5) * F) if len(label) > 2 else rnd(30 * F)
    by = y + rnd(4 * F)
    bfill = C_BADGE_UNB if unb else C_BADGE
    btxt = '#5b6671' if unb else '#ffffff'
    sb.append("<rect x='%s' y='%s' width='%s' height='%s' rx='%s' fill='%s'/>"
              % (num(x), num(by), num(badge_w), num(badge_h), num(rnd(4 * F)), bfill))
    sb.append("<text x='%s' y='%s' font-size='%s' font-weight='700' text-anchor='middle' fill='%s'>%s</text>"
              % (num(r1(x + badge_w / 2)), num(r1(by + badge_h * 0.72)), num(rnd(12 * F)), btxt, esc(label)))
    tx = x + badge_w + rnd(11 * F)
    sb.append("<text x='%s' y='%s' font-size='%s'><tspan font-weight='%s' fill='%s'>%s</tspan>"
              % (num(r1(tx)), num(y + rnd(18 * F)), num(rnd(13 * F)),
                 '400' if unb else '600', C_HINT if unb else C_PRIM, esc(row['Primary'])))
    if row.get('Hint'):
        sb.append("<tspan font-weight='400' font-size='%s' fill='%s'>  (%s)</tspan>"
                  % (num(rnd(11.5 * F)), C_HINT, esc(row['Hint'])))
    sb.append('</text>')
    if variants:
        sb.append("<text x='%s' y='%s' font-size='%s'>" % (num(r1(tx)), num(y + rnd(35 * F)), num(rnd(10.5 * F))))
        for i, v in enumerate(variants):
            if i:
                sb.append("<tspan fill='#b6c0ca'>     </tspan>")
            sb.append("<tspan fill='%s' font-weight='700'>%s </tspan><tspan fill='%s'>%s</tspan>"
                      % (v['Color'], esc(v['Tag']), C_VARTXT, esc(v['Text'])))
        sb.append('</text>')
    return row_h


def render_png(browser, svg_bytes, name, cw, ch):
    """Rasterize an SVG at 2x with a headless Chromium, from a copy in a temporary folder; returns the
    PNG's bytes (nothing is written in cards/ here). An isolated profile directory keeps it from
    colliding with a Chrome the user already has open."""
    work = Path(tempfile.mkdtemp(prefix='cardrender_'))
    svg_path, tmp_png = work / (name + '.svg'), work / 'card.png'
    try:
        svg_path.write_bytes(svg_bytes)
        subprocess.run([browser, '--headless=new', '--disable-gpu', '--no-sandbox', '--hide-scrollbars',
                        '--user-data-dir=%s' % (work / 'profile'), '--screenshot=%s' % tmp_png,
                        '--window-size=%d,%d' % (cw, ch), '--force-device-scale-factor=2',
                        svg_path.resolve().as_uri()],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=180)
        if not tmp_png.exists():
            sys.exit('regen_cards: render failed for %s; nothing was written.' % name)
        data = tmp_png.read_bytes()
    finally:
        shutil.rmtree(work, ignore_errors=True)
    with Image.open(io.BytesIO(data)) as o:
        print('  %-26s %dx%d' % (name + '.png', o.width, o.height))
    return data


# Build one card SVG + render it to PNG (2x), in memory: {file name: bytes}. cfg['F'] = font scale;
# cfg['Stack'] = images.
def new_card(cfg, browser):
    sb = []
    CW, CH, F, M = cfg['CanvasW'], cfg['CanvasH'], cfg['F'], 34
    sb.append("<svg xmlns='http://www.w3.org/2000/svg' xmlns:xlink='http://www.w3.org/1999/xlink' "
              "width='%d' height='%d' viewBox='0 0 %d %d' font-family='Segoe UI, Arial, sans-serif'>" % (CW, CH, CW, CH))
    sb.append("<rect width='%d' height='%d' fill='#ffffff'/>" % (CW, CH))
    title_y, sub_y, rule_y = rnd(30 * F), rnd(49 * F), rnd(60 * F)
    sb.append("<text x='%d' y='%s' font-size='%s' font-weight='700' fill='%s'>%s</text>"
              % (M, num(title_y), num(rnd(19 * F)), C_TITLE, esc(cfg['Title'])))
    sb.append("<text x='%d' y='%s' font-size='%s' fill='%s'>%s</text>"
              % (M, num(sub_y), num(rnd(10.5 * F)), C_SUB, esc(cfg['Sub'])))
    sb.append("<line x1='%d' y1='%s' x2='%d' y2='%s' stroke='%s' stroke-width='1.5'/>"
              % (M, num(rule_y), CW - M, num(rule_y), C_RULE))
    top = rule_y + rnd(18 * F)
    st = cfg.get('Stack')
    if st:
        zy = st.get('Y') or top
        zh = st.get('H') or CH - zy - rnd(46 * F)
        add_diagram_stack(sb, st['Rows'], st['X'], zy, st['W'], zh, st['Gap'], F)
    for col in cfg['Cols']:
        cy = col.get('Y') or top
        i = 0
        for r in col['Rows']:
            if r.get('Header'):
                sb.append("<text x='%s' y='%s' font-size='%s' font-weight='700' fill='%s' letter-spacing='0.6'>%s</text>"
                          % (num(col['X']), num(cy + rnd(14 * F)), num(rnd(12 * F)), C_SUB, esc(r['Header'])))
                ly = cy + rnd(21 * F)
                sb.append("<line x1='%s' y1='%s' x2='%s' y2='%s' stroke='%s' stroke-width='1'/>"
                          % (num(col['X']), num(ly), num(col['X'] + col['W'] - 12), num(ly), C_RULE))
                cy += rnd(31 * F)
                i = 0
                continue
            cy += add_row(sb, col['X'], cy, col['W'], r, i, F)
            i += 1
    if cfg.get('Legend'):
        sb.append("<text x='%d' y='%s' font-size='%s' fill='%s'>%s</text>"
                  % (M, num(CH - rnd(14 * F)), num(rnd(9 * F)), C_NOTE, esc(cfg['Legend'])))
    sb.append('</svg>')
    svg = ''.join(sb).encode('utf-8')                                 # UTF-8, no BOM
    return {cfg['Name'] + '.svg': svg, cfg['Name'] + '.png': render_png(browser, svg, cfg['Name'], CW, CH)}


# ================================================================ the card tables
# One dict per printed row. The card prints Label, Primary, Hint and Variants (V(tag, text, color));
# Header rows are column headings. The card wording is deliberately terse (vs MOZA.xml / CLAUDE.md)
# so it fits the narrow 40%-width columns - same bindings, shorter wording.
# The screen (dashboard/web/rig/rig.json) has room for whole words, so each row also carries:
#   'Screen'          the primary function in full words (searchable: "spacing" finds beam spacing)
#   'Where'           where the control is, in words ("Right hat up"), for every row
#   'Group'           the physical control the row is part of ("right hat", "COM hat"), as CLAUDE.md
#                     section 3 names them: a hat's five rows share one
#   'ScreenVariants'  {mode: full wording} for each card variant, keyed by MODES' 'Mode'
#   'Actions'         the MOZA.xml actions the primary wording describes ([] for an unbound row), and
#   'VariantActions'  {mode: [actions]} for each card variant: the generator and test_rig.py fail when
#                     the profile binds other actions on the row's inputs (two actions swapped, say)
#   'Inputs'          for an axis row: the profile inputs it is (js2_roty ...); button rows are js<n>_button<N>
#   'Jobs'            only where one press carries two functions told apart by the press (tap / hold):
#                     [{'Press': 'tap' or 'hold', 'Screen': ..., 'Actions': [the MOZA.xml actions]}]
# None of these reach the printed card. A status word (trial, unverified, flown) never goes in the
# wording: the status lives in STATUS below.

# ================================================================ AB6 (js1 49-62)
AB6 = [
    {'Header': 'AB6 BASE 49-62'},
    {'Label': '49', 'Primary': 'Power to weapons +', 'Hint': 'L wing 1',
     'Screen': 'Power assignment: weapons up (tap)', 'Where': 'Left wing button 1 (top)', 'Group': 'left wing', 'Actions': ['v_engineering_assignment_weapons_increase']},
    {'Label': '50', 'Primary': 'Power to engines +', 'Hint': 'L wing 2',
     'Screen': 'Power assignment: engines up (tap)', 'Where': 'Left wing button 2', 'Group': 'left wing', 'Actions': ['v_engineering_assignment_engine_increase']},
    {'Label': '51', 'Primary': 'Power to shields +', 'Hint': 'L wing 3',
     'Screen': 'Power assignment: shields up (tap)', 'Where': 'Left wing button 3', 'Group': 'left wing', 'Actions': ['v_engineering_assignment_shields_increase']},
    {'Label': '52', 'Primary': 'Power assignment reset', 'Hint': 'L wing 4',
     'Screen': 'Reset the power assignment to even', 'Where': 'Left wing button 4 (bottom)', 'Group': 'left wing', 'Actions': ['v_engineering_assignment_reset']},
    {'Label': '53', 'Primary': 'Weapons power toggle', 'Hint': 'R wing 1',
     'Screen': 'Weapons power on / off', 'Where': 'Right wing button 1 (top)', 'Group': 'right wing', 'Actions': ['v_power_toggle_weapons']},
    {'Label': '54', 'Primary': 'Thruster power toggle', 'Hint': 'R wing 2',
     'Screen': 'Thruster power on / off', 'Where': 'Right wing button 2', 'Group': 'right wing', 'Actions': ['v_power_toggle_thrusters']},
    {'Label': '55', 'Primary': 'Shield power toggle', 'Hint': 'R wing 3',
     'Screen': 'Shield power on / off', 'Where': 'Right wing button 3', 'Group': 'right wing', 'Actions': ['v_power_toggle_shields']},
    {'Label': '56', 'Primary': 'Shields to MAX (hold)', 'Hint': 'R wing 4',
     'Screen': 'All power to the shields (hold)', 'Where': 'Right wing button 4 (bottom)', 'Group': 'right wing', 'Actions': ['v_engineering_assignment_shields_max']},
    {'Label': '57-59', 'Primary': 'Left "Slider" lever', 'Hint': 'unbound - reserved', 'Unbound': True,
     'Screen': 'Left "Slider" lever, reserved', 'Where': 'Left base lever: top, middle, bottom', 'Group': 'left base lever', 'Actions': []},
    {'Label': '60-62', 'Primary': 'Right "Dial" lever', 'Hint': 'unbound - reserved', 'Unbound': True,
     'Screen': 'Right "Dial" lever, reserved', 'Where': 'Right base lever: top, middle, bottom', 'Group': 'right base lever', 'Actions': []},
]

# ================================================================ MHG (js1 1-29) + the stick axes
# The stick axes sit under GRIP 1-15 because that column has the room; on the screen they are listed
# with the grip side view (no view draws them, see VIEWS).
MHG_L = [
    {'Header': 'GRIP 1-15'},
    {'Label': '1', 'Primary': 'Fire Guns - Group 1 + selected preset', 'Variants': [V('Mine:', 'fire laser', C_MINE), V('Salv:', 'focused beam', C_SALV)],
     'Screen': 'Fire guns group 1 and the selected weapon preset', 'Where': 'Trigger', 'Group': 'trigger', 'Actions': ['v_weapon_preset_fire_guns0'],
     'VariantActions': {'mining': ['v_toggle_mining_laser_fire'], 'salvage': ['v_salvage_toggle_fire_focused']},
     'ScreenVariants': {'mining': 'Fire the mining laser (toggle)', 'salvage': 'Fire the focused salvage beam (toggle)'}},
    {'Label': '2', 'Primary': 'Launch missiles',
     'Screen': 'Launch missiles', 'Where': 'Top-left face button', 'Group': 'top-left button', 'Actions': ['v_weapon_toggle_launch_missile']},
    {'Label': '3', 'Primary': 'Look behind (hold)',
     'Screen': 'Look behind (hold)', 'Where': 'Pinky button (lower side)', 'Group': 'pinky button', 'Actions': ['v_view_look_behind']},
    {'Label': '4', 'Primary': 'Missile-mode toggle',
     'Screen': 'Switch between guns and missile operator mode', 'Where': 'Upper thumb button', 'Group': 'thumb button', 'Actions': ['v_toggle_missile_mode']},
    {'Label': '5', 'Primary': 'Lock target under reticle',
     'Screen': 'Lock the target under the reticle', 'Where': 'Lower-center face button', 'Group': 'lower button', 'Actions': ['v_target_under_reticle']},
    {'Label': '6', 'Primary': 'Fire Guns - Group 2', 'Variants': [V('Salv:', 'salvage gimbal', C_SALV)],
     'Screen': 'Fire guns group 2', 'Where': 'Trigger second stage', 'Group': 'trigger', 'Actions': ['v_weapon_preset_fire_guns1'],
     'VariantActions': {'salvage': ['v_salvage_toggle_gimbal_mode']},
     'ScreenVariants': {'salvage': 'Salvage gimbal mode on / off'}},
    {'Label': '7', 'Primary': 'Countermeasure: decoy (flares)',
     'Screen': 'Countermeasure: decoy burst (flares)', 'Where': 'Left hat up', 'Group': 'left hat', 'Actions': ['v_weapon_countermeasure_decoy_launch']},
    {'Label': '8', 'Primary': 'Cycle hostiles forward', 'Variants': [V('Salv:', 'fracture beam', C_SALV)],
     'Screen': 'Cycle hostile targets forward', 'Where': 'Left hat right', 'Group': 'left hat', 'Actions': ['v_target_cycle_hostile_fwd'],
     'VariantActions': {'salvage': ['v_salvage_toggle_fire_fracture']},
     'ScreenVariants': {'salvage': 'Fire the fracture beam (toggle)'}},
    {'Label': '9', 'Primary': 'Countermeasure: noise (chaff)',
     'Screen': 'Countermeasure: noise (chaff)', 'Where': 'Left hat down', 'Group': 'left hat', 'Actions': ['v_weapon_countermeasure_noise_launch']},
    {'Label': '10', 'Primary': 'Cycle hostiles back', 'Variants': [V('Salv:', 'disintegrate', C_SALV)],
     'Screen': 'Cycle hostile targets back', 'Where': 'Left hat left', 'Group': 'left hat', 'Actions': ['v_target_cycle_hostile_back'],
     'VariantActions': {'salvage': ['v_salvage_toggle_fire_disintegrate']},
     'ScreenVariants': {'salvage': 'Fire the disintegrate beam (toggle)'}},
    {'Label': '11', 'Primary': 'Lock selected target', 'Variants': [V('Salv:', 'cycle modifiers', C_SALV)],
     'Screen': 'Lock the selected target', 'Where': 'Left hat press', 'Group': 'left hat', 'Actions': ['v_target_lock_selected'],
     'VariantActions': {'salvage': ['v_salvage_cycle_modifiers_focused']},
     'ScreenVariants': {'salvage': 'Cycle the focused salvage modifiers'}},
    {'Label': '12', 'Primary': 'Cycle sub-target forward', 'Variants': [V('Mine:', 'module 1', C_MINE), V('Salv:', 'focus all', C_SALV)],
     'Screen': 'Cycle sub-targets forward', 'Where': 'Right hat up', 'Group': 'right hat', 'Actions': ['v_target_cycle_subitem_fwd'],
     'VariantActions': {'mining': ['v_mining_use_consumable1'], 'salvage': ['v_salvage_focus_all_heads']},
     'ScreenVariants': {'mining': 'Activate mining module, slot 1', 'salvage': 'Focus all salvage heads'}},
    {'Label': '13', 'Primary': 'Cycle attackers forward', 'Variants': [V('Mine:', 'module 2', C_MINE), V('Salv:', 'focus right', C_SALV)],
     'Screen': 'Cycle attackers forward', 'Where': 'Right hat right', 'Group': 'right hat', 'Actions': ['v_target_cycle_attacker_fwd'],
     'VariantActions': {'mining': ['v_mining_use_consumable2'], 'salvage': ['v_salvage_focus_right']},
     'ScreenVariants': {'mining': 'Activate mining module, slot 2', 'salvage': 'Focus the right salvage head'}},
    {'Label': '14', 'Primary': 'Cycle sub-target back', 'Variants': [V('Mine:', 'module 3', C_MINE), V('Salv:', 'beam axis H/V', C_SALV)],
     'Screen': 'Cycle sub-targets back', 'Where': 'Right hat down', 'Group': 'right hat', 'Actions': ['v_target_cycle_subitem_back'],
     'VariantActions': {'mining': ['v_mining_use_consumable3'], 'salvage': ['v_salvage_toggle_beam_spacing_axis']},
     'ScreenVariants': {'mining': 'Activate mining module, slot 3', 'salvage': 'Flip the beam axis (horizontal / vertical)'}},
    {'Label': '15', 'Primary': 'Cycle attackers back', 'Variants': [V('Salv:', 'focus left', C_SALV)],
     'Screen': 'Cycle attackers back', 'Where': 'Right hat left', 'Group': 'right hat', 'Actions': ['v_target_cycle_attacker_back'],
     'VariantActions': {'salvage': ['v_salvage_focus_left']},
     'ScreenVariants': {'salvage': 'Focus the left salvage head'}},
    {'Header': 'STICK AXES'},
    {'Label': 'X', 'Primary': 'Roll', 'Hint': 'stick left / right',
     'Screen': 'Roll', 'Where': 'Stick left / right', 'Group': 'stick', 'Actions': ['v_roll'], 'Inputs': ['js1_x']},
    {'Label': 'Y', 'Primary': 'Pitch (pull = nose up)', 'Hint': 'stick fwd / back',
     'Screen': 'Pitch (pull back = nose up)', 'Where': 'Stick forward / back', 'Group': 'stick', 'Actions': ['v_pitch'], 'Inputs': ['js1_y']},
    {'Label': 'RZ', 'Primary': 'Yaw', 'Hint': 'grip twist',
     'Screen': 'Yaw', 'Where': 'Grip twist', 'Group': 'stick', 'Actions': ['v_yaw'], 'Inputs': ['js1_rotz']},
]
MHG_R = [
    {'Header': 'GRIP 16-29'},
    {'Label': '16', 'Primary': 'Gimbal lock toggle', 'Variants': [V('Salv:', 'reset gimbal', C_SALV)],
     'Screen': 'Gimbal lock on / off', 'Where': 'Right hat press', 'Group': 'right hat', 'Actions': ['v_weapon_gimbals_state_toggle'],
     'VariantActions': {'salvage': ['v_salvage_reset_gimbal']},
     'ScreenVariants': {'salvage': 'Reset the salvage gimbal to center'}},
    {'Label': '17', 'Primary': 'Scan angle +', 'Variants': [V('Salv:', 'tractor dist + (trial)', C_SALV)],
     'Screen': 'Increase the scanning angle', 'Where': 'Lower hat up', 'Group': 'lower hat', 'Actions': ['v_inc_scan_focus_level'],
     'VariantActions': {'salvage': ['tractor_beam_vehicle_increase_distance']},
     'ScreenVariants': {'salvage': 'Vehicle tractor beam: push the held object further out'}},
    {'Label': '18', 'Primary': 'Activate scanning (hold)',
     'Screen': 'Scan the target under the reticle (hold)', 'Where': 'Lower hat right', 'Group': 'lower hat', 'Actions': ['v_scanning_trigger_scan']},
    {'Label': '19', 'Primary': 'Scan angle -', 'Variants': [V('Salv:', 'tractor dist - (trial)', C_SALV)],
     'Screen': 'Decrease the scanning angle', 'Where': 'Lower hat down', 'Group': 'lower hat', 'Actions': ['v_dec_scan_focus_level'],
     'VariantActions': {'salvage': ['tractor_beam_vehicle_decrease_distance']},
     'ScreenVariants': {'salvage': 'Vehicle tractor beam: pull the held object closer'}},
    {'Label': '20', 'Primary': 'Radar ping',
     'Screen': 'Radar ping (hold and release)', 'Where': 'Lower hat left', 'Group': 'lower hat', 'Actions': ['v_invoke_ping']},
    {'Label': '21', 'Primary': 'ADS / cockpit zoom toggle',
     'Screen': 'Precision targeting (cockpit zoom) on / off', 'Where': 'Lower hat press', 'Group': 'lower hat', 'Actions': ['v_ads_toggle']},
    {'Label': '22', 'Primary': 'Weapon preset - next', 'Variants': [V('Msl:', 'type +', C_NOTE), V('Mine:', 'pwr +', C_MINE), V('Salv:', 'gap +', C_SALV)],
     'Screen': 'Next weapon preset', 'Where': 'Rocker up', 'Group': 'rocker', 'Actions': ['v_weapon_preset_next'],
     'VariantActions': {'missile': ['v_weapon_cycle_missile_fwd'], 'mining': ['v_increase_mining_throttle'], 'salvage': ['v_salvage_increase_beam_spacing']},
     'ScreenVariants': {'missile': 'Next missile type', 'mining': 'Mining laser power up',
                        'salvage': 'Salvage beam spacing wider (step)'}},
    {'Label': '23', 'Primary': 'Weapon preset - prev', 'Variants': [V('Msl:', 'type -', C_NOTE), V('Mine:', 'pwr -', C_MINE), V('Salv:', 'gap -', C_SALV)],
     'Screen': 'Previous weapon preset', 'Where': 'Rocker down', 'Group': 'rocker', 'Actions': ['v_weapon_preset_prev'],
     'VariantActions': {'missile': ['v_weapon_cycle_missile_back'], 'mining': ['v_decrease_mining_throttle'], 'salvage': ['v_salvage_decrease_beam_spacing']},
     'ScreenVariants': {'missile': 'Previous missile type', 'mining': 'Mining laser power down',
                        'salvage': 'Salvage beam spacing narrower (step)'}},
    {'Label': '24', 'Primary': 'Weapon aim-type cycle', 'Variants': [V('Mine:', 'fracture/extract', C_MINE), V('Salv:', 'structural mode', C_SALV)],
     'Screen': 'Cycle the weapons aim mode', 'Where': 'Rocker press', 'Group': 'rocker', 'Actions': ['v_weapon_aim_type_cycle'],
     'VariantActions': {'mining': ['v_toggle_mining_laser_type'], 'salvage': ['v_salvage_cycle_modifiers_structural']},
     'ScreenVariants': {'mining': 'Switch the mining laser between fracture and extraction',
                        'salvage': 'Cycle the structural salvage field: fracture, disintegration, suction'}},
    {'Label': '25', 'Primary': 'Strafe up',
     'Screen': 'Strafe up', 'Where': 'Top mini-stick up', 'Group': 'top mini-stick', 'Actions': ['v_strafe_up']},
    {'Label': '26', 'Primary': 'Strafe right',
     'Screen': 'Strafe right', 'Where': 'Top mini-stick right', 'Group': 'top mini-stick', 'Actions': ['v_strafe_right']},
    {'Label': '27', 'Primary': 'Strafe down',
     'Screen': 'Strafe down', 'Where': 'Top mini-stick down', 'Group': 'top mini-stick', 'Actions': ['v_strafe_down']},
    {'Label': '28', 'Primary': 'Strafe left',
     'Screen': 'Strafe left', 'Where': 'Top mini-stick left', 'Group': 'top mini-stick', 'Actions': ['v_strafe_left']},
    {'Label': '29', 'Primary': 'Full reverse (hold)',
     'Screen': 'Full reverse thrust (hold)', 'Where': 'Top mini-stick press', 'Group': 'top mini-stick', 'Actions': ['v_strafe_back']},
]

# ================================================================ MTQ (js2 1-65 + axes)
MTQ_L = [
    {'Header': 'PANEL BUTTONS 1-30'},
    {'Label': '1', 'Primary': 'Jettison cargo (hold)', 'Hint': 'keypad A1, Mining',
     'Screen': 'Jettison volatile cargo (hold)', 'Where': 'Keypad A1', 'Group': 'keypad', 'Actions': ['v_jettison_volatile_cargo']},
    {'Label': '2', 'Primary': 'Fire left salvage beam', 'Hint': 'A2, Salvage',
     'Screen': 'Fire the left salvage beam (toggle)', 'Where': 'Keypad A2', 'Group': 'keypad', 'Actions': ['v_salvage_toggle_fire_left']},
    {'Label': '3', 'Primary': 'Fire right salvage beam', 'Hint': 'A3, Salvage',
     'Screen': 'Fire the right salvage beam (toggle)', 'Where': 'Keypad A3', 'Group': 'keypad', 'Actions': ['v_salvage_toggle_fire_right']},
    {'Label': '4', 'Primary': 'LAMP night-vision toggle', 'Hint': 'A4',
     'Screen': 'Night vision (LAMP, light amplification) on / off', 'Where': 'Keypad A4', 'Group': 'keypad', 'Actions': ['v_light_amplification_toggle']},
    {'Label': '5', 'Primary': 'Master mode SCM / NAV', 'Hint': 'NAV key',
     'Screen': 'Master mode: SCM / NAV', 'Where': 'NAV key', 'Group': 'keypad', 'Actions': ['v_master_mode_cycle']},
    {'Label': '6', 'Primary': 'Starmap', 'Hint': 'HDG key',
     'Screen': 'Star map', 'Where': 'HDG key', 'Group': 'keypad', 'Actions': ['v_starmap']},
    {'Label': '7', 'Primary': 'Engage quantum drive (hold)', 'Hint': 'SPD key',
     'Screen': 'Engage the quantum drive (hold)', 'Where': 'SPD key', 'Group': 'keypad', 'Actions': ['v_toggle_qdrive_engagement']},
    {'Label': '8', 'Primary': 'Landing req / hold: cargo', 'Hint': 'ALT key',
     'Screen': 'Request landing (tap); request cargo loading (hold)', 'Where': 'ALT key', 'Group': 'keypad', 'Actions': ['v_atc_request', 'v_atc_loading_area_request'],
     'Jobs': [{'Press': 'tap', 'Screen': 'Request landing', 'Actions': ['v_atc_request']},
              {'Press': 'hold', 'Screen': 'Request cargo loading', 'Actions': ['v_atc_loading_area_request']}]},
    {'Label': '9', 'Primary': 'Jump - inter-system', 'Hint': 'FD key',
     'Screen': 'Jump drive: request an inter-system jump', 'Where': 'FD key', 'Group': 'keypad', 'Actions': ['v_toggle_jump_request']},
    {'Label': '10', 'Primary': 'Dock (tap) / autoland (hold)', 'Hint': 'AP key',
     'Screen': 'Docking (tap); autoland (hold)', 'Where': 'AP key', 'Group': 'keypad', 'Actions': ['v_autoland', 'v_toggle_docking_request'],
     'Jobs': [{'Press': 'tap', 'Screen': 'Docking: initiate, cancel or undock', 'Actions': ['v_toggle_docking_request']},
              {'Press': 'hold', 'Screen': 'Autoland', 'Actions': ['v_autoland']}]},
    {'Label': '11', 'Primary': 'Speed limiter -', 'Hint': 'upper enc CCW',
     'Screen': 'Speed limiter down (step)', 'Where': 'Upper encoder, turn left', 'Group': 'upper encoder', 'Actions': ['v_ifcs_speed_limiter_decrement']},
    {'Label': '12', 'Primary': 'Speed limiter +', 'Hint': 'upper enc CW',
     'Screen': 'Speed limiter up (step)', 'Where': 'Upper encoder, turn right', 'Group': 'upper encoder', 'Actions': ['v_ifcs_speed_limiter_increment']},
    {'Label': '13', 'Primary': 'Speed limiter on / off', 'Hint': 'upper enc press',
     'Screen': 'Speed limiter on / off', 'Where': 'Upper encoder press', 'Group': 'upper encoder', 'Actions': ['v_ifcs_speed_limiter_toggle']},
    {'Label': '14', 'Primary': 'Accel / G limiter -', 'Hint': 'lower enc CCW',
     'Screen': 'Acceleration limiter down (step)', 'Where': 'Lower encoder, turn left', 'Group': 'lower encoder', 'Actions': ['v_accel_range_decrement']},
    {'Label': '15', 'Primary': 'Accel / G limiter +', 'Hint': 'lower enc CW',
     'Screen': 'Acceleration limiter up (step)', 'Where': 'Lower encoder, turn right', 'Group': 'lower encoder', 'Actions': ['v_accel_range_increment']},
    {'Label': '16', 'Primary': 'G-force safety toggle', 'Hint': 'lower enc press',
     'Screen': 'G-force safety on / off', 'Where': 'Lower encoder press', 'Group': 'lower encoder', 'Actions': ['v_ifcs_toggle_gforce_safety']},
    {'Label': '17', 'Primary': 'Guns mode', 'Hint': 'knob detent 1',
     'Screen': 'Guns operator mode', 'Where': 'Mode knob, detent 1 (full left)', 'Group': 'mode knob', 'Actions': ['v_set_guns_mode']},
    {'Label': '18', 'Primary': 'Missile mode', 'Hint': 'knob detent 2',
     'Screen': 'Missile operator mode', 'Where': 'Mode knob, detent 2', 'Group': 'mode knob', 'Actions': ['v_set_missile_mode']},
    {'Label': '19', 'Primary': 'Scan mode', 'Hint': 'knob detent 3',
     'Screen': 'Scanning operator mode', 'Where': 'Mode knob, detent 3 (center)', 'Group': 'mode knob', 'Actions': ['v_set_scan_mode']},
    {'Label': '20', 'Primary': 'Mining mode', 'Hint': 'knob detent 4',
     'Screen': 'Mining operator mode', 'Where': 'Mode knob, detent 4', 'Group': 'mode knob', 'Actions': ['v_set_mining_mode']},
    {'Label': '21', 'Primary': 'Salvage mode', 'Hint': 'knob detent 5',
     'Screen': 'Salvage operator mode', 'Where': 'Mode knob, detent 5 (full right)', 'Group': 'mode knob', 'Actions': ['v_set_salvage_mode']},
    {'Label': '22', 'Primary': 'Rocker center', 'Hint': 'rest', 'Unbound': True,
     'Screen': 'Power rocker at rest', 'Where': 'Power rocker, center', 'Group': 'power rocker', 'Actions': []},
    {'Label': '23', 'Primary': 'Master power OFF', 'Hint': 'rocker left',
     'Screen': 'Master power off', 'Where': 'Power rocker left', 'Group': 'power rocker', 'Actions': ['v_power_set_off']},
    {'Label': '24', 'Primary': 'Flight ready / power ON', 'Hint': 'rocker right',
     'Screen': 'Flight ready: power and systems on; press again to spin down', 'Where': 'Power rocker right', 'Group': 'power rocker', 'Actions': ['v_flightready']},
    {'Label': '25', 'Primary': 'Unlock + open all doors', 'Hint': 'toggle A up',
     'Screen': 'Unlock and open all doors', 'Where': 'Toggle A up', 'Group': 'toggle A', 'Actions': ['v_unlock_all_doors', 'v_open_all_doors']},
    {'Label': '26', 'Primary': 'Lock + close all doors', 'Hint': 'toggle A down',
     'Screen': 'Close and lock all doors', 'Where': 'Toggle A down', 'Group': 'toggle A', 'Actions': ['v_lock_all_doors', 'v_close_all_doors']},
    {'Label': '27', 'Primary': 'Lights on', 'Hint': 'toggle B up',
     'Screen': 'Lights on', 'Where': 'Toggle B up', 'Group': 'toggle B', 'Actions': ['v_lights_on']},
    {'Label': '28', 'Primary': 'Lights off', 'Hint': 'toggle B down',
     'Screen': 'Lights off', 'Where': 'Toggle B down', 'Group': 'toggle B', 'Actions': ['v_lights_off']},
    {'Label': '29', 'Primary': 'Landing gear retract', 'Hint': 'gear lever up',
     'Screen': 'Landing gear up', 'Where': 'Gear lever up', 'Group': 'gear lever', 'Actions': ['v_retract_landing_system']},
    {'Label': '30', 'Primary': 'Landing gear deploy', 'Hint': 'gear lever down',
     'Screen': 'Landing gear down', 'Where': 'Gear lever down', 'Group': 'gear lever', 'Actions': ['v_deploy_landing_system']},
]
MTQ_R = [
    {'Header': 'BUTTONS 31-65'},
    {'Label': '31-43', 'Primary': 'Lever detent buttons', 'Hint': 'unbound', 'Unbound': True,
     'Screen': 'Lever detent buttons', 'Where': 'FLAPS, SPEEDBRAKE and throttle lever detents', 'Group': 'lever detents', 'Actions': []},
    {'Label': '49', 'Primary': 'VTOL off', 'Hint': '3-pos switch rest',
     'Screen': 'VTOL off', 'Where': 'Right module switch at rest', 'Group': 'right module switch', 'Actions': ['v_vtol_off']},
    {'Label': '50', 'Primary': 'VTOL on', 'Hint': '3-pos switch fwd-latch',
     'Screen': 'VTOL on', 'Where': 'Right module switch forward (latches)', 'Group': 'right module switch', 'Actions': ['v_vtol_on']},
    {'Label': '51', 'Primary': 'Space brake', 'Hint': '3-pos switch back',
     'Screen': 'Space brake (hold)', 'Where': 'Right module switch back (springs back)', 'Group': 'right module switch', 'Actions': ['v_space_brake']},
    {'Label': '56', 'Primary': 'Shield face: front', 'Hint': 'WPN hat up',
     'Screen': 'Raise the front shield face', 'Where': 'WPN hat up', 'Group': 'WPN hat', 'Actions': ['v_shield_raise_level_forward']},
    {'Label': '55', 'Primary': 'Shield face: rear', 'Hint': 'WPN hat down',
     'Screen': 'Raise the rear shield face', 'Where': 'WPN hat down', 'Group': 'WPN hat', 'Actions': ['v_shield_raise_level_back']},
    {'Label': '54', 'Primary': 'Shield face: left', 'Hint': 'WPN hat left',
     'Screen': 'Raise the left shield face', 'Where': 'WPN hat left', 'Group': 'WPN hat', 'Actions': ['v_shield_raise_level_left']},
    {'Label': '53', 'Primary': 'Shield face: right', 'Hint': 'WPN hat right',
     'Screen': 'Raise the right shield face', 'Where': 'WPN hat right', 'Group': 'WPN hat', 'Actions': ['v_shield_raise_level_right']},
    {'Label': '52', 'Primary': 'Shield faces reset', 'Hint': 'WPN hat press',
     'Screen': 'Reset the shield faces to even', 'Where': 'WPN hat press', 'Group': 'WPN hat', 'Actions': ['v_shield_reset_level']},
    {'Label': '61', 'Primary': 'Cycle all contacts fwd', 'Hint': 'COM hat up',
     'Screen': 'Cycle all contacts forward', 'Where': 'COM hat up', 'Group': 'COM hat', 'Actions': ['v_target_cycle_all_fwd']},
    {'Label': '60', 'Primary': 'Cycle all contacts back', 'Hint': 'COM hat down',
     'Screen': 'Cycle all contacts back', 'Where': 'COM hat down', 'Group': 'COM hat', 'Actions': ['v_target_cycle_all_back']},
    {'Label': '59', 'Primary': 'Cycle pinned forward', 'Hint': 'COM hat left',
     'Screen': 'Cycle pinned targets forward', 'Where': 'COM hat left', 'Group': 'COM hat', 'Actions': ['v_target_cycle_pinned_fwd']},
    {'Label': '58', 'Primary': 'Lock closest hostile', 'Hint': 'COM hat right',
     'Screen': 'Lock the closest hostile', 'Where': 'COM hat right', 'Group': 'COM hat', 'Actions': ['v_target_cycle_hostile_reset']},
    {'Label': '57', 'Primary': 'Decoupled / hold: pin', 'Hint': 'COM hat press',
     'Screen': 'Decoupled flight on / off (tap); pin the selected target (hold)', 'Where': 'COM hat press', 'Group': 'COM hat', 'Actions': ['v_ifcs_vector_decoupling_toggle', 'v_target_pin_selected_hold'],
     'Jobs': [{'Press': 'tap', 'Screen': 'Decoupled flight on / off', 'Actions': ['v_ifcs_vector_decoupling_toggle']},
              {'Press': 'hold', 'Screen': 'Pin the selected target', 'Actions': ['v_target_pin_selected_hold']}]},
    {'Label': '62', 'Primary': 'Cycle camera view', 'Hint': 'mini-stick press',
     'Screen': 'Cycle the camera view', 'Where': 'Left module mini-stick press', 'Group': 'left module mini-stick', 'Actions': ['v_view_cycle_fwd']},
    {'Label': '63', 'Primary': 'Zoom in - cockpit', 'Hint': 'throttle dial fwd',
     'Screen': 'Zoom in (cockpit view)', 'Where': 'Throttle-lever dial, forward click', 'Group': 'throttle-lever dial', 'Actions': ['v_view_dynamic_zoom_rel_in']},
    {'Label': '64', 'Primary': 'Zoom out - cockpit', 'Hint': 'throttle dial back',
     'Screen': 'Zoom out (cockpit view)', 'Where': 'Throttle-lever dial, back click', 'Group': 'throttle-lever dial', 'Actions': ['v_view_dynamic_zoom_rel_out']},
    {'Label': '65', 'Primary': 'Boost / afterburner', 'Hint': 'L-Module button',
     'Screen': 'Boost (afterburner)', 'Where': 'Left module button', 'Group': 'left module button', 'Actions': ['v_afterburner']},
    {'Header': 'AXES'},
    {'Label': 'RY', 'Primary': 'Main throttle - forward', 'Hint': 'detent to detent',
     'Screen': 'Throttle forward: zero at the idle detent, full at the forward detent', 'Where': 'Throttle levers', 'Group': 'throttle levers', 'Actions': ['v_strafe_forward'],
     'Inputs': ['js2_roty']},
    {'Label': 'Z / RZ', 'Primary': 'Reverse pair - off', 'Hint': 'not output', 'Unbound': True,
     'Screen': 'Reverse thrust axes, not output by the device', 'Where': 'Throttle levers behind the idle detent', 'Group': 'throttle levers', 'Actions': [],
     'Inputs': ['js2_z', 'js2_rotz']},
    {'Label': 'Slider', 'Primary': 'Mining laser power', 'Hint': 'FLAPS, Mining',
     'Screen': 'Mining laser power (absolute)', 'Where': 'FLAPS lever', 'Group': 'FLAPS lever', 'Actions': ['v_mining_throttle'], 'Inputs': ['js2_slider2']},
    {'Label': 'Dial', 'Primary': 'Salvage beam spacing', 'Hint': 'S-brake, Salvage',
     'Screen': 'Salvage beam spacing (absolute)', 'Where': 'SPEEDBRAKE lever', 'Group': 'SPEEDBRAKE lever', 'Actions': ['v_salvage_beam_spacing_abs'], 'Inputs': ['js2_slider1']},
    {'Label': 'X / Y', 'Primary': 'Camera look (yaw / pitch)', 'Hint': 'mini-stick',
     'Screen': 'Camera look: left / right and up / down', 'Where': 'Left module mini-stick', 'Group': 'left module mini-stick', 'Actions': ['v_view_yaw', 'v_view_pitch'],
     'Inputs': ['js2_x', 'js2_y']},
    {'Label': 'RX', 'Primary': 'Throttle twin of RY', 'Hint': 'unbound', 'Unbound': True,
     'Screen': 'Throttle twin of RY', 'Where': 'Throttle levers', 'Group': 'throttle levers', 'Actions': [], 'Inputs': ['js2_rotx']},
]

# ================================================================ shared by the cards and the dashboard
# Everything below up to the functions is plain literals so dashboard/tests/test_rig.py can read it
# with `ast` (without running this file) and tell when dashboard/web/rig/ is stale.

# The two cards: which tables they print, in card order, and their heading and legend text. Screen,
# Product and Notes are the screen's: Notes is the legend as sentences, without the tag key (the
# screen names the modes in words), each with the screen views (VIEWS) it is about.
CARDS = [
    {'Name': 'MOZA_MHG_AB6_ref', 'Device': 'js1', 'Screen': 'Stick', 'Product': 'MOZA MHG grip on the AB6 base',
     'Tables': ['MHG_L', 'MHG_R', 'AB6'],
     'Title': 'MOZA MHG Grip + AB6 Base  -  Button Reference  (js1)',
     'Sub': 'MHG grip 1-29 mounted on the AB6 base 49-62, plus the stick axes  ·  trigger / hats / rocker reused per operator mode',
     'Legend': ('Combat (default)  ·  Msl: Missile  ·  Mine: Mining  ·  Salv: Salvage.  One control = a '
                'different job per operator mode (set on the MTQ knob); the right hat 12-16 carries the mining '
                'modules and salvage bank. AB6 wings 49-56 = power panel in every mode.'),
     'Notes': [{'Text': 'The trigger, the hats and the rocker do a different job in each operator mode; the mode is set on the MTQ mode knob.',
                'Views': ['grip_front', 'grip_side']},
               {'Text': 'The right hat (12-16) carries the mining modules and the salvage bank.', 'Views': ['grip_front']},
               {'Text': 'The AB6 wing buttons (49-56) are the power panel in every mode.', 'Views': ['base']}]},
    {'Name': 'MOZA_MTQ_ref', 'Device': 'js2', 'Screen': 'Throttle', 'Product': 'MOZA MTQ throttle panel',
     'Tables': ['MTQ_L', 'MTQ_R'],
     'Title': 'MOZA MTQ Throttle Panel  -  Button Reference  (js2)',
     'Sub': 'throttle 1-65 + axes  ·  buttons 44-48 are absent on the device',
     'Legend': ('Throttle forward = axis RY, idle detent = 0, forward detent = full; reverse = MHG stick press 29, held. '
                'Nothing is output outside the two detents.  FLAPS & Speedbrake levers drive analog axes (Slider / Dial) in Mining / Salvage '
                'modes; detent buttons 31-43 are unbound.  WPN-hat shield faces act only on S3 Quadrant shields.'),
     'Notes': [{'Text': 'Forward throttle is axis RY: zero at the idle detent, full at the forward detent. Nothing is output outside the two detents.',
                'Views': ['levers']},
               {'Text': 'Reverse is the MHG stick press (29), held.', 'Views': ['levers']},
               {'Text': 'The FLAPS and SPEEDBRAKE levers drive analog axes (Slider and Dial) in Mining and Salvage mode; their detent buttons 31-43 are unbound.',
                'Views': ['levers']},
               {'Text': 'The WPN-hat shield faces act only on Size 3 Quadrant shields.', 'Views': ['right_module']},
               {'Text': 'Buttons 44-48 are absent on the device.', 'Views': ['levers', 'right_module']}]},
]

# The operator modes: the card's variant tags and the MTQ mode knob detent that sets each (`Set` is the
# MOZA.xml action; the generator reads its input from the profile, CLAUDE.md section 3.3 numbers the
# detents 1-5). Flight and Quantum operator modes are not on the knob (CLAUDE.md section 4).
MODES = [
    {'Mode': 'combat', 'Tag': None, 'Name': 'Combat', 'Operator': 'Guns', 'Set': 'v_set_guns_mode', 'Detent': 1},
    {'Mode': 'missile', 'Tag': 'Msl:', 'Name': 'Missile', 'Operator': 'Missile', 'Set': 'v_set_missile_mode', 'Detent': 2},
    {'Mode': 'scan', 'Tag': None, 'Name': 'Scan', 'Operator': 'Scanning', 'Set': 'v_set_scan_mode', 'Detent': 3},
    {'Mode': 'mining', 'Tag': 'Mine:', 'Name': 'Mining', 'Operator': 'Mining', 'Set': 'v_set_mining_mode', 'Detent': 4},
    {'Mode': 'salvage', 'Tag': 'Salv:', 'Name': 'Salvage', 'Operator': 'Salvage', 'Set': 'v_set_salvage_mode', 'Detent': 5},
]

# The page's mode filters (the live views' `view.mode`, dashboard/STATE.md: flight, mining or salvage)
# -> the rig's modes each filter covers, the filter's own mode first. Flight is the guns mode ("Guns
# mode covers combat-flight", CLAUDE.md section 4, the knob note) together with the two other modes a
# pilot flies in, missile and scan. A row is live under a filter when it is live in any of the filter's
# modes; when that is not the first one, the page names the mode on the row.
LIVE_MODES = {'flight': ['combat', 'missile', 'scan'], 'mining': ['mining'], 'salvage': ['salvage']}

# In which operator modes each actionmap of MOZA.xml is live. Every mode is in Live, in Unknown (the
# docs do not say, or contradict each other) or else dead (the docs say the map is off there). Why =
# the whole sentences this rests on, each with In = where it sits (a section, a section's heading, or
# an item of section 6; for MOZA.xml a phrase of the comment it is in). test_rig.py checks that each
# occurs exactly once in its file and sits there, ignoring ** and `. Note = why a cell is unknown.
# The generator refuses a profile binding in a map that is not listed here.
_C = 'CLAUDE.md'
_X = 'MOZA.xml'
_ALWAYS = {'File': _C, 'In': '§5', 'Text': ("Always-active maps (power, defensive, movement, view, and seat_general) are "
                                           "deliberately not reused this way - that's why the AB6-wing power panel, the "
                                           "WPN-hat shield faces and the left-hat countermeasures are single-purpose.")}
_XML_ALWAYS = {'File': _X, 'In': 'DUPE/REUSE POLICY', 'Text': (
    'spaceship_power/defensive/movement/view/general, seat_general and lights are ALWAYS active, so their controls '
    '(AB6-wing power panel, WPN-hat shield faces, left-hat countermeasures, MTQ throttle/strafe/encoders) carry nothing '
    'else, except a stock tap/hold split ("AP" key, "ALT" key, COM hat press).')}
_XML_GATED = {'File': _X, 'In': 'DUPE/REUSE POLICY', 'Text': (
    'DUPE/REUSE POLICY: a physical button carrying several actions is fine ONLY when they sit in operator-gated maps '
    'that are never simultaneously active - guns/missiles/mining/salvage/targeting/scanning are gated by operator mode, '
    'so the trigger, rocker and MHG hats each do one thing per mode.')}
_ROCKER = {'File': _C, 'In': '§4 Missiles', 'Text': ('The rocker (22/23) does double duty: weapon presets in gun mode, '
                                                   'missile types in missile mode - the active operator mode decides which.')}
_TRIGGER = {'File': _C, 'In': '§2.4', 'Text': (
    'For example js1_button1 is the trigger for Fire Guns (spaceship_weapons), Fire Mining Laser (spaceship_mining), '
    'and Fire Focused Salvage Beam (spaceship_salvage) - the trigger does the right thing depending on which operator '
    'mode the seat is in.')}
_ALL = ['combat', 'missile', 'scan', 'mining', 'salvage']
MAPS = {
    'spaceship_power': {'Live': _ALL, 'Unknown': [], 'Why': [
        {'File': _C, 'In': '§4 Power management', 'Text': (
            'spaceship_power is always live, so the eight wing buttons carry nothing else in any mode: the combat '
            'target-cycle bank that sat there was deleted (the user never used it; general cycling is on the COM hat '
            'and the MHG hats), and the Mining / Salvage banks moved to the MHG right hat (§6 item 22).')},
        _ALWAYS]},
    'spaceship_general': {'Live': _ALL, 'Unknown': [], 'Why': [_XML_ALWAYS]},
    'lights_controller': {'Live': _ALL, 'Unknown': [], 'Why': [_XML_ALWAYS]},
    'spaceship_movement': {'Live': _ALL, 'Unknown': [], 'Why': [_ALWAYS]},
    'spaceship_view': {'Live': _ALL, 'Unknown': [], 'Why': [_ALWAYS]},
    'spaceship_defensive': {'Live': _ALL, 'Unknown': [], 'Why': [_ALWAYS]},
    'seat_general': {'Live': _ALL, 'Unknown': [], 'Why': [
        {'File': _C, 'In': '§5', 'Text': (
            'seat_general (missile-mode toggle, look-behind, the mode knob) is live in every operator mode; the one '
            'past breach of this rule was the mining-laser switch sharing js1_button4 with the missile-mode toggle '
            '(§6 item 18).')}]},
    'spaceship_weapons': {'Live': ['combat'], 'Unknown': [], 'Why': [_ROCKER, _TRIGGER, _XML_GATED]},
    'spaceship_missiles': {'Live': ['missile'], 'Unknown': [], 'Why': [_ROCKER, _XML_GATED]},
    'spaceship_scanning': {'Live': ['scan'], 'Unknown': [], 'Why': [
        {'File': _C, 'In': '§4 Radar & scanning',
         'Text': 'Hold to scan the target under the reticle for detailed info (requires Scan operator mode).'},
        _XML_GATED]},
    'spaceship_mining': {'Live': ['mining'], 'Unknown': [], 'Why': [
        {'File': _C, 'In': '§4 Mining', 'Text': 'These reuse MHG controls; active only in Mining operator mode.'}]},
    'spaceship_salvage': {'Live': ['salvage'], 'Unknown': [], 'Why': [
        {'File': _C, 'In': '§4 Salvage', 'Text': 'These reuse MHG controls; active only in Salvage operator mode.'}]},
    'spaceship_targeting': {'Live': ['combat'], 'Unknown': ['missile', 'scan'], 'Why': [
        {'File': _C, 'In': '§4 Targeting', 'Text': (
            "The MHG right hat is a multi-mode bank (since 2026-11-26): sub-target / attacker cycling in combat; in "
            "Mining / Salvage operator mode the same five inputs become those modes' banks (see Mining / Salvage).")},
        {'File': _C, 'In': '§4 Targeting', 'Text': (
            'Safe because targeting maps go inactive in mining/salvage - the same gating the left hat relies on '
            '(hostile cycle in combat, salvage beams in salvage).')},
        {'File': _C, 'In': '§4 Targeting', 'Text': 'Hard-locks the selected contact (enables lead pips + missile lock).'}],
        'Note': ('Missile and scan mode are unknown: the lock enabling "missile lock" points to live in missile mode, '
                 'section 5\'s "weapons/missiles/mining/salvage/targeting are never simultaneously live" would make it '
                 'dead there, and nothing is said about scan mode.')},
    'spaceship_targeting_advanced': {'Live': ['combat'], 'Unknown': ['missile', 'scan'], 'Why': [
        {'File': _C, 'In': '§4 Targeting', 'Text': (
            "The MHG right hat is a multi-mode bank (since 2026-11-26): sub-target / attacker cycling in combat; in "
            "Mining / Salvage operator mode the same five inputs become those modes' banks (see Mining / Salvage).")},
        {'File': _C, 'In': '§4 Targeting', 'Text': (
            'Safe because targeting maps go inactive in mining/salvage - the same gating the left hat relies on '
            '(hostile cycle in combat, salvage beams in salvage).')}],
        'Note': 'Missile and scan mode are unknown, as for spaceship_targeting.'},
    'spaceship_quantum': {'Live': [], 'Unknown': _ALL, 'Why': [
        {'File': _C, 'In': '§4 Quantum travel, navigation & docking',
         'Text': 'Spools & engages the quantum drive for in-system travel (needs NAV mode + an aligned marker).'},
        {'File': _C, 'In': '§4 Flight & movement',
         'Text': 'Toggles SCM (combat: weapons/shields) ↔ NAV (travel: quantum, higher speed, weapons offline).'}],
        'Note': ('Unknown in every mode: engaging needs NAV master mode, in which weapons are offline, so it is not '
                 'live where the guns are; these modes are operator modes, and the data has no master modes.')},
    'spaceship_hud': {'Live': [], 'Unknown': _ALL, 'Why': [],
                      'Note': 'The docs do not say in which operator modes the star map opens.'},
    'spaceship_docking': {'Live': [], 'Unknown': _ALL, 'Why': [],
                          'Note': 'The docs do not say in which operator modes docking works.'},
    'spaceship_radar': {'Live': [], 'Unknown': _ALL, 'Why': [],
                        'Note': 'The docs do not say in which operator modes the radar ping works.'},
}

# The status of each function the docs say something about: the one hand-kept place for the rig's
# statuses. Control = '<device> <card label>'; Part = None for the primary function or the variant's
# mode; Press = 'tap' / 'hold' for one job of a row with Jobs. Status: flown (confirmed in a ship),
# unverified (bound, not yet confirmed in a ship; a binding changed since the last load is unverified
# too, and its quote says it is not loaded yet), trial (the docs call it a trial). When =
# the date or build of the confirmation where the docs give it. Quote = the whole sentences of root
# CLAUDE.md it rests on, each with In = where it sits; test_rig.py checks that each occurs exactly once
# there, and (coarsely) that one of them says what the status says. It cannot check that a sentence
# means what the status claims: read the quote when you change either. A function with no entry has
# no status: the docs record neither a flight report nor a doubt about how that binding behaves.
STATUS = [
    {'Control': 'js1 3', 'Part': None, 'Status': 'flown', 'Quote': [
        {'In': '§4 Mode switching & LAMP', 'Text': 'Confirmed working in cockpit view.'}]},
    {'Control': 'js1 12', 'Part': 'mining', 'Status': 'flown', 'When': '2026-11-27', 'Quote': [
        {'In': '§4 Mining', 'Text': ('Slots 1 and 2 are confirmed in flight: the user used them on all three ARC-L4 runs '
                                    'of 2026-11-27 in the Golem (their report, 2026-11-28).')},
        {'In': '§6 item 22', 'Text': 'Tested since: module activation on the right hat works in the Golem (slots 1 and 2).'}]},
    {'Control': 'js1 13', 'Part': 'mining', 'Status': 'flown', 'When': '2026-11-27', 'Quote': [
        {'In': '§4 Mining', 'Text': ('Slots 1 and 2 are confirmed in flight: the user used them on all three ARC-L4 runs '
                                    'of 2026-11-27 in the Golem (their report, 2026-11-28).')},
        {'In': '§6 item 22', 'Text': 'Tested since: module activation on the right hat works in the Golem (slots 1 and 2).'}]},
    {'Control': 'js1 14', 'Part': 'mining', 'Status': 'unverified', 'Quote': [
        {'In': '§4 Mining', 'Text': ('Slots 1 and 2 both fire on the Golem (user, 2026-11-28); that slot 3 does nothing '
                                    'there was not checked in-ship.')}]},
    {'Control': 'js1 12', 'Part': 'salvage', 'Status': 'unverified', 'Quote': [
        {'In': '§4 Salvage', 'Text': "None of the bank's functions has been confirmed in-ship in its new place (nor was it on the wings)."}]},
    {'Control': 'js1 13', 'Part': 'salvage', 'Status': 'unverified', 'Quote': [
        {'In': '§4 Salvage', 'Text': "None of the bank's functions has been confirmed in-ship in its new place (nor was it on the wings)."}]},
    {'Control': 'js1 14', 'Part': 'salvage', 'Status': 'unverified', 'Quote': [
        {'In': '§4 Salvage', 'Text': "None of the bank's functions has been confirmed in-ship in its new place (nor was it on the wings)."}]},
    {'Control': 'js1 15', 'Part': 'salvage', 'Status': 'unverified', 'Quote': [
        {'In': '§4 Salvage', 'Text': "None of the bank's functions has been confirmed in-ship in its new place (nor was it on the wings)."}]},
    {'Control': 'js1 16', 'Part': 'salvage', 'Status': 'unverified', 'Quote': [
        {'In': '§4 Salvage', 'Text': ('Salvage bank on the MHG right hat (since 2026-11-26): ↑ focus all · ← / → focus '
                                     'left / right · ↓ flip the beam axis · press = gimbal reset, with fire left / right '
                                     'on MTQ A2 / A3.')},
        {'In': '§4 Salvage', 'Text': "None of the bank's functions has been confirmed in-ship in its new place (nor was it on the wings)."}]},
    {'Control': 'js1 17', 'Part': None, 'Status': 'unverified', 'Quote': [
        {'In': '§4 Radar & scanning', 'Text': ('Which way the cone actually goes is unverified - nobody has checked in a '
                                              'ship, and this row used to say the opposite ("narrows the cone"), §6 item 26.')},
        {'In': '§6 item 26', 'Text': ('Not checked in a ship, and only the user can settle it: in Scan operator mode (knob '
                                     'detent 3), press lower hat ↑ a few times and watch whether the scan cone on the HUD '
                                     'gets wider or narrower.')}]},
    {'Control': 'js1 19', 'Part': None, 'Status': 'unverified', 'Quote': [
        {'In': '§4 Radar & scanning', 'Text': 'Direction unverified, as above (this row used to say "widens the cone").'},
        {'In': '§6 item 26', 'Text': ('Not checked in a ship, and only the user can settle it: in Scan operator mode (knob '
                                     'detent 3), press lower hat ↑ a few times and watch whether the scan cone on the HUD '
                                     'gets wider or narrower.')}]},
    {'Control': 'js1 17', 'Part': 'salvage', 'Status': 'trial', 'Quote': [
        {'In': '§4 Salvage', 'Text': ('Trial (2026-11-26): push an object held by the vehicle tractor beam further out - for '
                                     'the Golem OX, whose tractor turret hangs off a salvage controller in the game files.')},
        {'In': '§6 item 15', 'Text': 'Update 2026-11-26: trial binding on the MHG lower hat ↑/↓ in Salvage mode (item 22); test it in the OX.'}]},
    {'Control': 'js1 19', 'Part': 'salvage', 'Status': 'trial', 'Quote': [
        {'In': '§4 Salvage', 'Text': 'Trial: pull the held object closer.'},
        {'In': '§6 item 15', 'Text': 'Update 2026-11-26: trial binding on the MHG lower hat ↑/↓ in Salvage mode (item 22); test it in the OX.'}]},
    {'Control': 'js1 24', 'Part': 'mining', 'Status': 'flown', 'When': '2026-11-27', 'Quote': [
        {'In': '§6 item 18', 'Text': ('Confirmed in flight by the user (2026-11-28): the rocker center switched the laser '
                                     'mode on all three ARC-L4 runs of 2026-11-27 in the Golem.')}]},
    {'Control': 'js1 24', 'Part': 'salvage', 'Status': 'unverified', 'Quote': [
        {'In': '§6 item 19', 'Text': 'Not yet tried in-ship.'}]},
    {'Control': 'js1 25', 'Part': None, 'Status': 'unverified', 'Quote': [
        {'In': '§6 item 20', 'Text': ('Loaded and validated in-game on 2026-11-26 (validate_actionmaps.py after each load '
                                     'of that day, §10.3).')},
        {'In': '§6 item 20', 'Text': 'Not reported from a flight since.'}]},
    {'Control': 'js1 26', 'Part': None, 'Status': 'unverified', 'Quote': [
        {'In': '§6 item 20', 'Text': ('Loaded and validated in-game on 2026-11-26 (validate_actionmaps.py after each load '
                                     'of that day, §10.3).')},
        {'In': '§6 item 20', 'Text': 'Not reported from a flight since.'}]},
    {'Control': 'js1 27', 'Part': None, 'Status': 'unverified', 'Quote': [
        {'In': '§6 item 20', 'Text': ('Loaded and validated in-game on 2026-11-26 (validate_actionmaps.py after each load '
                                     'of that day, §10.3).')},
        {'In': '§6 item 20', 'Text': 'Not reported from a flight since.'}]},
    {'Control': 'js1 28', 'Part': None, 'Status': 'unverified', 'Quote': [
        {'In': '§6 item 20', 'Text': ('Loaded and validated in-game on 2026-11-26 (validate_actionmaps.py after each load '
                                     'of that day, §10.3).')},
        {'In': '§6 item 20', 'Text': 'Not reported from a flight since.'}]},
    {'Control': 'js1 29', 'Part': None, 'Status': 'flown', 'When': '2026-11-26', 'Quote': [
        {'In': '§6 item 24', 'Text': 'Confirmed in flight (user, 2026-11-26 night): "pressing the coolie hat button goes in reverse now".'}]},
    {'Control': 'js1 49', 'Part': None, 'Status': 'unverified', 'Quote': [
        {'In': '§6 item 29', 'Text': 'The six moved bindings were written 2026-11-28, not yet loaded in game or flown.'}]},
    {'Control': 'js1 50', 'Part': None, 'Status': 'unverified', 'Quote': [
        {'In': '§6 item 29', 'Text': 'The six moved bindings were written 2026-11-28, not yet loaded in game or flown.'}]},
    {'Control': 'js1 51', 'Part': None, 'Status': 'unverified', 'Quote': [
        {'In': '§6 item 29', 'Text': 'The six moved bindings were written 2026-11-28, not yet loaded in game or flown.'}]},
    {'Control': 'js1 52', 'Part': None, 'Status': 'flown', 'When': '2026-11-26', 'Quote': [
        {'In': '§6 item 23', 'Text': 'The stick press (29) reversed fine, and so did the AB6 wing power panel.'}]},
    {'Control': 'js1 53', 'Part': None, 'Status': 'unverified', 'Quote': [
        {'In': '§6 item 29', 'Text': 'The six moved bindings were written 2026-11-28, not yet loaded in game or flown.'}]},
    {'Control': 'js1 54', 'Part': None, 'Status': 'unverified', 'Quote': [
        {'In': '§6 item 29', 'Text': 'The six moved bindings were written 2026-11-28, not yet loaded in game or flown.'}]},
    {'Control': 'js1 55', 'Part': None, 'Status': 'unverified', 'Quote': [
        {'In': '§6 item 29', 'Text': 'The six moved bindings were written 2026-11-28, not yet loaded in game or flown.'}]},
    {'Control': 'js1 56', 'Part': None, 'Status': 'flown', 'When': '2026-11-26', 'Quote': [
        {'In': '§6 item 23', 'Text': 'The stick press (29) reversed fine, and so did the AB6 wing power panel.'}]},
    {'Control': 'js2 1', 'Part': None, 'Status': 'unverified', 'Quote': [
        {'In': '§4 Mining', 'Text': 'Never tried in-ship.'}]},
    {'Control': 'js2 2', 'Part': None, 'Status': 'unverified', 'Quote': [
        {'In': '§4 Salvage', 'Text': ('Salvage bank on the MHG right hat (since 2026-11-26): ↑ focus all · ← / → focus '
                                     'left / right · ↓ flip the beam axis · press = gimbal reset, with fire left / right '
                                     'on MTQ A2 / A3.')},
        {'In': '§4 Salvage', 'Text': "None of the bank's functions has been confirmed in-ship in its new place (nor was it on the wings)."}]},
    {'Control': 'js2 3', 'Part': None, 'Status': 'unverified', 'Quote': [
        {'In': '§4 Salvage', 'Text': ('Salvage bank on the MHG right hat (since 2026-11-26): ↑ focus all · ← / → focus '
                                     'left / right · ↓ flip the beam axis · press = gimbal reset, with fire left / right '
                                     'on MTQ A2 / A3.')},
        {'In': '§4 Salvage', 'Text': "None of the bank's functions has been confirmed in-ship in its new place (nor was it on the wings)."}]},
    {'Control': 'js2 10', 'Part': None, 'Press': 'tap', 'Status': 'unverified', 'Quote': [
        {'In': '§4 Quantum travel, navigation & docking', 'Text': 'Not yet tried in a ship.'},
        {'In': '§4 Quantum travel, navigation & docking',
         'Text': 'On 2026-11-28 the user confirmed the hold on this key (Autoland) and reported nothing about the tap.'}]},
    {'Control': 'js2 10', 'Part': None, 'Press': 'hold', 'Status': 'flown', 'When': '2026-11-27', 'Quote': [
        {'In': '§4 Flight & movement',
         'Text': 'Confirmed in flight by the user (2026-11-28: Autoland worked on the Golem runs of 2026-11-27).'},
        {'In': '§6 item 23', 'Text': 'Autoland on the "AP" hold works (the user, 2026-11-28, after the Golem runs of 2026-11-27).'}]},
    {'Control': 'js2 52', 'Part': None, 'Status': 'flown', 'When': '2026-11-28', 'Quote': [
        {'In': '§4 Countermeasures & shield faces',
         'Text': 'Confirmed in flight by the user (2026-11-28): the four raises and the reset all work in the Corsair.'},
        {'In': '§6 item 14', 'Text': ("Update 2026-11-28: all five work in the Corsair, by the user's report: the four "
                                     'raises (js2 53 to 56) and the reset on the hat press (js2 52).')}]},
    {'Control': 'js2 53', 'Part': None, 'Status': 'flown', 'When': '2026-11-28', 'Quote': [
        {'In': '§4 Countermeasures & shield faces',
         'Text': 'Confirmed in flight by the user (2026-11-28): the four raises and the reset all work in the Corsair.'},
        {'In': '§6 item 14', 'Text': ("Update 2026-11-28: all five work in the Corsair, by the user's report: the four "
                                     'raises (js2 53 to 56) and the reset on the hat press (js2 52).')}]},
    {'Control': 'js2 54', 'Part': None, 'Status': 'flown', 'When': '2026-11-28', 'Quote': [
        {'In': '§4 Countermeasures & shield faces',
         'Text': 'Confirmed in flight by the user (2026-11-28): the four raises and the reset all work in the Corsair.'},
        {'In': '§6 item 14', 'Text': ("Update 2026-11-28: all five work in the Corsair, by the user's report: the four "
                                     'raises (js2 53 to 56) and the reset on the hat press (js2 52).')}]},
    {'Control': 'js2 55', 'Part': None, 'Status': 'flown', 'When': '2026-11-28', 'Quote': [
        {'In': '§4 Countermeasures & shield faces',
         'Text': 'Confirmed in flight by the user (2026-11-28): the four raises and the reset all work in the Corsair.'},
        {'In': '§6 item 14', 'Text': ("Update 2026-11-28: all five work in the Corsair, by the user's report: the four "
                                     'raises (js2 53 to 56) and the reset on the hat press (js2 52).')}]},
    {'Control': 'js2 56', 'Part': None, 'Status': 'flown', 'When': '2026-11-28', 'Quote': [
        {'In': '§4 Countermeasures & shield faces',
         'Text': 'Confirmed in flight by the user (2026-11-28): the four raises and the reset all work in the Corsair.'},
        {'In': '§6 item 14', 'Text': ("Update 2026-11-28: all five work in the Corsair, by the user's report: the four "
                                     'raises (js2 53 to 56) and the reset on the hat press (js2 52).')}]},
    {'Control': 'js2 57', 'Part': None, 'Status': 'unverified', 'Quote': [
        {'In': '§6 item 23', 'Text': 'Autoland on the "AP" hold and the rest of the rework were not reported then.'}]},
    {'Control': 'js2 58', 'Part': None, 'Status': 'unverified', 'Quote': [
        {'In': '§6 item 20', 'Text': ('Loaded and validated in-game on 2026-11-26 (validate_actionmaps.py after each load '
                                     'of that day, §10.3).')},
        {'In': '§6 item 20', 'Text': 'Not reported from a flight since.'}]},
    {'Control': 'js2 59', 'Part': None, 'Status': 'unverified', 'Quote': [
        {'In': '§6 item 20', 'Text': ('Loaded and validated in-game on 2026-11-26 (validate_actionmaps.py after each load '
                                     'of that day, §10.3).')},
        {'In': '§6 item 20', 'Text': 'Not reported from a flight since.'}]},
    {'Control': 'js2 60', 'Part': None, 'Status': 'unverified', 'Quote': [
        {'In': '§6 item 20', 'Text': ('Loaded and validated in-game on 2026-11-26 (validate_actionmaps.py after each load '
                                     'of that day, §10.3).')},
        {'In': '§6 item 20', 'Text': 'Not reported from a flight since.'}]},
    {'Control': 'js2 61', 'Part': None, 'Status': 'unverified', 'Quote': [
        {'In': '§6 item 20', 'Text': ('Loaded and validated in-game on 2026-11-26 (validate_actionmaps.py after each load '
                                     'of that day, §10.3).')},
        {'In': '§6 item 20', 'Text': 'Not reported from a flight since.'}]},
    {'Control': 'js2 RY', 'Part': None, 'Status': 'flown', 'When': '2026-11-27', 'Quote': [
        {'In': '§6 item 25', 'Text': ('Flown in the 6:13 PM and 7:14 PM sessions that day (two more trips to ARC-L4 in the '
                                     'Golem), and confirmed by the user at the end of the night: "throttle is good".')}]},
    {'Control': 'js2 Slider', 'Part': None, 'Status': 'flown', 'When': 'June 2026, Alpha 4.8', 'Quote': [
        {'In': '§4 Mining', 'Text': ("Confirmed in Golem: rest (up) = ~20% charge (the laser's minimum floor), FULL (down) "
                                    "= 100% - direction correct, no invert needed.")},
        {'In': '§11.1', 'Text': ('Fully covered and the only ship besides the Golem whose slider axis was confirmed '
                                'in-ship (June 2026, Alpha 4.8).')}]},
    {'Control': 'js2 Dial', 'Part': None, 'Status': 'flown', 'When': 'June 2026, Alpha 4.8', 'Quote': [
        {'In': '§4 Salvage', 'Text': ('Confirmed in Salvation: sweeping the lever opens/closes the gap across full travel '
                                     '(auto-mapped, no range to set).')},
        {'In': '§11.1', 'Text': ('Fully covered and the only ship besides the Golem whose slider axis was confirmed '
                                'in-ship (June 2026, Alpha 4.8).')}]},
]
# Advisory word lists, for a person to read (word_warnings): the generator prints a warning, and
# nothing fails, when no quote of a STATUS entry uses a word of its status, when an entry that is not
# a trial quotes the word "trial", or when no quote of a MAPS entry names a mode it calls live (or
# says "always" / "every" / "all") or dead (or says "only"). They do not read the sentences: a
# sentence can use the word and mean something else, and an honest one can say it in other words.
# They shape nothing in the rig files, so they are not in SOURCES.
MODE_WORDS = {'combat': r'(?i)\b(combat|guns?|SCM)\b', 'missile': r'(?i)\bmissiles?\b', 'scan': r'(?i)\bscan(ning)?\b',
              'mining': r'(?i)\bmining\b', 'salvage': r'(?i)\bsalvage\b',
              'live': r'(?i)\b(always|every|all)\b', 'dead': r'(?i)\bonly\b'}
STATUS_WORDS = {'flown': r'(?i)\b(confirmed|works|worked|reversed fine|goes in reverse|is good)\b',
                'unverified': r'(?i)\b(not yet|never|unverified|untested|not checked|not reported|reported nothing|none of)\b',
                'trial': r'(?i)\btrial\b'}

# The printed cards' diagram crops (x0, y0, x1, y1 in source pixels; the cards stack these six).
CARD_ART = [
    {'Id': 'mhg_front', 'Caption': 'MHG grip - front (hats & buttons)', 'File': 'MOZA_MHG.png', 'Box': (515, 90, 985, 575)},
    {'Id': 'mhg_side', 'Caption': 'MHG grip - side', 'File': 'MOZA_MHG.png', 'Box': (100, 168, 460, 770)},
    {'Id': 'ab6_base', 'Caption': 'AB6 base - wings & levers', 'File': 'MOZA_AB6.png', 'Box': (250, 110, 785, 650)},
    {'Id': 'mtq_panel', 'Caption': 'Throttle panel', 'File': 'MOZA_MTQ.png', 'Box': (60, 90, 612, 818)},
    {'Id': 'mtq_right', 'Caption': None, 'File': 'MOZA_MTQ.png', 'Box': (615, 72, 1045, 486)},
    {'Id': 'mtq_left', 'Caption': None, 'File': 'MOZA_MTQ.png', 'Box': (620, 488, 1045, 818)},
]

# The screen's diagram views, in the page's order (js1 then js2). Box = the crop out of File, in source
# pixels, before the art is trimmed to what is drawn. Buttons = the numbers whose discs the crop holds
# (read off the manufacturer art, CLAUDE.md section 3); every disc in a view is one of them, and a
# disc is in one view only (the generator checks both). A button row goes to the view whose Buttons
# hold all of its numbers. Axes = the axis rows listed with this view: {card label: [(word, box in
# source pixels holding that word as the art writes it: "Dial"; "X" and "Y")], or None where no view's
# crop shows the axis (MOZA draws the grip twist RZ below the front grip, outside every crop; the
# stick's X and Y and the throttle's Z / RZ nowhere)}. The generator shrinks each box to the word's ink.
# The throttle panel is cut in three (keypad, dials, levers): whole, it cannot be drawn large enough
# for its numbers on a near-square screen (dashboard/data/design/rig/NOTES.md, the designer's boxes).
VIEWS = [
    {'Id': 'grip_front', 'Device': 'js1', 'Title': 'Grip front', 'Caption': 'MHG grip, front: hats and buttons',
     'File': 'MOZA_MHG.png', 'Box': (515, 90, 985, 575), 'Buttons': '2, 5, 7-21, 25-29', 'Axes': {}},
    {'Id': 'grip_side', 'Device': 'js1', 'Title': 'Grip side', 'Caption': 'MHG grip, side: trigger, thumb and pinky buttons, rocker',
     'File': 'MOZA_MHG.png', 'Box': (126, 244, 433, 552), 'Buttons': '1, 3-4, 6, 22-24',
     'Axes': {'X': None, 'Y': None, 'RZ': None}},
    {'Id': 'base', 'Device': 'js1', 'Title': 'Base', 'Caption': 'AB6 base: wing buttons and levers',
     'File': 'MOZA_AB6.png', 'Box': (276, 226, 768, 596), 'Buttons': '49-62', 'Axes': {}},
    {'Id': 'keypad', 'Device': 'js2', 'Title': 'Keypad', 'Caption': 'MTQ throttle panel: keypad',
     'File': 'MOZA_MTQ.png', 'Box': (111, 492, 320, 760), 'Buttons': '1-10', 'Axes': {}},
    {'Id': 'dials', 'Device': 'js2', 'Title': 'Dials and switches', 'Caption': 'MTQ throttle panel: encoders, mode knob, rocker and toggles',
     'File': 'MOZA_MTQ.png', 'Box': (320, 492, 599, 760), 'Buttons': '11-30', 'Axes': {}},
    {'Id': 'levers', 'Device': 'js2', 'Title': 'Levers', 'Caption': 'MTQ throttle panel: levers, detents and axes',
     'File': 'MOZA_MTQ.png', 'Box': (111, 146, 503, 490), 'Buttons': '31-43',
     'Axes': {'RY': [('RY', (354, 168, 374, 185))], 'Z / RZ': None, 'Slider': [('Slider', (438, 168, 474, 185))],
              'Dial': [('Dial', (143, 168, 170, 185))], 'RX': [('RX', (243, 168, 261, 185))]}},
    {'Id': 'right_module', 'Device': 'js2', 'Title': 'Right module', 'Caption': 'MTQ right module: switch, WPN hat and COM hat',
     'File': 'MOZA_MTQ.png', 'Box': (615, 72, 1045, 486), 'Buttons': '49-61', 'Axes': {}},
    {'Id': 'left_module', 'Device': 'js2', 'Title': 'Left module', 'Caption': 'MTQ left module: mini-stick, throttle dial and button',
     'File': 'MOZA_MTQ.png', 'Box': (620, 488, 1045, 818), 'Buttons': '62-65',
     'Axes': {'X / Y': [('X', (943, 540, 955, 556)), ('Y', (883, 591, 896, 607))]}},
]

# MOZA's sample readings, painted out of the screen views (a number on a live dashboard reads as live):
# the numbers only, so the axis words beside two of them ("X 32767", "Y 32767") keep their X and Y.
# Box in source pixels; the pixels go transparent, or with Cap are dimmed to that brightness (the two
# lit level bars to the unlit ones' 142, so all four bars look alike). The printed cards keep them.
READINGS = [
    {'File': 'MOZA_MTQ.png', 'What': 'Dial reading 65535', 'Box': (144, 191, 179, 204)},
    {'File': 'MOZA_MTQ.png', 'What': 'RX reading 0', 'Box': (225, 191, 235, 204)},
    {'File': 'MOZA_MTQ.png', 'What': 'RY reading 0', 'Box': (356, 191, 365, 204)},
    {'File': 'MOZA_MTQ.png', 'What': 'Slider reading 65535', 'Box': (440, 191, 476, 204)},
    {'File': 'MOZA_MTQ.png', 'What': 'Dial level bar, lit', 'Box': (178, 146, 191, 233), 'Cap': 142},
    {'File': 'MOZA_MTQ.png', 'What': 'Slider level bar, lit', 'Box': (423, 146, 436, 233), 'Cap': 142},
    {'File': 'MOZA_MTQ.png', 'What': 'mini-stick reading 0, top', 'Box': (898, 492, 906, 503)},
    {'File': 'MOZA_MTQ.png', 'What': 'mini-stick reading 0, left', 'Box': (847, 543, 856, 553)},
    {'File': 'MOZA_MTQ.png', 'What': 'mini-stick X reading 32767', 'Box': (956, 542, 993, 553)},
    {'File': 'MOZA_MTQ.png', 'What': 'mini-stick Y reading 32767', 'Box': (897, 593, 933, 604)},
]

# Where each number disc is, roughly, in source pixels (read off the art): the generator finds the
# discs itself (find_discs) and uses these only to name them. Each must fall inside exactly one disc
# found in its view, and every disc found must get exactly one.
DISCS = {
    'js1': {1: (390, 414), 2: (688, 279), 3: (300, 520), 4: (329, 302), 5: (785, 325), 6: (340, 414),
            7: (581, 289), 8: (617, 324), 9: (581, 360), 10: (546, 324), 11: (581, 324), 12: (899, 244),
            13: (935, 280), 14: (899, 316), 15: (864, 280), 16: (899, 280), 17: (580, 462), 18: (616, 497),
            19: (580, 533), 20: (545, 497), 21: (580, 497), 22: (372, 299), 23: (372, 342), 24: (372, 320),
            25: (738, 133), 26: (774, 169), 27: (738, 204), 28: (702, 169), 29: (738, 169),
            49: (418, 299), 50: (418, 346), 51: (418, 391), 52: (418, 437), 53: (638, 299), 54: (638, 346),
            55: (638, 391), 56: (638, 437), 57: (286, 463), 58: (286, 507), 59: (286, 551), 60: (757, 463),
            61: (758, 507), 62: (757, 550)},
    'js2': {1: (154, 552), 2: (154, 601), 3: (154, 650), 4: (154, 699), 5: (226, 562), 6: (284, 562),
            7: (226, 629), 8: (284, 628), 9: (226, 694), 10: (284, 694), 11: (343, 534), 12: (385, 534),
            13: (364, 555), 14: (343, 604), 15: (385, 603), 16: (364, 625), 17: (515, 554), 18: (526, 529),
            19: (552, 518), 20: (577, 528), 21: (588, 554), 22: (440, 623), 23: (419, 622), 24: (464, 622),
            25: (358, 706), 26: (357, 726), 27: (407, 706), 28: (406, 726), 29: (455, 706), 30: (456, 726),
            31: (130, 331), 32: (237, 421), 33: (237, 394), 34: (329, 421), 35: (329, 394), 36: (477, 447),
            37: (477, 407), 38: (477, 366), 39: (477, 326), 40: (477, 286), 41: (237, 297), 42: (329, 297),
            43: (130, 301), 49: (854, 299), 50: (878, 298), 51: (833, 298), 52: (859, 135), 53: (896, 135),
            54: (823, 135), 55: (859, 172), 56: (859, 99), 57: (980, 229), 58: (1017, 229), 59: (944, 229),
            60: (980, 265), 61: (980, 192), 62: (688, 600), 63: (799, 620), 64: (828, 611), 65: (736, 621)},
}

# How find_discs tells a number disc in a screen image (test_rig.py runs the same on the PNGs):
# opacity level >= Level is ink; a closing (radius Close) bridges the cuts the digits make, holes are
# filled, an opening (radius Open) drops leader lines thinner than 2 * Open + 1 px; what is left counts
# as a disc when both sides are within Size, the sides' ratio within Aspect and it fills its box to at
# least Fill. Digit pixels are the disc's pixels at level <= Dark (their height is measured). A disc
# is round when every one of its pixels lies within Round px outside the circle of its box's longer
# side; otherwise it is a box (the rocker, toggle and switch badges). Ink = the level an axis word's
# pixels reach (Axes boxes are shrunk to it).
DISC_FINDER = {'Level': 12, 'Close': 1, 'Open': 2, 'Size': (11, 32), 'Aspect': (0.55, 1.8), 'Fill': 0.6, 'Dark': 6,
               'Round': 1.5, 'Ink': 6}

# How the screen views are drawn (the page is dark; the cards are dark on white). Brightness is the
# source's brightest channel, mapped to opacity: below Ground is the navy backdrop (fully transparent),
# Full and above (the number discs) fully opaque, the faint line work in between, so the numbers stand
# out from the outline. Levels = opacity steps; 16 fits a 4-bit PNG and looks the same as 256 next to
# it. Pad = px of margin kept round the drawn part. The code that makes the rig files (everything in
# this file from the "dashboard rig reference" heading to main) is hashed into rig.json too, so a
# change there makes test_rig.py ask for a regeneration.
RIG_ART = {'Color': '#E4ECF2', 'Ground': 0.25, 'Full': 0.82, 'Gamma': 0.8, 'Levels': 16, 'Pad': 2}

# The names of the discs, pinned: per device and button number, a hash of the source art's pixels
# under that button's disc (fingerprint()), taken when every name was read by eye against the art (the
# review of 2026-11-28 read all 103 numbers on contact sheets). The generator and test_rig.py fail when
# a name lands on another disc, or the art or the disc finder changed. Then re-verify by eye:
#     python tools/regen_cards.py --sheets <a folder outside the repo>
# writes one contact sheet per view (each disc cut from the art, enlarged, with the number the data
# gives it); read every tile, fix DISCS if a name is wrong, then paste the output of
#     python tools/regen_cards.py --fingerprints
FINGERPRINTS = {
    'js1': {1: '9d751bc003', 2: '7f401f9fd0', 3: '18d7a7d76e', 4: '46133d1843', 5: '8e0888d372', 6: '975e9bbc5b',
            7: '013bcc3477', 8: '9ffd4a5996', 9: '3343c8a29e', 10: '353ec8896c', 11: '438aed5587', 12: '0fb8c766cb',
            13: '1b5435b992', 14: 'bbdef2163e', 15: 'cfd83a8f0d', 16: 'b46ae3643e', 17: 'ef6066942c', 18: '2e5cace4d2',
            19: 'f75b35240c', 20: 'eb09caa78c', 21: 'a9d951f515', 22: '5a265fcc02', 23: 'f6a0776f59', 24: '418efc29b5',
            25: '71f3f4a34e', 26: 'da86e6dd87', 27: 'ae31b6bbb4', 28: '4a340aae41', 29: 'e6c3fcb610', 49: '0b1f916fd2',
            50: 'b3cfd3e6fc', 51: '08c60ddeb3', 52: 'ce2d112d36', 53: 'd170226838', 54: '8e3ea78912', 55: 'a590f92bd6',
            56: '84ae047bd0', 57: '4417219e47', 58: '6e09a9b775', 59: '25f58c7597', 60: 'a183f036dd', 61: '073c60928e',
            62: '263a60c885'},
    'js2': {1: 'bbe9c46eef', 2: 'e0c73e9e61', 3: '392fdd5c26', 4: '836d6b5199', 5: '91358164eb', 6: 'f6e55e5899',
            7: '630bef5bfe', 8: 'a25ec327c7', 9: '967d6d0679', 10: '1a2232c902', 11: 'd0bc20388f', 12: '9ab18a481a',
            13: 'a77138f4ae', 14: '7d407a3da7', 15: 'd9ba53afd6', 16: '9c6e6d29b3', 17: '6f0ffc2cc1', 18: '890ecf8e56',
            19: 'da42259581', 20: 'de2ceba9d9', 21: 'e3161e4816', 22: 'a2371737c2', 23: '76ec8688bb', 24: '991370c462',
            25: '07afcfbae7', 26: 'd488b42c4d', 27: '7fa2c461e8', 28: '205a5528a2', 29: '30973e3c09', 30: 'cf5151f44e',
            31: '7f614232fb', 32: '7439c2847d', 33: '764430a3c3', 34: '1160258afb', 35: '936ebd1df6', 36: '65509842ab',
            37: 'd989dbe3f1', 38: '9a09c88a27', 39: '228168acec', 40: '3386b364d0', 41: '9daf035abe', 42: 'c3d0e90662',
            43: '58859748c7', 49: '99d9eed457', 50: 'f62a7d6761', 51: '352a28ee26', 52: 'b32b4842fb', 53: 'd86d611e22',
            54: '0cdea928ba', 55: 'e73b5c3b3a', 56: '0f58fcc28d', 57: '8ede03a31f', 58: 'c2583e9052', 59: '70816b7c54',
            60: 'd41c7ab85a', 61: 'f3796c0d44', 62: 'c978b1e415', 63: '0139581fff', 64: '0574f57bd5', 65: '00e4fa0698'},
}

SOURCES = ['AB6', 'MHG_L', 'MHG_R', 'MTQ_L', 'MTQ_R', 'CARDS', 'MODES', 'LIVE_MODES', 'MAPS', 'STATUS',
           'CARD_ART', 'VIEWS', 'READINGS', 'DISCS', 'DISC_FINDER', 'RIG_ART', 'FINGERPRINTS']
RIG_SCHEMA = 2


# ================================================================ dashboard rig reference
def screen_art(view):
    """One screen view: its crop of the source art for the dark page, MOZA's sample readings painted
    out, one light color whose opacity follows the art's brightness, trimmed to the drawn part. Native
    pixels, never scaled. Returns (image, alpha per palette entry, (x, y) of its top-left in source px)."""
    a = RIG_ART
    x0, y0, x1, y1 = view['Box']
    src = Image.open(DIAG_DIR / view['File']).convert('RGBA')
    r, g, b, alpha = src.split()
    # The brightest channel, not luma: MOZA's green "pressed" discs (a state at capture time, not a
    # binding) then come out as bright as the gray ones, where luma would dim them to about 3/4.
    val = ImageChops.multiply(ImageChops.lighter(ImageChops.lighter(r, g), b), alpha)
    for rd in READINGS:
        if rd['File'] != view['File']:
            continue
        box = rd['Box']
        part = val.crop(box)
        val.paste(part.point(lambda v, c=rd['Cap']: min(v, c)) if 'Cap' in rd else 0, box)
    val = val.crop((x0, y0, x1, y1))
    n, lo, hi = a['Levels'], a['Ground'] * 255, a['Full'] * 255
    lut = [round(max(0.0, min(1.0, (v - lo) / (hi - lo))) ** a['Gamma'] * (n - 1)) for v in range(256)]
    idx = val.point(lut)
    bx0, by0, bx1, by1 = idx.getbbox()
    p = a['Pad']
    trim = (max(0, bx0 - p), max(0, by0 - p), min(idx.width, bx1 + p), min(idx.height, by1 + p))
    idx = idx.crop(trim)
    out = Image.frombytes('P', idx.size, idx.tobytes())
    rgb = [int(a['Color'][i:i + 2], 16) for i in (1, 3, 5)]
    out.putpalette(rgb * n)                       # n entries -> Pillow writes a 4-bit PNG for n <= 16
    return out, bytes(round(i * 255 / (n - 1)) for i in range(n)), (x0 + trim[0], y0 + trim[1])


def _rows_mask(levels, w, h, lo):
    """Row bitsets of the pixels at level >= lo (bit x of row y = pixel x, y)."""
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
    return [_or_rows(hor, y - k, y + k) for y in range(h)]


def _or_rows(rows, a, b):
    o = 0
    for y in range(max(0, a), min(len(rows), b + 1)):
        o |= rows[y]
    return o


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


def _fill_holes(rows, w):
    full, h = (1 << w) - 1, len(rows)
    inv = [(~r) & full for r in rows]
    edge = 1 | (1 << (w - 1))
    out = [inv[y] if y in (0, h - 1) else inv[y] & edge for y in range(h)]
    changed = True
    while changed:
        changed = False
        for y in range(h):
            o = out[y]
            n = o | (o << 1) | (o >> 1) | (out[y - 1] if y else 0) | (out[y + 1] if y < h - 1 else 0)
            n &= inv[y]
            if n != o:
                out[y], changed = n, True
    return [(~o) & full for o in out]


def find_discs(levels, w, h):
    """The number discs in a screen image: [(x0, y0, w, h, digit height, box)], top to bottom, then left
    to right. levels = the opacity level (0 .. Levels-1) of each pixel, row by row. See DISC_FINDER."""
    f = DISC_FINDER
    m = _rows_mask(levels, w, h, f['Level'])
    m = _erode(_dilate(m, f['Close'], w), f['Close'], w)
    m = _fill_holes(m, w)
    m = _dilate(_erode(m, f['Open'], w), f['Open'], w)
    seen, found = set(), []
    for y in range(h):
        r = m[y]
        while r:
            low = r & -r
            x = low.bit_length() - 1
            r ^= low
            if (x, y) in seen:
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
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            bx, by = min(xs), min(ys)
            bw, bh = max(xs) - bx + 1, max(ys) - by + 1
            if not (f['Size'][0] <= bw <= f['Size'][1] and f['Size'][0] <= bh <= f['Size'][1]):
                continue
            if not (f['Aspect'][0] <= bw / bh <= f['Aspect'][1]) or len(pts) < f['Fill'] * bw * bh:
                continue
            dark = [py for px_, py in pts if levels[py * w + px_] <= f['Dark']]
            cx, cy, rr = bx + bw / 2, by + bh / 2, max(bw, bh) / 2 + f['Round']
            box = any((px_ + 0.5 - cx) ** 2 + (py + 0.5 - cy) ** 2 > rr * rr for px_, py in pts)
            found.append((bx, by, bw, bh, max(dark) - min(dark) + 1 if dark else 0, box))
    return sorted(found, key=lambda d: (d[1], d[0]))


def pixel_hash(img):
    """Short hash of an image's pixels as RGBA (the PNG's palette and transparency applied), with its
    size; test_rig.py decodes the PNG with the standard library and computes the same."""
    rgba = img.convert('RGBA')
    return hashlib.sha256(b'%dx%d:' % rgba.size + rgba.tobytes()).hexdigest()[:16]


def parse_buttons(spec):
    """'2, 5, 7-21' -> {2, 5, 7, ..., 21}."""
    out = set()
    for part in spec.split(','):
        lo, _, hi = part.strip().partition('-')
        out.update(range(int(lo), int(hi or lo) + 1))
    return out


def label_numbers(label):
    """The button numbers a card label names ('12' -> {12}, '57-59' -> {57, 58, 59}); None for an axis."""
    m = re.fullmatch(r'(\d+)(?:-(\d+))?', label)
    if not m:
        return None
    return set(range(int(m.group(1)), int(m.group(2) or m.group(1)) + 1))


def row_id(dev, label):
    """The stable id of a card row: device + label ('js1-12', 'js1-57-59', 'js2-x-y')."""
    return dev + '-' + re.sub(r'[^a-z0-9]+', '-', label.lower()).strip('-')


def digest(obj):
    """Short hash of a JSON-able value; test_rig.py computes the same from its `ast` read."""
    raw = json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    return hashlib.sha256(raw).hexdigest()[:12]


def card_sources():
    """Everything rig.json is made from that lives in this file (the literals in SOURCES)."""
    g = globals()
    return {n: g[n] for n in SOURCES}


def canon(node):
    """A stable text of parsed code, for the code hash: each node's type and fields, without positions,
    docstrings or empty fields, and with the two forms only Python 3.8 writes (Index, ExtSlice)
    unwrapped. So every Python from 3.8 gives the same text for the same code; ast.dump does not (3.13
    leaves out the empty fields earlier versions print). test_rig.py has the same function."""
    if isinstance(node, list):
        return '[' + ', '.join(canon(x) for x in node) + ']'
    if not isinstance(node, ast.AST):
        return repr(node)
    kind = type(node).__name__
    if kind == 'Index':
        return canon(node.value)
    if kind == 'ExtSlice':
        return 'Tuple(elts=%s, ctx=Load())' % canon(node.dims)
    fields = []
    for name, value in ast.iter_fields(node):
        if name == 'body' and isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and value \
                and isinstance(value[0], ast.Expr) and isinstance(value[0].value, ast.Constant) \
                and isinstance(value[0].value.value, str):
            value = value[1:]                      # the docstring
        if value is None or value == [] or name in ('kind', 'type_comment'):
            continue
        fields.append('%s=%s' % (name, canon(value)))
    return '%s(%s)' % (kind, ', '.join(fields))


def rig_code():
    """The code that makes the rig files, as Python reads it: canon() of `jnum` and of every statement
    between the "dashboard rig reference" heading and `def main`. Comments, blank lines and docstrings
    do not count, so only a change to the code itself moves _meta.hash.code (test_rig.py hashes the
    same)."""
    text = Path(__file__).read_text(encoding='utf-8')
    lines = text.split('\n')
    a = next(i for i, ln in enumerate(lines) if ln.startswith('# ====') and ln.endswith(' dashboard rig reference')) + 1
    b = next(i for i, ln in enumerate(lines) if ln.startswith('def main(')) + 1
    keep = [n for n in ast.parse(text).body
            if a < n.lineno < b or (isinstance(n, ast.FunctionDef) and n.name == 'jnum')]
    return '\n'.join(canon(n) for n in keep)


def word_warnings():
    """The advisory word checks (see STATUS_WORDS), as lines for a person to read. Nothing fails on
    them; write_rig() and main() print them."""
    out = []
    for s in STATUS:
        key = (s['Control'], s['Part'], s.get('Press'))
        texts = [q.get('Text') or '' for q in s.get('Quote') or []]
        words = STATUS_WORDS.get(s['Status'])
        if words and not any(re.search(words, t) for t in texts):
            out.append('STATUS %r: no quote uses a word of "%s"' % (key, s['Status']))
        if s['Status'] != 'trial' and any(re.search(STATUS_WORDS['trial'], t) for t in texts):
            out.append('STATUS %r is %s, but a quote says "trial"' % (key, s['Status']))
    for amap, spec in sorted(MAPS.items()):
        texts = [q['Text'] for q in spec['Why']]
        for m in [x['Mode'] for x in MODES]:
            kind = 'live' if m in spec['Live'] else None if m in spec['Unknown'] else 'dead'
            if kind and not any(re.search(MODE_WORDS[m], t) or re.search(MODE_WORDS[kind], t) for t in texts):
                out.append('MAPS %s: no quote names %s mode, or says why the map is %s everywhere' % (amap, m, kind))
    return out


def print_word_warnings():
    for w in word_warnings():
        print('  warning (advisory; read the quote and the status together): ' + w)


def fingerprint(art, box):
    """The fingerprint of a disc: a short hash of the source art's RGBA pixels inside box (source px)."""
    crop = art.crop(box)
    return hashlib.sha256(b'%dx%d:' % crop.size + crop.tobytes()).hexdigest()[:10]


def read_profile():
    """MOZA.xml: the bindings [(actionmap, action, input, activationMode or None)] in file order, clears
    left out, and the set of (actionmap, action) the file names at all (a rebind or a clear)."""
    root = ET.parse(str(PROFILE)).getroot()
    binds, named = [], set()
    for am in root.iter('actionmap'):
        for a in am.findall('action'):
            named.add((am.get('name'), a.get('name')))
            for r in a.findall('rebind'):
                inp = r.get('input') or ''
                if re.fullmatch(r'[a-z]+\d+_\s*', inp):
                    continue                              # "js1_ " clears a stock binding
                binds.append((am.get('name'), a.get('name'), inp, r.get('activationMode')))
    return binds, named


def catalog_path():
    found = sorted(CATALOG_DIR.glob('SC_KEYBINDS_DATABASE_v*.md'),
                   key=lambda p: [int(x) for x in re.findall(r'\d+', p.stem)])
    if not found:
        sys.exit('regen_cards: no reference/SC_KEYBINDS_DATABASE_v*.md (python tools/gamedata.py catalog writes it).')
    return found[-1]


def read_catalog():
    """The action catalog in reference/: {(actionmap, action): {label, joystick, activation}}."""
    out, amap = {}, None
    for line in catalog_path().read_text(encoding='utf-8').splitlines():
        m = re.match(r'## (\S+)\s*$', line)
        if m:
            amap = m.group(1)
            continue
        m = re.match(r'\| `([^`]+)` \|(.*)\|\s*$', line)
        if m and amap:
            cells = [c.strip() for c in m.group(2).split('|')]
            if len(cells) == 6:
                out[(amap, m.group(1))] = {'label': cells[0], 'joystick': cells[3], 'activation': cells[5]}
    return out


HOLD_MODES = ('delayed_press', 'hold', 'delayed_hold', 'delayed_hold_no_retrigger')
STATUSES = ('flown', 'unverified', 'trial')
STATUS_DOUBT = {'flown': 0, None: 1, 'unverified': 2, 'trial': 3}    # a tap / hold pair: the more doubtful


def rig_doc(images, pin=True):
    """rig.json as a dict, and the fingerprints of the named discs. images = {view id: (file name, w, h,
    pixel hash, (x, y) origin, discs, levels)}. pin=False skips the fingerprint check (--fingerprints).
    Exits, having written nothing, when anything does not add up."""
    problems = []
    tables = card_sources()
    mode_ids = [m['Mode'] for m in MODES]
    mode_of = {m['Tag']: m['Mode'] for m in MODES if m['Tag']}
    binds, named = read_profile()
    cat = read_catalog()

    for rd in READINGS:                  # a reading box must cover something: the art may have moved
        src = Image.open(DIAG_DIR / rd['File']).convert('RGBA')
        r, g, b, alpha = src.split()
        val = ImageChops.multiply(ImageChops.lighter(ImageChops.lighter(r, g), b), alpha).crop(rd['Box'])
        if val.getextrema()[1] <= RIG_ART['Ground'] * 255:
            problems.append('READINGS %r covers no ink in %s' % (rd['What'], rd['File']))
        if 'Cap' in rd and val.getextrema()[1] <= rd['Cap']:
            problems.append('READINGS %r: nothing in it is brighter than its Cap' % rd['What'])
    for amap, spec in sorted(MAPS.items()):
        if set(spec['Live']) & set(spec['Unknown']) or not set(spec['Live'] + spec['Unknown']) <= set(mode_ids):
            problems.append('MAPS %s: a mode is twice or not a mode' % amap)
        if (spec['Live'] or len(spec['Unknown']) < len(mode_ids)) and not spec['Why']:
            problems.append('MAPS %s: live or dead somewhere, and cites nothing' % amap)
        if spec['Unknown'] and not spec.get('Note'):
            problems.append('MAPS %s: an unknown cell without a Note' % amap)
    on_input = {}
    for amap, action, inp, act_mode in binds:
        if amap not in MAPS:
            problems.append('MOZA.xml binds %s/%s, an actionmap MAPS does not list' % (amap, action))
            continue
        e = cat.get((amap, action))
        if e is None:
            problems.append('%s/%s is not in the catalog %s' % (amap, action, catalog_path().name))
            continue
        on_input.setdefault(inp, []).append({'map': amap, 'action': action, 'label': e['label'],
                                             'activation': act_mode or e['activation'] or None})
    # Stock joystick bindings the profile leaves in place (they land on js1, CLAUDE.md section 2.5), in
    # the maps above: the trigger's "fire the selected weapon preset" is the one there is.
    for (amap, action), e in sorted(cat.items()):
        if amap in MAPS and e['joystick'] and (amap, action) not in named \
                and re.fullmatch(r'[a-z]+\d*(?:_[a-z]+)?', e['joystick']):
            on_input.setdefault('js1_' + e['joystick'], []).append(
                {'map': amap, 'action': action, 'label': e['label'], 'activation': e['activation'] or None, 'stock': True})

    status_of = {}
    for s in STATUS:
        key = (s['Control'], s['Part'], s.get('Press'))
        if key in status_of or s['Status'] not in STATUSES:
            problems.append('STATUS %r is twice or has an unknown status' % (key,))
        if not s.get('Quote') or not all(q.get('In') and q.get('Text') for q in s['Quote']):
            problems.append('STATUS %r cites nothing, or a quote without In' % (key,))
        status_of[key] = s
    used = set()

    def status(control, part, press=None):
        s = status_of.get((control, part, press))
        if s:
            used.add((control, part, press))
        return s

    def put_status(e, s):
        """status, status_ref and status_when of a row, job or variant from its STATUS entry."""
        if s:
            e['status'] = s['Status']
            e['status_ref'] = '; '.join(dict.fromkeys(q['In'] for q in s['Quote']))
            if s.get('When'):
                e['status_when'] = s['When']

    rows, covered = [], set()
    for card in CARDS:
        dev = card['Device']
        for t in card['Tables']:
            for r in tables[t]:
                if 'Label' not in r:
                    continue                                    # a column header on the card
                label, control = r['Label'], '%s %s' % (dev, r['Label'])
                nums = label_numbers(label)
                buttons = sorted(nums) if nums else []
                inputs = ['%s_button%d' % (dev, n) for n in buttons] if nums else list(r.get('Inputs') or [])
                if not inputs or (nums and r.get('Inputs')):
                    problems.append('%s: no inputs, or Inputs on a button row' % control)
                if nums:
                    home = [v for v in VIEWS if v['Device'] == dev and nums <= parse_buttons(v['Buttons'])]
                else:
                    home = [v for v in VIEWS if v['Device'] == dev and label in v['Axes']]
                if len(home) != 1:
                    problems.append('%s fits %d views' % (control, len(home)))
                    continue
                vmodes = [mode_of.get(v['Tag']) for v in r.get('Variants') or []]
                if None in vmodes:
                    problems.append('%s: a variant tag is not in MODES' % control)
                    continue
                if sorted((r.get('ScreenVariants') or {})) != sorted(vmodes) or not r.get('Screen') \
                        or not r.get('Where') or not r.get('Group'):
                    problems.append('%s: Screen, Where, Group or ScreenVariants missing' % control)
                words = [r.get('Screen', ''), r.get('Where', '')] + list((r.get('ScreenVariants') or {}).values()) \
                    + [j['Screen'] for j in r.get('Jobs') or []]
                if any(re.search(r'\b(trial|unverified|flown)\b', w, re.I) for w in words):
                    problems.append('%s: a status word in the screen wording' % control)

                acts = []
                for inp in inputs:
                    covered.add(inp)
                    for a in on_input.get(inp, []):
                        spec = MAPS[a['map']]
                        part = spec['Live'][0] if (len(spec['Live']) == 1 and not spec['Unknown']
                                                    and spec['Live'][0] in vmodes) else 'primary'
                        acts.append(dict({'part': part}, **a))
                real = [a for a in acts if not a.get('stock')]
                if r.get('Unbound'):
                    if real:
                        problems.append('%s is marked unbound but MOZA.xml binds %s' % (control, real[0]['action']))
                elif not any(a['part'] == 'primary' for a in real):
                    problems.append('%s has a function but MOZA.xml binds nothing on %s' % (control, ', '.join(inputs)))
                for m in vmodes:
                    if not any(a['part'] == m for a in real):
                        problems.append('%s: the %s variant has no MOZA.xml action' % (control, m))
                # The row names the actions its wording describes; MOZA.xml must bind exactly those.
                said = {'primary': list(r.get('Actions', [None]))}
                said.update({m: list(x) for m, x in (r.get('VariantActions') or {}).items()})
                if sorted(said) != sorted(['primary'] + vmodes):
                    problems.append('%s: Actions / VariantActions do not match the card variants' % control)
                for part, names in sorted(said.items()):
                    got = sorted(a['action'] for a in real if a['part'] == part)
                    if sorted(names) != got:
                        problems.append('%s: the card says %s for %s, MOZA.xml binds %s on %s'
                                        % (control, sorted(names), part, got, ', '.join(inputs)))
                prim = [a for a in acts if a['part'] == 'primary' and MAPS[a['map']]['Live']]
                for i, a1 in enumerate(prim):       # one primary, so its jobs share a mode (else: a variant)
                    for a2 in prim[i + 1:]:
                        if not set(MAPS[a1['map']]['Live']) & set(MAPS[a2['map']]['Live']):
                            problems.append('%s: %s and %s act in different modes; the card needs a variant for one'
                                            % (control, a1['action'], a2['action']))

                modes = {}
                for m in mode_ids:
                    live = {a['part'] for a in acts if m in MAPS[a['map']]['Live']}
                    unknown = {a['part'] for a in acts if m in MAPS[a['map']]['Unknown']}
                    if len(live) > 1:
                        problems.append('%s: %s are all live in %s mode (one press fires both)' % (control, sorted(live), m))
                    modes[m] = ('variant' if m in live else 'primary') if live else ('unknown' if unknown else 'none')
                for m in vmodes:
                    if modes[m] != 'variant':
                        problems.append('%s: the %s variant is not live in %s mode' % (control, m, m))

                row = {'id': row_id(dev, label), 'device': dev, 'label': label, 'buttons': buttons,
                       'inputs': inputs, 'view': home[0]['Id'],
                       'drawn': bool(nums) or home[0]['Axes'][label] is not None,
                       'text': r['Screen'], 'where': r['Where'], 'group': r['Group']}
                if r.get('Unbound'):
                    row['unbound'] = True
                if r.get('Jobs'):
                    jobs, prim = [], {a['action'] for a in real if a['part'] == 'primary'}
                    if {x for j in r['Jobs'] for x in j['Actions']} != prim:
                        problems.append('%s: Jobs do not name exactly the primary actions %s' % (control, sorted(prim)))
                    whole = status(control, None)
                    for j in r['Jobs']:
                        modes_of = {a['activation'] for a in real if a['action'] in j['Actions']}
                        if not modes_of or not all((x == 'tap') if j['Press'] == 'tap' else (x in HOLD_MODES) for x in modes_of):
                            problems.append('%s: the %s job is %s in the profile' % (control, j['Press'], sorted(modes_of)))
                        s = status(control, None, j['Press']) or whole
                        e = {'press': j['Press'], 'text': j['Screen'], 'actions': list(j['Actions'])}
                        jm = [MAPS[a['map']] for a in real if a['action'] in j['Actions']]
                        e['modes'] = {m: 'live' if any(m in x['Live'] for x in jm) else
                                      'unknown' if any(m in x['Unknown'] for x in jm) else 'none' for m in mode_ids}
                        put_status(e, s)
                        jobs.append(e)
                    worst = max((j.get('status') for j in jobs), key=lambda x: STATUS_DOUBT[x])
                    if worst:
                        row['status'] = worst
                        if whole:
                            put_status(row, whole)
                    row['jobs'] = jobs
                else:
                    put_status(row, status(control, None))
                if r.get('Unbound') and row.get('status'):
                    problems.append('%s is unbound and has a status' % control)
                variants = []
                for var, m in zip(r.get('Variants') or [], vmodes):
                    e = {'mode': m, 'text': r['ScreenVariants'][m], 'card': var['Text']}
                    put_status(e, status(control, m))
                    variants.append(e)
                if variants:
                    row['variants'] = variants
                cardw = {'primary': r['Primary']}
                if r.get('Hint'):
                    cardw['hint'] = r['Hint']
                row['card'] = cardw
                row['modes'] = modes
                row['actions'] = acts
                row['discs'] = []                              # filled in with the views below
                rows.append(row)
    for inp in sorted({b[2] for b in binds} - covered):
        problems.append('MOZA.xml binds %s, which no card row names' % inp)
    for key in sorted(set(status_of) - used, key=str):
        problems.append('STATUS %r matches no function on the cards' % (key,))

    # The modes, with the knob detent the profile gives each.
    modes_out = []
    for m in MODES:
        inp = [b[2] for b in binds if b[1] == m['Set']]
        mm = re.fullmatch(r'(js\d+)_button(\d+)', inp[0]) if len(inp) == 1 else None
        if not mm:
            problems.append('mode %s: %s is not on one button in MOZA.xml' % (m['Mode'], m['Set']))
            continue
        knob_row = next((x for x in rows if x['device'] == mm.group(1) and x['buttons'] == [int(mm.group(2))]), None)
        if knob_row is None or not knob_row['card'].get('hint', '').endswith('knob detent %d' % m['Detent']):
            problems.append('mode %s: the card row of %s does not say knob detent %d' % (m['Mode'], inp[0], m['Detent']))
            continue
        modes_out.append({'id': m['Mode'], 'name': m['Name'], 'operator': m['Operator'], 'tag': m['Tag'],
                          'knob': {'device': mm.group(1), 'button': int(mm.group(2)), 'detent': m['Detent'],
                                   'row': knob_row['id']}})
    for k, v in LIVE_MODES.items():
        if not v or not set(v) <= set(mode_ids) or len(set(v)) != len(v):
            problems.append('LIVE_MODES %s -> %s: not a list of modes' % (k, v))

    # The views, and each row's marks on its view: the number discs (named by DISCS) and the axis words.
    notes_of = {}
    for c in CARDS:
        for note in c['Notes']:
            for vid in note['Views']:
                if not any(v['Id'] == vid and v['Device'] == c['Device'] for v in VIEWS):
                    problems.append('a note of %s names %s, not one of its views' % (c['Device'], vid))
                notes_of.setdefault(vid, []).append(note['Text'])
    views, prints, arts = [], {}, {}
    for v in VIEWS:
        name, w, h, phash, (ox, oy), discs, levels = images[v['Id']]
        claimed = sorted(parse_buttons(v['Buttons']))
        if v['File'] not in arts:
            arts[v['File']] = Image.open(DIAG_DIR / v['File']).convert('RGBA')
        taken = {}
        for n in claimed:
            px, py = DISCS[v['Device']][n]
            hit = [d for d in discs if d[0] <= px - ox < d[0] + d[2] and d[1] <= py - oy < d[1] + d[3]]
            if len(hit) != 1:
                problems.append('%s: button %d falls in %d of the discs found' % (v['Id'], n, len(hit)))
                continue
            if hit[0] in taken.values():
                problems.append('%s: button %d shares a disc' % (v['Id'], n))
            taken[n] = hit[0]
            bx, by, bw, bh = hit[0][:4]
            fp = fingerprint(arts[v['File']], (bx + ox, by + oy, bx + ox + bw, by + oy + bh))
            prints.setdefault(v['Device'], {})[n] = fp
            if pin and FINGERPRINTS.get(v['Device'], {}).get(n) != fp:
                problems.append('%s: button %s %d is named on a disc that is not the one verified by eye '
                                '(its fingerprint is %s, FINGERPRINTS has %s). Re-verify the names by eye: '
                                'python tools/regen_cards.py --sheets <folder>, then --fingerprints (see FINGERPRINTS)'
                                % (v['Id'], v['Device'], n, fp, FINGERPRINTS.get(v['Device'], {}).get(n)))
            for o in VIEWS:          # the disc is in no other view's crop
                if o is not v and o['File'] == v['File']:
                    a0, b0, a1, b1 = o['Box']
                    if bx + ox < a1 and a0 < bx + ox + bw and by + oy < b1 and b0 < by + oy + bh:
                        problems.append('button %s %d is drawn in %s and %s' % (v['Device'], n, v['Id'], o['Id']))
        for d in discs:
            if d not in taken.values():
                problems.append('%s: a disc at (%d, %d) that no button in Buttons claims' % (v['Id'], d[0] + ox, d[1] + oy))
        for row in rows:
            if row['view'] != v['Id']:
                continue
            for n in row['buttons']:
                if n in taken:
                    bx, by, bw, bh, _, box = taken[n]
                    row['discs'].append({'n': n, 'x': jnum(bx + bw / 2), 'y': jnum(by + bh / 2), 'w': bw, 'h': bh, 'box': box})
            for word, wbox in ([] if row['buttons'] else (v['Axes'].get(row['label']) or [])):
                x0, y0 = max(0, wbox[0] - ox), max(0, wbox[1] - oy)
                x1, y1 = min(w, wbox[2] - ox), min(h, wbox[3] - oy)
                ink = [(x, y) for y in range(y0, y1) for x in range(x0, x1) if levels[y * w + x] >= DISC_FINDER['Ink']]
                if not ink:
                    problems.append('%s: no word drawn for %s in %r' % (v['Id'], row['label'], wbox))
                    continue
                ix0, iy0 = min(q[0] for q in ink), min(q[1] for q in ink)
                ix1, iy1 = max(q[0] for q in ink) + 1, max(q[1] for q in ink) + 1
                if ix0 == x0 or iy0 == y0 or ix1 == x1 or iy1 == y1:
                    problems.append('%s: the word box of %s %r has ink at its edge' % (v['Id'], row['label'], wbox))
                row['discs'].append({'n': None, 'word': word, 'x': jnum((ix0 + ix1) / 2), 'y': jnum((iy0 + iy1) / 2),
                                     'w': ix1 - ix0, 'h': iy1 - iy0, 'box': True})
        disc_min = min((min(d[2], d[3]) for d in discs), default=0)
        digit_min = min((d[4] for d in discs), default=0)
        views.append({'id': v['Id'], 'device': v['Device'], 'title': v['Title'], 'caption': v['Caption'],
                      'image': name, 'w': w, 'h': h, 'hash': phash,
                      # the source art by its stem: every string in rig.json ending .png is an image beside it
                      'source': {'diagram': Path(v['File']).stem, 'box': [ox, oy, ox + w, oy + h]},
                      'buttons': claimed, 'disc_min': disc_min, 'digit_min': digit_min,
                      'scale_18': jnum(round(18 / disc_min, 2)) if disc_min else None,
                      'notes': notes_of.get(v['Id'], []),
                      'rows': [x['id'] for x in rows if x['view'] == v['Id']]})
    for row in rows:
        home = next(v for v in VIEWS if v['Id'] == row['view'])
        want = len(row['buttons']) if row['buttons'] else len(home['Axes'][row['label']] or [])
        if len(row['discs']) != want:
            problems.append('%s has %d marks on its view, not %d' % (row['id'], len(row['discs']), want))
    if problems:
        sys.exit('regen_cards: the rig reference does not add up:\n  ' + '\n  '.join(problems))

    devices = [{'id': c['Device'], 'name': c['Screen'], 'product': c['Product'], 'title': c['Title'],
                'sub': c['Sub'], 'legend': c['Legend'],
                'views': [v['Id'] for v in VIEWS if v['Device'] == c['Device']]} for c in CARDS]
    maps = {}
    for k, spec in sorted(MAPS.items()):
        maps[k] = {'live': list(spec['Live']), 'unknown': list(spec['Unknown']),
                   'dead': [m for m in mode_ids if m not in spec['Live'] and m not in spec['Unknown']],
                   'why': [{'file': q['File'], 'ref': q['In'], 'text': q['Text']} for q in spec['Why']]}
        if spec.get('Note'):
            maps[k]['note'] = spec['Note']
    files = sorted({v['File'] for v in VIEWS})
    used_cat = sorted([k[0], k[1], e['label'], e['joystick'], e['activation']] for k, e in cat.items() if k[0] in MAPS)
    counts = {'rows': len(rows), 'views': len(views),
              'discs': sum(1 for x in rows for d in x['discs'] if d['n'] is not None), 'status': {}}
    for x in rows:
        for s in [x.get('status')] + [v.get('status') for v in x.get('variants', [])]:
            counts['status'][s or 'none'] = counts['status'].get(s or 'none', 0) + 1
    counts['status'] = dict(sorted(counts['status'].items()))
    meta = {
        'schema': RIG_SCHEMA,
        'generated': None,
        'generated_by': 'tools/regen_cards.py (or --dashboard-only); do not edit by hand',
        'source': 'The card tables and the literals after them in tools/regen_cards.py; the art in diagrams/; '
                  'MOZA.xml (the actions on each input); the action catalog in reference/ (labels, stock '
                  'activation modes and stock joystick bindings).',
        'catalog': 'reference/' + catalog_path().name,
        'doc': 'Every field is described in dashboard/RIG.md.',
        'status': {'flown': 'Confirmed in a ship: root CLAUDE.md says it worked in flight (status_when: when, where it says).',
                   'unverified': ('Bound in MOZA.xml, but not yet confirmed in a ship (CLAUDE.md says so); the quote '
                                  'says whether the game has loaded it yet.'),
                   'trial': 'CLAUDE.md calls the binding a trial: bound to be tried out, not yet tried.',
                   'missing': 'No status key: the docs record neither a flight report nor a doubt about how that '
                              'binding behaves. Doubts about which physical control carries a number, and about '
                              'the game defaults the profile clears, are not statuses.'},
        'hash': {'tables': digest(tables), 'code': digest(rig_code()),
                 'diagrams': {f: hashlib.sha256((DIAG_DIR / f).read_bytes()).hexdigest()[:12] for f in files},
                 'profile': digest(sorted([list(b) for b in binds], key=str)), 'catalog': digest(used_cat)},
        'counts': counts,
    }
    doc = {'_meta': meta, 'modes': modes_out, 'live_modes': {k: list(v) for k, v in LIVE_MODES.items()},
           'maps': maps, 'devices': devices, 'views': views, 'rows': rows}
    return doc, prints


def dump_rig(doc):
    """rig.json text: small, one row per line so a changed row is a one-line diff."""
    d = lambda o: json.dumps(o, ensure_ascii=False)
    out = ['{', ' "_meta": {']
    meta = list(doc['_meta'].items())
    out += ['  %s: %s%s' % (d(k), d(v), ',' if i < len(meta) - 1 else '') for i, (k, v) in enumerate(meta)]
    out.append(' },')
    out.append(' "modes": [')
    out += ['  %s%s' % (d(x), ',' if i < len(doc['modes']) - 1 else '') for i, x in enumerate(doc['modes'])]
    out.append(' ],')
    out.append(' "live_modes": %s,' % d(doc['live_modes']))
    out.append(' "maps": {')
    items = list(doc['maps'].items())
    out += ['  %s: %s%s' % (d(k), d(v), ',' if i < len(items) - 1 else '') for i, (k, v) in enumerate(items)]
    out.append(' },')
    for key in ('devices', 'views', 'rows'):
        out.append(' %s: [' % d(key))
        out += ['  %s%s' % (d(x), ',' if i < len(doc[key]) - 1 else '') for i, x in enumerate(doc[key])]
        out.append(' ]%s' % (',' if key != 'rows' else ''))
    out.append('}')
    return '\n'.join(out) + '\n'


def build_rig(pin=True):
    """Everything dashboard/web/rig/ is to hold, made in memory: ({file name: bytes}, rig.json as a
    dict, the discs' fingerprints). Exits, having written nothing, when a check fails. Deterministic:
    the same tables, art, profile, catalog and code give the same bytes, and the date in rig.json
    moves only when a hash does."""
    images, files = {}, {}
    n = RIG_ART['Levels']
    for v in VIEWS:
        img, alphas, origin = screen_art(v)
        buf = io.BytesIO()
        img.save(buf, format='PNG', optimize=True, transparency=alphas)
        name = v['Id'] + '.png'
        files[name] = buf.getvalue()
        with Image.open(io.BytesIO(files[name])) as back:
            back.load()
            rgba = back.convert('RGBA')
        levels = [round(a * (n - 1) / 255) for a in rgba.getchannel('A').tobytes()]
        discs = find_discs(levels, rgba.width, rgba.height)
        images[v['Id']] = (name, rgba.width, rgba.height, pixel_hash(rgba), origin, discs, levels)
    doc, prints = rig_doc(images, pin)
    date = datetime.date.today().isoformat()
    try:
        prev = json.loads((RIG_DIR / 'rig.json').read_text(encoding='utf-8'))['_meta']
        if prev.get('hash') == doc['_meta']['hash'] and prev.get('schema') == RIG_SCHEMA and prev.get('generated'):
            date = prev['generated']
    except (OSError, ValueError, KeyError, TypeError):
        pass
    doc['_meta']['generated'] = date
    files['rig.json'] = dump_rig(doc).encode('utf-8')
    return files, doc, prints


def png_facts(data):
    """What makes two PNGs the same image here, however they were compressed: the chunk types in order
    (a run of IDAT counted once; so a text or time chunk is a difference), the header (size, bit depth,
    color type, interlace), the palette and transparency entries, and the pixels as RGBA. A different
    zlib build (Pillow on zlib-ng or on classic zlib) gives other bytes but the same facts."""
    import struct
    if data[:8] != b'\x89PNG\r\n\x1a\n':
        return None
    pos, kinds, parts = 8, [], {}
    while pos + 8 <= len(data):
        n, kind = struct.unpack('>I4s', data[pos:pos + 8])
        body = data[pos + 8:pos + 8 + n]
        if not kinds or kinds[-1] != kind or kind != b'IDAT':
            kinds.append(kind)
        if kind in (b'IHDR', b'PLTE', b'tRNS'):
            parts[kind] = body
        pos += 12 + n
    try:
        with Image.open(io.BytesIO(data)) as im:
            im.load()
            pixels = pixel_hash(im)
    except Exception:            # a broken file is never equal to anything
        return None
    return (tuple(k.decode('ascii', 'replace') for k in kinds), parts.get(b'IHDR'), parts.get(b'PLTE'),
            parts.get(b'tRNS'), pixels)


def same_file(path, data):
    """True when path already holds data: byte for byte for rig.json, by png_facts for an image."""
    try:
        old = path.read_bytes()
    except OSError:
        return False
    if path.suffix == '.png':
        return png_facts(old) is not None and png_facts(old) == png_facts(data)
    return old == data


def write_files(folder, files, keep_png=True):
    """Write {name: bytes} into folder, each through a temporary file, and return the names written.
    A file that already holds the same thing (same_file) is left alone, so a run on another Pillow
    build does not rewrite images whose pixels are unchanged. rig.json goes last. With keep_png False,
    a PNG the set does not name is removed afterwards (a renamed or dropped view leaves no orphan)."""
    folder.mkdir(parents=True, exist_ok=True)
    written = []
    for name in sorted(files, key=lambda n: n == 'rig.json'):
        if not same_file(folder / name, files[name]):
            write_atomic(folder / name, files[name])
            written.append(name)
    if not keep_png:
        for old in folder.glob('*.png'):
            if old.name not in files:
                old.unlink()
                written.append(old.name + ' (removed)')
    return written


def write_sheets(folder):
    """--sheets: one contact sheet per view for re-reading the disc names by eye. Each tile is the
    disc and a margin cut from the source art at 8x, the disc's box drawn on it, and the number the
    data gives it written under it."""
    from PIL import ImageDraw
    files, doc, prints = build_rig(pin=False)
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    rows = {r['id']: r for r in doc['rows']}
    s, pad, tile = 8, 6, 8 * 44
    for v in doc['views']:
        art = Image.open(DIAG_DIR / (v['source']['diagram'] + '.png')).convert('RGBA')
        ox, oy = v['source']['box'][:2]
        marks = [d for rid in v['rows'] for d in rows[rid]['discs'] if d['n'] is not None]
        cols = 6
        sheet = Image.new('RGB', (cols * tile, ((len(marks) + cols - 1) // cols) * (tile + 40)), (12, 18, 26))
        dr = ImageDraw.Draw(sheet)
        for i, d in enumerate(marks):
            cx, cy = ox + d['x'], oy + d['y']
            box = (int(cx - 22 + 0.5), int(cy - 22 + 0.5), int(cx - 22 + 0.5) + 44, int(cy - 22 + 0.5) + 44)
            ground = Image.new('RGBA', (44, 44), (22, 32, 48, 255))
            ground.alpha_composite(art.crop(box))
            big = ground.convert('RGB').resize((tile, tile), Image.NEAREST)
            x, y = (i % cols) * tile, (i // cols) * (tile + 40)
            sheet.paste(big, (x, y))
            bx0, by0 = (cx - d['w'] / 2 - box[0]) * s, (cy - d['h'] / 2 - box[1]) * s
            dr.rectangle([x + bx0, y + by0, x + bx0 + d['w'] * s, y + by0 + d['h'] * s], outline=(255, 60, 200))
            dr.text((x + 8, y + tile + 8), '%s %d (data)' % (v['device'], d['n']), fill=(255, 230, 0))
        out = folder / ('sheet_%s.png' % v['id'])
        sheet.save(out)
        print('  %s: %d discs' % (out, len(marks)))
    print('Read every tile: the number drawn in the art must be the one written under it.')


def write_rig():
    """dashboard/web/rig/: the eight screen views and rig.json, made and checked in memory first, then
    written; leftover temporary files of an interrupted run are swept first."""
    sweep_parts(RIG_DIR) if RIG_DIR.is_dir() else None
    files, doc, _ = build_rig()
    print_word_warnings()
    written = write_files(RIG_DIR, files, keep_png=False)
    c = doc['_meta']['counts']
    for name, data in files.items():
        print('  %-26s %d bytes%s' % (name, len(data), '' if name in written else ', unchanged'))
    print('  %d rows in %d views, %d discs' % (c['rows'], c['views'], c['discs']))


def main():
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0],
                                 epilog='Set CARD_BROWSER=<path> to choose the browser used for the PNG render.')
    ap.add_argument('--dashboard-only', action='store_true',
                    help='write only dashboard/web/rig/ (no cards, no browser needed)')
    ap.add_argument('--fingerprints', action='store_true',
                    help='print the FINGERPRINTS table of the discs as named now (after reading the --sheets by eye)')
    ap.add_argument('--sheets', metavar='FOLDER',
                    help='write contact sheets of every disc and its name into FOLDER, for reading by eye')
    args = ap.parse_args()
    if args.fingerprints:
        _, _, prints = build_rig(pin=False)
        print('FINGERPRINTS = {')
        for dev in sorted(prints):
            items = ['%d: %r' % (k, prints[dev][k]) for k in sorted(prints[dev])]
            lines = [', '.join(items[i:i + 6]) for i in range(0, len(items), 6)]
            print("    %r: {%s}," % (dev, (',\n' + ' ' * 12).join(lines)))
        print('}')
        return
    if args.sheets:
        write_sheets(args.sheets)
        return
    if args.dashboard_only:
        print('Writing the dashboard rig reference...')
        write_rig()
        print('Done -> %s' % RIG_DIR.relative_to(REPO).as_posix())
        return
    browser = find_browser()
    if not browser:
        sys.exit('regen_cards: no Chrome / Edge / Chromium found to render SVG -> PNG '
                 '(install one, or set CARD_BROWSER=<path to the browser executable>; '
                 '--dashboard-only writes the dashboard files without one).')

    print('Making the dashboard rig reference...')
    sweep_parts(RIG_DIR) if RIG_DIR.is_dir() else None
    sweep_parts(CARD_DIR)
    rig_files, rig, _ = build_rig()
    print_word_warnings()

    print('Cropping + recoloring diagram sub-views...')
    sub = {v['Id']: get_sub_diagram(v['File'], v['Box']) for v in CARD_ART}
    cap = {v['Id']: v['Caption'] for v in CARD_ART}
    text = {c['Name']: c for c in CARDS}

    def img(view_id, frac, va=None):
        im = {'D': sub[view_id], 'Frac': frac}
        if va:
            im['VA'] = va
        if cap[view_id]:
            im['Caption'] = cap[view_id]
        return im

    # Layout: LEFT ~60% of the sheet = images (two stacked bands - the two small views side by
    # side on top, the one big view below); RIGHT ~40% = the lookup table in two columns.
    # CanvasW:CanvasH = 11:8.5 (1.294) fills a Letter sheet in landscape. F is dialed down so
    # the narrow 40% table still fits. Geometry: image zone x=24..1064 (W=1040); table at x=1090.
    print('Rendering print cards (2x via %s)...' % os.path.basename(browser))

    # --- Card 1: MHG grip + AB6 base (js1), combined ---
    # Top band: the two grip views side by side (larger). Bottom band: the AB6 base
    # (smaller - far fewer buttons). Base Frac kept below the grips' so it reads smaller.
    card_files = {}
    t = text['MOZA_MHG_AB6_ref']
    card_files.update(new_card({
        'Name': t['Name'], 'F': 1.18, 'CanvasW': 1860, 'CanvasH': 1437,
        'Title': t['Title'], 'Sub': t['Sub'],
        'Stack': {'X': 24, 'W': 1040, 'Gap': 22, 'Rows': [
            {'HFrac': 1.12, 'Imgs': [img('mhg_front', 0.56, 't'), img('mhg_side', 0.44, 'b')]},
            {'HFrac': 1.00, 'Imgs': [img('ab6_base', 0.53, 'b')]},
        ]},
        'Cols': [{'X': 1090, 'W': 370, 'Rows': MHG_L}, {'X': 1475, 'W': 365, 'Rows': MHG_R + AB6}],
        'Legend': t['Legend'],
    }, browser))

    # --- Card 2: MTQ throttle (js2) ---
    # Top band: the two module views side by side. Bottom band: the throttle panel
    # (the big, button-dense view) below them.
    t = text['MOZA_MTQ_ref']
    card_files.update(new_card({
        'Name': t['Name'], 'F': 1.15, 'CanvasW': 1860, 'CanvasH': 1437,
        'Title': t['Title'], 'Sub': t['Sub'],
        'Stack': {'X': 24, 'W': 1040, 'Gap': 22, 'Rows': [
            {'HFrac': 0.95, 'Imgs': [img('mtq_right', 0.52, 't'), img('mtq_left', 0.52, 'b')]},
            {'HFrac': 1.30, 'Imgs': [img('mtq_panel', 0.74)]},
        ]},
        'Cols': [{'X': 1090, 'W': 370, 'Rows': MTQ_L}, {'X': 1475, 'W': 365, 'Rows': MTQ_R}],
        'Legend': t['Legend'],
    }, browser))

    # Everything was made and checked; only now is anything written.
    write_files(RIG_DIR, rig_files, keep_png=False)
    write_files(CARD_DIR, card_files)
    c = rig['_meta']['counts']
    print('Done -> %s (%d rows in %d views) and MOZA_MHG_AB6_ref, MOZA_MTQ_ref (.png + .svg) in %s'
          % (RIG_DIR.relative_to(REPO).as_posix(), c['rows'], c['views'], CARD_DIR.relative_to(REPO).as_posix()))


if __name__ == '__main__':
    main()
