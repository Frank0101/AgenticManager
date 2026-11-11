"""Unit tests for skills/agentic-manager-perf-review-prep/scripts/fetch_work.py.
Run with: python3 tests/run.py agentic-manager-perf-review-prep

Jira is a fake client and gh a fake runner, so nothing reaches a service.
"""

import json
import os
import re
import subprocess
import sys
import unittest
from unittest import mock

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(TEST_DIR))
sys.path.insert(0, os.path.join(REPO_ROOT, "skills",
                os.path.basename(TEST_DIR), "scripts"))
import fetch_work  # noqa: E402
sys.path.insert(0, TEST_DIR)
from prep_fixture import IDENTITIES, PREP, REQUEST, temp_output, write_prep  # noqa: E402


def issue(key, summary, resolved=None, parent=None):
    """A Jira issue as search() returns it."""
    return {"key": key, "id": key.split("-")[1], "fields": {"summary": summary, "issuetype": {"name": "Story"},
                                                            "status": {"name": "Done" if resolved else "In Progress"},
                                                            "resolutiondate": resolved, "parent": parent}}


class FakeJira:
    """Answers search() by whether the JQL asks for Done issues or not,
    recording each query."""
    base_url = "https://acme.atlassian.net"

    def __init__(self, panels=None):
        self.queries, self.panels = [], panels or {}

    def search(self, jql, fields):
        self.queries.append(jql)
        if "statusCategory = Done" in jql:
            return [issue("PROJ-12", "Migrate billing", "2026-09-01T10:00:00.000+0100",
                          {"key": "PROJ-1", "fields": {"summary": "Billing", "issuetype": {"name": "Epic"}}})]
        return [issue("PROJ-13", "Retire old billing")]

    def pull_requests(self, issue_id):
        return self.panels.get(issue_id, [])


class FakeGh:
    """A gh runner, signed in to one organisation: each search's PRs by its
    first flag, those dated within the search's window, and each PR's
    reviews, answered as GraphQL does."""

    def __init__(self, searches, reviews):
        self.searches, self.reviews, self.calls = searches, reviews, []

    def __call__(self, command, **kwargs):
        self.calls.append(command)
        args = command[1:]
        if args[:2] == ["auth", "status"]:
            answer = ""
        elif args[1].startswith("user/orgs"):
            answer = json.dumps([{"login": "acme"}])
        elif args[:2] == ["search", "prs"]:
            # The PRs of the search's first flag dated within its window: by
            # when they were merged for --merged-at, else opened.
            flag = next(f for f in ("--created", "--merged-at",
                        "--updated") if f in args)
            start, end = args[args.index(flag) + 1].split("..")
            stamp = "closedAt" if flag == "--merged-at" else "createdAt"
            answer = json.dumps([pr for pr in self.searches.get(args[2], [])
                                 if start <= (pr[stamp] or "")[:10] <= end])
        else:
            # A GraphQL query of reviews: each PR's, by the author it asks for.
            query = args[3].removeprefix("query=")
            author = re.findall(r'author: "([^"]+)"', query)[0]
            data = {f"p{n}": {"pullRequest": {"reviews": {"pageInfo": {"hasNextPage": False}, "nodes": [
                {"submittedAt": review["submitted_at"]} for review in self.reviews.get(number, [])
                if review["user"]["login"].casefold() == author.casefold()]}}}
                for n, number in re.findall(r"p(\d+): repository\(.*?pullRequest\(number: (\d+)\)", query)}
            answer = json.dumps({"data": data})
        return subprocess.CompletedProcess(command, 0, answer, "")


def pr(number, created="2026-09-01T10:00:00Z", closed=None):
    """A pull request as gh search prs returns it."""
    return {"number": number, "title": f"PR {number}", "repository": {"nameWithOwner": "acme/billing"},
            "url": f"https://github.com/acme/billing/pull/{number}", "createdAt": created, "closedAt": closed}


