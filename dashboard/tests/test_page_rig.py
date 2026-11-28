"""The rig reference section of the page (PLAN §4 item 18), in headless Edge over the DevTools
protocol, showing a real service instance (test_page_browser's `Scene`) and the real
`web/rig/rig.json` and images.

What is checked:
- Nothing of the section is fetched before it is opened; then rig.json and only the shown page's
  image. It opens with one click on the switcher in landscape and portrait, terminal on and off,
  and goes back to Live with one click.
- The page's model holds every row of rig.json (`_meta.counts.rows`), each on its view's page, and
  every numbered row has one mark per button on its page, carrying the number.
- Under each filter every row is drawn as the schema's reading rule says (RIG.md, "Reading a
  page filter", written again here in Python): changes or own job cyan, does nothing gray,
  unknown as keeping its job, unbound dim; a control live only in missile or scan mode carries
  that mode's name under Flight; the filter's label names the knob detents.
- Real pointer events: a row rings its mark and a mark its row; a click opens the row with its job
  in every mode; a filter; a Find query (words and a number) and a result opened on its page.
- No computed type under 18 px in any page, filter, opened row or Find query, in the four shapes;
  the view never overflows its region.
- The head's parts (each tab, Find, the key's entries, the filter's label and buttons) never
  intersect and never leave the section, on every page under every filter, in the four shapes and
  the 2560x1300 tab with the terminal on and off.
- Every number drawn over a diagram sits on its mark (rig.json's `discs`), within 2.5 px.
- It stays open, unchanged, through a change of context on the live side; it never changes
  while nothing is done to it (the one-second tick does not touch it); the diagram refits when
  something above the view takes height.

Skipped when Edge is not installed (set SCDASH_EDGE)."""
import json
import re
import sys
import time
import unittest

import scdash_testlib as lib
import test_page_browser as T

RIG = json.loads((lib.DASHBOARD / "web" / "rig" / "rig.json").read_text(encoding="utf-8"))
ROWS = {r["id"]: r for r in RIG["rows"]}
FILTERS = ("all", "flight", "mining", "salvage")
SHAPES = ((1920, 1080, "on"), (1920, 1080, "off"), (1080, 1920, "on"), (1080, 1920, "off"))
UNTIL_MINING = "2026-11-26T23:23:00.000Z"        # run_a.log at the ARC-L4 field: the Mining view

# The numbers drawn over the diagram: each one's center, from the art's corner.
DISCS = r"""
(() => {
  const art = document.querySelector(".rig .dg__art"), ar = art.getBoundingClientRect();
  return { s: +art.dataset.scale || 1, z: parseFloat(getComputedStyle(document.documentElement).zoom) || 1,
           discs: Array.from(document.querySelectorAll(".rig .dn")).map((n) => { const r = n.getBoundingClientRect();
             return { k: n.dataset.key, t: n.textContent.trim(), cx: r.left + r.width / 2 - ar.left, cy: r.top + r.height / 2 - ar.top }; }) };
})()
"""

# The head's parts as drawn, and every pair that intersects or part that leaves the section.
HEAD_OVERLAPS = r"""
(() => {
  const sec = document.querySelector(".rig").getBoundingClientRect();
  const parts = [];
  const name = (n) => n.matches(".tab") ? "tab " + n.dataset.page : n.matches(".mode") ? "filter " + n.dataset.mode
                    : n.matches(".rmk") ? "key " + n.textContent.trim() : "filter label";
  for (const n of document.querySelectorAll(".rig__head .tab, .rig__head .legend .rmk, .rig__head .modes__k, .rig__head .mode")) {
    const r = n.getBoundingClientRect();
    if (r.width && r.height) parts.push([name(n), r]);
  }
  const out = [];
  if (parts.length < 14) out.push("only " + parts.length + " parts drawn");
  const T = 1.5;                       // neighbors share a 1 px border (margin-left: -1px)
  for (const [k, r] of parts) {
    if (r.left < sec.left - 1 || r.right > sec.right + 1 || r.top < sec.top - 1 || r.bottom > sec.bottom + 1)
      out.push(k + " leaves the section");
  }
  for (let i = 0; i < parts.length; i++) for (let j = i + 1; j < parts.length; j++) {
    const a = parts[i][1], b = parts[j][1];
    const x = Math.min(a.right, b.right) - Math.max(a.left, b.left), y = Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top);
    if (x > T && y > T) out.push(parts[i][0] + " and " + parts[j][0] + " overlap by " + Math.round(x) + " x " + Math.round(y) + " px");
  }
  return out;
})()
"""


