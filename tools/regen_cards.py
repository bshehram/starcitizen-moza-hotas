"""regen_cards.py - the MOZA button-reference cards (split-diagram, print layout).

Produces the TWO reference cards, sized to fill a US-Letter sheet in LANDSCAPE
(11 x 8.5 in, aspect 1.294) for printing in hand:

    cards/MOZA_MHG_AB6_ref.png / .svg   (js1: MHG grip 1-29 + AB6 base 49-62)
    cards/MOZA_MTQ_ref.png     / .svg   (js2: MTQ throttle 1-65 + axes)

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

CROP RECTANGLES (x0, y0, x1, y1 in source-PNG pixels) - re-verify if MOZA ships new
device art (sources: AB6 890x691, MHG 1037x822, MTQ 1049x820):
  MTQ main   60, 90,612,818     MTQ right 615, 72,1045,486   MTQ left 620,488,1045,818
  MHG front 515, 90,985,575     MHG side  100,168, 460,770   AB6 base 250,110, 785,650

REQUIREMENTS: Python 3.8+, Pillow (`python -m pip install Pillow`), and Chrome, Edge or
Chromium for the SVG -> PNG render (found automatically on Windows, macOS and Linux;
set CARD_BROWSER=<path> to pick one).
RUN (from the project root):
    python tools/regen_cards.py
"""

import base64
import io
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    sys.exit('regen_cards: Pillow is required.  Run:  python -m pip install Pillow')

REPO = Path(__file__).resolve().parent.parent
DIAG_DIR = REPO / 'diagrams'
CARD_DIR = REPO / 'cards'
MID = '·'

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
# more images side by side: each owns a cell = Frac of the zone width (cells centred in
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
    {'Label': '49', 'Primary': 'Target: cycle in-view fwd', 'Variants': [V('Mine:', 'module 1', C_MINE), V('Salv:', 'focus all', C_SALV)]},
    {'Label': '50', 'Primary': 'Target: cycle in-view back', 'Variants': [V('Mine:', 'module 2', C_MINE), V('Salv:', 'focus left', C_SALV)]},
    {'Label': '51', 'Primary': 'Target: lock closest (any)', 'Variants': [V('Mine:', 'module 3', C_MINE), V('Salv:', 'focus right', C_SALV)]},
    {'Label': '52', 'Primary': 'Target: lock closest attacker', 'Variants': [V('Mine:', 'jettison cargo', C_MINE), V('Salv:', 'beam axis H/V', C_SALV)]},
    {'Label': '53', 'Primary': 'Target: cycle friendly fwd', 'Variants': [V('Salv:', 'fire left beam', C_SALV)]},
    {'Label': '54', 'Primary': 'Target: cycle friendly back', 'Variants': [V('Salv:', 'fire right beam', C_SALV)]},
    {'Label': '55', 'Primary': 'Target: cycle pinned back', 'Variants': [V('Salv:', 'reset gimbal', C_SALV)]},
    {'Label': '56', 'Primary': 'Target: reset sub-target'},
    {'Label': '57-59', 'Primary': 'Left "Slider" lever', 'Hint': 'unbound - reserved', 'Unbound': True},
    {'Label': '60-62', 'Primary': 'Right "Dial" lever', 'Hint': 'unbound - reserved', 'Unbound': True},
]

# ================================================================ MHG (js1 1-29)
MHG_L = [
    {'Header': 'GRIP 1-15'},
    {'Label': '1', 'Primary': 'Fire Guns - Group 1', 'Variants': [V('Mine:', 'fire laser', C_MINE), V('Salv:', 'focused beam', C_SALV)]},
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
    {'Label': '12', 'Primary': 'Cycle sub-target forward'},
    {'Label': '13', 'Primary': 'Cycle attackers forward'},
    {'Label': '14', 'Primary': 'Cycle sub-target back'},
    {'Label': '15', 'Primary': 'Cycle attackers back'},
]
MHG_R = [
    {'Header': 'GRIP 16-29'},
    {'Label': '16', 'Primary': 'Gimbal lock toggle'},
    {'Label': '17', 'Primary': 'Scan angle - narrow'},
    {'Label': '18', 'Primary': 'Activate scanning (hold)'},
    {'Label': '19', 'Primary': 'Scan angle - widen'},
    {'Label': '20', 'Primary': 'Radar ping'},
    {'Label': '21', 'Primary': 'ADS / cockpit zoom toggle'},
    {'Label': '22', 'Primary': 'Weapon preset - next', 'Variants': [V('Msl:', 'type +', C_NOTE), V('Mine:', 'pwr +', C_MINE), V('Salv:', 'gap +', C_SALV)]},
    {'Label': '23', 'Primary': 'Weapon preset - prev', 'Variants': [V('Msl:', 'type -', C_NOTE), V('Mine:', 'pwr -', C_MINE), V('Salv:', 'gap -', C_SALV)]},
    {'Label': '24', 'Primary': 'Weapon aim-type cycle', 'Variants': [V('Mine:', 'fracture/extract', C_MINE), V('Salv:', 'structural mode', C_SALV)]},
    {'Label': '25', 'Primary': 'Strafe up'},
    {'Label': '26', 'Primary': 'Strafe right'},
    {'Label': '27', 'Primary': 'Strafe down'},
    {'Label': '28', 'Primary': 'Strafe left'},
    {'Label': '29', 'Primary': 'Decoupled mode toggle'},
]

