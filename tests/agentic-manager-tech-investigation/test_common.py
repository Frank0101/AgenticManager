# Unit tests for skills/agentic-manager-tech-investigation/scripts/common.py.
# Run with: python3 tests/run.py agentic-manager-tech-investigation
#
# The config's path is patched to the test's own config, in a temporary folder.
import os
import sys
import tempfile
import unittest

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(TEST_DIR))
sys.path.insert(0, os.path.join(REPO_ROOT, "skills",
                os.path.basename(TEST_DIR), "scripts"))
import common  # noqa: E402
sys.path.insert(0, TEST_DIR)
from investigation_fixture import INVESTIGATION, temp_output  # noqa: E402


class StructureTest(unittest.TestCase):
    def test_report_headings_and_stages(self):
        # skip: (headings left out, stages shown)
        cases = [
            ((), [], ["current", "next", "target"]),
            (("evolution",), ["Roadmap", "Next evolution",
             "Target architecture"], ["current"]),
            (("architecture",), ["Architect summary", "Current architecture", "Next evolution",
                                 "Target architecture", "Technical decisions and gaps", "References"], []),
        ]
        for skip, removed, stages in cases:
            with self.subTest(skip=skip):
                titles = [title for _, title in common.report_headings(skip)]
                self.assertEqual(
                    titles, [title for _, title in common.HEADINGS if title not in removed])
                self.assertEqual(
                    [key for key, _, _ in common.report_stages(skip)], stages)

    def test_read_skip(self):
        # Only content.json's known dimensions, in their own order; nothing
        # without a readable content.json.
        cases = [(None, ()), ("not JSON", ()), ("[]", ()), ('{"skip": "evolution"}', ()),
                 ('{"skip": ["evolution", "design", "architecture"]}', ("architecture", "evolution"))]
        for text, expected in cases:
            with self.subTest(text=text), tempfile.TemporaryDirectory() as folder:
                if text is not None:
                    with open(os.path.join(folder, common.CONTENT), "w", encoding="utf-8") as f:
                        f.write(text)
                self.assertEqual(common.read_skip(folder), expected)

    def test_check_format(self):
        for label, ok in (("exec-summary", True), ("long-analysis", True), ("slack-update2", True),
                          ("Exec Summary", False), ("exec_summary", False), ("-exec", False), ("", False)):
            with self.subTest(label=label):
                if ok:
                    self.assertEqual(common.check_format(label), label)
                else:
                    with self.assertRaisesRegex(SystemExit, "short lower-case label"):
                        common.check_format(label)


class FoldersTest(unittest.TestCase):
    def test_investigation_dir(self):
        folder = temp_output(self)
        self.assertEqual(common.investigation_dir(INVESTIGATION),
                         (os.path.join(folder, INVESTIGATION), folder, False))
        with self.assertRaisesRegex(SystemExit, "without .."):
            common.investigation_dir("../elsewhere")

    def test_topic_of(self):
        cases = [("/out/Acme-Search_26-10-05", "Acme-Search"), ("/out/Acme-Search_26-10-05/", "Acme-Search"),
                 ("QA-Tools_26-01-31", "QA-Tools")]
        for folder, topic in cases:
            with self.subTest(folder=folder):
                self.assertEqual(common.topic_of(folder), topic)
        for folder in ("/out/Acme-Search", "/out/2026-10-05--acme-search"):
            with self.subTest(folder=folder), self.assertRaisesRegex(SystemExit, "not an investigation folder"):
                common.topic_of(folder)

    def test_load_json(self):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "maps.json")
            with self.assertRaisesRegex(SystemExit, "maps.json is missing"):
                common.load_json(path)
            for text, expected in (('{"a": 1}', {"a": 1}), ("{", None)):
                with self.subTest(text=text):
                    with open(path, "w", encoding="utf-8") as f:
                        f.write(text)
                    if expected is None:
                        with self.assertRaisesRegex(SystemExit, "maps.json is not readable JSON"):
                            common.load_json(path)
                    else:
                        self.assertEqual(common.load_json(path), expected)


class MarkdownTest(unittest.TestCase):
    def test_table(self):
        # Cells stay on one line, and a pipe in one is escaped once.
        self.assertEqual(common.table(["A", "B"], [["x | y", "a\nb"], ["already \\| escaped", 3]]),
                         "| A | B |\n| --- | --- |\n| x \\| y | a b |\n| already \\| escaped | 3 |")

    def test_markdown_links_exclude_fences(self):
        for fence in ("```", "~~~~"):
            for form in ("[Asset](asset.svg)", "[Asset][proof]", "[proof][]", "[proof]"):
                with self.subTest(fence=fence, form=form):
                    text = form + \
                        f"\n[proof]: asset.svg\n{fence}text\n[Ignored](gone.md)\n{fence}\n"
                    prose, blocks, unclosed = common.markdown(text)
                    definitions = {m[1].casefold(): m[2]
                                   for m in common.DEFINITION.finditer(prose)}
                    self.assertEqual([target for _, _, _, target in common.links(prose, definitions)],
                                     ["asset.svg"])
                    self.assertEqual(len(prose), len(text))
                    self.assertEqual(len(blocks), 1)
                    self.assertFalse(unclosed)
        prose, blocks, unclosed = common.markdown(
            "```text\n[Ignored](gone.md)")
        self.assertTrue(unclosed)
        self.assertEqual(list(common.links(prose, {})), [])
        self.assertEqual(blocks[0][3], "[Ignored](gone.md)")

    def test_slug(self):
        cases = [("F03 — Delivery is exploration", "f03--delivery-is-exploration"),
                 ("Boundary, method and access", "boundary-method-and-access"),
                 ("  Ready / in progress ", "ready--in-progress")]
        for heading, anchor in cases:
            with self.subTest(heading=heading):
                self.assertEqual(common.slug(heading), anchor)

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
        for name, text, expected in cases:
            with self.subTest(name):
                self.assertEqual(common.headings(text), expected)

    def test_connection_key(self):
        # A connection is known by its id, else by its ends.
        self.assertEqual(common.connection_key(
            {"id": "c1", "from": "a", "to": "b"}), "c1")
        self.assertEqual(common.connection_key(
            {"from": "a", "to": "b"}), "a->b")


if __name__ == "__main__":
    unittest.main()
