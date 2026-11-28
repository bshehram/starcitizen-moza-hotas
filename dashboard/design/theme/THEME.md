# The base color: one setting that colors the dashboard

The implementer's brief for [`../../PLAN.md`](../../PLAN.md) §4 item 19. Written by the design
session of 2026-11-28. A Worker builds from this file; a reviewer checks the build against it.

## Where it stands

- **Designed and mocked up on 2026-11-28. Not built.** Nothing in `scdash/`, `web/` or `tests/`
  has changed for it.
- The mockup is real: the page's own screens, frozen from a running test instance, with only the
  color tokens swapped. It is in the git-ignored `dashboard/data/design/theme/` on the PC where
  it was made (`index.html` lists everything; `sheets/` and `shots/` hold the captures). The
  designer looked at every capture. **The user has not seen any of it yet.**
- Two decisions are the user's and are still open: see "The user's decisions" below. Stage A can
  be built before they answer; stage B waits for a yes.

## What it is for, and what it is not

The user, 2026-11-28: "for the moza cockpit LED button settings i have all of the devices set to
use 0,0,255 which is the basic blue LED can we use that as the 'mother' color for the dashboard?
can we make it so we have a singular setting that accepts the RGB 0,0,0 format just like the moza
cockpit for the dashboard color theme 'Base' or whatever? this way if i change the moza rig to
0,255,0 which i think is the default green, we can change that in the dashboard too and it
reflects that so sort of like a theme type thing."

So: **one setting, an RGB triple written the way MOZA Cockpit writes it, from which the page
takes its color.** The default is `0,0,255`, the color of the LEDs on the stick and throttle
beside the screen.

It is not:

- **A second look.** The look stays direction B, "Avionics" (PLAN §11): the same type, line
  work, panes and layouts. Only color tokens change.
- **A way to move red, amber or green.** They mean alarm, attention and all-clear, and they keep
  their colors, shapes and words under every base.
- **A brightness control or a light theme.** The base gives a hue and a saturation. How light
  each part of the page is belongs to the design.
- **A match for the LED's exact color.** A pure LED color is not a screen color: `0,0,255` as
  text on the page's ground has a contrast of 2.3:1. The page takes the LED's hue and shows it
  at the lightness each part needs.

## The facts it rests on

- **[seen 2026-11-28]** Every color of the page is a custom property in the `:root` block of
  `web/style.css`, except: the reds of the failed-preflight screen (`#1A0B0B`, `#160909`,
  `#120707`, `#3A1A18`, `#1A0505`), two black shadows, and the terminal pane's fill `#080D12`
  and text `#D3DCE4`.
- **[seen 2026-11-28]** The rig reference's diagrams (`web/rig/*.png`) are one ink, `#E4ECF2`,
  with 16 levels of alpha on a transparent ground (`RIG_ART` in `../../../tools/regen_cards.py`).
  The page shows each as `<img class="dg__img">` and draws the button numbers over it (`.dn`).
- **[seen 2026-11-28]** A CSS mask made from one of those PNGs draws the line work in any color:
  rendered in headless Edge from a page served over HTTP on 127.0.0.1. From a `file://` page the
  same mask draws nothing (the browser does not load it). The real page is served over HTTP.
- **[seen 2026-11-28]** The page's content policy is `default-src 'none'; script-src 'self';
  style-src 'self'; img-src 'self' data:`. A stylesheet served by the service is allowed; an
  inline `style` attribute is not; `element.style.setProperty()` from script is (the meters
  already use it).
- **[seen 2026-11-28]** Settings: `scdash/config.py` (`DEFAULTS`, `BOUNDS`, `load_settings`,
  `_check`), read once at start from `data/config.json`. A value that fails its check takes the
  default, with a note in the log. `Service._service_block()` is the `service` part of every
  message; `Service._page_vars()` fills the placeholders of `index.html`.
- **[seen 2026-11-28]** Color distances in OKLab between the status colors: amber to red 0.136,
  green to amber 0.210. Today's cyan accent to green: 0.130.
- **[verify]** The request guard lets the browser's request for a mask image through. A mask is
  fetched in CORS mode, so its `Sec-Fetch-Mode` differs from an `<img>`'s; `Sec-Fetch-Site` is
  still `same-origin`. The browser test in "Tests" settles it.
- **[verify]** Nothing here has been seen on the side monitor or beside the lit rig. Whether
  `#83ABFF` on that panel reads as the LEDs' blue is the user's to say.

## The design

### What the base controls

The base is three whole numbers, red, green and blue, each 0 to 255.

- **Its hue** colors everything that is not a status color: the ground, the panes, the line
  work, the text's faint tint, and the accent. The hue is the base's own, measured in OKLCH (a
  color space in which equal steps look equal).
- **Its saturation** (as a color picker shows it: `(max - min) / max`) sets how strongly the
  ground, lines and text are tinted. A pastel base gives a grayer page. The accent does not fade
  with it: an accent that turns gray stops being one.
