"""GitHub through its CLI, gh, shared by every skill: whether it can be used,
its JSON answers, the pull requests that hold a commit or name a text in
their title, when pull requests were opened and merged, and what to do when
gh fails.

gh is the user's `github-cli` source, so it is used only when enabled, and
it signs in itself: no setting is read here. Every call takes `run`, which
runs the command, so a test answers for gh and nothing reaches GitHub.

failures.py sets out the rule: GitHub saying what was asked for isn't there
is an answer, and gh giving none is a failure. A single read of one thing,
gh_found(), returns the answer or why it isn't there; gh tells "not there"
only in its message, so NOT_FOUND_SIGNS lists its words for it, and GitHub
gives the same for a private repository the account can't see, which the
reason says. Any other call gh can't answer, whether it fails, times out or
answers something other than JSON, raises GhError with gh's own message,
never returns an empty answer: "gh failed" and "gh answered: nothing" stay
apart, so a failure such as GitHub's rate limit is never taken for a commit
in no pull request or a ticket nothing names. Nothing here knows about
Jira: matching a pull request to a ticket is ticket_pulls.py's.

Before failing, a call is tried again as retry.py sets out: a timeout or a
busy GitHub is passing, and a rate limit final, its advice to wait a minute
and run it again.

When pull requests were opened and merged is read through GraphQL, many in
one call (pull_events()): a call per pull request spent hundreds of requests
of a sprint's hourly limit. Owner, name and number go in as GraphQL
variables, never into the query's text. GitHub answers for each pull
request apart: when it says the pull request itself doesn't exist
(NOT_FOUND, such as one deleted that Jira still links), that is an answer,
returned with GitHub's words, so a caller can skip it; any other error, for
one pull request or the call, is a failure. Here, unlike in a single read,
a repository it can't find isn't an answer: it is also what an account
without access to it gets, and gh signed in to the wrong account would then
drop every pull request of the repository.
"""
import json
import re
import shutil
import subprocess
from typing import Any

from agentic_manager.batch import batches, gather
from agentic_manager.config import is_enabled
from agentic_manager.json_path import nested
from agentic_manager.retry import RATE_LIMITED, retried

GROUP, NAME = "source_control", "github-cli"
TIMEOUT = 60
# A pull request's page: its repository, owner/name, its owner and its number.
PULL_URL = re.compile(r"^https?://[^/\s]+/(([\w.-]+)/[\w.-]+)/pull/(\d+)")
# The same page, strictly, for the parts read through GraphQL: its host, owner,
# name and number. An owner is letters, digits and hyphens on GitHub.
PULL_PARTS = re.compile(
    r"https?://([\w.-]+(?::\d+)?)/([A-Za-z0-9-]+)/([\w.-]+)/pull/(\d+)(?:[/?#].*)?")
DEFAULT_HOST = "github.com"
# The words of a GraphQL call, which its failures name: the query and its
# variables are too long to show.
GRAPHQL = ["api", "graphql"]
SEARCH_LIMIT = 50
# What a pull request's opening and merge are read with; GraphQL's state is
# OPEN, CLOSED or MERGED, as gh pr view gives it.
EVENT_FIELDS = "url state createdAt mergedAt"
# What gh says when the call failed in passing: no answer in time, GitHub
# busy or briefly unwell, or the connection lost.
PASSING_SIGNS = ("no answer within", "http 500", "http 502", "http 503", "http 504", "timeout", "timed out",
                 "connection reset", "connection refused", "eof")
# What GitHub's GraphQL calls an error for something that doesn't exist.
NOT_FOUND = "NOT_FOUND"
# What gh says, in lower case, when GitHub has no such thing, or none the
# account can see: GraphQL's "Could not resolve to a PullRequest with the
# number of 9." (gh pr view), REST's "Not Found (HTTP 404)" (gh api), and
# "No commit found for SHA: ..." (HTTP 422) for a commit's pull requests.
NOT_FOUND_SIGNS = ("could not resolve to a ",
                   "http 404", "no commit found for sha")
# What to do when gh fails for anything but a rate limit (retry.py's
# RATE_LIMITED): gh's own setup, or the user goes on without GitHub.
GH_BROKEN = ("Check that gh works (gh auth status) and run it again, or disable the github-cli source to go on "
             "without GitHub.")


def gh_available():
    """Whether gh can be used: installed, and enabled as the user's github-cli source."""
    return shutil.which("gh") is not None and is_enabled(GROUP, NAME)


