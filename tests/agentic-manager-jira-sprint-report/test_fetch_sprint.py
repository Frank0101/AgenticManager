# Unit tests for skills/agentic-manager-jira-sprint-report/scripts/fetch_sprint.py.
# Run with: python3 tests/run.py agentic-manager-jira-sprint-report
#
# They cover the script's own logic: its arguments and the report folder. The
# Jira calls belong to the library's client, tested there; test_e2e_fetch.py
# runs the whole script against a fake Jira.
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
import fetch_sprint  # noqa: E402


class ArgsTest(unittest.TestCase):
    def parse(self, *args):
        with mock.patch.object(sys, "argv", ["fetch_sprint.py", *args]):
            return fetch_sprint.parse_args()

    def assert_rejected(self, expected, *args):
        err = io.StringIO()
        with contextlib.redirect_stderr(err), self.assertRaises(SystemExit) as raised:
            self.parse(*args)
        self.assertEqual(raised.exception.code, 2)
        self.assertIn(expected, err.getvalue())

    def test_valid_selectors(self):
        cases = [
            (("--sprint-id", "7"), {"sprint_id": "7"}),
            (("--project", "PROJ", "--active"),
             {"project": "PROJ", "active": True}),
            (("--board", "42"), {"board": "42"}),
            (("--sprint-name", "Sprint 3", "--board", "42"),
             {"sprint_name": "Sprint 3", "board": "42"}),
        ]
        for args, expected in cases:
            with self.subTest(args=args):
                parsed = self.parse(*args)
                self.assertEqual({k: getattr(parsed, k)
                                 for k in expected}, expected)

    def test_conflicting_selectors(self):
        cases = [
            ("pass exactly one of --sprint-id, --project or --board", ()),
            ("pass exactly one of --sprint-id, --project or --board",
             ("--sprint-id", "7", "--board", "42")),
            ("--sprint-name can't be combined with --sprint-id",
             ("--sprint-name", "S", "--sprint-id", "7")),
            ("--sprint-name needs exactly one of --project or --board",
             ("--sprint-name", "S")),
            ("--sprint-name needs exactly one of --project or --board",
             ("--sprint-name", "S", "--project", "PROJ", "--board", "42")),
            ("--active can't be combined with --sprint-name",
             ("--sprint-name", "S", "--board", "42", "--active")),
            ("--active applies only to --project or --board",
             ("--sprint-id", "7", "--active")),
        ]
        for expected, args in cases:
            with self.subTest(args=args):
                self.assert_rejected(expected, *args)

    def test_the_reports_folder_cant_be_chosen(self):
        self.assert_rejected("unrecognized arguments: --out-root",
                             "--sprint-id", "7", "--out-root", "reports")


class ReportDirTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = self.tmp.name
        self.logged = []

    def report(self, name, sprint_id):
        raw = os.path.join(self.root, name, "_raw")
        os.makedirs(raw)
        with open(os.path.join(raw, "sprint.json"), "w", encoding="utf-8") as f:
            json.dump({"id": sprint_id}, f)
        return os.path.join(self.root, name)

    def prepare(self, name, sprint_id):
        return fetch_sprint.prepare_report_dir(self.root, os.path.join(self.root, name), sprint_id,
                                               self.logged.append)

    def test_stored_sprint_id(self):
        broken = os.path.join(self.root, "broken", "_raw")
        os.makedirs(broken)
        with open(os.path.join(broken, "sprint.json"), "w", encoding="utf-8") as f:
            f.write("[]")
        cases = [("a report", self.report("a", 7), "7"),
                 ("no folder", os.path.join(self.root, "missing"), None),
                 ("a sprint.json that isn't an object", os.path.dirname(broken), None)]
        for name, folder, expected in cases:
            with self.subTest(name):
                self.assertEqual(
                    fetch_sprint.stored_sprint_id(folder), expected)

    def test_new_folder(self):
        raw = self.prepare("PROJ_Sprint_7_26-03-16", 7)
        self.assertEqual(raw, os.path.join(
            self.root, "PROJ_Sprint_7_26-03-16", "_raw"))
        self.assertEqual(os.listdir(raw), [])
        self.assertEqual(self.logged, [])

    def test_earlier_reports_of_the_same_sprint_are_deleted(self):
        earlier = self.report("PROJ_Sprint_7_26-03-13", 7)
        other = self.report("PROJ_Sprint_6_26-02-27", 6)
        same_name = self.report("PROJ_Sprint_7_26-03-16", 7)
        self.prepare("PROJ_Sprint_7_26-03-16", 7)
        self.assertFalse(os.path.exists(earlier))
        self.assertTrue(os.path.exists(other))
        self.assertEqual(os.listdir(os.path.join(same_name, "_raw")), [])
        self.assertEqual(sorted(self.logged), [f"deleting earlier report: {earlier}",
                                               f"deleting earlier report: {same_name}"])

    def test_refuses_to_delete_another_sprints_report(self):
        self.report("PROJ_Sprint_7_26-03-16", 6)
        with self.assertRaisesRegex(SystemExit, "it holds the report of sprint 6"):
            self.prepare("PROJ_Sprint_7_26-03-16", 7)

    def test_replaces_a_file_or_link_in_the_way(self):
        target = os.path.join(self.root, "PROJ_Sprint_7_26-03-16")
        open(target, "w").close()
        self.prepare("PROJ_Sprint_7_26-03-16", 7)
        self.assertTrue(os.path.isdir(os.path.join(target, "_raw")))
        elsewhere = os.path.join(self.root, "elsewhere")
        os.makedirs(elsewhere)
        link = os.path.join(self.root, "PROJ_Sprint_8_26-03-30")
        os.symlink(elsewhere, link)
        self.prepare("PROJ_Sprint_8_26-03-30", 8)
        self.assertFalse(os.path.islink(link))
        self.assertTrue(os.path.isdir(elsewhere))


class PreviousSprintTest(unittest.TestCase):
    def test_previous_sprint(self):
        def sprint(sprint_id, start, state="closed", board=42):
            return {"id": sprint_id, "state": state, "startDate": f"2026-{start}T09:00:00.000Z",
                    "completeDate": f"2026-{start}T10:00:00.000Z" if state == "closed" else None,
                    "originBoardId": board}
        current = sprint(7, "03-04", state="active")
        cases = [
            ("the latest start before this one",
             [sprint(5, "02-04"), sprint(6, "02-18"), current], 6),
            ("from another board, after a move to this one", [sprint(6, "02-18", board=41)], 6),
            ("still running", [sprint(5, "02-04"), sprint(6, "02-18", state="active")], 5),
            ("started after this one", [sprint(5, "02-04"), sprint(8, "03-18")], 5),
            ("none before it", [sprint(8, "03-18")], None),
        ]
        for name, sprints, expected in cases:
            with self.subTest(name):
                previous = fetch_sprint.previous_sprint(current, sprints)
                self.assertEqual(previous and previous["id"], expected)
        self.assertIsNone(fetch_sprint.previous_sprint({"id": 7, "startDate": None}, [sprint(6, "02-18")]))


class HelpersTest(unittest.TestCase):
    def test_project_key_of(self):
        cases = [("PROJ", [], "PROJ"),
                 (None, [{"key": "ABC-DEF-12"}], "ABC-DEF"), (None, [], None)]
        for project, issues, expected in cases:
            with self.subTest(project=project, issues=issues):
                self.assertEqual(fetch_sprint.project_key_of(
                    mock.Mock(project=project), issues), expected)

    def test_log_goes_to_stderr(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            fetch_sprint.log("hello")
        self.assertEqual(err.getvalue(), "hello\n")


if __name__ == "__main__":
    unittest.main()
