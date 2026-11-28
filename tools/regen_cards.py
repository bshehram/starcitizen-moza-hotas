"""regen_cards.py - the MOZA button-reference cards (split-diagram, print layout).

Produces the TWO reference cards, sized to fill a US-Letter sheet in LANDSCAPE
(11 x 8.5 in, aspect 1.294) for printing in hand:

    cards/MOZA_MHG_AB6_ref.png / .svg   (js1: MHG grip 1-29 + AB6 base 49-62 + stick axes)
    cards/MOZA_MTQ_ref.png     / .svg   (js2: MTQ throttle 1-65 + axes)

and, in the same run, the dashboard's rig reference, from the same tables and crops:

    dashboard/web/rig/rig.json          every card row, grouped by device and diagram view
    dashboard/web/rig/<view>.png        the six sub-views, light line work on transparency

The dashboard files need no browser: `--dashboard-only` writes just those.
dashboard/tests/test_rig.py fails when a card row changes and they were not rewritten.

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
  deliberately terser than MOZA.xml to fit the 40% columns.

CROP RECTANGLES (x0, y0, x1, y1 in source-PNG pixels) live in VIEWS below, one entry per
sub-view, with the button numbers each view draws - re-verify if MOZA ships new device
art (sources: AB6 890x691, MHG 1037x822, MTQ 1049x820):
  MTQ main   60, 90,612,818     MTQ right 615, 72,1045,486   MTQ left 620,488,1045,818
  MHG front 515, 90,985,575     MHG side  100,168, 460,770   AB6 base 250,110, 785,650

REQUIREMENTS: Python 3.8+, Pillow (`python -m pip install Pillow`), and Chrome, Edge or
Chromium for the SVG -> PNG render (found automatically on Windows, macOS and Linux;
set CARD_BROWSER=<path> to pick one). `--dashboard-only` needs Pillow alone.
RUN (from the project root):
    python tools/regen_cards.py                    # cards + dashboard rig files
    python tools/regen_cards.py --dashboard-only   # dashboard rig files only, no browser
"""

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
from pathlib import Path

try:
    from PIL import Image, ImageChops
except ImportError:
    sys.exit('regen_cards: Pillow is required.  Run:  python -m pip install Pillow')

REPO = Path(__file__).resolve().parent.parent
DIAG_DIR = REPO / 'diagrams'
CARD_DIR = REPO / 'cards'
RIG_DIR = REPO / 'dashboard' / 'web' / 'rig'
HAND_MARKS = REPO / 'dashboard' / 'reference' / 'controls.hand.json'

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


def render_png(browser, svg_path, png_path, cw, ch):
    """Rasterize the SVG at 2x with a headless Chromium. An isolated profile directory keeps it
    from colliding with a Chrome the user already has open."""
    work = Path(tempfile.mkdtemp(prefix='cardrender_'))
    tmp_png = work / 'card.png'
    try:
        subprocess.run([browser, '--headless=new', '--disable-gpu', '--no-sandbox', '--hide-scrollbars',
                        '--user-data-dir=%s' % (work / 'profile'), '--screenshot=%s' % tmp_png,
                        '--window-size=%d,%d' % (cw, ch), '--force-device-scale-factor=2',
                        svg_path.resolve().as_uri()],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=180)
        if not tmp_png.exists():
            sys.exit('regen_cards: render failed for %s.' % svg_path.name)
        shutil.move(str(tmp_png), str(png_path))
    finally:
        shutil.rmtree(work, ignore_errors=True)
    with Image.open(png_path) as o:
        print('  %-26s %dx%d' % (png_path.name, o.width, o.height))


# Build one card SVG + render to PNG (2x). cfg['F'] = font scale; cfg['Stack'] = images.
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
    svg_path = CARD_DIR / (cfg['Name'] + '.svg')
    svg_path.write_text(''.join(sb), encoding='utf-8', newline='')   # UTF-8, no BOM
    render_png(browser, svg_path, CARD_DIR / (cfg['Name'] + '.png'), CW, CH)


