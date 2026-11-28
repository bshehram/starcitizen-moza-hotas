# `dashboard/RIG.md`: the rig reference data (`web/rig/`)

The schema of `web/rig/rig.json` and the images beside it, for whoever builds the page's "Rig
reference" section or changes the generator. How to regenerate the files, and what to do after a
change, is in root [`../CLAUDE.md`](../CLAUDE.md) §8.3 and §8.5; how the service serves them is in
[`STATE.md`](STATE.md) and [`CLAUDE.md`](CLAUDE.md) ("The rig files").

## The files

`web/rig/rig.json` and the eight PNGs beside it are the data and art of the page's "Rig reference"
section. `tools/regen_cards.py` writes them (`--dashboard-only` without a browser) from the card
tables and the literals after them in that script, the art in `diagrams/`, `MOZA.xml` and the
action catalog in `reference/`. Nothing in the folder is edited by hand, and `tests/test_rig.py`
fails until it is regenerated after any of those changed. Schema 2 (2026-11-28, revised the same day
after its two reviews; the changes are listed at the end). The file is UTF-8 JSON with LF line
endings, about 90 KB.

**How the files are written.** The generator makes every file in memory and checks it all first. A
run a check refuses (the card tables and `MOZA.xml` disagree, a disc's name no longer matches the
one read by eye, and the rest of the list in root `CLAUDE.md` §8.2) writes nothing. Then each file
goes through a temporary file in the folder and is renamed into place, retried for about two seconds
while a reader (the dashboard's service, a browser) holds the old one. A file that already holds the
same thing is left alone: `rig.json` when its bytes are the same, a PNG when `png_facts()` is the
same (the chunk types in order, the header, the palette and transparency, and the pixels as RGBA),
so a run on a Pillow with another zlib build does not rewrite images whose pixels have not changed.
`rig.json` is written last. **A write that still fails** (a file held for longer, the disk full) can
leave a mixed set, for example new images beside an old `rig.json`: the test catches it, and a rerun
repairs it. Temporary files a killed run left behind are swept at the next run.

**A missing key means the value is absent, never false or "none" by accident.** Where absence has
a meaning, the field's row below says what it is. Every value is generated: "how it is known"
names the source.

## Top level

| Field | Type | What it is | How it is known |
| --- | --- | --- | --- |
| `_meta` | object | Provenance, hashes, the status key, counts (below). | Generator. |
| `modes` | list | The five operator modes, in the order a filter lists them. | `MODES` in the script; the knob from `MOZA.xml`. |
| `live_modes` | object | The page's mode filters, by `view.mode` of the live views (`flight`, `mining`, `salvage`) -> the list of mode ids the filter covers, the filter's own mode first: `flight` = `["combat", "missile", "scan"]`, `mining` = `["mining"]`, `salvage` = `["salvage"]`. Every mode is under one filter. | `LIVE_MODES`: flight is the guns mode ("Guns mode covers combat-flight", root `CLAUDE.md` §4) and the two other modes a pilot flies in. |
| `maps` | object | Per actionmap of `MOZA.xml`: in which modes it is live, dead or not known, why, and a note on every unknown cell. | `MAPS`, each list resting on quoted whole sentences. |
| `devices` | list | `js1` (stick), `js2` (throttle). | `CARDS`. |
| `views` | list | The eight image views, in page order (js1 then js2). | `VIEWS`; sizes, hashes and disc sizes measured. |
| `rows` | list | The 96 card rows, in card order. | The card tables, `MOZA.xml`, `STATUS`, the discs found in the art. |

## `_meta`

| Field | Type | Meaning |
| --- | --- | --- |
| `schema` | int | 2. Bumped when a field changes meaning. |
| `generated` | `YYYY-MM-DD` | The day a hash last changed: an input (tables, art, profile, catalog) or the code that makes the files (`hash.code`). A run that changes nothing keeps the date. No finer time. |
| `generated_by`, `source`, `doc` | string | Provenance in words; `doc` names this file. |
| `catalog` | string | The catalog file read, relative to the repo (`reference/SC_KEYBINDS_DATABASE_v4.10.md`). |
| `status` | object | The meaning of each status, and `missing`: what a row or variant without `status` means. |
| `hash` | object | 12 hex digits each. `tables`: the script's literals the files are made from (its `SOURCES`: the card tables, `CARDS`, `MODES`, `LIVE_MODES`, `MAPS`, `STATUS`, `CARD_ART`, `VIEWS`, `READINGS`, `DISCS`, `DISC_FINDER`, `RIG_ART`, `FINGERPRINTS`), as values. `code`: the script's rig code as Python parses it: `jnum` and every statement between the "dashboard rig reference" heading and `main`, written out by `canon()` (node types and fields; no positions, comments, blank lines or docstrings), so only a change to the code itself moves it. `diagrams`: each source PNG's bytes. `profile`: the bindings of `MOZA.xml`, as parsed. `catalog`: the catalog rows of the actionmaps used, as parsed. Line endings move none of them. |
| `counts` | object | `rows` (96), `views` (8), `discs` (103: the numbered marks), `status` (rows' and variants' statuses counted together: flown 15, unverified 28, trial 2, none 75). |

## `modes[]`

| Field | Type | Meaning |
| --- | --- | --- |
| `id` | string | `combat`, `missile`, `scan`, `mining`, `salvage`. The keys of every `modes` object below. |
| `name` | string | Screen name: Combat, Missile, Scan, Mining, Salvage. |
| `operator` | string | The game's operator mode: Guns, Missile, Scanning, Mining, Salvage. |
| `tag` | string or null | The printed card's tag for it (`Msl:`, `Mine:`, `Salv:`); null for combat (untagged on the card) and scan (no card tag). |
| `knob` | object | The MTQ mode knob detent that sets the mode: `{device, button, detent, row}`, e.g. Mining = js2 button 20, detent 4, row `js2-20`. Button from `MOZA.xml` (`v_set_<mode>_mode`), detent checked against the card row's hint. |

Flight and Quantum operator modes are not on the knob (root `CLAUDE.md` §4) and not modes here.

## `maps.<actionmap>`

`{live: [mode], dead: [mode], unknown: [mode], why: [{file, ref, text}], note?}`. Every mode is in
exactly one list. `dead` = the docs say the map is off there; `unknown` = the docs do not say, or
contradict each other. `why` quotes whole sentences of root `CLAUDE.md` or of `MOZA.xml`'s comments
the lists rest on, `ref` = where each sits ("§4 Targeting", "§6 item 20"; for `MOZA.xml` a phrase of
its comment). The test checks that each occurs exactly once in its file, in that place, as whole
sentences. `note` (string or absent) is present on every map with an unknown cell and says why it is
unknown. Unknown today: `spaceship_hud` (star map), `spaceship_docking`, `spaceship_radar` (ping)
and `spaceship_quantum` in every mode (engaging the quantum drive needs NAV master mode, where
weapons are offline, and these modes are operator modes; the data has no master modes), and the two
targeting maps in missile and scan mode (the docs conflict).

## `devices[]`

| Field | Type | Meaning |
| --- | --- | --- |
| `id` | string | `js1`, `js2`. |
| `name` | string | Screen name: Stick, Throttle. |
| `product` | string | "MOZA MHG grip on the AB6 base", "MOZA MTQ throttle panel". |
| `title`, `sub`, `legend` | string | The printed card's heading, subheading and footer, as printed (the stick card's footer still holds the tag key; the screen should use `views[].notes`). |
| `views` | list of string | The device's view ids, in page order. |

