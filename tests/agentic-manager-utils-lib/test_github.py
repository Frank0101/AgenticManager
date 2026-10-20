"""Unit tests for skills/agentic-manager-utils-lib/agentic_manager/github.py.
Run with: python3 tests/run.py agentic-manager-utils-lib

gh answers from a fake runner, so nothing reaches GitHub; is_enabled and
shutil.which are patched, so no config is read.
"""

import json
import os
import subprocess
import sys
import unittest
from unittest import mock

# tests/<skill>/ mirrors skills/<skill>/.
TEST_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(TEST_DIR))
sys.path.insert(0, os.path.join(
    REPO_ROOT, "skills", os.path.basename(TEST_DIR)))
from agentic_manager import batch, github, retry  # noqa: E402
sys.path.insert(0, TEST_DIR)
from gh_fake import graphql_answer, is_graphql  # noqa: E402

PR = "https://github.com/acme/api/pull/{}"


# Retries wait for real; here they needn't.
retry.RETRY_WAITS = (0, 0, 0)


class Fails:
    """A case's expected failure: the message gh_json() raises GhError with,
    and whether it is not_found."""

    def __init__(self, message, not_found=False):
        self.message, self.not_found = message, not_found


class Runner:
    """A runner that answers every command with `stdout`, `code` and
    `stderr`, or raises `error`, and records each command."""

    def __init__(self, stdout="", code=0, error=None, stderr=""):
        self.stdout, self.code, self.error, self.stderr, self.calls = stdout, code, error, stderr, []

    def __call__(self, command, **kwargs):
        self.calls.append(command)
        if self.error:
            raise self.error
        return subprocess.CompletedProcess(command, self.code, self.stdout, self.stderr)


def answering(value):
    """A runner whose gh answers `value` as JSON."""
    return Runner(json.dumps(value))


