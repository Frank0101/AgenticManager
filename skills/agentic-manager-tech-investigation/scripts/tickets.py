"""Reads tickets from Jira: each one in full, with its sprints, history, children,
links, web links and comments, and with --prs its pull requests and what each
changed; the tickets a JQL query finds, one line each; and the discussion of the
pull requests the investigation picks from them.

One call prints, as plain text, what an MCP took a call per ticket, child, link
and pull request to answer, each with every field. A ticket or pull request the
service has none of, or of a project the user excludes, is answered with why in
its place; any other failure stops the script, as the library's failures.py says.
"""
import argparse
import re
import subprocess
import sys

from common import (GH_UNAVAILABLE, PROJECT_KEY, PULLS_UNREAD, JiraClient, pull_parts, browse_url, gather, gh_available, gh_found, nested, plain_text,
                    pulls_by_ticket, stops_on_failure)

FIELDS = ["summary", "status", "issuetype", "parent", "created", "updated", "resolutiondate",
          "labels", "fixVersions", "issuelinks", "description", "assignee"]
# The changes printed as the ticket's history, by how the changelog names them.
HISTORY = {"status": "status", "sprint": "Sprint"}
LINE_FIELDS = ["summary", "status", "issuetype", "parent"]
# The field sites use for acceptance criteria, found by its name.
CRITERIA = "acceptance criteria"
# What a pull request changed is read with.
GH_PR_FIELDS = "mergeCommit,mergedAt,changedFiles,files,commits"
# What a pull request's discussion is read with.
GH_DISCUSSION_FIELDS = ("title,state,author,body,reviews,comments,createdAt,mergedAt,baseRefName,"
                        "headRefName,mergeCommit,url")


def ticket(client, key, site, prs, gh, run=subprocess.run):
    """Everything printed for one ticket, as text: with `prs`, its pull
    requests too, read only when `gh`. Text is printed in full, links kept,
    since tickets are read in full and the pages they link are followed."""
    criteria, sprint = site["criteria"], site["sprint"]
    issue, unread = client.issue(
        key, FIELDS + [f for f in (criteria, sprint) if f])
    if issue is None:
        return unread
    fields = issue["fields"]
    current = issue["key"]
    calls = {"children": lambda: client.search(f"parent = {current} ORDER BY key", LINE_FIELDS),
             "comments": lambda: client.comments(current),
             "remote": lambda: client.remote_links(current),
             "history": lambda: client.field_changes(current, HISTORY)}
    read = dict(zip(calls, gather(calls.values(), lambda call: call())))
    children, comments = read["children"], read["comments"]
    parent = fields.get("parent")
    out = [f"{line(issue)} · {browse_url(client.base_url, current)}"]
    if current != key:
        out.append(f"Moved: {key} is now {current}")
    out += [f"Parent: {line(parent)}" if parent else "Parent: none",
            f"Created {day(fields.get('created'))} · updated {day(fields.get('updated'))} · "
            f"resolved {day(fields.get('resolutiondate'))}",
            "Assignee: " + nested(fields, ["assignee", "displayName"], "none"),
            "Labels: " + (", ".join(fields.get("labels") or [])
                          or "none") + " · Fix versions: "
            + (", ".join(v.get("name", "?")
               for v in fields.get("fixVersions") or []) or "none"),
            "", "Description:", indented(plain_text(fields.get("description"), links=True))]
    if criteria:
        out += ["", "Acceptance criteria:",
                indented(plain_text(fields.get(criteria), links=True))]
    lines = links(issue)
    sprints = sprint_lines(fields.get(sprint)) if sprint else []
    history = history_lines(read["history"])
    web = web_link_lines(read["remote"])
    out += ["", f"Sprints ({len(sprints)}):", *sprints,
            "", f"History ({len(history)}):", *history,
            "", f"Children ({len(children)}):", *
            (f"  {line(c)}" for c in children),
            "", f"Links ({len(lines)}):", *(f"  {entry}" for entry in lines),
            "", f"Web links ({len(web)}):", *web]
    if prs:
        out += ["", *pull_section(client, issue, gh, run)]
    out += ["", f"Comments ({len(comments)}):"]
    for comment in comments:
        author = nested(comment, ["author", "displayName"], "?")
        text = plain_text(comment.get("body"),
                          links=True).replace("\n", "\n    ")
        out.append(f"  {day(comment.get('created'))} · {author}: {text}")
    return "\n".join(out)


def links(issue):
    """Each link as 'relation KEY · type · status · summary'."""
    out = []
    for link in nested(issue, ["fields", "issuelinks"], []):
        side = "outwardIssue" if "outwardIssue" in link else "inwardIssue"
        if other := link.get(side):
            relation = nested(
                link, ["type", "outward" if side == "outwardIssue" else "inward"], "links")
            out.append(f"{relation} {line(other)}")
    return out


def line(issue):
    """A ticket on one line: key, type, status and summary."""
    fields = issue.get("fields") or {}
    return " · ".join([issue["key"], name_of(fields, "issuetype"), name_of(fields, "status"),
                       fields.get("summary") or ""])


