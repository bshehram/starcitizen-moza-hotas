# `tools/` — regeneration and validation scripts

The scripts that rebuild the generated parts of this repo — the **reference cards** and the
**keybind action catalogue** — and check the profile against the game. None is needed to *use*
the profile, only to maintain it. All are written to be **run from the project root** (one level
up), not from inside this folder.

## Files

| File | What it does |
| --- | --- |
| `gamedata.py` | **Reads the game's own control definitions out of `Data.p4k`** (read-only, about a second). `check` pre-flights [`../MOZA.xml`](../MOZA.xml) against the installed build: unknown action names, actions in the wrong actionmap, and game-default joystick bindings the profile doesn't override. `catalogue` regenerates the action catalogue in [`../reference/`](../reference/README.md). Run both when a new SC patch ships. |
| `validate_actionmaps.ps1` | **Confirms the game accepted the profile.** Diffs [`../MOZA.xml`](../MOZA.xml) against the game's own normalized export (`…\Profiles\default\actionmaps.xml`) and flags any action the game files under a different map (`MISMATCH`) or drops outright (`NOT-IN-EXPORT`). Load the profile in-game first so the export is current. |
| `regen_cards.ps1` | **Rebuilds the reference cards.** Takes the manufacturer art in [`../diagrams/`](../diagrams/README.md) plus binding tables embedded in the script, recolors/crops the diagrams, composites them with the lookup table in SVG, and rasterizes to PNG via headless Chrome/Edge. Writes all four files in [`../cards/`](../cards/README.md). Re-run after any binding change. |

## Running

From the project root:

```powershell
python tools\gamedata.py check                                             # pre-flight MOZA.xml against the installed game build
python tools\gamedata.py catalogue                                         # regenerate the action catalogue for the installed build
powershell -ExecutionPolicy Bypass -File .\tools\validate_actionmaps.ps1   # after loading MOZA.xml in-game: did the game keep every binding?
powershell -ExecutionPolicy Bypass -File .\tools\regen_cards.ps1           # rebuild the reference cards
```

`gamedata.py check` and `validate_actionmaps.ps1` answer different questions. The first works
before you ever start the game and knows about **every** action in the build; the second is the
proof that the running game really kept each binding.

## Requirements

- **`gamedata.py`** needs **Python 3** and a zstd decoder: Python 3.14+ has one built in; on
  older Pythons run `python -m pip install zstandard` once. It needs no internet — it reads
  `Data.p4k` from this install (pass `--p4k <path>` for another one, e.g. PTU).
- **`validate_actionmaps.ps1`** needs only Windows PowerShell — it reads two local XML files (no
  internet, no extra deps). Load `MOZA.xml` in-game first so the game's export reflects it; pass
  `-Profile <path>` to point at a different export.
- **`regen_cards.ps1`** needs Windows PowerShell with .NET `System.Drawing` and **Chrome or
  Edge** (auto-detected, used headless to rasterize SVG → PNG at 2×, ≈330 DPI).

## Gotchas

- **Game-default joystick bindings stay live under a custom profile.** The game's stock layout
  binds a number of actions to "joystick button N", and those land on joystick 1 (`js1`) unless
  the profile rebinds or clears that action. `gamedata.py check` lists them as `GHOST`; the ones
  that share a button with something the profile binds fire **both** actions. Clear an unwanted
  one with `<rebind input="js1_ "/>`.
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
