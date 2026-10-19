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
that name the key without being linked: in their title or body, searched in
the repositories of the owners the panel's pull requests name or --owner
gives, or holding a commit the panel lists. Of the panel's commits in no pull
request, those on the repository's default branch are listed, as code that
reached it without review; the others, such as work rebased away before a
merge, are only counted; and those gh couldn't check are listed apart, never
claimed either way. Without gh, or with github-cli disabled, the panel's pull
requests and commits are printed and the output says what wasn't read.
Projects the user excludes don't exist here: the library's client never reads
them, and a key of one is answered with why, as a key Jira doesn't have is, so
the other keys still print.

A pull request's description, reviews and comments are a command of their
own: which pull requests matter is known only once the ticket is read, and
printed for every one they would make a ticket with many pull requests long.
"""
import argparse
import json
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

from common import ISSUE_KEY, PULL_URL, JiraClient, NotFound, browse_url, is_enabled, nested, plain_text

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
SEARCH_LIMIT = 50
# Why a pull request Jira doesn't link is listed.
NAMES_KEY = "names the key, not linked in Jira"
HOLDS_COMMITS = "holds commits that name the key, not linked in Jira"
WORKERS = 8


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
    children, comments, panel = read["children"], read["comments"], read["panel"]
    if gh:
        extra, details, commits = github(
            current, panel, read["repositories"], owners, run)
    else:
        extra, details = [], {}
        every = [(r, c) for r in read["repositories"]
                 for c in r.get("commits") or []]
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
    prs = pr_lines(panel, extra, details, gh)
    sprints = sprint_lines(fields.get(sprint)) if sprint else []
    history = history_lines(read["history"])
    web = web_link_lines(read["remote"])
    out += ["", f"Sprints ({len(sprints)}):", *sprints,
            "", f"History ({len(history)}):", *history,
            "", f"Children ({len(children)}):", *
            (f"  {line(c)}" for c in children),
            "", f"Links ({len(lines)}):", *(f"  {entry}" for entry in lines),
            "", f"Web links ({len(web)}):", *web,
            "", f"Pull requests ({len(panel) + len(extra)}):", *(f"  {entry}" for entry in prs)]
    if not gh:
        out.append("  gh isn't available or github-cli isn't enabled: merge commits, files changed and pull "
                   "requests that name the key without being linked in Jira weren't read")
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


def pr_lines(panel, extra, details, gh):
    """The pull request lines: the panel's, then those only gh found, each
    with what gh adds."""
    out = []
    for pr in panel:
        out.append(" · ".join([pr_label(pr.get("url")), pr.get("status", "?"),
                               f"{nested(pr, ['source', 'branch'], '?')} → "
                               f"{nested(pr, ['destination', 'branch'], '?')}",
                               f"updated {day(pr.get('lastUpdate'))}", pr.get("url", "")]))
        out += detail_lines(details.get(pr.get("url")), gh)
    for pr in extra:
        detail = details.get(pr["url"]) or {}
        out.append(" · ".join([pr_label(pr["url"]), pr["state"],
                               f"{detail.get('headRefName', '?')} → {detail.get('baseRefName', '?')}",
                               f"updated {day(pr.get('updatedAt'))}", pr["url"], pr["why"]]))
        out += detail_lines(detail, gh)
    return out


def pr_label(url):
    match = PULL_URL.match(url or "")
    return f"{match[1]}#{match[3]}" if match else url


def detail_lines(detail, gh):
    if not gh:
        return []
    if not detail:
        return ["    gh couldn't read it"]
    merge = nested(detail, ["mergeCommit", "oid"])
    files = [f["path"] for f in detail.get("files") or []]
    head = f"    merge commit {merge} on {day(detail.get('mergedAt'))}" if merge else "    not merged"
    shown = f"{len(files)} of {detail.get('changedFiles')}" if detail.get(
        "changedFiles", len(files)) != len(files) else str(len(files))
    return [head + f" · files changed ({shown}): " + (", ".join(files) or "none")]


def history_lines(changes):
    """Each status or sprint change, dated, in time order."""
    return [f"  {day(c['created'])} · {c['field']}: {c.get('fromString') or 'none'} → "
            f"{c.get('toString') or 'none'}" for c in changes]


def web_link_lines(remote):
    """Each web link: title and URL."""
    return [f"  {nested(r, ['object', 'title'], '?')} · {nested(r, ['object', 'url'], '?')}" for r in remote]


def github(key, panel, repositories, owners, run=subprocess.run):
    """(pull requests Jira doesn't link, {url: gh's details of every pull
    request}, the commit section's lines), read with gh."""
    known = {pr.get("url") for pr in panel}
    repo_owners = set(owners) | {m[2] for pr in panel if (
        m := PULL_URL.match(pr.get("url") or ""))}
    extra = unlinked(key, repo_owners, known, run)

    def view(prs):
        urls = [pr["url"] for pr in prs if PULL_URL.match(pr.get("url") or "")]
        with ThreadPoolExecutor(max_workers=WORKERS) as pool:
            return dict(zip(urls, pool.map(lambda url: gh_json(["pr", "view", url, "--json", GH_PR_FIELDS], run),
                                           urls)))
    details = view([*panel, *extra])
    outside = outside_commits(repositories, details)
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        pulls = list(pool.map(lambda pair: commit_pulls(
            pair[0].get("name", ""), pair[1].get("id", ""), run), outside))
    listed = known | {pr["url"] for pr in extra}
    holding = {}
    for found in pulls:
        holding |= {pr["url"]: {**pr, "why": HOLDS_COMMITS}
                    for pr in found or [] if pr["url"] not in listed}
    details |= view(list(holding.values()))
    # A commit gh couldn't look up isn't claimed to be in no pull request.
    unreviewed = [pair for pair, found in zip(outside, pulls) if found == []]
    commits, unchecked = unreviewed_lines(unreviewed, run)
    unknown = [pair for pair, found in zip(
        outside, pulls) if found is None] + unchecked
    if unknown:
        commits += ["", f"Commits gh couldn't check ({len(unknown)}):", *(
            commit_line(*pair) for pair in unknown)]
    return [*extra, *holding.values()], details, commits


