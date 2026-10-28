"""Unit tests for skills/agentic-manager-utils-lib/agentic_manager/ticket_pulls.py.
Run with: python3 tests/run.py agentic-manager-utils-lib

gh answers from a fake runner, so nothing reaches GitHub, and Jira from a
fake client, its panels written as JiraClient returns them.
"""

import os
import subprocess
import sys
import unittest

# tests/<skill>/ mirrors skills/<skill>/.
TEST_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(TEST_DIR))
sys.path.insert(0, os.path.join(
    REPO_ROOT, "skills", os.path.basename(TEST_DIR)))
from agentic_manager import ticket_pulls  # noqa: E402
from agentic_manager.jira import PANEL_LIMIT  # noqa: E402
sys.path.insert(0, TEST_DIR)
from gh_fake import graphql_answer  # noqa: E402


PR = "https://github.com/acme/api/pull/{}"


class gh:
    """A runner that answers gh's GraphQL calls from `events`, each pull
    request's by its URL, and records each command; GitHub can't resolve
    one `events` hasn't."""

    def __init__(self, events):
        self.events, self.calls = events, []

    def __call__(self, command, **kwargs):
        self.calls.append(command)
        return subprocess.CompletedProcess(command, *graphql_answer(command[1:], self.events.get))


class Panels:
    """A Jira client whose Development panel lists, by issue id, `pulls`, and
    whose search by parent finds `subtasks`, recording each read."""

    def __init__(self, pulls, subtasks=()):
        self.pulls, self.subtasks, self.read = pulls, subtasks, []

    def search(self, jql, fields):
        self.read.append(("search", jql))
        return list(self.subtasks)

    def pull_requests(self, issue_id):
        self.read.append(("pulls", issue_id))
        return self.pulls.get(issue_id, [])


def sub_task(key, parent):
    return {"id": key, "key": key, "fields": {"parent": {"key": parent}}}


