"""Unit tests for skills/agentic-manager-utils-lib/agentic_manager/commands.py.
Run with: python3 tests/run.py agentic-manager-utils-lib
"""

import io
import os
import sys
import tempfile
import unittest
from unittest import mock

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(TEST_DIR))
sys.path.insert(0, os.path.join(
    REPO_ROOT, "skills", "agentic-manager-utils-lib"))
from agentic_manager import commands  # noqa: E402


class CommandsTest(unittest.TestCase):
    def test_script_command(self):
        # By the folder the agent ran one of the skill's scripts from, even
        # through a symlink, as the skill pre-approves it; by the skill's own
        # folder otherwise.
        with tempfile.TemporaryDirectory() as folder:
            scripts = os.path.join(
                os.path.realpath(folder), "skill", "scripts")
            os.makedirs(scripts)
            module = os.path.join(scripts, "common.py")
            link = os.path.join(folder, "linked")
            os.symlink(scripts, link)
            # name: (sys.argv[0], the folder expected in the command)
            cases = [("one of the skill's scripts", os.path.join(link, "fetch.py"), link),
                     ("not one of the skill's scripts", os.path.join(folder, "run.py"), scripts)]
            for name, ran, expected in cases:
                with self.subTest(name), mock.patch.object(sys, "argv", [ran]):
                    self.assertEqual(commands.script_command(module, "fetch.py"),
                                     f"python3 {os.path.join(expected, 'fetch.py')}")
                    # The library's module, beside the skill's folder, as the
                    # frontmatter names it.
                    self.assertEqual(commands.library_command(module, "extract_saved.py"),
                                     "python3 " + os.path.join(os.path.dirname(expected), "..",
                                                               "agentic-manager-utils-lib", "agentic_manager",
                                                               "extract_saved.py"))

    def test_stdin_json(self):
        with mock.patch.object(sys, "stdin", io.StringIO('{"a": 1}')):
            self.assertEqual(commands.stdin_json("usage"), {"a": 1})
        with mock.patch.object(sys, "stdin", io.StringIO("not json")), \
                self.assertRaisesRegex(SystemExit, "isn't JSON(.|\n)*usage"):
            commands.stdin_json("usage")


if __name__ == "__main__":
    unittest.main()
