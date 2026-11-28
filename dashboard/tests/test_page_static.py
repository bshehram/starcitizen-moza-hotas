"""The page's three files read as text (no browser): the rules that keep it inside its content
policy and its type floor, proven from the source.

- Every view the service can send (plan.VIEWS and the reference) has a renderer in app.js, and
  each is the function named for its view (v<Name>), with a body of its own.
- No inline script, no inline style attribute, no event-handler attribute, no style set as a
  string from script (nor through setAttributeNS or an attribute name in a variable), no web font.
- Nothing from another origin: no address with a scheme, a `//host`, an IP address or localhost
  in any of the three files; `location` is only reloaded; fetches and streams take literal paths.
- Text is never parsed as markup: app.js has no innerHTML, outerHTML, insertAdjacentHTML,
  setHTMLUnsafe, document.write, eval, Function constructor, DOMParser or createContextualFragment,
  no string that spells part of one, and no property key joined from strings.
- No type under 18 px: every font size in style.css (whatever the property's case), literal or
  through a custom property, resolves to 18 px or more, and every type token is 18 px or more
  wherever it is set; no zoom under 1, no font-size-adjust, no scale() under 1 on anything but an
  icon, and no size set from script without the floor.

test_page_browser.py measures the same floor in the browser, in every view."""
import re
import unittest

import scdash_testlib as lib
from scdash import plan as P

WEB = lib.DASHBOARD / "web"
FLOOR_PX = 18
SVG_NS = "http://www.w3.org/2000/svg"


def read(name):
    return (WEB / name).read_text(encoding="utf-8")


def strip_css_comments(css):
    return re.sub(r"/\*.*?\*/", "", css, flags=re.S)


def strip_js_comments(js):
    out, i, n = [], 0, len(js)
    quote = None
    while i < n:
        c = js[i]
        if quote:
            out.append(c)
            if c == "\\" and i + 1 < n:
                out.append(js[i + 1])
                i += 2
                continue
            if c == quote:
                quote = None
            i += 1
            continue
        if c in "\"'`":
            quote = c
            out.append(c)
            i += 1
            continue
        if js.startswith("//", i):
            j = js.find("\n", i)
            i = n if j < 0 else j
            continue
        if js.startswith("/*", i):
            j = js.find("*/", i + 2)
            i = n if j < 0 else j + 2
            continue
        out.append(c)
        i += 1
    return "".join(out)


def string_literals(js):
    """The contents of every string literal in comment-free JavaScript (quotes and backticks)."""
    out, i, n = [], 0, len(js)
    while i < n:
        c = js[i]
        if c in "\"'`":
            j, buf = i + 1, []
            while j < n and js[j] != c:
                if js[j] == "\\" and j + 1 < n:
                    buf.append(js[j:j + 2])
                    j += 2
                    continue
                buf.append(js[j])
                j += 1
            out.append("".join(buf))
            i = j + 1
            continue
        i += 1
    return out


def renderer_names(js):
    m = re.search(r"const RENDERERS = \{(.*?)\};", js, re.S)
    if not m:
        return set()
    return set(re.findall(r"([a-z]+)\s*:", m.group(1)))


def css_tokens(css):
    """Every custom property set anywhere: name -> [values]."""
    out = {}
    for name, value in re.findall(r"(--[\w-]+)\s*:\s*([^;}]+)", css):
        out.setdefault(name, []).append(value.strip())
    return out


def px_of(value, tokens, seen=()):
    """The pixel sizes a font size can take: a list, empty when it cannot be resolved."""
    value = value.strip()
    m = re.fullmatch(r"(\d+(?:\.\d+)?)px", value)
    if m:
        return [float(m.group(1))]
    m = re.fullmatch(r"var\((--[\w-]+)\)", value)
    if m and m.group(1) not in seen:
        out = []
        for v in tokens.get(m.group(1), []):
            out += px_of(v, tokens, seen + (m.group(1),))
        return out
    return []


