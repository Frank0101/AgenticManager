"""Unit tests for skills/agentic-manager-tech-investigation/scripts/finish_report.py.
The whole pipeline has end-to-end tests in test_e2e_investigation.py.
Run with: python3 tests/run.py agentic-manager-tech-investigation
"""

import json
import os
import sys
import unittest

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(TEST_DIR))
sys.path.insert(0, os.path.join(REPO_ROOT, "skills",
                os.path.basename(TEST_DIR), "scripts"))
import finish_report  # noqa: E402
sys.path.insert(0, TEST_DIR)
from investigation_fixture import INVESTIGATION, LEDGER, content, temp_output  # noqa: E402

REPORT = "Acme-Search_Report.md"


class FinishReportTest(unittest.TestCase):
    def setUp(self):
        self.folder = os.path.join(temp_output(self), INVESTIGATION)
        os.makedirs(self.folder)
        self.write("ledger.md", LEDGER)
        self.write(REPORT, "an earlier report")

    def write(self, name, text):
        with open(os.path.join(self.folder, name), "w", encoding="utf-8") as f:
            f.write(text)

    def test_invalid_text_writes_nothing(self):
        # The earlier report is gone, and nothing replaces it.
        self.write("content.json", json.dumps({}))
        with self.assertRaisesRegex(SystemExit, "content.json has problems"):
            finish_report.finish(INVESTIGATION)
        self.assertFalse(os.path.exists(os.path.join(self.folder, REPORT)))

    def test_valid_text_writes_a_report_that_passes(self):
        # The report is written anew from content.json, and passes the
        # final check.
        self.write("content.json", json.dumps(content()))
        result = finish_report.finish(INVESTIGATION)
        self.assertEqual(result["path"], os.path.join(self.folder, REPORT))
        with open(result["path"], encoding="utf-8") as f:
            self.assertNotEqual(f.read(), "an earlier report")


if __name__ == "__main__":
    unittest.main()
