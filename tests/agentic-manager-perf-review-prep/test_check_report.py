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
from prep_fixture import CONTENT, STEP_CHANGE, VIEW_CHECK, CONTEXT_STEP_CHANGE, CONTEXT_DATA, CONTEXT_SUMMARIES, DATA, DATA_BY_PROJECT, DATA_NO_EPIC_FIRST, PERSON, REPORT_FOLDER, REVIEW_IN_PERIOD, SUMMARIES, VALUE_NAMES  # noqa: E402


class CheckReportTest(unittest.TestCase):
    def test_report_problems(self):
        # name: (a change to the report's text, expected in the
        # problems, or None for none): each Jira figure is read back from the
        # table and worked out again from the items.
        report = make_report.render(
            PERSON, DATA, REPORT_FOLDER, CONTENT, STEP_CHANGE, VIEW_CHECK)
        cases = [("as written", None, None),
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
                 ("no Observations subtitle", ("*What the period's feedback, the manager's notes and Slack show, by "
                                               "company value.*\n\n", ""), "Observations must start with its subtitle"),
                 ("the Observations subtitle changed", ("Slack show, by company value", "Slack show"),
                  "Observations must start with its subtitle"),
                 ("a point count changed", ("Details (3 points)",
                  "Details (4 points)"), "Going well points"),
                 ("a point's text changed", ("Presented the migration",
                  "Presented the plan"), "Going well points"),
                 ("a point's source changed",
                  (">Slack<", ">Feedback<"), "Going well points"),
                 ("a period changed", (">Q3 2026<", ">Q2 2026<"), "Going well points"),
                 ("an evidence's day changed", (">Journal 20 Aug</a>",
                  ">Journal 21 Aug</a>"), "To improve points"),
                 ("a summary changed", ("Jane explains outages",
                  "Jane fixes outages"), "Going well summary"),
                 ("a context point's text changed", ("Moved to the payments team",
                  "Moved to the billing team"), "Context points"),
                 ("a context point's source changed", ('<td>Slack</td><td><a href="https://acme.slack.com/archives/C2',
                  '<td>Feedback</td><td><a href="https://acme.slack.com/archives/C2'), "Context points"),
                 ("a page's reference changed",
                  (">Page Jane</a>", ">Page Sam</a>"), "Context points"),
                 ("a context point dropped", ('<tr valign="top"><td>Is preparing a promotion case with the manager'
                                              '</td><td>Feedback</td><td>Q3 2026</td></tr>\n', ""), "Context points"),
                 ("the context summary changed", ("Jane moved to the payments team",
                  "Jane moved to the data team"), "Context summary"),
                 ("a review's period changed", ("<td>Q3 Check-in 2026</td>", "<td>Q2 Check-in 2026</td>"),
                  "To improve points"),
                 ("a review's source changed", ("<td>Review</td><td>Q3", "<td>Feedback</td><td>Q3"),
                  "To improve points"),
                 ("a step change label changed", ("<td>Held</td>",
                  "<td>Worsened</td>"), "step change rows"),
                 ("a step change's review point changed", ("<td>To improve: Could lead",
                                                           "<td>Going well: Could lead"), "step change rows"),
                 ("a step change's evidence changed", ("<td>Not raised again in the period</td>",
                                                       "<td>Raised again</td>"), "step change rows"),
                 ("a step change's cited source changed", ("(Feedback: Q3 2026)", "(Slack: Q3 2026)"),
                  "step change rows"),
                 ("a step change's cited point dropped", ("<br>Could raise risks earlier in planning "
                                                          "(Review: Q3 Check-in 2026)", ""), "step change rows"),
                 ("a step change row dropped", ("<tr valign=\"top\"><td>–</td>", "<tr valign=\"top\"><td>?</td>"),
                  "step change rows"),
                 ("the step change's count changed", ("Details (4 changes)", "Details (3 changes)"),
                  "step change rows"),
                 ("the step change summary changed", ("Jane no longer needs support", "Jane needs support"),
                  "step change summary"),
                 ("no Step change section", ("## Step change",
                  "## Shift"), "then its Step change one"),
                 ("a view check label changed", ("<td>Confirmed</td>", "<td>Contradicted</td>"),
                  "manager view check rows"),
                 ("the not in view label changed", ("<td>Not in the manager's view</td>", "<td>Not in your view</td>"),
                  "manager view check rows"),
                 ("a view check's view point changed", ("<td>Context: Came back", "<td>Going well: Came back"),
                  "manager view check rows"),
                 ("a view check's no support changed", ("<td>No support in the period</td>", "<td>Some support</td>"),
                  "manager view check rows"),
                 ("a view check's cited point dropped", ("<br>Posted the billing rollout plan in a cross-team channel "
                                                         "(Slack: <a href=\"https://acme.slack.com/archives/C2/p2\">"
                                                         "Slack 20 Aug</a>)", ""), "manager view check rows"),
                 ("the view check's count changed", ("Details (4 checks)", "Details (3 checks)"),
                  "manager view check rows"),
                 ("the view check summary changed", ("The manager's view that Jane has led",
                                                     "The manager's view that Jane led"), "manager view check summary"),
                 ("no Manager view check section", (f"## {common.ai_marked('Manager view check')}", "## View"),
                  "then its Step change one, its Manager view check one"),
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
                text = report.replace(
                    change[0], change[1], 1) if change else report
                problems = " ".join(
                    check_report.report_problems(text, DATA, SUMMARIES, VALUE_NAMES, REPORT_FOLDER, CONTENT, STEP_CHANGE, VIEW_CHECK))
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
                    make_report.render(PERSON, data, REPORT_FOLDER, CONTENT, STEP_CHANGE, VIEW_CHECK), data, SUMMARIES, VALUE_NAMES, REPORT_FOLDER, CONTENT, STEP_CHANGE, VIEW_CHECK)))

    def test_observations_order(self):
        # Two points swapped, the older first, or a value moved under
        # another: the check orders them again from the summaries.
        report = make_report.render(
            PERSON, DATA, REPORT_FOLDER, CONTENT, STEP_CHANGE, VIEW_CHECK)
        slack, notes = (point["point"]
                        for point in DATA["observations"]["going_well"][0]["points"])
        swapped = report.replace(slack, "\0").replace(
            notes, slack).replace("\0", notes)
        self.assertIn("Going well points", " ".join(check_report.report_problems(
            swapped, DATA, SUMMARIES, VALUE_NAMES, REPORT_FOLDER, CONTENT, STEP_CHANGE, VIEW_CHECK)))
        self.assertIn("Going well points", " ".join(check_report.report_problems(
            report.replace(">Teamwork<",
                           ">Ownership<", 1), DATA,
            SUMMARIES, VALUE_NAMES, REPORT_FOLDER, CONTENT, STEP_CHANGE, VIEW_CHECK)))

    def test_context_order(self):
        # Two context points swapped, the undated page's after a dated one:
        # the check orders them again from the summaries, undated first.
        report = make_report.render(
            PERSON, DATA, REPORT_FOLDER, CONTENT, STEP_CHANGE, VIEW_CHECK)
        page, piece = (point["point"]
                       for point in DATA["observations"]["context"][:2])
        swapped = report.replace(page, "\0").replace(
            piece, page).replace("\0", piece)
        self.assertIn("Context points", " ".join(check_report.report_problems(
            swapped, DATA, SUMMARIES, VALUE_NAMES, REPORT_FOLDER, CONTENT, STEP_CHANGE, VIEW_CHECK)))

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
            **DATA, "observations": build_data.observations(summaries, [REVIEW_IN_PERIOD], VALUE_NAMES)}
        self.assertEqual(check_report.report_problems(
            make_report.render(PERSON, data, REPORT_FOLDER, CONTENT, STEP_CHANGE, VIEW_CHECK), data, summaries, VALUE_NAMES, REPORT_FOLDER, CONTENT, STEP_CHANGE, VIEW_CHECK), [])

    def test_step_change(self):
        # name: (data.json's previous reviews, step_change.json,
        # a change to the report, expected in the problems, or None for
        # none): with no previous review the step change says N/A alone,
        # unmarked, else it is marked, a review context point that changed
        # shown.
        def change(old, new):
            return lambda report: report.replace(old, new, 1)
        no_review = {**SUMMARIES, "reviews": {"pieces": [REVIEW_IN_PERIOD]}}
        step = STEP_CHANGE
        # The latest previous review with no period, then with no date
        # either, as data.json and the summaries give it, the checker naming
        # it again from the summaries.

        def unnamed(**fields):
            pieces = [{**piece, **fields} if piece["period"] == DATA["reviews"]["latest"]["period"] else piece
                      for piece in SUMMARIES["reviews"]["pieces"]]
            return ({**DATA["reviews"], "latest": {**DATA["reviews"]["latest"], **fields}},
                    {**SUMMARIES, "reviews": {"pieces": pieces}})
        date_only, date_only_summaries = unnamed(period=None)
        neither, neither_summaries = unnamed(period=None, date=None)
        cases = [("no previous review", None, None, no_review, lambda report: report, None),
                 ("no previous review, a summary", None, None, no_review,
                  change(
                      "N/A: no review before the period to compare with", "Jane improved."),
                  "must say N/A: no review before the period to compare with alone"),
                 ("no previous review, marked", None, None, no_review,
                  change("## Step change", f"## {common.ai_marked('Step change')}"), "must say N/A"),
                 ("unmarked", DATA["reviews"], step, SUMMARIES,
                  change(f"## {common.ai_marked('Step change')}", "## Step change"), "step change summary"),
                 ("the subtitle missing", DATA["reviews"], step, SUMMARIES,
                  change("*How the period compares", "How the period compares"), "step change must start with"),
                 ("the subtitle naming another review", DATA["reviews"], step, SUMMARIES,
                  change("review, Mid Year Review 2026:",
                         "review, Annual Review 2025:"),
                  "subtitle, *How the period compares with the latest previous review, Mid Year Review 2026:"),
                 ("a review of a date only", date_only, step,
                  date_only_summaries, lambda report: report, None),
                 ("a review of a date only, named by its period", date_only, step, date_only_summaries,
                  change("review, of 30/06/2026:", "review, Mid Year Review 2026:"), "review, of 30/06/2026:"),
                 ("a review of neither", neither, step,
                  neither_summaries, lambda report: report, None),
                 ("a review of neither, named by a date", neither, step, neither_summaries,
                  change("previous review:", "previous review, of 30/06/2026:"), "step change must start with"),
                 ("a review context point changed", CONTEXT_DATA["reviews"], CONTEXT_STEP_CHANGE,
                  CONTEXT_SUMMARIES, lambda report: report, None)]
        for name, reviews, step_change, summaries, edit, expected in cases:
            with self.subTest(name):
                data = {**DATA, "reviews": reviews}
                report = make_report.render(
                    PERSON, data, REPORT_FOLDER, CONTENT, step_change, VIEW_CHECK)
                problems = " ".join(check_report.report_problems(
                    edit(report), data, summaries, VALUE_NAMES, REPORT_FOLDER, CONTENT, step_change, VIEW_CHECK))
                if expected is None:
                    self.assertEqual(problems, "")
                else:
                    self.assertIn(expected, problems)
        # A step change step_change.json can't have, such as one citing a point
        # that isn't there, is refused before any row is read.
        bad = {**step, "rows": [{**step["rows"][0],
                                 "evidence": ["G9"]}, *step["rows"][1:]]}
        report = make_report.render(
            PERSON, DATA, REPORT_FOLDER, CONTENT, STEP_CHANGE, VIEW_CHECK)
        self.assertIn("evidence names G9", " ".join(check_report.report_problems(
            report, DATA, SUMMARIES, VALUE_NAMES, REPORT_FOLDER, CONTENT, bad, VIEW_CHECK)))

    def test_view_check(self):
        # name: (the manager's view, data.json's and its summary, the view
        # check, a change to the report, expected in the problems, or None for
        # none): it is marked as the agent's, under its subtitle.
        def change(old, new):
            return lambda report: report.replace(old, new, 1)
        heading = "## Manager view check"
        cases = [("as written", DATA["view"], SUMMARIES["orientation"], VIEW_CHECK, lambda report: report, None),
                 ("unmarked", DATA["view"], SUMMARIES["orientation"], VIEW_CHECK,
                  change(f"## {common.ai_marked('Manager view check')}", heading), "manager view check summary"),
                 ("the subtitle changed", DATA["view"], SUMMARIES["orientation"], VIEW_CHECK,
                  change("what the view leaves out.*", "what it leaves out.*"), "manager view check must start with")]
        for name, view, orientation, view_check, edit, expected in cases:
            with self.subTest(name):
                data = {**DATA, "view": view}
                report = make_report.render(
                    PERSON, data, REPORT_FOLDER, CONTENT, STEP_CHANGE, view_check)
                problems = " ".join(check_report.report_problems(
                    edit(report), data, {
                        **SUMMARIES, "orientation": orientation}, VALUE_NAMES, REPORT_FOLDER,
                    CONTENT, STEP_CHANGE, view_check))
                if expected is None:
                    self.assertEqual(problems, "")
                else:
                    self.assertIn(expected, problems)
        # A view check view_check.json can't have, such as one citing a point
        # that isn't there, is refused before any row is read.
        bad = {**VIEW_CHECK, "rows": [{**VIEW_CHECK["rows"]
                                       [0], "evidence": ["G9"]}, *VIEW_CHECK["rows"][1:]]}
        report = make_report.render(
            PERSON, DATA, REPORT_FOLDER, CONTENT, STEP_CHANGE, VIEW_CHECK)
        self.assertIn("evidence names G9", " ".join(check_report.report_problems(
            report, DATA, SUMMARIES, VALUE_NAMES, REPORT_FOLDER, CONTENT, STEP_CHANGE, bad)))

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
                    PERSON, data, REPORT_FOLDER, CONTENT, STEP_CHANGE, VIEW_CHECK)
                self.assertIn(entry, report)
                self.assertEqual(check_report.report_problems(
                    report, data, SUMMARIES, VALUE_NAMES, REPORT_FOLDER, CONTENT, STEP_CHANGE, VIEW_CHECK), [])
                self.assertIn("main focus", " ".join(check_report.report_problems(
                    report.replace(entry, entry.replace("(", "(7"), 1), data, SUMMARIES, VALUE_NAMES, REPORT_FOLDER, CONTENT, STEP_CHANGE, VIEW_CHECK)))


if __name__ == "__main__":
    unittest.main()
