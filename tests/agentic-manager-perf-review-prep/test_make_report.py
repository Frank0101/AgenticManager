"""Unit tests for skills/agentic-manager-perf-review-prep/scripts/make_report.py.
Run with: python3 tests/run.py agentic-manager-perf-review-prep
"""

import html
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
from prep_fixture import (CONTENT, STEP_CHANGE, VIEW_CHECK, CONTEXT_STEP_CHANGE, CONTEXT_DATA, DATA, DATA_NO_EPIC_FIRST, PERSON,  # noqa: E402
                          REPORT_FOLDER, SUMMARIES, VALUE_NAMES)


class MakeReportTest(unittest.TestCase):
    def test_render(self):
        # The fixture's Jira figures, each linked to its search, with its
        # breakdown and chart, as the final check reads them back.
        report = make_report.render(
            PERSON, DATA, REPORT_FOLDER, CONTENT, STEP_CHANGE, VIEW_CHECK)
        self.assertTrue(report.startswith(
            "# Jane Doe: performance review prep\n\nPeriod: 10/08/2026 to 10/11/2026"))
        self.assertIn(
            f"<a href=\"{html.escape(DATA['jira']['resolved_points_search_url'])}\">3</a> (avg=3)", report)
        # The Notion pages, the most recent week first, each week named once
        # beside its pages, in small type.
        self.assertIn(
            f'<table width="100%" style="{common.SMALL_TYPE}">', report)
        self.assertIn('<tr valign="top"><td rowspan="1">10–16 Aug</td><td>'
                      '<a href="https://www.notion.so/billing-plan">Billing plan</a></td><td>'
                      'Engineering</td></tr>', report)
        self.assertEqual(check_report.report_problems(
            report, DATA, SUMMARIES, VALUE_NAMES, REPORT_FOLDER, CONTENT, STEP_CHANGE, VIEW_CHECK), [])

    def test_observations_section(self):
        # Each part's heading, marked as the agent's, its summary, then its
        # table folded with how many points it holds, a divider apart from the
        # next part: each value named once beside its points, the value with
        # the most first, each point with the second value it names, its
        # source and references, a piece's period or each evidence's source
        # and day, linked, the most recent first; a part with none, its
        # heading alone.
        report = make_report.render(
            PERSON, DATA, REPORT_FOLDER, CONTENT, STEP_CHANGE, VIEW_CHECK)
        self.assertIn(
            f'{common.ai_marked("<b>Going well</b>")}\n\nJane explains outages', report)
        self.assertIn('<details><summary>Details (3 points)</summary>', report)
        self.assertIn('</details>\n\n---\n\n<b>To improve</b>', report)
        self.assertIn('<tr valign="top"><td rowspan="2">Teamwork</td><td></td><td>'
                      "Explained the outage&#x27;s cause in the incident channel, and colleagues thanked them"
                      '</td><td>Slack</td><td><a href="https://'
                      'acme.slack.com/archives/C1/p1">Slack 3 Sep</a></td></tr>', report)
        self.assertIn('<td>Feedback</td><td>Q3 2026'
                      '</td></tr>', report)
        self.assertIn('<a href="../../../journals/2026_10_01.md">Journal 1 Oct</a>, '
                      '<a href="../../../journals/2026_08_20.md">Journal 20 Aug</a>', report)
        # Context last, not grouped: its point, source and references, a
        # page's undated evidence named by its title.
        self.assertIn('</details>\n\n---\n\n<b>Context</b>', report)
        self.assertIn(
            f'<tr valign="top"><th width="70%">{common.ai_marked("Point")}</th><th width="10%">Source</th>'
            '<th width="20%">References</th></tr>\n<tr valign="top"><td>Moved to the payments team in the summer</td>'
            '<td>Manager\'s notes</td><td><a href="../../../pages/Jane.md">Page Jane</a></td></tr>\n'
            '<tr valign="top"><td>Is preparing a promotion case with the manager</td><td>Feedback</td>'
            '<td>Q3 2026</td></tr>', report)
        for part, heading in (("to_improve", "To improve"), ("context", "Context")):
            with self.subTest(part):
                empty = {**DATA, "observations": {**
                                                  DATA["observations"], part: []}, "reviews": None}
                self.assertIn(f"<b>{heading}</b>\n\n" + ("---" if part != "context" else "## Step change"),
                              make_report.render(PERSON, empty, REPORT_FOLDER, CONTENT, None, {**VIEW_CHECK, "rows": []}))
        # The Observations first, under its subtitle, the script's, unmarked,
        # its Point column marked as the agent's.
        self.assertIn(
            "Period: 10/08/2026 to 10/11/2026\n\n## Observations\n\n*What the period's feedback, the manager's "
            f"notes and Slack show, by company value.*\n\n{common.ai_marked('<b>Going well</b>')}", report)
        self.assertIn(
            f'<th width="10%">{common.ai_marked("Value")}</th><th width="10%">{common.ai_marked("Also")}</th>'
            f'<th width="50%">{common.ai_marked("Point")}</th>', report)
        # A point naming two values sits under the first, the second next to
        # the value's column.
        self.assertIn(
            "<td>Ownership</td><td>Presented the migration to the wider team</td>", report)

    def test_step_change_section(self):
        # A section of its own after the Observations: its heading, marked as
        # the agent's, its subtitle, the script's, unmarked, naming the latest
        # previous review, its summary, then its table folded with how many rows it
        # holds, in small type, its Change column marked: by change, in
        # STEP_CHANGES' order, then by the review point's order, one with
        # none last; each review point after its part, or –; each cited
        # point with its source and references, one to a line, an improved
        # one citing none not raised again.
        report = make_report.render(
            PERSON, DATA, REPORT_FOLDER, CONTENT, STEP_CHANGE, VIEW_CHECK)
        self.assertIn(f'</details>\n\n## {common.ai_marked("Step change")}\n\n*How the period compares with the '
                      'latest previous review, Mid Year Review 2026: what improved, persisted, worsened or held, and '
                      'how the context changed.*\n\nJane no longer needs support', report)
        # The review named by its period, else by its date, else not at all.
        latest = DATA["reviews"]["latest"]
        for name, review, expected in (("a period", latest, ", Mid Year Review 2026:"),
                                       ("a date only", {
                                        **latest, "period": None}, ", of 30/06/2026:"),
                                       ("neither", {**latest, "period": None, "date": None}, ":")):
            with self.subTest(name):
                data = {**DATA, "reviews": {**
                                            DATA["reviews"], "latest": review}}
                self.assertIn(f"*How the period compares with the latest previous review{expected} what improved",
                              make_report.render(PERSON, data, REPORT_FOLDER, CONTENT, STEP_CHANGE, VIEW_CHECK))
        self.assertIn(
            "<details><summary>Details (4 changes)</summary>", report)
        self.assertIn(f'<th width="35%">Review point</th><th width="15%">{common.ai_marked("Change")}</th>'
                      '<th width="50%">Evidence</th>', report)
        step = report.split("## Step change", 1)[1].split(
            "## Manager view check", 1)[0]
        rows = [line for line in step.split("\n") if line.startswith('<tr valign="top"><td>')
                and ("<td>To improve: " in line or "<td>Going well: " in line or "<td>–</td>" in line)]
        self.assertEqual(rows, [
            '<tr valign="top"><td>To improve: Could lead a design review alone</td><td>Improved</td>'
            '<td>Not raised again in the period</td></tr>',
            '<tr valign="top"><td>To improve: Flagged delays only when asked</td><td>Still to improve</td>'
            '<td>Didn&#x27;t flag delays until asked, many times (Manager\'s notes: '
            '<a href="../../../journals/2026_10_01.md">Journal 1 Oct</a>, '
            '<a href="../../../journals/2026_08_20.md">Journal 20 Aug</a>)<br>'
            'Could raise risks earlier in planning (Review: Q3 Check-in 2026)</td></tr>',
            '<tr valign="top"><td>Going well: Delivered the billing migration on time</td><td>Held</td>'
            '<td>Agreed to own the billing migration and has kept to its plan (Feedback: Q3 2026)</td></tr>',
            '<tr valign="top"><td>–</td><td>New context</td><td>Moved to the payments team in the summer '
            '(Manager\'s notes: <a href="../../../pages/Jane.md">Page Jane</a>)</td></tr>'])
        # A context point of the review that changed comes before a new one.
        report = make_report.render(
            PERSON, CONTEXT_DATA, REPORT_FOLDER, CONTENT, CONTEXT_STEP_CHANGE, VIEW_CHECK)
        self.assertIn('<td>Context: Had no promotion case planned yet</td><td>Context changed</td><td>Is preparing a '
                      'promotion case with the manager (Feedback: Q3 2026)</td></tr>\n<tr valign="top"><td>–</td>'
                      '<td>New context</td>', report)
        # With no row, the summary alone; with no previous review, N/A and
        # why, unmarked, and nothing else, not even the subtitle.
        cases = [("no row", DATA, {**STEP_CHANGE, "rows": []},
                  'how the context changed.*\n\nJane no longer needs support to lead a design '
                  "review, but still flags delays only when asked, as both previous reviews said.\n\n"
                  f"## {common.ai_marked('Manager view check')}"),
                 ("no previous review", {**DATA, "reviews": None}, None,
                  f"</details>\n\n## Step change\n\nN/A: no review before the period to compare with\n\n"
                  f"## {common.ai_marked('Manager view check')}")]
        for name, data, step_change, expected in cases:
            with self.subTest(name):
                self.assertIn(expected, make_report.render(
                    PERSON, data, REPORT_FOLDER, CONTENT, step_change, VIEW_CHECK))

    def test_view_check_section(self):
        # A section of its own after the step change, in the same form: its
        # heading, marked as the agent's, its subtitle, its summary, then its table folded
        # with how many rows it holds, its Check column marked: by check, in
        # VIEW_CHECKS' order, then by the view point's order, one with none
        # last; each view point after its part, or –; each cited point with
        # its source and references, one to a line, one citing none with no
        # support in the period.
        report = make_report.render(
            PERSON, DATA, REPORT_FOLDER, CONTENT, STEP_CHANGE, VIEW_CHECK)
        self.assertIn(f'</details>\n\n## {common.ai_marked("Manager view check")}\n\n*How the manager\'s view, '
                      'given at the start of the prep, holds against the period\'s evidence: what it confirms, what '
                      'has little support or is contradicted, and what the view leaves out.*\n\nThe manager\'s view '
                      'that Jane has led', report)
        view = report.split(
            "## " + common.ai_marked("Manager view check"), 1)[1].split("## GitHub", 1)[0]
        self.assertIn("<details><summary>Details (4 checks)</summary>", view)
        self.assertIn(f'<th width="35%">View point</th><th width="15%">{common.ai_marked("Check")}</th>'
                      '<th width="50%">Evidence</th>', view)
        migration = ('Presented the migration to the wider team (Manager\'s notes: '
                     '<a href="../../../journals/2026_09_02.md">Journal 2 Sep</a>)')
        self.assertEqual([line for line in view.split("\n") if line.startswith('<tr valign="top"><td>')], [
            '<tr valign="top"><td>Going well: Has led the billing migration well since May</td><td>Confirmed</td>'
            f'<td>Agreed to own the billing migration and has kept to its plan (Feedback: Q3 2026)<br>{migration}'
            '</td></tr>',
            '<tr valign="top"><td>Context: Came back from a long leave in May</td><td>Little support</td>'
            '<td>No support in the period</td></tr>',
            '<tr valign="top"><td>To improve: Could share progress with the wider team more often</td>'
            f'<td>Contradicted</td><td>{migration}<br>Posted the billing rollout plan in a cross-team channel '
            '(Slack: <a href="https://acme.slack.com/archives/C2/p2">Slack 20 Aug</a>)</td></tr>',
            '<tr valign="top"><td>–</td><td>Not in the manager\'s view</td><td>Didn&#x27;t flag delays until '
            'asked, many times (Manager\'s notes: <a href="../../../journals/2026_10_01.md">Journal 1 Oct</a>, '
            '<a href="../../../journals/2026_08_20.md">Journal 20 Aug</a>)<br>'
            'Could raise risks earlier in planning (Review: Q3 Check-in 2026)</td></tr>'])

    def test_focus_section(self):
        # Every entry of the main focus, in its order, an epic linked with its
        # title and count, the issues with no epic linked to their search, as
        # the final check reads them back.
        report = make_report.render(
            PERSON, DATA_NO_EPIC_FIRST, REPORT_FOLDER, CONTENT, STEP_CHANGE, VIEW_CHECK)
        jira = DATA_NO_EPIC_FIRST["jira"]
        self.assertIn(f'<ol><li><a href="{html.escape(jira["no_epic_search_url"])}">no epic</a> (3)</li>'
                      f'<li><a href="{html.escape(jira["epic_search_urls"]["PROJ-1"])}">PROJ-1</a> Billing (2)</li>'
                      '</ol>', report)
        self.assertEqual(check_report.report_problems(
            report, DATA_NO_EPIC_FIRST, SUMMARIES, VALUE_NAMES, REPORT_FOLDER, CONTENT, STEP_CHANGE, VIEW_CHECK), [])

    def test_notion_pages_by_calendar_week(self):
        # Pages found by a week's search split in two share that week's row.
        page = DATA["notion"]["created"][0]
        pages = [{**page, "between": ["2026-08-10", "2026-08-12"]},
                 {**page, "url": "https://www.notion.so/billing-risks", "title": "Billing risks",
                  "between": ["2026-08-13", "2026-08-16"]}]
        data = {**DATA, "notion": {**DATA["notion"],
                                   "created": pages, "counts": {"created": 2}}}
        report = make_report.render(
            PERSON, data, REPORT_FOLDER, CONTENT, STEP_CHANGE, VIEW_CHECK)
        self.assertEqual(report.count(
            '<td rowspan="2">10–16 Aug</td>'), 1)
        self.assertEqual(check_report.report_problems(
            report, data, SUMMARIES, VALUE_NAMES, REPORT_FOLDER, CONTENT, STEP_CHANGE, VIEW_CHECK), [])


if __name__ == "__main__":
    unittest.main()
