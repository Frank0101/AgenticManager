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
import check_report  # noqa: E402
import common  # noqa: E402
import make_report  # noqa: E402
sys.path.insert(0, TEST_DIR)
from prep_fixture import DATA, DATA_BY_PROJECT, DATA_NO_EPIC_FIRST, PERSON  # noqa: E402


class CheckReportTest(unittest.TestCase):
    def test_report_problems(self):
        # name: (a change to the report's text, the charts, expected in the
        # problems, or None for none): each Jira figure is read back from the
        # table and worked out again from the items.
        report = make_report.render(PERSON, DATA)
        cases = [("as written", None, common.CHART_FILES, None),
                 ("a page count changed", ("Pages created</b> (1)", "Pages created</b> (2)"),
                  common.CHART_FILES, "Notion pages"),
                 ("a page's week changed", ("<small>10–16 Aug</small>", "<small>17–23 Aug</small>"),
                  common.CHART_FILES, "Notion pages"),
                 ("a page's area changed", ("<small>Engineering</small>", "<small>Billing</small>"),
                  common.CHART_FILES, "Notion pages"),
                 ("a week's span changed", ('rowspan="1"', 'rowspan="2"'),
                  common.CHART_FILES, "Notion pages"),
                 ("no Notion section", ("## Notion", "## Pages"),
                  common.CHART_FILES, "then its Notion one"),
                 ("a count changed", ('">1</a>', '">2</a>'),
                  common.CHART_FILES, "cell for created"),
                 ("a breakdown changed", ("(1 Task)", "(1 Bug)"),
                  common.CHART_FILES, "cell for created"),
                 ("an average changed", ("avg=3", "avg=4"),
                  common.CHART_FILES, "cell for resolved_points"),
                 ("a focus count changed", ("Billing (1)", "Billing (2)"),
                  common.CHART_FILES, "Jira main focus"),
                 ("a GitHub count changed", ('">1</a> (in 1 repository)', '">2</a> (in 1 repository)'),
                  common.CHART_FILES, "GitHub cell for opened"),
                 ("a median changed", ("<td>150 (median", "<td>151 (median"),
                  common.CHART_FILES, "GitHub cell for merged_lines"),
                 ("a repository's count changed", ("acme/billing</a> (1)", "acme/billing</a> (2)"),
                  common.CHART_FILES, "GitHub main focus"),
                 ("a repository's code changed", ("<li>A <a", "<li>B <a"),
                  common.CHART_FILES, "GitHub main focus"),
                 ("no GitHub section", ("## GitHub", "## Code"),
                  common.CHART_FILES, "then its GitHub one"),
                 ("no charts", ('<td><a href="_charts', '<td><a href="charts'),
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
        # name: (a change to data.json's Jira, or GitHub, facts, expected in
        # the problems): each series a chart draws is counted again from the
        # items, so a model that disagrees with them fails.
        cases = [("the pie's epics", lambda jira: jira["resolved_by_epic"].update(epics=[]),
                  "resolved issues by epic"),
                 ("a week's count", lambda jira: jira["created_by_week"]["total"].reverse(),
                  "issues created"),
                 ("the story points' stacks", lambda jira: jira["points_by_epic"].clear(),
                  "story points"),
                 ("the epics coloured", lambda jira: jira["epic_order"].append("PROJ-9"),
                  "epics the charts colour")]
        github = [("the repositories' pie", lambda github: github["merged_by_repo"].update(other=1),
                   "merged pull requests by repository"),
                  ("a week's merged", lambda github: github["merged_by_week"]["total"].reverse(),
                   "pull requests merged"),
                  ("the sizes", lambda github: github["lines_distribution"]["total"].reverse(),
                   "merged pull requests' size"),
                  ("the repositories coloured", lambda github: github["repo_order"].clear(),
                   "repositories the charts colour")]
        for name, change, source, expected in [*((name, change, "jira", expected) for name, change, expected in cases),
                                               *((name, change, "github", expected)
                                                 for name, change, expected in github)]:
            with self.subTest(name):
                data = copy.deepcopy(DATA)
                change(data[source])
                self.assertIn(expected, " ".join(check_report.report_problems(
                    make_report.render(PERSON, data), data, common.CHART_FILES)))

    def test_focus(self):
        # name: (data.json, an entry of its Jira main focus as the report
        # writes it, the same with a wrong count): the check reads every
        # entry back, those with no epic wherever they rank, and a project's
        # unlinked when no resolved issue has an epic.
        cases = [("no epic before an epic", DATA_NO_EPIC_FIRST, "no epic</a> (3)</li>"),
                 ("by project", DATA_BY_PROJECT, "<li>PROJ (1)</li>")]
        for name, data, entry in cases:
            with self.subTest(name):
                report = make_report.render(PERSON, data)
                self.assertIn(entry, report)
                self.assertEqual(check_report.report_problems(
                    report, data, common.CHART_FILES), [])
                self.assertIn("main focus", " ".join(check_report.report_problems(
                    report.replace(entry, entry.replace("(", "(7"), 1), data, common.CHART_FILES)))


if __name__ == "__main__":
    unittest.main()
