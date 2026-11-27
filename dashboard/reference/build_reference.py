#!/usr/bin/env python3
"""build_reference.py - rebuild the dashboard's reference tables from the installed game's files.

Writes four files next to this script:

  locations.json    every location code the game log can print -> display name, kind, body, system,
                    and a shared `place` id (quantum targets, inventory locations, route start names)
  resources.json    the resource id in a commodity sale or purchase line -> the commodity's name
  ores.json         per ore: scan value per rock and per cluster size, look-alikes, rarity tier,
                    fixed quality values, where it spawns; plus `spots` (what spawns at each place)
  refineries.json   refining methods (from the game) and yield bonus by station and ore
                    (player-reported, from refineries.hand.json)

Game facts are read from the installed build: `Data\\Game2.dcb` (the game's record database),
`global.ini` (English text) and the solar-system object containers (`.socpak`), all inside
Data.p4k, read-only.

Generated and hand-entered data are kept apart by file:
  * `<name>.json` is output only. Every run rebuilds it from the game files plus `<name>.hand.json`.
  * `<name>.hand.json` holds everything entered by hand (community figures, things seen in the log or
    on screen, things the player said). This script only reads it. An entry there with the same key
    as a generated one replaces it (locations, resources, refinery stations) or replaces just the
    fields it gives (ores); a `spots` entry in ores.hand.json adds a place whose rock mix is then
    read from the game.
Two guards stop a run from losing anything typed into an output by mistake:
  * same build and same version of this script as the file on disk (`_meta.change`, `_meta.generator`):
    the output is then fully determined, so an entry that differs from what would be generated, or
    that would disappear, was edited by hand; nothing is written and the keys are listed;
  * otherwise: an entry whose `src` is not "game" and that would disappear is reported the same way.
Keys the hand file supplied (listed in `_meta.hand_keys`, `_meta.hand_patterns`) are exempt, so
deleting an entry from a hand file just deletes it. `--force` overrides both guards. A run that
changes nothing keeps the old `generated` date, so a re-run on the same build is byte-identical.

Usage (from the project root):
    python dashboard/reference/build_reference.py           rebuild the four files
    python dashboard/reference/build_reference.py --check   rebuild in memory, report differences, write nothing
    python dashboard/reference/build_reference.py --p4k "D:\\...\\LIVE\\Data.p4k"

Needs the game installed and a zstd decoder (Python 3.14+, or `python -m pip install zstandard`).
The dashboard itself only reads the JSON files, with the standard library.
"""
import argparse
import datetime
import hashlib
import json
import re
import struct
import sys
import zlib
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent                  # ...\mappings\dashboard\reference
ROOT = HERE.parent.parent                               # ...\mappings
sys.path.insert(0, str(ROOT / 'tools'))
import gamedata  # noqa: E402  (the repo's Data.p4k reader: central directory, zstd, CryXmlB)

DCB_ENTRY = 'Data\\Game2.dcb'
SYSTEM_ROOTS = ('Data\\ObjectContainers\\PU\\system\\stanton\\stantonsystem.socpak',
                'Data\\ObjectContainers\\PU\\system\\pyro\\pyrosystem.socpak',
                'Data\\ObjectContainers\\PU\\system\\nyx\\nyxsystem.socpak')
OUTPUTS = ('locations', 'resources', 'ores', 'refineries', 'controls')
MAIN_MAP = {'locations': 'locations', 'resources': 'resources', 'ores': 'ores', 'refineries': 'stations',
            'controls': 'modes'}
# NOT WIRED YET (round 2, stopped 2026-11-27 before they were finished and tested): build_ships,
# fetch_snapshots and build_prices below exist but no output uses them, so a normal run never goes
# online. See dashboard/data/handoff/activity_survey.md for where that work stopped.
SOURCES = {
    'game': 'Read from the installed game files for this build: Data\\Game2.dcb records, '
            'Data\\Localization\\english\\global.ini, and the solar-system object containers (.socpak) '
            'in Data.p4k.',
    'ref': 'A community source, named and dated on the entry.',
    'seen': "Seen in the game's own output (Game.log lines or the in-game screen); the entry says what.",
    'user': 'Told to an earlier session by the player.',
}
TODAY = datetime.date.today().isoformat()


# =========================================================================== Data.p4k access
def _zip64(extra, usize, csize, lho):
    p = 0
    while p + 4 <= len(extra):
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
    return usize, csize, lho


def index_central_directory(cd, keep):
    """{lower-case name: (name, method, csize, usize, local header offset)} for entries `keep` accepts."""
    out = {}
    pos, n = 0, len(cd)
    while pos < n:
        if cd[pos:pos + 4] != b'PK\x01\x02':
            pos = cd.find(b'PK\x01\x02', pos)
            if pos < 0:
                break
        method = struct.unpack_from('<H', cd, pos + 10)[0]
        csize, usize = struct.unpack_from('<II', cd, pos + 20)
        nlen, xlen, clen = struct.unpack_from('<HHH', cd, pos + 28)
        lho = struct.unpack_from('<I', cd, pos + 42)[0]
        name = cd[pos + 46:pos + 46 + nlen].decode('utf-8', 'replace')
        if keep(name):
            usize, csize, lho = _zip64(cd[pos + 46 + nlen:pos + 46 + nlen + xlen], usize, csize, lho)
            out[name.lower()] = (name, method, csize, usize, lho)
        pos += 46 + nlen + xlen + clen
    return out


def _decompress(method, data):
    if method == 0:
        return data
    if method == 8:
        return zlib.decompress(data, -15)
    if method == 100:
        return gamedata.zstd_decompress(data)
    raise ValueError('unsupported compression method %d' % method)


class Archive:
    """Read-only access to Data.p4k: whole entries, and single files inside a stored .socpak."""

    def __init__(self, path):
        self.f = open(path, 'rb')
        cd = gamedata.read_central_directory(self.f)
        self.idx = index_central_directory(
            cd, lambda n: n.lower().endswith('.socpak') or n == DCB_ENTRY or n == gamedata.LABELS_ENTRY)

    def close(self):
        self.f.close()

    def _data_start(self, base, lho):
        self.f.seek(base + lho)
        nlen, xlen = struct.unpack_from('<HH', self.f.read(30), 26)
        return base + lho + 30 + nlen + xlen

    def read(self, name):
        e = self.idx.get(name.lower().replace('/', '\\'))
        if not e:
            return None
        _n, method, csize, _usize, lho = e
        self.f.seek(self._data_start(0, lho))
        return _decompress(method, self.f.read(csize))

    def socpak_files(self, socpak):
        """{inner name: (method, csize, data offset)} for a stored .socpak, without reading it whole."""
        e = self.idx.get(socpak.lower().replace('/', '\\'))
        if not e or e[1] != 0:
            return None, None
        _n, _m, csize, _u, lho = e
        base = self._data_start(0, lho)
        tail_len = min(csize, 66000)
        self.f.seek(base + csize - tail_len)
        tail = self.f.read(tail_len)
        eocd = tail.rfind(b'PK\x05\x06')
        if eocd < 0:
            return None, None
        cd_size, cd_off = struct.unpack_from('<II', tail, eocd + 12)
        if cd_off == 0xFFFFFFFF or cd_size == 0xFFFFFFFF:
            loc = tail.rfind(b'PK\x06\x07', 0, eocd)
            self.f.seek(base + struct.unpack_from('<Q', tail, loc + 8)[0])
            cd_size, cd_off = struct.unpack_from('<QQ', self.f.read(56), 40)
        self.f.seek(base + cd_off)
        inner = index_central_directory(self.f.read(cd_size), lambda n: True)
        return base, inner

    def socpak_read(self, base, entry):
        _n, method, csize, _u, lho = entry
        self.f.seek(self._data_start(base, lho))
        return _decompress(method, self.f.read(csize))

    def extract_to(self, name, fh):
        """Stream one zstd entry into an open file in 4 MB pieces (keeps a 341 MB entry out of memory)."""
        e = self.idx.get(name.lower().replace('/', '\\'))
        if not e:
            return False
        _n, method, csize, _usize, lho = e
        self.f.seek(self._data_start(0, lho))
        try:
            import zstandard
            dobj = zstandard.ZstdDecompressor().decompressobj()
        except ImportError:
            dobj = None
        if method != 100 or dobj is None:
            fh.write(_decompress(method, self.f.read(csize)))
            return True
        left = csize
        while left > 0:
            chunk = self.f.read(min(left, 4 << 20))
            if not chunk:
                break
            left -= len(chunk)
            fh.write(dobj.decompress(chunk))
        return True


# =========================================================================== DataCore (Game2.dcb, v8)
_SIZES = {0x1: 1, 0x2: 1, 0x3: 2, 0x4: 4, 0x5: 8, 0x6: 1, 0x7: 2, 0x8: 4, 0x9: 8, 0xA: 4, 0xB: 4,
          0xC: 8, 0xD: 4, 0xE: 16, 0xF: 4, 0x110: 8, 0x210: 8, 0x310: 20}
_FMT = {0x1: '<?', 0x2: '<b', 0x3: '<h', 0x4: '<i', 0x5: '<q', 0x6: '<B', 0x7: '<H', 0x8: '<I',
        0x9: '<Q', 0xB: '<f', 0xC: '<d'}


def guid_str(b16):
    """A DataCore GUID as the game prints it in its logs and object containers."""
    a1, a2, a3 = struct.unpack_from('<HHI', b16, 0)
    rest = b16[8:16][::-1].hex()
    return '%08x-%04x-%04x-%s-%s' % (a3, a2, a1, rest[:4], rest[4:])


