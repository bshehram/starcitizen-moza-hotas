# `reference/` — bulk reference material

Background reference that the binding work is checked against: the full catalogue of every
bindable Star Citizen action, and a standalone printable sheet of this profile's bindings.
Neither file is needed to *use* the profile; they're for understanding and maintaining it.

## Files

| File | What it is |
| --- | --- |
| `STARBINDER_KEYBINDS_DATABASE_v4.8.md` | **Master action catalogue.** Every bindable SC action that *exists* (≈714 of them) with its official in-game label and description, grouped by category. Sourced from the public [starbinder](https://starbinder.space/) keybind database. **Patch-versioned** — the `v4.8` in the name is the SC version it was captured from. I use this to verify that the action names (`v_*`) in [`../MOZA.xml`](../MOZA.xml) are real and labelled correctly. |
| `MOZA_BINDINGS.html` | **Self-contained printable binding sheet.** A single-file HTML page (inline CSS, no assets) listing this profile's bindings organized **by device**, with color-coded tags for combat / mining / salvage / utility. Open it in any browser and print to US-Letter. A text companion to the visual cards in [`../cards/`](../cards/README.md). |

## Refreshing the catalogue

The catalogue is specific to an SC patch, so I regenerate it when a new version ships. The
refresh script (see [`../tools/`](../tools/README.md)) auto-detects the version, re-downloads the
data, writes `STARBINDER_KEYBINDS_DATABASE_v<version>.md`, and deletes the previous snapshot.

How it works, in short: starbinder is a static client-side app whose search box indexes plain
JSON the page fetches. The script reads the **`UPDATED FOR <x.y>`** banner for the version, pulls
`keybinds.json` (the master DB, keyed by action name) and `localisation.json` (resolves
`@ui_*` description references), groups actions by their first keyword, and renders one Markdown
table per category. The data files are plain HTTPS GETs — no auth, no API key.

## Provenance / license

The catalogue is **derived from third-party data** (the starbinder database and the
[Star Citizen wiki](https://starcitizen.tools/)) and is **not** covered by this repo's MIT
license — see [License & provenance](../README.md#license--provenance) in the root README. The
`MOZA_BINDINGS.html` sheet is my own original work.
