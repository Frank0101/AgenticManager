"""Unit tests for skills/agentic-manager-jira-sprint-report/scripts/prepare_report.py.
Run with: python3 tests/run.py agentic-manager-jira-sprint-report

The scripts it runs are replaced by fakes; test_e2e_fetch.py runs the whole
script against a fake Jira.
"""

import contextlib
import io
import json
import os
import subprocess
import sys
import unittest
from unittest import mock

# tests/<skill>/ mirrors skills/<skill>/.
TEST_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(TEST_DIR))
sys.path.insert(0, os.path.join(REPO_ROOT, "skills",
                os.path.basename(TEST_DIR), "scripts"))
import prepare_report  # noqa: E402

REPORT_DIR = "/out/jira-sprint-reports/PROJ_Sprint_7_26-03-16"
FETCHED = {"sprint_id": 7, "label": "PROJ_Sprint_7",
           "report_dir": REPORT_DIR, "temporary": False}


class RunTest(unittest.TestCase):
    def test_run(self):
        # A script's stdout on success; on failure, its stdout goes to stderr
        # and the run exits with its code.
        cases = [("success", 0, "out\n", None),
                 ("failure", 3, "what went wrong\n", 3)]
        for name, code, stdout, exits in cases:
            with self.subTest(name), mock.patch.object(prepare_report.subprocess, "run",
                                                       return_value=subprocess.CompletedProcess([], code, stdout)) as run:
                err = io.StringIO()
                with contextlib.redirect_stderr(err):
                    if exits is None:
                        self.assertEqual(prepare_report.run(
                            "make_brief.py", "--report-dir", "x"), stdout)
                    else:
                        with self.assertRaises(SystemExit) as raised:
                            prepare_report.run(
                                "make_brief.py", "--report-dir", "x")
                        self.assertEqual(raised.exception.code, exits)
                self.assertEqual(
                    err.getvalue(), "" if exits is None else stdout)
                command = run.call_args.args[0]
                self.assertEqual((command[0], os.path.basename(command[1]), command[2:]),
                                 (sys.executable, "make_brief.py", ["--report-dir", "x"]))


class MainTest(unittest.TestCase):
    def main(self, *argv):
        """(stdout, stderr, the scripts run with their arguments)."""
        runs = []

        def run(script, *args):
            runs.append((script, *args))
            return {"fetch_sprint.py": "progress line\n" + json.dumps(FETCHED) + "\n",
                    "build_sprint_data.py": "wrote data.json\n"}.get(script, "")
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(prepare_report, "run", side_effect=run), \
                mock.patch.object(sys, "argv", ["prepare_report.py", *argv]), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            prepare_report.main()
        return out.getvalue(), err.getvalue(), runs

    def test_runs_the_steps_in_order(self):
        out, err, runs = self.main("--project", "PROJ")
        self.assertEqual(runs, [("fetch_sprint.py", "--project", "PROJ"),
                                ("build_sprint_data.py",
                                 "--report-dir", REPORT_DIR),
                                ("make_brief.py", "--report-dir", REPORT_DIR)])
        # One line of JSON: the fetch's, plus the brief and content.json's
        # path for output_file.py; the build's summary goes to stderr.
        self.assertEqual(len(out.splitlines()), 1)
        self.assertEqual(json.loads(out), {**FETCHED, "brief": os.path.join(REPORT_DIR, "brief.json"),
                                           "content_path": "PROJ_Sprint_7_26-03-16/content.json"})
        self.assertEqual(err, "wrote data.json\n")


if __name__ == "__main__":
    unittest.main()
