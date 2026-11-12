"""Unit tests for skills/agentic-manager-tech-investigation/scripts/protocol.py.
Run with: python3 tests/run.py agentic-manager-tech-investigation
"""

import json
import os
import sys
import unittest

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(TEST_DIR))
sys.path.insert(0, os.path.join(REPO_ROOT, "skills",
                os.path.basename(TEST_DIR), "scripts"))
import protocol  # noqa: E402

# What investigate.py fills for every task.
FILLS = {"topic": "Acme Search", "documentation": "the notion-mcp source", "code": "the gitlab-cli source", "scripts": "/s", "lib": "/l",
         "investigation": "Acme_26-10-05", "ledger": "/x/ledger.md", "task_work": "/w", "repos": "/r"}


class ProtocolTest(unittest.TestCase):
    def test_every_file_is_filled(self):
        # A placeholder nothing fills would reach the agent as {{name}}.
        for name in sorted(os.listdir(protocol.FOLDER)):
            # _work is a task's text too: render adds it to every task.
            if name.endswith(".md") and (not name.startswith("_") or name == "_work.md"):
                with self.subTest(name):
                    text = protocol.text(name[:-3], **FILLS)
                    self.assertNotIn("{{", text)
                    self.assertTrue(text)
        self.assertIn("coverage is an object whose read is one of: full, partial, listing",
                      protocol.text("research", **FILLS))
        self.assertIn("`python3 /s/tickets.py`",
                      protocol.text("research", **FILLS))
        # Every task reads a repository from the run's one clone of it.
        self.assertIn("use the run's shared clone of it, /r/<owner>-<repo>",
                      protocol.text("research", **FILLS))

    def test_examples_print_one_record_per_line(self):
        for name in sorted(os.listdir(os.path.join(protocol.FOLDER, "examples"))):
            data = protocol.example(name[:-5])
            with self.subTest(name):
                printed = protocol.compact(data)
                self.assertEqual(json.loads(printed), data)
                self.assertLess(len(printed), len(
                    json.dumps(data, ensure_ascii=False, indent=2)))
        printed = protocol.compact({"sources": [{"key": "s1"}, {"key": "s2"}], "outcome": {"answered": "f1"},
                                    "new_questions": []})
        self.assertEqual(printed, '{\n  "sources": [\n    {"key": "s1"},\n    {"key": "s2"}\n  ],\n'
                                  '  "outcome": {"answered": "f1"},\n  "new_questions": []\n}')


if __name__ == "__main__":
    unittest.main()
