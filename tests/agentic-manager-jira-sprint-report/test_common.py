# Unit tests for skills/agentic-manager-jira-sprint-report/scripts/common.py.
# Run with: python3 tests/run.py agentic-manager-jira-sprint-report
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
import common  # noqa: E402
from agentic_manager import output_file  # noqa: E402


class LibraryTest(unittest.TestCase):
    def test_library_names_are_importable_from_here(self):
        from agentic_manager import jira, output_folder
        for name in ("ISSUE_KEY", "JiraClient", "date_only", "key_order", "nested", "parse_ts", "value_at"):
            self.assertIs(getattr(common, name), getattr(jira, name))
        self.assertIs(common.output_folder, output_folder.output_folder)


class BlockerCandidateTest(unittest.TestCase):
    def test_is_blocker_candidate(self):
        cases = [((True, "Done", "done", "Low"), True),
                 ((False, "On Hold", "indeterminate", "Low"), True),
                 ((False, "BLOCKED", "done", None), True),
                 ((False, "In Progress", "indeterminate", "High"), True),
                 ((False, "Done", "done", "Highest"), False),
                 ((False, "In Progress", "indeterminate", "Medium"), False),
                 ((False, None, None, None), False)]
        for args, expected in cases:
            with self.subTest(args=args):
                self.assertIs(common.is_blocker_candidate(*args), expected)


class SprintEventsTest(unittest.TestCase):
    def test_split_ids(self):
        self.assertEqual(common.split_ids(" 6, 7 ,"), {"6", "7"})
        self.assertEqual(common.split_ids(None), set())

    def test_add_and_remove_events(self):
        def sprint(created, old, new):
            return {"created": created, "field": "sprint", "from": old, "to": new}
        events = [
            sprint("2026-03-04T10:00:00.000+0100", "7", "8"),
            sprint("2026-03-03T10:00:00.000+0100", "6", "6, 7"),
            sprint("2026-03-01T10:00:00.000+0100", "", "6"),
            sprint("2026-03-05T10:00:00.000+0100", "8", "8, 9"),
            # Another field's ids are never sprint moves.
            {"created": "2026-03-06T10:00:00.000+0100",
                "field": "status", "from": "", "to": "7"},
        ]
        self.assertEqual(common.add_and_remove_events(events, "7"),
                         (["2026-03-03T10:00:00.000+0100"], ["2026-03-04T10:00:00.000+0100"]))


class SprintMovesTest(unittest.TestCase):
    CREATED = "2026-03-01T10:00:00.000+0100"
    ADD = "2026-03-03T10:00:00.000+0100"
    REMOVE = "2026-03-02T10:00:00.000+0100"

    def test_sprint_moves(self):
        # The creation counts as the first add when no add comes first.
        cases = [
            ("in time order", [self.ADD], [self.REMOVE],
             [(1, self.CREATED), (-1, self.REMOVE), (1, self.ADD)]),
            ("no moves", [], [], [(1, self.CREATED)]),
            ("an add first", [self.ADD], [], [(1, self.ADD)]),
        ]
        for name, added, removed, expected in cases:
            with self.subTest(name):
                moves = common.sprint_moves(added, removed, self.CREATED)
                self.assertEqual([(move, ts)
                                 for _, move, ts in moves], expected)

    def test_issue_moves(self):
        raw = {"key": "PROJ-1", "fields": {"created": self.CREATED}}
        changes = [{"created": self.REMOVE, "field": "sprint", "from": "7", "to": ""},
                   {"created": self.ADD, "field": "sprint", "from": "", "to": "7"}]
        self.assertEqual([(move, ts) for _, move, ts in common.issue_moves(raw, changes, "7")],
                         [(1, self.CREATED), (-1, self.REMOVE), (1, self.ADD)])

    def test_membership_at_exact_instants(self):
        moves = common.sprint_moves([self.ADD], [self.REMOVE], self.CREATED)
        for instant, expected in [(self.CREATED, True), (self.REMOVE, False), (self.ADD, True)]:
            with self.subTest(instant=instant):
                self.assertIs(common.in_sprint_at(
                    moves, common.parse_ts(instant)), expected)


