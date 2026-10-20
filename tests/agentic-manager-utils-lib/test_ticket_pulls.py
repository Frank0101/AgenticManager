"""Unit tests for skills/agentic-manager-utils-lib/agentic_manager/ticket_pulls.py.
Run with: python3 tests/run.py agentic-manager-utils-lib

gh answers from a fake runner, by the command after gh, so nothing reaches
GitHub; the panel's answers are written as JiraClient returns them. A
command the fake has no answer for fails.
"""

import json
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
from agentic_manager.github import GhError  # noqa: E402
from agentic_manager.ticket_pulls import COMMITS, PANEL, SEARCH  # noqa: E402
from agentic_manager import retry  # noqa: E402
sys.path.insert(0, TEST_DIR)
from gh_fake import graphql_answer, is_graphql  # noqa: E402


# Retries wait for real; here they needn't.
retry.RETRY_WAITS = (0, 0, 0)


PR = "https://github.com/acme/api/pull/{}"
REFUSED = "HTTP 401: Bad credentials"


class gh:
    """A runner that answers gh's commands from `answers`, by the words after
    gh up to the first option, a GraphQL call by each pull request's
    "pr view <url>", and records each command; a command it has no answer
    for fails with REFUSED on stderr."""

    def __init__(self, answers):
        self.answers, self.calls = answers, []

    def __call__(self, command, **kwargs):
        self.calls.append(command)
        if is_graphql(command[1:]):
            return subprocess.CompletedProcess(command, *graphql_answer(
                command[1:], lambda url: self.answers.get(f"pr view {url}")))
        words = []
        for word in command[1:]:
            if word.startswith("--"):
                break
            words.append(word)
        answer = self.answers.get(" ".join(words))
        if answer is None:
            return subprocess.CompletedProcess(command, 1, "", REFUSED)
        return subprocess.CompletedProcess(command, 0, json.dumps(answer), "")


def search_hit(number, title, body=""):
    return {"url": PR.format(number), "state": "open", "title": title, "body": body,
            "updatedAt": "2026-10-12T08:00:00Z"}


