# Unit tests for skills/agentic-manager-jira-sprint-report/scripts/build_sprint_data.py.
# Run with: python3 tests/run.py agentic-manager-jira-sprint-report
#
# They call the script's functions directly with a few hand-made issues.
# test_e2e_pipeline.py runs it on a whole made-up sprint.
import json
import os
import sys
import tempfile
import unittest
from datetime import timedelta, timezone
from unittest import mock

# tests/<skill>/ mirrors skills/<skill>/.
TEST_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(TEST_DIR))
sys.path.insert(0, os.path.join(REPO_ROOT, "skills",
                os.path.basename(TEST_DIR), "scripts"))
import build_sprint_data as build  # noqa: E402
import common  # noqa: E402
from agentic_manager import output_file  # noqa: E402
from common import NO_EPIC, parse_ts  # noqa: E402

START = "2026-03-02T09:00:00.000+0100"
START_DATE = "2026-03-02"
CLOSE = "2026-03-13T17:00:00.000+0100"
FIELDS = ("customfield_flag", "customfield_points")
PLUS_ONE = timezone(timedelta(hours=1))
# {status name: (id, category)}
STATUS = {"To Do": ("1", "new"), "In Progress": ("3", "indeterminate"),
          "Done": ("10", "done"), "Duplicate": ("11", "done")}
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


def moved(created, old, new):
    return {"created": created, "field": "status", "from": STATUS[old][0], "fromString": old,
            "to": STATUS[new][0], "toString": new}


def changed(created, field, old, new, old_id=None, new_id=None):
    return {"created": created, "field": field, "from": old_id, "fromString": old,
            "to": new_id, "toString": new}


def context(epics=None, previous=None):
    return build.Context("7", START, START_DATE, CATEGORIES, FIELDS, epics or {}, PLUS_ONE, previous)


# Sprint 6 closed an hour before Sprint 7 started.
PREVIOUS = {"id": 6, "name": "Sprint 6",
            "completeDate": "2026-03-02T08:00:00.000+0100"}


def carried(created=PREVIOUS["completeDate"]):
    """Moved from Sprint 6 into Sprint 7 when Sprint 6 closed; Jira keeps
    Sprint 6 in the field."""
    return {"created": created, "field": "sprint", "from": "6", "to": "6, 7",
            "fromString": None, "toString": None}


def points(created, old, new):
    return changed(created, "points", old, new)


def spell(key, scope="original", outcome="not_completed", pts: int | float | None = 2, carried_in=False, parent=None, events=None,
          status="In Progress", marker=None):
    """A spell as build_spells returns it, with only what the later steps read."""
    return {"key": key, "summary": key, "description": f"About {key}", "status": status,
            "closedAsNonDelivery": marker, "scope": scope, "outcome": outcome, "points": pts,
            "counted": not (scope == "extra" and outcome == "removed"),
            "carriedIn": carried_in, "parentKey": parent, "parentSummary": f"Epic {parent}" if parent else None,
            "events": events or [{"at": START, "date": START_DATE, "type": "committed", "points": pts,
                                  "done": outcome == "completed"}]}


def ev(day, kind, pts=2, done=False, time="10:00", **extra):
    return {"at": at(day, time), "date": f"2026-{day}", "type": kind, "points": pts, "done": done, **extra}


class DatesTest(unittest.TestCase):
    def test_sprint_date(self):
        cases = [
            ("converted to the site offset",
             "2026-03-01T23:30:00.000Z", False, "2026-03-02"),
            ("none", None, False, None),
            # 00:00 on the 8th at +01:00: the sprint ran through the 7th.
            ("an end on midnight names the last day worked",
             "2026-03-07T23:00:00.000Z", True, "2026-03-07"),
            ("an end during the day", "2026-03-07T16:00:00.000Z", True, "2026-03-07"),
            ("an end just after midnight stays on that day",
             "2026-03-07T23:00:00.500Z", True, "2026-03-08"),
        ]
        for name, ts, end_of_period, expected in cases:
            with self.subTest(name):
                self.assertEqual(build.sprint_date(
                    ts, PLUS_ONE, end_of_period=end_of_period), expected)


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
        created = "2026-02-20T10:00:00.000+0100"
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
                    changes, created, PREVIOUS), expected)
        self.assertFalse(build.in_sprint_when_closed(
            [carried()], created, None))

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
                found = build.build_spells(
                    raw("PROJ-1"), changes, context(previous=previous), CLOSE)
                self.assertEqual([s["carriedIn"] for s in found], expected)


