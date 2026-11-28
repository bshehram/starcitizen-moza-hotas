"""The page's three files read as text (no browser): the rules that keep it inside its content
policy and its type floor, proven from the source.

- Every view the service can send (plan.VIEWS and the reference) has a renderer in app.js.
- No inline script, no inline style attribute, no event-handler attribute, no style set as a
  string from script, nothing loaded from another origin, no web font.
- Text is never parsed as markup: app.js has no innerHTML, outerHTML, insertAdjacentHTML,
  document.write, eval, Function constructor, DOMParser or createContextualFragment.
- No type under 18 px: every font size in style.css, literal or through a custom property, resolves
  to 18 px or more, and every type token is 18 px or more wherever it is set.

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
        for prop, value in re.findall(r"(?<![\w-])(font-size|font)\s*:\s*([^;]+)", body):
            value = value.replace("!important", "").strip()
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
                    "Function(", "DOMParser", "createContextualFragment", "srcdoc"):
            self.assertNotIn(bad, js, "app.js uses %s" % bad)


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

    def test_the_parser_sees_the_sizes(self):
        sizes = font_sizes(self.css)
        self.assertGreater(len(sizes), 100)        # the stylesheet sets many; a parser that sees none proves nothing
        self.assertIn(("body", "var(--t-m)"), sizes)


if __name__ == "__main__":
    unittest.main()
