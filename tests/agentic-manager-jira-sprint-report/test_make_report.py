# Unit tests for skills/agentic-manager-jira-sprint-report/scripts/make_report.py.
# Run with: python3 tests/run.py agentic-manager-jira-sprint-report
#
# The sprint is described in report_fixture.py.
import copy
import os
import re
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
from report_fixture import BASE, CONTENT, ev, sprint_data, ticket  # noqa: E402


def report(**changes):
    return Report(sprint_data(**changes), copy.deepcopy(CONTENT))


class HelpersTest(unittest.TestCase):
    def test_were(self):
        self.assertEqual(
            (make_report.were(1), make_report.were(2)), ("was", "were"))

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

    def test_table_text_keeps_a_markdown_cell_on_one_line(self):
        self.assertEqual(report().table_text("a | b\nc"), "a \\| b c")


class TagsTest(unittest.TestCase):
    def test_tag(self):
        self.assertEqual(make_report.tag("removed"),
                         '<span style="background:#b5b2aa;color:#1a1a1a;border-radius:10px;padding:1px 7px;'
                         'margin:1px 3px 1px 0;font-size:90%;white-space:nowrap;display:inline-block">Descoped</span>')
        self.assertIn(">Re-estimated: 5 → 3</span>",
                      make_report.tag("reestimated", ": 5 → 3"))

    def test_event_tags(self):
        r = report()
        cases = [
            ({"type": "committed", "done": False}, ["Added"]),
            ({"type": "joined", "done": True}, ["Added", "Already done"]),
            ({"type": "reestimated", "fromPoints": None,
             "points": 3}, ["Re-estimated: – → 3 pts"]),
            ({"type": "reestimated", "fromPoints": 5,
             "points": 3}, ["Re-estimated: 5 → 3 pts"]),
            ({"type": "removed"}, ["Descoped"]),
            ({"type": "completed"}, ["Completed"]
             ), ({"type": "reopened"}, ["Reopened"]),
        ]
        for event, expected in cases:
            with self.subTest(event["type"]):
                self.assertEqual(re.findall(
                    r">([^<]+)</span>", r.tags(event)), expected)


class TablesTest(unittest.TestCase):
    def rows(self, table):
        return [" | ".join(" ".join(re.sub(r"<[^>]+>", " ", c).split())
                           for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.S))
                for row in re.findall(r"<tr>(.*?)</tr>", table, re.S)]

    def test_timeline_table(self):
        table = report().timeline_table()
        self.assertTrue(table.startswith('<table style="font-size:75%">'))
        self.assertEqual(self.rows(table), [
            "Date | Ticket | Events | End of day",
            "02/03/2026 (sprint start) | PROJ-1 (2 pts) | Added | Commitment: 5 tickets (9 pts) Open: 4 tickets "
            "(8 pts) of the commitment 4 tickets (8 pts) with extra",
            "PROJ-2 (2 pts) | Added", "PROJ-4 (1 pt) | Added Already done", "PROJ-5 (2 pts) | Added",
            "PROJ-6 (2 pts) | Added",
            "03/03/2026 | PROJ-1 (3 pts) | Re-estimated: 2 → 3 pts | Open: 4 tickets (9 pts) of the commitment "
            "4 tickets (9 pts) with extra",
            "04/03/2026 | PROJ-1 (3 pts) | Completed | Open: 1 ticket (2 pts) of the commitment 1 ticket (2 pts) "
            "with extra",
            "PROJ-2 (2 pts) | Descoped", "PROJ-6 (2 pts) | Descoped",
            "05/03/2026 | PROJ-2 (2 pts) | Added | Open: 0 tickets (0 pts) of the commitment 2 tickets (3 pts) "
            "with extra",
            "PROJ-3 (1 pt) | Added", "PROJ-5 (2 pts) | Completed",
            "06/03/2026 | PROJ-3 (1 pt) | Completed | Open: 0 tickets (0 pts) of the commitment 1 ticket (2 pts) "
            "with extra",
            "13/03/2026 (sprint closed) | – | Open: 0 tickets (0 pts) of the commitment 1 ticket (2 pts) with extra"])
        self.assertIn(
            '<td rowspan="5" style="vertical-align:top">02/03/2026<br>(sprint start)</td>', table)
        self.assertIn('<td colspan="2">–</td>', table)

    def test_tags_follow_the_events_order(self):
        data = sprint_data()
        data["spells"][4] = ticket("PROJ-4", [ev(2, "committed", 1, done=True), ev(6, "reopened", 1),
                                              ev(6, "completed", 1, done=True)], "completed")
        data["spells"][4]["events"][2]["at"] = "2026-03-06T11:00:00.000+0000"
        table = Report(sprint_data(
            spells=data["spells"]), CONTENT).timeline_table()
        self.assertIn("06/03/2026 | PROJ-3 (1 pt) | Completed |",
                      "\n".join(self.rows(table)))
        self.assertIn("PROJ-4 (1 pt) | Reopened Completed", self.rows(table))

    def test_days_past_the_burndown_have_no_figures(self):
        # An active sprint past its end: the burndown stops at the end date.
        data = sprint_data(sprint_status="active", today="2026-03-16")
        rows = self.rows(Report(data, CONTENT).timeline_table())
        self.assertEqual(rows[-1], "16/03/2026 (today) | – | –")

    def test_epic_table(self):
        table = report().epic_table()
        self.assertIn(f'<td><a href="{BASE}/browse/PROJ-100">PROJ-100: Login &lt;beta&gt;</a></td>'
                      "<td>3/5 tickets (6/10 pts)</td><td>0/1 ticket (0/2 pts)</td>", table.replace("\n", ""))
        self.assertIn(
            "<td>(no epic)</td><td>–</td><td>1/1 ticket (1/1 pts)</td>", table.replace("\n", ""))
        self.assertIn("<th style=\"width:14%\">Commitment</th>", table)

    def test_epic_commentary(self):
        # A labelled sentence per group with tickets to describe, in order,
        # escaped; "Open" for not completed work while the sprint runs; "–"
        # for an epic with nothing to describe.
        closed = report().epic_table().replace("\n", "")
        self.assertIn("<td><b>Completed:</b> Staff can sign in with a password.<br>"
                      "<b>Not completed:</b> Remembering the last sign-in method is still in progress.<br>"
                      "<b>Descoped:</b> Sign-in audit logging &amp; the admin screen were dropped.</td>", closed)
        self.assertIn(
            "<td><b>Completed:</b> The export now handles empty files.</td>", closed)
        self.assertIn("<b>Open:</b> Remembering",
                      report(sprint_status="active", today="2026-03-10").epic_table())
        spells = sprint_data()["spells"]
        spells[2]["status"] = "In Review"  # PROJ-2's extra spell
        review = sprint_data(spells=spells)
        content = copy.deepcopy(CONTENT)
        content["epic_commentary"]["PROJ-100"]["in_review"] = content["epic_commentary"]["PROJ-100"].pop(
            "not_completed")
        self.assertIn("<b>In review:</b> Remembering",
                      Report(review, content).epic_table())
        only_left_out = sprint_data(spells=[s for s in sprint_data()[
                                    "spells"] if s["key"] in ("PROJ-4", "PROJ-5")])
        self.assertIn("<td>–</td></tr>", Report(only_left_out, {**CONTENT, "epic_commentary": {}}).epic_table()
                      .replace("\n", ""))


