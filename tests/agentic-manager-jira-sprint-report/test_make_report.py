# Unit tests for skills/agentic-manager-jira-sprint-report/scripts/make_report.py.
# Run with: python3 tests/run.py agentic-manager-jira-sprint-report
#
# The sprint is described in report_fixture.py.
import copy
import os
import sys
import unittest

# tests/<skill>/ mirrors skills/<skill>/.
TEST_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(TEST_DIR))
sys.path.insert(0, os.path.join(REPO_ROOT, "skills",
                os.path.basename(TEST_DIR), "scripts"))
import make_report  # noqa: E402
from common import NO_EPIC  # noqa: E402
from make_report import Report  # noqa: E402

sys.path.insert(0, TEST_DIR)
from report_fixture import BASE, CONTENT, issue, row, sprint_data, totals  # noqa: E402


def report(**changes):
    return Report(sprint_data(**changes), copy.deepcopy(CONTENT))


class HelpersTest(unittest.TestCase):
    def test_were_and_they(self):
        self.assertEqual(
            (make_report.were(1), make_report.were(2)), ("was", "were"))
        self.assertEqual(
            (make_report.they(1), make_report.they(0)), ("it", "they"))

    def test_strip_em_dashes(self):
        self.assertEqual(make_report.strip_em_dashes({"a": ["x — y", 3], "b": "p—q"}),
                         {"a": ["x, y", 3], "b": "p, q"})


class LinksTest(unittest.TestCase):
    def test_links(self):
        r = report()
        self.assertEqual(r.md_key("PROJ-1"), f"[PROJ-1]({BASE}/browse/PROJ-1)")
        self.assertEqual(r.html_key("PROJ-1"),
                         f'<a href="{BASE}/browse/PROJ-1">PROJ-1</a>')
        self.assertEqual(r.linkify("See PROJ-1 and a-2."),
                         f"See [PROJ-1]({BASE}/browse/PROJ-1) and a-2.")
        self.assertEqual(r.linkify_html("PROJ-1 < 2"),
                         f'<a href="{BASE}/browse/PROJ-1">PROJ-1</a> &lt; 2')

    def test_table_text_keeps_a_markdown_cell_on_one_line(self):
        self.assertEqual(report().table_text("a | b\nc"), "a \\| b c")


class CellsTest(unittest.TestCase):
    def setUp(self):
        self.r = report()
        self.link = self.r.html_key

    def test_cell_shapes(self):
        link = self.link
        cases = [
            ("empty", [("Delivered", [])], False, "–"),
            ("flat", [("Delivered", ["PROJ-1", "PROJ-5"])], False,
             f"2 stories / 5 pts<br>{link('PROJ-1')}, {link('PROJ-5')}"),
            ("subcategorised", [("Delivered", ["PROJ-1"]), ("Already done", ["PROJ-4"])], False,
             f"2 stories / 4 pts<br><br><b>Delivered, 1 story / 3 pts</b><br>{link('PROJ-1')}"
             f"<br><br><b>Already done, 1 story / 1 pt</b><br>{link('PROJ-4')}"),
            ("forced groups", [("Delivered", ["PROJ-1"])], True,
             f"1 story / 3 pts<br><br><b>Delivered, 1 story / 3 pts</b><br>{link('PROJ-1')}"),
        ]
        for name, groups, force, expected in cases:
            with self.subTest(name):
                self.assertEqual(self.r.cell(
                    groups, force_groups=force), expected)

    def test_removed_cell(self):
        data = sprint_data()
        data["removed_issues"] += [issue("PROJ-7",
                                         1, already=True), issue("PROJ-8", 4)]
        r = Report(data, CONTENT)
        cell = r.removed_cell(row(
            "2026-03-04", departure=["PROJ-6", "PROJ-7", "PROJ-8"], removed_done=["PROJ-7", "PROJ-8"]))
        self.assertIn("<b>Descoped, 1 story / 2 pts</b>", cell)
        self.assertIn("<b>Already done, 1 story / 1 pt</b>", cell)
        self.assertIn("<b>Removed after completion, 1 story / 4 pts</b>", cell)

    def test_added_cell_groups_reinstated_work(self):
        self.assertTrue(self.r.added_cell(
            row("2026-03-05", added=["PROJ-3"])).startswith("1 story / 1 pt<br>"))
        cell = self.r.added_cell(
            row("2026-03-05", added=["PROJ-3"], readded=["PROJ-6"]))
        self.assertIn("<b>New scope, 1 story / 1 pt</b>", cell)
        self.assertIn("<b>Reinstated, 1 story / 2 pts</b>", cell)

    def test_completion_cell_separates_non_delivery_and_already_done(self):
        cell = self.r.completion_cell(row("2026-03-05", completed_original=["PROJ-1", "PROJ-5"],
                                          already_done_original=["PROJ-4"]), "original")
        self.assertIn("<b>Delivered, 1 story / 3 pts</b>", cell)
        self.assertIn("<b>Closed as duplicate, 1 story / 2 pts</b>", cell)
        self.assertIn("<b>Already done, 1 story / 1 pt</b>", cell)


