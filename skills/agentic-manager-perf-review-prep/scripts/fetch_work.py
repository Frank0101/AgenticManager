"""Fetches a prep's person's work in the period from Jira and GitHub into work.json: the items themselves.

The writing step cites work, such as a ticket or a pull request, so each item
keeps its title, date and link; the counts are worked out later, once Notion
is in too. Jira gives the issues resolved in the period and those still
open, which show work carried across it; GitHub the pull requests opened and
merged, only in the organisations the user's gh belongs to, so personal
repositories stay out of a work review, each with the Jira issue that lists
it, so the work counts by epic and what has no ticket shows.
"""
import argparse
import json
import os
import subprocess
from datetime import date, timedelta

from common import (JIRA_SOURCE, PERSON, WORK_LISTS, JiraClient, browse_url, gather,
                    gh_json, gh_orgs, period_days, prep_dir, read_json, require_gh, stops_on_failure,
                    write_work)

JIRA_FIELDS = ["summary", "issuetype", "parent", "resolutiondate", "status"]
PR_FIELDS = "number,title,repository,url,createdAt,closedAt"
SEARCH_LIMIT = 1000
# Each list is one search over the whole period, so few searches run; one
# that comes back full, at SEARCH_LIMIT, may be cut short, so its window is
# split in halves and each searched again. GitHub's secondary rate limit,
# which searches in quick succession meet, is the library's to wait out.
OUTPUT = """Prints one line of JSON: path, the file written, and how many items each list holds.

It writes jira and github to work.json, keeping its Notion pages, and
dropping its facts and commentary, which work_commentary.py works out again:
  jira     resolved, the issues resolved in the period, and open, those
           touched in it and not Done: key, id, title, type, parent ({key,
           title, type}, or null), status, url and, for resolved, date, the
           day it was resolved
  github   opened and merged, each PR's repo, number, title, url, date,
           the day it was opened or merged, and issue, the key of the
           person's Jira issue whose Development panel lists it, or null
"""


def fetch(prep, client=None, run=subprocess.run):
    """Fetch the work of the prep `prep`'s person and write it to work.json;
    returns where it is and how many items each list holds."""
    folder = prep_dir(prep)
    person = read_json(os.path.join(folder, PERSON))
    client = client or JiraClient()
    work = {"jira": jira_work(client, person["sources"][JIRA_SOURCE]["id"], person),
            "github": github_work(person["sources"]["github-cli"]["id"], person, run)}
    link_issues(work["github"], linked_prs(client, work["jira"]))
    path = write_work(prep, work, period_days(person))
    return {"path": path, "counts": {f"{source}.{name}": len(items) for source, lists in work.items()
                                     for name, items in lists.items()}}


# Jira.

def jira_work(client, account, person):
    """{resolved, open}: the Jira issues of the account `account` in the
    review's period in `person`."""
    # Neither filters on the resolution date alone, which Jira doesn't always
    # clear when an issue is reopened; dates are written to the minute, as a
    # literal with seconds silently matches nothing.
    start, end = person["start"], f'{person["end"]} 23:59'
    resolved = client.search(f'assignee = "{account}" AND statusCategory = Done '
                             f'AND resolutiondate >= "{start}" AND resolutiondate <= "{end}"', JIRA_FIELDS)
    still_open = client.search(f'assignee = "{account}" AND statusCategory != Done '
                               f'AND updated >= "{start}" AND updated <= "{end}"', JIRA_FIELDS)
    return {"resolved": [issue_item(client, issue, dated=True) for issue in resolved],
            "open": [issue_item(client, issue, dated=False) for issue in still_open]}


def linked_prs(client, jira):
    """{url: issue key}: the pull requests the Development panel of each
    issue of `jira`, resolved or still open, lists, read four at a time."""
    issues = [item for name in WORK_LISTS["jira"] for item in jira[name]]
    found = gather(issues, lambda item: client.pull_requests(item["id"]))
    return {pull_key(pr["url"]): item["key"] for item, prs in zip(issues, found) for pr in prs if pr.get("url")}