# ================================================================ AB6 (js1 49-62)
# NOTE: variant/primary labels here are deliberately terse (vs MOZA.xml / CLAUDE.md)
# so they fit the narrow 40%-width legend columns - same bindings, shorter wording.
AB6 = [
    {'Header': 'AB6 BASE 49-62'},
    {'Label': '49', 'Primary': 'Weapons power toggle', 'Hint': 'L wing 1'},
    {'Label': '50', 'Primary': 'Thruster power toggle', 'Hint': 'L wing 2'},
    {'Label': '51', 'Primary': 'Shield power toggle', 'Hint': 'L wing 3'},
    {'Label': '52', 'Primary': 'Power assignment reset', 'Hint': 'L wing 4'},
    {'Label': '53', 'Primary': 'Power to weapons +', 'Hint': 'R wing 1'},
    {'Label': '54', 'Primary': 'Power to engines +', 'Hint': 'R wing 2'},
    {'Label': '55', 'Primary': 'Power to shields +', 'Hint': 'R wing 3'},
    {'Label': '56', 'Primary': 'Shields to MAX (hold)', 'Hint': 'R wing 4'},
    {'Label': '57-59', 'Primary': 'Left "Slider" lever', 'Hint': 'unbound - reserved', 'Unbound': True},
    {'Label': '60-62', 'Primary': 'Right "Dial" lever', 'Hint': 'unbound - reserved', 'Unbound': True},
]

# ================================================================ MHG (js1 1-29) + the stick axes
# The stick axes sit under GRIP 1-15 because that column has the room; in rig.json they go to the
# stick_axes view (no diagram view draws them).
MHG_L = [
    {'Header': 'GRIP 1-15'},
    {'Label': '1', 'Primary': 'Fire Guns - Group 1 + selected preset', 'Variants': [V('Mine:', 'fire laser', C_MINE), V('Salv:', 'focused beam', C_SALV)]},
    {'Label': '2', 'Primary': 'Launch missiles'},
    {'Label': '3', 'Primary': 'Look behind (hold)'},
    {'Label': '4', 'Primary': 'Missile-mode toggle'},
    {'Label': '5', 'Primary': 'Lock target under reticle'},
    {'Label': '6', 'Primary': 'Fire Guns - Group 2', 'Variants': [V('Salv:', 'salvage gimbal', C_SALV)]},
    {'Label': '7', 'Primary': 'Countermeasure: decoy (flares)'},
    {'Label': '8', 'Primary': 'Cycle hostiles forward', 'Variants': [V('Salv:', 'fracture beam', C_SALV)]},
    {'Label': '9', 'Primary': 'Countermeasure: noise (chaff)'},
    {'Label': '10', 'Primary': 'Cycle hostiles back', 'Variants': [V('Salv:', 'disintegrate', C_SALV)]},
    {'Label': '11', 'Primary': 'Lock selected target', 'Variants': [V('Salv:', 'cycle modifiers', C_SALV)]},
    {'Label': '12', 'Primary': 'Cycle sub-target forward', 'Variants': [V('Mine:', 'module 1', C_MINE), V('Salv:', 'focus all', C_SALV)]},
    {'Label': '13', 'Primary': 'Cycle attackers forward', 'Variants': [V('Mine:', 'module 2', C_MINE), V('Salv:', 'focus right', C_SALV)]},
    {'Label': '14', 'Primary': 'Cycle sub-target back', 'Variants': [V('Mine:', 'module 3', C_MINE), V('Salv:', 'beam axis H/V', C_SALV)]},
    {'Label': '15', 'Primary': 'Cycle attackers back', 'Variants': [V('Salv:', 'focus left', C_SALV)]},
    {'Header': 'STICK AXES'},
    {'Label': 'X', 'Primary': 'Roll', 'Hint': 'stick left / right'},
    {'Label': 'Y', 'Primary': 'Pitch (pull = nose up)', 'Hint': 'stick fwd / back'},
    {'Label': 'RZ', 'Primary': 'Yaw', 'Hint': 'grip twist'},
]
MHG_R = [
    {'Header': 'GRIP 16-29'},
    {'Label': '16', 'Primary': 'Gimbal lock toggle', 'Variants': [V('Salv:', 'reset gimbal', C_SALV)]},
    {'Label': '17', 'Primary': 'Scan angle +', 'Variants': [V('Salv:', 'tractor dist + (trial)', C_SALV)]},
    {'Label': '18', 'Primary': 'Activate scanning (hold)'},
    {'Label': '19', 'Primary': 'Scan angle -', 'Variants': [V('Salv:', 'tractor dist - (trial)', C_SALV)]},
    {'Label': '20', 'Primary': 'Radar ping'},
    {'Label': '21', 'Primary': 'ADS / cockpit zoom toggle'},
    {'Label': '22', 'Primary': 'Weapon preset - next', 'Variants': [V('Msl:', 'type +', C_NOTE), V('Mine:', 'pwr +', C_MINE), V('Salv:', 'gap +', C_SALV)]},
    {'Label': '23', 'Primary': 'Weapon preset - prev', 'Variants': [V('Msl:', 'type -', C_NOTE), V('Mine:', 'pwr -', C_MINE), V('Salv:', 'gap -', C_SALV)]},
    {'Label': '24', 'Primary': 'Weapon aim-type cycle', 'Variants': [V('Mine:', 'fracture/extract', C_MINE), V('Salv:', 'structural mode', C_SALV)]},
    {'Label': '25', 'Primary': 'Strafe up'},
    {'Label': '26', 'Primary': 'Strafe right'},
    {'Label': '27', 'Primary': 'Strafe down'},
    {'Label': '28', 'Primary': 'Strafe left'},
    {'Label': '29', 'Primary': 'Full reverse (hold)'},
]

