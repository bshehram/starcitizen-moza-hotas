# `tools/` — working notes for Claude

The regeneration and validation scripts. The human-facing usage, requirements, and gotchas are in
[`README.md`](README.md); this file is the working guidance for editing or running them.

## What you need to know

- **All tooling is Python 3, cross-platform.** The user wants the repo workable from a Mac too, so
  the PowerShell scripts were ported to Python on 2026-11-23 and deleted. Keep it that way: no
  new `.ps1`, no Windows-only APIs, `pathlib` for paths, argument lists (not shell strings) for
  subprocesses. Dependencies go in [`requirements.txt`](requirements.txt).
- **Run everything from the project root**, not from inside `tools/`. The scripts locate the repo
  from their own path, but the docs and commands assume the root.
- **`gamedata.py` is the ground-truth reader.** It pulls `Data\Libs\Config\defaultProfile.xml`
  and the English `global.ini` straight out of `Data.p4k` (read-only, ~1 s) — the game's own list
  of every action, its **actionmap**, and its default bindings for the build that is installed.
  - `python tools/gamedata.py check` — run this **first** after any edit to
    [`../MOZA.xml`](../MOZA.xml) and after every game patch. `UNKNOWN` = the action name no longer
    exists; `WRONG-MAP` = the game will silently drop it; `MULTI-BIND` = the action has more
    than one `<rebind>`, and the game keeps only the last (added 2026-11-26 after a second rebind
    silently replaced the throttle's reverse axis and Autoland); `STRAY-PROFILE` = another
    control-profile `.xml` somewhere under the mappings folder, which the game lists in its
    profile menu as a second "MOZA (1)" (added 2026-11-28 after a session's before-copy did
    exactly that; printed only when one is found, dot-folders skipped); `GHOST` = a stock joystick binding
    (they land on `js1`) the profile neither rebinds nor clears. A ghost on an input the profile
    also uses double-fires wherever both maps are active — judge each one by whether the two
    contexts can be live together; many (spectator, menus, turret aim) are harmless or wanted.
  - `python tools/gamedata.py catalog` — rewrites the catalog in
    [`../reference/`](../reference/CLAUDE.md) and removes the previous snapshot. After it runs,
    update the version stamp in [`../CLAUDE.md`](../CLAUDE.md).
  - Needs `zstandard` on Python < 3.14 (installed with `--user` into the system Python 3.12 on
    2026-11-23). The user has cleared installing packages like this as needed.
  - Finds `Data.p4k` by walking up from the repo (`LIVE` = four folders above the root). In a
    clone outside the game install that path doesn't exist, so `--p4k` is required there.
  - It reads only plain-zstd entries. If CIG ever encrypts those two files it exits with a clear
    message; a community extractor such as unp4k is the fallback (see [`../CLAUDE.md` §10](../CLAUDE.md)).
- **`validate_actionmaps.py` is the post-load proof.** It diffs [`../MOZA.xml`](../MOZA.xml)
  against the game's normalized export (`…\Profiles\default\actionmaps.xml`). The game **drops**
  wrong-map actions, so a `MISMATCH` — or an unexplained `NOT-IN-EXPORT` on a non-default action —
  means the running game did not keep a binding. Since 2026-11-26 it also compares the **inputs**:
  `INPUT-DIFF` = the game holds a different input for that action (a lost or replaced binding, or
  the profile not loaded since an edit), and `LEFTOVER` = a joystick binding the game holds that
  `MOZA.xml` does not declare (loading is an overlay, so a binding removed from the file lingers
  in the game). Non-zero exit on `MISMATCH`, `INPUT-DIFF` or `LEFTOVER`. Before that date it
  compared actionmaps only and reported a clean result while two bindings were lost. Reads local
  files only. It can only be as fresh as the last time the profile was loaded in-game: the game
  writes the export when it quits, so load, quit, then run.
- **`regen_cards.py` rebuilds [`../cards/`](../cards/CLAUDE.md)** from the art in
  [`../diagrams/`](../diagrams/CLAUDE.md) plus binding tables embedded in the script. Key rules:
  - The cards are **not auto-derived from [`../MOZA.xml`](../MOZA.xml)**. When a binding changes,
    edit the matching row in this script *and* the XML, then re-run. See [`../CLAUDE.md` §8.3](../CLAUDE.md).
  - Needs Pillow and a Chromium-family browser (Chrome, Edge or Chromium; `CARD_BROWSER`
    overrides the search). Look at both PNGs after a run for clipped text.
  - **The same run also writes the dashboard's rig reference** into `../dashboard/web/rig/`
    (since 2026-11-27): `rig.json`, every card row placed in one of eight views, and six diagram
    images in the page's colors (light line work on a transparent ground). The `VIEWS` list in
    the script says which button numbers each view's drawing shows and holds its crop box;
    `RIG_ART` holds the recolor settings. `python tools/regen_cards.py --dashboard-only` writes
    just those files, without the browser.
  - `dashboard/tests/test_rig.py` reads the tables with `ast` and **fails when a card row, a
    status mark in `dashboard/reference/controls.hand.json` or a source diagram has changed and
    the rig files were not regenerated**. So after any card edit, run the generator and commit
    `dashboard/web/rig/` with the cards.
  - The rounding helpers (`rnd`, `r1`) round half-to-even on purpose, to reproduce the original
    geometry exactly. Read [`../CLAUDE.md` §8.4](../CLAUDE.md) before changing the render code.

## Where the detail lives

- Card generator internals and layout knobs: [`../CLAUDE.md` §8](../CLAUDE.md).
- Catalog refresh and why the source changed from starbinder to the game files: [`../CLAUDE.md` §7](../CLAUDE.md).
- Actionmap correctness and the two-step check workflow: [`../CLAUDE.md` §10](../CLAUDE.md).
