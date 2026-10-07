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
    """The fixture sprint, as the model sees it (see build_sprint_data.py):
    original PROJ-1 (carried over), 2, 3 (Done at the start, descoped), 4
    (descoped), 6 (left: descoped; came back as extra work, Duplicate), 8
    (completed, descoped) and 10 (Done at the start); extra PROJ-5 and 7;
    PROJ-11 left before the start."""

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
        return [f"{e['type']} {e['date'][8:]}" for e in spell["events"]]

    def test_who_belongs(self):
        data = self.build()
        self.assertEqual(data["sprint_start"], "2026-03-04")
        self.assertEqual({k: [t["scope"] for t in spells] for k, spells in self.spells(data).items()}, {
            "PROJ-1": ["original"], "PROJ-2": ["original"], "PROJ-3": ["original"], "PROJ-4": ["original"],
            "PROJ-5": ["extra"], "PROJ-6": ["original", "extra"], "PROJ-7": ["extra"], "PROJ-8": ["original"],
            "PROJ-10": ["original"]})
        self.assertEqual(data["left_before_start_keys"], ["PROJ-11"])

    def test_outcomes(self):
        data = self.build()
        self.assertEqual({k: [t["outcome"] for t in spells] for k, spells in self.spells(data).items()}, {
            "PROJ-1": ["completed"], "PROJ-2": ["not_completed"], "PROJ-3": ["removed"], "PROJ-4": ["removed"],
            "PROJ-5": ["completed"], "PROJ-6": ["removed", "completed"], "PROJ-7": ["not_completed"],
            "PROJ-8": ["removed"], "PROJ-10": ["completed"]})
        self.assertEqual(
            [i["key"] for i in data["non_delivery_closures"]["issues"]], ["PROJ-6"])
        outcomes = ("completed", "not_completed", "removed")
        self.assertEqual({row: [data["outcome_breakdown_counts"][f"{row}_{o}"] for o in outcomes]
                          for row in ("original", "extra")}, {"original": [2, 1, 4], "extra": [2, 1, 0]})
        self.assertEqual([data["outcome_breakdown_points"]
                         [f"original_{o}"] for o in outcomes], [4, 5, 8])

    def test_events(self):
        spells = self.spells(self.build())
        tickets = self.tickets(self.build())
        self.assertEqual({k: [event for t in found for event in self.kinds(t)] for k, found in spells.items()}, {
            "PROJ-1": ["committed 04", "completed 06"],
            "PROJ-2": ["committed 04"],
            "PROJ-3": ["committed 04", "removed 05"],
            "PROJ-4": ["committed 04", "removed 09"],
            "PROJ-5": ["joined 04", "completed 10"],
            "PROJ-6": ["committed 04", "removed 05", "joined 06", "completed 11"],
            "PROJ-7": ["joined 10"],
            "PROJ-8": ["committed 04", "completed 05", "removed 06"],
            "PROJ-10": ["committed 04"]})
        self.assertEqual([tickets[k]["events"][0]["done"] for k in ("PROJ-3", "PROJ-10", "PROJ-2")],
                         [True, True, False])
        self.assertEqual(tickets["PROJ-7"]["events"][0]
                         ["at"], tickets["PROJ-7"]["created"])

    def test_edited_start_date_is_used_as_is(self):
        # Everything joined after a start moved back to 02/03: all extra, and
        # the extra work later removed was never part of the sprint.
        self.raw["sprint.json"]["startDate"] = "2026-03-02T09:00:00.000Z"
        data = self.build()
        self.assertEqual(data["sprint_start"], "2026-03-02")
        self.assertEqual({t["scope"] for t in data["spells"]}, {"extra"})
        self.assertEqual([t["key"] for t in data["spells"] if not t["counted"]],
                         ["PROJ-3", "PROJ-4", "PROJ-6", "PROJ-8", "PROJ-11"])

    def test_issue_in_the_sprint_since_creation_with_only_a_removal(self):
        # Jira logs no add for a sprint set when the issue was created.
        self.raw["changelogs/PROJ-4.json"] = [fixture.removed(9, to="8")]
        proj_4 = self.tickets(self.build())["PROJ-4"]
        self.assertEqual((proj_4["scope"], self.kinds(
            proj_4)), ("original", ["committed 04", "removed 09"]))
        self.assert_runs("make_charts.py", "--print-series")

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
        self.assertIn("| Carried over from Sprint 6 | 2 tickets \\| 29% of commitment (5 pts \\| 29%); 1 ticket (3 pts) "
                      "completed |", md)

    def test_descoped_extra_work_is_history_not_final_situation(self):
        # PROJ-5, extra, is descoped after completing: the timeline and the
        # burndown show it, the final situation doesn't count it.
        self.raw["changelogs/PROJ-5.json"] = self.raw["changelogs/PROJ-5.json"] + [
            fixture.removed(11, to="8")]
        self.raw["sprint_issues.json"] = [
            i for i in self.raw["sprint_issues.json"] if i["key"] != "PROJ-5"]
        self.raw["punted_issues.json"] = self.raw["punted_issues.json"] + [
            i for i in fixture.CURRENT if i["key"] == "PROJ-5"]
        report = self.raw["sprint_report.json"]["contents"]
        report["completedIssues"] = [
            e for e in report["completedIssues"] if e["key"] != "PROJ-5"]
        report["puntedIssues"] = report["puntedIssues"] + [{"key": "PROJ-5"}]
        before = self.build()
        proj_5 = self.tickets(before)["PROJ-5"]
        self.assertEqual((proj_5["scope"], proj_5["outcome"],
                         proj_5["counted"]), ("extra", "removed", False))
        self.assertIn(("PROJ-5", "removed"), [(e["key"], e["type"])
                      for row in before["timeline"] for e in row["events"]])
        self.assertEqual(before["outcome_breakdown_counts"]
                         ["extra_completed"], 1)  # PROJ-6 only
        burndown = {r["date"]: r["total"] - r["committed"]
                    for r in before["burndown"]}
        # Extra open: PROJ-5 (2) from the 4th; with PROJ-6's new spell (1) on the 9th.
        self.assertEqual(
            (burndown["2026-03-04"], burndown["2026-03-09"]), (2, 3))

    def test_sub_tasks_are_left_out(self):
        self.assertNotIn("PROJ-9", self.tickets(self.build()))

    def test_same_day_leave_and_return_is_a_descope_then_an_addition(self):
        self.raw["changelogs/PROJ-6.json"] = [fixture.added(4), fixture.removed(5, "09:00"),
                                              fixture.added(5, "17:00")]
        spells = self.spells(self.build())["PROJ-6"]
        self.assertEqual([(t["scope"], self.kinds(t)) for t in spells],
                         [("original", ["committed 04", "removed 05"]), ("extra", ["joined 05"])])

    def test_completion_after_the_close_is_not_completed(self):
        # The sprint closed at 16:00 on 13/03; PROJ-6 was closed an hour later.
        changes = self.raw["changelogs/PROJ-6.json"]
        changes[-1] = fixture.completed((13, "17:00"), "Duplicate")
        self.jira_did_not_complete_proj_6()
        proj_6 = self.tickets(self.build())["PROJ-6"]
        self.assertEqual(
            (proj_6["status"], proj_6["outcome"]), ("In Progress", "not_completed"))
        self.assertNotIn("completed 13", self.kinds(proj_6))

    def test_reopened_before_the_close_is_not_completed(self):
        self.issue(
            "PROJ-6")["fields"]["status"] = fixture.status_field("To Do")
        self.raw["changelogs/PROJ-6.json"].append(
            fixture.moved((12,), "Duplicate", "To Do"))
        self.jira_did_not_complete_proj_6()
        proj_6 = self.tickets(self.build())["PROJ-6"]
        self.assertEqual((proj_6["outcome"], self.kinds(proj_6)[-2:]),
                         ("not_completed", ["completed 11", "reopened 12"]))

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

    def test_epics(self):
        # PROJ-100: PROJ-1 and 10 completed, PROJ-2 open, PROJ-6 and 8
        # descoped; PROJ-6 completed again as extra work.
        epics = {e["key"]: e for e in self.build()["epics"]}
        self.assertEqual(set(epics), {"PROJ-100", "PROJ-101", "__no_epic__"})
        self.assertEqual(epics["PROJ-101"]["removed_stories"], 2)
        self.assertEqual((epics["PROJ-100"]["original_stories_done"], epics["PROJ-100"]["original_stories_total"],
                          epics["PROJ-100"]["extra_stories_done"]), (2, 5, 1))

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
                    "build_sprint_data.py")
                self.assertEqual(proc.returncode, 1)
                self.assertIn(expected, proc.stderr)
                self.assertFalse(os.path.exists(
                    os.path.join(self.dir, "data.json")))
                shutil.rmtree(os.path.join(self.dir, "_raw"))


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
    """
    DONE_AT_START = fixture.moved(
        "2026-02-27T10:00:00.000+0000", "In Progress", "Done")
    NEW = [f"PROJ-{n}" for n in range(20, 26)]

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
        self.tickets = {t["key"]: t for t in self.data["spells"]}

    def test_all_are_original_commitment(self):
        cases = [
            ("never reopened", "PROJ-20", "completed", ["committed 04"]),
            ("reopened after the close", "PROJ-21",
             "completed", ["committed 04"]),
            ("reopened and Done again", "PROJ-22", "completed",
             ["committed 04", "reopened 06", "completed 09"]),
            ("reopened and still open", "PROJ-23",
             "not_completed", ["committed 04", "reopened 06"]),
            ("reopened and removed open", "PROJ-24", "removed",
             ["committed 04", "reopened 06", "removed 09"]),
            ("reopened, Done again and removed", "PROJ-25", "removed",
             ["committed 04", "reopened 06", "completed 07", "removed 09"]),
        ]
        for name, key, outcome, events in cases:
            with self.subTest(name):
                ticket = self.tickets[key]
                self.assertEqual((ticket["scope"], ticket["outcome"],
                                  [f"{e['type']} {e['date'][8:]}" for e in ticket["events"]]),
                                 ("original", outcome, events))
                self.assertTrue(ticket["events"][0]["done"])

    def test_outcomes_change_only_where_expected(self):
        def grew(field, key):
            return self.data[field][key] - self.before[field][key]
        self.assertEqual([grew("outcome_breakdown_counts", f"original_{o}")
                          for o in ("completed", "not_completed", "removed")], [3, 1, 2])
        self.assertEqual([grew("outcome_breakdown_points", f"original_{o}")
                          for o in ("completed", "not_completed", "removed")], [5, 2, 9])
        self.assertEqual([grew("outcome_breakdown_counts", f"extra_{o}")
                          for o in ("completed", "not_completed", "removed")], [0, 0, 0])

    def test_burndown_moves_reopened_points_back_to_the_commitment(self):
        now = {r["date"]: r for r in self.data["burndown"]}
        before = {r["date"]: r for r in self.before["burndown"]}
        # Reopened on the 6th: 14 pts open again; 9 once PROJ-25 is done on the
        # 7th; 2 once PROJ-22 is done and PROJ-24 is removed on the 9th.
        reopened = {"2026-03-04": 0, "2026-03-05": 0, "2026-03-06": 14, "2026-03-07": 9, "2026-03-08": 9,
                    "2026-03-09": 2, "2026-03-13": 2}
        for day, points in reopened.items():
            with self.subTest(day):
                self.assertEqual(now[day]["committed"] -
                                 before[day]["committed"], points)
                self.assertEqual(now[day]["total"] -
                                 before[day]["total"], points)
        out = self.assert_runs("make_charts.py", "--print-series").stdout
        self.assertIn("baseline 33 pts", out)

    def test_planning_and_target_completion_count_them(self):
        self.assertIn("Of the 13 tickets (33 pts) in the commitment, 8 tickets (19 pts) were already Done at the start",
                      self.md)
        self.assertIn(
            "| Sprint target completion | 38%, 5/13 tickets (9/33 pts) completed |", self.md)
        self.assertIn(
            '<a href="https://acme.atlassian.net/browse/PROJ-20">PROJ-20</a> (1 pt)', self.md)
        self.assertEqual(self.md.count(">Already done</span>"), 8)
        self.assertEqual(self.md.count(">Reopened</span>"),
                         4)  # PROJ-22 to 25, on the 6th

    def test_epic_table_counts_them_as_original(self):
        def row(data):
            return next(e for e in data["epics"] if e["key"] == "__no_epic__")
        now, before = row(self.data), row(self.before)
        diff = {k: now[k] - before[k]
                for k in now if isinstance(now[k], (int, float))}
        self.assertEqual([diff[k] for k in ("original_stories_total", "original_stories_done",
                                            "original_points_total", "original_points_done",
                                            "extra_stories_total")], [6, 3, 16, 5, 0])


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

    def test_closing_day_stops_at_the_exact_close(self):
        before = self.build()["burndown"]
        self.raw["changelogs/PROJ-2.json"].append(
            fixture.completed((13, "17:00")))
        self.issue("PROJ-2")["fields"]["status"] = fixture.status_field("Done")
        self.assertEqual(self.build()["burndown"], before)

    def test_ticket_first_added_after_close_is_explained_without_being_counted(self):
        self.raw["changelogs/PROJ-7.json"] = [fixture.added(16)]
        self.raw["_meta.json"]["blocker_candidate_keys"] = []
        data, md = self.make_report()
        self.assertNotIn("PROJ-7", [s["key"] for s in data["spells"]])
        self.assertEqual(data["left_before_start_keys"], ["PROJ-11"])
        self.assertEqual(
            data["membership_cross_check_excluded_keys"], ["PROJ-7"])
        self.assertIn("PROJ-7) (– pts) is reconstructed from changelogs", md)

    def test_print_series(self):
        self.build()
        out = self.assert_runs("make_charts.py", "--print-series").stdout
        # The baseline is the whole commitment at the start, including PROJ-3
        # and PROJ-10, already Done then.
        self.assertIn(
            "baseline 17 pts committed at the start on 2026-03-04", out)
        # Start day: the baseline, then the day's close, without the work
        # already Done and with PROJ-5 (added after the start).
        self.assertRegex(out, r"2026-03-04 +Wed +start +17 +17 +17 +0")
        self.assertRegex(out, r"2026-03-04 +Wed +close +14 +16 +17 +-3")
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
        for name in ("outcome-tickets.svg", "outcome-pts.svg", "burndown.svg"):
            with open(os.path.join(self.dir, name), encoding="utf-8") as f:
                self.assertTrue(f.read().startswith("<svg "), name)


class TimezoneTest(ReportTest):
    def test_active_snapshot_date_follows_fetch_in_reporting_timezone(self):
        cases = [
            ("Europe/London", "2026-03-30", "2026-04-03", "today"),
            ("America/New_York", "2026-03-29", "2026-04-03", "today"),
            ("Europe/London", "2026-03-30", "2026-03-27", "sprint end"),
        ]
        for zone, expected_day, end_day, cutoff_label in cases:
            with self.subTest(zone=zone, end=end_day):
                self.raw = copy.deepcopy(fixture.raw_files())
                self.raw["_meta.json"].update(
                    fetched_at="2026-03-29T23:30:00Z", report_timezone=zone)
                self.raw["sprint.json"].update(
                    state="active", completeDate=None, endDate=f"{end_day}T17:00:00Z")
                self.content["goal_verdict"] = "At risk"
                data, md = self.make_report()
                self.assertEqual(data["today"], expected_day)
                self.assertEqual(data["burndown"][-1]
                                 ["date"], min(expected_day, end_day))
                today_row = next(
                    row for row in data["timeline"] if "today" in row["labels"])
                self.assertEqual(today_row["date"], expected_day)
                display_day = "/".join(reversed(expected_day.split("-")))
                self.assertIn(f"snapshot as at {display_day}", md)
                with open(os.path.join(self.dir, "burndown.svg"), encoding="utf-8") as f:
                    self.assertIn(f">{cutoff_label}<", f.read())

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

    def test_old_raw_data_requires_a_fresh_fetch(self):
        self.raw["_meta.json"].pop("report_timezone")
        self.write_raw()
        proc = self.run_script("build_sprint_data.py")
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("no reporting timezone", proc.stderr)
        self.assertFalse(os.path.exists(os.path.join(self.dir, "data.json")))


class OutputFolderTest(ReportTest):
    def test_a_report_folder_outside_the_output_folder_gets_nothing(self):
        self.make_report()
        outside = os.path.join(self.tmp.name, "elsewhere")
        cases = [
            ("build_sprint_data.py", [], ["data.json"]),
            ("make_charts.py", [], ["outcome-tickets.svg",
             "outcome-pts.svg", "burndown.svg"]),
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
            "Of the 7 tickets (17 pts) in the commitment, 2 tickets (3 pts) were already Done at the start "
            "([PROJ-3](https://acme.atlassian.net/browse/PROJ-3), [PROJ-10](https://acme.atlassian.net/browse/PROJ-10)), "
            "and 4 tickets (8 pts) were descoped.",
            md)
        self.assertIn(
            "- [PROJ-6](https://acme.atlassian.net/browse/PROJ-6) (1 pt) left the sprint", md)
        self.assertIn("04/03/2026–13/03/2026", md)
        self.assertIn("<b>Commitment:</b><br>7 tickets (17 pts)", md)
        # PROJ-6 left on the 5th and came back on the 6th: Descoped, then Added.
        self.assertIn("PROJ-6</a> (1 pt)</td><td><span", md)
        self.assertIn(">Descoped</span>", md)
        self.assertNotIn("mid-sprint snapshot", md)

    def test_active_sprint_report(self):
        self.raw["sprint.json"].update(state="active", completeDate=None)
        self.raw["_meta.json"]["fetched_at"] = "2026-03-11T12:00:00Z"
        self.content["goal_verdict"] = "On track"
        _, md = self.make_report()
        self.assertIn(
            'This is a mid-sprint snapshot as at 11/03/2026, with 2 days left. "Open" means not completed yet.', md)
        self.assertIn(
            "2 tickets (6 pts) are open, 1 ticket (5 pts) of them from the commitment, with 2 days left.", md)
        self.assertIn("(today)", md)

    def test_no_goal(self):
        self.raw["sprint.json"]["goal"] = None
        self.content["goal_verdict"] = "No goal set in Jira for this sprint"
        _, md = self.make_report()
        self.assertIn("*No goal was set in Jira for this sprint*", md)
        self.assertIn(
            "| Goal outcome [AI Generated] | No goal set in Jira for this sprint |", md)

    def test_goal_verdict_must_suit_the_sprint(self):
        cases = [({}, "On track"), ({"goal": None}, "Partially met")]
        for sprint_changes, verdict in cases:
            with self.subTest(verdict=verdict):
                self.raw = copy.deepcopy(fixture.raw_files())
                self.raw["sprint.json"].update(sprint_changes)
                self.content["goal_verdict"] = verdict
                self.build()
                self.assert_runs("make_charts.py")
                with open(os.path.join(self.dir, "content.json"), "w", encoding="utf-8") as f:
                    json.dump(self.content, f)
                proc = self.run_script("make_report.py")
                self.assertNotEqual(proc.returncode, 0)
                self.assertIn("goal_verdict must be one of", proc.stderr)

    def test_em_dashes_are_replaced(self):
        self.content["key_achievements"] = "The import flow — finally — shipped."
        _, md = self.make_report()
        self.assertIn("The import flow, finally, shipped.", md)

    def test_jira_source_text_survives_the_pipeline(self):
        source = "One story — fix issues"
        self.raw["sprint.json"].update(name=source, goal=source)
        self.raw["previous_sprint.json"]["name"] = source
        for parent in self.raw["parents.json"]:
            parent["fields"]["summary"] = source
        _, md = self.make_report()
        self.assertIn("# Sprint Summary: " + source, md)
        self.assertIn("| Goal | " + source + " |", md)
        self.assertIn("Carried over from " + source, md)
        self.assertIn(": " + source + "</a>", md)

    def test_bad_content_fails(self):
        cases = [
            (lambda content: content["epic_commentary"].pop(
                "PROJ-101"), "epic_commentary.PROJ-101 needs a sentence for exactly these groups: "
                             "not_completed, descoped"),
            (lambda content: content.update(key_achievements=["One.", "Two."]),
             "key_achievements must be a non-empty string"),
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
            ("<b>Commitment:</b><br>7 tickets (17 pts)", "<b>Commitment:</b><br>7 tickets (18 pts)",
             "FAIL  timeline: 04/03/2026 end of day"),
            ("The import flow shipped", "The import flow — shipped", "FAIL  em dashes"),
            ("04/03/2026–13/03/2026", "2026-03-04–13/03/2026", "FAIL  dates"),
            ("[PROJ-6](https://acme.atlassian.net/browse/PROJ-6) (1 pt) left the sprint",
             "PROJ-6 (1 pt) left the sprint", "FAIL  links"),
            ("4 tickets (8 pts) were descoped", "4 tickets (9 pts) were descoped",
             "FAIL  commentary: states 4 tickets (8 pts) descoped"),
            (">Added</span></td></tr>\n<tr><td style=\"white-space:nowrap\"><a href=\"https://acme.atlassian.net/browse/PROJ-6\">",
             ">Completed</span></td></tr>\n<tr><td style=\"white-space:nowrap\"><a href=\"https://acme.atlassian.net/browse/PROJ-6\">",
             "FAIL  timeline: 04/03/2026 lists each ticket's events, in time order"),
            ("was the commitment too large?", "the commitment was too large.",
             "FAIL  retro: each note ends with a question"),
            ("<td>2/5 tickets (4/12 pts)</td>", "<td>3/5 tickets (4/12 pts)</td>",
             "FAIL  epics: PROJ-100 shows 2/5 tickets (4/12 pts)"),
            ("The import flow shipped", "The import flow story shipped",
             "FAIL  vocabulary: no story or stories"),
            ('<td rowspan="8" style', '<td rowspan="7" style', "FAIL  cell shapes"),
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
