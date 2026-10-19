"""Jira Cloud REST client, using only the standard library.

Credentials come from the user's AgenticManager config
(~/.config/agentic-manager/config.json), source "sources.workflow.jira-api": its
`base-url`, `email` and `api-token`. Jira Cloud authenticates an API token with
Basic auth (email + token). The token is never printed or written to any file;
errors name a setting, never its value. If you add debug output here, print
URLs and status codes only, never headers.

Its `excluded-projects` lists the projects the user's organisation doesn't
allow AI agents to read. The client enforces it, so no skill has to: it
refuses a request for an excluded project or ticket, leaves excluded projects
out of every search (those the account can see: JQL refuses a project it
can't, whose tickets no search returns anyway), and drops them from the parent, links and sub-tasks of
the issues it returns, as if they didn't exist.

The greenhopper endpoints (board estimation field, sprint report) are internal,
not part of Atlassian's documented API, so they could change without notice. The
sprint report is still required: it is the only source of `puntedIssues`
(issues removed from a sprint). Once an issue leaves a sprint its own Sprint
field no longer mentions it, so the public API can't find it. If its shape
changes, sprint_report() fails rather than return a sprint report with its
removals missing. The dev-status endpoints, behind an issue's Development
panel, are internal too: they are the only way to the pull requests a code
host's integration links to an issue.
"""
import base64
import json
import re
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from agentic_manager.config import read_source
from agentic_manager.json_path import nested
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
    """The client for the user's Jira site, which never reads a project `excluded-projects` lists."""

    def __init__(self):
        settings = read_source(GROUP, NAME, SETTINGS, lists=(EXCLUDED,))
        self.base_url = settings["base-url"].rstrip("/")
        credentials = f"{settings['email']}:{settings['api-token']}".encode()
        self._auth = "Basic " + base64.b64encode(credentials).decode()
        self.excluded = frozenset(settings[EXCLUDED])
        self._visible = None

    def is_excluded(self, key):
        """Whether issue `key`, or project `key`, is of an excluded project."""
        return key.rpartition("-")[0] in self.excluded or key in self.excluded

    def _refuse_excluded(self, key):
        if self.is_excluded(key):
            raise SystemExit(f"{key} is of a project excluded by `{EXCLUDED}` in {SOURCE}: "
                             "it is never read")

    def _visible_excluded(self):
        """The excluded projects the account can see, looked up once."""
        if self._visible is None:
            visible = []
            for key in sorted(self.excluded):
                try:
                    self._get(f"/rest/api/3/project/{key}")
                    visible.append(key)
                except NotFound:
                    pass
            self._visible = visible
        return self._visible

    def _scrubbed(self, issue):
        """`issue` without the parent, links and sub-tasks of excluded projects."""
        fields = issue.get("fields") or {}
        if self.is_excluded(nested(fields, ["parent", "key"], "")):
            fields.pop("parent")
        if "issuelinks" in fields:
            fields["issuelinks"] = [link for link in fields["issuelinks"] if not self.is_excluded(
                nested(link, ["outwardIssue", "key"]) or nested(link, ["inwardIssue", "key"], ""))]
        if "subtasks" in fields:
            fields["subtasks"] = [task for task in fields["subtasks"]
                                  if not self.is_excluded(task.get("key", ""))]
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
        most recently closed. Exits if none or, for a name or the active one,
        several match. `log` receives warnings.

        A name given with no board or project is looked for in the project its
        first word spells, as in "PROJ Sprint 6". A wrong guess fails with a message
        that says so."""
        if sprint_id:
            return self.sprint(sprint_id)

        guessed = False
        if name and not board_id and not project:
            project, guessed = name.split()[0], True
        note = (f" ({project!r} is the first word of the sprint name; "
                "give a project or a board)") if guessed else ""

        if board_id:
            board_ids = [board_id]
        else:
            try:
                boards = self.boards_for_project(project)
            except NotFound:
                if not guessed:
                    raise
                boards = []
            # Only scrum boards have sprints; asking a kanban board for its sprints
            # fails with 400 and would abort the whole lookup.
            board_ids = [b["id"] for b in boards if b.get("type") == "scrum"]
            if not board_ids:
                raise SystemExit(
                    f"no scrum board found for project {project}{note}")

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
            raise SystemExit(
                f"no sprint {wanted} found on board(s) {board_ids}{note}")
        if name or active:
            if len(candidates) > 1:
                raise SystemExit(f"{len(candidates)} sprints match (ids {[c['id'] for c in candidates]}); "
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
        """Jira's own sprint report, the only source of removed issues."""
        data = self._get("/rest/greenhopper/1.0/rapid/charts/sprintreport",
                         {"rapidViewId": board_id, "sprintId": sprint_id})
        contents = nested(data, ["contents"])
        if contents is None or "puntedIssues" not in contents:
            raise SystemExit(
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
        find the setting (404).
        A site can have several points-like fields and boards may use
        different ones, so the board's own setting comes first."""
        try:
            data = self._get("/rest/greenhopper/1.0/rapidviewconfig/editmodel.json",
                             {"rapidViewId": board_id})
        except NotFound:
            return None
        stat = nested(data, ["estimationStatisticConfig",
                             "currentEstimationStatistic"], {})
        if stat.get("typeId") == "field" and stat.get("fieldId"):
            return stat["fieldId"]
        return None

    def project(self, key):
        """A project by its key, with its name; NotFound when the site has
        none the account can see, which tells a ticket key from a word of the
        same shape, such as SHA-256."""
        self._refuse_excluded(key)
        return self._get(f"/rest/api/3/project/{key}")

    def issue(self, key, fields):
        """One issue by key, with `fields`. A key of a ticket moved to another
        project still finds it, under its current key."""
        self._refuse_excluded(key)
        issue = self._get(
            f"/rest/api/3/issue/{key}", {"fields": ",".join(fields)})
        self._refuse_excluded(issue["key"])
        return self._scrubbed(issue)

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
        repositoryName; [] for none."""
        return self._development(issue_id, "pullrequest", "pullRequests")

    def commits(self, issue_id):
        """The repositories an issue's Development panel lists, each with the
        commits that name the issue: name, url and commits (id, displayId,
        message, authorTimestamp, url); [] for none."""
        return self._development(issue_id, "repository", "repositories")

    def _development(self, issue_id, data_type, items):
        """The `items` of one kind of the Development panel, from every code
        host its summary names."""
        summary = self._get(f"{DEV_STATUS}/summary", {"issueId": issue_id})
        hosts = nested(summary, ["summary", data_type, "byInstanceType"], {})
        out = []
        for host in hosts:
            detail = self._get(f"{DEV_STATUS}/detail", {"issueId": issue_id, "applicationType": host,
                                                        "dataType": data_type})
            out += [item for found in detail.get("detail", [])
                    for item in found.get(items, [])]
        return out

    def remote_links(self, key):
        """An issue's web links, such as pages and documents, each with its
        object's title and url."""
        self._refuse_excluded(key)
        return self._get(f"/rest/api/3/issue/{key}/remotelink")

    def issues_by_keys(self, keys, fields):
        """Issues by key through JQL; [] for no keys rather than a query that
        matches everything. Keys of excluded projects are left out."""
        return self._issues_where("key", [k for k in keys if not self.is_excluded(k)], fields)

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
        names = {ident: name for name, ident in fields.items() if ident}
        values = self._paginate(
            f"/rest/api/3/issue/{issue_key}/changelog", {}, "values")
        changes = []
        for entry in values:
            for item in entry.get("items", []):
                name = names.get(item.get("fieldId")) or names.get(
                    item.get("field"))
                if name:
                    changes.append({"created": entry.get("created"), "field": name,
                                    **{k: item.get(k) for k in ("from", "to", "fromString", "toString")}})
        # Sort on the parsed instant, not the string: offsets change with
        # daylight saving, so a string sort misorders events across the switch.
        changes.sort(key=lambda c: parse_ts(c["created"]))
        return changes

    def comments(self, issue_key):
        self._refuse_excluded(issue_key)
        return self._paginate(f"/rest/api/3/issue/{issue_key}/comment", {}, "comments")

    def _get(self, path, params=None):
        url = f"{self.base_url}{path}"
        if params:
            url += "?" + urlencode(params)
        request = Request(
            url, headers={"Accept": "application/json", "Authorization": self._auth})
        try:
            with urlopen(request, timeout=30, context=ssl_context()) as response:
                return json.load(response)
        except HTTPError as e:
            if e.code == 401:
                raise SystemExit(
                    f"Jira returned 401 Unauthorized for {path}. Check that your `api-token` in "
                    f"{SOURCE} is valid and belongs to the account in your `email` setting.")
            if e.code == 403:
                raise SystemExit(
                    f"Jira returned 403 Forbidden for {path}: the account lacks permission.")
            if e.code == 404:
                raise NotFound(path)
            raise SystemExit(f"Jira returned {e.code} for {path}.")
        except URLError:
            raise SystemExit(
                f"could not reach Jira. Check your `base-url` setting in {SOURCE} and the connection.")

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
            batch = page.get(items, [])
            out.extend(batch)
            start_at += len(batch)
            if not batch or page.get("isLast") is True or start_at >= page.get("total", float("inf")):
                break
        return out

    def _issues_where(self, clause, values, fields):
        """Issues whose `clause` is one of `values`."""
        return self.search(f"{clause} in ({','.join(values)})", fields) if values else []


class NotFound(SystemExit):
    """The error a request that Jira answers with 404 raises."""

    def __init__(self, path):
        super().__init__(f"Jira returned 404 Not Found for {path}")


def browse_url(base, key):
    """The page of issue `key` on the Jira site at `base`."""
    return f"{base}/browse/{key}"


def key_order(key):
    """Sort key for Jira keys in number order: PROJ-2 before PROJ-10."""
    project, _, number = key.rpartition("-")
    return (project, int(number)) if number.isdigit() else (key, 0)


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
            cells = node.get("content") or []
            if kind == "tableRow":
                for index, cell in enumerate(cells):
                    parts.append(" | " if index else "")
                    walk(cell, in_cell=True)
            else:
                for child in cells:
                    walk(child, in_cell)
            if kind in ADF_BLOCKS:
                parts.append(" " if in_cell else "\n")
        walk(value)
        lines = "".join(parts).splitlines()
    return "\n".join(line for line in (" ".join(raw.split()) for raw in lines) if line)
