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


def context(epics=None):
    return build.Context("7", START, START_DATE, CATEGORIES, FIELDS, epics or {})


def issue(key, points=None, extra=False, carried=False, parent=None, already=False, removed_done=False,
          entered=START_DATE, returns=(), departures=(), done_at_departures=None, completion=None):
    """An issue as build_issue returns it, with only what the later steps read."""
    return {"key": key, "summary": key, "storyPoints": points, "addedMidSprint": extra,
            "carriedOver": carried, "parentKey": parent, "parentSummary": f"Epic {parent}" if parent else None,
            "alreadyDoneOnArrival": already, "wasDoneAtRemoval": removed_done,
            "enteredSprintOn": entered, "returnEvents": list(returns), "departureEvents": list(departures),
            "doneAtDepartures": (list(done_at_departures) if done_at_departures is not None
                                 else [removed_done] * len(departures)),
            "effectiveCompletionDate": completion}


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
        ]
        for name, ts, end_of_period, expected in cases:
            with self.subTest(name):
                self.assertEqual(build.sprint_date(
                    ts, PLUS_ONE, end_of_period=end_of_period), expected)

    def test_site_offset(self):
        cases = [
            ("from the first issue with a creation time",
             ([{"fields": {}}, raw("PROJ-1", created="2026-03-01T10:00:00.000+0200")],),
             timezone(timedelta(hours=2))),
            ("from the fallback timestamp",
             ([], "2026-03-01T10:00:00.000+0100"), PLUS_ONE),
            ("UTC with neither", ([],), timezone.utc),
        ]
        for name, args, expected in cases:
            with self.subTest(name):
                self.assertEqual(build.site_offset(*args), expected)


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


class MembershipTest(unittest.TestCase):
    def test_membership(self):
        created = "2026-02-20T10:00:00.000+0100"
        before, before_2 = "2026-02-27T10:00:00.000+0100", "2026-02-28T10:00:00.000+0100"
        just_after = "2026-03-02T09:00:01.000+0100"
        day_3, day_4, day_5 = ("2026-03-03T10:00:00.000+0100", "2026-03-04T10:00:00.000+0100",
                               "2026-03-05T10:00:00.000+0100")
        # name: (added, removed, created, expected (entered, extra, returns, departures) or None)
        cases = {
            "in the sprint at the start is original": ([before_2], [], created, (None, False, [], [])),
            "added at the start instant is original": ([START], [], created, (None, False, [], [])),
            "added after the start is extra, even the same day": ([just_after], [], created,
                                                                  (just_after, True, [], [])),
            "created in the sprint before the start has no add": ([], [], created, (None, False, [], [])),
            "created in the sprint after the start is extra": ([], [], day_5, (day_5, True, [], [])),
            "a removal first means it was added at creation": ([], [day_4], created, (None, False, [], [day_4])),
            "joined and left before the start isn't in the sprint": ([before], [before_2], created, None),
            "departures and returns after entering": ([day_3, day_5], [day_4], created,
                                                      (day_3, True, [day_5], [day_4])),
            "original work stays original after leaving and returning": ([before_2, day_5], [day_4], created,
                                                                         (None, False, [day_5], [day_4])),
        }
        for name, (added, removed, created_at, expected) in cases.items():
            with self.subTest(name):
                self.assertEqual(build.membership(
                    added, removed, created_at, parse_ts(START)), expected)


