"""Unit tests for skills/agentic-manager-perf-review-prep/scripts/set_notion.py.
Run with: python3 tests/run.py agentic-manager-perf-review-prep
"""

import json
import os
import sys
import unittest

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(TEST_DIR))
sys.path.insert(0, os.path.join(REPO_ROOT, "skills",
                os.path.basename(TEST_DIR), "scripts"))
import set_notion  # noqa: E402
sys.path.insert(0, TEST_DIR)
from prep_fixture import NOTION_SEARCHES, PREP, WORK, temp_output, write_prep  # noqa: E402


class SetNotionTest(unittest.TestCase):
    def setUp(self):
        self.folder = temp_output(self)
        write_prep(self.folder, work=WORK)

    def test_writes_the_searches(self):
        # The searches as given into Notion's raw file, then work.json, built
        # from it and Jira's and GitHub's, already in: only the page of its
        # own, dated by its search's range.
        paths = set_notion.set_notion(PREP, {"created": NOTION_SEARCHES})
        with open(paths["raw"], encoding="utf-8") as f:
            self.assertEqual(json.load(f), {"created": NOTION_SEARCHES})
        with open(paths["work"], encoding="utf-8") as f:
            self.assertEqual(json.load(f), WORK)

    def test_refuses_wrong_searches(self):
        # Writing nothing, with the input's shape to follow.
        with self.assertRaisesRegex(SystemExit, "must cover(.|\n)*Input, on stdin"):
            set_notion.set_notion(PREP, {"created": NOTION_SEARCHES[1:]})


if __name__ == "__main__":
    unittest.main()
