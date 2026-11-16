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
from prep_fixture import CONTENT, DATA, DATA_BY_PROJECT, DATA_NO_EPIC_FIRST, PERSON, REPORT_FOLDER, SUMMARIES, VALUE_NAMES  # noqa: E402


class CheckReportTest(unittest.TestCase):
    def test_report_problems(self):
        # name: (a change to the report's text, the charts, expected in the
        # problems, or None for none): each Jira figure is read back from the
        # table and worked out again from the items.
        report = make_report.render(PERSON, DATA, REPORT_FOLDER, CONTENT)
        cases = [("as written", None, common.CHART_FILES, None),
                 ("a page count changed", ("Pages created</b> (1)", "Pages created</b> (2)"),
                  common.CHART_FILES, "Notion pages"),
                 ("a page's week changed", (">10–16 Aug<", ">17–23 Aug<"),
                  common.CHART_FILES, "Notion pages"),
                 ("a page's area changed", (">Engineering<", ">Billing<"),
                  common.CHART_FILES, "Notion pages"),
                 ("a week's span changed", ('rowspan="1">10–16', 'rowspan="2">10–16'),
                  common.CHART_FILES, "Notion pages"),
                 ("no Notion section", ("## Notion", "## Pages"),
                  common.CHART_FILES, "its Jira one and its Notion one"),
                 ("no Feedback section", ("## Observations", "## Evidence"),
                  common.CHART_FILES, "must have its Observations section"),
                 ("a point count changed", ("Details (3 points)", "Details (4 points)"),
                  common.CHART_FILES, "Going well points"),
                 ("a point's text changed", ("Presented the migration", "Presented the plan"),
                  common.CHART_FILES, "Going well points"),
                 ("a point's source changed", (">Slack<", ">Feedback<"),
                  common.CHART_FILES, "Going well points"),
                 ("a period changed", (">Q3 2026<", ">Q2 2026<"),
                  common.CHART_FILES, "Going well points"),
                 ("an evidence's day changed", (">Journal 20 Aug</a>", ">Journal 21 Aug</a>"),
                  common.CHART_FILES, "To improve points"),
                 ("a summary changed", ("Jane explains outages", "Jane fixes outages"),
                  common.CHART_FILES, "Going well summary"),
                 ("a value's span changed", ('rowspan="2">Teamwork', 'rowspan="1">Teamwork'),
                  common.CHART_FILES, "Going well points"),
                 ("a count changed", ('">1</a> (1 Task)', '">2</a> (1 Task)'),
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
                 ("no Jira section", ("## Jira", "## Tickets"),
                  common.CHART_FILES, "its Jira one"),
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
                    check_report.report_problems(text, DATA, charts, SUMMARIES, VALUE_NAMES, REPORT_FOLDER, CONTENT))
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
                 ("a focus share", lambda jira: jira["focus"][0].update(
                     share=50), "shares the Jira pie"),
                 ("the epics coloured", lambda jira: jira["epic_order"].append("PROJ-9"),
                  "epics the charts colour")]
        github = [("the repositories' pie", lambda github: github["merged_by_repo"].update(other=1),
                   "merged pull requests by repository"),
                  ("a week's merged", lambda github: github["merged_by_week"]["total"].reverse(),
                   "pull requests merged"),
                  ("the sizes", lambda github: github["lines_distribution"]["total"].reverse(),
                   "merged pull requests' size"),
                  ("a focus share", lambda github: github["focus"][0].update(
                      share=50), "shares the GitHub pie"),
                  ("the repositories coloured", lambda github: github["repo_order"].clear(),
                   "repositories the charts colour")]
        for name, change, source, expected in [*((name, change, "jira", expected) for name, change, expected in cases),
                                               *((name, change, "github", expected)
                                                 for name, change, expected in github)]:
            with self.subTest(name):
                data = copy.deepcopy(DATA)
                change(data[source])
                self.assertIn(expected, " ".join(check_report.report_problems(
                    make_report.render(PERSON, data, REPORT_FOLDER, CONTENT), data, common.CHART_FILES, SUMMARIES, VALUE_NAMES, REPORT_FOLDER, CONTENT)))

    def test_observations_order(self):
        # Two points swapped, the older first, or a value moved under
        # another: the check orders them again from the summaries.
        report = make_report.render(PERSON, DATA, REPORT_FOLDER, CONTENT)
        slack, notes = (point["point"]
                        for point in DATA["observations"]["going_well"][0]["points"])
        swapped = report.replace(slack, "\0").replace(
            notes, slack).replace("\0", notes)
        self.assertIn("Going well points", " ".join(check_report.report_problems(
            swapped, DATA, common.CHART_FILES, SUMMARIES, VALUE_NAMES, REPORT_FOLDER, CONTENT)))
        self.assertIn("Going well points", " ".join(check_report.report_problems(
            report.replace(">Teamwork<",
                           ">Ownership<", 1), DATA, common.CHART_FILES,
            SUMMARIES, VALUE_NAMES, REPORT_FOLDER, CONTENT)))

    def test_observations_same_day(self):
        # Evidence of the same day keeps the order the summary gives it, in
        # the model and in the check alike.
        later = {"date": "2026-10-01",
                 "link": "/vault/journals/2026_10_01_b.md"}
        notes = {**SUMMARIES["notes"], "to_improve": [{**SUMMARIES["notes"]["to_improve"][0], "evidence": [
            SUMMARIES["notes"]["to_improve"][0]["evidence"][0], later,
            *SUMMARIES["notes"]["to_improve"][0]["evidence"][1:]]}]}
        summaries = {**SUMMARIES, "notes": notes}
        data = {
            **DATA, "observations": build_data.observations(summaries, VALUE_NAMES)}
        self.assertEqual(check_report.report_problems(
            make_report.render(PERSON, data, REPORT_FOLDER, CONTENT), data, common.CHART_FILES, summaries, VALUE_NAMES, REPORT_FOLDER, CONTENT), [])

    def test_focus(self):
        # name: (data.json, an entry of its Jira main focus as the report
        # writes it, the same with a wrong count): the check reads every
        # entry back, those with no epic wherever they rank, and a project's
        # unlinked when no resolved issue has an epic.
        cases = [("no epic before an epic", DATA_NO_EPIC_FIRST, "no epic</a> (3)</li>"),
                 ("by project", DATA_BY_PROJECT, "<li>PROJ (1)</li>")]
        for name, data, entry in cases:
            with self.subTest(name):
                report = make_report.render(
                    PERSON, data, REPORT_FOLDER, CONTENT)
                self.assertIn(entry, report)
                self.assertEqual(check_report.report_problems(
                    report, data, common.CHART_FILES, SUMMARIES, VALUE_NAMES, REPORT_FOLDER, CONTENT), [])
                self.assertIn("main focus", " ".join(check_report.report_problems(
                    report.replace(entry, entry.replace("(", "(7"), 1), data, common.CHART_FILES, SUMMARIES, VALUE_NAMES, REPORT_FOLDER, CONTENT)))


if __name__ == "__main__":
    unittest.main()
