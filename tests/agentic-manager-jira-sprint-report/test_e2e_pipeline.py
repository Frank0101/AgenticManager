# End-to-end tests for the sprint-report scripts that run after the fetch:
# build_sprint_data.py, make_brief.py, make_charts.py, make_report.py and
# check_report.py, run one after the other, and finish_report.py, which runs the
# last three. Each script's functions have unit tests in test_<script>.py; these
# cover the command lines, exit codes and outputs, and that the scripts fit.
# Run with: python3 tests/run.py agentic-manager-jira-sprint-report
#
# Each test writes the made-up sprint in sprint_fixture.py into a report folder,
# changing it first where the case needs to. HOME points at a temporary folder
# holding the test's own config, whose output root is in that folder too, so the
# scripts write their files there.
import copy
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

# tests/<skill>/ mirrors skills/<skill>/.
TEST_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(TEST_DIR))
SCRIPTS = os.path.join(REPO_ROOT, "skills",
                       os.path.basename(TEST_DIR), "scripts")
sys.path.insert(0, TEST_DIR)
import sprint_fixture as fixture  # noqa: E402

REPORT = "PROJ_Sprint_7_Sprint_Report.md"
CHARTS = ("outcome-tickets.svg", "outcome-pts.svg", "burndown.svg")


class ReportTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = os.path.join(self.tmp.name, "home")
        root = os.path.join(self.tmp.name, "output")
        self.dir = os.path.join(root, "jira-sprint-reports",
                                "PROJ_Sprint_7_26-03-16")
        config = os.path.join(self.home, ".config",
                              "agentic-manager", "config.json")
        os.makedirs(os.path.dirname(config))
        with open(config, "w", encoding="utf-8") as f:
            json.dump({"output": {"root": root}}, f)
        self.raw = copy.deepcopy(fixture.raw_files())
        self.content = copy.deepcopy(fixture.CONTENT)

    def tearDown(self):
        self.tmp.cleanup()

    def write_raw(self):
        for path, payload in self.raw.items():
            full = os.path.join(self.dir, "_raw", path)
            os.makedirs(os.path.dirname(full), exist_ok=True)
            with open(full, "w", encoding="utf-8") as f:
                json.dump(payload, f)

    def run_script(self, name, *args, report_dir=None):
        return subprocess.run([sys.executable, os.path.join(SCRIPTS, name),
                               "--report-dir", report_dir or self.dir, *args],
                              env=dict(os.environ, HOME=self.home), capture_output=True, text=True)

    def assert_runs(self, name, *args):
        proc = self.run_script(name, *args)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        return proc

    def build(self):
        self.write_raw()
        self.assert_runs("build_sprint_data.py")
        with open(os.path.join(self.dir, "data.json"), encoding="utf-8") as f:
            return json.load(f)

    # Builds, draws, writes and checks the report; returns data.json and the Markdown.
    def make_report(self):
        data = self.build()
        self.assert_runs("make_charts.py")
        # The agent writes a sentence for each group of each epic, which
        # depends on the data the test built.
        self.content["epic_commentary"] = fixture.epic_commentary(data)
        with open(os.path.join(self.dir, "content.json"), "w", encoding="utf-8") as f:
            json.dump(self.content, f)
        self.assert_runs("make_report.py")
        self.assert_runs("check_report.py")
        with open(os.path.join(self.dir, REPORT), encoding="utf-8") as f:
            return data, f.read()

    def issue(self, key):
        return next(i for group in ("sprint_issues.json", "punted_issues.json")
                    for i in self.raw[group] if i["key"] == key)

    # Moves PROJ-6 from Jira's completed issues to its not-completed ones.
    def jira_did_not_complete_proj_6(self):
        contents = self.raw["sprint_report.json"]["contents"]
        contents["completedIssues"] = [
            i for i in contents["completedIssues"] if i["key"] != "PROJ-6"]
        contents["issuesNotCompletedInCurrentSprint"].append({"key": "PROJ-6"})


