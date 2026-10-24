"""Checks that the map of the skills' code is complete: every module of the
library and of each skill's scripts folder has a header comment, and every
function or class the map lists has a docstring, since the map takes its
descriptions from them (see agentic_manager/code_map.py). A header comment is
at most HEADER_LINES lines: a script's usage is in its --help.
Run with: python3 tests/run.py repo
"""

import ast
import os
import sys
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(
    REPO_ROOT, "skills", "agentic-manager-utils-lib"))
from agentic_manager import code_map  # noqa: E402

HEADER_LINES = 10


def header_lines(source):
    """How many lines the module docstring of `source` takes, its quotes
    included, or 0 when it has none."""
    body = ast.parse(source).body
    first = body[0] if body else None
    if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
        return (first.end_lineno or first.lineno) - first.lineno + 1
    return 0


class DocumentedTest(unittest.TestCase):
    def test_every_module_and_listed_name_says_what_it_is_for(self):
        for skill, folder in code_map.folders().items():
            for entry in code_map.modules(folder):
                where = f"{skill}/{entry['module']}.py"
                with self.subTest(where):
                    self.assertTrue(
                        entry["about"], f"{where}: add a header comment")
                    blank = [name for name,
                             about in entry["names"] if not about]
                    self.assertEqual(
                        blank, [], f"{where}: add a docstring to {blank}")

    def test_every_header_comment_is_short(self):
        for skill, folder in code_map.folders().items():
            for name in sorted(os.listdir(folder)):
                if name.endswith(".py"):
                    with self.subTest(f"{skill}/{name}"), open(os.path.join(folder, name), encoding="utf-8") as f:
                        lines = header_lines(f.read())
                        self.assertLessEqual(lines, HEADER_LINES,
                                             f"{skill}/{name}: the header comment is {lines} lines; keep it to "
                                             f"{HEADER_LINES}, with usage in --help and reasons by their code")

    def test_header_lines(self):
        cases = [('"""One line."""\nx = 1\n', 1),
                 ('"""Two\nlines.\n"""\n', 3), ("x = 1\n", 0), ("", 0)]
        for source, expected in cases:
            with self.subTest(source):
                self.assertEqual(header_lines(source), expected)


if __name__ == "__main__":
    unittest.main()
