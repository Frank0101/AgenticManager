# End-to-end tests for the sprint-report scripts that run after the fetch:
# build_sprint_data.py, make_charts.py, make_report.py and check_report.py, run one
# after the other. Each script's functions have unit tests in test_<script>.py.
# Run with: python3 tests/run.py agentic-manager-jira-sprint-report
#
# Each test writes the made-up sprint in sprint_fixture.py into a report folder,
# changing it first where the case needs to. HOME points at a temporary folder
# holding the test's own config, whose output root is in that folder too, so the
# scripts write their files there.
import copy
import json
import os
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
        self.today = "2026-03-16"

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
        self.assert_runs("build_sprint_data.py", "--today", self.today)
        with open(os.path.join(self.dir, "data.json"), encoding="utf-8") as f:
            return json.load(f)

    # Builds, draws, writes and checks the report; returns data.json and the Markdown.
    def make_report(self):
        data = self.build()
        self.assert_runs("make_charts.py")
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
    def issues(self, data):
        return {i["key"]: i for i in data["issues"] + data["removed_issues"]}

    def test_commitment_is_what_was_in_the_sprint_at_the_start(self):
        data = self.build()
        issues = self.issues(data)
        self.assertEqual(data["sprint_start"], "2026-03-04")
        # Added the day before the start: original. Added the same day, after it: extra.
        self.assertFalse(issues["PROJ-2"]["addedMidSprint"])
        self.assertTrue(issues["PROJ-5"]["addedMidSprint"])
        self.assertEqual(data["added_mid_sprint_keys"], ["PROJ-5", "PROJ-7"])

    def test_original_work_enters_at_the_start(self):
        timeline = self.build()["scope_timeline"]
        self.assertEqual(timeline[0]["date"], "2026-03-04")
        self.assertEqual(timeline[0]["added_keys"],
                         ["PROJ-1", "PROJ-2", "PROJ-3", "PROJ-4", "PROJ-5", "PROJ-6", "PROJ-8", "PROJ-10"])

    def test_edited_start_date_is_used_as_is(self):
        self.raw["sprint.json"]["startDate"] = "2026-03-02T09:00:00.000Z"
        data = self.build()
        self.assertEqual(data["sprint_start"], "2026-03-02")
        self.assertEqual(
            len(data["added_mid_sprint_keys"]), len(data["issues"]))

    def test_issue_in_the_sprint_since_creation_with_only_a_removal(self):
        # Jira logs no add for a sprint set when the issue was created.
        self.raw["changelogs/PROJ-4.json"] = [fixture.removed(9, to="8")]
        data = self.build()
        proj_4 = self.issues(data)["PROJ-4"]
        self.assertFalse(proj_4["addedMidSprint"])
        self.assertEqual(data["removed_summary"]["descoped_incomplete"], {
                         "count": 1, "points": 3})
        self.assert_runs("make_charts.py", "--print-series")

    def test_left_before_the_start_is_not_reported(self):
        data = self.build()
        self.assertNotIn("PROJ-11", self.issues(data))
        self.assertEqual(data["removed_before_start_keys"], ["PROJ-11"])

    def test_issue_created_in_the_running_sprint_is_extra(self):
        issue = self.issues(self.build())["PROJ-7"]
        self.assertEqual(issue["enteredSprintAt"], issue["created"])
        self.assertTrue(issue["addedMidSprint"])

    def test_outcome_mirrors_the_board(self):
        data = self.build()
        self.assertEqual(data["outcome_counts"], {
                         "completed": 4, "carried_over": 2})
        self.assertEqual(data["outcome_points"], {
                         "completed": 7, "carried_over": 6})
        self.assertEqual(
            [i["key"] for i in data["non_delivery_closures"]["issues"]], ["PROJ-6"])

    def test_sub_tasks_are_left_out(self):
        data = self.build()
        self.assertNotIn("PROJ-9", [i["key"] for i in data["issues"]])

    def test_removals_are_split(self):
        summary = self.build()["removed_summary"]
        self.assertEqual(summary, {"descoped_incomplete": {"count": 1, "points": 3},
                                   "already_done_on_arrival": {"count": 1, "points": 2},
                                   "completed_before_removal": {"count": 1, "points": 2},
                                   "total": {"count": 3, "points": 7}})

    def test_done_at_the_start_is_credited_at_the_start(self):
        # PROJ-10 was finished after joining but before the start. PROJ-3 arrived
        # Done too, but was removed: it is only a removal, never a completion.
        data = self.build()
        start = data["scope_timeline"][0]
        self.assertEqual(start["already_done_original_keys"], ["PROJ-10"])
        self.assertTrue(self.issues(data)["PROJ-10"]["alreadyDoneOnArrival"])
        self.assertTrue(self.issues(data)["PROJ-3"]["alreadyDoneOnArrival"])
        self.assertFalse(any("PROJ-3" in r["completed_original_keys"] + r["already_done_original_keys"]
                             for r in data["scope_timeline"]))

    def test_cross_day_return_is_recorded(self):
        timeline = {r["date"]: r for r in self.build()["scope_timeline"]}
        self.assertIn("PROJ-6", timeline["2026-03-05"]["departure_keys"])
        self.assertEqual(timeline["2026-03-06"]["readded_keys"], ["PROJ-6"])

    def test_same_day_return_cancels_out(self):
        self.raw["changelogs/PROJ-6.json"] = [fixture.added(4), fixture.removed(5, "09:00"),
                                              fixture.added(5, "17:00")]
        timeline = self.build()["scope_timeline"]
        self.assertFalse(
            any("PROJ-6" in r["departure_keys"] + r["readded_keys"] for r in timeline))

    def test_completion_after_close_counts_as_carried_over(self):
        # The sprint closed at 16:00 on 13/03; PROJ-6 was closed an hour later.
        changes = self.raw["changelogs/PROJ-6.json"]
        changes[-1] = fixture.completed((13, "17:00"), "Duplicate")
        self.jira_did_not_complete_proj_6()
        data = self.build()
        proj_6 = self.issues(data)["PROJ-6"]
        self.assertEqual(
            (proj_6["status"], proj_6["carriedOver"]), ("In Progress", True))
        self.assertEqual(data["outcome_counts"], {
                         "completed": 3, "carried_over": 3})
        self.assertFalse(
            any("PROJ-6" in r["completed_original_keys"] for r in data["scope_timeline"]))

    def test_reopened_before_the_close_is_not_done(self):
        self.issue(
            "PROJ-6")["fields"]["status"] = fixture.status_field("To Do")
        self.raw["changelogs/PROJ-6.json"].append(
            fixture.moved((12,), "Duplicate", "To Do"))
        self.jira_did_not_complete_proj_6()
        data = self.build()
        proj_6 = self.issues(data)["PROJ-6"]
        self.assertIsNone(proj_6["completedAt"])
        self.assertTrue(proj_6["carriedOver"])
        self.assertFalse(
            any("PROJ-6" in r["completed_original_keys"] for r in data["scope_timeline"]))

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

    def test_blocker_candidates(self):
        self.assertEqual(self.build()["blocker_candidate_keys"], ["PROJ-7"])

    def test_epics_include_removed_work_and_no_epic(self):
        epics = {e["key"]: e for e in self.build()["epics"]}
        self.assertEqual(set(epics), {"PROJ-100", "PROJ-101", "__no_epic__"})
        self.assertEqual(epics["PROJ-101"]["removed_stories"], 2)
        self.assertEqual((epics["PROJ-100"]["original_stories_done"], epics["PROJ-100"]["original_stories_total"]),
                         (4, 5))

    def test_output_is_deterministic(self):
        self.build()
        with open(os.path.join(self.dir, "data.json"), "rb") as f:
            first = f.read()
        self.build()
        with open(os.path.join(self.dir, "data.json"), "rb") as f:
            self.assertEqual(f.read(), first)

    def test_bad_raw_data_writes_nothing(self):
        def drop_last_not_completed(raw):
            raw["sprint_report.json"]["contents"]["issuesNotCompletedInCurrentSprint"].pop()

        def empty_sprint_report(raw):
            for bucket in ("completedIssues", "issuesNotCompletedInCurrentSprint", "puntedIssues"):
                raw["sprint_report.json"]["contents"][bucket] = []

        cases = [
            (lambda raw: self.jira_did_not_complete_proj_6(),
             "completed: ['PROJ-6'] in our data but not in Jira's sprint report"),
            (drop_last_not_completed, "differs from Jira's sprint report"),
            (empty_sprint_report, "Jira's sprint report is empty"),
            (lambda raw: raw.pop("changelogs/PROJ-2.json"),
             "missing changelogs for PROJ-2"),
        ]
        for change, expected in cases:
            with self.subTest(expected):
                self.raw = copy.deepcopy(fixture.raw_files())
                change(self.raw)
                self.write_raw()
                proc = self.run_script(
                    "build_sprint_data.py", "--today", self.today)
                self.assertEqual(proc.returncode, 1)
                self.assertIn(expected, proc.stderr)
                self.assertFalse(os.path.exists(
                    os.path.join(self.dir, "data.json")))
                shutil.rmtree(os.path.join(self.dir, "_raw"))


