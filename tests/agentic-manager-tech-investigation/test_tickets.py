"""Unit tests for skills/agentic-manager-tech-investigation/scripts/tickets.py.
Run with: python3 tests/run.py agentic-manager-tech-investigation

The ticket is read from a fake client and gh answers from a fake runner, so
nothing reaches Jira or GitHub.
"""

import contextlib
import io
import json
import os
import subprocess
import sys
import unittest
from unittest import mock

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(TEST_DIR))
sys.path.insert(0, os.path.join(REPO_ROOT, "skills",
                os.path.basename(TEST_DIR), "scripts"))
import tickets  # noqa: E402
from common import GhError, JiraError  # noqa: E402
from agentic_manager import retry  # noqa: E402


# Retries wait for real; here they needn't.
retry.RETRY_WAITS = (0, 0, 0)


PR = "https://github.com/acme/api/pull/{}"
SITE = {"criteria": "customfield_9", "sprint": "customfield_7"}
NO_FIELDS = {"criteria": None, "sprint": None}


def issue(key, kind="Story", status="To Do", summary="Something", **fields):
    return {"id": "1", "key": key, "fields": {"issuetype": {"name": kind}, "status": {"name": status},
                                              "summary": summary, **fields}}


# Why the client reads nothing for a key, as it answers: one Jira doesn't
# have, and one of an excluded project.
UNREAD = {"PROJ-404": "PROJ-404: Jira has no such ticket, or this account can't see it",
          "EXCL-1": "EXCL-1 is of a project excluded by `excluded-projects`: it is never read"}


# The ticket's sub-task, as both the search for its children and that for
# its sub-tasks find it.
SUB_TASK = {**issue("PROJ-124", "Sub-task", "Done", "Add the retry worker",
                    parent={"key": "PROJ-123"}), "id": "124"}
# The sub-task's panel lists #41 again and #60, which only it links.
PANELS = {"1": [{"url": PR.format(41), "status": "MERGED", "source": {"branch": "PROJ-123-retry"},
                 "destination": {"branch": "main"}, "lastUpdate": "2026-10-10T08:00:00.000+0000"}],
          "124": [{"url": PR.format(41), "status": "MERGED"},
                  {"url": PR.format(60), "status": "OPEN", "source": {"branch": "PROJ-124-worker"},
                   "destination": {"branch": "main"}, "lastUpdate": "2026-10-12T08:00:00.000+0000"}]}


class FakeClient:
    """The client calls tickets.py makes, answering for ticket PROJ-123 (asked
    as OLD-9, its key before it moved), and recording each search and panel
    read."""
    base_url = "https://acme.atlassian.net"

    def __init__(self):
        self.read = []

    def issue(self, key, fields):
        if key in UNREAD:
            return None, UNREAD[key]
        if key == "PROJ-500":
            raise JiraError(
                "Jira returned 500 for /rest/api/3/issue/PROJ-500.")
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
                                  "outwardIssue": issue("PROJ-130", summary="Switch the gateway")}]), None

    def search(self, jql, fields):
        assert jql in ("parent = PROJ-123 ORDER BY key",
                       "parent in (PROJ-123) AND issuetype in subTaskIssueTypes()"), jql
        self.read.append(("search", jql))
        return [SUB_TASK]

    def comments(self, key):
        return [{"created": "2026-09-05T10:00:00.000+0100", "author": {"displayName": "Alex Example"},
                 "body": "Agreed: retry three times.\nThen dead-letter."}]

    def pull_requests(self, issue_id):
        self.read.append(("pulls", issue_id))
        return PANELS.get(issue_id, [])

    def remote_links(self, key):
        return [{"object": {"title": "Retry design", "url": "https://acme.test/design"}}]

    def field_changes(self, key, fields):
        assert fields == {"status": "status", "sprint": "Sprint"}, fields
        return [{"created": "2026-09-03T10:00:00.000+0100", "field": "sprint", "fromString": None,
                 "toString": "PROJ Sprint 11"},
                {"created": "2026-09-10T10:00:00.000+0100", "field": "status", "fromString": "To Do",
                 "toString": "In Progress"}]


# What the fake gh says for a command it has no answer for.
REFUSED = "HTTP 401: Bad credentials"