## `views[]`

| Field | Type | Meaning |
| --- | --- | --- |
| `id` | string | `grip_front`, `grip_side`, `base`, `keypad`, `dials`, `levers`, `right_module`, `left_module` (lower-case letters, digits, underscores). |
| `device` | string | `js1` or `js2`. |
| `title` | string | Short tab name: Grip front, Grip side, Base, Keypad, Dials and switches, Levers, Right module, Left module. |
| `caption` | string | A longer line ("MTQ throttle panel: keypad"). |
| `image` | string | The PNG beside `rig.json`: `<id>.png`. |
| `w`, `h` | int | Its native size in pixels. All coordinates below are in these pixels, origin top left. |
| `hash` | string | 16 hex digits: sha256 of `"<w>x<h>:"` plus the pixels as RGBA bytes. The test decodes the PNG with the standard library and compares. |
| `source` | object | `{diagram, box: [x0, y0, x1, y1]}`: where the image comes from: `diagrams/<diagram>.png` (the stem only, so that the only strings in the file ending `.png` are the images beside it), the crop after trimming. The image is that box at 1:1, never scaled. |
| `buttons` | list of int | Every number drawn in the view, ascending. Each has exactly one disc in the image, and the image has no other disc. |
| `disc_min` | int | The smallest disc's shorter side, in pixels. |
| `digit_min` | int | The shortest digit height inside a disc, in pixels (7 to 9). |
| `scale_18` | number | `18 / disc_min`: the smallest scale at which every disc is at least 18 px across. |
| `notes` | list of string | The card footer's sentences about this view, in card order; may be empty. Each is whole sentences, without the tag key. |
| `rows` | list of string | The ids of the rows on this view, in card order. |