class BuildTest(ReportTest):
    """The fixture sprint, as the model sees it (see build_sprint_data.py).
    The other tests change it, so this pins what they start from; one
    ticket's history at a time is covered by test_e2e_cases.py."""

    def spells(self, data):
        """{key: [its spells]}."""
        found = {}
        for spell in data["spells"]:
            found.setdefault(spell["key"], []).append(spell)
        return found

    def tickets(self, data):
        """{key: its last spell}."""
        return {key: spells[-1] for key, spells in self.spells(data).items()}

    def kinds(self, spell):
        return [f"{e['type']} {e['date'][8:]}" + (" done" if e["done"] and e["type"] in ("committed", "joined") else "")
                for e in spell["events"]]

    def test_each_ticket(self):
        # Each spell as (scope, outcome, events), " done" marking work already
        # Done when it joined. Sub-task PROJ-9 is left out, and PROJ-11, which
        # left before the start, is in no part of the report.
        cases = {
            "PROJ-1": [("original", "completed", ["committed 04", "completed 06"])],
            "PROJ-2": [("original", "not_completed", ["committed 04"])],
            "PROJ-3": [("original", "removed", ["committed 04 done", "removed 05"])],
            "PROJ-4": [("original", "removed", ["committed 04", "removed 09"])],
            "PROJ-5": [("extra", "completed", ["joined 04", "completed 10"])],
            # Left, then came back as extra work and closed as a Duplicate.
            "PROJ-6": [("original", "removed", ["committed 04", "removed 05"]),
                       ("extra", "completed", ["joined 06", "completed 11"])],
            "PROJ-7": [("extra", "not_completed", ["joined 10"])],
            "PROJ-8": [("original", "removed", ["committed 04", "completed 05", "removed 06"])],
            "PROJ-10": [("original", "completed", ["committed 04 done"])],
        }
        found = self.spells(self.build())
        self.assertEqual(set(found), set(cases))
        for key, expected in cases.items():
            with self.subTest(key):
                self.assertEqual([(s["scope"], s["outcome"], self.kinds(s))
                                 for s in found[key]], expected)

    def test_totals(self):
        data = self.build()
        self.assertEqual(data["sprint_start"], "2026-03-04")
        self.assertEqual(data["left_before_start_keys"], ["PROJ-11"])
        self.assertEqual(
            [i["key"] for i in data["non_delivery_closures"]["issues"]], ["PROJ-6"])
        self.assertEqual(data["blocker_candidate_keys"], ["PROJ-7"])
        outcomes = ("completed", "not_completed", "removed")
        self.assertEqual({row: [data["outcome_breakdown_counts"][f"{row}_{o}"] for o in outcomes]
                          for row in ("original", "extra")}, {"original": [2, 1, 4], "extra": [2, 1, 0]})
        self.assertEqual([data["outcome_breakdown_points"]
                         [f"original_{o}"] for o in outcomes], [4, 5, 8])
        # PROJ-100: PROJ-1 and 10 completed, PROJ-2 open, PROJ-6 and 8
        # descoped; PROJ-6 completed again as extra work.
        epics = {e["key"]: e for e in data["epics"]}
        self.assertEqual(set(epics), {"PROJ-100", "PROJ-101", "__no_epic__"})
        self.assertEqual(epics["PROJ-101"]["removed_stories"], 2)
        self.assertEqual((epics["PROJ-100"]["original_stories_done"], epics["PROJ-100"]["original_stories_total"],
                          epics["PROJ-100"]["extra_stories_done"]), (2, 5, 1))

    def test_edited_start_date_is_used_as_is(self):
        # Everything joined after a start moved back to 02/03: all extra, and
        # the extra work later removed was never part of the sprint.
        self.raw["sprint.json"]["startDate"] = "2026-03-02T09:00:00.000Z"
        data = self.build()
        self.assertEqual(data["sprint_start"], "2026-03-02")
        self.assertEqual({t["scope"] for t in data["spells"]}, {"extra"})
        self.assertEqual([t["key"] for t in data["spells"] if not t["counted"]],
                         ["PROJ-3", "PROJ-4", "PROJ-6", "PROJ-8", "PROJ-11"])

    def test_carry_over_is_original_work_in_the_previous_sprint_when_it_closed(self):
        # PROJ-1 and PROJ-3 moved in when Sprint 6 closed. PROJ-2 left Sprint 6
        # before it closed, and PROJ-5 was in it then but joined after the start.
        data, md = self.make_report()
        self.assertEqual([k for k, t in self.tickets(
            data).items() if t["carriedIn"]], ["PROJ-1", "PROJ-3"])
        self.assertEqual(data["previous_sprint"]["name"], "Sprint 6")
        counts, points = data["outcome_breakdown_counts"], data["outcome_breakdown_points"]
        outcomes = ("completed", "not_completed", "removed")
        self.assertEqual(([counts[f"carried_in_{o}"] for o in outcomes], [points[f"carried_in_{o}"] for o in outcomes]),
                         ([1, 0, 1], [3, 0, 2]))
        for c in (counts, points):
            for outcome in outcomes:
                self.assertEqual(
                    c[f"original_{outcome}"], c[f"carried_in_{outcome}"] + c[f"new_{outcome}"])
        # The charts show the carry-over; the header table doesn't.
        self.assertNotIn("| Carried over", md)

    def test_later_edits_change_nothing(self):
        # What happened to the issues after the sprint closed, as Jira shows it
        # today, must not change the report on it.
        before = self.build()
        after = "2026-03-20T10:00:00.000+0000"

        def edit(key, fields, *changes):
            self.issue(key)["fields"].update(fields)
            self.raw[f"changelogs/{key}.json"].extend(changes)
        edit("PROJ-6", {"status": fixture.status_field("To Do")},
             fixture.moved(after, "Duplicate", "To Do"))
        edit("PROJ-2", {"status": fixture.status_field("Done")},
             fixture.moved(after, "In Progress", "Done"))
        edit("PROJ-4", {"status": fixture.status_field("Done")},
             fixture.moved(after, "To Do", "Done"))
        edit("PROJ-3", {"status": fixture.status_field("To Do")},
             fixture.moved(after, "Done", "To Do"))
        edit("PROJ-1", {fixture.POINTS_FIELD: 8.0, "priority": {"name": "Highest"},
                        "parent": {"id": fixture.EXPORT[2], "key": fixture.EXPORT[0],
                                   "fields": {"summary": fixture.EXPORT[1]}}},
             {"created": after, "field": "points", "from": None,
                 "fromString": "3", "to": None, "toString": "8"},
             {"created": after, "field": "priority", "from": "3", "fromString": "Medium", "to": "1",
              "toString": "Highest"},
             {"created": after, "field": "parent", "from": fixture.IMPORT[2], "fromString": fixture.IMPORT[0],
              "to": fixture.EXPORT[2], "toString": fixture.EXPORT[0]})
        self.assertEqual(self.build(), before)

    def test_output_is_deterministic(self):
        self.build()
        with open(os.path.join(self.dir, "data.json"), "rb") as f:
            first = f.read()
        self.build()
        with open(os.path.join(self.dir, "data.json"), "rb") as f:
            self.assertEqual(f.read(), first)

    def test_bad_raw_data_writes_nothing(self):
        # Raw files that disagree with each other or with Jira mean the fetch
        # caught the sprint mid-change or is incomplete: guessing would
        # misreport it, so the build stops with exit 1 and no data.json.
        # Each guard's own message is unit-tested in test_build_sprint_data.py.
        cases = [
            (lambda raw: self.jira_did_not_complete_proj_6(),
             "completed: ['PROJ-6'] in our data but not in Jira's sprint report"),
            # Raw data fetched before the reporting timezone was stored needs
            # a fresh fetch, rather than days cut at UTC.
            (lambda raw: raw["_meta.json"].pop(
                "report_timezone"), "no reporting timezone"),
        ]
        for change, expected in cases:
            with self.subTest(expected):
                self.raw = copy.deepcopy(fixture.raw_files())
                change(self.raw)
                self.write_raw()
                proc = self.run_script("build_sprint_data.py")
                self.assertEqual(proc.returncode, 1)
                self.assertIn(expected, proc.stderr)
                self.assertFalse(os.path.exists(
                    os.path.join(self.dir, "data.json")))
                shutil.rmtree(os.path.join(self.dir, "_raw"))


