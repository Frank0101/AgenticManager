"""Unit tests for skills/agentic-manager-jira-sprint-report/scripts/make_brief.py, on the
hand-written sprint in report_fixture.py.
Run with: python3 tests/run.py agentic-manager-jira-sprint-report
"""

import copy
import json
import os
import sys
import tempfile
import unittest
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import report_fixture as fixture  # noqa: E402,F401  (puts the scripts on the path)
import make_brief  # noqa: E402


class BriefTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.makedirs(os.path.join(self.tmp.name, "comments"))
        with open(os.path.join(self.tmp.name, "comments", "PROJ-2.json"), "w", encoding="utf-8") as f:
            json.dump([{"created": "2026-03-05T10:00:00.000+0000", "author": {"displayName": "Alex Example"},
                        "body": "Waiting on Security."},
                       {"created": "2026-03-06T10:00:00.000+0000", "body": ""}], f)
        self.data = fixture.sprint_data()
        self.brief = make_brief.build_brief(self.data, self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

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
        # PROJ-2 is carried over from Sprint 6, in both its original and extra spells.
        self.assertEqual({(t["key"], t["carried_in"]) for t in self.tickets()}, {
            ("PROJ-1", False), ("PROJ-2", True), ("PROJ-3", False), ("PROJ-6", False)})

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
                brief = make_brief.build_brief(data, self.tmp.name)
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
        # The old brief could not distinguish these different required verdicts.
        self.assertEqual(briefs[0], briefs[1])

    def test_comments_only_for_blocker_candidates_without_authors(self):
        # AI text names teams, never colleagues, so authors stay out; an empty
        # comment says nothing.
        with_comments = {t["key"]: t["comments"]
                         for t in self.tickets() if "comments" in t}
        self.assertEqual(with_comments, {
                         "PROJ-2": [{"date": "05/03/2026", "text": "Waiting on Security."}]})

    def test_epics_in_order_of_completed_pts(self):
        # Commitment and extra together: the order Key Achievements takes.
        self.assertEqual([(e["key"], e["completed_pts"]) for e in self.brief["epics"]],
                         [("PROJ-100", 6), ("__no_epic__", 1)])
        self.assertEqual(
            self.brief["epics"][0]["description"], "Staff sign in with their work account.")

    def test_sprint(self):
        # Dates as the report shows them; only the verdicts the sprint allows.
        self.assertEqual(self.brief["sprint"], {
            "name": "Sprint 7", "status": "closed", "goal": ["Ship login"], "start": "02/03/2026",
            "end": "13/03/2026", "today": "16/03/2026",
            "goal_verdicts": ["Fully met", "Partially met", "Not met"]})

    def test_goal_lines_and_verdicts_of_a_running_sprint(self):
        # A goal over several lines is a list of themes, blank lines dropped.
        brief = make_brief.build_brief(fixture.sprint_data(
            sprint_status="active", sprint_goal="Ship login\n\n  Fix export \n", today="2026-03-05"), self.tmp.name)
        self.assertEqual(brief["sprint"]["goal"], ["Ship login", "Fix export"])
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
        self.assertEqual(facts[2:], ["PROJ-100: Login <beta> completed 3/5 tickets (6/10 pts) of its commitment",
                                     "PROJ-100: Login <beta> completed 0/1 ticket (0/2 pts) of its extra work",
                                     "(no epic) completed 1/1 ticket (1/1 pts) of its extra work"])


class HelpersTest(unittest.TestCase):
    def test_comments(self):
        # No file means no comments; a comment Jira gives no date keeps its
        # text, and one with no text is dropped. Dates are in the reporting
        # timezone, as every other date: 23:30 UTC is the next day in Rome.
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        os.makedirs(os.path.join(tmp.name, "comments"))
        cases = [
            ("no file", None, []),
            ("no date", [{"body": "Unblocked."}], [
             {"date": None, "text": "Unblocked."}]),
            ("blank text", [
             {"created": "2026-03-05T10:00:00.000+0000", "body": "  "}], []),
            ("late in the day", [{"created": "2026-03-05T23:30:00.000+0000", "body": "Blocked."}],
             [{"date": "06/03/2026", "text": "Blocked."}]),
            ("deadline in ADF", [{"created": "2026-03-05T10:00:00.000+0000", "body": {
                "type": "paragraph", "content": [
                    {"type": "text", "text": "Blocked until "},
                    {"type": "date", "attrs": {"timestamp": "1772755200000"}},
                    {"type": "text", "text": "."}]}}],
             [{"date": "05/03/2026", "text": "Blocked until 06/03/2026."}]),
            ("date-only ADF", [{"body": {"type": "date", "attrs": {"timestamp": "1772755200000"}}}],
             [{"date": None, "text": "06/03/2026"}]),
        ]
        for number, (name, values, expected) in enumerate(cases, start=1):
            with self.subTest(name):
                key = f"PROJ-{number}"
                if values is not None:
                    with open(os.path.join(tmp.name, "comments", f"{key}.json"), "w", encoding="utf-8") as f:
                        json.dump(values, f)
                self.assertEqual(make_brief.comments(
                    tmp.name, key, ZoneInfo("Europe/Rome")), expected)

    def test_plain(self):
        # Report text as a reader sees it: link text without its URL, no HTML,
        # and table pipes unescaped.
        cases = [("[PROJ-1](https://acme.test/browse/PROJ-1) (3 pts)", "PROJ-1 (3 pts)"),
                 ('Goal <sup style="x">[AI Gen.]</sup>', "Goal [AI Gen.]"),
                 ("Login \\| Search", "Login | Search")]
        for markdown, expected in cases:
            with self.subTest(markdown):
                self.assertEqual(make_brief.plain(markdown), expected)


if __name__ == "__main__":
    unittest.main()
