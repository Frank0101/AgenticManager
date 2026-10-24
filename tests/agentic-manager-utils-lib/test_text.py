"""Unit tests for skills/agentic-manager-utils-lib/agentic_manager/text.py.
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
from agentic_manager import text  # noqa: E402


class TextTest(unittest.TestCase):
    def test_word_count(self):
        # A link counts as its text; only tokens with a letter or a digit count.
        cases = [("JavaScript and per-market", 3),
                 ("[PROJ-1 fix](https://acme.test/browse/PROJ-1) done", 3),
                 ("Cost – high (see [doc][d])", 4),
                 ("don't stop at 3.14 & more", 5),
                 ("![chart](c.svg) shows it", 3),
                 ("a  b\nc\n[d]: https://acme.test/d", 3),
                 ('[a doc](<https://acme.test/a b> "Title") here', 3),
                 ("", 0), ("– & /", 0)]
        for written, expected in cases:
            with self.subTest(written):
                self.assertEqual(text.word_count(written), expected)

    def test_slug(self):
        cases = [("Quarterly Review: Q3 2026", "quarterly-review-q3-2026"),
                 ("  --Team / Roadmap--  ", "team-roadmap"),
                 ("Café_Menu", "caf-menu"),
                 ("already-a-slug", "already-a-slug"),
                 ("– & /", ""), ("", "")]
        for written, expected in cases:
            with self.subTest(written):
                self.assertEqual(text.slug(written), expected)

    def test_free_name(self):
        # The base when free, else the first free number from 2, after the
        # caller's separator.
        cases = [(set(), "-", "intro"),
                 ({"intro"}, "-", "intro-2"),
                 ({"intro", "intro-2", "intro-3"}, "-", "intro-4"),
                 ({"intro", "intro-3"}, "-", "intro-2"),
                 ({"intro"}, "--", "intro--2"),
                 ({"intro", "intro--2"}, "--", "intro--3")]
        for taken, separator, expected in cases:
            with self.subTest(taken=sorted(taken), separator=separator):
                self.assertEqual(text.free_name(
                    "intro", taken.__contains__, separator), expected)

    def test_heading_anchor(self):
        cases = [("F03 — Delivery is exploration", "f03--delivery-is-exploration"),
                 ("Boundary, method and access", "boundary-method-and-access"),
                 ("  Ready / in progress ", "ready--in-progress")]
        for heading, anchor in cases:
            with self.subTest(heading=heading):
                self.assertEqual(text.heading_anchor(heading), anchor)

    def test_headings(self):
        # Headings inside fenced code are not headings, and a fence closes only
        # on a bare fence line ("```python" inside code doesn't close it); a
        # repeated anchor is numbered as viewers number it.
        cases = [
            ("fences and repeats",
             "# Title\n\n## Repeat\n\n```text\n## Not a heading\n```\n\n~~~~\n# Nor this\n~~~~\n\n"
             "### Repeat ###\n\n## Repeat\n",
             [(1, "Title", "title"), (2, "Repeat", "repeat"), (3, "Repeat", "repeat-1"),
              (2, "Repeat", "repeat-2")]),
            ("a fence line with a language inside code",
             "# Title\n\n```text\n```python\n## Still code\n```\n\n## Real\n",
             [(1, "Title", "title"), (2, "Real", "real")]),
        ]
        for name, written, expected in cases:
            with self.subTest(name):
                self.assertEqual(text.headings(written), expected)

    def test_markdown_links_exclude_fences(self):
        for fence in ("```", "~~~~"):
            for form in ("[Asset](asset.svg)", "[Asset][proof]", "[proof][]", "[proof]"):
                with self.subTest(fence=fence, form=form):
                    written = form + \
                        f"\n[proof]: asset.svg\n{fence}text\n[Ignored](gone.md)\n{fence}\n"
                    prose, blocks, unclosed = text.markdown(written)
                    definitions = text.link_definitions(prose)
                    self.assertEqual([target for _, _, _, target in text.links(prose, definitions)],
                                     ["asset.svg"])
                    self.assertEqual(len(prose), len(written))
                    self.assertEqual(len(blocks), 1)
                    self.assertFalse(unclosed)
        prose, blocks, unclosed = text.markdown(
            "```text\n[Ignored](gone.md)")
        self.assertTrue(unclosed)
        self.assertEqual(list(text.links(prose, {})), [])
        self.assertEqual(blocks[0][3], "[Ignored](gone.md)")

    def test_inline_links(self):
        definitions = {"proof": "asset.svg"}
        cases = [("full", "[Asset][proof]", "[Asset](asset.svg)"),
                 ("collapsed", "[Proof][]", "[Proof](asset.svg)"),
                 ("image", "![Asset][proof]", "![Asset](asset.svg)"),
                 ("undefined", "[Asset][gone]", "[Asset][gone]")]
        for name, written, expected in cases:
            with self.subTest(name):
                self.assertEqual(text.inline_links(
                    written, definitions), expected)

    def test_local_link(self):
        # (target, what it resolves to): a path beside the document, the
        # document itself for a bare anchor, and None for a web page.
        cases = [("other.md#Config%20Sources", ("/docs/other.md", "config sources")),
                 ("img/chart.svg", ("/docs/img/chart.svg", "")),
                 ("#2-research", ("/docs/doc.md", "2-research")),
                 ("https://acme.test/page#part", None)]
        for target, expected in cases:
            with self.subTest(target):
                found = text.local_link("/docs/doc.md", target)
                self.assertEqual(found and (str(found[0]), found[1]), expected)


if __name__ == "__main__":
    unittest.main()
