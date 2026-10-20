"""Reads tickets from Jira: each one with its sprints, history, children,
links, web links, pull requests, commits and comments in one call, or the
tickets a JQL query finds, one line each; and the discussion of the pull
requests the investigation picks from them.

Why a script: through an MCP, a ticket took a call for itself, one for each
child or link and more for its pull requests, each answering with every field;
here one call prints what the investigation reads, as plain text, which costs
fewer tokens than JSON. Text is printed in full, links kept, since tickets are
read in full and the pages they link are followed.

Jira's Development panel lists the pull requests and commits the code host's
integration links to a ticket; gh adds what the panel lacks (the merge commit,
the files changed, each pull request's commits) and finds the pull requests
that name the key without being linked: in their title, as the library's
ticket_pulls.py matches a key, searched in the repositories of the owners the
panel's pull requests name or --owner gives, or holding a commit the panel
lists. Of the panel's commits in no pull request, those on the repository's
default branch are listed, as code that reached it without review; the
others, such as work rebased away before a merge, are only counted; those
GitHub has no such commit or repository of are listed with why. As the
library's failures.py sets out, a ticket, pull request, commit or repository
the service says it has none of is its answer: why is printed where it would
have been, and the rest still prints. A call to Jira or gh that fails, once
the library has tried it again, stops the script with the service's message
and what to do: a commit gh couldn't check is never read as in no pull
request. Without gh, or with github-cli disabled, the panel's pull requests
and commits are printed and the output says what wasn't read.
Projects the user excludes don't exist here: the library's client never reads
them, and a key of one is answered with why, as a key Jira doesn't have is.

A pull request's description, reviews and comments are a command of their
own: which pull requests matter is known only once the ticket is read, and
printed for every one they would make a ticket with many pull requests long.
"""
import argparse
import subprocess
import sys

from common import (COMMITS, PANEL, PULL_URL, SEARCH, JiraClient, browse_url, first_found, gather, gh_available,
                    gh_found, holding_pulls, nested, panel_commits, panel_pulls, plain_text, search_pulls,
                    stops_on_failure)

FIELDS = ["summary", "status", "issuetype", "parent", "created", "updated", "resolutiondate",
          "labels", "fixVersions", "issuelinks", "description", "assignee"]
# The changes printed as the ticket's history, by how the changelog names them.
HISTORY = {"status": "status", "sprint": "Sprint"}
LINE_FIELDS = ["summary", "status", "issuetype", "parent"]
# The field sites use for acceptance criteria, found by its name.
CRITERIA = "acceptance criteria"
GH_PR_FIELDS = "mergeCommit,mergedAt,baseRefName,headRefName,changedFiles,files,commits"
# What a pull request's discussion is read with.
GH_DISCUSSION_FIELDS = ("title,state,author,body,reviews,comments,createdAt,mergedAt,baseRefName,"
                        "headRefName,mergeCommit,url")
# Why a pull request Jira doesn't link is listed, by how it was found.
WHY = {SEARCH: "names the key in its title, not linked in Jira",
       COMMITS: "holds commits that name the key, not linked in Jira"}


def ticket(client, key, site, owners, gh, run=subprocess.run):
    """Everything printed for one ticket, as text."""
    criteria, sprint = site["criteria"], site["sprint"]
    issue, unread = client.issue(
        key, FIELDS + [f for f in (criteria, sprint) if f])
    if issue is None:
        return unread
    fields = issue["fields"]
    current = issue["key"]
    calls = {"children": lambda: client.search(f"parent = {current} ORDER BY key", LINE_FIELDS),
             "comments": lambda: client.comments(current),
             "panel": lambda: client.pull_requests(issue["id"]),
             "repositories": lambda: client.commits(issue["id"]),
             "remote": lambda: client.remote_links(current),
             "history": lambda: client.field_changes(current, HISTORY)}
    read = dict(zip(calls, gather(calls.values(), lambda call: call())))
    children, comments, panel = read["children"], read["comments"], panel_pulls(
        read["panel"])
    if gh:
        pulls, details, commits = github(
            current, panel, read["repositories"], owners, run)
    else:
        pulls, details = panel, {}
        every = panel_commits(read["repositories"])
        commits = [f"Commits, those in pull requests not told apart without gh ({len(every)}):",
                   *(commit_line(r, c) for r, c in every)]
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
    prs = pr_lines(pulls, details, gh)
    sprints = sprint_lines(fields.get(sprint)) if sprint else []
    history = history_lines(read["history"])
    web = web_link_lines(read["remote"])
    out += ["", f"Sprints ({len(sprints)}):", *sprints,
            "", f"History ({len(history)}):", *history,
            "", f"Children ({len(children)}):", *
            (f"  {line(c)}" for c in children),
            "", f"Links ({len(lines)}):", *(f"  {entry}" for entry in lines),
            "", f"Web links ({len(web)}):", *web,
            "", f"Pull requests ({len(pulls)}):", *(f"  {entry}" for entry in prs)]
    if not gh:
        out.append("  gh isn't available or github-cli isn't enabled: merge commits, files changed and pull "
                   "requests that name the key in their title without being linked in Jira weren't read")
    out += ["", *commits]
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