class DataCore:
    """Minimal reader for DataCore version 8. Records come out as nested dicts; a reference to
    another record comes out as that record's name."""

    def __init__(self, buf):
        B = self.B = buf
        version = struct.unpack_from('<i', B, 4)[0]
        if version != 8:
            sys.exit('Game2.dcb is DataCore version %d; this reader knows version 8. The format '
                     'changed with a patch: update DataCore in build_reference.py.' % version)
        o = 16
        counts = struct.unpack_from('<26i', B, o)
        (n_struct, n_prop, n_enum, n_map, n_rec, c_bool, c_i8, c_i16, c_i32, c_i64, c_u8, c_u16, c_u32,
         c_u64, c_f32, c_f64, c_guid, c_str, c_loc, c_enum, c_strong, c_weak, c_ref, c_enumopt,
         len_text, len_blob) = counts
        o += 26 * 4
        self.structs = [struct.unpack_from('<iiHHI', B, o + i * 16) for i in range(n_struct)]
        o += n_struct * 16
        self.props = [struct.unpack_from('<iHHHH', B, o + i * 12) for i in range(n_prop)]
        o += n_prop * 12 + n_enum * 8
        maps = [struct.unpack_from('<II', B, o + i * 8) for i in range(n_map)]
        o += n_map * 8
        recs = [struct.unpack_from('<iiii16sHH', B, o + i * 36) for i in range(n_rec)]
        o += n_rec * 36
        self.arr = {}
        for dt, cnt in ((0x2, c_i8), (0x3, c_i16), (0x4, c_i32), (0x5, c_i64), (0x6, c_u8), (0x7, c_u16),
                        (0x8, c_u32), (0x9, c_u64), (0x1, c_bool), (0xB, c_f32), (0xC, c_f64), (0xE, c_guid),
                        (0xA, c_str), (0xD, c_loc), (0xF, c_enum), (0x110, c_strong), (0x210, c_weak),
                        (0x310, c_ref)):
            self.arr[dt] = o
            o += _SIZES[dt] * cnt
        o += 4 * c_enumopt
        self.text0 = o
        o += len_text
        self.blob0 = o
        o += len_blob
        self._pc, self._sc = {}, {}
        self.mstart = {}
        for cnt, si in maps:
            self.mstart.setdefault(si, o)
            o += cnt * self.ssize(si)
        if o != len(B):
            sys.exit('Game2.dcb layout check failed (data ends at %d, file is %d bytes): the format '
                     'changed with a patch.' % (o, len(B)))
        self.records, self.by_raw, self.by_name = [], {}, {}
        for r in recs:
            rec = {'name': self.blob(r[0]), 'file': self.text(r[1]), 'struct': self.struct_name(r[3]),
                   'si': r[3], 'ii': r[5], 'guid': guid_str(r[4])}
            self.records.append(rec)
            self.by_raw[r[4]] = rec
            self.by_name[rec['name']] = rec
        self.by_guid = {r['guid']: r for r in self.records}

    def _cstr(self, base, off):
        # find(), not index(): works on bytes and on an mmap alike
        return self.B[base + off:self.B.find(b'\0', base + off)].decode('utf-8', 'replace')

    def blob(self, off):
        return self._cstr(self.blob0, off)

    def text(self, off):
        return self._cstr(self.text0, off)

    def struct_name(self, si):
        return self.blob(self.structs[si][0])

    def all_props(self, si):
        if si not in self._pc:
            _n, parent, cnt, first, _ = self.structs[si]
            self._pc[si] = (self.all_props(parent) if parent != -1 else []) + \
                [self.props[first + k] for k in range(cnt)]
        return self._pc[si]

    def ssize(self, si):
        if si not in self._sc:
            self._sc[si] = sum(8 if conv else (self.ssize(psi) if dt == 0x10 else _SIZES[dt])
                               for (_pn, psi, dt, conv, _) in self.all_props(si))
        return self._sc[si]

    def _scalar(self, dt, off):
        if dt in _FMT:
            v = struct.unpack_from(_FMT[dt], self.B, off)[0]
            return float(round(v, 6)) if dt == 0xB else v
        if dt in (0xA, 0xD, 0xF):
            return self.text(struct.unpack_from('<i', self.B, off)[0])
        if dt == 0xE:
            return guid_str(self.B[off:off + 16])
        raise ValueError(dt)

    def _ref(self, off):
        g = self.B[off + 4:off + 20]
        if g == b'\0' * 16:
            return None
        rec = self.by_raw.get(g)
        return rec['name'] if rec else guid_str(g)

    def _inst(self, si, ii, depth):
        return self._struct(si, self.mstart[si] + ii * self.ssize(si), depth)

    def record(self, rec, depth=8):
        if isinstance(rec, str):
            rec = self.by_name.get(rec)
            if rec is None:
                return None
        return self._inst(rec['si'], rec['ii'], depth)

    def _struct(self, si, off, depth):
        out = {'_type': self.struct_name(si)}
        if depth < 0:
            return out
        B = self.B
        for (pn, psi, dt, conv, _) in self.all_props(si):
            name = self.blob(pn)
            if not conv:
                if dt == 0x10:
                    out[name] = self._struct(psi, off, depth - 1)
                    off += self.ssize(psi)
                    continue
                if dt == 0x110:
                    s, i = struct.unpack_from('<II', B, off)
                    out[name] = None if s == 0xFFFFFFFF else self._inst(s, i, depth - 1)
                elif dt == 0x210:
                    out[name] = None
                elif dt == 0x310:
                    out[name] = self._ref(off)
                else:
                    out[name] = self._scalar(dt, off)
                off += _SIZES[dt]
                continue
            cnt, first = struct.unpack_from('<ii', B, off)
            off += 8
            vals = []
            for idx in range(first, first + cnt):
                if dt == 0x10:
                    vals.append(self._inst(psi, idx, depth - 1))
                elif dt == 0x110:
                    s, i = struct.unpack_from('<II', B, self.arr[0x110] + idx * 8)
                    vals.append(None if s == 0xFFFFFFFF else self._inst(s, i, depth - 1))
                elif dt == 0x210:
                    vals.append(None)
                elif dt == 0x310:
                    vals.append(self._ref(self.arr[0x310] + idx * 20))
                else:
                    vals.append(self._scalar(dt, self.arr[dt] + idx * _SIZES[dt]))
            out[name] = vals
        return out


# =========================================================================== small helpers
def slug(text):
    return re.sub(r'-{2,}', '-', re.sub(r'[^a-z0-9]+', '-', text.lower())).strip('-')


def r3(x):
    """Round a float32-ish value for output (24.299999 -> 24.3); integers stay integers."""
    if x is None:
        return None
    v = round(float(x), 3)
    return int(v) if v == int(v) else v


def short_record(name):
    return name.split('.', 1)[1] if '.' in name else name


def valid_name(s):
    return bool(s) and not s.startswith('<=') and not s.startswith('@')


class Game:
    """Everything read from the installed build, loaded once."""

    def __init__(self, p4k):
        print('Reading %s ...' % p4k)
        self.info = gamedata.build_info(p4k)
        self.build = self._build_id(p4k)
        self.arc = Archive(p4k)
        # Game2.dcb is about 341 MB unpacked. It is streamed to a temporary file and memory-mapped,
        # so the pages are file-backed (the OS can drop and reread them) rather than held in the
        # process: memory is tight on this PC while the game runs.
        import mmap
        import tempfile
        self._tmp = tempfile.NamedTemporaryFile(prefix='scdash-dcb-', suffix='.tmp', delete=False)
        ok = self.arc.extract_to(DCB_ENTRY, self._tmp)
        self._tmp.flush()
        if not ok:
            self.close()
            sys.exit('Data\\Game2.dcb not found in %s' % p4k)
        self._map = mmap.mmap(self._tmp.fileno(), 0, access=mmap.ACCESS_READ)
        self.dc = DataCore(self._map)
        labels_raw = self.arc.read(gamedata.LABELS_ENTRY)
        self.labels = {}
        for line in labels_raw.decode('utf-8-sig', 'replace').splitlines():
            key, sep, val = line.partition('=')
            if sep:
                self.labels[key.split(',')[0].strip().lower()] = val.strip()
        print('  Game2.dcb: %d records; global.ini: %d strings' % (len(self.dc.records), len(self.labels)))

    def close(self):
        import os
        self.dc = None
        if getattr(self, '_map', None) is not None:
            self._map.close()
            self._map = None
        if getattr(self, '_tmp', None) is not None:
            self._tmp.close()
            try:
                os.remove(self._tmp.name)
            except OSError:
                pass
            self._tmp = None
        self.arc.close()

    @staticmethod
    def _build_id(p4k):
        try:
            d = json.loads((p4k.parent / 'build_manifest.id').read_text(encoding='utf-8'))['Data']
            return {'version': d.get('Version', '?'), 'change': d.get('RequestedP4ChangeNum', '?'),
                    'branch': d.get('Branch', '?')}
        except (OSError, ValueError, KeyError):
            return {'version': 'unknown', 'change': 'unknown', 'branch': 'unknown'}

    def label(self, key):
        if not key:
            return ''
        if key.startswith('@'):
            return self.labels.get(key[1:].lower(), '')
        return key


# =========================================================================== object-container hierarchy
def walk_hierarchy(game):
    """Every Child entity under the three system roots, following every external .socpak once.
    Returns a list of dicts: entity, smr (star-map record guid or None), cls, pak, parent (index), in."""
    ents = []
    seen_paks = set()
    queue = [(r, None) for r in SYSTEM_ROOTS]
    qi = 0
    while qi < len(queue):
        pak, parent = queue[qi]
        qi += 1
        key = pak.lower().replace('/', '\\')
        if key in seen_paks:
            continue
        seen_paks.add(key)
        stem = key.rsplit('\\', 1)[-1][:-len('.socpak')]
        base, inner = game.arc.socpak_files(key)
        if not inner or (stem + '.xml') not in inner:
            continue
        root = gamedata.cryxml_to_tree(game.arc.socpak_read(base, inner[stem + '.xml']))

        def visit(node, par):
            for coc in node.findall('ChildObjectContainers'):
                for ch in coc.findall('Child'):
                    me = len(ents)
                    # a few names carry a stray trailing space in the game data; the log's
                    # "selected point <CODE> as ..." cannot show it, so keys are stripped
                    ents.append({'entity': (ch.get('entityName') or '').strip(), 'smr': ch.get('starMapRecord'),
                                 'cls': ch.get('class'), 'pak': (ch.get('name') or '').lower().replace('/', '\\'),
                                 'parent': par, 'in': stem,
                                 'pos': _floats(ch.get('pos'), 3, (0.0, 0.0, 0.0)),
                                 'rot': _floats(ch.get('rot'), 4, (1.0, 0.0, 0.0, 0.0))})
                    if ch.get('external') == '1' and ents[me]['pak'].endswith('.socpak'):
                        queue.append((ents[me]['pak'], me))
                    visit(ch, me)
        visit(root, parent)
    # global positions: a child's pos and rot are relative to its parent container, and a parent is
    # always listed before its children, so one forward pass composes the transforms
    for e in ents:
        p = e['parent']
        if p is None:
            e['gpos'], e['grot'] = e['pos'], e['rot']
        else:
            pe = ents[p]
            r = _qrot(pe['grot'], e['pos'])
            e['gpos'] = (pe['gpos'][0] + r[0], pe['gpos'][1] + r[1], pe['gpos'][2] + r[2])
            e['grot'] = _qmul(pe['grot'], e['rot'])
    print('  object containers: %d read, %d entities' % (len(seen_paks), len(ents)))
    return ents


