"""Unit tests for skills/agentic-manager-jira-sprint-report/scripts/build_sprint_data.py.
Run with: python3 tests/run.py agentic-manager-jira-sprint-report

They call the script's functions directly with a few hand-made issues.
test_e2e_pipeline.py runs it on a whole made-up sprint.
"""

import json
import os
import sys
import tempfile
import unittest
from datetime import timedelta, timezone
from unittest import mock
from zoneinfo import ZoneInfo

# tests/<skill>/ mirrors skills/<skill>/.
TEST_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(TEST_DIR))
sys.path.insert(0, os.path.join(REPO_ROOT, "skills",
                os.path.basename(TEST_DIR), "scripts"))
import build_sprint_data as build  # noqa: E402
import common  # noqa: E402
from agentic_manager import output_file  # noqa: E402
from common import NO_EPIC, parse_ts  # noqa: E402
sys.path.insert(0, TEST_DIR)
from sprint_fixture import STATUS, moved  # noqa: E402
from report_fixture import ev, pull, ticket  # noqa: E402

START = "2026-03-02T09:00:00.000+0100"
START_DATE = "2026-03-02"
CLOSE = "2026-03-13T17:00:00.000+0100"
FIELDS = ("customfield_flag", "customfield_points")
PLUS_ONE = timezone(timedelta(hours=1))
CATEGORIES = {i: category for i, category in STATUS.values()}


def at(day, time="10:00"):
    return f"2026-{day}T{time}:00.000+0100"


def raw(key, created="2026-02-20T10:00:00.000+0100", status="To Do", points=None, resolution=None,
        parent=None, **fields):
    """A raw issue as Jira's API returns it today."""
    return {"key": key, "fields": {
        "summary": f"Summary of {key}", "created": created,
        "status": {"id": STATUS[status][0], "name": status, "statusCategory": {"key": STATUS[status][1]}},
        "resolution": {"name": resolution} if resolution else None,
        "issuetype": {"name": "Story"}, "priority": {"name": "Medium"},
        "parent": ({"id": f"id-{parent}", "key": parent, "fields": {"summary": f"Epic {parent}"}}
                   if parent else None),
        "customfield_points": points, **fields}}


def done(key, **kwargs):
    return raw(key, status="Done", resolution="Done", **kwargs)


def joined(created, sprint="7"):
    return {"created": created, "field": "sprint", "from": "", "to": sprint,
            "fromString": None, "toString": None}


def left(created, sprint="7"):
    return {"created": created, "field": "sprint", "from": sprint, "to": "",
            "fromString": None, "toString": None}


def changed(created, field, old, new, old_id=None, new_id=None):
    return {"created": created, "field": field, "from": old_id, "fromString": old,
            "to": new_id, "toString": new}


def context(epics=None, previous=None):
    return build.Context("7", START, CATEGORIES, FIELDS, epics or {}, PLUS_ONE, previous)


# Sprint 6 closed an hour before Sprint 7 started.
PREVIOUS = {"id": 6, "name": "Sprint 6",
            "completeDate": "2026-03-02T08:00:00.000+0100"}


def carried(created=PREVIOUS["completeDate"]):
    """Moved from Sprint 6 into Sprint 7 when Sprint 6 closed; Jira keeps
    Sprint 6 in the field."""
    return {"created": created, "field": "sprint", "from": "6", "to": "6, 7",
            "fromString": None, "toString": None}


def events(issue, changes):
    """The ticket's events, from which the model works out its spells."""
    return build.ticket_events(issue, changes, context(), CLOSE)


def spells_of(issue, changes, ctx=None, moment=CLOSE):
    """The ticket's spells, from its events as main() works them out."""
    ctx = ctx or context()
    return build.spells_from_events(issue, build.ticket_events(issue, changes, ctx, moment), ctx, moment)


def points(created, old, new):
    return changed(created, "points", old, new)


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
                self.assertEqual(build.sprint_date(ts, PLUS_ONE), expected)


class FieldsTest(unittest.TestCase):
    def test_epic_names(self):
        names = build.epic_names([raw("PROJ-1", parent="PROJ-100"), raw("PROJ-2")],
                                 [{"id": "1200", "key": "PROJ-200", "fields": {"summary": "Old epic"}}])
        self.assertEqual(names, {"id-PROJ-100": ("PROJ-100", "Epic PROJ-100"),
                                 "1200": ("PROJ-200", "Old epic")})

    def test_non_delivery_marker(self):
        cases = [("Duplicate", "Done", "duplicate"), ("Closed", "Won't Do", "won't do"),
                 ("Done", "Done", None), (None, None, None)]
        for status, resolution, expected in cases:
            with self.subTest(status=status, resolution=resolution):
                self.assertEqual(build.non_delivery_marker(
                    status, resolution), expected)


class ChangelogsTest(unittest.TestCase):
    def test_load_changelogs(self):
        with tempfile.TemporaryDirectory() as folder:
            with open(os.path.join(folder, "PROJ-1.json"), "w", encoding="utf-8") as f:
                json.dump([joined(START)], f)
            self.assertEqual(build.load_changelogs(folder, [raw("PROJ-1")]),
                             {"PROJ-1": [joined(START)]})
            with self.assertRaisesRegex(SystemExit, "missing changelogs for PROJ-2"):
                build.load_changelogs(folder, [raw("PROJ-1"), raw("PROJ-2")])


class CarryOverTest(unittest.TestCase):
    def test_in_sprint_when_closed(self):
        issue = raw("PROJ-1", created="2026-02-20T10:00:00.000+0100")
        cases = [
            ("moved when it closed, there since creation", [carried()], True),
            ("joined it, then moved when it closed", [
             joined(at("02-23"), "6"), carried()], True),
            ("left it before it closed", [
             left(at("02-25"), "6"), joined(at("03-02", "08:30"))], False),
            ("joined it after it closed", [
             joined(at("03-02", "08:30"), "6")], False),
            ("never in it", [joined(at("02-25"))], False),
        ]
        for name, changes, expected in cases:
            with self.subTest(name):
                self.assertEqual(build.in_sprint_when_closed(
                    events(issue, changes), PREVIOUS), expected)
        self.assertFalse(build.in_sprint_when_closed(
            events(issue, [carried()]), None))

    def test_only_original_work_is_carried_over(self):
        # Carry-over describes the commitment: work that came from the previous
        # sprint but joined after the start, or a later spell of carried work,
        # is extra, not carried in.
        cases = [
            ("in the commitment", [carried()], PREVIOUS, [True]),
            ("no previous sprint on the board", [carried()], None, [False]),
            ("joined after the start", [carried(at("03-02", "08:00")), left(at("03-02", "08:30")),
                                        joined(at("03-03"))], PREVIOUS, [False]),
            ("new work", [joined(at("03-01"))], PREVIOUS, [False]),
            ("descoped and back: only the first spell", [carried(), left(at("03-04")), joined(at("03-06"))],
             PREVIOUS, [True, False]),
        ]
        for name, changes, previous, expected in cases:
            with self.subTest(name):
                found = spells_of(raw("PROJ-1"), changes,
                                  context(previous=previous))
                self.assertEqual([s["carriedIn"] for s in found], expected)