class TablesTest(unittest.TestCase):
    def test_timeline_table(self):
        table = report().timeline_table()
        self.assertIn("<td>02/03/2026<br>(sprint start)</td>", table)
        self.assertIn("<td>13/03/2026<br>(sprint closed)</td>", table)
        self.assertIn("<td><b>Total</b></td><td><b>6 stories / 11 pts</b></td><td><b>1 story / 2 pts</b></td>"
                      "<td><b>3 stories / 6 pts</b></td><td><b>1 story / 1 pt</b></td>", table.replace("\n", ""))

    def test_timeline_total_notes_what_is_still_in_scope_when_it_differs(self):
        counts = {"original_completed": 2, "original_not_completed": 1, "extra_completed": 1,
                  "extra_not_completed": 0}
        points = {"original_completed": 5, "original_not_completed": 2, "extra_completed": 1,
                  "extra_not_completed": 0}
        table = report(commitment_breakdown_counts=counts,
                       commitment_breakdown_points=points).timeline_table()
        self.assertIn(
            "<b>3 stories / 6 pts (still in scope: 2 stories / 5 pts)</b>", table)

    def test_epic_table(self):
        table = report().epic_table()
        self.assertIn(f'<td><a href="{BASE}/browse/PROJ-100">PROJ-100: Login &lt;beta&gt;</a></td>'
                      "<td>3/5</td><td>6/10</td><td>–</td><td>–</td>", table.replace("\n", ""))
        self.assertIn("<td>(no epic)</td><td>0/0</td><td>0/0</td><td>1/1</td><td>1/1</td>",
                      table.replace("\n", ""))
        self.assertIn(
            f'Most of <a href="{BASE}/browse/PROJ-100">PROJ-100</a> shipped.', table)


class ProseTest(unittest.TestCase):
    def test_scope_summary(self):
        text = report().scope_summary()
        self.assertTrue(text.startswith("**5 issues (9 points)** are in scope: 4 completed (7 points) and "
                                        "1 carried over (2 points). The net removals include 1 incomplete "
                                        "story (2 points) genuinely descoped."))
        self.assertIn(
            "The Completed columns include 1 story (1 point) already Done when it entered", text)
        self.assertIn(
            f"[PROJ-5]({BASE}/browse/PROJ-5): 2 points closed as non-delivery", text)
        self.assertNotIn("housekeeping", text)

    def test_scope_summary_of_an_active_sprint_with_removals_done(self):
        summary = {"descoped_incomplete": totals(0, 0), "already_done_on_arrival": totals(2, 3),
                   "completed_before_removal": totals(1, 1), "total": totals(3, 4)}
        text = report(sprint_status="active",
                      removed_summary=summary).scope_summary()
        self.assertIn("1 still open (2 points)", text)
        self.assertIn("2 stories (3 points) were already Done when they entered the sprint and later removed "
                      "as housekeeping.", text)
        self.assertIn(
            "1 story (1 point) was removed after completion.", text)

    def test_scope_summary_names_issues_left_out_of_the_jira_comparison(self):
        self.assertNotIn("Historical membership", report().scope_summary())
        text = report(membership_cross_check_excluded_keys=[
                      "PROJ-6"]).scope_summary()
        self.assertIn(
            f"Historical membership for [PROJ-6]({BASE}/browse/PROJ-6) is reconstructed", text)

    def test_removed_work_already_done_is_not_in_the_completed_columns(self):
        data = sprint_data()
        data["already_done_on_arrival"]["issues"][0]["stillInSprint"] = False
        self.assertNotIn("The Completed columns include",
                         Report(data, CONTENT).scope_summary())

    def test_scope_notes_for_a_leave_and_return(self):
        data = sprint_data()
        data["scope_timeline"][2]["readded_keys"] = ["PROJ-6"]
        self.assertEqual(Report(data, CONTENT).scope_notes(), [
            f"[PROJ-6]({BASE}/browse/PROJ-6) left the sprint on 04/03/2026 and returned on 05/03/2026; "
            "both movements are in the timeline totals."])

    def test_scope_notes_pair_repeated_cycles(self):
        data = sprint_data()
        data["scope_timeline"][2]["readded_keys"] = ["PROJ-6"]
        data["scope_timeline"][4:4] = [row("2026-03-07", departure=["PROJ-6"]),
                                       row("2026-03-08", readded=["PROJ-6"])]
        notes = Report(data, CONTENT).scope_notes()
        self.assertEqual(len(notes), 2)
        self.assertIn(
            "left the sprint on 04/03/2026 and returned on 05/03/2026", notes[0])
        self.assertIn(
            "left the sprint on 07/03/2026 and returned on 08/03/2026", notes[1])

    def test_health_notes(self):
        notes = report().health_notes()
        self.assertEqual(notes[0], "Planning baseline: 5 stories / 10 pts were in the sprint when it started "
                                   "on 02/03/2026, 1 story / 1 pt of them already Done, leaving 4 stories / 9 pts "
                                   "to do (the burndown's baseline).")
        data = sprint_data()
        data["issues"][3]["startState"]["done"] = False
        self.assertEqual(Report(data, CONTENT).health_notes()[0],
                         "Planning baseline: 5 stories / 10 pts were in the sprint when it started on 02/03/2026.")
        self.assertEqual(notes[1], "Sprint target completion: 2/4 original-commitment tickets closed (50%); "
                                   "excludes 1 ticket already closed when the sprint started (PROJ-4).")
        self.assertEqual(notes[2], "Goal discipline: Jira recorded the sprint goal as “Ship login”; the report "
                                   "verdict is Partially met.")
        self.assertIn("Scope added after commitment: 1 story / 1 pt, equal to 20% of the initial story count "
                      "and 10% of its points.", notes)
        self.assertTrue(notes[-1].startswith("Unfinished-work shape: 1 story / 2 pts carried over; status mix "
                                             "is 1 In Progress (2 pts); blocker candidates are PROJ-2."))

    def test_health_notes_without_a_goal_or_with_a_multi_line_one(self):
        self.assertIn("no sprint goal was set in Jira",
                      report(sprint_goal="").health_notes()[2])
        self.assertIn("“Ship login / Fix search”",
                      report(sprint_goal="- Ship login\n\n- Fix search").health_notes()[2])

    def test_days_left(self):
        cases = [
            ("closed", {}, " with ", ""),
            ("active", {"sprint_status": "active", "today": "2026-03-10"}, " with ",
             " with 3 calendar days remaining"),
            ("overdue", {"sprint_status": "active", "today": "2026-03-15"}, ", ",
             ", the recorded end date 2 calendar days overdue"),
        ]
        for name, changes, prefix, expected in cases:
            with self.subTest(name):
                self.assertEqual(report(**changes).days_left(prefix), expected)


