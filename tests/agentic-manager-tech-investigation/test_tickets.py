"""Unit tests for skills/agentic-manager-tech-investigation/scripts/tickets.py.
Run with: python3 tests/run.py agentic-manager-tech-investigation

The ticket is read from a fake client and gh answers from a fake runner, so
nothing reaches Jira or GitHub.
"""

import json
import os
import subprocess
import sys
import unittest

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(TEST_DIR))
sys.path.insert(0, os.path.join(REPO_ROOT, "skills",
                os.path.basename(TEST_DIR), "scripts"))
import tickets  # noqa: E402
from common import NotFound  # noqa: E402

PR = "https://github.com/acme/api/pull/{}"
SITE = {"criteria": "customfield_9", "sprint": "customfield_7"}
NO_FIELDS = {"criteria": None, "sprint": None}


def issue(key, kind="Story", status="To Do", summary="Something", **fields):
    return {"id": "1", "key": key, "fields": {"issuetype": {"name": kind}, "status": {"name": status},
                                              "summary": summary, **fields}}


def commit(sha, message):
    return {"id": sha, "displayId": sha[:2], "message": message, "authorTimestamp": "2026-10-08T08:00:00.000+0000",
            "url": f"https://github.com/acme/api/commit/{sha}"}


class FakeClient:
    """The client calls tickets.py makes, answering for ticket PROJ-123 (asked
    as OLD-9, its key before it moved)."""
    base_url = "https://acme.atlassian.net"

    def issue(self, key, fields):
        if key == "PROJ-404":
            raise NotFound("/rest/api/3/issue/PROJ-404")
        description = {"type": "doc", "content": [{"type": "paragraph", "content": [
            {"type": "text", "text": "See the design",
             "marks": [{"type": "link", "attrs": {"href": "https://acme.test/design"}}]}]}]}
        return issue("PROJ-123", status="In Progress", summary="Retry failed payments",
                     parent=issue("PROJ-100", "Epic",
                                  "In Progress", "Payments resilience"),
                     created="2026-09-02T10:00:00.000+0100", updated="2026-10-11T09:00:00.000+0100",
                     resolutiondate=None, labels=["payments"], fixVersions=[], assignee={"displayName": "Sam Example"},
                     description=description, customfield_9="Retries stop after 3 attempts",
                     customfield_7=[{"name": "PROJ Sprint 12", "state": "active", "goal": "Ship\n\nretries"},
                                    {"name": "PROJ Sprint 11", "state": "closed"}],
                     issuelinks=[{"type": {"outward": "blocks", "inward": "is blocked by"},
                                  "outwardIssue": issue("PROJ-130", summary="Switch the gateway")}])

    def search(self, jql, fields):
        assert jql == "parent = PROJ-123 ORDER BY key", jql
        return [issue("PROJ-124", "Sub-task", "Done", "Add the retry worker")]

    def comments(self, key):
        return [{"created": "2026-09-05T10:00:00.000+0100", "author": {"displayName": "Alex Example"},
                 "body": "Agreed: retry three times.\nThen dead-letter."}]

    def pull_requests(self, issue_id):
        return [{"url": PR.format(41), "status": "MERGED", "source": {"branch": "PROJ-123-retry"},
                 "destination": {"branch": "main"}, "lastUpdate": "2026-10-10T08:00:00.000+0000"}]

    def commits(self, issue_id):
        # c1 is in #41, c4 in #47, c2 in #60, which Jira doesn't link; c3
        # reached main in no pull request; c5 is on no branch any more; gh
        # can't tell c6's branch.
        return [{"name": "acme/api", "commits": [commit("c1", "PROJ-123 Add the worker"),
                                                 commit(
                                                     "c2", "PROJ-123 Hotfix\n\nDetails."),
                                                 commit(
                                                     "c3", "PROJ-123 Tweak on main"),
                                                 commit(
                                                     "c4", "PROJ-123 Backoff"),
                                                 commit(
                                                     "c5", "PROJ-123 Draft"),
                                                 commit("c6", "PROJ-123 Unknown")]}]

    def remote_links(self, key):
        return [{"object": {"title": "Retry design", "url": "https://acme.test/design"}}]

    def field_changes(self, key, fields):
        assert fields == {"status": "status", "sprint": "Sprint"}, fields
        return [{"created": "2026-09-03T10:00:00.000+0100", "field": "sprint", "fromString": None,
                 "toString": "PROJ Sprint 11"},
                {"created": "2026-09-10T10:00:00.000+0100", "field": "status", "fromString": "To Do",
                 "toString": "In Progress"}]


