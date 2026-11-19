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
from prep_fixture import OBSERVATIONS_CONTENT, PREP, STEP_CHANGE_CONTENT, temp_output, write_prep  # noqa: E402


class FinishReportTest(unittest.TestCase):
    def test_finish(self):
        # The report and every chart, checked once written.
        folder = temp_output(self)
        write_prep(folder, report=False)
        made = finish_report.finish(PREP)
        self.assertEqual((made["problems"], sorted(os.listdir(os.path.join(folder, PREP, common.CHARTS_DIR)))),
                         ([], sorted(common.CHART_FILES)))

    def test_agents_files_first(self):
        # name: (observations_content.json, step_change_content.json, expected problems, or a text
        # in them): nothing written while one is missing or breaks a rule,
        # each problem naming its file and field.
        cases = [("all missing", None, None,
                  ["observations_content.json is missing: write it, as the observations task says",
                   "step_change_content.json is missing: write it, as the step-change task says"]),
                 ("the step change missing", OBSERVATIONS_CONTENT, None,
                  ["step_change_content.json is missing: write it, as the step-change task says"]),
                 ("a summary breaking a rule", {
                  **OBSERVATIONS_CONTENT, "going_well": ""}, STEP_CHANGE_CONTENT, "going_well is empty"),
                 ("the step change breaking a rule", OBSERVATIONS_CONTENT, {**STEP_CHANGE_CONTENT, "rows": []},
                  "step_change_content.json has no row for P-I1, P-I2")]
        for name, content, step_change, expected in cases:
            with self.subTest(name):
                folder = temp_output(self)
                write_prep(folder, observations_content=content,
                           step_change_content=step_change, report=False)
                made = finish_report.finish(PREP)
                self.assertEqual((made["report"], os.path.exists(os.path.join(folder, PREP, common.CHARTS_DIR))),
                                 (None, False))
                if isinstance(expected, list):
                    self.assertEqual(made["problems"], expected)
                else:
                    self.assertIn(expected, " ".join(made["problems"]))


if __name__ == "__main__":
    unittest.main()
