"""Unit tests for skills/agentic-manager-perf-review-prep/scripts/finish_report.py.
Run with: python3 tests/run.py agentic-manager-perf-review-prep
"""

import os
import sys
import unittest

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(TEST_DIR))
sys.path.insert(0, os.path.join(REPO_ROOT, "skills",
                os.path.basename(TEST_DIR), "scripts"))
import common  # noqa: E402
import finish_report  # noqa: E402
sys.path.insert(0, TEST_DIR)
from prep_fixture import CONTENT, PREP, STEP_CHANGE, VIEW_CHECK, temp_output, write_prep  # noqa: E402


class FinishReportTest(unittest.TestCase):
    def test_finish(self):
        # The report and every chart, checked once written.
        folder = temp_output(self)
        write_prep(folder, report=False)
        made = finish_report.finish(PREP)
        self.assertEqual((made["problems"], sorted(os.listdir(os.path.join(folder, PREP, common.CHARTS_DIR)))),
                         ([], sorted(common.CHART_FILES)))

    def test_content_first(self):
        # name: (content.json, step_change.json, view_check.json, expected
        # problems, or a text in them): nothing written while one is missing
        # or breaks a rule, each problem naming its file and field.
        cases = [("all missing", None, None, None,
                  ["content.json is missing: write it, as step 8's observations task says",
                   "step_change.json is missing: write it, as step 8's step-change task says",
                   "view_check.json is missing: write it, as step 8's view-check task says"]),
                 ("the step change missing", CONTENT, None, VIEW_CHECK,
                  ["step_change.json is missing: write it, as step 8's step-change task says"]),
                 ("the view check missing", CONTENT, STEP_CHANGE, None,
                  ["view_check.json is missing: write it, as step 8's view-check task says"]),
                 ("a summary breaking a rule", {
                  **CONTENT, "going_well": ""}, STEP_CHANGE, VIEW_CHECK, "going_well is empty"),
                 ("the step change breaking a rule", CONTENT, {**STEP_CHANGE, "rows": []}, VIEW_CHECK,
                  "step_change.json has no row for R-I1, R-I2"),
                 ("the view check breaking a rule", CONTENT, STEP_CHANGE, {**VIEW_CHECK, "rows": []},
                  "view_check.json has no row for V-G1, V-I1, V-C1")]
        for name, content, step_change, view_check, expected in cases:
            with self.subTest(name):
                folder = temp_output(self)
                write_prep(folder, content=content, step_change=step_change,
                           view_check=view_check, report=False)
                made = finish_report.finish(PREP)
                self.assertEqual((made["report"], os.path.exists(os.path.join(folder, PREP, common.CHARTS_DIR))),
                                 (None, False))
                if isinstance(expected, list):
                    self.assertEqual(made["problems"], expected)
                else:
                    self.assertIn(expected, " ".join(made["problems"]))


if __name__ == "__main__":
    unittest.main()
