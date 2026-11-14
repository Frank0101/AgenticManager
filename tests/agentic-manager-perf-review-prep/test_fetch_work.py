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
from prep_fixture import PERSON, PREP, WORK_RAW, temp_output, write_prep  # noqa: E402


def issue(key, summary, created, resolved=None, parent=None):
    """A Jira issue as search() returns it, assigned to a1 when resolved,
    reported by a1 when not."""
    return {"key": key, "fields": {"summary": summary, "issuetype": {"name": "Story"},
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

    def search(self, jql, fields):
        self.queries.append(jql)
        if jql.startswith("assignee"):
            return [issue("PROJ-12", "Migrate billing", "2026-07-01T10:00:00.000+0100", "2026-09-01T10:00:00.000+0100",
                          {"key": "PROJ-1", "fields": {"summary": "Billing", "issuetype": {"name": "Epic"}}})]
        return [issue("PROJ-13", "Retire old billing", "2026-08-20T10:00:00.000+0100")]


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
                               "created_jql": client.queries[0], "resolved_jql": client.queries[1],
                               "resolved": client.search("assignee", []), "created": client.search("reporter", [])})

    def test_github_raw(self):
        # Opened and merged as gh returns them, only in the organisations gh
        # belongs to, with the same searches on github.com.
        run = FakeGh({"--author": [pr(1, closed="2026-09-03T10:00:00Z")]})
        with mock.patch.object(common, "gh_available", return_value=True):
            raw = fetch_work.github_raw("janedoe", PERSON, run)
        self.assertEqual({key: value for key, value in raw.items() if key not in ("opened", "merged")},
                         {"start": "2026-08-10", "end": "2026-11-10", "orgs": ["acme"],
                          "opened_query": "is:pr author:janedoe created:2026-08-10..2026-11-10 org:acme",
                          "merged_query": "is:pr is:merged author:janedoe merged:2026-08-10..2026-11-10 org:acme"})
        self.assertEqual((raw["opened"], raw["merged"]),
                         ([pr(1, closed="2026-09-03T10:00:00Z")], [pr(1, closed="2026-09-03T10:00:00Z")]))
        self.assertTrue(all(
            "--owner" in call and "acme" in call for call in run.calls if call[1] == "search"))

    def test_a_full_search_is_split(self):
        # A search that comes back full may be cut short: its window is
        # split in halves, each searched again, until none is full; a single
        # day that comes back full stops.
        two_days = [pr(n, created=f"2026-09-0{1 + n % 2}T10:00:00Z")
                    for n in range(fetch_work.SEARCH_LIMIT)]
        run = FakeGh({"--author": two_days})
        found = fetch_work.search(
            ["--author", "janedoe"], "--created", ("2026-09-01", "2026-09-30"), "acme", run)
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
        # Jira by the person's account there, GitHub by their login, each
        # to its raw file; Notion's is in already, so work.json is built
        # from all three.
        folder = temp_output(self)
        write_prep(folder, work=None, raw_work={"notion": WORK_RAW["notion"]})
        logins = []

        def github_raw(login, person, run):
            logins.append(login)
            return WORK_RAW["github"]
        client = FakeJira()
        with mock.patch.object(fetch_work, "github_raw", github_raw):
            result = fetch_work.fetch(PREP, client=client)
        with open(result["raw"][1], encoding="utf-8") as f:
            self.assertEqual(json.load(f), WORK_RAW["github"])
        with open(result["work"], encoding="utf-8") as f:
            work = json.load(f)
        days = common.period_days(PERSON)
        self.assertEqual((work, common.work_problems(work, days)), (common.build_work(
            {"jira": common.read_json(result["raw"][0]), "github": WORK_RAW["github"],
             "notion": WORK_RAW["notion"]}, days), []))
        self.assertEqual(logins, [PERSON["sources"]["github-cli"]["id"]])
        self.assertTrue(
            all(f'"{PERSON["sources"]["jira-api"]["id"]}"' in jql for jql in client.queries))
        self.assertEqual(result["counts"], {"jira.resolved": 1, "jira.created": 1,
                                            "github.opened": 1, "github.merged": 1})


if __name__ == "__main__":
    unittest.main()