class BriefTest(ReportTest):
    def test_goal_evidence_survives_the_build_and_brief_pipeline(self):
        data = self.build()
        self.assert_runs("make_brief.py")
        with open(os.path.join(self.dir, "brief.json"), encoding="utf-8") as f:
            brief = json.load(f)
        original = [s for s in data["spells"]
                    if s["counted"] and s["scope"] == "original"]
        self.assertEqual([(t["key"], t["outcome"], t["points"]) for t in brief["goal_tickets"]],
                         [(s["key"], s["outcome"], s["points"]) for s in original])
        # Already-Done commitment is evidence for the goal, not an achievement.
        self.assertIn("PROJ-10", [t["key"] for t in brief["goal_tickets"]])
        self.assertNotIn("PROJ-10", [t["key"]
                         for e in brief["epics"] for t in e["tickets"]])


class ReopenedAtTheStartTest(ReportTest):
    """Work in the sprint at the start is original commitment, Done or not. The
    fixture sprint starts on 04/03 at 12:00 and closes on 13/03 at 16:00. Six
    issues are added to it, all in the sprint since before the start and Done
    on 27/02, so the sprint starts with their points completed; reopening moves
    them back to not completed:

      PROJ-20  1 pt  never reopened
      PROJ-21  1 pt  reopened on 14/03, after the close
      PROJ-22  3 pts reopened 06/03, Done again 09/03, in the sprint at the close
      PROJ-23  2 pts reopened 06/03, still open at the close
      PROJ-24  4 pts reopened 06/03, removed 09/03 while open
      PROJ-25  5 pts reopened 06/03, Done again 07/03, removed 09/03

    Each ticket's events are covered by test_e2e_cases.py; this checks the
    figures each view shows for them, against the fixture sprint without them.
    """
    DONE_AT_START = fixture.moved(
        "2026-02-27T10:00:00.000+0000", "In Progress", "Done")

    def add(self, key, points, status, changes, removed=False):
        group = "punted_issues.json" if removed else "sprint_issues.json"
        resolution = "Done" if status == "Done" else None
        self.raw[group].append(fixture.issue(
            key, points, status, fixture.ts(1), resolution))
        self.raw[f"changelogs/{key}.json"] = [self.DONE_AT_START, *changes]

    def add_scenarios(self):
        reopened = fixture.moved((6,), "Done", "In Progress")
        self.add("PROJ-20", 1, "Done", [])
        self.add("PROJ-21", 1, "In Progress",
                 [fixture.moved((14,), "Done", "In Progress")])
        self.add("PROJ-22", 3, "Done", [reopened, fixture.completed((9,))])
        self.add("PROJ-23", 2, "In Progress", [reopened])
        self.add("PROJ-24", 4, "In Progress",
                 [reopened, fixture.removed(9, to="8")], removed=True)
        self.add("PROJ-25", 5, "Done", [reopened, fixture.completed((7,)), fixture.removed(9, to="8")],
                 removed=True)
        contents = self.raw["sprint_report.json"]["contents"]
        contents["completedIssues"] += [{"key": k}
                                        for k in ("PROJ-20", "PROJ-21", "PROJ-22")]
        contents["issuesNotCompletedInCurrentSprint"].append(
            {"key": "PROJ-23"})
        contents["puntedIssues"] += [{"key": k}
                                     for k in ("PROJ-24", "PROJ-25")]

    def test_every_view_counts_them_as_commitment(self):
        before = self.build()
        self.add_scenarios()
        data, md = self.make_report()
        outcomes = ("completed", "not_completed", "removed")

        def grew(field, key):
            return data[field][key] - before[field][key]
        with self.subTest("charts"):
            self.assertEqual(
                [grew("outcome_breakdown_counts", f"original_{o}") for o in outcomes], [3, 1, 2])
            self.assertEqual(
                [grew("outcome_breakdown_points", f"original_{o}") for o in outcomes], [5, 2, 9])
            self.assertEqual(
                [grew("outcome_breakdown_counts", f"extra_{o}") for o in outcomes], [0, 0, 0])
        with self.subTest("burndown"):
            now = {r["date"]: r for r in data["burndown"]}
            then = {r["date"]: r for r in before["burndown"]}
            # Reopened on the 6th: 14 pts open again; 9 once PROJ-25 is done on
            # the 7th; 2 once PROJ-22 is done and PROJ-24 is removed on the 9th.
            reopened = {"2026-03-04": 0, "2026-03-05": 0, "2026-03-06": 14, "2026-03-07": 9, "2026-03-08": 9,
                        "2026-03-09": 2, "2026-03-13": 2}
            self.assertEqual({day: (now[day]["committed"] - then[day]["committed"],
                                    now[day]["total"] - then[day]["total"]) for day in reopened},
                             {day: (points, points) for day, points in reopened.items()})
            self.assertIn("baseline 33 pts", self.assert_runs(
                "make_charts.py", "--print-series").stdout)
        with self.subTest("report"):
            self.assertIn("Of the 13 tickets (33 pts) in the commitment, 8 tickets (19 pts) were already Done "
                          "at the start", md)
            self.assertIn(
                "| Sprint target completion | 38%, 5/13 tickets (9/33 pts) completed |", md)
            self.assertIn(
                '<a href="https://acme.atlassian.net/browse/PROJ-20">PROJ-20</a> (1 pt)', md)
            self.assertEqual(md.count(">Already done</span>"), 8)
            # PROJ-22 to 25, on the 6th
            self.assertEqual(md.count(">Reopened</span>"), 4)
        with self.subTest("epic table"):
            def row(found):
                return next(e for e in found["epics"] if e["key"] == "__no_epic__")
            now_row, then_row = row(data), row(before)
            self.assertEqual([now_row[k] - then_row[k] for k in (
                "original_stories_total", "original_stories_done", "original_points_total",
                "original_points_done", "extra_stories_total")], [6, 3, 16, 5, 0])