**How large to draw a view.** No page text goes under 18 px. The art's own digits are `digit_min`
px tall at 1x; an 18 px label's digits are about 13 px tall, so the art's numbers reach that at
`13 / digit_min` and are smaller below it. A page that draws its own numbers over the discs (the
designer's plan) needs only `scale_18` for the discs to hold them. Measured 2026-11-28:

| View | Image | `disc_min` | `digit_min` | `scale_18` | Art digits at 13 px | Rows |
| --- | --- | --- | --- | --- | --- | --- |
| Grip front | 413 x 453 | 17 | 7 | 1.06 | 1.86x | 22 |
| Grip side | 288 x 308 | 16 | 8 | 1.12 | 1.62x | 10 |
| Base | 492 x 370 | 14 | 7 | 1.29 | 1.86x | 10 |
| Keypad | 209 x 267 | 15 | 7 | 1.2 | 1.86x | 10 |
| Dials and switches | 279 x 268 | 15 | 8 | 1.2 | 1.62x | 20 |
| Levers | 392 x 344 | 16 | 9 | 1.12 | 1.44x | 6 |
| Right module | 362 x 372 | 15 | 8 | 1.2 | 1.62x | 13 |
| Left module | 308 x 279 | 16 | 9 | 1.12 | 1.44x | 5 |

The PNGs are 4-bit palette images: one color (`#E4ECF2`) in 16 opacity steps on a transparent
ground, made for the page's dark panel. MOZA's sample readings are painted out: the numbers
("65535", "0", "32767"; the axis words X and Y beside two of them stay), and the two lit level bars
are dimmed to match the unlit ones. The printed cards keep them.
The text MOZA drew (A1 to A4, the knob's 1 to 5, "Slider", "Dial", "Left Module") is raster and
under 18 px. There is no ninth image of the whole throttle panel: the cards' `cards/*.svg` hold it.

## `rows[]`

| Field | Type | Meaning | How it is known |
| --- | --- | --- | --- |
| `id` | string | Stable id: device and label, lower case, runs of other characters as `-`: `js1-12`, `js1-57-59`, `js2-x-y`, `js2-z-rz`. It changes only if the printed label does. | Generated from the label. |
| `device` | string | `js1` or `js2`. | Card. |
| `label` | string | As printed on the card badge: `12`, `57-59`, `X / Y`, `Slider`. | Card. |
| `buttons` | list of int | The button numbers, ranges expanded (`57-59` -> `[57, 58, 59]`); empty for an axis row. | Label. |
| `inputs` | list of string | The profile inputs: `js1_button12`, `js2_roty`, `js2_x` + `js2_y`. | Label; an axis row's from the table. |
| `view` | string | The one view the row is on. A button row is on the view that draws its numbers; an axis row on the view `VIEWS` gives it (stick axes: grip side; throttle axes: levers; mini-stick: left module). | `VIEWS`. |
| `drawn` | bool | A view's image shows the control: true for every button row, and for the axis rows whose name the art writes inside a crop (RY, RX, Dial, Slider, X / Y). False for the stick's X, Y and RZ and the throttle's Z / RZ (MOZA draws the grip twist RZ, under the front grip, outside every crop; the others nowhere). | `VIEWS`. |
| `text` | string | The primary function in whole words for the screen ("Cycle sub-targets forward"), worded after the game's label of the action it names. No status word. | Table (`Screen`), whose `Actions` must be the actions `MOZA.xml` binds there. |
| `where` | string | Where the control is, in words, for every row ("Right hat up", "Trigger second stage", "Rocker press", "Keypad A1"). | Table (`Where`). |
| `group` | string | The physical control the row belongs to, as root `CLAUDE.md` §3 names it ("right hat", "COM hat", "upper encoder", "keypad", "trigger"). Rows of one control share it; 33 groups. | Table (`Group`). |
| `unbound` | `true` or absent | Nothing is bound to the control. Absent = bound. An unbound row has no status and is "none" in every mode. | Table, checked against `MOZA.xml`. |
| `status` | string or absent | The primary function's status: `flown`, `unverified` or `trial` (`_meta.status` says what each means). Absent = the docs record neither a flight report nor a doubt about how that binding behaves (doubts about which physical control carries a number, and about the game defaults the profile clears, are not statuses). On a row with `jobs`, the more doubtful of its jobs' statuses (flown < absent < unverified < trial). | `STATUS` in the script, each entry quoting whole sentences of root `CLAUDE.md`. |
| `status_ref` | string or absent | Where the status's sentences sit in root `CLAUDE.md` ("§6 item 24", "§4 Mining; §11.1"); present with `status`, except on a row whose jobs carry their own (read the jobs'). | The quotes' places in `STATUS`. |
| `status_when` | string or absent | When a `flown` confirmation was made, where the docs say: a date ("2026-11-26") or a month and build ("June 2026, Alpha 4.8"). Absent = the docs give no date. So a page can say how old a confirmation is. | `STATUS` (`When`), checked to sit beside a quote. |
| `jobs` | list or absent | Only where a tap and a hold on one press do different things (js2 8, js2 10): `[{press: "tap" or "hold", text, actions: [action], modes: {mode: "live" / "none" / "unknown"}, status?, status_ref?, status_when?}]`. | Table (`Jobs`), checked against the actions' activation modes. |
| `variants` | list or absent | The other operator modes' jobs on the same press: `[{mode, text, card, status?, status_ref?, status_when?}]`, in card order. `text` is the screen wording ("Salvage beam spacing wider (step)"), `card` the printed one ("gap +"). | Table (`ScreenVariants`, `Variants`, `VariantActions`), `STATUS`. |
| `card` | object | The printed card's wording: `{primary, hint?}` (hint absent when the card prints none). The card's variants are `variants[].card`. | Table. |
| `modes` | object | For each mode id: what the press does there (below). | `MOZA.xml` actionmaps and `maps`. |
| `actions` | list | Every action on the row's inputs: `{part, map, action, label, activation, stock?}`. `part` = `primary` or the variant's mode; `label` the in-game label; `activation` the effective activation mode: the profile's `activationMode`, else the catalog's stock mode, null where the catalog gives none (the stick and mini-stick axes, the Dial, and seven salvage actions); `stock: true` = a stock joystick binding the profile leaves in place (only the trigger's "Weapon Preset - Fire"). | `MOZA.xml`, the catalog. |
| `discs` | list | The row's marks on its view, in the view image's pixels: `[{n, word?, x, y, w, h, box}]`. A button row has one per button (`n` = the number, in `buttons` order); an axis row the art draws has one per word the art writes for it (`n` null, `word` = "Dial", "RX", "X", "Y"...); an undrawn axis row has none. `x`, `y` = the center (may end in .5); `w`, `h` = the size of the art's own mark; `box` = false for a round disc, true for a box-shaped badge (the grip rocker 22-24, the throttle's power rocker 22-24, toggles 25-30 and switch 49-51) and for every word. | Found by code in the PNG (`find_discs`), named from rough positions in `DISCS`; the test finds them again. |

### Reading `modes`

`row.modes[mode]` is one of:

- `"variant"`: the press changes job in this mode; the job is the `variants` entry with that `mode`.
- `"primary"`: the primary job acts in this mode (`text`). Whether that is "keeps its job" or "its
  own job belongs to this mode" shows in the other modes: a row that is `"primary"` in all five stays
  live in every mode (60 rows: power panel, countermeasures, strafe, look-behind, throttle, lights,
  doors...); one that is `"none"` in combat and `"primary"` in mining is a mining control (js2 1,
  Slider).
- `"none"`: nothing on this press acts in this mode (the docs say its maps are off there), e.g.
  target cycling on js1 8 in Mining mode, or every mode of an unbound row.
- `"unknown"`: what acts here is not known: the docs do not say whether its map is live in this
  mode (radar ping and the star map everywhere; targeting in missile and scan mode).

**Reading a page filter** (`live_modes`): a row is live under a filter when it is `"primary"` or
`"variant"` in any of the filter's modes. When the first such mode is not the filter's first one, the
page names that mode on the row (under Flight, js1 2 shows "Missile" and js1 17-19 "Scan"). A row is
`unknown` under a filter when it is unknown in some of its modes and live in none, and does nothing
when it is `"none"` in all of them.

So under a Mining filter: `variant` = changes job, `primary` with `modes.combat == "primary"` =
keeps its job, `primary` with `modes.combat != "primary"` = a job of this mode, `none` = does
nothing, `unknown` = say nothing. A tap / hold row's `jobs[].modes` tell which half acts (js2 10
in Mining: the hold, Autoland, is live; for the tap, docking, the docs do not say).

