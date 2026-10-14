"""Unit tests for skills/agentic-manager-utils-lib/agentic_manager/extract_saved.py.
Run with: python3 tests/run.py agentic-manager-utils-lib

The saved results are invented, in the shape of a Jira search.
"""

import contextlib
import io
import json
import os
import sys
import tempfile
import unittest

# tests/<skill>/ mirrors skills/<skill>/.
TEST_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(TEST_DIR))
sys.path.insert(0, os.path.join(
    REPO_ROOT, "skills", os.path.basename(TEST_DIR)))
from agentic_manager import extract_saved  # noqa: E402

SAVED = {"issues": {"nodes": [
    {"key": "PROJ-1", "fields": {"summary": "Build the\nAPI", "status": {"name": "Done"},
                                 "fixVersions": [{"name": "1.0"}], "labels": ["a", "b"]}},
    {"key": "PROJ-2", "fields": {"summary": "Scan uploads", "status": None}},
]}, "context": {"sites": [{"id": 1}]}}


class ExtractSavedTest(unittest.TestCase):
    def test_at(self):
        item = SAVED["issues"]["nodes"][0]
        # path: value
        cases = [("key", "PROJ-1"), ("fields.status.name", "Done"), ("fields.fixVersions.0.name", "1.0"),
                 ("fields.fixVersions.5.name", None), ("fields.missing.name", None), ("", item)]
        for path, expected in cases:
            with self.subTest(path):
                self.assertEqual(extract_saved._at(item, path), expected)

    def test_lines(self):
        # (fields, items): lines. The longest list of objects is found when --items is left out.
        cases = [
            ((["key", "fields.status.name", "fields.summary"], None),
             ["2 items at issues.nodes", "PROJ-1 | Done | Build the API", "PROJ-2 |  | Scan uploads"]),
            ((["key", "fields.labels"], "issues.nodes"),
             ["2 items at issues.nodes", 'PROJ-1 | ["a","b"]', "PROJ-2 | "]),
            ((["id"], "context.sites"), ["1 items at context.sites", "1"]),
        ]
        for (fields, items), expected in cases:
            with self.subTest(fields=fields, items=items):
                self.assertEqual(extract_saved._lines(
                    SAVED, fields, items), expected)
        for data, items, message in (({"a": 1}, None, "holds no list of objects"),
                                     (SAVED, "issues", "is not a list")):
            with self.subTest(message), self.assertRaisesRegex(SystemExit, message):
                extract_saved._lines(data, ["key"], items)

    def test_main(self):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "saved.txt")
            with open(path, "w", encoding="utf-8") as f:
                json.dump(SAVED, f)
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                extract_saved.main(
                    ["--path", path, "--fields", "key, fields.status.name"])
            self.assertEqual(
                out.getvalue(), "2 items at issues.nodes\nPROJ-1 | Done\nPROJ-2 | \n")
            with open(path, "w", encoding="utf-8") as f:
                f.write("not json")
            with self.assertRaisesRegex(SystemExit, "is not readable JSON"):
                extract_saved.main(["--path", path, "--fields", "key"])
            with self.assertRaisesRegex(SystemExit, "is missing in"):
                extract_saved.main(
                    ["--path", os.path.join(folder, "none"), "--fields", "key"])


if __name__ == "__main__":
    unittest.main()
