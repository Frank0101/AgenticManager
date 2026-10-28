"""Unit tests for skills/agentic-manager-jira-sprint-report/scripts/check_report.py.
Run with: python3 tests/run.py agentic-manager-jira-sprint-report

Each test renders the report of report_fixture.py's sprint with make_report,
breaks one thing in it, and checks that the matching check fails.
"""

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
from common import CHART_FILES, ai, expected_files  # noqa: E402
from make_report import FULL_PANEL, Report, tag  # noqa: E402

sys.path.insert(0, TEST_DIR)
from report_fixture import BASE, CONTENT, TICKETS, caveat_data, ev, ticket, sprint_data  # noqa: E402

# The [AI Gen.] label as make_report renders it.
AI = ai("")


def ticket_event(data, key, kind):
    """A ticket's first event of a kind, in data.json."""
    return next(e for e in data["ticket_events"][key] if e["type"] == kind)


def without(data, key, kind):
    """Drops a ticket's events of a kind from data.json."""
    data["ticket_events"][key] = [
        e for e in data["ticket_events"][key] if e["type"] != kind]


def event_at(at, **fields):
    """A Jira event at an instant of March 2026 in UTC, dated as the
    reporting timezone, London, dates it then."""
    return {"at": at, "date": at[:10], "source": "jira", **fields}


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
        # The exit code is what the skill acts on: non-zero on any failure.
        cases = [("a failure", [(True, "a", "fine"), (False, "b", "broken")], 1,
                  "  ok    a: fine\n  FAIL  b: broken\n\n1 check(s) failed\n"),
                 ("all passed", [(True, "a", "fine")], 0, "  ok    a: fine\n\nall 1 checks passed\n")]
        for name, checks, code, printed in cases:
            with self.subTest(name):
                c = check_report.Checker()
                self.assertEqual([c.check(*args)
                                 for args in checks], [ok for ok, _, _ in checks])
                out = io.StringIO()
                with contextlib.redirect_stdout(out):
                    self.assertEqual(c.report(), code)
                self.assertEqual(out.getvalue(), printed)

    def test_ratio_units_with_fractional_operands(self):
        data = {"spells": [], "membership_cross_check_excluded_keys": []}
        for ratio in ("2/3", "2/2.5", "0.5/2", "0.5/2.5", "0/0.5"):
            for suffix in (" ticket", " tickets", " pts", "", ".", " ptsx"):
                with self.subTest(ratio=ratio, suffix=suffix):
                    c = check_report.Checker()
                    check_report.check_vocabulary(c, ratio + suffix, data)
                    failures = [f for f in c.failures if f.startswith(
                        "vocabulary: ratios only as")]
                    if suffix in (" ticket", " tickets", " pts"):
                        self.assertEqual(failures, [])
                    else:
                        self.assertEqual(failures, [
                            f"vocabulary: ratios only as N/M tickets (N/M pts) ['{ratio}']"])
        c = check_report.Checker()
        check_report.check_vocabulary(c, "02/03/2026", data)
        self.assertFalse(any(f.startswith("vocabulary: ratios only as")
                         for f in c.failures))


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

    def assert_fails(self, expected, md=None, data=None):
        """Some failure starts with `expected`: a check's name, or the start of
        one of its messages."""
        prefix = expected if ":" in expected else f"{expected}: "
        failures = self.failures(md, data)
        self.assertTrue(any(f.startswith(prefix)
                        for f in failures), f"no {prefix!r} failure in {failures}")

    def replace(self, old, new):
        """The report with `old`, which must appear in it, replaced by `new`."""
        self.assertIn(old, self.md)
        return self.md.replace(old, new, 1)

    def test_status_rows_of_every_kind_pass(self):
        # Whatever a row's flag and counts, the section the generator writes
        # passes the section's own check.
        def linked(merged=0, opened=0, declined=0):
            return {"merged": merged, "open": opened, "declined": declined}
        # name: changes to the first row
        cases = {"not started, 1 PR": {"flag": "work_started", "linked": linked(merged=1), "otherTickets": 0},
                 "not started, 1 open PR": {"flag": "work_started", "linked": linked(opened=1), "otherTickets": 0},
                 "not started, all merged": {"flag": "work_started", "linked": linked(merged=3), "otherTickets": 2},
                 "not started, mixed": {"flag": "work_started", "linked": linked(5, 2, 1), "otherTickets": 1},
                 "Done, several open": {"ownOpen": 3},
                 "Done, a full panel alone": {"flag": None, "ownOpen": 0, "fullPanel": True}}
        for name, changes in cases.items():
            with self.subTest(name):
                data = sprint_data()
                data["status_checks"][0].update(changes)
                md = Report(data, copy.deepcopy(CONTENT)).build()
                table = next(t for t in check_report.html_tables(
                    md) if check_report.table_kind(t) == "status")
                checked = check_report.Checker()
                check_report.check_status_section(checked, md, table, data)
                self.assertEqual(checked.failures, [])

    def test_generated_reports_pass(self):
        cases = {"closed": ({}, "Partially met"),
                 "active": ({"sprint_status": "active", "today": "2026-03-10", "sprint_complete_date": None},
                            "At risk"),
                 "closed late": ({"sprint_complete_date": "2026-03-16"}, "Partially met"),
                 "no goal": ({"sprint_goal": ""}, "No goal set in Jira for this sprint"),
                 "blank goal": ({"sprint_goal": "   "}, "No goal set in Jira for this sprint"),
                 "blank goal lines": ({"sprint_goal": "\n \n"}, "No goal set in Jira for this sprint"),
                 # Jira's goal, with its keys linked and pipes escaped, reads back as Jira's.
                 "a goal over several lines": ({"sprint_goal": "Ship login\nFix PROJ-1 | export"}, "Partially met"),
                 "literal HTML and entities": ({"sprint_goal": "Ship <beta> & preserve &amp;\nFix PROJ-1 | export"},
                                               "Partially met"),
                 "no previous sprint": ({"previous_sprint": None}, "Partially met")}
        for name, (changes, verdict) in cases.items():
            with self.subTest(name):
                data = sprint_data(**changes)
                md = Report(data, {**copy.deepcopy(CONTENT),
                            "goal_verdict": verdict}).build()
                self.assertEqual(self.failures(md, data), [])

    def test_scenarios_pass_and_their_breakages_fail(self):
        # Sprints unlike the fixture: the generated report passes the checks
        # each breakage is meant for, and each breakage fails them.
        offsets = [ev(2, "committed", 2), dict(ev(6, "completed", 2, done=True), at="2026-03-06T09:30:00+0100"),
                   dict(ev(6, "reopened", 2), at="2026-03-06T09:00:00+0000")]
        source = "One story — issues closed on 2026-03-01 at 50.5%"
        copied = sprint_data(sprint_name=source, sprint_goal=source)
        copied["epics"][0]["name"] = source
        retro = {"retro_notes": ["PROJ-1 (5 pts) changed: was it ready?"]}
        cases = [
            ("literal goal markup", sprint_data(sprint_goal="Ship <beta> & preserve &amp;"), {},
             [("Ship &lt;beta&gt;", "Ship <beta>", "header"),
              ("preserve &amp;amp;", "preserve &amp;", "header")]),
            # Events are ordered by instant, not by their text: 09:30+0100 is
            # before 09:00+0000.
            ("instants across offsets",
             sprint_data(
                 spells=[ticket("PROJ-1", offsets, "not_completed", status="In Progress")]), {},
             [(tag("completed") + tag("reopened"), tag("reopened") + tag("completed"),
               "timeline: 06/03/2026 lists")]),
            # Past the planned end both the burndown and commentary keep
            # tracking work through the fetch.
            ("overdue", sprint_data(sprint_status="active", sprint_complete_date=None, today="2026-03-16",
                                    as_of_instant="2026-03-16T12:00:00Z", spells=[ticket("PROJ-1", [
                                        ev(2, "committed", 2), ev(15, "completed", 2, done=True)], "completed")]),
             {}, [("Nothing is open", "1 ticket (2 pts) is open", "commentary: states that nothing")]),
            # Open work with no estimate is "– pts", never "0 pts".
            ("unestimated open work", sprint_data(spells=[ticket("PROJ-1", [ev(2, "committed", None)],
                                                                 "not_completed", status="To Do")]),
             {}, [("1 ticket (– pts) was not completed", "1 ticket (0 pts) was not completed",
                   "commentary: states what is still open")]),
            # All the work was added after the start: the report says so
            # rather than a ratio of nothing.
            ("no commitment", sprint_data(spells=[t for t in TICKETS if t["key"] == "PROJ-3"]), {},
             [("Nothing was committed at the start", "All 0 tickets (0 pts) in the commitment stayed in the sprint",
               "commentary: states that nothing was committed"),
              ("No commitment", "n/a, 0/0 tickets (0/0 pts) completed", "header: Sprint target completion")]),
            ("membership not checked against Jira", sprint_data(membership_cross_check_excluded_keys=["PROJ-6"]), {},
             [("is reconstructed from changelogs", "is assumed",
               "commentary: states the membership cross-check limitation")]),
            # A ticket that left before the report may be named, but only in
            # the membership caveat.
            ("membership of a ticket without a spell", sprint_data(membership_cross_check_excluded_keys=["PROJ-99"]),
             {}, [("PROJ-99", "PROJ-98", "commentary: names only tickets"),
                  ("At the close,", "At the close, PROJ-99,", "commentary: names only tickets")]),
            # The commentary's fixed phrases name a ticket with its estimate at
            # that event; the agent's text, with its latest.
            ("estimate when already Done", sprint_data(spells=[ticket("PROJ-1", [
                ev(2, "committed", 2, done=True), ev(3, "reestimated", 5, done=True, fromPoints=2)], "completed")]),
             retro, [("PROJ-1) (2 pts) was already Done", "PROJ-1) (5 pts) was already Done", "vocabulary"),
                     ("(5 pts) changed", "(2 pts) changed", "vocabulary")]),
            ("estimate when descoped", sprint_data(spells=[
                ticket("PROJ-1", [ev(2, "committed", 2),
                       ev(4, "removed", 2)], "removed"),
                ticket("PROJ-1", [ev(5, "joined", 5)], "not_completed", scope="extra")]),
             retro, [("PROJ-1) (2 pts) was descoped", "PROJ-1) (5 pts) was descoped", "vocabulary"),
                     ("(5 pts) changed", "(2 pts) changed", "vocabulary")]),
            ("estimate when added and descoped again", sprint_data(spells=[
                ticket("PROJ-1", [ev(3, "joined", 5), ev(4, "removed", 5)], "removed", scope="extra")]),
             retro, [("PROJ-1) (5 pts) was added and descoped", "PROJ-1) (2 pts) was added and descoped",
                      "vocabulary")]),
            # Copied Jira text keeps its wording; the same words in generated
            # or agent text still fail.
            ("copied Jira words", copied, {},
             [("Login shipped: staff", source + ": staff", check) for check in ("vocabulary", "em dashes", "dates")]),
            # Only the title is plain text: a key in a copied field is linked.
            ("copied Jira keys", sprint_data(sprint_name="Sprint PROJ-90", sprint_goal="Deliver PROJ-91"), {},
             [(f"[PROJ-91]({BASE}/browse/PROJ-91)", "PROJ-91", "links"),
              (f'<a href="{BASE}/browse/PROJ-100">PROJ-100: Login &lt;beta&gt;</a>', "PROJ-100: Login", "links")]),
            ("an epic with nothing to describe",
             sprint_data(spells=[s for s in sprint_data()[
                         "spells"] if s["key"] in ("PROJ-4", "PROJ-5")]),
             {"epic_commentary": {}}, [("<td>–</td>\n</tr>", "<td>Done.</td>\n</tr>", "epics: PROJ-100 has no scope")]),
        ]
        for name, data, content, breakages in cases:
            md = Report(data, {**copy.deepcopy(CONTENT), **content}).build()
            failures = check_report.run_checks(
                md, data, self.tmp.name).failures
            for check in {expected.split(":")[0] for _, _, expected in breakages}:
                with self.subTest(name, check=check):
                    self.assertEqual(
                        [f for f in failures if f.startswith(f"{check}:")], [])
            for old, new, expected in breakages:
                with self.subTest(name, old=old, expected=expected):
                    self.assertIn(old, md)
                    self.assert_fails(expected, md.replace(old, new, 1), data)

    def test_only_the_reports_files_are_allowed(self):
        # Every file a report folder holds passes, and so does a hidden one; any other fails.
        expected = expected_files(self.data["label"])
        for name in sorted(expected - set(CHART_FILES.values())):
            open(os.path.join(self.tmp.name, name), "w").close()
        open(os.path.join(self.tmp.name, ".DS_Store"), "w").close()
        self.assertEqual(self.failures(), [])
        for stray in ("notes.md", "draft.json", "content.json.bak"):
            with self.subTest(stray):
                open(os.path.join(self.tmp.name, stray), "w").close()
                self.assert_fails("files")
                os.remove(os.path.join(self.tmp.name, stray))

    def test_caveats_require_every_affected_ticket(self):
        for kind in ("membership", "non_delivery"):
            for count in (99, 100):
                with self.subTest(kind=kind, count=count):
                    keys = [f"PROJ-{n}" for n in range(100, 100 + count)]
                    data = caveat_data(kind, keys)
                    report = Report(data, CONTENT)
                    md = report.timeline_table() + "\n\n" + report.commentary()
                    valid = check_report.Checker()
                    check_report.check_commentary(valid, md, data)
                    self.assertEqual(valid.failures, [])
                    for replacement in ("", "PROJ-999"):
                        broken = md.replace(
                            report.md_key(keys[-1]), replacement)
                        checked = check_report.Checker()
                        check_report.check_commentary(checked, broken, data)
                        self.assertTrue(any("caveat names every affected ticket" in failure
                                            for failure in checked.failures), checked.failures)

    def test_each_check_catches_its_breakage(self):
        proj_6 = f'<a href="{BASE}/browse/PROJ-6">PROJ-6</a>'
        proj_1 = f'<a href="{BASE}/browse/PROJ-1">PROJ-1'
        cases = [
            ("timeline", ">Descoped</span>", ">Removed</span>"),
            ("timeline", f'>Descoped</span></td></tr>\n<tr><td style="white-space:nowrap">{proj_6}',
             f'>Completed</span></td></tr>\n<tr><td style="white-space:nowrap">{proj_6}'),
            ("timeline", ">Re-estimated: 2 → 3 pts</span>",
             ">Re-estimated: 3 pts</span>"),
            ("timeline", f"{proj_6} (2 pts)", f"{proj_6} (3 pts)"),
            ("timeline", "<br>1 ticket (2 pts) with extra",
             "<br>1 ticket (3 pts) with extra"),
            ("timeline", "<b>Commitment:</b><br>5 tickets (9 pts)",
             "<b>Commitment:</b><br>5 tickets (10 pts)"),
            ("timeline", "<b>Still open:</b>", "<b>Open:</b>"),
            ("timeline", ">03/03/2026</td>", ">07/03/2026</td>"),
            ("timeline: the days are the timeline's, in order (6)",
             ">04/03/2026</td>", ">05/04/2026</td>"),
            ("cell shapes", '<td rowspan="5" style', '<td rowspan="4" style'),
            ("commentary: states 2 tickets (4 pts) descoped",
             "2 tickets (4 pts) were descoped", "2 tickets (5 pts) were descoped"),
            ("commentary: mentions left and came back",
             f" and [PROJ-2]({BASE}/browse/PROJ-2) (2 pts) left the sprint and came back, counting as "
             "descoped and then as extra", ""),
            ("commentary: states the commitment, 5 tickets (9 pts)",
             "Of the 5 tickets (9 pts) in the commitment", "Of the 5 tickets (10 pts) in the commitment"),
            ("commentary: names only tickets of the sprint",
             f"PROJ-5]({BASE}/browse/PROJ-5) (2 pts) was resolved", f"PROJ-9]({BASE}/browse/PROJ-9) (2 pts) was resolved"),
            ("commentary: states what is still open, 1 ticket (2 pts)",
             "1 ticket (2 pts) was not completed", "1 ticket (3 pts) was not completed"),
            ("commentary: at most 100 words before its caveats",
             "At the close,", "At the close, after a long and eventful sprint full of changes that the team handled "
             "with care, attention and a great deal of patience across many working days and meetings, " * 2),
            ("commentary: the timeline is followed by its commentary",
             Report(self.data, CONTENT).commentary(), ""),
            ("epics: PROJ-100 has a row", ">PROJ-100: ", ">PROJ-101: "),
            ("epics", "<td>60%, 3/5 tickets (6/10 pts)</td>",
             "<td>60%, 3/6 tickets (6/10 pts)</td>"),
            ("epics", "<td>60%, 3/5 tickets (6/10 pts)</td>",
             "<td>3/5 tickets (6/10 pts)</td>"),
            ("epics", "<b>Not completed:</b>", "<b>Open:</b>"),
            ("epics", "<br><br><b>Descoped:</b> Sign-in audit logging &amp; the admin screen were dropped.", ""),
            ("epics", "<br><br><b>Not completed:</b>", "<br><b>Not completed:</b>"),
            ("header", f"| Goal outcome{AI} |", "| Goal outcome |"),
            ("header", "| Field | Detail |", "| Item | Detail |"),
            ("header", "| Dates | 02/03/2026–13/03/2026 |",
             "| Dates | 02/03/2026 to 13/03/2026 |"),
            ("header", "| Goal | Ship login |", "| Goal | Ship it |"),
            ("header", "| Sprint target completion |", "| Target |"),
            ("header: Sprint target completion is a table of its own under Sprint Metrics",
             "## Sprint Metrics\n\n| Field", "## Sprint Metrics\n\nThe figures.\n\n| Field"),
            ("images: outcome-pts.svg sits under the Sprint Metrics heading",
             "![Sprint outcome in pts](outcome-pts.svg)\n\n## Scope Timeline",
             "## Scope Timeline\n\n![Sprint outcome in pts](outcome-pts.svg)"),
            ("header", "3/5 tickets (6/10 pts) completed",
             "3/5 tickets (6/11 pts) completed"),
            ("header", "| 60%, 3/5 tickets", "| 3/5 tickets"),
            # The carry-over row was removed on purpose: the charts show it.
            ("header", "3/5 tickets (6/10 pts) completed |",
             "3/5 tickets (6/10 pts) completed |\n| Carried over from Sprint 6 | 1 ticket |"),
            ("images",
             "## Scope Timeline\n\n![Sprint burndown](burndown.svg)", "## Scope Timeline"),
            ("em dashes", "Partially met", "Partially met — mostly"),
            ("dates", "02/03/2026–", "2026-03-02–"),
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
            ("vocabulary", f"[PROJ-1]({BASE}/browse/PROJ-1) (3 pts)",
             f"[PROJ-1]({BASE}/browse/PROJ-1)"),
            ("vocabulary", f"[PROJ-1]({BASE}/browse/PROJ-1) (3 pts)",
             f"[PROJ-1]({BASE}/browse/PROJ-1) (5 pts)"),
            ("vocabulary", f"were descoped ([PROJ-2]({BASE}/browse/PROJ-2), [PROJ-6]({BASE}/browse/PROJ-6))",
             f"were descoped ([PROJ-6]({BASE}/browse/PROJ-6), [PROJ-2]({BASE}/browse/PROJ-2))"),
            ("status: a Status to Verify section sits right above the retro notes",
             "## Status to Verify", "## Statuses"),
            ("status: the table lists each flagged ticket", f'{proj_1}</a> (3 pts)</td><td class="jira">Done<',
             f'{proj_1}</a> (3 pts)</td><td class="jira">To Do<'),
            ("status: the table lists each flagged ticket", f'{proj_1}</a> (3 pts)</td><td class="jira">',
             f'{proj_1}</a> (2 pts)</td><td class="jira">'),
            ("status: PROJ-1 shows Done, but 1 PR", "Done, but 1 PR is still open.",
             "Done, but 2 PRs are still open."),
            ("status: PROJ-1 shows Done, but 1 PR", "Done, but 1 PR is still open.</td>",
             "Done, but 1 PR is still open. " + FULL_PANEL + ".</td>"),
            # Copied Jira text keeps its wording; the generated text doesn't.
            ("vocabulary", "1 PR is still open.", "1 PR isn't closed."),
        ]
        for check, old, new in cases:
            with self.subTest(check=check, old=old):
                self.assert_fails(check, self.replace(old, new))

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
            ("a stored flag that its events don't give", lambda d: d["spells"][0].update(reopened=True),
             "model: PROJ-1's doneAtStart, reopened, reestimated and cameBack flags are what its events give"),
            ("a sprint target that isn't the commitment's", lambda d: d["target_completion"].update(completed=0),
             "model: the sprint target is the original commitment's spells, and those completed"),
            ("a non-delivery count", lambda d: d["non_delivery_closures"].update(count=0),
             "model: the non-delivery closures are the counted spells completed as Duplicate or Won't Do"),
            ("non-delivery pts", lambda d: d["non_delivery_closures"].update(points=5),
             "model: the non-delivery closures are"),
            ("a non-delivery ticket missing", lambda d: d["non_delivery_closures"]["issues"].clear(),
             "model: the non-delivery closures are"),
            ("a non-delivery estimate", lambda d: d["non_delivery_closures"]["issues"][0].update(storyPoints=8),
             "model: the non-delivery closures are"),
            ("the estimated ticket count", lambda d: d.update(points_estimated_issue_count=2),
             "model: the estimated and total ticket counts are the counted spells'"),
            ("the total ticket count", lambda d: d.update(points_total_issue_count=9),
             "model: the estimated and total ticket counts are the counted spells'"),
            ("a second original spell", lambda d: d["spells"][2].update(scope="original", events=[
                dict(d["spells"][2]["events"][0], type="committed")]),
             "model: PROJ-2's events are well formed (committed)"),
            ("missing final burndown days", lambda d: d["burndown"].pop(),
             "model: the burndown covers every day"),
            ("missing middle burndown day", lambda d: d["burndown"].pop(1),
             "model: the burndown covers every day"),
            ("duplicate burndown day", lambda d: d["burndown"].append(d["burndown"][-1]),
             "model: the burndown covers every day"),
            ("the burndown", lambda d: d["burndown"][0].update(committed=99),
             "model: the burndown on 02/03/2026 is the spells' open tickets and pts"),
            ("the baseline", lambda d: d.update(burndown_baseline=99),
             "model: the burndown starts at the whole commitment, 9"),
            # The epic table is recomputed from the spells, not trusted from data.json.
            ("a ticket under the wrong epic", lambda d: d["spells"][0].update(parentKey=None),
             "epics: PROJ-100 shows"),
            # The pull requests' ownership and state, and the status rows,
            # are recomputed from each pull request's title, branch and times.
            ("a pull request taken as the ticket's own", lambda d: d["ticket_pull_requests"]["PROJ-1"][1].update(
                own=True), "model: PROJ-1's pull requests are as at the end"),
            ("a merge with no merge time", lambda d: d["ticket_pull_requests"]["PROJ-2"][0].update(mergedAt=None),
             "model: PROJ-2's pull requests are as at the end"),
            ("a merge after the end", lambda d: d["ticket_pull_requests"]["PROJ-2"][0].update(
                mergedAt="2026-03-20T10:00:00.000+0000"), "model: PROJ-2's pull requests are as at the end"),
            ("a ticket without its pull requests", lambda d: d["ticket_pull_requests"].pop("PROJ-3"),
             "model: every ticket in the sprint at the end has its pull requests"),
            ("a flagged ticket missing", lambda d: d["status_checks"].pop(),
             "model: the Status to Verify rows are the tickets"),
            ("a wrong flag", lambda d: d["status_checks"][0].update(flag="work_started"),
             "model: the Status to Verify rows are the tickets"),
            ("a full panel that isn't stored", lambda d: d["status_checks"][1].update(fullPanel=True),
             "model: the Status to Verify rows are the tickets"),
            ("rows out of order", lambda d: d["status_checks"].reverse(),
             "model: the Status to Verify rows are in the epics' order"),
            ("the timeline", lambda d: d["timeline"][1]["events"].clear(),
             "model: the timeline holds exactly the spells' events"),
            ("the breakdown", lambda d: d["outcome_breakdown_points"].update(extra_completed=5),
             "model: the charts' extra completed is the counted spells' 1 ticket (5 pts)"),
            ("the carry-over split", lambda d: d["outcome_breakdown_counts"].update(new_removed=0),
             "model: the charts' new removed is the counted spells'"),
            ("the charted commitment", lambda d: d["outcome_breakdown_counts"].update(original_removed=0),
             "model: the charts' original removed is the counted spells'"),
            # The commentary groups are recomputed from the spells too.
            ("completed work described as descoped", lambda d: d["epics"][0]["scope_groups"].update(
                completed=[], descoped=[{"key": "PROJ-1"}] + d["epics"][0]["scope_groups"]["descoped"]),
             "model: PROJ-100's commentary groups hold the tickets their outcomes give"),
            ("work done before the sprint described as completed", lambda d: d["epics"][0].update(
                left_out=[t for t in d["epics"][0]
                          ["left_out"] if t["key"] != "PROJ-4"],
                scope_groups={**d["epics"][0]["scope_groups"], "completed": [{"key": "PROJ-1"}, {"key": "PROJ-4"}]}),
             "model: PROJ-100's commentary groups hold the tickets their outcomes give"),
            ("descoped work left out", lambda d: d["epics"][0].update(
                left_out=d["epics"][0]["left_out"] + [{"key": "PROJ-6"}],
                scope_groups={**d["epics"][0]["scope_groups"], "descoped": [{"key": "PROJ-2"}]}),
             "model: PROJ-100's commentary groups hold the tickets their outcomes give"),
            # The spells are worked out from each ticket's events, so the two
            # must tell the same story.
            ("a completion with no status change", lambda d: without(d, "PROJ-1", "status_changed"),
             "model: PROJ-1's spell events are what its ticket events give"),
            ("an estimate the ticket never had", lambda d: ticket_event(d, "PROJ-1", "points_changed").update(to=5),
             "model: PROJ-1's spell events are what its ticket events give"),
            ("a removal with no sprint change", lambda d: without(d, "PROJ-6", "sprint_changed"),
             "model: PROJ-6's spell events are what its ticket events give"),
            ("a commitment while out of the sprint",
             lambda d: ticket_event(
                 d, "PROJ-4", "created")["values"].update(sprint=[]),
             "model: PROJ-4's spell events are what its ticket events give"),
            ("a change a running spell misses", lambda d: d["ticket_events"]["PROJ-2"].append(
                event_at("2026-03-06T10:00:00.000+0000", type="status_changed", **{
                    "from": "In Progress", "to": "Done", "fromCategory": "indeterminate", "toCategory": "done"})),
             "model: PROJ-2's spell events are what its ticket events give ['end']"),
            ("ticket events out of time order", lambda d: d["ticket_events"]["PROJ-1"].reverse(),
             "model: PROJ-1's ticket events are in time order"),
            ("an unknown event type", lambda d: d["ticket_events"]["PROJ-3"].append(
                event_at("2026-03-06T11:00:00.000+0000", type="assignee_changed")),
             "model: PROJ-3's ticket events are well formed"),
            ("a date that isn't its instant's", lambda d: ticket_event(d, "PROJ-3", "created").update(
                date="2026-02-21"), "model: PROJ-3's ticket events are well formed"),
            ("an event after the end", lambda d: d["ticket_events"]["PROJ-3"].append(
                event_at("2026-03-14T10:00:00.000+0000", type="priority_changed", **{
                    "from": "Medium", "to": "High"})), "model: PROJ-3's ticket events are well formed"),
            ("a second creation", lambda d: d["ticket_events"]["PROJ-3"].insert(
                0, ticket_event(d, "PROJ-3", "created")), "model: PROJ-3's ticket events are well formed"),
            # The build leaves the pull request data out, so a GitHub event is unknown.
            ("a pull request event", lambda d: d["ticket_events"]["PROJ-1"].append(
                event_at("2026-03-04T09:00:00Z", source="github", type="last_pr_merged",
                         url="https://github.com/acme/api/pull/41", via="PROJ-1")),
             "model: PROJ-1's ticket events are well formed"),
            ("events of a ticket without a spell", lambda d: d["ticket_events"].update(
                {"PROJ-9": d["ticket_events"]["PROJ-3"]}),
             "model: every ticket with a spell has its events, and no other ticket"),
            ("a ticket without its events", lambda d: d["ticket_events"].pop("PROJ-3"),
             "model: every ticket with a spell has its events, and no other ticket"),
        ]
        for name, breakage, expected in cases:
            with self.subTest(name):
                data = sprint_data()
                breakage(data)
                self.assert_fails(expected, data=data)

    def test_missing_parts(self):
        # A chart beside the report, or the tables and sections in it.
        cases = [
            ("a chart", lambda: os.remove(os.path.join(self.tmp.name, CHART_FILES["burndown"])), self.md,
             ["images"]),
            ("tables and sections", lambda: None, "# Sprint Summary\n\nNothing here.\n",
             ["timeline: table found", "epics: table found"]),
        ]
        for name, remove, md, expected in cases:
            with self.subTest(name):
                remove()
                for failure in expected:
                    self.assert_fails(failure, md)

    def test_framing(self):
        # Only the timeline and epic tables need a heading directly above them.
        epics = "<table><tr><th>Epic</th><th>Commentary</th></tr></table>"
        cases = [("an epic table", "<table><tr><th>Epic</th><th>Commentary</th></tr></table>\n\n" + "Prose. " * 10,
                  ["headings: epics table has a heading above it"]),
                 ("another table", "<table><tr><th>Field</th></tr></table>", []),
                 # The report's title isn't a section heading.
                 ("only the title above", "# Sprint Summary: S1\n\n" + epics,
                  ["headings: epics table has a heading above it"]),
                 ("prose between the heading and the table", "## Delivery by epic\n\nProse.\n\n" + epics,
                  ["headings: epics table directly follows 'Delivery by epic'"])]
        for name, md, expected in cases:
            with self.subTest(name):
                c = check_report.Checker()
                check_report.check_framing(c, md)
                self.assertEqual(c.failures, expected)


if __name__ == "__main__":
    unittest.main()
