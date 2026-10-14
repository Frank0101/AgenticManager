"""Unit tests for skills/agentic-manager-utils-lib/agentic_manager/code_map.py.
Run with: python3 tests/run.py agentic-manager-utils-lib
"""

import ast
import os
import sys
import tempfile
import unittest

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(TEST_DIR))
sys.path.insert(0, os.path.join(
    REPO_ROOT, "skills", "agentic-manager-utils-lib"))
from agentic_manager import code_map  # noqa: E402


class CodeMapTest(unittest.TestCase):
    def test_imported_names(self):
        # A name counts as used however another module reaches it.
        trees = {name: ast.parse(code) for name, code in {
            "a": "X = 1\ndef f(): pass\ndef g(): pass\ndef h(): pass\ndef _p(): pass\ndef main(): pass",
            "b": "from a import f\nimport a\na.g()",
            "c": "import a as x\nx.h"}.items()}
        self.assertEqual(code_map.imported_names(trees)["a"], {"f", "g", "h"})
        self.assertEqual(code_map.public_names(trees["a"]), {"f", "g", "h"})
        self.assertTrue(code_map.is_command(trees["a"]))

    def test_first_sentence(self):
        cases = [("What it does. More detail.", "What it does."),
                 ("A sentence that runs\nover two lines. Then more.",
                  "A sentence that runs over two lines."),
                 ("First paragraph\n\nSecond paragraph.", "First paragraph"),
                 (None, "")]
        for text, expected in cases:
            with self.subTest(text):
                self.assertEqual(code_map.first_sentence(text), expected)

    def test_a_command_lists_only_what_other_modules_use(self):
        # A skill's command lists only the names its folder's other modules
        # use; a module without a main lists every public name.
        with tempfile.TemporaryDirectory() as folder:
            files = {"common.py": '"""Shared."""\ndef shared():\n    """Shared helper."""\n',
                     "make.py": '"""A command."""\nfrom common import shared\n'
                                'def used():\n    """Used elsewhere."""\ndef alone():\n    """Not used."""\n'
                                'def main():\n    pass\n',
                     "other.py": '"""Another command."""\nfrom make import used\ndef main():\n    pass\n'}
            for name, text in files.items():
                with open(os.path.join(folder, name), "w", encoding="utf-8") as f:
                    f.write(text)
            found = {e["module"]: e for e in code_map.modules(folder)}
            self.assertEqual(found["common"]["names"], [
                             ("shared", "Shared helper.")])
            self.assertEqual(found["make"]["names"], [
                             ("used", "Used elsewhere.")])
            self.assertEqual(
                (found["other"]["about"], found["other"]["names"]), ("Another command.", []))

    def test_the_map_starts_with_the_library_and_refuses_an_unknown_skill(self):
        self.assertEqual(next(iter(code_map.folders())),
                         "agentic-manager-utils-lib")
        self.assertTrue(code_map.code_map("agentic-manager-utils-lib").startswith(
            "# agentic-manager-utils-lib\n\n## `check_config.py`"))
        with self.assertRaisesRegex(SystemExit, "no skill 'nope'"):
            code_map.code_map("nope")


if __name__ == "__main__":
    unittest.main()