def _floats(text, n, default):
    try:
        v = tuple(float(x) for x in (text or '').split(','))
        return v if len(v) == n else default
    except ValueError:
        return default


def _qmul(a, b):
    aw, ax, ay, az = a
    bw, bx, by, bz = b
    return (aw * bw - ax * bx - ay * by - az * bz, aw * bx + ax * bw + ay * bz - az * by,
            aw * by - ax * bz + ay * bw + az * bx, aw * bz + ax * by - ay * bx + az * bw)


def _qrot(q, v):
    """Rotate vector v by unit quaternion q (w, x, y, z)."""
    w, x, y, z = q
    vx, vy, vz = v
    # t = 2 * cross(q.xyz, v); v' = v + w * t + cross(q.xyz, t)
    tx, ty, tz = 2 * (y * vz - z * vy), 2 * (z * vx - x * vz), 2 * (x * vy - y * vx)
    return (vx + w * tx + (y * tz - z * ty), vy + w * ty + (z * tx - x * tz), vz + w * tz + (x * ty - y * tx))


GUID_RE = re.compile(rb'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}')


def find_provider_presets(game, preset_guids):
    """{socpak (lower, backslashes): sorted preset names} for every system container that binds a
    HarvestableProviderPreset (planet pivots, asteroid clouds)."""
    found = {}
    for key, entry in sorted(game.arc.idx.items()):
        if not key.startswith('data\\objectcontainers\\pu\\system\\') or not key.endswith('.socpak'):
            continue
        base, inner = game.arc.socpak_files(key)
        if not inner:
            continue
        hits = set()
        for _iname, ie in sorted(inner.items()):
            body = game.arc.socpak_read(base, ie)
            if b'HarvestableProvider' not in body and b'AsteroidGasCloud' not in body:
                continue
            for m in GUID_RE.finditer(body):
                g = m.group(0).decode()
                if g in preset_guids:
                    hits.add(preset_guids[g])
        if hits:
            found[key] = sorted(hits)
    return found


# =========================================================================== locations
STAR_SYSTEM = {'StantonStar': 'Stanton', 'PyroStar': 'Pyro', 'NyxStar': 'Nyx'}
LPOINT_RE = re.compile(r'^((?:Stanton|Pyro)\d+)_L(\d)$')
SUBCLUSTER_RE = re.compile(r'^((?:Stanton|Pyro)\d+)_L(\d)_\d\d$')
# Belts and rings whose star-map record has a blank name (or no record): name from the global.ini
# key given here. The pairing of key to place is by name, not stated in the game files.
REGIONS = {
    'GlaciemRing': ('Nyx_AsteroidBelt1', 'Nyx', 'glaciemring'),
    'KeegerBelt': ('Nyx_AsteroidBelt2', 'Nyx', 'keegerbelt'),
    'OOC_AaronHalo': ('AaronHalo', 'Stanton', 'aaronhalo'),
}


# Records that are never a location the log names: hospital and clinic sub-records inside a station or
# city (a respawn there logs the station or city), and private mining-claim markers.
LEFT_OUT_KINDS = {'clinic', 'mining claim'}
# kinds that get a position (`pos`, meters in the system's own coordinates)
POS_KINDS = {'star', 'planet', 'moon', 'station', 'landing zone', 'gateway', 'field', 'lagrange point'}


class Locations:
    def __init__(self, game, ents, presets_by_pak):
        self.g = game
        self.ents = ents
        dc = game.dc
        self.types = {r['name']: dc.record(r, 0)['name'] for r in dc.records if r['struct'] == 'StarMapObjectType'}
        self.smo = {}                      # code -> info
        self.by_guid = {}
        for r in dc.records:
            if r['struct'] != 'StarMapObject':
                continue
            d = dc.record(r, 1)
            code = short_record(r['name'])
            lp = d.get('locationParams') or {}
            info = {'code': code, 'guid': r['guid'], 'file': r['file'], 'name_key': d.get('name') or '',
                    'name': game.label(d.get('name')), 'nav': d.get('navIcon'), 'type': self.types.get(d.get('type'), ''),
                    'parent': short_record(d['parent']) if d.get('parent') else None,
                    'enter': bool(lp.get('setEntityLocationOnEnter')), 'respawn': d.get('respawnLocationType')}
            self.smo[code] = info
            self.by_guid[r['guid']] = info
        # which entities point at which record
        self.ents_of = defaultdict(list)
        for i, e in enumerate(ents):
            if e['smr'] and e['smr'] in self.by_guid:
                self.ents_of[self.by_guid[e['smr']]['code']].append(i)
        self.presets_by_pak = presets_by_pak
        self.spot_codes = set()            # records that are a mining spot (fills kind 'field')
        self._body, self._system = {}, {}

    # ---------------------------------------------------------------- classification
    def is_template(self, s):
        f = s['file'].lower()
        return ('/mission_item/' in f or '/player_related/' in f or 'template' in s['code'].lower()
                or s['code'] == 'PlaceholderStarMapRecord')

    def kind(self, s):
        code, name, t, nav = s['code'], s['name'], s['type'], s['nav']
        if t == 'SolarSystem':
            return 'system'
        if t == 'Star':
            return 'star'
        if t == 'Planet':
            return 'planet'
        if t == 'Moon':
            return 'moon'
        if t == 'CardinalPoint':
            return 'orbital marker'
        if code in REGIONS:
            return 'belt'
        if t == 'LandingZone' or nav == 'LandingZone':
            return 'landing zone'
        if code.startswith('RR_JP_'):
            return 'gateway'
        if t in ('JumpPoint', 'ManmadeJumpPoint') or (t == 'Anomaly' and 'Jump Point' in name):
            return 'jump point'
        if LPOINT_RE.match(code):
            return 'field' if code in self.spot_codes else 'lagrange point'
        if SUBCLUSTER_RE.match(code):
            return 'asteroid cluster'
        if code.startswith('PrivateMiningPoint'):
            return 'mining claim'
        if code.startswith('AsteroidCluster_MiningBase'):
            return 'asteroid base'
        if t in ('Asteroid', 'Asteroid_ValidQT'):
            return 'field' if (name.startswith('Cluster ') or name.endswith(' Cluster')) else 'asteroid base'
        if s['respawn'] in ('Hospital', 'CriminalHospital') and \
                re.search(r'clinic|hospital|medstation|medical|health', name, re.I):
            return 'clinic'
        if t in ('Outpost', 'Outpost_InvalidQT'):
            return 'outpost'
        if 'Comm Array' in name:
            return 'comm array'
        if code.startswith('TransitPoint'):
            return 'transit point'
        if nav == 'Station' or name.endswith(' Station'):
            return 'station'
        if t in ('PointOfInterest', 'NavPoint', 'Anomaly', 'Manmade', 'Manmade_VisibleOnInteraction'):
            return 'point of interest'
        return 'other'

    def display_name(self, s):
        if s['code'] in REGIONS:
            return self.g.labels.get(REGIONS[s['code']][0].lower(), '')
        return s['name']

    def system(self, code):
        if code in self._system:
            return self._system[code]
        self._system[code] = None
        s = self.smo.get(code)
        out = None
        if s:
            if s['type'] == 'SolarSystem':
                out = s['name'].replace(' System', '') if valid_name(s['name']) else None
            elif code in STAR_SYSTEM:
                out = STAR_SYSTEM[code]
            elif code in REGIONS:
                out = REGIONS[code][1]
            elif s['parent']:
                out = self.system(s['parent'])
            if not out:
                for i in self.ents_of.get(code, []):
                    out = {'stantonsystem': 'Stanton', 'pyrosystem': 'Pyro', 'nyxsystem': 'Nyx'}.get(self.root_of(i))
                    if out:
                        break
        self._system[code] = out
        return out

    def root_of(self, i):
        e = self.ents[i]
        while e['parent'] is not None:
            e = self.ents[e['parent']]
        return e['in']

    def body(self, code):
        """Name of the planet or moon a place is on or at (L-point -> its planet), else a ring/belt."""
        if code in self._body:
            return self._body[code]
        self._body[code] = None
        s = self.smo.get(code)
        out = None
        if s:
            if s['type'] in ('Planet', 'Moon'):
                out = s['name']
            elif code in REGIONS:
                out = self.display_name(s)
            else:
                m = LPOINT_RE.match(code) or SUBCLUSTER_RE.match(code)
                if m and m.group(1) in self.smo:
                    out = self.smo[m.group(1)]['name']
            if not out:
                for i in self.ents_of.get(code, []):
                    p = self.ents[i]['parent']
                    while p is not None and not out:
                        e = self.ents[p]
                        a = self.by_guid.get(e['smr']) if e['smr'] else None
                        if a and a['code'] != code:
                            if a['type'] in ('Planet', 'Moon'):
                                out = a['name']
                            elif LPOINT_RE.match(a['code']):
                                out = self.body(a['code'])
                            if out or a['type'] in ('Star',):
                                break
                        p = e['parent']
                    if out:
                        break
            if not out and s['parent'] and s['parent'] not in STAR_SYSTEM:
                out = self.body(s['parent'])
            if not out:
                for i in self.ents_of.get(code, []):
                    chain = []
                    p = i
                    while p is not None:
                        chain.append(self.ents[p]['in'] + ' ' + self.ents[p]['pak'])
                        p = self.ents[p]['parent']
                    for rcode, (_k, _sys, folder) in REGIONS.items():
                        if rcode in self.smo and any(folder in c for c in chain):
                            out = self.display_name(self.smo[rcode])
                    if out:
                        break
        self._body[code] = out
        return out

    def short(self, s, kind, system):
        name = self.display_name(s)
        m = re.match(r'^([A-Z]{3})-(L\d) ', name)
        if kind == 'station' and m:
            return '%s-%s' % m.groups()
        m = re.match(r'^([A-Z]{3}) (L\d)(-[A-Z])?$', name)
        if m:
            base = '%s-%s%s' % (m.group(1), m.group(2), m.group(3) or '')
            return base + (' field' if kind == 'field' else '')
        if kind == 'field' and re.match(r'^PYR\d L\d$', name):
            return name + ' field'
        if kind == 'gateway':
            return '%s (%s)' % (name, system)
        return name

    # ---------------------------------------------------------------- build
    def build(self):
        g = self.g
        places = {}                        # code -> entry (without the key)
        for code, s in sorted(self.smo.items()):
            if self.is_template(s) or s['type'] == 'CardinalPoint':
                continue
            if code not in REGIONS and not valid_name(s['name']):
                continue
            if code in REGIONS and not valid_name(self.display_name(s)):
                continue
            if not (self.ents_of.get(code) or s['enter'] or s['type'] in ('SolarSystem', 'Star')
                    or code in REGIONS):
                continue
            system = self.system(code)
            if not system:
                continue
            kind = self.kind(s)
            if kind in LEFT_OUT_KINDS:
                continue
            places[code] = {'name': self.display_name(s), 'short': self.short(s, kind, system), 'kind': kind,
                            'body': self.body(code), 'system': system}
            if kind in POS_KINDS and self.ents_of.get(code):
                gp = self.ents[self.ents_of[code][0]]['gpos']
                places[code]['pos'] = [int(round(c)) for c in gp]
        # Aaron Halo has a container but no star-map record: add it by its entity name
        if 'OOC_AaronHalo' not in places and any(e['entity'] == 'OOC_AaronHalo' for e in self.ents):
            nm = g.labels.get('aaronhalo', '')
            if nm:
                places['OOC_AaronHalo'] = {'name': nm, 'short': nm, 'kind': 'belt', 'body': None, 'system': 'Stanton'}
        # place ids: from the short name; any id two records would share falls back to the record code
        sl = defaultdict(list)
        for code, p in places.items():
            sl[slug(p['short'])].append(code)
        for sid, codes in sl.items():
            for code in codes:
                places[code]['place'] = sid if len(codes) == 1 else slug(code)
        self.place_of_code = {c: p['place'] for c, p in places.items()}
        self.places = places

        entries = {}
        notes = {}

        def put(key, entry):
            if key and key not in entries:
                entries[key] = entry

        for code, p in places.items():
            put(code, dict(p, src='game'))
        # quantum-target family: entity names in the object containers
        ent_targets = defaultdict(set)
        for e in self.ents:
            if e['smr'] and e['smr'] in self.by_guid:
                c = self.by_guid[e['smr']]['code']
                if c in places:
                    ent_targets[e['entity']].add(c)
        if 'OOC_AaronHalo' in places:
            ent_targets['OOC_AaronHalo'].add('OOC_AaronHalo')
        skipped_ambiguous = []
        for ent, codes in sorted(ent_targets.items()):
            if ent in entries:
                continue
            if len(codes) == 1:
                put(ent, dict(places[next(iter(codes))], src='game'))
            elif len(codes) <= 6:
                put(ent, self._candidates([places[c] for c in sorted(codes)],
                                          'The game uses this code for %d places; the inventory location '
                                          'logged on arrival tells which.' % len(codes)))
            else:
                skipped_ambiguous.append((ent, len(codes)))
        # display names, as printed in "Projected Start Location is <name>" and refinery notices
        TRAVEL = {'system', 'star', 'planet', 'moon', 'landing zone', 'station', 'gateway', 'field',
                  'lagrange point', 'asteroid base', 'outpost', 'jump point', 'comm array', 'transit point',
                  'belt', 'asteroid cluster', 'point of interest', 'clinic'}
        by_name = defaultdict(list)
        for code, p in places.items():
            if p['kind'] in TRAVEL:
                by_name[p['name']].append(code)
        for name, codes in sorted(by_name.items()):
            if name in entries:
                continue
            if len(codes) == 1:
                put(name, dict(places[codes[0]], src='game'))
            elif len(codes) <= 4:
                put(name, self._candidates([places[c] for c in sorted(codes)],
                                           'Several places share this name; the code logged next to it tells which.'))
        # orbital markers OM-1 .. OM-6 (the CardinalPoint record names them Nav_<n>)
        for n in range(1, 7):
            nm = g.labels.get('nav_%d' % n)
            if nm:
                put(nm, {'name': nm, 'short': nm, 'kind': 'orbital marker', 'body': None, 'system': None,
                         'place': None, 'src': 'game',
                         'note': 'Orbital marker %d. Every planet and moon has one; the log line does not say '
                                 'which body it belongs to.' % n})
        # dynamic codes: <record>_<entity id>, from the mission and player marker records
        patterns = []
        for code, s in sorted(self.smo.items()):
            f = s['file'].lower()
            if ('/mission_item/' in f or '/player_related/' in f) and valid_name(s['name']) \
                    and 'template' not in code.lower():
                patterns.append({'prefix': code + '_', 'name': s['name'], 'kind': 'mission marker'
                                 if '/mission_item/' in f else 'player marker', 'src': 'game'})
        self.skipped_ambiguous = skipped_ambiguous
        return entries, patterns, notes

    @staticmethod
    def _candidates(ps, note):
        same = lambda k: ps[0][k] if all(p[k] == ps[0][k] for p in ps) else None  # noqa: E731
        return {'name': same('name') or ' / '.join(p['name'] for p in ps),
                'short': same('short') or ' / '.join(p['short'] for p in ps),
                'kind': same('kind') or 'other', 'body': same('body'), 'system': same('system'), 'place': None,
                'candidates': sorted(p['place'] for p in ps), 'src': 'game', 'note': note}


