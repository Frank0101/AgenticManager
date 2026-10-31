"""Unit tests for skills/agentic-manager-jira-sprint-report/scripts/common.py.
Run with: python3 tests/run.py agentic-manager-jira-sprint-report
"""

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
from common import parse_ts  # noqa: E402
sys.path.insert(0, TEST_DIR)
from sprint_fixture import moved  # noqa: E402
from ticket_fixture import (CATEGORIES, CLOSE, FIELDS, PLUS_ONE, START, at, carried, changed, context,  # noqa: E402
                            done, events, flag, joined, left, points, raw)


class ChunksTest(unittest.TestCase):
    def test_chunks(self):
        # Each case: text, size, the pieces. A piece ends at the last line
        # break, else the last space, in its second half; with neither it is
        # cut at the size.
        cases = [
            ("short", "one two", 20, ["one two"]),
            ("empty", "", 20, [""]),
            ("at a line break", "aaaa bbbb\ncccc dddd\neeee ffff", 14,
             ["aaaa bbbb", "cccc dddd", "eeee ffff"]),
            ("at a space, with no line break", "aaaa bbbb cccc dddd", 12,
             ["aaaa bbbb", "cccc dddd"]),
            ("a break in the first half is not used", "a\nbbbbbbbbbbbbbbbbbbbb", 10,
             ["a\nbbbbbbbb", "bbbbbbbbbb", "bb"]),
            ("no break at all", "x" * 25, 10, ["x" * 10, "x" * 10, "x" * 5]),
        ]
        for name, text, size, expected in cases:
            with self.subTest(name):
                self.assertEqual(common.chunks(text, size), expected)

    def test_chunks_lose_no_word_and_respect_the_size(self):
        text = "\n".join(f"line {n} " + "w" * (n % 9) for n in range(300))
        pieces = common.chunks(text)
        self.assertGreater(len(pieces), 1)
        self.assertTrue(
            all(len(p) <= common.DESCRIPTION_CHUNK_CHARS for p in pieces))
        self.assertEqual(" ".join(" ".join(pieces).split()),
                         " ".join(text.split()))


class ReportTimezoneTest(unittest.TestCase):
    def test_report_timezone(self):
        # A named zone keeps its clock changes; anything else is refused
        # rather than read as UTC.
        zone = common.report_timezone("Europe/London")
        for stamp, expected in [("2026-01-10T12:00:00Z", 0),
                                ("2026-07-10T12:00:00Z", 3600)]:
            with self.subTest(stamp=stamp):
                offset = common.parse_ts(stamp).astimezone(zone).utcoffset()
                assert offset is not None
                self.assertEqual(offset.total_seconds(), expected)
        for name in (None, "", " ", 3, "Missing/Zone", "/absolute"):
            with self.subTest(name=name), self.assertRaisesRegex(SystemExit, "reporting timezone"):
                common.report_timezone(name)


class IssuesTest(unittest.TestCase):
    def test_standard_issues(self):
        # Sub-tasks are left out; an issue without a type counts as standard.
        issues = [{"key": "PROJ-1", "fields": {"issuetype": {"subtask": False}}},
                  {"key": "PROJ-2", "fields": {"issuetype": {"subtask": True}}},
                  {"key": "PROJ-3"}]
        self.assertEqual([i["key"] for i in common.standard_issues(issues)], [
                         "PROJ-1", "PROJ-3"])

    def test_spell_epic(self):
        cases = [({"parentKey": "PROJ-100", "parentSummary": "Sign-in"}, ("PROJ-100", "Sign-in")),
                 ({"parentKey": None, "parentSummary": None}, (common.NO_EPIC, common.NO_EPIC_NAME))]
        for spell, expected in cases:
            with self.subTest(spell=spell):
                self.assertEqual(common.spell_epic(spell), expected)


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