def pr_lines(pulls, details, gh):
    """The pull request lines, in the order found: the panel's, with its
    branches, then those only gh found, with gh's branches and why they are
    listed; each with what gh adds."""
    out = []
    for pr in pulls:
        detail = details.get(pr.get("url"))
        if pr["found"] == PANEL:
            branches = [nested(pr, ["source", "branch"], "?"),
                        nested(pr, ["destination", "branch"], "?")]
        else:
            branches = [nested(detail, ["headRefName"], "?"),
                        nested(detail, ["baseRefName"], "?")]
        why = [WHY[pr["found"]]] if pr["found"] in WHY else []
        out.append(" · ".join([pr_label(pr.get("url")), pr["state"], " → ".join(branches),
                               f"updated {day(pr.get('updatedAt'))}", pr.get("url", ""), *why]))
        out += detail_lines(detail, gh)
    return out


def pr_label(url):
    match = PULL_URL.match(url or "")
    return f"{match[1]}#{match[3]}" if match else url


def detail_lines(detail, gh):
    """What gh adds to a pull request's line: its merge and files changed,
    or why GitHub has none (a line of text)."""
    if not gh:
        return []
    if isinstance(detail, str):
        return [f"    {detail}"]
    if not detail:
        return ["    gh couldn't read it"]
    merge = nested(detail, ["mergeCommit", "oid"])
    files = [f["path"] for f in detail.get("files") or []]
    head = f"    merge commit {merge} on {day(detail.get('mergedAt'))}" if merge else "    not merged"
    shown = f"{len(files)} of {detail.get('changedFiles')}" if detail.get(
        "changedFiles", len(files)) != len(files) else str(len(files))
    return [head + f" · files changed ({shown}): " + (", ".join(files) or "none")]


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


def github(key, panel, repositories, owners, run=subprocess.run):
    """(every pull request found: the panel's, those whose title names the
    key, then those holding the panel's commits; {url: gh's details of each,
    or why GitHub has no such pull request}; the commit section's lines),
    read with gh."""
    repo_owners = set(owners) | {m[2] for pr in panel if (
        m := PULL_URL.match(pr.get("url") or ""))}
    pulls = first_found(panel, search_pulls(key, repo_owners, run))
    details = view(pulls, run)
    held = holding_pulls(outside_commits(
        panel_commits(repositories), details), run)
    found = first_found(pulls, *(prs for _, prs, _ in held))
    details |= view(found[len(pulls):], run)
    commits = unreviewed_lines([pair for pair, prs, why in held if not prs and not why],
                               [(pair, why) for pair, _, why in held if why], run)
    return found, details, commits


def view(prs, run=subprocess.run):
    """{url: gh's details, or why GitHub has no such pull request} of the
    pull requests of `prs` on GitHub."""
    urls = [pr["url"] for pr in prs if PULL_URL.match(pr.get("url") or "")]
    read = gather(urls, lambda url: gh_found(
        ["pr", "view", url, "--json", GH_PR_FIELDS], "pull request", run))
    return {url: detail if why is None else why for url, (detail, why) in zip(urls, read)}


def outside_commits(commits, details):
    """The (repository, commit) of `commits` in none of the pull requests gh
    read, merge commits included."""
    read = [d for d in details.values() if not isinstance(d, str)]
    in_prs = {c.get("oid") for d in read for c in d.get("commits") or []} | {
        nested(d, ["mergeCommit", "oid"]) for d in read}
    return [(repository, commit) for repository, commit in commits if commit.get("id") not in in_prs]


