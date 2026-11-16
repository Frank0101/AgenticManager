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
from prep_fixture import CONTENT, DATA, DATA_NO_EPIC_FIRST, PERSON, REPORT_FOLDER, SUMMARIES, VALUE_NAMES  # noqa: E402


class MakeReportTest(unittest.TestCase):
    def test_render(self):
        # The fixture's Jira figures, each linked to its search, with its
        # breakdown and chart, as the final check reads them back.
        report = make_report.render(PERSON, DATA, REPORT_FOLDER, CONTENT)
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
            report, DATA, common.CHART_FILES, SUMMARIES, VALUE_NAMES, REPORT_FOLDER, CONTENT), [])

    def test_observations_section(self):
        # Each part's heading, marked as the agent's, its summary, then its
        # table folded with how many points it holds, a divider apart from the
        # next part: each value named once beside its points, the value with
        # the most first, each point with the second value it names, its
        # source and references, a piece's period or each evidence's source
        # and day, linked, the most recent first; a part with none, its
        # heading alone.
        report = make_report.render(PERSON, DATA, REPORT_FOLDER, CONTENT)
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
        empty = {**DATA, "observations": {**
                                          DATA["observations"], "to_improve": []}}
        self.assertIn("<b>To improve</b>\n\n## GitHub",
                      make_report.render(PERSON, empty, REPORT_FOLDER, CONTENT))
        # The Observations first, its Point column marked as the agent's.
        self.assertIn(
            "Period: 10/08/2026 to 10/11/2026\n\n## Observations\n", report)
        self.assertIn(
            f'<th width="10%">Value</th><th width="10%">Also</th><th width="50%">{common.ai_marked("Point")}</th>', report)
        # A point naming two values sits under the first, the second next to
        # the value's column.
        self.assertIn(
            "<td>Ownership</td><td>Presented the migration to the wider team</td>", report)

    def test_focus_section(self):
        # Every entry of the main focus, in its order, an epic linked with its
        # title and count, the issues with no epic linked to their search, as
        # the final check reads them back.
        report = make_report.render(
            PERSON, DATA_NO_EPIC_FIRST, REPORT_FOLDER, CONTENT)
        jira = DATA_NO_EPIC_FIRST["jira"]
        self.assertIn(f'<ol><li><a href="{html.escape(jira["no_epic_search_url"])}">no epic</a> (3)</li>'
                      f'<li><a href="{html.escape(jira["epic_search_urls"]["PROJ-1"])}">PROJ-1</a> Billing (2)</li>'
                      '</ol>', report)
        self.assertEqual(check_report.report_problems(
            report, DATA_NO_EPIC_FIRST, common.CHART_FILES, SUMMARIES, VALUE_NAMES, REPORT_FOLDER, CONTENT), [])

    def test_notion_pages_by_calendar_week(self):
        # Pages found by a week's search split in two share that week's row.
        page = DATA["notion"]["created"][0]
        pages = [{**page, "between": ["2026-08-10", "2026-08-12"]},
                 {**page, "url": "https://www.notion.so/billing-risks", "title": "Billing risks",
                  "between": ["2026-08-13", "2026-08-16"]}]
        data = {**DATA, "notion": {**DATA["notion"],
                                   "created": pages, "counts": {"created": 2}}}
        report = make_report.render(PERSON, data, REPORT_FOLDER, CONTENT)
        self.assertEqual(report.count(
            '<td rowspan="2">10–16 Aug</td>'), 1)
        self.assertEqual(check_report.report_problems(
            report, data, common.CHART_FILES, SUMMARIES, VALUE_NAMES, REPORT_FOLDER, CONTENT), [])


if __name__ == "__main__":
    unittest.main()
