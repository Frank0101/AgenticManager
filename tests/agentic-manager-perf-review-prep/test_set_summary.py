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
from prep_fixture import MANAGER_FEEDBACK, OTHER_FEEDBACK, PREVIOUS_FEEDBACK, PREP, temp_output, write_prep  # noqa: E402


class SetSummaryTest(unittest.TestCase):
    def setUp(self):
        self.folder = temp_output(self)
        write_prep(self.folder, manager=None, other=None, previous=None)

    def path(self, name):
        return os.path.join(self.folder, PREP, name)

    def read(self, name):
        with open(self.path(name), encoding="utf-8") as f:
            return json.load(f)

    def test_writes_each_kind_as_given_and_a_correction_replaces_it(self):
        # Each kind to its own file, the three the same way, and a correction
        # replaces it whole, even with no points at all.
        empty = {"going_well": [], "to_improve": [], "context": []}
        cases = [("manager", "manager_feedback.json", MANAGER_FEEDBACK),
                 ("other", "other_feedback.json", OTHER_FEEDBACK),
                 ("previous", "previous_feedback.json", PREVIOUS_FEEDBACK)]
        for kind, name, value in cases:
            with self.subTest(kind):
                self.assertEqual(set_summary.set_summary(
                    PREP, kind, value), self.path(name))
                self.assertEqual(self.read(name), value)
                set_summary.set_summary(PREP, kind, empty)
                self.assertEqual(self.read(name), empty)

    def test_refuses_a_summary_that_breaks_its_rules(self):
        # The rules are common's feedback_problems(), tested in
        # test_common.py: a summary that breaks them writes nothing, and the
        # message shows the input to send for its kind.
        cases = [("manager", "manager_feedback.json", {"text": "Strong half overall."},
                  "the current manager feedback must have the parts"),
                 ("other", "other_feedback.json", {**OTHER_FEEDBACK, "context": [""]},
                  "the other feedback's context must be a list of points"),
                 ("previous", "previous_feedback.json",
                  {**PREVIOUS_FEEDBACK,
                      "going_well": [{"point": "Led it", "values": ["Grit"]}]},
                  "the previous feedback's going_well")]
        for kind, name, value, expected in cases:
            with self.subTest(kind):
                with self.assertRaisesRegex(SystemExit, f"{expected}(.|\n)*--of {kind}(.|\n)*END_OF_INPUT"):
                    set_summary.set_summary(PREP, kind, value)
                self.assertFalse(os.path.exists(self.path(name)))


if __name__ == "__main__":
    unittest.main()
