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
from check_report import Checker, check_commentary  # noqa: E402
from common import CHART_FILES, NO_EPIC  # noqa: E402
from make_report import Report  # noqa: E402

sys.path.insert(0, TEST_DIR)
from report_fixture import BASE, CONTENT, ev, sprint_data, ticket  # noqa: E402

# The [AI Gen.] label as rendered: a small superscript after the title, so it
# reads as a note on the heading or label, not part of it.
AI = ' <sup style="font-size:0.6rem;font-weight:normal">[AI Gen.]</sup>'

ACTIVE = {"sprint_status": "active",
          "today": "2026-03-10", "sprint_complete_date": None}


def report(**changes):
    return Report(sprint_data(**changes), copy.deepcopy(CONTENT))


def plain(text):
    """Markdown links reduced to their text."""
    return re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)


class HelpersTest(unittest.TestCase):
    def test_helpers(self):
        r = report()
        cases = [
            ("were, one", make_report.were(1), "was"),
            ("were, many", make_report.were(2), "were"),
            # Em dashes in the agent's text become commas, at any depth.
            ("strip_em_dashes", make_report.strip_em_dashes({"a": ["x — y", 3], "b": "p—q"}),
             {"a": ["x, y", 3], "b": "p, q"}),
            ("md_key", r.md_key("PROJ-1"), f"[PROJ-1]({BASE}/browse/PROJ-1)"),
            ("html_key", r.html_key("PROJ-1"),
             f'<a href="{BASE}/browse/PROJ-1">PROJ-1</a>'),
            # Only Jira-shaped keys are linked.
            ("linkify", r.linkify("See PROJ-1 and a-2."),
             f"See [PROJ-1]({BASE}/browse/PROJ-1) and a-2."),
            # A Markdown table cell must stay on one line and not split on |.
            ("table_text", r.table_text("a | b\nc"), "a \\| b c"),
            # A tag sets both colours, so it reads the same in light and dark.
            ("tag", make_report.tag("removed"),
             '<span style="background:#b5b2aa;color:#1a1a1a;border-radius:10px;padding:1px 7px;'
             'margin:1px 3px 1px 0;font-size:90%;white-space:nowrap;display:inline-block">Descoped</span>'),
            ("tag with a suffix", re.findall(r">([^<]+)</span>", make_report.tag("reestimated", ": 5 → 3")),
             ["Re-estimated: 5 → 3"]),
        ]
        for name, got, expected in cases:
            with self.subTest(name):
                self.assertEqual(got, expected)

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
            ({"type": "completed"}, ["Completed"]),
            ({"type": "reopened"}, ["Reopened"]),
        ]
        for event, expected in cases:
            with self.subTest(event["type"]):
                self.assertEqual(re.findall(
                    r">([^<]+)</span>", r.tags(event)), expected)