def font_sizes(css):
    """(selector, size text) for every font size declared, from `font-size:` and from the size
    part of a `font:` shorthand (the value before a `/line-height`, or the one before the family)."""
    out = []
    for sel, body in re.findall(r"([^{}]+)\{([^{}]*)\}", css):
        for prop, value in re.findall(r"(?<![\w-])(font-size|font)\s*:\s*([^;]+)", body, re.I):   # CSS names ignore case
            prop = prop.lower()
            value = re.sub(r"(?i)!\s*important", "", value).strip()
            if prop == "font-size":
                out.append((sel.strip(), value))
                continue
            if value in ("inherit", "initial", "unset"):
                continue
            m = re.search(r"(var\(--[\w-]+\)|\d+(?:\.\d+)?(?:px|em|rem|%|pt|vw|vh))\s*(?:/|\s+var\(--f-)", value)
            out.append((sel.strip(), m.group(1) if m else value))
    return out


class ViewRenderers(unittest.TestCase):
    def test_every_view_the_service_can_send_has_a_renderer(self):
        names = set(P.VIEWS) | {P.REFERENCE}
        have = renderer_names(read("app.js"))
        self.assertTrue(have, "no RENDERERS table found in app.js")
        self.assertEqual(sorted(names - have), [], "views with no renderer")
        self.assertEqual(sorted(have - names), [], "renderers for views the service does not send")

    def test_each_view_is_drawn_by_its_own_renderer(self):
        """`selling: vIdle` or `refinery: (m) => frameOnly("refinery")` keep the table complete and
        draw the wrong thing (page review). Each name maps to v<Name>, which exists, takes its model
        and is more than the empty frame."""
        js = strip_js_comments(read("app.js"))
        block = re.search(r"const RENDERERS = \{(.*?)\};", js, re.S).group(1)
        pairs = re.findall(r"([a-z]+)\s*:\s*([^,}]+)", block)
        self.assertEqual(sorted(n for n, _ in pairs), sorted(set(P.VIEWS) | {P.REFERENCE}))
        for name, fn in pairs:
            want = "v" + name[0].upper() + name[1:]
            self.assertEqual(fn.strip(), want, "%s is drawn by %s" % (name, fn.strip()))
            m = re.search(r"function %s\((\w*)[^)]*\)\s*\{(.*?)\n  \}" % want, js, re.S)
            self.assertIsNotNone(m, "no function %s" % want)
            body = m.group(2)
            self.assertTrue(m.group(1), "%s does not take its model" % want)
            self.assertNotRegex(body.strip(), r"^return frameOnly\(", "%s is only the empty frame" % want)
            self.assertGreater(len(body), 120, "%s is hollow" % want)


