# `reference/` — bulk reference material

Background reference that the binding work is checked against: the full catalogue of every
bindable Star Citizen action, and a standalone printable sheet of this profile's bindings.
Neither file is needed to *use* the profile; they're for understanding and maintaining it.

## Files

| File | What it is |
| --- | --- |
| `SC_KEYBINDS_DATABASE_v4.10.md` | **Master action catalogue.** Every action the game build defines (1,104 entries across 50 actionmaps), grouped by its **actionmap**, with the official in-game label, description, and the game's default keyboard / joystick / gamepad bindings. Generated from the game's own `defaultProfile.xml` and English `global.ini` inside `Data.p4k`. **Patch-versioned** — the `v4.10` in the name is the SC version it was read from. I use this to verify that the action names (`v_*`) in [`../MOZA.xml`](../MOZA.xml) are real, labelled correctly, and bound under the right actionmap. |
| `MOZA_BINDINGS.html` | **Self-contained printable binding sheet.** A single-file HTML page (inline CSS, no assets) listing this profile's bindings organized **by device**, with color-coded tags for combat / mining / salvage / utility. Open it in any browser and print to US-Letter. A text companion to the visual cards in [`../cards/`](../cards/README.md). |

> **The catalogue answers the actionmap question.** Each section heading is an actionmap name —
> the value that goes in `<actionmap name="…">`. An action bound under any other actionmap is
> silently dropped by the game. The scripts that check this for the whole profile live in
> [`../tools/`](../tools/README.md).

## Refreshing the catalogue

The catalogue is specific to an SC patch, so I regenerate it when a new version ships. The
generator (see [`../tools/`](../tools/README.md)) reads the two source files directly from the
installed game's `Data.p4k`, writes `SC_KEYBINDS_DATABASE_v<version>.md`, and deletes the
previous snapshot. No download is involved, so the catalogue always matches the build that is
actually installed.

Earlier versions of this catalogue (up to Alpha 4.8) came from the public starbinder keybind
database. That site's domain registration had expired by November 2026, which is why the
catalogue is now built from the game files instead.

## Provenance / license

The catalogue is **derived from Star Citizen's game data** (action names, labels and default
bindings are Cloud Imperium Games') and is **not** covered by this repo's MIT license — see
[License & provenance](../README.md#license--provenance) in the root README. The
`MOZA_BINDINGS.html` sheet is my own original work.
