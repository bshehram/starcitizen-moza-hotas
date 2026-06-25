# `cards/` — printable button-reference cheat sheets

Generated **cheat sheets** that map every physical control to its in-game function, one
card per game device. Sized to fill a **US-Letter sheet in landscape** (11×8.5): print at
"Fit to page" / 100%, landscape, and the image fills the page. Each card is a 60/40 split —
the manufacturer diagram (split into its sub-views and stacked) on the left, a
**button# → function** lookup table on the right.

These are **generated artifacts**, not hand-drawn. Rebuild them with
[`../tools/regen_cards.ps1`](../tools/regen_cards.ps1); see
[`../CLAUDE.md` §8](../CLAUDE.md) for the full how-to.

## Files

| File | What it is |
| --- | --- |
| `MOZA_MHG_AB6_ref.png` | **`js1` card (raster).** MHG grip (1–29) **+** AB6 base (49–62) combined, with grip-front / grip-side / base sub-views stacked beside the lookup table. Embedded in the root [README](../README.md) and meant for printing. |
| `MOZA_MHG_AB6_ref.svg` | **`js1` card (editable source).** Self-contained vector source for the PNG above — each recolored sub-view is embedded as a base64 PNG, so no sidecar files are needed. The PNG is rasterized from this at 2× (≈330 DPI) via headless Chrome/Edge. |
| `MOZA_MTQ_ref.png` | **`js2` card (raster).** MTQ throttle panel (1–65) plus axes, with the Right Module / Left Module / throttle-panel sub-views stacked beside the lookup table. |
| `MOZA_MTQ_ref.svg` | **`js2` card (editable source).** Self-contained vector source for the MTQ PNG, same build pipeline as above. |

## Editing & regenerating

- **Don't hand-edit the PNGs.** Re-run [`../tools/regen_cards.ps1`](../tools/regen_cards.ps1)
  from the project root and it overwrites all four files.
- The **button numbers/leader lines come from the manufacturer art** in
  [`../diagrams/`](../diagrams/) and are never placed by hand — the script only recolors and
  crops that art.
- The **function text** lives in the binding tables inside `regen_cards.ps1`, **not** here and
  **not** auto-derived from [`../MOZA.xml`](../MOZA.xml). When you change a binding you must
  update the matching row in that script too (see [`../CLAUDE.md` §8.3](../CLAUDE.md)) — the
  XML is the source of truth, the card tables are a hand-maintained view of it.
