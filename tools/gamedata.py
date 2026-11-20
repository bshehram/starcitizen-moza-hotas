#!/usr/bin/env python3
"""gamedata.py - read Star Citizen's own control definitions straight out of Data.p4k.

The game ships its authoritative list of bindable actions as
    Data\\Libs\\Config\\defaultProfile.xml      (every action, its actionmap, its default bindings)
    Data\\Localization\\english\\global.ini     (the in-game labels / descriptions)
packed inside the ~160 GB Data.p4k. This tool reads just those two entries (read-only, a few
seconds) and does two jobs:

  catalogue   Regenerate reference/SC_KEYBINDS_DATABASE_v<major.minor>.md - every bindable action
              grouped by its TRUE actionmap, with label, description and default bindings.
              Older SC_/STARBINDER_ snapshots in reference/ are removed.

  check       Pre-flight MOZA.xml against the installed build, no game launch needed:
                UNKNOWN    action name does not exist in this build        (binding is dead)
                WRONG-MAP  action exists, but not in that actionmap        (game drops it)
                GHOST      a game-default joystick binding the profile does not override.
                           Defaults land on joystick 1 (js1), so a ghost on a button the
                           profile also uses fires BOTH actions.
              Exit code is non-zero if any UNKNOWN / WRONG-MAP is found.

Usage (from the project root):
    python tools/gamedata.py check
    python tools/gamedata.py catalogue
    python tools/gamedata.py check --p4k "D:\\...\\LIVE\\Data.p4k" --mapping MOZA.xml

Requires Python 3 and a zstd decoder: Python 3.14+ has one built in; on older Pythons run
    python -m pip install zstandard
"""
import argparse
import json
import os
import re
import struct
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent          # ...\controls\mappings
LIVE = ROOT.parents[4]                                  # ...\StarCitizen\LIVE
PROFILE_ENTRY = 'Data\\Libs\\Config\\defaultProfile.xml'
LABELS_ENTRY = 'Data\\Localization\\english\\global.ini'
ZSTD_MAGIC = b'\x28\xb5\x2f\xfd'
DEVICES = ('keyboard', 'mouse', 'joystick', 'gamepad')


# --------------------------------------------------------------------------- p4k reading
def zstd_decompress(data):
    try:
        from compression import zstd                    # Python 3.14+
        return zstd.ZstdDecompressor().decompress(data)
    except ImportError:
        pass
    try:
        import zstandard
    except ImportError:
        sys.exit('No zstd decoder found. Run:  python -m pip install zstandard')
    return zstandard.ZstdDecompressor().decompressobj().decompress(data)


def read_central_directory(f):
    """Data.p4k is a ZIP64 archive; return its central directory as one bytes blob."""
    f.seek(0, os.SEEK_END)
    size = f.tell()
    tail_len = min(size, 70000)
    f.seek(size - tail_len)
    tail = f.read(tail_len)
    eocd = tail.rfind(b'PK\x05\x06')
    loc = tail.rfind(b'PK\x06\x07', 0, eocd) if eocd >= 0 else -1
    if loc < 0:
        sys.exit('Not a ZIP64 archive (no end-of-central-directory locator found).')
    f.seek(struct.unpack_from('<Q', tail, loc + 8)[0])
    rec = f.read(56)
    if rec[:4] != b'PK\x06\x06':
        sys.exit('ZIP64 end-of-central-directory record not found.')
    cd_size, cd_off = struct.unpack_from('<QQ', rec, 40)
    f.seek(cd_off)
    return f.read(cd_size)


