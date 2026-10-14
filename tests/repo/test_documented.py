"""Checks that the map of the skills' code is complete: every module of the
library and of each skill's scripts folder has a header comment, and every
function or class the map lists has a docstring, since the map takes its
descriptions from them (see agentic_manager/code_map.py).
Run with: python3 tests/run.py repo
"""

import os
import sys
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(
    REPO_ROOT, "skills", "agentic-manager-utils-lib"))
from agentic_manager import code_map  # noqa: E402


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


if __name__ == "__main__":
    unittest.main()
