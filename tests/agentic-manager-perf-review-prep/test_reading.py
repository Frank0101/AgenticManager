"""Unit tests for skills/agentic-manager-perf-review-prep/scripts/reading.py.
Its flow, start to finished, is tested through each source, in
test_read_notes.py and test_read_slack.py.
Run with: python3 tests/run.py agentic-manager-perf-review-prep
"""

import os
import sys
import unittest

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(TEST_DIR))
sys.path.insert(0, os.path.join(REPO_ROOT, "skills",
                os.path.basename(TEST_DIR), "scripts"))
import reading  # noqa: E402
sys.path.insert(0, TEST_DIR)
from prep_fixture import DELAY, PRESENTED  # noqa: E402

MESSAGE = {"date": "2026-08-20", "link": "https://acme.slack.com/archives/C1/p1",
           "synopsis": "In a cross-team channel, posted the billing rollout plan; three people asked follow-ups"}


class ReadingTest(unittest.TestCase):
    def test_items_problems(self):
        # name: (the answer, the days of the task's notes, expected in its
        # problems, or None for none); a page's day is None.
        notes = ["2026-08-20", "2026-08-20"]
        cases = [("valid", {"items": [DELAY, PRESENTED]}, notes, None),
                 ("pages", {"items": [{"note": 1, "synopsis": "Moved team"}]}, [
                  None], None),
                 ("none to read", {"items": []}, [], None),
                 ("not an object", [PRESENTED],
                  notes, 'must be {"items": [...]}'),
                 ("in doubt is the merge's", {
                  "items": [], "in_doubt": []}, notes, 'must be {"items": [...]}'),
                 ("a note left out", {"items": [PRESENTED]}, notes, "1 to 2, must have one synopsis, by its number: "
                  "missing 2"),
                 ("a note twice", {
                  "items": [PRESENTED, DELAY, PRESENTED]}, notes, "must have one synopsis"),
                 ("a note that isn't there", {"items": [PRESENTED, DELAY, {**DELAY, "note": 3}]}, notes,
                  "must have one synopsis"),
                 ("a judgment", {"items": [{**PRESENTED, "part": "going_well"}, DELAY]}, notes,
                  "must have the fields note, synopsis"),
                 ("blank", {"items": [
                  {**PRESENTED, "synopsis": " "}, DELAY]}, notes, "synopsis must be text"),
                 ("too long", {"items": [{**PRESENTED, "synopsis": "word " * 121}, DELAY]}, notes, "at most 120")]
        for name, answer, task_notes, expected in cases:
            with self.subTest(name):
                problems = reading.items_problems(answer, task_notes)
                if expected is None:
                    self.assertEqual(problems, [])
                else:
                    self.assertIn(expected, " ".join(problems))

    def test_linked_items_problems(self):
        # name: (the item, expected in its problems, or None for none): an
        # item not numbered has its own day, of the task's, and its link.
        days = ["2026-08-20"]
        cases = [("valid", MESSAGE, None),
                 ("another day", {**MESSAGE, "date": "2026-09-01"},
                  "must be the day of what it comes from"),
                 ("no link", {**MESSAGE, "link": None},
                  "link, None, must be the address"),
                 ("numbered", {"note": 1, "synopsis": "x"}, "must have the fields date, link, synopsis")]
        for name, item, expected in cases:
            with self.subTest(name):
                problems = reading.items_problems(
                    {"items": [item]}, days=days, linked=True)
                if expected is None:
                    self.assertEqual(problems, [])
                else:
                    self.assertIn(expected, " ".join(problems))

    def test_every_protocol_file_is_filled(self):
        # A placeholder nothing fills would reach a subagent as {{name}}; the
        # shared rules on people reach every task.
        for name in ("notes", "pages", "notes-merge", "slack", "slack-merge"):
            with self.subTest(name):
                text = reading.read_protocol(name)
                self.assertNotIn("{{", text)
                self.assertIn('never "he" or "she"', text)


if __name__ == "__main__":
    unittest.main()