class SpellsTest(unittest.TestCase):
    def build(self, changes, issue=None, moment=CLOSE):
        return spells_of(issue or raw("PROJ-1"), changes, moment=moment)

    def test_spells(self):
        before, just_after = at("02-27"), "2026-03-02T09:00:01.000+0100"
        original, extra = ("original", "not_completed",
                           True), ("extra", "not_completed", True)
        cases = [
            ("in the sprint at the start", [joined(before)], None, [original]),
            ("added at the start instant", [joined(START)], None, [original]),
            ("created in the sprint before the start", [], None, [original]),
            ("added after the start, even the same day",
             [joined(just_after)], None, [extra]),
            ("created in the running sprint", [], raw(
                "PROJ-1", created=at("03-05")), [extra]),
            ("joined and left before the start", [
             joined(before), left(at("02-28"))], None, []),
            ("extra work that left for good is shown, not counted", [joined(at("03-03")), left(at("03-05"))], None,
             [("extra", "removed", False)]),
            ("original work that left for good", [joined(before), left(at("03-05"))], None,
             [("original", "removed", True)]),
            ("leaving and coming back: descoped, then extra", [joined(before), left(at("03-04")), joined(at("03-06"))],
             None, [("original", "removed", True), extra]),
            ("leaving and coming back the same day", [joined(before), left(at("03-04")), joined(at("03-04", "15:00"))],
             None, [("original", "removed", True), extra]),
            ("out, back, out again", [joined(before), left(at("03-03")), joined(at("03-05")), left(at("03-07"))],
             None, [("original", "removed", True), ("extra", "removed", False)]),
            ("moves after the close are ignored", [
             joined(before), left(at("03-14"))], None, [original]),
            ("extra work that left after the close", [
             joined(at("03-03")), left(at("03-14"))], None, [extra]),
        ]
        for name, changes, issue, expected in cases:
            with self.subTest(name):
                self.assertEqual([(s["scope"], s["outcome"], s["counted"]) for s in self.build(changes, issue)],
                                 expected)

    def test_events(self):
        cases = [
            ("done at the start, reopened", [joined(at("02-27")), moved(at("03-04"), "Done", "In Progress")],
             done("PROJ-1", points=3), [[("committed", True, 3), ("reopened", False, 3)]], ["not_completed"]),
            ("re-estimated, then done", [joined(at("02-27")), points(at("03-03"), "2", "5"),
                                         moved(at("03-05"), "To Do", "Done")],
             done("PROJ-1", points=5), [[("committed", False, 2),
                                         ("reestimated", False, 5), ("completed", True, 5)]],
             ["completed"]),
            ("status changes that keep it open aren't events",
             [joined(at("02-27")), moved(at("03-04"), "To Do", "In Progress")],
             raw("PROJ-1", status="In Progress", points=2), [[("committed", False, 2)]], ["not_completed"]),
            ("completed and removed in one edit", [joined(at("02-27")), moved(at("03-05"), "To Do", "Done"),
                                                   left(at("03-05"))],
             done("PROJ-1", points=2), [[("committed", False, 2),
                                         ("completed", True, 2), ("removed", True, 2)]],
             ["removed"]),
            ("changed while out of the sprint, read afresh when it comes back",
             [joined(at("02-27")), left(at("03-03")), points(at("03-04"), "2", "4"),
              moved(at("03-04"), "To Do", "Done"), joined(at("03-05"))],
             done("PROJ-1", points=4), [[("committed", False, 2),
                                         ("removed", False, 2)], [("joined", True, 4)]],
             ["removed", "completed"]),
        ]
        for name, changes, issue, expected, outcomes in cases:
            with self.subTest(name):
                found = self.build(changes, issue)
                self.assertEqual([[(e["type"], e["done"], e["points"])
                                 for e in s["events"]] for s in found], expected)
                self.assertEqual([s["outcome"] for s in found], outcomes)
                self.assertEqual([s["points"] for s in found], [
                                 events[-1][2] for events in expected])

    def test_events_carry_the_old_estimate_and_the_local_date(self):
        found = self.build([joined(at("02-27")), points("2026-03-03T23:30:00.000+0000", "2", "5")],
                           raw("PROJ-1", points=5))
        self.assertEqual(found[0]["events"][1], {"at": "2026-03-03T23:30:00.000+0000", "date": "2026-03-04",
                                                 "type": "reestimated", "points": 5, "done": False, "fromPoints": 2})

    def test_fields_are_as_at_the_end_or_when_it_left(self):
        # A report run later must give the same figures, so fields are read as
        # at the close or when the ticket left, never as Jira shows them today.
        cases = [
            ("done outside the sprint after leaving: as when it left",
             [joined(at("02-27")), left(at("03-04")),
              moved(at("03-06"), "To Do", "Done")], done("PROJ-1"),
             ("To Do", "removed", None)),
            ("done after the close: as at the close",
             [joined(at("02-27")), moved(at("03-14"),
                                         "To Do", "Done")], done("PROJ-1"),
             ("To Do", "not_completed", None)),
            # A Duplicate counts as completed, as in Jira's report, but is named.
            ("closed as a duplicate", [joined(at("02-27")), moved(at("03-04"), "To Do", "Duplicate")],
             raw("PROJ-1", status="Duplicate", resolution="Done"), ("Duplicate", "completed", "duplicate")),
        ]
        for name, changes, issue, expected in cases:
            with self.subTest(name):
                found = self.build(changes, issue)[0]
                self.assertEqual(
                    (found["status"], found["outcome"], found["closedAsNonDelivery"]), expected)

    def test_epic(self):
        # An epic fetched for its name shows it; one that wasn't falls back to
        # its key rather than dropping the ticket from the epic table.
        issue = raw("PROJ-1", parent="PROJ-100")
        cases = [
            ("known epic", issue, {
             "id-PROJ-100": ("PROJ-100", "Sign-in")}, ("PROJ-100", "Sign-in")),
            ("epic not fetched", issue, {}, ("PROJ-100", "PROJ-100")),
            ("no epic", raw("PROJ-1"),
             {"id-PROJ-100": ("PROJ-100", "Sign-in")}, (None, None)),
        ]
        for name, issue, epics, expected in cases:
            with self.subTest(name):
                found = spells_of(issue, [], context(epics))[0]
                self.assertEqual(
                    (found["parentKey"], found["parentSummary"]), expected)
                self.assertNotIn("parentId", found)