class HistoryTest(unittest.TestCase):
    CATEGORIES = {"1": "new", "3": "indeterminate", "10": "done", "11": "done"}

    def raw(self, status=("1", "To Do", "new"), **fields):
        return {"key": "PROJ-1", "fields": {
            "created": "2026-03-01T10:00:00.000+0100",
            "status": {"id": status[0], "name": status[1], "statusCategory": {"key": status[2]}},
            "resolution": None, "priority": {"name": "Medium"}, "parent": None, **fields}}

    def moved(self, day, old, new, names=("To Do", "In Progress", "Done", "Duplicate")):
        by_id = dict(zip(("1", "3", "10", "11"), names))
        return {"created": f"2026-03-{day:02d}T10:00:00.000+0100", "field": "status",
                "from": old, "fromString": by_id[old], "to": new, "toString": by_id[new]}

    def at(self, day):
        return common.parse_ts(f"2026-03-{day:02d}T12:00:00.000+0100")

    def history(self, raw, changes, flagged=None, points=None):
        return common.History(raw, changes, self.CATEGORIES, flagged, points)

    def test_points_value(self):
        for value, expected in [(None, None), ("", None), (3.0, 3), ("2", 2), ("2.5", 2.5)]:
            with self.subTest(value=value):
                points = common.points_value(value)
                self.assertEqual(points, expected)
                self.assertIs(type(points), type(expected))

    def test_status_categories(self):
        self.assertEqual(common.status_categories(
            [{"id": 3, "statusCategory": {"key": "done"}}]), {"3": "done"})

    def test_as_of(self):
        closed = {"state": "closed", "completeDate": "C", "endDate": "E"}
        cases = [(closed, "C"), ({**closed, "completeDate": None}, "E"),
                 ({"state": "active", "endDate": "E"}, "F")]
        for sprint, expected in cases:
            with self.subTest(sprint=sprint):
                self.assertEqual(common.as_of(sprint, "F"), expected)

    def test_status_and_completion_at(self):
        # Done on the 4th, moved to Duplicate on the 6th, reopened on the 9th.
        history = self.history(self.raw(), [self.moved(4, "3", "10"), self.moved(6, "10", "11"),
                                            self.moved(9, "11", "1")])
        cases = [(3, ("In Progress", "indeterminate"), None),
                 (5, ("Done", "done"), "2026-03-04T10:00:00.000+0100"),
                 (7, ("Duplicate", "done"), "2026-03-04T10:00:00.000+0100"),
                 (10, ("To Do", "new"), None)]
        for day, status, completed in cases:
            with self.subTest(day=day):
                self.assertEqual(history.status_at(self.at(day)), status)
                self.assertEqual(history.completed_at(self.at(day)), completed)

    def test_reopened_at(self):
        # Done on the 4th, reopened on the 6th, Done again on the 8th, then moved
        # to Duplicate (still Done) and back to In Progress on the 12th.
        history = self.history(self.raw(), [self.moved(4, "3", "10"), self.moved(6, "10", "3"),
                                            self.moved(8, "3", "10"), self.moved(
                                                10, "10", "11"),
                                            self.moved(12, "11", "3")])
        cases = [("the first reopening", 3, 20, "2026-03-06T10:00:00.000+0100"),
                 ("not before the window", 6, 20, "2026-03-12T10:00:00.000+0100"),
                 ("not after the window", 3, 5, None),
                 ("up to and including the end of the window", 3, 6, "2026-03-06T10:00:00.000+0100")]
        for name, after, until, expected in cases:
            with self.subTest(name):
                self.assertEqual(history.reopened_at(
                    self.at(after), self.at(until)), expected)
        self.assertIsNone(self.history(
            self.raw(), []).reopened_at(self.at(1), self.at(20)))

    def test_created_done_completed_when_created(self):
        history = self.history(self.raw(status=("10", "Done", "done")), [])
        self.assertEqual(history.completed_at(self.at(5)),
                         "2026-03-01T10:00:00.000+0100")

    def test_state_at(self):
        raw = self.raw(customfield_points=8.0, customfield_flag=None,
                       resolution={"name": "Done"}, priority={"name": "Low"},
                       parent={"id": "200", "key": "PROJ-200"})
        changes = [
            {"created": "2026-03-08T10:00:00.000+0100", "field": "points",
             "from": None, "fromString": "3", "to": None, "toString": "8"},
            {"created": "2026-03-04T10:00:00.000+0100", "field": "flagged",
             "from": None, "fromString": None, "to": "[10000]", "toString": "Impediment"},
            {"created": "2026-03-08T10:00:00.000+0100", "field": "flagged",
             "from": "[10000]", "fromString": "Impediment", "to": None, "toString": None},
            {"created": "2026-03-08T10:00:00.000+0100", "field": "resolution",
             "from": None, "fromString": None, "to": "1", "toString": "Done"},
            {"created": "2026-03-08T10:00:00.000+0100", "field": "priority",
             "from": "2", "fromString": "High", "to": "4", "toString": "Low"},
            {"created": "2026-03-08T10:00:00.000+0100", "field": "parent",
             "from": "100", "fromString": "PROJ-100", "to": "200", "toString": "PROJ-200"},
        ]
        history = self.history(
            raw, changes, "customfield_flag", "customfield_points")
        self.assertEqual(history.state_at(self.at(5)), {
            "status": "To Do", "statusCategory": "new", "resolution": None, "storyPoints": 3,
            "flagged": True, "priority": "High", "parentId": "100", "parentKey": "PROJ-100"})
        self.assertEqual(history.state_at(self.at(9)), {
            "status": "To Do", "statusCategory": "new", "resolution": "Done", "storyPoints": 8,
            "flagged": False, "priority": "Low", "parentId": "200", "parentKey": "PROJ-200"})
        unset = self.history(raw, [])
        self.assertEqual((unset.state_at(self.at(5))["storyPoints"], unset.state_at(self.at(5))["flagged"]),
                         (None, False))

    def test_unknown_status(self):
        # Not in Jira's list of statuses: the current status's category, else a failure.
        history = self.history(self.raw(status=("50", "Custom", "indeterminate")),
                               [{"created": "2026-03-04T10:00:00.000+0100", "field": "status",
                                 "from": "60", "fromString": "Gone", "to": "50", "toString": "Custom"}])
        self.assertEqual(history.status_at(self.at(5)),
                         ("Custom", "indeterminate"))
        with self.assertRaisesRegex(SystemExit, "PROJ-1: status 60 is not in Jira's list of statuses"):
            history.status_at(self.at(3))


