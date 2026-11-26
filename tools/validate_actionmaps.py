"""validate_actionmaps.py - prove the running game holds exactly the bindings in MOZA.xml, using the
game's own normalized export as the oracle.

WHY THIS EXISTS
  `tools/gamedata.py check` catches a bad profile BEFORE you launch, by reading CIG's
  defaultProfile.xml out of Data.p4k. This script is the other half: proof of what the RUNNING game
  ended up with. The game writes a normalized copy of its current bindings to:

      ...\\StarCitizen\\LIVE\\user\\client\\0\\Profiles\\default\\actionmaps.xml

  Facts that make that file a validator (all seen in real exports):
    1. The game files each ACCEPTED action under its TRUE actionmap, and DROPS an action placed in
       the wrong one.
    2. The game keeps ONE joystick binding per action. If a profile lists two, the last wins.
    3. Loading a profile is an OVERLAY: an action the file does not mention keeps whatever binding
       the game already had, including one from an earlier version of the profile.
  So: load your profile in-game (Options > Keybindings, or `pp_rebindkeys MOZA.xml`), then run this.
    - MISMATCH      = the action is in the export under a DIFFERENT map -> MOZA.xml is wrong, fix it.
    - INPUT-DIFF    = right map, but the game holds a different input than MOZA.xml asks for (the
                      binding was lost or replaced, or the profile has not been loaded since an edit).
    - LEFTOVER      = the game holds a joystick binding MOZA.xml does not declare (left by an older
                      version of the profile, or made in the game's menu). It still fires. Clear it
                      in the Keybindings menu, or add a temporary clear to MOZA.xml.
    - NOT-IN-EXPORT = the export does not list this action. Either the binding equals an SC default
                      (benign: the export lists only what differs from stock) or it was DROPPED.
    - OK            = same actionmap and same input as MOZA.xml.

USAGE (from the project root; any OS with Python 3.8+, no extra packages):
    python tools/validate_actionmaps.py
    python tools/validate_actionmaps.py --profile /path/to/actionmaps.xml

Exit code is non-zero on any MISMATCH, INPUT-DIFF or LEFTOVER (handy for a quick gate).
"""

import argparse
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent           # ...\controls\mappings
CLIENT0 = ROOT.parent.parent                            # ...\user\client\0 when run in the game folder
JOYSTICK = re.compile(r'^js\d+_')


def bindings(path):
    """{(actionmap, action): [joystick rebind, ...]} in file order. Structure-agnostic: MOZA.xml is
    ActionMaps>actionmap, the game export is ActionMaps>ActionProfiles>actionmap. A rebind is the
    tuple (input, activationMode, multiTap); only joystick inputs are kept, because MOZA.xml is a
    joystick profile and keyboard or gamepad changes made in the game are not its business."""
    out = {}
    for m in ET.parse(path).getroot().iter('actionmap'):
        for a in m.findall('action'):
            rebinds = [(r.get('input'), r.get('activationMode'), r.get('multiTap'))
                       for r in a.findall('rebind') if JOYSTICK.match(r.get('input') or '')]
            out.setdefault((m.get('name'), a.get('name')), []).extend(rebinds)
    return out


def show(rebinds):
    parts = []
    for inp, mode, taps in rebinds:
        text = 'clear (%s)' % inp.strip() if inp.endswith('_ ') else inp
        if mode:
            text += ' ' + mode
        if taps:
            text += ' x' + taps
        parts.append(text)
    return ', '.join(parts) or 'nothing'


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--mapping', type=Path, default=ROOT / 'MOZA.xml',
                    help='profile to validate (default: MOZA.xml next to tools/)')
    ap.add_argument('--profile', type=Path,
                    default=CLIENT0 / 'Profiles' / 'default' / 'actionmaps.xml',
                    help="the game's export (default: <client\\0>/Profiles/default/actionmaps.xml)")
    args = ap.parse_args()

    if not args.mapping.exists():
        sys.exit('MOZA mapping not found: %s' % args.mapping)
    if not args.profile.exists():
        sys.exit('Game export not found: %s\n  Load the profile in-game first (it writes this file), '
                 'or pass --profile <path>.' % args.profile)

    moza = bindings(args.mapping)
    game = bindings(args.profile)

    # Action name -> actionmaps the game files it under. Some action names exist in more than one
    # actionmap (a ship copy and a ground-vehicle copy of v_yaw, v_view_yaw, ...), so an export entry
    # under another map is only a MISMATCH if MOZA.xml does not itself declare that other copy.
    filed = {}
    for amap, action in game:
        filed.setdefault(action, []).append(amap)

    ok, mismatch, input_diff, not_in_export = 0, [], [], []
    for (amap, action), wanted in moza.items():
        if action not in filed:
            not_in_export.append((action, amap))
        elif amap in filed[action]:
            held = game[(amap, action)]
            if held == wanted:
                ok += 1
            else:
                input_diff.append((action, amap, show(wanted), show(held)))
        else:
            unclaimed = [m for m in filed[action] if (m, action) not in moza]
            if unclaimed:
                mismatch.append((action, amap, ','.join(unclaimed)))
            else:
                not_in_export.append((action, amap))

    leftover = [(action, amap, show(held)) for (amap, action), held in game.items()
                if held and (amap, action) not in moza]

    newer = args.mapping.stat().st_mtime > args.profile.stat().st_mtime
    print('Profile (oracle): %s' % args.profile)
    print('Mapping:          %s' % args.mapping)
    if newer:
        print('NOTE: MOZA.xml was edited after the game last wrote its export - load it in-game, quit '
              'the game, then run this again.')
    print()
    print('OK: %d   MISMATCH: %d   INPUT-DIFF: %d   LEFTOVER: %d   NOT-IN-EXPORT: %d'
          % (ok, len(mismatch), len(input_diff), len(leftover), len(not_in_export)))
    if mismatch:
        print('\n=== MISMATCH (wrong actionmap - FIX THESE) ===')
        for action, amap, where in mismatch:
            print('  %s: MOZA=[%s]  GAME=[%s]' % (action, amap, where))
    if input_diff:
        print('\n=== INPUT-DIFF (the game holds a different input) ===')
        for action, amap, wanted, held in input_diff:
            print('  %s / %s: MOZA=[%s]  GAME=[%s]' % (amap, action, wanted, held))
    if leftover:
        print('\n=== LEFTOVER (bound in the game, not in MOZA.xml - still fires) ===')
        for action, amap, held in sorted(leftover, key=lambda x: (x[1], x[0])):
            print('  %s / %s: GAME=[%s]' % (amap, action, held))
    if not_in_export:
        print('\n=== NOT-IN-EXPORT (game default OR dropped - verify the ones that matter) ===')
        for action, amap in not_in_export:
            print('  %s: MOZA=[%s]' % (action, amap))
    problems = len(mismatch) + len(input_diff) + len(leftover)
    print()
    print('The game holds exactly what MOZA.xml declares.' if not problems
          else '%d problem(s) - see above.' % problems)
    return 1 if problems else 0


if __name__ == '__main__':
    sys.exit(main())
