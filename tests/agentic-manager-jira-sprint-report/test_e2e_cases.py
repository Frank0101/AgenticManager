"""End-to-end tests of the one model every part of the sprint report is built
from: which tickets belong to the sprint and each one's dated events. Each
case below is one made-up ticket with its own history, all in one closed
sprint, run through build_sprint_data.py, make_charts.py, make_report.py and
check_report.py. The tests check each ticket's scope, outcome, latest
estimate and events, then that the whole report passes the checker, which
replays the same events and requires the charts, header, epic table, prose,
timeline table and burndown to agree with them.
Run with: python3 tests/run.py agentic-manager-jira-sprint-report
"""

import os
import re
import sys
import unittest

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, TEST_DIR)
import sprint_fixture as fx  # noqa: E402
from test_e2e_pipeline import REPORT, ReportTest  # noqa: E402

ts, mv = fx.ts, fx.moved


def add(day, time="10:00", previous=""):
    """Joins Sprint 7, keeping any closed sprint already in the field."""
    return {"created": ts(day, time), "field": "sprint", "from": previous,
            "to": f"{previous}, 7" if previous else "7", "fromString": None, "toString": None}


def rem(day, time="10:00"):
    return {"created": ts(day, time), "field": "sprint", "from": "7", "to": "", "fromString": None, "toString": None}


def carried():
    """Moved from Sprint 6 into Sprint 7 when Sprint 6 closed (04/03 09:00)."""
    return {"created": ts(4, "09:00"), "field": "sprint", "from": "6", "to": "6, 7",
            "fromString": None, "toString": None}


def left_previous(day):
    return {"created": ts(day), "field": "sprint", "from": "6", "to": "", "fromString": None, "toString": None}


def done(day, old="To Do"):
    return mv((day,), old, "Done")


def reopen(day):
    return mv((day,), "Done", "In Progress")


def redone(day):
    return mv((day,), "In Progress", "Done")


def estimate(day, old, new):
    return {"created": ts(day), "field": "points", "from": None, "to": None,
            "fromString": str(old), "toString": str(new)}


