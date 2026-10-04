# Unit tests for skills/agentic-manager-jira-sprint-report/scripts/check_report.py.
# Run with: python3 tests/run.py agentic-manager-jira-sprint-report
#
# Each test renders the report of report_fixture.py's sprint with make_report,
# breaks one thing in it, and checks that the matching check fails.
import contextlib
import copy
import io
import os
import sys
import tempfile
import unittest

# tests/<skill>/ mirrors skills/<skill>/.
TEST_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(TEST_DIR))
sys.path.insert(0, os.path.join(REPO_ROOT, "skills",
                os.path.basename(TEST_DIR), "scripts"))
import check_report  # noqa: E402
from common import CHART_FILES  # noqa: E402
from make_report import Report  # noqa: E402

sys.path.insert(0, TEST_DIR)
from report_fixture import BASE, CONTENT, sprint_data  # noqa: E402


class HelpersTest(unittest.TestCase):
    def test_has_key_matches_the_exact_key(self):
        cell = f'<a href="{BASE}/browse/PROJ-10">PROJ-10</a>'
        self.assertTrue(check_report.has_key(cell, "PROJ-10"))
        self.assertFalse(check_report.has_key(cell, "PROJ-1"))

    def test_html_parsing(self):
        table = "<table><tr><th>Date</th><th>Added to sprint</th></tr><tr><td>a<br>b</td><td>c</td></tr></table>"
        self.assertEqual(check_report.html_tables(f"x {table} y"), [table])
        self.assertEqual([check_report.cells_of(r) for r in check_report.rows_of(table)],
                         [["Date", "Added to sprint"], ["a<br>b", "c"]])
        self.assertEqual(check_report.strip_tags("<b>a</b><br>b"), "a  b")
        self.assertEqual(check_report.table_kind(table), "timeline")
        self.assertIsNone(check_report.table_kind(
            "<table><tr><th>Other</th></tr></table>"))

    def test_parsed_number(self):
        self.assertEqual((check_report.parsed_number("3.0"),
                         check_report.parsed_number("2.5")), (3, 2.5))
        self.assertIsInstance(check_report.parsed_number("3.0"), int)

    def test_prose_has(self):
        md = "We descoped three stories worth 14 points.\n<table>5 stories, 9 pts</table>"
        cases = [("in words", md, 3, 14, True), ("in digits", "3 (14 pts)", 3, 14, True),
                 ("only inside a table", md, 5, 9, False)]
        for name, text, count, points, expected in cases:
            with self.subTest(name):
                self.assertIs(check_report.prose_has(
                    text, count, points), expected)

    def test_checker(self):
        c = check_report.Checker()
        self.assertTrue(c.check(True, "a", "fine"))
        self.assertFalse(c.check(False, "b", "broken"))
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(c.report(), 1)
        self.assertIn("  ok    a: fine\n  FAIL  b: broken\n", out.getvalue())
        self.assertIn("1 check(s) failed", out.getvalue())


class ChecksTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        for name in CHART_FILES.values():
            open(os.path.join(self.tmp.name, name), "w").close()
        self.data = sprint_data()
        self.md = Report(self.data, copy.deepcopy(CONTENT)).build()

    def failures(self, md=None, data=None):
        return check_report.run_checks(md or self.md, data or self.data, self.tmp.name).failures

    def assert_fails(self, check, md):
        failures = self.failures(md)
        self.assertTrue(any(f.startswith(f"{check}: ") for f in failures),
                        f"no {check!r} failure in {failures}")

    def replace(self, old, new):
        """The report with `old`, which must appear in it, replaced by `new`."""
        self.assertIn(old, self.md)
        return self.md.replace(old, new, 1)

    def test_generated_reports_pass(self):
        for name, changes in {"closed": {}, "active": {"sprint_status": "active", "today": "2026-03-10",
                                                       "sprint_complete_date": None}}.items():
            with self.subTest(name):
                data = sprint_data(**changes)
                md = Report(data, copy.deepcopy(CONTENT)).build()
                self.assertEqual(self.failures(md, data), [])

    def test_excluded_membership_must_be_stated(self):
        data = sprint_data(membership_cross_check_excluded_keys=["PROJ-6"])
        md = Report(data, copy.deepcopy(CONTENT)).build()
        self.assertEqual(self.failures(md, data), [])
        stated = "later sprint moves prevent comparison with Jira's current membership buckets"
        self.assertIn("figures: historical membership comparison limitation stated",
                      self.failures(md.replace(stated, "ok"), data))

    def test_descope_not_stated(self):
        # A descope no other sentence of the report shares, so only its own wording states it.
        data = sprint_data()
        data["removed_summary"]["descoped_incomplete"] = {
            "count": 7, "points": 13}
        md = Report(data, copy.deepcopy(CONTENT)).build()
        c = check_report.Checker()
        check_report.check_figures(c, md, data)
        self.assertEqual(c.failures, [])
        for stated in ("7 incomplete stories (13 points)", "7 stories / 13 pts were"):
            self.assertIn(stated, md)
            md = md.replace(stated, "some work")
        c = check_report.Checker()
        check_report.check_figures(c, md, data)
        self.assertEqual(c.failures, ["figures: descope stated"])

    def test_each_check_catches_its_breakage(self):
        flat = f'<td>1 story / 3 pts<br><a href="{BASE}/browse/PROJ-1">PROJ-1</a>'
        cases = [
            ("figures", "4 completed (7 points)", "4 completed (8 points)"),
            ("movements", "<b>Descoped,", "<b>Dropped,"),
            ("headings", "## Delivery by Epic\n",
             "## Delivery by Epic\n\nIntro.\n"),
            ("commentary",
             f"Delivery centred on [PROJ-100]({BASE}/browse/PROJ-100).", ""),
            ("columns", "<b>6 stories / 11 pts</b>", "<b>6 stories / 12 pts</b>"),
            ("columns", "<b>6 stories / 11 pts</b>", "<b>16 stories / 11 pts</b>"),
            ("columns", "<td>1 story / 3 pts<br>", "<td>1 story / 4 pts<br>"),
            ("cell shapes", flat, flat + "<br>note"),
            ("cell shapes", "<td>1 story / 3 pts<br>", "<td>three<br>"),
            ("subgroups", "<b>Already done, 1 story / 1 pt</b>",
             "<b>Already done, 1 story / 2 pts</b>"),
            ("totals row", "<b>3 stories / 6 pts</b>",
             "<b>3 stories / 6 pts (still in scope: 3 stories / 6 pts)</b>"),
            ("spacing", "<td>1 story / 3 pts<br><a",
             "<td>1 story / 3 pts<br><br><a"),
            ("quantities", "<td>–</td>", "<td>(3 pts)</td>"),
            ("epics", "<td>3/5</td>", "<td>3/6</td>"),
            ("retro", "Board-data quality:", "Data:"),
            ("retro", "leaving 4 stories / 9 pts to do",
             "leaving 4 stories / 10 pts to do"),
            ("images",
             "## Scope Timeline\n\n![Sprint burndown](burndown.svg)", "## Scope Timeline"),
            ("em dashes", "Partially met", "Partially met — mostly"),
            ("dates", "02/03/2026–", "2026-03-02–"),
            ("links", "Delivery centred on", "PROJ-9 and delivery centred on"),
        ]
        for check, old, new in cases:
            with self.subTest(check=check, old=old):
                self.assert_fails(check, self.replace(old, new))

    def test_missing_chart(self):
        os.remove(os.path.join(self.tmp.name, CHART_FILES["burndown"]))
        self.assert_fails("images", self.md)

    def test_missing_tables_and_sections(self):
        failures = self.failures("# Sprint Summary\n\nNothing here.\n")
        for expected in ("timeline: table found", "epics: table found", "retro: section found"):
            self.assertIn(expected, failures)

    def test_missing_rows(self):
        cases = [("<td>04/03/2026</td>", "<td>05/04/2026</td>", "movements: 04/03/2026 has a row"),
                 ("<td><b>Total</b></td>",
                  "<td><b>Sum</b></td>", "totals row: present"),
                 (">PROJ-100: ", ">PROJ-101: ", "epics: PROJ-100 has a row")]
        for old, new, expected in cases:
            with self.subTest(expected):
                self.assertIn(expected, self.failures(self.replace(old, new)))

    def test_table_without_a_heading(self):
        md = "<table><tr><th>Epic</th><th>Commentary</th></tr></table>\n\n" + "Prose. " * 10
        c = check_report.Checker()
        check_report.check_framing(c, md)
        self.assertEqual(
            c.failures, ["headings: epics table has a heading above it"])

    def test_other_tables_are_not_framed(self):
        c = check_report.Checker()
        check_report.check_framing(c, "<table><tr><th>Field</th></tr></table>")
        self.assertEqual((c.failures, c.passes), ([], []))


if __name__ == "__main__":
    unittest.main()
