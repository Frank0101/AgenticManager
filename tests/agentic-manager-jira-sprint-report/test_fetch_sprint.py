"""Unit tests for skills/agentic-manager-jira-sprint-report/scripts/fetch_sprint.py.
Run with: python3 tests/run.py agentic-manager-jira-sprint-report

They cover the script's own logic: its arguments and the report folder. The
Jira calls belong to the library's client, tested there; test_e2e_fetch.py
runs the whole script against a fake Jira.
"""

import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

# tests/<skill>/ mirrors skills/<skill>/.
TEST_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(TEST_DIR))
sys.path.insert(0, os.path.join(REPO_ROOT, "skills",
                os.path.basename(TEST_DIR), "scripts"))
import fetch_sprint  # noqa: E402
from common import RAW_DIR, SPRINT_FILE  # noqa: E402
from agentic_manager import retry  # noqa: E402
sys.path.insert(0, TEST_DIR)
from sprint_fixture import report_folder  # noqa: E402
# The fake gh's GraphQL answers follow the library's query.
sys.path.insert(0, os.path.join(os.path.dirname(
    TEST_DIR), "agentic-manager-utils-lib"))
from gh_fake import graphql_answer, is_graphql  # noqa: E402


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


class ReportDirTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = self.tmp.name
        self.logged = []

    def report(self, name, sprint):
        """A report folder in the root whose sprint.json holds `sprint`: an
        id, or text as it is."""
        return report_folder(os.path.join(self.root, name),
                             sprint if isinstance(sprint, str) else {"id": sprint})

    def prepare(self, name, sprint_id):
        return fetch_sprint.prepare_report_dir(os.path.join(self.root, name), sprint_id,
                                               self.logged.append)

    def test_stored_sprint_id(self):
        # A folder that isn't a readable report is never taken for one.
        cases = [("a report", self.report("a", 7), "7"),
                 ("no folder", os.path.join(self.root, "missing"), None),
                 ("a sprint.json that isn't an object",
                  self.report("list", "[]"), None),
                 ("a sprint.json that isn't JSON", self.report("text", "{"), None)]
        for name, folder, expected in cases:
            with self.subTest(name):
                self.assertEqual(
                    fetch_sprint.stored_sprint_id(folder), expected)

    def test_new_folder(self):
        raw = self.prepare("PROJ_Sprint_7_26-03-16", 7)
        self.assertEqual(raw, os.path.join(
            self.root, "PROJ_Sprint_7_26-03-16", "_raw"))
        self.assertEqual(os.listdir(raw), [])
        self.assertEqual(self.logged, [])

    def test_only_the_report_of_the_same_sprint_and_day_is_deleted(self):
        # Earlier days' reports of the sprint stay, as does every other
        # sprint's report, and a report elsewhere that a link points to.
        earlier_day = self.report("PROJ_Sprint_7_26-03-13", 7)
        other = self.report("PROJ_Sprint_6_26-03-16", 6)
        same_day = self.report("PROJ_Sprint_7_26-03-16", 7)
        outside = tempfile.TemporaryDirectory()
        self.addCleanup(outside.cleanup)
        linked = report_folder(os.path.join(
            outside.name, "PROJ_Sprint_7_26-03-01"), {"id": 7})
        os.symlink(linked, os.path.join(self.root, "link"))
        self.prepare("PROJ_Sprint_7_26-03-16", 7)
        self.assertTrue(os.path.exists(earlier_day))
        self.assertTrue(os.path.exists(other))
        self.assertTrue(os.path.islink(os.path.join(self.root, "link")))
        self.assertTrue(os.path.exists(
            os.path.join(linked, RAW_DIR, SPRINT_FILE)))
        self.assertEqual(os.listdir(os.path.join(same_day, "_raw")), [])
        self.assertEqual(
            self.logged, [f"replacing the report of the same sprint and day: {same_day}"])

    def test_refuses_to_delete_another_sprints_report(self):
        self.report("PROJ_Sprint_7_26-03-16", 6)
        with self.assertRaisesRegex(SystemExit, "it holds the report of sprint 6"):
            self.prepare("PROJ_Sprint_7_26-03-16", 7)

    def test_replaces_a_file_or_link_in_the_way(self):
        # Whatever holds the destination's name is removed, but a link is
        # removed itself, never what it points to.
        elsewhere = os.path.join(self.root, "elsewhere")
        os.makedirs(elsewhere)
        cases = [("a file", lambda path: open(path, "w").close()),
                 ("a link to a folder", lambda path: os.symlink(elsewhere, path)),
                 ("a broken link", lambda path: os.symlink(os.path.join(self.root, "gone"), path))]
        for sprint_id, (name, make) in enumerate(cases, start=7):
            with self.subTest(name):
                target = os.path.join(self.root, f"PROJ_Sprint_{sprint_id}")
                make(target)
                self.prepare(f"PROJ_Sprint_{sprint_id}", sprint_id)
                self.assertFalse(os.path.islink(target))
                self.assertTrue(os.path.isdir(os.path.join(target, "_raw")))
        self.assertTrue(os.path.isdir(elsewhere))


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


