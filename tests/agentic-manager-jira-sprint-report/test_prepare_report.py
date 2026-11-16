"""Unit tests for skills/agentic-manager-jira-sprint-report/scripts/prepare_report.py.
Run with: python3 tests/run.py agentic-manager-jira-sprint-report

The steps it runs are replaced by fakes; test_e2e_fetch.py runs the whole
script against a fake Jira.
"""

import contextlib
import io
import json
import os
import sys
import unittest
from unittest import mock

# tests/<skill>/ mirrors skills/<skill>/.
TEST_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(TEST_DIR))
sys.path.insert(0, os.path.join(REPO_ROOT, "skills",
                os.path.basename(TEST_DIR), "scripts"))
import prepare_report  # noqa: E402

REPORT_DIR = "/out/jira-sprint-reports/PROJ-Sprint-7_26-03-16"
FETCHED = {"sprint_id": 7, "label": "PROJ-Sprint-7",
           "report_dir": REPORT_DIR, "temporary": False}


class MainTest(unittest.TestCase):
    def main(self, *argv):
        """(stdout, stderr, the steps run with their arguments)."""
        runs = []

        def fetch(args):
            runs.append(("fetch", args.project))
            return dict(FETCHED)

        def build(report_dir):
            runs.append(("build", report_dir))
            return f"{report_dir}/data.json", ["original commitment: 1 spell(s)"]

        def brief(report_dir):
            runs.append(("brief", report_dir))
            return os.path.join(report_dir, "brief.json")
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(prepare_report, "fetch_sprint", side_effect=fetch), \
                mock.patch.object(prepare_report, "build_data", side_effect=build), \
                mock.patch.object(prepare_report, "write_brief", side_effect=brief), \
                mock.patch.object(sys, "argv", ["prepare_report.py", *argv]), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            prepare_report.main()
        return out.getvalue(), err.getvalue(), runs

    def test_runs_the_steps_in_order(self):
        out, err, runs = self.main("--project", "PROJ")
        self.assertEqual(runs, [("fetch", "PROJ"), ("build", REPORT_DIR),
                                ("brief", REPORT_DIR)])
        # One line of JSON: the fetch's, plus the brief and content.json's
        # path for output_file.py; the build's summary goes to stderr.
        self.assertEqual(len(out.splitlines()), 1)
        self.assertEqual(json.loads(out), {**FETCHED, "brief": os.path.join(REPORT_DIR, "brief.json"),
                                           "content_path": "PROJ-Sprint-7_26-03-16/content.json"})
        self.assertEqual(
            err, f"original commitment: 1 spell(s)\nwrote {REPORT_DIR}/data.json\n")

    def test_selectors_are_checked_first(self):
        # A usage error, as fetch_sprint.py gives it, before any step runs.
        err = io.StringIO()
        with mock.patch.object(prepare_report, "fetch_sprint") as fetch, \
                mock.patch.object(sys, "argv", ["prepare_report.py"]), \
                contextlib.redirect_stderr(err), self.assertRaises(SystemExit) as raised:
            prepare_report.main()
        self.assertEqual(raised.exception.code, 2)
        self.assertIn(
            "pass exactly one of --sprint-id, --project or --board", err.getvalue())
        fetch.assert_not_called()


if __name__ == "__main__":
    unittest.main()