def read_entry(f, cd, name):
    """Extract one named entry. Entries we need are zstd (method 100) or stored (method 0)."""
    raw = name.encode('utf-8')
    pos = -1
    while True:
        pos = cd.find(raw, pos + 1)
        if pos < 0:
            sys.exit('Entry not found in Data.p4k: %s' % name)
        hdr = pos - 46
        if hdr >= 0 and cd[hdr:hdr + 4] == b'PK\x01\x02' and struct.unpack_from('<H', cd, hdr + 28)[0] == len(raw):
            break
    method = struct.unpack_from('<H', cd, hdr + 10)[0]
    csize, usize = struct.unpack_from('<II', cd, hdr + 20)
    elen = struct.unpack_from('<H', cd, hdr + 30)[0]
    lho = struct.unpack_from('<I', cd, hdr + 42)[0]
    extra = cd[pos + len(raw):pos + len(raw) + elen]
    p = 0
    while p + 4 <= len(extra):                          # ZIP64 extra field holds the real sizes/offset
        hid, hlen = struct.unpack_from('<HH', extra, p)
        if hid == 0x0001:
            q = p + 4
            if usize == 0xFFFFFFFF:
                usize = struct.unpack_from('<Q', extra, q)[0]
                q += 8
            if csize == 0xFFFFFFFF:
                csize = struct.unpack_from('<Q', extra, q)[0]
                q += 8
            if lho == 0xFFFFFFFF:
                lho = struct.unpack_from('<Q', extra, q)[0]
            break
        p += 4 + hlen
    f.seek(lho)
    local = f.read(30)
    nlen, xlen = struct.unpack_from('<HH', local, 26)
    f.seek(lho + 30 + nlen + xlen)
    data = f.read(csize)
    if method == 0:
        return data[:usize]
    if method == 100:
        if data[:4] != ZSTD_MAGIC:
            sys.exit('%s is not plain zstd in this build (encrypted?) - this tool cannot read it.' % name)
        return zstd_decompress(data)
    sys.exit('%s uses unsupported compression method %d.' % (name, method))


def cryxml_to_tree(buf):
    """CryXmlB (CIG's binary XML) -> ElementTree root. Plain-text XML is passed through."""
    if buf[:7] != b'CryXmlB':
        return ET.fromstring(buf)
    (_flen, node_off, node_cnt, attr_off, attr_cnt, child_off, child_cnt,
     str_off, str_size) = struct.unpack_from('<9I', buf, 8)
    strtab = buf[str_off:str_off + str_size]

    def s(off):
        return strtab[off:strtab.find(b'\x00', off)].decode('utf-8', 'replace')

    attrs = [struct.unpack_from('<II', buf, attr_off + i * 8) for i in range(attr_cnt)]
    children = struct.unpack_from('<%di' % child_cnt, buf, child_off) if child_cnt else ()
    elems, kids = [], []
    for i in range(node_cnt):
        name_o, content_o, acnt, ccnt, _parent, first_attr, first_child, _res = struct.unpack_from(
            '<IIHHiiii', buf, node_off + i * 28)
        e = ET.Element(s(name_o), {s(attrs[k][0]): s(attrs[k][1]) for k in range(first_attr, first_attr + acnt)})
        e.text = s(content_o) or None
        elems.append(e)
        kids.append(children[first_child:first_child + ccnt])
    for e, ks in zip(elems, kids):
        for k in ks:
            e.append(elems[k])
    return elems[0]


def load_game_data(p4k):
    if not p4k.exists():
        sys.exit('Data.p4k not found: %s  (pass --p4k)' % p4k)
    with open(p4k, 'rb') as f:
        cd = read_central_directory(f)
        profile = cryxml_to_tree(read_entry(f, cd, PROFILE_ENTRY))
        labels_raw = read_entry(f, cd, LABELS_ENTRY)
    labels = {}
    for line in labels_raw.decode('utf-8-sig', 'replace').splitlines():
        key, sep, val = line.partition('=')
        if sep:
            labels[key.split(',')[0].strip().lower()] = val.strip()
    return profile, labels