class ReopenedAtTheStartTest(ReportTest):
    """Original work that was Done at the start isn't initial commitment. If it is
    reopened while in the sprint, it is extra scope from that day. The fixture
    sprint starts on 04/03 at 12:00 and closes on 13/03 at 16:00. Six issues are
    added to it, all in the sprint since before the start and Done on 27/02:

      PROJ-20  1 pt  never reopened
      PROJ-21  1 pt  reopened on 14/03, after the close
      PROJ-22  3 pts reopened 06/03, Done again 09/03, in the sprint at the close
      PROJ-23  2 pts reopened 06/03, still open at the close
      PROJ-24  4 pts reopened 06/03, removed 09/03 while open
      PROJ-25  5 pts reopened 06/03, Done again 07/03, removed 09/03
    """
    DONE_AT_START = fixture.moved(
        "2026-02-27T10:00:00.000+0000", "In Progress", "Done")
    NEW = {f"PROJ-{n}" for n in range(20, 26)}

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

    def setUp(self):
        super().setUp()
        self.before = self.build()
        self.add_scenarios()
        self.data, self.md = self.make_report()
        self.issues = {
            i["key"]: i for i in self.data["issues"] + self.data["removed_issues"]}
        self.timeline = {r["date"]: r for r in self.data["scope_timeline"]}

    def test_which_issues_are_initial_commitment(self):
        # name: (key, added mid-sprint, entered the sprint on, already Done on arrival)
        cases = [
            ("never reopened", "PROJ-20", False, "2026-03-04", True),
            ("reopened after the close", "PROJ-21", False, "2026-03-04", True),
            ("reopened and Done again", "PROJ-22", True, "2026-03-06", False),
            ("reopened and still open", "PROJ-23", True, "2026-03-06", False),
            ("reopened and removed open", "PROJ-24", True, "2026-03-06", False),
            ("reopened, Done again and removed",
             "PROJ-25", True, "2026-03-06", False),
        ]
        for name, key, extra, entered, already in cases:
            with self.subTest(name):
                issue = self.issues[key]
                self.assertEqual((issue["addedMidSprint"], issue["enteredSprintOn"], issue["alreadyDoneOnArrival"]),
                                 (extra, entered, already))

    def test_timeline(self):
        start = self.timeline["2026-03-04"]
        self.assertEqual([k for k in start["added_keys"] if k in self.NEW], [
                         "PROJ-20", "PROJ-21"])
        self.assertEqual([k for k in start["already_done_original_keys"] if k in self.NEW],
                         ["PROJ-20", "PROJ-21"])
        self.assertEqual(self.timeline["2026-03-06"]["added_keys"],
                         ["PROJ-22", "PROJ-23", "PROJ-24", "PROJ-25"])
        self.assertEqual(self.timeline["2026-03-06"]["added_points"], 14)
        # Completions: PROJ-25 before it left, PROJ-22 when it was Done again.
        self.assertEqual(self.timeline["2026-03-07"]
                         ["completed_extra_keys"], ["PROJ-25"])
        self.assertEqual(self.timeline["2026-03-09"]
                         ["completed_extra_keys"], ["PROJ-22"])
        # Removals: the open one is descoped, the finished one is not.
        removal = self.timeline["2026-03-09"]
        self.assertEqual(([k for k in removal["departure_keys"] if k in self.NEW],
                          [k for k in removal["removed_done_keys"] if k in self.NEW]),
                         (["PROJ-24", "PROJ-25"], ["PROJ-25"]))
        # Nothing of the reopened work is outstanding commitment or already done.
        for key in ("PROJ-22", "PROJ-23", "PROJ-24", "PROJ-25"):
            self.assertNotIn(key, start["added_keys"])
            self.assertTrue(
                all(key not in r["already_done_extra_keys"] for r in self.data["scope_timeline"]))

    def test_outcome_and_removals_change_only_where_expected(self):
        def grew(field, key):
            return self.data[field][key] - self.before[field][key]
        # Done at the close: PROJ-20, 21 and 22. Carried over: PROJ-23.
        self.assertEqual((grew("outcome_counts", "completed"),
                         grew("outcome_counts", "carried_over")), (3, 1))
        self.assertEqual((grew("outcome_points", "completed"),
                         grew("outcome_points", "carried_over")), (5, 2))
        summary, before = self.data["removed_summary"], self.before["removed_summary"]
        self.assertEqual(summary["descoped_incomplete"]["points"] -
                         before["descoped_incomplete"]["points"], 4)
        self.assertEqual(summary["completed_before_removal"]["points"]
                         - before["completed_before_removal"]["points"], 5)
        self.assertEqual(summary["already_done_on_arrival"],
                         before["already_done_on_arrival"])

    def test_epic_table_counts_reopened_work_as_extra(self):
        def row(data):
            return next(e for e in data["epics"] if e["key"] == "__no_epic__")
        now, before = row(self.data), row(self.before)
        diff = {k: now[k] - before[k]
                for k in now if isinstance(now[k], (int, float))}
        # Extra: PROJ-22 and 25 are done, PROJ-23 and 24 are not. Original: 20 and 21 are done.
        self.assertEqual((diff["extra_stories_total"],
                         diff["extra_stories_done"]), (4, 2))
        self.assertEqual((diff["extra_points_total"],
                         diff["extra_points_done"]), (14, 8))
        self.assertEqual((diff["original_stories_total"],
                         diff["original_stories_done"]), (2, 2))

    def test_burndown_adds_the_reopened_points_on_the_day_and_never_to_the_commitment(self):
        now = {r["date"]: r for r in self.data["burndown"]}
        before = {r["date"]: r for r in self.before["burndown"]}
        # The extra points: 14 from the 6th, 9 once PROJ-25 is done on the 7th, 2 once PROJ-22 is done
        # and PROJ-24 is removed on the 9th.
        extra = {"2026-03-04": 0, "2026-03-05": 0, "2026-03-06": 14, "2026-03-07": 9, "2026-03-08": 9,
                 "2026-03-09": 2, "2026-03-13": 2}
        for day, points in extra.items():
            with self.subTest(day):
                self.assertEqual(now[day]["committed"],
                                 before[day]["committed"])
                self.assertEqual(now[day]["total"] -
                                 before[day]["total"], points)
        out = self.assert_runs("make_charts.py", "--print-series").stdout
        self.assertIn("baseline 14 pts", out)

    def test_planning_and_target_completion_leave_out_the_reopened_work(self):
        # Original work is the fixture's plus PROJ-20 and 21; both were Done at the start.
        self.assertIn(
            "excludes 4 tickets already closed when the sprint started", self.md)
        self.assertIn(
            "Planning baseline: 9 stories / 19 pts were in the sprint when it started", self.md)
        self.assertIn(
            "4 stories / 5 pts of them already Done, leaving 5 stories / 14 pts to do", self.md)


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
                          ("2026-03-06", "2026-03-07", "2026-03-11", "2026-03-12")], [9, 12, 8, 9])
        out = self.assert_runs("make_charts.py", "--print-series").stdout
        self.assertIn("baseline 14 pts", out)

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
        for field in ("outcome_counts", "outcome_points", "scope_timeline", "burndown", "removed_summary"):
            self.assertEqual(after[field], before[field], field)
        self.assertEqual(
            after["membership_cross_check_excluded_keys"], ["PROJ-1"])
        self.assertIn("later sprint moves prevent comparison", md)

    def test_closing_day_stops_at_the_exact_close(self):
        before = self.build()["burndown"]
        self.raw["changelogs/PROJ-2.json"].append(
            fixture.completed((13, "17:00")))
        self.issue("PROJ-2")["fields"]["status"] = fixture.status_field("Done")
        self.assertEqual(self.build()["burndown"], before)

    def test_print_series(self):
        self.build()
        out = self.assert_runs("make_charts.py", "--print-series").stdout
        # The baseline leaves out PROJ-3 and PROJ-10, Done at the start, as
        # Jira's burndown does.
        self.assertIn(
            "baseline 14 pts committed at the start on 2026-03-04", out)
        # Start day: the baseline, then the day's close, with PROJ-5 (added after it).
        self.assertRegex(out, r"2026-03-04 +Wed +start +14 +14 +14 +0")
        self.assertRegex(out, r"2026-03-04 +Wed +close +14 +16 +14 +0")
        self.assertRegex(out, r"2026-03-13 +Fri +close +5 +6 +0 +5")

    def test_late_close_extends_the_chart(self):
        # Planned to end on Friday 13/03, but closed on Monday 16/03.
        self.raw["sprint.json"]["completeDate"] = "2026-03-16T16:00:00.000Z"
        self.build()
        out = self.assert_runs("make_charts.py", "--print-series").stdout
        self.assertRegex(out, r"2026-03-13 +Fri +close +5 +6 +0 +5")
        self.assertRegex(out, r"2026-03-16 +Mon +close +5 +6 +0 +5")

    def test_writes_svg_charts(self):
        self.build()
        self.assert_runs("make_charts.py")
        for name in ("outcome-stories.svg", "outcome-points.svg", "burndown.svg"):
            with open(os.path.join(self.dir, name), encoding="utf-8") as f:
                self.assertTrue(f.read().startswith("<svg "), name)