# ================================================================ MTQ (js2 1-65 + axes)
MTQ_L = [
    {'Header': 'PANEL BUTTONS 1-30'},
    {'Label': '1', 'Primary': 'Weapons power toggle', 'Hint': 'keypad A1'},
    {'Label': '2', 'Primary': 'Thruster power toggle', 'Hint': 'A2'},
    {'Label': '3', 'Primary': 'Shield power toggle', 'Hint': 'A3'},
    {'Label': '4', 'Primary': 'LAMP night-vision toggle', 'Hint': 'A4'},
    {'Label': '5', 'Primary': 'Master mode SCM / NAV', 'Hint': 'NAV key'},
    {'Label': '6', 'Primary': 'Starmap', 'Hint': 'HDG key'},
    {'Label': '7', 'Primary': 'Engage quantum drive', 'Hint': 'SPD key'},
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
    {'Label': '22', 'Primary': 'Rocker centre', 'Hint': 'rest', 'Unbound': True},
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
    {'Label': '31-43', 'Primary': 'unbound (analog axes)', 'Unbound': True},
    {'Label': '49', 'Primary': 'VTOL off', 'Hint': '3-pos switch rest'},
    {'Label': '50', 'Primary': 'VTOL on', 'Hint': '3-pos switch fwd-latch'},
    {'Label': '51', 'Primary': 'Space brake', 'Hint': '3-pos switch back'},
    {'Label': '56', 'Primary': 'Power to weapons', 'Hint': 'WPN hat up'},
    {'Label': '55', 'Primary': 'Power to shields', 'Hint': 'WPN hat down'},
    {'Label': '54', 'Primary': 'Power to engines', 'Hint': 'WPN hat left'},
    {'Label': '53', 'Primary': 'Power allocation reset', 'Hint': 'WPN hat right'},
    {'Label': '52', 'Primary': 'Power to shields MAX', 'Hint': 'WPN hat hold'},
    {'Label': '61', 'Primary': 'Cycle all contacts fwd', 'Hint': 'COM hat up'},
    {'Label': '60', 'Primary': 'Cycle all contacts back', 'Hint': 'COM hat down'},
    {'Label': '59', 'Primary': 'Cycle pinned forward', 'Hint': 'COM hat left'},
    {'Label': '58', 'Primary': 'Lock closest hostile', 'Hint': 'COM hat right'},
    {'Label': '57', 'Primary': 'Pin target', 'Hint': 'COM hat press'},
    {'Label': '62', 'Primary': 'Cycle camera view', 'Hint': 'mini-stick press'},
    {'Label': '63', 'Primary': 'Zoom in - cockpit', 'Hint': 'throttle dial fwd'},
    {'Label': '64', 'Primary': 'Zoom out - cockpit', 'Hint': 'throttle dial back'},
    {'Label': '65', 'Primary': 'Boost / afterburner', 'Hint': 'L-Module button'},
    {'Header': 'AXES'},
    {'Label': 'RY', 'Primary': 'Main throttle - forward', 'Hint': 'throttle lever'},
    {'Label': 'RZ', 'Primary': 'Throttle - reverse', 'Hint': 'behind idle detent'},
    {'Label': 'Slider', 'Primary': 'Mining laser power', 'Hint': 'FLAPS, Mining'},
    {'Label': 'Dial', 'Primary': 'Salvage beam spacing', 'Hint': 'S-brake, Salvage'},
    {'Label': 'X / Y', 'Primary': 'Camera look (yaw / pitch)', 'Hint': 'mini-stick'},
    {'Label': 'RX / Z', 'Primary': 'Throttle twins', 'Hint': 'unbound', 'Unbound': True},
]