# ================================================================ MTQ (js2 1-65 + axes)
MTQ_L = [
    {'Header': 'PANEL BUTTONS 1-30'},
    {'Label': '1', 'Primary': 'Jettison cargo (hold)', 'Hint': 'keypad A1, Mining'},
    {'Label': '2', 'Primary': 'Fire left salvage beam', 'Hint': 'A2, Salvage'},
    {'Label': '3', 'Primary': 'Fire right salvage beam', 'Hint': 'A3, Salvage'},
    {'Label': '4', 'Primary': 'LAMP night-vision toggle', 'Hint': 'A4'},
    {'Label': '5', 'Primary': 'Master mode SCM / NAV', 'Hint': 'NAV key'},
    {'Label': '6', 'Primary': 'Starmap', 'Hint': 'HDG key'},
    {'Label': '7', 'Primary': 'Engage quantum drive (hold)', 'Hint': 'SPD key'},
    {'Label': '8', 'Primary': 'Landing req / hold: cargo', 'Hint': 'ALT key'},
    {'Label': '9', 'Primary': 'Jump - inter-system', 'Hint': 'FD key'},
    {'Label': '10', 'Primary': 'Dock (tap) / autoland (hold)', 'Hint': 'AP key'},
    {'Label': '11', 'Primary': 'Speed limiter -', 'Hint': 'upper enc CCW'},
    {'Label': '12', 'Primary': 'Speed limiter +', 'Hint': 'upper enc CW'},
    {'Label': '13', 'Primary': 'Speed limiter on / off', 'Hint': 'upper enc press'},
    {'Label': '14', 'Primary': 'Accel / G limiter -', 'Hint': 'lower enc CCW'},
    {'Label': '15', 'Primary': 'Accel / G limiter +', 'Hint': 'lower enc CW'},
    {'Label': '16', 'Primary': 'G-force safety toggle', 'Hint': 'lower enc press'},
    {'Label': '17', 'Primary': 'Guns mode', 'Hint': 'knob detent 1'},
    {'Label': '18', 'Primary': 'Missile mode', 'Hint': 'knob detent 2'},
    {'Label': '19', 'Primary': 'Scan mode', 'Hint': 'knob detent 3'},
    {'Label': '20', 'Primary': 'Mining mode', 'Hint': 'knob detent 4'},
    {'Label': '21', 'Primary': 'Salvage mode', 'Hint': 'knob detent 5'},
    {'Label': '22', 'Primary': 'Rocker center', 'Hint': 'rest', 'Unbound': True},
    {'Label': '23', 'Primary': 'Master power OFF', 'Hint': 'rocker left'},
    {'Label': '24', 'Primary': 'Flight ready / power ON', 'Hint': 'rocker right'},
    {'Label': '25', 'Primary': 'Unlock + open all doors', 'Hint': 'toggle A up'},
    {'Label': '26', 'Primary': 'Lock + close all doors', 'Hint': 'toggle A down'},
    {'Label': '27', 'Primary': 'Lights on', 'Hint': 'toggle B up'},
    {'Label': '28', 'Primary': 'Lights off', 'Hint': 'toggle B down'},
    {'Label': '29', 'Primary': 'Landing gear retract', 'Hint': 'gear lever up'},
    {'Label': '30', 'Primary': 'Landing gear deploy', 'Hint': 'gear lever down'},
]
MTQ_R = [
    {'Header': 'BUTTONS 31-65'},
    {'Label': '31-43', 'Primary': 'Lever detent buttons', 'Hint': 'unbound', 'Unbound': True},
    {'Label': '49', 'Primary': 'VTOL off', 'Hint': '3-pos switch rest'},
    {'Label': '50', 'Primary': 'VTOL on', 'Hint': '3-pos switch fwd-latch'},
    {'Label': '51', 'Primary': 'Space brake', 'Hint': '3-pos switch back'},
    {'Label': '56', 'Primary': 'Shield face: front (trial)', 'Hint': 'WPN hat up'},
    {'Label': '55', 'Primary': 'Shield face: rear (trial)', 'Hint': 'WPN hat down'},
    {'Label': '54', 'Primary': 'Shield face: left (trial)', 'Hint': 'WPN hat left'},
    {'Label': '53', 'Primary': 'Shield face: right (trial)', 'Hint': 'WPN hat right'},
    {'Label': '52', 'Primary': 'Shield faces reset (trial)', 'Hint': 'WPN hat press'},
    {'Label': '61', 'Primary': 'Cycle all contacts fwd', 'Hint': 'COM hat up'},
    {'Label': '60', 'Primary': 'Cycle all contacts back', 'Hint': 'COM hat down'},
    {'Label': '59', 'Primary': 'Cycle pinned forward', 'Hint': 'COM hat left'},
    {'Label': '58', 'Primary': 'Lock closest hostile', 'Hint': 'COM hat right'},
    {'Label': '57', 'Primary': 'Decoupled / hold: pin', 'Hint': 'COM hat press'},
    {'Label': '62', 'Primary': 'Cycle camera view', 'Hint': 'mini-stick press'},
    {'Label': '63', 'Primary': 'Zoom in - cockpit', 'Hint': 'throttle dial fwd'},
    {'Label': '64', 'Primary': 'Zoom out - cockpit', 'Hint': 'throttle dial back'},
    {'Label': '65', 'Primary': 'Boost / afterburner', 'Hint': 'L-Module button'},
    {'Header': 'AXES'},
    {'Label': 'RY', 'Primary': 'Main throttle - forward', 'Hint': 'detent to detent'},
    {'Label': 'Z / RZ', 'Primary': 'Reverse pair - off', 'Hint': 'not output', 'Unbound': True},
    {'Label': 'Slider', 'Primary': 'Mining laser power', 'Hint': 'FLAPS, Mining'},
    {'Label': 'Dial', 'Primary': 'Salvage beam spacing', 'Hint': 'S-brake, Salvage'},
    {'Label': 'X / Y', 'Primary': 'Camera look (yaw / pitch)', 'Hint': 'mini-stick'},
    {'Label': 'RX', 'Primary': 'Throttle twin of RY', 'Hint': 'unbound', 'Unbound': True},
]

