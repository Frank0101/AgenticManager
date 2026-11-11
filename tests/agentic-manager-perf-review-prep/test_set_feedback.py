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

import set_feedback  # noqa: E402
sys.path.insert(0, TEST_DIR)
from prep_fixture import PIECE, PREP, temp_output, write_prep  # noqa: E402


class SetFeedbackTest(unittest.TestCase):
    def setUp(self):
        self.folder = temp_output(self)
        write_prep(self.folder, feedback=None)
        self.path = os.path.join(self.folder, PREP, "feedback.json")

    def read(self):
        with open(self.path, encoding="utf-8") as f:
            return json.load(f)

    def test_writes_them_oldest_first_and_a_correction_replaces_them(self):
        older = {**PIECE, "start": "2025-07-01",
                 "end": "2025-12-31", "rating": "Below"}
        self.assertEqual(set_feedback.set_feedback(
            PREP, {"pieces": [PIECE, older]}), self.path)
        self.assertEqual(self.read(), {"pieces": [older, PIECE]})
        set_feedback.set_feedback(PREP, {"pieces": []})
        self.assertEqual(self.read(), {"pieces": []})

    def test_writes_undated_feedback_last_in_the_order_given(self):
        first = {**PIECE, "start": None, "end": None, "rating": None,
                 "context": ["Mentors new joiners"]}
        second = {**first, "context": ["Runs the guild"]}
        only_end = {**first, "end": "2025-03-31",
                    "context": ["Shipped the search revamp"]}
        set_feedback.set_feedback(
            PREP, {"pieces": [first, PIECE, second, only_end]})
        self.assertEqual(self.read(), {"pieces": [
                         only_end, PIECE, first, second]})

    def test_refuses_feedback_that_breaks_a_rule(self):
        # The rules are common.feedback_problems(), tested in test_common.py:
        # feedback that breaks them writes nothing, and the message shows the
        # input to send.
        with self.assertRaisesRegex(SystemExit, "must be one of the company's: Below, Meets, Exceeds(.|\n)*END_OF_INPUT"):
            set_feedback.set_feedback(
                PREP, {"pieces": [{**PIECE, "rating": "Good"}]})
        self.assertFalse(os.path.exists(self.path))


if __name__ == "__main__":
    unittest.main()