def pulls_holding(repository, sha, run=subprocess.run):
    """(pulls, why), as gh_found() gives them: the pull requests of a GitHub
    repository, owner/name, that hold commit `sha`, as {url, state,
    updatedAt} with state OPEN, CLOSED or MERGED, none when no pull request
    holds it; or why GitHub has no such commit."""
    return gh_found(["api", f"repos/{repository}/commits/{sha}/pulls", "--jq",
                     "[.[] | {url: .html_url, state: (if .merged_at then \"MERGED\" else (.state | ascii_upcase) end), "
                     "updatedAt: .updated_at}]"], "commit", run)


def search_pull_titles(text, owner, run=subprocess.run):
    """The pull requests in the repositories of `owner` whose title GitHub's
    search matches `text` in, at most SEARCH_LIMIT, as {url, state, title,
    updatedAt} with state in capitals. Raises GhError when gh can't tell.
    GitHub's search matches words, so a caller checks the title for what it
    needs."""
    found = gh_json(["search", "prs", text, "--owner", owner, "--match", "title", "--limit", str(SEARCH_LIMIT),
                     "--json", "url,state,title,updatedAt"], run)
    return [{**pr, "state": (pr.get("state") or "?").upper()} for pr in found]


def pull_events(urls, run=subprocess.run):
    """(events, gone) of the pull requests at `urls`: events as {url: {url,
    state, createdAt, mergedAt}}, when each was opened and, if it was, merged
    (else mergedAt is None), with state OPEN, CLOSED or MERGED; and gone as
    {url: GitHub's words} of those GitHub says don't exist, in the order of
    `urls`. Raises GhError for any other that gh couldn't read, such as one
    GitHub can't resolve or a URL whose parts aren't safe to ask about. Read
    in a GraphQL call for each batch (batch.py) of one host's pull requests:
    each is a single object, not a connection, so a call costs one point of
    GraphQL's hourly 5,000 and stays far below its node limit."""
    urls = list(dict.fromkeys(urls))
    hosts = {}
    for url in urls:
        if not (parts := PULL_PARTS.fullmatch(url)):
            raise GhError(
                GRAPHQL, f"{url}: not a pull request's address gh can be asked about")
        hosts.setdefault(parts[1], []).append(url)
    calls = [(host, chunk) for host, found in hosts.items()
             for chunk in batches(found)]
    events, missing = {}, {}
    for answered, unread in gather(calls, lambda call: batch_events(call[0], call[1], run)):
        events.update(answered)
        missing.update(unread)
    gone = {}
    for url in urls:
        if failed := missing.get(url):
            if not failed.not_found:
                raise failed
            gone[url] = failed.message
    return events, gone


def batch_events(host, urls, run=subprocess.run):
    """({url: its events}, {url: GhError}) of the pull requests at `urls`, all
    on `host`, read in one GraphQL call: a repository by alias r<i>, its pull
    requests by p<j>, each one's owner, name and number a variable. Raises
    GhError when gh answers nothing for the call as a whole."""
    query, fields, aliases = events_query(urls)
    args = [*GRAPHQL, *(["--hostname", host] if host !=
                        DEFAULT_HOST else []), "-f", f"query={query}", *fields]
    answer = retried(lambda: graphql_once(args, run), passing, note)
    errors: dict[tuple, dict] = {tuple(error.get("path") or ())[:2]: error
                                 for error in answer.get("errors") or [] if isinstance(error, dict)}
    events, missing = {}, {}
    for (repository, pull), url in aliases.items():
        node = nested(answer, ["data", repository, pull])
        if isinstance(node, dict):
            events[url] = node
        else:
            own = errors.get((repository, pull))
            message = ((own or errors.get((repository,)) or {}).get("message")
                       or "GitHub gave no answer for it")
            missing[url] = GhError(GRAPHQL, f"{url}: {message}",
                                   not_found=bool(own) and own.get("type") == NOT_FOUND)
    return events, missing


def events_query(urls):
    """(query, gh's field arguments, {(repository alias, pull alias): url})
    that read the events of the pull requests at `urls`, grouped by
    repository. Raises ValueError for a URL PULL_PARTS doesn't match, so
    nothing unchecked reaches the call."""
    repositories = {}
    for url in urls:
        parts = PULL_PARTS.fullmatch(url)
        if not parts:
            raise ValueError(f"not a pull request's address: {url}")
        repositories.setdefault(
            (parts[2], parts[3]), []).append((url, parts[4]))
    declared, fields, lines, aliases = [], [], [], {}
    for i, ((owner, name), pulls) in enumerate(repositories.items()):
        declared += [f"$o{i}: String!", f"$n{i}: String!"]
        fields += ["-f", f"o{i}={owner}", "-f", f"n{i}={name}"]
        reads = []
        for url, number in pulls:
            j = len(aliases)
            aliases[(f"r{i}", f"p{j}")] = url
            declared.append(f"$p{j}: Int!")
            fields += ["-F", f"p{j}={int(number)}"]
            reads.append(f"p{j}: pullRequest(number: $p{j}) {{ ...pull }}")
        lines.append(
            f"r{i}: repository(owner: $o{i}, name: $n{i}) {{ {' '.join(reads)} }}")
    query = "\n".join([f"query({', '.join(declared)}) {{", *lines, "}",
                       f"fragment pull on PullRequest {{ {EVENT_FIELDS} }}"])
    return query, fields, aliases