class ValuesTest(unittest.TestCase):
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

    def test_as_of(self):
        # A closed sprint is reported as it closed, whatever the state's case;
        # any other sprint as it was at the fetch.
        closed = {"state": "Closed", "completeDate": "C", "endDate": "E"}
        cases = [(closed, "C"), ({**closed, "completeDate": None}, "E"),
                 ({"state": "active", "endDate": "E"}, "F"), ({"state": None}, "F")]
        for sprint, expected in cases:
            with self.subTest(sprint=sprint):
                self.assertEqual(common.as_of(sprint, "F"), expected)


class DatesTest(unittest.TestCase):
    def test_sprint_date(self):
        cases = [
            ("converted to the site offset",
             "2026-03-01T23:30:00.000Z", "2026-03-02"),
            ("none", None, None),
            # 00:00 on the 8th at +01:00: the day Jira shows, the 8th, is the
            # sprint's last day, included.
            ("an end on midnight names the day Jira shows",
             "2026-03-07T23:00:00.000Z", "2026-03-08"),
            ("an end during the day", "2026-03-07T16:00:00.000Z", "2026-03-07"),
        ]
        for name, ts, expected in cases:
            with self.subTest(name):
                self.assertEqual(common.sprint_date(ts, PLUS_ONE), expected)


