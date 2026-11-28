"""Checks on the dashboard's reference tables in dashboard/reference/.

Standard library only; needs no game install. Run from the project root:
    python -m unittest dashboard/tests/test_reference.py
or  python -m unittest discover -s dashboard/tests -p test_reference.py

What is checked: the tables (and their hand-entered inputs) parse as JSON with no duplicate or
empty keys, follow their shape, say where every entry came from, and use `place` ids consistently
across locations.json, ores.json, refineries.json and shops.json; ships, contract kinds, shops and
prices against what the log samples print; and that the generator never goes online by itself.
"""
import ast
import json
import os
import re
import subprocess
import sys
import tempfile
import unicodedata
import unittest
from pathlib import Path
from unittest import mock

REF = Path(__file__).resolve().parent.parent / 'reference'
ROOT = REF.parent.parent
SAMPLES = Path(__file__).resolve().parent / 'samples'
PRICES = REF.parent / 'data' / 'reference' / 'prices.json'
CARDS = ROOT / 'tools' / 'regen_cards.py'
TABLES = ('locations', 'resources', 'ores', 'refineries', 'controls', 'ships', 'contracts', 'shops')
VIEWS = ('combat', 'cargo', 'salvage', 'mining', 'mission')
SETTINGS = ('foot', 'ship', 'vehicle', None)
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