class gh:
    """A runner that answers gh's commands from `answers`, by their first two
    words (a pull request's view by its URL), and records each command."""

    def __init__(self, answers):
        self.answers, self.calls = answers, []

    def __call__(self, command, **kwargs):
        self.calls.append(command)
        answer = self.answers.get(" ".join(command[1:3]))
        if isinstance(answer, dict) and command[1:3] == ["pr", "view"]:
            answer = answer.get(command[3])
        return subprocess.CompletedProcess(command, 0 if answer is not None else 1,
                                           json.dumps(answer) if answer is not None else "")


DETAIL = {"mergeCommit": {"oid": "m41"}, "mergedAt": "2026-10-10T08:00:00Z", "baseRefName": "main",
          "headRefName": "x", "changedFiles": 2, "files": [{"path": "worker.py"}, {"path": "queue.py"}],
          "commits": [{"oid": "c1"}]}
SEARCH = [{"url": PR.format(41), "state": "MERGED", "title": "PROJ-123 Retry", "body": ""},
          {"url": PR.format(47), "state": "OPEN", "title": "Backoff",
           "body": "Part of PROJ-123.", "updatedAt": "2026-10-12T08:00:00Z"},
          {"url": PR.format(48), "state": "MERGED", "title": "[PROJ-123] Jitter", "body": "",
           "updatedAt": "2026-10-11T08:00:00Z"},
          {"url": PR.format(50), "state": "OPEN", "title": "PROJ-1234 Other", "body": ""}]
GH = {"search prs": SEARCH,
      "pr view": {PR.format(41): DETAIL,
                  PR.format(47): {**DETAIL, "mergeCommit": None, "headRefName": "backoff", "commits": [{"oid": "c4"}]},
                  PR.format(48): {**DETAIL, "mergeCommit": {"oid": "m48"}, "headRefName": "jitter", "commits": []},
                  PR.format(60): {**DETAIL, "mergeCommit": {"oid": "m60"}, "headRefName": "hotfix",
                                  "commits": [{"oid": "c2"}]}},
      "api repos/acme/api/commits/c2/pulls": [{"url": PR.format(60), "state": "MERGED",
                                               "updatedAt": "2026-10-09T08:00:00Z"}],
      "api repos/acme/api/commits/c3/pulls": [], "api repos/acme/api/commits/c5/pulls": [],
      "api repos/acme/api/commits/c6/pulls": [],
      "api repos/acme/api": {"branch": "main"},
      "api repos/acme/api/compare/main...c3": {"status": "behind"},
      "api repos/acme/api/compare/main...c5": {"status": "diverged"}}


