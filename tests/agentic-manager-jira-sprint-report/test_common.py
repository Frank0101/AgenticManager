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
        for name in ("ISSUE_KEY", "JiraClient", "key_order", "nested", "parse_ts", "plain_text", "value_at"):
            self.assertIs(getattr(common, name), getattr(jira, name))
        self.assertIs(common.output_folder, output_folder.output_folder)


class ReportTimezoneTest(unittest.TestCase):
    def test_named_timezone(self):
        zone = common.report_timezone("Europe/London")
        for stamp, expected in [("2026-01-10T12:00:00Z", 0),
                                ("2026-07-10T12:00:00Z", 3600)]:
            with self.subTest(stamp=stamp):
                self.assertEqual(common.parse_ts(stamp).astimezone(
                    zone).utcoffset().total_seconds(), expected)

    def test_missing_or_unknown_timezone(self):
        for name in (None, "", " ", 3, "Missing/Zone", "/absolute"):
            with self.subTest(name=name), self.assertRaisesRegex(SystemExit, "reporting timezone"):
                common.report_timezone(name)


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
        # A changelog's sprint field is a comma-separated list, or empty.
        for value, expected in [(" 6, 7 ,", {"6", "7"}), ("", set()), (None, set())]:
            with self.subTest(value=value):
                self.assertEqual(common.split_ids(value), expected)

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
        # Before its creation the issue was in no sprint.
        before = "2026-02-28T10:00:00.000+0100"
        for instant, expected in [(before, False), (self.CREATED, True), (self.REMOVE, False), (self.ADD, True)]:
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
        # Changelogs give status ids as strings, the statuses list as numbers.
        self.assertEqual(common.status_categories(
            [{"id": 3, "statusCategory": {"key": "done"}}]), {"3": "done"})

    def test_history_fields(self):
        # Story points and Flagged are the site's own fields; the rest are Jira's names.
        self.assertEqual(common.history_fields("customfield_flag", "customfield_points"), {
            "sprint": "Sprint", "status": "status", "resolution": "resolution", "priority": "priority",
            "parent": "IssueParentAssociation", "points": "customfield_points", "flagged": "customfield_flag"})

    def test_as_of(self):
        # A closed sprint is reported as it closed, whatever the state's case;
        # any other sprint as it was at the fetch.
        closed = {"state": "Closed", "completeDate": "C", "endDate": "E"}
        cases = [(closed, "C"), ({**closed, "completeDate": None}, "E"),
                 ({"state": "active", "endDate": "E"}, "F"), ({"state": None}, "F")]
        for sprint, expected in cases:
            with self.subTest(sprint=sprint):
                self.assertEqual(common.as_of(sprint, "F"), expected)

    def test_status_at(self):
        # Done on the 4th, moved to Duplicate on the 6th, reopened on the 9th.
        history = self.history(self.raw(), [self.moved(4, "3", "10"), self.moved(6, "10", "11"),
                                            self.moved(9, "11", "1")])
        cases = [(3, ("In Progress", "indeterminate")), (5, ("Done", "done")),
                 (7, ("Duplicate", "done")), (10, ("To Do", "new"))]
        for day, status in cases:
            with self.subTest(day=day):
                self.assertEqual(history.status_at(self.at(day)), status)
                self.assertEqual(history.done_at(
                    self.at(day)), status[1] == "done")

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
        # With no changelog the current fields held throughout; without the
        # site's points or Flagged field the issue has no estimate and no flag.
        unset = self.history(self.raw(customfield_points=8.0, priority=None), [])
        self.assertEqual(unset.state_at(self.at(5)), {
            "status": "To Do", "statusCategory": "new", "resolution": None, "storyPoints": None,
            "flagged": False, "priority": "", "parentId": None, "parentKey": None})

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

    def test_report_file(self):
        self.assertEqual(common.report_file("PROJ_Sprint_7"),
                         "PROJ_Sprint_7_Sprint_Report.md")

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
        # A step run out of order names the file it lacks, not a traceback.
        with self.assertRaisesRegex(SystemExit, "missing /no/such/file.json"):
            common.load_json("/no/such/file.json")

    def test_report_label(self):
        # The key is prefixed unless the name starts with it, in any case; each
        # run of characters unsafe in a file name becomes one underscore.
        cases =[("PROJ", "Sprint 3", "PROJ_Sprint_3"), ("PROJ", "proj sprint 3", "proj_sprint_3"),
                 ("PROJ", "Q1: Login / Search!", "PROJ_Q1_Login_Search"), (None, None, "Sprint")]
        for project, name, expected in cases:
            with self.subTest(name=name):
                self.assertEqual(common.report_label(project, name), expected)