# =========================================================================== resources
def build_resources(game):
    dc = game.dc
    out = {}
    for r in dc.records:
        if r['struct'] != 'ResourceType':
            continue
        d = dc.record(r, 1)
        name = game.label(d.get('displayName'))
        e = {'name': name if valid_name(name) else short_record(r['name']), 'record': short_record(r['name'])}
        if d.get('refinedVersion'):
            rd = dc.record(d['refinedVersion'], 0)
            rn = game.label(rd.get('displayName')) if rd else ''
            e['refined'] = rn if valid_name(rn) else short_record(d['refinedVersion'])
        if not valid_name(name):
            e['note'] = 'No English name in global.ini; the record name is shown instead.'
        e['src'] = 'game'
        out[r['guid']] = e
    return out


# =========================================================================== ores
TIERS = ('Legendary', 'Uncommon', 'Common', 'Epic', 'Rare')     # Uncommon before Common for matching
LOOKALIKE_FRACTION = 0.01


def ore_name(game, res_record):
    """'ResourceType.Ore_Tungsten' -> 'Tungsten': the ore's English name without '(Ore)' / '(Raw)'."""
    d = game.dc.record(res_record, 1)
    if not d:
        return short_record(res_record)
    nm = game.label(d.get('displayName'))
    nm = re.sub(r'^Raw ', '', re.sub(r' \((Ore|Raw|R)\)$', '', nm)) if valid_name(nm) else ''
    return nm or re.sub(r'^(Ore_|Raw_)', '', short_record(res_record)).replace('_', ' ')


def refined_name(game, res_record):
    d = game.dc.record(res_record, 1)
    if d and d.get('refinedVersion'):
        rd = game.dc.record(d['refinedVersion'], 0)
        nm = game.label(rd.get('displayName')) if rd else ''
        return nm if valid_name(nm) else None
    return None