def read_cards(path):
    """The card tables of tools/regen_cards.py, read with ast (nothing in it is run), by device:
    js1 = AB6 + MHG_L + MHG_R, js2 = MTQ_L + MTQ_R. {device: {label: row}}."""
    import ast
    tree = ast.parse(Path(path).read_text(encoding='utf-8'))
    consts = {n.targets[0].id: n.value.value for n in tree.body
              if isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name)
              and isinstance(n.value, ast.Constant)}

    def ev(n):
        if isinstance(n, ast.Constant):
            return n.value
        if isinstance(n, ast.List):
            return [ev(x) for x in n.elts]
        if isinstance(n, ast.Dict):
            return {ev(k): ev(v) for k, v in zip(n.keys, n.values)}
        if isinstance(n, ast.Name):
            return consts[n.id]
        if isinstance(n, ast.Call) and getattr(n.func, 'id', None) == 'V':
            tag, text, color = (ev(a) for a in n.args)
            return {'Tag': tag, 'Text': text, 'Color': color}
        raise ValueError('unexpected card expression')

    tables = {n.targets[0].id: ev(n.value) for n in tree.body
              if isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name)
              and n.targets[0].id in ('AB6', 'MHG_L', 'MHG_R', 'MTQ_L', 'MTQ_R')}
    out = {}
    for dev, names in (('js1', ('AB6', 'MHG_L', 'MHG_R')), ('js2', ('MTQ_L', 'MTQ_R'))):
        out[dev] = {row['Label']: row for t in names for row in tables[t] if 'Label' in row}
    return out


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
                           ('ores', 'spots'), ('refineries', 'stations'), ('refineries', 'places'),
                           ('ships', 'ships'), ('ships', 'fleet'), ('contracts', 'contracts'),
                           ('contracts', 'generators'), ('contracts', 'titles'), ('shops', 'shops')):
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

    # ------------------------------------------------------------------ positions
    def test_positions(self):
        n = 0
        for k, v in self.locs.items():
            if 'pos' in v:
                n += 1
                with self.subTest(code=k):
                    self.assertEqual(len(v['pos']), 3)
                    self.assertTrue(all(isinstance(c, int) for c in v['pos']))
        self.assertGreater(n, 0)
        for pid, entries in self.places.items():
            ps = {tuple(v['pos']) for _k, v in entries if 'pos' in v}
            with self.subTest(place=pid):
                self.assertLessEqual(len(ps), 1, 'one place, one position')

    # ------------------------------------------------------------------ controls (card tables)
    def test_controls_match_the_cards(self):
        """Every control named in controls.hand.json exists on the cards, and controls.json still
        carries the cards' wording. Fails when a card label is renamed or a row's wording changes."""
        cards = read_cards(CARDS)
        hand = load('controls.hand.json')
        for mode, m in hand['modes'].items():
            refs = [c for it in m['items'] for c in it['controls']] + ([m['knob']] if m.get('knob') else [])
            for ref in refs:
                with self.subTest(mode=mode, control=ref):
                    dev, _, label = ref.partition(' ')
                    self.assertIn(label, cards.get(dev, {}), '%s is not on the cards' % ref)
        out = self.t['controls']['modes']
        self.assertEqual(set(out), set(hand['modes']))
        tags = {'mining': 'Mine:', 'salvage': 'Salv:', 'missile': 'Msl:'}
        for mode, m in out.items():
            for it in m['items']:
                for p in it['parts']:
                    with self.subTest(mode=mode, control=p['control']):
                        dev, _, label = p['control'].partition(' ')
                        row = cards[dev][label]
                        self.assertEqual(p['primary'], row['Primary'])
                        self.assertIn(p['text'], [row['Primary']] + [x['Text'] for x in row.get('Variants') or []
                                                                     if x['Tag'] in tags.values()])
                self.assertIn(it['src'], SRC)
                self.assertIn(it.get('status', 'flown'), ('flown', 'unverified', 'trial'))

    # ------------------------------------------------------------------ refining (places and methods)
    def test_refinery_places_and_methods(self):
        ref = self.t['refineries']
        self.assertTrue(ref['places'])
        for pid, p in ref['places'].items():
            with self.subTest(place=pid):
                self.assertIn(pid, self.places)
                self.assertEqual(p['name'], self.places[pid][0][1]['name'])
                self.assertEqual(p['src'], 'game')
                self.assertTrue(p['amenity'] or p['refinery_shop'])
        for pid in ref['stations']:
            with self.subTest(yield_station=pid):
                self.assertIn(pid, ref['places'], 'a station with reported yields has a refinery in the game files')
        self.assertEqual(len(ref['methods']), 9)
        for k, m in ref['methods'].items():
            with self.subTest(method=k):
                self.assertLessEqual(set(m), {'name', 'speed', 'yield', 'detail', 'src'},
                                     'the game holds no numeric cost or time per method: none is invented')
                self.assertIn(m['speed'], ('Slow', 'Normal', 'Fast'))
                self.assertIn(m['yield'], ('low', 'medium', 'high'))
                self.assertEqual(m['src'], 'game')
        self.assertEqual(ref['methods']['FastCareful']['name'], 'Pyrometric Chromalysis')

    # ------------------------------------------------------------------ privacy
    def test_no_personal_data(self):
        """Generic game data only: no Windows user folders, log file names or session ids."""
        bad = re.compile(r'(?i)(C:\\Users\\|AppData|logbackups|Game Build\(|playerId|accountId|geid\b)')
        for p in sorted(REF.glob('*.json')):
            with self.subTest(file=p.name):
                self.assertIsNone(bad.search(p.read_text(encoding='utf-8')))


# ====================================================================== helpers for the round-2 tables
SUB_RE = re.compile(r'^(.+)_(\d+)$')
MARKER_RE = re.compile(r'generator name \[([^\]]*)\], contract \[([^\]]*)\]')
ACCEPTED_RE = re.compile(r'Added notification "Contract (?:Accepted|Complete): +(.+?): "')
SHOP_RE = re.compile(r'shopName\[([^\]]+)\]')
CLASS_RE = re.compile(r"'([A-Z]{3,4}_[A-Za-z0-9_]+?)_(\d{6,})'")