class QuantitiesTest(unittest.TestCase):
    def test_formats(self):
        # Each figure has one shape in every part of the report. Exactly 1 is
        # singular, 1.0 too; 0 is plural; no estimate is "–", never 0.
        cases = [
            (common.number, (3.0,), "3"), (common.number, (2.5,), "2.5"), (common.number, (4,), "4"),
            (common.plural, (0, "it", "they"), "they"), (common.plural, (1, "it", "they"), "it"),
            (common.plural, (1.0, "it", "they"), "it"), (common.plural, (2, "it", "they"), "they"),
            (common.unit, (1,), "ticket"), (common.unit, (0,), "tickets"), (common.unit, (2,), "tickets"),
            (common.pts, (1,), "1 pt"), (common.pts, (1.0,), "1 pt"), (common.pts, (2.0,), "2 pts"),
            (common.pts, (0.5,), "0.5 pts"), (common.pts, (0,), "0 pts"), (common.pts, (None,), "– pts"),
            (common.qty, (1, 3.0), "1 ticket (3 pts)"), (common.qty, (7, 7), "7 tickets (7 pts)"),
            (common.qty, (4, None), "4 tickets (– pts)"),
            # The unit follows the total: "1/1 ticket", "0/2 tickets".
            (common.ratio, (11, 22, 34, 74), "11/22 tickets (34/74 pts)"),
            (common.ratio, (1, 1, 2.0, 2), "1/1 ticket (2/2 pts)"),
            (common.ratio, (0, 2, 0, 1), "0/2 tickets (0/1 pts)"),
            (common.ticket_ref, ("PROJ-20", 2), "PROJ-20 (2 pts)"),
            (common.ticket_ref, ("PROJ-13", None), "PROJ-13 (– pts)"),
            (common.estimate, (5,), "5"), (common.estimate, (2.0,), "2"), (common.estimate, (0,), "0"),
            (common.estimate, (None,), "–"),
            # A share above zero never reads 0%; nothing to share is n/a.
            (common.whole_percentage, (1, 3), "33%"), (common.whole_percentage, (2, 3), "67%"),
            (common.whole_percentage, (2, 4), "50%"), (common.whole_percentage, (5, 5), "100%"),
            (common.whole_percentage, (0, 5), "0%"), (common.whole_percentage, (1, 300), "<1%"),
            (common.whole_percentage, (1, 200), "<1%"), (common.whole_percentage, (1, 0), "n/a"),
            # Just short of the whole never reads as all of it.
            (common.whole_percentage, (199, 200), ">99%"), (common.whole_percentage, (299, 300), ">99%"),
            (common.whole_percentage, (99, 100), "99%"),
            (common.display_date, ("2026-03-02",), "02/03/2026"),
        ]
        for function, args, expected in cases:
            with self.subTest(function=function.__name__, args=args):
                self.assertEqual(function(*args), expected)


