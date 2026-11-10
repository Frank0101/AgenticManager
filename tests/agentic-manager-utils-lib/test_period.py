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
        for text in ("10/08/2026", "2026-02-30", ""):
            with self.subTest(text), self.assertRaisesRegex(argparse.ArgumentTypeError, "YYYY-MM-DD"):
                period.day_argument(text)


if __name__ == "__main__":
    unittest.main()
