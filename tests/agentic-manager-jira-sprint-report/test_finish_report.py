"""Unit tests for skills/agentic-manager-jira-sprint-report/scripts/finish_report.py.
Run with: python3 tests/run.py agentic-manager-jira-sprint-report

The steps it calls are replaced by fakes; test_e2e_pipeline.py runs the
whole script on a made-up sprint.
"""

import contextlib
import io
import json
import os
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
from check_report import Checker  # noqa: E402


def checker(*failures):
    """A Checker with one passing check and `failures`."""
    found = Checker()
    found.check(True, "a", "fine")
    for failure in failures:
        found.check(False, "b", failure)
    return found


class FinishReportTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = tmp.name
        with open(os.path.join(self.dir, "data.json"), "w", encoding="utf-8") as f:
            json.dump({"label": "PROJ_Sprint_7"}, f)
        self.report = os.path.join(self.dir, "PROJ_Sprint_7_Sprint_Report.md")

    def finish(self, steps):
        """(exit code, stdout, the steps run), each step doing what `steps`
        gives it: an exception to raise, or a result to return."""
        runs = []

        def step(name, default):
            def run(*args):
                runs.append(name)
                self.assertEqual(args[0], self.dir)
                outcome = steps.get(name, default)
                if isinstance(outcome, BaseException):
                    raise outcome
                return outcome
            return run
        out = io.StringIO()
        with mock.patch.object(finish_report, "write_report", side_effect=step("report", self.report)), \
                mock.patch.object(finish_report, "write_charts", side_effect=step("charts", [])), \
                mock.patch.object(finish_report, "check_report", side_effect=step("check", checker())), \
                mock.patch.object(sys, "argv", ["finish_report.py", "--report-dir", self.dir]), \
                contextlib.redirect_stdout(out), self.assertRaises(SystemExit) as raised:
            finish_report.main()
        return raised.exception.code, out.getvalue(), runs

    def test_outcomes(self):
        # name: (what the steps do, exit code, what is printed, steps run)
        everything = ["report", "charts", "check"]
        cases = [
            ("passing", {}, 0, f"all 1 checks passed\nreport: {self.report}\n", everything),
            # Only the failures, the summary and the path: not the passes.
            ("failed checks", {"check": checker("broken")}, 1,
             f"  FAIL  b: broken\n1 check(s) failed\nreport (inspect the failed checks before rerunning): {self.report}\n",
             everything),
            # content.json's problems stop the run before the report is checked.
            ("bad content", {"report": SystemExit("content.json:\n  - problem")}, 1,
             "content.json:\n  - problem\n", ["report"]),
            ("charts fail", {"charts": SystemExit("burndown check failed")}, 1,
             "burndown check failed\n", ["report", "charts"]),
        ]
        for name, steps, code, printed, runs in cases:
            with self.subTest(name):
                self.assertEqual(self.finish(steps), (code, printed, runs))

    def test_a_crash_is_shown_whole(self):
        # A crash isn't content.json's fault: it stops the run as it is.
        with self.assertRaises(KeyError):
            self.finish({"check": KeyError("x")})


if __name__ == "__main__":
    unittest.main()