class TicketEventsTest(unittest.TestCase):
    """A ticket's events, and what they say at a past moment."""

    def test_events(self):
        # Each tracked field's value at creation is its first change's old
        # value, else today's; a change after the close is left out of the
        # events but still says what the value was at creation.
        issue = done("PROJ-1", points=5, parent="PROJ-100")
        changes = [joined(at("02-27")), points(at("03-03"), "2", "5"), moved(at("03-04"), "To Do", "Done"),
                   changed(at("03-05"), "parent", "PROJ-90",
                           "PROJ-100", "id-PROJ-90", "id-PROJ-100"),
                   moved(at("03-14"), "Done", "In Progress")]
        jira = {"source": "jira"}
        self.assertEqual(common.ticket_events(issue, changes, context(), CLOSE), [
            {"at": "2026-02-20T10:00:00.000+0100", "date": "2026-02-20", **jira, "type": "created", "values": {
                "sprint": [], "status": "To Do", "statusCategory": "new", "resolution": "Done", "priority": "Medium",
                "parent": "PROJ-90", "parentId": "id-PROJ-90", "points": 2, "flagged": False}},
            {"at": at("02-27"), "date": "2026-02-27", **jira,
             "type": "sprint_changed", "from": [], "to": ["7"]},
            {"at": at("03-03"), "date": "2026-03-03", **jira,
             "type": "points_changed", "from": 2, "to": 5},
            {"at": at("03-04"), "date": "2026-03-04", **jira, "type": "status_changed", "from": "To Do", "to": "Done",
             "fromCategory": "new", "toCategory": "done"},
            {"at": at("03-05"), "date": "2026-03-05", **jira, "type": "parent_changed", "from": "PROJ-90",
             "to": "PROJ-100", "fromId": "id-PROJ-90", "toId": "id-PROJ-100"}])

    def test_initial_sprints(self):
        # Jira logs no change for the sprints a ticket is created in: each
        # sprint whose first move isn't an add, and the reported sprint when
        # no change names it.
        def change(created, old, new):
            return {"created": created, "field": "sprint", "from": old, "to": new}
        cases = [
            ("no sprint change", [], ["7"]),
            ("added later", [joined(at("02-27"))], []),
            ("removed first", [left(at("02-27"))], ["7"]),
            ("carried over from the previous sprint", [carried()], ["6"]),
            ("removed and added at one instant", [
             joined(at("02-27")), left(at("02-27"))], ["7"]),
            ("a later sprint added after this one", [joined(at("02-27")),
                                                     change(at("03-14"), "7", "7, 8")], []),
            ("sorted as numbers", [
             change(at("02-27"), "10", "")], ["7", "10"]),
        ]
        for name, changes, expected in cases:
            with self.subTest(name):
                self.assertEqual(common.initial_sprints(
                    changes, "7"), expected)

    def test_state_at(self):
        # Replayed from the events: the creation's values, then each change
        # up to the instant, a change counting from its exact instant.
        issue = done("PROJ-1", points=8, priority={"name": "Low"}, parent="PROJ-200",
                     customfield_flag=None)
        changes = [moved(at("03-04"), "To Do", "Done"), moved(at("03-06"), "Done", "Duplicate"),
                   flag(at("03-04")), flag(at("03-08"),
                                           on=False), points(at("03-08"), "3", "8"),
                   changed(at("03-08"), "priority", "High", "Low"),
                   changed(at("03-08"), "parent", "PROJ-100", "PROJ-200", "id-PROJ-100", "id-PROJ-200")]
        found = events(issue, changes)
        before = {"status": "To Do", "statusCategory": "new", "resolution": "Done", "storyPoints": 3,
                  "flagged": False, "priority": "High", "parentId": "id-PROJ-100", "parentKey": "PROJ-100"}
        cases = [(at("03-03"), before),
                 (at("03-04"), {**before, "status": "Done",
                  "statusCategory": "done", "flagged": True}),
                 (at("03-07"), {**before, "status": "Duplicate",
                  "statusCategory": "done", "flagged": True}),
                 (at("03-09"), {**before, "status": "Duplicate", "statusCategory": "done", "storyPoints": 8,
                                "priority": "Low", "parentId": "id-PROJ-200", "parentKey": "PROJ-200"})]
        for instant, expected in cases:
            with self.subTest(instant=instant):
                self.assertEqual(common.state_at(
                    "PROJ-1", found, parse_ts(instant)), expected)

    def test_unknown_status(self):
        # Not in Jira's list of statuses: the current status's category, else
        # a failure when the state is read while it held.
        issue = raw("PROJ-1", status="In Progress")
        found = common.ticket_events(issue, [changed(at("03-04"), "status", "Gone", "In Progress", "60", "3")],
                                     common.Context("7", START, {}, FIELDS, {}, PLUS_ONE, None), CLOSE)
        self.assertEqual(common.state_at("PROJ-1", found, parse_ts(at("03-05")))["statusCategory"],
                         "indeterminate")
        with self.assertRaisesRegex(SystemExit, "PROJ-1: status 'Gone' is not in Jira's list of statuses"):
            common.state_at("PROJ-1", found, parse_ts(at("03-03")))

    def test_sprint_moves_of(self):
        # The creation counts as the first add when the ticket was in the
        # sprint then; membership changes at each move's exact instant.
        issue = raw("PROJ-1", created=at("03-01"))
        cases = [
            ("in the sprint since creation", [left(at("03-02")), joined(at("03-03"))],
             [(1, at("03-01")), (-1, at("03-02")), (1, at("03-03"))]),
            ("no moves", [], [(1, at("03-01"))]),
            ("added later", [joined(at("03-03"))], [(1, at("03-03"))]),
        ]
        for name, changes, expected in cases:
            with self.subTest(name):
                moves = common.sprint_moves_of(events(issue, changes), "7")
                self.assertEqual([(move, ts)
                                 for _, move, ts in moves], expected)
        moves = common.sprint_moves_of(events(issue, cases[0][1]), "7")
        for instant, expected in [(at("02-28"), False), (at("03-01"), True), (at("03-02"), False),
                                  (at("03-03"), True)]:
            with self.subTest(instant=instant):
                self.assertIs(common.in_sprint_at(
                    moves, parse_ts(instant)), expected)


