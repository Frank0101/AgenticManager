# End-to-end tests for skills/agentic-manager-tech-investigation/scripts/check_report.py:
# they run the whole script, as the skill does. Its functions have unit tests in
# test_check_report.py; test_e2e_pipeline.py runs it on a whole investigation.
# Run with: python3 tests/run.py agentic-manager-tech-investigation
#
# HOME and TMPDIR point at a temporary folder holding no config: the check needs none.
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(TEST_DIR))
SCRIPT = os.path.join(REPO_ROOT, "skills", os.path.basename(
    TEST_DIR), "scripts", "check_report.py")


class CheckReportCommandTest(unittest.TestCase):
    def test_missing_report_returns_json_without_config(self):
        with tempfile.TemporaryDirectory() as folder:
            process = subprocess.run(
                [sys.executable, SCRIPT, "--report",
                    str(Path(folder) / "missing.md")],
                env={**os.environ, "HOME": folder, "TMPDIR": folder},
                capture_output=True, text=True, check=False,
            )
            self.assertEqual(process.returncode, 1)
            self.assertEqual(len(process.stdout.splitlines()),
                             1, process.stdout)
            result = json.loads(process.stdout)
            self.assertFalse(result["ok"])
            self.assertIn("Cannot read report", result["errors"][0])
            self.assertEqual(process.stderr, "")
            self.assertFalse((Path(folder) / "missing.md").exists())
            self.assertFalse((Path(folder) / ".config").exists())


if __name__ == "__main__":
    unittest.main()
