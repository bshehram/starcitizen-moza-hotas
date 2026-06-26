# MOZA HOTAS — Star Citizen Binding Profile

[![XML parsing](https://img.shields.io/badge/XML_parsing-passing-brightgreen)](MOZA.xml)
[![Internally tested](https://img.shields.io/badge/internally_tested-in--game_verified-brightgreen)](#status)
[![Star Citizen](https://img.shields.io/badge/Star_Citizen-Alpha_4.8-1f6fb2)](https://robertsspaceindustries.com/)
[![Bindings](https://img.shields.io/badge/bindings-119_across_17_maps-informational)](MOZA.xml)
[![Devices](https://img.shields.io/badge/devices-MHG_%C2%B7_AB6_%C2%B7_MTQ-orange)](#requirements)
[![Platform](https://img.shields.io/badge/platform-Windows_%7C_DirectInput-lightgrey)](#requirements)
[![License: MIT](https://img.shields.io/badge/license-MIT-success)](LICENSE)

This is my hand-tuned Star Citizen control-mapping profile for a **MOZA flight setup**: an MHG
grip on an AB6 FFB base, plus an MTQ throttle quadrant. The whole rig drives flight, combat,
mining, and salvage from physical controls, and I've documented and verified every binding
in-game.

> **All you actually need from this repo is [`MOZA.xml`](MOZA.xml).** Everything else is
> documentation, reference art, and the scripts that regenerate it. Jump to
> [Installing](#installing) for the two ways to put it in place.

**Folder docs** — each subfolder has its own README with the detail for what lives there:
[`diagrams/`](diagrams/README.md) · [`cards/`](cards/README.md) ·
[`reference/`](reference/README.md) · [`tools/`](tools/README.md).

---

## Requirements

This profile is tuned to one specific rig. To **use it as-is** you need:

| | Requirement | Why |
| --- | --- | --- |
| 🪟 | **Windows** | Star Citizen is Windows-only, and the profile binds devices by their **DirectInput GUIDs**. No macOS/Linux. |
| 🕹️ | **MOZA MHG grip + MOZA AB6 FFB base + MOZA MTQ Throttle Panel** | Every binding maps to these exact devices. On different hardware the device GUIDs won't match and the bindings land nowhere. |
| 🚀 | **Star Citizen** (captured against **Alpha 4.8**) | Action names (`v_*`) are CIG's; a major patch can rename or remove some. |
| ⚙️ | **MOZA Cockpit / Pithouse** configurator | A couple of device-side settings are assumed on — notably **"Detent Button Mapping" ON** (so the throttle rear detent emits button 34 for reverse) and **mixed-mode** on the AB6/MTQ levers (so the sliders emit an analog axis). |

> **Don't have this exact rig?** You can still read the bindings as a starting point and rebind
> to your own devices, but the GUIDs in [`MOZA.xml`](MOZA.xml) are MOZA-specific, so it won't
> load cleanly onto other hardware without editing.

Regenerating the docs and cards (not needed just to *use* the profile) takes Windows PowerShell
with .NET `System.Drawing`, Chrome or Edge, and internet access. See [`tools/`](tools/README.md).

---

## Installing

Star Citizen loads control profiles from:

```
…\StarCitizen\LIVE\user\client\0\controls\mappings\
```

The game does **not** load profiles automatically — you apply them yourself (see below).

**Option A — just the file (minimal).** Copy [`MOZA.xml`](MOZA.xml) into that folder. That's it.

**Option B — the whole repo as your mappings folder (what I do).** Clone this repo *into* the
mappings folder. The game only reads `MOZA.xml` at the root and **ignores subfolders**, so the
diagrams, cards, and tools come along harmlessly and I get the reference material right where I
fly:

```powershell
cd "…\StarCitizen\LIVE\user\client\0\controls\mappings\"
git clone https://github.com/bshehram/starcitizen-moza-hotas.git
# then copy starcitizen-moza-hotas\MOZA.xml up one level, or clone with the repo contents at the mappings root
```

**Then load it in-game**, either way:

- **Options → Keybindings → Control Profiles → Load**, or
- open the console (`` ` ``) and run `pp_rebindkeys MOZA.xml` (the file name, no path).

> **Tip:** save your profile under a custom name before loading it, so a game patch that resets
> defaults can't overwrite your work.

---

## Hardware

| Game device | Physical hardware | Buttons | Axes |
| --- | --- | --- | --- |
| `js1` | **MOZA MHG** grip on **MOZA AB6 FFB** base (one DirectInput device) | grip 1–29, base 49–62 | roll / pitch / yaw twist + 2 lever axes |
| `js2` | **MOZA MTQ** Throttle Panel | 1–65 | throttle + camera mini-stick + 2 side sliders |

The MHG grip and the AB6 base report as **one** DirectInput device (`js1`): grip buttons are
1–29, the base's buttons continue at 49–62 (there's a 30–48 gap with no physical buttons). The
MTQ throttle is a **separate** device (`js2`). The full physical-control → button-number maps
live in [`diagrams/`](diagrams/README.md).

Product GUIDs as written in the profile:

- `js1` → `MOZA AB6 FFB Base  {1002346E-0000-0000-0000-504944564944}`
- `js2` → `MOZA MTQ Throttle Panel  {1101346E-0000-0000-0000-504944564944}`

> **⚑ Vehicle-only by design.** On foot I play on an Xbox controller, so this profile binds
> only seat/vehicle contexts — there are no on-foot (`player` / `spectator`) bindings.

> **⚠ Device-instance fragility.** `js1`/`js2` are assigned by the order the game enumerates USB
> devices. If Windows re-enumerates them (port change, hub, reconnect order) the two sticks can
> **swap**, and every binding points at the wrong device. If that happens, re-plug in the
> original order, or swap the `instance="1"`/`instance="2"` Product lines in the XML.

---

## Reference cards

Printable US-Letter cheat sheets (one per device), generated from the manufacturer diagrams.
Full detail and how to print in [`cards/`](cards/README.md).

| `js1` — MHG grip + AB6 base | `js2` — MTQ throttle |
| --- | --- |
| ![MHG + AB6 card](cards/MOZA_MHG_AB6_ref.png) | ![MTQ card](cards/MOZA_MTQ_ref.png) |

---

## Repo layout

```
MOZA.xml            the profile the game loads — THE ONLY FILE YOU NEED (keep in root)
README.md           this file
LICENSE             MIT license
diagrams/           manufacturer button-number maps (source art) + button-index tables
cards/              generated printable cheat sheets (PNG + editable SVG)
reference/          starbinder action catalogue (v4.8) + an HTML binding sheet
tools/              regeneration scripts (run from the project root)
```

Each folder above has its own README with the details:
[`diagrams/`](diagrams/README.md) · [`cards/`](cards/README.md) ·
[`reference/`](reference/README.md) · [`tools/`](tools/README.md). (You'll also see `CLAUDE.md`
files scattered through the repo — those are working notes for the Claude AI assistant and aren't
needed by human readers.)

---

## Tooling

Both scripts are PowerShell, run from the project root. Full usage, requirements, and gotchas are
in [`tools/`](tools/README.md).

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\refresh_keybinds_db.ps1   # refresh the action catalogue for a new SC patch
powershell -ExecutionPolicy Bypass -File .\tools\regen_cards.ps1           # rebuild the reference cards after a binding change
powershell -ExecutionPolicy Bypass -File .\tools\validate_actionmaps.ps1   # check every binding sits in the actionmap the game files it under
```

---

## Status

- **XML parsing — passing.** `MOZA.xml` is well-formed (`xmllint --noout MOZA.xml` is clean):
  119 `<action>`/`<rebind>` pairs across 17 action maps, with no action bound to two different
  inputs. Buttons that appear in several maps (the trigger, rocker, hats, AB6 wings) are
  intentional **operator-mode reuse** — only one of those maps is live at a time, depending on
  whether the seat is in flight, mining, or salvage mode.
- **Internally tested — in-game verified.** I validated the bindings in live Star Citizen
  (Alpha 4.8), including the mining-laser and salvage-spacing slider axes, which I confirmed in a
  Golem and a Salvation. I cross-checked the action labels and descriptions against the
  [starbinder](https://starbinder.space/) master catalogue, captured in
  [`reference/`](reference/README.md).

> Badges are self-reported — this is my personal config repo, not a CI'd codebase. The XML
> "passing" claim is reproducible locally with the `xmllint` command above, and "tested" means
> hands-on in the game.

---

## Contributing

I maintain this solo, but **PRs are welcome and I'll review them** — corrections, bindings for
other MOZA layouts, newer-patch updates, or improvements to the docs and cards. Please:

- keep [`MOZA.xml`](MOZA.xml) loading cleanly (run `xmllint --noout MOZA.xml`), and
- if you change a binding, update its inline comment in the XML and the card tables in
  `tools/regen_cards.ps1` (the cards aren't auto-derived from the XML — see
  [`tools/`](tools/README.md)).

Open an issue first if it's a big change, so we don't duplicate effort.

---

## License & provenance

Released under the [MIT License](LICENSE) — © 2026 Basit Shehram.

Everything here is **original work**: I built the `MOZA.xml` profile, the reference cards, the
regeneration scripts, the HTML binding sheet, and all the documentation for this repo. **No
third-party profile generator is used anywhere** — the cards are built solely by the in-repo
`tools/regen_cards.ps1`.

Two third-party *inputs* are **not** covered by the MIT license and remain their owners' property:

- the **manufacturer diagrams** (`diagrams/*.png`) — MOZA's own button-number art, used as the
  source layer for the cards; and
- the **action catalogue** in `reference/` — derived from the public
  [starbinder](https://starbinder.space/) keybind database and the
  [Star Citizen wiki](https://starcitizen.tools/).

Star Citizen is a trademark of Cloud Imperium Games. This is an unofficial, fan-made config and
is not affiliated with or endorsed by CIG or MOZA.
