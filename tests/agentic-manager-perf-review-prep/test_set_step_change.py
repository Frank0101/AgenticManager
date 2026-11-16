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
from prep_fixture import DATA, PREP, STEP_CHANGE, temp_output, write_prep  # noqa: E402


class SetStepChangeTest(unittest.TestCase):
    def test_set_step_change(self):
        # name: (data.json's previous reviews, the step change, expected in
        # the problem, or None when it is written): written once it compares
        # data.json's latest review with the period; refused, writing
        # nothing, with every problem.
        rows = STEP_CHANGE["rows"]
        cases = [("a row missing", DATA["reviews"], {**STEP_CHANGE, "rows": rows[:1]},
                  "step_change.json has no row for R-I1, R-I2"),
                 ("null with a previous review",
                  DATA["reviews"], None, "step_change.json must be {"),
                 ("as written", DATA["reviews"], STEP_CHANGE, None),
                 ("null with no previous review", None, None, None)]
        for name, reviews, value, expected in cases:
            with self.subTest(name):
                folder = temp_output(self)
                write_prep(folder, data={
                           **DATA, "reviews": reviews}, step_change=None, report=False)
                path = os.path.join(folder, PREP, "step_change.json")
                if expected is None:
                    self.assertEqual(common.read_json(
                        set_step_change.set_step_change(PREP, value)), value)
                    continue
                with self.assertRaisesRegex(SystemExit, f"{re.escape(expected)}(.|\n)*END_OF_INPUT"):
                    set_step_change.set_step_change(PREP, value)
                self.assertFalse(os.path.exists(path))


if __name__ == "__main__":
    unittest.main()