class SpellsTest(unittest.TestCase):
    def build(self, changes, issue=None, moment=CLOSE):
        return build.build_spells(issue or raw("PROJ-1"), changes, context(), moment)

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
                found = build.build_spells(issue, [], context(epics), CLOSE)[0]
                self.assertEqual(
                    (found["parentKey"], found["parentSummary"]), expected)
                self.assertNotIn("parentId", found)


class ReplayTest(unittest.TestCase):
    def test_replay(self):
        events = [ev("03-02", "committed"), ev("03-04", "completed",
                                               done=True), ev("03-05", "removed", done=True)]
        cases = [("before it entered", at("03-01"), None), ("committed", at("03-03"), (True, False, 2)),
                 ("completed", at("03-04"), (True, True, 2)), ("removed", at("03-06"), (False, True, 2))]
        for name, until, expected in cases:
            with self.subTest(name):
                self.assertEqual(build.replay(
                    events, parse_ts(until)), expected)


class BreakdownAndEpicsTest(unittest.TestCase):
    TICKETS = [spell("PROJ-1", outcome="completed", pts=3, parent="PROJ-100", carried_in=True),
               spell("PROJ-2", outcome="removed", pts=1, parent="PROJ-100"),
               spell("PROJ-3", outcome="not_completed",
                     pts=None, parent="PROJ-100"),
               spell("PROJ-4", scope="extra", outcome="completed", pts=5, parent="PROJ-200")]

    def test_outcome_breakdown(self):
        counts, points_ = build.outcome_breakdown(self.TICKETS)
        self.assertEqual({k: v for k, v in counts.items() if v}, {
            "original_completed": 1, "original_removed": 1, "original_not_completed": 1,
            "carried_in_completed": 1, "new_removed": 1, "new_not_completed": 1, "extra_completed": 1})
        self.assertEqual({k: v for k, v in points_.items() if v}, {
            "original_completed": 3, "original_removed": 1, "carried_in_completed": 3, "new_removed": 1,
            "extra_completed": 5})

    def test_extra_spells_that_ended_descoped_are_not_counted(self):
        uncounted = spell("PROJ-9", scope="extra",
                          outcome="removed", pts=8, parent="PROJ-300")
        self.assertEqual(build.outcome_breakdown(
            self.TICKETS + [uncounted]), build.outcome_breakdown(self.TICKETS))
        self.assertNotIn(
            "PROJ-300", [e["key"] for e in build.build_epics(self.TICKETS + [uncounted])])

    def test_epics(self):
        epics = build.build_epics(
            self.TICKETS + [spell("PROJ-5", scope="extra", pts=1)])
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
        # figures count it.
        def completed_in_sprint(key, **extra):
            return spell(key, outcome="completed", parent="PROJ-100", **extra,
                         events=[ev("03-02", "committed"), ev("03-04", "completed", done=True)])
        spells = [
            completed_in_sprint("PROJ-1"),
            spell("PROJ-2", outcome="completed",
                  parent="PROJ-100"),  # Done at the start
            completed_in_sprint(
                "PROJ-3", marker="duplicate", status="Duplicate"),
            spell("PROJ-4", parent="PROJ-100", status="In Review"),
            spell("PROJ-5", parent="PROJ-100", status="Code review"),
            spell("PROJ-6", parent="PROJ-100", status="To Do"),
            spell("PROJ-7", outcome="removed",
                  parent="PROJ-100", status="In Review"),
            spell("PROJ-8", scope="extra", outcome="removed",
                  parent="PROJ-100"),  # not counted
            spell("PROJ-9", scope="extra", outcome="completed", parent="PROJ-100",
                  # joined already Done
                  events=[ev("03-03", "joined", done=True)]),
            spell("PROJ-10", outcome="removed", parent="PROJ-100",
                  # Done, then descoped
                  events=[ev("03-02", "committed", done=True), ev("03-04", "removed", done=True)]),
            spell("PROJ-11", outcome="removed", parent="PROJ-100",
                  events=[ev("03-02", "committed", done=True), ev("03-03", "reopened"), ev("03-04", "removed")]),
        ]
        spells[3]["flagged"] = True
        epic = build.build_epics(spells, {"PROJ-100": "Staff sign-in"})[0]
        self.assertEqual(epic["description"], "Staff sign-in")
        self.assertEqual({group: [t["key"] for t in tickets] for group, tickets in epic["scope_groups"].items()},
                         {"completed": ["PROJ-1"], "in_review": ["PROJ-4", "PROJ-5"], "not_completed": ["PROJ-6"],
                          "descoped": ["PROJ-7", "PROJ-11"]})
        self.assertEqual([(t["key"], t["reason"]) for t in epic["left_out"]],
                         [("PROJ-2", "done_at_start"), ("PROJ-3", "non_delivery"), ("PROJ-9", "done_at_start"),
                          ("PROJ-10", "done_at_start")])
        # Each ticket carries what the commentary needs to describe it,
        # including its estimate, status and flag.
        self.assertEqual(epic["scope_groups"]["in_review"][0],
                         {"key": "PROJ-4", "scope": "original", "points": 2, "status": "In Review", "flagged": True,
                          "summary": "PROJ-4", "description": "About PROJ-4"})
        self.assertEqual(epic["left_out"][1],
                         {"key": "PROJ-3", "scope": "original", "points": 2, "status": "Duplicate", "flagged": False,
                          "summary": "PROJ-3", "description": "About PROJ-3", "reason": "non_delivery"})
        self.assertEqual(epic["original_stories_done"], 3)
        self.assertEqual(build.build_epics(spells)[0]["description"], "")

    def test_description(self):
        long = "word " * 500
        cases = [("none", {}, ""), ("text", {"description": "Fix  the\nexport"}, "Fix the\nexport"),
                 ("cut", {"description": long}, long[:build.DESCRIPTION_CHARS].rstrip() + "…")]
        for name, fields, expected in cases:
            with self.subTest(name):
                self.assertEqual(build.description(fields), expected)
        self.assertEqual(build.epic_descriptions([{"key": "PROJ-100", "fields": {"description": "Sign-in"}},
                                                  {"id": "7", "fields": {}}]), {"PROJ-100": "Sign-in"})


