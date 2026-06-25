# `diagrams/` — manufacturer button-number maps + button-index tables

The MOZA configurator's own button-number diagrams for each device. These are the authoritative
map from a physical control to its button index, and every binding in
[`../MOZA.xml`](../MOZA.xml) is numbered against them. This README also carries the full
button-index tables in text, so you can look up a number without opening the images.

> **⚠ Do not delete or rename the PNGs.** They are the source layer for the printable reference
> cards in [`../cards/`](../cards/README.md): the card generator recolors and crops these images
> to build the cards. Remove them and the cards can't be regenerated.

## Files

| File | Device | What it shows |
| --- | --- | --- |
| `MOZA_MHG.png` | MHG grip (part of `js1`) | The flight-stick grip: trigger, thumb buttons, hats, and coolie. Buttons **1–29**. |
| `MOZA_AB6.png` | AB6 FFB base (part of `js1`) | The base: wing pushbuttons and the two mixed-mode levers. Buttons **49–62**. (Grip + base report as one DirectInput device, `js1`.) |
| `MOZA_MTQ.png` | MTQ Throttle Panel (`js2`) | The throttle quadrant: keypad, encoders, mode knob, toggles, side sliders, and the two modules. Buttons **1–65** plus the axes. |

---

## `js1` — MHG grip (1–29)

| # | Physical control | # | Physical control |
| --- | --- | --- | --- |
| 1 | Main index **trigger** (blade) | 16 | Right hat, center press |
| 2 | Top-left face thumb button | 17 | Lower/front thumb hat, up |
| 3 | Lower side button (pinky side) | 18 | Lower hat, right |
| 4 | Upper thumb button | 19 | Lower hat, down |
| 5 | Lower-center face thumb button | 20 | Lower hat, left |
| 6 | Trigger **second stage** (front of trigger) | 21 | Lower hat, center press |
| 7 | Left thumb hat, up | 22 | Upper thumb **rocker, up** |
| 8 | Left thumb hat, right | 23 | Upper rocker, down |
| 9 | Left thumb hat, down | 24 | Upper rocker, center |
| 10 | Left thumb hat, left | 25 | Top coolie/POV hat, up |
| 11 | Left thumb hat, center press | 26 | Top coolie hat, right |
| 12 | Right hat, up | 27 | Top coolie hat, down |
| 13 | Right hat, right | 28 | Top coolie hat, left |
| 14 | Right hat, down | 29 | Top coolie hat, center press |
| 15 | Right hat, left | | |

## `js1` — AB6 base (49–62)

| # | Physical control | # | Physical control |
| --- | --- | --- | --- |
| 49 | Left wing button 1 (top) | 56 | Right wing button 4 (bottom) |
| 50 | Left wing button 2 | 57 | Left **"Slider"** lever, top |
| 51 | Left wing button 3 | 58 | Left "Slider" lever, middle |
| 52 | Left wing button 4 (bottom) | 59 | Left "Slider" lever, bottom |
| 53 | Right wing button 1 (top) | 60 | Right **"Dial"** lever, top |
| 54 | Right wing button 2 | 61 | Right "Dial" lever, middle |
| 55 | Right wing button 3 | 62 | Right "Dial" lever, bottom |

Wing buttons (49–56) are plain momentary pushbuttons: 49–52 = **left** wing, 53–56 = **right**
wing. The left **"Slider"** (57–59) and right **"Dial"** (60–62) are mixed-mode levers: each
emits both its 3 detent buttons *and* a continuous analog axis (`js1_slider1` / `js1_slider2`).
Both are maintained (they stay where you leave them) and are currently **unbound** in this combat
profile.

## `js2` — MTQ throttle (1–65)

| # | Physical control | # | Physical control |
| --- | --- | --- | --- |
| 1 | Keypad **A1** | 25 | Lower-strip **toggle A**, up |
| 2 | Keypad **A2** | 26 | Lower-strip **toggle A**, down |
| 3 | Keypad **A3** | 27 | Lower-strip **toggle B**, up |
| 4 | Keypad **A4** | 28 | Lower-strip **toggle B**, down |
| 5 | Keypad **"NAV"** | 29 | Lower-strip **toggle C** (gear lever), up |
| 6 | Keypad **"HDG"** | 30 | Lower-strip **toggle C** (gear lever), down |
| 7 | Keypad **"SPD"** | 36–40 | **FLAPS slider** (mixed buttons+axis): 40 rest "0" … 36 "FULL" |
| 8 | Keypad **"ALT"** | 31 / 43 | **SPEEDBRAKE slider** (mixed buttons+axis): 43 rest "DOWN", 31 "ARMED" |
| 9 | Keypad **"FD"** | 34 | Main-throttle reverse detent |
| 10 | Keypad **"AP"** | 49/50/51 | Right Module **3-pos switch**: 49 rest, 50 latched-fwd, 51 momentary-back |
| 11 | Upper encoder, CCW/left | 52–56 | Right Module **"WPN" hat**: 56↑ 55↓ 53→ 54← 52=press |
| 12 | Upper encoder, CW/right | 57–61 | Right Module **"COM" hat**: 61↑ 60↓ 58→ 59← 57=press |
| 13 | Upper encoder, center press | 62 | Left Module **mini-stick press** (axes `js2_x`/`js2_y`) |
| 14 | Lower encoder, CCW/left | 63 | **Throttle-lever dial**, fwd/CW click (encoder) |
| 15 | Lower encoder, CW/right | 64 | **Throttle-lever dial**, back/CCW click (encoder) |
| 16 | Lower encoder, center press | 65 | Left Module face button |
| 17–21 | **Rotary mode-selector knob**, detents 1–5 (17 = full CCW … 21 = full CW) | 22/23/24 | 3-position rocker (23 L / 22 C / 24 R) |

**Axes:** the throttle is a synced pair reporting as **X Rotation + Y Rotation**
(`js2_rotx` + `js2_roty`); it's bound on `js2_roty`. The Left Module mini-stick = `js2_x` /
`js2_y` drives camera look. The two side sliders are slider-family axes: **FLAPS** = `js2_slider2`
and **SPEEDBRAKE** = `js2_slider1`. Buttons **44–48** are absent on the MTQ, so don't bind to them.

---

## Notes

- **Provenance / license:** these PNGs are MOZA's own art, included as reference only. They are
  **not** covered by this repo's MIT license and remain MOZA's property — see
  [License & provenance](../README.md#license--provenance) in the root README.
- **If MOZA ships new device art** with a different layout, replace the relevant PNG here, then
  re-verify the crop rectangles in the card generator and rebuild the cards. See
  [`../tools/`](../tools/README.md).
- The button numbers and leader lines are baked into these images, so the cards in
  [`../cards/`](../cards/README.md) never place a number by hand.
