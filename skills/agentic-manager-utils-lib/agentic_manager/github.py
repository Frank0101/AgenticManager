"""GitHub through its CLI, gh, shared by every skill: whether it can be used,
its JSON answers, when pull requests were opened and merged, and what to do
when gh fails.

gh is the user's `github-cli` source, used only when enabled, and signs in
itself: no setting is read here. Every call takes `run`, which runs the
command, so a test answers for gh and nothing reaches GitHub. As failures.py
sets out, GitHub saying a thing isn't there is an answer, and gh giving none
a failure, tried again as retry.py sets out and then raised as GhError.
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
# A GitHub pull request's address, the one rule every skill reads one by: its
# host (a GitHub Enterprise site may have a port), owner, repository name and
# number, each named; anything after the number, such as /files, is allowed.
# An owner is letters, digits and hyphens, as GitHub allows, so the parts are
# safe to send in a query.
PULL_URL = re.compile(
    r"https?://(?P<host>[\w.-]+(?::\d+)?)/(?P<owner>[A-Za-z0-9-]+)/(?P<name>[\w.-]+)/pull/(?P<number>\d+)"
    r"(?:[/?#].*)?")
DEFAULT_HOST = "github.com"
# A GraphQL call's first words, before its query and variables.
GRAPHQL = ["api", "graphql"]
# A word of gh's command: gh's commands are a group and a command (pr view,
# search prs) or api and its endpoint (api graphql), in lower-case words, so
# at most COMMAND_WORDS of them name it. A failure names the command by these
# alone: its other arguments, a URL, a query or flags, are too long to show
# and can hold what was searched for.
COMMAND_WORD = re.compile(r"[a-z]+(?:-[a-z]+)*")
COMMAND_WORDS = 2
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
# account can see, such as a private repository: GraphQL's "Could not resolve
# to a PullRequest with the number of 9." (gh pr view) and REST's "Not Found
# (HTTP 404)" (gh api). gh tells it only in its message.
NOT_FOUND_SIGNS = ("could not resolve to a ", "http 404")
# What to do when gh fails for anything but a rate limit (retry.py's
# RATE_LIMITED): gh's own setup, or the user goes on without GitHub.
GH_BROKEN = ("Check that gh works (gh auth status) and run it again, or disable the github-cli source to go on "
             "without GitHub.")


def gh_available():
    """Whether gh can be used: installed, and enabled as the user's github-cli source."""
    return shutil.which("gh") is not None and is_enabled(GROUP, NAME)


def gh_signed_in(run=subprocess.run):
    """Whether gh is signed in, as `gh auth status` says, for a skill that
    checks before any work that gh can be used. Raises GhError when gh can't
    be run or doesn't answer in time."""
    return _ran(["auth", "status"], ["auth", "status"], run).returncode == 0


def pull_events(urls, run=subprocess.run):
    """(events, gone) of the pull requests at `urls`: events as {url: {url,
    state, createdAt, mergedAt}}, when each was opened and, if it was, merged
    (else mergedAt is None), with state OPEN, CLOSED or MERGED; and gone as
    {url: GitHub's words} of those GitHub says don't exist, in the order of
    `urls`. Raises GhError for any other that gh couldn't read, such as one
    GitHub can't resolve or a URL whose parts aren't safe to ask about. Read
    in a GraphQL call for each batch (batch.py) of one host's pull requests,
    as a call per pull request spent hundreds of requests of a sprint's
    hourly limit: each is a single object, not a connection, so a call costs
    one point of GraphQL's hourly 5,000 and stays far below its node
    limit."""
    urls = list(dict.fromkeys(urls))
    hosts = {}
    for url in urls:
        if not (parts := pull_parts(url)):
            raise GhError(
                GRAPHQL, f"{url}: not a pull request's address gh can be asked about")
        hosts.setdefault(parts["host"], []).append(url)
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


def pull_parts(url):
    """The parts of a GitHub pull request's address, host, owner, name and
    number, by name; None when `url` isn't one."""
    return PULL_URL.fullmatch(url or "")


def batch_events(host, urls, run=subprocess.run):
    """({url: its events}, {url: GhError}) of the pull requests at `urls`, all
    on `host`, read in one GraphQL call: a repository by alias r<i>, its pull
    requests by p<j>, each one's owner, name and number a variable, never in
    the query's text. Raises GhError when gh answers nothing for the call as
    a whole. GitHub answers for each pull request apart: one it says doesn't
    exist (NOT_FOUND, such as one deleted that Jira still links) is an
    answer; any other error is a failure. Unlike in gh_found(), a repository
    it can't find isn't an answer: it is also what an account without access
    gets, and gh signed in to the wrong account would then drop every pull
    request of the repository."""
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
    repository. Raises ValueError for a URL that isn't a pull request's, so
    nothing unchecked reaches the call."""
    repositories = {}
    for url in urls:
        parts = pull_parts(url)
        if not parts:
            raise ValueError(f"not a pull request's address: {url}")
        repositories.setdefault(
            (parts["owner"], parts["name"]), []).append((url, parts["number"]))
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
    fails in passing; raises GhError when gh gives none, whether it fails,
    times out or answers something other than JSON. It never returns an
    empty answer for a failure, so one such as GitHub's rate limit is never
    taken for a thing that doesn't exist."""
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
    return f"{error.name}: {first}"


class GhError(Exception):
    """A gh command that gave no answer: `command`, the words after gh,
    `message`, why, in gh's own words (its stderr) when it gave any, and
    `not_found`, whether GitHub said what was asked for doesn't exist."""

    def __init__(self, command, message, not_found=False):
        self.command, self.message, self.not_found = command, message, not_found
        super().__init__(f"{self.name}: {message}")

    @property
    def name(self):
        """The command as its failures name it, such as "gh pr view"."""
        return command_name(self.command)

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


def command_name(command):
    """gh's command `command`, the words after gh, by its first words, such
    as "gh pr view": its leading lower-case words, at most COMMAND_WORDS,
    up to the first that isn't one, such as a URL, a key, a path or a flag."""
    words = []
    for word in command[:COMMAND_WORDS]:
        if not COMMAND_WORD.fullmatch(word):
            break
        words.append(word)
    return " ".join(["gh", *words])
