"""End-to-end tests for skills/agentic-manager-utils-lib/agentic_manager/period.py:
they run it as a script, as an agent does to turn the period a user names into
days. Its functions have unit tests in test_period.py.
Run with: python3 tests/run.py agentic-manager-utils-lib
"""

import json
import os
import subprocess
import sys
import unittest
from datetime import date

# tests/<skill>/ mirrors skills/<skill>/.
TEST_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(TEST_DIR))
SCRIPT = os.path.join(REPO_ROOT, "skills", os.path.basename(TEST_DIR),
                      "agentic_manager", "period.py")


def run_script(*args):
    """(exit code, stdout, stderr) of the script."""
    proc = subprocess.run([sys.executable, SCRIPT, *args],
                          capture_output=True, text=True)
    return proc.returncode, proc.stdout, proc.stderr


class PeriodScriptTest(unittest.TestCase):
    def test_prints_the_period(self):
        code, out, err = run_script(
            "--start", "2026-01-01", "--end", "2026-06-30")
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(out), {"start": "2026-01-01", "end": "2026-06-30",
                                           "shown": "01/01/2026 to 30/06/2026"})
        code, out, err = run_script("--last-months", "3")
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(out)["end"], date.today().isoformat())

    def test_failures(self):
        # name: (arguments, exit code, expected on stderr)
        cases = [("both ways", ["--last-months", "3", "--start", "2026-01-01"], 2, "not both"),
                 ("not a date", ["--start", "01/01/2026",
                  "--end", "2026-06-30"], 2, "YYYY-MM-DD"),
                 ("ends after today", [
                  "--start", "2026-01-01", "--end", "2999-01-01"], 1, "after today"),
                 ("no period", [], 1, "name the period")]
        for name, args, expected_code, expected in cases:
            with self.subTest(name):
                code, out, err = run_script(*args)
                self.assertEqual((code, out), (expected_code, ""))
                self.assertIn(expected, err)


if __name__ == "__main__":
    unittest.main()
