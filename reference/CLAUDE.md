# `reference/` — working notes for Claude

Bulk reference material: the starbinder action catalogue and a printable HTML binding sheet. The
human-facing description is in [`README.md`](README.md); this file is the working guidance for
editing or relying on these files.

## What you need to know

- **`STARBINDER_KEYBINDS_DATABASE_v<version>.md` is generated and patch-specific.** Don't
  hand-edit it. Regenerate with `../tools/refresh_keybinds_db.ps1` when a new SC patch ships; the
  script rewrites the versioned file and deletes the old snapshot. See
  [`../tools/CLAUDE.md`](../tools/CLAUDE.md) and the full recipe in [`../CLAUDE.md` §7](../CLAUDE.md).
- **After a refresh, update the version stamp** referenced at the top of [`../CLAUDE.md`](../CLAUDE.md)
  (and its folder-layout block) if the version changed.
- **Use this catalogue to validate edits to [`../MOZA.xml`](../MOZA.xml).** It's the authoritative
  list of real action names (`v_*`) and their official labels/descriptions — check a name here
  before adding or correcting a binding.
- **The catalogue does NOT give the actionmap.** It groups actions by their first *keyword* (a
  category like "camera - advanced camera controls"), which is **not** the SC actionmap an action
  must be bound under. Inferring an actionmap from the category is how bindings end up silently
  dropped. For the correct actionmap, use the game's local profile export / `defaultProfile.xml` and
  [`../tools/validate_actionmaps.ps1`](../tools/CLAUDE.md) — see [`../CLAUDE.md` §10](../CLAUDE.md).
- **`MOZA_BINDINGS.html` is hand-authored**, not script-generated. Edit it directly if you change
  bindings, the same way you'd update the cards.

## Where the detail lives

- Refresh tooling and the manual download recipe: [`../CLAUDE.md` §7](../CLAUDE.md) and
  [`../tools/CLAUDE.md`](../tools/CLAUDE.md).
- Reference links (starbinder, SC wiki): [`../CLAUDE.md` §9](../CLAUDE.md).
