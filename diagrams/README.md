# `diagrams/` — manufacturer button-number maps (source art)

The **MOZA configurator's own button-number diagrams** for each device. These are the
authoritative map from a **physical control → its button index**, and every binding in
[`../MOZA.xml`](../MOZA.xml) is numbered against them.

> **⚠ Do not delete or rename these.** They are the **source layer** for the printable
> reference cards in [`../cards/`](../cards/) — [`../tools/regen_cards.ps1`](../tools/regen_cards.ps1)
> recolors and crops these PNGs to build the cards. Remove them and the cards can't be regenerated.

## Files

| File | Device | What it shows |
| --- | --- | --- |
| `MOZA_MHG.png` | MHG grip (part of `js1`) | The flight-stick **grip**: trigger, thumb buttons, hats, and coolie — buttons **1–29**. |
| `MOZA_AB6.png` | AB6 FFB base (part of `js1`) | The **base**: wing pushbuttons and the two mixed-mode levers — buttons **49–62**. (Grip + base report as one DirectInput device, `js1`.) |
| `MOZA_MTQ.png` | MTQ Throttle Panel (`js2`) | The **throttle quadrant**: keypad, encoders, mode knob, toggles, side sliders, and the two modules — buttons **1–65** plus the axes. |

## Notes

- **Provenance / license:** these are **MOZA's own art**, included here as reference only. They
  are **not** covered by this repo's MIT license and remain MOZA's property — see
  [License & provenance](../README.md#license--provenance) in the root README.
- **If MOZA ships new device art** with a different layout, replace the relevant PNG here and
  re-verify the crop rectangles (`x0,y0,x1,y1`) at the top of
  [`../tools/regen_cards.ps1`](../tools/regen_cards.ps1), then rebuild the cards.
- The full physical-control → button-index tables are written out in
  [`../CLAUDE.md` §3](../CLAUDE.md).
