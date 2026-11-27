"""Checks on the dashboard's reference tables in dashboard/reference/.

Standard library only; needs no game install. Run from the project root:
    python -m unittest dashboard/tests/test_reference.py
or  python -m unittest discover -s dashboard/tests -p test_reference.py

What is checked: the four tables (and their hand-entered inputs) parse as JSON with no duplicate or
empty keys, follow their shape, say where every entry came from, and use `place` ids consistently
across locations.json, ores.json and refineries.json.
"""
import json
import re
import unittest
from pathlib import Path

REF = Path(__file__).resolve().parent.parent / 'reference'
TABLES = ('locations', 'resources', 'ores', 'refineries')
SRC = {'game', 'ref', 'seen', 'user'}
PLACE_RE = re.compile(r'^[a-z0-9]+(?:-[a-z0-9]+)*$')
GUID_RE = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')
DATE_RE = re.compile(r'^\d{4}-\d{2}-\d{2}$')
PLACE_FIELDS = ('name', 'short', 'kind', 'body', 'system')


class DuplicateKey(ValueError):
    pass


def _no_dupes(pairs):
    out = {}
    for k, v in pairs:
        if k in out:
            raise DuplicateKey('duplicate key %r' % k)
        if k == '':
            raise DuplicateKey('empty key')
        out[k] = v
    return out


def load(name):
    with open(REF / name, encoding='utf-8') as f:
        return json.load(f, object_pairs_hook=_no_dupes)


