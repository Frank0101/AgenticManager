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
others, such as work rebased away before a merge, are only counted; and those
gh couldn't check are listed apart, never claimed either way. A gh call that
fails doesn't stop the others: the library's loops collect the failures, and
each is printed where its answer would have been, with gh's words and the
library's advice, so a pull request, owner or commit gh couldn't read is
never taken for one with nothing to show. Without gh, or with github-cli
disabled, the panel's pull requests and commits are printed and the output
says what wasn't read.
Projects the user excludes don't exist here: the library's client never reads
them, and a key of one is answered with why, as a key Jira doesn't have is, so
the other keys still print.

A pull request's description, reviews and comments are a command of their
own: which pull requests matter is known only once the ticket is read, and
printed for every one they would make a ticket with many pull requests long.
"""
import argparse
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

from common import (COMMITS, PANEL, PULL_URL, SEARCH, WORKERS, GhError, JiraClient, NotFound, browse_url, first_found,
                    gather, gh_available, gh_json, holding_pulls, nested, panel_commits, panel_pulls, plain_text,
                    search_pulls)

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
    try:
        issue = client.issue(
            key, FIELDS + [f for f in (criteria, sprint) if f])
    except NotFound:
        return f"{key}: Jira has no such ticket, or this account can't see it"
    except SystemExit as refused:
        # Such as a ticket of an excluded project: the other keys still print.
        return str(refused.code)
    fields = issue["fields"]
    current = issue["key"]
    calls = {"children": lambda: client.search(f"parent = {current} ORDER BY key", LINE_FIELDS),
             "comments": lambda: client.comments(current),
             "panel": lambda: client.pull_requests(issue["id"]),
             "repositories": lambda: client.commits(issue["id"]),
             "remote": lambda: client.remote_links(current),
             "history": lambda: client.field_changes(current, HISTORY)}
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        read = dict(zip(calls, pool.map(lambda call: call(), calls.values())))
    children, comments, panel = read["children"], read["comments"], panel_pulls(
        read["panel"])
    if gh:
        pulls, details, unread, unsearched, commits = github(
            current, panel, read["repositories"], owners, run)
    else:
        pulls, details, unread, unsearched = panel, {}, {}, []
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
    prs = pr_lines(pulls, details, unread, gh)
    unsearched = [
        f"gh couldn't search {owner}: {failed.explanation}" for owner, failed in unsearched]
    sprints = sprint_lines(fields.get(sprint)) if sprint else []
    history = history_lines(read["history"])
    web = web_link_lines(read["remote"])
    out += ["", f"Sprints ({len(sprints)}):", *sprints,
            "", f"History ({len(history)}):", *history,
            "", f"Children ({len(children)}):", *
            (f"  {line(c)}" for c in children),
            "", f"Links ({len(lines)}):", *(f"  {entry}" for entry in lines),
            "", f"Web links ({len(web)}):", *web,
            "", f"Pull requests ({len(pulls)}):", *(f"  {entry}" for entry in prs + unsearched)]
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


def pr_lines(pulls, details, unread, gh):
    """The pull request lines, in the order found: the panel's, with its
    branches, then those only gh found, with gh's branches and why they are
    listed; each with what gh adds, or why gh couldn't read it (`unread`,
    {url: GhError})."""
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
        out += detail_lines(detail, unread.get(pr.get("url")), gh)
    return out


def pr_label(url):
    match = PULL_URL.match(url or "")
    return f"{match[1]}#{match[3]}" if match else url


def detail_lines(detail, failed, gh):
    if not gh:
        return []
    if failed:
        return [f"    gh couldn't read it: {failed.explanation}"]
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
    key, then those holding the panel's commits; {url: gh's details of each};
    {url: GhError} of those gh couldn't read; [(owner, GhError)] of the
    owners gh couldn't search; the commit section's lines), read with gh."""
    repo_owners = set(owners) | {m[2] for pr in panel if (
        m := PULL_URL.match(pr.get("url") or ""))}
    titled, unsearched = search_pulls(key, repo_owners, run)
    pulls = first_found(panel, titled)
    details, unread = view(pulls, run)
    outside = outside_commits(panel_commits(repositories), details)
    held, unheld = holding_pulls(outside, run)
    found = first_found(pulls, *(prs for _, prs in held))
    more, more_unread = view(found[len(pulls):], run)
    details, unread = details | more, unread | more_unread
    # A commit gh couldn't look up isn't claimed to be in no pull request.
    commits, unchecked = unreviewed_lines(
        [pair for pair, prs in held if not prs], run)
    if unknown := unheld + unchecked:
        commits += ["", f"Commits gh couldn't check ({len(unknown)}):", *(
            f"{commit_line(*pair)} · {failed.explanation}" for pair, failed in unknown)]
    return found, details, unread, unsearched, commits