def build_ores(game, locs, ents, presets_by_pak):
    dc = game.dc
    # ---- elements
    elements = {}
    for r in dc.records:
        if r['struct'] != 'MineableElement' or re.search(r'template|test', r['name'], re.I):
            continue
        d = dc.record(r, 1)
        if not d.get('resourceType'):
            continue
        elements[r['name']] = {
            'ore': ore_name(game, d['resourceType']), 'resource': d['resourceType'],
            'resistance': r3(d.get('elementResistance')), 'instability': r3(d.get('elementInstability')),
            'window_midpoint': r3(d.get('elementOptimalWindowMidpoint')),
            'window_randomness': r3(d.get('elementOptimalWindowMidpointRandomness')),
            'window_thinness': r3(d.get('elementOptimalWindowThinness')),
            'explosion_multiplier': r3(d.get('elementExplosionMultiplier')),
            'cluster_factor': r3(d.get('elementClusterFactor'))}
    # ---- rocks (mineable entity classes)
    rocks = {}
    for r in dc.records:
        nm = r['name']
        if not nm.startswith('EntityClassDefinition.MineableRock_') or re.search(r'template|_test|blocker', nm, re.I):
            continue
        d = dc.record(r, 7)
        comp, sig = None, None
        for c in d.get('Components') or []:
            if not c:
                continue
            if c['_type'] == 'MineableParams':
                comp = c.get('composition')
            elif c['_type'] == 'SSCSignatureSystemParams':
                try:
                    sig = c['radarProperties']['baseSignatureParams']['signatures'][4]
                except (KeyError, IndexError, TypeError):
                    sig = None
        if not comp:
            continue
        cd = dc.record(comp, 3)
        parts = []
        for p in cd.get('compositionArray') or []:
            el = elements.get(p.get('mineableElement'))
            if not el:
                continue
            parts.append({'ore': el['ore'], 'min': r3(p['minPercentage']), 'max': r3(p['maxPercentage']),
                          'quality_scale': r3(p['qualityScale']), 'chance': r3(p['probability'])})
        if not parts:
            continue
        totals = defaultdict(float)
        for p in parts:
            totals[p['ore']] += p['max']
        primary = max(sorted(totals), key=lambda o: totals[o])
        code = short_record(nm)
        mode = 'vehicle' if '_GroundVehicle_' in code else 'hand' if '_FPS_' in code else 'ship'
        setting = 'surface' if '_Surface' in code else 'asteroid' if '_Asteroid' in code else None
        tier = next((t for t in TIERS if re.search(r'(Surface|Asteroid)%s_' % t, code)), None)
        primary_el = next((el for el in elements.values() if el['ore'] == primary), None)
        rocks[code] = {'ore': primary, 'mode': mode, 'setting': setting, 'tier': tier,
                       'signature': int(sig) if sig else None, 'composition': parts,
                       'element': {k: v for k, v in (primary_el or {}).items() if k not in ('ore', 'resource')},
                       'resource': (primary_el or {}).get('resource'), 'clusters': {}}
    # ---- provider presets: what spawns where, and the cluster sizes used
    preset_info = {}
    harvest_to_rock = {}
    for r in dc.records:
        if r['struct'] == 'HarvestablePreset':
            d = dc.record(r, 0)
            if d.get('entityClass'):
                harvest_to_rock[r['name']] = short_record(d['entityClass'])
    cluster_cache = {}
    cluster_defs = {}

    def cluster_preset(name):
        if name not in cluster_cache:
            d = dc.record(name, 2) or {}
            ps = d.get('clusterParamsArray') or []
            tot = sum(p['relativeProbability'] for p in ps) or 1.0
            cluster_cache[name] = [{'min': p['minSize'], 'max': p['maxSize'],
                                    'chance': r3(p['relativeProbability'] / tot)}
                                   for p in sorted(ps, key=lambda p: (p['minSize'], p['maxSize']))]
        return cluster_cache[name]

    GROUPS = {'SpaceShip_Mineables': 'ship', 'GroundVehicle_Mineables': 'vehicle', 'FPS_Mineables': 'hand'}
    for r in dc.records:
        if r['struct'] != 'HarvestableProviderPreset':
            continue
        d = dc.record(r, 4)
        mix = {}
        for grp in d.get('harvestableGroups') or []:
            mode = GROUPS.get(grp.get('groupName'))
            if not mode:
                continue
            items = []
            for h in grp.get('harvestables') or []:
                rock = harvest_to_rock.get(h.get('harvestable')) or (
                    short_record(h['harvestableEntityClass']) if h.get('harvestableEntityClass') else None)
                if rock not in rocks or not h['relativeProbability'] or h['relativeProbability'] <= 0:
                    continue            # a weight of 0 means it never spawns there
                items.append((rock, h['relativeProbability'], h.get('clustering')))
            tot = sum(i[1] for i in items) or 1.0
            out = []
            for rock, rp, cl in items:
                it = {'ore': rocks[rock]['ore'], 'rock': rock, 'share': r3(rp / tot)}
                if cl:
                    it['cluster'] = short_record(cl)
                    cluster_defs[short_record(cl)] = cluster_preset(cl)
                out.append(it)
            if out:
                mix[mode] = sorted(out, key=lambda x: (-x['share'], x['ore'], x['rock']))
        preset_info[short_record(r['name'])] = mix
    # ---- spots: the named place each preset-binding container belongs to
    SPOT_KINDS = {'planet', 'moon', 'field', 'lagrange point', 'asteroid base', 'belt', 'station'}
    users = defaultdict(list)
    for i, e in enumerate(ents):
        if e['pak']:
            users[e['pak']].append(i)
    spot_members = defaultdict(set)    # place code -> presets
    unplaced = []
    for pak, presets in sorted(presets_by_pak.items()):
        if not users.get(pak):
            unplaced.append((pak, presets))
            continue
        for i in users[pak]:
            code = None
            p = i
            chain_text = []
            while p is not None:
                e = ents[p]
                chain_text.append(e['in'] + ' ' + e['pak'] + ' ' + e['entity'])
                a = locs.by_guid.get(e['smr']) if e['smr'] else None
                if a and a['code'] in locs.places and locs.places[a['code']]['kind'] in SPOT_KINDS:
                    code = a['code']
                    break
                if e['entity'] == 'OOC_AaronHalo':
                    code = 'OOC_AaronHalo'
                    break
                p = e['parent']
            if code is None:
                for rcode, (_k, _s, folder) in REGIONS.items():
                    if rcode in locs.places and any(folder in c for c in chain_text):
                        code = rcode
            if code:
                spot_members[code].update(presets)
            else:
                unplaced.append((pak, presets))
    return elements, rocks, preset_info, cluster_defs, spot_members, unplaced


def assemble_ores(game, locs, rocks, preset_info, cluster_defs, spot_members, hand_spots):
    """Spots (grouping asteroid bases), found-lists, look-alikes and quality per ore."""
    dc = game.dc
    places = locs.places
    spots = {}
    groups = defaultdict(list)
    for code, presets in sorted(spot_members.items()):
        p = places[code]
        if p['kind'] == 'asteroid base' or (p['kind'] == 'station' and code.startswith('Nyx_TSG')):
            groups[(tuple(sorted(presets)), p['system'])].append(code)
            continue
        spots[p['place']] = {'name': p['name'], 'kind': p['kind'], 'body': p['body'], 'system': p['system'],
                             'places': [p['place']], 'mixes': sorted(presets), 'src': 'game'}
    for (presets, system), codes in sorted(groups.items()):
        names = sorted(set(places[c]['name'] for c in codes))
        label = (names[0] + 's') if len(names) == 1 else 'Asteroid mining bases'
        sid = slug('%s %s' % (system, label))
        spots[sid] = {'name': '%s in %s (%d)' % (label, system, len(codes)), 'kind': 'asteroid bases',
                      'body': None, 'system': system, 'places': sorted(places[c]['place'] for c in codes),
                      'mixes': list(presets), 'src': 'game'}
    for sid, s in sorted(hand_spots.items()):
        spots[sid] = dict(s)
    for s in spots.values():
        s['rocks'] = {}
        for mix in s['mixes']:
            for mode, items in sorted(preset_info.get(mix, {}).items()):
                s['rocks'].setdefault(mode, []).extend(dict(it, mix=mix) for it in items)
    # found-lists per ore, and which spots carry each rock
    rock_spots = defaultdict(set)
    found = defaultdict(list)
    for sid, s in sorted(spots.items()):
        for mode, items in sorted(s['rocks'].items()):
            for it in items:
                rock_spots[it['rock']].add(sid)
                if it.get('cluster'):
                    rocks[it['rock']]['clusters'][it['cluster']] = cluster_defs[it['cluster']]
                found[it['ore']].append({'spot': sid, 'name': s['name'], 'mode': mode,
                                         'setting': rocks[it['rock']]['setting'], 'share': it['share'],
                                         'rock': it['rock'], 'src': s['src']})
    # Scan readings and look-alikes, for ship rocks only: "reading = signature x rocks in the cluster"
    # is attested for a ship's scanner [ref]; for ROC and hand rocks it is not, so none is computed.
    readings = []
    for code, rk in sorted(rocks.items()):
        if not rk['signature'] or rk['mode'] != 'ship':
            continue
        for _cp, sizes in sorted(rk['clusters'].items()):
            for sz in sizes:
                if sz['min'] == sz['max']:
                    readings.append((rk['mode'], rk['ore'], sz['min'], rk['signature'] * sz['min'], code))
    readings = sorted(set(readings))
    ores = {}
    by_ore = defaultdict(list)
    for code, rk in sorted(rocks.items()):
        by_ore[rk['ore']].append(code)
    for ore, codes in sorted(by_ore.items()):
        rk_out = {}
        for code in codes:
            rk = rocks[code]
            clusters = []
            for cp, sizes in sorted(rk['clusters'].items()):
                out_sizes = []
                for sz in sizes:
                    if sz['min'] != sz['max']:
                        out_sizes.append({'rocks_min': sz['min'], 'rocks_max': sz['max'], 'chance': sz['chance']})
                        continue
                    n = sz['min']
                    c = {'rocks': n, 'chance': sz['chance']}
                    if rk['signature'] and rk['mode'] == 'ship':
                        scan = rk['signature'] * n
                        c['scan'] = scan
                        dedup = {}
                        for (m2, o2, n2, s2, code2) in readings:
                            if m2 == rk['mode'] and o2 != ore and abs(s2 - scan) <= LOOKALIKE_FRACTION * scan:
                                # a shared spot counts only for the same setting (a moon's surface and
                                # the belt around it are both one spot, but not one scan)
                                shared = (rock_spots.get(code, set()) & rock_spots.get(code2, set())
                                          if rocks[code2]['setting'] == rk['setting'] else set())
                                k = (o2, n2, s2)
                                if k in dedup:
                                    dedup[k]['same_spots'] = sorted(set(dedup[k]['same_spots']) | shared)
                                else:
                                    dedup[k] = {'ore': o2, 'rocks': n2, 'scan': s2, 'diff': s2 - scan,
                                                'same_spots': sorted(shared)}
                        c['lookalikes'] = sorted(dedup.values(), key=lambda x: (abs(x['diff']), x['ore'], x['rocks']))
                    out_sizes.append(c)
                clusters.append({'preset': cp, 'sizes': out_sizes})
            rk_out[code] = {'mode': rk['mode'], 'setting': rk['setting'], 'tier': rk['tier'],
                            'signature': rk['signature'], 'clusters': clusters, 'composition': rk['composition']}
        traces = []
        for code2, rk2 in sorted(rocks.items()):
            if rk2['ore'] == ore:
                continue
            for p in rk2['composition']:
                if p['ore'] == ore:
                    traces.append({'rock': code2, 'rock_ore': rk2['ore'], 'min': p['min'], 'max': p['max'],
                                   'quality_scale': p['quality_scale']})
        f = sorted(found.get(ore, []), key=lambda x: (x['mode'], -x['share'], x['name'], x['rock']))
        el = next((rocks[c]['element'] for c in codes if rocks[c]['element']), {})
        ores[ore] = {'rocks': rk_out, 'found': f, 'traces': traces, 'element': el, 'src': 'game'}
        res = next((rocks[c]['resource'] for c in codes if rocks[c].get('resource')), None)
        if res:
            ores[ore]['resource'] = short_record(res)
            rn = refined_name(game, res)
            if rn:
                ores[ore]['refined'] = rn
    # quality: distribution, Pyro / Nyx overrides, and the fixed values quality snaps to
    for r in dc.records:
        if r['struct'] != 'ResourceType':
            continue
        d = dc.record(r, 5)
        crafting = next((p for p in d.get('properties') or [] if p and p['_type'] == 'ResourceTypeCraftingData'), None)
        if not crafting:
            continue
        nm = ore_name(game, r['name'])
        if nm not in ores:
            continue
        q = {}
        dist = (crafting.get('qualityDistribution') or {}).get('qualityDistributionRecord')
        if dist:
            dd = dc.record(dist, 3)['qualityDistribution']
            q['distribution'] = {'min': dd.get('min'), 'max': dd.get('max'), 'mean': r3(dd.get('mean')),
                                 'sd': r3(dd.get('stddev')), 'record': short_record(dist)}
            m = re.match(r'(Common|Uncommon|Rare|Epic|Legendary)ShipMineable', short_record(dist))
            if m:
                q['tier'] = m.group(1)
        ovr = (crafting.get('qualityLocationOverride') or {}).get('locationOverrideRecord')
        if ovr:
            od = dc.record(ovr, 4)['locationOverride']['locationOverrideList'] or []
            merged = {}
            for o in od:
                loc = short_record(o['location'] or '')
                s = locs.smo.get(loc)
                where = (s['name'] if s and valid_name(s['name']) else loc)
                qd = o['qualityDistribution'] or {}
                key = (where, qd.get('min'), qd.get('max'), r3(qd.get('mean')), r3(qd.get('stddev')))
                merged[key] = merged.get(key, 0) + 1
            q['overrides'] = [{'where': k[0], 'count': v, 'min': k[1], 'max': k[2], 'mean': k[3], 'sd': k[4]}
                              for k, v in sorted(merged.items())]
            q['overrides_record'] = short_record(ovr)
        qz = (crafting.get('qualityQuantization') or {}).get('qualityQuantizationRecord')
        if qz:
            bands = dc.record(qz, 3)['qualityQuantization']['bands'] or []
            q['bands'] = [{'from': b['start'], 'to': b['end'], 'value': b['mappedValue']} for b in bands]
            q['values'] = [b['mappedValue'] for b in bands]
        if q:
            q['resource'] = short_record(r['name'])
            q['src'] = 'game'
            prev = ores[nm].get('quality')
            # keep the raw (Ore_/Raw_) record's data when both raw and refined carry it
            if not prev or not re.match(r'^(Ore_|Raw_)', prev['resource']):
                ores[nm]['quality'] = q
    for ore, o in ores.items():
        tiers = sorted(set(rk['tier'] for rk in o['rocks'].values() if rk['tier']))
        if 'quality' in o and o['quality'].get('tier'):
            o['tier'] = o['quality']['tier']
        elif tiers:
            o['tier'] = tiers[0]
        modes = sorted(set(rk['mode'] for rk in o['rocks'].values()))
        o['modes'] = modes
    for s in spots.values():
        for mode in s['rocks']:
            s['rocks'][mode].sort(key=lambda x: (-x['share'], x['ore'], x['rock'], x['mix']))
    return ores, spots