# Sprint 7 starts on 04/03 at 12:00 and closes on 13/03 at 16:00. Each case:
# (name, changes, status today, points today, Jira's bucket, expected spells),
# each spell as (scope: "original", "carried" or "extra"; outcome; latest
# estimate; counted in the final situation; events as "type day[ done][:points]").
O, C, X = "original", "carried", "extra"
CASES = [
    ("open at start, done", [add(3), done(6)], "Done", 2, "done",
     [(O, "completed", 2, True, ["committed 04", "completed 06"])]),
    # Changelog entries are ordered by their instant, whatever order Jira lists them in.
    ("changes listed out of order", [done(6), add(3)], "Done", 2, "done",
     [(O, "completed", 2, True, ["committed 04", "completed 06"])]),
    ("open at start, open at the close", [add(3)], "To Do", 2, "open",
     [(O, "not_completed", 2, True, ["committed 04"])]),
    ("done only after the close", [add(3), done(14)], "Done", 2, "open",
     [(O, "not_completed", 2, True, ["committed 04"])]),
    # The close is an instant, not a day: done an hour after it is too late.
    ("done on the closing day, after the close", [add(3), mv((13, "17:00"), "To Do", "Done")], "Done", 2, "open",
     [(O, "not_completed", 2, True, ["committed 04"])]),
    ("done, then reopened before the close", [add(3), done(6), reopen(9)], "In Progress", 2, "open",
     [(O, "not_completed", 2, True, ["committed 04", "completed 06", "reopened 09"])]),
    # Jira logs no add for a sprint set when the issue was created.
    ("in the sprint since creation, only its removal logged", [rem(9)], "To Do", 2, "punted",
     [(O, "removed", 2, True, ["committed 04", "removed 09"])]),
    ("descoped while open", [add(3), rem(6)], "To Do", 2, "punted",
     [(O, "removed", 2, True, ["committed 04", "removed 06"])]),
    ("done, then descoped", [add(3), done(5), rem(6)], "Done", 2, "punted",
     [(O, "removed", 2, True, ["committed 04", "completed 05", "removed 06"])]),
    ("left, came back, done", [add(3), rem(5), add(7), done(8)], "Done", 2, "done",
     [(O, "removed", 2, True, ["committed 04", "removed 05"]), (X, "completed", 2, True, ["joined 07", "completed 08"])]),
    ("left, came back, open", [add(3), rem(5), add(7)], "To Do", 2, "open",
     [(O, "removed", 2, True, ["committed 04", "removed 05"]), (X, "not_completed", 2, True, ["joined 07"])]),
    ("left and came back the same day", [add(3), rem(6, "09:00"), add(6, "15:00")], "To Do", 2, "open",
     [(O, "removed", 2, True, ["committed 04", "removed 06"]), (X, "not_completed", 2, True, ["joined 06"])]),
    ("out, back, out again", [add(3), rem(5), add(7), rem(9)], "To Do", 2, "punted",
     [(O, "removed", 2, True, ["committed 04", "removed 05"]), (X, "removed", 2, False, ["joined 07", "removed 09"])]),
    ("descoped open, done outside the sprint", [add(3), rem(5), done(6)], "Done", 2, "punted",
     [(O, "removed", 2, True, ["committed 04", "removed 05"])]),
    ("done at start, stays", [done(1), add(3)], "Done", 2, "done",
     [(O, "completed", 2, True, ["committed 04 done"])]),
    ("done at start, descoped", [done(1), add(3), rem(6)], "Done", 2, "punted",
     [(O, "removed", 2, True, ["committed 04 done", "removed 06"])]),
    ("done at start, reopened, done again", [done(1), add(3), reopen(6), redone(8)], "Done", 2, "done",
     [(O, "completed", 2, True, ["committed 04 done", "reopened 06", "completed 08"])]),
    ("done at start, reopened, open at the close", [done(1), add(3), reopen(6)], "In Progress", 2, "open",
     [(O, "not_completed", 2, True, ["committed 04 done", "reopened 06"])]),
    ("done at start, reopened, descoped open", [done(1), add(3), reopen(6), rem(8)], "In Progress", 2, "punted",
     [(O, "removed", 2, True, ["committed 04 done", "reopened 06", "removed 08"])]),
    ("done at start, reopened, done again, descoped", [done(1), add(3), reopen(6), redone(7), rem(8)], "Done", 2,
     "punted", [(O, "removed", 2, True, ["committed 04 done", "reopened 06", "completed 07", "removed 08"])]),
    ("done at start, reopened after the close", [done(1), add(3), reopen(14)], "In Progress", 2, "done",
     [(O, "completed", 2, True, ["committed 04 done"])]),
    ("carried over, done", [carried(), done(6)], "Done", 2, "done",
     [(C, "completed", 2, True, ["committed 04", "completed 06"])]),
    ("carried over, descoped", [carried(), rem(6)], "To Do", 2, "punted",
     [(C, "removed", 2, True, ["committed 04", "removed 06"])]),
    ("carried over, left and came back", [carried(), rem(6), add(8)], "To Do", 2, "open",
     [(C, "removed", 2, True, ["committed 04", "removed 06"]), (X, "not_completed", 2, True, ["joined 08"])]),
    ("left Sprint 6 before it closed, then committed", [left_previous(2), add(3)], "To Do", 2, "open",
     [(O, "not_completed", 2, True, ["committed 04"])]),
    ("joined and left before the start", [
     add(3), rem(4, "09:00")], "To Do", 2, "punted", []),
    ("descoped after the close", [add(3), rem(14)], "To Do", 2, "open",
     [(O, "not_completed", 2, True, ["committed 04"])]),
    ("re-estimated 2 to 5, done", [add(3), estimate(6, 2, 5), done(8)], "Done", 5, "done",
     [(O, "completed", 5, True, ["committed 04:2", "reestimated 06:5", "completed 08:5"])]),
    ("closed as Duplicate", [add(3), mv((6,), "To Do", "Duplicate")], "Duplicate", 2, "done",
     [(O, "completed", 2, True, ["committed 04", "completed 06"])]),
    ("no estimate, done", [add(3), done(6)], "Done", None, "done",
     [(O, "completed", None, True, ["committed 04:-", "completed 06:-"])]),
    ("re-estimated 2 to 3, then descoped", [add(3), estimate(6, 2, 3), rem(8)], "To Do", 3, "punted",
     [(O, "removed", 3, True, ["committed 04:2", "reestimated 06:3", "removed 08:3"])]),
    ("re-estimated 2 to 4 while out, came back, done",
     [add(3), rem(5), estimate(6, 2, 4), add(7), done(8)], "Done", 4, "done",
     [(O, "removed", 2, True, ["committed 04:2", "removed 05:2"]),
      (X, "completed", 4, True, ["joined 07:4", "completed 08:4"])]),
    ("extra, done", [add(5), done(9)], "Done", 2, "done",
     [(X, "completed", 2, True, ["joined 05", "completed 09"])]),
    ("extra, open at the close", [add(5)], "To Do", 2, "open",
     [(X, "not_completed", 2, True, ["joined 05"])]),
    ("extra, descoped while open", [add(5), rem(8)], "To Do", 2, "punted",
     [(X, "removed", 2, False, ["joined 05", "removed 08"])]),
    ("extra, done, then descoped", [add(5), done(6), rem(8)], "Done", 2, "punted",
     [(X, "removed", 2, False, ["joined 05", "completed 06", "removed 08"])]),
    ("extra, done when it joined, stays", [done(1), add(5)], "Done", 2, "done",
     [(X, "completed", 2, True, ["joined 05 done"])]),
    ("extra, done when it joined, descoped", [done(1), add(5), rem(8)], "Done", 2, "punted",
     [(X, "removed", 2, False, ["joined 05 done", "removed 08"])]),
    ("extra, created in the running sprint", [], "To Do", 2, "open",
     [(X, "not_completed", 2, True, ["joined 06"])]),
    ("extra, left, came back, done", [add(5), rem(6), add(8), done(9)], "Done", 2, "done",
     [(X, "removed", 2, False, ["joined 05", "removed 06"]), (X, "completed", 2, True, ["joined 08", "completed 09"])]),
    ("extra, done when it joined, reopened, done again", [done(1), add(5), reopen(7), redone(9)], "Done", 2,
     "done", [(X, "completed", 2, True, ["joined 05 done", "reopened 07", "completed 09"])]),
    ("extra, in Sprint 6 at its close but joined after the start", [add(5, previous="6")], "To Do", 2, "open",
     [(X, "not_completed", 2, True, ["joined 05"])]),
    ("extra, re-estimated 2 to 1, open", [add(5), estimate(7, 2, 1)], "To Do", 1, "open",
     [(X, "not_completed", 1, True, ["joined 05:2", "reestimated 07:1"])]),
]
CREATED_IN_SPRINT = "extra, created in the running sprint"
BUCKETS = {"done": "completedIssues",
           "open": "issuesNotCompletedInCurrentSprint", "punted": "puntedIssues"}