class BlockerCandidatesTest(unittest.TestCase):
    def test_blocker_candidates(self):
        # A ticket in the sprint at the close that was flagged, blocked or
        # high priority and not done then, from its events: the tickets whose
        # comments the fetch reads and data.json's blocker candidates.
        # name: (the ticket today, its changes, a candidate)
        cases = [
            ("flagged at the close", raw("PROJ-1"), [flag(at("03-04"))], True),
            ("flag cleared before the close", raw("PROJ-1"),
             [flag(at("03-04")), flag(at("03-06"), on=False)], False),
            ("flagged after the close", raw("PROJ-1", customfield_flag=[{"value": "Impediment"}]),
             [flag(at("03-14"))], False),
            ("in a blocked status", raw("PROJ-1"),
             [moved(at("03-04"), "To Do", "Blocked")], True),
            ("unblocked before the close", raw("PROJ-1", status="In Progress"),
             [moved(at("03-04"), "To Do", "Blocked"), moved(at("03-05"), "Blocked", "In Progress")], False),
            ("high priority and open", raw("PROJ-1"),
             [changed(at("03-04"), "priority", "Medium", "High")], True),
            ("high priority but done", done("PROJ-1", priority={"name": "High"}),
             [moved(at("03-04"), "To Do", "Done")], False),
            ("high priority only after the close", raw("PROJ-1", priority={"name": "High"}),
             [changed(at("03-14"), "priority", "Medium", "High")], False),
            ("flagged but left before the close", raw("PROJ-1"),
             [flag(at("03-04")), left(at("03-05"))], False),
            ("flagged and done", done("PROJ-1"),
             [flag(at("03-04")), moved(at("03-05"), "To Do", "Done")], True),
            ("flagged, joined only after the close", raw("PROJ-1"),
             [joined(at("02-27"), "6"), flag(at("03-04")), joined(at("03-14"))], False),
            ("flagged, left and came back before the close", raw("PROJ-1"),
             [flag(at("03-04")), left(at("03-05")), joined(at("03-06"))], True),
        ]
        for name, issue, changes, expected in cases:
            with self.subTest(name):
                found = common.blocker_candidates(
                    {"PROJ-1": events(issue, changes)}, "7", CLOSE)
                self.assertEqual(found, ["PROJ-1"] if expected else [])

    def test_without_the_flagged_field(self):
        # A site without a Flagged field has no flagged tickets, whatever
        # the issue's fields hold.
        issue = raw("PROJ-1", customfield_flag=[{"value": "Impediment"}])
        ctx = common.Context("7", START, CATEGORIES,
                             (None, FIELDS[1]), {}, PLUS_ONE, None)
        self.assertEqual(common.blocker_candidates(
            {"PROJ-1": common.ticket_events(issue, [], ctx, CLOSE)}, "7", CLOSE), [])


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

    def test_write_json(self):
        path = os.path.join(self.folder, "PROJ_Sprint_7", "_raw", "data.json")
        common.write_json(path, {"x": [1]})
        with open(path, encoding="utf-8") as f:
            self.assertEqual(f.read(), json.dumps({"x": [1]}, indent=2))

    def test_nothing_is_written_outside_the_output_folder(self):
        os.symlink(self.tmp, os.path.join(self.folder, "link"))
        cases = [
            ("a sibling folder", os.path.join(self.tmp, "other", "data.json"),
             "without \\.\\."),
            ("the parent folder", os.path.join(self.tmp, "data.json"),
             "without \\.\\."),
            ("through a symbolic link", os.path.join(self.folder, "link", "data.json"),
             "without \\.\\."),
        ]
        for name, path, expected in cases:
            with self.subTest(name):
                with self.assertRaisesRegex(SystemExit, expected):
                    common.write_report_file(path, "{}")
                self.assertFalse(os.path.exists(path))

    def test_report_label(self):
        # The key is prefixed unless the name starts with it, in any case; each
        # run of characters unsafe in a file name becomes one underscore.
        cases = [("PROJ", "Sprint 3", "PROJ_Sprint_3"), ("PROJ", "proj sprint 3", "proj_sprint_3"),
                 ("PROJ", "Q1: Login / Search!", "PROJ_Q1_Login_Search"), (None, None, "Sprint")]
        for project, name, expected in cases:
            with self.subTest(name=name):
                self.assertEqual(common.report_label(project, name), expected)