class TimelineTest(unittest.TestCase):
    def test_timeline(self):
        tickets = [spell("PROJ-10", events=[ev("03-02", "committed"), ev("03-04", "completed", done=True)]),
                   spell("PROJ-2", scope="extra", events=[ev("03-04", "joined", pts=1)])]
        rows = build.build_timeline(
            tickets, "closed", "2026-03-02", "2026-03-13", "2026-03-13", "2026-03-16")
        self.assertEqual([(r["date"], r["labels"], [(e["key"], e["type"]) for e in r["events"]]) for r in rows], [
            ("2026-03-02", ["sprint_start"], [("PROJ-10", "committed")]),
            ("2026-03-04", [], [("PROJ-2", "joined"), ("PROJ-10", "completed")]),
            ("2026-03-13", ["sprint_closed"], [])])
        self.assertEqual(rows[1]["events"][0], {"key": "PROJ-2", "scope": "extra", "at": at("03-04"), "type": "joined",
                                                "points": 1, "done": False})

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
            spell("PROJ-1", pts=3, events=[ev("03-02", "committed", 3, time="09:00"),
                                           ev("03-03", "completed", 3, done=True)]),
            spell("PROJ-2", pts=5, events=[ev("03-02", "committed", 2, time="09:00"),
                                           ev("03-04", "reestimated", 5, fromPoints=2)]),
            spell("PROJ-3", events=[ev("03-02", "committed",
                  1, time="09:00"), ev("03-05", "removed", 1)]),
            # Joined, left (an uncounted spell), then came back done: a new spell.
            spell("PROJ-4", scope="extra", outcome="removed",
                  events=[ev("03-03", "joined", 4), ev("03-04", "removed", 4)]),
            spell("PROJ-4", scope="extra", outcome="completed",
                  events=[ev("03-05", "joined", 4, done=True)]),
            spell("PROJ-5", events=[ev("03-02", "committed", 6, done=True, time="09:00"),
                                    ev("03-05", "reopened", 6)]),
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
              "with --board, using another scrum board of the project"]),
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
        issues = [raw("PROJ-1"), done("PROJ-2"), raw("PROJ-3"),
                  raw("PROJ-4"), done("PROJ-5")]
        changes = {"PROJ-1": [], "PROJ-2": [moved(at("03-04"), "To Do", "Done")],
                   "PROJ-3": [joined(at("03-03")), left(at("03-05"))],
                   "PROJ-4": [joined(at("02-27")), left(at("02-28"))],
                   "PROJ-5": [moved(at("03-14"), "To Do", "Done")]}
        self.assertEqual(build.membership_sets(issues, changes, context(), CLOSE),
                         (["PROJ-1", "PROJ-2", "PROJ-5"], ["PROJ-2"], ["PROJ-3", "PROJ-4"]))


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
        self.write_report = True
        self.previous = None
        self.write_previous = True
        self.fetched_at = "2026-03-16T09:00:00+00:00"
        # {key: changes}; by default the current issues have none and the
        # removed ones a removal.
        self.changelogs = {}

    def write(self, name, payload):
        path = os.path.join(self.dir, "_raw", name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f)

    def run_main(self):
        self.write("_meta.json", {"label": "PROJ_Sprint_7", "fetched_at": self.fetched_at,
                   "report_timezone": "Europe/Paris",
                                  "story_points_field": "customfield_points"})
        self.write("statuses.json", [{"id": i, "statusCategory": {
                   "key": c}} for i, c in CATEGORIES.items()])
        self.write("sprint.json", self.sprint)
        self.write("sprint_issues.json", self.current)
        self.write("punted_issues.json", self.removed)
        if self.write_report:
            self.write("sprint_report.json", self.report)
        if self.write_previous:
            self.write("previous_sprint.json", self.previous)
        for issue in self.current + self.removed:
            default = [left(at("03-04"))] if issue in self.removed else []
            self.write(f"changelogs/{issue['key']}.json",
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
            (change("fetched_at", None), "no fetch timestamp"),
            (change("current", []), "the sprint has no issues"),
            (lambda: self.sprint.update(state="future"),
             "sprint state 'future': only active and closed sprints"),
            (lambda: self.sprint.update(startDate=None),
             "the sprint has no start or end date"),
            (lambda: self.sprint.update(endDate=None),
             "the sprint has no start or end date"),
            (change("removed", [raw(
                "PROJ-1")]), r"\['PROJ-1'\] are both in the sprint and in Jira's removed list"),
            (change("write_report", False), "Jira's sprint report is missing"),
            (change("write_previous", False), "no previous_sprint.json"),
            (lambda: self.report["contents"].update(completedIssues=[{"key": "PROJ-9"}]),
             "data differs from Jira's sprint report"),
            (lambda: (self.sprint.update(state="active"), setattr(self, "fetched_at", None)),
             "can't tell the moment the report describes"),
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