class HeaderTest(unittest.TestCase):
    def test_header_table(self):
        # Always these 4 rows in this order, so readers find the same figure in
        # every report. The fixture has a previous sprint, yet no carry-over
        # row: the outcome charts show the carry-over.
        def table(dates, goal, target):
            return ("| Field | Detail |\n|---|---|\n"
                    f"| Dates | {dates} |\n| Goal | {goal} |\n| Goal outcome{AI} | Partially met |\n"
                    f"| Sprint target completion | {target} |")
        cases = [
            ("closed on its end date", {},
             table("02/03/2026–13/03/2026", "Ship login", "60%, 3/5 tickets (6/10 pts) completed")),
            ("active", ACTIVE,
             table("02/03/2026–13/03/2026", "Ship login", "60%, 3/5 tickets (6/10 pts) completed so far")),
            ("closed late, without a goal", {"sprint_complete_date": "2026-03-16", "sprint_goal": ""},
             table("02/03/2026–13/03/2026 (completed 16/03/2026)", "*No goal was set in Jira for this sprint*",
                   "60%, 3/5 tickets (6/10 pts) completed")),
            ("blank goal", {"sprint_goal": "   "},
             table("02/03/2026–13/03/2026", "*No goal was set in Jira for this sprint*",
                   "60%, 3/5 tickets (6/10 pts) completed")),
            ("blank goal lines", {"sprint_goal": "\n \n"},
             table("02/03/2026–13/03/2026", "*No goal was set in Jira for this sprint*",
                   "60%, 3/5 tickets (6/10 pts) completed")),
            # Jira's goal keeps its wording, one line per <br>, its keys linked
            # and its pipes escaped so the cell holds.
            ("a goal over several lines", {"sprint_goal": "Ship login\n\n  Fix PROJ-1 | export  \n"},
             table("02/03/2026–13/03/2026", f"Ship login<br>Fix [PROJ-1]({BASE}/browse/PROJ-1) \\| export",
                   "60%, 3/5 tickets (6/10 pts) completed")),
            ("literal HTML and entities", {"sprint_goal": 'Ship <beta> & preserve &amp;\nFix PROJ-1 | "export"'},
             table("02/03/2026–13/03/2026",
                   f'Ship &lt;beta&gt; &amp; preserve &amp;amp;<br>Fix [PROJ-1]({BASE}/browse/PROJ-1) \\| "export"',
                   "60%, 3/5 tickets (6/10 pts) completed")),
        ]
        for name, changes, expected in cases:
            with self.subTest(name):
                self.assertEqual(report(**changes).header_table(), expected)


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
            "02/03/2026 (sprint start) | PROJ-1 (2 pts) | Added | Commitment: 5 tickets (9 pts) Still open: 4 tickets "
            "(8 pts) of the commitment 4 tickets (8 pts) with extra",
            "PROJ-2 (2 pts) | Added", "PROJ-4 (1 pt) | Added Already done", "PROJ-5 (2 pts) | Added",
            "PROJ-6 (2 pts) | Added",
            "03/03/2026 | PROJ-1 (3 pts) | Re-estimated: 2 → 3 pts | Still open: 4 tickets (9 pts) of the commitment "
            "4 tickets (9 pts) with extra",
            "04/03/2026 | PROJ-1 (3 pts) | Completed | Still open: 1 ticket (2 pts) of the commitment 1 ticket (2 pts) "
            "with extra",
            "PROJ-2 (2 pts) | Descoped", "PROJ-6 (2 pts) | Descoped",
            "05/03/2026 | PROJ-2 (2 pts) | Added | Still open: 0 tickets (0 pts) of the commitment 2 tickets (3 pts) "
            "with extra",
            "PROJ-3 (1 pt) | Added", "PROJ-5 (2 pts) | Completed",
            "06/03/2026 | PROJ-3 (1 pt) | Completed | Still open: 0 tickets (0 pts) of the commitment 1 ticket (2 pts) "
            "with extra",
            "13/03/2026 (sprint closed) | – | Still open: 0 tickets (0 pts) of the commitment 1 ticket (2 pts) with extra"])
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

    def test_overdue_sprint_keeps_its_current_figures(self):
        # An active sprint past its planned end continues through the fetch.
        data = sprint_data(sprint_status="active", today="2026-03-16")
        rows = self.rows(Report(data, CONTENT).timeline_table())
        self.assertEqual(rows[-1], "16/03/2026 (today) | – | Still open: 0 tickets (0 pts) of the commitment "
                         "1 ticket (2 pts) with extra")

    def test_epic_table(self):
        table = report().epic_table().replace("\n", "")
        self.assertIn(f'<th style="width:14%">Commitment</th><th style="width:14%">Extra</th>'
                      f'<th style="width:52%">Commentary{AI}</th>', table)
        # The epic's name is Jira text, so it is escaped.
        self.assertIn(f'<td><a href="{BASE}/browse/PROJ-100">PROJ-100: Login &lt;beta&gt;</a></td>'
                      "<td>3/5 tickets (6/10 pts)</td><td>0/1 ticket (0/2 pts)</td>", table)
        # No epic has no Jira page to link; no commitment reads "–", not 0/0.
        self.assertIn(
            "<td>(no epic)</td><td>–</td><td>1/1 ticket (1/1 pts)</td>", table)

    def test_epic_commentary(self):
        # A labelled sentence per group with tickets to describe, in order and
        # escaped; "Open" for not completed work while the sprint runs; "–"
        # for an epic with nothing to describe.
        in_review = sprint_data()
        in_review["spells"][2]["status"] = "In Review"  # PROJ-2's extra spell
        in_review = sprint_data(spells=in_review["spells"])
        review_content = copy.deepcopy(CONTENT)
        review_content["epic_commentary"]["PROJ-100"]["in_review"] = \
            review_content["epic_commentary"]["PROJ-100"].pop("not_completed")
        left_out = sprint_data(spells=[s for s in sprint_data()[
                               "spells"] if s["key"] in ("PROJ-4", "PROJ-5")])
        cases = [
            ("closed", sprint_data(), CONTENT,
             "<td><b>Completed:</b> Staff can sign in with a password.<br>"
             "<b>Not completed:</b> Remembering the last sign-in method is still in progress.<br>"
             "<b>Descoped:</b> Sign-in audit logging &amp; the admin screen were dropped.</td>"),
            ("no epic", sprint_data(), CONTENT,
             "<td><b>Completed:</b> The export now handles empty files.</td>"),
            ("active", sprint_data(**ACTIVE), CONTENT, "<b>Open:</b> Remembering"),
            ("in review", in_review, review_content,
             "<b>In review:</b> Remembering"),
            ("nothing to describe", left_out, {
             **CONTENT, "epic_commentary": {}}, "<td>–</td></tr>"),
        ]
        for name, data, content, expected in cases:
            with self.subTest(name):
                self.assertIn(expected, Report(
                    data, content).epic_table().replace("\n", ""))