# =========================================================================== refining methods
def build_methods(game):
    out = {}
    for r in game.dc.records:
        if r['struct'] != 'RefiningProcess':
            continue
        d = game.dc.record(r, 1)
        nm = game.label(d.get('processName'))
        if not valid_name(nm):
            continue
        key = '%s%s' % (d.get('refiningSpeed'), d.get('refiningQuality'))
        detail = game.label(d.get('processDetail')).replace('\\n', ' ').strip()
        out[key] = {'name': nm, 'speed': d.get('refiningSpeed'),
                    'yield': {'Careful': 'high', 'Normal': 'medium', 'Wasteful': 'low'}.get(d.get('refiningQuality'),
                                                                                         d.get('refiningQuality')),
                    'detail': detail or None, 'src': 'game'}
    return {k: out[k] for k in sorted(out)}


# =========================================================================== ships
SCU_CELL = 1.25            # one SCU is a 1.25 m cube; a cargo grid holds whole cells


def _components(d):
    return [c for c in (d or {}).get('Components') or [] if c]


def _comp(d, t):
    return next((c for c in _components(d) if c['_type'] == t), None)


def build_ships(game):
    """Every vehicle entity class: name, maker, cargo grid (SCU), crew, the game's career and role."""
    dc = game.dc
    grid_cache = {}

    def grid_scu(cls):
        """SCU of one cargo-grid item class (0 if it is not a cargo grid)."""
        if cls in grid_cache:
            return grid_cache[cls]
        grid_cache[cls] = 0
        d = dc.record(cls, 3)
        att = _comp(d, 'SAttachableComponentParams')
        inv = _comp(d, 'SCItemInventoryContainerComponentParams')
        if not att or not inv or (att.get('AttachDef') or {}).get('Type') != 'CargoGrid':
            return 0
        cont = dc.record(inv.get('containerParams'), 3) if inv.get('containerParams') else None
        dim = (cont or {}).get('interiorDimensions') or {}
        cells = 1
        for axis in ('x', 'y', 'z'):
            cells *= int(round(float(dim.get(axis) or 0) / SCU_CELL, 6))
        grid_cache[cls] = cells
        return cells

    def loadout_scu(entries):
        total = 0
        for e in entries or []:
            if not e:
                continue
            cls = e.get('entityClassReference')
            if cls:
                total += grid_scu(cls)
            sub = (e.get('loadout') or {}).get('entries')
            if sub:
                total += loadout_scu(sub)
        return total

    makers = {}
    out = {}
    for r in dc.records:
        if r['struct'] != 'EntityClassDefinition':
            continue
        f = r['file']
        if '/entities/spaceships/' not in f and '/entities/groundvehicles/' not in f:
            continue
        d = dc.record(r, 6)
        v = _comp(d, 'VehicleComponentParams')
        if not v:
            continue
        name = game.label(v.get('vehicleName'))
        if not valid_name(name):
            continue
        code = short_record(r['name'])
        mk = v.get('manufacturer')
        if mk and mk not in makers:
            md = dc.record(mk, 3) or {}
            loc = md.get('Localization') or {}
            makers[mk] = {'code': md.get('Code') or short_record(mk), 'name': game.label(loc.get('Name')) or None}
        lo = _comp(d, 'SEntityComponentDefaultLoadoutParams')
        scu = loadout_scu(((lo or {}).get('loadout') or {}).get('entries'))
        e = {'name': name, 'maker': (makers.get(mk) or {}).get('name'), 'maker_code': (makers.get(mk) or {}).get('code'),
             'kind': 'ground vehicle' if '/entities/groundvehicles/' in f else 'ship',
             'cargo_scu': scu, 'crew': v.get('crewSize'),
             'career': game.label(v.get('vehicleCareer')) or None, 'role': game.label(v.get('vehicleRole')) or None}
        if re.search(r'_AI_|_PU_AI|_Template$|_Unmanned|_Teach$|_Tutorial|_NoInterior', code, re.I):
            e['variant'] = 'npc or special'
        e['src'] = 'game'
        out[code] = e
    return out


# =========================================================================== online snapshots (--fetch only)
UEX = 'https://api.uexcorp.space/2.0/'
SCMDB = 'https://scmdb.net/data/'
USER_AGENT = 'sc-reference-builder/1.0'          # a generic client name: nothing about the user


def _get_json(url):
    import urllib.request                        # imported here: a normal run never loads it
    req = urllib.request.Request(url, headers={'User-Agent': USER_AGENT, 'Accept': 'application/json'})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode('utf-8'))


def _write_snapshot(name, doc):
    p = HERE / name
    p.write_text(json.dumps(doc, indent=0, ensure_ascii=False, sort_keys=False) + '\n', encoding='utf-8', newline='\n')
    print('  wrote snapshot %s (%d bytes)' % (name, p.stat().st_size))


def fetch_snapshots(change):
    """The one step that goes online: UEX commodity prices and terminals, and SCMDB's mission list
    for the installed build (and the newest test build, if SCMDB has one). Saved lean, so a normal
    run rebuilds prices.json and contracts.json from these files byte for byte."""
    print('Fetching (the only online step) ...')
    prices = _get_json(UEX + 'commodities_prices_all')['data']
    terms = _get_json(UEX + 'terminals')['data']
    used = {r['id_terminal'] for r in prices}
    tdoc = {}
    for t in sorted(terms, key=lambda t: t['id']):
        if t['id'] in used:
            tdoc[str(t['id'])] = {'name': t.get('name'), 'display': t.get('displayname'), 'type': t.get('type'),
                                  'station': t.get('space_station_name'), 'city': t.get('city_name'),
                                  'outpost': t.get('outpost_name'), 'planet': t.get('planet_name'),
                                  'moon': t.get('moon_name'), 'system': t.get('star_system_name')}
    rows = sorted([r['commodity_name'], r['id_terminal'], r.get('price_buy') or 0, r.get('price_sell') or 0,
                   _day(r.get('date_modified'))] for r in prices)
    _write_snapshot('prices.hand.json', {
        '_doc': 'Snapshot of UEX Corp API 2.0 /commodities_prices_all and /terminals, written by '
                'build_reference.py --fetch and read by every normal run. Rows: [commodity, terminal id, buy, sell, '
                'last updated]. Prices are aUEC per SCU, crowd-reported by players. Do not edit by hand; fetch again.',
        'source': 'UEX Corp API 2.0 (api.uexcorp.space)', 'fetched': TODAY, 'terminals': tdoc, 'rows': rows})
    versions = _get_json(SCMDB + 'game-versions.json')
    builds = {}
    for v in versions:
        ver, fn = v.get('version', ''), v.get('file', '')
        if ver.endswith('.' + change) or '-ptu.' in ver:
            d = _get_json(SCMDB + fn)
            lean = []
            for c in (d.get('contracts') or []) + (d.get('legacyContracts') or []):
                names = sorted(set([c.get('debugName')] + list(c.get('debugNames') or [])) - {None})
                lean.append({'names': names, 'type': c.get('missionType'), 'category': c.get('category'),
                             'giver': c.get('contractorName'), 'title': c.get('title')})
            builds[ver] = sorted(lean, key=lambda c: (c['names'][:1], c['type'] or '', c['title'] or ''))
    _write_snapshot('contracts.scmdb.hand.json', {
        '_doc': 'Snapshot of SCMDB (scmdb.net) mission data: per build, every contract with its internal names '
                '(the `contract [...]` in a mission marker line), mission type, contractor and title. Written by '
                'build_reference.py --fetch; do not edit by hand.',
        'source': 'SCMDB (scmdb.net/data), community extract of the game files', 'fetched': TODAY, 'builds': builds})