class QuantitiesTest(unittest.TestCase):
    def test_formats(self):
        # Each figure has one shape in every part of the report. Exactly 1 is
        # singular, 1.0 too; 0 is plural; no estimate is "–", never 0.
        cases = [
            (common.number, (3.0,), "3"), (common.number,
                                           (2.5,), "2.5"), (common.number, (4,), "4"), (common.number, (0.1 + 0.2,), "0.3"),
            (common.plural, (0, "it", "they"),
             "they"), (common.plural, (1, "it", "they"), "it"),
            (common.plural, (1.0, "it", "they"),
             "it"), (common.plural, (2, "it", "they"), "they"),
            (common.unit, (1,), "ticket"), (common.unit,
                                            (0,), "tickets"), (common.unit, (2,), "tickets"),
            (common.pts, (1,), "1 pt"), (common.pts,
                                         (1.0,), "1 pt"), (common.pts, (2.0,), "2 pts"),
            (common.pts, (0.5,), "0.5 pts"), (common.pts,
                                              (0,), "0 pts"), (common.pts, (None,), "– pts"),
            (common.qty, (1, 3.0), "1 ticket (3 pts)"), (common.qty,
                                                         (7, 7), "7 tickets (7 pts)"),
            (common.qty, (4, None), "4 tickets (– pts)"),
            # Only the estimates that are set add up; none set is no
            # estimate; no work at all is 0.
            (common.known_sum, ([2, 3],), 5),
            (common.known_sum, ([2, None, 0.5],), 2.5),
            (common.known_sum, ([None, None],), None),
            (common.known_sum, ([],), 0),
            # The unit follows the total: "1/1 ticket", "0/2 tickets".
            (common.ratio, (11, 22, 34, 74), "11/22 tickets (34/74 pts)"),
            (common.ratio, (1, 1, 2.0, 2), "1/1 ticket (2/2 pts)"),
            (common.ratio, (0, 2, 0, 1), "0/2 tickets (0/1 pts)"),
            # Unestimated pts read "–".
            (common.ratio, (1, 2, None, None), "1/2 tickets (–/– pts)"),
            (common.ratio, (0, 2, 0, None), "0/2 tickets (0/– pts)"),
            (common.ratio, (1, 2, None, 3), "1/2 tickets (–/3 pts)"),
            (common.ticket_ref, ("PROJ-20", 2), "PROJ-20 (2 pts)"),
            (common.ticket_ref, ("PROJ-13", None), "PROJ-13 (– pts)"),
            (common.estimate, (5,), "5"), (common.estimate,
                                           (2.0,), "2"), (common.estimate, (0,), "0"),
            (common.estimate, (None,), "–"),
            # A share above zero never reads 0%; nothing to share is n/a.
            (common.whole_percentage, (1, 3),
             "33%"), (common.whole_percentage, (2, 3), "67%"),
            (common.whole_percentage, (2, 4),
             "50%"), (common.whole_percentage, (5, 5), "100%"),
            (common.whole_percentage, (0, 5),
             "0%"), (common.whole_percentage, (1, 300), "<1%"),
            (common.whole_percentage, (1, 200),
             "<1%"), (common.whole_percentage, (1, 0), "n/a"),
            # Just short of the whole never reads as all of it.
            (common.whole_percentage, (199, 200),
             ">99%"), (common.whole_percentage, (299, 300), ">99%"),
            (common.whole_percentage, (99, 100), "99%"),
            # A share of unestimated pts, or in them, is unknown.
            (common.whole_percentage, (None, 5), "–"),
            (common.whole_percentage, (0, None), "–"),
            (common.display_date, ("2026-03-02",), "02/03/2026"),
        ]
        for function, args, expected in cases:
            with self.subTest(function=function.__name__, args=args):
                self.assertEqual(function(*args), expected)


class OutcomeTotalTest(unittest.TestCase):
    def test_outcome_total(self):
        # A row's tickets add up; its pts by known_sum's rule over the
        # outcomes that hold tickets: unestimated tickets alone are None,
        # and a row with no tickets is 0.
        def cells(completed, not_completed, descoped):
            return {"new_completed": completed, "new_not_completed": not_completed, "new_descoped": descoped}
        counts = cells(1, 2, 0)
        cases = [("fully estimated", cells(3, 2, 0), 5), ("partly estimated", cells(None, 2, 0), 2),
                 ("all unestimated", cells(None, None, 0), None)]
        for name, points, expected in cases:
            with self.subTest(name):
                self.assertEqual(common.outcome_total(
                    points, "new", counts), expected)
        self.assertEqual(common.outcome_total(counts, "new"), 3)
        self.assertEqual(common.outcome_total(
            cells(0, 0, 0), "new", cells(0, 0, 0)), 0)