class BuildIssueTest(unittest.TestCase):
    def test_build_issue(self):
        # name: (raw issue as it is today, its changes, expected facts at the close)
        cases = {
            "original work": (raw("PROJ-1", points=3), [], {
                "addedMidSprint": False, "enteredSprintAt": START, "enteredSprintOn": START_DATE,
                "alreadyDoneOnArrival": False, "completedAt": None, "effectiveCompletionDate": None}),
            "extra work completed in the sprint": (
                done("PROJ-1"), [joined(at("03-04")), moved(at("03-06"), "In Progress", "Done")], {
                    "addedMidSprint": True, "enteredSprintOn": "2026-03-04", "alreadyDoneOnArrival": False,
                    "completedAt": at("03-06"), "effectiveCompletionDate": "2026-03-06"}),
            "done before the start is credited at the start": (
                done("PROJ-1"), [moved(at("02-27"), "In Progress", "Done")], {
                    "addedMidSprint": False, "alreadyDoneOnArrival": True,
                    "effectiveCompletionDate": START_DATE}),
            "done before joining is credited on joining": (
                done("PROJ-1"), [moved(at("03-03"), "In Progress", "Done"), joined(at("03-05"))], {
                    "alreadyDoneOnArrival": True, "effectiveCompletionDate": "2026-03-05"}),
            "created Done completed when created": (done("PROJ-1"), [], {
                "alreadyDoneOnArrival": True, "completedAt": "2026-02-20T10:00:00.000+0100"}),
            # Done at the start, so not initial commitment: reopening it adds scope.
            "done at the start, reopened and done again is extra delivery": (
                done("PROJ-1"), [moved(at("02-27"), "In Progress", "Done"), moved(at("03-03"), "Done", "To Do"),
                                 moved(at("03-06"), "To Do", "Done")], {
                    "addedMidSprint": True, "enteredSprintOn": "2026-03-03", "alreadyDoneOnArrival": False,
                    "effectiveCompletionDate": "2026-03-06"}),
            "done at the start and reopened is open extra work": (
                raw("PROJ-1", status="In Progress"),
                [moved(at("02-27"), "In Progress", "Done"), moved(at("03-03"), "Done", "In Progress")], {
                    "addedMidSprint": True, "enteredSprintOn": "2026-03-03", "statusCategory": "indeterminate",
                    "alreadyDoneOnArrival": False, "completedAt": None}),
            "done at the start and reopened only after the close stays original": (
                done("PROJ-1"), [moved(at("02-27"), "In Progress", "Done"), moved(at("03-16"), "Done", "To Do")], {
                    "addedMidSprint": False, "alreadyDoneOnArrival": True}),
            "done at the start and reopened while out of the sprint stays original": (
                raw("PROJ-1", status="In Progress"),
                [moved(at("02-27"), "In Progress", "Done"), left(at("03-03")),
                 moved(at("03-04"), "Done", "In Progress"), joined(at("03-05"))], {
                    "addedMidSprint": False, "returnEvents": [at("03-05")]}),
            "a move between Done statuses isn't a new completion": (
                raw("PROJ-1", status="Duplicate"),
                [moved(at("03-04"), "In Progress", "Done"), moved(at("03-06"), "Done", "Duplicate")], {
                    "status": "Duplicate", "completedAt": at("03-04")}),
            # The report describes the close: what happened later changes nothing.
            "reopened after the close is Done": (
                raw("PROJ-1", status="To Do", points=8),
                [moved(at("03-06"), "In Progress", "Done"), moved(at("03-16"), "Done", "To Do"),
                 changed(at("03-16"), "points", "3", "8")], {
                    "status": "Done", "statusCategory": "done", "storyPoints": 3,
                    "effectiveCompletionDate": "2026-03-06"}),
            "completed after the close is open": (
                done("PROJ-1"), [moved(at("03-14"), "In Progress", "Done")], {
                    "status": "In Progress", "completedAt": None, "effectiveCompletionDate": None}),
            "the epic it was in at the close": (
                raw("PROJ-1", parent="PROJ-100"),
                [changed(at("03-16"), "parent", "PROJ-200", "PROJ-100", "1200", "id-PROJ-100")], {
                    "parentKey": "PROJ-200", "parentSummary": "Old epic"}),
            "flag and priority at the close": (
                raw("PROJ-1", priority={"name": "Low"}),
                [changed(at("03-10"), "flagged", None, "Impediment"),
                 changed(at("03-16"), "flagged", "Impediment", None),
                 changed(at("03-16"), "priority", "Highest", "Low")], {
                    "flagged": True, "priority": "Highest"}),
        }
        epics = {"1200": ("PROJ-200", "Old epic"),
                 "id-PROJ-100": ("PROJ-100", "Epic PROJ-100")}
        for name, (issue_raw, changes, expected) in cases.items():
            with self.subTest(name):
                facts = build.build_issue(
                    issue_raw, changes, context(epics), CLOSE)
                assert facts is not None
                self.assertEqual({k: facts[k] for k in expected}, expected)

    def test_not_in_the_sprint_after_the_start(self):
        self.assertIsNone(build.build_issue(raw("PROJ-1"), [joined(at("02-27")), left(at("02-28"))],
                                            context(), CLOSE))

    def test_done_at_each_departure(self):
        facts = build.build_issue(
            done("PROJ-1"), [left(at("03-04")), joined(at("03-05")), moved(at("03-06"), "In Progress", "Done"),
                             left(at("03-09"))], context())
        assert facts is not None
        self.assertEqual((facts["departureEvents"], facts["doneAtDepartures"], facts["stateAt"]),
                         ([at("03-04"), at("03-09")], [False, True], at("03-09")))