# ================================================================ shared by the cards and the dashboard
# Everything below is plain literals so dashboard/tests/test_rig.py can read it with `ast`
# (without running this file) and tell when dashboard/web/rig/ is stale.

# The two cards: which tables they print, in card order, and their heading and legend text.
CARDS = [
    {'Name': 'MOZA_MHG_AB6_ref', 'Device': 'js1', 'Short': 'Stick: MHG grip + AB6 base',
     'Tables': ['MHG_L', 'MHG_R', 'AB6'],
     'Title': 'MOZA MHG Grip + AB6 Base  -  Button Reference  (js1)',
     'Sub': 'MHG grip 1-29 mounted on the AB6 base 49-62, plus the stick axes  ·  trigger / hats / rocker reused per operator mode',
     'Legend': ('Combat (default)  ·  Msl: Missile  ·  Mine: Mining  ·  Salv: Salvage.  One control = a '
                'different job per operator mode (set on the MTQ knob); the right hat 12-16 carries the mining '
                'modules and salvage bank. AB6 wings 49-56 = power panel in every mode.')},
    {'Name': 'MOZA_MTQ_ref', 'Device': 'js2', 'Short': 'Throttle: MTQ',
     'Tables': ['MTQ_L', 'MTQ_R'],
     'Title': 'MOZA MTQ Throttle Panel  -  Button Reference  (js2)',
     'Sub': 'throttle 1-65 + axes  ·  buttons 44-48 are absent on the device',
     'Legend': ('Throttle forward = axis RY, idle detent = 0, forward detent = full; reverse = MHG stick press 29, held. '
                'Nothing is output outside the two detents.  FLAPS & Speedbrake levers drive analog axes (Slider / Dial) in Mining / Salvage '
                'modes; detent buttons 31-43 are unbound.  WPN-hat shield faces act only on S3 Quadrant shields (trial).')},
]

