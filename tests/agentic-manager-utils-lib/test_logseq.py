"""Unit tests for skills/agentic-manager-utils-lib/agentic_manager/logseq.py.
Run with: python3 tests/run.py agentic-manager-utils-lib

The graph is a temporary folder each test writes; read_source is patched, so
no config is read.
"""

import os
import sys
import tempfile
import unittest
from unittest import mock

# tests/<skill>/ mirrors skills/<skill>/.
TEST_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(TEST_DIR))
sys.path.insert(0, os.path.join(
    REPO_ROOT, "skills", os.path.basename(TEST_DIR)))
from agentic_manager import logseq  # noqa: E402


class LogseqTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.graph = tmp.name

    def write(self, folder, name, text):
        os.makedirs(os.path.join(self.graph, folder), exist_ok=True)
        with open(os.path.join(self.graph, folder, name), "w", encoding="utf-8") as f:
            f.write(text)

    def test_graph_path(self):
        # The path, ~ expanded, when it holds the graph's notes; else it exits
        # naming the setting, never its value.
        with mock.patch.object(logseq, "read_source", return_value={"path": self.graph}) as read:
            with self.assertRaisesRegex(SystemExit, "`path` setting of sources.local_vault.logseq-fs") as raised:
                logseq.graph_path()
            self.assertNotIn(self.graph, str(raised.exception))
            os.makedirs(os.path.join(self.graph, "journals"))
            self.assertEqual(logseq.graph_path(), self.graph)
        read.assert_called_with("local_vault", "logseq-fs", ("path",))
        home = os.path.dirname(self.graph)
        with mock.patch.dict(os.environ, {"HOME": home}), \
                mock.patch.object(logseq, "read_source", return_value={"path": "~/" + os.path.basename(self.graph)}):
            self.assertEqual(logseq.graph_path(), self.graph)

    def test_notes(self):
        # Journals then pages, each in name order, only Markdown; a page by
        # its title.
        self.write("pages", "Team___Platform.md", "platform")
        self.write("pages", "Jane Doe.md", "about Jane")
        self.write("journals", "2026_07_22.md", "- met [[Jane]]")
        self.write("journals", "notes.txt", "not a note")
        self.assertEqual(list(logseq.notes(self.graph)), [
            ("journals", "2026_07_22", "- met [[Jane]]"),
            ("pages", "Jane Doe", "about Jane"), ("pages", "Team/Platform", "platform")])

    def test_page_title(self):
        for stem, title in [("Jane Doe", "Jane Doe"), ("Team___Platform", "Team/Platform"),
                            ("Q3%3A plan", "Q3: plan")]:
            with self.subTest(stem):
                self.assertEqual(logseq.page_title(stem), title)

    def test_links(self):
        # [[Page]], #[[Page]] and #Page, in order, each time; a # in a word
        # or a URL, or a heading's #, isn't a tag.
        text = ("# Heading\n- 1:1 with [[Jane]] and #[[Jane Doe]] about #Hiring, #okr.\n"
                "- see https://acme.test/page#top and C# code, [[ Jane ]]")
        self.assertEqual(logseq.links(text), [
                         "Jane", "Jane Doe", "Hiring", "okr", "Jane"])

    def test_page_aliases(self):
        # The aliases a page declares in its properties, before its first
        # block, written plain, as links or as tags; an alias:: in a block
        # is that block's property, not the page's.
        for text, expected in [("alias:: JD, [[Jane D]], #Janie\ntags:: person\n- note\n  alias:: JJ",
                                ["JD", "Jane D", "Janie"]),
                               ("title:: Jane Doe\nAlias:: jd\n\n- note",
                                ["jd"]),
                               ("- alias:: JD\n- note", []),
                               ("", [])]:
            with self.subTest(text):
                self.assertEqual(logseq.page_aliases(text), expected)


if __name__ == "__main__":
    unittest.main()