class CurrentAndRemovedTest(unittest.TestCase):
    def test_movements_are_bounded_by_the_cutoff(self):
        changes = [joined(at("02-27")), left(at("03-16")), joined(at("03-17"))]
        facts = build.build_issue(raw("PROJ-1"), changes, context(), CLOSE)
        self.assertEqual((facts["departureEvents"], facts["returnEvents"], facts["sprintRemoveEvents"]),
                         ([], [], []))
        current, removed = build.scope_at(
            [raw("PROJ-1")], {"PROJ-1": changes}, context(), CLOSE)
        self.assertEqual(([i["key"] for i in current],
                         removed), (["PROJ-1"], []))

    def test_future_entry_is_not_reported(self):
        changes = [joined(at("03-16"))]
        self.assertIsNone(build.build_issue(
            raw("PROJ-1"), changes, context(), CLOSE))
        self.assertEqual(build.scope_at(
            [raw("PROJ-1")], {"PROJ-1": changes}, context(), CLOSE), ([], []))

    def test_removed_state_uses_the_last_departure_before_close(self):
        changes = [left(at("03-05")), joined(at("03-16")), left(at("03-17"))]
        issues, _ = build.build_removed_issues(
            [raw("PROJ-1")], {"PROJ-1": changes}, context(), CLOSE)
        self.assertEqual(issues[0]["stateAt"], at("03-05"))
        self.assertEqual(issues[0]["returnEvents"], [])

    def test_current_outcomes(self):
        issues = [raw("PROJ-1"), done("PROJ-2"), done("PROJ-3"),
                  raw("PROJ-4", status="Duplicate", resolution="Done")]
        changes = {"PROJ-1": [], "PROJ-2": [moved(at("03-10"), "In Progress", "Done")],
                   "PROJ-3": [moved(at("03-14"), "In Progress", "Done")],
                   "PROJ-4": [moved(at("03-05"), "In Progress", "Duplicate")]}
        current = {i["key"]: i for i in build.build_current_issues(
            issues, changes, context(), CLOSE)}
        self.assertEqual({k: (i["carriedOver"], i["closedAsNonDelivery"]) for k, i in current.items()},
                         {"PROJ-1": (True, None), "PROJ-2": (False, None),
                          "PROJ-3": (True, None), "PROJ-4": (False, "duplicate")})

    def test_active_sprint_is_as_at_the_fetch(self):
        fetched = at("03-14", "12:00")
        current = build.build_current_issues(
            [done("PROJ-3")], {"PROJ-3": [moved(at("03-14"), "In Progress", "Done")]}, context(), fetched)
        self.assertFalse(current[0]["carriedOver"])

    def test_current_issue_whose_changelog_disagrees(self):
        changes = {"PROJ-1": [joined(at("02-27")), left(at("02-28"))]}
        with self.assertRaisesRegex(SystemExit, "PROJ-1 is in the sprint but its changelog says it isn't"):
            build.build_current_issues(
                [raw("PROJ-1")], changes, context(), CLOSE)

    def test_removed_issues(self):
        issues = [raw("PROJ-1"), raw("PROJ-2", status="To Do"),
                  raw("PROJ-3"), done("PROJ-4")]
        changes = {"PROJ-1": [left(at("03-05"))],
                   # Done at its removal, reopened since: it is reported as it was then.
                   "PROJ-2": [moved(at("03-04"), "In Progress", "Done"), left(at("03-05")),
                              moved(at("03-20"), "Done", "To Do")],
                   "PROJ-3": [joined(at("02-27")), left(at("02-28"))],
                   # Removed while open and completed later: not Done at its removal.
                   "PROJ-4": [left(at("03-05")), moved(at("03-06"), "In Progress", "Done")]}
        removed, before_start = build.build_removed_issues(
            issues, changes, context())
        self.assertEqual([(i["key"], i["wasDoneAtRemoval"], i["status"], i["removedFromSprintAt"])
                          for i in removed],
                         [("PROJ-1", False, "To Do", at("03-05")), ("PROJ-2", True, "Done", at("03-05")),
                          ("PROJ-4", False, "In Progress", at("03-05"))])
        self.assertEqual(before_start, ["PROJ-3"])

    def test_reopened_then_removed_is_extra_scope_descoped(self):
        changes = {"PROJ-1": [moved(at("02-27"), "In Progress", "Done"), moved(at("03-03"), "Done", "In Progress"),
                              left(at("03-05"))]}
        removed, _ = build.build_removed_issues(
            [raw("PROJ-1", status="In Progress")], changes, context())
        issue = removed[0]
        self.assertEqual((issue["addedMidSprint"], issue["enteredSprintOn"], issue["wasDoneAtRemoval"],
                          issue["departureEvents"]), (True, "2026-03-03", False, [at("03-05")]))

    def test_removed_issue_without_a_removal(self):
        with self.assertRaisesRegex(SystemExit, "PROJ-1 is in Jira's removed list but its changelog"):
            build.build_removed_issues(
                [raw("PROJ-1")], {"PROJ-1": []}, context())


