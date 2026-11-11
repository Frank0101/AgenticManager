"""Unit tests for skills/agentic-manager-utils-lib/agentic_manager/protocol.py.
Run with: python3 tests/run.py agentic-manager-utils-lib
"""

import os
import sys
import tempfile
import unittest

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(TEST_DIR))
sys.path.insert(0, os.path.join(REPO_ROOT, "skills",
                "agentic-manager-utils-lib"))
from agentic_manager import protocol  # noqa: E402


class ProtocolTest(unittest.TestCase):
    def test_fill(self):
        # A value given, a shared part, a part's own placeholders, and a value
        # given winning over a part of the same name.
        with tempfile.TemporaryDirectory() as folder:
            for name, text in [("task.md", "# Task\n\nRead {{what}}. {{rule}}\n"),
                               ("_rule.md", "Write about {{who}}.\n"),
                               ("_what.md", "the part, never shown\n"),
                               ("broken.md", "Ask {{nobody}}.")]:
                with open(os.path.join(folder, name), "w", encoding="utf-8") as f:
                    f.write(text)
            self.assertEqual(protocol.fill(folder, "task", {"what": "the notes", "who": "Jane"}),
                             "# Task\n\nRead the notes. Write about Jane.")
            with self.assertRaisesRegex(SystemExit, "protocol/broken.md names {{nobody}}, which nothing fills"):
                protocol.fill(folder, "broken")


if __name__ == "__main__":
    unittest.main()
