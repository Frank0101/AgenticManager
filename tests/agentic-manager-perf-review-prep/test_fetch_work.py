"""Unit tests for skills/agentic-manager-perf-review-prep/scripts/fetch_work.py.
Run with: python3 tests/run.py agentic-manager-perf-review-prep

Jira is a fake client and gh a fake runner, so nothing reaches a service.
"""

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
import common  # noqa: E402
import fetch_work  # noqa: E402
sys.path.insert(0, TEST_DIR)
from prep_fixture import PERSON, PREP, WORK, temp_output, write_prep  # noqa: E402


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
    first flag, those dated within the search's window."""

    def __init__(self, searches):
        self.searches, self.calls = searches, []

    def __call__(self, command, **kwargs):
        self.calls.append(command)
        args = command[1:]
        if args[:2] == ["auth", "status"]:
            answer = ""
        elif args[1].startswith("user/orgs"):
            answer = json.dumps([{"login": "acme"}])
        else:
            # The PRs of the search's first flag dated within its window: by
            # when they were merged for --merged-at, else opened.
            flag = next(f for f in ("--created", "--merged-at") if f in args)
            start, end = args[args.index(flag) + 1].split("..")
            stamp = "closedAt" if flag == "--merged-at" else "createdAt"
            answer = json.dumps([pr for pr in self.searches.get(args[2], [])
                                 if start <= (pr[stamp] or "")[:10] <= end])
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
        work = fetch_work.jira_work(client, "a1", PERSON)
        self.assertEqual(work, {
            "resolved": [{"key": "PROJ-12", "id": "12", "title": "Migrate billing", "type": "Story",
                          "parent": {"key": "PROJ-1", "title": "Billing", "type": "Epic"}, "status": "Done",
                          "url": "https://acme.atlassian.net/browse/PROJ-12", "date": "2026-09-01"}],
            "open": [{"key": "PROJ-13", "id": "13", "title": "Retire old billing", "type": "Story", "parent": None,
                      "status": "In Progress", "url": "https://acme.atlassian.net/browse/PROJ-13"}]})
        self.assertTrue(
            all('<= "2026-11-10 23:59"' in jql for jql in client.queries))

    def test_github_work(self):
        # Opened and merged as found, dated by when they were opened or
        # merged, only in the organisations gh belongs to.
        run = FakeGh({"--author": [pr(1, closed="2026-09-03T10:00:00Z")]})
        with mock.patch.object(common, "gh_available", return_value=True):
            work = fetch_work.github_work("janedoe", PERSON, run)
        self.assertEqual([(item["number"], item["date"]) for name in ("opened", "merged") for item in work[name]],
                         [(1, "2026-09-01"), (1, "2026-09-03")])
        self.assertEqual(sorted(work), ["merged", "opened"])
        self.assertTrue(all(
            "--owner" in call and "acme" in call for call in run.calls if call[1] == "search"))

    def test_links_pull_requests_to_their_issue(self):
        # A PR an issue's Development panel lists gets that issue, whatever
        # the case of its address; one no issue lists gets none.
        client = FakeJira(
            {"12": [{"url": "https://GitHub.com/acme/billing/pull/1/"}]})
        github = {"opened": [{"url": "https://github.com/acme/billing/pull/1"},
                             {"url": "https://github.com/acme/billing/pull/2"}], "merged": []}
        fetch_work.link_issues(github, fetch_work.linked_prs(
            client, fetch_work.jira_work(client, "a1", PERSON)))
        self.assertEqual([item["issue"]
                         for item in github["opened"]], ["PROJ-12", None])

    def test_a_full_search_is_split(self):
        # A search that comes back full may be cut short: its window is
        # split in halves, each searched again, until none is full; a single
        # day that comes back full stops.
        two_days = [pr(n, created=f"2026-09-0{1 + n % 2}T10:00:00Z")
                    for n in range(fetch_work.SEARCH_LIMIT)]
        run = FakeGh({"--author": two_days})
        found = fetch_work.search(["--author", "janedoe"], "--created", ("2026-09-01", "2026-09-30"),
                                  "acme", run)
        self.assertEqual(sorted(item["number"] for item in found), list(
            range(fetch_work.SEARCH_LIMIT)))
        windows = [call[call.index("--created") + 1] for call in run.calls]
        self.assertEqual((windows[0], len(windows) > 1),
                         ("2026-09-01..2026-09-30", True))
        one_day = [pr(n) for n in range(fetch_work.SEARCH_LIMIT)]
        with self.assertRaisesRegex(SystemExit, "on 2026-09-01, the most it returns"):
            fetch_work.search(["--author", "janedoe"], "--created", ("2026-09-01", "2026-09-30"),
                              "acme", FakeGh({"--author": one_day}))

    def test_fetch(self):
        # Jira by the person's account there, GitHub by their login,
        # each pull request with the issue that lists it, or none; the
        # Notion pages already in work.json are kept, and its facts and
        # commentary dropped, as they no longer match.
        folder = temp_output(self)
        write_prep(folder, work=WORK)
        opened = {"repo": "acme/billing", "number": 1, "title": "PR 1",
                  "url": "https://github.com/acme/billing/pull/1", "date": "2026-09-01"}
        merged = {**opened, "number": 2,
                  "url": "https://github.com/acme/billing/pull/2"}
        logins = []

        def github_work(login, person, run):
            logins.append(login)
            return {"opened": [opened], "merged": [merged]}
        client = FakeJira(
            {"12": [{"url": "https://github.com/acme/billing/pull/1"}]})
        with mock.patch.object(fetch_work, "github_work", github_work):
            result = fetch_work.fetch(PREP, client=client)
        with open(result["path"], encoding="utf-8") as f:
            work = json.load(f)
        self.assertEqual((sorted(work), work["notion"], work["github"]),
                         (["github", "jira", "notion"], WORK["notion"],
                          {"opened": [{**opened, "issue": "PROJ-12"}], "merged": [{**merged, "issue": None}]}))
        self.assertEqual(logins, [PERSON["sources"]["github-cli"]["id"]])
        self.assertTrue(
            all(f'assignee = "{PERSON["sources"]["jira-api"]["id"]}"' in jql for jql in client.queries))
        self.assertEqual(result["counts"], {"jira.resolved": 1, "jira.open": 1,
                                            "github.opened": 1, "github.merged": 1})


if __name__ == "__main__":
    unittest.main()