def _day(ts):
    if not ts:
        return None
    return datetime.datetime.fromtimestamp(int(ts), datetime.timezone.utc).date().isoformat()


def build_prices(locs_entries, resources, snap):
    """prices.json from the UEX snapshot: per commodity, every terminal's buy and sell price and date."""
    if not snap:
        return {}, {}
    by_name = {}
    for k, v in locs_entries.items():
        if v.get('place'):
            for n in (v['name'], v['short']):
                by_name.setdefault(n.lower(), v['place'])
    terms = {}
    unmatched = set()
    for tid, t in snap['terminals'].items():
        place = None
        for n in (t.get('station'), t.get('city'), t.get('outpost'), t.get('display')):
            if n and n.lower() in by_name:
                place = by_name[n.lower()]
                break
        if place is None:
            unmatched.add(tid)
        terms[tid] = {'terminal': t.get('name'), 'place': place,
                      'where': t.get('station') or t.get('city') or t.get('outpost') or t.get('display'),
                      'body': t.get('moon') or t.get('planet'), 'system': t.get('system')}
    names = {}
    for rid, r in resources.items():
        names.setdefault(r['name'].lower(), (r['name'], rid))
    out = {}
    for cname, tid, buy, sell, date in snap['rows']:
        t = terms.get(str(tid))
        if not t:
            continue
        game = names.get(cname.lower())
        key = game[0] if game else cname
        e = out.setdefault(key, {'resource': game[1] if game else None, 'terminals': [], 'src': 'ref'})
        row = dict(t)
        row.update({'buy': buy or None, 'sell': sell or None, 'date': date})
        e['terminals'].append(row)
    for e in out.values():
        e['terminals'].sort(key=lambda r: (r['system'] or '', r['where'] or '', r['terminal'] or ''))
        if e['resource'] is None:
            e['note'] = 'No game commodity has this exact name; it is the UEX name.'
    return out, {'terminals': len(terms), 'terminals_without_place': len(unmatched)}


# =========================================================================== controls (from the card tables)
CARD_FILE = ROOT / 'tools' / 'regen_cards.py'
CARD_TABLES = {'js1': ('AB6', 'MHG_L', 'MHG_R'), 'js2': ('MTQ_L', 'MTQ_R')}
VARIANT_TAGS = {'mining': 'Mine:', 'salvage': 'Salv:', 'missile': 'Msl:'}


def read_card_tables(path=CARD_FILE):
    """The card tables of tools/regen_cards.py, read with `ast` (nothing in that file is run).
    Returns {'js1': {label: row}, 'js2': {label: row}}; a row has Label, Primary, Hint, Variants."""
    import ast
    tree = ast.parse(Path(path).read_text(encoding='utf-8'))
    consts = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name) \
                and isinstance(node.value, ast.Constant):
            consts[node.targets[0].id] = node.value.value

    def ev(n):
        if isinstance(n, ast.Constant):
            return n.value
        if isinstance(n, ast.List):
            return [ev(x) for x in n.elts]
        if isinstance(n, ast.Dict):
            return {ev(k): ev(v) for k, v in zip(n.keys, n.values)}
        if isinstance(n, ast.Name) and n.id in consts:
            return consts[n.id]
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == 'V' and len(n.args) == 3:
            tag, text, color = (ev(a) for a in n.args)
            return {'Tag': tag, 'Text': text, 'Color': color}
        raise ValueError('unexpected expression in a card table, line %d' % getattr(n, 'lineno', 0))

    raw = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            if any(node.targets[0].id in t for t in CARD_TABLES.values()):
                raw[node.targets[0].id] = ev(node.value)
    out = {}
    for dev, tables in CARD_TABLES.items():
        rows = {}
        for t in tables:
            if t not in raw:
                raise ValueError('card table %s not found in %s' % (t, path))
            for row in raw[t]:
                if 'Label' in row:
                    if row['Label'] in rows:
                        raise ValueError('card label %s %s appears twice' % (dev, row['Label']))
                    rows[row['Label']] = dict(row, table=t)
        out[dev] = rows
    return out


def card_text(row, variant):
    """The card's wording for a row in a mode: the mode's variant if the row has one, else Primary."""
    tag = VARIANT_TAGS.get(variant)
    for v in row.get('Variants') or []:
        if tag and v.get('Tag') == tag:
            return v['Text']
    return row['Primary']


def build_controls(hand):
    cards = read_card_tables()
    modes = {}
    problems = []
    for mode, m in sorted((hand.get('modes') or {}).items()):
        items = []
        for it in m.get('items') or []:
            variant = it.get('variant', m.get('variant'))
            parts = []
            for ref in it['controls']:
                dev, _, label = ref.partition(' ')
                row = cards.get(dev, {}).get(label)
                if row is None:
                    problems.append('%s: %r is not on the cards' % (mode, ref))
                    continue
                p = {'control': ref, 'text': card_text(row, variant), 'primary': row['Primary']}
                if row.get('Hint'):
                    p['hint'] = row['Hint']
                if row.get('Unbound'):
                    p['unbound'] = True
                parts.append(p)
            out = {'where': it['where'], 'controls': list(it['controls']),
                   'text': ' · '.join(p['text'] for p in parts), 'parts': parts}
            for k in ('status', 'note'):
                if it.get(k):
                    out[k] = it[k]
            out['src'] = 'user'
            items.append(out)
        knob = m.get('knob')
        entry = {'title': m.get('title') or mode, 'variant': m.get('variant')}
        if knob:
            dev, _, label = knob.partition(' ')
            row = cards.get(dev, {}).get(label)
            if row is None:
                problems.append('%s: knob %r is not on the cards' % (mode, knob))
            else:
                entry['knob'] = {'control': knob, 'text': row['Primary'], 'hint': row.get('Hint')}
        entry['items'] = items
        entry['src'] = 'user'
        modes[mode] = entry
    if problems:
        sys.exit('controls.hand.json names controls the cards do not have:\n  ' + '\n  '.join(problems))
    return modes


# =========================================================================== writing
ENTRY_ORDER = ('prefix', 'name', 'short', 'kind', 'body', 'system', 'place', 'pos', 'candidates', 'record', 'refined',
               'src', 'source', 'date', 'note')


def order_entry(e):
    if not isinstance(e, dict):
        return e
    keys = [k for k in ENTRY_ORDER if k in e] + sorted(k for k in e if k not in ENTRY_ORDER)
    return {k: e[k] for k in keys}


def dump(doc, main):
    """Deterministic JSON: _meta indented, then one line per entry of the main map."""
    out = ['{']
    keys = list(doc.keys())
    for i, k in enumerate(keys):
        comma = ',' if i < len(keys) - 1 else ''
        v = doc[k]
        if k == main and isinstance(v, dict):
            out.append('  %s: {' % json.dumps(k))
            items = list(v.items())
            for j, (kk, vv) in enumerate(items):
                out.append('    %s: %s%s' % (json.dumps(kk, ensure_ascii=False),
                                             json.dumps(order_entry(vv), ensure_ascii=False, separators=(', ', ': ')),
                                             ',' if j < len(items) - 1 else ''))
            out.append('  }' + comma)
        elif isinstance(v, (dict, list)) and k != '_meta':
            if isinstance(v, dict):
                out.append('  %s: {' % json.dumps(k))
                items = list(v.items())
                for j, (kk, vv) in enumerate(items):
                    out.append('    %s: %s%s' % (json.dumps(kk, ensure_ascii=False),
                                                 json.dumps(order_entry(vv), ensure_ascii=False, separators=(', ', ': ')),
                                                 ',' if j < len(items) - 1 else ''))
                out.append('  }' + comma)
            else:
                out.append('  %s: [' % json.dumps(k))
                for j, vv in enumerate(v):
                    out.append('    %s%s' % (json.dumps(order_entry(vv), ensure_ascii=False, separators=(', ', ': ')),
                                             ',' if j < len(v) - 1 else ''))
                out.append('  ]' + comma)
        else:
            body = json.dumps(v, ensure_ascii=False, indent=2)
            out.append('  %s: %s%s' % (json.dumps(k), body.replace('\n', '\n  '), comma))
    out.append('}')
    return '\n'.join(out) + '\n'


def load_hand(name):
    p = HERE / ('%s.hand.json' % name)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding='utf-8'))
    except ValueError as e:
        sys.exit('%s is not valid JSON: %s' % (p.name, e))


GENERATOR_HASH = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()[:12]


def meta(game, name, extra):
    m = {'build': game.build['version'], 'change': game.build['change'], 'generated': TODAY,
         'generator': GENERATOR_HASH,
         'generated_by': 'dashboard/reference/build_reference.py (do not edit by hand; put hand-entered data '
                         'in %s.hand.json)' % name,
         'sources': dict(SOURCES)}
    m.update(extra)
    return m


def sort_map(d):
    return {k: d[k] for k in sorted(d, key=lambda s: (s.lower(), s))}


def guard(name, old, new, hand_keys, force):
    """Refuse to overwrite an output whose entries were edited or added by hand outside the hand file.
    Returns a list of problems (empty = safe)."""
    main = MAIN_MAP[name]
    om, nm = old.get(main) or {}, new.get(main) or {}
    problems = []
    om_meta = old.get('_meta') or {}
    # Strict check only when both the build and this script are unchanged: then the output is fully
    # determined by the game files and the hand files, so any other difference is a hand edit.
    same_build = (om_meta.get('change') == new['_meta']['change']
                  and om_meta.get('generator') == new['_meta']['generator'])
    # keys the hand file supplied last time: removing them from the hand file is deliberate
    old_hand = set(om_meta.get('hand_keys') or [])
    for k, v in om.items():
        if k in old_hand or k in hand_keys:
            continue
        if k not in nm:
            src = v.get('src') if isinstance(v, dict) else None
            if same_build or src not in ('game', None):
                problems.append('%s: entry %r would be dropped (src %s). Move it into %s.hand.json.'
                                % (name, k, src, name))
        elif same_build and nm[k] != v:
            problems.append('%s: entry %r differs from what this build generates; it was edited in the output. '
                            'Put the change in %s.hand.json.' % (name, k, name))
    if name == 'locations':
        old_hand_p = set(om_meta.get('hand_patterns') or [])
        op = {p['prefix']: p for p in old.get('patterns') or []}
        np_ = {p['prefix']: p for p in new.get('patterns') or []}
        for k, v in op.items():
            if k in old_hand_p:
                continue
            if k not in np_ and (same_build or v.get('src') != 'game'):
                problems.append('locations: pattern %r would be dropped. Move it into locations.hand.json.' % k)
            elif k in np_ and same_build and np_[k] != v and k not in set(new['_meta'].get('hand_patterns') or []):
                problems.append('locations: pattern %r was edited in the output. Put the change in '
                                'locations.hand.json.' % k)
    if force:
        return []
    return problems