class VocabularyTest(unittest.TestCase):
    def test_banned_words(self):
        # Whole words only, in any case: "history", "issued" or "someone" are
        # fine, and a hyphen splits "twenty-one" into two spelled-out numbers.
        cases = [
            ("3 tickets (5 pts) completed; the history of the issued fix, by someone", []),
            ("Two stories and one issue", [("story or stories", ["stories"]), ("issue or issues", ["issue"]),
                                           ("spelled-out numbers (write digits)", ["Two", "one"])]),
            ("A point, then twenty-one Points", [("points (write pts)", ["point", "Points"]),
                                                 ("spelled-out numbers (write digits)", ["twenty", "one"])]),
            ("The Story was Closed", [("story or stories", ["Story"]),
                                      ("closed (write completed, or at the close)", ["Closed"])]),
        ]
        for text, expected in cases:
            with self.subTest(text):
                self.assertEqual(common.banned_words(text), expected)

    def test_word_count(self):
        # A link counts as its text, never its URL; hyphenated words count once.
        cases = [("JavaScript and per-market", 3), ("[PROJ-1 fix](https://acme.test/browse/PROJ-1) done", 3),
                 ("a  b\nc", 3), ("", 0)]
        for text, expected in cases:
            with self.subTest(text):
                self.assertEqual(common.word_count(text), expected)

    def test_ai_label_follows_the_title(self):
        # The label is a note after the title, sized in rem so it reads the same
        # after a heading and in a table cell.
        self.assertEqual(common.ai("Goal outcome"),
                         'Goal outcome <sup style="font-size:0.6rem;font-weight:normal">[AI Gen.]</sup>')


class ScopeGroupsTest(unittest.TestCase):
    def test_scope_group_label(self):
        # Not completed work reads "Open" only while the sprint runs.
        cases = [("completed", "active", "Completed"), ("in_review", "closed", "In review"),
                 ("not_completed", "active", "Open"), ("not_completed", "closed", "Not completed"),
                 ("descoped", "active", "Descoped")]
        for group, status, expected in cases:
            with self.subTest(group=group, status=status):
                self.assertEqual(common.scope_group_label(group, status), expected)

    def test_epic_groups(self):
        # Only groups with tickets, always in the report's order.
        epic = {"scope_groups": {"descoped": ["PROJ-2"], "not_completed": [], "in_review": [],
                                 "completed": ["PROJ-1"]}}
        self.assertEqual(common.epic_groups(epic), ["completed", "descoped"])

    def test_outcome_total(self):
        # A row's work however it ended, descoped included; other rows don't count.
        breakdown = {"original_completed": 3, "original_not_completed": 2, "original_removed": 1,
                     "extra_completed": 5, "extra_not_completed": 0, "extra_removed": 0}
        self.assertEqual(common.outcome_total(breakdown, "original"), 6)


class TargetCompletionTest(unittest.TestCase):
    def test_target_completion(self):
        def ticket(key, scope="original", outcome="completed"):
            return {"key": key, "scope": scope, "outcome": outcome}
        data = {"spells": [ticket("PROJ-1"), ticket("PROJ-2", outcome="not_completed"),
                           ticket("PROJ-3", scope="extra"), ticket("PROJ-4", outcome="removed")]}
        self.assertEqual(common.target_completion(
            data), (["PROJ-1"], ["PROJ-1", "PROJ-2", "PROJ-4"]))


class AllowedVerdictsTest(unittest.TestCase):
    def test_allowed_verdicts(self):
        # A 10-day sprint, 02/03 to 12/03: its halfway day is 07/03.
        def data(status="active", today="2026-03-06", goal="Ship login"):
            return {"sprint_status": status, "sprint_goal": goal, "sprint_start": "2026-03-02",
                    "sprint_end": "2026-03-12", "today": today}
        cases = [
            # The day before halfway, or before the start, is too early.
            (data(), ("Too early to tell",)),
            (data(today="2026-03-01"), ("Too early to tell",)),
            # From the halfway day on, including a sprint running past its end.
            (data(today="2026-03-07"), ("On track", "At risk")),
            (data(today="2026-03-20"), ("On track", "At risk")),
            # The halfway day is a whole day: with an odd span its midpoint
            # is at noon, and the morning of that day can be judged too.
            ({**data(today="2026-03-06"), "sprint_end": "2026-03-11"}, ("On track", "At risk")),
            # A closed sprint is judged whenever it closed.
            (data(status="closed"), ("Fully met", "Partially met", "Not met")),
            # No goal leaves nothing to judge, closed or not.
            (data(goal=""), ("No goal set in Jira for this sprint",)),
            (data(status="closed", goal=""), ("No goal set in Jira for this sprint",)),
        ]
        for case, expected in cases:
            with self.subTest(case):
                self.assertEqual(common.allowed_verdicts(case), expected)


if __name__ == "__main__":
    unittest.main()