def contract_kind(doc, generator=None, contract=None, title=None):
    """The lookup order contracts.json `_meta.lookup` describes, as the service is to do it.
    Returns (how, kind, view, setting)."""
    cs, gens = doc['contracts'], doc['generators']
    e = cs.get(contract) if contract else None
    if e is None and contract:
        m = SUB_RE.match(contract)
        if m and m.group(1) in cs and int(m.group(2)) < cs[m.group(1)].get('subs', 0):
            e = cs[m.group(1)]
    if e is not None:
        for a in e.get('also') or []:
            if a['generator'] == generator:
                return 'contract', a['kind'], a['view'], e['setting']
        return 'contract', e['kind'], e['view'], e['setting']
    g = gens.get(generator) if generator else None
    if g and g.get('view'):
        return 'generator', g.get('kind', 'unknown'), g['view'], g.get('setting')
    if title:
        t = doc['titles'].get(title)
        if t is None:
            t = next((p for p in doc['title_patterns'] if re.match(p['pattern'], title)), None)
        if t is not None:
            return 'title', t['kind'], t['view'], t['setting']
    for r in doc['rules']:
        for value in (contract, generator):
            if value and re.search(r['pattern'], value):
                return 'rule', r.get('kind', 'unknown'), r['view'], r.get('setting')
    return 'none', 'unknown', 'mission', None


def sample_text():
    """The real (sanitized) log samples. `built_*.log` files are lines made up from the game's
    text for activities no real log covers yet; they prove nothing about what the log prints,
    so the tables are not checked against them here."""
    return '\n'.join(p.read_text(encoding='utf-8', errors='replace')
                     for p in sorted(SAMPLES.glob('*.log')) if not p.name.startswith('built_'))


def fold(s):
    """Compare names without diacritics or case ('Gatac Hyūn' is 'Gatac Hyun' in the game files)."""
    return ''.join(c for c in unicodedata.normalize('NFKD', s) if not unicodedata.combining(c)).lower()


def import_generator():
    if str(REF) not in sys.path:
        sys.path.insert(0, str(REF))
    import build_reference
    return build_reference


