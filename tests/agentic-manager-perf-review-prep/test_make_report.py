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
import build_data  # noqa: E402
import check_report  # noqa: E402
import common  # noqa: E402
import make_report  # noqa: E402
sys.path.insert(0, TEST_DIR)
from prep_fixture import (EARLIER_WORK_CONTENT, POINT_WORK_IMPACT, WORK_IMPACT_CONTENT, OBSERVATIONS_CONTENT, STEP_CHANGE_CONTENT, CONTEXT_STEP_CHANGE, CONTEXT_DATA, DATA, DATA_NO_EPIC_FIRST, PERSON,  # noqa: E402
                          REPORT_FOLDER, SUMMARIES, VALUE_NAMES)


class MakeReportTest(unittest.TestCase):
    def test_render(self):
        # The fixture's Jira figures, each linked to its search, with its
        # breakdown and chart, as the final check reads them back.
        report = make_report.render(
            PERSON, DATA, REPORT_FOLDER, OBSERVATIONS_CONTENT, STEP_CHANGE_CONTENT, WORK_IMPACT_CONTENT)
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
            report, DATA, SUMMARIES, VALUE_NAMES, REPORT_FOLDER, OBSERVATIONS_CONTENT, STEP_CHANGE_CONTENT, WORK_IMPACT_CONTENT), [])

    def test_work_impact_section(self):
        # First, after the period: its heading marked as the agent's, its
        # subtitle, each initiative's title over its impact line and paragraph, in the order
        # recorded, then, folded, each one's evidence in the order it cites
        # it, as the observations' tables: an item's title, kind and link by
        # its key, a point's text, source, references and id.
        report = make_report.render(
            PERSON, DATA, REPORT_FOLDER, OBSERVATIONS_CONTENT, STEP_CHANGE_CONTENT, WORK_IMPACT_CONTENT)
        self.assertIn(f"Period: 10/08/2026 to 10/11/2026\n\n## {common.ai_marked('Work and impact')}\n\n"
                      f"{common.WORK_IMPACT_SUBTITLE}\n\n### In the period\n\n<b>Billing migration</b>\n\n"
                      "*The payments team moved off the old billing system.*\n\nJane led the billing migration",
                      report)
        self.assertLess(report.index("<b>Billing migration</b>"),
                        report.index("<b>Old billing retirement</b>"))
        # Each initiative's evidence folded under its paragraph.
        self.assertIn(
            "relied on.\n\n<details><summary>Details (5 items)</summary>", report)
        self.assertIn('<details><summary>Details (1 item)</summary>', report)
        self.assertIn(
            '<tr valign="top"><td>Billing</td><td>Jira epic</td>'
            '<td><a href="https://acme.atlassian.net/browse/PROJ-1">PROJ-1</a></td><td>–</td></tr>\n'
            '<tr valign="top"><td>Migrate billing</td><td>GitHub</td>'
            '<td><a href="https://github.com/acme/billing/pull/1">acme/billing#1</a></td><td>–</td></tr>\n'
            '<tr valign="top"><td>Billing plan</td><td>Notion</td>'
            '<td><a href="https://www.notion.so/billing-plan">Notion page</a></td><td>–</td></tr>\n'
            '<tr valign="top"><td>Agreed to own the billing migration and has kept to its plan</td>'
            '<td>Other feedback</td><td>–</td><td>G3</td></tr>\n'
            '<tr valign="top"><td>Presented the migration to the wider team</td><td>Manager\'s notes</td>'
            '<td><a href="../../../journals/2026_09_02.md">Journal 2 Sep</a></td><td>G2</td></tr>', report)
        self.assertIn(
            '<tr valign="top"><td>Retire old billing</td><td>Jira</td>'
            '<td><a href="https://acme.atlassian.net/browse/PROJ-13">PROJ-13</a></td><td>–</td></tr>', report)

    def test_earlier_work_section(self):
        # With the work before the period, its bullets close the work and
        # its impact, after a divider, under their heading; with none, the
        # part is left out.
        report = make_report.render(PERSON, DATA, REPORT_FOLDER, OBSERVATIONS_CONTENT, STEP_CHANGE_CONTENT,
                                    WORK_IMPACT_CONTENT, EARLIER_WORK_CONTENT)
        self.assertIn("</details>\n\n---\n\n### Before the period\n\n- "
                      f"{EARLIER_WORK_CONTENT['bullets'][0]}\n\n## Observations", report)
        self.assertNotIn("Before the period", make_report.render(
            PERSON, DATA, REPORT_FOLDER, OBSERVATIONS_CONTENT, STEP_CHANGE_CONTENT, WORK_IMPACT_CONTENT, None))

    def test_observations_section(self):
        # Each part's heading, marked as the agent's, its summary, then its
        # table folded with how many points it holds, a divider apart from the
        # next part: each value named once beside its points, the value with
        # the most first, each point with the second value it names, its
        # source and references, each evidence's source
        # and day, linked, the most recent first; a part with none, its
        # heading alone.
        report = make_report.render(
            PERSON, DATA, REPORT_FOLDER, OBSERVATIONS_CONTENT, STEP_CHANGE_CONTENT, WORK_IMPACT_CONTENT)
        # Each summarised value in bold over its summary, in its table's
        # order, its points folded under it, then the line on the points
        # under no value over them, then the points no summary covers.
        self.assertIn(
            f'### {common.ai_marked("Going well")}\n\n<b>Teamwork</b>\n\nJane explains outages to the teams around '
            'them and presented the billing migration to the wider team.\n\n<details><summary>Details (2 points)'
            '</summary>', report)
        self.assertIn('</details>\n\n<b>Ownership</b>\n\nJane has owned the billing migration and kept to its plan.'
                      '\n\n<details><summary>Details (1 point)</summary>', report)
        self.assertIn(
            '<b>Also:</b> Jane could share progress with the wider team more often.\n\n<details>', report)
        self.assertIn(
            '</details>\n\n<details><summary>Details (1 other point)</summary>', report)
        self.assertIn('</details>\n\n---\n\n### To improve', report)
        self.assertIn('<tr valign="top"><td></td><td>'
                      "Explained the outage&#x27;s cause in the incident channel, and colleagues thanked them"
                      '</td><td>Slack</td><td><a href="https://'
                      'acme.slack.com/archives/C1/p1">Slack 3 Sep</a></td><td>G1</td></tr>', report)
        self.assertIn('<td>Other feedback</td><td>–'
                      '</td><td>G3</td></tr>', report)
        # The current manager feedback's points name no value, so they come
        # with no reference: among the points no summary covers, under No
        # value, or under the line on them.
        self.assertIn('<tr valign="top"><td rowspan="1">No value</td><td></td><td>'
                      'Has led the billing migration well since May</td><td>Manager feedback</td><td>–</td><td>G4</td></tr>', report)
        self.assertIn('<tr valign="top"><td>'
                      'Could share progress with the wider team more often</td><td>Manager feedback</td><td>–</td><td>I3</td></tr>',
                      report)
        self.assertIn('<a href="../../../journals/2026_10_01.md">Journal 1 Oct</a>, '
                      '<a href="../../../journals/2026_08_20.md">Journal 20 Aug</a>', report)
        # Context last, not grouped: its id, point, source and references, a
        # page's undated evidence named by its title.
        self.assertIn('</details>\n\n---\n\n### Context', report)
        self.assertIn(
            f'<tr valign="top"><th width="65%">{common.ai_marked("Point")}</th><th width="10%">Source</th>'
            '<th width="20%">References</th><th width="5%">ID</th></tr>\n<tr valign="top">'
            '<td>Is preparing a promotion case with the manager</td><td>Other feedback</td><td>–</td><td>C1</td></tr>\n'
            '<tr valign="top"><td>Moved to the payments team in the summer</td>'
            '<td>Manager\'s notes</td><td><a href="../../../pages/Jane.md">Page Jane</a></td><td>C2</td></tr>', report)
        for part, heading in (("to_improve", "To improve"), ("context", "Context")):
            with self.subTest(part):
                empty = {**DATA, "observations": {**
                                                  DATA["observations"], part: []}, "previous": None}
                self.assertIn(f"### {heading}\n\n" + ("---" if part != "context" else "## Step change"),
                              make_report.render(PERSON, empty, REPORT_FOLDER, OBSERVATIONS_CONTENT, None, WORK_IMPACT_CONTENT))
        # The Observations after the work and its impact, under its subtitle,
        # the script's, unmarked, its Point column marked as the agent's.
        self.assertIn(
            "</details>\n\n## Observations\n\n*What the current manager feedback, the period's "
            "other feedback, the manager's notes and Slack show, by company value.*\n\n"
            f"### {common.ai_marked('Going well')}", report)
        self.assertIn(
            f'<th width="10%">{common.ai_marked("Value")}</th><th width="10%">{common.ai_marked("Also")}</th>'
            f'<th width="45%">{common.ai_marked("Point")}</th>', report)
        # A point naming two values sits under the first, the second next to
        # the value's column.
        self.assertIn(
            "<td>Ownership</td><td>Presented the migration to the wider team</td>", report)

    def test_step_change_section(self):
        # A section of its own after the Observations: its heading, marked as
        # the agent's, its subtitle, the script's, unmarked, its summary, then its table folded with how many rows it
        # holds, in small type, its Change column marked: by change, in
        # STEP_CHANGES' order, then by the previous point's order, one with
        # none last; each previous point after its part, or –; each cited
        # point with its source and references, one to a line, an improved
        # one citing none not raised again.
        report = make_report.render(
            PERSON, DATA, REPORT_FOLDER, OBSERVATIONS_CONTENT, STEP_CHANGE_CONTENT, WORK_IMPACT_CONTENT)
        self.assertIn(f'</details>\n\n## {common.ai_marked("Step change")}\n\n*How the period compares with the '
                      'previous feedback: what improved, persisted, worsened or held, and '
                      'how the context changed.*\n\nJane no longer needs support', report)
        self.assertIn(
            "<details><summary>Details (4 changes)</summary>", report)
        self.assertIn(f'<th width="35%">{common.ai_marked("Previous feedback point")}</th>'
                      f'<th width="15%">{common.ai_marked("Change")}</th>'
                      f'<th width="50%">{common.ai_marked("Evidence")}</th>', report)
        step = report.split("## Step change", 1)[1].split("## GitHub", 1)[0]
        rows = [line for line in step.split("\n") if line.startswith('<tr valign="top"><td>')
                and ("<td>To improve: " in line or "<td>Going well: " in line or "<td>–</td>" in line)]
        self.assertEqual(rows, [
            '<tr valign="top"><td>To improve: Could lead a design review alone</td><td>Improved</td>'
            '<td>Not raised again in the period</td></tr>',
            '<tr valign="top"><td>To improve: Flagged delays only when asked</td><td>Still to improve</td>'
            '<td>Didn&#x27;t flag delays until asked, many times (Manager\'s notes: '
            '<a href="../../../journals/2026_10_01.md">Journal 1 Oct</a>, '
            '<a href="../../../journals/2026_08_20.md">Journal 20 Aug</a>)<br>'
            'Could raise risks earlier in planning (Other feedback)</td></tr>',
            '<tr valign="top"><td>Going well: Delivered the billing migration on time</td><td>Held</td>'
            '<td>Agreed to own the billing migration and has kept to its plan (Other feedback)</td></tr>',
            '<tr valign="top"><td>–</td><td>New context</td><td>Moved to the payments team in the summer '
            '(Manager\'s notes: <a href="../../../pages/Jane.md">Page Jane</a>)</td></tr>'])
        # A context point of the previous feedback that changed comes before a new one.
        report = make_report.render(
            PERSON, CONTEXT_DATA, REPORT_FOLDER, OBSERVATIONS_CONTENT, CONTEXT_STEP_CHANGE, WORK_IMPACT_CONTENT)
        self.assertIn('<td>Context: Had no promotion case planned yet</td><td>Context changed</td><td>Is preparing a '
                      'promotion case with the manager (Other feedback)</td></tr>\n<tr valign="top"><td>–</td>'
                      '<td>New context</td>', report)
        # With no row, the summary alone; with no previous feedback, N/A and
        # why, unmarked, and nothing else, not even the subtitle.
        cases = [("no row", DATA, {**STEP_CHANGE_CONTENT, "rows": []},
                  'how the context changed.*\n\nJane no longer needs support to lead a design '
                  "review, but still flags delays only when asked, as the previous feedback said.\n\n"
                  "## GitHub"),
                 ("no previous feedback", {**DATA, "previous": None}, None,
                  "</details>\n\n## Step change\n\nN/A: no previous feedback to compare with\n\n"
                  "## GitHub")]
        for name, data, step_change, expected in cases:
            with self.subTest(name):
                self.assertIn(expected, make_report.render(
                    PERSON, data, REPORT_FOLDER, OBSERVATIONS_CONTENT, step_change, WORK_IMPACT_CONTENT))

    def test_two_rows_of_one_previous_point_are_not_collapsed(self):
        # A previous point whose aspects went differently has a row for each:
        # each keeps the point's text, its own label and its own evidence, in
        # the order of the labels, and the final check reads them back.
        rows = [{"previous_point": "P-I1", "change": "still_to_improve", "evidence": ["I1"]},
                {"previous_point": "P-I1",
                    "change": "improved", "evidence": ["G2"]},
                {"previous_point": "P-I2", "change": "worsened", "evidence": ["I2"]}]
        step = {"summary": "Jane improved on leading a design review, but still has risks to raise earlier "
                           "and flags delays only when asked.", "rows": rows}
        report = make_report.render(
            PERSON, DATA, REPORT_FOLDER, OBSERVATIONS_CONTENT, step, WORK_IMPACT_CONTENT)
        section = report.split("## Step change", 1)[1].split("## GitHub", 1)[0]
        self.assertIn(
            "<details><summary>Details (3 changes)</summary>", section)
        found = [line for line in section.split("\n") if line.startswith(
            '<tr valign="top"><td>To improve: ')]
        self.assertEqual(found, [
            '<tr valign="top"><td>To improve: Could lead a design review alone</td><td>Improved</td>'
            '<td>Presented the migration to the wider team (Manager\'s notes: '
            '<a href="../../../journals/2026_09_02.md">Journal 2 Sep</a>)</td></tr>',
            '<tr valign="top"><td>To improve: Could lead a design review alone</td><td>Still to improve</td>'
            '<td>Could raise risks earlier in planning (Other feedback)</td></tr>',
            '<tr valign="top"><td>To improve: Flagged delays only when asked</td><td>Worsened</td>'
            '<td>Didn&#x27;t flag delays until asked, many times (Manager\'s notes: '
            '<a href="../../../journals/2026_10_01.md">Journal 1 Oct</a>, '
            '<a href="../../../journals/2026_08_20.md">Journal 20 Aug</a>)</td></tr>'])
        self.assertEqual(check_report.report_problems(
            report, DATA, SUMMARIES, VALUE_NAMES, REPORT_FOLDER, OBSERVATIONS_CONTENT, step, WORK_IMPACT_CONTENT), [])

    def test_manager_and_other_feedback_both_render(self):
        # A table holding points of both feedbacks shows each, with its own
        # source and no reference, the manager's first among the undated, in
        # going well, to improve and context alike, and the final check reads
        # the report back from the summaries.
        empty = {"going_well": [], "to_improve": [], "context": []}
        summaries = {"manager": {"going_well": [{"point": "Led the migration", "values": ["Ownership"]}],
                                 "to_improve": [{"point": "Share progress", "values": ["Teamwork"]}],
                                 "context": ["Back from leave"]},
                     "other": {"going_well": [{"point": "Kept to the plan", "values": ["Ownership"]}],
                               "to_improve": [{"point": "Raise risks", "values": ["Teamwork"]}],
                               "context": ["Preparing a promotion case"]},
                     "previous": empty, "notes": empty, "slack": empty}
        data = {
            **DATA, "observations": build_data.observations(summaries, VALUE_NAMES), "previous": None}
        content = {"going_well": {"values": {"Ownership": "Jane led the migration and kept to the plan."}, "also": None},
                   "to_improve": {"values": {"Teamwork": "Jane could share progress and raise risks."}, "also": None},
                   "context": "Jane is back from leave and preparing a promotion case."}
        report = make_report.render(
            PERSON, data, REPORT_FOLDER, content, None, POINT_WORK_IMPACT)
        for expected in ('<td></td><td>Led the migration</td><td>Manager feedback</td><td>–</td><td>G1</td></tr>',
                         '<td>Kept to the plan</td><td>Other feedback</td><td>–</td><td>G2</td></tr>',
                         '<td></td><td>Share progress</td><td>Manager feedback</td><td>–</td><td>I1</td></tr>',
                         '<td>Raise risks</td><td>Other feedback</td><td>–</td><td>I2</td></tr>',
                         '<tr valign="top"><td>Back from leave</td><td>Manager feedback</td><td>–</td><td>C1</td></tr>\n'
                         '<tr valign="top"><td>Preparing a promotion case</td><td>Other feedback</td><td>–</td><td>C2</td></tr>'):
            self.assertIn(expected, report)
        self.assertEqual(check_report.report_problems(
            report, data, summaries, VALUE_NAMES, REPORT_FOLDER, content, None, POINT_WORK_IMPACT), [])

    def test_focus_section(self):
        # Every entry of the main focus, in its order, an epic linked with its
        # title and count, the issues with no epic linked to their search.
        report = make_report.render(
            PERSON, DATA_NO_EPIC_FIRST, REPORT_FOLDER, OBSERVATIONS_CONTENT, STEP_CHANGE_CONTENT, WORK_IMPACT_CONTENT)
        jira = DATA_NO_EPIC_FIRST["jira"]
        self.assertIn(f'<ol><li><a href="{html.escape(jira["no_epic_search_url"])}">no epic</a> (3)</li>'
                      f'<li><a href="{html.escape(jira["epic_search_urls"]["PROJ-1"])}">PROJ-1</a> Billing (2)</li>'
                      '</ol>', report)

    def test_notion_pages_by_calendar_week(self):
        # Pages found by a week's search split in two share that week's row.
        page = DATA["notion"]["created"][0]
        pages = [{**page, "between": ["2026-08-10", "2026-08-12"]},
                 {**page, "url": "https://www.notion.so/billing-risks", "title": "Billing risks",
                  "between": ["2026-08-13", "2026-08-16"]}]
        data = {**DATA, "notion": {**DATA["notion"],
                                   "created": pages, "counts": {"created": 2}}}
        report = make_report.render(
            PERSON, data, REPORT_FOLDER, OBSERVATIONS_CONTENT, STEP_CHANGE_CONTENT, WORK_IMPACT_CONTENT)
        self.assertEqual(report.count(
            '<td rowspan="2">10–16 Aug</td>'), 1)
        self.assertEqual(check_report.report_problems(
            report, data, SUMMARIES, VALUE_NAMES, REPORT_FOLDER, OBSERVATIONS_CONTENT, STEP_CHANGE_CONTENT, WORK_IMPACT_CONTENT), [])


if __name__ == "__main__":
    unittest.main()