def kind(row, f):
    """The schema's reading rule: what a row is under a filter."""
    if row.get("unbound"):
        return "unbound"
    if f == "all":
        return "all"
    modes = RIG["live_modes"][f]
    st = row["modes"]
    first = next((m for m in modes if st[m] in ("primary", "variant")), None)
    if first:
        if st[first] == "variant":
            return "change"
        return "keep" if st["combat"] == "primary" or f == "flight" else "own"
    if any(st[m] == "unknown" for m in modes):
        return "keep"                             # drawn as keeping its job
    return "none"


def css_kind(classes):
    c = set(classes.split())
    if "rr--unbound" in c:
        return "unbound"
    if "rr--em" in c:
        return "em"
    if "rr--quiet" in c:
        return "none"
    return "plain"


EXPECT_CSS = {"change": "em", "own": "em", "none": "none", "unbound": "unbound", "keep": "plain", "all": "plain"}


class TheFileAsThePageReadsIt(unittest.TestCase):
    def test_the_schema_and_names_the_page_relies_on(self):
        self.assertEqual(RIG["_meta"]["schema"], 2)
        js = (lib.DASHBOARD / "web" / "app.js").read_text(encoding="utf-8")
        filters = re.findall(r'\["(\w+)", "\w+"\]', re.search(r"const RIG_FILTERS = \[(.*?)\];", js).group(1))
        self.assertEqual(filters, list(FILTERS))
        self.assertEqual(sorted(RIG["live_modes"]), sorted(f for f in FILTERS if f != "all"))
        image = re.compile(re.search(r"const RIG_IMAGE = /(.*?)/;", js).group(1))
        for v in RIG["views"]:
            self.assertTrue(image.fullmatch(v["image"]), v["image"])
            for rid in v["rows"]:
                self.assertEqual(ROWS[rid]["view"], v["id"])
        self.assertEqual(sum(len(v["rows"]) for v in RIG["views"]), RIG["_meta"]["counts"]["rows"])


