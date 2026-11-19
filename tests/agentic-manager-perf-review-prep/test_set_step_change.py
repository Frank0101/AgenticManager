"""Unit tests for skills/agentic-manager-perf-review-prep/scripts/set_step_change.py.
Run with: python3 tests/run.py agentic-manager-perf-review-prep
"""

import os
import re
import sys
import unittest

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(TEST_DIR))
sys.path.insert(0, os.path.join(REPO_ROOT, "skills",
                os.path.basename(TEST_DIR), "scripts"))
import common  # noqa: E402
import set_step_change  # noqa: E402
sys.path.insert(0, TEST_DIR)
from prep_fixture import DATA, PREP, STEP_CHANGE_CONTENT, temp_output, write_prep  # noqa: E402


class SetStepChangeTest(unittest.TestCase):
    def test_set_step_change(self):
        # name: (a change to data.json, the value, expected in the problem,
        # or None when it is written): written once it compares data.json's
        # previous feedback with the period; refused, writing nothing, with
        # every problem and the input.
        cases = [("a row missing", {}, {**STEP_CHANGE_CONTENT, "rows": STEP_CHANGE_CONTENT["rows"][:1]},
                  "step_change_content.json has no row for P-I1, P-I2"),
                 ("null with previous feedback", {}, None,
                  "step_change_content.json must be {"),
                 ("as written", {}, STEP_CHANGE_CONTENT, None),
                 ("two rows for one previous point, an aspect each", {}, {**STEP_CHANGE_CONTENT, "rows": [
                     {"previous_point": "P-I1",
                         "change": "improved", "evidence": ["G2"]},
                     {"previous_point": "P-I1",
                         "change": "still_to_improve", "evidence": ["I1"]},
                     *STEP_CHANGE_CONTENT["rows"][:3]]}, None),
                 ("two rows for one point, another to-improve point with none", {}, {
                     **STEP_CHANGE_CONTENT, "rows": [
                         {"previous_point": "P-I1",
                             "change": "improved", "evidence": ["G2"]},
                         {"previous_point": "P-I1", "change": "still_to_improve", "evidence": ["I1"]}]},
                  "step_change_content.json has no row for P-I2"),
                 ("null with no previous feedback", {"previous": None}, None, None)]
        for name, changes, value, expected in cases:
            with self.subTest(name):
                folder = temp_output(self)
                write_prep(folder, data={
                           **DATA, **changes}, step_change_content=None, report=False)
                path = os.path.join(
                    folder, PREP, common.STEP_CHANGE_CONTENT)
                if expected is None:
                    self.assertEqual(common.read_json(
                        set_step_change.set_step_change(PREP, value)), value)
                    continue
                with self.assertRaisesRegex(SystemExit, f"{re.escape(expected)}(.|\n)*"
                                            "python3 set_step_change.py --prep(.|\n)*END_OF_INPUT"):
                    set_step_change.set_step_change(PREP, value)
                self.assertFalse(os.path.exists(path))

    def test_help_says_a_point_may_have_a_row_for_each_aspect(self):
        # The input's text, shown in --help and in every error, lets a
        # previous point whose aspects went differently have several rows.
        self.assertIn(
            "at least a row per to-improve point of the previous feedback", set_step_change.INPUT)
        self.assertIn("a point whose aspects\n                  went differently may have a row for each",
                      set_step_change.INPUT)
        self.assertNotIn("such as P-I1, once", set_step_change.INPUT)


if __name__ == "__main__":
    unittest.main()
