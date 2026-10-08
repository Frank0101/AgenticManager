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

    def test_arguments(self):
        # Each case is the parsed selectors, or, for arguments refused as a
        # usage error, the message: conflicting selectors fail rather than
        # one silently winning.
        cases = [
            (("--sprint-id", "7"), {"sprint_id": "7"}),
            (("--project", "PROJ", "--active"),
             {"project": "PROJ", "active": True}),
            (("--board", "42"), {"board": "42"}),
            (("--sprint-name", "Sprint 3", "--board", "42"),
             {"sprint_name": "Sprint 3", "board": "42"}),
            (("--sprint-name", "Sprint 3", "--project", "PROJ"),
             {"sprint_name": "Sprint 3", "project": "PROJ", "active": False}),
            ((), "pass exactly one of --sprint-id, --project or --board"),
            (("--sprint-id", "7", "--board", "42"),
             "pass exactly one of --sprint-id, --project or --board"),
            (("--sprint-name", "S", "--sprint-id", "7"),
             "--sprint-name can't be combined with --sprint-id"),
            (("--sprint-name", "S"),
             "--sprint-name needs exactly one of --project or --board"),
            (("--sprint-name", "S", "--project", "PROJ", "--board", "42"),
             "--sprint-name needs exactly one of --project or --board"),
            (("--sprint-name", "S", "--board", "42", "--active"),
             "--active can't be combined with --sprint-name"),
            (("--sprint-id", "7", "--active"),
             "--active applies only to --project or --board"),
            # Report folders always go in the skill's output folder.
            (("--sprint-id", "7", "--out-root", "reports"),
             "unrecognized arguments: --out-root"),
        ]
        for args, expected in cases:
            with self.subTest(args=args):
                if isinstance(expected, dict):
                    parsed = self.parse(*args)
                    self.assertEqual({k: getattr(parsed, k)
                                     for k in expected}, expected)
                    continue
                err = io.StringIO()
                with contextlib.redirect_stderr(err), self.assertRaises(SystemExit) as raised:
                    self.parse(*args)
                self.assertEqual(raised.exception.code, 2)
                self.assertIn(expected, err.getvalue())


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

    def broken(self, name, text):
        raw = os.path.join(self.root, name, "_raw")
        os.makedirs(raw)
        with open(os.path.join(raw, "sprint.json"), "w", encoding="utf-8") as f:
            f.write(text)
        return os.path.join(self.root, name)

    def test_stored_sprint_id(self):
        # A folder that isn't a readable report is never taken for one.
        cases = [("a report", self.report("a", 7), "7"),
                 ("no folder", os.path.join(self.root, "missing"), None),
                 ("a sprint.json that isn't an object",
                  self.broken("list", "[]"), None),
                 ("a sprint.json that isn't JSON", self.broken("text", "{"), None)]
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
        # Only real folders of this sprint go: never another sprint's report,
        # nor a report elsewhere that a link in the folder points to.
        earlier = self.report("PROJ_Sprint_7_26-03-13", 7)
        other = self.report("PROJ_Sprint_6_26-02-27", 6)
        same_name = self.report("PROJ_Sprint_7_26-03-16", 7)
        outside = tempfile.TemporaryDirectory()
        self.addCleanup(outside.cleanup)
        linked = os.path.join(outside.name, "PROJ_Sprint_7_26-03-01")
        os.makedirs(os.path.join(linked, "_raw"))
        with open(os.path.join(linked, "_raw", "sprint.json"), "w", encoding="utf-8") as f:
            json.dump({"id": 7}, f)
        os.symlink(linked, os.path.join(self.root, "link"))
        self.prepare("PROJ_Sprint_7_26-03-16", 7)
        self.assertFalse(os.path.exists(earlier))
        self.assertTrue(os.path.exists(other))
        self.assertTrue(os.path.islink(os.path.join(self.root, "link")))
        self.assertTrue(os.path.exists(
            os.path.join(linked, "_raw", "sprint.json")))
        self.assertEqual(os.listdir(os.path.join(same_name, "_raw")), [])
        self.assertEqual(sorted(self.logged), [f"deleting earlier report: {earlier}",
                                               f"deleting earlier report: {same_name}"])

    def test_refuses_to_delete_another_sprints_report(self):
        self.report("PROJ_Sprint_7_26-03-16", 6)
        with self.assertRaisesRegex(SystemExit, "it holds the report of sprint 6"):
            self.prepare("PROJ_Sprint_7_26-03-16", 7)

    def test_replaces_a_file_or_link_in_the_way(self):
        # Whatever holds the destination's name is removed, but a link is
        # removed itself, never what it points to.
        elsewhere = os.path.join(self.root, "elsewhere")
        os.makedirs(elsewhere)
        cases = [("a file", lambda path: open(path, "w").close()),
                 ("a link to a folder", lambda path: os.symlink(elsewhere, path)),
                 ("a broken link", lambda path: os.symlink(os.path.join(self.root, "gone"), path))]
        for sprint_id, (name, make) in enumerate(cases, start=7):
            with self.subTest(name):
                target = os.path.join(self.root, f"PROJ_Sprint_{sprint_id}")
                make(target)
                self.prepare(f"PROJ_Sprint_{sprint_id}", sprint_id)
                self.assertFalse(os.path.islink(target))
                self.assertTrue(os.path.isdir(os.path.join(target, "_raw")))
        self.assertTrue(os.path.isdir(elsewhere))


