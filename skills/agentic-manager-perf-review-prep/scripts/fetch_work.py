"""Fetches a prep's person's work in the period from Jira and GitHub into their raw files, which work.json is built from.

Each raw file keeps what the API returned, with the period and the searches
that found it, so whose each item is can be checked again without searching
again. Jira gives the issues the person resolved in the period and those
they created in it, whatever their status now; GitHub the pull requests they
opened and merged, only in the organisations gh belongs to, so personal
repositories stay out. Done is a status's category, never a resolution date
alone, which Jira doesn't always clear when an issue is reopened.
"""
import argparse
import json
import os
import subprocess
from datetime import date, timedelta

from common import (JIRA_SOURCE, PERSON, JiraClient, gh_json, gh_orgs, period_days, prep_dir, read_json, require_gh,
                    stops_on_failure, WORK_LISTS, write_work)

JIRA_FIELDS = ["summary", "issuetype", "parent", "resolutiondate", "created", "status", "assignee", "reporter",
               "updated"]
PR_FIELDS = "number,title,repository,url,createdAt,closedAt,author,updatedAt"
SEARCH_LIMIT = 1000
# Each list is one search over the whole period, so few searches run; one
# that comes back full, at SEARCH_LIMIT, may be cut short, so its window is
# split in halves and each searched again. GitHub's secondary rate limit,
# which searches in quick succession meet, is the library's to wait out.
OUTPUT = """Prints one line of JSON: raw, the raw files written, work, work.json's path once
set_notion.py has recorded Notion too, else null, and how many items each list holds.

It writes each source's raw file in the prep's _raw, and work.json once
every source's is in:
  jira     start and end, the period; base_url, the Jira site's; resolved,
           the issues assigned to the person and resolved in the period, and
           created, those they created in it, as Jira's search returns them;
           and resolved_jql and created_jql, the searches that found them
  github   start and end; orgs, the organisations searched; opened and
           merged, the person's pull requests opened and merged in the
           period, as gh's search returns them; and opened_query and
           merged_query, the same searches on github.com
"""


def fetch(prep, client=None, run=subprocess.run):
    """Fetch the work of the prep `prep`'s person and write it to its raw
    files, and work.json once Notion is in too; returns where they are and
    how many items each list holds."""
    folder = prep_dir(prep)
    person = read_json(os.path.join(folder, PERSON))
    raws = {"jira": jira_raw(client or JiraClient(), person["sources"][JIRA_SOURCE]["id"], person),
            "github": github_raw(person["sources"]["github-cli"]["id"], person, run)}
    written = [write_work(prep, source, raw, period_days(person))
               for source, raw in raws.items()]
    return {"raw": [paths["raw"] for paths in written], "work": written[-1]["work"],
            "counts": {f"{source}.{name}": len(raw[name]) for source, raw in raws.items() for name in WORK_LISTS[source]}}


# Jira.

def jira_raw(client, account, person):
    """Jira's raw file: the issues the account `account` resolved and those
    it created in the review's period in `person`, with the searches."""
    # Dates are written to the minute, as a literal with seconds silently
    # matches nothing.
    start, end = person["start"], f'{person["end"]} 23:59'
    jqls = {"resolved": f'assignee = "{account}" AND statusCategory = Done '
            f'AND resolutiondate >= "{start}" AND resolutiondate <= "{end}"',
            "created": f'reporter = "{account}" AND created >= "{start}" AND created <= "{end}"'}
    return {"start": person["start"], "end": person["end"], "base_url": client.base_url,
            **{f"{name}_jql": jql for name, jql in jqls.items()},
            **{name: client.search(jql, JIRA_FIELDS) for name, jql in jqls.items()}}


# GitHub.

def github_raw(login, person, run=subprocess.run):
    """GitHub's raw file: the pull requests the account `login` opened and
    merged in the review's period in `person`, in the organisations gh
    belongs to, with the same searches on github.com."""
    require_gh(run, "the person's pull requests are fetched")
    period, window = (person["start"], person["end"]
                      ), f'{person["start"]}..{person["end"]}'
    orgs = gh_orgs(run)
    in_orgs = [f"org:{org}" for org in orgs]
    raw = {"start": person["start"], "end": person["end"], "orgs": orgs,
           "opened_query": " ".join(["is:pr", f"author:{login}", f"created:{window}", *in_orgs]),
           "merged_query": " ".join(["is:pr", "is:merged", f"author:{login}", f"merged:{window}", *in_orgs]),
           "opened": [], "merged": []}
    for org in orgs:
        raw["opened"] += search(["--author", login],
                                "--created", period, org, run)
        raw["merged"] += search(["--author", login, "--merged"],
                                "--merged-at", period, org, run)
    return raw


def search(flags, date_flag, window, org, run=subprocess.run):
    """The pull requests `gh search prs` finds with `flags` in the
    organisation `org`, dated by
    `date_flag` within `window`, (first, last) as YYYY-MM-DD: a search that
    comes back full is split in halves, each searched the same way, and
    exits when a single day comes back full, as some would be missing."""
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


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Fetch the prep's person's work in the period from Jira and GitHub into their raw files, and build work.json once Notion's is in too.",
        epilog=OUTPUT, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--prep", required=True,
                        help="the prep's folder, <Person>_<YY-MM-DD>, as init_prep.py printed it")
    args = parser.parse_args(argv)
    with stops_on_failure():
        print(json.dumps(fetch(args.prep), ensure_ascii=False))


if __name__ == "__main__":
    main()
