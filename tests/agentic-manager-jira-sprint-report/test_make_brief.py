"""Unit tests for skills/agentic-manager-jira-sprint-report/scripts/make_brief.py, on the
hand-written sprint in report_fixture.py.
Run with: python3 tests/run.py agentic-manager-jira-sprint-report
"""

import copy
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import report_fixture as fixture  # noqa: E402,F401  (puts the scripts on the path)
import make_brief  # noqa: E402
import common  # noqa: E402


class BriefTest(unittest.TestCase):
    def setUp(self):
        self.data = fixture.sprint_data()
        self.brief = make_brief.build_brief(self.data)

    def tickets(self):
        return [t for e in self.brief["epics"] for t in e["tickets"]]

    def test_work_the_sprint_did_not_do_is_not_listed(self):
        # PROJ-4 was already Done at the start and PROJ-5 is a Duplicate.
        self.assertEqual(sorted((t["key"], t["group"], t["scope"]) for t in self.tickets()), [
            ("PROJ-1", "completed", "original"), ("PROJ-2", "descoped", "original"),
            ("PROJ-2", "not_completed", "extra"), ("PROJ-3", "completed", "extra"),
            ("PROJ-6", "descoped", "original")])

    def test_tickets_carry_what_the_text_needs(self):
        ticket = next(t for t in self.tickets() if t["key"] == "PROJ-1")
        self.assertEqual(ticket, {"key": "PROJ-1", "group": "completed", "carried_in": False, "scope": "original", "points": 3,
                                  "status": "Done", "flagged": False, "summary": "Work item PROJ-1",
                                  "description": "What PROJ-1 changes."})

    def test_carried_in_marks_the_work_of_the_previous_sprint(self):
        # PROJ-2 was carried over from Sprint 6 in its original spell, not in its later extra one.
        self.assertEqual({(t["key"], t["scope"], t["carried_in"]) for t in self.tickets()}, {
            ("PROJ-1", "original", False), ("PROJ-2",
                                            "original", True), ("PROJ-2", "extra", False),
            ("PROJ-3", "extra", False), ("PROJ-6", "original", False)})

    def test_long_descriptions_come_as_a_first_chunk_with_their_count(self):
        data = fixture.sprint_data()
        long = "\n".join(f"Line {n} of the description." for n in range(200))
        epic = data["epics"][0]
        epic["scope_groups"]["completed"][0]["description"] = long
        epic["description"] = long
        brief = make_brief.build_brief(data)
        first = brief["epics"][0]["tickets"][0]
        pieces = common.chunks(long)
        self.assertGreater(len(pieces), 1)
        self.assertEqual((first["description"], first["description_chunks"]),
                         (pieces[0], len(pieces)))
        self.assertEqual(brief["epics"][0]["description_chunks"], len(pieces))
        # A short description has no count.
        short = next(t for t in self.tickets() if t["key"] == "PROJ-3")
        self.assertNotIn("description_chunks", short)

    def test_goal_tickets_include_all_original_outcomes(self):
        tickets = self.brief["goal_tickets"]
        self.assertEqual([(t["key"], t["outcome"]) for t in tickets], [
            ("PROJ-1", "completed"), ("PROJ-2", "removed"),
            ("PROJ-4", "completed"), ("PROJ-5", "completed"), ("PROJ-6", "removed")])
        self.assertEqual(tickets[0], {
            "key": "PROJ-1", "summary": "Work item PROJ-1", "points": 3,
            "outcome": "completed", "epic_key": "PROJ-100", "epic_name": "Login <beta>"})

    def test_goal_theme_denominator_keeps_work_excluded_from_commentary(self):
        briefs = []
        for hidden_summary, expected_total in (("Search setup", 6), ("Other work", 3)):
            with self.subTest(hidden_summary=hidden_summary):
                spells = copy.deepcopy(fixture.TICKETS)
                spells[0].update(summary="Search lookup",
                                 outcome="not_completed", status="In Progress")
                spells[0]["events"] = spells[0]["events"][:-1]
                for spell in spells:
                    if spell["key"] in ("PROJ-4", "PROJ-5"):
                        spell["summary"] = hidden_summary
                data = fixture.sprint_data(spells=spells, sprint_status="active",
                                           sprint_goal="Search: ship search", today="2026-03-11")
                brief = make_brief.build_brief(data)
                theme = [t for t in brief["goal_tickets"]
                         if "Search" in t["summary"]]
                total = sum(t["points"] for t in theme)
                open_points = sum(t["points"]
                                  for t in theme if t["outcome"] == "not_completed")
                self.assertEqual((open_points, total), (3, expected_total))
                self.assertEqual(open_points > total / 2,
                                 hidden_summary == "Other work")
                briefs.append(
                    {k: v for k, v in brief.items() if k != "goal_tickets"})
        # Only goal_tickets tells these two sprints, with different verdicts, apart.
        self.assertEqual(briefs[0], briefs[1])

    def test_comments_only_for_blocker_candidates(self):
        # data.json's comments, on each listing of a candidate: PROJ-2 has
        # two spells.
        with_comments = [(t["key"], t["comments"])
                         for t in self.tickets() if "comments" in t]
        self.assertEqual(with_comments, [
                         ("PROJ-2", [{"date": "05/03/2026", "text": "Waiting on Security."}])] * 2)

    def test_ticket_events_once_for_each_ticket_listed(self):
        # PROJ-2 is listed twice, its events once; PROJ-4 and PROJ-5 aren't
        # listed. Status changes and pull request events only, in time order.
        self.assertEqual(list(self.brief["ticket_events"]), [
                         "PROJ-1", "PROJ-2", "PROJ-6", "PROJ-3"])
        self.assertEqual(self.brief["ticket_events"]["PROJ-1"], [
            {"date": "03/03/2026", "type": "first_pr_opened", "url": fixture.PULL},
            {"date": "04/03/2026", "type": "last_pr_merged", "url": fixture.PULL},
            {"date": "04/03/2026", "type": "status_changed", "from": "In Progress", "to": "Done"}])
        self.assertNotIn("pull_request_events", self.brief)

    def test_says_when_pull_request_events_were_not_read(self):
        brief = make_brief.build_brief(fixture.sprint_data(
            pull_request_events_read=False))
        self.assertEqual(brief["pull_request_events"],
                         make_brief.EVENTS_NOT_READ)

    def test_epics_in_order_of_completed_pts(self):
        # Commitment and extra together: the order Key Achievements takes.
        self.assertEqual([(e["key"], e["completed_pts"]) for e in self.brief["epics"]],
                         [("PROJ-100", 6), ("__no_epic__", 1)])
        self.assertEqual(
            self.brief["epics"][0]["description"], "Staff sign in with their work account.")

    def test_sprint(self):
        # Dates as the report shows them; only the verdicts the sprint allows.
        self.assertEqual(self.brief["sprint"], {
            "name": "Sprint 7", "status": "closed", "goal": "Ship login", "start": "02/03/2026",
            "end": "13/03/2026", "today": "16/03/2026",
            "goal_verdicts": ["Fully met", "Partially met", "Not met"]})

    def test_goal_and_verdicts_of_a_running_sprint(self):
        # The goal as Jira holds it, one string whose lines are its themes.
        brief = make_brief.build_brief(fixture.sprint_data(
            sprint_status="active", sprint_goal="Ship login\n\n  Fix export \n", today="2026-03-05"))
        self.assertEqual(brief["sprint"]["goal"],
                         "Ship login\n\n  Fix export \n")
        self.assertEqual(brief["sprint"]["goal_verdicts"], [
                         "Too early to tell"])

    def test_report_facts_are_the_reports_own_wording(self):
        # The retro notes quote them, so they must match the report word for
        # word, without its links.
        facts = self.brief["report_facts"]
        self.assertEqual(
            facts[0], "Sprint target completion: 60%, 3/5 tickets (6/10 pts) completed")
        self.assertTrue(facts[1].startswith("Of the 5 tickets"), facts[1])
        self.assertNotIn("](", facts[1])
        self.assertEqual(facts[2:], ["PROJ-100: Login <beta> completed 60%, 3/5 tickets (6/10 pts) of its commitment",
                                     "PROJ-100: Login <beta> completed 0/1 ticket (0/2 pts) of its extra work",
                                     "(no epic) completed 1/1 ticket (1/1 pts) of its extra work"])


class HelpersTest(unittest.TestCase):
    def test_brief_comments(self):
        # Dated as the brief dates everything; a comment Jira gives no date
        # keeps its text.
        cases = [
            ("none", [], []),
            ("dated", [{"at": "2026-03-05T23:30:00.000+0000", "date": "2026-03-06", "text": "Blocked."}],
             [{"date": "06/03/2026", "text": "Blocked."}]),
            ("no date", [{"at": None, "date": None, "text": "Unblocked."}],
             [{"date": None, "text": "Unblocked."}]),
        ]
        for name, comments, expected in cases:
            with self.subTest(name):
                self.assertEqual(make_brief.brief_comments(comments), expected)


if __name__ == "__main__":
    unittest.main()
