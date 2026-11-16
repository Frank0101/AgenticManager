"""Unit tests for skills/agentic-manager-perf-review-prep/scripts/set_comparison.py.
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
import set_comparison  # noqa: E402
sys.path.insert(0, TEST_DIR)
from prep_fixture import DATA, PREP, STEP_CHANGE, VIEW_CHECK, temp_output, write_prep  # noqa: E402


class SetComparisonTest(unittest.TestCase):
    def test_set_comparison(self):
        # name: (the comparison, a change to data.json, the value, expected
        # in the problem, or None when it is written): written once it
        # compares data.json's baseline with the period; refused, writing
        # nothing, with every problem and the comparison's input.
        step, view = common.STEP_CHANGE_COMPARISON, common.VIEW_CHECK_COMPARISON
        cases = [("step change, a row missing", step, {}, {**STEP_CHANGE, "rows": STEP_CHANGE["rows"][:1]},
                  "step_change.json has no row for R-I1, R-I2"),
                 ("step change, null with a previous review", step,
                  {}, None, "step_change.json must be {"),
                 ("step change, as written", step, {}, STEP_CHANGE, None),
                 ("step change, null with no previous review", step,
                  {"reviews": None}, None, None),
                 ("view check, a row missing", view, {}, {**VIEW_CHECK, "rows": VIEW_CHECK["rows"][:2]},
                  "view_check.json has no row for V-G1, V-C1"),
                 ("view check, null", view, {},
                  None, "view_check.json must be {"),
                 ("view check, as written", view, {}, VIEW_CHECK, None)]
        for name, comparison, changes, value, expected in cases:
            with self.subTest(name):
                folder = temp_output(self)
                write_prep(folder, data={
                           **DATA, **changes}, step_change=None, view_check=None, report=False)
                path = os.path.join(folder, PREP, comparison.file)
                if expected is None:
                    self.assertEqual(common.read_json(
                        set_comparison.set_comparison(PREP, comparison, value)), value)
                    continue
                with self.assertRaisesRegex(SystemExit, f"{re.escape(expected)}(.|\n)*"
                                            f"--of {comparison.task}(.|\n)*END_OF_INPUT"):
                    set_comparison.set_comparison(PREP, comparison, value)
                self.assertFalse(os.path.exists(path))


if __name__ == "__main__":
    unittest.main()