def main():
    import argparse
    argparse.ArgumentParser(description=__doc__.split('\n')[0],
                            epilog='Set CARD_BROWSER=<path> to choose the browser used for the PNG render.').parse_args()
    browser = find_browser()
    if not browser:
        sys.exit('regen_cards: no Chrome / Edge / Chromium found to render SVG -> PNG '
                 '(install one, or set CARD_BROWSER=<path to the browser executable>).')

    print('Cropping + recoloring diagram sub-views...')
    sub_mtq_main = get_sub_diagram('MOZA_MTQ.png', (60, 90, 612, 818))
    sub_mtq_right = get_sub_diagram('MOZA_MTQ.png', (615, 72, 1045, 486))
    sub_mtq_left = get_sub_diagram('MOZA_MTQ.png', (620, 488, 1045, 818))
    sub_mhg_front = get_sub_diagram('MOZA_MHG.png', (515, 90, 985, 575))
    sub_mhg_side = get_sub_diagram('MOZA_MHG.png', (100, 168, 460, 770))
    sub_ab6_base = get_sub_diagram('MOZA_AB6.png', (250, 110, 785, 650))

    # Layout: LEFT ~60% of the sheet = images (two stacked bands - the two small views side by
    # side on top, the one big view below); RIGHT ~40% = the lookup table in two columns.
    # CanvasW:CanvasH = 11:8.5 (1.294) fills a Letter sheet in landscape. F is dialled down so
    # the narrow 40% table still fits. Geometry: image zone x=24..1064 (W=1040); table at x=1090.
    print('Rendering print cards (2x via %s)...' % os.path.basename(browser))

    # --- Card 1: MHG grip + AB6 base (js1), combined ---
    # Top band: the two grip views side by side (larger). Bottom band: the AB6 base
    # (smaller - far fewer buttons). Base Frac kept below the grips' so it reads smaller.
    new_card({
        'Name': 'MOZA_MHG_AB6_ref', 'F': 1.18, 'CanvasW': 1860, 'CanvasH': 1437,
        'Title': 'MOZA MHG Grip + AB6 Base  -  Button Reference  (js1)',
        'Sub': 'MHG grip 1-29 mounted on the AB6 base 49-62  %s  trigger / hats / rocker / wings reused per operator mode' % MID,
        'Stack': {'X': 24, 'W': 1040, 'Gap': 22, 'Rows': [
            {'HFrac': 1.12, 'Imgs': [
                {'D': sub_mhg_front, 'Frac': 0.56, 'VA': 't', 'Caption': 'MHG grip - front (hats & buttons)'},
                {'D': sub_mhg_side, 'Frac': 0.44, 'VA': 'b', 'Caption': 'MHG grip - side'}]},
            {'HFrac': 1.00, 'Imgs': [
                {'D': sub_ab6_base, 'Frac': 0.53, 'VA': 'b', 'Caption': 'AB6 base - wings & levers'}]},
        ]},
        'Cols': [{'X': 1090, 'W': 370, 'Rows': MHG_L}, {'X': 1475, 'W': 365, 'Rows': MHG_R + AB6}],
        'Legend': ('Combat (default)  %s  Msl: Missile  %s  Mine: Mining  %s  Salv: Salvage.  One control = a '
                   'different job per operator mode (set on the MTQ knob); AB6 wings 49-56 are targeting in '
                   'combat, module/salvage banks in those modes.' % (MID, MID, MID)),
    }, browser)

    # --- Card 2: MTQ throttle (js2) ---
    # Top band: the two module views side by side. Bottom band: the throttle panel
    # (the big, button-dense view) below them.
    new_card({
        'Name': 'MOZA_MTQ_ref', 'F': 1.15, 'CanvasW': 1860, 'CanvasH': 1437,
        'Title': 'MOZA MTQ Throttle Panel  -  Button Reference  (js2)',
        'Sub': 'throttle 1-65 + axes  %s  buttons 44-48 are absent on the device' % MID,
        'Stack': {'X': 24, 'W': 1040, 'Gap': 22, 'Rows': [
            {'HFrac': 0.95, 'Imgs': [
                {'D': sub_mtq_right, 'Frac': 0.52, 'VA': 't'},
                {'D': sub_mtq_left, 'Frac': 0.52, 'VA': 'b'}]},
            {'HFrac': 1.30, 'Imgs': [
                {'D': sub_mtq_main, 'Frac': 0.74, 'Caption': 'Throttle panel'}]},
        ]},
        'Cols': [{'X': 1090, 'W': 370, 'Rows': MTQ_L}, {'X': 1475, 'W': 365, 'Rows': MTQ_R}],
        'Legend': ('Throttle forward = axis RY; reverse = axis RZ, the travel behind the idle detent (MOZA Reverse '
                   'Thrust mode).  FLAPS & Speedbrake levers drive analog axes (Slider / Dial) in Mining / Salvage '
                   'modes; detent buttons 31-43 are unbound.'),
    }, browser)

    print('Done -> MOZA_MHG_AB6_ref, MOZA_MTQ_ref (.png + .svg) in %s' % CARD_DIR)


if __name__ == '__main__':
    main()