class PreviousSprintTest(unittest.TestCase):
    def test_previous_sprint(self):
        def sprint(sprint_id, start, state="closed", board=42, completed=True):
            return {"id": sprint_id, "state": state, "startDate": start and f"2026-{start}T09:00:00.000Z",
                    "completeDate": f"2026-{start}T10:00:00.000Z" if state == "closed" and completed else None,
                    "originBoardId": board}
        current = sprint(7, "03-04", state="active")
        cases = [
            ("the latest start before this one", current,
             [sprint(5, "02-04"), sprint(6, "02-18"), current], 6),
            # After a team moves board, its earlier sprints keep the old origin.
            ("from another board, after a move to this one",
             current, [sprint(6, "02-18", board=41)], 6),
            ("still running", current, [
             sprint(5, "02-04"), sprint(6, "02-18", state="active")], 5),
            ("closed without a completion date", current,
             [sprint(5, "02-04"), sprint(6, "02-18", completed=False)], 5),
            ("started after this one", current, [
             sprint(5, "02-04"), sprint(8, "03-18")], 5),
            ("none before it", current, [sprint(8, "03-18")], None),
            ("a sprint never started", sprint(
                7, None, state="active"), [sprint(6, "02-18")], None),
        ]
        for name, this, sprints, expected in cases:
            with self.subTest(name):
                previous = fetch_sprint.previous_sprint(this, sprints)
                self.assertEqual(previous and previous["id"], expected)


class HelpersTest(unittest.TestCase):
    def test_comments_as_of(self):
        before = "2026-03-13T15:59:59Z"
        cutoff = "2026-03-13T16:00:00Z"
        after = "2026-03-13T16:00:01Z"
        cases = [
            ({"created": before, "updated": before}, True),
            ({"created": before, "updated": cutoff}, True),
            ({"created": before, "updated": after}, False),
            ({"created": cutoff, "updated": cutoff}, True),
            ({"created": after, "updated": before}, False),
            ({"created": before}, True),
            ({"created": cutoff}, True),
            ({"created": after}, False),
            ({"created": before, "updated": None}, True),
            ({"updated": after}, False),
            ({}, True),
        ]
        for dates, included in cases:
            with self.subTest(dates=dates):
                comment = {**dates, "body": "Waiting on a dependency."}
                self.assertEqual(fetch_sprint.comments_as_of(
                    [comment], fetch_sprint.parse_ts(cutoff)), [comment] if included else [])

    def test_project_key_of(self):
        # --project wins; otherwise an issue key up to its last hyphen; with
        # neither, no key.
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
