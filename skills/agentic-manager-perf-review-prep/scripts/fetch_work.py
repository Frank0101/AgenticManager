"""Fetches a prep's person's work in the period from Jira and GitHub into work.json: the items, never metrics.

The writing step cites work, such as a ticket or a pull request, more than it
weighs averages, so each item keeps its title, date and link, and nothing is
computed from them. Jira gives the issues resolved in the period and those
still open, which show work carried across it; GitHub the pull requests
opened, merged and reviewed, only in the organisations the user's gh belongs
to, so personal repositories stay out of a work review, each with the Jira
issue that lists it, so the work counts by epic and what has no ticket shows.
"""
import argparse
import json
import os
import subprocess
import time
from datetime import date

from common import (ABSENT, IDENTITIES, REQUEST, WORK, GhError, JiraClient, browse_url, gather, gh_available, gh_json, gh_orgs,
                    gh_signed_in, months_of, prep_dir, read_json, stops_on_failure, write_prep_file)

JIRA_FIELDS = ["summary", "issuetype", "parent", "resolutiondate", "status"]
PR_FIELDS = "number,title,repository,url,createdAt,closedAt"
SEARCH_LIMIT = 1000
# GitHub allows about 30 searches a minute, each page of results counting as
# one, and refuses calls made in quick succession with its secondary rate
# limit, so searches run one at a time, SEARCH_PAUSE seconds apart, a month
# each to keep every one to few pages; one GitHub refuses so is tried again
# after waiting LIMIT_WAIT seconds, as it asks, LIMIT_TRIES times at most.
SEARCH_PAUSE = 5
LIMIT_WAIT = 60
LIMIT_TRIES = 3
# Pull requests whose reviews one GraphQL call reads.
REVIEW_BATCH = 50
OUTPUT = """Prints one line of JSON: path, the file written, and how many items each list holds.

work.json holds, for a source the person isn't in, {"absent": true}, else:
  jira     resolved, the issues resolved in the period, and open, those
           touched in it and not Done: key, id, title, type, parent ({key,
           title, type}, or null), status, url and, for resolved, date, the
           day it was resolved
  github   opened, merged and reviewed, each PR's repo, number, title, url,
           date, the day it was opened, merged, or first reviewed by the
           person in the period, and issue, the key of the person's Jira
           issue whose Development panel lists it, or null for none
"""


def fetch(prep, client=None, run=subprocess.run):
    """Fetch the work of the prep `prep`'s person and write it to work.json;
    returns where it is and how many items each list holds."""
    folder = prep_dir(prep)
    request = read_json(os.path.join(folder, REQUEST))
    identities = read_json(os.path.join(folder, IDENTITIES))
    jira = identities["jira-api"]
    github = identities["github-cli"]
    client = None if jira == ABSENT else client or JiraClient()
    work = {"jira": ABSENT if client is None else jira_work(client, jira["id"], request),
            "github": ABSENT if github == ABSENT else github_work(github["id"], request, run)}
    if work["github"] != ABSENT:
        link_issues(work["github"], {} if client is None else linked_prs(
            client, work["jira"]))
    path = write_prep_file(prep, WORK, work)
    return {"path": path, "counts": {f"{source}.{name}": len(items) for source, lists in work.items()
                                     if lists != ABSENT for name, items in lists.items()}}


# Jira.

def jira_work(client, account, request):
    """{resolved, open}: the Jira issues of the account `account` in the
    period of `request`."""
    # Neither filters on the resolution date alone, which Jira doesn't always
    # clear when an issue is reopened; dates are written to the minute, as a
    # literal with seconds silently matches nothing.
    start, end = request["start"], f'{request["end"]} 23:59'
    resolved = client.search(f'assignee = "{account}" AND statusCategory = Done '
                             f'AND resolutiondate >= "{start}" AND resolutiondate <= "{end}"', JIRA_FIELDS)
    still_open = client.search(f'assignee = "{account}" AND statusCategory != Done '
                               f'AND updated >= "{start}" AND updated <= "{end}"', JIRA_FIELDS)
    return {"resolved": [issue_item(client, issue, dated=True) for issue in resolved],
            "open": [issue_item(client, issue, dated=False) for issue in still_open]}


