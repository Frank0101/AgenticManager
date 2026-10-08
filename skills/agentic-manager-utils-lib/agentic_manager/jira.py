"""Jira Cloud REST client, using only the standard library.

Credentials come from the user's AgenticManager config
(~/.config/agentic-manager/config.json), source "sources.workflow.jira-api": its
`base-url`, `email` and `api-token`. Jira Cloud authenticates an API token with
Basic auth (email + token). The token is never printed or written to any file;
errors name a setting, never its value. If you add debug output here, print
URLs and status codes only, never headers.

The greenhopper endpoints (board estimation field, sprint report) are internal,
not part of Atlassian's documented API, so they could change without notice. The sprint report is still required: it
is the only source of `puntedIssues` (issues removed from a sprint). Once an
issue leaves a sprint its own Sprint field no longer mentions it, so the public
API can't find it. If its shape changes, sprint_report() fails rather than
return a sprint report with its removals missing.
"""
import base64
import json
import re
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from agentic_manager.config import read_source

SOURCE = "sources.workflow.jira-api"
SETTINGS = ("base-url", "email", "api-token")

# Field names that hold story points, tried in order when the board's own
# estimation setting can't be read. Sites differ: company-managed projects
# usually use "Story Points", team-managed ones "Story point estimate".
STORY_POINT_FIELD_NAMES = ("Story Points", "Story point estimate")

PAGE_SIZE = 100

# A Jira issue key such as PROJ-12.
ISSUE_KEY = re.compile(r"\b[A-Z][A-Z0-9]+-\d+\b")


def key_order(key):
    """Sort key for Jira keys in number order: PROJ-2 before PROJ-10."""
    project, _, number = key.rpartition("-")
    return (project, int(number)) if number.isdigit() else (key, 0)


def nested(node, path, default=None):
    """The value at `path` in nested Jira objects, or `default` if any step is
    missing or null. `node` itself may be None."""
    for key in path:
        if node is None:
            return default
        node = node.get(key)
    return node if node is not None else default


def parse_ts(ts):
    """Parse both timestamp shapes Jira emits: issue and changelog stamps carry
    a literal offset ("...+0100"), the Agile API's sprint dates end in "Z"."""
    return datetime.fromisoformat(ts)


# Atlassian Document Format nodes that end a line of text.
ADF_BLOCKS = {"paragraph", "heading", "listItem", "codeBlock",
              "blockquote", "tableRow", "rule", "mediaGroup"}


def plain_text(value):
    """A rich-text field (a description or a comment) as plain text, whether
    Jira returns it in Atlassian Document Format, as API v3 does, or as a
    string, as the Agile API does; "" for none. Line breaks between blocks are
    kept, other whitespace collapsed. ADF date timestamps become UTC calendar
    dates in DD/MM/YYYY format."""
    if not value:
        return ""
    if isinstance(value, str):
        lines = value.splitlines()
    else:
        parts = []

        def walk(node, in_cell=False):
            kind, attrs = node.get("type"), node.get("attrs") or {}
            if kind == "text":
                parts.append(node.get("text", ""))
            elif kind == "hardBreak":
                parts.append(" " if in_cell else "\n")
            elif kind == "date":
                date = datetime.fromtimestamp(
                    int(attrs["timestamp"]) / 1000, timezone.utc)
                parts.append(date.strftime("%d/%m/%Y"))
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