class gh:
    """A runner that answers gh's commands from `answers`, by their first two
    words (a pull request's view by its URL), and records each command; a
    command it has no answer for fails as REFUSED says."""

    def __init__(self, answers):
        self.answers, self.calls = answers, []

    def __call__(self, command, **kwargs):
        self.calls.append(command)
        answer = self.answers.get(" ".join(command[1:3]))
        if isinstance(answer, dict) and command[1:3] == ["pr", "view"]:
            answer = answer.get(command[3])
        if answer is None:
            return subprocess.CompletedProcess(command, 1, "", REFUSED + "\n")
        return subprocess.CompletedProcess(command, 0, json.dumps(answer), "")


class failing_gh(gh):
    """The runner of `GH`, but the command whose words after gh are
    `failing` fails with `message` on stderr, REFUSED by default."""

    def __init__(self, failing, message=REFUSED):
        super().__init__(GH)
        self.failing, self.message = failing, message

    def __call__(self, command, **kwargs):
        if " ".join(command[1:]).split(" --")[0] != self.failing:
            return super().__call__(command, **kwargs)
        self.calls.append(command)
        return subprocess.CompletedProcess(command, 1, "", self.message + "\n")


# What gh says when GitHub has no such pull request, and the line printed
# for it.
NO_PULL = "GraphQL: Could not resolve to a PullRequest with the number of {}. (repository.pullRequest)"


def missing(thing, words):
    return f"GitHub has no such {thing}, or this account can't see it: {words}"


DETAIL = {"mergeCommit": {"oid": "m41"}, "mergedAt": "2026-10-10T08:00:00Z", "changedFiles": 2,
          "files": [{"path": "worker.py"}, {"path": "queue.py"}],
          "commits": [{"oid": "c1", "committedDate": "2026-10-08T08:00:00Z", "messageHeadline": "Add the worker"},
                      {"oid": "c2", "committedDate": "2026-10-09T08:00:00Z", "messageHeadline": "Cap retries"}]}
GH = {"pr view": {PR.format(41): DETAIL,
                  PR.format(60): {**DETAIL, "mergeCommit": None, "changedFiles": 3, "commits": []}}}
# The pull requests printed for PROJ-123: its own, then those only its
# sub-task links, with the sub-task it came through.
PULL_LINES = [
    "Pull requests (2):",
    "  acme/api#41 · MERGED · PROJ-123-retry → main · updated 2026-10-10 · " +
    PR.format(41),
    "      merge commit m41 on 2026-10-10 · files changed (2): worker.py, queue.py",
    "      commits (2):",
    "        c1 · 2026-10-08 · Add the worker",
    "        c2 · 2026-10-09 · Cap retries",
    "  acme/api#60 · OPEN · PROJ-124-worker → main · updated 2026-10-12 · " +
    PR.format(60) + " · via PROJ-124",
    # gh lists at most 100 files: the count says how many there are.
    "      not merged · files changed (2 of 3): worker.py, queue.py",
    "      commits (0):"]