Counts (2026-11-28): combat 78 primary / 15 none / 3 unknown; missile 60 / 2 variant / 18 / 16;
scan 62 / 0 / 18 / 16; mining 61 / 7 / 25 / 3; salvage 62 / 15 / 16 / 3. Under the Flight filter:
82 rows live, 11 do nothing, 3 unknown (the star map, the quantum drive, the radar ping).

## Status values (counted on 96 rows and 24 variants, 2026-11-28)

| Status | Rows | Variants | Meaning |
| --- | --- | --- | --- |
| `flown` | 12 | 3 | Confirmed in a ship: root `CLAUDE.md` says it worked in flight. |
| `unverified` | 21 | 7 | Bound, not yet confirmed in a ship. Most are loaded in the game; a binding changed since the last load is unverified too, and its quote says so (the six AB6 wing buttons swapped on 2026-11-28). |
| `trial` | 0 | 2 | The docs call the binding a trial. |
| absent | 63 | 12 | The docs record neither a flight report nor a doubt about the binding. |

js2 10 also carries per-job statuses (tap = Docking, unverified; hold = Autoland, flown). Eleven
rows carry `status_when`: js1 29 and the AB6 wing buttons 52 and 56 (2026-11-26), js2 RY (2026-11-27),
the five WPN-hat shield-face buttons js2 52 to 56 (2026-11-28),
js2 Slider and Dial ("June 2026, Alpha 4.8"); so do three variants (the Mining jobs of js1 12, 13
and 24, 2026-11-27) and one job (the js2 10 hold, 2026-11-27). js1 3's confirmation has no date in
the docs.