class OutputFolderTest(ReportTest):
    def test_a_report_folder_outside_the_output_folder_gets_nothing(self):
        self.make_report()
        outside = os.path.join(self.tmp.name, "elsewhere")
        cases = [
            ("build_sprint_data.py", ["--today", self.today], ["data.json"]),
            ("make_charts.py", [], ["outcome-stories.svg",
             "outcome-points.svg", "burndown.svg"]),
            ("make_report.py", [], [REPORT]),
        ]
        for script, args, outputs in cases:
            with self.subTest(script):
                shutil.copytree(self.dir, outside)
                for name in outputs:
                    os.remove(os.path.join(outside, name))
                proc = self.run_script(script, *args, report_dir=outside)
                self.assertEqual(proc.returncode, 1, proc.stdout)
                self.assertIn("where sprint reports are written", proc.stderr)
                self.assertEqual(
                    [n for n in outputs if os.path.exists(os.path.join(outside, n))], [])
                shutil.rmtree(outside)


class MakeReportTest(ReportTest):
    def test_closed_sprint_report(self):
        _, md = self.make_report()
        self.assertIn(
            "**6 issues (13 points)** are in scope: 4 completed (7 points) and 2 carried over", md)
        self.assertIn("[PROJ-1](https://acme.atlassian.net/browse/PROJ-1)", md)
        self.assertIn("04/03/2026–13/03/2026", md)
        self.assertIn(
            "Planning baseline: 7 stories / 17 pts were in the sprint when it started on 04/03/2026, "
            "2 stories / 3 pts of them already Done, leaving 5 stories / 14 pts to do (the burndown's baseline).", md)
        self.assertIn("<b>Reinstated, 1 story / 1 pt</b>", md)
        self.assertNotIn("mid-sprint snapshot", md)

    def test_active_sprint_report(self):
        self.raw["sprint.json"].update(state="active", completeDate=None)
        self.today = "2026-03-11"
        _, md = self.make_report()
        self.assertIn(
            "This is a mid-sprint snapshot as at 11/03/2026, with 2 calendar days remaining.", md)
        self.assertIn("2 still open", md)
        self.assertIn("(today)", md)

    def test_no_goal(self):
        self.raw["sprint.json"]["goal"] = None
        _, md = self.make_report()
        self.assertIn("*No goal was set in Jira for this sprint*", md)
        self.assertIn("Goal discipline: no sprint goal was set in Jira", md)

    def test_em_dashes_are_replaced(self):
        self.content["key_achievements"] = [
            "The import flow — finally — shipped."]
        _, md = self.make_report()
        self.assertIn("The import flow, finally, shipped.", md)

    def test_bad_content_fails(self):
        cases = [
            (lambda content: content["epic_commentary"].pop(
                "PROJ-101"), "epic_commentary is missing: PROJ-101"),
            (lambda content: content.update(key_achievements=["One.", "Two.", "Three."]),
             "key_achievements must be a list of 1-2"),
        ]
        self.build()
        for change, expected in cases:
            with self.subTest(expected):
                content = copy.deepcopy(fixture.CONTENT)
                change(content)
                with open(os.path.join(self.dir, "content.json"), "w", encoding="utf-8") as f:
                    json.dump(content, f)
                proc = self.run_script("make_report.py")
                self.assertEqual(proc.returncode, 1)
                self.assertIn(expected, proc.stderr)