@unittest.skipUnless(T.find_edge() and sys.platform == "win32", "needs Edge on Windows (set SCDASH_EDGE)")
class RigInTheBrowser(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scene = T.Scene("run_a.log", until=UNTIL_MINING, plan=T.RUN_A_PLAN, terminal=True).start()
        cls.edge = None
        try:
            cls.edge = T.Edge(T.find_edge())
            cls.page = cls.edge.new_page(cls.scene.url)
            if not cls.page.wait("document.getElementById('view-host') && !document.getElementById('view-wait')", 20):
                raise AssertionError("the page drew nothing")
            if not cls.page.wait("document.getElementById('view-host').className === 'v v--mining'", 15):
                raise AssertionError("not the Mining view: %s" % cls.page.js("document.getElementById('view-host').className"))
            cls.before = cls.page.js("performance.getEntriesByType('resource').map((e) => e.name)")
            cls.page.click("#sw-rig")
            if not cls.page.wait("window.scdash.rig() !== null", 20):
                raise AssertionError("the reference did not load: %s" % cls.page.js("(document.querySelector('.rig') || {}).textContent"))
            cls.after = cls.page.js("performance.getEntriesByType('resource').map((e) => e.name)")
            cls.opened_on = cls.page.js("window.scdash.rig().state.mode")
            cls.live_mode = cls.page.js("fetch('/api/state').then((r) => r.json()).then((s) => s.board.view.mode)")
        except Exception:
            cls.tearDownClass()
            raise

    @classmethod
    def tearDownClass(cls):
        try:
            if getattr(cls, "page", None):
                cls.page.close()
            if cls.edge:
                cls.edge.close()
        finally:
            cls.scene.stop()

    def setUp(self):
        p = self.page
        p.size(1920, 1080)
        p.js("document.documentElement.dataset.terminal = 'on'")
        if p.js("document.getElementById('view-host').className") != "v v--reference":
            p.click("#sw-rig")
            self.assertTrue(p.wait("document.getElementById('view-host').className === 'v v--reference'", 10))
        time.sleep(T.SETTLE)

    # helpers
    def state(self):
        return self.page.js("window.scdash.rig().state")

    def go(self, page_id):
        self.page.click('.rig .tab[data-page="%s"]' % page_id)
        self.assertTrue(self.page.wait("window.scdash.rig().state.page === %s" % json.dumps(page_id), 5))
        time.sleep(T.SETTLE)                     # a click right after a redraw is not taken

    def mode(self, f):
        if self.state()["mode"] != f:
            self.page.click('.rig .mode[data-mode="%s"]' % f)
        self.assertTrue(self.page.wait("window.scdash.rig().state.mode === %s" % json.dumps(f), 5))
        time.sleep(T.SETTLE)

    def hover(self, selector):
        x, y = self.page.center(selector)
        self.page.call("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": x, "y": y, "button": "none", "buttons": 0})
        time.sleep(0.05)

    def find_query(self, text):
        p = self.page
        p.click(".rig .find__in")
        p.call("Input.dispatchKeyEvent", {"type": "keyDown", "key": "Escape", "code": "Escape", "windowsVirtualKeyCode": 27})
        p.call("Input.dispatchKeyEvent", {"type": "keyUp", "key": "Escape", "code": "Escape", "windowsVirtualKeyCode": 27})
        if text:
            p.type_text(text)
        self.assertTrue(p.wait("window.scdash.rig().state.q === %s" % json.dumps(text), 5))
        time.sleep(T.SETTLE)

    # the checks
    def test_fetched_only_when_opened_and_opens_on_the_live_mode(self):
        self.assertEqual([u for u in self.before if "/rig/" in u], [])
        rig = sorted(u.rsplit("/", 1)[1] for u in self.after if "/rig/" in u)
        self.assertEqual(rig, ["grip_front.png", "rig.json"])          # the first page's image only
        self.assertEqual(self.live_mode, "mining")
        self.assertEqual(self.opened_on, "mining")

    def test_the_model_holds_every_row_and_every_numbered_row_has_its_marks(self):
        s = self.page.js("window.scdash.rig()")
        self.assertEqual(s["total"], RIG["_meta"]["counts"]["rows"])
        self.assertEqual(s["lost"], 0)
        self.assertEqual([x["id"] for x in s["pages"]], [v["id"] for v in RIG["views"]])
        for pg, v in zip(s["pages"], RIG["views"]):
            self.assertEqual(sorted(pg["rows"] + pg["axes"]), sorted(v["rows"]), v["id"])
            self.assertEqual(pg["discs"], sum(len(ROWS[r]["discs"]) for r in v["rows"]), v["id"])
        self.mode("all")
        for v in RIG["views"]:
            self.go(v["id"])
            drawn = self.page.js("Array.from(document.querySelectorAll('.rig .rr')).map((n) => n.dataset.key)")
            self.assertEqual(sorted(drawn), sorted(v["rows"]), v["id"])
            marks = self.page.js("Array.from(document.querySelectorAll('.rig .dn')).map((n) => [n.dataset.key, n.textContent])")
            for rid in v["rows"]:
                row = ROWS[rid]
                mine = [t for k, t in marks if k == rid]
                if row["buttons"]:
                    self.assertEqual(sorted(mine), sorted(str(b) for b in row["buttons"]), rid)
                else:
                    self.assertEqual(len(mine), len(row["discs"]), rid)     # an axis word's box, or none
        self.go("find")
        self.find_query("")
        self.assertEqual(self.page.js("document.querySelectorAll('.rig .find .rr').length"), len(RIG["rows"]))

    def test_every_row_under_every_filter_follows_the_reading_rule(self):
        self.go("find")
        self.find_query("")
        for f in FILTERS:
            self.mode(f)
            got = dict(self.page.js("Array.from(document.querySelectorAll('.rig .find .rr')).map((n) => [n.dataset.key, n.className])"))
            self.assertEqual(sorted(got), sorted(ROWS), f)
            wrong = ["%s: %s, drawn %s" % (rid, kind(r, f), css_kind(got[rid])) for rid, r in ROWS.items()
                     if EXPECT_CSS[kind(r, f)] != css_kind(got[rid])]
            self.assertEqual(wrong, [], f)
            if f in ("mining", "salvage"):
                lead = sum(1 for r in ROWS.values() if kind(r, f) in ("change", "own"))
                self.assertIn("· %d" % lead, self.page.js("document.querySelector('.rig .find__sec--lead').textContent"))
            knob = sorted(m["knob"]["detent"] for m in RIG["modes"] if m["id"] in RIG["live_modes"].get(f, []))
            label = self.page.js("document.querySelector('.rig .modes__k').textContent")
            self.assertEqual(label, "Mode" if f == "all" else "Mode · knob " + ("%d–%d" % (knob[0], knob[-1]) if len(knob) > 1 else str(knob[0])))
        # under Flight a control live only in missile or scan mode says which
        self.mode("flight")
        tags = dict(self.page.js("Array.from(document.querySelectorAll('.rig .find .rr')).map((n) => [n.dataset.key, (n.querySelector('.rr__l .rr__tag') || {}).textContent || null])"))
        self.assertEqual(tags["js1-2"], "Missile")
        self.assertEqual(tags["js1-18"], "Scan")
        self.assertIsNone(tags["js1-12"])

    def test_point_click_filter_and_find_with_the_pointer(self):
        p = self.page
        self.go("grip_front")
        self.mode("salvage")
        # row -> mark, mark -> row
        self.hover('.rig .rr[data-key="js1-12"]')
        self.assertTrue(p.js("document.querySelector('.rig .dn[data-key=\"js1-12\"]').classList.contains('is-hot')"))
        self.hover('.rig .dn[data-key="js1-13"]')
        self.assertTrue(p.js("document.querySelector('.rig .rr[data-key=\"js1-13\"]').classList.contains('is-hot')"))
        self.assertFalse(p.js("document.querySelector('.rig .dn[data-key=\"js1-12\"]').classList.contains('is-hot')"))
        # a filter: js1-12 takes its salvage job, cyan
        salv = next(v["text"] for v in ROWS["js1-12"]["variants"] if v["mode"] == "salvage")
        self.assertEqual(p.js("document.querySelector('.rig .rr[data-key=\"js1-12\"] .rr__f').textContent"), salv)
        self.assertTrue(p.js("document.querySelector('.rig .dn[data-key=\"js1-12\"]').classList.contains('dn--em')"))
        self.assertEqual(p.js("document.querySelector('.rig .tab[data-page=\"grip_front\"] .tab__n').textContent"),
                         "%d salvage" % sum(1 for r in RIG["views"][0]["rows"] if kind(ROWS[r], "salvage") in ("change", "own")))
        # a click on the mark opens the row with its job in every mode; a second closes it
        p.click('.rig .dn[data-key="js1-12"]')
        self.assertTrue(p.wait("!!document.querySelector('.rig .rr--sel[data-key=\"js1-12\"]')", 5))
        text = p.js("document.querySelector('.rig .rr--sel').textContent")
        for v in ROWS["js1-12"]["variants"]:
            self.assertIn(v["text"], text)
        self.assertIn(ROWS["js1-12"]["text"], text)
        self.assertTrue(p.js("document.querySelector('.rig .dn[data-key=\"js1-12\"]').classList.contains('is-sel')"))
        # a double click on a row opens it once (the second click of a double click is not taken)
        time.sleep(T.SETTLE)
        x, y = p.center('.rig .rr[data-key="js1-13"]')
        for cc in (1, 2):
            p.call("Input.dispatchMouseEvent", {"type": "mousePressed", "x": x, "y": y, "button": "left", "buttons": 1, "clickCount": cc})
            p.call("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": x, "y": y, "button": "left", "buttons": 0, "clickCount": cc})
        time.sleep(T.SETTLE)
        self.assertEqual(self.state()["sel"], "js1-13")
        p.click('.rig .rr[data-key="js1-13"]')
        self.assertTrue(p.wait("!document.querySelector('.rig .rr--sel')", 5))
        time.sleep(T.SETTLE)
        p.click('.rig .dn[data-key="js1-12"]')
        self.assertTrue(p.wait("!!document.querySelector('.rig .rr--sel[data-key=\"js1-12\"]')", 5))
        time.sleep(T.SETTLE)
        p.click('.rig .rr[data-key="js1-12"]')
        self.assertTrue(p.wait("!document.querySelector('.rig .rr--sel')", 5))
        # Find: words as a phrase, then a number; a result opens on its page, outlined
        self.go("find")
        self.find_query("right hat")
        got = p.js("Array.from(document.querySelectorAll('.rig .find .rr')).map((n) => n.dataset.key)")
        self.assertEqual(sorted(got), sorted(r for r, x in ROWS.items() if x["group"] == "right hat"))
        self.find_query("58")                             # a button number: js1 57-59 (a range) and js2 58
        self.assertEqual(sorted(p.js("Array.from(document.querySelectorAll('.rig .find .rr')).map((n) => n.dataset.key)")),
                         sorted(r for r, x in ROWS.items() if 58 in x["buttons"]))
        p.click('.rig .find .rr[data-key="js1-57-59"]')
        self.assertTrue(p.wait("window.scdash.rig().state.page === 'base'", 5))
        self.assertTrue(p.js("!!document.querySelector('.rig .rr--sel[data-key=\"js1-57-59\"]')"))
        self.assertEqual(p.js("document.querySelector('.rig .tab[aria-selected=\"true\"]').dataset.page"), "base")
        self.go("find")
        self.find_query("")

    def test_no_type_under_18_px_and_no_overflow_in_any_state_or_shape(self):
        p = self.page
        problems = []
        pages = [v["id"] for v in RIG["views"]] + ["find"]
        for w, h, term in SHAPES:
            p.size(w, h)
            p.js("document.documentElement.dataset.terminal = %s" % json.dumps(term))
            for f in FILTERS:
                p.js("document.querySelector('.rig .mode[data-mode=%s]').click()" % json.dumps(f))
                for pg in pages:
                    p.js("document.querySelector('.rig .tab[data-page=%s]').click()" % json.dumps(pg))
                    if pg != "find" and f == "salvage":           # an opened row too
                        p.js("document.querySelector('.rig .rr').click()")
                    time.sleep(0.03)
                    for x in p.js(T.SMALL_TYPE):
                        problems.append("%dx%d %s %s %s: %s" % (w, h, term, f, pg, x))
                    over = p.js("(() => { const v = document.getElementById('view'); return Math.max(v.scrollHeight - v.clientHeight, v.scrollWidth - v.clientWidth); })()")
                    if over > 1:
                        problems.append("%dx%d %s %s %s: the view overflows by %s px" % (w, h, term, f, pg, over))
            p.js("(() => { const i = document.querySelector('.rig .find__in'); i.value = 'salvage'; i.dispatchEvent(new Event('input')); })()")
            for x in p.js(T.SMALL_TYPE):
                problems.append("%dx%d %s find 'salvage': %s" % (w, h, term, x))
            p.js("(() => { const i = document.querySelector('.rig .find__in'); i.value = ''; i.dispatchEvent(new Event('input')); })()")
        self.assertEqual(problems, [])

    def test_the_head_never_overlaps_in_any_page_filter_or_shape(self):
        """The user's first look at the real window (2026-11-28): at 1920x1080 with the terminal
        off, the marks' key was drawn on top of the Find tab (the tabs had grown with "+ axes").
        Every part of the head (each tab, Find, each entry of the key, the filter's label and each
        of its buttons) is measured on every page under every filter, in the four shapes and the
        2560x1300 tab: no two may intersect (neighboring tabs and buttons share a 1 px border) and
        none may leave the section."""
        p = self.page
        problems = []
        pages = [v["id"] for v in RIG["views"]] + ["find"]
        for w, h, term in SHAPES + ((2560, 1300, "off"), (2560, 1300, "on")):
            p.size(w, h)
            p.js("document.documentElement.dataset.terminal = %s" % json.dumps(term))
            for f in FILTERS:
                p.js("document.querySelector('.rig .mode[data-mode=%s]').click()" % json.dumps(f))
                for pg in pages:
                    p.js("document.querySelector('.rig .tab[data-page=%s]').click()" % json.dumps(pg))
                    time.sleep(0.03)
                    for x in p.js(HEAD_OVERLAPS):
                        problems.append("%dx%d terminal %s, %s, %s: %s" % (w, h, term, f, pg, x))
        self.assertEqual(problems[:20], [], "%d problems" % len(problems))

    def test_every_number_sits_on_its_mark(self):
        """Each number the page draws over a diagram is centered on the place rig.json gives its
        mark (`discs`, in the art's pixels, times the art's scale), within 2.5 px, on every page in
        three shapes. A number 9 px off passed every test before (page review)."""
        p = self.page
        problems = []
        for w, h, term in ((1920, 1080, "on"), (1080, 1920, "off"), (2560, 1300, "off")):
            p.size(w, h)
            p.js("document.documentElement.dataset.terminal = %s" % json.dumps(term))
            for v in RIG["views"]:
                if not v.get("image"):
                    continue
                p.js("document.querySelector('.rig .tab[data-page=%s]').click()" % json.dumps(v["id"]))
                time.sleep(0.05)
                d = p.js(DISCS)
                if not d["discs"]:
                    problems.append("%dx%d %s: no numbers drawn" % (w, h, v["id"]))
                for x in d["discs"]:
                    want = [q for q in ROWS[x["k"]]["discs"]
                            if (str(q["n"]) == x["t"] if q["n"] is not None else not x["t"])]
                    err = min((abs(x["cx"] / d["z"] - q["x"] * d["s"]) + abs(x["cy"] / d["z"] - q["y"] * d["s"]) for q in want),
                              default=None)
                    if err is None or err > 2.5:
                        problems.append("%dx%d %s: %r of %s is %s px from its mark" % (w, h, v["id"], x["t"], x["k"], err))
        self.assertEqual(problems[:20], [], "%d problems" % len(problems))

    def test_still_while_untouched_and_refits_when_the_view_loses_height(self):
        p = self.page
        self.go("grip_front")
        time.sleep(0.6)                                       # the page's own first fit, after it is drawn
        p.js("window.__rigMut = 0; window.__rigObs = new MutationObserver((l) => { window.__rigMut += l.length; });"
             "window.__rigObs.observe(document.querySelector('.rig'), {subtree: true, childList: true, attributes: true, characterData: true});")
        time.sleep(3.2)                                       # three ticks, and any message the service sends
        self.assertEqual(p.js("window.__rigObs.disconnect(), window.__rigMut"), 0)
        before = float(p.js("document.querySelector('.rig .dg__art').dataset.scale"))
        p.js("(() => { const d = document.createElement('div'); d.id = 'probe-alert'; d.className = 'alert alert--bad';"
             " d.textContent = 'probe'; document.getElementById('alerts').appendChild(d); d.style.height = '220px'; })()")
        self.assertTrue(p.wait("parseFloat(document.querySelector('.rig .dg__art').dataset.scale) < %r" % (before - 0.01), 5),
                        "the diagram did not refit")
        p.js("(() => { const n = document.getElementById('probe-alert'); if (n) n.remove(); })()")
        self.assertTrue(p.wait("Math.abs(parseFloat(document.querySelector('.rig .dg__art').dataset.scale) - %r) < 0.002" % before, 5))

    def test_one_click_open_and_back_in_every_shape_and_it_stays_through_a_change_of_context(self):
        p = self.page
        for w, h, term in SHAPES:
            p.size(w, h)
            p.js("document.documentElement.dataset.terminal = %s" % json.dumps(term))
            p.click("#sw-live")
            self.assertTrue(p.wait("document.getElementById('view-host').className !== 'v v--reference'", 10), (w, h, term))
            time.sleep(T.SETTLE)
            p.click("#sw-rig")
            self.assertTrue(p.wait("document.getElementById('view-host').className === 'v v--reference'"
                                   " && !!document.querySelector('.rig .rig__head .tab')", 10), (w, h, term))
            time.sleep(T.SETTLE)
        p.size(1920, 1080)
        p.js("document.documentElement.dataset.terminal = 'on'")
        self.go("levers")
        self.mode("salvage")
        p.click('.rig .rr[data-key="js2-dial"]')
        self.assertTrue(p.wait("!!document.querySelector('.rig .rr--sel[data-key=\"js2-dial\"]')", 5))
        kept = self.state()
        p.js("document.querySelector('.rig').dataset.probe = 'same node'")
        auto = p.js("fetch('/api/state').then((r) => r.json()).then((s) => s.board.view.auto)")
        # a new quantum target: the live side moves on (a new context)
        line = next(ln for ln in lib.sample_bytes("run_a.log").split(b"\n") if b"Player Selected Quantum Target" in ln and b"LOC_RR_S4_L2" in ln)
        line = b"<" + T.iso_ms(time.time()).encode("ascii") + line[line.index(b">"):] + b"\n"
        self.scene.inst.write_log(line, mode="ab")
        self.assertTrue(p.wait("fetch('/api/state').then((r) => r.json()).then((s) => s.board.view.auto !== %s)" % json.dumps(auto), 20),
                        "the live side did not move on")
        time.sleep(0.6)
        self.assertEqual(p.js("document.getElementById('view-host').className"), "v v--reference")
        self.assertEqual(p.js("document.querySelector('.rig').dataset.probe"), "same node")
        self.assertEqual(self.state(), kept)
        # back to Live with one click, and the reference comes back as it was, on the live mode
        p.click("#sw-live")
        self.assertTrue(p.wait("document.getElementById('view-host').className === 'v v--travel'", 10), p.js("document.getElementById('view-host').className"))
        live_mode = p.js("fetch('/api/state').then((r) => r.json()).then((s) => s.board.view.mode)")
        time.sleep(T.SETTLE)
        p.click("#sw-rig")
        self.assertTrue(p.wait("document.getElementById('view-host').className === 'v v--reference'", 10))
        s = self.state()
        self.assertEqual((s["page"], s["sel"], s["mode"]), ("levers", "js2-dial", live_mode))


if __name__ == "__main__":
    unittest.main()