class ContentPolicy(unittest.TestCase):
    def test_no_inline_script_style_or_handler_in_the_markup(self):
        html = read("index.html")
        for m in re.finditer(r"<script\b([^>]*)>(.*?)</script>", html, re.S | re.I):
            self.assertIn("src=", m.group(1), "an inline script")
            self.assertEqual(m.group(2).strip(), "", "a script with a body")
        self.assertIsNone(re.search(r"\sstyle\s*=", html, re.I), "an inline style attribute")
        self.assertIsNone(re.search(r"<style\b", html, re.I), "a style element")
        self.assertIsNone(re.search(r"\son[a-z]+\s*=", html, re.I), "an event-handler attribute")
        self.assertIsNone(re.search(r"javascript:", html, re.I), "a javascript: address")

    def test_no_style_set_as_a_string_from_script(self):
        js = strip_js_comments(read("app.js"))
        self.assertIsNone(re.search(r"setAttribute\(\s*['\"]style['\"]", js), "a style attribute set from script")
        self.assertIsNone(re.search(r"\.cssText\b", js), "cssText")
        self.assertIsNone(re.search(r"setAttribute\(\s*['\"]on", js), "an event-handler attribute set from script")

    def test_nothing_from_another_origin(self):
        for name in ("index.html", "app.js", "style.css"):
            text = read(name)
            text = strip_css_comments(text) if name.endswith(".css") else text
            text = strip_js_comments(text) if name.endswith(".js") else text
            urls = [u for u in re.findall(r"(?:https?:)?//[\w.-]+\.[a-z]{2,}[^\s'\")]*", text, re.I) if u != SVG_NS]
            self.assertEqual(urls, [], "%s names another origin" % name)
        css = strip_css_comments(read("style.css"))
        self.assertIsNone(re.search(r"@import|@font-face", css), "an import or a web font")
        for u in re.findall(r"url\(\s*([^)]*)\)", css):
            self.assertTrue(u.strip("'\" ").startswith("data:"), "a stylesheet url(): %s" % u)
        html = read("index.html")
        for attr in re.findall(r"\s(?:src|href)\s*=\s*\"([^\"]*)\"", html):
            self.assertTrue(attr.startswith("/") and not attr.startswith("//") or attr.startswith("#") or attr.startswith("data:"),
                            "index.html loads %r" % attr)

    def test_text_is_never_parsed_as_markup(self):
        js = strip_js_comments(read("app.js"))
        for bad in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval(", "new Function",
                    "Function(", "DOMParser", "createContextualFragment", "srcdoc", "setHTMLUnsafe", "setHTML(",
                    "parseHTMLUnsafe", "parseHTML(", "insertAdjacentElement", "execCommand"):
            self.assertNotIn(bad, js, "app.js uses %s" % bad)

    def test_no_markup_writer_spelled_another_way(self):
        """The names above can be put together at run time: `el["inner" + "HTML"]`. No string in
        app.js holds any part of "HTML" (the page never needs one), and no property is reached
        through a key built by joining strings (page review: three such mutations went unseen)."""
        js = strip_js_comments(read("app.js"))
        for lit in string_literals(js):
            self.assertNotRegex(lit, r"(?i)html|innerh|outerh|adjacent", "a string that names markup: %r" % lit)
        self.assertIsNone(re.search(r"\[\s*([\"'`])[^\"'`\]]*\1\s*\+", js), "a property key joined from strings")

    def test_no_style_attribute_by_any_name(self):
        """`setAttribute` and `setAttributeNS` take only a literal name, and never `style` or an
        event handler: a name in a variable (`"sty" + "le"`) or the NS form got past the test above."""
        js = strip_js_comments(read("app.js"))
        for m in re.finditer(r"\.setAttribute\(\s*([^,]*),", js):
            arg = m.group(1).strip()
            self.assertRegex(arg, r"^([\"'])[\w-]+\1$", "setAttribute with a name that is not a literal: %s" % arg)
            self.assertNotRegex(arg.lower(), r"^[\"'](style|on\w*|srcdoc)[\"']$", "setAttribute(%s)" % arg)
        self.assertNotIn("setAttributeNS", js, "setAttributeNS (the namespaced form of setAttribute)")
        self.assertNotIn("setAttributeNode", js)
        self.assertNotIn("attributes[", js)

    def test_the_page_never_leaves_its_origin(self):
        """No address with a scheme or a host in it at all (an IP address, `localhost:2942` and a
        bare `//host` included; the SVG namespace is a name, not a load), and nothing that sends
        the page somewhere else: `location` is only ever reloaded."""
        for name in ("index.html", "app.js", "style.css"):
            text = read(name)
            text = strip_css_comments(text) if name.endswith(".css") else text
            text = strip_js_comments(text) if name.endswith(".js") else text
            text = text.replace(SVG_NS, "")
            self.assertIsNone(re.search(r"(?i)\b[a-z][a-z0-9+.-]*://", text), "%s holds an address with a scheme" % name)
            self.assertIsNone(re.search(r"(?i)[\"'(=]\s*//[\w\[]", text), "%s holds a //host address" % name)
            self.assertIsNone(re.search(r"(?i)\b(localhost|127\.0\.0\.1|\d{1,3}(\.\d{1,3}){3})(:\d+)?\b", text),
                              "%s names a host" % name)
        js = strip_js_comments(read("app.js"))
        for m in re.finditer(r"\blocation\b\s*(\.\s*\w+|\[|=)", js):
            self.assertEqual(re.sub(r"\s", "", m.group(1)), ".reload", "location%s: only a reload is allowed" % m.group(1))
        for bad in ("window.open", ".href =", ".href=", "navigate(", "sendBeacon", "WebSocket", "new Worker",
                    "importScripts", "import("):
            self.assertNotIn(bad, js, "app.js: %s" % bad)

    def test_fetches_and_streams_name_the_page_s_own_paths(self):
        """Every fetch, EventSource and image source is a literal path from the root, a path
        passed in by a caller, or a rig image name checked against RIG_IMAGE."""
        js = strip_js_comments(read("app.js"))
        for m in re.finditer(r"\b(fetch|EventSource)\(\s*([^,)]*)", js):
            arg = m.group(2).strip()
            self.assertTrue(re.fullmatch(r"([\"'])/[\w/.-]*\1", arg) or arg in ("path",),
                            "%s(%s): not a literal path of this origin" % (m.group(1), arg))
        for m in re.finditer(r"\.src\s*=\s*([^;\n]*)", js):
            self.assertEqual(m.group(1).strip(), '"/rig/" + p.image', "an image source other than a rig diagram: %s" % m.group(1))
        self.assertIn("RIG_IMAGE.test(", js, "the rig's image names are checked before they are used")


