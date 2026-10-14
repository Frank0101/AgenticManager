"""Unit tests for skills/agentic-manager-utils-lib/agentic_manager/json_path.py.
Run with: python3 tests/run.py agentic-manager-utils-lib
"""

import os
import sys
import unittest

# tests/<skill>/ mirrors skills/<skill>/.
TEST_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(TEST_DIR))
sys.path.insert(0, os.path.join(
    REPO_ROOT, "skills", os.path.basename(TEST_DIR)))
from agentic_manager import json_path  # noqa: E402


class JsonPathTest(unittest.TestCase):
    def test_nested(self):
        node = {"status": {"statusCategory": {"key": "done"}}, "parent": None,
                "fixVersions": [{"name": "1.0"}]}
        cases = [(node, ["status", "statusCategory", "key"], None, "done"), (node, ["parent", "key"], "x", "x"),
                 (node, ["missing"], "", ""), (None,
                                               ["parent", "id"], None, None),
                 (node, ["fixVersions", 0, "name"], None, "1.0"), (node, [
                     "fixVersions", "0", "name"], None, "1.0"),
                 (node, ["fixVersions", 1, "name"], "x", "x"), (node, ["status", "statusCategory", "key", "x"], None, None)]
        for node, path, default, expected in cases:
            with self.subTest(path=path):
                self.assertEqual(json_path.nested(
                    node, path, default), expected)


if __name__ == "__main__":
    unittest.main()