def view(prs, run=subprocess.run):
    """({url: gh's details}, {url: GhError}) of the pull requests of `prs` on
    GitHub."""
    urls = [pr["url"] for pr in prs if PULL_URL.match(pr.get("url") or "")]
    details, failures = gather(urls, lambda url: gh_json(
        ["pr", "view", url, "--json", GH_PR_FIELDS], run))
    return dict(details), dict(failures)


def outside_commits(commits, details):
    """The (repository, commit) of `commits` in none of the pull requests gh
    read, merge commits included."""
    in_prs = {c.get("oid") for d in details.values() for c in d.get("commits") or []} | {
        nested(d, ["mergeCommit", "oid"]) for d in details.values()}
    return [(repository, commit) for repository, commit in commits if commit.get("id") not in in_prs]


def unreviewed_lines(commits, run=subprocess.run):
    """(the commit section, [(pair, GhError)] of the commits whose branch gh
    couldn't tell), from the (repository, commit) pairs in no pull request:
    those on their repository's default branch, then a count of the
    others."""
    names = sorted({r.get("name", "") for r, _ in commits})
    branches, unknown = gather(names, lambda name: default_branch(name, run))
    branches, unknown = dict(branches), dict(unknown)

    def on_default(pair):
        name = pair[0].get("name", "")
        if name in unknown:
            raise unknown[name]
        return on_branch(name, branches[name], pair[1].get("id", ""), run)
    compared, unchecked = gather(commits, on_default)
    listed = [commit_line(*pair) for pair, on in compared if on]
    out = [
        f"Commits on the default branch in no pull request ({len(listed)}):", *listed]
    if others := sum(not on for _, on in compared):
        out.append(f"  {others} more in no pull request and not on the default branch, such as work "
                   "rebased away before a merge")
    return out, unchecked


def default_branch(repository, run=subprocess.run):
    """A GitHub repository's default branch, owner/name; raises GhError when
    gh can't tell."""
    return gh_json(["api", f"repos/{repository}", "--jq", "{branch: .default_branch}"], run).get("branch")


def on_branch(repository, branch, sha, run=subprocess.run):
    """Whether commit `sha` is on `branch`; raises GhError when gh can't
    tell."""
    compared = gh_json(["api", f"repos/{repository}/compare/{branch}...{sha}",
                        "--jq", "{status: .status}"], run)
    return compared["status"] in ("behind", "identical")


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
    try:
        pr = gh_json(["pr", "view", url, "--json", GH_DISCUSSION_FIELDS], run)
        # Every page, as one list of pages: a filter would run on each page apart.
        pages = gh_json(["api", f"repos/{match[1]}/pulls/{match[3]}/comments?per_page=100", "--paginate",
                         "--slurp"], run)
    except GhError as failed:
        return f"{url}: gh couldn't read it: {failed.explanation}"
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
    if args.command == "pr":
        if not gh_available():
            raise SystemExit("gh isn't available or github-cli isn't enabled: a pull request's discussion "
                             "is read with it")
        with ThreadPoolExecutor(max_workers=WORKERS) as pool:
            print("\n\n".join(pool.map(pr_discussion, args.urls)))
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
    texts = [ticket(client, key, site, args.owner, gh) for key in args.keys]
    print("\n\n".join(texts))


if __name__ == "__main__":
    sys.exit(main())