PR = "https://github.com/acme/api/pull/{}"


class Panel:
    """A Jira client whose Development panel lists, by issue id, `pulls`, and
    whose search by parent finds `subtasks`, recording each issue whose panel
    is read and each search. It has no other read, so the fetch can't look up
    the panel's commits."""

    def __init__(self, pulls, subtasks=()):
        self.pulls, self.subtasks, self.read = pulls, subtasks, []

    def search(self, jql, fields):
        self.read.append(("search", jql))
        return list(self.subtasks)

    def pull_requests(self, issue_id):
        self.read.append(("pulls", issue_id))
        return self.pulls.get(issue_id, [])


class gh:
    """A runner that answers gh's commands from `answers`, by the words after
    gh up to the first option, a GraphQL call by each pull request's "pr view
    <url>" and, when it holds "api graphql", as a whole by that; it records
    each command. A command it has no answer for fails with GitHub's rate
    limit message, as gh does, and a pull request GitHub can't resolve."""

    def __init__(self, answers):
        self.answers, self.calls = answers, []

    def __call__(self, command, **kwargs):
        self.calls.append(" ".join(command))
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


def sub_task(key, parent):
    return {"id": key, "key": key, "fields": {"parent": {"key": parent}}}


class PullRequestsTest(unittest.TestCase):
    ISSUES = [{"id": "1", "key": "PROJ-1"}, {"id": "2", "key": "PROJ-2"},
              {"id": "3", "key": "PROJ-3"}]
    PANEL = {"1": [{"url": PR.format(41), "status": "MERGED"}],
             "2": [{"url": "https://github.com/acme-labs/web/pull/43", "status": "OPEN"}]}
    # When GitHub says each was opened, by URL.
    TIMES = {f"pr view {url}": {"createdAt": "2026-03-05T10:00:00Z"}
             for url in (PR.format(41), PR.format(42), PR.format(44), "https://github.com/acme-labs/web/pull/43")}

    def test_pull_requests(self):
        # Only the panel's, each kept as found there; a ticket whose panel
        # lists none has none, as GitHub isn't searched for more. GitHub is
        # read only for the times, in GraphQL calls.
        acme_labs = "https://github.com/acme-labs/web/pull/43"
        # name: (the panel's pull requests by issue id, {key: [url]})
        cases = [
            ("the panel's", self.PANEL,
             {"PROJ-1": [PR.format(41)], "PROJ-2": [acme_labs], "PROJ-3": []}),
            ("several on one ticket", {"3": [{"url": PR.format(42)}, {"url": PR.format(44)}]},
             {"PROJ-1": [], "PROJ-2": [], "PROJ-3": [PR.format(42), PR.format(44)]}),
            ("none listed", {}, {"PROJ-1": [], "PROJ-2": [], "PROJ-3": []}),
        ]
        for name, panel, expected in cases:
            with self.subTest(name):
                client = Panel(panel)
                run = gh(self.TIMES)
                found = fetch_sprint.pull_requests(
                    client, self.ISSUES, True, run)
                self.assertEqual({key: [pr["url"] for pr in prs]
                                  for key, prs in found["tickets"].items()}, expected)
                # Each found through the panel of its own ticket, as there
                # are no sub-tasks.
                self.assertTrue(all((pr["found"], pr["via"]) == ("panel", key)
                                    for key, prs in found["tickets"].items() for pr in prs))
                self.assertEqual({r[1] for r in client.read if r[0] == "pulls"}, {
                                 "1", "2", "3"})
                # No gh call but the GraphQL reads of the times, none
                # without a pull request.
                self.assertTrue(
                    all(is_graphql(c.split()[1:]) for c in run.calls), run.calls)
                self.assertEqual(bool(run.calls), any(expected.values()))
                self.assertTrue(found["github_read"])
                # GitHub's times of every pull request found.
                self.assertEqual(found["events"], {url: {"createdAt": "2026-03-05T10:00:00Z"}
                                                   for urls in expected.values() for url in urls})

    def test_pull_requests_through_sub_tasks(self):
        # A sub-task's pull requests are its parent's, each kept once with
        # the ticket it came through, the ticket before its sub-tasks, and
        # its sub-tasks in key order.
        # PROJ-12 and PROJ-11 are sub-tasks of PROJ-1, PROJ-21 of PROJ-2 and
        # PROJ-31 of PROJ-3, found by the search out of key order.
        subtasks = [sub_task("PROJ-12", "PROJ-1"), sub_task("PROJ-31", "PROJ-3"),
                    sub_task("PROJ-11", "PROJ-1"), sub_task("PROJ-21", "PROJ-2")]
        times = {f"pr view {PR.format(n)}": {} for n in (41, 43, 44)}
        # name: (the panel's pull requests by issue id, {key: [(number,
        # via)]} of the tickets with any)
        cases = [
            ("a ticket with none of its own, all through its sub-tasks",
             {"PROJ-21": [{"url": PR.format(43)}]},
             {"PROJ-2": [(43, "PROJ-21")]}),
            ("linked to the ticket and a sub-task: kept once, through the ticket",
             {"1": [{"url": PR.format(41)}],
              "PROJ-11": [{"url": PR.format(41)}, {"url": PR.format(44)}]},
             {"PROJ-1": [(41, "PROJ-1"), (44, "PROJ-11")]}),
            ("sub-tasks in key order",
             {"PROJ-12": [{"url": PR.format(41)}],
              "PROJ-11": [{"url": PR.format(41)}]},
             {"PROJ-1": [(41, "PROJ-11")]}),
        ]
        for name, panel, expected in cases:
            with self.subTest(name):
                client = Panel(panel, subtasks)
                run = gh(times)
                found = fetch_sprint.pull_requests(
                    client, self.ISSUES, True, run)
                self.assertEqual({key: [(int(pr["url"].rsplit("/", 1)[1]), pr["via"]) for pr in prs]
                                  for key, prs in found["tickets"].items() if prs}, expected)
                self.assertTrue(all(pr["found"] == "panel" for prs in found["tickets"].values()
                                    for pr in prs))
                # Only tickets are keys, never a sub-task.
                self.assertEqual(list(found["tickets"]), [
                                 "PROJ-1", "PROJ-2", "PROJ-3"])
                # One search for every ticket's sub-tasks, and every panel
                # of a ticket and its sub-tasks read.
                self.assertEqual([r for r in client.read if r[0] == "search"],
                                 [("search", "parent in (PROJ-1,PROJ-2,PROJ-3)")])
                self.assertEqual({r[1] for r in client.read if r[0] == "pulls"},
                                 {"1", "2", "3", "PROJ-11", "PROJ-12", "PROJ-21", "PROJ-31"})
                self.assertTrue(
                    all(is_graphql(c.split()[1:]) for c in run.calls), run.calls)

    def test_without_gh_nothing_is_read(self):
        # The panel alone gives no events, so it isn't read either.
        client, run = Panel(self.PANEL), gh(self.TIMES)
        self.assertEqual(fetch_sprint.pull_requests(client, self.ISSUES, False, run),
                         {"github_read": False, "tickets": {}, "events": {}, "skipped": []})
        self.assertEqual((client.read, run.calls), ([], []))

    def test_a_pull_request_github_cant_find_is_skipped(self):
        # One GitHub says doesn't exist, such as one deleted that Jira still
        # links, is dropped from every ticket, so it gives no events, said
        # on stderr with the tickets it came through and kept as skipped
        # with GitHub's message; the others are kept, and the fetch goes on.
        acme_labs = "https://github.com/acme-labs/web/pull/43"
        gone = "{}: Could not resolve to a PullRequest with the number of {}."
        # name: (the panel's pull requests by issue id, those GitHub can't
        # find, {key: [url]} kept, the skipped as (url, via))
        cases = [
            ("one", self.PANEL, [acme_labs],
             {"PROJ-1": [PR.format(41)], "PROJ-2": [], "PROJ-3": []}, [(acme_labs, ["PROJ-2"])]),
            ("linked to two tickets", {**self.PANEL, "3": [{"url": PR.format(41)}, {"url": PR.format(44)}]},
             [PR.format(41)], {
                "PROJ-1": [], "PROJ-2": [acme_labs], "PROJ-3": [PR.format(44)]},
             [(PR.format(41), ["PROJ-1", "PROJ-3"])]),
            ("every one", self.PANEL, [PR.format(41), acme_labs], {"PROJ-1": [], "PROJ-2": [], "PROJ-3": []},
             [(PR.format(41), ["PROJ-1"]), (acme_labs, ["PROJ-2"])]),
        ]
        for name, panel, missing, kept, skipped in cases:
            with self.subTest(name), contextlib.redirect_stderr(io.StringIO()) as said:
                run = gh({k: v for k, v in self.TIMES.items()
                          if k.removeprefix("pr view ") not in missing})
                found = fetch_sprint.pull_requests(
                    Panel(panel), self.ISSUES, True, run)
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
        # library's advice, and how many failed when several did. A pull
        # request GitHub can't find beside it doesn't change that, and a
        # rate limit stops at once, never tried again.
        stopped = "GitHub couldn't be read, so no report was written"
        limited = f": {LIMIT} Wait a minute and run it again."
        refused = ("Resource not accessible. Check that gh works (gh auth status) and run it again, or disable "
                   "the github-cli source to go on without GitHub.")
        acme_labs = "https://github.com/acme-labs/web/pull/43"

        def answer(*errors):
            """GitHub's answer to the GraphQL call with PR 41 (r0, p0) and
            acme_labs (r1, p1): each error a (pull, its type), the others read."""
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
                  f"{stopped} (2 gh calls failed, the first shown): gh api graphql: {PR.format(41)}: ", refused),
                 ("the GraphQL call rate limited", None,
                  f"{stopped} (2 gh calls failed, the first shown): gh api graphql: ", limited)]
        for name, graphql, start, end in cases:
            run = gh({**self.TIMES, "api graphql": graphql})
            with self.subTest(name), contextlib.redirect_stderr(io.StringIO()), \
                    self.assertRaises(SystemExit) as raised:
                fetch_sprint.pull_requests(
                    Panel(self.PANEL), self.ISSUES, True, run)
            message = str(raised.exception.code)
            self.assertTrue(message.startswith(start), message)
            self.assertTrue(message.endswith(end), message)
            self.assertEqual(len(run.calls), 1, run.calls)

    def test_parallelism(self):
        # Four Jira reads at a time: its internal Development-panel endpoint
        # drops connections under more.
        self.assertEqual(fetch_sprint.MAX_WORKERS, 4)


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