def linked_prs(client, jira):
    """{url: issue key}: the pull requests the Development panel of each
    issue of `jira`, resolved or still open, lists, read four at a time."""
    issues = [item for name in ("resolved", "open") for item in jira[name]]
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
    `dated`. Its parent is kept with its type, so the writing step groups by
    epic where the parent is one."""
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

def github_work(login, request, run=subprocess.run, pause=time.sleep):
    """{opened, merged, reviewed}: the pull requests of the GitHub account
    `login` in the period of `request`, in the organisations gh belongs to,
    searched a month at a time, `pause` between searches, and their reviews
    read in GraphQL batches."""
    if not gh_available():
        raise SystemExit("gh isn't installed or the github-cli source isn't enabled: the person's pull requests "
                         "are fetched with it")
    if not gh_signed_in(run):
        raise SystemExit(
            "gh isn't signed in: run gh auth login, then run this again")
    windows = [f'{month["start"]}..{month["end"]}' for month in months_of(
        date.fromisoformat(request["start"]), date.fromisoformat(request["end"])).values()]
    lists = {"opened": [], "merged": [], "reviewed": []}
    for org in gh_orgs(run):
        candidates = {}
        for window in windows:
            lists["opened"] += [pr_item(pr, pr["createdAt"]) for pr in search(
                ["--author", login, "--created", window], org, run, pause)]
            lists["merged"] += [pr_item(pr, pr["closedAt"]) for pr in search(
                ["--author", login, "--merged", "--merged-at", window], org, run, pause)]
            # The search only finds PRs updated with them as a reviewer: each
            # one's reviews tell whether they reviewed it in the period. A PR
            # updated in two months is found twice, and read once.
            candidates.update((pr["url"], pr) for pr in search(
                ["--reviewed-by", login, "--updated", window], org, run, pause))
        days = review_days(list(candidates.values()), login, request, run)
        lists["reviewed"] += [pr_item(pr, days[url])
                              for url, pr in candidates.items() if days.get(url)]
    return {name: sorted(items, key=lambda item: (item["date"], item["url"])) for name, items in lists.items()}


def search(flags, org, run=subprocess.run, pause=time.sleep):
    """The pull requests `gh search prs` finds with `flags` in the
    organisation `org`, after `pause`; stops when the search fills its last
    page, which may be cut short, rather than counting what came back."""
    found = []
    for attempt in range(1, LIMIT_TRIES + 1):
        pause(SEARCH_PAUSE)
        try:
            found = gh_json(["search", "prs", *flags, "--owner", org,
                             "--limit", str(SEARCH_LIMIT), "--json", PR_FIELDS], run)
            break
        except GhError as error:
            if "secondary rate limit" not in error.message or attempt == LIMIT_TRIES:
                raise
            pause(LIMIT_WAIT)
    if len(found) >= SEARCH_LIMIT:
        raise SystemExit(f"gh search prs {' '.join(flags)} --owner {org} found {SEARCH_LIMIT} pull requests, the "
                         "most it returns in a month, so some may be missing")
    return found


def review_days(prs, login, request, run=subprocess.run):
    """{url: day} of the pull requests `prs` the account `login` reviewed in
    the period of `request`: the first day it submitted a review in it. Asks
    GraphQL for the reviews of REVIEW_BATCH of them at once, rather than one
    call each, which for a busy reviewer takes most of the fetch."""
    days = {}
    for start in range(0, len(prs), REVIEW_BATCH):
        batch = prs[start:start + REVIEW_BATCH]
        fields = " ".join(
            f'p{n}: repository(owner: {json.dumps(owner)}, name: {json.dumps(name)}) '
            f'{{ pullRequest(number: {pr["number"]}) {{ reviews(first: 100, author: {json.dumps(login)}) '
            "{ pageInfo { hasNextPage } nodes { submittedAt } } } }"
            for n, pr in enumerate(batch) for owner, name in [pr["repository"]["nameWithOwner"].split("/", 1)])
        data = gh_json(
            ["api", "graphql", "-f", f"query=query {{ {fields} }}"], run).get("data") or {}
        for n, pr in enumerate(batch):
            reviews = (((data.get(f"p{n}") or {}).get(
                "pullRequest") or {}).get("reviews") or {})
            if (reviews.get("pageInfo") or {}).get("hasNextPage"):
                raise SystemExit(
                    f"{pr['url']} has over 100 reviews by {login}: too many to read in one call")
            in_period = sorted(node["submittedAt"][:10] for node in reviews.get("nodes", [])
                               if node.get("submittedAt") and request["start"] <= node["submittedAt"][:10] <= request["end"])
            if in_period:
                days[pr["url"]] = in_period[0]
    return days


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
