"""Jira Cloud REST client, using only the standard library.

Its settings are the user's `jira-api` source. The API token, sent with the
email as Basic auth, is never printed or written anywhere, and errors name a
setting, never its value: debug output added here shows URLs and status
codes only, never headers. A request that fails once retry.py gives up raises JiraError, while
"Jira has none" is an answer (failures.py), so a skill tells "Jira answered
no" from "Jira failed" without sorting errors. The client enforces the
source's `excluded-projects`, so no skill has to.
"""
import base64
import json
import re
import socket
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from agentic_manager.batch import batches
from agentic_manager.config import read_source
from agentic_manager.json_path import nested
from agentic_manager.retry import RATE_LIMITED, RETRY_WAITS, retried
from agentic_manager.text import DISPLAY_DATE
from agentic_manager.web import ssl_context

GROUP, NAME = "workflow", "jira-api"
SOURCE = f"sources.{GROUP}.{NAME}"
SETTINGS = ("base-url", "email", "api-token")
EXCLUDED = "excluded-projects"

# Field names that hold story points, tried in order when the board's own
# estimation setting can't be read. Sites differ: company-managed projects
# usually use "Story Points", team-managed ones "Story point estimate".
STORY_POINT_FIELD_NAMES = ("Story Points", "Story point estimate")

PAGE_SIZE = 100
# Jira's "bulk fetch" of many issues' changelogs: a request for each batch of
# issues (batch.py) rather than one per issue.
BATCH_CHANGELOG = "/rest/api/3/changelog/bulkfetch"
# Change histories a page of the batched changelog's answer holds: the most
# Jira allows.
BATCH_CHANGELOG_PAGE = 10000
# Why a ticket isn't read when Jira answers it has none: it says the same of
# one the account can't see.
NO_SUCH_TICKET = "Jira has no such ticket, or this account can't see it"
# The answers that mean Jira is busy or briefly unwell, not that the request
# is wrong, as when a skill reads many issues at once.
TRANSIENT_CODES = {500, 502, 503, 504}
# The kind of a connection that failed, for the line a retry prints, by the
# type of its error, never its text, which can echo the request or a secret;
# the first that matches, so a subclass comes before its base.
FAILURE_KINDS = ((ConnectionResetError, "connection reset"), (ConnectionRefusedError, "connection refused"),
                 (socket.gaierror, "name not resolved"), (TimeoutError, "timed out"))
# The endpoints behind an issue's Development panel: internal, not part of
# Atlassian's documented API, but the only way to the pull requests a code
# host's integration links to an issue.
DEV_STATUS = "/rest/dev-status/latest/issue"
# The type of Jira Software's Sprint field. A site can have other fields named
# Sprint, so the field is found by its type.
SPRINT_TYPE = "com.pyxis.greenhopper.jira:gh-sprint"
# Where a JQL query's ordering starts: a clause added to the query goes before it.
ORDER_BY = re.compile(r"\border\s+by\b", re.I)

# A Jira issue key such as PROJ-12: its project key, capitals and digits
# starting with a letter, then the issue's number. PROJECT_KEY is the pattern
# a skill builds on when it needs the key's parts or its own context around it.
PROJECT_KEY = r"[A-Z][A-Z0-9]+"
ISSUE_KEY = re.compile(rf"\b{PROJECT_KEY}-\d+\b")
# Atlassian Document Format nodes that end a line of text.
ADF_BLOCKS = {"paragraph", "heading", "listItem", "codeBlock",
              "blockquote", "tableRow", "rule", "mediaGroup"}