class TypeFloor(unittest.TestCase):
    def setUp(self):
        self.css = strip_css_comments(read("style.css"))
        self.tokens = css_tokens(self.css)

    def test_every_type_token_is_18_px_or_more_wherever_it_is_set(self):
        small = []
        for name, values in self.tokens.items():
            if not (name.startswith("--t-") or name in ("--fig", "--hero")):
                continue
            for v in values:
                sizes = px_of(v, self.tokens)
                if not sizes:
                    small.append("%s: %s (not a size this test can read)" % (name, v))
                small += ["%s: %s" % (name, v) for s in sizes if s < FLOOR_PX]
        self.assertEqual(small, [])

    def test_every_font_size_resolves_to_18_px_or_more(self):
        bad = []
        for sel, value in font_sizes(self.css):
            sizes = px_of(value, self.tokens)
            if not sizes:
                bad.append("%s: %s (not a size this test can read)" % (sel, value))
            bad += ["%s: %s = %gpx" % (sel, value, s) for s in sizes if s < FLOOR_PX]
        self.assertEqual(bad, [])

    def test_nothing_makes_type_smaller_than_its_size(self):
        """A size can be undercut without a font size (page review): `zoom` under 1, a
        `transform: scale()` under 1, `font-size-adjust`. Only the 4K step zooms (by 1.5), and only
        the travel legs' diamond (an icon, no text) is scaled down."""
        for sel, body in re.findall(r"([^{}]+)\{([^{}]*)\}", self.css):
            for v in re.findall(r"(?i)(?<![\w-])zoom\s*:\s*([^;]+)", body):
                self.assertRegex(v.strip(), r"^(1(\.\d+)?|[2-9](\.\d+)?|normal)$", "%s: zoom %s" % (sel.strip(), v))
            self.assertIsNone(re.search(r"(?i)font-size-adjust", body), "%s: font-size-adjust" % sel.strip())
            for v in re.findall(r"(?i)\bscale[xyz3d]*\(\s*([^),]+)", body) + re.findall(r"(?i)(?<![\w-])scale\s*:\s*([\d.]+)", body):
                if float(re.sub(r"[^\d.]", "", v) or 1) < 1:
                    self.assertEqual(sel.strip(), ".leg__dot", "%s scales down by %s" % (sel.strip(), v))
        js = strip_js_comments(read("app.js"))
        for bad in (r"\.style\.(zoom|transform|scale|fontSizeAdjust|font|fontStretch)\b\s*=",
                    r"\.style\[", r"setProperty\(\s*[\"'](font|zoom|transform|scale)", r"\.style\s*=", r"\.cssText"):
            self.assertIsNone(re.search(bad, js), "app.js sets a size another way: %s" % bad)
        for m in re.finditer(r"\.style\.fontSize\s*=\s*([^;\n]+)", js):
            v = m.group(1).strip()
            self.assertTrue(v == '""' or v.startswith("Math.max(18,"), "a font size set from script without the floor: %s" % v)

    def test_the_parser_sees_the_sizes(self):
        sizes = font_sizes(self.css)
        self.assertGreater(len(sizes), 100)        # the stylesheet sets many; a parser that sees none proves nothing
        self.assertIn(("body", "var(--t-m)"), sizes)


if __name__ == "__main__":
    unittest.main()
