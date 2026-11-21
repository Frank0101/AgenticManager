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
        # name: (the agent's files to write instead of the fixture's, None
        # for missing, expected problems, or a text in them): nothing written
        # while one is missing or breaks a rule, each problem naming its file
        # and field.
        files = ("work_impact_content", "earlier_work_content",
                 "observations_content", "step_change_content")
        cases = [("all missing", dict.fromkeys(files),
                  [f"{name} is missing: write it, as the {task} task says"
                   for name, task, _ in common.agent_files()]),
                 ("the step change missing", {"step_change_content": None},
                  ["step_change_content.json is missing: write it, as the step-change task says"]),
                 ("the work and its impact breaking a rule",
                  {"work_impact_content": {"initiatives": []}}, "with at least one initiative"),
                 ("the work before the period breaking a rule",
                  {"earlier_work_content": {"bullets": []}}, "earlier_work_content.json"),
                 ("a summary breaking a rule",
                  {"observations_content": {**OBSERVATIONS_CONTENT,
                                            "going_well": {"values": {}, "also": None}}},
                  "going_well summarises no value"),
                 ("the step change breaking a rule", {"step_change_content": {**STEP_CHANGE_CONTENT, "rows": []}},
                  "step_change_content.json has no row for P-I1, P-I2")]
        for name, written, expected in cases:
            with self.subTest(name):
                folder = temp_output(self)
                write_prep(folder, **written, report=False)
                made = finish_report.finish(PREP)
                self.assertEqual((made["report"], os.path.exists(os.path.join(folder, PREP, common.CHARTS_DIR))),
                                 (None, False))
                if isinstance(expected, list):
                    self.assertEqual(made["problems"], expected)
                else:
                    self.assertIn(expected, " ".join(made["problems"]))


if __name__ == "__main__":
    unittest.main()
