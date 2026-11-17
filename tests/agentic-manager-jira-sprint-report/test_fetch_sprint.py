"""Unit tests for skills/agentic-manager-jira-sprint-report/scripts/fetch_sprint.py.
Run with: python3 tests/run.py agentic-manager-jira-sprint-report

They cover the script's own logic: its arguments, the previous sprint, the
changelogs it keeps and each ticket's pull requests. The Jira calls belong to
the library's client, tested there; test_e2e_fetch.py runs the whole script
against a fake Jira.
"""

import contextlib
import io
import json
import os
import subprocess
import sys
import unittest
from unittest import mock

# tests/<skill>/ mirrors skills/<skill>/.
TEST_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(TEST_DIR))
sys.path.insert(0, os.path.join(REPO_ROOT, "skills",
                os.path.basename(TEST_DIR), "scripts"))
import fetch_sprint  # noqa: E402
from agentic_manager import retry  # noqa: E402
from agentic_manager.github import GH_BROKEN  # noqa: E402
sys.path.insert(0, TEST_DIR)
from sprint_fixture import PR  # noqa: E402
# The fake gh's GraphQL answers follow the library's query.
sys.path.insert(0, os.path.join(os.path.dirname(
    TEST_DIR), "agentic-manager-utils-lib"))
from gh_fake import graphql_answer, is_graphql, is_search, search_answer  # noqa: E402


# Retries wait for real; here they needn't.
retry.RETRY_WAITS = (0, 0, 0)


class ArgsTest(unittest.TestCase):
    def parse(self, *args):
        with mock.patch.object(sys, "argv", ["fetch_sprint.py", *args]):
            return fetch_sprint.parse_args()

    def test_arguments(self):
        # Each case is the parsed selectors, or, for arguments refused as a
        # usage error, the message: conflicting selectors fail rather than
        # one silently winning.
        cases = [
            (("--sprint-id", "7"), {"sprint_id": "7"}),
            (("--project", "PROJ", "--active"),
             {"project": "PROJ", "active": True}),
            (("--board", "42"), {"board": "42"}),
            (("--sprint-name", "Sprint 3", "--board", "42"),
             {"sprint_name": "Sprint 3", "board": "42"}),
            (("--sprint-name", "Sprint 3", "--project", "PROJ"),
             {"sprint_name": "Sprint 3", "project": "PROJ", "active": False}),
            ((), "pass exactly one of --sprint-id, --project or --board"),
            # The board whose sprint report is read, when the sprint's own fails.
            (("--sprint-id", "7", "--board", "42"),
             {"sprint_id": "7", "board": "42"}),
            (("--sprint-id", "7", "--project", "PROJ"),
             "--sprint-id can't be combined with --project"),
            (("--project", "PROJ", "--board", "42"),
             "pass exactly one of --sprint-id, --project or --board"),
            (("--sprint-name", "S", "--sprint-id", "7"),
             "--sprint-name can't be combined with --sprint-id"),
            (("--sprint-name", "PROJ Sprint 3"),
             {"sprint_name": "PROJ Sprint 3", "project": None, "board": None}),
            (("--sprint-name", "S", "--project", "PROJ", "--board", "42"),
             "--sprint-name takes at most one of --project or --board"),
            (("--sprint-name", "S", "--board", "42", "--active"),
             "--active can't be combined with --sprint-name"),
            (("--sprint-id", "7", "--active"),
             "--active can't be combined with --sprint-id"),
            # Report folders always go in the skill's output folder.
            (("--sprint-id", "7", "--out-root", "reports"),
             "unrecognized arguments: --out-root"),
        ]
        for args, expected in cases:
            with self.subTest(args=args):
                if isinstance(expected, dict):
                    parsed = self.parse(*args)
                    self.assertEqual({k: getattr(parsed, k)
                                     for k in expected}, expected)
                    continue
                err = io.StringIO()
                with contextlib.redirect_stderr(err), self.assertRaises(SystemExit) as raised:
                    self.parse(*args)
                self.assertEqual(raised.exception.code, 2)
                self.assertIn(expected, err.getvalue())