class TicketEventsTest(unittest.TestCase):
    """A ticket's events, which its spells are worked out from."""

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
        self.assertEqual(build.ticket_events(issue, changes, context(), CLOSE), [
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
                self.assertEqual(build.initial_sprints(changes, "7"), expected)

    def test_spells_come_from_the_events_alone(self):
        # Hand-written events, with no changelog: committed at the start,
        # completed on 04/03.
        events = [{"at": at("02-20"), "date": "2026-02-20", "source": "jira", "type": "created", "values": {
            "sprint": ["7"], "status": "To Do", "statusCategory": "new", "resolution": None, "priority": "High",
            "parent": None, "parentId": None, "points": 3, "flagged": False}},
            {"at": at("03-04"), "date": "2026-03-04", "source": "jira", "type": "status_changed", "from": "To Do",
             "to": "Done", "fromCategory": "new", "toCategory": "done"}]
        spell, = build.spells_from_events(
            raw("PROJ-1"), events, context(), CLOSE)
        self.assertEqual([(e["type"], e["done"], e["points"]) for e in spell["events"]],
                         [("committed", False, 3), ("completed", True, 3)])
        self.assertEqual((spell["status"], spell["priority"], spell["outcome"]),
                         ("Done", "High", "completed"))

    def test_a_status_jira_no_longer_lists(self):
        # Its category is unknown, which matters only when a spell reads it.
        gone = changed(at("02-27"), "status", "Old", "To Do", "60", "1")
        cases = [("left before the start", [gone], None),
                 ("left during the sprint", [dict(gone, created=at("03-04"))],
                  "PROJ-1: status 'Old' is not in Jira's list of statuses")]
        for name, changes, failure in cases:
            with self.subTest(name):
                events = build.ticket_events(
                    raw("PROJ-1"), changes, context(), CLOSE)
                self.assertIsNone(events[0]["values"]["statusCategory"])
                if failure:
                    with self.assertRaisesRegex(SystemExit, failure):
                        build.spells_from_events(
                            raw("PROJ-1"), events, context(), CLOSE)
                else:
                    self.assertEqual(len(build.spells_from_events(
                        raw("PROJ-1"), events, context(), CLOSE)), 1)


class ReplayTest(unittest.TestCase):
    def test_replay(self):
        events = [ev(2, "committed"), ev(4, "completed", done=True),
                  ev(5, "removed", done=True)]
        # An event counts from its exact instant.
        cases = [("before it entered", at("03-01"), None), ("committed", at("03-03"), (True, False, 2)),
                 ("completed", events[1]["at"], (True, True, 2)), ("removed", at("03-06"), (False, True, 2))]
        for name, until, expected in cases:
            with self.subTest(name):
                self.assertEqual(build.replay(
                    events, parse_ts(until)), expected)


class BreakdownAndEpicsTest(unittest.TestCase):
    def test_target_completion(self):
        # The original commitment only, at each spell's latest estimate.
        spells = [ticket("PROJ-1", [ev(2, "committed", 3, done=True)], "completed"),
                  ticket("PROJ-2", [ev(2, "committed")], "not_completed"),
                  ticket("PROJ-3", [ev(3, "joined", done=True)],
                         "completed", scope="extra"),
                  ticket("PROJ-4", [ev(2, "committed", 1), ev(4, "removed", 1)], "removed")]
        self.assertEqual(build.target_completion(spells), {
            "completed": 1, "total": 3, "completed_points": 3, "total_points": 6})

    TICKETS = [ticket("PROJ-1", [ev(2, "committed", 3, done=True)], "completed", carried=True),
               ticket("PROJ-2", [ev(2, "committed", 1),
                      ev(4, "removed", 1)], "removed"),
               ticket("PROJ-3", [ev(2, "committed", None)], "not_completed"),
               ticket("PROJ-4", [ev(3, "joined", 5, done=True)], "completed", scope="extra", parent="PROJ-200")]

    def test_outcome_breakdown(self):
        counts, points_ = build.outcome_breakdown(self.TICKETS)
        self.assertEqual({k: v for k, v in counts.items() if v}, {
            "original_completed": 1, "original_removed": 1, "original_not_completed": 1,
            "carried_in_completed": 1, "new_removed": 1, "new_not_completed": 1, "extra_completed": 1})
        self.assertEqual({k: v for k, v in points_.items() if v}, {
            "original_completed": 3, "original_removed": 1, "carried_in_completed": 3, "new_removed": 1,
            "extra_completed": 5})

    def test_non_delivery_closures(self):
        # The counted spells completed as a non-delivery, at their latest
        # estimates; an uncounted spell is left out.
        duplicate = ticket("PROJ-1", [ev(2, "committed", 3), ev(4, "completed", 3, done=True)], "completed",
                           status="Duplicate", marker="duplicate")
        uncounted = dict(ticket("PROJ-2", [ev(3, "joined", 5), ev(4, "removed", 5)], "removed", scope="extra"),
                         closedAsNonDelivery="won't do")
        self.assertEqual(build.non_delivery_closures(self.TICKETS + [duplicate, uncounted]), {
            "count": 1, "points": 3,
            "issues": [{"key": "PROJ-1", "status": "Duplicate", "resolution": "Done", "storyPoints": 3,
                        "marker": "duplicate", "summary": "Work item PROJ-1"}]})

    def test_extra_spells_that_ended_descoped_are_not_counted(self):
        uncounted = ticket("PROJ-9", [ev(3, "joined", 8), ev(4, "removed", 8)], "removed", scope="extra",
                           parent="PROJ-300")
        self.assertEqual(build.outcome_breakdown(
            self.TICKETS + [uncounted]), build.outcome_breakdown(self.TICKETS))
        self.assertNotIn(
            "PROJ-300", [e["key"] for e in build.build_epics(self.TICKETS + [uncounted])])

    def test_epics(self):
        epics = build.build_epics(
            self.TICKETS + [ticket("PROJ-5", [ev(3, "joined", 1)], "not_completed", scope="extra", parent=None)])
        self.assertEqual([e["key"] for e in epics], [
                         "PROJ-200", "PROJ-100", NO_EPIC])
        proj_100 = epics[1]
        self.assertEqual([proj_100[k] for k in ("original_stories_done", "original_stories_total",
                                                "original_points_done", "original_points_total",
                                                "removed_stories", "removed_points")], [1, 3, 3, 4, 1, 1])
        self.assertEqual((epics[2]["extra_stories_total"],
                         epics[2]["extra_stories_done"]), (1, 0))

    def test_epic_scope_groups(self):
        # Completed holds only work completed during the spell; work done
        # before it, or resolved as a non-delivery, is left out, though the
        # figures count it. Descoped work is always Descoped.
        def completed_in_sprint(key, **extra):
            return ticket(key, [ev(2, "committed"), ev(4, "completed", done=True)], "completed", **extra)
        spells = [
            completed_in_sprint("PROJ-1"),
            ticket("PROJ-2", [ev(2, "committed", done=True)],
                   "completed"),  # Done at the start
            completed_in_sprint(
                "PROJ-3", marker="duplicate", status="Duplicate"),
            ticket("PROJ-4", [ev(2, "committed")],
                   "not_completed", status="In Review"),
            ticket("PROJ-5", [ev(2, "committed")],
                   "not_completed", status="Code review"),
            ticket("PROJ-6", [ev(2, "committed")],
                   "not_completed", status="To Do"),
            ticket("PROJ-7", [ev(2, "committed"), ev(4, "removed")],
                   "removed", status="In Review"),
            ticket("PROJ-8", [ev(3, "joined"), ev(4, "removed")],
                   "removed", scope="extra"),  # not counted
            # joined already Done
            ticket("PROJ-9", [ev(3, "joined", done=True)],
                   "completed", scope="extra"),
            # Done, then descoped: described as descoped all the same
            ticket("PROJ-10", [ev(2, "committed", done=True),
                   ev(4, "removed", done=True)], "removed"),
        ]
        spells[3]["flagged"] = True
        epic = build.build_epics(spells, {"PROJ-100": "Staff sign-in"})[0]
        self.assertEqual(epic["description"], "Staff sign-in")
        self.assertEqual({group: [t["key"] for t in tickets] for group, tickets in epic["scope_groups"].items()},
                         {"completed": ["PROJ-1"], "in_review": ["PROJ-4", "PROJ-5"], "not_completed": ["PROJ-6"],
                          "descoped": ["PROJ-7", "PROJ-10"]})
        self.assertEqual([(t["key"], t["reason"]) for t in epic["left_out"]],
                         [("PROJ-2", "done_at_start"), ("PROJ-3", "non_delivery"), ("PROJ-9", "done_at_start")])
        # Each ticket carries what the commentary needs to describe it,
        # including its estimate, status, flag and whether it was carried over.
        self.assertEqual(epic["scope_groups"]["in_review"][0],
                         {"key": "PROJ-4", "scope": "original", "carriedIn": False, "points": 2, "status": "In Review",
                          "flagged": True, "summary": "Work item PROJ-4", "description": "What PROJ-4 changes."})
        self.assertEqual(epic["left_out"][1],
                         {"key": "PROJ-3", "scope": "original", "carriedIn": False, "points": 2, "status": "Duplicate",
                          "flagged": False, "summary": "Work item PROJ-3", "description": "What PROJ-3 changes.",
                          "reason": "non_delivery"})
        self.assertEqual(epic["original_stories_done"], 3)
        self.assertEqual(build.build_epics(spells)[0]["description"], "")

    def test_description(self):
        long = "word " * 500
        cases = [("none", {}, ""), ("text", {"description": "Fix  the\nexport"}, "Fix the\nexport"),
                 ("whole, however long", {"description": long}, long.strip())]
        for name, fields, expected in cases:
            with self.subTest(name):
                self.assertEqual(build.description(fields), expected)
        self.assertEqual(build.epic_descriptions([{"key": "PROJ-100", "fields": {"description": "Sign-in"}},
                                                  {"id": "7", "fields": {}}]), {"PROJ-100": "Sign-in"})


class StatusChecksTest(unittest.TestCase):
    PR = "https://github.com/acme/api/pull/{}"

    def test_is_own_pull(self):
        # A pull request is the ticket's own when its title or branch names
        # the ticket or the sub-task it came through, or names no ticket.
        # name: (title, branch, via, own)
        cases = [("names the ticket", "PROJ-1 add the importer", "", "PROJ-1", True),
                 ("its branch names the ticket", "Add the importer",
                  "feature/PROJ-1-importer", "PROJ-1", True),
                 ("names no ticket", "ADR 0051: what a search returns",
                  "adr/0051", "PROJ-1", True),
                 ("names the sub-task it came through",
                  "PROJ-9 read the files", "", "PROJ-9", True),
                 ("names only another ticket", "PROJ-5 cache the settings",
                  "PROJ-5-cache", "PROJ-1", False),
                 ("names another ticket and this one",
                  "PROJ-5 and PROJ-1 together", "", "PROJ-1", True),
                 ("a lower-case key isn't one", "proj-5 cache", "", "PROJ-1", True)]
        for name, title, branch, via, own in cases:
            with self.subTest(name):
                self.assertEqual(build.is_own_pull(
                    {"title": title, "branch": branch, "via": via}, "PROJ-1"), own)

    def test_pull_state(self):
        # name: (mergedAt, closedAt, state)
        cases = [("open", None, None, "open"), ("merged", at("03-05"), at("03-05"), "merged"),
                 ("declined", None, at("03-05"), "declined")]
        for name, merged, closed, state in cases:
            with self.subTest(name):
                self.assertEqual(build.pull_state(
                    {"mergedAt": merged, "closedAt": closed}), state)

    def test_ticket_pulls(self):
        # As at the moment: one opened after it is left out, and a merge or
        # closing after it doesn't count yet. One without GitHub's times stops.
        raw = {"tickets": {"PROJ-1": [
            {"url": self.PR.format(41), "name": "PROJ-1 import",
             "source": {"branch": "PROJ-1"}, "via": "PROJ-1"},
            {"url": self.PR.format(
                42), "name": "PROJ-5 cache", "via": "PROJ-1"},
            {"url": self.PR.format(43), "name": "Later work", "via": "PROJ-1"}]},
            "events": {self.PR.format(41): {"createdAt": at("03-03"), "mergedAt": at("03-12"),
                                            "closedAt": at("03-12")},
                       self.PR.format(42): {"createdAt": at("03-03"), "mergedAt": None, "closedAt": at("03-04")},
                       self.PR.format(43): {"createdAt": at("03-12"), "mergedAt": None, "closedAt": None}}}
        found = build.ticket_pulls(raw, "PROJ-1", at("03-10"))
        self.assertEqual([(pr["url"][-2:], pr["title"], pr["branch"], pr["mergedAt"], pr["closedAt"], pr["own"],
                           pr["state"]) for pr in found],
                         [("41", "PROJ-1 import", "PROJ-1", None, None, True, "open"),
                          ("42", "PROJ-5 cache", "", None, at("03-04"), False, "declined")])
        self.assertEqual(build.ticket_pulls(raw, "PROJ-2", at("03-10")), [])
        del raw["events"][self.PR.format(42)]
        with self.assertRaisesRegex(SystemExit, f"PROJ-1: no GitHub times for {self.PR.format(42)}"):
            build.ticket_pulls(raw, "PROJ-1", at("03-10"))

    def test_status_flag(self):
        # Each status category with its own pull requests' states, the
        # others' ignored: not started with work, or Done with one open. A
        # started ticket is never flagged, however its pull requests stand.
        other = pull(50, "PROJ-5 cache", "open", "PROJ-1")
        # name: (category, states of its own, flag)
        cases = [("not started, none", "new", [], None),
                 ("not started, one open", "new", ["open"], "work_started"),
                 ("not started, one merged", "new",
                  ["merged"], "work_started"),
                 ("not started, only declined", "new", ["declined"], None),
                 ("started, all merged", "indeterminate",
                  ["merged", "declined"], None),
                 ("started, one open", "indeterminate",
                  ["merged", "open"], None),
                 ("started, none", "indeterminate", [], None),
                 ("Done, one open", "done", [
                  "merged", "open"], "open_after_done"),
                 ("Done, all merged", "done", ["merged"], None),
                 ("Done, only another ticket's open", "done", [], None)]
        for name, category, states, flag in cases:
            with self.subTest(name):
                pulls = [pull(41 + i, "PROJ-1 work", state, "PROJ-1")
                         for i, state in enumerate(states)]
                self.assertEqual(build.status_flag(
                    category, pulls + [other]), flag)

    def test_build_status_checks(self):
        # The flagged tickets in the sprint at the end, and the Done ones with
        # a full panel, in the epics' order and then by key, with their
        # counts; a started ticket and a descoped one aren't listed, even
        # with a full panel.
        def not_started(spell):
            return dict(spell, status="To Do", statusCategory="new")
        spells = [not_started(ticket("PROJ-3", [ev(2, "committed")], "not_completed", parent="PROJ-101")),
                  ticket("PROJ-1", [ev(2, "committed")],
                         "not_completed", status="In Progress"),
                  ticket("PROJ-2", [ev(2, "committed"),
                         ev(4, "completed", done=True)], "completed"),
                  ticket("PROJ-4", [ev(2, "committed"),
                         ev(4, "completed", done=True)], "completed"),
                  ticket("PROJ-6", [ev(2, "committed")],
                         "not_completed", status="In Review"),
                  not_started(ticket("PROJ-5", [ev(2, "committed"), ev(4, "removed")], "removed"))]
        pulls_of = {"PROJ-1": [pull(41, "PROJ-1 a", "merged", "PROJ-1")],
                    "PROJ-2": [pull(43, "PROJ-1 c", "open", "PROJ-1"), pull(42, "PROJ-9 b", "open", "PROJ-1")],
                    "PROJ-3": [pull(44, "PROJ-1 d", "merged", "PROJ-1")],
                    "PROJ-4": [pull(45, "PROJ-1 e", "merged", "PROJ-1")],
                    "PROJ-6": [pull(47, "PROJ-1 g", "merged", "PROJ-1")],
                    "PROJ-5": [pull(46, "PROJ-1 f", "merged", "PROJ-1")]}
        epics = [{"key": "PROJ-101"}, {"key": "PROJ-100"}]
        rows = build.build_status_checks(
            spells, pulls_of, {"PROJ-4", "PROJ-6"}, epics)
        # Its own open pull requests, then every linked one by state.
        self.assertEqual([(r["key"], r["epicKey"], r["status"], r["flag"], r["fullPanel"], r["ownOpen"],
                           r["linked"], r["otherTickets"]) for r in rows],
                         [("PROJ-3", "PROJ-101", "To Do", "work_started", False, 0,
                           {"merged": 1, "open": 0, "declined": 0}, 0),
                          ("PROJ-2", "PROJ-100", "Done", "open_after_done", False, 1,
                           {"merged": 0, "open": 2, "declined": 0}, 1),
                          ("PROJ-4", "PROJ-100", "Done", None, True, 0, {"merged": 1, "open": 0, "declined": 0}, 0)])


class TimelineTest(unittest.TestCase):
    def test_timeline(self):
        tickets = [ticket("PROJ-10", [ev(2, "committed"), ev(4, "completed", done=True)], "completed"),
                   ticket("PROJ-2", [ev(4, "joined", 1)], "not_completed", scope="extra")]
        rows = build.build_timeline(
            tickets, "closed", "2026-03-02", "2026-03-13", "2026-03-13", "2026-03-16")
        self.assertEqual([(r["date"], r["labels"], [(e["key"], e["type"]) for e in r["events"]]) for r in rows], [
            ("2026-03-02", ["sprint_start"], [("PROJ-10", "committed")]),
            ("2026-03-04", [], [("PROJ-2", "joined"), ("PROJ-10", "completed")]),
            ("2026-03-13", ["sprint_closed"], [])])
        self.assertEqual(rows[1]["events"][0], {"key": "PROJ-2", "scope": "extra", "at": tickets[1]["events"][0]["at"],
                                                "type": "joined", "points": 1, "done": False})

    def test_labels(self):
        # A running sprint is marked at today; a closed one at its close, or
        # at its planned end when Jira has no close date.
        cases = [
            ("closed", "closed", "2026-03-12",
             ("2026-03-12", ["sprint_closed"])),
            ("closed without a close date", "closed",
             None, ("2026-03-13", ["sprint_closed"])),
            ("active", "active", None, ("2026-03-10", ["today"])),
        ]
        for name, status, complete, expected in cases:
            with self.subTest(name):
                rows = build.build_timeline(
                    [], status, START_DATE, "2026-03-13", complete, "2026-03-10")
                self.assertEqual([(r["date"], r["labels"]) for r in rows],
                                 [(START_DATE, ["sprint_start"]), expected])


class BurndownTest(unittest.TestCase):
    def test_burndown(self):
        tickets = [
            ticket("PROJ-1", [ev(2, "committed", 3),
                   ev(3, "completed", 3, done=True)], "completed"),
            ticket("PROJ-2", [ev(2, "committed", 2), ev(4, "reestimated", 5, fromPoints=2)],
                   "not_completed"),
            ticket("PROJ-3", [ev(2, "committed", 1),
                   ev(5, "removed", 1)], "removed"),
            # Joined, left (an uncounted spell), then came back done: a new spell.
            ticket("PROJ-4", [ev(3, "joined", 4), ev(4, "removed", 4)],
                   "removed", scope="extra"),
            ticket("PROJ-4", [ev(5, "joined", 4, done=True)],
                   "completed", scope="extra"),
            ticket("PROJ-5", [ev(2, "committed", 6, done=True),
                   ev(5, "reopened", 6)], "not_completed"),
        ]
        rows = build.build_burndown(
            tickets, "2026-03-02", "2026-03-05", "2026-03-05T12:00:00.000+0100", PLUS_ONE)
        self.assertEqual([(r["committed"], r["total"])
                         for r in rows], [(6, 6), (3, 7), (6, 6), (11, 11)])


class CrossCheckTest(unittest.TestCase):
    def report(self, completed=("PROJ-1",), not_completed=("PROJ-2",), punted=("PROJ-3", "PROJ-9")):
        def keys(ks):
            return [{"key": k} for k in ks]
        return {"contents": {"completedIssues": keys(completed),
                             "issuesNotCompletedInCurrentSprint": keys(not_completed),
                             "puntedIssues": keys(punted)}}

    def check(self, report):
        return build.cross_check(report, ["PROJ-1", "PROJ-2"], ["PROJ-1"], ["PROJ-3", "PROJ-9"], ["PROJ-8"])

    def test_cross_check(self):
        in_another_sprint = self.report(completed=())
        in_another_sprint["contents"]["issuesCompletedInAnotherSprint"] = [
            {"key": "PROJ-1"}]
        cases = [
            ("agreeing", self.report(), []),
            # Jira lists work Done in another sprint apart; it is still completed.
            ("completed in another sprint counts as completed", in_another_sprint, []),
            # None, not [], so main() can say the report is missing rather than
            # that the data agrees.
            ("no report", None, None),
            ("no contents", {}, None),
            # Some boards return the report with every bucket empty.
            ("empty report", self.report((), (), ()),
             ["Jira's sprint report is empty: this board doesn't serve it. Fetch the sprint again "
              "with --sprint-id and --board, using another scrum board of the project"]),
            # Jira's buckets show today's membership, so they can't verify
            # tickets moved after the end.
            ("tickets moved later are left out", self.report(
                punted=("PROJ-3", "PROJ-8", "PROJ-9")), []),
            ("differences both ways", self.report(completed=("PROJ-1", "PROJ-5"), punted=("PROJ-9",)), [
                "in-scope: ['PROJ-5'] in Jira's sprint report but not in our data",
                "completed: ['PROJ-5'] in Jira's sprint report but not in our data",
                "removed: ['PROJ-3'] in our data but not in Jira's sprint report"]),
        ]
        for name, report, expected in cases:
            with self.subTest(name):
                self.assertEqual(self.check(report), expected)


class MembershipSetsTest(unittest.TestCase):
    def test_membership_sets(self):
        # From the events, as at the close: PROJ-5 was completed after it.
        issues = [raw("PROJ-1"), done("PROJ-2"), raw("PROJ-3"),
                  raw("PROJ-4"), done("PROJ-5")]
        changes = {"PROJ-1": [], "PROJ-2": [moved(at("03-04"), "To Do", "Done")],
                   "PROJ-3": [joined(at("03-03")), left(at("03-05"))],
                   "PROJ-4": [joined(at("02-27")), left(at("02-28"))],
                   "PROJ-5": [moved(at("03-14"), "To Do", "Done")]}
        events_of = {i["key"]: events(i, changes[i["key"]]) for i in issues}
        self.assertEqual(build.membership_sets(events_of, "7", CLOSE),
                         (["PROJ-1", "PROJ-2", "PROJ-5"], ["PROJ-2"], ["PROJ-3", "PROJ-4"]))


def flag(created, on=True):
    return changed(created, "flagged", None if on else "Impediment", "Impediment" if on else None,
                   None if on else "[10000]", "[10000]" if on else None)


class BlockerCandidatesTest(unittest.TestCase):
    def test_blocker_candidates(self):
        # A ticket in the sprint at the close that was flagged, blocked or
        # high priority and not done then, from its events; the fetch picks
        # the same tickets from the changelogs, by the same rule.
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
        ]
        for name, issue, changes, expected in cases:
            with self.subTest(name):
                found = build.blocker_candidates(
                    {"PROJ-1": events(issue, changes)}, "7", CLOSE)
                self.assertEqual(found, ["PROJ-1"] if expected else [])
                self.assertEqual(common.blocker_candidate_keys([issue], {"PROJ-1": changes}, CATEGORIES,
                                                               FIELDS[0], "7", parse_ts(CLOSE)), found)


class BlockerCommentsTest(unittest.TestCase):
    def test_blocker_comments(self):
        # Each candidate's comments as at the close, as plain text, without
        # their authors; a blank one says nothing, and one written or edited
        # after the close is left out, as its text then isn't known. Dates
        # are in the reporting timezone: 23:30 UTC is the next day in Rome.
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        adf = {"type": "paragraph", "content": [
            {"type": "text", "text": "Blocked until "},
            {"type": "date", "attrs": {"timestamp": "1772755200000"}},
            {"type": "text", "text": "."}]}
        # name: (the fetched comments, or None for no file, the comments kept)
        cases = [
            ("no file", None, []),
            ("text and author", [{"created": "2026-03-05T10:00:00.000+0000", "author": {"displayName": "Alex Example"},
                                  "body": "Waiting on Security."}],
             [{"at": "2026-03-05T10:00:00.000+0000", "date": "2026-03-05", "text": "Waiting on Security."}]),
            ("no date", [{"body": "Unblocked."}], [
             {"at": None, "date": None, "text": "Unblocked."}]),
            ("blank text", [
             {"created": "2026-03-05T10:00:00.000+0000", "body": "  "}], []),
            ("late in the day", [{"created": "2026-03-05T23:30:00.000+0000", "body": "Blocked."}],
             [{"at": "2026-03-05T23:30:00.000+0000", "date": "2026-03-06", "text": "Blocked."}]),
            ("deadline in ADF", [{"created": "2026-03-05T10:00:00.000+0000", "body": adf}],
             [{"at": "2026-03-05T10:00:00.000+0000", "date": "2026-03-05", "text": "Blocked until 06/03/2026."}]),
            ("written after the close", [
             {"created": "2026-03-14T10:00:00.000+0000", "body": "Unblocked."}], []),
            ("edited after the close", [{"created": "2026-03-05T10:00:00.000+0000",
                                         "updated": "2026-03-14T10:00:00.000+0000", "body": "Edited."}], []),
        ]
        for number, (name, values, expected) in enumerate(cases, start=1):
            with self.subTest(name):
                key = f"PROJ-{number}"
                if values is not None:
                    with open(os.path.join(tmp.name, f"{key}.json"), "w", encoding="utf-8") as f:
                        json.dump(values, f)
                self.assertEqual(build.blocker_comments(tmp.name, [key], CLOSE, ZoneInfo("Europe/Rome")),
                                 {key: expected})

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
                self.assertEqual(build.comments_as_of(
                    [comment], parse_ts(cutoff)), [comment] if included else [])


class MainTest(unittest.TestCase):
    """main()'s guards, on a minimal raw folder. The temporary folder is the
    skill's output folder."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        for module in (common, output_file):
            patcher = mock.patch.object(
                module, "output_folder", return_value=(self.tmp.name, False))
            patcher.start()
            self.addCleanup(patcher.stop)
        self.reset()

    # A new report folder with valid raw contents, which a test then breaks.
    def reset(self):
        self.dir = tempfile.mkdtemp(dir=self.tmp.name)
        self.sprint = {"id": 7, "name": "Sprint 7", "state": "closed", "startDate": "2026-03-02T08:00:00.000Z",
                       "endDate": "2026-03-13T16:00:00.000Z", "completeDate": "2026-03-13T16:00:00.000Z"}
        self.current, self.removed = [raw("PROJ-1")], []
        self.report = {"contents": {"issuesNotCompletedInCurrentSprint": [
            {"key": "PROJ-1"}], "puntedIssues": []}}
        self.previous = None
        self.fetched_at = "2026-03-16T09:00:00+00:00"
        # {key: changes}; by default the current issues have none and the
        # removed ones a removal.
        self.changelogs = {}
        # The raw pull request data, as fetch_sprint.py writes it.
        self.pulls = {"tickets": {}, "full_panels": [],
                      "events": {}, "skipped": []}

    def write(self, name, payload):
        path = os.path.join(self.dir, common.RAW_DIR, name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f)

    def run_main(self):
        self.write(common.META_FILE, {"label": "PROJ_Sprint_7", "fetched_at": self.fetched_at,
                   "report_timezone": "Europe/Paris",
                                      "story_points_field": "customfield_points"})
        self.write(common.STATUSES_FILE, [{"id": i, "statusCategory": {
                   "key": c}} for i, c in CATEGORIES.items()])
        self.write(common.SPRINT_FILE, self.sprint)
        self.write(common.SPRINT_ISSUES_FILE, self.current)
        self.write(common.PUNTED_ISSUES_FILE, self.removed)
        self.write(common.SPRINT_REPORT_FILE, self.report)
        self.write(common.PREVIOUS_SPRINT_FILE, self.previous)
        self.write(common.PARENTS_FILE, [])
        self.write(common.PULL_REQUESTS_FILE, self.pulls)
        for issue in self.current + self.removed:
            default = [left(at("03-04"))] if issue in self.removed else []
            self.write(os.path.join(common.CHANGELOGS_DIR, f"{issue['key']}.json"),
                       self.changelogs.get(issue["key"], default))
        argv = ["build_sprint_data.py", "--report-dir",
                self.dir]
        with mock.patch.object(sys, "argv", argv), mock.patch("builtins.print"):
            build.main()
        with open(os.path.join(self.dir, "data.json"), encoding="utf-8") as f:
            return json.load(f)

    def assert_fails(self, expected):
        with self.assertRaisesRegex(SystemExit, expected):
            self.run_main()
        self.assertFalse(os.path.exists(
            os.path.join(self.dir, "data.json")))

    def test_writes_data(self):
        data = self.run_main()
        self.assertEqual((data["sprint_start"], data["sprint_end"], data["sprint_complete_date"],
                          data["as_of_instant"], data["previous_sprint"], [t["outcome"] for t in data["spells"]]),
                         ("2026-03-02", "2026-03-13", "2026-03-13", self.sprint["completeDate"], None,
                          ["not_completed"]))

    def test_closed_sprint(self):
        # One sprint holding each case the report must name apart.
        self.previous = PREVIOUS
        self.current = [raw("PROJ-1", points=2, priority={"name": "High"}),
                        raw("PROJ-2", status="Duplicate", resolution="Done", points=3)]
        self.removed = [raw("PROJ-3"), raw("PROJ-4")]
        self.changelogs = {
            "PROJ-1": [carried()],
            "PROJ-2": [moved(at("03-04"), "To Do", "Duplicate")],
            # Moved out after the close: still in scope, but today's Jira
            # report can't vouch for it.
            "PROJ-3": [left(at("03-15"))],
            # Joined and left before the start: in no part of the report.
            "PROJ-4": [joined(at("02-27")), left(at("02-28"))],
        }
        self.report = {"contents": {"completedIssues": [{"key": "PROJ-2"}],
                                    "issuesNotCompletedInCurrentSprint": [{"key": "PROJ-1"}],
                                    "puntedIssues": [{"key": "PROJ-3"}, {"key": "PROJ-4"}]}}
        data = self.run_main()
        self.assertEqual([(t["key"], t["outcome"], t["carriedIn"]) for t in data["spells"]],
                         [("PROJ-1", "not_completed", True), ("PROJ-2", "completed", False),
                          ("PROJ-3", "not_completed", False)])
        self.assertEqual(data["previous_sprint"], {"id": 6, "name": "Sprint 6", "complete_instant":
                                                   PREVIOUS["completeDate"], "complete_date": START_DATE})
        self.assertEqual(
            data["membership_cross_check_excluded_keys"], ["PROJ-3"])
        self.assertEqual(data["left_before_start_keys"], ["PROJ-4"])
        self.assertEqual(data["non_delivery_closures"], {"count": 1, "points": 3, "issues": [
            {"key": "PROJ-2", "status": "Duplicate", "resolution": "Done", "storyPoints": 3, "marker": "duplicate",
             "summary": "Summary of PROJ-2"}]})
        self.assertEqual(data["blocker_candidate_keys"], ["PROJ-1"])
        self.assertEqual((data["points_estimated_issue_count"],
                         data["points_total_issue_count"]), (2, 3))
        # The baseline is the whole commitment, Done or not.
        self.assertEqual(data["burndown_baseline"], 5)
        self.assertEqual([r["date"]
                         for r in data["burndown"]][-1], "2026-03-13")

    def test_ticket_events_are_kept_for_the_tickets_with_spells(self):
        # PROJ-2 joined and left before the start: no spell, so no events.
        self.current, self.removed = [raw("PROJ-1")], [raw("PROJ-2")]
        self.changelogs = {"PROJ-2": [joined(at("02-27")), left(at("02-28"))]}
        self.report["contents"]["puntedIssues"] = [{"key": "PROJ-2"}]
        data = self.run_main()
        self.assertEqual(list(data["ticket_events"]), ["PROJ-1"])
        self.assertEqual([e["type"]
                         for e in data["ticket_events"]["PROJ-1"]], ["created"])

    def test_pull_requests_are_as_at_the_end(self):
        # A ticket's pull requests as at the close, beside its ticket events,
        # which stay Jira's alone: one opened after it is left out, and a
        # merge after it leaves one open then, so the ticket, To Do, is
        # flagged as started. One GitHub gave no times for stops the build.
        pr = "https://github.com/acme/api/pull/{}"
        self.pulls["tickets"] = {"PROJ-1": [
            {"url": pr.format(41), "name": "PROJ-1 add the importer", "source": {"branch": "PROJ-1-importer"},
             "via": "PROJ-1"},
            {"url": pr.format(42), "name": "Tidy the README", "via": "PROJ-1"}]}
        self.pulls["events"] = {
            pr.format(41): {"url": pr.format(41), "state": "MERGED", "createdAt": at("03-10"),
                            "mergedAt": at("03-20"), "closedAt": at("03-20")},
            pr.format(42): {"url": pr.format(42), "state": "OPEN", "createdAt": at("03-14"),
                            "mergedAt": None, "closedAt": None}}
        data = self.run_main()
        self.assertEqual(
            {e["source"] for events in data["ticket_events"].values() for e in events}, {"jira"})
        self.assertEqual(data["ticket_pull_requests"], {"PROJ-1": [
            {"url": pr.format(41), "title": "PROJ-1 add the importer", "branch": "PROJ-1-importer", "via": "PROJ-1",
             "createdAt": at("03-10"), "mergedAt": None, "closedAt": None, "own": True, "state": "open"}]})
        self.assertEqual(data["full_panel_keys"], [])
        self.assertEqual([(r["key"], r["flag"], r["linked"]) for r in data["status_checks"]],
                         [("PROJ-1", "work_started", {"merged": 0, "open": 1, "declined": 0})])
        del self.pulls["events"][pr.format(41)]
        os.remove(os.path.join(self.dir, "data.json"))
        self.assert_fails(f"PROJ-1: no GitHub times for {pr.format(41)}")

    def test_active_sprint_runs_to_the_fetch(self):
        # The fetch ends actuals both before and after the planned end.
        for day in ("2026-03-05", "2026-03-16"):
            with self.subTest(day=day):
                self.fetched_at = f"{day}T09:00:00+00:00"
                self.sprint.update(state="active", completeDate=None)
                data = self.run_main()
                self.assertEqual((data["sprint_status"], data["as_of_instant"], data["today"],
                                  data["sprint_complete_date"]), ("active", self.fetched_at, day, None))
                self.assertEqual(data["burndown"][-1]["date"], day)
                self.assertEqual(data["timeline"][-1]["labels"], ["today"])

    def test_sub_tasks_are_left_out(self):
        self.current.append(
            raw("PROJ-2", issuetype={"name": "Sub-task", "subtask": True}))
        self.assertEqual([t["key"]
                         for t in self.run_main()["spells"]], ["PROJ-1"])

    def test_guards(self):
        def change(name, value):
            return lambda: setattr(self, name, value)
        cases = [
            (change("current", []), "the sprint has no issues"),
            (change("removed", [raw(
                "PROJ-1")]), r"\['PROJ-1'\] are both in the sprint and in Jira's removed list"),
            (change("report", {}), "Jira's sprint report is missing"),
            (lambda: self.report["contents"].update(completedIssues=[{"key": "PROJ-9"}]),
             "data differs from Jira's sprint report"),
            # The raw files disagree with each other: the fetch caught the
            # sprint mid-change, so guessing would misreport it.
            (lambda: self.changelogs.update({"PROJ-1": [left(at("03-04"))]}),
             "PROJ-1 is in the sprint but its changelog says it isn't"),
            (lambda: (setattr(self, "removed", [raw("PROJ-2")]), self.changelogs.update({"PROJ-2": []})),
             "PROJ-2 is in Jira's removed list but its changelog has no removal from sprint 7"),
        ]
        for apply, expected in cases:
            with self.subTest(expected):
                self.reset()
                apply()
                self.assert_fails(expected)


if __name__ == "__main__":
    unittest.main()
