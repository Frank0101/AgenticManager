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
from prep_fixture import DATA, DATA_NO_EPIC_FIRST, PERSON  # noqa: E402


class MakeReportTest(unittest.TestCase):
    def test_render(self):
        # The fixture's Jira figures, each linked to its search, with its
        # breakdown and chart, as the final check reads them back.
        report = make_report.render(PERSON, DATA)
        self.assertTrue(report.startswith(
            "# Jane Doe: performance review prep\n\nPeriod: 10/08/2026 to 10/11/2026"))
        self.assertIn(
            f"<a href=\"{html.escape(DATA['jira']['resolved_points_search_url'])}\">3</a> (avg=3)", report)
        # The Notion pages, the most recent week first, each week named once
        # beside its pages, in small type.
        self.assertIn('<tr valign="top"><td rowspan="1"><small><small>10–16 Aug</small></small></td><td><small>'
                      '<small><a href="https://www.notion.so/billing-plan">Billing plan</a></small></small></td><td>'
                      '<small><small>Engineering</small></small></td></tr>', report)
        self.assertEqual(check_report.report_problems(
            report, DATA, common.CHART_FILES), [])

    def test_focus_section(self):
        # Every entry of the main focus, in its order, an epic linked with its
        # title and count, the issues with no epic linked to their search, as
        # the final check reads them back.
        report = make_report.render(PERSON, DATA_NO_EPIC_FIRST)
        jira = DATA_NO_EPIC_FIRST["jira"]
        self.assertIn(f'<ol><li><a href="{html.escape(jira["no_epic_search_url"])}">no epic</a> (3)</li>'
                      f'<li><a href="{html.escape(jira["epic_search_urls"]["PROJ-1"])}">PROJ-1</a> Billing (2)</li>'
                      '</ol>', report)
        self.assertEqual(check_report.report_problems(
            report, DATA_NO_EPIC_FIRST, common.CHART_FILES), [])

    def test_notion_pages_by_calendar_week(self):
        # Pages found by a week's search split in two share that week's row.
        page = DATA["notion"]["created"][0]
        pages = [{**page, "between": ["2026-08-10", "2026-08-12"]},
                 {**page, "url": "https://www.notion.so/billing-risks", "title": "Billing risks",
                  "between": ["2026-08-13", "2026-08-16"]}]
        data = {**DATA, "notion": {**DATA["notion"],
                                   "created": pages, "counts": {"created": 2}}}
        report = make_report.render(PERSON, data)
        self.assertEqual(report.count(
            '<td rowspan="2"><small><small>10–16 Aug</small></small></td>'), 1)
        self.assertEqual(check_report.report_problems(
            report, data, common.CHART_FILES), [])


if __name__ == "__main__":
    unittest.main()