def key_of(index):
    return f"PROJ-{index + 1}"


class CasesTest(ReportTest):
    def setUp(self):
        super().setUp()
        self.raw = {k: v for k, v in self.raw.items(
        ) if not k.startswith(("changelogs/", "comments/"))}
        current, punted = [], []
        contents = {bucket: [] for bucket in (
            *BUCKETS.values(), "issuesCompletedInAnotherSprint")}
        for index, (name, changes, status, points, bucket, _) in enumerate(CASES):
            created = ts(6, "09:00") if name == CREATED_IN_SPRINT else ts(
                1, "08:00")
            issue = fx.issue(key_of(index), points, status, created,
                             "Done" if status in ("Done", "Duplicate") else None)
            (punted if bucket == "punted" else current).append(issue)
            self.raw[f"changelogs/{key_of(index)}.json"] = changes
            contents[BUCKETS[bucket]].append({"key": key_of(index)})
        self.raw.update({"sprint_issues.json": current, "punted_issues.json": punted,
                         "sprint_report.json": {"contents": contents}})
        self.content.update(key_achievements="Every case was reported.", blockers_risks="Nothing to report.",
                            retro_notes=["Every case was reported: did any surprise the team?"])

    def test_each_case(self):
        data = self.build()
        by_key = {}
        for spell in data["spells"]:
            by_key.setdefault(spell["key"], []).append(spell)

        def shown(e, with_points):
            text = f"{e['type']} {e['date'][8:]}" + (" done" if e["done"] and e["type"] in (
                "committed", "joined") else "")
            if with_points:
                text += ":" + ("-" if e["points"]
                               is None else f"{e['points']:g}")
            return text
        for index, (name, *_, expected) in enumerate(CASES):
            with self.subTest(name):
                spells = by_key.get(key_of(index), [])
                self.assertEqual(len(spells), len(expected))
                if not expected:
                    self.assertIn(
                        key_of(index), data["left_before_start_keys"])
                for position, (spell, (scope, outcome, points, counted, events)) in enumerate(zip(spells, expected)):
                    self.assertEqual(
                        (spell["scope"], spell["carriedIn"]), (X if scope == X else O, scope == C))
                    self.assertEqual(
                        (spell["outcome"], spell["points"], spell["counted"]), (outcome, points, counted))
                    self.assertEqual([shown(e, ":" in wanted) for e, wanted in zip(
                        spell["events"], events)], events)
                    self.assertEqual(len(spell["events"]), len(events))
                    self.assertEqual((spell["doneAtStart"], spell["reopened"], spell["reestimated"], spell["cameBack"]),
                                     (" done" in events[0], any(e.startswith("reopened") for e in events),
                                      any(e.startswith("reestimated") for e in events), position > 0))

    def test_the_whole_report_agrees_with_the_events(self):
        # check_report.py has already passed on it; these replay the events
        # independently of the checker, so a bug shared by both still shows.
        data, md = self.make_report()
        spells = [s for case in CASES for s in case[5]]
        original = [s for s in spells if s[0] != X]
        self.assertEqual(sum(data["outcome_breakdown_counts"][f"original_{o}"]
                             for o in ("completed", "not_completed", "removed")), len(original))
        self.assertEqual(sum(data["outcome_breakdown_counts"][f"extra_{o}"]
                             for o in ("completed", "not_completed", "removed")),
                         sum(1 for s in spells if s[0] == X and s[3]))
        done = sum(s[1] == 'completed' for s in original)
        self.assertIn(f"| Sprint target completion | {round(100 * done / len(original))}%, {done}/"
                      f"{len(original)} tickets (", md)
        self.assertEqual(data["non_delivery_closures"]["count"], 1)
        with open(os.path.join(self.dir, REPORT), encoding="utf-8") as f:
            self.assertEqual(f.read(), md)
        # Reading the timeline as a reader does, from its tags and each
        # ticket's estimate, gives the burndown on every day: nothing moves it
        # unseen.
        table_match = re.search(
            r'<table style="font-size:75%">.*?</table>', md, re.S)
        assert table_match is not None, "report has no timeline table"
        table = table_match[0]
        days, day = {}, None
        for row in re.findall(r"<tr>(.*?)</tr>", table, re.S)[1:]:
            cells = re.findall(r"<td([^>]*)>(.*?)</td>", row, re.S)
            if "rowspan" in cells[0][0]:
                day = re.sub(r"<[^>]+>", " ", cells[0][1]).split()[0]
                days[day] = []
                cells = cells[1:-1]
            if len(cells) == 2:
                ticket_match = re.search(
                    r">(PROJ-\d+)</a> \(([^ )]+) pts?\)", cells[0][1])
                assert ticket_match is not None, "timeline cell has no ticket and estimate"
                key, shown_estimate = ticket_match.groups()
                days[day].append((key, 0 if shown_estimate == "–" else float(shown_estimate),
                                  re.findall(r">([^<]+)</span>", cells[1][1])))
        first_day = next(iter(days))
        stories = {}  # key: [in the sprint and open, estimate, original]
        replayed = {}
        for day, rows in days.items():
            for key, points, tags in rows:
                for tag in tags:
                    if tag == "Added":
                        stories[key] = [True, points, day ==
                                        first_day and key not in stories]
                    elif tag in ("Already done", "Completed", "Descoped"):
                        stories[key][0] = False
                    elif tag == "Reopened":
                        stories[key][0] = True
                stories[key][1] = points
            replayed[day] = (sum(p for is_open, p, original in stories.values() if is_open and original),
                             sum(p for is_open, p, _ in stories.values() if is_open))
        last = None
        for reading in data["burndown"]:
            day = "/".join(reversed(reading["date"].split("-")))
            last = replayed.get(day, last)
            self.assertEqual(
                last, (reading["committed"], reading["total"]), day)


if __name__ == "__main__":
    unittest.main()