class BuildTest(unittest.TestCase):
    def test_sections_in_order(self):
        md = report().build()
        headings = [line for line in md.splitlines() if line.startswith("#")]
        self.assertEqual(headings, ["# Sprint Summary: Sprint 7", "## Scope Timeline",
                                    "## Delivery by Epic", "## Key Achievements", "## Blockers & Risks",
                                    "## Notes for Sprint Retro", "### Sprint Health Data"])
        self.assertIn("| Dates | 02/03/2026–13/03/2026 |", md)
        self.assertIn("| Goal outcome | Partially met |", md)
        self.assertIn(
            f"[PROJ-3]({BASE}/browse/PROJ-3) was added for the demo.", md)
        self.assertTrue(md.endswith("\n") and not md.endswith("\n\n"))

    def test_active_sprint_and_late_close(self):
        md = report(sprint_status="active", today="2026-03-10").build()
        self.assertIn(
            "This is a mid-sprint snapshot as at 10/03/2026, with 3 calendar days remaining.", md)
        md = report(sprint_complete_date="2026-03-16", sprint_goal="").build()
        self.assertIn(
            "| Dates | 02/03/2026–13/03/2026 (completed 16/03/2026) |", md)
        self.assertIn(
            "| Goal | *No goal was set in Jira for this sprint* |", md)

    def test_retro_discussion_points_only_when_given(self):
        r = report()
        self.assertNotIn("### Discussion Points", r.build())
        r.content["retro_notes"] = ["Why did PROJ-2 stall?"]
        self.assertIn("### Discussion Points\n\n- Why did", r.build())


class ValidateContentTest(unittest.TestCase):
    def assert_invalid(self, expected, **changes):
        content = {**copy.deepcopy(CONTENT), **changes}
        with self.assertRaises(SystemExit) as raised:
            make_report.validate_content(content, sprint_data())
        self.assertIn(expected, str(raised.exception))

    def test_valid(self):
        make_report.validate_content(copy.deepcopy(CONTENT), sprint_data())

    def test_invalid(self):
        cases = [
            ("key_achievements must be a list of 1-2 non-empty strings",
             {"key_achievements": []}),
            ("blockers_risks must be a list of 1-2 non-empty strings",
             {"blockers_risks": ["a", "b", "c"]}),
            ("retro_notes must be a list of 0-3 non-empty strings",
             {"retro_notes": [" "]}),
            ("scope_notes must be a list of 0+ non-empty strings",
             {"scope_notes": "text"}),
            ("goal_verdict must be a non-empty string", {"goal_verdict": ""}),
            ("delivery_commentary must be a non-empty string",
             {"delivery_commentary": None}),
            ("epic_commentary must map each epic key to a sentence",
             {"epic_commentary": []}),
            (f"epic_commentary is missing: {NO_EPIC}", {
             "epic_commentary": {"PROJ-100": "x"}}),
        ]
        for expected, changes in cases:
            with self.subTest(expected):
                self.assert_invalid(expected, **changes)


if __name__ == "__main__":
    unittest.main()
