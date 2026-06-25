# `cards/` — working notes for Claude

Generated printable cheat sheets (PNG + editable SVG), one per device. The human-facing
description, the print settings, and what each card stacks are in [`README.md`](README.md); this
file is the working guidance for editing these files.

## What you need to know

- **These four files are generated — never hand-edit them.** Rebuild with `../tools/regen_cards.ps1`
  (run from the project root); it overwrites all four. See [`../tools/CLAUDE.md`](../tools/CLAUDE.md).
- **Source of truth is [`../MOZA.xml`](../MOZA.xml), not these cards.** The function text comes
  from binding tables hand-maintained inside `regen_cards.ps1`. Nothing cross-checks those tables
  against the XML, so when a binding changes you must edit **both** the XML and the matching row
  in the script, then re-run it. This is the most common way the cards drift — see
  [`../CLAUDE.md` §8.3](../CLAUDE.md).
- **Button numbers ride along inside the diagram art** in [`../diagrams/`](../diagrams/CLAUDE.md);
  the generator never places a number by hand.

## Where the detail lives

- Build pipeline, layout knobs, and the headless-render gotchas: [`../CLAUDE.md` §8](../CLAUDE.md)
  and [`../tools/CLAUDE.md`](../tools/CLAUDE.md).
- The binding meanings behind the table text: [`../CLAUDE.md` §4](../CLAUDE.md).
