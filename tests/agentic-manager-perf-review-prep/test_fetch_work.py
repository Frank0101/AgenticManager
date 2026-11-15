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
import build_data  # noqa: E402
import common  # noqa: E402
import fetch_work  # noqa: E402
sys.path.insert(0, TEST_DIR)
from prep_fixture import PERSON, PREP, WORK_RAW, temp_output, write_prep  # noqa: E402
# The fake gh's GraphQL answers follow the library's query.
sys.path.insert(0, os.path.join(os.path.dirname(
    TEST_DIR), "agentic-manager-utils-lib"))
from gh_fake import is_search, search_answer  # noqa: E402


def issue(key, summary, created, resolved=None, parent=None):
    """A Jira issue as search() returns it, assigned to a1 when resolved,
    reported by a1 when not."""
    return {"key": key, "fields": {"summary": summary, "issuetype": {"name": "Story", "subtask": False},
                                   "status": {"name": "Done" if resolved else "In Progress"},
                                   "created": created, "resolutiondate": resolved, "parent": parent,
                                   "assignee": {"accountId": "a1"} if resolved else None,
                                   "reporter": {"accountId": "a2" if resolved else "a1"},
                                   "updated": resolved or created}}


class FakeJira:
    """Answers search() by whether the JQL asks for the issues the person
    resolved or those they created, recording each query."""
    base_url = "https://acme.atlassian.net"

    def __init__(self):
        self.queries = []

    def points_fields(self):
        return ["customfield_10016"]

    def search(self, jql, fields):
        self.queries.append(jql)
        if jql.startswith("assignee"):
            return [issue("PROJ-12", "Migrate billing", "2026-07-01T10:00:00.000+0100", "2026-09-01T10:00:00.000+0100",
                          {"key": "PROJ-1", "fields": {"summary": "Billing", "issuetype": {"name": "Epic", "subtask": False}}})]
        return [issue("PROJ-13", "Retire old billing", "2026-08-20T10:00:00.000+0100")]


class FakeGh:
    """A gh runner, signed in to one organisation, whose GraphQL search finds
    `pulls`, those its window dates, by when they were opened or merged."""

    def __init__(self, pulls):
        self.pulls, self.calls = pulls, []

    def __call__(self, command, **kwargs):
        self.calls.append(command)
        args = command[1:]
        if is_search(args):
            return subprocess.CompletedProcess(command, *search_answer(args, self.pulls))
        answer = json.dumps([{"login": "acme"}]) if args[1].startswith(
            "user/orgs") else ""
        return subprocess.CompletedProcess(command, 0, answer, "")


def pr(number, created="2026-09-01T10:00:00Z", merged=None):
    """A pull request as GitHub's search returns it."""
    return {"number": number, "title": f"PR {number}", "repository": {"nameWithOwner": "acme/billing"},
            "url": f"https://github.com/acme/billing/pull/{number}", "createdAt": created, "mergedAt": merged,
            "additions": 10, "deletions": 2, "changedFiles": 1}


