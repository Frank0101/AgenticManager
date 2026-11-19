"""Unit tests for skills/agentic-manager-utils-lib/agentic_manager/code_map.py.
Run with: python3 tests/run.py agentic-manager-utils-lib
"""

import ast
import os
import sys
import tempfile
import unittest

# tests/<skill>/ mirrors skills/<skill>/.
TEST_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(TEST_DIR))
sys.path.insert(0, os.path.join(
    REPO_ROOT, "skills", os.path.basename(TEST_DIR)))
from agentic_manager import code_map  # noqa: E402


def write_fixture(root, files):
    """Writes `files`, {relative path: text}, under `root`."""
    for relative, text in files.items():
        path = os.path.join(root, *relative.split("/"))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)


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

    def test_protocol_parts(self):
        # Where each shared part lands, from a fixture skill of invented names:
        # a part used by a protocol, by another part, through a chain, by a
        # script alone and by nothing; a {{value}} no part fills isn't a part's
        # user, and a plain word in a script counts only as a protocol call's
        # argument.
        with tempfile.TemporaryDirectory() as skill:
            write_fixture(skill, {
                "protocol/plan.md": "Do it. {{sketch}} Then {{count}} times.\n",
                "protocol/check-list.md": "{{trim}}\n",
                "protocol/_sketch.md": "A sketch, with {{trim}}.\n",
                "protocol/_trim.md": "Trim it, as {{base}} says.\n",
                "protocol/_base.md": "The base.\n",
                "protocol/_spare.md": "Nothing names it.\n",
                "protocol/_loose.md": "Only a script fills it.\n",
                "scripts/make.py": 'import protocol\nprotocol.text("plan")\n'
                                   'tasks = {"check-list": 1, "spare": 2}\nfill_protocol(F, "_loose")\n',
                "scripts/other.py": 'kinds = {"plan": 1}\nphase = "plan"\n'})
            found = {part["part"]: part for part in code_map.parts_of(skill)}
            cases = [("a part used by a protocol and by another part", "_trim",
                      [("_sketch", ["plan"]), ("check-list", [])], ["make"]),
                     ("a part reached through a chain", "_base",
                      [("_trim", ["check-list", "plan"])], ["make"]),
                     ("a part only a protocol names",
                      "_sketch", [("plan", [])], ["make"]),
                     ("a part nothing names", "_spare", [], []),
                     ("a part only a script fills by name", "_loose", [], ["make"])]
            self.assertEqual(
                sorted(found), ["_base", "_loose", "_sketch", "_spare", "_trim"])
            for name, part, users, scripts in cases:
                with self.subTest(name):
                    self.assertEqual(
                        (found[part]["users"], found[part]["scripts"]), (users, scripts))

    def test_scripts_that_fill_by_name(self):
        # A name counts as a call's argument when the call mentions protocol,
        # and as a string anywhere for a part or a hyphenated name; a plain
        # word elsewhere, such as a dict key, doesn't.
        with tempfile.TemporaryDirectory() as folder:
            for name, text in {"a.py": 'protocol.text("plan")\n', "b.py": 'x = {"plan": 1}\n',
                               "c.py": 'y = "_part"\nz = "check-list.md"\n',
                               "d.py": 'render("plan")\nfill_protocol(F, "plan")\n'}.items():
                with open(os.path.join(folder, name), "w", encoding="utf-8") as f:
                    f.write(text)
            self.assertEqual(code_map.filled_by(folder, {"plan", "_part", "check-list"}),
                             {"plan": ["a", "d"], "_part": ["c"], "check-list": ["c"]})

    def test_the_map_lists_the_parts_of_a_skill_with_protocols(self):
        with tempfile.TemporaryDirectory() as skill:
            write_fixture(skill, {"protocol/plan.md": "{{sketch}}\n", "protocol/_sketch.md": "A sketch.\n",
                                  "scripts/make.py": 'protocol.text("plan")\n'})
            lines = code_map.parts_section(skill)
            self.assertEqual(lines[1], "## Protocol parts")
            self.assertEqual(
                lines[-1], "- `_sketch.md`: used in `plan.md`; filled by `make.py`")
            self.assertTrue(lines[3].startswith("*A part is a `_name.md`"))
        with tempfile.TemporaryDirectory() as skill:
            write_fixture(skill, {"protocol/plan.md": "No parts.\n"})
            self.assertEqual(code_map.parts_section(skill), [])
            self.assertEqual(code_map.parts_section(
                os.path.join(skill, "nowhere")), [])

    def test_the_real_skills_parts_are_listed(self):
        # The map of a skill with protocols ends with its parts, and the
        # library, which has none, with its modules.
        full = code_map.code_map()
        self.assertIn("## Protocol parts", full)
        self.assertNotIn("## Protocol parts", code_map.code_map(
            "agentic-manager-utils-lib"))

    def test_the_map_starts_with_the_library_and_refuses_an_unknown_skill(self):
        self.assertEqual(next(iter(code_map.folders())),
                         "agentic-manager-utils-lib")
        self.assertTrue(code_map.code_map("agentic-manager-utils-lib").startswith(
            "# agentic-manager-utils-lib\n\n## `batch.py`"))
        with self.assertRaisesRegex(SystemExit, "no skill 'nope'"):
            code_map.code_map("nope")


if __name__ == "__main__":
    unittest.main()