class PreviousSprintTest(unittest.TestCase):
    def test_previous_sprint(self):
        def sprint(sprint_id, start, state="closed", board=42, completed=True):
            return {"id": sprint_id, "state": state, "startDate": start and f"2026-{start}T09:00:00.000Z",
                    "completeDate": f"2026-{start}T10:00:00.000Z" if state == "closed" and completed else None,
                    "originBoardId": board}
        current = sprint(7, "03-04", state="active")
        cases = [
            ("the latest start before this one", current,
             [sprint(5, "02-04"), sprint(6, "02-18"), current], 6),
            # After a team moves board, its earlier sprints keep the old origin.
            ("from another board, after a move to this one",
             current, [sprint(6, "02-18", board=41)], 6),
            ("still running", current, [
             sprint(5, "02-04"), sprint(6, "02-18", state="active")], 5),
            ("closed without a completion date", current,
             [sprint(5, "02-04"), sprint(6, "02-18", completed=False)], 5),
            ("started after this one", current, [
             sprint(5, "02-04"), sprint(8, "03-18")], 5),
            ("none before it", current, [sprint(8, "03-18")], None),
            ("a sprint never started", sprint(
                7, None, state="active"), [sprint(6, "02-18")], None),
        ]
        for name, this, sprints, expected in cases:
            with self.subTest(name):
                previous = fetch_sprint.previous_sprint(this, sprints)
                self.assertEqual(previous and previous["id"], expected)


ACME_LABS = "https://github.com/acme-labs/web/pull/43"


class Panel:
    """A Jira client whose Development panel lists, by issue id, `pulls`, and
    whose search by parent finds no sub-tasks, recording each issue whose
    panel is read and each search. It has no other read, so the fetch can't
    look up the panel's commits. How sub-tasks' pull requests join their
    ticket's is the library's ticket_pulls.py, tested there."""

    def __init__(self, pulls):
        self.pulls, self.read = pulls, []

    def search(self, jql, fields):
        self.read.append(("search", jql))
        return []

    def pull_requests(self, issue_id):
        self.read.append(("pulls", issue_id))
        return self.pulls.get(issue_id, [])


class gh:
    """A runner that answers gh's commands from `answers`, by the words after
    gh up to the first option, a GraphQL search by the pull requests under
    "search", a GraphQL call by each pull request's "pr view <url>" and,
    when it holds "api graphql", as a whole by that; it records
    each command. A command it has no answer for fails with GitHub's rate
    limit message, as gh does, and a pull request GitHub can't resolve."""

    def __init__(self, answers):
        self.answers, self.calls = answers, []

    def __call__(self, command, **kwargs):
        self.calls.append(" ".join(command))
        if is_search(command[1:]) and "search" in self.answers:
            return subprocess.CompletedProcess(command, *search_answer(command[1:], self.answers["search"]))
        if is_graphql(command[1:]):
            if "api graphql" not in self.answers:
                return subprocess.CompletedProcess(command, *graphql_answer(
                    command[1:], lambda url: self.answers.get(f"pr view {url}")))
            answer = self.answers["api graphql"]
        else:
            words = []
            for word in command[1:]:
                if word.startswith("--"):
                    break
                words.append(word)
            answer = self.answers.get(" ".join(words))
        if answer is None:
            return subprocess.CompletedProcess(command, 1, "", LIMIT + "\n")
        return subprocess.CompletedProcess(command, 0, json.dumps(answer), "")


LIMIT = "HTTP 403: API rate limit exceeded for user ID 1."


