"""Unit tests for skills/agentic-manager-perf-review-prep/scripts/check_report.py.
Run with: python3 tests/run.py agentic-manager-perf-review-prep
"""

import copy
import os
import sys
import unittest

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(TEST_DIR))
sys.path.insert(0, os.path.join(REPO_ROOT, "skills",
                os.path.basename(TEST_DIR), "scripts"))
import build_data  # noqa: E402
import check_report  # noqa: E402
import common  # noqa: E402
import make_report  # noqa: E402
sys.path.insert(0, TEST_DIR)
from prep_fixture import PERSON, DATA  # noqa: E402


class CheckReportTest(unittest.TestCase):
    def test_report_problems(self):
        # name: (a change to the report's text, the charts, expected in the
        # problems, or None for none): each Jira figure is read back from the
        # table and worked out again from the items.
        report = make_report.render(PERSON, DATA)
        cases = [("as written", None, common.CHART_FILES, None),
                 ("a count changed", ('">1</a>', '">2</a>'),
                  common.CHART_FILES, "cell for created"),
                 ("a breakdown changed", ("(1 Task)", "(1 Bug)"),
                  common.CHART_FILES, "cell for created"),
                 ("an average changed", ("avg=3", "avg=4"),
                  common.CHART_FILES, "cell for resolved_points"),
                 ("a focus count changed", ("Billing (1)", "Billing (2)"),
                  common.CHART_FILES, "main focus"),
                 ("no charts", ("<td><img", "<td><image"),
                  common.CHART_FILES, "a row of three figures and one of their charts"),
                 ("a chart missing", None,
                  common.CHART_FILES[1:], "the charts folder must hold only"),
                 ("a .DS_Store beside the charts", None, [*common.CHART_FILES, ".DS_Store"], None)]
        for name, change, charts, expected in cases:
            with self.subTest(name):
                text = report.replace(
                    change[0], change[1], 1) if change else report
                problems = " ".join(
                    check_report.report_problems(text, DATA, charts))
                if expected is None:
                    self.assertEqual(problems, "")
                else:
                    self.assertIn(expected, problems)

    def test_model_problems(self):
        # name: (a change to data.json's Jira facts, expected in the
        # problems): each series a chart draws is counted again from the
        # issues, so a model that disagrees with them fails.
        cases = [("the pie's epics", lambda jira: jira["resolved_by_epic"].update(epics=[], no_epic=1),
                  "resolved issues by epic"),
                 ("a week's count", lambda jira: jira["created_by_week"]["total"].reverse(),
                  "issues created"),
                 ("the story points' stacks", lambda jira: jira["points_by_epic"].clear(),
                  "story points")]
        for name, change, expected in cases:
            with self.subTest(name):
                data = copy.deepcopy(DATA)
                change(data["jira"])
                self.assertIn(expected, " ".join(check_report.report_problems(
                    make_report.render(PERSON, data), data, common.CHART_FILES)))

    def test_focus_by_project(self):
        # When no resolved issue has an epic, the main focus lists their
        # projects, unlinked, and the check reads them back.
        data = copy.deepcopy(DATA)
        jira = data["jira"]
        jira["resolved"] = [{**issue, "epic": None}
                            for issue in jira["resolved"]]
        jira.update(build_data.source_facts(
            "jira", {"created": jira["created"], "resolved": jira["resolved"]}, data["weeks"]))
        report = make_report.render(PERSON, data)
        self.assertIn("<li>PROJ (1)</li>", report)
        self.assertIn("the projects with the most of them", report)
        self.assertEqual(check_report.report_problems(
            report, data, common.CHART_FILES), [])
        self.assertIn("main focus", " ".join(check_report.report_problems(
            report.replace("PROJ (1)", "PROJ (7)"), data, common.CHART_FILES)))


if __name__ == "__main__":
    unittest.main()
