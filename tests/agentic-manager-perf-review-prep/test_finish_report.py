"""Unit tests for skills/agentic-manager-perf-review-prep/scripts/finish_report.py.
Run with: python3 tests/run.py agentic-manager-perf-review-prep
"""

import os
import sys
import unittest

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(TEST_DIR))
sys.path.insert(0, os.path.join(REPO_ROOT, "skills",
                os.path.basename(TEST_DIR), "scripts"))
import common  # noqa: E402
import finish_report  # noqa: E402
sys.path.insert(0, TEST_DIR)
from prep_fixture import PREP, temp_output, write_prep  # noqa: E402


class FinishReportTest(unittest.TestCase):
    def test_finish(self):
        # The report and every chart, checked once written.
        folder = temp_output(self)
        write_prep(folder, report=False)
        made = finish_report.finish(PREP)
        self.assertEqual((made["problems"], sorted(os.listdir(os.path.join(folder, PREP, common.CHARTS_DIR)))),
                         ([], sorted(common.CHART_FILES)))


if __name__ == "__main__":
    unittest.main()