class PullRequestsTest(unittest.TestCase):
    ISSUES = [{"id": "1", "key": "PROJ-1"}, {"id": "2", "key": "PROJ-2"},
              {"id": "3", "key": "PROJ-3"}]
    PANEL = {"1": [{"url": PR.format(41), "status": "MERGED"}],
             "2": [{"url": ACME_LABS, "status": "OPEN"}]}
    # When GitHub says each was opened, by URL.
    TIMES = {f"pr view {url}": {"createdAt": "2026-03-05T10:00:00Z"}
             for url in (PR.format(41), PR.format(42), PR.format(44), ACME_LABS)}

    def test_pull_requests(self):
        # Only the panel's, each kept as found there; a ticket whose panel
        # lists none has none, as GitHub isn't searched for more. GitHub is
        # read only for the times, in GraphQL calls.
        # name: (the panel's pull requests by issue id, {key: [url]})
        cases = [
            ("the panel's", self.PANEL,
             {"PROJ-1": [PR.format(41)], "PROJ-2": [ACME_LABS], "PROJ-3": []}),
            ("several on one ticket", {"3": [{"url": PR.format(42)}, {"url": PR.format(44)}]},
             {"PROJ-1": [], "PROJ-2": [], "PROJ-3": [PR.format(42), PR.format(44)]}),
            ("none listed", {}, {"PROJ-1": [], "PROJ-2": [], "PROJ-3": []}),
        ]
        for name, panel, expected in cases:
            with self.subTest(name):
                client = Panel(panel)
                run = gh(self.TIMES)
                found = fetch_sprint.pull_requests(
                    client, self.ISSUES, run)
                self.assertEqual({key: [pr["url"] for pr in prs]
                                  for key, prs in found["tickets"].items()}, expected)
                # Each found through the panel of its own ticket, as there
                # are no sub-tasks.
                self.assertTrue(all(pr["via"] == key
                                    for key, prs in found["tickets"].items() for pr in prs))
                self.assertEqual({r[1] for r in client.read if r[0] == "pulls"}, {
                                 "1", "2", "3"})
                # No gh call but the GraphQL reads of the times, none
                # without a pull request.
                self.assertTrue(
                    all(is_graphql(c.split()[1:]) for c in run.calls), run.calls)
                self.assertEqual(bool(run.calls), any(expected.values()))
                # GitHub's times of every pull request found.
                self.assertEqual(found["events"], {url: {"createdAt": "2026-03-05T10:00:00Z"}
                                                   for urls in expected.values() for url in urls})

    def test_a_pull_request_github_cant_find_is_skipped(self):
        # One GitHub says doesn't exist, such as one deleted that Jira still
        # links, is dropped from every ticket, so it gives no events, said
        # on stderr with the tickets it came through and kept as skipped
        # with GitHub's message; the others are kept, and the fetch goes on.
        gone = "{}: Could not resolve to a PullRequest with the number of {}."
        # name: (the panel's pull requests by issue id, those GitHub can't
        # find, {key: [url]} kept, the skipped as (url, via))
        cases = [
            ("one", self.PANEL, [ACME_LABS],
             {"PROJ-1": [PR.format(41)], "PROJ-2": [], "PROJ-3": []}, [(ACME_LABS, ["PROJ-2"])]),
            ("linked to two tickets", {**self.PANEL, "3": [{"url": PR.format(41)}, {"url": PR.format(44)}]},
             [PR.format(41)], {
                "PROJ-1": [], "PROJ-2": [ACME_LABS], "PROJ-3": [PR.format(44)]},
             [(PR.format(41), ["PROJ-1", "PROJ-3"])]),
            ("every one", self.PANEL, [PR.format(41), ACME_LABS], {"PROJ-1": [], "PROJ-2": [], "PROJ-3": []},
             [(PR.format(41), ["PROJ-1"]), (ACME_LABS, ["PROJ-2"])]),
        ]
        for name, panel, missing, kept, skipped in cases:
            with self.subTest(name), contextlib.redirect_stderr(io.StringIO()) as said:
                run = gh({k: v for k, v in self.TIMES.items()
                          if k.removeprefix("pr view ") not in missing})
                found = fetch_sprint.pull_requests(
                    Panel(panel), self.ISSUES, run)
                self.assertEqual({key: [pr["url"] for pr in prs]
                                  for key, prs in found["tickets"].items()}, kept)
                self.assertEqual(found["events"], {url: {"createdAt": "2026-03-05T10:00:00Z"}
                                                   for urls in kept.values() for url in urls})
                messages = [gone.format(url, url.rsplit("/", 1)[1])
                            for url, _ in skipped]
                self.assertEqual(found["skipped"], [{"url": url, "via": via, "message": message}
                                                    for (url, via), message in zip(skipped, messages)])
                self.assertEqual(said.getvalue(), "".join(
                    f"skipped a pull request GitHub says doesn't exist, found through {', '.join(via)}: "
                    f"{message}\n" for (_, via), message in zip(skipped, messages)))

    def test_a_gh_failure_stops(self):
        # Never taken for a pull request with no times: the fetch stops
        # instead, with the first failure's command, gh's words and the
        # library's advice. A pull request GitHub can't find beside it
        # doesn't change that, and GitHub's hourly rate limit stops at once,
        # never tried again.
        stopped = "GitHub couldn't be read, so no report was written"
        limited = f": {LIMIT} {retry.RATE_LIMITED}"
        refused = f"Resource not accessible. {GH_BROKEN}"

        def answer(*errors):
            """GitHub's answer to the GraphQL call with PR 41 (r0, p0) and
            ACME_LABS (r1, p1): each error a (pull, its type), the others read."""
            failing = dict(errors)
            return {"data": {"r0": {"p0": None if "p0" in failing else {}},
                             "r1": {"p1": None if "p1" in failing else {}}},
                    "errors": [{"type": kind, "path": [repository, pull], "message": "Resource not accessible"
                                if kind == "FORBIDDEN" else "Could not resolve to a PullRequest."}
                               for repository, pull, kind in (("r0", "p0", failing.get("p0")),
                                                              ("r1", "p1", failing.get("p1"))) if kind]}
        # name: (the gh answer to the GraphQL call, how the message starts,
        # how it ends)
        cases = [("a pull request gh can't read", answer(("p0", "FORBIDDEN")),
                  f"{stopped}: gh api graphql: {PR.format(41)}: ", refused),
                 ("beside one GitHub can't find", answer(("p0", "FORBIDDEN"), ("p1", "NOT_FOUND")),
                  f"{stopped}: gh api graphql: {PR.format(41)}: ", refused),
                 ("several", answer(("p0", "FORBIDDEN"), ("p1", "FORBIDDEN")),
                  f"{stopped}: gh api graphql: {PR.format(41)}: ", refused),
                 ("the GraphQL call rate limited", None,
                  f"{stopped}: gh api graphql: ", limited)]
        for name, graphql, start, end in cases:
            run = gh({**self.TIMES, "api graphql": graphql})
            # Raised as GhError, which main stops on with NO_REPORT.
            with self.subTest(name):
                with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as raised, \
                        fetch_sprint.stops_on_failure(fetch_sprint.NO_REPORT):
                    fetch_sprint.pull_requests(
                        Panel(self.PANEL), self.ISSUES, run)
                message = str(raised.exception.code)
                self.assertTrue(message.startswith(start), message)
                self.assertTrue(message.endswith(end), message)
                self.assertEqual(len(run.calls), 1, run.calls)