class GithubTest(unittest.TestCase):
    def test_gh_json(self):
        # An answer, even an empty one, is returned; a failure raises with
        # gh's own message, so "gh failed" is never read as "nothing found".
        # name: (runner, expected answer, or the failure's message)
        limit = "HTTP 403: API rate limit exceeded for user ID 1."
        cases = [
            ("answer", answering({"a": 1}), {"a": 1}),
            ("empty answer", answering([]), []),
            ("failure", Runner("{}", code=1, stderr=limit + "\n"), Fails(limit)),
            ("failure without a message", Runner(
                code=4), Fails("exited with code 4")),
            ("not JSON", Runner("oops"), Fails(
                "answered something other than JSON")),
            ("not installed", Runner(error=FileNotFoundError("gh")),
             Fails("couldn't run gh: gh")),
            ("timeout", Runner(error=subprocess.TimeoutExpired("gh", 60)),
             Fails("no answer within 60 seconds")),
        ]
        command = ["pr", "view", PR.format(1)]
        for name, run, expected in cases:
            with self.subTest(name):
                if isinstance(expected, Fails):
                    with self.assertRaises(github.GhError) as raised:
                        github.gh_json(command, run)
                    self.assertEqual((raised.exception.command, raised.exception.message),
                                     (command, expected.message))
                    self.assertEqual(str(raised.exception),
                                     f"gh pr view {PR.format(1)}: {expected.message}")
                else:
                    self.assertEqual(github.gh_json(command, run), expected)
                # A timeout is tried until the retries run out; anything
                # else, a rate limit included, once.
                tries = {"timeout": [command] * (len(retry.RETRY_WAITS) + 1)}
                self.assertEqual(
                    run.calls, [["gh", *c] for c in tries.get(name, [command])])

    def test_gather(self):
        # Every subject is tried: an answer, even an empty one, is kept apart
        # from a failure, each in the order of the subjects.
        failed = github.GhError(
            ["api", "b"], "HTTP 403: API rate limit exceeded")

        def call(subject):
            if subject == "b":
                raise failed
            return [] if subject == "c" else [subject]
        # name: (workers, subjects, expected (answers, failures))
        cases = [("parallel", 8, ["a", "b", "c"], ([("a", ["a"]), ("c", [])], [("b", failed)])),
                 ("one at a time", 1, ["a", "b", "c"],
                  ([("a", ["a"]), ("c", [])], [("b", failed)])),
                 ("none", 8, [], ([], []))]
        for name, workers, subjects, expected in cases:
            with self.subTest(name):
                self.assertEqual(github.gather(
                    subjects, call, workers), expected)

    def test_advice(self):
        # One wording for every skill: wait a minute for GitHub's rate limit,
        # or fix gh or go on without it; the explanation puts gh's words on one line.
        # name: (gh's message, the advice, the explanation)
        cases = [
            ("rate limit", "HTTP 403: API rate limit exceeded for user ID 1.", github.RATE_LIMITED,
             "HTTP 403: API rate limit exceeded for user ID 1. Wait a minute and run it again."),
            ("secondary rate limit", "You have exceeded a secondary Rate Limit.", github.RATE_LIMITED,
             "You have exceeded a secondary Rate Limit. Wait a minute and run it again."),
            ("not signed in", "To get started with GitHub CLI, please run:  gh auth login\n", github.GH_BROKEN,
             "To get started with GitHub CLI, please run: gh auth login. Check that gh works (gh auth status) "
             "and run it again, or disable the github-cli source to go on without GitHub."),
            ("no message", "exited with code 4", github.GH_BROKEN,
             "exited with code 4. " + github.GH_BROKEN),
        ]
        for name, message, advice, explanation in cases:
            with self.subTest(name):
                failed = github.GhError(["search", "prs", "PROJ-123"], message)
                self.assertEqual(
                    (failed.advice, failed.explanation), (advice, explanation))

    def test_passing(self):
        # What retry.retried() makes of a gh failure: no answer in time or
        # GitHub busy is passing, tried again; a rate limit, and anything
        # else, is final.
        # name: (gh's message, whether it is passing)
        cases = [
            ("rate limit", "HTTP 403: API rate limit exceeded for user ID 1.", False),
            ("secondary rate limit", "You have exceeded a secondary rate limit", False),
            ("rate limit on a busy answer",
             "HTTP 503: API rate limit exceeded", False),
            ("no answer in time", "no answer within 60 seconds", True),
            ("GitHub busy", "HTTP 502: Bad Gateway (https://api.github.com/graphql)", True),
            ("connection lost", "Post \"https://api.github.com/graphql\": read: connection reset by peer", True),
            ("not signed in", "To get started with GitHub CLI, please run:  gh auth login", False),
            ("not found", "GraphQL: Could not resolve to a PullRequest with the number of 9.", False),
        ]
        for name, message, expected in cases:
            with self.subTest(name):
                self.assertIs(github.passing(
                    github.GhError(["pr", "view"], message)), expected)
        self.assertIs(github.passing(ValueError("not gh's")), False)

    def test_gh_json_tries_again(self):
        # A passing failure is tried again, and the answer returned.
        answers = [subprocess.CompletedProcess([], 1, "", "HTTP 503: Service Unavailable"),
                   subprocess.CompletedProcess([], 0, "[]", "")]
        run = mock.Mock(side_effect=answers)
        self.assertEqual(github.gh_json(["search", "prs", "x"], run), [])
        self.assertEqual(run.call_count, 2)

    def test_gh_available(self):
        # name: (gh on the path, github-cli enabled, expected)
        cases = [("both", "/usr/bin/gh", True, True), ("not installed", None, True, False),
                 ("not enabled", "/usr/bin/gh", False, False)]
        for name, path, enabled, expected in cases:
            with self.subTest(name), mock.patch.object(github.shutil, "which", return_value=path), \
                    mock.patch.object(github, "is_enabled", return_value=enabled) as is_enabled:
                self.assertEqual(github.gh_available(), expected)
                if path:
                    is_enabled.assert_called_once_with(
                        "source_control", "github-cli")

    def test_reads(self):
        # name: (call, gh's answer, expected, the command's start)
        found = [{"url": PR.format(41), "state": "MERGED",
                  "updatedAt": "2026-10-10T08:00:00Z"}]
        searched = [{"url": PR.format(47), "state": "open", "title": "PROJ-123 Backoff"},
                    {"url": PR.format(48), "title": "PROJ-123 Jitter"}]
        cases = [
            ("pulls holding", lambda run: github.pulls_holding("acme/api", "c1", run), found, found,
             ["gh", "api", "repos/acme/api/commits/c1/pulls"]),
            # States in capitals, as the other reads give them.
            ("search", lambda run: github.search_pull_titles("PROJ-123", "acme", run), searched,
             [{**searched[0], "state": "OPEN"}, {**searched[1], "state": "?"}],
             ["gh", "search", "prs", "PROJ-123", "--owner", "acme", "--match", "title"]),
        ]
        for name, call, answer, expected, command in cases:
            with self.subTest(name):
                run = answering(answer)
                self.assertEqual(call(run), expected)
                self.assertEqual(run.calls[0][:len(command)], command)
            with self.subTest(name + ", gh fails"), self.assertRaises(github.GhError):
                call(Runner(code=1))
            with self.subTest(name + ", gh answers nothing"):
                self.assertEqual(call(answering([])), [])

    def test_pull_url(self):
        # url: (repository, owner, number), or None for a page that isn't a pull request
        cases = [(PR.format(41), ("acme/api", "acme", "41")),
                 ("https://github.com/acme/api/pull/41/files",
                  ("acme/api", "acme", "41")),
                 ("https://github.com/acme/api/issues/41", None),
                 ("https://bitbucket.org/acme/api/pull-requests/3", None)]
        for url, expected in cases:
            with self.subTest(url):
                match = github.PULL_URL.match(url)
                self.assertEqual(match and match.groups(), expected)

    def test_pull_events(self):
        # Many pull requests in one GraphQL call, grouped by repository, each
        # value a variable; split into calls of a batch each, one host
        # each; one GitHub can't resolve, or whose address isn't safe to ask
        # about, a failure of its own while the rest are answered, marked
        # not_found only when GitHub says the pull request doesn't exist.
        def node(url):
            return {"url": url, "state": "MERGED", "createdAt": "2026-10-01T08:00:00Z",
                    "mergedAt": "2026-10-10T08:00:00Z"}
        web = "https://github.com/acme/web/pull/{}"
        enterprise = "https://git.acme.test/acme/api/pull/{}"
        unsafe = "https://github.com/acme/api$x/pull/1"
        # name: (urls, those GitHub can't resolve, the batch size, each
        # call's --hostname, "" for GitHub's own, the urls answered, the
        # failures)
        cases = [
            ("one call, two repositories", [PR.format(41), web.format(7), PR.format(42)], [], 50,
             [""], [PR.format(41), web.format(7), PR.format(42)], []),
            ("each once", [PR.format(41), PR.format(41)],
             [], 50, [""], [PR.format(41)], []),
            ("split into batches", [PR.format(n) for n in range(1, 6)], [], 2, [""] * 3,
             [PR.format(n) for n in range(1, 6)], []),
            ("one host a call", [PR.format(41), enterprise.format(3)], [], 50,
             ["", "git.acme.test"], [PR.format(41), enterprise.format(3)], []),
            ("one GitHub can't resolve", [PR.format(41), PR.format(9)], [PR.format(9)], 50, [""],
             [PR.format(41)], [(PR.format(9), f"{PR.format(9)}: Could not resolve to a PullRequest with the "
                                "number of 9.", True)]),
            ("an address not safe to ask about", [unsafe, PR.format(41)], [], 50, [""], [PR.format(41)],
             [(unsafe, f"{unsafe}: not a pull request's address gh can be asked about", False)]),
            ("none", [], [], 50, [], [], []),
        ]
        for name, urls, missing, size, hosts, answered, failed in cases:
            with self.subTest(name), mock.patch.object(batch, "BATCH_SIZE", size):
                calls = []

                def run(command, **kwargs):
                    calls.append(command[1:])
                    code, out, err = graphql_answer(command[1:], lambda url: None if url in missing
                                                    else node(url))
                    return subprocess.CompletedProcess(command, code, out, err)
                events, failures = github.pull_events(urls, run)
                self.assertEqual(events, {url: node(url) for url in answered})
                self.assertEqual([(url, error.message, error.not_found)
                                 for url, error in failures], failed)
                self.assertTrue(
                    all(error.command == ["api", "graphql"] for _, error in failures))
                self.assertEqual(sorted((c[c.index("--hostname") + 1] if "--hostname" in c else "")
                                        for c in calls), sorted(hosts))
                self.assertTrue(all(is_graphql(c) for c in calls))

    def test_events_query(self):
        # Aliases r<i> for each repository and p<j> for each pull request;
        # owner, name and number only as variables, never in the query.
        query, fields, aliases = github.events_query(
            [PR.format(41), "https://github.com/acme/web/pull/7", PR.format(42)])
        self.assertEqual(query, "\n".join([
            "query($o0: String!, $n0: String!, $p0: Int!, $p1: Int!, $o1: String!, $n1: String!, $p2: Int!) {",
            "r0: repository(owner: $o0, name: $n0) { p0: pullRequest(number: $p0) { ...pull } "
            "p1: pullRequest(number: $p1) { ...pull } }",
            "r1: repository(owner: $o1, name: $n1) { p2: pullRequest(number: $p2) { ...pull } }",
            "}", "fragment pull on PullRequest { url state createdAt mergedAt }"]))
        self.assertEqual(fields, ["-f", "o0=acme", "-f", "n0=api", "-F", "p0=41", "-F", "p1=42",
                                  "-f", "o1=acme", "-f", "n1=web", "-F", "p2=7"])
        self.assertEqual(aliases, {("r0", "p0"): PR.format(41), ("r0", "p1"): PR.format(42),
                                   ("r1", "p2"): "https://github.com/acme/web/pull/7"})
        # Anything that could change the query or a variable's meaning.
        for url in ("https://github.com/acme/api/pull/4x", "https://github.com/ac{me}/api/pull/1",
                    'https://github.com/acme/a"pi/pull/1', "https://github.com/acme/api/issues/1"):
            with self.subTest(url), self.assertRaises(ValueError):
                github.events_query([url])

    def test_graphql_failures(self):
        # The call as a whole failing, with gh's words; an answer holding
        # data is GitHub's even when gh exits non-zero, and only a pull
        # request GitHub says doesn't exist is not_found: a repository it
        # can't find is also what an account without access gets.
        # name: (exit code, stdout, stderr, expected events or the message)
        data = {
            "data": {"r0": {"p0": {"url": PR.format(41), "state": "OPEN"}}}}
        gone = "Could not resolve to a PullRequest with the number of 41."
        no_repository = "Could not resolve to a Repository with the name 'acme/api'."
        cases = [("rate limit", 1, json.dumps({"data": None, "errors": [{"message": "API rate limit exceeded"}]}),
                  "gh: API rate limit exceeded", Fails("gh: API rate limit exceeded")),
                 ("errors only", 1, json.dumps(
                     {"errors": [{"message": "Bad query"}]}), "", Fails("Bad query")),
                 ("refused", 1, "", "HTTP 401: Bad credentials",
                  Fails("HTTP 401: Bad credentials")),
                 ("not JSON", 0, "oops", "", Fails(
                     "answered something other than GraphQL data")),
                 ("data", 0, json.dumps(data), "", {
                  PR.format(41): {"url": PR.format(41), "state": "OPEN"}}),
                 ("pull request not found", 1, json.dumps({"data": {"r0": {"p0": None}}, "errors": [
                     {"type": "NOT_FOUND", "path": ["r0", "p0"], "message": gone}]}), "gh: " + gone,
                  Fails(f"{PR.format(41)}: {gone}", True)),
                 ("repository not found", 1, json.dumps({"data": {"r0": None}, "errors": [
                     {"type": "NOT_FOUND", "path": ["r0"], "message": no_repository}]}), "gh: " + no_repository,
                  Fails(f"{PR.format(41)}: {no_repository}")),
                 ("pull request refused", 1, json.dumps({"data": {"r0": {"p0": None}}, "errors": [
                     {"type": "FORBIDDEN", "path": ["r0", "p0"], "message": "Resource not accessible"}]}), "",
                  Fails(f"{PR.format(41)}: Resource not accessible"))]
        for name, code, out, err, expected in cases:
            with self.subTest(name):
                def run(command, **kwargs):
                    return subprocess.CompletedProcess(command, code, out, err)
                events, failures = github.pull_events([PR.format(41)], run)
                if isinstance(expected, Fails):
                    self.assertEqual([(url, e.command, e.message, e.not_found) for url, e in failures],
                                     [(PR.format(41), ["api", "graphql"], expected.message, expected.not_found)])
                else:
                    self.assertEqual((events, failures), (expected, []))


if __name__ == "__main__":
    unittest.main()
