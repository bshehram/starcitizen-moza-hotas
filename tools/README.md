# `tools/` — regeneration and validation scripts

The scripts that rebuild the generated parts of this repo — the **reference cards** and the
**keybind action catalogue** — and check the profile against the game. None is needed to *use*
the profile, only to maintain it. All are plain **Python 3**, so they run on Windows, macOS or
Linux, and all are written to be **run from the project root** (one level up), not from inside
this folder.

## Files

| File | What it does |
| --- | --- |
| `gamedata.py` | **Reads the game's own control definitions out of `Data.p4k`** (read-only, about a second). `check` pre-flights [`../MOZA.xml`](../MOZA.xml) against the installed build: unknown action names, actions in the wrong actionmap, and game-default joystick bindings the profile doesn't override. `catalogue` regenerates the action catalogue in [`../reference/`](../reference/README.md). Run both when a new SC patch ships. |
| `validate_actionmaps.py` | **Confirms the game accepted the profile.** Diffs [`../MOZA.xml`](../MOZA.xml) against the game's own normalized export (`…\Profiles\default\actionmaps.xml`) and flags any action the game files under a different map (`MISMATCH`) or drops outright (`NOT-IN-EXPORT`). Load the profile in-game first so the export is current. |
| `regen_cards.py` | **Rebuilds the reference cards.** Takes the manufacturer art in [`../diagrams/`](../diagrams/README.md) plus binding tables embedded in the script, crops and recolors the diagrams, composites them with the lookup table in SVG, and rasterizes to PNG with a headless Chrome, Edge or Chromium. Writes all four files in [`../cards/`](../cards/README.md). Re-run after any binding change. |
| `requirements.txt` | The Python packages the scripts need: Pillow, and zstandard on Python older than 3.14. |

## Running

From the project root:

```sh
python -m pip install -r tools/requirements.txt   # one-time setup
python tools/gamedata.py check                    # pre-flight MOZA.xml against the installed game build
python tools/gamedata.py catalogue                # regenerate the action catalogue for the installed build
python tools/validate_actionmaps.py               # after loading MOZA.xml in-game: did the game keep every binding?
python tools/regen_cards.py                       # rebuild the reference cards
```

(On a Mac, use `python3` if `python` isn't on your path.)

`gamedata.py check` and `validate_actionmaps.py` answer different questions. The first works
before you ever start the game and knows about **every** action in the build; the second is the
proof that the running game really kept each binding.

## Requirements

- **`gamedata.py`** needs a zstd decoder: Python 3.14+ has one built in, older Pythons get
  `zstandard` from `requirements.txt`. It needs no internet, but it does need the game: it reads
  `Data.p4k` from the install this repo sits in. Pass `--p4k <path>` for another one (e.g. PTU),
  or when running from a clone outside the game folder.
- **`validate_actionmaps.py`** needs nothing beyond Python — it reads two local XML files. Load
  `MOZA.xml` in-game first so the game's export reflects it; pass `--profile <path>` to point at
  a different export.
- **`regen_cards.py`** needs **Pillow** and **Chrome, Edge or Chromium** (found automatically on
  Windows, macOS and Linux; set `CARD_BROWSER=<path>` to choose one). The browser runs headless
  to rasterize SVG → PNG at 2×, ≈330 DPI. This is the one tool that works without the game, so
  cards can be rebuilt from a clone on any machine.

## Gotchas

- **Game-default joystick bindings stay live under a custom profile.** The game's stock layout
  binds a number of actions to "joystick button N", and those land on joystick 1 (`js1`) unless
  the profile rebinds or clears that action. `gamedata.py check` lists them as `GHOST`; the ones
  that share a button with something the profile binds fire **both** actions. Clear an unwanted
  one with `<rebind input="js1_ "/>`.
- **Cards are not auto-derived from [`../MOZA.xml`](../MOZA.xml).** The function text lives in
  hand-maintained tables inside `regen_cards.py`, so when I change a binding I edit the matching
  row there too. The XML is the source of truth; the card tables are a view of it.
- **Card fonts depend on the machine.** The cards ask for Segoe UI, then Arial. Rendered on a Mac
  they use Arial, which runs slightly wider, so check the PNG for clipped table text.
- **After a catalogue refresh**, the SC version may change; update the version stamp where the
  repo records it.
