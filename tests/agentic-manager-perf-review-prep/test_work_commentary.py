"""Unit tests for skills/agentic-manager-perf-review-prep/scripts/work_commentary.py.
Run as a script, it has end-to-end tests in test_e2e_init.py.
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
import work_commentary  # noqa: E402
sys.path.insert(0, TEST_DIR)
from prep_fixture import COMMENTARY, PREP, WORK_FACTS, WORK_ITEMS, temp_output, write_prep  # noqa: E402


class WorkCommentaryTest(unittest.TestCase):
    def setUp(self):
        self.folder = temp_output(self)
        write_prep(self.folder, work=WORK_ITEMS)

    def read_work(self):
        with open(os.path.join(self.folder, PREP, "work.json"), encoding="utf-8") as f:
            return json.load(f)

    def test_starts_then_takes_the_commentary(self):
        # start stores the facts and writes the task, with the facts and the
        # titles by area; submit stores the commentary next to them.
        started = work_commentary.start(PREP)
        self.assertEqual(self.read_work(), {**WORK_ITEMS, "facts": WORK_FACTS})
        path = started["task"].split(": ", 1)[1]
        self.assertTrue(path.endswith(
            os.path.join(PREP, "_raw", "work", "task.md")))
        with open(path, encoding="utf-8") as f:
            task = f.read()
        for expected in ("# Comment on a person's work", "## The person\n\nJane Doe", '"title": "Billing"',
                         "- Jira resolved, Billing: Migrate billing", "- Jira open, no parent: Retire old billing",
                         "- Notion created, Engineering / Billing: Billing plan", "about 80 words", "every step change", '"main_areas": [',
                         'never "he" or "she"', "work_commentary.py submit --prep Jane-Doe_26-11-10"):
            self.assertIn(expected, task)
        work_commentary.submit(PREP, COMMENTARY)
        self.assertEqual(self.read_work(), {
                         **WORK_ITEMS, "facts": WORK_FACTS, "commentary": COMMENTARY})

    def test_refuses_what_it_cant_take(self):
        # name: (what to do, expected in why it stops).
        cases = [("a commentary before start", lambda: work_commentary.submit(PREP, COMMENTARY),
                  "facts aren't worked out: run .* start"),
                 ("a source not gathered", lambda: (write_prep(self.folder, work={
                     k: v for k, v in WORK_ITEMS.items() if k != "notion"}), work_commentary.start(PREP)),
                  "notion not gathered yet: run set_notion.py first"),
                 ("text for a source the person isn't in",
                  lambda: (work_commentary.start(PREP),
                           work_commentary.submit(PREP, {**COMMENTARY, "github": "Opened many PRs."})),
                  "github must be null(.|\n)*The answer's shape"),
                 ("a paragraph too long",
                  lambda: (work_commentary.start(PREP),
                           work_commentary.submit(PREP, {**COMMENTARY, "jira": "word " * 121})),
                  "at most 120")]
        for name, do, expected in cases:
            with self.subTest(name):
                write_prep(self.folder, work=WORK_ITEMS)
                with self.assertRaisesRegex(SystemExit, expected):
                    do()


if __name__ == "__main__":
    unittest.main()