## Guarantees the test makes

Every input `MOZA.xml` binds has a row; every row not `unbound` names a bound input, and an
`unbound` row none. Each row names the actions its wording is about, and those are exactly the
actions bound on its input in each mode. The printed cards (`cards/*.svg`) say what the tables say.
The 96 row ids are pinned in the test. Each button a view claims has exactly one disc in its image
and no disc is unclaimed; each numbered row has a mark per button on its view; every disc still
carries the name read by eye (a fingerprint of the art under it), and disc names agree with the
`where` words inside each hat, rocker and encoder. The readings listed are painted out. Statuses
and `maps` match the script. Every sentence they quote occurs exactly once in its file, in the place
named, as whole sentences: it starts where a sentence starts (the file's start, a new paragraph, an
XML comment's start, after `.`, `!` or `?`, at a table cell, or at a list item or blockquote line;
not after a colon or a dash in mid-line) and ends where one ends. The activity strips' statuses in
`reference/controls.hand.json` agree. Each PNG decodes and has its stated size and hash. With Pillow,
`rig.json` is byte for byte what the generator makes today, and each PNG the same image by
`png_facts()`; without Pillow that comparison is skipped, and the test says on the console what it
did not check.

**Advisory, not checked:** the generator prints a warning, and nothing fails, when no quote of a
status uses a word of that status (`STATUS_WORDS`), when a status that is not a trial quotes the
word "trial", or when no quote of a `maps` entry names a mode it calls live or dead (`MODE_WORDS`).

**Not guaranteed:** that the wording describes its action well (only that it is about that action);
that a quoted sentence means what the status or the map claims (it is checked to exist, to be unique,
to sit in its place and to be whole sentences, not read), or that the sentence after it does not
take it back; that MOZA drew no sample reading `READINGS` does not list; that `generated` was not
edited by hand to another day in the allowed range (when no hash moved, the generator keeps the date
it finds).

## Changes since the first version of schema 2

The first review's fix round (2026-11-28):

- `live_modes`: values are lists of modes, the filter's own mode first (were one mode each).
- `_meta.hash.art_code` is now `_meta.hash.code`, and covers all of the script's rig code;
  `generated` moves when it changes.
- `maps.*.note` (new, on every map with an unknown cell); `maps.*.why[].ref` is now a checked place.
  `spaceship_quantum` is unknown in every mode (was live in combat).
- `status_when` (new) on rows, jobs and variants; `status_ref` is derived from the quotes' places.
- `_meta.status.missing` reworded (what an absent status means).
- Screen wording: js1 2 "Launch missiles" (no hold claim), js1 20 "Radar ping (hold and release)",
  js2 24 "... press again to spin down". The printed cards are unchanged.

After the second review (2026-11-28); no field changed meaning, so still schema 2:

- `_meta.hash.code` is taken over the parsed code (`canon()`) and includes `jnum`: a comment, a
  blank line or a docstring no longer moves it. `canon()` is written so that every Python from 3.8
  gives the same text (it leaves out the empty fields 3.13's `ast.dump` drops, and unwraps 3.8's
  `Index`); only 3.12 was there to run it on.
- `_meta.hash.tables` no longer covers `STATUS_WORDS` and `MODE_WORDS`, which became advisory and
  shape nothing in the files.
- `_meta.doc` names this file (it named a section of `STATE.md` that was never written).
- PNGs are compared by `png_facts()`, not bytes; a file that already holds the same thing is not
  rewritten, and `rig.json` is written last.