class ChartsTest(ReportTest):
    def test_reopening_and_reestimation_use_each_days_history(self):
        self.issue("PROJ-2")["fields"][fixture.POINTS_FIELD] = 8
        self.raw["changelogs/PROJ-2.json"] += [
            {"created": fixture.ts(7), "field": "points", "from": None, "fromString": "5",
             "to": None, "toString": "8"}]
        self.issue(
            "PROJ-6")["fields"]["status"] = fixture.status_field("To Do")
        self.raw["changelogs/PROJ-6.json"].append(
            fixture.moved((12,), "Duplicate", "To Do"))
        self.jira_did_not_complete_proj_6()
        data, _ = self.make_report()
        rows = {r["date"]: r for r in data["burndown"]}
        self.assertEqual([rows[day]["committed"] for day in
                          ("2026-03-06", "2026-03-07", "2026-03-11", "2026-03-12")], [8, 11, 8, 8])
        out = self.assert_runs("make_charts.py", "--print-series").stdout
        self.assertIn("baseline 17 pts", out)

    def test_later_sprint_moves_do_not_change_historical_figures(self):
        before = self.build()
        issue = self.issue("PROJ-1")
        self.raw["sprint_issues.json"].remove(issue)
        self.raw["punted_issues.json"].append(issue)
        self.raw["changelogs/PROJ-1.json"].append(fixture.removed(16))
        contents = self.raw["sprint_report.json"]["contents"]
        contents["completedIssues"] = [
            i for i in contents["completedIssues"] if i["key"] != "PROJ-1"]
        contents["puntedIssues"].append({"key": "PROJ-1"})
        after, md = self.make_report()
        for field in ("spells", "outcome_breakdown_counts", "outcome_breakdown_points", "timeline", "burndown"):
            self.assertEqual(after[field], before[field], field)
        self.assertEqual(
            after["membership_cross_check_excluded_keys"], ["PROJ-1"])
        self.assertIn(
            "later sprint moves prevent checking it against Jira", md)

    def test_ticket_first_added_after_close_is_explained_without_being_counted(self):
        self.raw["changelogs/PROJ-7.json"] = [fixture.added(16)]
        data, md = self.make_report()
        self.assertNotIn("PROJ-7", [s["key"] for s in data["spells"]])
        self.assertEqual(data["left_before_start_keys"], ["PROJ-11"])
        self.assertEqual(
            data["membership_cross_check_excluded_keys"], ["PROJ-7"])
        self.assertIn("PROJ-7) (– pts) is reconstructed from changelogs", md)

    def test_print_series(self):
        # --print-series is how the agent reads the burndown without the SVG.
        # Columns: date, weekday, point, committed, total, ideal, spread.
        cases = [
            # The baseline is the whole commitment at the start, including
            # PROJ-3 and PROJ-10, already Done then. The start day shows the
            # baseline, then the day's close, without the work already Done
            # and with PROJ-5 (added after the start).
            ("closed on time", None, [
                r"baseline 17 pts committed at the start on 2026-03-04",
                r"2026-03-04 +Wed +start +17 +17 +17 +0",
                r"2026-03-04 +Wed +close +14 +16 +17 +-3",
                r"2026-03-13 +Fri +close +5 +6 +0 +5"]),
            # Planned to end on Friday 13/03, but closed on Monday 16/03: the
            # chart runs on to the close.
            ("closed late", "2026-03-16T16:00:00.000Z", [
                r"2026-03-13 +Fri +close +5 +6 +0 +5",
                r"2026-03-16 +Mon +close +5 +6 +0 +5"]),
        ]
        for name, complete_date, lines in cases:
            with self.subTest(name):
                self.raw = copy.deepcopy(fixture.raw_files())
                if complete_date:
                    self.raw["sprint.json"]["completeDate"] = complete_date
                self.build()
                out = self.assert_runs(
                    "make_charts.py", "--print-series").stdout
                for line in lines:
                    self.assertRegex(out, line)


