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
from prep_fixture import PERSON, PREP, DATA, temp_output, write_prep  # noqa: E402


class MakeReportTest(unittest.TestCase):
    def test_render(self):
        # The fixture's Jira figures, each linked to its search, with its
        # breakdown and chart, as the final check reads them back.
        report = make_report.render(PERSON, DATA)
        self.assertTrue(report.startswith(
            "# Jane Doe: performance review prep\n\nPeriod: 10/08/2026 to 10/11/2026"))
        self.assertIn(
            f"<a href=\"{html.escape(DATA['jira']['resolved_points_search_url'])}\">3</a> (avg=3)", report)
        self.assertEqual(check_report.report_problems(
            report, DATA, common.CHART_FILES), [])

    def test_focus_section(self):
        # Every epic of the main focus, each linked with its title and count,
        # as the final check reads them back.
        issue = DATA["jira"]["resolved"][0]
        invoices = {"key": "PROJ-2", "title": "Invoices",
                    "url": "https://acme.atlassian.net/browse/PROJ-2"}
        resolved = [issue, {**issue, "key": "PROJ-14", "url": "https://acme.atlassian.net/browse/PROJ-14",
                            "epic": invoices}]
        jira = {**DATA["jira"], "resolved": resolved,
                **build_data.source_facts("jira", {"created": DATA["jira"]["created"], "resolved": resolved},
                                          DATA["weeks"])}
        jira["epic_search_urls"] = {
            **jira["epic_search_urls"], "PROJ-2": "https://acme.atlassian.net/issues/?jql=x"}
        work = {**DATA, "jira": jira}
        report = make_report.render(PERSON, work)
        self.assertIn(
            '<a href="https://acme.atlassian.net/issues/?jql=x">PROJ-2</a> Invoices (1)', report)
        self.assertEqual(check_report.report_problems(
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
