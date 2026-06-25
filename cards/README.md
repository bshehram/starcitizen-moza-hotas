# `cards/` — printable button-reference cheat sheets

Generated cheat sheets that map every physical control to its in-game function, one card per
game device. I print these and keep them next to the rig. Each card is sized to fill a **US-Letter
sheet in landscape** (11×8.5): the manufacturer diagram, split into its sub-views and stacked,
fills the left ~60%, beside a **button# → function** lookup table on the right ~40%.

These are **generated artifacts**, not hand-drawn. Rebuild them with the card generator in
[`../tools/`](../tools/README.md); the button-number art comes from [`../diagrams/`](../diagrams/README.md).

## Files

| File | What it is |
| --- | --- |
| `MOZA_MHG_AB6_ref.png` | **`js1` card (raster).** MHG grip (1–29) **+** AB6 base (49–62) combined, with the grip-front / grip-side / base sub-views stacked beside the lookup table. This is the one embedded in the root [README](../README.md), and the one to print. |
| `MOZA_MHG_AB6_ref.svg` | **`js1` card (editable source).** Self-contained vector source for the PNG above — each recolored sub-view is embedded as a base64 PNG, so there are no sidecar files. The PNG is rasterized from this at 2× (≈330 DPI) by headless Chrome/Edge. |
| `MOZA_MTQ_ref.png` | **`js2` card (raster).** MTQ throttle panel (1–65) plus axes, with the Right Module / Left Module / throttle-panel sub-views stacked beside the lookup table. |
| `MOZA_MTQ_ref.svg` | **`js2` card (editable source).** Self-contained vector source for the MTQ PNG, same build pipeline as above. |

## What each card stacks

| Card | Device | Top band (two views side by side) | Bottom band (one big view) |
| --- | --- | --- | --- |
| `MOZA_MHG_AB6_ref` | `js1` — grip 1–29 + base 49–62 | MHG grip front · MHG grip side | AB6 base |
| `MOZA_MTQ_ref` | `js2` — throttle 1–65 + axes | Right Module · Left Module | Throttle panel |

## Printing

Print at **"Fit to page" / 100%, landscape**. The image is already the page aspect ratio
(1.294), so it fills the sheet with no cropping.

## Editing & regenerating

- **Don't hand-edit the PNGs.** Re-run the card generator (see [`../tools/`](../tools/README.md))
  and it overwrites all four files in this folder.
- The **button numbers and leader lines come from the manufacturer art** in
  [`../diagrams/`](../diagrams/README.md) and are never placed by hand — the generator only
  recolors and crops that art.
- The **function text** lives in binding tables inside the generator script, **not** here and
  **not** auto-derived from [`../MOZA.xml`](../MOZA.xml). The XML is the source of truth; the card
  tables are a hand-maintained view of it, so when I change a binding I update both. Details in
  [`../tools/`](../tools/README.md).