class FetchWorkTest(unittest.TestCase):
    def test_jira_work(self):
        # Resolved in the period and still open, each item with its parent,
        # and JQL dates to the minute.
        client = FakeJira()
        work = fetch_work.jira_work(client, "a1", REQUEST)
        self.assertEqual(work, {
            "resolved": [{"key": "PROJ-12", "id": "12", "title": "Migrate billing", "type": "Story",
                          "parent": {"key": "PROJ-1", "title": "Billing", "type": "Epic"}, "status": "Done",
                          "url": "https://acme.atlassian.net/browse/PROJ-12", "date": "2026-09-01"}],
            "open": [{"key": "PROJ-13", "id": "13", "title": "Retire old billing", "type": "Story", "parent": None,
                      "status": "In Progress", "url": "https://acme.atlassian.net/browse/PROJ-13"}]})
        self.assertTrue(
            all('<= "2026-11-10 23:59"' in jql for jql in client.queries))

    def test_github_work(self):
        # Opened and merged as found; reviewed only where the person submitted
        # a review in the period, dated by the first such review.
        run = FakeGh({"--author": [pr(1, closed="2026-09-03T10:00:00Z")], "--reviewed-by": [pr(2), pr(3), pr(4)]},
                     {"2": [{"user": {"login": "janedoe"}, "submitted_at": "2026-07-01T09:00:00Z"},
                            {"user": {"login": "JaneDoe"}, "submitted_at": "2026-09-05T09:00:00Z"}],
                      "3": [{"user": {"login": "sam"}, "submitted_at": "2026-09-05T09:00:00Z"}],
                      "4": [{"user": {"login": "janedoe"}, "submitted_at": None}]})
        with mock.patch.object(fetch_work, "gh_available", return_value=True):
            work = fetch_work.github_work(
                "janedoe", REQUEST, run, pause=lambda seconds: None)
        self.assertEqual([(item["number"], item["date"]) for name in ("opened", "merged") for item in work[name]],
                         [(1, "2026-09-01"), (1, "2026-09-03")])
        self.assertEqual(work["reviewed"], [{"repo": "acme/billing", "number": 2, "title": "PR 2",
                                             "url": "https://github.com/acme/billing/pull/2", "date": "2026-09-05"}])
        self.assertTrue(all(
            "--owner" in call and "acme" in call for call in run.calls if call[1] == "search"))
        # The reviews of the candidates in one GraphQL call, not one each.
        self.assertEqual(
            sum(call[1:3] == ["api", "graphql"] for call in run.calls), 1)

    def test_links_pull_requests_to_their_issue(self):
        # A PR an issue's Development panel lists gets that issue, whatever
        # the case of its address; one no issue lists gets none.
        client = FakeJira(
            {"12": [{"url": "https://GitHub.com/acme/billing/pull/1/"}]})
        github = {"opened": [{"url": "https://github.com/acme/billing/pull/1"},
                             {"url": "https://github.com/acme/billing/pull/2"}], "merged": [], "reviewed": []}
        fetch_work.link_issues(github, fetch_work.linked_prs(
            client, fetch_work.jira_work(client, "a1", REQUEST)))
        self.assertEqual([item["issue"]
                         for item in github["opened"]], ["PROJ-12", None])

    def test_a_full_search_stops(self):
        # A search that fills its last page may be cut short.
        run = FakeGh({"--author": [pr(n)
                     for n in range(fetch_work.SEARCH_LIMIT)]}, {})
        with self.assertRaisesRegex(SystemExit, "most it returns in a month"):
            fetch_work.search(["--author", "janedoe", "--created", "2026-09-01..2026-09-30"],
                              "acme", run, pause=lambda seconds: None)

    def test_a_rate_limited_search_waits_and_tries_again(self):
        # GitHub's secondary rate limit: wait and try again, LIMIT_TRIES
        # times; any other failure stops at once.
        waits = []
        answers = iter([subprocess.CompletedProcess([], 1, "", "HTTP 403: You have exceeded a secondary rate limit"),
                        subprocess.CompletedProcess([], 0, json.dumps([pr(1)]), "")])
        found = fetch_work.search(["--author", "janedoe", "--created", "2026-09-01..2026-09-30"], "acme",
                                  lambda command, **kwargs: next(answers), pause=waits.append)
        self.assertEqual(([item["number"] for item in found], waits),
                         ([1], [fetch_work.SEARCH_PAUSE, fetch_work.LIMIT_WAIT, fetch_work.SEARCH_PAUSE]))
        refused = subprocess.CompletedProcess(
            [], 1, "", "HTTP 403: You have exceeded a secondary rate limit")
        with self.assertRaisesRegex(Exception, "secondary rate limit"):
            fetch_work.search(["--author", "janedoe", "--created", "2026-09-01..2026-09-30"], "acme",
                              lambda command, **kwargs: refused, pause=lambda seconds: None)

    def test_fetch_records_absent_sources(self):
        # A source the person isn't in is recorded as absent, and not fetched.
        folder = temp_output(self)
        write_prep(folder, identities={
                   **IDENTITIES, "github-cli": {"absent": True}}, work=None)
        result = fetch_work.fetch(PREP, client=FakeJira())
        with open(result["path"], encoding="utf-8") as f:
            self.assertEqual(json.load(f)["github"], {"absent": True})
        self.assertEqual(result["counts"], {
                         "jira.resolved": 1, "jira.open": 1})

    def test_pull_requests_without_jira_have_no_issue(self):
        # With no Jira account, every pull request still says it has no
        # issue, as work.json promises.
        write_prep(temp_output(self), identities={
                   **IDENTITIES, "jira-api": {"absent": True}}, work=None)
        found = {"opened": [
            {"url": "https://github.com/acme/billing/pull/1"}], "merged": [], "reviewed": []}
        with mock.patch.object(fetch_work, "github_work", lambda login, request, run: found):
            result = fetch_work.fetch(PREP)
        with open(result["path"], encoding="utf-8") as f:
            self.assertEqual(json.load(f)["github"]["opened"], [
                             {"url": "https://github.com/acme/billing/pull/1", "issue": None}])


if __name__ == "__main__":
    unittest.main()
