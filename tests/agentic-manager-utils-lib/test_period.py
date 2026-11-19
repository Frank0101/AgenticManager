"""Unit tests for skills/agentic-manager-utils-lib/agentic_manager/period.py.
Run as a script, it has end-to-end tests in test_e2e_period.py.
Run with: python3 tests/run.py agentic-manager-utils-lib
"""

import argparse
import os
import sys
import unittest
from datetime import date

# tests/<skill>/ mirrors skills/<skill>/.
TEST_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(TEST_DIR))
sys.path.insert(0, os.path.join(
    REPO_ROOT, "skills", os.path.basename(TEST_DIR)))
from agentic_manager import period  # noqa: E402

TODAY = date(2026, 11, 10)


class PeriodTest(unittest.TestCase):
    def test_is_day(self):
        # Only a real day as YYYY-MM-DD; another form fromisoformat accepts,
        # a month or a day that doesn't exist, no.
        cases = [("2026-06-30", True), ("20260630", False),
                 ("2026-06", False), ("2026-02-30", False)]
        for value, expected in cases:
            with self.subTest(value):
                self.assertEqual(period.is_day(value), expected)

    def test_days(self):
        self.assertEqual(period.days(date(2026, 2, 27), date(2026, 3, 1)),
                         [date(2026, 2, 27), date(2026, 2, 28), date(2026, 3, 1)])
        self.assertEqual(period.days(date(2026, 3, 1), date(2026, 2, 27)), [])

    def test_last_months(self):
        # It ends today and starts the same day N months back, or that month's
        # last day when it is shorter.
        cases = [(3, TODAY, date(2026, 8, 10)),
                 (12, TODAY, date(2025, 11, 10)),
                 (1, date(2026, 1, 15), date(2025, 12, 15)),
                 (3, date(2026, 8, 31), date(2026, 5, 31)),
                 (3, date(2026, 5, 31), date(2026, 2, 28)),
                 (3, date(2028, 5, 31), date(2028, 2, 29)),
                 (24, date(2026, 3, 1), date(2024, 3, 1))]
        for months, today, start in cases:
            with self.subTest(months=months, today=today):
                self.assertEqual(period.last_months(
                    months, today), (start, today))
        with self.assertRaisesRegex(ValueError, "at least 1"):
            period.last_months(0, TODAY)

    def test_period_problem(self):
        # name: (start, end, expected in the problem, or None)
        cases = [("ends today", date(2026, 8, 10), TODAY, None),
                 ("one day", TODAY, TODAY, None),
                 ("ends after today", date(2026, 10, 1), date(2026, 12, 31),
                  "ends on 31/12/2026, after today, 10/11/2026"),
                 ("starts after it ends", date(2026, 6, 30), date(2026, 1, 1),
                  "starts on 30/06/2026, after it ends, on 01/01/2026")]
        for name, start, end, expected in cases:
            with self.subTest(name):
                problem = period.period_problem(start, end, TODAY)
                if expected is None:
                    self.assertIsNone(problem)
                else:
                    self.assertIn(expected, problem or "")

    def test_resolve(self):
        # The period named on the command line, as the user confirms it.
        self.assertEqual(period.resolve(period.parse_args(["--last-months", "3"]), TODAY),
                         {"start": "2026-08-10", "end": "2026-11-10", "shown": "10/08/2026 to 10/11/2026"})
        self.assertEqual(period.resolve(period.parse_args(["--start", "2026-01-01", "--end", "2026-06-30"]), TODAY),
                         {"start": "2026-01-01", "end": "2026-06-30", "shown": "01/01/2026 to 30/06/2026"})
        for args, expected in [(["--last-months", "0"], "at least 1"),
                               (["--start", "2026-01-01"], "name the period"),
                               (["--start", "2026-01-01", "--end", "2026-12-31"], "after today")]:
            with self.subTest(args), self.assertRaisesRegex(SystemExit, expected):
                period.resolve(period.parse_args(args), TODAY)

    def test_day_argument(self):
        self.assertEqual(period.day_argument(
            " 2026-08-10 "), date(2026, 8, 10))
        for text in ("10/08/2026", "2026-02-30", "20260810", ""):
            with self.subTest(text), self.assertRaisesRegex(argparse.ArgumentTypeError, "YYYY-MM-DD"):
                period.day_argument(text)

    def test_months_of(self):
        # name: (first day, last day, the months): each month of the period,
        # its first and last month clipped to it.
        cases = [("clipped at both ends", date(2026, 8, 10), date(2026, 10, 3),
                  {"2026-08": ("2026-08-10", "2026-08-31"), "2026-09": ("2026-09-01", "2026-09-30"),
                   "2026-10": ("2026-10-01", "2026-10-03")}),
                 ("whole months", date(2026, 9, 1), date(2026, 10, 31),
                  {"2026-09": ("2026-09-01", "2026-09-30"), "2026-10": ("2026-10-01", "2026-10-31")}),
                 ("a one-day month", date(2026, 8, 20), date(2026, 9, 1),
                  {"2026-08": ("2026-08-20", "2026-08-31"), "2026-09": ("2026-09-01", "2026-09-01")}),
                 ("inside one month", date(2026, 9, 5), date(2026, 9, 12),
                  {"2026-09": ("2026-09-05", "2026-09-12")}),
                 ("one day", date(2026, 9, 5), date(2026, 9, 5),
                  {"2026-09": ("2026-09-05", "2026-09-05")}),
                 ("a leap February", date(2028, 1, 31), date(2028, 3, 1),
                  {"2028-01": ("2028-01-31", "2028-01-31"), "2028-02": ("2028-02-01", "2028-02-29"),
                   "2028-03": ("2028-03-01", "2028-03-01")}),
                 ("across a year", date(2026, 12, 15), date(2027, 1, 10),
                  {"2026-12": ("2026-12-15", "2026-12-31"), "2027-01": ("2027-01-01", "2027-01-10")})]
        for name, first, last, expected in cases:
            with self.subTest(name):
                self.assertEqual(period.months_of(first, last),
                                 {month: {"start": start, "end": end} for month, (start, end) in expected.items()})

    def test_calendar_weeks(self):
        # The Monday to Sunday of the day, clipped to the period, and every
        # week of a period, the first and last clipped to it.
        week_cases = [("mid-week", "2026-08-12", ["2026-08-10", "2026-08-16"]),
                      ("the period's first week", "2026-08-03",
                       ["2026-08-05", "2026-08-09"]),
                      ("the period's last day, a Monday", "2026-11-09", ["2026-11-09", "2026-11-09"])]
        for name, day, expected in week_cases:
            with self.subTest(name):
                self.assertEqual(period.calendar_week(
                    day, "2026-08-05", "2026-11-09"), expected)
        cases = [("a Wednesday to a Monday", "2026-07-01", "2026-07-20",
                  [["2026-07-01", "2026-07-05"], ["2026-07-06", "2026-07-12"], ["2026-07-13", "2026-07-19"],
                   ["2026-07-20", "2026-07-20"]]),
                 ("whole weeks", "2026-07-06", "2026-07-19",
                  [["2026-07-06", "2026-07-12"], ["2026-07-13", "2026-07-19"]]),
                 ("a Sunday first, a one-day first week", "2026-07-05", "2026-07-13",
                  [["2026-07-05", "2026-07-05"], ["2026-07-06", "2026-07-12"], ["2026-07-13", "2026-07-13"]]),
                 ("a Sunday last, a full last week", "2026-07-06", "2026-07-26",
                  [["2026-07-06", "2026-07-12"], ["2026-07-13", "2026-07-19"], ["2026-07-20", "2026-07-26"]]),
                 ("inside one week", "2026-07-07",
                  "2026-07-09", [["2026-07-07", "2026-07-09"]]),
                 ("one day", "2026-07-12", "2026-07-12",
                  [["2026-07-12", "2026-07-12"]]),
                 ("across a year", "2026-12-30", "2027-01-05", [["2026-12-30", "2027-01-03"], ["2027-01-04", "2027-01-05"]])]
        for name, start, end, expected in cases:
            with self.subTest(name):
                self.assertEqual(period.calendar_weeks(start, end), expected)


if __name__ == "__main__":
    unittest.main()
