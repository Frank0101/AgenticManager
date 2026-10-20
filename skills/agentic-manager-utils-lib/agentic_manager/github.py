"""GitHub through its CLI, gh, shared by every skill: whether it can be used,
its JSON answers, the pull requests that hold a commit or name a text in
their title, when pull requests were opened and merged, and what to do when
gh fails.

gh is the user's `github-cli` source, so it is used only when enabled, and
it signs in itself: no setting is read here. Every call takes `run`, which
runs the command, so a test answers for gh and nothing reaches GitHub.

A call gh can't answer, whether it fails, times out or answers something
other than JSON, raises GhError with gh's own message, never returns an
empty answer: "gh failed" and "gh answered: nothing" stay apart, so a
failure such as GitHub's rate limit is never taken for a commit in no pull
request or a ticket nothing names. gather() makes many calls and collects
the failures instead of stopping at the first, so each caller decides what
they mean for it: stop and say so, or show each as not known. Either way it
shows gh's words and the error's advice, so every skill tells the user the
same thing to do. Nothing here knows about Jira: matching a pull request to
a ticket is ticket_pulls.py's.

Before failing, a call is tried again as retry.py sets out: a timeout or a
busy GitHub is passing. A rate limit is final: the skills make few calls (the
sprint report about 9), so waiting one out isn't worth the machinery, and
its advice is to wait a minute and run it again.

When pull requests were opened and merged is read through GraphQL, many in
one call (pull_events()): a call per pull request spent hundreds of requests
of a sprint's hourly limit. Owner, name and number go in as GraphQL
variables, never into the query's text, and a pull request GitHub can't
resolve is a failure of its own while the rest of the call is answered. When
GitHub says the pull request itself doesn't exist (NOT_FOUND, such as one
deleted that Jira still links), its error is `not_found`, so a caller can
skip it without reading gh's words; a repository it can't find isn't, as
that is also what an account without access to it gets.
"""
import json
import re
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor

from agentic_manager.batch import batches
from agentic_manager.config import is_enabled
from agentic_manager.json_path import nested
from agentic_manager.retry import retried

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
# Parallel gh calls: GitHub discourages concurrent requests (its secondary
# rate limit), and reading pull requests in batches leaves few to make.
WORKERS = 4
# What gh says when the call failed in passing: no answer in time, GitHub
# busy or briefly unwell, or the connection lost.
PASSING_SIGNS = ("no answer within", "http 500", "http 502", "http 503", "http 504", "timeout", "timed out",
                 "connection reset", "connection refused", "eof")
# What GitHub's GraphQL calls an error for something that doesn't exist.
NOT_FOUND = "NOT_FOUND"
# What to do when gh fails: a rate limit passes within a minute or so;
# anything else is gh's own setup, or the user goes on without GitHub.
RATE_LIMITED = "Wait a minute and run it again."
GH_BROKEN = ("Check that gh works (gh auth status) and run it again, or disable the github-cli source to go on "
             "without GitHub.")


def gh_available():
    """Whether gh can be used: installed, and enabled as the user's github-cli source."""
    return shutil.which("gh") is not None and is_enabled(GROUP, NAME)


def pulls_holding(repository, sha, run=subprocess.run):
    """The pull requests of a GitHub repository, owner/name, that hold commit
    `sha`, as {url, state, updatedAt} with state OPEN, CLOSED or MERGED; none
    when no pull request holds it. Raises GhError when gh can't tell."""
    return gh_json(["api", f"repos/{repository}/commits/{sha}/pulls", "--jq",
                    "[.[] | {url: .html_url, state: (if .merged_at then \"MERGED\" else (.state | ascii_upcase) end), "
                    "updatedAt: .updated_at}]"], run)


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
    """(events, failures) of the pull requests at `urls`: events as {url:
    {url, state, createdAt, mergedAt}}, when each was opened and, if it was,
    merged (else mergedAt is None), with state OPEN, CLOSED or MERGED; and
    failures as [(url, GhError)] of those gh couldn't read, in the order of
    `urls`, such as one GitHub can't resolve, `not_found` when it doesn't
    exist, or a URL whose parts aren't safe to ask about. Read in a GraphQL
    call for each batch (batch.py) of one host's pull requests: each is a
    single object, not a connection, so a call costs one point of GraphQL's
    hourly 5,000 and stays far below its node limit."""
    urls = list(dict.fromkeys(urls))
    unsafe, hosts = {}, {}
    for url in urls:
        if parts := PULL_PARTS.fullmatch(url):
            hosts.setdefault(parts[1], []).append(url)
        else:
            unsafe[url] = GhError(
                GRAPHQL, f"{url}: not a pull request's address gh can be asked about")
    calls = [(host, chunk) for host, found in hosts.items()
             for chunk in batches(found)]
    answered, failed = gather(
        calls, lambda call: batch_events(call[0], call[1], run))
    events, unread = {}, dict(unsafe)
    for _, (found, missing) in answered:
        events.update(found)
        unread.update(missing)
    for (_, chunk), error in failed:
        unread.update(dict.fromkeys(chunk, error))
    return events, [(url, unread[url]) for url in urls if url in unread]


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


def gather(subjects, call, workers=WORKERS):
    """(answers, failures) of `call`, which reads one subject with gh, for
    each of `subjects`: answers as [(subject, answer)] of those gh answered,
    even with nothing, and failures as [(subject, GhError)] of those it
    couldn't, each in the order of `subjects`; one failure never stops the
    others."""
    def attempt(subject):
        try:
            return call(subject)
        except GhError as failed:
            return failed
    subjects = list(subjects)
    answers, failures = [], []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for subject, outcome in zip(subjects, pool.map(attempt, subjects)):
            (failures if isinstance(outcome, GhError)
             else answers).append((subject, outcome))
    return answers, failures


def gh_json(args, run=subprocess.run):
    """gh's JSON answer to `args`, the command after gh, tried again while gh
    fails in passing; raises GhError when gh gives none."""
    return retried(lambda: gh_once(args, run), passing, note)


def gh_once(args, run):
    """gh's JSON answer to one try of `args`; raises GhError when gh gives none."""
    done = _ran(args, args, run)
    if done.returncode:
        raise GhError(args, (done.stderr or "").strip()
                      or f"exited with code {done.returncode}")
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
    time, or GitHub busy or unreachable; a rate limit, and anything else, is
    final."""
    if not isinstance(error, GhError):
        return False
    message = error.message.lower()
    return "rate limit" not in message and any(sign in message for sign in PASSING_SIGNS)


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
    def advice(self):
        """What the user does about it: wait a minute for GitHub's rate limit,
        or fix gh or disable the github-cli source."""
        return RATE_LIMITED if "rate limit" in self.message.lower() else GH_BROKEN

    @property
    def explanation(self):
        """gh's message on one line, then the advice: how a skill shows the
        failure to the user."""
        return f"{' '.join(self.message.split()).rstrip('.')}. {self.advice}"
