# Unit tests for skills/agentic-manager-jira-sprint-report/scripts/finish_report.py.
# Run with: python3 tests/run.py agentic-manager-jira-sprint-report
#
# The scripts it runs are replaced by fakes; test_e2e_pipeline.py runs the
# whole script on a made-up sprint.
import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

# tests/<skill>/ mirrors skills/<skill>/.
TEST_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(TEST_DIR))
sys.path.insert(0, os.path.join(REPO_ROOT, "skills",
                os.path.basename(TEST_DIR), "scripts"))
import finish_report  # noqa: E402

PASSED = "  ok    a: fine\n\nall 1 checks passed\n"
FAILED = "  ok    a: fine\n  FAIL  b: broken\n\n1 check(s) failed\n"
CRASHED = "Traceback (most recent call last):\nKeyError: 'x'\n"


class FinishReportTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = tmp.name
        with open(os.path.join(self.dir, "data.json"), "w", encoding="utf-8") as f:
            json.dump({"label": "PROJ_Sprint_7"}, f)
        self.report = os.path.join(self.dir, "PROJ_Sprint_7_Sprint_Report.md")

    def finish(self, results):
        """(exit code, stdout, the scripts run) with each script's (code, output)
        from `results`, (0, "") when it has none."""
        runs = []

        def run(script, report_dir):
            runs.append(script)
            self.assertEqual(report_dir, self.dir)
            code, output = results.get(script, (0, ""))
            return subprocess.CompletedProcess([], code, output)
        out = io.StringIO()
        with mock.patch.object(finish_report, "run", side_effect=run), \
                mock.patch.object(sys, "argv", ["finish_report.py", "--report-dir", self.dir]), \
                contextlib.redirect_stdout(out), self.assertRaises(SystemExit) as raised:
            finish_report.main()
        return raised.exception.code, out.getvalue(), runs

    def test_outcomes(self):
        # name: (each script's code and output, exit code, what is printed, scripts run)
        everything = ["make_charts.py", "make_report.py", "check_report.py"]
        cases = [
            ("passing", {"check_report.py": (0, PASSED)}, 0,
             f"all 1 checks passed\nreport: {self.report}\n", everything),
            # Only the failures, the summary and the path: not the passes.
            ("failed checks", {"check_report.py": (1, FAILED)}, 1,
             f"  FAIL  b: broken\n1 check(s) failed\nreport (inspect the failed checks before rerunning): {self.report}\n",
             everything),
            # A crash isn't content.json's fault: shown whole, with no advice.
            ("crashed check", {"check_report.py": (
                1, CRASHED)}, 1, CRASHED, everything),
            # content.json's problems stop the run before the report is checked.
            ("bad content", {"make_report.py": (1, "content.json:\n  - problem\n")}, 1,
             "content.json:\n  - problem\n", ["make_charts.py", "make_report.py"]),
            ("charts fail", {"make_charts.py": (1, "burndown check failed\n")}, 1,
             "burndown check failed\n", ["make_charts.py"]),
        ]
        for name, results, code, printed, runs in cases:
            with self.subTest(name):
                self.assertEqual(self.finish(results), (code, printed, runs))

    def test_run(self):
        # Each script runs on the report folder, its stderr merged into stdout.
        with mock.patch.object(finish_report.subprocess, "run") as run:
            finish_report.run("make_charts.py", self.dir)
        command, kwargs = run.call_args.args[0], run.call_args.kwargs
        self.assertEqual((command[0], os.path.basename(command[1]), command[2:]),
                         (sys.executable, "make_charts.py", ["--report-dir", self.dir]))
        self.assertEqual((kwargs["stdout"], kwargs["stderr"]),
                         (subprocess.PIPE, subprocess.STDOUT))


if __name__ == "__main__":
    unittest.main()