class JiraClient:
    """The client for the user's Jira site, which never reads a project `excluded-projects` lists.

    Those are the projects the user's organisation doesn't allow AI agents
    to read. An excluded key given to issue() or project() is answered as
    one Jira doesn't have, with why; any other request about an excluded
    project or ticket is refused, unsent, with a JiraError; and excluded
    projects are left out of every search and dropped from the parent,
    links and sub-tasks of the issues returned, as if they didn't exist."""

    def __init__(self):
        settings = read_source(GROUP, NAME, SETTINGS, lists=(EXCLUDED,))
        self.base_url = settings["base-url"].rstrip("/")
        credentials = f"{settings['email']}:{settings['api-token']}".encode()
        self._auth = "Basic " + base64.b64encode(credentials).decode()
        self.excluded = frozenset(settings[EXCLUDED])
        self._visible = None

    def _is_excluded(self, key):
        """Whether issue `key`, or project `key`, is of an excluded project."""
        return project_of(key) in self.excluded or key in self.excluded

    def _refuse_excluded(self, key):
        """Raises JiraError, unsent, for a request about `key` of an excluded project."""
        if self._is_excluded(key):
            raise JiraError(excluded_reason(key))

    def _visible_excluded(self):
        """The excluded projects the account can see, looked up once: those a
        search leaves out, as JQL refuses a project the account can't see,
        whose tickets no search returns anyway."""
        if self._visible is None:
            visible = []
            for key in sorted(self.excluded):
                if self._found(f"/rest/api/3/project/{key}") is not None:
                    visible.append(key)
            self._visible = visible
        return self._visible

    def _scrubbed(self, issue):
        """`issue` without the parent, links and sub-tasks of excluded projects."""
        fields = issue.get("fields") or {}
        if self._is_excluded(nested(fields, ["parent", "key"], "")):
            fields.pop("parent")
        if "issuelinks" in fields:
            fields["issuelinks"] = [link for link in fields["issuelinks"] if not self._is_excluded(
                nested(link, ["outwardIssue", "key"]) or nested(link, ["inwardIssue", "key"], ""))]
        if "subtasks" in fields:
            fields["subtasks"] = [task for task in fields["subtasks"]
                                  if not self._is_excluded(task.get("key", ""))]
        return issue

    def _not_excluded(self, jql):
        """`jql` with the clause that leaves excluded projects out, before its ordering."""
        visible = self._visible_excluded()
        if not visible:
            return jql
        # Quoted: a key can be a JQL reserved word, such as IN.
        clause = "project not in (" + \
            ",".join(f'"{key}"' for key in visible) + ")"
        order = ORDER_BY.search(jql)
        where, ordering = (jql[:order.start()],
                           jql[order.start():]) if order else (jql, "")
        where = f"({where.strip()}) AND {clause}" if where.strip() else clause
        return f"{where} {ordering.strip()}".strip()

    def whoami(self):
        """The authenticated user profile, including displayName and timeZone."""
        return self._get("/rest/api/3/myself")

    def fields(self):
        return self._get("/rest/api/3/field")

    def field_ids(self):
        """{field name: field id} of the site's fields; of several fields with
        one name, the first Jira lists."""
        by_name = {}
        for field in self.fields():
            by_name.setdefault(field.get("name"), field.get("id"))
        return by_name

    def sprint_field(self):
        """The id of the Sprint field, whose value is each sprint the issue was
        in with its name, state and goal; None on a site without one."""
        return next((f.get("id") for f in self.fields()
                     if nested(f, ["schema", "custom"]) == SPRINT_TYPE), None)

    def statuses(self):
        return self._get("/rest/api/3/status")

    def find_sprint(self, sprint_id=None, board_id=None, project=None, name=None, active=False,
                    log=None):
        """One sprint, by id, or on a board or a project's scrum boards: the one
        named `name` in any state, else the active one if `active`, else the
        most recently closed. Raises JiraError if none or, for a name or the
        active one, several match. `log` receives warnings.

        A name given with no board or project is looked for in the project its
        first word spells, as in "PROJ Sprint 6". A wrong guess fails with a message
        that says so."""
        if sprint_id:
            return self.sprint(sprint_id)

        guessed = False
        if name and not board_id and not project:
            project, guessed = name.split()[0], True
        hint = (f" ({project!r} is the first word of the sprint name; "
                "give a project or a board)") if guessed else ""

        if board_id:
            board_ids = [board_id]
        else:
            try:
                boards = self.boards_for_project(project)
            except JiraError as failed:
                if not (guessed and failed.not_found):
                    raise
                boards = []
            # Only scrum boards have sprints; asking a kanban board for its sprints
            # fails with 400 and would abort the whole lookup.
            board_ids = [b["id"] for b in boards if b.get("type") == "scrum"]
            if not board_ids:
                raise JiraError(
                    f"no scrum board found for project {project}{hint}")

        # A named sprint is matched in any state: the user named it, and it is most
        # often the one in progress.
        state = None if name else ("active" if active else "closed")
        # The same sprint can appear on several boards of a project; dedupe by id.
        seen, candidates = set(), []
        for board in board_ids:
            for sprint in self.sprints_for_board(board, state=state):
                if name and sprint.get("name") != name:
                    continue
                if sprint["id"] not in seen:
                    seen.add(sprint["id"])
                    candidates.append(sprint)

        if not candidates:
            wanted = f"named {name!r}" if name else state
            raise JiraError(
                f"no sprint {wanted} found on board(s) {board_ids}{hint}")
        if name or active:
            if len(candidates) > 1:
                raise JiraError(f"{len(candidates)} sprints match (ids {[c['id'] for c in candidates]}); "
                                "give a sprint id or a board to pick one")
            return candidates[0]
        if log and len({c.get("originBoardId") for c in candidates}) > 1:
            log("warning: closed sprints span several boards; picked the latest. "
                "Give a board to choose one.")

        def ended(sprint):
            stamp = sprint.get("completeDate") or sprint.get("endDate")
            return parse_ts(stamp) if stamp else datetime.min.replace(tzinfo=timezone.utc)
        return max(candidates, key=ended)

    def sprint(self, sprint_id):
        return self._get(f"/rest/agile/1.0/sprint/{sprint_id}")

    def boards_for_project(self, project_key):
        self._refuse_excluded(project_key)
        return self._paginate("/rest/agile/1.0/board", {"projectKeyOrId": project_key}, "values")

    def sprints_for_board(self, board_id, state=None):
        params = {"state": state} if state else {}
        return self._paginate(f"/rest/agile/1.0/board/{board_id}/sprint", params, "values")

    def sprint_issues(self, sprint_id, fields):
        params = {"fields": ",".join(fields)}
        if clause := self._not_excluded(""):
            params["jql"] = clause
        return [self._scrubbed(issue) for issue in
                self._paginate(f"/rest/agile/1.0/sprint/{sprint_id}/issue", params, "issues")]

    def sprint_report(self, board_id, sprint_id):
        """Jira's own sprint report, the only source of removed issues
        (`puntedIssues`): once an issue leaves a sprint its own Sprint field no
        longer mentions it, so the public API can't find it. The endpoint is
        internal (greenhopper), not part of Atlassian's documented API, so a
        changed shape fails rather than return a report without its
        removals."""
        data = self._get("/rest/greenhopper/1.0/rapid/charts/sprintreport",
                         {"rapidViewId": board_id, "sprintId": sprint_id})
        contents = nested(data, ["contents"])
        if contents is None or "puntedIssues" not in contents:
            raise JiraError(
                "Jira's sprint report came back in an unexpected shape (no contents.puntedIssues). "
                "This internal endpoint may have changed. Removed issues can't be found any other "
                "way, so this fails rather than return the sprint report without them.")
        return data

    def flagged_and_points_fields(self, board_id):
        """(Flagged field id, story points field id); either may be None. The
        points field is the board's own estimation setting, else the first
        field named as in STORY_POINT_FIELD_NAMES."""
        by_name = self.field_ids()
        points = self.board_estimation_field(board_id)
        if not points:
            points = next(
                (by_name[n] for n in STORY_POINT_FIELD_NAMES if n in by_name), None)
        return by_name.get("Flagged"), points

    def board_estimation_field(self, board_id):
        """The field the board sums as story points (Board settings >
        Estimation), or None if it estimates by issue count or Jira doesn't
        find the setting (404), read from an internal (greenhopper) endpoint.
        A site can have several points-like fields and boards may use
        different ones, so the board's own setting comes first."""
        data = self._found("/rest/greenhopper/1.0/rapidviewconfig/editmodel.json",
                           {"rapidViewId": board_id})
        if data is None:
            return None
        stat = nested(data, ["estimationStatisticConfig",
                             "currentEstimationStatistic"], {})
        if stat.get("typeId") == "field" and stat.get("fieldId"):
            return stat["fieldId"]
        return None

    def project(self, key):
        """A project by its key, with its name; None when the site has none
        the account can see, or it is excluded, which tells a ticket key from
        a word of the same shape, such as SHA-256."""
        if self._is_excluded(key):
            return None
        return self._found(f"/rest/api/3/project/{key}")

    def issue(self, key, fields):
        """(the issue, None), one issue by key with `fields`, or (None, why
        it isn't read, a line naming the key) when Jira has no such ticket
        the account can see or it is of an excluded project. A key of a
        ticket moved to another project still finds it, under its current
        key."""
        if self._is_excluded(key):
            return None, excluded_reason(key)
        issue = self._found(
            f"/rest/api/3/issue/{key}", {"fields": ",".join(fields)})
        if issue is None:
            return None, f"{key}: {NO_SUCH_TICKET}"
        if self._is_excluded(issue["key"]):
            return None, excluded_reason(issue["key"])
        return self._scrubbed(issue), None

    def search(self, jql, fields):
        """Every issue a JQL query matches, with `fields`, excluded projects
        left out. Paging is token-based and ends only when `nextPageToken` is
        absent."""
        out, token, jql = [], None, self._not_excluded(jql)
        while True:
            params = {"jql": jql, "maxResults": PAGE_SIZE,
                      "fields": ",".join(fields)}
            if token:
                params["nextPageToken"] = token
            page = self._get("/rest/api/3/search/jql", params)
            out.extend(self._scrubbed(issue)
                       for issue in page.get("issues", []))
            token = page.get("nextPageToken")
            if not token:
                return out

    def pull_requests(self, issue_id):
        """The pull requests an issue's Development panel lists, from every
        code host connected to the site, as the panel describes them: name,
        url, status, source and destination branch, lastUpdate,
        repositoryName; [] for none. Read from each code host the panel's
        summary names."""
        summary = self._get(f"{DEV_STATUS}/summary", {"issueId": issue_id})
        hosts = nested(
            summary, ["summary", "pullrequest", "byInstanceType"], {})
        out = []
        for host in hosts:
            detail = self._get(f"{DEV_STATUS}/detail", {"issueId": issue_id, "applicationType": host,
                                                        "dataType": "pullrequest"})
            out += [pr for found in detail.get("detail", [])
                    for pr in found.get("pullRequests", [])]
        return out

    def remote_links(self, key):
        """An issue's web links, such as pages and documents, each with its
        object's title and url."""
        self._refuse_excluded(key)
        return self._get(f"/rest/api/3/issue/{key}/remotelink")

    def issues_by_keys(self, keys, fields):
        """Issues by key through JQL; [] for no keys rather than a query that
        matches everything. Keys of excluded projects are left out."""
        return self._issues_where("key", [k for k in keys if not self._is_excluded(k)], fields)

    def issues_by_ids(self, ids, fields):
        """Issues by numeric id, as changelogs name them; [] for no ids."""
        return self._issues_where("id", ids, fields)

    def field_changes(self, issue_key, fields):
        """Every change of the given fields of an issue, in time order, as
        {"created", "field", "from", "to", "fromString", "toString"}. `fields`
        maps the name each change is stored under to how the changelog names
        the field: its id ("status", "customfield_10016") or, for fields logged
        without one, its name ("IssueParentAssociation"). Reads the whole
        changelog, since the changes can sit past the first page; a truncated
        changelog would give a wrong history with no error anywhere."""
        self._refuse_excluded(issue_key)
        return tracked_changes(self._paginate(
            f"/rest/api/3/issue/{issue_key}/changelog", {}, "values"), fields)

    def batched_field_changes(self, issues, fields):
        """(changes, gone): changes as {key: field_changes(key, fields)} of
        each of `issues` Jira has, in their order, each issue given with its
        "id" and "key", read with Jira's batched changelog read: a batch of
        issues a request, every page of each; and gone as {key: why, a line
        naming the key} of those Jira has no such ticket of, or none the
        account can see. The answer names issues by id, which `issues` turns
        back into keys. Jira gives no entry both for an issue never changed
        and for one it doesn't have or the account can't see, so the issues
        left without one are looked up with one search by id: one found gives
        [], as an empty entry does. Every field is asked for, not only the
        tracked ones: a field logged without an id, such as
        IssueParentAssociation, can't be named in `fieldIds`. Refuses, before
        any request, an issue of an excluded project. The batched read gives
        a change's time in milliseconds, so it is written as the per-issue
        changelog writes it, in the account's time zone, and the two give the
        same changes."""
        for issue in issues:
            self._refuse_excluded(issue["key"])
        zone = ZoneInfo(self.whoami().get("timeZone")
                        or "UTC") if issues else None
        keys = {str(issue["id"]): issue["key"] for issue in issues}
        histories = {issue_id: [] for issue_id in keys}
        logged = set()
        for ids in batches(keys):
            body = {"issueIdsOrKeys": ids,
                    "maxResults": BATCH_CHANGELOG_PAGE}
            while True:
                page = self._post(BATCH_CHANGELOG, body)
                for log in page.get("issueChangeLogs", []):
                    logged.add(str(log["issueId"]))
                    histories[str(log["issueId"])].extend(
                        {**history,
                            "created": jira_stamp(history.get("created"), zone)}
                        for history in log.get("changeHistories") or [])
                if not (token := page.get("nextPageToken")):
                    break
                body = {**body, "nextPageToken": token}
        unseen = [issue_id for issue_id in keys if issue_id not in logged]
        found = {str(issue["id"]) for chunk in batches(unseen)
                 for issue in self.issues_by_ids(chunk, ["key"])}
        gone = {keys[issue_id]: f"{keys[issue_id]}: {NO_SUCH_TICKET}"
                for issue_id in unseen if issue_id not in found}
        return ({key: tracked_changes(histories[issue_id], fields)
                 for issue_id, key in keys.items() if key not in gone}, gone)

    def comments(self, issue_key):
        self._refuse_excluded(issue_key)
        return self._paginate(f"/rest/api/3/issue/{issue_key}/comment", {}, "comments")

    def _found(self, path, params=None):
        """Jira's answer for `path`, or None when Jira answers 404."""
        try:
            return self._get(path, params)
        except JiraError as failed:
            if failed.not_found:
                return None
            raise

    def _get(self, path, params=None):
        url = f"{self.base_url}{path}"
        if params:
            url += "?" + urlencode(params)
        return self._send(path, Request(url, headers=self._headers()))

    def _post(self, path, body):
        """Jira's answer to `body` sent as JSON to `path`, tried again as a GET
        is: the only POST, the batched changelog read, reads and changes
        nothing."""
        return self._send(path, Request(f"{self.base_url}{path}", data=json.dumps(body).encode(), method="POST",
                                        headers={**self._headers(), "Content-Type": "application/json"}))

    def _headers(self):
        return {"Accept": "application/json", "Authorization": self._auth}

    def _send(self, path, request):
        """Jira's answer to `request`, to `path`, tried again while it fails
        in passing; a failure raises JiraError, naming `path` and the setting
        to check, never a secret."""
        def attempt():
            with urlopen(request, timeout=30, context=ssl_context()) as response:
                return json.load(response)
        try:
            return retried(attempt, passing, lambda error: note(error, path))
        except HTTPError as e:
            if e.code == 401:
                raise JiraError(f"Jira returned 401 Unauthorized for {path}.",
                                f"Check that your `api-token` in {SOURCE} is valid and belongs to the account "
                                "in your `email` setting.")
            if e.code == 403:
                raise JiraError(
                    f"Jira returned 403 Forbidden for {path}: the account lacks permission.")
            if e.code == 404:
                raise JiraError(
                    f"Jira returned 404 Not Found for {path}.", not_found=True)
            if e.code == 429:
                raise JiraError(
                    f"Jira returned 429 Too Many Requests for {path}.", RATE_LIMITED)
            raise JiraError(f"Jira returned {e.code} for {path}.")
        except (URLError, TimeoutError, ConnectionError):
            raise JiraError(f"could not reach Jira, after trying {len(RETRY_WAITS) + 1} times.",
                            f"Check your `base-url` setting in {SOURCE} and the connection.")

    def _paginate(self, path, params, items):
        """Every item of a paged list, under the page's `items` key. Paging ends
        on an empty page, `isLast`, or once `total` items have been read, when
        the page gives one. A short page doesn't end it: the server caps
        maxResults (board sprints at 50 even when asked for 100), so stopping
        there would drop results."""
        out, start_at = [], 0
        while True:
            page = self._get(
                path, {**params, "startAt": start_at, "maxResults": PAGE_SIZE})
            found = page.get(items, [])
            out.extend(found)
            start_at += len(found)
            if not found or page.get("isLast") is True or start_at >= page.get("total", float("inf")):
                break
        return out

    def _issues_where(self, clause, values, fields):
        """Issues whose `clause` is one of `values`."""
        return self.search(f"{clause} in ({','.join(values)})", fields) if values else []


