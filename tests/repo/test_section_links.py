"""Checks that every link to a section in AGENTS.md and each skill's SKILL.md
reaches a heading, in the same document or another Markdown file, so renaming
a heading can't silently break a link to it. Anchors are the ones a Markdown
viewer gives, GitHub style, and fenced code is neither a heading nor a link
(see agentic_manager/text.py).
Run with: python3 tests/run.py repo
"""

import glob
import os
import sys
import tempfile
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(
    REPO_ROOT, "skills", "agentic-manager-utils-lib"))
from agentic_manager.text import headings, link_definitions, links, local_link, markdown  # noqa: E402


def documents():
    """AGENTS.md and every skill's SKILL.md."""
    return [os.path.join(REPO_ROOT, "AGENTS.md")] + sorted(
        glob.glob(os.path.join(REPO_ROOT, "skills", "*", "SKILL.md")))


def anchors(path):
    """The anchors of the headings in the Markdown file at `path`."""
    with open(path, encoding="utf-8") as f:
        return {anchor for _, _, anchor in headings(f.read())}


def broken_links(path):
    """The section links of the Markdown file at `path` that reach no heading."""
    with open(path, encoding="utf-8") as f:
        prose = markdown(f.read())[0]
    broken = []
    for _, _, _, target in links(prose, link_definitions(prose)):
        local = local_link(path, target) if target else None
        if local is None or not local[1] or local[0].suffix != ".md":
            continue
        linked, anchor = local
        if not linked.is_file() or anchor not in anchors(linked):
            broken.append(target)
    return broken


class SectionLinksTest(unittest.TestCase):
    def test_every_section_link_reaches_a_heading(self):
        for path in documents():
            where = os.path.relpath(path, REPO_ROOT)
            with self.subTest(where):
                self.assertEqual(broken_links(path), [],
                                 f"{where}: fix the link or the heading it names")

    def test_broken_links_are_found(self):
        # (other.md's text, the document's text, the broken links)
        other = "# Other\n\n## Config sources\n"
        cases = [
            ("a link to a heading",
             "# Doc\n\n## 1. Define\n\nSee [it](#1-define).\n", []),
            ("a renamed heading",
             "# Doc\n\n## 1. Scope\n\nSee [it](#1-define).\n", ["#1-define"]),
            ("a heading only in fenced code",
             "# Doc\n\n```markdown\n## Define\n```\n\nSee [it](#define).\n", ["#define"]),
            ("a link only in fenced code",
             "# Doc\n\n```text\n[it](#gone)\n```\n", []),
            ("a repeated heading",
             "# Doc\n\n## A\n\n## A\n\nSee [it](#a-1).\n", []),
            ("another file's heading",
             "# Doc\n\nSee [it](other.md#config-sources).\n", []),
            ("another file's missing heading",
             "# Doc\n\nSee [it](other.md#gone).\n", ["other.md#gone"]),
            ("a missing file",
             "# Doc\n\nSee [it](missing.md#a).\n", ["missing.md#a"]),
            ("a reference definition",
             "# Doc\n\nSee [it][r].\n\n[r]: #gone\n", ["#gone"]),
            ("a web page's anchor",
             "# Doc\n\nSee [it](https://acme.test/page#part).\n", []),
        ]
        for name, written, expected in cases:
            with self.subTest(name), tempfile.TemporaryDirectory() as folder:
                with open(os.path.join(folder, "other.md"), "w", encoding="utf-8") as f:
                    f.write(other)
                path = os.path.join(folder, "doc.md")
                with open(path, "w", encoding="utf-8") as f:
                    f.write(written)
                self.assertEqual(broken_links(path), expected)


if __name__ == "__main__":
    unittest.main()