class FetchWorkTest(unittest.TestCase):
    def test_jira_raw(self):
        # Those the person created in the period, whatever their status, and
        # those they resolved in it, as Jira returns them, with the searches;
        # JQL dates to the minute.
        client = FakeJira()
        raw = fetch_work.jira_raw(client, "a1", PERSON)
        self.assertEqual(client.queries, [
            'reporter = "a1" AND created >= "2026-08-10" AND created <= "2026-11-10 23:59"',
            'assignee = "a1" AND statusCategory = Done AND resolutiondate >= "2026-08-10" '
            'AND resolutiondate <= "2026-11-10 23:59"'])
        self.assertEqual(raw, {"start": "2026-08-10", "end": "2026-11-10", "base_url": FakeJira.base_url,
                               "points_fields": ["customfield_10016"], "parents": [],
                               "created_jql": client.queries[0], "resolved_jql": client.queries[1],
                               "resolved": client.search("assignee", []), "created": client.search("reporter", [])})

    def test_jira_raw_with_sub_tasks(self):
        # The stories the sub-tasks belong to are fetched once, for their
        # epics, and a sub-task counts in its story's epic.
        epic = {"key": "PROJ-2", "fields": {"summary": "Invoices",
                                            "issuetype": {"name": "Epic", "subtask": False}}}
        story = {"key": "PROJ-20", "fields": {"summary": "Invoice export", "issuetype": {"name": "Story", "subtask": False},
                                              "parent": epic}}
        sub_task = issue("PROJ-21", "Export CSV", "2026-08-12T10:00:00.000+0100", "2026-09-02T10:00:00.000+0100",
                         {"key": "PROJ-20", "fields": {"summary": "Invoice export",
                                                       "issuetype": {"name": "Story", "subtask": False}}})
        sub_task["fields"]["issuetype"] = {"name": "Sub-task", "subtask": True}

        class WithSubTask(FakeJira):
            def search(self, jql, fields):
                self.queries.append(jql)
                if jql.startswith("key in"):
                    return [story]
                return [sub_task] if jql.startswith("assignee") else []
        client = WithSubTask()
        raw = fetch_work.jira_raw(client, "a1", PERSON)
        self.assertEqual(
            (client.queries[-1], raw["parents"]), ("key in (PROJ-20)", [story]))
        item = common.work_items("jira", raw)["resolved"][0]
        self.assertEqual(item["epic"], {"key": "PROJ-2", "title": "Invoices",
                                        "url": "https://acme.atlassian.net/browse/PROJ-2"})
        # Its epic's search finds it through its story.
        self.assertIn("AND%20%28parent%20in%20%28PROJ-20%29%29",
                      build_data.epic_search_urls(raw)["PROJ-2"])

    def test_github_raw(self):
        # Opened and merged, each with its size, as GitHub's search returns
        # them, only in the organisations gh belongs to, with the same
        # searches on github.com.
        merged, opened = pr(1, merged="2026-09-03T10:00:00Z"), pr(
            2, created="2026-08-01T10:00:00Z")
        run = FakeGh([merged, opened])
        with mock.patch("agentic_manager.github.gh_available", return_value=True):
            raw = fetch_work.github_raw("janedoe", PERSON, run)
        self.assertEqual(raw, {"start": "2026-08-10", "end": "2026-11-10", "orgs": ["acme"],
                               "opened_query": "is:pr author:janedoe org:acme created:2026-08-10..2026-11-10",
                               "merged_query": "is:pr is:merged author:janedoe org:acme merged:2026-08-10..2026-11-10",
                               "opened": [merged], "merged": [merged]})

    def test_fetch(self):
        # gh checked first; then Jira by the person's account there, GitHub
        # by their login, each to its raw file, nothing else.
        folder = temp_output(self)
        write_prep(folder, data=None, raw_work={"notion": WORK_RAW["notion"]})
        logins = []

        def github_raw(login, person, run):
            logins.append(login)
            return WORK_RAW["github"]
        client = FakeJira()
        with mock.patch.object(fetch_work, "github_raw", github_raw), \
                mock.patch.object(fetch_work, "require_gh") as require_gh:
            result = fetch_work.fetch(PREP, client=client)
        require_gh.assert_called_once()
        with open(result["raw"][1], encoding="utf-8") as f:
            self.assertEqual(json.load(f), WORK_RAW["github"])
        self.assertFalse(os.path.exists(
            os.path.join(folder, PREP, common.DATA)))
        self.assertEqual(logins, [PERSON["sources"]["github-cli"]["id"]])
        self.assertTrue(
            all(f'"{PERSON["sources"]["jira-api"]["id"]}"' in jql for jql in client.queries))
        self.assertEqual(result["counts"], {"jira.resolved": 1, "jira.created": 1,
                                            "github.opened": 1, "github.merged": 1})


if __name__ == "__main__":
    unittest.main()