class TimezoneTest(ReportTest):
    def test_active_snapshot_date_follows_fetch_in_reporting_timezone(self):
        cases = [
            ("Europe/London", "2026-03-29T23:30:00Z", "2026-03-30", "2026-04-03"),
            ("America/New_York", "2026-03-29T23:30:00Z", "2026-03-29", "2026-04-03"),
            ("Europe/London", "2026-03-29T23:30:00Z", "2026-03-30", "2026-03-27"),
            ("Europe/London", "2026-03-29T23:00:00Z", "2026-03-30", "2026-03-27"),
        ]
        for zone, fetched_at, expected_day, end_day in cases:
            with self.subTest(zone=zone, end=end_day, fetched_at=fetched_at):
                self.raw = copy.deepcopy(fixture.raw_files())
                self.raw["_meta.json"].update(
                    fetched_at=fetched_at, report_timezone=zone)
                self.raw["sprint.json"].update(
                    state="active", completeDate=None, endDate=f"{end_day}T17:00:00Z")
                self.content["goal_verdict"] = "At risk"
                data, md = self.make_report()
                self.assertEqual(data["today"], expected_day)
                self.assertEqual(data["burndown"][-1]
                                 ["date"], expected_day)
                today_row = next(
                    row for row in data["timeline"] if "today" in row["labels"])
                self.assertEqual(today_row["date"], expected_day)
                display_day = "/".join(reversed(expected_day.split("-")))
                self.assertIn(f"snapshot as at {display_day}", md)
                with open(os.path.join(self.dir, "burndown.svg"), encoding="utf-8") as f:
                    self.assertIn(">today<", f.read())

    def test_timeline_and_burndown_agree_across_clock_changes(self):
        cases = [
            ("spring", "2026-01-10T10:00:00+0000", "2026-03-26T23:30:00Z",
             "2026-03-31T16:00:00Z", "2026-03-29T23:30:00Z", "2026-03-30", "2026-03-29"),
            ("autumn", "2026-07-10T10:00:00+0100", "2026-10-23T08:00:00Z",
             "2026-10-27T16:00:00Z", "2026-10-25T23:30:00Z", "2026-10-25", "2026-10-24"),
        ]
        for name, created, start, close, completed, completion_day, previous_day in cases:
            with self.subTest(name=name):
                self.raw = copy.deepcopy(fixture.raw_files())
                self.raw["sprint.json"].update(
                    startDate=start, endDate=close, completeDate=close)
                self.raw["sprint_issues.json"] = [
                    fixture.issue("PROJ-1", 3, "Done", created, "Done")]
                self.raw["punted_issues.json"] = []
                self.raw["changelogs/PROJ-1.json"] = [
                    fixture.completed(completed)]
                self.raw["sprint_report.json"] = {"contents": {
                    "completedIssues": [{"key": "PROJ-1"}], "puntedIssues": []}}
                self.raw["_meta.json"]["fetched_at"] = close
                data, md = self.make_report()
                completion = data["spells"][0]["events"][-1]
                self.assertEqual(
                    (completion["type"], completion["date"]), ("completed", completion_day))
                rows = {row["date"]: row for row in data["burndown"]}
                self.assertEqual(rows[previous_day]["total"], 3)
                self.assertEqual(rows[completion_day]["total"], 0)
                completed_row = next(row for row in data["timeline"]
                                     if any(e["type"] == "completed" for e in row["events"]))
                self.assertEqual(completed_row["date"], completion_day)
                self.assertEqual(data["report_timezone"], "Europe/London")
                self.assertNotIn("Reporting timezone", md)
                if name == "spring":
                    self.assertEqual(data["sprint_start"], "2026-03-26")