# The operator modes behind the variant tags (the legend's "Msl: Missile  ·  Mine: Mining ...").
MODES = [
    {'Mode': 'combat', 'Tag': None, 'Name': 'Combat (default)'},
    {'Mode': 'missile', 'Tag': 'Msl:', 'Name': 'Missile'},
    {'Mode': 'mining', 'Tag': 'Mine:', 'Name': 'Mining'},
    {'Mode': 'salvage', 'Tag': 'Salv:', 'Name': 'Salvage'},
]

# The diagram sub-views. Box = crop out of File (the cards and the dashboard use the same crops).
# Buttons = the numbers drawn in that view, read off the manufacturer art (CLAUDE.md section 3): a
# card row goes to the view that draws all of its numbers. The grip's side view draws the trigger,
# pinky, thumb button and rocker (1, 3, 4, 6, 22-24); everything else on the grip is on the front.
# A row whose label is not a number (RY, Slider, X / Y ...) goes to its device's view with 'Axes',
# which has no image; 'Axes' names the view each axis is drawn on, where it is drawn at all.
VIEWS = [
    {'Id': 'mhg_front', 'Device': 'js1', 'Title': 'MHG grip - front', 'Caption': 'MHG grip - front (hats & buttons)',
     'File': 'MOZA_MHG.png', 'Box': (515, 90, 985, 575), 'Buttons': '2, 5, 7-21, 25-29'},
    {'Id': 'mhg_side', 'Device': 'js1', 'Title': 'MHG grip - side', 'Caption': 'MHG grip - side',
     'File': 'MOZA_MHG.png', 'Box': (100, 168, 460, 770), 'Buttons': '1, 3-4, 6, 22-24'},
    {'Id': 'ab6_base', 'Device': 'js1', 'Title': 'AB6 base', 'Caption': 'AB6 base - wings & levers',
     'File': 'MOZA_AB6.png', 'Box': (250, 110, 785, 650), 'Buttons': '49-62'},
    # The stick's own axes. None is drawn in a cropped view: MOZA's art shows the twist (RZ) only
    # below the grip, outside the mhg_front crop, and the AB6 art shows no X / Y.
    {'Id': 'stick_axes', 'Device': 'js1', 'Title': 'Stick axes', 'Caption': None, 'File': None, 'Box': None,
     'Axes': {}},
    {'Id': 'mtq_panel', 'Device': 'js2', 'Title': 'MTQ throttle panel', 'Caption': 'Throttle panel',
     'File': 'MOZA_MTQ.png', 'Box': (60, 90, 612, 818), 'Buttons': '1-43'},
    {'Id': 'mtq_right', 'Device': 'js2', 'Title': 'MTQ right module', 'Caption': None,
     'File': 'MOZA_MTQ.png', 'Box': (615, 72, 1045, 486), 'Buttons': '49-61'},
    {'Id': 'mtq_left', 'Device': 'js2', 'Title': 'MTQ left module', 'Caption': None,
     'File': 'MOZA_MTQ.png', 'Box': (620, 488, 1045, 818), 'Buttons': '62-65'},
    {'Id': 'mtq_axes', 'Device': 'js2', 'Title': 'MTQ axes', 'Caption': None, 'File': None, 'Box': None,
     'Axes': {'RY': 'mtq_panel', 'Slider': 'mtq_panel', 'Dial': 'mtq_panel', 'RX': 'mtq_panel', 'X / Y': 'mtq_left'}},
]

# How the dashboard copies of the sub-views are drawn (the page is dark; the cards are dark on white).
# Brightness is the source's brightest channel, mapped to opacity: below Ground is the navy backdrop
# (fully transparent), Full and above (the number discs) fully opaque, the faint line work in between,
# so the numbers stand out from the outline. Levels = opacity steps; 16 fits a 4-bit PNG and looks the
# same as 256 next to it. Bump Version after changing get_screen_art itself, so the test sees it.
RIG_ART = {'Version': 1, 'Color': '#E4ECF2', 'Ground': 0.25, 'Full': 0.82, 'Gamma': 0.8, 'Levels': 16, 'Pad': 2}