def jira_stamp(created, zone):
    """A change's time as Jira's per-issue changelog writes it, such as
    2026-10-02T14:19:18.009+0100, from the milliseconds the batched read gives;
    text already in that form is kept."""
    if not isinstance(created, (int, float)):
        return created
    moment = datetime.fromtimestamp(created / 1000, zone)
    return f"{moment:%Y-%m-%dT%H:%M:%S}.{int(created) % 1000:03d}{moment:%z}"


def tracked_changes(histories, fields):
    """The changes of `fields` (see JiraClient.field_changes) in an issue's
    change histories, each {"created", "items"}, sorted by instant."""
    names = {ident: name for name, ident in fields.items() if ident}
    changes = []
    for entry in histories:
        for item in entry.get("items", []):
            name = names.get(item.get("fieldId")) or names.get(
                item.get("field"))
            if name:
                changes.append({"created": entry.get("created"), "field": name,
                                **{k: item.get(k) for k in ("from", "to", "fromString", "toString")}})
    # Sort on the parsed instant, not the string: offsets change with
    # daylight saving, so a string sort misorders events across the switch.
    # Changes of one instant go by field, as the per-issue and the batched
    # changelog list them in different orders.
    changes.sort(key=lambda c: (parse_ts(c["created"]), c["field"]))
    return changes