class TicketPullsTest(unittest.TestCase):
    def test_panel_pulls(self):
        panel = [{"url": PR.format(41), "status": "MERGED", "source": {"branch": "x"},
                  "lastUpdate": "2026-10-10T08:00:00.000+0000"},
                 {"url": "https://bitbucket.org/acme/api/pull-requests/3"}]
        self.assertEqual(ticket_pulls.panel_pulls(panel), [
            {**panel[0], "state": "MERGED",
                "updatedAt": "2026-10-10T08:00:00.000+0000"},
            {**panel[1], "state": "?", "updatedAt": None}])

    def test_pulls_by_ticket(self):
        # A ticket's pull requests are those of its panel and its
        # sub-tasks', each once, through the ticket before its sub-tasks,
        # those in key order, with the issue it came through.
        issues = [{"id": "1", "key": "PROJ-1"}, {"id": "2", "key": "PROJ-2"},
                  {"id": "3", "key": "PROJ-3"}]
        # PROJ-12 and PROJ-11 are sub-tasks of PROJ-1, PROJ-21 of PROJ-2,
        # found by the search out of key order.
        subtasks = [sub_task("PROJ-12", "PROJ-1"), sub_task("PROJ-21", "PROJ-2"),
                    sub_task("PROJ-11", "PROJ-1")]
        # name: (the panels' pull requests by issue id, {key: [(number, via)]})
        cases = [
            ("none listed", {}, {"PROJ-1": [], "PROJ-2": [], "PROJ-3": []}),
            ("the ticket's own", {"3": [{"url": PR.format(42)}, {"url": PR.format(44)}]},
             {"PROJ-1": [], "PROJ-2": [], "PROJ-3": [(42, "PROJ-3"), (44, "PROJ-3")]}),
            ("only through a sub-task", {"PROJ-21": [{"url": PR.format(43)}]},
             {"PROJ-1": [], "PROJ-2": [(43, "PROJ-21")], "PROJ-3": []}),
            ("on the ticket and a sub-task: kept once, through the ticket",
             {"1": [{"url": PR.format(
                 41)}], "PROJ-11": [{"url": PR.format(41)}, {"url": PR.format(44)}]},
             {"PROJ-1": [(41, "PROJ-1"), (44, "PROJ-11")], "PROJ-2": [], "PROJ-3": []}),
            ("sub-tasks in key order", {"PROJ-12": [{"url": PR.format(41)}], "PROJ-11": [{"url": PR.format(41)}]},
             {"PROJ-1": [(41, "PROJ-11")], "PROJ-2": [], "PROJ-3": []}),
        ]
        for name, pulls, expected in cases:
            with self.subTest(name):
                client = Panels(pulls, subtasks)
                found = ticket_pulls.pulls_by_ticket(client, issues)
                self.assertEqual({key: [(int(pr["url"].rsplit("/", 1)[1]), pr["via"]) for pr in prs]
                                  for key, prs in found.items()}, expected)
                self.assertEqual(list(found), ["PROJ-1", "PROJ-2", "PROJ-3"])
                # One search for every ticket's sub-tasks, and every panel of
                # a ticket and its sub-tasks read.
                self.assertEqual([r for r in client.read if r[0] == "search"],
                                 [("search", "parent in (PROJ-1,PROJ-2,PROJ-3) AND issuetype in subTaskIssueTypes()")])
                self.assertEqual({r[1] for r in client.read if r[0] == "pulls"},
                                 {"1", "2", "3", "PROJ-11", "PROJ-12", "PROJ-21"})
        # No tickets: no search.
        with self.subTest("no tickets"):
            client = Panels({"1": [{"url": PR.format(41)}]}, subtasks)
            self.assertEqual(ticket_pulls.pulls_by_ticket(client, []), {})
            self.assertEqual(client.read, [])

    def test_full_panels(self):
        # A ticket whose panel, or a sub-task's, lists PANEL_LIMIT pull
        # requests may have more: it is reported, in the tickets' order, and
        # its pull requests are those found, as pulls_by_ticket() gives them.
        issues = [{"id": "1", "key": "PROJ-1"}, {"id": "2", "key": "PROJ-2"}]
        subtasks = [sub_task("PROJ-21", "PROJ-2")]
        full = [{"url": PR.format(100 + n)} for n in range(PANEL_LIMIT)]
        # name: (the panels' pull requests by issue id, the full panels' tickets)
        cases = [("none full", {"1": full[1:], "PROJ-21": full[1:]}, []),
                 ("the ticket's own", {"2": full, "1": full[:3]}, ["PROJ-2"]),
                 ("a sub-task's", {"PROJ-21": full}, ["PROJ-2"]),
                 ("both tickets", {"PROJ-21": full, "1": full}, ["PROJ-1", "PROJ-2"])]
        for name, pulls, expected in cases:
            with self.subTest(name):
                found, panels = ticket_pulls.pulls_and_full_panels(
                    Panels(pulls, subtasks), issues)
                self.assertEqual(panels, expected)
                # Every pull request a full panel listed is kept.
                self.assertEqual({key: len(prs) for key, prs in found.items()},
                                 {"PROJ-1": len(pulls.get("1", [])),
                                  "PROJ-2": len({pr["url"] for panel in ("2", "PROJ-21") for pr in pulls.get(panel, [])})})

    def test_first_found(self):
        first = [{"url": PR.format(41), "via": "PROJ-1"}]
        second = [{"url": PR.format(41), "via": "PROJ-11"},
                  {"url": PR.format(47), "via": "PROJ-11"}]
        third = [{"url": PR.format(60), "via": "PROJ-12"},
                 {"url": PR.format(47), "via": "PROJ-12"}]
        self.assertEqual(ticket_pulls.first_found(first, second, third),
                         [first[0], second[1], third[0]])

    def test_read_events(self):
        events = {"url": PR.format(41), "state": "MERGED", "createdAt": "2026-10-01T08:00:00Z",
                  "mergedAt": "2026-10-10T08:00:00Z"}
        run = gh({PR.format(41): events})
        pulls = [{"url": PR.format(41)}, {"url": PR.format(41)},
                 {"url": "https://bitbucket.org/acme/api/pull-requests/3"}]
        # Each pull request on GitHub once, in one GraphQL call; one
        # elsewhere isn't asked about.
        self.assertEqual(ticket_pulls.read_events(pulls, run),
                         ({PR.format(41): events}, {}))
        self.assertEqual(len(run.calls), 1)
        # One GitHub says doesn't exist is returned apart, with its words.
        self.assertEqual(ticket_pulls.read_events(pulls + [{"url": PR.format(47)}], run),
                         ({PR.format(41): events}, {PR.format(47): f"{PR.format(47)}: Could not resolve to a "
                                                    "PullRequest with the number of 47."}))
        self.assertEqual(len(run.calls), 2)


if __name__ == "__main__":
    unittest.main()