# ================================================================ dashboard rig reference
def screen_art(file, box):
    """Crop box out of a source diagram for the dark dashboard page: one light color whose opacity
    follows the art's brightness, trimmed to the drawn part. Native pixels, never scaled."""
    a = RIG_ART
    src = Image.open(DIAG_DIR / file).convert('RGBA').crop(box)
    r, g, b, alpha = src.split()
    # The brightest channel, not luma: MOZA's green "pressed" discs (a state at capture time, not a
    # binding) then come out as bright as the gray ones, where luma would dim them to about 3/4.
    val = ImageChops.multiply(ImageChops.lighter(ImageChops.lighter(r, g), b), alpha)
    n, lo, hi = a['Levels'], a['Ground'] * 255, a['Full'] * 255
    lut = [round(max(0.0, min(1.0, (v - lo) / (hi - lo))) ** a['Gamma'] * (n - 1)) for v in range(256)]
    idx = val.point(lut)
    x0, y0, x1, y1 = idx.getbbox()
    p = a['Pad']
    idx = idx.crop((max(0, x0 - p), max(0, y0 - p), min(idx.width, x1 + p), min(idx.height, y1 + p)))
    out = Image.frombytes('P', idx.size, idx.tobytes())
    rgb = [int(a['Color'][i:i + 2], 16) for i in (1, 3, 5)]
    out.putpalette(rgb * n)                       # n entries -> Pillow writes a 4-bit PNG for n <= 16
    return out, bytes(round(i * 255 / (n - 1)) for i in range(n))


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


def digest(obj):
    """Short hash of a JSON-able value; test_rig.py computes the same from its `ast` read."""
    raw = json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    return hashlib.sha256(raw).hexdigest()[:12]


def card_sources():
    """Everything rig.json is made from that lives in this file."""
    return {'AB6': AB6, 'MHG_L': MHG_L, 'MHG_R': MHG_R, 'MTQ_L': MTQ_L, 'MTQ_R': MTQ_R,
            'CARDS': CARDS, 'MODES': MODES, 'VIEWS': VIEWS, 'RIG_ART': RIG_ART}


STATUS_RANK = {'flown': 0, 'unverified': 1, 'trial': 2}


def hand_marks(rows_by_dev):
    """The flown / unverified / trial marks of dashboard/reference/controls.hand.json, keyed by
    (device, label, mode). mode None = the row's primary function. The file marks a control within an
    operator mode's strip; the mark belongs to that mode's variant when the row has one, otherwise to
    the primary (the same rule as reference/build_reference.py). Two marks on one function: the more
    doubtful wins."""
    if not HAND_MARKS.is_file():
        return {}
    hand = json.loads(HAND_MARKS.read_text(encoding='utf-8'))
    tag_of = {m['Mode']: m['Tag'] for m in MODES}
    marks = {}
    for mode_name, m in sorted((hand.get('modes') or {}).items()):
        for it in m.get('items') or []:
            status = it.get('status')
            if not status:
                continue
            variant = it.get('variant', m.get('variant'))
            for ref in it.get('controls') or []:
                dev, _, label = ref.partition(' ')
                row = rows_by_dev.get(dev, {}).get(label)
                if row is None:
                    print('  note: controls.hand.json names %r (mode %s), which is not on the cards' % (ref, mode_name))
                    continue
                tag = tag_of.get(variant)
                on_variant = tag is not None and any(v['Tag'] == tag for v in row.get('Variants') or [])
                key = (dev, label, variant if on_variant else None)
                if key not in marks or STATUS_RANK.get(status, 9) > STATUS_RANK.get(marks[key], 9):
                    marks[key] = status
    return marks