# ====================================================================== ships
class Ships(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.doc = load('ships.json')
        cls.ships, cls.fleet = cls.doc['ships'], cls.doc['fleet']
        cls.hand = load('ships.hand.json')

    def test_shape(self):
        how = self.doc['_meta']['cargo_how_means']
        self.assertGreater(len(self.ships), 500)
        for k, e in self.ships.items():
            with self.subTest(cls=k):
                self.assertRegex(k, r'^[A-Za-z0-9_]+$')
                self.assertTrue(e['name'])
                self.assertIn(e['kind'], ('ship', 'ground vehicle'))
                self.assertIn(e['cargo_how'], how)
                if e['cargo_how'] == 'several named grids':
                    self.assertIsNone(e['cargo_scu'])
                    self.assertGreaterEqual(len(e['cargo_grids']), 2)
                else:
                    self.assertIsInstance(e['cargo_scu'], int)
                    self.assertGreaterEqual(e['cargo_scu'], 0)
                    self.assertEqual(e['cargo_scu'] > 0, e['cargo_how'] in ('loadout', 'named grid'))
                self.assertTrue(e['crew'] is None or isinstance(e['crew'], int))
                self.assertEqual(e['src'], 'game')

    def test_golem_ox_cargo(self):
        self.assertEqual(self.ships['DRAK_Golem_OX']['cargo_scu'], 64)
        self.assertEqual(self.ships['DRAK_Golem_OX']['cargo_how'], 'loadout')
        self.assertEqual(self.ships['ANVL_Liberator']['cargo_scu'], 400)

    def test_fleet_is_claude_md_section_11(self):
        """Every ship in the root CLAUDE.md section 11 table is a fleet class here, and no other."""
        text = (ROOT / 'CLAUDE.md').read_text(encoding='utf-8')
        sec = text[text.index('## 11. Fleet'):text.index('### 11.1')]
        names = {fold(n) for n in re.findall(r'^\| \*\*(.+?)\*\* \|', sec, re.M)}
        self.assertEqual(len(names), 11)
        self.assertEqual(names, {fold(f['name']) for f in self.fleet.values()})
        for cls in self.fleet:
            self.assertIn(cls, self.ships)

    def test_fleet_jobs(self):
        jobs = {cls: f['job'] for cls, f in self.fleet.items()}
        self.assertEqual({c: j for c, j in jobs.items() if j},
                         {'DRAK_Golem': 'mining', 'RSI_Salvation': 'salvage', 'DRAK_Golem_OX': 'cargo',
                          'ORIG_m80': 'combat'})
        self.assertIsNone(jobs['GAMA_Hyun'], 'a ship with two jobs decides no view')
        for f in self.fleet.values():
            self.assertEqual(f['src'], 'user')
        self.assertEqual({c: f.get('job') for c, f in self.hand['fleet'].items()}, jobs)

    def test_log_classes_resolve(self):
        """The vehicle classes the sanitized log samples print are keys (the log's own spelling)."""
        classes = set(m.group(1) for m in CLASS_RE.finditer(sample_text()))
        self.assertIn('ORIG_m80', classes)
        for c in sorted(classes):
            with self.subTest(cls=c):
                self.assertIn(c, self.ships)


# ====================================================================== contract kinds
class Contracts(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.doc = load('contracts.json')
        cls.hand = load('contracts.hand.json')

    def test_shape(self):
        cs, gens = self.doc['contracts'], self.doc['generators']
        self.assertGreater(len(cs), 1500)
        for name, e in cs.items():
            with self.subTest(contract=name):
                self.assertIn(e['generator'], gens)
                self.assertIn(e['view'], VIEWS)
                self.assertIn(e['setting'], SETTINGS)
                self.assertTrue(e['kind'])
                self.assertEqual(e['src'], 'game')
                self.assertTrue(e['type'] is None or e['type'] in self.doc['types'])
                if 'subs' in e:
                    self.assertGreater(e['subs'], 0)
                if 'sub_of' in e:
                    self.assertIn(e['sub_of'], cs)
        for g, e in gens.items():
            with self.subTest(generator=g):
                self.assertEqual(sum(e['views'].values()), e['contracts'])
                self.assertEqual('view' in e, len(e['views']) == 1)
        for t, e in self.doc['titles'].items():
            self.assertIn(e['view'], VIEWS)
        for p in self.doc['title_patterns']:
            re.compile(p['pattern'])
            self.assertIn(p['view'], VIEWS)

    def test_every_game_type_has_a_rule(self):
        types = set(self.hand['types'])
        for t in self.doc['types']:
            self.assertIn(t, types, 'mission type %s has no row in contracts.hand.json' % t)

    def test_rules(self):
        self.assertEqual(self.doc['rules'], self.hand['rules'])
        for r in self.hand['rules'] + self.hand['templates'] + self.hand['setting_rules']:
            re.compile(r['pattern'])
            if 'view' in r:
                self.assertIn(r['view'], VIEWS)
            self.assertIn(r.get('setting'), SETTINGS)
        chk = self.doc['_meta']['rules_check']
        self.assertGreaterEqual(chk['same_view'] / chk['contracts'], 0.9,
                                'the fallback rules should agree with the game on most contracts')

    def test_example_is_combat_on_foot(self):
        """The marker line seen in the old logs: generator name [CitizensForProsperity_Mercenary_FPS],
        contract [CFP_Pyro_E_DerelictOutpostsCaves_EliminateAll]."""
        got = contract_kind(self.doc, 'CitizensForProsperity_Mercenary_FPS',
                            'CFP_Pyro_E_DerelictOutpostsCaves_EliminateAll')
        self.assertEqual(got, ('contract', 'combat', 'combat', 'foot'))
        self.assertEqual(self.doc['contracts']['CFP_Pyro_E_DerelictOutpostsCaves_EliminateAll']['giver'],
                         'Citizens for Prosperity')
        # a contract of that generator the table does not know still lands on combat, on foot
        self.assertEqual(contract_kind(self.doc, 'CitizensForProsperity_Mercenary_FPS', 'CFP_NotYetMade'),
                         ('generator', 'combat', 'combat', 'foot'))

    def test_marker_lines_in_the_samples(self):
        """Every marker line in the samples resolves to a game record of the same generator; the
        `_<n>` endings the log prints are sub-contract indexes the record has."""
        pairs = set(MARKER_RE.findall(sample_text()))
        self.assertTrue(pairs)
        subs = 0
        for gen, con in sorted(pairs):
            with self.subTest(contract=con):
                how, kind, view, _setting = contract_kind(self.doc, gen, con)
                self.assertEqual(how, 'contract')
                base = con if con in self.doc['contracts'] else SUB_RE.match(con).group(1)
                subs += base != con
                self.assertEqual(self.doc['contracts'][base]['generator'], gen)
                self.assertEqual(view, 'cargo')
        self.assertGreater(subs, 0, 'the samples include sub-contract names')

    def test_titles_in_the_samples(self):
        titles = set(ACCEPTED_RE.findall(sample_text()))
        self.assertTrue(titles)
        for t in sorted(titles):
            with self.subTest(title=t):
                self.assertEqual(contract_kind(self.doc, title=t)[:3], ('title', 'delivery', 'cargo'))

    def test_unknown_lands_on_mission(self):
        self.assertEqual(contract_kind(self.doc, 'Zzz_NewGiver_Generator', 'Zzz_Unheard_Of_Thing'),
                         ('none', 'unknown', 'mission', None))
        self.assertEqual(contract_kind(self.doc), ('none', 'unknown', 'mission', None))

    def test_bounty_hunters_guild(self):
        """5.0's guild missions come from a contractor this build already has generators for; a new
        contract name under a new generator still lands on combat by the rules (names invented)."""
        gens = self.doc['generators']
        bhg = sorted(g for g in gens if g.startswith('BountyHuntersGuild_'))
        self.assertTrue(bhg)
        for g in bhg:
            self.assertEqual(gens[g]['view'], 'combat')
        self.assertEqual(contract_kind(self.doc, 'BountyHuntersGuild_FPS', 'Zzz_New')[2:], ('combat', 'foot'))
        self.assertEqual(contract_kind(self.doc, 'Zzz_BountyHuntersGuild_Board', 'Zzz_BHG_Bounty_Easy')[2:],
                         ('combat', 'ship'))


# ====================================================================== shops
class Shops(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.doc = load('shops.json')
        cls.shops = cls.doc['shops']
        places = set(v['place'] for v in load('locations.json')['locations'].values() if v.get('place'))
        cls.place_ids = places

    def test_shape(self):
        kinds = {'commodity terminal', 'item shop', 'refinery', 'rental', 'landing services', 'other'}
        for name, s in self.shops.items():
            with self.subTest(shop=name):
                self.assertTrue(name.startswith('SCShop_'))
                self.assertIn(s['kind'], kinds)
                self.assertTrue(s['name'])
                self.assertEqual(s['place'] is not None, len(s['places']) == 1)
                if s['place']:
                    self.assertEqual(s['places'], [s['place']])
                for p in s['places']:
                    self.assertIn(p, self.place_ids)
                self.assertIn(s['src'], SRC)
        c = self.doc['_meta']['counts']
        self.assertEqual(c['one_place'] + c['shared'] + c['unplaced'], len(self.shops))

    def test_names_seen_in_logs(self):
        """The nine shop names in the old logs (data/handoff/activity_survey.md) and those in the samples."""
        seen = {'SCShop_CommEx_TDD_NewBabbage', 'SCShop_Admin_lt_base_g', 'SCShop_AdminOffice_GrimHex',
                'SCShop_Levski_CargoOffice_Commodities', 'SCShop_Pyro_RestStop_Rund_Admin',
                'SCShop_ht_delta_rayari_m_store', 'SCShop_ht_delta_shubin_m_store', 'SCShop_RefineryAdmin_ORE',
                'SCShop_Refinery_Rentals'}
        seen |= set(SHOP_RE.findall(sample_text()))
        for n in sorted(seen):
            with self.subTest(shop=n):
                self.assertIn(n, self.shops)
        tdd = self.shops['SCShop_CommEx_TDD_NewBabbage']
        self.assertEqual((tdd['kind'], tdd['place']), ('commodity terminal', 'new-babbage'))
        ore = self.shops['SCShop_RefineryAdmin_ORE']
        self.assertEqual(ore['kind'], 'refinery')
        self.assertIsNone(ore['place'])
        self.assertIn('mic-l2', ore['places'])
        self.assertEqual(self.shops['SCShop_Refinery_Rentals']['kind'], 'rental')
        self.assertGreater(len(self.shops['SCShop_Admin_lt_base_g']['places']), 10, 'a chain template is shared')


# ====================================================================== prices, and staying offline
def _uex_fixture(folder):
    """A tiny made-up UEX snapshot in the API's own envelope (invented figures)."""
    prices = {'status': 'ok', 'data': [
        {'commodity_name': 'Tungsten', 'id_terminal': 7, 'price_buy': 0, 'price_sell': 3000,
         'date_modified': 1795000000},
        {'commodity_name': 'Agricium', 'id_terminal': 7, 'price_buy': 2500, 'price_sell': 0,
         'date_modified': 1795000000},
        {'commodity_name': 'Made Up Goods', 'id_terminal': 8, 'price_buy': 10, 'price_sell': 9,
         'date_modified': 'not a time'},
        {'commodity_name': 'Tungsten', 'id_terminal': 99, 'price_buy': 1, 'price_sell': 1}]}
    terms = {'status': 'ok', 'data': [
        {'id': 7, 'name': 'Admin - Test', 'type': 'commodity', 'space_station_name': 'ARC-L1 Wide Forest Station',
         'star_system_name': 'Stanton'},
        {'id': 8, 'name': 'Nowhere', 'type': 'commodity', 'city_name': 'No Such City'}, 'junk']}
    (Path(folder) / 'commodities_prices_all.json').write_text(json.dumps(prices), encoding='utf-8')
    (Path(folder) / 'terminals.json').write_text(json.dumps(terms), encoding='utf-8')


class Prices(unittest.TestCase):

    def test_prices_are_not_committed(self):
        self.assertFalse((REF / 'prices.json').exists(), 'prices.json belongs in dashboard/data/reference/')
        self.assertFalse(list(REF.glob('*uex*')) + list(REF.glob('*scmdb*')))
        ignore = (ROOT / '.gitignore').read_text(encoding='utf-8')
        self.assertIn('dashboard/data/', ignore)

    def test_builder_offline(self):
        """The normal-run prices path (load_uex + build_prices) works with every socket refused."""
        br = import_generator()
        locs = load('locations.json')['locations']
        res = load('resources.json')['resources']
        shops = load('shops.json')['shops']

        def refuse(*a, **k):
            raise AssertionError('network use')
        with tempfile.TemporaryDirectory() as d, \
                mock.patch('socket.socket.connect', refuse), mock.patch('socket.create_connection', refuse), \
                mock.patch.object(br, '_get_json', refuse):
            _uex_fixture(d)
            snap = br.load_uex([Path(d) / 'missing', d])
            self.assertIsNotNone(snap)
            com, terms, counts = br.build_prices(locs, res, shops, snap)
        self.assertEqual(set(terms), {'7', '8'})
        self.assertEqual(terms['7']['place'], 'arc-l1')
        self.assertEqual(terms['7']['shop'], 'SCShop_Admin_lt_base_g')
        self.assertIsNone(terms['8']['place'])
        self.assertEqual(com['Tungsten']['rows'], [{'terminal': 7, 'place': 'arc-l1', 'buy': None, 'sell': 3000,
                                                    'date': '2026-11-18'}])
        self.assertIsNotNone(com['Tungsten']['resource'])
        self.assertIsNone(com['Made Up Goods']['resource'])
        self.assertIsNone(com['Made Up Goods']['rows'][0]['date'])
        self.assertEqual(counts['terminals_without_place'], 1)

    def test_prices_file_shape(self):
        if not PRICES.exists():
            self.skipTest('no prices.json (git-ignored; built when a UEX snapshot is on disk)')
        p = json.loads(PRICES.read_text(encoding='utf-8'))
        shops = load('shops.json')['shops']
        places = set(v['place'] for v in load('locations.json')['locations'].values() if v.get('place'))
        self.assertIn('why_not_in_git', p['_meta'])
        for tid, t in p['terminals'].items():
            self.assertTrue(t['place'] is None or t['place'] in places)
            self.assertTrue(t['shop'] is None or t['shop'] in shops)
            self.assertEqual(t['src'], 'ref')
        for c, e in p['commodities'].items():
            for r in e['rows']:
                self.assertIn(str(r['terminal']), p['terminals'])
                self.assertTrue(r['buy'] is not None or r['sell'] is not None)
                self.assertTrue(r['date'] is None or DATE_RE.match(r['date']))


class StaysOffline(unittest.TestCase):

    def test_import_loads_no_network_module(self):
        code = ('import sys; sys.path.insert(0, %r); import build_reference; '
                'print("urllib.request" in sys.modules, "http.client" in sys.modules)' % str(REF))
        out = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True, timeout=60)
        self.assertEqual(out.stdout.split(), ['False', 'False'], out.stderr)

    def test_check_and_fetch_exclude_each_other(self):
        br = import_generator()
        self.assertFalse(br.parse_args(['--check']).fetch)
        with mock.patch('sys.stderr'), self.assertRaises(SystemExit):
            br.parse_args(['--check', '--fetch'])

    def test_only_fetch_goes_online(self):
        """In the generator's source, urlopen is reached only through _get_json, _get_json only from
        fetch_snapshots, and fetch_snapshots only under `if args.fetch:` in main."""
        tree = ast.parse((REF / 'build_reference.py').read_text(encoding='utf-8'))
        calls = {}
        guarded = []
        for fn in [n for n in tree.body if isinstance(n, ast.FunctionDef)]:
            for node in ast.walk(fn):
                if isinstance(node, ast.Call):
                    f = node.func
                    name = f.attr if isinstance(f, ast.Attribute) else getattr(f, 'id', None)
                    calls.setdefault(name, set()).add(fn.name)
            if fn.name == 'main':
                for node in ast.walk(fn):
                    if isinstance(node, ast.If) and ast.unparse(node.test) == 'args.fetch':
                        guarded += [ast.unparse(s) for s in node.body]
        self.assertEqual(calls.get('urlopen'), {'_get_json'})
        self.assertEqual(calls.get('_get_json'), {'fetch_snapshots'})
        self.assertEqual(calls.get('fetch_snapshots'), {'main'})
        self.assertIn('fetch_snapshots()', guarded)
        src = ast.unparse(next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'main'))
        self.assertEqual(src.count('fetch_snapshots('), 1)

    def test_check_never_reaches_the_network(self):
        """`main(['--check', ...])` with no game stops before anything else, and never opens a socket."""
        br = import_generator()

        def refuse(*a, **k):
            raise AssertionError('network use')
        with mock.patch('socket.socket.connect', refuse), mock.patch.object(br, '_get_json', refuse), \
                mock.patch.object(br, 'fetch_snapshots', refuse), self.assertRaises(SystemExit):
            br.main(['--check', '--p4k', os.path.join(tempfile.gettempdir(), 'no-such-Data.p4k')])


# ====================================================================== generated and hand files apart
class HandAndGenerated(unittest.TestCase):

    def test_hand_files_hold_only_hand_data(self):
        self.assertEqual(set(load('ships.hand.json')), {'_doc', 'fleet', 'ships'})
        self.assertEqual(set(load('shops.hand.json')), {'_doc', 'kinds', 'labels', 'shops'})
        self.assertEqual(set(load('contracts.hand.json')),
                         {'_doc', 'types', 'templates', 'template_settings', 'setting_rules', 'rules'})

    def test_outputs_say_they_are_generated(self):
        for name in ('ships', 'contracts', 'shops', 'refineries'):
            with self.subTest(table=name):
                m = load('%s.json' % name)['_meta']
                self.assertIn('%s.hand.json' % name, m['generated_by'])
                self.assertIn('inputs', m)
                self.assertRegex(m['inputs'], r'^[0-9a-f]{12}$')

    def test_generated_entries_come_from_the_game(self):
        """Only the hand file's keys may carry another source; the rest of each table is the game's."""
        for name, main in (('ships', 'ships'), ('contracts', 'contracts'), ('shops', 'shops')):
            doc = load('%s.json' % name)
            hk = set(doc['_meta']['hand_keys'])
            for k, v in doc[main].items():
                if k not in hk:
                    self.assertEqual(v.get('src'), 'game', '%s: %s' % (name, k))


if __name__ == '__main__':
    unittest.main()