class TicketPullsTest(unittest.TestCase):
    def test_panel_pulls(self):
        panel = [{"url": PR.format(41), "status": "MERGED", "source": {"branch": "x"},
                  "lastUpdate": "2026-10-10T08:00:00.000+0000"},
                 {"url": "https://bitbucket.org/acme/api/pull-requests/3"}]
        self.assertEqual(ticket_pulls.panel_pulls(panel), [
            {**panel[0], "state": "MERGED",
                "updatedAt": "2026-10-10T08:00:00.000+0000", "found": PANEL},
            {**panel[1], "state": "?", "updatedAt": None, "found": PANEL}])

    def test_panel_commits(self):
        repositories = [{"name": "acme/api", "commits": [{"id": "c1"}, {"id": "c2"}]},
                        {"name": "acme/web", "commits": None}, {"name": "acme/ops"}]
        self.assertEqual(ticket_pulls.panel_commits(repositories),
                         [(repositories[0], {"id": "c1"}), (repositories[0], {"id": "c2"})])

    def test_holding_pulls(self):
        api = {"name": "acme/api"}
        run = gh({"api repos/acme/api/commits/c1/pulls": [{"url": PR.format(41), "state": "MERGED"}],
                  "api repos/acme/api/commits/c2/pulls": []})
        c1, c2, c3 = (api, {"id": "c1"}), (api, {
            "id": "c2"}), (api, {"id": "c3"})
        merged = [{"url": PR.format(41), "state": "MERGED", "found": COMMITS}]
        # In the order of the commits: found, in none, and those gh can't
        # tell about apart, never read as in no pull request.
        held, failures = ticket_pulls.holding_pulls([c1, c3, c2], run)
        self.assertEqual(held, [(c1, merged), (c2, [])])
        self.assertEqual([(pair, failed.message) for pair, failed in failures],
                         [(c3, REFUSED)])
        self.assertEqual(ticket_pulls.holding_pull(c2, run), [])
        with self.assertRaisesRegex(GhError, "Bad credentials"):
            ticket_pulls.holding_pull(c3, run)

    def test_search_pulls(self):
        # name: (gh's hits, the URLs found)
        cases = [
            ("title", [search_hit(47, "PROJ-123 Backoff")], [PR.format(47)]),
            ("in brackets", [search_hit(48, "[PROJ-123] Jitter")],
             [PR.format(48)]),
            # A key only in the description is a mention, never a match.
            ("body only", [search_hit(
                49, "Tune the backoff", "Follow-up to PROJ-123.")], []),
            ("longer key", [search_hit(50, "PROJ-1234 Other")], []),
            ("no title", [{"url": PR.format(51), "state": "open"}], []),
        ]
        for name, hits, expected in cases:
            with self.subTest(name):
                found, failures = ticket_pulls.search_pulls(
                    "PROJ-123", {"acme"}, gh({"search prs PROJ-123": hits}))
                self.assertEqual(
                    ([pr["url"] for pr in found], failures), (expected, []))
                self.assertTrue(all(pr["found"] == SEARCH and pr["state"] == "OPEN"
                                    for pr in found))
        # Every owner is searched, in order, and a pull request found twice
        # is listed once; gh answering no hit finds nothing, and an owner gh
        # can't search is a failure, the others still searched.
        run = gh({"search prs PROJ-123": [search_hit(47, "PROJ-123 Backoff")]})
        found, failures = ticket_pulls.search_pulls(
            "PROJ-123", {"acme-labs", "acme"}, run)
        self.assertEqual((len(found), failures), (1, []))
        self.assertEqual([c[c.index("--owner") + 1]
                         for c in run.calls], ["acme", "acme-labs"])
        self.assertEqual(ticket_pulls.search_pulls(
            "PROJ-123", {"acme"}, gh({"search prs PROJ-123": []})), ([], []))

        class by_owner(gh):
            def __call__(self, command, **kwargs):
                answer = self.answers.get(
                    command[command.index("--owner") + 1])
                if answer is None:
                    return subprocess.CompletedProcess(command, 1, "", REFUSED)
                return subprocess.CompletedProcess(command, 0, json.dumps(answer), "")
        found, failures = ticket_pulls.search_pulls(
            "PROJ-123", {"acme", "acme-labs"}, by_owner({"acme-labs": [search_hit(47, "PROJ-123 Backoff")]}))
        self.assertEqual([pr["url"] for pr in found], [PR.format(47)])
        self.assertEqual([(owner, failed.message) for owner, failed in failures],
                         [("acme", REFUSED)])

    def test_first_found(self):
        panel = [{"url": PR.format(41), "found": PANEL}]
        search = [{"url": PR.format(41), "found": SEARCH},
                  {"url": PR.format(47), "found": SEARCH}]
        commits = [{"url": PR.format(60), "found": COMMITS},
                   {"url": PR.format(47), "found": COMMITS}]
        self.assertEqual(ticket_pulls.first_found(panel, search, commits),
                         [panel[0], search[1], commits[0]])

    def test_read_events(self):
        events = {"url": PR.format(41), "state": "MERGED", "createdAt": "2026-10-01T08:00:00Z",
                  "mergedAt": "2026-10-10T08:00:00Z"}
        run = gh({f"pr view {PR.format(41)}": events})
        pulls = [{"url": PR.format(41)}, {"url": PR.format(41)},
                 {"url": "https://bitbucket.org/acme/api/pull-requests/3"}]
        # Each pull request on GitHub once, in one GraphQL call; one
        # elsewhere isn't asked about.
        self.assertEqual(ticket_pulls.read_events(pulls, run),
                         ({PR.format(41): events}, []))
        self.assertEqual(len(run.calls), 1)
        # One GitHub can't resolve is a failure, the others still read.
        found, failures = ticket_pulls.read_events(
            pulls + [{"url": PR.format(47)}], run)
        self.assertEqual(found, {PR.format(41): events})
        self.assertEqual([(url, failed.message) for url, failed in failures],
                         [(PR.format(47), f"{PR.format(47)}: Could not resolve to a PullRequest with the number "
                           "of 47.")])
        self.assertEqual(len(run.calls), 2)


if __name__ == "__main__":
    unittest.main()
