"""Unit tests for skills/agentic-manager-perf-review-prep/scripts/make_report.py.
Run with: python3 tests/run.py agentic-manager-perf-review-prep
"""

import html
import os
import re
import sys
import unittest
from datetime import date

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(TEST_DIR))
sys.path.insert(0, os.path.join(REPO_ROOT, "skills",
                os.path.basename(TEST_DIR), "scripts"))
import common  # noqa: E402
import make_report  # noqa: E402
sys.path.insert(0, TEST_DIR)
from prep_fixture import PERSON, PREP, WORK, temp_output, write_prep  # noqa: E402


class MakeReportTest(unittest.TestCase):
    def test_week_groups(self):
        # Calendar weeks, Monday to Sunday, the first and last clipped to the
        # period; a long period groups them, always the same weeks, so there
        # are at most twenty.
        weeks = make_report.week_groups("2026-08-10", "2026-11-10")
        self.assertEqual((len(weeks), weeks[0], weeks[-1]),
                         (14, (date(2026, 8, 10), date(2026, 8, 16)), (date(2026, 11, 9), date(2026, 11, 10))))
        self.assertEqual(make_report.week_groups("2026-09-02", "2026-09-02"),
                         [(date(2026, 9, 2), date(2026, 9, 2))])
        year = make_report.week_groups("2026-01-01", "2026-12-31")
        self.assertLessEqual(len(year), make_report.MAX_POINTS)
        self.assertEqual((year[0][0], year[-1][1]),
                         (date(2026, 1, 1), date(2026, 12, 31)))

    def test_over_time_chart(self):
        # A point per week, each month named once, under its first week, even
        # when the period starts mid-week.
        weeks = make_report.week_groups("2026-07-01", "2026-08-20")
        chart = make_report.over_time_chart(
            [{"date": "2026-07-02"}, {"date": "2026-08-18"}], weeks, "resolved")
        points = re.findall(r'<polyline points="([^"]+)"', chart)[0].split()
        self.assertEqual(len(points), len(weeks))
        self.assertEqual(re.findall(r">(Jul|Aug)<", chart), ["Jul", "Aug"])

    def test_points_chart(self):
        # A bar for each number of points, the average's line between the two
        # it lies between; a note when nothing is estimated.
        chart = make_report.points_chart(
            [{"points": p} for p in (1, 3, 3, None)], 7 / 3)
        self.assertEqual(len(re.findall(r"<rect x=", chart)), 2)
        self.assertIn('stroke-dasharray="5 4"', chart)
        self.assertIn("No estimated issues",
                      make_report.points_chart([{"points": None}], None))
        self.assertAlmostEqual(
            make_report.average_x(2, [1, 3], [100, 200]), 150)

    def test_render(self):
        # The fixture's Jira figures, each linked to its search, with its
        # breakdown and chart, as the final check reads them back.
        report = make_report.render(PERSON, WORK)
        self.assertTrue(report.startswith(
            "# Jane Doe: performance review prep\n\nPeriod: 10/08/2026 to 10/11/2026"))
        self.assertIn(
            f"<a href=\"{html.escape(WORK['jira']['resolved_points_search_url'])}\">3</a> (avg=3)", report)
        self.assertEqual(common.report_problems(
            report, WORK, common.CHART_FILES), [])

    def test_focus_section(self):
        # Every epic of the main focus, each linked with its title and count,
        # as the final check reads them back.
        issue = WORK["jira"]["resolved"][0]
        invoices = {"key": "PROJ-2", "title": "Invoices",
                    "url": "https://acme.atlassian.net/browse/PROJ-2"}
        resolved = [issue, {**issue, "key": "PROJ-14", "url": "https://acme.atlassian.net/browse/PROJ-14",
                            "epic": invoices}]
        jira = {**WORK["jira"], "resolved": resolved,
                **common.source_facts("jira", {"created": WORK["jira"]["created"], "resolved": resolved},
                                      common.period_days(PERSON))}
        jira["epic_search_urls"] = {
            **jira["epic_search_urls"], "PROJ-2": "https://acme.atlassian.net/issues/?jql=x"}
        work = {**WORK, "jira": jira}
        report = make_report.render(PERSON, work)
        self.assertIn(
            '<a href="https://acme.atlassian.net/issues/?jql=x">PROJ-2</a> Invoices (1)', report)
        self.assertEqual(common.report_problems(
            report, work, common.CHART_FILES), [])

    def test_make_report(self):
        # The report and every chart, checked once written.
        folder = temp_output(self)
        write_prep(folder, report=False)
        made = make_report.make_report(PREP)
        self.assertEqual((made["problems"], sorted(os.listdir(os.path.join(folder, PREP, common.CHARTS_DIR)))),
                         ([], sorted(common.CHART_FILES)))


if __name__ == "__main__":
    unittest.main()