class OutputFolderTest(ReportTest):
    def test_a_report_folder_outside_the_output_folder_gets_nothing(self):
        # Every script that writes refuses a --report-dir outside the
        # configured output folder, so a wrong path can't overwrite anything.
        self.make_report()
        self.assert_runs("make_brief.py")
        outside = os.path.join(self.tmp.name, "elsewhere")
        cases = [
            ("build_sprint_data.py", ["data.json"]),
            ("make_brief.py", ["brief.json"]),
            ("make_charts.py", list(CHARTS)),
            ("make_report.py", [REPORT]),
        ]
        for script, outputs in cases:
            with self.subTest(script):
                shutil.copytree(self.dir, outside)
                for name in outputs:
                    os.remove(os.path.join(outside, name))
                proc = self.run_script(script, report_dir=outside)
                self.assertEqual(proc.returncode, 1, proc.stdout)
                self.assertIn(
                    "must be a relative path inside the output folder", proc.stderr)
                self.assertEqual(
                    [n for n in outputs if os.path.exists(os.path.join(outside, n))], [])
                shutil.rmtree(outside)


class MakeReportTest(ReportTest):
    def test_report_text(self):
        # Each case changes the fixture sprint or content.json, makes the
        # report (which must pass check_report.py) and looks for the wording
        # the case decides.
        source = "One story — fix issues"

        def active():
            self.raw["sprint.json"].update(state="active", completeDate=None)
            self.raw["_meta.json"]["fetched_at"] = "2026-03-11T12:00:00Z"
            self.content["goal_verdict"] = "On track"

        def no_goal():
            self.raw["sprint.json"]["goal"] = None
            self.content["goal_verdict"] = "No goal set in Jira for this sprint"

        def jira_text():
            self.raw["sprint.json"].update(name=source, goal=source)
            self.raw["previous_sprint.json"]["name"] = source
            for parent in self.raw["parents.json"]:
                parent["fields"]["summary"] = source

        cases = [
            ("closed sprint", None, [
                "Of the 7 tickets (17 pts) in the commitment, 2 tickets (3 pts) were already Done at the start "
                "([PROJ-3](https://acme.atlassian.net/browse/PROJ-3), "
                "[PROJ-10](https://acme.atlassian.net/browse/PROJ-10)), and 4 tickets (8 pts) were descoped.",
                "- [PROJ-6](https://acme.atlassian.net/browse/PROJ-6) (1 pt) left the sprint",
                "04/03/2026–13/03/2026",
                "<b>Commitment:</b><br>7 tickets (17 pts)",
                # PROJ-6 left on the 5th and came back on the 6th: Descoped, then Added.
                "PROJ-6</a> (1 pt)</td><td><span", ">Descoped</span>"], ["mid-sprint snapshot"]),
            # A running sprint reads as a snapshot, its open work as not yet done.
            ("active sprint", active, [
                'This is a mid-sprint snapshot as at 11/03/2026, with 2 days left. "Open" means not completed yet.',
                "2 tickets (6 pts) are open, 1 ticket (5 pts) of them from the commitment, with 2 days left.",
                "(today)"], []),
            ("no goal", no_goal, [
                "*No goal was set in Jira for this sprint*",
                "| Goal outcome <sup style=\"font-size:0.6rem;font-weight:normal\">[AI Gen.]</sup> "
                "| No goal set in Jira for this sprint |"], []),
            # Em dashes are a tell of AI text: the agent's are replaced...
            ("em dash in content.json",
             lambda: self.content.update(
                 key_achievements="The import flow — finally — shipped."),
             ["The import flow, finally, shipped."], []),
            # ...but text copied from Jira stays as the team wrote it, and the
            # checker accepts it.
            ("em dash in Jira's text", jira_text, [
                "# Sprint Summary: " + source, "| Goal | " + source + " |", ": " + source + "</a>"], []),
        ]
        for name, change, present, absent in cases:
            with self.subTest(name):
                self.raw = copy.deepcopy(fixture.raw_files())
                self.content = copy.deepcopy(fixture.CONTENT)
                if change:
                    change()
                _, md = self.make_report()
                for text in present:
                    self.assertIn(text, md)
                for text in absent:
                    self.assertNotIn(text, md)

    def test_bad_content_fails(self):
        # content.json is checked against data.json before anything is
        # written: make_report.py exits 1 naming the field to fix.
        cases = [
            # The verdicts allowed depend on the sprint: closed or running,
            # with a goal or without.
            ({}, {"goal_verdict": "On track"}, "goal_verdict must be one of"),
            ({"goal": None}, {"goal_verdict": "Partially met"},
             "goal_verdict must be one of"),
            ({}, {"key_achievements": ["One.", "Two."]},
             "key_achievements must be a non-empty string"),
            # Every epic needs a sentence for each group it has tickets in.
            ({}, {"epic_commentary": {}}, "epic_commentary.PROJ-101 needs a sentence for exactly these "
                                          "groups: not_completed, descoped"),
        ]
        for sprint_changes, content_changes, expected in cases:
            with self.subTest(expected, sprint=sprint_changes):
                self.raw = copy.deepcopy(fixture.raw_files())
                self.raw["sprint.json"].update(sprint_changes)
                content = copy.deepcopy(fixture.CONTENT)
                content["epic_commentary"] = fixture.epic_commentary(
                    self.build())
                content.update(content_changes)
                with open(os.path.join(self.dir, "content.json"), "w", encoding="utf-8") as f:
                    json.dump(content, f)
                proc = self.run_script("make_report.py")
                self.assertEqual(proc.returncode, 1)
                self.assertIn(expected, proc.stderr)
                self.assertFalse(os.path.exists(
                    os.path.join(self.dir, REPORT)))