class TicketTest(unittest.TestCase):
    def test_ticket(self):
        run = gh(GH)
        text = tickets.ticket(FakeClient(), "OLD-9", SITE,
                              ["acme-labs"], True, run)
        self.assertEqual(text, "\n".join([
            "PROJ-123 · Story · In Progress · Retry failed payments · https://acme.atlassian.net/browse/PROJ-123",
            "Moved: OLD-9 is now PROJ-123",
            "Parent: PROJ-100 · Epic · In Progress · Payments resilience",
            "Created 2026-09-02 · updated 2026-10-11 · resolved none",
            "Assignee: Sam Example",
            "Labels: payments · Fix versions: none",
            "", "Description:", "  See the design (https://acme.test/design)",
            "", "Acceptance criteria:", "  Retries stop after 3 attempts",
            # A goal over several lines is printed on one.
            "", "Sprints (2):", "  PROJ Sprint 12 · active · goal: Ship retries",
            "  PROJ Sprint 11 · closed · goal: none",
            "", "History (2):", "  2026-09-03 · sprint: none → PROJ Sprint 11",
            "  2026-09-10 · status: To Do → In Progress",
            "", "Children (1):", "  PROJ-124 · Sub-task · Done · Add the retry worker",
            "", "Links (1):", "  blocks PROJ-130 · Story · To Do · Switch the gateway",
            "", "Web links (1):", "  Retry design · https://acme.test/design",
            "", "Pull requests (4):",
            "  acme/api#41 · MERGED · PROJ-123-retry → main · updated 2026-10-10 · " +
                PR.format(41),
            "      merge commit m41 on 2026-10-10 · files changed (2): worker.py, queue.py",
            # Found by gh; #50 names PROJ-1234, not PROJ-123.
            "  acme/api#47 · OPEN · backoff → main · updated 2026-10-12 · " +
                PR.format(47)
            + " · names the key, not linked in Jira",
            "      not merged · files changed (2): worker.py, queue.py",
            # A key in brackets, as titles often carry it, still names it.
            "  acme/api#48 · MERGED · jitter → main · updated 2026-10-11 · " +
                PR.format(48)
            + " · names the key, not linked in Jira",
            "      merge commit m48 on 2026-10-10 · files changed (2): worker.py, queue.py",
            "  acme/api#60 · MERGED · hotfix → main · updated 2026-10-09 · " +
                PR.format(60)
            + " · holds commits that name the key, not linked in Jira",
            "      merge commit m60 on 2026-10-10 · files changed (2): worker.py, queue.py",
            "", "Commits on the default branch in no pull request (1):",
            "  acme/api c3 · 2026-10-08 · PROJ-123 Tweak on main · https://github.com/acme/api/commit/c3",
            "  1 more in no pull request and not on the default branch, such as work rebased away before a merge",
            # Never claimed on the default branch or off it.
            "", "Commits gh couldn't check (1):",
            "  acme/api c6 · 2026-10-08 · PROJ-123 Unknown · https://github.com/acme/api/commit/c6",
            "", "Comments (1):",
            "  2026-09-05 · Alex Example: Agreed: retry three times.\n    Then dead-letter.",
        ]))
        # Searched in the owners given and those of the linked pull requests.
        owners = [c[c.index("--owner") + 1]
                  for c in run.calls if c[1:3] == ["search", "prs"]]
        self.assertEqual(owners, ["acme", "acme-labs"])

    def test_without_gh_and_failures(self):
        # name: (gh available, runner, expected lines)
        cases = [
            ("no gh", False, gh({}), [
                "  gh isn't available or github-cli isn't enabled: merge commits, files changed and pull requests "
                "that name the key without being linked in Jira weren't read",
                "Commits, those in pull requests not told apart without gh (6):",
                "  acme/api c2 · 2026-10-08 · PROJ-123 Hotfix · https://github.com/acme/api/commit/c2"]),
            # A commit gh can't look up is never said to be in no pull request.
            ("gh fails", True, gh({}), [
                "      gh couldn't read it", "Commits on the default branch in no pull request (0):",
                "Commits gh couldn't check (6):",
                "  acme/api c1 · 2026-10-08 · PROJ-123 Add the worker · https://github.com/acme/api/commit/c1"]),
        ]
        for name, available, run, expected in cases:
            with self.subTest(name):
                text = tickets.ticket(
                    FakeClient(), "PROJ-123", NO_FIELDS, [], available, run)
                for wanted in expected:
                    self.assertIn(wanted, text.split("\n"))
                self.assertNotIn("Acceptance criteria:", text)
                self.assertIn("Sprints (0):", text)
                if not available:
                    self.assertEqual(run.calls, [])
        self.assertEqual(tickets.ticket(FakeClient(), "PROJ-404", NO_FIELDS, [], False),
                         "PROJ-404: Jira has no such ticket, or this account can't see it")

    def test_pr_discussion(self):
        run = gh({"pr view": {PR.format(41): {
            "title": "PROJ-123 Retry", "state": "MERGED", "author": {"login": "sam"}, "body": "Why:\n\nretries.",
            "createdAt": "2026-10-01T08:00:00Z", "mergedAt": "2026-10-10T08:00:00Z", "baseRefName": "main",
            "headRefName": "PROJ-123-retry", "mergeCommit": {"oid": "m41"},
            "reviews": [{"author": {"login": "alex"}, "state": "CHANGES_REQUESTED", "body": "Cap the backoff.",
                         "submittedAt": "2026-10-02T08:00:00Z"},
                        {"author": {"login": "alex"}, "state": "APPROVED", "body": "", "submittedAt": "2026-10-03T08:00:00Z"}],
            "comments": [{"author": {"login": "bot"}, "body": "Checks passed", "createdAt": "2026-10-01T09:00:00Z"}]}},
            # Two pages, as gh's --slurp gives them.
            "api repos/acme/api/pulls/41/comments?per_page=100": [
                [{"path": "worker.py", "line": 12, "user": {"login": "alex"}, "created_at": "2026-10-02T08:00:00Z",
                  "body": "Why 3?\nSay so."}],
                [{"path": "queue.py", "line": None, "original_line": 4, "user": {"login": "sam"},
                  "created_at": "2026-10-04T08:00:00Z", "body": "Done."}]]})
        self.assertEqual(tickets.pr_discussion(PR.format(41), run), "\n".join([
            "acme/api#41 · MERGED · PROJ-123 Retry · " + PR.format(41),
            "By sam · PROJ-123-retry → main · opened 2026-10-01 · merged 2026-10-10 · merge commit m41",
            "", "Description:", "  Why:", "", "  retries.",
            "", "Reviews (2):", "  2026-10-02 · alex · CHANGES_REQUESTED: Cap the backoff.",
            "  2026-10-03 · alex · APPROVED: no text",
            "", "Review comments (2):", "  2026-10-02 · alex · worker.py:12: Why 3?\n    Say so.",
            # A comment on a line the pull request changed since keeps its first line.
            "  2026-10-04 · sam · queue.py:4: Done.",
            "", "Comments (1):", "  2026-10-01 · bot: Checks passed"]))
        cases = [("https://bitbucket.org/acme/api/pull-requests/3", gh({}),
                  "https://bitbucket.org/acme/api/pull-requests/3: not a GitHub pull request"),
                 (PR.format(41), gh({}), PR.format(41) + ": gh couldn't read it")]
        for url, failing, expected in cases:
            with self.subTest(expected):
                self.assertEqual(tickets.pr_discussion(url, failing), expected)

    def test_criteria_field(self):
        # Found by its name in any case; a site without it has none.
        class Fields:
            def __init__(self, names):
                self.names = names

            def field_ids(self):
                return self.names
        cases = [({"Summary": "summary", "Acceptance Criteria": "customfield_9"}, "customfield_9"),
                 ({"Summary": "summary"}, None)]
        for names, expected in cases:
            with self.subTest(expected):
                self.assertEqual(tickets.criteria_field(
                    Fields(names)), expected)

    def test_pr_label(self):
        cases = [(PR.format(41), "acme/api#41"),
                 ("https://bitbucket.org/acme/api/pull-requests/3", "https://bitbucket.org/acme/api/pull-requests/3")]
        for url, expected in cases:
            with self.subTest(url):
                self.assertEqual(tickets.pr_label(url), expected)

    def test_search_line(self):
        cases = [(issue("PROJ-2", parent={"key": "PROJ-1"}), "PROJ-2 · Story · To Do · Something · parent PROJ-1"),
                 (issue("PROJ-1", "Epic"), "PROJ-1 · Epic · To Do · Something")]
        for found, expected in cases:
            with self.subTest(expected):
                self.assertEqual(tickets.search_line(found), expected)


if __name__ == "__main__":
    unittest.main()