def build_info(p4k):
    manifest = p4k.parent / 'build_manifest.id'
    try:
        d = json.loads(manifest.read_text(encoding='utf-8'))['Data']
    except (OSError, ValueError, KeyError):
        return {'short': 'unknown', 'long': 'unknown build (no build_manifest.id next to Data.p4k)'}
    m = re.search(r'(\d+\.\d+)', d.get('Branch', '')) or re.search(r'(\d+\.\d+)', d.get('Version', ''))
    return {
        'short': m.group(1) if m else 'unknown',
        'long': 'build %s, branch %s, change %s, built %s' % (
            d.get('Version', '?'), d.get('Branch', '?'), d.get('RequestedP4ChangeNum', '?'), d.get('BuildDateStamp', '?')),
    }


# --------------------------------------------------------------------------- model
def default_binds(action, dev):
    """Default inputs for one device: the attribute plus any <device> child elements."""
    out = []
    v = action.get(dev)
    if v and v.strip():
        out.append(v.strip())
    for ch in action.findall(dev):
        for node in [ch] + ch.findall('inputdata'):
            i = node.get('input')
            if i and i.strip():
                out.append(i.strip())
    return out


def activation(action):
    mode = action.get('activationMode')
    if mode:
        return mode
    flags = [n[2:].lower() for n in ('onPress', 'onHold', 'onRelease') if action.get(n) == '1']
    return '+'.join(flags)


def game_maps(profile):
    """[(mapname, map_element, [action_element, ...]), ...] in game order."""
    return [(am.get('name'), am, am.findall('action')) for am in profile.findall('actionmap')]


# --------------------------------------------------------------------------- catalogue
def cmd_catalogue(args):
    profile, labels = load_game_data(args.p4k)
    info = build_info(args.p4k)

    def loc(key):
        if not key:
            return ''
        return labels.get(key[1:].lower(), '') if key.startswith('@') else key

    def cell(text):
        return re.sub(r'\s+', ' ', (text or '').replace('\\n', ' ')).replace('|', '\\|').strip()

    def slug(text):
        return re.sub(r'-{2,}', '-', re.sub(r'[^a-z0-9 _-]', '', text.lower()).replace(' ', '-')).strip('-')

    maps = game_maps(profile)
    total = sum(len(a) for _, _, a in maps)
    out = [
        '# Star Citizen - Master Keybinding Reference (all bindable actions)',
        '',
        '> Every action the installed game build defines, grouped by its **actionmap** - the name that goes in',
        '> `<actionmap name="...">` in a profile XML. An action placed in any other actionmap is silently dropped.',
        '> **Source:** the game\'s own `Data\\Libs\\Config\\defaultProfile.xml` + English `global.ini`, read from `Data.p4k`.',
        '> **Game build:** Star Citizen Alpha **%s** (%s).' % (info['short'], info['long']),
        '> **Actions:** %d entries across %d actionmaps.' % (total, len(maps)),
        '>',
        '> `Action` is the internal name for `<action name="...">`. The default columns are what the game binds',
        '> out of the box; **joystick defaults apply to joystick 1 (`js1`)** and stay live under a custom profile',
        '> unless that profile rebinds or clears the action. Actions with no label are hidden from the in-game',
        '> Keybindings menu. Regenerate with `python tools/gamedata.py catalogue`.',
        '',
        '## Contents',
        '',
    ]
    for name, am, actions in maps:
        title = cell(loc(am.get('UILabel')))
        out.append('- [`%s`](#%s)%s (%d)' % (name, slug(name), ' - ' + title if title else '', len(actions)))
    out.append('')
    for name, am, actions in maps:
        title = cell(loc(am.get('UILabel')))
        out += ['## %s' % name, '']
        if title:
            out += ['*In-game group: %s*' % title, '']
        out += ['| Action | In-Game Label | Description | Keyboard / Mouse | Joystick | Gamepad | Activation |',
                '| --- | --- | --- | --- | --- | --- | --- |']
        for a in actions:
            kbm = default_binds(a, 'keyboard') + default_binds(a, 'mouse')
            out.append('| `%s` | %s | %s | %s | %s | %s | %s |' % (
                a.get('name'),
                cell(loc(a.get('UILabel'))) or '-',
                cell(loc(a.get('UIDescription'))),
                cell(', '.join(kbm)), cell(', '.join(default_binds(a, 'joystick'))),
                cell(', '.join(default_binds(a, 'gamepad'))), activation(a)))
        out.append('')

    ref = ROOT / 'reference'
    target = ref / ('SC_KEYBINDS_DATABASE_v%s.md' % info['short'])
    target.write_text('\n'.join(out), encoding='utf-8', newline='\n')
    for old in list(ref.glob('SC_KEYBINDS_DATABASE_v*.md')) + list(ref.glob('STARBINDER_KEYBINDS_DATABASE_v*.md')):
        if old != target:
            print('Removing old snapshot: %s' % old.name)
            old.unlink()
    print('Wrote %s  (%d actions, %d actionmaps, %s)' % (target, total, len(maps), info['long']))
    return 0


