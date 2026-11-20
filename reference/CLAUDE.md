# `reference/` — working notes for Claude

Bulk reference material: the game-derived action catalogue and a printable HTML binding sheet. The
human-facing description is in [`README.md`](README.md); this file is the working guidance for
editing or relying on these files.

## What you need to know

- **`SC_KEYBINDS_DATABASE_v<version>.md` is generated and patch-specific.** Don't hand-edit it.
  Regenerate with `python tools/gamedata.py catalogue` (from the project root) when a new SC patch
  ships; the tool rewrites the versioned file and deletes the old snapshot. See
  [`../tools/CLAUDE.md`](../tools/CLAUDE.md) and [`../CLAUDE.md` §7](../CLAUDE.md).
- **After a refresh, update the version stamp** referenced at the top of [`../CLAUDE.md`](../CLAUDE.md)
  (and its folder-layout block) if the version changed.
- **The catalogue is authoritative for names, labels AND actionmaps.** It is built from the game's
  own `defaultProfile.xml`, so each `##` section heading is the real actionmap an action must be
  bound under, and the default-binding columns show what the game binds out of the box. (The old
  starbinder-sourced catalogue grouped by a keyword *category* that was **not** the actionmap —
  that caveat no longer applies, but don't carry over an actionmap guess from older notes.)
- **Some action names appear in more than one actionmap** (`v_pitch`, `v_view_yaw`,
  `v_flightready`, the door actions, `v_starmap` …) — once for ships, once for ground vehicles.
  A binding under `spaceship_*` does **not** cover the `vehicle_*` copy.
- **The joystick default column matters.** Those defaults apply to `js1` and stay live under
  `MOZA.xml` unless rebound or cleared — see the `GHOST` report from `gamedata.py check`.
- **`MOZA_BINDINGS.html` is hand-authored**, not script-generated. Edit it directly if you change
  bindings, the same way you'd update the cards.

## Where the detail lives

- Catalogue generation and why starbinder was dropped: [`../CLAUDE.md` §7](../CLAUDE.md) and
  [`../tools/CLAUDE.md`](../tools/CLAUDE.md).
- Reference links (SC wiki, community tools): [`../CLAUDE.md` §9](../CLAUDE.md).