class OtherPullRequestsTest(unittest.TestCase):
    START, END = "2026-03-04T12:00:00.000Z", "2026-03-13T16:00:00.000Z"
    WINDOW = ("2026-03-03", "2026-03-14")

    def test_other_pull_requests(self):
        # The people who authored the tickets' pull requests, apps left out,
        # each searched in the account's organisations for the pull requests
        # merged in the days around the sprint, by address and merge time;
        # of those merged during it, only the ones no ticket links, the
        # skipped included, are read.
        author = {PR.format(41): {"__typename": "User", "login": "janedoe"},
                  PR.format(42): {"__typename": "Bot", "login": "renovate"}}
        pulls = {"tickets": {}, "events": {url: {"author": who} for url, who in author.items()},
                 "skipped": [{"url": PR.format(43), "via": ["PROJ-1"], "message": "gone"}]}
        merged = "2026-03-08T10:00:00Z"
        # 52 and 53 were merged on the days searched, but before the start
        # and after the end.
        found = [{"url": PR.format(n), "mergedAt": merged} for n in (41, 43, 50)] + [
            {"url": PR.format(52), "mergedAt": "2026-03-04T11:00:00Z"},
            {"url": PR.format(53), "mergedAt": "2026-03-13T17:00:00Z"}]
        run = gh({"api user/orgs?per_page=100": [{"login": "acme"}], "search": found,
                  f"pr view {PR.format(50)}": {"title": "Fix the build"}})
        self.assertEqual(fetch_sprint.other_pull_requests(pulls, self.START, self.END, run), {
            "people": ["janedoe"], "orgs": ["acme"], "window": list(self.WINDOW),
            "pulls": {PR.format(50): {"title": "Fix the build"}}, "gone": {}})
        # GitHub is searched a day wider on each side of the sprint.
        searches = [call for call in run.calls if "search(query:" in call]
        self.assertEqual(len(searches), 1)
        self.assertIn(
            "q=is:pr is:merged author:janedoe org:acme merged:2026-03-03..2026-03-14", searches[0])
        # With no one to search, GitHub isn't asked.
        run = gh({})
        self.assertEqual(fetch_sprint.other_pull_requests({"tickets": {}, "events": {}, "skipped": []}, self.START,
                                                          self.END, run),
                         {"people": [], "orgs": [], "window": list(self.WINDOW), "pulls": {}, "gone": {}})
        self.assertEqual(run.calls, [])