class TotalsAndEpicsTest(unittest.TestCase):
    def test_totals(self):
        self.assertEqual(build.totals(
            [issue("PROJ-1", 3), issue("PROJ-2", None)]), {"count": 2, "points": 3})

    def test_bucketed(self):
        counts, points = build.bucketed([issue("PROJ-1", 3), issue("PROJ-2", 2, carried=True), issue("PROJ-3", None)],
                                        lambda i: "carried" if i["carriedOver"] else "done",
                                        ("done", "carried", "unused"))
        self.assertEqual((counts, points), ({"done": 2, "carried": 1, "unused": 0},
                                            {"done": 3, "carried": 2, "unused": 0}))

    def test_epics(self):
        current = [issue("PROJ-1", 3, parent="PROJ-100"), issue("PROJ-2", 2, parent="PROJ-100", carried=True),
                   issue("PROJ-3", 5, extra=True, parent="PROJ-200"), issue("PROJ-4", 1)]
        removed = [issue("PROJ-5", 2, parent="PROJ-100", removed_done=True),
                   issue("PROJ-6", 1, parent="PROJ-100"),
                   issue("PROJ-7", 4, parent="PROJ-300", removed_done=True, already=True)]
        epics = {e["key"]: e for e in build.build_epics(current, removed)}
        self.assertEqual([e["key"] for e in build.build_epics(current, removed)],
                         ["PROJ-100", "PROJ-200", NO_EPIC, "PROJ-300"])
        proj_100 = epics["PROJ-100"]
        self.assertEqual((proj_100["original_stories_total"], proj_100["original_stories_done"],
                          proj_100["original_points_total"], proj_100["original_points_done"]), (4, 2, 8, 5))
        self.assertEqual((proj_100["removed_stories"], proj_100["removed_points"],
                          proj_100["removed_done_stories"], proj_100["removed_done_points"]), (2, 3, 1, 2))
        self.assertEqual((epics["PROJ-200"]["extra_stories_total"],
                         epics["PROJ-200"]["extra_points_done"]), (1, 5))
        self.assertEqual(epics[NO_EPIC]["name"], "(no epic)")
        # Already Done when it entered: counted as removed, never in the delivery figures.
        proj_300 = epics["PROJ-300"]
        self.assertEqual(
            (proj_300["removed_done_stories"], proj_300["original_stories_total"]), (1, 0))


