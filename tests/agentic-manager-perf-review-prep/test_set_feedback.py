"""Unit tests for skills/agentic-manager-perf-review-prep/scripts/set_feedback.py.
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
import common  # noqa: E402
import set_feedback  # noqa: E402
sys.path.insert(0, TEST_DIR)
from prep_fixture import PREP, RATINGS, REVIEW, temp_output, write_prep  # noqa: E402


class SetFeedbackTest(unittest.TestCase):
    def setUp(self):
        self.folder = temp_output(self)
        write_prep(self.folder, feedback=None)
        self.path = os.path.join(self.folder, PREP, "feedback.json")

    def read(self):
        with open(self.path, encoding="utf-8") as f:
            return json.load(f)

    def test_rules(self):
        # The company's ratings as the config lists them, and the days feedback
        # may end on for the prep's period, 10/08/2026 to 10/11/2026.
        self.assertEqual(set_feedback.rules(PREP), {"ratings": RATINGS, "earliest_end": "2024-08-10",
                                                    "latest_end": "2026-11-10", "parts": common.SUMMARY_PARTS})

    def test_writes_them_oldest_first_and_a_correction_replaces_them(self):
        older = {**REVIEW, "start": "2025-07-01",
                 "end": "2025-12-31", "rating": "Below"}
        self.assertEqual(set_feedback.set_feedback(
            PREP, {"reviews": [REVIEW, older]}), self.path)
        self.assertEqual(self.read(), {"reviews": [older, REVIEW]})
        set_feedback.set_feedback(PREP, {"reviews": []})
        self.assertEqual(self.read(), {"reviews": []})

    def test_writes_undated_feedback_last_in_the_order_given(self):
        first = {**REVIEW, "start": None, "end": None, "rating": None,
                 "going_well": ["Mentors new joiners"]}
        second = {**first, "going_well": ["Runs the guild well"]}
        only_end = {**first, "end": "2025-03-31",
                    "going_well": ["Shipped the search revamp"]}
        set_feedback.set_feedback(
            PREP, {"reviews": [first, REVIEW, second, only_end]})
        self.assertEqual(self.read(), {"reviews": [
                         only_end, REVIEW, first, second]})

    def test_refuses_feedback_that_breaks_a_rule(self):
        # The rules are common.feedback_problems(), tested in test_common.py:
        # feedback that breaks them writes nothing, and the message shows the
        # input to send.
        with self.assertRaisesRegex(SystemExit, "must be one of the company's: Below, Meets, Exceeds(.|\n)*END_OF_INPUT"):
            set_feedback.set_feedback(
                PREP, {"reviews": [{**REVIEW, "rating": "Good"}]})
        self.assertFalse(os.path.exists(self.path))


if __name__ == "__main__":
    unittest.main()