class ExpectedFilesTest(unittest.TestCase):
    def test_expected_files(self):
        self.assertEqual(common.expected_files("PROJ_Sprint_3"),
                         {"_raw", "data.json", "content.json", "brief.json", "outcome-tickets.svg",
                          "outcome-pts.svg", "burndown.svg", "PROJ_Sprint_3_Sprint_Report.md"})


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

    def test_text_rule_problems(self):
        # Banned words first, then each format the text breaks. The estimate
        # rule applies only with the tickets' latest estimates, and only to
        # tickets of the sprint.
        latest = {"PROJ-1": 3, "PROJ-2": None}
        cases = [
            ("valid", "11/22 tickets (34/74 pts), 27% of commitment, on 13/03/2026; **Open:** PROJ-1 (3 pts), "
             "PROJ-2 (– pts), PROJ-9 (8 pts)", latest, []),
            ("banned word", "Two stories", None, [("no story or stories", ["stories"]),
                                                  ("no spelled-out numbers (write digits)", ["Two"])]),
            ("decimal percentage", "27.5% done", None,
             [(common.PERCENT_RULE, ["27.5%"])]),
            ("bare ratio", "3/5 done", None, [(common.RATIO_RULE, ["3/5"])]),
            ("old amount", "3 tickets / 5 pts", None,
             [(common.AMOUNT_RULE, ["3 tickets / "])]),
            ("bold that isn't a label", "**Great** work, <b>Open:</b> <b>all</b>", None,
             [(common.BOLD_RULE, ["Great", "all"])]),
            ("ISO date", "on 2026-03-13", None,
             [(common.DATE_RULE, ["2026-03-13"])]),
            ("an estimate that isn't the latest, or none", "PROJ-1 (2 pts) and PROJ-2 grew", latest,
             [(common.ESTIMATE_RULE, ["PROJ-1 (2 pts)", "PROJ-2"])]),
            ("without the latest estimates", "PROJ-1 (2 pts)", None, []),
            ("a quoted list of keys",
             "3 tickets (5 pts) were descoped (PROJ-1, PROJ-2)", latest, []),
        ]
        for name, text, given, expected in cases:
            with self.subTest(name):
                self.assertEqual(common.text_rule_problems(
                    text, given), expected)


class ScopeGroupsTest(unittest.TestCase):
    def test_scope_group_label(self):
        # Not completed work reads "Open" only while the sprint runs.
        cases = [("completed", "active", "Completed"), ("in_review", "closed", "In review"),
                 ("not_completed", "active", "Open"), ("not_completed",
                                                       "closed", "Not completed"),
                 ("descoped", "active", "Descoped")]
        for group, status, expected in cases:
            with self.subTest(group=group, status=status):
                self.assertEqual(common.scope_group_label(
                    group, status), expected)


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
            ({**data(today="2026-03-06"), "sprint_end": "2026-03-11"},
             ("On track", "At risk")),
            # A closed sprint is judged whenever it closed.
            (data(status="closed"), ("Fully met", "Partially met", "Not met")),
            # No goal leaves nothing to judge, closed or not.
            (data(goal=""), ("No goal set in Jira for this sprint",)),
            (data(goal="   "), ("No goal set in Jira for this sprint",)),
            (data(status="closed", goal="\n \n"),
             ("No goal set in Jira for this sprint",)),
            (data(status="closed", goal=""),
             ("No goal set in Jira for this sprint",)),
        ]
        for case, expected in cases:
            with self.subTest(case):
                self.assertEqual(common.allowed_verdicts(case), expected)


if __name__ == "__main__":
    unittest.main()
