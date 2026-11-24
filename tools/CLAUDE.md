# `tools/` — working notes for Claude

The regeneration and validation scripts. The human-facing usage, requirements, and gotchas are in
[`README.md`](README.md); this file is the working guidance for editing or running them.

## What you need to know

- **Run everything from the project root**, not from inside `tools/` — the PowerShell scripts
  assume the root as the working directory.
- **`gamedata.py` is the ground-truth reader.** It pulls `Data\Libs\Config\defaultProfile.xml`
  and the English `global.ini` straight out of `Data.p4k` (read-only, ~1 s) — the game's own list
  of every action, its **actionmap**, and its default bindings for the build that is installed.
  - `python tools/gamedata.py check` — run this **first** after any edit to
    [`../MOZA.xml`](../MOZA.xml) and after every game patch. `UNKNOWN` = the action name no longer
    exists; `WRONG-MAP` = the game will silently drop it; `GHOST` = a stock joystick binding
    (they land on `js1`) the profile neither rebinds nor clears. A ghost on an input the profile
    also uses double-fires wherever both maps are active — judge each one by whether the two
    contexts can be live together; many (spectator, menus, turret aim) are harmless or wanted.
  - `python tools/gamedata.py catalogue` — rewrites the catalogue in
    [`../reference/`](../reference/CLAUDE.md) and removes the previous snapshot. After it runs,
    update the version stamp in [`../CLAUDE.md`](../CLAUDE.md).
  - Needs Python 3 plus `zstandard` (or Python 3.14+, which has zstd built in). The system Python
    on this machine did not have `zstandard` when the tool was written — if the import fails, ask
    before installing into the user's Python, or run it from a scratch venv. (On 2026-11-23 it was
    installed with `python -m pip install --user zstandard` into the system Python 3.12, so `check`
    now runs there directly.)
  - It reads only plain-zstd entries. If CIG ever encrypts those two files it exits with a clear
    message; a community extractor such as unp4k is the fallback (see [`../CLAUDE.md` §10](../CLAUDE.md)).
- **`validate_actionmaps.ps1` is the post-load proof.** It diffs [`../MOZA.xml`](../MOZA.xml)
  against the game's normalized export (`…\Profiles\default\actionmaps.xml`). The game **drops**
  wrong-map actions, so a `MISMATCH` — or an unexplained `NOT-IN-EXPORT` on a non-default action —
  means the running game did not keep a binding. Reads local files only. It can only be as fresh
  as the last time the profile was loaded in-game, so check the export's timestamp.
- **`regen_cards.ps1` rebuilds [`../cards/`](../cards/CLAUDE.md)** from the art in
  [`../diagrams/`](../diagrams/CLAUDE.md) plus binding tables embedded in the script. Key rules:
  - The cards are **not auto-derived from [`../MOZA.xml`](../MOZA.xml)**. When a binding changes,
    edit the matching row in this script *and* the XML, then re-run. See [`../CLAUDE.md` §8.3](../CLAUDE.md).
  - Keep the script **pure ASCII** (the one `·` separator is injected by code-point), and keep
    SVG output UTF-8 without BOM.
  - The headless-Chrome render has several traps (paths with spaces, stderr "bytes written"
    escalating to an error, `--window-size` tokenization). They're already worked around — read
    [`../CLAUDE.md` §8.4](../CLAUDE.md) before touching that code.

## Where the detail lives

- Card generator internals and layout knobs: [`../CLAUDE.md` §8](../CLAUDE.md).
- Catalogue refresh and why the source changed from starbinder to the game files: [`../CLAUDE.md` §7](../CLAUDE.md).
- Actionmap correctness and the two-step check workflow: [`../CLAUDE.md` §10](../CLAUDE.md).