class BurndownTest(unittest.TestCase):
    def series(self, issue_raw, changes, cutoff=CLOSE):
        facts = build.build_issue(issue_raw, changes, context(), cutoff)
        return {row["date"]: row for row in build.build_burndown(
            [issue_raw], {issue_raw["key"]: changes}, context(), [
                facts], PLUS_ONE, cutoff,
            build.sprint_date(cutoff, PLUS_ONE))}

    def test_daily_status_points_and_membership(self):
        cases = [
            ("reopened", raw("PROJ-1", points=4),
             [moved(at("03-05"), "To Do", "Done"),
              moved(at("03-09"), "Done", "To Do")],
             {"2026-03-04": 4, "2026-03-05": 0, "2026-03-08": 0, "2026-03-09": 4}),
            ("re-estimated", raw("PROJ-1", points=8), [changed(at("03-06"), "points", "3", "8")],
             {"2026-03-02": 3, "2026-03-05": 3, "2026-03-06": 8}),
            ("departed and returned", raw("PROJ-1", points=2),
             [left(at("03-05")), joined(at("03-07"))],
             {"2026-03-04": 2, "2026-03-05": 0, "2026-03-06": 0, "2026-03-07": 2}),
            ("after close on the same day", done("PROJ-1", points=8),
             [moved(at("03-13", "18:00"), "To Do", "Done"),
              changed(at("03-13", "18:00"), "points", "3", "8"), left(at("03-13", "18:00"))],
             {"2026-03-13": 3}),
        ]
        for name, issue_raw, changes, expected in cases:
            with self.subTest(name):
                rows = self.series(issue_raw, changes)
                self.assertEqual({day: rows[day]["committed"]
                                 for day in expected}, expected)

    def test_start_state_is_kept_when_the_issue_is_reopened_and_re_estimated(self):
        facts = build.build_issue(raw("PROJ-1", points=8),
                                  [moved(at("03-04"), "Done", "To Do"),
                                   changed(at("03-06"), "points", "3", "8")], context(), CLOSE)
        self.assertEqual(facts["startState"], {"storyPoints": 3, "done": True})
        # Reopened in the sprint, so extra scope: it is never in the baseline.
        self.assertEqual(
            (facts["addedMidSprint"], facts["alreadyDoneOnArrival"]), (True, False))

    def test_active_snapshot_stops_at_fetch_instant(self):
        rows = self.series(done("PROJ-1", points=3),
                           [moved(at("03-06", "15:00"), "To Do", "Done")], at("03-06", "12:00"))
        self.assertEqual(rows["2026-03-06"]["committed"], 3)
        self.assertNotIn("2026-03-07", rows)