def link_issues(github, linked):
    """Give each pull request of `github` its Jira issue, from `linked`, or
    null when no issue lists it, so the work can be counted by epic and what
    has no ticket shows."""
    for items in github.values():
        for item in items:
            item["issue"] = linked.get(pull_key(item["url"]))


def pull_key(url):
    """A pull request's address as Jira and GitHub can both be matched by:
    lowercase, without a trailing slash."""
    return url.rstrip("/").casefold()


def issue_item(client, issue, dated):
    """An issue as work.json records it, with its resolution day when
    `dated`. Its parent is kept with its type and title, as the work's facts
    count issues by parent, their area."""
    fields = issue["fields"]
    parent = fields.get("parent")
    item = {"key": issue["key"], "id": issue["id"], "title": fields.get("summary") or "",
            "type": fields["issuetype"]["name"],
            "parent": {"key": parent["key"], "title": parent["fields"].get("summary") or "",
                       "type": parent["fields"]["issuetype"]["name"]} if parent else None,
            "status": fields["status"]["name"], "url": browse_url(client.base_url, issue["key"])}
    if dated:
        item["date"] = fields["resolutiondate"][:10]
    return item


# GitHub.

def github_work(login, person, run=subprocess.run):
    """{opened, merged}: the pull requests of the GitHub account `login` in
    the review's period in `person`, in the organisations gh belongs to. Reviews are left out: a search
    finds only the PRs updated in the period, not reviewed in it, and
    checking each one's reviews cost most of the fetch for little value."""
    require_gh(run, "the person's pull requests are fetched")
    period = (person["start"], person["end"])
    lists = {"opened": [], "merged": []}
    for org in gh_orgs(run):
        lists["opened"] += [pr_item(pr, pr["createdAt"]) for pr in search(
            ["--author", login], "--created", period, org, run)]
        lists["merged"] += [pr_item(pr, pr["closedAt"]) for pr in search(
            ["--author", login, "--merged"], "--merged-at", period, org, run)]
    return {name: sorted(items, key=lambda item: (item["date"], item["url"])) for name, items in lists.items()}


def search(flags, date_flag, window, org, run=subprocess.run):
    """The pull requests `gh search prs` finds with `flags` in the
    organisation `org`, dated by `date_flag` within `window`, (first, last)
    as YYYY-MM-DD: a search that comes back full is split in halves, each
    searched the same way, and exits when a single day comes back full."""
    first, last = window
    found = gh_json(["search", "prs", *flags, date_flag, f"{first}..{last}", "--owner", org,
                     "--limit", str(SEARCH_LIMIT), "--json", PR_FIELDS], run)
    if len(found) < SEARCH_LIMIT:
        return found
    if first == last:
        raise SystemExit(f"gh search prs {' '.join(flags)} --owner {org} found {SEARCH_LIMIT} pull requests on "
                         f"{first}, the most it returns, so some may be missing")
    start = date.fromisoformat(first)
    middle = start + (date.fromisoformat(last) - start) // 2
    halves = [search(flags, date_flag, (first, middle.isoformat()), org, run),
              search(flags, date_flag, ((middle + timedelta(days=1)).isoformat(), last), org, run)]
    return list({pr["url"]: pr for half in halves for pr in half}.values())


def pr_item(pr, stamp):
    """A pull request as work.json records it, dated by the day of
    `stamp`."""
    return {"repo": pr["repository"]["nameWithOwner"], "number": pr["number"], "title": pr["title"],
            "url": pr["url"], "date": date.fromisoformat(stamp[:10]).isoformat()}


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Fetch the prep's person's work in the period from Jira and GitHub into work.json.",
        epilog=OUTPUT, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--prep", required=True,
                        help="the prep's folder, <Person>_<YY-MM-DD>, as init_prep.py printed it")
    args = parser.parse_args(argv)
    with stops_on_failure():
        print(json.dumps(fetch(args.prep), ensure_ascii=False))


if __name__ == "__main__":
    main()