class ProseTest(unittest.TestCase):
    def commentary(self, spells, **changes):
        return plain(Report(sprint_data(spells=spells, **changes), CONTENT).commentary())

    def test_commentary(self):
        ideal = [ticket("PROJ-1", [ev(2, "committed", 3),
                        ev(4, "completed", 3, done=True)], "completed")]
        cases = [
            ("closed", {},
             "Of the 5 tickets (9 pts) in the commitment, PROJ-4 (1 pt) was already Done at the start, and "
             "2 tickets (4 pts) were descoped (PROJ-2, PROJ-6). 2 tickets (3 pts) were added as extra "
             "(PROJ-2, PROJ-3). PROJ-1 (2 → 3 pts) was re-estimated and PROJ-2 (2 pts) left the "
             "sprint and came back, counting as descoped and then as extra. At the close, 1 ticket (2 pts) "
             "was not completed, all of it extra. PROJ-5 (2 pts) was resolved as Duplicate or Won't Do and "
             "counts as completed."),
            ("active", ACTIVE,
             "Of the 5 tickets (9 pts) in the commitment, PROJ-4 (1 pt) was already Done at the start, and "
             "2 tickets (4 pts) were descoped (PROJ-2, PROJ-6). 2 tickets (3 pts) were added as extra "
             "(PROJ-2, PROJ-3). PROJ-1 (2 → 3 pts) was re-estimated and PROJ-2 (2 pts) left the "
             "sprint and came back, counting as descoped and then as extra. 1 ticket (2 pts) is open, all of it "
             "extra, with 3 days left. PROJ-5 (2 pts) was resolved as Duplicate or Won't Do and counts as "
             "completed."),
            # Nothing departed from the ideal, so there is nothing else to say.
            ("ideal", {"spells": ideal},
             "The 1 ticket (3 pts) in the commitment stayed in the sprint. Everything in the sprint was "
             "completed by the close."),
        ]
        for name, changes, expected in cases:
            with self.subTest(name):
                self.assertEqual(
                    plain(report(**changes).commentary()), expected)
        # Tickets in the commentary are links, with their estimate after.
        self.assertIn(
            f"[PROJ-4]({BASE}/browse/PROJ-4) (1 pt)", report().commentary())

    def test_commentary_states_what_is_open(self):
        # What is open says how much of it is from the commitment, as that is
        # what the sprint promised.
        committed = ticket(
            "PROJ-1", [ev(2, "committed", 2)], "not_completed", status="To Do")
        extra = ticket("PROJ-2", [ev(3, "joined", 1)],
                       "not_completed", status="To Do", scope="extra")
        done = ticket("PROJ-1", [ev(2, "committed", 3),
                      ev(4, "completed", 3, done=True)], "completed")
        cases = [
            ("all from the commitment", [committed], {},
             "At the close, 1 ticket (2 pts) was not completed."),
            ("some from the commitment", [committed, extra], {},
             "At the close, 2 tickets (3 pts) were not completed, 1 ticket (2 pts) of them from the commitment."),
            ("nothing, while running", [done], ACTIVE,
             "Nothing is open, with 3 days left."),
        ]
        for name, spells, changes, expected in cases:
            with self.subTest(name):
                self.assertTrue(self.commentary(
                    spells, **changes).endswith(expected))

    def test_commentary_reestimates(self):
        # From the estimate before the first re-estimate to the latest; an
        # estimate never set or cleared stays unknown rather than 0.
        def reestimated(key, before, after):
            return ticket(key, [ev(2, "committed", before), ev(3, "reestimated", after, fromPoints=before)],
                          "not_completed", status="To Do")
        cases = [
            ("one", [reestimated("PROJ-1", 5, 3)],
             "PROJ-1 (5 → 3 pts) was re-estimated"),
            ("cleared", [reestimated("PROJ-1", 2, None)],
             "PROJ-1 (2 → – pts) was re-estimated"),
            ("several", [reestimated("PROJ-1", 5, 3), reestimated("PROJ-2", None, 5)],
             "2 tickets (5 → 8 pts) were re-estimated (PROJ-1, PROJ-2)"),
            # Over 3 tickets, the keys are counted rather than named.
            ("many", [reestimated(f"PROJ-{n}", 1, 2) for n in range(1, 5)],
             "4 tickets (4 → 8 pts) were re-estimated."),
        ]
        for name, spells, expected in cases:
            with self.subTest(name):
                self.assertIn(expected, self.commentary(spells))

    def test_commentary_word_limit_with_all_departures(self):
        spells = sprint_data()["spells"] + [
            ticket("PROJ-7", [ev(2, "committed", 1, done=True),
                   ev(5, "reopened", 1)], "not_completed"),
            ticket("PROJ-8", [ev(3, "joined", 1),
                   ev(4, "removed", 1)], "removed", scope="extra"),
            ticket("PROJ-9", [ev(3, "joined", None)], "not_completed", scope="extra")]
        for today in ("2026-03-10", "2026-03-12", "2026-03-13", "2026-03-14", "2026-03-16"):
            with self.subTest(today=today):
                data = sprint_data(spells=spells, **{**ACTIVE, "today": today})
                # Check the core without the non-delivery caveat.
                r = Report(data, CONTENT)
                commentary = r.commentary()
                core = commentary
                for caveat in r.commentary_caveats():
                    core = core.replace(caveat, "")
                self.assertLessEqual(
                    make_report.word_count(core), make_report.COMMENTARY_WORDS)
                # Shortened, every departure remains, including the open commitment.
                for phrase in ("already Done", "were descoped", "added as extra", "descoped again",
                               "was reopened", "re-estimated", "left the sprint and came back",
                               "descoped, then extra", "unestimated", "1 ticket (1 pt) from the commitment"):
                    self.assertIn(phrase, core)
                checked = Checker()
                check_commentary(checked, r.timeline_table() +
                                 "\n\n" + commentary, data)
                self.assertEqual(checked.failures, [])

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
        few = self.commentary(spells[:5])
        self.assertIn(
            "2 tickets (2 pts) were added as extra (PROJ-10, PROJ-11)", few)
        self.assertIn(
            "were added and descoped again (PROJ-110, PROJ-111), so they don't count", few)
        many = self.commentary(spells)
        self.assertNotIn("PROJ-1", many)
        self.assertIn("30 tickets (30 pts) were added as extra; 30 tickets (30 pts) were added and descoped again",
                      many)
        self.assertIn("4 tickets (4 pts) were reopened", many)
        self.assertLessEqual(
            make_report.word_count(many), make_report.COMMENTARY_WORDS)

    def test_commentary_caveats_are_never_cut(self):
        cases = [(["PROJ-6"], "The membership of PROJ-6 (2 pts) is reconstructed from changelogs, as later sprint "
                              "moves prevent checking it against Jira."),
                 (["PROJ-1", "PROJ-6"], "The membership of 2 tickets (5 pts) is reconstructed from changelogs "
                                        "(PROJ-1, PROJ-6), as later sprint moves prevent checking it against Jira.")]
        for keys, expected in cases:
            with self.subTest(keys=keys):
                text = plain(
                    report(membership_cross_check_excluded_keys=keys).commentary())
                self.assertTrue(text.endswith(expected), text)

    def test_large_caveats_name_every_ticket(self):
        for kind in ("membership", "non_delivery"):
            for count in (99, 100):
                with self.subTest(kind=kind, count=count):
                    keys = [f"PROJ-{n}" for n in range(100, 100 + count)]
                    if kind == "membership":
                        data = sprint_data(
                            membership_cross_check_excluded_keys=keys)
                    else:
                        data = sprint_data(spells=[ticket(key, [ev(2, "committed", 1),
                                                                ev(3, "completed", 1, done=True)], "completed", marker="duplicate") for key in keys])
                    caveat = Report(data, CONTENT).commentary_caveats()[-1]
                    self.assertEqual(re.findall(
                        r"\[(PROJ-\d+)\]", caveat), keys)

    def test_days_left(self):
        cases = [
            ("closed", {}, " with ", ""),
            ("active", ACTIVE, " with ", " with 3 days left"),
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
        self.assertEqual(headings, ["# Sprint Summary: Sprint 7", "## Scope Timeline", "## Delivery by Epic",
                                    f"## Key Achievements{AI}", f"## Blockers & Risks{AI}",
                                    f"## Notes for Sprint Retro{AI}"])
        # The outcome charts sit above the timeline, the burndown under its heading.
        self.assertEqual(re.findall(r"!\[[^\]]*\]\(([^)]+)\)", md),
                         [CHART_FILES["outcome_tickets"], CHART_FILES["outcome_pts"], CHART_FILES["burndown"]])
        self.assertIn(
            f"## Scope Timeline\n\n![Sprint burndown]({CHART_FILES['burndown']})", md)
        self.assertIn(
            "</table>\n\nOf the 5 tickets (9 pts) in the commitment,", md)
        self.assertIn(
            f"## Key Achievements{AI}\n\nLogin shipped: staff can sign in", md)
        # The agent's retro notes may name tickets; they are linked here.
        self.assertIn(
            f"## Notes for Sprint Retro{AI}\n\n- [PROJ-1]({BASE}/browse/PROJ-1) (3 pts) grew", md)
        self.assertTrue(md.endswith(
            "left the sprint and came back: should it have stayed out?\n"))

    def test_mid_sprint_snapshot_note(self):
        # A running sprint's figures are provisional; the note says so.
        note = 'This is a mid-sprint snapshot as at 10/03/2026, with 3 days left. "Open" means not completed yet.'
        self.assertIn(
            f"# Sprint Summary: Sprint 7\n\n{note}\n\n| Field |", report(**ACTIVE).build())
        self.assertNotIn("mid-sprint snapshot", report().build())

    def test_no_values_in_bold(self):
        md = report().build()
        bold = re.findall(r"\*\*(.+?)\*\*", md) + \
            re.findall(r"<b>(.+?)</b>", md)
        self.assertEqual(set(bold), {
                         "Commitment:", "Still open:", "Completed:", "Not completed:", "Descoped:"})


class ValidateContentTest(unittest.TestCase):
    def test_validate_content(self):
        # None: the content is valid. Otherwise each problem names the
        # content.json field to fix, so it is fixed where it was written.
        commentary = CONTENT["epic_commentary"]
        cases = [
            (None, {}),
            # Retro notes may name tickets, unlike the summaries.
            (None, {"retro_notes": ["PROJ-1 (3 pts) grew: why?"]}),
            # The shape. The text rules wait for a valid shape, as they read
            # the fields: a list here would otherwise crash them.
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
             {"epic_commentary": {**commentary, NO_EPIC: {}}}),
            ("epic_commentary.PROJ-100 needs a sentence for exactly these groups: completed, not_completed, descoped",
             {"epic_commentary": {**commentary,
                                  "PROJ-100": {**commentary["PROJ-100"], "in_review": "x"}}}),
            ("epic_commentary.PROJ-100 needs a sentence for exactly these groups",
             {"epic_commentary": {**commentary,
                                  "PROJ-100": {**commentary["PROJ-100"], "descoped": " "}}}),
            # The text: word limits, no ticket keys (describe the work), one
            # paragraph, and the report's vocabulary.
            ("key_achievements: 81 words, at most 80",
             {"key_achievements": "word " * 81}),
            ("blockers_risks: names tickets ['PROJ-2']",
             {"blockers_risks": "PROJ-2 is open."}),
            ("blockers_risks: must be a single paragraph",
             {"blockers_risks": "Open.\n\nStill open."}),
            ("epic_commentary.PROJ-100.completed: must be one sentence",
             {"epic_commentary": {**commentary, "PROJ-100": {**commentary["PROJ-100"],
                                  "completed": "Staff can sign in. Password reset also works."}}}),
            # An epic's limit counts all its groups' sentences together.
            ("epic_commentary.PROJ-100: 68 words, at most 60",
             {"epic_commentary": {**commentary, "PROJ-100": {**commentary["PROJ-100"], "completed": "word " * 50}}}),
            ("epic_commentary.__no_epic__: names tickets ['PROJ-3']",
             {"epic_commentary": {**commentary, NO_EPIC: {"completed": "PROJ-3 shipped."}}}),
            ("key_achievements: no story or stories, found ['stories']", {
             "key_achievements": "Two stories shipped."}),
            ("key_achievements: no spelled-out numbers (write digits), found ['Two']",
             {"key_achievements": "Two tickets shipped."}),
            ("retro_notes[1]: no points (write pts), found ['points']",
             {"retro_notes": ["Fine?", "Were 9 points too many?"]}),
            ("retro_notes[0]: no closed (write completed, or at the close), found ['closed']",
             {"retro_notes": ["PROJ-1 (3 pts) closed late: why?"]}),
            ("retro_notes[0]: no issue or issues", {
             "retro_notes": ["Was it an issue?"]}),
        ]
        for expected, changes in cases:
            with self.subTest(expected, changes=changes if expected is None else None):
                content = {**copy.deepcopy(CONTENT), **changes}
                if expected is None:
                    make_report.validate_content(content, sprint_data())
                    continue
                with self.assertRaises(SystemExit) as raised:
                    make_report.validate_content(content, sprint_data())
                self.assertIn(expected, str(raised.exception))


if __name__ == "__main__":
    unittest.main()