def rig_doc(images):
    """rig.json as a dict. images = {view id: (file name, w, h)}."""
    mode_of = {m['Tag']: m['Mode'] for m in MODES if m['Tag']}
    tables = card_sources()
    rows_by_dev = {}
    for card in CARDS:
        rows_by_dev[card['Device']] = {r['Label']: r for t in card['Tables'] for r in tables[t] if 'Label' in r}
    marks = hand_marks(rows_by_dev)

    views, placed, problems = [], {}, []
    for v in VIEWS:
        e = {'id': v['Id'], 'device': v['Device'], 'title': v['Title']}
        if v['Id'] in images:
            e['image'], e['w'], e['h'] = images[v['Id']]
        if v.get('Buttons'):
            e['buttons'] = v['Buttons']
        e['rows'] = []
        views.append(e)
    by_id = {e['id']: e for e in views}
    for card in CARDS:
        dev = card['Device']
        for t in card['Tables']:
            for r in tables[t]:
                if 'Label' not in r:
                    continue                                    # a column header on the card
                label = r['Label']
                nums = label_numbers(label)
                home = [v for v in VIEWS if v['Device'] == dev and (
                    (nums is not None and v.get('Buttons') and nums <= parse_buttons(v['Buttons']))
                    or (nums is None and 'Axes' in v))]
                if len(home) != 1:
                    problems.append('%s %s (%d views fit)' % (dev, label, len(home)))
                    continue
                row = {'label': label, 'primary': r['Primary']}
                if r.get('Hint'):
                    row['hint'] = r['Hint']
                if r.get('Unbound'):
                    row['unbound'] = True
                if marks.get((dev, label, None)):
                    row['status'] = marks[(dev, label, None)]
                if r.get('Variants'):
                    row['variants'] = []
                    for var in r['Variants']:
                        mode = mode_of.get(var['Tag'])
                        if mode is None:
                            problems.append('%s %s: variant tag %r is not in MODES' % (dev, label, var['Tag']))
                            continue
                        ve = {'mode': mode, 'text': var['Text']}
                        if marks.get((dev, label, mode)):
                            ve['status'] = marks[(dev, label, mode)]
                        row['variants'].append(ve)
                drawn = (home[0].get('Axes') or {}).get(label)
                if drawn:
                    row['drawn_on'] = drawn
                by_id[home[0]['Id']]['rows'].append(row)
                placed[(dev, label)] = home[0]['Id']
    if problems:
        sys.exit('regen_cards: card rows that fit no single diagram view:\n  ' + '\n  '.join(problems))

    files = sorted({v['File'] for v in VIEWS if v['File']})
    meta = {
        'generated': None,
        'generated_by': 'tools/regen_cards.py (or --dashboard-only); do not edit by hand',
        'source': 'The card tables, CARDS, MODES, VIEWS and RIG_ART in tools/regen_cards.py; the art in diagrams/; '
                  'status marks from dashboard/reference/controls.hand.json.',
        'hash': {'tables': digest(tables),
                 'diagrams': {f: hashlib.sha256((DIAG_DIR / f).read_bytes()).hexdigest()[:12] for f in files},
                 'marks': digest(sorted([d, l, m or '', s] for (d, l, m), s in marks.items()))},
        'lookup': 'views: in card order, js1 then js2. A view holds the card rows whose button numbers its image '
                  'draws (`buttons`); `image` is a file beside this one, `w` x `h` its native pixels (at 1:1 the '
                  'number discs are 14-19 px across with 7-10 px digits, so about 2x brings them to 18 px). The axes '
                  'views (stick_axes, mtq_axes) have no image: `drawn_on` names the view an axis is drawn on, '
                  'where one draws it. Row: `label` as printed on the diagram, `primary` (the combat / default function), `hint` '
                  '(where the control is), `variants` [{mode, text}] for other operator modes, `unbound`, and '
                  '`status` (flown / unverified / trial, from controls.hand.json) on the primary or on the variant '
                  'it is about. A missing key means none.',
        'counts': {'rows': len(placed), 'views': len(views)},
    }
    devices = [{'id': c['Device'], 'name': c['Short'], 'title': c['Title'], 'sub': c['Sub'], 'legend': c['Legend']}
               for c in CARDS]
    modes = [{'mode': m['Mode'], 'tag': m['Tag'], 'name': m['Name']} for m in MODES]
    return {'_meta': meta, 'modes': modes, 'devices': devices, 'views': views}


def dump_rig(doc):
    """rig.json text: small, one card row per line so a changed row is a one-line diff."""
    d = lambda o: json.dumps(o, ensure_ascii=False)
    out = ['{', ' "_meta": {']
    meta = list(doc['_meta'].items())
    out += ['  %s: %s%s' % (d(k), d(v), ',' if i < len(meta) - 1 else '') for i, (k, v) in enumerate(meta)]
    out.append(' },')
    for key in ('modes', 'devices'):
        out.append(' %s: [' % d(key))
        out += ['  %s%s' % (d(x), ',' if i < len(doc[key]) - 1 else '') for i, x in enumerate(doc[key])]
        out.append(' ],')
    out.append(' "views": [')
    for i, v in enumerate(doc['views']):
        head = {k: x for k, x in v.items() if k != 'rows'}
        out.append('  %s, "rows": [' % d(head)[:-1])
        out += ['   %s%s' % (d(r), ',' if j < len(v['rows']) - 1 else '') for j, r in enumerate(v['rows'])]
        out.append('  ]}%s' % (',' if i < len(doc['views']) - 1 else ''))
    out.append(' ]')
    out.append('}')
    return '\n'.join(out) + '\n'