def gh_json(args, run=subprocess.run):
    """gh's JSON answer, or None when gh fails."""
    try:
        done = run(["gh", *args], capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if done.returncode:
        return None
    try:
        return json.loads(done.stdout)
    except ValueError:
        return None


def unlinked(key, owners, known, run=subprocess.run):
    """The pull requests of `owners` that name `key` in their title or body
    and the panel doesn't list, as {url, state, title, updatedAt}."""
    def names(text):
        return key in ISSUE_KEY.findall(text or "")
    found = {}
    for owner in sorted(owners):
        result = gh_json(["search", "prs", key, "--owner", owner, "--limit", str(SEARCH_LIMIT),
                          "--json", "url,state,title,body,updatedAt"], run) or []
        found |= {pr["url"]: {**pr, "state": pr.get("state", "?").upper(), "why": NAMES_KEY}
                  for pr in result if pr["url"] not in known
                  and (names(pr.get("title")) or names(pr.get("body")))}
    return list(found.values())


def outside_commits(repositories, details):
    """(repository, commit) of the panel's commits in none of the pull
    requests gh read, merge commits included."""
    in_prs = {c.get("oid") for d in details.values() if d for c in d.get("commits") or []} | {
        nested(d, ["mergeCommit", "oid"]) for d in details.values() if d}
    return [(repository, commit) for repository in repositories for commit in repository.get("commits") or []
            if commit.get("id") not in in_prs]


def commit_pulls(repository, sha, run=subprocess.run):
    """The pull requests of a GitHub repository, owner/name, that hold commit
    `sha`, as {url, state, updatedAt}; None when gh can't tell."""
    return gh_json(["api", f"repos/{repository}/commits/{sha}/pulls", "--jq",
                    "[.[] | {url: .html_url, state: (if .merged_at then \"MERGED\" else (.state | ascii_upcase) end), "
                    "updatedAt: .updated_at}]"], run)


def unreviewed_lines(commits, run=subprocess.run):
    """(the commit section, the commits whose branch gh couldn't tell), from
    the commits in no pull request: those on their repository's default
    branch, then a count of the others."""
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        names = sorted({r.get("name", "") for r, _ in commits})
        branches = dict(
            zip(names, pool.map(lambda name: default_branch(name, run), names)))
        found = list(pool.map(lambda pair: on_branch(pair[0].get("name", ""), branches[pair[0].get("name", "")],
                                                     pair[1].get("id", ""), run), commits))
    listed = [commit_line(r, c) for (r, c), on in zip(commits, found) if on]
    out = [
        f"Commits on the default branch in no pull request ({len(listed)}):", *listed]
    if others := sum(on is False for on in found):
        out.append(f"  {others} more in no pull request and not on the default branch, such as work "
                   "rebased away before a merge")
    return out, [pair for pair, on in zip(commits, found) if on is None]


def default_branch(repository, run=subprocess.run):
    """A GitHub repository's default branch, owner/name, or None when gh can't tell."""
    about = gh_json(
        ["api", f"repos/{repository}", "--jq", "{branch: .default_branch}"], run)
    return about and about.get("branch")


def on_branch(repository, branch, sha, run=subprocess.run):
    """Whether commit `sha` is on `branch`; None when gh can't tell."""
    if not branch:
        return None
    compared = gh_json(["api", f"repos/{repository}/compare/{branch}...{sha}",
                        "--jq", "{status: .status}"], run)
    return compared["status"] in ("behind", "identical") if compared else None


def commit_line(repository, commit):
    message = (commit.get("message") or "").split("\n")[0]
    return (f"  {repository.get('name', '?')} {commit.get('displayId', '?')} · "
            f"{day(commit.get('authorTimestamp'))} · {message} · {commit.get('url', '?')}")


def sprint_lines(sprints):
    """Each sprint the ticket was in: name, state and goal, on one line."""
    return [f"  {s.get('name', '?')} · {s.get('state', '?')} · goal: {' '.join((s.get('goal') or 'none').split())}"
            for s in sprints or []]


def gh_available():
    """Whether gh can be used: installed, and enabled as the user's github-cli source."""
    return shutil.which("gh") is not None and is_enabled("source_control", "github-cli")


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
    pr = gh_json(["pr", "view", url, "--json", GH_DISCUSSION_FIELDS], run)
    # Every page, as one list of pages: a filter would run on each page apart.
    pages = gh_json(["api", f"repos/{match[1]}/pulls/{match[3]}/comments?per_page=100", "--paginate",
                     "--slurp"], run)
    if pr is None or pages is None:
        return f"{url}: gh couldn't read it"
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
                      help="a GitHub owner whose repositories to search for pull requests that name the key, "
                      "besides those of the pull requests Jira links; repeat for more")
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
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        texts = list(pool.map(lambda key: ticket(
            client, key, site, args.owner, gh), args.keys))
    print("\n\n".join(texts))


if __name__ == "__main__":
    sys.exit(main())
