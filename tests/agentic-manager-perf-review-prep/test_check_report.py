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
from prep_fixture import OBSERVATIONS_CONTENT, STEP_CHANGE_CONTENT, CONTEXT_STEP_CHANGE, CONTEXT_DATA, CONTEXT_SUMMARIES, DATA, DATA_BY_PROJECT, DATA_NO_EPIC_FIRST, PERSON, REPORT_FOLDER, SUMMARIES, VALUE_NAMES  # noqa: E402


class CheckReportTest(unittest.TestCase):
    def test_report_problems(self):
        # name: (a change to the report's text, (old, new) for its first
        # old, or an edit of the whole text, expected in the problems, or
        # None for none): each Jira figure is read back from the table and
        # worked out again from the items, and the observations' order from
        # the summaries.
        report = make_report.render(
            PERSON, DATA, REPORT_FOLDER, OBSERVATIONS_CONTENT, STEP_CHANGE_CONTENT)

        def swapped(first, second):
            return lambda text: text.replace(first, "\0").replace(second, first).replace("\0", second)
        slack, notes = (
            point["point"] for point in DATA["observations"]["going_well"][0]["points"])
        page, piece = (point["point"]
                       for point in DATA["observations"]["context"][:2])
        cases = [("as written", None, None),
                 ("two points swapped, the older first",
                  swapped(slack, notes), "Going well points"),
                 ("a value moved under another",
                  (">Teamwork<", ">Ownership<"), "Going well points"),
                 ("the undated page's context point after a dated one",
                  swapped(page, piece), "Context points"),
                 ("a page count changed", ("Pages created</b> (1)",
                  "Pages created</b> (2)"), "Notion pages"),
                 ("a page's week changed",
                  (">10–16 Aug<", ">17–23 Aug<"), "Notion pages"),
                 ("a page's area changed",
                  (">Engineering<", ">Billing<"), "Notion pages"),
                 ("a week's span changed", ('rowspan="1">10–16',
                  'rowspan="2">10–16'), "Notion pages"),
                 ("no Notion section", ("## Notion", "## Pages"),
                  "its Jira one and its Notion one"),
                 ("no Feedback section", ("## Observations", "## Evidence"),
                  "must have its Observations section"),
                 ("no Observations subtitle", ("*What the current manager feedback, the period's other feedback, the "
                                               "manager's notes and Slack show, by company value.*\n\n", ""),
                  "Observations must start with its subtitle"),
                 ("the Observations subtitle changed", ("Slack show, by company value", "Slack show"),
                  "Observations must start with its subtitle"),
                 ("a point count changed", ("Details (4 points)",
                  "Details (5 points)"), "Going well points"),
                 ("a manager feedback point's source changed", ("<td>Manager feedback</td>", "<td>Other feedback</td>"),
                  "Going well points"),
                 ("a manager feedback point dropped", ("Has led the billing migration well since May", "Has led it well"),
                  "Going well points"),
                 ("a point's text changed", ("Presented the migration",
                  "Presented the plan"), "Going well points"),
                 ("a point's source changed",
                  (">Slack<", ">Other feedback<"), "Going well points"),
                 ("a reference changed", ("<td>Other feedback</td><td>–</td>", "<td>Other feedback</td><td>Q2</td>"),
                  "Going well points"),
                 ("an evidence's day changed", (">Journal 20 Aug</a>",
                  ">Journal 21 Aug</a>"), "To improve points"),
                 ("a summary changed", ("Jane explains outages",
                  "Jane fixes outages"), "Going well summary"),
                 ("a context point's text changed", ("Moved to the payments team",
                  "Moved to the billing team"), "Context points"),
                 ("a context point's source changed", ('<td>Slack</td><td><a href="https://acme.slack.com/archives/C2',
                  '<td>Other feedback</td><td><a href="https://acme.slack.com/archives/C2'), "Context points"),
                 ("a page's reference changed",
                  (">Page Jane</a>", ">Page Sam</a>"), "Context points"),
                 ("a context point dropped", ('<tr valign="top"><td>Is preparing a promotion case with the manager'
                                              '</td><td>Other feedback</td><td>–</td><td>C1</td></tr>\n', ""), "Context points"),
                 ("the context summary changed", ("Jane moved to the payments team",
                  "Jane moved to the data team"), "Context summary"),
                 ("an other feedback point's source changed",
                  ("Could raise risks earlier in planning</td><td>Other feedback</td>",
                   "Could raise risks earlier in planning</td><td>Slack</td>"), "To improve points"),
                 ("a step change label changed", ("<td>Held</td>",
                  "<td>Worsened</td>"), "step change rows"),
                 ("a step change's previous point changed", ("<td>To improve: Could lead",
                                                             "<td>Going well: Could lead"), "step change rows"),
                 ("a step change's evidence changed", ("<td>Not raised again in the period</td>",
                                                       "<td>Raised again</td>"), "step change rows"),
                 ("a step change's cited source changed", ("(Other feedback)", "(Slack)"),
                  "step change rows"),
                 ("a step change's cited point dropped", ("<br>Could raise risks earlier in planning "
                                                          "(Other feedback)", ""), "step change rows"),
                 ("a step change row dropped", ("<tr valign=\"top\"><td>–</td>", "<tr valign=\"top\"><td>?</td>"),
                  "step change rows"),
                 ("the step change's count changed", ("Details (4 changes)", "Details (3 changes)"),
                  "step change rows"),
                 ("the step change summary changed", ("Jane no longer needs support", "Jane needs support"),
                  "step change summary"),
                 ("no Step change section", ("## Step change",
                  "## Shift"), "then its Step change one"),
                 ("a value's span changed", ('rowspan="2">Teamwork',
                  'rowspan="1">Teamwork'), "Going well points"),
                 ("a count changed", ('">1</a> (1 Task)',
                  '">2</a> (1 Task)'), "cell for created"),
                 ("a breakdown changed", ("(1 Task)", "(1 Bug)"), "cell for created"),
                 ("an average changed", ("avg=3", "avg=4"),
                  "cell for resolved_points"),
                 ("a focus count changed", ("Billing (1)",
                  "Billing (2)"), "Jira main focus"),
                 ("a GitHub count changed", ('">1</a> (in 1 repository)',
                  '">2</a> (in 1 repository)'), "GitHub cell for opened"),
                 ("a median changed", ("<td>150 (median",
                  "<td>151 (median"), "GitHub cell for merged_lines"),
                 ("a repository's count changed", ("acme/billing</a> (1)",
                  "acme/billing</a> (2)"), "GitHub main focus"),
                 ("a repository's code changed",
                  ("<li>A <a", "<li>B <a"), "GitHub main focus"),
                 ("no GitHub section", ("## GitHub", "## Code"), "its GitHub one"),
                 ("no Jira section", ("## Jira", "## Tickets"), "its Jira one"),
                 ("a chart's link broken", ('<td><a href="_charts', '<td><a href="charts'),
                  "a row of three figures and one of their charts"),
                 ("a cell's chart replaced", (
                     '_charts/github_opened_over_time.svg" target="_blank"><img src="_charts/github_opened_over_time.svg"',
                     '_charts/other.svg" target="_blank"><img src="_charts/other.svg"'),
                  "GitHub cell for opened")]
        for name, change, expected in cases:
            with self.subTest(name):
                text = change(report) if callable(change) else report.replace(
                    change[0], change[1], 1) if change else report
                problems = " ".join(
                    check_report.report_problems(text, DATA, SUMMARIES, VALUE_NAMES, REPORT_FOLDER, OBSERVATIONS_CONTENT, STEP_CHANGE_CONTENT))
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
                    make_report.render(PERSON, data, REPORT_FOLDER, OBSERVATIONS_CONTENT, STEP_CHANGE_CONTENT), data, SUMMARIES, VALUE_NAMES, REPORT_FOLDER, OBSERVATIONS_CONTENT, STEP_CHANGE_CONTENT)))

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
            make_report.render(PERSON, data, REPORT_FOLDER, OBSERVATIONS_CONTENT, STEP_CHANGE_CONTENT), data, summaries, VALUE_NAMES, REPORT_FOLDER, OBSERVATIONS_CONTENT, STEP_CHANGE_CONTENT), [])

    def test_step_change(self):
        # name: (data.json's previous feedback, step_change_content.json,
        # a change to the report, expected in the problems, or None for
        # none): with no previous feedback the step change says N/A alone,
        # unmarked, else it is marked, a previous context point that changed
        # shown.
        def change(old, new):
            return lambda report: report.replace(old, new, 1)
        empty = {"going_well": [], "to_improve": [], "context": []}
        no_previous = {**SUMMARIES, "previous": empty}
        step = STEP_CHANGE_CONTENT
        two_rows = {**step, "rows": [{"previous_point": "P-I1", "change": "improved", "evidence": ["G2"]},
                                     {"previous_point": "P-I1",
                                         "change": "still_to_improve", "evidence": ["I1"]},
                                     *step["rows"][:3]]}
        na = "N/A: no previous feedback to compare with"
        cases = [("no previous feedback", None, None, no_previous, lambda report: report, None),
                 ("no previous feedback, a summary", None, None, no_previous,
                  change(na, "Jane improved."), f"must say {na} alone"),
                 ("no previous feedback, marked", None, None, no_previous,
                  change("## Step change", f"## {common.ai_marked('Step change')}"), "must say N/A"),
                 ("unmarked", DATA["previous"], step, SUMMARIES,
                  change(f"## {common.ai_marked('Step change')}", "## Step change"), "step change summary"),
                 ("the subtitle missing", DATA["previous"], step, SUMMARIES,
                  change("*How the period compares", "How the period compares"), "step change must start with"),
                 ("the subtitle naming another baseline", DATA["previous"], step, SUMMARIES,
                  change("with the previous feedback:",
                         "with the previous review:"),
                  "subtitle, *How the period compares with the previous feedback:"),
                 ("two rows for one previous point, an aspect each", DATA["previous"], two_rows, SUMMARIES,
                  lambda report: report, None),
                 ("a row of one previous point dropped", DATA["previous"], two_rows, SUMMARIES,
                  change("<td>Still to improve</td>", "<td>Improved</td>"), "step change rows"),
                 ("a previous context point changed", CONTEXT_DATA["previous"], CONTEXT_STEP_CHANGE,
                  CONTEXT_SUMMARIES, lambda report: report, None)]
        for name, previous, step_change, summaries, edit, expected in cases:
            with self.subTest(name):
                data = {**DATA, "previous": previous}
                report = make_report.render(
                    PERSON, data, REPORT_FOLDER, OBSERVATIONS_CONTENT, step_change)
                problems = " ".join(check_report.report_problems(
                    edit(report), data, summaries, VALUE_NAMES, REPORT_FOLDER, OBSERVATIONS_CONTENT, step_change))
                if expected is None:
                    self.assertEqual(problems, "")
                else:
                    self.assertIn(expected, problems)

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
                    PERSON, data, REPORT_FOLDER, OBSERVATIONS_CONTENT, STEP_CHANGE_CONTENT)
                self.assertIn(entry, report)
                self.assertEqual(check_report.report_problems(
                    report, data, SUMMARIES, VALUE_NAMES, REPORT_FOLDER, OBSERVATIONS_CONTENT, STEP_CHANGE_CONTENT), [])
                self.assertIn("main focus", " ".join(check_report.report_problems(
                    report.replace(entry, entry.replace("(", "(7"), 1), data, SUMMARIES, VALUE_NAMES, REPORT_FOLDER, OBSERVATIONS_CONTENT, STEP_CHANGE_CONTENT)))


if __name__ == "__main__":
    unittest.main()
