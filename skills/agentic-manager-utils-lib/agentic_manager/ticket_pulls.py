"""Jira tickets' pull requests, shared by every skill that relates tickets to
code: those the Development panels of each ticket and of its sub-tasks list,
which panels may have left some out, and when each was opened, merged and closed.

A sub-task's work is its parent's, as Jira's sprint report rolls it in. The
panel is the link the team's integration made, and GitHub isn't searched for
more: reading the panels' commits cost a request per commit, using up
GitHub's hourly limit in a few runs, and found only pull requests of tickets
the panel already listed some for; a search of titles found none.
"""
import subprocess

from agentic_manager.batch import gather
from agentic_manager.github import pull_events, pull_parts
from agentic_manager.jira import PANEL_LIMIT, key_order
from agentic_manager.json_path import nested

# Jira's condition for the issue types that are sub-tasks.
SUB_TASKS = "issuetype in subTaskIssueTypes()"


def pulls_by_ticket(client, issues):
    """{key: its pull requests} of each of `issues` (Jira issues, with id and
    key), in their order: those the Development panels of the ticket and of
    its sub-tasks list, each once, through the ticket before its sub-tasks,
    those in key order, with `via`, the key of the issue it came through.
    Raises JiraError when Jira can't answer."""
    return pulls_and_full_panels(client, issues)[0]


def pulls_and_full_panels(client, issues):
    """(pulls_by_ticket(), the keys of `issues`, in their order, whose own
    panel or a sub-task's listed PANEL_LIMIT pull requests or more, across
    its code hosts, so may
    have left some out). Raises JiraError when Jira can't answer.

    A full panel is reported, never taken as the ticket's every pull request:
    the panel keeps the most recently updated, and those it leaves out can
    still be open, such as idle drafts (one ticket had 190 on GitHub, 100 in
    its panel, and 88 of the others open)."""
    children = sub_tasks(client, [issue["key"] for issue in issues])
    # Each ticket, then its sub-tasks: (the ticket's key, the issue looked at).
    looked = [(issue["key"], seen) for issue in issues
              for seen in (issue, *children.get(issue["key"], []))]
    panels = gather(looked, lambda pair: panel_pulls(
        client.pull_requests(pair[1]["id"])))
    groups = {issue["key"]: [] for issue in issues}
    full = set()
    for (key, seen), prs in zip(looked, panels):
        groups[key].append([{**pr, "via": seen["key"]} for pr in prs])
        if len(prs) >= PANEL_LIMIT:
            full.add(key)
    return ({key: first_found(*found) for key, found in groups.items()},
            [key for key in groups if key in full])


def sub_tasks(client, keys):
    """{key: its sub-tasks, in key order} of the tickets of `keys`, found by
    one search by parent. Only sub-tasks: an epic is a parent too, but its
    stories are tickets of their own, each with its own code, and an epic,
    not added to sprints, holds none."""
    found = client.search(
        f"parent in ({','.join(keys)}) AND {SUB_TASKS}", ["parent"]) if keys else []
    children = {}
    for issue in sorted(found, key=lambda i: key_order(i["key"])):
        children.setdefault(nested(issue.get("fields"), [
                            "parent", "key"]), []).append(issue)
    return children


def panel_pulls(panel):
    """The pull requests of a ticket's Development panel, as
    JiraClient.pull_requests() returns them, each with the panel's fields
    and its state (the panel's status, or ? without one) and updatedAt."""
    return [{**pr, "state": pr.get("status") or "?", "updatedAt": pr.get("lastUpdate")}
            for pr in panel]


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
    github.pull_events() gives them: when each was opened, merged and closed, and
    GitHub's words for those it says don't exist. Raises GhError for any
    other gh failure."""
    return pull_events([pr["url"] for pr in pulls if pull_parts(pr.get("url"))], run)