class ScopeTimelineTest(unittest.TestCase):
    def timeline(self, current, removed=(), status="closed", today="2026-03-10"):
        return build.build_scope_timeline(current, list(removed), status, START_DATE, "2026-03-13",
                                          "2026-03-13", today)

    def rows(self, *args, **kwargs):
        return {row["date"]: row for row in self.timeline(*args, **kwargs)}

    def test_a_closed_sprint_without_dates_gets_no_close_row(self):
        rows = build.build_scope_timeline(
            [], [], "closed", START_DATE, None, None, "2026-03-10")
        self.assertEqual([r["labels"] for r in rows], [["sprint_start"]])

    def test_labels(self):
        self.assertEqual({d: r["labels"] for d, r in self.rows([]).items()},
                         {START_DATE: ["sprint_start"], "2026-03-13": ["sprint_closed"]})
        self.assertEqual(self.rows([], status="active")[
                         "2026-03-10"]["labels"], ["today"])

    def test_entries_and_completions(self):
        rows = self.rows([
            issue("PROJ-2", 3, completion="2026-03-05"),
            issue("PROJ-1", 2, extra=True, entered="2026-03-04",
                  completion="2026-03-06"),
            issue("PROJ-3", 1, already=True, completion=START_DATE),
        ])
        self.assertEqual((rows[START_DATE]["added_keys"], rows[START_DATE]
                         ["added_points"]), (["PROJ-2", "PROJ-3"], 4))
        self.assertEqual(
            rows[START_DATE]["already_done_original_keys"], ["PROJ-3"])
        self.assertEqual((rows["2026-03-04"]["added_keys"],
                         rows["2026-03-04"]["added_points"]), (["PROJ-1"], 2))
        self.assertEqual(rows["2026-03-05"]["completed_original_points"], 3)
        self.assertEqual(rows["2026-03-06"]
                         ["completed_extra_keys"], ["PROJ-1"])

    def test_cross_day_departure_and_return(self):
        rows = self.rows([issue("PROJ-1", 3, departures=["2026-03-04T10:00:00.000+0100"],
                                returns=["2026-03-05T10:00:00.000+0100"])])
        self.assertEqual((rows["2026-03-04"]["departure_keys"],
                         rows["2026-03-04"]["departure_points"]), (["PROJ-1"], 3))
        self.assertEqual((rows["2026-03-05"]["readded_keys"],
                         rows["2026-03-05"]["readded_points"]), (["PROJ-1"], 3))

    def test_leaving_and_returning_the_same_day_cancels_out(self):
        rows = self.rows([issue("PROJ-1", 3, departures=["2026-03-04T10:00:00.000+0100"],
                                returns=["2026-03-04T15:00:00.000+0100"])])
        self.assertNotIn("2026-03-04", rows)

    def test_removed_issues(self):
        rows = self.rows([], [
            issue("PROJ-1", 2, departures=["2026-03-05T10:00:00.000+0100"]),
            issue("PROJ-2", 3, departures=["2026-03-06T10:00:00.000+0100"], removed_done=True,
                  completion="2026-03-04"),
            # Already Done when it entered: a removal only, never a completion.
            issue("PROJ-3", 1, departures=["2026-03-02T15:00:00.000+0100"], removed_done=True, already=True,
                  completion=START_DATE),
        ])
        self.assertEqual(rows["2026-03-05"]["departure_keys"], ["PROJ-1"])
        self.assertEqual(rows["2026-03-05"]["removed_done_keys"], [])
        self.assertEqual(rows["2026-03-06"]["removed_done_keys"], ["PROJ-2"])
        self.assertEqual(rows["2026-03-04"]
                         ["completed_original_keys"], ["PROJ-2"])
        start = rows[START_DATE]
        self.assertEqual(
            (start["departure_keys"], start["removed_done_keys"]), (["PROJ-3"], ["PROJ-3"]))
        self.assertEqual((start["completed_original_keys"],
                         start["already_done_original_keys"]), ([], []))

    def test_done_is_judged_at_each_departure(self):
        rows = self.rows([issue("PROJ-1", 2, departures=["2026-03-04T10:00:00.000+0100"],
                                returns=["2026-03-05T10:00:00.000+0100"], done_at_departures=[False],
                                completion="2026-03-09")])
        self.assertEqual((rows["2026-03-04"]["departure_keys"], rows["2026-03-04"]["removed_done_keys"]),
                         (["PROJ-1"], []))


