# Unit tests for skills/agentic-manager-jira-sprint-report/scripts/check_report.py.
# Run with: python3 tests/run.py agentic-manager-jira-sprint-report
#
# Each test renders the report of report_fixture.py's sprint with make_report,
# breaks one thing in it, and checks that the matching check fails.
import contextlib
import copy
import io
import os
import sys
import tempfile
import unittest

# tests/<skill>/ mirrors skills/<skill>/.
TEST_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(TEST_DIR))
sys.path.insert(0, os.path.join(REPO_ROOT, "skills",
                os.path.basename(TEST_DIR), "scripts"))
import check_report  # noqa: E402
from common import CHART_FILES  # noqa: E402
from make_report import Report  # noqa: E402

sys.path.insert(0, TEST_DIR)
from report_fixture import BASE, CONTENT, ev, ticket, sprint_data  # noqa: E402


class HelpersTest(unittest.TestCase):
    def test_html_parsing(self):
        table = ("<table><tr><th>Date</th><th>Events</th><th>End of day</th></tr>"
                 "<tr><td>a<br>b</td><td>c</td><td>d</td></tr></table>")
        self.assertEqual(check_report.html_tables(f"x {table} y"), [table])
        self.assertEqual([check_report.cells_of(r) for r in check_report.rows_of(table)],
                         [["Date", "Events", "End of day"], ["a<br>b", "c", "d"]])
        self.assertEqual(check_report.strip_tags("<b>a</b><br>b"), "a  b")
        self.assertEqual(check_report.table_kind(table), "timeline")
        self.assertIsNone(check_report.table_kind(
            "<table><tr><th>Other</th></tr></table>"))

    def test_checker(self):
        c = check_report.Checker()
        self.assertTrue(c.check(True, "a", "fine"))
        self.assertFalse(c.check(False, "b", "broken"))
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(c.report(), 1)
        self.assertIn("  ok    a: fine\n  FAIL  b: broken\n", out.getvalue())
        self.assertIn("1 check(s) failed", out.getvalue())


class ChecksTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        for name in CHART_FILES.values():
            open(os.path.join(self.tmp.name, name), "w").close()
        self.data = sprint_data()
        self.md = Report(self.data, copy.deepcopy(CONTENT)).build()

    def failures(self, md=None, data=None):
        return check_report.run_checks(md or self.md, data or self.data, self.tmp.name).failures

    def assert_fails(self, check, md):
        failures = self.failures(md)
        self.assertTrue(any(f.startswith(f"{check}: ") for f in failures),
                        f"no {check!r} failure in {failures}")

    def replace(self, old, new):
        """The report with `old`, which must appear in it, replaced by `new`."""
        self.assertIn(old, self.md)
        return self.md.replace(old, new, 1)

    def test_generated_reports_pass(self):
        cases = {"closed": ({}, "Partially met"),
                 "active": ({"sprint_status": "active", "today": "2026-03-10", "sprint_complete_date": None},
                            "At risk"),
                 "no goal": ({"sprint_goal": ""}, "No goal set in Jira for this sprint"),
                 "no previous sprint": ({"previous_sprint": None}, "Partially met")}
        for name, (changes, verdict) in cases.items():
            with self.subTest(name):
                data = sprint_data(**changes)
                md = Report(data, {**copy.deepcopy(CONTENT),
                            "goal_verdict": verdict}).build()
                self.assertEqual(self.failures(md, data), [])

    def test_source_labels_are_decoded(self):
        for name in ("Release | 6", "Release\n6", "Release PROJ-100"):
            with self.subTest(name=name):
                data = sprint_data(previous_sprint={"name": name})
                check = check_report.Checker()
                check_report.check_header(
                    check, Report(data, CONTENT).build(), data)
                self.assertEqual(check.failures, [])

    def test_timeline_orders_instants_across_offsets(self):
        events = [ev(2, "committed", 2),
                  dict(ev(6, "completed", 2, done=True),
                       at="2026-03-06T09:30:00+0100"),
                  dict(ev(6, "reopened", 2), at="2026-03-06T09:00:00+0000")]
        data = sprint_data(
            spells=[ticket("PROJ-1", events, "not_completed", status="In Progress")])
        table = Report(data, CONTENT).timeline_table()
        self.assertLess(table.index(">Completed</span>"),
                        table.index(">Reopened</span>"))
        for rendered, valid in ((table, True), (table.replace(">Completed</span>", ">TEMP</span>")
                                                .replace(">Reopened</span>", ">Completed</span>")
                                                .replace(">TEMP</span>", ">Reopened</span>"), False)):
            with self.subTest(valid=valid):
                check = check_report.Checker()
                check_report.check_timeline(check, rendered, data)
                self.assertEqual(not check.failures, valid)

    def test_overdue_commentary_uses_current_outcomes(self):
        data = sprint_data(sprint_status="active", sprint_complete_date=None, today="2026-03-16",
                           as_of_instant="2026-03-16T12:00:00Z", spells=[ticket("PROJ-1", [
                               ev(2, "committed", 2), ev(15, "completed", 2, done=True)], "completed")])
        self.assertEqual(data["burndown"][-1]["total_stories"], 1)
        md = Report(data, CONTENT).build()
        self.assertIn("Nothing is open", md)
        for rendered, valid in ((md, True), (md.replace("Nothing is open", "1 ticket (2 pts) is open"), False)):
            with self.subTest(valid=valid):
                check = check_report.Checker()
                check_report.check_commentary(check, rendered, data)
                self.assertEqual(not check.failures, valid, check.failures)

    def test_copied_jira_words_do_not_exempt_generated_prose(self):
        source = "One story — issues closed on 2026-03-01 at 50.5%"
        data = sprint_data(sprint_name=source, sprint_goal=source,
                           previous_sprint={"name": source})
        data["epics"][0]["name"] = source
        md = Report(data, CONTENT).build()
        self.assertEqual(self.failures(md, data), [])
        # The same words outside source slots still fail.
        changed = md.replace("Login shipped: staff", source + ": staff")
        failures = self.failures(changed, data)
        for check in ("vocabulary:", "em dashes:", "dates:"):
            self.assertTrue(any(f.startswith(check)
                            for f in failures), failures)

    def test_source_fields_still_require_ticket_links(self):
        data = sprint_data(sprint_name="Sprint PROJ-90", sprint_goal="Deliver PROJ-91",
                           previous_sprint={"name": "Sprint PROJ-92"})
        md = Report(data, CONTENT).build()
        for key in ("PROJ-91", "PROJ-92", "PROJ-100"):
            with self.subTest(key=key):
                check = check_report.Checker()
                check_report.check_style(check, md)
                self.assertEqual(check.failures, [])
                if key == "PROJ-100":
                    changed = md.replace(f'<a href="{BASE}/browse/{key}">{key}: Login &lt;beta&gt;</a>',
                                         f'{key}: Login &lt;beta&gt;')
                else:
                    changed = md.replace(f"[{key}]({BASE}/browse/{key})", key)
                check = check_report.Checker()
                check_report.check_style(check, changed)
                self.assertTrue(any(f.startswith("links:")
                                for f in check.failures), check.failures)

    def test_historical_estimates_are_checked_by_phrase(self):
        scenarios = [
            ([ticket("PROJ-1", [ev(2, "committed", 2, done=True),
                                ev(3, "reestimated", 5, done=True, fromPoints=2)], "completed")],
             "PROJ-1) (2 pts) was already Done", "PROJ-1) (5 pts) was already Done"),
            ([ticket("PROJ-1", [ev(2, "committed", 2), ev(4, "removed", 2)], "removed"),
              ticket("PROJ-1", [ev(5, "joined", 5)], "not_completed", scope="extra")],
             "PROJ-1) (2 pts) was descoped", "PROJ-1) (5 pts) was descoped"),
        ]
        for spells, old, wrong in scenarios:
            with self.subTest(old=old):
                data = sprint_data(spells=spells)
                content = {
                    **CONTENT, "retro_notes": ["PROJ-1 (5 pts) changed: was it ready?"]}
                md = Report(data, content).build()
                for rendered, valid in ((md, True), (md.replace(old, wrong), False),
                                        (md.replace("(5 pts) changed", "(2 pts) changed"), False)):
                    check = check_report.Checker()
                    check_report.check_vocabulary(check, rendered, data)
                    self.assertEqual(not check.failures, valid, check.failures)

    def test_excluded_membership_must_be_stated(self):
        data = sprint_data(membership_cross_check_excluded_keys=["PROJ-6"])
        md = Report(data, copy.deepcopy(CONTENT)).build()
        self.assertEqual(self.failures(md, data), [])
        self.assertIn("commentary: states the membership cross-check limitation",
                      self.failures(md.replace("is reconstructed from changelogs", "is assumed"), data))

    def test_excluded_ticket_without_a_spell_is_allowed_only_in_membership_caveat(self):
        data = sprint_data(membership_cross_check_excluded_keys=["PROJ-99"])
        md = Report(data, CONTENT).build()
        for rendered, valid in ((md, True), (md.replace("PROJ-99", "PROJ-98"), False),
                                (md.replace("At the close,", "At the close, PROJ-99,"), False)):
            with self.subTest(valid=valid, rendered=rendered):
                check = check_report.Checker()
                check_report.check_commentary(check, rendered, data)
                self.assertEqual(not check.failures, valid, check.failures)

    def test_commentary_must_match_the_spells(self):
        cases = [
            ("2 tickets (4 pts) were descoped", "2 tickets (5 pts) were descoped",
             "commentary: states 2 tickets (4 pts) descoped"),
            (" and [PROJ-2](https://acme.test/browse/PROJ-2) (2 pts) left the sprint and came back, counting as "
             "descoped and then as extra", "", "commentary: mentions left and came back"),
            ("Of the 5 tickets (9 pts) in the commitment", "Of the 5 tickets (10 pts) in the commitment",
             "commentary: states the commitment, 5 tickets (9 pts)"),
            ("PROJ-5](https://acme.test/browse/PROJ-5) (2 pts) was resolved",
             "PROJ-9](https://acme.test/browse/PROJ-9) (2 pts) was resolved",
             "commentary: names only tickets of the sprint"),
            ("1 ticket (2 pts) was not completed", "1 ticket (3 pts) was not completed",
             "commentary: states what is still open, 1 ticket (2 pts)"),
            ("At the close,", "At the close, after a long and eventful sprint full of changes that the team handled "
             "with care, attention and a great deal of patience across many working days and meetings, " * 2,
             "commentary: at most 100 words before its caveats"),
        ]
        for old, new, expected in cases:
            with self.subTest(expected):
                self.assertIn(old, self.md)
                failures = self.failures(self.md.replace(old, new, 1))
                self.assertTrue(any(f.startswith(expected)
                                for f in failures), failures)
        data = sprint_data()
        data["outcome_breakdown_counts"]["new_removed"] = 0
        self.assertIn("figures: carry-over and new work add up to the original commitment's removed",
                      self.failures(data=data))

    def test_each_check_catches_its_breakage(self):
        proj_1 = f'<a href="{BASE}/browse/PROJ-1">PROJ-1</a>'
        cases = [
            ("timeline", ">Descoped</span>", ">Removed</span>"),
            ("timeline", ">Descoped</span></td></tr>\n<tr><td style=\"white-space:nowrap\"><a href=\"https://acme.test/browse/PROJ-6\">",
             ">Completed</span></td></tr>\n<tr><td style=\"white-space:nowrap\"><a href=\"https://acme.test/browse/PROJ-6\">"),
            ("timeline", ">Re-estimated: 2 → 3 pts</span>",
             ">Re-estimated: 3 pts</span>"),
            ("timeline", '<a href="https://acme.test/browse/PROJ-6">PROJ-6</a> (2 pts)',
             '<a href="https://acme.test/browse/PROJ-6">PROJ-6</a> (3 pts)'),
            ("timeline", "<br>1 ticket (2 pts) with extra",
             "<br>1 ticket (3 pts) with extra"),
            ("timeline", "<b>Commitment:</b><br>5 tickets (9 pts)",
             "<b>Commitment:</b><br>5 tickets (10 pts)"),
            ("timeline", ">03/03/2026</td>", ">07/03/2026</td>"),
            ("cell shapes", '<td rowspan="5" style', '<td rowspan="4" style'),
            ("epics", "<td>3/5 tickets (6/10 pts)</td>",
             "<td>3/6 tickets (6/10 pts)</td>"),
            ("epics", "<b>Not completed:</b>", "<b>Open:</b>"),
            ("epics", "<br><b>Descoped:</b> Sign-in audit logging &amp; the admin screen were dropped.", ""),
            ("epics", "Staff can sign in with a password.",
             "Staff can sign in with a password. They can also reset it by email."),
            ("epics", "Staff can sign in with a password.",
             "Staff can sign in with a password, " + "and more " * 20),
            ("epics", "Staff can sign in with a password.",
             "Staff can sign in with a password (PROJ-1)."),
            ("retro", "should it have stayed out?", "it should have stayed out."),
            ("retro", "- [PROJ-1](https://acme.test/browse/PROJ-1) (3 pts) grew during the sprint: was it refined enough?",
             "- To be written?"),
            ("ai labels",
             "## Key Achievements [AI Generated]", "## Key Achievements"),
            ("ai labels",
             "## Notes for Sprint Retro [AI Generated]", "## Notes for Sprint Retro"),
            ("ai labels", "Commentary [AI Generated]</th>", "Commentary</th>"),
            ("header", "| Goal outcome [AI Generated] |", "| Goal outcome |"),
            ("retro", "should it have stayed out?\n",
             "should it have stayed out?\n\nA closing remark.\n"),
            ("summaries", "Login shipped: staff", "Login shipped (PROJ-1): staff"),
            ("summaries", "Login shipped: staff",
             "Login shipped" + " and more" * 40 + ": staff"),
            ("summaries", "Nothing from the commitment",
             "- Nothing from the commitment"),
            ("images",
             "## Scope Timeline\n\n![Sprint burndown](burndown.svg)", "## Scope Timeline"),
            ("em dashes", "Partially met", "Partially met — mostly"),
            ("dates", "02/03/2026–", "2026-03-02–"),
            ("header", "| Carried over from Sprint 6 | 1 ticket \\| 20% of commitment",
             "| Carried over from Sprint 6 | 1 ticket \\| 25% of commitment"),
            ("header", "(2 pts \\| 20%)", "(3 pts \\| 20%)"),
            ("header", "| Carried over from Sprint 6 |",
             "| Carried over from Sprint 5 |"),
            ("header", "3/5 tickets (6/10 pts) completed",
             "3/5 tickets (6/11 pts) completed"),
            ("header", "3/5 tickets (6/10 pts) completed", "3/5 tickets completed"),
            ("header", "| 60%, 3/5 tickets", "| 3/5 tickets"),
            ("header", "| 60%, 3/5 tickets", "| 59%, 3/5 tickets"),
            ("header", "| Goal outcome [AI Generated] | Partially met |\n",
             "| Goal outcome [AI Generated] | Partially met |\n| Reporting timezone | Europe/London |\n"),
            ("header", "| Goal outcome [AI Generated] | Partially met |",
             "| Goal outcome [AI Generated] | Mostly met |"),
            ("header", "| Goal | Ship login |", "| Goal | Ship it |"),
            ("header", "| Dates | 02/03/2026–13/03/2026 |",
             "| Dates | 02/03/2026 to 13/03/2026 |"),
            ("header", "| Sprint target completion |", "| Target |"),
            ("header", "| Goal outcome [AI Generated] | Partially met |\n",
             "| Goal outcome [AI Generated] | Partially met |\n| Owner | Alex |\n"),
            ("header", "| Field | Detail |", "| Item | Detail |"),
            ("links", "Login shipped", "PROJ-9 and login shipped"),
            ("vocabulary", "Login shipped", "The login story shipped"),
            ("vocabulary", "Login shipped", "Login issues shipped"),
            ("vocabulary", "Login shipped", "Login points shipped"),
            ("vocabulary", "Login shipped", "Two logins shipped"),
            ("vocabulary", "Login shipped", "Login closed and shipped"),
            ("vocabulary", "Login shipped", "Login shipped at 50.5%"),
            ("vocabulary", "Login shipped", "Login shipped 3/5"),
            ("vocabulary", "Login shipped", "Login shipped 3 tickets / 4 pts"),
            ("vocabulary", "Login shipped", "**Login** shipped"),
            ("vocabulary", "[PROJ-1](https://acme.test/browse/PROJ-1) (3 pts)",
             "[PROJ-1](https://acme.test/browse/PROJ-1)"),
            ("vocabulary", "[PROJ-1](https://acme.test/browse/PROJ-1) (3 pts)",
             "[PROJ-1](https://acme.test/browse/PROJ-1) (5 pts)"),
            ("vocabulary", "were descoped ([PROJ-2](https://acme.test/browse/PROJ-2), "
                           "[PROJ-6](https://acme.test/browse/PROJ-6))",
             "were descoped ([PROJ-6](https://acme.test/browse/PROJ-6), [PROJ-2](https://acme.test/browse/PROJ-2))"),
        ]
        for check, old, new in cases:
            with self.subTest(check=check, old=old):
                self.assert_fails(check, self.replace(old, new))

    def test_charts_must_chart_the_target_pool(self):
        data = sprint_data()
        data["outcome_breakdown_counts"]["original_removed"] = 0
        self.assertTrue(any(f.startswith("header: the charts' original commitment")
                            for f in self.failures(data=data)))

    def test_data_that_drifts_from_the_events_fails(self):
        cases = [
            ("an outcome", lambda d: d["spells"][0].update(outcome="removed"),
             "model: PROJ-1 ends completed, as its events give"),
            ("a latest estimate", lambda d: d["spells"][0].update(points=2),
             "model: PROJ-1 ends completed, as its events give"),
            ("a reopening that doesn't reopen", lambda d: d["spells"][4]["events"].append(
                {"at": "2026-03-06T10:00:00.000+0000", "date": "2026-03-06", "type": "reopened", "points": 1,
                 "done": True}), "model: PROJ-4 ends completed, as its events give"),
            ("an extra spell that ended descoped, still counted", lambda d: d["spells"][3].update(
                outcome="removed", events=d["spells"][3]["events"] + [
                    {"at": "2026-03-07T10:00:00.000+0000", "date": "2026-03-07", "type": "removed", "points": 1,
                     "done": True}]), "model: PROJ-3 ends removed, not counted, as its events give"),
            ("a second original spell", lambda d: d["spells"][2].update(scope="original", events=[
                dict(d["spells"][2]["events"][0], type="committed")]),
             "model: PROJ-2's events are well formed (committed)"),
            ("the burndown", lambda d: d["burndown"][0].update(committed=99),
             "model: the burndown on 02/03/2026 is the spells' open tickets and pts"),
            ("the baseline", lambda d: d.update(burndown_baseline=99),
             "model: the burndown starts at the whole commitment, 9"),
            ("the timeline", lambda d: d["timeline"][1]["events"].clear(),
             "model: the timeline holds exactly the spells' events"),
            ("the breakdown", lambda d: d["outcome_breakdown_points"].update(extra_completed=5),
             "model: the charts' extra completed is the counted spells' 1 ticket (5 pts)"),
        ]
        for name, breakage, expected in cases:
            with self.subTest(name):
                data = sprint_data()
                breakage(data)
                self.assertIn(expected, self.failures(data=data))

    def test_missing_chart(self):
        os.remove(os.path.join(self.tmp.name, CHART_FILES["burndown"]))
        self.assert_fails("images", self.md)

    def test_missing_tables_and_sections(self):
        failures = self.failures("# Sprint Summary\n\nNothing here.\n")
        for expected in ("timeline: table found", "epics: table found", "retro: section found"):
            self.assertIn(expected, failures)

    def test_missing_rows(self):
        cases = [(">04/03/2026</td>", ">05/04/2026</td>", "timeline: the days are the timeline's, in order (6)"),
                 (">PROJ-100: ", ">PROJ-101: ", "epics: PROJ-100 has a row")]
        for old, new, expected in cases:
            with self.subTest(expected):
                self.assertIn(expected, self.failures(self.replace(old, new)))

    def test_table_without_a_heading(self):
        md = "<table><tr><th>Epic</th><th>Commentary</th></tr></table>\n\n" + "Prose. " * 10
        c = check_report.Checker()
        check_report.check_framing(c, md)
        self.assertEqual(
            c.failures, ["headings: epics table has a heading above it"])

    def test_other_tables_are_not_framed(self):
        c = check_report.Checker()
        check_report.check_framing(c, "<table><tr><th>Field</th></tr></table>")
        self.assertEqual((c.failures, c.passes), ([], []))


if __name__ == "__main__":
    unittest.main()
