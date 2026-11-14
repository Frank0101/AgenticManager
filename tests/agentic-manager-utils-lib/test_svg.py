"""Unit tests for skills/agentic-manager-utils-lib/agentic_manager/svg.py.
Run with: python3 tests/run.py agentic-manager-utils-lib
"""

import os
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


if __name__ == "__main__":
    unittest.main()