class ChangelogsTest(unittest.TestCase):
    def test_read_changelogs(self):
        # Each issue's changes, in the issues' order; one Jira now has none
        # of gets [] and a line on stderr, and the rest are kept.
        change = {"created": "2026-03-10T11:00:00.000+0000", "field": "status"}
        why = "PROJ-2: Jira has no such ticket, or this account can't see it"
        # name: (the client's (changes, gone), the changelogs, stderr)
        cases = [("every issue", ({"PROJ-1": [change], "PROJ-2": []}, {}),
                  {"PROJ-1": [change], "PROJ-2": []}, ""),
                 ("one gone", ({"PROJ-1": [change]}, {"PROJ-2": why}), {"PROJ-1": [change], "PROJ-2": []},
                  f"no changelog read, so its current values stand for its history: {why}\n")]
        issues = [{"id": "1", "key": "PROJ-1"}, {"id": "2", "key": "PROJ-2"}]
        for name, answer, expected, said in cases:
            with self.subTest(name), contextlib.redirect_stderr(io.StringIO()) as err:
                client = mock.Mock(
                    **{"batched_field_changes.return_value": answer})
                changelogs = fetch_sprint.read_changelogs(
                    client, issues, {"status": "status"})
                self.assertEqual(changelogs, expected)
                self.assertEqual(list(changelogs), ["PROJ-1", "PROJ-2"])
                self.assertEqual(err.getvalue(), said)
                client.batched_field_changes.assert_called_once_with(
                    issues, {"status": "status"})


class HelpersTest(unittest.TestCase):
    def test_project_key_of(self):
        # --project wins; otherwise an issue key up to its last hyphen; with
        # neither, no key.
        cases = [("PROJ", [], "PROJ"),
                 (None, [{"key": "ABC-DEF-12"}], "ABC-DEF"), (None, [], None)]
        for project, issues, expected in cases:
            with self.subTest(project=project, issues=issues):
                self.assertEqual(fetch_sprint.project_key_of(
                    mock.Mock(project=project), issues), expected)

    def test_log_goes_to_stderr(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            fetch_sprint.log("hello")
        self.assertEqual(err.getvalue(), "hello\n")


if __name__ == "__main__":
    unittest.main()