# --------------------------------------------------------------------------- check
def cmd_check(args):
    profile, _labels = load_game_data(args.p4k)
    info = build_info(args.p4k)
    maps = game_maps(profile)
    where = {}                                           # action -> [maps it is defined in]
    in_map = {}                                          # (map, action) -> element
    for name, _am, actions in maps:
        for a in actions:
            where.setdefault(a.get('name'), []).append(name)
            in_map[(name, a.get('name'))] = a

    mroot = ET.parse(args.mapping).getroot()
    bound, used = set(), {}                              # used: js input -> ['map/action', ...]
    unknown, wrong, ok = [], [], 0
    for am in mroot.iter('actionmap'):
        for a in am.findall('action'):
            key = (am.get('name'), a.get('name'))
            bound.add(key)
            for r in a.findall('rebind'):
                inp = (r.get('input') or '').strip()
                if inp and not inp.endswith('_'):        # "js1_ " (stripped: "js1_") is a cleared binding
                    used.setdefault(inp, []).append('%s/%s' % key)
            if key[1] not in where:
                unknown.append(key)
            elif key not in in_map:
                wrong.append((key, where[key[1]]))
            else:
                ok += 1

    print('Game:    Star Citizen Alpha %s (%s)' % (info['short'], info['long']))
    print('Mapping: %s' % args.mapping)
    print('')
    print('OK: %d   UNKNOWN: %d   WRONG-MAP: %d' % (ok, len(unknown), len(wrong)))
    for m, a in unknown:
        print('  UNKNOWN    %s / %s  - no such action in this build' % (m, a))
    for (m, a), maps_ in wrong:
        print('  WRONG-MAP  %s / %s  - the game defines it in: %s' % (m, a, ', '.join(maps_)))

    colliding, quiet = [], []
    for name, _am, actions in maps:
        for a in actions:
            if (name, a.get('name')) in bound:
                continue
            for j in default_binds(a, 'joystick'):
                clash = used.get('js1_' + j.split('+')[-1], [])
                (colliding if clash else quiet).append((name, a.get('name'), j, activation(a), clash))
    print('')
    print('GHOST defaults on an input this profile also binds (both fire where both maps are active): %d' % len(colliding))
    for m, a, j, mode, clash in colliding:
        print('  js1_%-10s %s / %s (%s)  <->  %s' % (j, m, a, mode or '-', '; '.join(clash)))
    print('')
    print('Other un-overridden joystick defaults (input not otherwise used by this profile): %d' % len(quiet))
    for m, a, j, mode, _clash in quiet:
        print('  js1_%-10s %s / %s (%s)' % (j, m, a, mode or '-'))
    return 1 if (unknown or wrong) else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('command', choices=('catalogue', 'check'))
    ap.add_argument('--p4k', type=Path, default=LIVE / 'Data.p4k', help='path to Data.p4k (default: this install)')
    ap.add_argument('--mapping', type=Path, default=ROOT / 'MOZA.xml', help='profile to check (default: MOZA.xml)')
    args = ap.parse_args()
    return cmd_catalogue(args) if args.command == 'catalogue' else cmd_check(args)


if __name__ == '__main__':
    sys.exit(main())