def name_of(fields, field):
    return nested(fields, [field, "name"], "?")


def indented(text):
    return "\n".join(f"  {row}" if row.strip() else "" for row in text.split("\n")) if text else "  none"


def day(stamp):
    return stamp[:10] if stamp else "none"


def pull_section(client, issue, gh, run=subprocess.run):
    """The pull requests' lines: those the Development panels of the ticket and
    of its sub-tasks list, as the library reads them for every skill, each with
    what gh says it changed. Commits matter only as part of a pull request, and
    the current code comes from cloning the repository, so neither the panel's
    commits nor GitHub's pull requests naming the key are read. Without gh, no
    panel is read either, and the lines say so."""
    if not gh:
        return ["Pull requests (not read):", f"  {PULLS_UNREAD}"]
    pulls = pulls_by_ticket(client, [issue])[issue["key"]]
    return [f"Pull requests ({len(pulls)}):", *(f"  {entry}" for entry in pr_lines(pulls, view(pulls, run), issue["key"]))]


def pr_lines(pulls, details, key):
    """The pull request lines, in the order found, each with the panel's
    branches, the sub-task it came through when not the ticket `key`, and
    what gh adds."""
    out = []
    for pr in pulls:
        branches = [nested(pr, ["source", "branch"], "?"),
                    nested(pr, ["destination", "branch"], "?")]
        via = [f"via {pr['via']}"] if pr.get("via") != key else []
        out.append(" · ".join([pr_label(pr.get("url")), pr["state"], " → ".join(branches),
                               f"updated {day(pr.get('updatedAt'))}", pr.get("url", ""), *via]))
        out += detail_lines(details.get(pr.get("url")))
    return out


def pr_label(url):
    parts = pull_parts(url)
    return f"{parts['owner']}/{parts['name']}#{parts['number']}" if parts else url


def detail_lines(detail):
    """What gh adds to a pull request's line: its merge, files changed and
    commits, or why GitHub has none (a line of text)."""
    if isinstance(detail, str):
        return [f"    {detail}"]
    if not detail:
        return ["    not a GitHub pull request: gh doesn't read it"]
    merge = nested(detail, ["mergeCommit", "oid"])
    files = [f["path"] for f in detail.get("files") or []]
    commits = detail.get("commits") or []
    head = f"    merge commit {merge} on {day(detail.get('mergedAt'))}" if merge else "    not merged"
    shown = f"{len(files)} of {detail.get('changedFiles')}" if detail.get(
        "changedFiles", len(files)) != len(files) else str(len(files))
    return [head + f" · files changed ({shown}): " + (", ".join(files) or "none"),
            f"    commits ({len(commits)}):",
            *(f"      {c.get('oid') or '?'} · {day(c.get('committedDate'))} · {c.get('messageHeadline') or ''}"
              for c in commits)]


def view(prs, run=subprocess.run):
    """{url: gh's details, or why GitHub has no such pull request} of the
    pull requests of `prs` on GitHub."""
    urls = [pr["url"] for pr in prs if pull_parts(pr.get("url"))]
    read = gather(urls, lambda url: gh_found(
        ["pr", "view", url, "--json", GH_PR_FIELDS], "pull request", run))
    return {url: detail if why is None else why for url, (detail, why) in zip(urls, read)}


def sprint_lines(sprints):
    """Each sprint the ticket was in: name, state and goal, on one line."""
    return [f"  {s.get('name', '?')} · {s.get('state', '?')} · goal: {' '.join((s.get('goal') or 'none').split())}"
            for s in sprints or []]


def history_lines(changes):
    """Each status or sprint change, dated, in time order."""
    return [f"  {day(c['created'])} · {c['field']}: {c.get('fromString') or 'none'} → "
            f"{c.get('toString') or 'none'}" for c in changes]


def web_link_lines(remote):
    """Each web link: title and URL."""
    return [f"  {nested(r, ['object', 'title'], '?')} · {nested(r, ['object', 'url'], '?')}" for r in remote]


def site_fields(client):
    """{criteria, sprint}: the ids of the site's acceptance criteria and
    Sprint fields, each None when the site has none."""
    return {"criteria": criteria_field(client), "sprint": client.sprint_field()}


def criteria_field(client):
    """The id of the field named as acceptance criteria, or None."""
    return next((ident for name, ident in client.field_ids().items() if (name or "").casefold() == CRITERIA), None)


def moved_projects(client, jql):
    """Why a search found nothing, for each project its query names: a project
    renamed since is found by its old key under its current one, and a search
    on the old key returns nothing, without an error."""
    keys = re.findall(rf'\bproject\s*=\s*"?({PROJECT_KEY})\b', jql, re.I)
    for listed in re.findall(r"\bproject\s+in\s*\(([^)]*)\)", jql, re.I):
        keys += re.findall(rf'"?({PROJECT_KEY})\b', listed)
    notes = []
    for key in dict.fromkeys(keys):
        project = client.project(key)
        current = project.get("key") if isinstance(project, dict) else None
        if current is None:
            notes.append(f"No project {key} that the account can see")
        elif current != key:
            notes.append(
                f"Moved: project {key} is now {current}: search under {current}")
    return notes