def unreviewed_lines(commits, missing=(), run=subprocess.run):
    """The commit section, from the (repository, commit) pairs in no pull
    request: those on their repository's default branch, then a count of
    the others; then those GitHub has no such commit or repository of, from
    `missing`, (pair, why) of those already known, and from the pairs."""
    names = sorted({r.get("name", "") for r, _ in commits})
    branches = dict(
        zip(names, gather(names, lambda name: default_branch(name, run))))

    def on_default(pair):
        name = pair[0].get("name", "")
        branch, why = branches[name]
        if why:
            return None, why
        return on_branch(name, branch, pair[1].get("id", ""), run)
    compared = gather(commits, on_default)
    listed = [commit_line(*pair)
              for pair, (on, _) in zip(commits, compared) if on]
    out = [
        f"Commits on the default branch in no pull request ({len(listed)}):", *listed]
    if others := sum(on is False for on, _ in compared):
        out.append(f"  {others} more in no pull request and not on the default branch, such as work "
                   "rebased away before a merge")
    gone = [*missing, *((pair, why)
                        for pair, (_, why) in zip(commits, compared) if why)]
    if gone:
        out += ["", f"Commits GitHub didn't find ({len(gone)}):",
                *(f"{commit_line(*pair)} · {why}" for pair, why in gone)]
    return out


def default_branch(repository, run=subprocess.run):
    """(branch, why): a GitHub repository's default branch, owner/name, or
    why GitHub has no such repository; raises GhError when gh can't tell."""
    found, why = gh_found(["api", f"repos/{repository}", "--jq", "{branch: .default_branch}"],
                          "repository", run)
    return (found.get("branch"), None) if why is None else (None, why)


def on_branch(repository, branch, sha, run=subprocess.run):
    """(whether commit `sha` is on `branch`, None), or (None, why) GitHub
    has no such commit; raises GhError when gh can't tell."""
    compared, why = gh_found(["api", f"repos/{repository}/compare/{branch}...{sha}",
                              "--jq", "{status: .status}"], "commit", run)
    return (compared["status"] in ("behind", "identical"), None) if why is None else (None, why)


def commit_line(repository, commit):
    message = (commit.get("message") or "").split("\n")[0]
    return (f"  {repository.get('name', '?')} {commit.get('displayId', '?')} · "
            f"{day(commit.get('authorTimestamp'))} · {message} · {commit.get('url', '?')}")


def site_fields(client):
    """{criteria, sprint}: the ids of the site's acceptance criteria and
    Sprint fields, each None when the site has none."""
    return {"criteria": criteria_field(client), "sprint": client.sprint_field()}


def criteria_field(client):
    """The id of the field named as acceptance criteria, or None."""
    return next((ident for name, ident in client.field_ids().items() if (name or "").casefold() == CRITERIA), None)


def search_line(issue):
    """A search result on one line, with its parent."""
    parent = nested(issue, ["fields", "parent", "key"])
    return line(issue) + (f" · parent {parent}" if parent else "")


def pr_discussion(url, run=subprocess.run):
    """Everything printed for one pull request: its description, reviews,
    review comments on code lines and conversation comments, in full."""
    match = PULL_URL.match(url)
    if not match:
        return f"{url}: not a GitHub pull request"
    pr, why = gh_found(
        ["pr", "view", url, "--json", GH_DISCUSSION_FIELDS], "pull request", run)
    if why:
        return f"{url}: {why}"
    # Every page, as one list of pages: a filter would run on each page apart.
    pages, why = gh_found(["api", f"repos/{match[1]}/pulls/{match[3]}/comments?per_page=100", "--paginate",
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
                               "links, web links, pull requests, commits and comments",
                               description="print tickets in full, with their sprints, history, children, "
                               "links, web links, pull requests, commits and comments")
    show.add_argument("keys", nargs="+", metavar="KEY", help="a ticket's key, such as PROJ-123; give several "
                      "for one call")
    show.add_argument("--owner", action="append", default=[],
                      help="a GitHub owner whose repositories to search for pull requests that name the key "
                      "in their title, besides those of the pull requests Jira links; repeat for more")
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
                raise SystemExit("gh isn't available or github-cli isn't enabled: a pull request's discussion "
                                 "is read with it")
            print("\n\n".join(gather(args.urls, pr_discussion)))
            return
        client = JiraClient()
        if args.command == "search":
            found = client.search(args.jql, LINE_FIELDS)
            print("\n".join([f"{len(found)} tickets",
                  *(search_line(i) for i in found)]))
            return
        site, gh = site_fields(client), gh_available()
        # One ticket after another: each already reads WORKERS at a time, and
        # tickets read together would run more calls at once than that.
        texts = [ticket(client, key, site, args.owner, gh)
                 for key in args.keys]
        print("\n\n".join(texts))


if __name__ == "__main__":
    sys.exit(main())
