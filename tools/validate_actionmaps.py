"""validate_actionmaps.py - prove the running game kept every binding in MOZA.xml, using the game's
own normalized export as the oracle.

WHY THIS EXISTS
  An action bound under the wrong actionmap is silently dropped by the game - that is how camera
  bindings once ended up doing nothing. `tools/gamedata.py check` catches that BEFORE you launch, by
  reading CIG's defaultProfile.xml out of Data.p4k. This script is the other half: proof that the
  RUNNING game kept each binding. The game writes a normalized copy of whatever profile is currently
  loaded to:

      ...\\StarCitizen\\LIVE\\user\\client\\0\\Profiles\\default\\actionmaps.xml

  Two facts make that file a perfect validator:
    1. The game files each ACCEPTED action under its TRUE actionmap.
    2. The game DROPS any action whose actionmap is wrong (or whose binding it rejects).
  So: load your profile in-game (Options > Keybindings, or `pp_rebindkeys MOZA.xml`), then run this.
    - MISMATCH      = the action is in the export under a DIFFERENT map -> MOZA.xml is wrong, fix it.
    - NOT-IN-EXPORT = the game did not keep this binding. Either it equals an SC default (benign) or
                      it was DROPPED (wrong map / rejected binding). Verify the ones that matter.
    - OK            = MOZA's actionmap matches the game's filing.

USAGE (from the project root; any OS with Python 3.8+, no extra packages):
    python tools/validate_actionmaps.py
    python tools/validate_actionmaps.py --profile /path/to/actionmaps.xml

Exit code is non-zero if any MISMATCH is found (handy for a quick gate).
"""

import argparse
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent           # ...\controls\mappings
CLIENT0 = ROOT.parent.parent                            # ...\user\client\0 when run in the game folder


def actionmaps(path):
    """Yield (actionmap name, action name) pairs. Structure-agnostic: MOZA.xml is
    ActionMaps>actionmap, the game export is ActionMaps>ActionProfiles>actionmap."""
    for m in ET.parse(path).getroot().iter('actionmap'):
        for a in m.findall('action'):
            yield m.get('name'), a.get('name')


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

    # Authoritative lookup: action name -> actionmaps it appears in (from the game export).
    auth = {}
    for amap, action in actionmaps(args.profile):
        auth.setdefault(action, []).append(amap)

    # Every (actionmap, action) pair MOZA.xml declares. Some action names exist in more than one
    # actionmap (a ship copy and a ground-vehicle copy of v_yaw, v_view_yaw, ...), so an export entry
    # under another map is only a MISMATCH if MOZA.xml does not itself declare that other copy.
    moza = list(actionmaps(args.mapping))
    moza_pairs = set(moza)

    ok, mismatch, not_in_export = 0, [], []
    for amap, action in moza:
        if action not in auth:
            not_in_export.append((action, amap))
        elif amap in auth[action]:
            ok += 1
        else:
            unclaimed = [m for m in auth[action] if (m, action) not in moza_pairs]
            if unclaimed:
                mismatch.append((action, amap, ','.join(unclaimed)))
            else:
                not_in_export.append((action, amap))

    print('Profile (oracle): %s' % args.profile)
    print('Mapping:          %s' % args.mapping)
    print()
    print('OK (map matches game): %d   MISMATCH: %d   NOT-IN-EXPORT: %d'
          % (ok, len(mismatch), len(not_in_export)))
    if mismatch:
        print('\n=== MISMATCH (wrong actionmap - FIX THESE) ===')
        for action, amap, game in mismatch:
            print('  %s: MOZA=[%s]  GAME=[%s]' % (action, amap, game))
    if not_in_export:
        print('\n=== NOT-IN-EXPORT (game default OR dropped - verify the ones that matter) ===')
        for action, amap in not_in_export:
            print('  %s: MOZA=[%s]' % (action, amap))
    print()
    print('No actionmap mismatches against the game\'s filing.' if not mismatch
          else '%d mismatch(es) - see above.' % len(mismatch))
    return 1 if mismatch else 0


if __name__ == '__main__':
    sys.exit(main())