def write_rig():
    """dashboard/web/rig/: the six sub-views in the page's colors and rig.json. Deterministic: the same
    tables and art give the same bytes, and the date only moves when a hash does."""
    RIG_DIR.mkdir(parents=True, exist_ok=True)
    images = {}
    for v in VIEWS:
        if not v['File']:
            continue
        img, alphas = screen_art(v['File'], v['Box'])
        name = v['Id'] + '.png'
        img.save(RIG_DIR / name, format='PNG', optimize=True, transparency=alphas)
        images[v['Id']] = (name, img.width, img.height)
        print('  %-26s %dx%d  %d bytes' % (name, img.width, img.height, (RIG_DIR / name).stat().st_size))
    for old in RIG_DIR.glob('*.png'):                    # a renamed or dropped view leaves no orphan
        if old.name not in {n for n, _, _ in images.values()}:
            old.unlink()
    doc = rig_doc(images)
    path = RIG_DIR / 'rig.json'
    date = datetime.date.today().isoformat()
    try:
        prev = json.loads(path.read_text(encoding='utf-8'))['_meta']
        if prev.get('hash') == doc['_meta']['hash'] and prev.get('generated'):
            date = prev['generated']
    except (OSError, ValueError, KeyError, TypeError):
        pass
    doc['_meta']['generated'] = date
    path.write_text(dump_rig(doc), encoding='utf-8', newline='\n')
    print('  %-26s %d rows in %d views  %d bytes' % ('rig.json', doc['_meta']['counts']['rows'],
                                                     doc['_meta']['counts']['views'], path.stat().st_size))


def main():
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0],
                                 epilog='Set CARD_BROWSER=<path> to choose the browser used for the PNG render.')
    ap.add_argument('--dashboard-only', action='store_true',
                    help='write only dashboard/web/rig/ (no cards, no browser needed)')
    args = ap.parse_args()
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

    print('Writing the dashboard rig reference...')
    write_rig()

    print('Cropping + recoloring diagram sub-views...')
    sub = {v['Id']: get_sub_diagram(v['File'], v['Box']) for v in VIEWS if v['File']}
    cap = {v['Id']: v['Caption'] for v in VIEWS}
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
    t = text['MOZA_MHG_AB6_ref']
    new_card({
        'Name': t['Name'], 'F': 1.18, 'CanvasW': 1860, 'CanvasH': 1437,
        'Title': t['Title'], 'Sub': t['Sub'],
        'Stack': {'X': 24, 'W': 1040, 'Gap': 22, 'Rows': [
            {'HFrac': 1.12, 'Imgs': [img('mhg_front', 0.56, 't'), img('mhg_side', 0.44, 'b')]},
            {'HFrac': 1.00, 'Imgs': [img('ab6_base', 0.53, 'b')]},
        ]},
        'Cols': [{'X': 1090, 'W': 370, 'Rows': MHG_L}, {'X': 1475, 'W': 365, 'Rows': MHG_R + AB6}],
        'Legend': t['Legend'],
    }, browser)

    # --- Card 2: MTQ throttle (js2) ---
    # Top band: the two module views side by side. Bottom band: the throttle panel
    # (the big, button-dense view) below them.
    t = text['MOZA_MTQ_ref']
    new_card({
        'Name': t['Name'], 'F': 1.15, 'CanvasW': 1860, 'CanvasH': 1437,
        'Title': t['Title'], 'Sub': t['Sub'],
        'Stack': {'X': 24, 'W': 1040, 'Gap': 22, 'Rows': [
            {'HFrac': 0.95, 'Imgs': [img('mtq_right', 0.52, 't'), img('mtq_left', 0.52, 'b')]},
            {'HFrac': 1.30, 'Imgs': [img('mtq_panel', 0.74)]},
        ]},
        'Cols': [{'X': 1090, 'W': 370, 'Rows': MTQ_L}, {'X': 1475, 'W': 365, 'Rows': MTQ_R}],
        'Legend': t['Legend'],
    }, browser)

    print('Done -> MOZA_MHG_AB6_ref, MOZA_MTQ_ref (.png + .svg) in %s' % CARD_DIR)


if __name__ == '__main__':
    main()
