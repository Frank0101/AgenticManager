"""Unit tests for skills/agentic-manager-slides-deck/scripts/make_deck.py.
The whole pipeline has end-to-end tests in test_e2e_pipeline.py.
Run with: python3 tests/run.py agentic-manager-slides-deck
"""

import json
import os
import re
import sys
import unittest

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(TEST_DIR))
sys.path.insert(0, os.path.join(REPO_ROOT, "skills",
                os.path.basename(TEST_DIR), "scripts"))
import check_deck  # noqa: E402
import common  # noqa: E402
import make_deck  # noqa: E402
sys.path.insert(0, TEST_DIR)
from deck_fixture import content, slide  # noqa: E402


def chart_data(page):
    """The charts' data the page's script holds, as written there."""
    line = check_deck.CHARTS_DATA.search(page)
    assert line
    return line[1]


class ProblemsTest(unittest.TestCase):
    def test_the_fixture_is_valid(self):
        errors, texts = make_deck.problems(content())
        self.assertEqual(errors, [])
        self.assertEqual(len(texts), 3)

    def test_svg_fragment_urls_are_allowed(self):
        # An SVG paint server, such as a gradient, is a url() to a fragment
        # of the page itself, not a file.
        data = content()
        data["slides"][0] = slide("<svg><defs><linearGradient id='g'/></defs>"
                                  "<rect style='fill: url(#g)' width='1' height='1'/></svg>")
        data["style"] = [".a { fill: url(#g); }"]
        self.assertEqual(make_deck.problems(data)[0], [])

    def test_problems_name_the_field(self):
        # Each case: a change to the fixture, and the problem it raises.
        def ring(**changes):
            def change(data):
                data["rings"]["phases"].update(changes)
            return change

        def set_slide(*lines, **fields):
            def change(data):
                data["slides"][0] = dict(slide(*lines), **fields)
            return change

        cases = [
            ("slides not a list", lambda d: d.update(
                {"slides": "x"}), "slides: must be a nonempty list"),
            ("unknown field", lambda d: d.update(
                {"notes": []}), "slides.json: unknown field(s) notes"),
            ("title on two lines", lambda d: d.update(
                {"title": "A\nB"}), "title: must be one nonempty line"),
            ("style as a string", lambda d: d.update(
                {"style": ".a {}"}), "style: must be a list of lines"),
            ("style imports", lambda d: d.update(
                {"style": ["@import url(x.css);"]}), "style: must not load files"),
            ("remote image in CSS", lambda d: d.update(
                {"style": [".a { background: url('https://x/y.png'); }"]}), "style: must not load"),
            ("no slides", lambda d: d.update(
                {"slides": []}), "slides: must be a nonempty list"),
            ("empty html", set_slide(" "), "slides[0].html: is empty"),
            ("bad class", set_slide("<p>x</p>", **{"class": "a;b"}),
             "slides[0].class: must be class names"),
            ("unclosed tag", set_slide("<div>", "<p>x</p>"),
             "slides[0].html: <div> opened on line 1 is never closed"),
            ("crossed tags", set_slide("<div><p>x</div></p>"),
             "slides[0].html: line 1: </div> closes nothing: <p> opened on line 1 is still open"),
            ("script", set_slide("<script>alert(1)</script>"),
             "slides[0].html: line 1: <script> isn't allowed"),
            ("style element", set_slide("<style>p{}</style>"),
             "<style> isn't allowed"),
            ("mermaid diagram", set_slide("<pre class='mermaid'>graph LR; A-->B</pre>"),
             "<pre class='mermaid'>: draw a diagram as inline SVG"),
            ("remote image", set_slide("<img src='https://example.com/a.png'>"),
             "<img src> loads a remote file"),
            ("protocol-relative image", set_slide("<img src='//example.com/a.png'>"),
             "<img src> loads a remote file"),
            ("remote background", set_slide("<div style='background: url(http://x/y.png)'></div>"),
             "<div style> loads a file"),
            # A downloaded image used by its path, as a CSS background, would
            # show with no credit and pass the check, which reads only links.
            ("image by its path as a background",
             set_slide(
                 "<div style=\"background: url('../_assets/earth/image.jpg')\"></div>"),
             "<div style> loads a file: an image goes in <img src='{{asset:<name>}}'>"),
            ("image by its path in the style",
             lambda d: d.update(
                 style=[".hero { background: url(../_assets/earth/image.jpg); }"]),
             "style: must not load files"),
            ("unknown token", set_slide("{{chart:sales}}"),
             "slides[0].html: {{chart:sales}} names no chart in `charts`"),
            ("stray braces", set_slide("<p>{{revenue}}</p>"),
             "slides[0].html: `{{` starts no token: write {{chart:<id>}}, {{ring:<id>}}, {{asset:<name>}} or {{page}}"),
            ("image not in _assets", set_slide("<img src='{{asset:logo.svg}}'>"),
             "slides[0].html: {{asset:logo.svg}} names no image in _assets"),
            # An image placed where the page links nothing, as a CSS
            # background or as text, is refused here, not by the check.
            ("image as a background", set_slide("<div style=\"background: url('{{asset:logo.svg}}')\"></div>"),
             "{{asset:logo.svg}} goes only in an image's link"),
            ("image as text", set_slide(
                "<p>{{asset:logo.svg}}</p>"), "{{asset:logo.svg}} goes only in an image's link"),
            ("token in the style", lambda d: d.update(style=["a { background: url({{asset:logo.svg}}) }"]),
             "style: holds a {{...}} token"),
            ("blurred box-shadow", lambda d: d.update(style=[".a {", "  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);", "}"]),
             "style: line 2: `box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1)` draws a blurred shadow"),
            ("a blurred shadow after a solid one", lambda d: d.update(style=[".a { box-shadow: 4px 4px 0 #000, inset 0 0 6px red; }"]),
             "style: line 1: `box-shadow: 4px 4px 0 #000, inset 0 0 6px red` draws a blurred shadow"),
            ("text-shadow", lambda d: d.update(style=["h1 { text-shadow: 1px 1px 2px #000; }"]),
             "style: line 1: `text-shadow: 1px 1px 2px #000` draws a blurred shadow"),
            ("filter drop-shadow", lambda d: d.update(style=["img { filter: grayscale(1) drop-shadow(0 4px 6px rgb(0 0 0 / 20%)); }"]),
             "style: line 1: `filter: grayscale(1) drop-shadow(0 4px 6px rgb(0 0 0 / 20%))` draws a blurred shadow"),
            ("shadow from a custom property", lambda d: d.update(style=[":root { --lift: 0 6px 18px #0002; }", ".a { box-shadow: var(--lift); }"]),
             "style: line 2: `box-shadow: var(--lift)` draws a blurred shadow"),
            ("inline style shadow", set_slide("<div style='box-shadow: 0 0 12px #000'></div>"),
             "slides[0].html: line 1: <div style> `box-shadow: 0 0 12px #000` draws a blurred shadow"),
            ("inline shadow from the deck's custom property",
             lambda d: d.update(style=[":root { --lift: 0 6px 18px #0002; }"],
                                slides=[slide("<p style='text-shadow: var(--lift)'>x</p>")] + d["slides"][1:]),
             "slides[0].html: line 1: <p style> `text-shadow: var(--lift)` draws a blurred shadow"),
            ("body restyled", lambda d: d.update(style=["body { background: #000; }"]),
             "style: line 1: `body` restyles the page around the deck"),
            ("slides-wrapper restyled", lambda d: d.update(style=[".a {}", ".slides-wrapper { gap: 0; }"]),
             "style: line 2: `.slides-wrapper` restyles the page around the deck"),
            ("toolbar button restyled", lambda d: d.update(style=[".toolbar button { color: red; }"]),
             "style: line 1: `.toolbar button` restyles the page around the deck"),
            ("toolbar in a selector list, in a media rule",
             lambda d: d.update(
                 style=["@media print {", "  .a, .toolbar { display: none; }", "}"]),
             "style: line 2: `.a, .toolbar` restyles the page around the deck"),
            ("image by its path", set_slide("<img src='/Users/me/logo.png'>"),
             "<img src> loads '/Users/me/logo.png': add the image with add_asset.py"),
            ("image by a relative path", set_slide("<img src='../_assets/logo.png'>"),
             "<img src> loads '../_assets/logo.png'"),
            ("chart placed twice", set_slide("{{chart:revenue}}"),
             "charts.revenue: must be placed exactly once, as {{chart:revenue}} in a slide's html, not 2 times"),
            ("chart never placed", lambda d: d["slides"].pop(1),
             "charts.revenue: must be placed exactly once"),
            ("chart id", lambda d: d["charts"].update({"Sales": d["charts"]["revenue"]}),
             "charts.Sales: an id is lowercase words"),
            ("chart type", lambda d: d["charts"]["revenue"].update(
                {"type": "column"}), "charts.revenue.type: must be one of"),
            ("chart datasets", lambda d: d["charts"]["revenue"]["data"].update(
                {"datasets": []}), "charts.revenue.data.datasets: must be a nonempty list"),
            ("chart options", lambda d: d["charts"]["revenue"].update(
                {"options": []}), "charts.revenue.options: must be an object"),
            ("chart field", lambda d: d["charts"]["revenue"].update(
                {"plugins": {}}), "charts.revenue: unknown field(s) plugins"),
            ("format not an object", lambda d: d["charts"]["revenue"].update(
                {"format": "£"}), "charts.revenue.format: must be an object"),
            ("format field", lambda d: d["charts"]["revenue"].update(
                {"format": {"currency": "GBP"}}), "charts.revenue.format: unknown field(s) currency"),
            ("format prefix", lambda d: d["charts"]["revenue"].update(
                {"format": {"prefix": 3}}), "charts.revenue.format.prefix: must be text on one line"),
            ("format decimals", lambda d: d["charts"]["revenue"].update(
                {"format": {"decimals": 1.5}}), "charts.revenue.format.decimals: must be a whole number"),
            ("ring size", ring(size=0), "rings.phases.size: must be a number above 0"),
            ("ring outer", ring(outer=121), "rings.phases.outer: must be a radius"),
            ("ring inner", ring(inner=88), "rings.phases.inner: must be a radius"),
            ("ring gap", ring(gap=-1), "rings.phases.gap: must be degrees"),
            ("ring start", ring(start="top"),
             "rings.phases.start: must be degrees"),
            ("one segment", ring(segments=[{"color": "red"}]),
             "rings.phases.segments: must list at least 2"),
            ("segment colour", ring(segments=[{"color": "red'"}, {"color": "blue"}]),
             "rings.phases.segments[0].color: must be a CSS colour"),
            ("segment value", ring(segments=[{"color": "red", "value": 0}, {"color": "blue"}]),
             "rings.phases.segments[0].value: must be a number above 0"),
            ("gap swallows a segment", ring(gap=91, segments=[{"color": "red"}] * 4),
             "rings.phases.gap: 91° leaves nothing of the narrowest segment, 90° wide"),
        ]
        for name, change, expected in cases:
            with self.subTest(name):
                data = content()
                change(data)
                errors = make_deck.problems(data)[0]
                self.assertTrue(any(expected in error for error in errors),
                                f"{expected!r} not in {errors}")

    def test_accepted_slides(self):
        # Each case: the slides replacing the fixture's first and third.
        # Void elements, self-closed SVG and entities need no closing tag, a
        # link to a page is fine (only loading a remote file isn't), and an
        # image in _assets can be placed on several slides.
        cases = [
            ("html", slide("<p>a<br>b</p><img src='data:image/png;base64,AA'>",
                           "<svg viewBox='0 0 10 10'><path d='M0,0 L10,10' /><circle cx='5' cy='5' r='2'></circle></svg>",
                           "<a href='https://example.com'>Q&amp;A</a>"),
             slide("<p>Thanks</p>")),
            ("an image twice", slide("<img src='{{asset:acme-logo}}'>"),
             slide("<p>Thanks</p>", "<img src='{{asset:acme-logo}}'>")),
        ]
        for name, first, third in cases:
            with self.subTest(name):
                data = content()
                data["slides"][0], data["slides"][2] = first, third
                self.assertEqual(make_deck.problems(
                    data, frozenset({"acme-logo"}))[0], [])

    def test_accepted_style(self):
        # Each case: the deck's style and the first slide's html. A shadow
        # with no blur prints as it shows, and a selector merely like the
        # page's own restyles none of it.
        cases = [
            ("shadow with no blur", [
             ".a { box-shadow: 4px 4px 0 #1e3a8a, inset 0 0 0 1px #ddd; }"], "<p>x</p>"),
            ("text-shadow with no blur",
             ["h1 { text-shadow: 2px 2px #000; }"], "<p>x</p>"),
            ("no shadow", [
             ".a { box-shadow: none; filter: blur(2px) drop-shadow(3px 3px 0 red); }"], "<p>x</p>"),
            ("custom property with no blur", [":root { --offset: 6px 6px 0 #0f172a; }", ".a { box-shadow: var(--offset); }"],
             "<p>x</p>"),
            ("inline shadow with no blur", [],
             "<div style='box-shadow: 3px 3px 0 0 #000'></div>"),
            ("shadow in a comment", [
             "/* box-shadow: 0 2px 8px #000; */", "body-text { color: red; }"], "<p>x</p>"),
            ("selectors like the page's", [".toolbar-row, .body, #body, .slides-wrapper-x, .slide .toolbox { color: red; }"],
             "<p>x</p>"),
        ]
        for name, style, html in cases:
            with self.subTest(name):
                data = content()
                data["style"], data["slides"][0] = style, slide(html)
                self.assertEqual(make_deck.problems(data)[0], [])