def passing(error):
    """Whether a failed request is passing, to retry.retried(): a dropped
    connection, a timeout or an answer of TRANSIENT_CODES; any other answer
    is final, a 429 included: a rate limit, as every service's is, with the
    advice to wait a minute."""
    if isinstance(error, HTTPError):
        return error.code in TRANSIENT_CODES
    return isinstance(error, (URLError, TimeoutError, ConnectionError))


def note(error, path):
    """What failed, for the line a retry prints: the status Jira answered,
    or the kind of failure when it gave none, and `path`, the request's path
    without its query, which can hold JQL; never Jira's body or the error's
    text, which a secret could be in."""
    if isinstance(error, HTTPError):
        return f"Jira answered {error.code} on {path}"
    kind = failure_kind(error)
    return f"Jira couldn't be reached{f' ({kind})' if kind else ''} on {path}"


def failure_kind(error):
    """The kind of a failed connection, such as "connection reset", from the
    type of `error` or, for a URLError, of the error it wraps (its reason);
    None for any other."""
    reason = error.reason if isinstance(error, URLError) else error
    return next((words for kind, words in FAILURE_KINDS if isinstance(reason, kind)), None)


def excluded_reason(key):
    """Why issue or project `key`, of an excluded project, is never read."""
    return f"{key} is of a project excluded by `{EXCLUDED}` in {SOURCE}: it is never read"