class ProseTest(unittest.TestCase):
    def plain(self, text):
        return re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)

    def test_commentary(self):
        self.assertEqual(self.plain(report().commentary()),
                         "Of the 5 tickets (9 pts) in the commitment, PROJ-4 (1 pt) was already Done at the start, and "
                         "2 tickets (4 pts) were descoped (PROJ-2, PROJ-6). 2 tickets (3 pts) were added as extra "
                         "(PROJ-2, PROJ-3). PROJ-1 (2 → 3 pts) was re-estimated and PROJ-2 (2 pts) left the "
                         "sprint and came back, counting as descoped and then as extra. At the close, 1 ticket (2 pts) "
                         "was not completed, all of it extra. PROJ-5 (2 pts) was resolved as Duplicate or Won't Do and "
                         "counts as completed.")
        self.assertIn(
            f"[PROJ-4]({BASE}/browse/PROJ-4) (1 pt)", report().commentary())
        self.assertIn("1 ticket (2 pts) is open, all of it extra, with 3 days left.",
                      self.plain(report(sprint_status="active", today="2026-03-10").commentary()))

    def test_commentary_reestimates(self):
        spells = [ticket("PROJ-1", [ev(2, "committed", 5), ev(3, "reestimated", 3, fromPoints=5)], "not_completed",
                         status="To Do"),
                  ticket("PROJ-2", [ev(2, "committed", None), ev(4, "reestimated", 5, fromPoints=None)],
                         "not_completed", status="To Do")]
        one = self.plain(
            Report(sprint_data(spells=spells[:1]), CONTENT).commentary())
        self.assertIn("PROJ-1 (5 → 3 pts) was re-estimated", one)
        both = self.plain(
            Report(sprint_data(spells=spells), CONTENT).commentary())
        self.assertIn(
            "2 tickets (5 → 8 pts) were re-estimated (PROJ-1, PROJ-2)", both)

    def test_cleared_estimate_stays_unknown(self):
        spells = [ticket("PROJ-1", [ev(2, "committed", 2), ev(3, "reestimated", None, fromPoints=2)],
                         "not_completed", status="To Do")]
        text = self.plain(
            Report(sprint_data(spells=spells), CONTENT).commentary())
        self.assertIn("PROJ-1 (2 → – pts) was re-estimated", text)

    def test_commentary_word_limit_with_all_departures(self):
        spells = sprint_data()["spells"] + [
            ticket("PROJ-7", [ev(2, "committed", 1, done=True),
                   ev(5, "reopened", 1)], "not_completed"),
            ticket("PROJ-8", [ev(3, "joined", 1),
                   ev(4, "removed", 1)], "removed", scope="extra"),
            ticket("PROJ-9", [ev(3, "joined", None)], "not_completed", scope="extra")]
        data = sprint_data(
            spells=spells, sprint_status="active", today="2026-03-10")
        # Check the core without the non-delivery caveat.
        r = Report(data, CONTENT)
        core = r.commentary()
        for caveat in r.commentary_caveats():
            core = core.replace(caveat, "")
        self.assertLessEqual(
            len(make_report.plain_words(core)), make_report.COMMENTARY_WORDS)
        for phrase in ("already Done", "were descoped", "added as extra", "descoped again",
                       "was reopened", "re-estimated", "left the sprint and came back", "unestimated"):
            self.assertIn(phrase, core)

    def test_commentary_of_an_ideal_sprint(self):
        spells = [ticket("PROJ-1", [ev(2, "committed", 3),
                         ev(4, "completed", 3, done=True)], "completed")]
        self.assertEqual(self.plain(Report(sprint_data(spells=spells), CONTENT).commentary()),
                         "The 1 ticket (3 pts) in the commitment stayed in the sprint. Everything in the sprint was "
                         "completed by the close.")

    def test_commentary_counts_instead_of_naming_when_too_long(self):
        spells = [ticket("PROJ-1", [ev(2, "committed", 1)],
                         "not_completed", status="To Do")]
        for n in range(10, 40):
            spells.append(ticket(
                f"PROJ-{n}", [ev(3, "joined", 1)], "not_completed", status="To Do", scope="extra"))
            spells.append(ticket(f"PROJ-{n + 100}", [ev(3, "joined", 1), ev(4, "removed", 1)], "removed",
                                 status="To Do", scope="extra"))
        for n in range(40, 44):
            spells.append(ticket(f"PROJ-{n}", [ev(2, "committed", 1, done=True), ev(5, "reopened", 1)],
                                 "not_completed", status="To Do"))
        few = self.plain(
            Report(sprint_data(spells=spells[:5]), CONTENT).commentary())
        self.assertIn(
            "2 tickets (2 pts) were added as extra (PROJ-10, PROJ-11)", few)
        self.assertIn(
            "were added and descoped again (PROJ-110, PROJ-111), so they don't count", few)
        many = self.plain(
            Report(sprint_data(spells=spells), CONTENT).commentary())
        self.assertNotIn("PROJ-1", many)
        self.assertIn("30 tickets (30 pts) were added as extra; 30 tickets (30 pts) were added and descoped again",
                      many)
        self.assertIn("4 tickets (4 pts) were reopened", many)
        self.assertLessEqual(
            len(make_report.plain_words(many)), make_report.COMMENTARY_WORDS)

    def test_commentary_caveats_are_never_cut(self):
        cases = [(["PROJ-6"], "The membership of PROJ-6 (2 pts) is reconstructed from changelogs, as later sprint "
                              "moves prevent checking it against Jira."),
                 (["PROJ-1", "PROJ-6"], "The membership of 2 tickets (5 pts) is reconstructed from changelogs "
                                        "(PROJ-1, PROJ-6), as later sprint moves prevent checking it against Jira.")]
        for keys, expected in cases:
            with self.subTest(keys=keys):
                text = self.plain(
                    report(membership_cross_check_excluded_keys=keys).commentary())
                self.assertTrue(text.endswith(expected), text)

    def test_days_left(self):
        cases = [
            ("closed", {}, " with ", ""),
            ("active", {"sprint_status": "active",
             "today": "2026-03-10"}, " with ", " with 3 days left"),
            ("last day", {"sprint_status": "active",
             "today": "2026-03-13"}, " with ", " with no days left"),
            ("overdue", {"sprint_status": "active", "today": "2026-03-15"},
             ", ", ", 2 days past the end date"),
        ]
        for name, changes, prefix, expected in cases:
            with self.subTest(name):
                self.assertEqual(report(**changes).days_left(prefix), expected)


