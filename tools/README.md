# `tools/` — regeneration scripts

The PowerShell scripts that rebuild the generated parts of this repo: the **reference cards** and
the **keybind action catalogue**. Neither is needed to *use* the profile — only to maintain it.
Both are written to be **run from the project root** (one level up), not from inside this folder.

## Files

| File | What it does |
| --- | --- |
| `regen_cards.ps1` | **Rebuilds the reference cards.** Takes the manufacturer art in [`../diagrams/`](../diagrams/README.md) plus binding tables embedded in the script, recolors/crops the diagrams, composites them with the lookup table in SVG, and rasterizes to PNG via headless Chrome/Edge. Writes all four files in [`../cards/`](../cards/README.md). Re-run after any binding change. |
| `refresh_keybinds_db.ps1` | **Regenerates the action catalogue.** Re-downloads the public [starbinder](https://starbinder.space/) keybind data, auto-detects the current SC version, and rewrites the versioned catalogue in [`../reference/`](../reference/README.md), deleting the previous snapshot. Run when a new SC patch ships. |
| `validate_actionmaps.ps1` | **Checks every binding is in the right actionmap.** Diffs [`../MOZA.xml`](../MOZA.xml) against the game's own normalized export (`…\Profiles\default\actionmaps.xml`) and flags any action the game files under a different map (`MISMATCH`) or drops outright (`NOT-IN-EXPORT`). Load the profile in-game first so the export is current. (The action catalogue groups actions by *category*, which is **not** the actionmap, so it can't answer this.) |

## Running

From the project root:

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\regen_cards.ps1           # rebuild the reference cards
powershell -ExecutionPolicy Bypass -File .\tools\refresh_keybinds_db.ps1   # refresh the action catalogue for a new patch
powershell -ExecutionPolicy Bypass -File .\tools\validate_actionmaps.ps1   # check every binding is in the right actionmap (load MOZA.xml in-game first)
```

## Requirements

- **`regen_cards.ps1`** needs Windows PowerShell with .NET `System.Drawing` and **Chrome or
  Edge** (auto-detected, used headless to rasterize SVG → PNG at 2×, ≈330 DPI).
- **`refresh_keybinds_db.ps1`** needs internet access — plain HTTPS GETs, no auth or API key.
- **`validate_actionmaps.ps1`** needs only Windows PowerShell — it reads two local XML files (no
  internet, no extra deps). Load `MOZA.xml` in-game first so the game's export reflects it; pass
  `-Profile <path>` to point at a different export.

## Gotchas

- **Cards are not auto-derived from [`../MOZA.xml`](../MOZA.xml).** The function text lives in
  hand-maintained tables inside `regen_cards.ps1`, so when I change a binding I edit the matching
  row there too. The XML is the source of truth; the card tables are a view of it.
- **`regen_cards.ps1` renders from a path with spaces while Chrome may be open.** It works around
  this by rendering to a space-free temp path (then moving the file into [`../cards/`](../cards/README.md)),
  passing the SVG as a `%20`-encoded URI, and using an isolated `--user-data-dir`. The headless
  Chrome call writes a "bytes written" line to stderr that has to be redirected so it isn't
  mistaken for a failure.
- **`regen_cards.ps1` stays pure ASCII** (the one `·` separator is injected by code-point), and
  SVGs are written UTF-8 without BOM, so the script can't be corrupted by encoding mismatches.
- **After a catalogue refresh**, the SC version may change; update the version stamp where the
  repo records it.
