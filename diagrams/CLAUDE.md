# `diagrams/` — working notes for Claude

Manufacturer button-number art for the three MOZA devices. The human-facing description and the
full button-index tables are in [`README.md`](README.md); this file is the working guidance for
editing or relying on these files.

## What you need to know

- **These PNGs are source art — treat them as read-only.** They are MOZA's own diagrams, and
  they are the **input layer** for the reference cards. Deleting or cropping them breaks card
  regeneration. See [`../cards/CLAUDE.md`](../cards/CLAUDE.md) and
  [`../tools/CLAUDE.md`](../tools/CLAUDE.md).
- **Button numbers are baked into the art.** Never hand-place or relabel a number anywhere; the
  card generator only recolors and crops these images. The numbers you see are MOZA's own.
- **Crop rectangles** that carve each sub-view out of these PNGs live in `../tools/regen_cards.py`:
  `CARD_ART` holds the six the printed cards use, `VIEWS` the eight of the dashboard's rig reference
  (the throttle panel cut into keypad, dials and levers), and `DISCS` / `FINGERPRINTS` where each
  button's number disc sits and the names as they were read by eye. Only re-verify them if MOZA
  ships new device art with a different layout — then update the crops, read the disc names again
  (`--sheets`, see [`../tools/CLAUDE.md`](../tools/CLAUDE.md)) and rebuild the cards.

## Where the detail lives

- Full physical-control → button-index tables: [`README.md`](README.md) here, and the master
  copy in [`../CLAUDE.md` §3](../CLAUDE.md).
- Hardware setup, device GUIDs, and the `js1`/`js2` instance-swap caveat: [`../CLAUDE.md` §1](../CLAUDE.md).
- How these images become cards: [`../CLAUDE.md` §8](../CLAUDE.md) and [`../tools/CLAUDE.md`](../tools/CLAUDE.md).