def write_outputs(game, docs, hand_keys, check, force):
    changed, problems = [], []
    texts = {}
    for name, doc in docs.items():
        path = HERE / ('%s.json' % name)
        old = None
        if path.exists():
            try:
                old = json.loads(path.read_text(encoding='utf-8'))
            except ValueError:
                old = None
        if old is not None:
            problems += guard(name, old, doc, hand_keys.get(name, set()), force)
            # keep the old date when nothing else changed, so a re-run is byte-identical
            od = (old.get('_meta') or {}).get('generated')
            if od:
                trial = json.loads(json.dumps(doc))
                trial['_meta']['generated'] = od
                if dump(trial, MAIN_MAP[name]) == path.read_text(encoding='utf-8'):
                    doc = trial
        text = dump(doc, MAIN_MAP[name])
        texts[name] = text
        if not path.exists() or path.read_text(encoding='utf-8') != text:
            changed.append(name)
    if problems:
        print('\nNOT WRITTEN - hand edits would be lost:')
        for p in problems:
            print('  ' + p)
        print('Run again with --force only if those edits are meant to go.')
        return 2
    if check:
        print('\n--check: %s' % ('these files would change: ' + ', '.join(changed) if changed else 'all four files are up to date'))
        return 1 if changed else 0
    for name in changed:
        (HERE / ('%s.json' % name)).write_text(texts[name], encoding='utf-8', newline='\n')
    for name in docs:
        print('  %-16s %s (%d bytes)' % (name + '.json', 'written' if name in changed else 'unchanged', len(texts[name].encode('utf-8'))))
    return 0


# =========================================================================== main
def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--p4k', type=Path, default=gamedata.LIVE / 'Data.p4k' if gamedata.LIVE else None)
    ap.add_argument('--check', action='store_true', help='build in memory and report; write nothing')
    ap.add_argument('--force', action='store_true', help='overwrite even if hand edits in an output would be lost')
    args = ap.parse_args()
    if args.p4k is None or not args.p4k.exists():
        sys.exit('Data.p4k not found (%s). Pass --p4k.' % args.p4k)

    game = Game(args.p4k)
    ents = walk_hierarchy(game)
    preset_guids = {r['guid']: r['name'] for r in game.dc.records if r['struct'] == 'HarvestableProviderPreset'}
    presets_by_pak = find_provider_presets(game, preset_guids)
    presets_by_pak = {k: [short_record(p) for p in v] for k, v in presets_by_pak.items()}
    print('  containers binding a mining preset: %d' % len(presets_by_pak))

    locs = Locations(game, ents, presets_by_pak)
    # first pass decides which L-points are mining fields (kind 'field'), then build for real
    locs.build()
    spot_members = build_ores(game, locs, ents, presets_by_pak)[4]
    locs.spot_codes = set(spot_members)
    loc_entries, patterns, _notes = locs.build()
    _elements, rocks, preset_info, cluster_defs, spot_members, unplaced = build_ores(game, locs, ents, presets_by_pak)

    hand = {n: load_hand(n) for n in OUTPUTS}
    hand_keys = {}

    # ---- locations
    hl = hand['locations']
    for k, v in (hl.get('locations') or {}).items():
        if k in loc_entries:
            print('  locations.hand.json overrides generated entry %r' % k)
        loc_entries[k] = v
    hand_keys['locations'] = set((hl.get('locations') or {}).keys())
    pat = {p['prefix']: p for p in patterns}
    for p in hl.get('patterns') or []:
        pat[p['prefix']] = p
    patterns = sorted(pat.values(), key=lambda p: (-len(p['prefix']), p['prefix']))
    loc_doc = {
        '_meta': meta(game, 'locations', {
            'lookup': 'Keys are codes exactly as Game.log prints them: quantum targets ("selected point <CODE>"), '
                      'inventory locations ("Location[<CODE>]"), route start names ("Projected Start Location is '
                      '<name>"), refinery-notice station names, and planet names from terrain lines. `place` is '
                      'shared by every code that means the same place; it is null when a code cannot be pinned to '
                      'one place, and then `candidates` lists the possibilities when they are known. Codes built at '
                      'runtime ("<record>_<entity id>") are not keys: match them against `patterns`, longest '
                      'prefix first.',
            'counts': {}})}
    loc_doc['locations'] = sort_map(loc_entries)
    loc_doc['patterns'] = patterns
    loc_doc['_meta']['counts'] = {'entries': len(loc_entries), 'places': len(set(
        v['place'] for v in loc_entries.values() if v.get('place'))), 'patterns': len(patterns)}

    # ---- resources
    res = build_resources(game)
    hr = hand['resources'].get('resources') or {}
    res.update(hr)
    hand_keys['resources'] = set(hr)
    res_doc = {'_meta': meta(game, 'resources', {
        'lookup': 'Keys are the resourceGUID values in SendCommoditySellRequest / SendCommodityBuyRequest lines '
                  '(lower case). `name` is the in-game English name; `record` is the game\'s ResourceType record; '
                  '`refined` names what an ore refines into.', 'counts': {'entries': len(res)}}),
        'resources': sort_map(res)}

    # ---- ores
    ho = hand['ores']
    hand_spots = ho.get('spots') or {}
    ores, spots = assemble_ores(game, locs, rocks, preset_info, cluster_defs, spot_members, hand_spots)
    for k, v in (ho.get('ores') or {}).items():
        ores.setdefault(k, {}).update(v)          # field-level: hand fields replace generated ones
    hand_keys['ores'] = set((ho.get('ores') or {}).keys())
    ore_doc = {'_meta': meta(game, 'ores', {
        'lookup': 'Keyed by the ore\'s English name without "(Ore)" / "(Raw)" (`refined` is what it refines '
                  'into). rocks.<class>.signature is the scan value of one rock [game]. For ship rocks each '
                  'clusters[].sizes[] entry gives the reading for that many rocks, `scan` = signature x rocks: '
                  'that rule is community knowledge [ref], matched by a published example (Iron 4,270 x 4 = '
                  '17,080), and it is not applied to ROC or hand-mined rocks. `lookalikes` are other ores whose '
                  'ship readings fall within %d%% of it, with the spots where both spawn (`same_spots`). '
                  '`quality.values` are the fixed figures a lot\'s quality snaps to (`bands` gives the ranges); the '
                  'draw is a normal distribution clipped at `min`..`max`, applied to the composition parts with '
                  'quality_scale 1.0 and scaled down for the others. `found` lists the spots where the ore has its '
                  'own rock, with that rock\'s share of the spawns there; `traces` lists other ores\' rocks that '
                  'contain it. `spots` (below) gives the full rock mix of each place.' % int(LOOKALIKE_FRACTION * 100),
        'counts': {'ores': len(ores), 'spots': len(spots)}}),
        'ores': sort_map(ores), 'spots': sort_map(spots)}

    # ---- refineries
    hf = hand['refineries']
    stations = hf.get('stations') or {}
    hand_keys['refineries'] = set(stations)
    ref_meta_extra = {'lookup': 'stations.<place>.yields.<ore> is a list of reports, newest first; `bonus` is '
                                'the yield modifier in percent shown on the refinery terminal. Every report '
                                'carries its date and source. `methods` comes from the game files.',
                      'counts': {'stations': len(stations)}}
    if hf.get('_sources'):
        ref_meta_extra['report_sources'] = hf['_sources']
    ref_doc = {'_meta': meta(game, 'refineries', ref_meta_extra), 'methods': build_methods(game),
               'stations': sort_map(stations)}

    # ---- controls per operator mode, worded from the card tables in tools/regen_cards.py
    hc = hand['controls']
    ctl_modes = build_controls(hc)
    hand_keys['controls'] = set(ctl_modes)
    ctl_doc = {'_meta': meta(game, 'controls', {
        'lookup': 'modes.<mode>.items is the strip of controls a view shows, in order. `where` is the physical '
                  'control, `text` the card wording (joined with " · " when one item is several controls), '
                  '`parts` the card row behind each control. `status`: flown (confirmed in a ship), unverified '
                  '(bound, not yet confirmed in a ship), trial (the docs call it a trial); no status means the '
                  'docs raise no doubt. Source: the card tables in tools/regen_cards.py and CLAUDE.md sections 4 '
                  'to 6; the selection is in controls.hand.json.',
        'cards': 'tools/regen_cards.py', 'counts': {'modes': len(ctl_modes)}}), 'modes': ctl_modes}

    docs = {'locations': loc_doc, 'resources': res_doc, 'ores': ore_doc, 'refineries': ref_doc,
            'controls': ctl_doc}
    for name, doc in docs.items():
        doc['_meta']['hand_keys'] = sorted(hand_keys.get(name, set()))
    loc_doc['_meta']['hand_patterns'] = sorted(p['prefix'] for p in hl.get('patterns') or [])
    print('  locations: %d entries (%d ambiguous entity names left out), %d patterns'
          % (len(loc_entries), len(locs.skipped_ambiguous), len(patterns)))
    print('  resources: %d   ores: %d   spots: %d   refinery stations: %d'
          % (len(res), len(ores), len(spots), len(stations)))
    if unplaced:
        print('  preset containers not placed in this build\'s hierarchy: %s'
              % ', '.join('%s (%s)' % (p.rsplit('\\', 1)[-1], '/'.join(v)) for p, v in unplaced))
    rc = write_outputs(game, docs, hand_keys, args.check, args.force)
    game.close()
    return rc


if __name__ == '__main__':
    sys.exit(main())