class JiraError(Exception):
    """A request Jira gave no answer to: `message`, what failed, naming the
    path, never Jira's response body, which could echo the token; `advice`,
    what the user does about it, or ""; and `not_found`, whether Jira
    answered 404."""

    def __init__(self, message, advice="", not_found=False):
        self.message, self.advice, self.not_found = message, advice, not_found
        super().__init__(self.explanation)

    @property
    def explanation(self):
        """The message, then the advice: how a skill shows the failure to the user."""
        return f"{self.message} {self.advice}" if self.advice else self.message


def browse_url(base, key):
    """The page of issue `key` on the Jira site at `base`."""
    return f"{base}/browse/{key}"


def key_order(key):
    """Sort key for Jira keys in number order: PROJ-2 before PROJ-10."""
    number = key.rpartition("-")[2]
    return (project_of(key), int(number)) if number.isdigit() else (key, 0)


def project_of(key):
    """The project key of issue `key`, up to its last hyphen: PROJ for
    PROJ-12; "" for a key without one, such as a project key."""
    return key.rpartition("-")[0]


def parse_ts(ts):
    """Parse both timestamp shapes Jira emits: issue and changelog stamps carry
    a literal offset ("...+0100"), the Agile API's sprint dates end in "Z"."""
    return datetime.fromisoformat(ts)


