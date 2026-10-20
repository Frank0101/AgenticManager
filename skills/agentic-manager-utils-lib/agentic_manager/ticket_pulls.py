"""A Jira ticket's pull requests, found in three ways, shared by every skill
that relates tickets to code: those its Development panel lists, those on
GitHub that hold the commits the panel lists, and those on GitHub whose title
names its key. Each found pull request is a dict with at least url, state
(such as OPEN or MERGED), updatedAt and `found`, the way that found it
(PANEL, COMMITS or SEARCH); one from the panel also keeps the panel's own
fields, such as its source and destination branches. read_events() then
reads when each was opened and merged, many in one GraphQL call.

Which ways a skill uses, and in what order, is the skill's choice, so each
way is a function of its own and first_found() keeps each pull request once,
as the first way that found it; the panel and its commits come from
jira.JiraClient's pull_requests() and commits(), which a skill calls itself,
alongside its other reads of the ticket.

A pull request names a key only in its title, never in its description: a
key only in a description is a mention, such as "follow-up to PROJ-123",
not the ticket's work; a long description makes a match likelier to be wrong;
and Jira's GitHub integration doesn't link a pull request for it either. The
key is matched whole, so PROJ-1234 doesn't name PROJ-123. As failures.py
sets out, a commit GitHub doesn't have is returned with why, and a gh call
that fails otherwise raises GhError and stops the rest, as batch.gather()
does: a commit, owner or pull request gh couldn't answer for is never left
out as if it held or named nothing.
"""
import subprocess

from agentic_manager.batch import gather
from agentic_manager.github import PULL_URL, pull_events, pulls_holding, search_pull_titles
from agentic_manager.jira import ISSUE_KEY

# How each pull request was found.
PANEL, COMMITS, SEARCH = "panel", "commits", "search"


def panel_pulls(panel):
    """The pull requests of a ticket's Development panel, as
    JiraClient.pull_requests() returns them, each as a found pull request
    that keeps the panel's fields."""
    return [{**pr, "state": pr.get("status") or "?", "updatedAt": pr.get("lastUpdate"), "found": PANEL}
            for pr in panel]


def panel_commits(repositories):
    """(repository, commit) of each commit of a ticket's Development panel,
    as JiraClient.commits() returns its repositories."""
    return [(repository, commit) for repository in repositories for commit in repository.get("commits") or []]


def holding_pulls(commits, run=subprocess.run):
    """[(pair, pulls, why)] for the (repository, commit) pairs of `commits`,
    as panel_commits() gives them, in their order, each as holding_pull()
    gives it. Raises GhError when gh can't tell for one."""
    commits = list(commits)
    return [(pair, *held) for pair, held in zip(commits, gather(commits, lambda pair: holding_pull(pair, run)))]


def holding_pull(pair, run=subprocess.run):
    """(pulls, why): the found pull requests of a (repository, commit) pair's
    GitHub repository that hold the commit, none when no pull request does;
    or none and why GitHub has no such commit. Raises GhError when gh can't
    tell."""
    repository, commit = pair
    pulls, why = pulls_holding(repository.get(
        "name", ""), commit.get("id", ""), run)
    return [{**pr, "found": COMMITS} for pr in pulls or []], why


def search_pulls(key, owners, run=subprocess.run):
    """The found pull requests in the repositories of `owners` whose title
    names `key`, each once. Owners are searched one at a time, in name
    order, as GitHub's search allows few requests a minute. Raises GhError
    when gh can't search one."""
    searched = gather(sorted(owners), lambda owner: search_pull_titles(
        key, owner, run), workers=1)
    found = {pr["url"]: {**pr, "found": SEARCH} for hits in searched for pr in hits
             if key in ISSUE_KEY.findall(pr.get("title") or "")}
    return list(found.values())


def first_found(*groups):
    """The pull requests of `groups`, each once, as the first group that
    holds it found it, in the order found."""
    found = {}
    for group in groups:
        for pr in group:
            found.setdefault(pr["url"], pr)
    return list(found.values())


def read_events(pulls, run=subprocess.run):
    """(events, gone) of each pull request of `pulls` on GitHub, as
    github.pull_events() gives them: when each was opened and merged, and
    GitHub's words for those it says don't exist."""
    return pull_events([pr["url"] for pr in pulls if PULL_URL.match(pr.get("url") or "")], run)