- **Its brightness is ignored.** `0,0,64` gives the same page as `0,0,255`.
- **A base with no color** (saturation under 0.08: white, any gray, black) gives a neutral gray
  page, and the accent is the look's own cyan, `#46D3E6`, exactly as the user chose it on
  2026-11-27. There is no hue to take, and the page needs an accent that differs from its text.

### Luminance is the design's, so contrast does not depend on the base

Every derived token has a **relative luminance of its own** (the quantity contrast ratios are
computed from), taken from the look as built. The derivation finds the color of the base's hue
that has exactly that luminance. So every contrast ratio on the page is the same for every base,
to within the rounding of 8-bit color.

One primitive does all of it:

> `fit(Y, C, h)`: the sRGB color with hue `h` and relative luminance `Y`, with the largest
> chroma up to `C` that sRGB can show. Chroma gives way first. Luminance and hue never do.

| Token | Luminance | Chroma at full saturation | Used for |
| --- | --- | --- | --- |
| `--c-bg` | 0.0029 | 0.012 | the page's ground |
| `--c-pane` | 0.0050 | 0.017 | the strip, the feed, pane fills |
| `--c-pane-2` | 0.0078 | 0.019 | raised things: a pressed button, the desk panel |
| `--c-term` (new) | 0.0038 | 0.014 | the terminal pane's fill, today the literal `#080D12` |
| `--c-line` | 0.0153 | 0.025 | hairlines |
| `--c-line-2` | 0.0329 | 0.034 | stronger lines, borders, unlit meter cells |
| `--c-br` | 0.1131 | 0.044 | corner brackets |
| `--c-text` | 0.8290 | 0.012 | text; also the ink of the rig diagrams |
| `--c-term-text` (new) | 0.7064 | 0.015 | the terminal's text, today the literal `#D3DCE4` |
| `--c-text-2` | 0.4679 | 0.026 | secondary text |
| `--c-text-3` | 0.3609 | 0.031 | labels |
| `--c-accent-dim` | 0.0760 | 0.060, not scaled by saturation | quiet accent borders |
| `--c-accent` | 0.400 to 0.760, see below | 0.130 to 0.060, not scaled by saturation | the accent |

The chroma of a body token is its figure times the base's saturation. The figures are today's
own: with a base whose hue is near 250 the body comes out as it is now (`0,0,255` gives a ground
of `#070A0F`; today's is `#060A0E`).

### The accent

1. **Full strength:** chroma 0.130 at the base's hue, at luminance 0.536 (today's cyan) where
   sRGB can show that chroma there. Blues and violets cannot be that light and that strong at
   once, so for them the luminance comes down to the lightest value that still carries the
   chroma, and never under 0.400. `0,0,255` gives `#83ABFF` at luminance 0.41.
2. **Pale near a status color.** Starting from full strength, the accent is moved in 32 equal
   steps toward a pale end (luminance 0.760, chroma 0.060) and stops at the first step where its
   OKLab distance from green, amber and red is at least 0.110, 0.130 and 0.170. Far from all
   three (blue, violet, most cyans) it stops at step 0. On a green rig it stops about two thirds
   of the way (`#B5E4B1`); on a red rig about four fifths (`#FFCFC7`).

The floors: the two closest status colors, amber and red, are 0.136 apart, so the accent is kept
about as far from a status color as the status colors are from each other. Red gets more room
because a false alarm costs most; green a little less because mistaking the accent for all-clear
costs least, and the user named a green rig as the case that has to work.

### What does not move

| Token or literal | Value | Why |
| --- | --- | --- |
| `--c-ok`, `--c-warn`, `--c-bad` | `#4FDB8F`, `#FFB23E`, `#FF8578` | all-clear, attention, alarm |
| `--c-warn-tint`, `--c-bad-tint`, `--c-bad-hatch` | `#241B0B`, `#241010`, `#2E1212` | the fills behind them |
| the failed-preflight reds | `#1A0B0B`, `#160909`, `#120707`, `#3A1A18`, `#1A0505` | the loudest state stays the same under every base |
| `--c-claude` | `#D97757` | a brand mark, not the instrument's color |
| the two shadows | `rgba(0, 0, 0, .55)` | black |

Their shapes and words do not change either: an octagon, a triangle, a check, and the word beside
each.

**A rig whose color is near a status color** (green, red, orange, yellow, pink):

- The ground, panes, lines and labels take the rig's hue as on any other rig. They are dark and
  weakly colored, so they cannot be read as a status: the page reads as a green or a red
  instrument.
- The accent keeps the rig's hue and turns pale, as far as the floors above require. A pale
  green heading beside a saturated green check, a pale pink badge beside a salmon alarm: the
  status color is always the stronger of the two, and it alone carries a shape and a word.