class FilesTest(unittest.TestCase):
    def test_report_file(self):
        self.assertEqual(common.report_file("PROJ_Sprint_7"),
                         "PROJ_Sprint_7_Sprint_Report.md")

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = os.path.realpath(tmp.name)
        self.folder = os.path.join(self.tmp, "jira-sprint-reports")
        os.makedirs(self.folder)
        for module in (common, output_file):
            patcher = mock.patch.object(
                module, "output_folder", return_value=(self.folder, False))
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_write_and_load_json(self):
        path = os.path.join(self.folder, "PROJ_Sprint_7", "_raw", "data.json")
        common.write_json(path, {"x": [1]})
        self.assertEqual(common.load_json(path), {"x": [1]})
        with open(path, encoding="utf-8") as f:
            self.assertEqual(f.read(), json.dumps({"x": [1]}, indent=2))

    def test_nothing_is_written_outside_the_output_folder(self):
        os.symlink(self.tmp, os.path.join(self.folder, "link"))
        cases = [
            ("a sibling folder", os.path.join(self.tmp, "other", "data.json"),
             "where sprint reports are written"),
            ("the parent folder", os.path.join(self.tmp, "data.json"),
             "where sprint reports are written"),
            ("through a symbolic link", os.path.join(self.folder, "link", "data.json"),
             "where sprint reports are written"),
        ]
        for name, path, expected in cases:
            with self.subTest(name):
                with self.assertRaisesRegex(SystemExit, expected):
                    common.write_report_file(path, "{}")
                self.assertFalse(os.path.exists(path))

    def test_load_missing_json(self):
        with self.assertRaisesRegex(SystemExit, "missing /no/such/file.json"):
            common.load_json("/no/such/file.json")

    def test_report_label(self):
        cases = [("PROJ", "Sprint 3", "PROJ_Sprint_3"), ("PROJ", "proj sprint 3", "proj_sprint_3"),
                 ("PROJ", "Q1: Login / Search!", "PROJ_Q1_Login_Search"), (None, None, "Sprint")]
        for project, name, expected in cases:
            with self.subTest(name=name):
                self.assertEqual(common.report_label(project, name), expected)


class QuantitiesTest(unittest.TestCase):
    def test_number(self):
        self.assertEqual((common.number(3.0), common.number(
            2.5), common.number(4)), ("3", "2.5", "4"))

    def test_plural(self):
        self.assertEqual([common.plural(n, "it", "they") for n in (0, 1, 1.0, 2)],
                         ["they", "it", "it", "they"])

    def test_units(self):
        self.assertEqual((common.unit(1), common.unit(2)),
                         ("story", "stories"))
        self.assertEqual((common.pts(1), common.pts(2.0)), ("1 pt", "2 pts"))
        self.assertEqual(
            (common.points_text(1), common.points_text(0)), ("1 point", "0 points"))
        self.assertEqual(common.qty(1, 3.0), "1 story / 3 pts")

    def test_percentage(self):
        self.assertEqual([common.percentage(part, whole) for part, whole in ((1, 3), (2, 4), (1, 0))],
                         ["33.3%", "50%", "n/a"])

    def test_display_date(self):
        self.assertEqual(common.display_date("2026-03-02"), "02/03/2026")


class TargetCompletionTest(unittest.TestCase):
    def test_target_completion(self):
        def issue(key, extra=False, already=False):
            return {"key": key, "addedMidSprint": extra, "startState": {"done": already}}
        data = {"issues": [issue("PROJ-1"), issue("PROJ-2"), issue("PROJ-3", extra=True),
                           issue("PROJ-10", already=True), issue("PROJ-9", already=True)],
                "removed_issues": [issue("PROJ-4")],
                "scope_timeline": [{"completed_original_keys": ["PROJ-1"]},
                                   {"completed_original_keys": ["PROJ-4"]}]}
        closed, pool, excluded = common.target_completion(data)
        self.assertEqual(pool, ["PROJ-1", "PROJ-2", "PROJ-4"])
        self.assertEqual(closed, ["PROJ-1", "PROJ-4"])
        self.assertEqual(excluded, ["PROJ-9", "PROJ-10"])


if __name__ == "__main__":
    unittest.main()