class FinishReportTest(ReportTest):
    """finish_report.py prints only what the agent must act on: the failures,
    the summary line and the report's path."""

    def write_content(self, data, **changes):
        self.content["epic_commentary"] = fixture.epic_commentary(data)
        self.content.update(changes)
        with open(os.path.join(self.dir, "content.json"), "w", encoding="utf-8") as f:
            json.dump(self.content, f)

    def test_fractional_estimates_finish_the_report(self):
        self.issue("PROJ-2")["fields"][fixture.POINTS_FIELD] = 5.5
        for state, verdict in (("closed", "Partially met"), ("active", "On track")):
            with self.subTest(state=state):
                self.raw["sprint.json"]["state"] = state
                if state == "active":
                    self.raw["sprint.json"]["completeDate"] = None
                    self.raw["_meta.json"]["fetched_at"] = "2026-03-11T12:00:00Z"
                data = self.build()
                self.write_content(data, goal_verdict=verdict)
                self.assert_runs("finish_report.py")
                with open(os.path.join(self.dir, REPORT), encoding="utf-8") as f:
                    md = f.read()
                self.assertIn("(4/17.5 pts)", md)
                self.assertIn("(4/12.5 pts)", md)

    def test_outcomes(self):
        # Charts come first, so each case draws them. A report from content
        # the agent must fix is never written, so a stale or half-right one
        # isn't left to be shared; a crash isn't a content.json problem, so
        # it is shown whole, without that advice.
        path = re.escape(os.path.join(self.dir, REPORT))

        def breakdown_drift(data):
            # A breakdown that no longer matches the spells it was built from.
            data["outcome_breakdown_counts"]["carried_in_completed"] += 1

        def crash(data):
            del data["non_delivery_closures"]
        # name: (changes to content.json, change to data.json, exit code,
        # stdout as a regex, whether the report is written)
        cases = [
            ("passing", {}, None, 0, rf"all \d+ checks passed\nreport: {path}\n", True),
            ("bad content", {"key_achievements": "PROJ-1 shipped."}, None, 1,
             re.escape(
                 "content.json:\n  - key_achievements: names tickets ['PROJ-1']; describe the work instead\n"),
             False),
            ("failed checks", {}, breakdown_drift, 1,
             rf"(  FAIL  .*\n)+\d+ check\(s\) failed\nreport \(inspect the failed checks before rerunning\): {path}\n",
             True),
            ("crashed check", {}, crash, 1,
             r"(?s)(?!.*fix content\.json)Traceback.*non_delivery_closures.*", True),
        ]
        for name, changes, change_data, code, stdout, written in cases:
            with self.subTest(name):
                for old in (REPORT, *CHARTS):
                    if os.path.exists(os.path.join(self.dir, old)):
                        os.remove(os.path.join(self.dir, old))
                self.content = copy.deepcopy(fixture.CONTENT)
                data = self.build()
                self.write_content(data, **changes)
                if change_data:
                    change_data(data)
                    with open(os.path.join(self.dir, "data.json"), "w", encoding="utf-8") as f:
                        json.dump(data, f)
                proc = self.run_script("finish_report.py")
                self.assertEqual(proc.returncode, code,
                                 proc.stdout + proc.stderr)
                self.assertTrue(re.fullmatch(stdout, proc.stdout), proc.stdout)
                for chart in CHARTS:
                    with open(os.path.join(self.dir, chart), encoding="utf-8") as f:
                        self.assertTrue(f.read().startswith("<svg "), chart)
                self.assertEqual(os.path.exists(
                    os.path.join(self.dir, REPORT)), written)


class CheckReportTest(ReportTest):
    def test_a_broken_report_fails(self):
        # Which check catches which breakage is unit-tested in
        # test_check_report.py; here, that check_report.py exits 1 and names
        # the failure.
        self.make_report()
        path = os.path.join(self.dir, REPORT)
        with open(path, encoding="utf-8") as f:
            report = f.read()
        old = "<b>Commitment:</b><br>7 tickets (17 pts)"
        self.assertIn(old, report)
        with open(path, "w", encoding="utf-8") as f:
            f.write(report.replace(old, old.replace("17", "18"), 1))
        proc = self.run_script("check_report.py")
        self.assertEqual(proc.returncode, 1, proc.stdout)
        self.assertIn("FAIL  timeline: 04/03/2026 end of day", proc.stdout)


if __name__ == "__main__":
    unittest.main()