class TicketTest(unittest.TestCase):
    def test_ticket(self):
        run, client = gh(GH), FakeClient()
        text = tickets.ticket(client, "OLD-9", SITE, True, True, run)
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
            "", *PULL_LINES,
            "", "Comments (1):",
            "  2026-09-05 · Alex Example: Agreed: retry three times.\n    Then dead-letter.",
        ]))
        # The panels of the ticket and its sub-task, found by one search by
        # parent; gh only views each pull request once: no search of
        # titles, no commit's pull requests and no comparison.
        self.assertEqual(
            sorted(r[1] for r in client.read if r[0] == "pulls"), ["1", "124"])
        self.assertIn(
            ("search", "parent in (PROJ-123) AND issuetype in subTaskIssueTypes()"), client.read)
        self.assertEqual(sorted(c[3] for c in run.calls), [
                         PR.format(41), PR.format(60)])
        self.assertTrue(all(c[1:3] == ["pr", "view"]
                        for c in run.calls), run.calls)

    def test_pull_requests_only_when_asked(self):
        # Without --prs, only the ticket is read from Jira: no panel, no
        # search for sub-tasks, nothing of GitHub, and no pull request
        # section. With --prs but without gh, no panel is read either, and
        # the output says why in one line.
        # name: (prs, gh, the lines from the web links to the comments)
        web = [
            "Web links (1):", "  Retry design · https://acme.test/design", ""]
        cases = [("without --prs", False, True, web),
                 ("without --prs or gh", False, False, web),
                 ("--prs without gh", True, False,
                  [*web, "Pull requests (not read):", f"  {tickets.NO_GH}", ""])]
        for name, prs, with_gh, expected in cases:
            with self.subTest(name):
                run, client = gh(GH), FakeClient()
                lines = tickets.ticket(
                    client, "PROJ-123", NO_FIELDS, prs, with_gh, run).split("\n")
                start = lines.index("Web links (1):")
                self.assertEqual(
                    lines[start:lines.index("Comments (1):")], expected)
                self.assertEqual(
                    client.read, [("search", "parent = PROJ-123 ORDER BY key")])
                self.assertEqual(run.calls, [])
                self.assertNotIn("Acceptance criteria:", lines)
                self.assertIn("Sprints (0):", lines)

    def test_jira_answers(self):
        # A ticket Jira doesn't have, or of an excluded project, is Jira's
        # answer, said so, and the other keys still print.
        for key, expected in UNREAD.items():
            with self.subTest(key):
                self.assertEqual(tickets.ticket(
                    FakeClient(), key, NO_FIELDS, True, False), expected)
        # Any other failure is raised, with Jira's message.
        with self.assertRaisesRegex(JiraError, "Jira returned 500"):
            tickets.ticket(FakeClient(), "PROJ-500", NO_FIELDS, True, False)
        # On the command line, the answers print with the other tickets, and
        # a failure stops it, printing nothing but Jira's message.
        # name: (keys, what is printed, the message it stops with or None)
        cases = [("answers", ["PROJ-404", "PROJ-123", "EXCL-1"], None),
                 ("a failure", ["PROJ-404", "PROJ-500"], "Jira returned 500 for /rest/api/3/issue/PROJ-500.")]
        for name, keys, stop in cases:
            with self.subTest(name), mock.patch.object(tickets, "JiraClient", return_value=FakeClient()), \
                    mock.patch.object(tickets, "site_fields", return_value=NO_FIELDS), \
                    mock.patch.object(tickets, "gh_available", return_value=False), \
                    contextlib.redirect_stdout(io.StringIO()) as printed:
                if stop:
                    with self.assertRaises(SystemExit) as stopped:
                        tickets.main(["show", *keys])
                    self.assertEqual(stopped.exception.code, stop)
                    self.assertEqual(printed.getvalue(), "")
                else:
                    tickets.main(["show", *keys])
                    blocks = printed.getvalue().split("\n\n")
                    self.assertEqual(blocks[0], UNREAD["PROJ-404"])
                    self.assertEqual(blocks[-1], UNREAD["EXCL-1"] + "\n")
                    self.assertTrue(blocks[1].startswith(
                        "PROJ-123 · Story"), blocks[1])

    def test_github_has_none(self):
        # A pull request GitHub has none of is its answer: why is printed
        # where what it changed would have been, asked once, and the rest
        # still prints.
        failing = f"pr view {PR.format(60)}"
        run = failing_gh(failing, NO_PULL.format(60))
        lines = tickets.ticket(FakeClient(), "PROJ-123",
                               NO_FIELDS, True, True, run).split("\n")
        start = lines.index(PULL_LINES[0])
        self.assertEqual(lines[start:start + len(PULL_LINES) - 1],
                         [*PULL_LINES[:-2], "      " + missing("pull request", NO_PULL.format(60))])
        self.assertIn("Comments (1):", lines)
        self.assertEqual([" ".join(c[1:]).split(" --")[0]
                         for c in run.calls].count(failing), 1)

    def test_a_gh_failure_stops(self):
        # Never printed as a pull request with nothing to show: the failure
        # is raised, and the command line stops with gh's words and the
        # library's advice.
        ticket = tickets.ticket
        run = failing_gh(f"pr view {PR.format(60)}")
        with self.assertRaisesRegex(GhError, REFUSED):
            tickets.ticket(FakeClient(), "PROJ-123",
                           NO_FIELDS, True, True, run)
        with mock.patch.object(tickets, "JiraClient", return_value=FakeClient()), \
                mock.patch.object(tickets, "site_fields", return_value=NO_FIELDS), \
                mock.patch.object(tickets, "gh_available", return_value=True), \
                mock.patch.object(tickets, "ticket", side_effect=lambda client, key, site, prs, gh: ticket(
                    client, key, site, prs, gh, run)), \
                contextlib.redirect_stdout(io.StringIO()) as printed, \
                self.assertRaises(SystemExit) as stopped:
            tickets.main(["show", "PROJ-123", "--prs"])
        self.assertEqual(printed.getvalue(), "")
        self.assertRegex(str(stopped.exception.code), "^GitHub couldn't be read: gh .*: " + REFUSED +
                         r"\. Check that gh works \(gh auth status\) and run it again, or disable the "
                         "github-cli source to go on without GitHub\\.$")

    def test_command_line(self):
        # Each command reaches its function with the arguments given.
        # name: (arguments, the calls of ticket, pr_discussion and the client's search)
        client = mock.Mock(search=mock.Mock(return_value=[issue("PROJ-2")]))
        cases = [
            ("show", ["show", "PROJ-1", "PROJ-2"],
             [mock.call(client, "PROJ-1", SITE, False, True),
              mock.call(client, "PROJ-2", SITE, False, True)],
             [], []),
            ("show --prs", ["show", "PROJ-1", "--prs"],
             [mock.call(client, "PROJ-1", SITE, True, True)], [], []),
            ("pr", ["pr", PR.format(41), PR.format(47)], [],
             [mock.call(PR.format(41)), mock.call(PR.format(47))], []),
            ("search", ["search", "parent = PROJ-1"], [], [],
             [mock.call("parent = PROJ-1", tickets.LINE_FIELDS)]),
        ]
        for name, argv, shown, discussed, searched in cases:
            with self.subTest(name):
                client.search.reset_mock()
                with mock.patch.object(tickets, "JiraClient", return_value=client), \
                        mock.patch.object(tickets, "site_fields", return_value=SITE), \
                        mock.patch.object(tickets, "gh_available", return_value=True), \
                        mock.patch.object(tickets, "ticket", return_value="ticket") as ticket, \
                        mock.patch.object(tickets, "pr_discussion", return_value="discussion") as discussion, \
                        contextlib.redirect_stdout(io.StringIO()):
                    tickets.main(argv)
                self.assertCountEqual(ticket.call_args_list, shown)
                self.assertCountEqual(
                    discussion.call_args_list, discussed)
                self.assertCountEqual(client.search.call_args_list, searched)
        # GitHub isn't searched by owner any more: --owner is refused.
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as refused:
            tickets.main(["show", "PROJ-1", "--owner", "acme"])
        self.assertEqual(refused.exception.code, 2)

    def test_pr_discussion(self):
        answers = {"pr view": {PR.format(41): {
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
                  "created_at": "2026-10-04T08:00:00Z", "body": "Done."}]]}
        self.assertEqual(tickets.pr_discussion(PR.format(41), gh(answers)), "\n".join([
            "acme/api#41 · MERGED · PROJ-123 Retry · " + PR.format(41),
            "By sam · PROJ-123-retry → main · opened 2026-10-01 · merged 2026-10-10 · merge commit m41",
            "", "Description:", "  Why:", "", "  retries.",
            "", "Reviews (2):", "  2026-10-02 · alex · CHANGES_REQUESTED: Cap the backoff.",
            "  2026-10-03 · alex · APPROVED: no text",
            "", "Review comments (2):", "  2026-10-02 · alex · worker.py:12: Why 3?\n    Say so.",
            # A comment on a line the pull request changed since keeps its first line.
            "  2026-10-04 · sam · queue.py:4: Done.",
            "", "Comments (1):", "  2026-10-01 · bot: Checks passed"]))
        self.assertEqual(tickets.pr_discussion("https://bitbucket.org/acme/api/pull-requests/3", gh({})),
                         "https://bitbucket.org/acme/api/pull-requests/3: not a GitHub pull request")
        # A pull request GitHub has none of is its answer, printed with its
        # URL, whichever of its reads says so; a failure is raised, never
        # printed as the discussion.
        for failing in (f"pr view {PR.format(41)}", "api repos/acme/api/pulls/41/comments?per_page=100"):
            with self.subTest(failing):
                run = failing_gh(failing, NO_PULL.format(41))
                run.answers = answers
                self.assertEqual(tickets.pr_discussion(PR.format(41), run),
                                 f"{PR.format(41)}: {missing('pull request', NO_PULL.format(41))}")
        with self.assertRaisesRegex(GhError, REFUSED):
            tickets.pr_discussion(PR.format(41), gh({}))

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