class CheckReportTest(ReportTest):
    def test_a_broken_report_fails(self):
        self.make_report()
        path = os.path.join(self.dir, REPORT)
        with open(path, encoding="utf-8") as f:
            md = f.read()
        cases = [
            ("<b>10 stories / 21 pts</b>", "<b>10 stories / 22 pts</b>",
             "FAIL  columns: Added total is 10 stories / 21 pts"),
            ("<b>4 stories / 8 pts</b></td>", "<b>4 stories / 8 pts (3 left)</b></td>",
             "FAIL  totals row: Removed is a bare total"),
            ("1 story / 3 pts<br><a", "1 story / 3 pts<br><br><a", "FAIL  spacing"),
            ("Delivery concentrated", "Delivery — concentrated", "FAIL  em dashes"),
            ("04/03/2026–13/03/2026", "2026-03-04–13/03/2026", "FAIL  dates"),
            ("[PROJ-5](https://acme.atlassian.net/browse/PROJ-5) was added",
             "PROJ-5 was added", "FAIL  links"),
            ("4 completed (7 points)", "4 completed (8 points)",
             "FAIL  figures: completed"),
            ("<b>Reinstated, 1 story / 1 pt</b>", "<b>New scope, 1 story / 1 pt</b>",
             "FAIL  movements: PROJ-6 return shown as Reinstated"),
            ("Board-data quality:", "Board data:",
             "FAIL  retro: Board-data quality covered"),
            ("<td>4/5</td>", "<td>3/5</td>", "FAIL  epics: PROJ-100 shows 4/5"),
            ('PROJ-5</a></td>', 'PROJ-5</a> <i>(late)</i></td>', "FAIL  cell shapes"),
        ]
        for old, new, expected in cases:
            with self.subTest(expected):
                self.assertIn(old, md)
                with open(path, "w", encoding="utf-8") as f:
                    f.write(md.replace(old, new, 1))
                proc = self.run_script("check_report.py")
                self.assertEqual(proc.returncode, 1, proc.stdout)
                self.assertIn(expected, proc.stdout)

    def test_missing_chart(self):
        self.make_report()
        os.remove(os.path.join(self.dir, "burndown.svg"))
        proc = self.run_script("check_report.py")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("FAIL  images: burndown.svg exists", proc.stdout)


if __name__ == "__main__":
    unittest.main()