def value_at(changes, field, instant, current):
    """A field's value at `instant`, as (id, string), from its changes (see
    JiraClient.field_changes) and its `current` (id, string): the new value of
    the last change at or before the instant, else the old value of the first
    change after it, else the current value. Jira logs no change for a value
    set when the issue was created, so a field never changed has had its
    current value all along."""
    mine = [c for c in changes if c["field"] == field]
    before = [c for c in mine if parse_ts(c["created"]) <= instant]
    if before:
        return before[-1]["to"], before[-1]["toString"]
    after = [c for c in mine if parse_ts(c["created"]) > instant]
    if after:
        return after[0]["from"], after[0]["fromString"]
    return current


def plain_text(value, links=False):
    """A rich-text field (a description or a comment) as plain text, whether
    Jira returns it in Atlassian Document Format, as API v3 does, or as a
    string, as the Agile API does; "" for none. Line breaks between blocks are
    kept, other whitespace collapsed. ADF date timestamps become UTC calendar
    dates in DD/MM/YYYY format. With `links`, linked text is followed by its
    URL in brackets, so the pages a ticket links can be followed."""
    if not value:
        return ""
    if isinstance(value, str):
        lines = value.splitlines()
    else:
        parts = []

        def walk(node, in_cell=False):
            kind, attrs = node.get("type"), node.get("attrs") or {}
            if kind == "text":
                text = node.get("text", "")
                href = next((m.get("attrs", {}).get("href") for m in node.get("marks") or []
                             if m.get("type") == "link"), None)
                parts.append(
                    f"{text} ({href})" if links and href and href != text else text)
            elif kind == "hardBreak":
                parts.append(" " if in_cell else "\n")
            elif kind == "date":
                date = datetime.fromtimestamp(
                    int(attrs["timestamp"]) / 1000, timezone.utc)
                parts.append(date.strftime(DISPLAY_DATE))
            elif kind in ("mention", "emoji", "status"):
                parts.append(
                    str(attrs.get("text") or attrs.get("shortName") or ""))
            elif kind in ("inlineCard", "blockCard", "embedCard"):
                parts.append(str(attrs.get("url") or ""))
            children = node.get("content") or []
            if kind == "tableRow":
                for index, cell in enumerate(children):
                    parts.append(" | " if index else "")
                    walk(cell, in_cell=True)
            else:
                for child in children:
                    walk(child, in_cell)
            if kind in ADF_BLOCKS:
                parts.append(" " if in_cell else "\n")
        walk(value)
        lines = "".join(parts).splitlines()
    return "\n".join(line for line in (" ".join(raw.split()) for raw in lines) if line)