class RingTest(unittest.TestCase):
    def test_segments_share_the_circle_by_value(self):
        # Values 1, 2 and 1 with 4° gaps starting at 12 o'clock: 90°, 180°
        # and 90° wide, each 2° in from its share's edges.
        ring = {"size": 200, "outer": 100, "inner": 50, "gap": 4,
                "segments": [{"color": "red"}, {"color": "blue", "value": 2}, {"color": "green"}]}
        svg = make_deck.ring_svg("phases", ring)
        self.assertTrue(svg.startswith(
            '<svg class="ring" id="ring-phases" viewBox="0 0 200 200" width="200" height="200">'))
        paths = re.findall(r'<path d="([^"]+)" fill="(\w+)"/>', svg)
        self.assertEqual([fill for _, fill in paths], ["red", "blue", "green"])
        self.assertEqual([d for d, _ in paths],
                         [common.arc_segment(100, 100, 100, 50, 2, 88),
                          common.arc_segment(100, 100, 100, 50, 92, 268),
                          common.arc_segment(100, 100, 100, 50, 272, 358)])


class BuildTest(unittest.TestCase):
    def build(self, data):
        errors, texts = make_deck.problems(data)
        self.assertEqual(errors, [])
        return make_deck.build(data, texts, {})

    def test_page(self):
        # The page wraps each slide in its frame with its own classes, puts
        # the deck's CSS after the fixed rules, places charts and rings, and
        # loads Chart.js only when a slide holds a chart.
        page = self.build(content())
        self.assertIn("<title>Acme Q3 Review</title>", page)
        self.assertLess(page.index("@media print"),
                        page.index(".title { font-size: 40px; }"))
        self.assertEqual(re.findall(r'<div class="(slide(?: [^"]*)?)">', page),
                         ["slide dark", "slide", "slide"])
        self.assertIn(
            '<div class="chart"><canvas id="chart-revenue"></canvas></div>', page)
        self.assertIn('<svg class="ring" id="ring-phases"', page)
        self.assertNotIn("{{", page)
        self.assertIn(f'<script src="{common.CHART_JS}"></script>', page)
        data = content()
        data["slides"] = [slide("<p>Only text</p>")]
        data["charts"], data["rings"] = {}, {}
        plain = self.build(data)
        self.assertNotIn("<script src", plain)
        self.assertIn("function zoom(", plain)

    def test_page_numbers_count_the_slides(self):
        data = content()
        for s in data["slides"]:
            s["html"].append("<span class='n'>{{page}}</span>")
        self.assertEqual(re.findall(r"<span class='n'>(.*?)</span>", self.build(data)),
                         ["1", "2", "3"])

    def test_a_charts_format_reaches_the_page_as_data(self):
        # The format stays data in the page; the page's own script turns it
        # into Chart.js's label functions.
        data = content()
        data["charts"]["revenue"]["format"] = {
            "prefix": "£", "suffix": "m", "decimals": 1}
        page = self.build(data)
        self.assertEqual(json.loads(chart_data(page))["revenue"]["format"],
                         {"prefix": "£", "suffix": "m", "decimals": 1})
        self.assertIn("const formatted = (format, value)", page)

    def test_chart_data_cant_end_the_script(self):
        # Text in a chart's data is escaped, so "</script>" in a label can't
        # close the script that holds it.
        data = content()
        data["charts"]["revenue"]["data"]["labels"] = ["</script><b>"]
        line = chart_data(self.build(data))
        self.assertNotIn("<", line)
        self.assertEqual(json.loads(
            line)["revenue"]["data"]["labels"], ["</script><b>"])


if __name__ == "__main__":
    unittest.main()
