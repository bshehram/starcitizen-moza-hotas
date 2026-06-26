# `tools/` — working notes for Claude

The two PowerShell regeneration scripts. The human-facing usage, requirements, and gotchas are in
[`README.md`](README.md); this file is the working guidance for editing or running them.

## What you need to know

- **Run both from the project root**, not from inside `tools/` — the paths inside assume the root
  as the working directory.
- **`regen_cards.ps1` rebuilds [`../cards/`](../cards/CLAUDE.md)** from the art in
  [`../diagrams/`](../diagrams/CLAUDE.md) plus binding tables embedded in the script. Key rules:
  - The cards are **not auto-derived from [`../MOZA.xml`](../MOZA.xml)**. When a binding changes,
    edit the matching row in this script *and* the XML, then re-run. See [`../CLAUDE.md` §8.3](../CLAUDE.md).
  - Keep the script **pure ASCII** (the one `·` separator is injected by code-point), and keep
    SVG output UTF-8 without BOM.
  - The headless-Chrome render has several traps (paths with spaces, stderr "bytes written"
    escalating to an error, `--window-size` tokenization). They're already worked around — read
    [`../CLAUDE.md` §8.4](../CLAUDE.md) before touching that code.
- **`refresh_keybinds_db.ps1` rebuilds the catalogue in [`../reference/`](../reference/CLAUDE.md)**
  by re-downloading starbinder data. After it runs, update the version stamp in
  [`../CLAUDE.md`](../CLAUDE.md). Full recipe and data-file URLs in [`../CLAUDE.md` §7](../CLAUDE.md).
- **`validate_actionmaps.ps1` checks actionmap placement.** It diffs [`../MOZA.xml`](../MOZA.xml)
  against the game's normalized export (`…\Profiles\default\actionmaps.xml`). The game **drops**
  wrong-map actions, so a `MISMATCH` — or an unexplained `NOT-IN-EXPORT` on a non-default action —
  means a binding is in the wrong actionmap. Reads local files only (no internet). Why this is the
  authoritative local source, and the load-then-check workflow, are in [`../CLAUDE.md` §10](../CLAUDE.md).
  Note the catalogue's keyword *category* is **not** the actionmap — don't infer one from the other.

## Where the detail lives

- Card generator internals and layout knobs: [`../CLAUDE.md` §8](../CLAUDE.md).
- Catalogue refresh recipe: [`../CLAUDE.md` §7](../CLAUDE.md).