- **The price, on a red, orange or yellow rig:** the accent ends up close to the text color
  (OKLab distance 0.05 to 0.07, against 0.23 on a blue rig). Emphasis there leans on weight,
  position and the 3-pixel bars, which every accented element already has. The rig reference's
  highlighted buttons are still told from the plain ones in the captures, but weakly. On a green
  rig the distance is 0.10 and the highlight is clear.
- The failed-preflight screen and the alerts are drawn from the fixed colors, so they look the
  same on every base. Captures: `sheets/fail.png`, `sheets/alerts.png`.

### The rig reference

- **The diagrams' line work** is drawn in `--c-text` through a CSS mask made from the same PNG,
  so it follows the base exactly and the image files stay as they are (one ink with alpha). The
  card generator and `web/rig/` do not change.
- **The button numbers** over the art keep their roles: a plain number is filled with
  `--c-text`, a number whose job changes in the chosen mode with `--c-accent`, a quiet one with
  `--c-line-2`. So the "changes in this mode" highlight follows the base through the accent,
  with the pale rule above.
- The row badges, the left bars and the pressed filter button use `--c-accent` and follow the
  same way. Nothing in the rig section gets a color of its own.

### The numbers, checked

Computed by the reference module below over 1,445 bases: every whole degree of the color wheel
at saturations 1, 0.5, 0.2 and 0.09, plus black, white, gray, `1,0,0` and `0,0,64`
**[seen 2026-11-28, the designer's run]**.

| Pair | At `0,0,255` | Worst over all bases | Must stay at or above |
| --- | --- | --- | --- |
| `--c-text` on `--c-bg` / `--c-pane` / `--c-pane-2` / `--c-term` | 16.6 / 16.0 / 15.2 / 16.4 | 15.13 | 15.0 |
| `--c-text-2` on the same four | 9.8 / 9.4 / 9.0 / 9.7 | 8.90 | 8.8 |
| `--c-text-3` on the same four | 7.7 / 7.4 / 7.07 / 7.6 | 7.06 | 7.0 |
| `--c-accent` on the same four | 8.7 / 8.4 / 8.0 / 8.6 | 7.87 | 7.5 |
| `--c-term-text` on `--c-term` | 14.1 | 13.97 | 13.5 |
| `--c-bg` on `--c-accent` (a number on an accent badge) | 8.7 | 8.60 | 7.5 |
| `--c-br` on `--c-bg` (not text) | 3.08 | 3.05 | 3.0 |
| accent to green / amber / red, OKLab | 0.243 / 0.291 / 0.247 | 0.110 / 0.130 / 0.170 | 0.110 / 0.130 / 0.170 |

The stylesheet's own rule, "every text color 7:1 or better on `--c-bg`, `--c-pane` and
`--c-pane-2`", holds for every base. The tightest pair is the same one as today: labels on a
raised pane (7.11 in the look as built).

Luminance error from 8-bit rounding, at worst: 5.3 % for `--c-bg` (one step of one channel near
black, which moves a contrast ratio by under 0.3 %), under 0.7 % for every text token.

### The reference module

This is the whole derivation. `scdash/theme.py` is this code (the iteration counts and bounds
matter: the vectors under it are exact).

```python
"""The dashboard's colors from one base color. Pure: no file, no clock, nothing imported but math and re."""
import math
import re

DEFAULT_BASE = (0, 0, 255)
GRAY_BELOW = 0.08                      # a base less saturated than this has no color
LOOK_ACCENT, LOOK_ACCENT_DIM = "#46D3E6", "#1D5560"    # the look's own cyan, used when the base has no color

# The body: token, luminance, chroma at full saturation.
BODY = (
    ("--c-bg",        0.0029, 0.012),
    ("--c-pane",      0.0050, 0.017),
    ("--c-pane-2",    0.0078, 0.019),
    ("--c-term",      0.0038, 0.014),
    ("--c-line",      0.0153, 0.025),
    ("--c-line-2",    0.0329, 0.034),
    ("--c-br",        0.1131, 0.044),
    ("--c-text",      0.8290, 0.012),
    ("--c-term-text", 0.7064, 0.015),
    ("--c-text-2",    0.4679, 0.026),
    ("--c-text-3",    0.3609, 0.031),
)
ACCENT_C = 0.130                       # the accent at full strength: its chroma,
ACCENT_Y_MAX = 0.536                   # its luminance where the hue can carry that chroma,
ACCENT_Y_MIN = 0.400                   # and the luminance it is never under
PALE_Y, PALE_C, PALE_STEPS = 0.760, 0.060, 32          # the pale end, and the steps toward it
ACCENT_DIM_Y, ACCENT_DIM_C = 0.0760, 0.060

# What does not move, and how far the accent stays from each (distance in OKLab).
STATUS = {"ok": "#4FDB8F", "warn": "#FFB23E", "bad": "#FF8578"}
FLOOR = {"ok": 0.110, "warn": 0.130, "bad": 0.170}


def parse_base(value):
    """The setting's value -> (r, g, b), or None when it is refused."""
    if isinstance(value, (list, tuple)):
        ok = len(value) == 3 and all(type(v) is int and 0 <= v <= 255 for v in value)
        return tuple(value) if ok else None
    if not isinstance(value, str) or len(value) > 32:
        return None
    t = value.strip(" \t")
    m = re.fullmatch(r"#([0-9A-Fa-f]{6})", t)
    if m:
        return tuple(int(m.group(1)[i:i + 2], 16) for i in (0, 2, 4))
    m = re.fullmatch(r"[Rr][Gg][Bb]\(([^()]*)\)", t)
    if m:
        t = m.group(1).strip(" \t")
    m = re.fullmatch(r"([0-9]{1,3})(?: *, *| +)([0-9]{1,3})(?: *, *| +)([0-9]{1,3})", t)
    if not m:
        return None
    v = tuple(int(x) for x in m.groups())
    return v if max(v) <= 255 else None


def _lin(rgb):                         # 8-bit sRGB -> linear RGB
    return tuple(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in (v / 255 for v in rgb))


def _rgb(lin):                         # linear RGB -> 8-bit sRGB, clipped and rounded
    out = []
    for v in lin:
        v = max(0.0, min(1.0, v))
        v = 12.92 * v if v <= 0.0031308 else 1.055 * v ** (1 / 2.4) - 0.055
        out.append(max(0, min(255, int(round(v * 255)))))
    return tuple(out)


def _y(lin):                           # relative luminance (WCAG)
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def _lab(lin):                         # linear RGB -> OKLab
    r, g, b = lin
    l = (0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b) ** (1 / 3)
    m = (0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b) ** (1 / 3)
    s = (0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b) ** (1 / 3)
    return (0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s,
            1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s,
            0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s)


def _from_lch(L, C, h):                # OKLCH -> linear RGB, not clipped
    a, b = C * math.cos(math.radians(h)), C * math.sin(math.radians(h))
    l = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3
    m = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3
    s = (L - 0.0894841775 * a - 1.2914855480 * b) ** 3
    return (4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
            -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
            -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s)


def hex_rgb(h):
    return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))


def luminance(rgb):
    return _y(_lin(rgb))


def contrast(a, b):
    hi, lo = sorted((luminance(a), luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def distance(a, b):                    # between two 8-bit colors, in OKLab
    return math.dist(_lab(_lin(a)), _lab(_lin(b)))


def _lightness(y, c, h):               # the OKLCH lightness at which chroma c and hue h have luminance y
    lo, hi = 0.0, 1.5
    for _ in range(40):
        mid = (lo + hi) / 2
        if _y(_from_lch(mid, c, h)) < y:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def _fits(y, c, h):                    # can sRGB show it
    return all(-1e-6 <= v <= 1 + 1e-6 for v in _from_lch(_lightness(y, c, h), c, h))


def _chroma(y, c, h):                  # the largest chroma up to c that sRGB can show
    if _fits(y, c, h):
        return c
    lo, hi = 0.0, c
    for _ in range(24):
        mid = (lo + hi) / 2
        if _fits(y, mid, h):
            lo = mid
        else:
            hi = mid
    return lo


def fit(y, c, h):
    """The sRGB color of hue h and luminance y, with the largest chroma up to c that sRGB can show."""
    c = _chroma(y, c, h)
    return _rgb(_from_lch(_lightness(y, c, h), c, h))


def _accent(h):
    if _fits(ACCENT_Y_MAX, ACCENT_C, h):
        y0 = ACCENT_Y_MAX
    elif not _fits(ACCENT_Y_MIN, ACCENT_C, h):
        y0 = ACCENT_Y_MIN
    else:                              # the lightest luminance that still carries the chroma
        lo, hi = ACCENT_Y_MIN, ACCENT_Y_MAX
        for _ in range(16):
            mid = (lo + hi) / 2
            if _fits(mid, ACCENT_C, h):
                lo = mid
            else:
                hi = mid
        y0 = lo
    c0 = _chroma(y0, ACCENT_C, h)
    rgb = None
    for i in range(PALE_STEPS + 1):    # paler step by step, until it is far enough from every status color
        p = i / PALE_STEPS
        rgb = fit(y0 + p * (PALE_Y - y0), c0 + p * (PALE_C - c0), h)
        if all(distance(rgb, hex_rgb(STATUS[k])) >= FLOOR[k] for k in STATUS):
            return rgb, p
    return rgb, 1.0


def derive(base):
    """{"base": "r,g,b", "hue": degrees or None, "sat": 0-1, "pale": 0-1, "tokens": {name: "#RRGGBB"}}"""
    hi, lo = max(base), min(base)
    sat = 0.0 if hi == 0 else (hi - lo) / hi
    hue = None
    if sat < GRAY_BELOW:
        sat = 0.0
    else:
        L, a, b = _lab(_lin(base))
        hue = math.degrees(math.atan2(b, a)) % 360
    as_hex = lambda rgb: "#%02X%02X%02X" % rgb
    tokens = {name: as_hex(fit(y, c * sat, hue or 0.0)) for name, y, c in BODY}
    pale = 0.0
    if hue is None:
        tokens["--c-accent"], tokens["--c-accent-dim"] = LOOK_ACCENT, LOOK_ACCENT_DIM
    else:
        rgb, pale = _accent(hue)
        tokens["--c-accent"] = as_hex(rgb)
        tokens["--c-accent-dim"] = as_hex(fit(ACCENT_DIM_Y, ACCENT_DIM_C, hue))
    return {"base": "%d,%d,%d" % tuple(base), "hue": None if hue is None else round(hue, 1), "sat": round(sat, 3),
            "pale": round(pale, 3), "tokens": tokens}
```

### Vectors

`derive()` must return exactly these.

| Token | `0,0,255` | `0,255,0` | `255,0,0` | `255,255,255` | `255,255,0` | `255,128,0` | `0,255,255` | `128,128,255` |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `--c-bg` | #070A0F | #070B07 | #0F0807 | #0A0A0A | #0A0A05 | #0E0906 | #050B0B | #09090C |
| `--c-pane` | #0C1017 | #0B110A | #170D0C | #101010 | #101008 | #160E09 | #061211 | #0F0F13 |
| `--c-pane-2` | #11161E | #101710 | #1E1311 | #161616 | #16160C | #1D140E | #0A1818 | #15151A |
| `--c-term` | #090C13 | #090E08 | #120B09 | #0C0C0C | #0D0D06 | #120B07 | #050E0E | #0C0C0F |
| `--c-line` | #1B212D | #1A2419 | #2D1D1B | #212121 | #222214 | #2B1E16 | #112424 | #202127 |
| `--c-line-2` | #2A3345 | #283727 | #442D2A | #333333 | #333420 | #422F23 | #1B3737 | #31323C |
| `--c-br` | #525F78 | #4F644D | #775752 | #5E5E5E | #5F6043 | #745948 | #3E6565 | #5C5E6B |
| `--c-text` | #E7EBF3 | #E6EDE5 | #F3E9E7 | #EBEBEB | #EBECE3 | #F2E9E4 | #E2EDED | #EAEBEF |
| `--c-term-text` | #D6DBE5 | #D5DDD4 | #E5D8D6 | #DBDBDB | #DBDCD1 | #E4D9D2 | #D0DEDD | #DADAE0 |
| `--c-text-2` | #AEB7C7 | #ACBAAB | #C7B1AE | #B6B6B6 | #B6B8A5 | #C5B3A8 | #A3BBBA | #B4B6BF |
| `--c-text-3` | #98A2B6 | #96A695 | #B69C98 | #A2A2A2 | #A2A48E | #B39E91 | #8BA7A7 | #A0A1AC |
| `--c-accent` | #83ABFF | #B5E4B1 | #FFCFC7 | #46D3E6 | #DFE1AB | #FFD5BC | #66DFDE | #9FA4FF |
| `--c-accent-dim` | #3E4E6F | #395536 | #6D433C | #1D5560 | #4F5028 | #69462F | #1B5656 | #484B6F |
| hue | 264.1 | 142.5 | 29.2 | none | 109.8 | 53.0 | 194.8 | 280.1 |
| sat | 1.000 | 1.000 | 1.000 | 0.000 | 1.000 | 1.000 | 1.000 | 0.498 |
| pale | 0.000 | 0.656 | 0.812 | 0.000 | 0.844 | 0.875 | 0.312 | 0.000 |

More, for the tests: `0,0,64` equals `0,0,255` in every token. `0,0,0`, `128,128,128`,
`200,200,210` and `235,235,255` (saturation 0.078) equal `255,255,255`. `230,230,255`
(saturation 0.098) has a hue again: its accent is `#A9A3FF`.

## The setting

### Its name and where it lives

`theme.base` in `dashboard/data/config.json`, documented in `dashboard/config.example.json`:

```json
"_theme": "The color the page takes its colors from. base: red, green, blue, each 0 to 255, written as MOZA Cockpit shows an LED color, so the screen matches the rig's lights. \"0,0,255\" is blue; \"0,255,0\" green. The hue and the saturation are used; how bright each part of the page is belongs to the design, and red, amber and green keep their meanings. A base with no color (white, gray, black) gives a gray page with the look's own cyan accent. Also accepted: \"rgb(0,0,255)\", \"#0000FF\" and [0, 0, 255]. Unlike the other settings this one is picked up while the service runs: within a second with the game running, within about ten seconds without.",
"theme": {
  "base": "0,0,255"
}
```

### What is accepted (`theme.parse_base`)

| Accepted | Example |
| --- | --- |
| three whole numbers 0 to 255, separated by a comma, by spaces, or by both; spaces or tabs at the ends are ignored; leading zeros are fine | `"0,0,255"`, `"0, 0, 255"`, `"0 0 255"`, `"000,000,255"` |
| the same inside `rgb( )`, in any letter case | `"rgb(0, 0, 255)"` |
| six hex digits with their `#` | `"#0000FF"`, `"#0000ff"` |
| a JSON list of three whole numbers 0 to 255 | `[0, 0, 255]` |

Refused, each taking the default `0,0,255` with a note in the log, like any other bad setting:
a number over 255 or under 0; a decimal or an exponent (`"0.5,0,255"`, `[0, 0, 255.0]`); a
percentage; a color's name (`"blue"`); hex without `#` or with three digits; two or four numbers;
any other separator; a line break inside the text; digits of another script (use `[0-9]`:
Python's `\d` and `int()` accept them); `true` or `false` in a list; text over 32 characters;
any other JSON type. The canonical text, used everywhere after parsing, is `"r,g,b"` with no
spaces.

### How it reaches the page

Two paths, from one dictionary (`theme.derive(base)["tokens"]`, 13 names):

1. **First paint: `GET /theme.css`.** A route behind `READ` that answers
   `:root{--c-bg:#070A0F;...}` as `text/css; charset=utf-8` with `Cache-Control: no-store`.
   `index.html` links it right after `/style.css`. It blocks rendering like any stylesheet, so
   the page never shows one base and then another.
2. **A change while the page is open: the message.** `service.theme` in every message:
   `{"base": "0,0,255", "pale": 0.0, "accent": "base", "tokens": {"--c-bg": "#070A0F", ...}}`
   (`accent` is `"base"`, or `"look"` when the base has no color). When `base` differs from what
   the page last applied, the page sets each token on `document.documentElement` with
   `style.setProperty`. It applies a pair only if the name is one of its own 13 and the value
   matches `^#[0-9A-F]{6}$`; anything else in the block is ignored.

The stylesheet's own `:root` values become the tokens of `0,0,255`, so a page whose `/theme.css`
failed still looks like the default.

### How a change takes effect

**Live.** `Service._refresh_theme()` runs where `_refresh_plan()` runs (at most every
`PLAN_CHECK_SECONDS`, on a loop turn that happens anyway: no new wake-up). It does one `os.stat`
of `data/config.json` and compares the modification time and size with the last ones seen.

| What it finds | What happens |
| --- | --- |
| nothing changed | nothing |
| the file is gone | the default base; logged |
| the file cannot be opened, is over 1 MB, is not JSON or not an object | **the current base is kept**; logged once per such state. (An editor may be halfway through saving. After a restart such a file gives the defaults, as it does today.) |
| it parses, and `theme` is absent | the default base |
| it parses, and `theme.base` is accepted | that base |
| it parses, and `theme` or `theme.base` is refused | the default base, with the note |

A new base is derived (about 3 ms), logged (`theme base 0,255,0 (was 0,0,255)`), and sent with
the next message, which this turn asks for the way a plan change does. Only `theme` is taken from
a live read; every other setting still needs a restart, and the log line says so when another key
changed.

`run`, `start` and `replay` take `--base R,G,B`. A flag that `parse_base` refuses ends the
command with a usage error. With the flag, the file's `theme` is not read for that run. A replay
without the flag uses the default (its data folder is a temporary one).

`status` gains `theme`: `{"base", "from": "config.json" | "default" | "flag", "accent", "pale"}`,
and its text form one line, `Theme  0,0,255 (config.json)`.

## What changes, file by file

Stage A. Files not listed do not change.

| File | Change |
| --- | --- |
| `scdash/theme.py` (new) | The reference module above, as it is. |
| `scdash/config.py` | `DEFAULTS["theme"] = {"base": "0,0,255"}`. `_check` gets one special case, the key `theme.base`: accepted when `theme.parse_base(value)` is not None, and the stored value is the canonical text. |
| `scdash/service.py` | The theme held on the service (derived at start); `_refresh_theme()`; `theme` in `_service_block()` and in `status()`; the `/theme.css` route in `_register()`. |
| `scdash.py` | `--base` on `run`, `start`, `replay`; the `Theme` line of `status`. |
| `web/index.html` | `<link rel="stylesheet" href="/theme.css">` after the page's stylesheet. |
| `web/style.css` | (1) The 11 derived tokens of the `:root` color block take the values of `0,0,255`; `--c-term` and `--c-term-text` are added; the block's comment says where the values come from. (2) `.term`: `--fill: var(--c-term)` and `color: var(--c-term-text)`. (3) `.dg__img` becomes a masked box: `background-color: var(--c-text)` and `mask: var(--art) center / 100% 100% no-repeat` (with the `-webkit-` form beside it). (4) The opening comment's "One cyan for the instrument" becomes "one accent, taken from the base color". No selector is added or removed. |
| `web/app.js` | (1) `applyTheme(svc.theme)` in `render()`, as "How it reaches the page" says. (2) The diagram: `dg__img` is a `<div role="img">` with the same `aria-label` text the `alt` had, and `--art` set with `style.setProperty("--art", 'url("/rig/' + name + '")')`, only when `name` matches `^[a-z0-9_]{1,48}\.png$`. |
| `config.example.json` | The `_theme` and `theme` entries above. |
| `STATE.md`, `CLAUDE.md`, `README.md` (of `dashboard/`) | `service.theme` and `/theme.css`; the module in the map; the setting. |
| `tests/` | See "Tests". |

Easy to break:

- **Do not derive in the page.** One implementation, in Python, with the tests. The page only
  applies names and values it is sent.
- **Do not touch the status tokens or the failed-preflight literals.** A test pins them.
- **`0,0,255` in the stylesheet and `theme.derive((0, 0, 255))` must agree.** A test compares
  them, so change the stylesheet by running the module, not by hand.
- **The diagram image must still be requested only when its page is drawn** (a session that
  never opens the reference pays nothing: PLAN §4 item 18). A mask is fetched when its box is
  rendered, which keeps that, but `tests/test_page_rig.py` has to be made to look at the new
  element.
- **A failed mask draws nothing, not a white box.** Check it: point `--art` at a missing file
  and look.
- The mockup's `mock.css` shows the three stylesheet changes as overrides. It is a mockup:
  write them into `style.css` properly, do not copy its `::before` workaround.

## Stage B: the same setting on the desk panel (waits for the user's yes)

Recommended, as a second step after stage A is in use.

- A "Theme" part at the foot of the desk panel: a swatch of the base, the base's text in a
  one-line field, an Apply button, and one line saying what the service made of it ("Accent
  pale: this color is near the alarm red", "No color: the look's own cyan accent").
- `POST /api/theme` behind `CHANGE`, body `{"base": "0,255,0"}`. Refused text: 400, the answer
  naming the accepted forms. Accepted: the service writes `theme.base` into `data/config.json`
  and applies it at once.
- **Still one setting.** The panel writes the same key the file holds. There is no second store.
- **What it displaces:** today the service only reads `config.json` ("the user's, read only",
  `dashboard/CLAUDE.md`). Stage B makes one exception, with rules: read the whole file, change
  that one key, keep every other key and every `_` comment, write through the usual temporary
  file and rename, never through a link; a file that is not a JSON object is not written (409,
  with a message the toast shows); a missing file is created holding only `theme`.
- It needs its own design pass for the panel's layout in both orientations, and captures.

## Tests that must exist (stage A)

`tests/test_theme.py` (pure, no browser, under 10 s):

- `parse_base`: every row of the accepted table and every refused case named above.
- `derive`: the vector table, exactly; the equalities listed under it; the same input twice gives
  the same output.
- A sweep (every 2 degrees of the color wheel at saturations 1, 0.5, 0.2, 0.09, plus black,
  white, gray): every token is `#RRGGBB`; each pair of "The numbers, checked" is at or above its
  last column; the accent's distance from each status color is at or above its floor; no body
  token's luminance is more than 6 % from its figure; exactly the 13 names come back, and no
  status token among them.
- `theme.STATUS` equals the three status tokens of `web/style.css`.

`tests/test_page_static.py`:

- The 13 derived tokens in `style.css` equal `theme.derive((0, 0, 255))["tokens"]`.
- The fixed tokens and the five failed-preflight literals are in the file with the values of
  "What does not move".
- Outside the `:root` block the stylesheet holds no color literal but those five and the two
  shadows.
- `app.js` holds the 13 names once, as the list `applyTheme` checks against.

Settings and service (`test_service.py` or `test_wiring.py`, a temporary data folder as always):

- `load_settings`: each accepted form gives the canonical text; a refused one gives the default
  and a note.
- `/theme.css`: its guard, content type, `no-store`, and that its values equal
  `service.theme.tokens` of `/api/state`.
- Live: write `config.json` with a new base while an instance runs, and the next message
  carries it, with the log line. Then each row of the table in "How a change takes effect":
  gone, unreadable (kept), refused (default and note), absent (default).
- `--base`: used; the file is ignored for that run; a bad flag is a usage error.

Browser (`test_page_browser.py`, `test_page_rig.py`):

- With `--base 0,255,0`: before any message is handled, the computed `--c-accent` of
  `document.documentElement` is green's (the stylesheet path).
- After `config.json` changes under a running instance, the computed `--c-accent` changes with
  no reload.
- A message whose `theme.tokens` holds an unknown name, a value that is not `#RRGGBB`, or a
  name twice sets nothing it should not (inject one through the page's own render path).
- The diagram: the masked box has a mask image and the size of the art; the PNG is requested
  only once the reference page is drawn; the request is answered 200 (this is the **[verify]**
  about the guard).
- The existing 18-pixel and contrast-independent tests pass unchanged under `--base 255,0,0`.

## Done when

1. The suite passes, with the tests above in it.
2. `python dashboard/scdash.py status` prints the `Theme` line.
3. With an instance running on a temporary folder: changing `theme.base` in its `config.json`
   recolors the open page within a second or two, with no restart and no reload.
4. The Worker has captured the real page (not the mockup) at bases `0,0,255`, `0,255,0`,
   `255,0,0` and `255,255,255`, for Mining, Now, the rig reference with the Salvage filter and
   the failed preflight, in landscape and portrait, and has looked at every capture. They match
   the mockup's captures of the same screens.
5. Not part of done, and only the user can report it: how it looks on the side monitor beside
   the lit rig.

## How to attack it

- Feed `parse_base` and the live read hostile values: very long text, nested lists, `NaN`,
  numbers as text with signs, a 100 MB `config.json`, a `config.json` that is a folder or a link.
- Look for a base where a contrast or a distance floor fails: the sweep is every degree, not
  every color. Try low saturations just over 0.08 and hues at the edges of the pale rule.
- Check that the three status tokens cannot be reached: a message that names `--c-bad` must not
  change it.
- Kill the service's read of `config.json` halfway (hold the file open without sharing) and see
  that the page keeps its colors.
- Look at the failed-preflight screen and a red alert on a red base and on a green base. They
  must look as they do on blue.
- Measure the idle cost before and after (PLAN §9): one more `stat` on a turn that already runs.

## The user's decisions

| Question | Recommendation, first | What each option costs | Answer |
| --- | --- | --- | --- |
| The same setting on the desk panel, as a second step (stage B)? | **Yes.** Typing a color and seeing the page change is how the setting is used in MOZA Cockpit. | Yes: the service writes one key of `config.json`, which it only reads today; a panel part to design and capture. No: the color is changed in the file, by hand or by asking Claude; nothing else changes. | open |
| On a rig near a status color (green, red, orange, yellow), what is the accent? | **The rig's own hue, pale** (this design). The page stays one color family, and the accent cannot be read as a status. | Pale: on red, orange and yellow rigs the accent is close to the text color and emphasis is weaker. The other way, a strong accent in the look's cyan on those rigs: emphasis as strong as on blue, but a red or green page with cyan highlights, two colors where the request was for one. | open |

Decided by the design session, open to change:

| Decision | Why |
| --- | --- |
| The default is `0,0,255`, so the look as chosen on 2026-11-27 (ink-blue ground, cyan accent) is no longer the default: its cyan gives way to the rig's blue. The ground barely changes. | It is what the request asks for. No base gives the old pair exactly (they are two hues); a base with no color keeps the cyan on a gray ground. |
| Brightness of the base is ignored. | It is an LED's brightness, not a color. A dim LED is still a blue rig. |
| A base with no color keeps the look's cyan accent. | With a white accent, the highlighted buttons of the rig reference and every "now" mark would differ from text only by a little brightness. |
| The values are computed in the service, not in the page and not in CSS. | One implementation that the unit tests can sweep. A browser clips an out-of-range `oklch()` color in its own way, which would move luminance. |
| `/theme.css` for the first paint, the message for changes. | No flash of the default on a page opened with another base; no reload when the base changes. |

## Considered and turned down

- **Using the LED color itself as the accent.** `0,0,255` on the ground is 2.3:1. Unreadable.
- **Fixed lightness in HSL or OKLCH for every hue.** Equal lightness is not equal luminance:
  yellow and blue at the same lightness differ several times over in contrast. Luminance is what
  the contrast rule is written in, so the tokens are defined by it.
- **Turning the accent's hue away from a status color** (a red rig gets a magenta accent, a green
  rig a cyan one). The accent stays strong, but the page no longer shows the rig's color where it
  shows most. Kept as the second option of the user's question above.
- **A neutral white accent near a status color.** Then nothing but brightness separates an
  accented number from a plain one.
- **Moving the status colors away from the base instead.** They are the fixed points of the
  design (PLAN §11).
- **A second, deeper "lamp" tone for bars and lit meter cells**, closer to the LED. It needs a
  new token and a dozen selectors re-pointed, for a gain the blue captures did not show a need
  for.
- **Deriving in CSS with `oklch()` and relative colors.** No test can sweep it without a
  browser, and out-of-range colors are clipped, not fitted.
- **Reloading the page on a change.** It would drop the open desk panel and the rig reference's
  place.
- **A second store for the panel** (the `user` block of `state.json`). Two places for one
  setting, and a rule for which wins.

## Not part of this, worth knowing

- The taskbar icon (`scdash.ico`) is a file: it keeps its ink blue and cyan.
- The tracked mockup of the look (`../avionics/`) stays as the user chose it. It is the record of
  that choice, not the page.
- A suggestion, not designed here: give the rig reference's highlighted numbers a cue that is
  not a color (a thin ring), so the highlight is as clear on a red or yellow rig as on a blue
  one, and for anyone who does not see the hue. It would change the section in every base, so
  it is the user's call.