class JiraClient:
    def __init__(self):
        settings = read_source("workflow", "jira-api", SETTINGS)
        self.base_url = settings["base-url"].rstrip("/")
        credentials = f"{settings['email']}:{settings['api-token']}".encode()
        self._auth = "Basic " + base64.b64encode(credentials).decode()

    def _get(self, path, params=None):
        url = f"{self.base_url}{path}"
        if params:
            url += "?" + urlencode(params)
        request = Request(
            url, headers={"Accept": "application/json", "Authorization": self._auth})
        try:
            with urlopen(request, timeout=30) as response:
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

    def whoami(self):
        """The authenticated user profile, including displayName and timeZone."""
        return self._get("/rest/api/3/myself")

    def fields(self):
        return self._get("/rest/api/3/field")

    def sprint(self, sprint_id):
        return self._get(f"/rest/agile/1.0/sprint/{sprint_id}")

    def boards_for_project(self, project_key):
        return self._paginate("/rest/agile/1.0/board", {"projectKeyOrId": project_key}, "values")

    def sprints_for_board(self, board_id, state=None):
        params = {"state": state} if state else {}
        return self._paginate(f"/rest/agile/1.0/board/{board_id}/sprint", params, "values")

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

    def find_sprint(self, sprint_id=None, board_id=None, project=None, name=None, active=False,
                    log=None):
        """One sprint, by id, or on a board or a project's scrum boards: the one
        named `name` in any state, else the active one if `active`, else the
        most recently closed. Exits if none or, for a name or the active one,
        several match. `log` receives warnings."""
        if sprint_id:
            return self.sprint(sprint_id)

        if board_id:
            board_ids = [board_id]
        else:
            boards = self.boards_for_project(project)
            # Only scrum boards have sprints; asking a kanban board for its sprints
            # fails with 400 and would abort the whole lookup.
            board_ids = [b["id"] for b in boards if b.get("type") == "scrum"]
            if not board_ids:
                raise SystemExit(f"no scrum board found for project {project}")

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
                f"no sprint {wanted} found on board(s) {board_ids}")
        if name or active:
            if len(candidates) > 1:
                raise SystemExit(f"{len(candidates)} sprints match (ids {[c['id'] for c in candidates]}); "
                                 "give a sprint id or a board to pick one")
            return candidates[0]
        if log and len({c.get("originBoardId") for c in candidates}) > 1:
            log("warning: closed sprints span several boards; picked the latest. "
                "Give a board to choose one.")
        return max(candidates, key=lambda s: parse_ts(s.get("completeDate") or s["endDate"])
                   if s.get("completeDate") or s.get("endDate") else datetime.min.replace(tzinfo=timezone.utc))

    def flagged_and_points_fields(self, board_id):
        """(Flagged field id, story points field id); either may be None. The
        points field is the board's own estimation setting, else the first
        field named as in STORY_POINT_FIELD_NAMES."""
        by_name = {}
        for field in self.fields():
            by_name.setdefault(field.get("name"), field.get("id"))
        points = self.board_estimation_field(board_id)
        if not points:
            points = next(
                (by_name[n] for n in STORY_POINT_FIELD_NAMES if n in by_name), None)
        return by_name.get("Flagged"), points

    def sprint_issues(self, sprint_id, fields):
        return self._paginate(f"/rest/agile/1.0/sprint/{sprint_id}/issue",
                              {"fields": ",".join(fields)}, "issues")

    def issues_by_keys(self, keys, fields):
        """Issues by key through JQL; [] for no keys rather than a query that
        matches everything."""
        return self._issues_where("key", keys, fields)

    def issues_by_ids(self, ids, fields):
        """Issues by numeric id, as changelogs name them; [] for no ids."""
        return self._issues_where("id", ids, fields)

    def _issues_where(self, clause, values, fields):
        """Issues whose `clause` is one of `values`. Paging is token-based and
        ends only when `nextPageToken` is absent."""
        if not values:
            return []
        out, token = [], None
        while True:
            params = {"jql": f"{clause} in ({','.join(values)})", "maxResults": PAGE_SIZE,
                      "fields": ",".join(fields)}
            if token:
                params["nextPageToken"] = token
            page = self._get("/rest/api/3/search/jql", params)
            batch = page.get("issues", [])
            out.extend(batch)
            token = page.get("nextPageToken")
            if not token:
                break
        return out

    def field_changes(self, issue_key, fields):
        """Every change of the given fields of an issue, in time order, as
        {"created", "field", "from", "to", "fromString", "toString"}. `fields`
        maps the name each change is stored under to how the changelog names
        the field: its id ("status", "customfield_10016") or, for fields logged
        without one, its name ("IssueParentAssociation"). Reads the whole
        changelog, since the changes can sit past the first page; a truncated
        changelog would give a wrong history with no error anywhere."""
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

    def statuses(self):
        return self._get("/rest/api/3/status")

    def comments(self, issue_key):
        return self._paginate(f"/rest/api/3/issue/{issue_key}/comment", {}, "comments")

    def board_estimation_field(self, board_id):
        """The field the board sums as story points (Board settings >
        Estimation), or None if it estimates by issue count or can't be read.
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


class NotFound(SystemExit):
    def __init__(self, path):
        super().__init__(f"Jira returned 404 Not Found for {path}")