def search_line(issue):
    """A search result on one line, with its parent."""
    parent = nested(issue, ["fields", "parent", "key"])
    return line(issue) + (f" · parent {parent}" if parent else "")


def pr_discussion(url, run=subprocess.run):
    """Everything printed for one pull request: its description, reviews,
    review comments on code lines and conversation comments, in full. A
    command of its own: which pull requests matter is known only once the
    ticket is read, and printed for every one they would make a ticket with
    many pull requests long."""
    parts = pull_parts(url)
    if not parts:
        return f"{url}: not a GitHub pull request"
    pr, why = gh_found(
        ["pr", "view", url, "--json", GH_DISCUSSION_FIELDS], "pull request", run)
    if why:
        return f"{url}: {why}"
    # Every page, as one list of pages: a filter would run on each page apart.
    pages, why = gh_found(["api", f"repos/{parts['owner']}/{parts['name']}/pulls/{parts['number']}/comments?per_page=100", "--paginate",
                           "--slurp"], "pull request", run)
    if why:
        return f"{url}: {why}"
    inline = [comment for page in pages for comment in page]
    merge = nested(pr, ["mergeCommit", "oid"])
    reviews, comments = pr.get("reviews") or [], pr.get("comments") or []
    return "\n".join([
        f"{pr_label(url)} · {pr.get('state', '?')} · {pr.get('title', '')} · {url}",
        f"By {who(pr)} · {pr.get('headRefName', '?')} → {pr.get('baseRefName', '?')} · opened "
        f"{day(pr.get('createdAt'))} · "
        + (f"merged {day(pr.get('mergedAt'))} · merge commit {merge}" if merge else "not merged"),
        "", "Description:", indented((pr.get("body") or "").strip()),
        "", f"Reviews ({len(reviews)}):",
        *(f"  {day(r.get('submittedAt'))} · {who(r)} · {r.get('state', '?')}: {said(r.get('body'))}"
          for r in reviews),
        "", f"Review comments ({len(inline)}):",
        *(f"  {day(c.get('created_at'))} · {nested(c, ['user', 'login'], '?')} · {c.get('path', '?')}:"
          f"{c.get('line') or c.get('original_line') or '?'}: {said(c.get('body'))}" for c in inline),
        "", f"Comments ({len(comments)}):",
        *(f"  {day(c.get('createdAt'))} · {who(c)}: {said(c.get('body'))}" for c in comments)])


def who(item):
    """The author of a pull request, review or comment, as gh names it."""
    return nested(item, ["author", "login"], "?")


def said(body):
    return (body or "no text").strip().replace("\n", "\n    ")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Read tickets from Jira.")
    commands = parser.add_subparsers(dest="command", required=True)
    show = commands.add_parser("show", help="print tickets in full, with their sprints, history, children, "
                               "links, web links and comments, and with --prs their pull requests",
                               description="print tickets in full, with their sprints, history, children, "
                               "links, web links and comments, and with --prs their pull requests")
    show.add_argument("keys", nargs="+", metavar="KEY", help="a ticket's key, such as PROJ-123; give several "
                      "for one call")
    show.add_argument("--prs", action="store_true",
                      help="also print each ticket's pull requests, those the Development panels of it and of "
                      "its sub-tasks list, with what each changed: merge commit, files and commits; read only "
                      "with gh. An epic has no sub-tasks: show its stories for theirs")
    pr = commands.add_parser("pr", help="print pull requests' descriptions, reviews and comments in full",
                             description="print pull requests' descriptions, reviews and comments in full")
    pr.add_argument("urls", nargs="+", metavar="URL", help="a pull request's URL, as show prints it; give "
                    "several for one call")
    search = commands.add_parser("search", help="print the tickets a JQL query finds, one line each",
                                 description="print the tickets a JQL query finds, one line each")
    search.add_argument(
        "jql", help="the query, such as 'parent = PROJ-100 ORDER BY key'")
    args = parser.parse_args(argv)
    with stops_on_failure():
        if args.command == "pr":
            if not gh_available():
                raise SystemExit(
                    f"{GH_UNAVAILABLE}: a pull request's discussion is read with it")
            print("\n\n".join(gather(args.urls, pr_discussion)))
            return
        client = JiraClient()
        if args.command == "search":
            found = client.search(args.jql, LINE_FIELDS)
            print("\n".join([f"{len(found)} tickets",
                  *(search_line(i) for i in found),
                  *([] if found else moved_projects(client, args.jql))]))
            return
        site, gh = site_fields(client), gh_available()
        # One ticket after another: each already reads WORKERS at a time, and
        # tickets read together would run more calls at once than that.
        texts = [ticket(client, key, site, args.prs, gh)
                 for key in args.keys]
        print("\n\n".join(texts))


if __name__ == "__main__":
    sys.exit(main())
