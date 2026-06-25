# `reference/` — bulk reference material

Background reference that the binding work is checked against — the **full catalogue of every
bindable Star Citizen action**, and a **standalone printable sheet** of this profile's bindings.
Neither file is needed to *use* the profile; they're for understanding and maintaining it.

## Files

| File | What it is |
| --- | --- |
| `STARBINDER_KEYBINDS_DATABASE_v4.8.md` | **Master action catalogue.** Every bindable SC action that *exists* (≈714 of them) with its official in-game label and description, grouped by category. Sourced from the public [starbinder](https://starbinder.space/) keybind database. **Patch-versioned** — the `v4.8` in the name is the SC version it was captured from. This is the lookup used to verify that action names (`v_*`) in [`../MOZA.xml`](../MOZA.xml) are real and labelled correctly. |
| `MOZA_BINDINGS.html` | **Self-contained printable binding sheet.** A single-file HTML page (inline CSS, no assets) listing this profile's bindings organized **by device**, with color-coded tags for combat / mining / salvage / utility. Open it in any browser and print to US-Letter. A human-readable companion to the visual cards in [`../cards/`](../cards/). |

## Maintenance

- **Refreshing the catalogue:** it's specific to an SC patch, so regenerate it when a new
  version ships. Run [`../tools/refresh_keybinds_db.ps1`](../tools/refresh_keybinds_db.ps1) from
  the project root — it auto-detects the version, re-downloads the data, writes
  `STARBINDER_KEYBINDS_DATABASE_v<version>.md`, and deletes the previous snapshot. Then bump the
  version stamp referenced in [`../CLAUDE.md`](../CLAUDE.md). Full recipe in
  [`../CLAUDE.md` §7](../CLAUDE.md).
- **Provenance / license:** the catalogue is **derived from third-party data** (the starbinder
  database and the [Star Citizen wiki](https://starcitizen.tools/)) and is **not** covered by
  this repo's MIT license — see [License & provenance](../README.md#license--provenance). The
  `MOZA_BINDINGS.html` sheet is original work authored for this repo.