class CrossCheckTest(unittest.TestCase):
    CURRENT = [issue("PROJ-1"), issue("PROJ-2", carried=True)]
    REMOVED = [issue("PROJ-3")]

    def report(self, completed=("PROJ-1",), not_completed=("PROJ-2",), punted=("PROJ-3", "PROJ-9")):
        def keys(ks):
            return [{"key": k} for k in ks]
        return {"contents": {"completedIssues": keys(completed),
                             "issuesNotCompletedInCurrentSprint": keys(not_completed),
                             "puntedIssues": keys(punted)}}

    def check(self, report):
        return build.cross_check(report, self.CURRENT, self.REMOVED, ["PROJ-9"])

    def test_agreeing(self):
        self.assertEqual(self.check(self.report()), [])

    def test_completed_in_another_sprint_counts_as_completed(self):
        report = self.report(completed=())
        report["contents"]["issuesCompletedInAnotherSprint"] = [
            {"key": "PROJ-1"}]
        self.assertEqual(self.check(report), [])

    def test_missing_report(self):
        self.assertIsNone(self.check({}))
        self.assertIsNone(self.check(None))

    def test_empty_report(self):
        self.assertIn("this board doesn't serve it", " ".join(
            self.check(self.report((), (), ())) or []))

    def test_differences_both_ways(self):
        self.assertEqual(self.check(self.report(completed=("PROJ-1", "PROJ-5"), punted=("PROJ-9",))), [
            "in-scope: ['PROJ-5'] in Jira's sprint report but not in our data",
            "completed: ['PROJ-5'] in Jira's sprint report but not in our data",
            "removed: ['PROJ-3'] in our data but not in Jira's sprint report"])


class MainTest(unittest.TestCase):
    """main()'s guards, on a minimal raw folder."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
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
        self.fetched_at = "2026-03-16T09:00:00+00:00"

    def write(self, name, payload):
        path = os.path.join(self.dir, "_raw", name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f)

    def run_main(self):
        self.write("_meta.json", {"label": "PROJ_Sprint_7", "fetched_at": self.fetched_at,
                   "story_points_field": "customfield_points"})
        self.write("statuses.json", [{"id": i, "statusCategory": {
                   "key": c}} for i, c in CATEGORIES.items()])
        self.write("sprint.json", self.sprint)
        self.write("sprint_issues.json", self.current)
        self.write("punted_issues.json", self.removed)
        if self.write_report:
            self.write("sprint_report.json", self.report)
        for issue in self.current + self.removed:
            self.write(f"changelogs/{issue['key']}.json",
                       [left("2026-03-04T10:00:00.000+0100")] if issue in self.removed else [])
        argv = ["build_sprint_data.py", "--report-dir",
                self.dir, "--today", "2026-03-16"]
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
        self.assertEqual((data["sprint_start"], data["sprint_end"], data["outcome_counts"]),
                         ("2026-03-02", "2026-03-13", {"completed": 0, "carried_over": 1}))

    def test_sub_tasks_are_left_out(self):
        self.current.append(
            raw("PROJ-2", issuetype={"name": "Sub-task", "subtask": True}))
        self.assertEqual([i["key"]
                         for i in self.run_main()["issues"]], ["PROJ-1"])

    def test_guards(self):
        def change(name, value):
            return lambda: setattr(self, name, value)
        cases = [
            (change("current", []), "the sprint has no issues"),
            (lambda: self.sprint.update(state="future"),
             "sprint state 'future': only active and closed sprints"),
            (lambda: self.sprint.update(startDate=None),
             "the sprint has no start date"),
            (change("removed", [raw(
                "PROJ-1")]), r"\['PROJ-1'\] are both in the sprint and in Jira's removed list"),
            (change("write_report", False), "Jira's sprint report is missing"),
            (lambda: self.report["contents"].update(completedIssues=[{"key": "PROJ-9"}]),
             "data differs from Jira's sprint report"),
            (lambda: (self.sprint.update(state="active"), setattr(self, "fetched_at", None)),
             "can't tell the moment the report describes"),
        ]
        for apply, expected in cases:
            with self.subTest(expected):
                self.reset()
                apply()
                self.assert_fails(expected)


if __name__ == "__main__":
    unittest.main()
