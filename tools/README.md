# `tools/` — regeneration scripts

The PowerShell scripts that rebuild the generated parts of this repo: the **reference cards**
and the **keybind action catalogue**. Neither is needed to *use* the profile — only to
maintain it. Both are written to be **run from the project root** (one level up), not from
inside this folder.

## Files

| File | What it does |
| --- | --- |
| `regen_cards.ps1` | **Rebuilds the reference cards.** Takes the manufacturer art in [`../diagrams/`](../diagrams/) plus the binding tables embedded in the script, and writes all four files in [`../cards/`](../cards/) (`MOZA_MHG_AB6_ref.{png,svg}`, `MOZA_MTQ_ref.{png,svg}`). Recolors/crops the diagrams, composites them with the lookup table in SVG, and rasterizes to PNG via headless Chrome/Edge. Re-run after any binding change. |
| `refresh_keybinds_db.ps1` | **Regenerates the action catalogue.** Re-downloads the public [starbinder](https://starbinder.space/) keybind data, auto-detects the current SC version, and rewrites [`../reference/STARBINDER_KEYBINDS_DATABASE_v<version>.md`](../reference/), deleting the previous versioned snapshot. Run when a new SC patch ships. |

## Running

From the project root:

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\regen_cards.ps1           # rebuild the reference cards
powershell -ExecutionPolicy Bypass -File .\tools\refresh_keybinds_db.ps1   # refresh the action catalogue for a new patch
```

## Requirements & gotchas

- **`regen_cards.ps1`** needs Windows PowerShell with .NET `System.Drawing` and **Chrome or
  Edge** (auto-detected, used headless to rasterize SVG → PNG at 2×, ≈330 DPI).
- **`refresh_keybinds_db.ps1`** needs internet access (plain HTTPS GETs — no auth/API key).
  After it runs, update the version stamp referenced in [`../CLAUDE.md`](../CLAUDE.md) if it changed.
- **Cards are not auto-derived from [`../MOZA.xml`](../MOZA.xml).** The function text lives in
  hand-maintained tables inside `regen_cards.ps1`, so when you change a binding you must edit the
  matching row there too. The XML is the source of truth; the card tables are a view of it.

Full details, layout knobs, and the headless-render caveats are in
[`../CLAUDE.md` §7–8](../CLAUDE.md).
