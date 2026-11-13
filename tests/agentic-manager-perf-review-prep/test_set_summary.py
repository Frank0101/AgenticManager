"""Unit tests for skills/agentic-manager-perf-review-prep/scripts/set_summary.py.
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
import set_summary  # noqa: E402
sys.path.insert(0, TEST_DIR)
from prep_fixture import NOTE, ORIENTATION, PIECE, PREP, temp_output, write_prep  # noqa: E402


class SetSummaryTest(unittest.TestCase):
    def setUp(self):
        self.folder = temp_output(self)
        write_prep(self.folder, orientation=None, reviews=None, feedback=None)

    def path(self, name):
        return os.path.join(self.folder, PREP, name)

    def read(self, name):
        with open(self.path(name), encoding="utf-8") as f:
            return json.load(f)

    def test_writes_each_kind_as_given_and_a_correction_replaces_it(self):
        # Each kind to its own file, pieces in the order given, as the agent
        # lists them from the most recent: a period is a label, so there's
        # nothing to sort by.
        older = {**PIECE, "period": "Annual Review 2025", "rating": "Below"}
        cases = [("orientation", "orientation.json", ORIENTATION, {**ORIENTATION, "context": []}),
                 ("reviews", "reviews.json", {"pieces": [{**PIECE, "period": None, "rating": None}, PIECE, older]},
                  {"pieces": []}),
                 ("feedback", "feedback.json", {"pieces": [{**NOTE, "period": None}, NOTE,
                                                           {**NOTE, "period": "Q2 2026"}]}, {"pieces": []})]
        for kind, name, value, corrected in cases:
            with self.subTest(kind):
                self.assertEqual(set_summary.set_summary(
                    PREP, kind, value), self.path(name))
                self.assertEqual(self.read(name), value)
                set_summary.set_summary(PREP, kind, corrected)
                self.assertEqual(self.read(name), corrected)

    def test_refuses_a_summary_that_breaks_its_rules(self):
        # The rules are common's orientation_problems(), reviews_problems()
        # and feedback_problems(), tested in test_common.py: a summary that
        # breaks them writes nothing, and the message shows the input to send
        # for its kind.
        cases = [("orientation", "orientation.json", {"text": "Strong half overall."},
                  "orientation must have the parts"),
                 ("reviews", "reviews.json", {"pieces": [{**PIECE, "rating": "Good"}]},
                  "must be one of the company's: Below, Meets, Exceeds"),
                 ("feedback", "feedback.json", {"pieces": [{**NOTE, "period": ""}]}, "must be a text")]
        for kind, name, value, expected in cases:
            with self.subTest(kind):
                with self.assertRaisesRegex(SystemExit, f"{expected}(.|\n)*--of {kind}(.|\n)*END_OF_INPUT"):
                    set_summary.set_summary(PREP, kind, value)
                self.assertFalse(os.path.exists(self.path(name)))


if __name__ == "__main__":
    unittest.main()