class ReferenceTables(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.t = {}
        for name in TABLES:
            cls.t[name] = load('%s.json' % name)
        cls.locs = cls.t['locations']['locations']
        cls.places = {}
        for k, v in cls.locs.items():
            if v.get('place'):
                cls.places.setdefault(v['place'], []).append((k, v))

    # ------------------------------------------------------------------ parsing and _meta
    def test_files_parse_without_duplicate_or_empty_keys(self):
        for name in TABLES:
            with self.subTest(table=name):
                load('%s.json' % name)          # raises on duplicates or empty keys
        for p in sorted(REF.glob('*.hand.json')):
            with self.subTest(hand=p.name):
                load(p.name)

    def test_meta(self):
        for name in TABLES:
            with self.subTest(table=name):
                m = self.t[name]['_meta']
                for k in ('build', 'change', 'generated', 'generator', 'sources'):
                    self.assertIn(k, m)
                self.assertRegex(m['generated'], DATE_RE)
                self.assertTrue(SRC <= set(m['sources']), 'every src value is explained in _meta.sources')

    def test_keys_are_clean(self):
        for name, main in (('locations', 'locations'), ('resources', 'resources'), ('ores', 'ores'),
                           ('ores', 'spots'), ('refineries', 'stations')):
            with self.subTest(table=name, map=main):
                for k in self.t[name][main]:
                    self.assertTrue(k and k == k.strip(), 'key %r is empty or has outer spaces' % k)

    # ------------------------------------------------------------------ locations
    def test_locations_shape(self):
        for k, v in self.locs.items():
            with self.subTest(code=k):
                for f in ('name', 'short', 'kind', 'body', 'system', 'place', 'src'):
                    self.assertIn(f, v)
                self.assertTrue(isinstance(v['name'], str) and v['name'])
                self.assertTrue(isinstance(v['short'], str) and v['short'])
                self.assertTrue(isinstance(v['kind'], str) and v['kind'])
                for f in ('body', 'system'):
                    self.assertTrue(v[f] is None or (isinstance(v[f], str) and v[f]))
                self.assertIn(v['src'], SRC)
                if v['place'] is None:
                    self.assertTrue(v.get('candidates') or v.get('note'),
                                    'an entry with no place explains why (candidates or note)')
                else:
                    self.assertRegex(v['place'], PLACE_RE)

    def test_place_ids_are_consistent(self):
        for pid, entries in self.places.items():
            first = entries[0][1]
            for code, v in entries[1:]:
                with self.subTest(place=pid, code=code):
                    for f in PLACE_FIELDS:
                        self.assertEqual(v[f], first[f], '%s differs from %s on %r' % (code, entries[0][0], f))

    def test_candidates_point_at_real_places(self):
        for k, v in self.locs.items():
            if 'candidates' in v:
                with self.subTest(code=k):
                    self.assertIsNone(v['place'])
                    self.assertGreaterEqual(len(v['candidates']), 2)
                    self.assertEqual(len(set(v['candidates'])), len(v['candidates']))
                    for c in v['candidates']:
                        self.assertIn(c, self.places)

    def test_patterns(self):
        pats = self.t['locations']['patterns']
        prefixes = [p['prefix'] for p in pats]
        self.assertEqual(len(prefixes), len(set(prefixes)), 'duplicate pattern prefix')
        self.assertEqual(prefixes, sorted(prefixes, key=lambda s: (-len(s), s)), 'longest prefix first')
        for p in pats:
            with self.subTest(prefix=p.get('prefix')):
                self.assertTrue(p['prefix'] and p['name'] and p['kind'])
                self.assertIn(p['src'], SRC)
                self.assertNotIn(p['prefix'], self.locs)

    def test_known_codes(self):
        """A few codes the user's logs print, with the names the game gives them."""
        expect = {'LOC_RR_S3_L1': ('arc-l1', 'ARC-L1 Wide Forest Station'),
                  'RR_ARC_L1': ('arc-l1', 'ARC-L1 Wide Forest Station'),
                  'LOC_RR_S4_L2': ('mic-l2', 'MIC-L2 Long Forest Station'),
                  'RR_JP_StantonMagnus': ('nyx-gateway-stanton', 'Nyx Gateway'),
                  'OOC_Stanton_3b_Wala': ('wala', 'Wala'),
                  'NewBabbage_LOC': ('new-babbage', 'New Babbage'),
                  'Stanton4_NewBabbage': ('new-babbage', 'New Babbage')}
        for code, (pid, name) in expect.items():
            with self.subTest(code=code):
                self.assertEqual(self.locs[code]['place'], pid)
                self.assertEqual(self.locs[code]['name'], name)

    # ------------------------------------------------------------------ resources
    def test_resources(self):
        res = self.t['resources']['resources']
        self.assertGreater(len(res), 0)
        for k, v in res.items():
            with self.subTest(id=k):
                self.assertRegex(k, GUID_RE)
                self.assertTrue(v['name'] and v['record'])
                self.assertIn(v['src'], SRC)
        self.assertEqual(res['60f116f4-c02a-45b2-9ded-333747795124']['name'], 'Tungsten')

    # ------------------------------------------------------------------ ores
    def test_ores(self):
        ores, spots = self.t['ores']['ores'], self.t['ores']['spots']
        for ore, o in ores.items():
            with self.subTest(ore=ore):
                self.assertIn(o['src'], SRC)
                self.assertTrue(o['rocks'])
                for rk, r in o['rocks'].items():
                    self.assertIn(r['mode'], ('ship', 'vehicle', 'hand'))
                    self.assertTrue(r['signature'] is None or (isinstance(r['signature'], int) and r['signature'] > 0))
                    for c in r['clusters']:
                        for s in c['sizes']:
                            if 'scan' in s:
                                self.assertEqual(r['mode'], 'ship')
                                self.assertEqual(s['scan'], r['signature'] * s['rocks'])
                                for lk in s['lookalikes']:
                                    self.assertIn(lk['ore'], ores)
                                    self.assertNotEqual(lk['ore'], ore)
                                    for sp in lk['same_spots']:
                                        self.assertIn(sp, spots)
                    for p in r['composition']:
                        self.assertIn(p['ore'], ores)
                        self.assertLessEqual(p['min'], p['max'])
                for f in o['found']:
                    self.assertIn(f['spot'], spots)
                    self.assertIn(f['rock'], o['rocks'])
                    self.assertIn(f['src'], SRC)
                    self.assertTrue(0 < f['share'] <= 1)
                q = o.get('quality')
                if q:
                    self.assertIn(q['src'], SRC)
                    if 'values' in q:
                        self.assertEqual(q['values'], [b['value'] for b in q['bands']])
                        self.assertEqual(q['bands'][0]['from'], 0)
                        self.assertEqual(q['bands'][-1]['to'], 1000)
                        for a, b in zip(q['bands'], q['bands'][1:]):
                            self.assertEqual(a['to'] + 1, b['from'])
        for sid, s in spots.items():
            with self.subTest(spot=sid):
                self.assertRegex(sid, PLACE_RE)
                self.assertIn(s['src'], SRC)
                self.assertTrue(s['places'])
                for pid in s['places']:
                    self.assertIn(pid, self.places, 'spot place %r is not in locations.json' % pid)
                for mode, items in s['rocks'].items():
                    for it in items:
                        self.assertIn(it['ore'], ores)

    def test_ores_the_user_works_on(self):
        ores = self.t['ores']['ores']
        for ore, sig in (('Tungsten', 3870), ('Beryl', 3540), ('Agricium', 3885)):
            with self.subTest(ore=ore):
                sigs = {r['signature'] for r in ores[ore]['rocks'].values() if r['mode'] == 'ship'}
                self.assertEqual(sigs, {sig})
                self.assertEqual(len(ores[ore]['quality']['values']), 8)
                self.assertTrue(any(f['mode'] == 'ship' for f in ores[ore]['found']))

    # ------------------------------------------------------------------ refineries
    def test_refineries(self):
        ref = self.t['refineries']
        ores = self.t['ores']['ores']
        for k, m in ref['methods'].items():
            with self.subTest(method=k):
                self.assertTrue(m['name'])
                self.assertIn(m['src'], SRC)
        self.assertTrue(ref['stations'])
        for pid, st in ref['stations'].items():
            with self.subTest(station=pid):
                self.assertIn(st['src'], SRC)
                self.assertEqual(st['place'], pid)
                self.assertIn(pid, self.places, 'refinery %r is not a place in locations.json' % pid)
                self.assertEqual(st['name'], self.places[pid][0][1]['name'])
                for ore, reports in st['yields'].items():
                    self.assertIn(ore, ores)
                    self.assertTrue(reports)
                    dates = [r['date'] for r in reports]
                    self.assertEqual(dates, sorted(dates, reverse=True), 'newest first')
                    for r in reports:
                        self.assertIsInstance(r['bonus'], int)
                        self.assertRegex(r['date'], DATE_RE)
                        self.assertIn(r['src'], SRC)
                        self.assertTrue(r['source'])
                        self.assertIn(r['source'], ref['_meta'].get('report_sources', {}))

    # ------------------------------------------------------------------ privacy
    def test_no_personal_data(self):
        """Generic game data only: no Windows user folders, log file names or session ids."""
        bad = re.compile(r'(?i)(C:\\Users\\|AppData|logbackups|Game Build\(|playerId|accountId|geid\b)')
        for p in sorted(REF.glob('*.json')):
            with self.subTest(file=p.name):
                self.assertIsNone(bad.search(p.read_text(encoding='utf-8')))


if __name__ == '__main__':
    unittest.main()