def gh_found(args, thing, run=subprocess.run) -> tuple[Any, str | None]:
    """(gh's JSON answer to `args`, None), or (None, why) when GitHub has no
    such `thing`, such as "pull request", or none this account can see: a
    line in gh's words. Raises GhError for any other failure, as gh_json()
    does."""
    try:
        return gh_json(args, run), None
    except GhError as failed:
        if not failed.not_found:
            raise
        words = " ".join(failed.message.split()).rstrip(".")
        return None, f"GitHub has no such {thing}, or this account can't see it: {words}"


def gh_json(args, run=subprocess.run):
    """gh's JSON answer to `args`, the command after gh, tried again while gh
    fails in passing; raises GhError when gh gives none."""
    return retried(lambda: gh_once(args, run), passing, note)


def gh_once(args, run):
    """gh's JSON answer to one try of `args`; raises GhError when gh gives none."""
    done = _ran(args, args, run)
    if done.returncode:
        message = (done.stderr or "").strip()
        raise GhError(args, message or f"exited with code {done.returncode}",
                      not_found=any(sign in message.lower() for sign in NOT_FOUND_SIGNS))
    try:
        return json.loads(done.stdout)
    except ValueError:
        raise GhError(args, "answered something other than JSON")


def graphql_once(args, run):
    """GitHub's answer to one try of the GraphQL call `args`, {data, errors},
    even when gh fails because some of the query couldn't be resolved;
    raises GhError, as the words `gh api graphql`, when it holds no data."""
    done = _ran(args, GRAPHQL, run)
    try:
        answer = json.loads(done.stdout or "")
    except ValueError:
        answer = None
    if isinstance(answer, dict) and isinstance(answer.get("data"), dict):
        return answer
    if done.returncode:
        reasons = [str(error["message"]) for error in nested(answer, ["errors"], [])
                   if isinstance(error, dict) and error.get("message")]
        raise GhError(GRAPHQL, (done.stderr or "").strip() or "; ".join(reasons)
                      or f"exited with code {done.returncode}")
    raise GhError(GRAPHQL, "answered something other than GraphQL data")


def _ran(args, words, run):
    """The finished gh process of `args`; raises GhError, as `words`, when
    gh doesn't run or answer in time."""
    try:
        return run(["gh", *args], capture_output=True, text=True, timeout=TIMEOUT)
    except subprocess.TimeoutExpired:
        raise GhError(words, f"no answer within {TIMEOUT} seconds")
    except OSError as failed:
        raise GhError(words, f"couldn't run gh: {failed}")


def passing(error):
    """Whether a failed gh call is passing, to retry.retried(): no answer in
    time, or GitHub busy or unreachable; a rate limit, something GitHub says
    isn't there, and anything else, is final."""
    if not isinstance(error, GhError) or error.rate_limited or error.not_found:
        return False
    return any(sign in error.message.lower() for sign in PASSING_SIGNS)


def note(error):
    """What failed, for the line a retry prints: the gh command and the
    first line of gh's message."""
    first = (error.message.splitlines() or [""])[0].strip().rstrip(".")
    return f"gh {' '.join(error.command[:2])}: {first}"


class GhError(Exception):
    """A gh command that gave no answer: `command`, the words after gh,
    `message`, why, in gh's own words (its stderr) when it gave any, and
    `not_found`, whether GitHub said what was asked for doesn't exist."""

    def __init__(self, command, message, not_found=False):
        super().__init__(f"gh {' '.join(command)}: {message}")
        self.command, self.message, self.not_found = command, message, not_found

    @property
    def rate_limited(self):
        """Whether GitHub refused the call for its rate limit, primary or
        secondary."""
        return "rate limit" in self.message.lower()

    @property
    def advice(self):
        """What the user does about it: wait a minute for GitHub's rate limit,
        or fix gh or disable the github-cli source."""
        return RATE_LIMITED if self.rate_limited else GH_BROKEN

    @property
    def explanation(self):
        """gh's message on one line, then the advice: how a skill shows the
        failure to the user."""
        return f"{' '.join(self.message.split()).rstrip('.')}. {self.advice}"