class BuildTest(unittest.TestCase):
    def test_sections_in_order(self):
        md = report().build()
        headings = [line for line in md.splitlines() if line.startswith("#")]
        self.assertEqual(headings, ["# Sprint Summary: Sprint 7", "## Scope Timeline",
                                    "## Delivery by Epic", "## Key Achievements [AI Generated]",
                                    "## Blockers & Risks [AI Generated]", "## Notes for Sprint Retro [AI Generated]"])
        self.assertIn("| Dates | 02/03/2026–13/03/2026 |", md)
        self.assertIn("| Goal outcome [AI Generated] | Partially met |", md)
        self.assertIn(
            "</table>\n\nOf the 5 tickets (9 pts) in the commitment,", md)
        self.assertIn(
            "## Key Achievements [AI Generated]\n\nLogin shipped: staff can sign in", md)
        self.assertIn(
            "## Notes for Sprint Retro [AI Generated]\n\n- [PROJ-1](https://acme.test/browse/PROJ-1) (3 pts) grew", md)
        self.assertTrue(md.endswith(
            "left the sprint and came back: should it have stayed out?\n"))

    def test_active_sprint_and_late_close(self):
        md = report(sprint_status="active", today="2026-03-10").build()
        self.assertIn('This is a mid-sprint snapshot as at 10/03/2026, with 3 days left. "Open" means not '
                      'completed yet.', md)
        md = report(sprint_complete_date="2026-03-16", sprint_goal="").build()
        self.assertIn(
            "| Dates | 02/03/2026–13/03/2026 (completed 16/03/2026) |", md)
        self.assertIn(
            "| Goal | *No goal was set in Jira for this sprint* |", md)

    def test_target_completion_row(self):
        cases = [
            ({}, "| Sprint target completion | 60%, 3/5 tickets (6/10 pts) completed |"),
            ({"sprint_status": "active", "today": "2026-03-10"},
             "| Sprint target completion | 60%, 3/5 tickets (6/10 pts) completed so far |"),
        ]
        for changes, expected in cases:
            with self.subTest(changes=changes):
                self.assertIn(expected, report(**changes).build())

    def test_carry_over_row(self):
        cases = [
            ({}, "| Carried over from Sprint 6 | 1 ticket \\| 20% of commitment (2 pts \\| 20%); 0 tickets (0 pts) "
                 "completed |"),
            ({"sprint_status": "active", "today": "2026-03-10"},
             "0 tickets (0 pts) completed so far |"),
            ({"previous_sprint": None},
             "| Carried over | None: no earlier sprint on this board |"),
        ]
        for changes, expected in cases:
            with self.subTest(changes=changes):
                self.assertIn(expected, report(**changes).build())

    def test_no_values_in_bold(self):
        md = report().build()
        bold = re.findall(r"\*\*(.+?)\*\*", md) + \
            re.findall(r"<b>(.+?)</b>", md)
        self.assertEqual({b for b in bold}, {"Commitment:",
                         "Open:", "Completed:", "Not completed:", "Descoped:"})


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
            ("key_achievements must be a non-empty string: one paragraph",
             {"key_achievements": ["A bullet."]}),
            ("blockers_risks must be a non-empty string: one paragraph",
             {"blockers_risks": " "}),
            ("retro_notes must be a list of 1-5 notes, each ending with a question",
             {"retro_notes": []}),
            ("retro_notes must be a list of 1-5",
             {"retro_notes": ["Why?"] * 6}),
            ("retro_notes must be a list of 1-5",
             {"retro_notes": ["A fact without a question."]}),
            ("scope_notes is no longer used", {
             "scope_notes": ["Added for the demo."]}),
            ('goal_verdict must be one of: "Fully met", "Partially met", "Not met"', {
             "goal_verdict": ""}),
            ("goal_verdict must be one of", {"goal_verdict": "Mostly met"}),
            ("delivery_commentary is no longer used", {
             "delivery_commentary": "Delivery centred on login."}),
            ("epic_commentary must map each epic key to its groups' sentences",
             {"epic_commentary": []}),
            ("epic_commentary.PROJ-100 must map each group to a sentence",
             {"epic_commentary": {"PROJ-100": "x", NO_EPIC: {"completed": "x"}}}),
            (f"epic_commentary.{NO_EPIC} needs a sentence for exactly these groups: completed",
             {"epic_commentary": {**CONTENT["epic_commentary"], NO_EPIC: {}}}),
            ("epic_commentary.PROJ-100 needs a sentence for exactly these groups: completed, not_completed, descoped",
             {"epic_commentary": {**CONTENT["epic_commentary"],
                                  "PROJ-100": {**CONTENT["epic_commentary"]["PROJ-100"], "in_review": "x"}}}),
            ("epic_commentary.PROJ-100 needs a sentence for exactly these groups",
             {"epic_commentary": {**CONTENT["epic_commentary"],
                                  "PROJ-100": {**CONTENT["epic_commentary"]["PROJ-100"], "descoped": " "}}}),
        ]
        for expected, changes in cases:
            with self.subTest(expected):
                self.assert_invalid(expected, **changes)


if __name__ == "__main__":
    unittest.main()
