"""Unit tests for skills/agentic-manager-utils-lib/agentic_manager/svg.py.
Run with: python3 tests/run.py agentic-manager-utils-lib
"""

import os
import re
import sys
import unittest

# tests/<skill>/ mirrors skills/<skill>/.
TEST_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(TEST_DIR))
sys.path.insert(0, os.path.join(
    REPO_ROOT, "skills", os.path.basename(TEST_DIR)))
from agentic_manager import svg  # noqa: E402


class SvgTest(unittest.TestCase):
    def test_helpers(self):
        cases = [("esc", svg.esc('<a "b">'), "&lt;a &quot;b&quot;&gt;"),
                 ("nice_step", [svg.nice_step(span) for span in (
                     5, 12, 30, 300, 20000)], [1, 2, 5, 50, 3000]),
                 ("text escaped", svg.text(1, 2, "a<b", anchor="end"),
                  '<text x="1.0" y="2.0" font-size="12" fill="#1a1a1a" text-anchor="end">a&lt;b</text>')]
        for name, got, expected in cases:
            with self.subTest(name):
                self.assertEqual(got, expected)

    def test_text_width(self):
        # Wide letters measure wider than narrow ones, and bold wider still:
        # label columns and fit-inside-a-bar decisions rely on it.
        self.assertGreater(svg.text_width("WWW", 12),
                           svg.text_width("iii", 12))
        self.assertAlmostEqual(svg.text_width("Done", 12, bold=True),
                               svg.text_width("Done", 12) * 1.08)

    def test_svg(self):
        # A document of the given size on the shared surface, its body inside.
        document = svg.svg(100, 50, ["<line/>"])
        self.assertTrue(document.startswith(
            '<svg xmlns="http://www.w3.org/2000/svg" width="100" height="50"'))
        self.assertIn(f'fill="{svg.SURFACE}"/>\n<line/>\n</svg>', document)

    def test_legend(self):
        # A box per entry without a line, else a line of its width and dash
        # pattern, solid without one; a row wraps before the right edge, and
        # the bottom sits below the last row.
        entries = [("Done", "#111111", None), ("Ideal", "#222222", (1.8, "7 5")),
                   ("Actual", "#333333", (2.4, None))]
        elements, bottom = svg.legend(entries, 10, 400, 50)
        self.assertEqual(
            elements[0], '<rect x="10.0" y="50.0" width="10" height="10" fill="#111111"/>')
        self.assertIn('stroke="#222222" stroke-width="1.8" stroke-linecap="round" stroke-dasharray="7 5"/>',
                      elements[2])
        self.assertTrue(elements[4].endswith(
            'stroke="#333333" stroke-width="2.4" stroke-linecap="round"/>'))
        self.assertEqual([svg.esc(label) in "".join(elements)
                         for label, *_ in entries], [True] * 3)
        self.assertEqual(bottom, 68)
        wrapped, wrapped_bottom = svg.legend(entries, 10, 120, 50)
        rows = sorted({float(y) for y in re.findall(
            r'<text x="[\d.]+" y="([\d.]+)"', "".join(wrapped))})
        self.assertEqual((len(rows), wrapped_bottom), (3, 68 + 2 * 16))

    def test_arc_segment(self):
        # Known paths: a 57° donut segment, and a 270° pie segment (large-arc flag set).
        cases = [((120, 120, 88, 44, -88.5, -31.5),
                  "M32.03,117.7 A88,88,0,0,1,74.02,44.97 L97.01,82.48 A44,44,0,0,0,76.02,118.85 Z"),
                 ((100, 100, 80, 0, 0, 270),
                  "M100,20 A80,80,0,1,1,20,100 L100,100 A0,0,0,1,0,100,100 Z")]
        for args, expected in cases:
            with self.subTest(args):
                self.assertEqual(svg.arc_segment(*args), expected)


if __name__ == "__main__":
    unittest.main()
