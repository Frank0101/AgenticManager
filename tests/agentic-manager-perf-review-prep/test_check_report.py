"""Unit tests for skills/agentic-manager-perf-review-prep/scripts/check_report.py.
Run with: python3 tests/run.py agentic-manager-perf-review-prep
"""

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
from prep_fixture import PERSON, DATA  # noqa: E402


class CheckReportTest(unittest.TestCase):
    def test_report_problems(self):
        # name: (a change to the report's text, the charts, expected in the
        # problems, or None for none): each Jira figure is read back from the
        # table and worked out again from the items.
        report = make_report.render(PERSON, DATA)
        cases = [("as written", None, common.CHART_FILES, None),
                 ("a count changed", ('">1</a>', '">2</a>'),
                  common.CHART_FILES, "cell for created"),
                 ("a breakdown changed", ("(1 Task)", "(1 Bug)"),
                  common.CHART_FILES, "cell for created"),
                 ("an average changed", ("avg=3", "avg=4"),
                  common.CHART_FILES, "cell for resolved_points"),
                 ("no charts", ("<td><img", "<td><image"),
                  common.CHART_FILES, "a row of three figures and one of their charts"),
                 ("a chart missing", None,
                  common.CHART_FILES[1:], "the charts folder must hold only"),
                 ("a .DS_Store beside the charts", None, [*common.CHART_FILES, ".DS_Store"], None)]
        for name, change, charts, expected in cases:
            with self.subTest(name):
                text = report.replace(
                    change[0], change[1], 1) if change else report
                problems = " ".join(
                    check_report.report_problems(text, DATA, charts))
                if expected is None:
                    self.assertEqual(problems, "")
                else:
                    self.assertIn(expected, problems)


if __name__ == "__main__":
    unittest.main()
