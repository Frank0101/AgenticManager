"""Checks that every skill names a run's folders and document by the library's
names (agentic_manager/output_folder.py), never by literals of its own, so a
run's folder is laid out the same way in every skill (see AGENTS.md, Output
folder, reruns and examples).
Run with: python3 tests/run.py repo
"""

import ast
import os
import re
import sys
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(
    REPO_ROOT, "skills", "agentic-manager-utils-lib"))
from agentic_manager import code_map, output_folder  # noqa: E402

FOLDERS = (output_folder.RAW_DIR, output_folder.CHARTS_DIR)
# A document's name written by hand: a suffix such as "_Report.md".
DOCUMENT_SUFFIX = re.compile(r"_[A-Z]\w*\.(md|html)")


def literal_names(source):
    """[(line, text)]: the string literals of `source` that write a run
    folder's name, or a document's suffix, by hand."""
    return [(node.lineno, node.value) for node in ast.walk(ast.parse(source))
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
            and (node.value in FOLDERS or node.value.startswith(tuple(f"{name}/" for name in FOLDERS))
                 or DOCUMENT_SUFFIX.fullmatch(node.value))]


class RunFolderTest(unittest.TestCase):
    def test_skills_use_the_librarys_names(self):
        for skill, folder in code_map.folders().items():
            if skill == "agentic-manager-utils-lib":
                continue
            for name in sorted(os.listdir(folder)):
                if not name.endswith(".py"):
                    continue
                with self.subTest(f"{skill}/{name}"), open(os.path.join(folder, name), encoding="utf-8") as f:
                    self.assertEqual(literal_names(f.read()), [],
                                     f"{skill}/{name}: use the library's RAW_DIR, CHARTS_DIR and "
                                     "document_name() from agentic_manager/output_folder.py instead")

    def test_literal_names(self):
        # name: (source, whether it writes a name by hand)
        cases = [("a folder", 'RAW = "_raw"', True), ("a path in it", 'p = "_charts/a.svg"', True),
                 ("a suffix", 'S = "_Report.md"',
                  True), ("the library's name", "p = f'{RAW_DIR}/a'", False),
                 ("prose naming it", 'H = "writes _raw and the report"', False)]
        for name, source, expected in cases:
            with self.subTest(name):
                self.assertEqual(bool(literal_names(source)), expected)


if __name__ == "__main__":
    unittest.main()
