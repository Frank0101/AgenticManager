"""Helpers shared by the sprint-report scripts: file names, blocker candidates, an
issue's moves into and out of the sprint, its state at a past moment, and the
quantity formats every part of the report uses.

It also puts the agentic-manager-utils-lib skill, installed next to this one, on
sys.path and imports what the scripts need from it. The scripts import those
names from here, never from agentic_manager directly, so they don't depend on
the order of their imports."""
import json
import os
import re
import sys
from datetime import datetime

LIB_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)),
                       "..", "..", "agentic-manager-utils-lib")
sys.path.insert(0, LIB_DIR)
from agentic_manager.output_folder import output_folder  # noqa: E402,F401
from agentic_manager.jira import (ISSUE_KEY, JiraClient, date_only, key_order,  # noqa: E402,F401
                                  nested, parse_ts, value_at)

# Files inside a report folder. fetch_sprint.py creates the folder; each later
# step reads and writes here.
RAW_DIR = "_raw"
DATA_FILE = "data.json"
CONTENT_FILE = "content.json"
CHART_FILES = {
    "outcome_stories": "outcome-stories.svg",
    "outcome_points": "outcome-points.svg",
    "burndown": "burndown.svg",
}

# data.json's key for the issues without an epic.
NO_EPIC = "__no_epic__"

# Blocker candidates: flagged, in a blocked-type status, or high priority and
# still open. Teams mark impediments in different ways, often with a workflow
# status rather than Jira's Flagged field, so status names count too.
HIGH_PRIORITIES = {"highest", "high"}
BLOCKED_STATUSES = {"blocked", "impeded",
                    "on hold", "waiting", "waiting for support"}


def is_blocker_candidate(flagged, status, status_category, priority):
    if flagged or (status or "").lower() in BLOCKED_STATUSES:
        return True
    return status_category != "done" and (priority or "").lower() in HIGH_PRIORITIES


# The fields whose history the report reads, by the name changelogs/<KEY>.json
# stores their changes under, and how Jira's changelog names them. The story
# points and Flagged fields are the site's own custom fields.
def history_fields(flagged_field, points_field):
    return {"sprint": "Sprint", "status": "status", "resolution": "resolution",
            "priority": "priority", "parent": "IssueParentAssociation",
            "points": points_field, "flagged": flagged_field}


def status_categories(statuses):
    """{status id: status category key} from Jira's list of statuses."""
    return {str(s["id"]): nested(s, ["statusCategory", "key"]) for s in statuses}


def points_value(value):
    """Story points as a number, or None: whole points as int, fractions kept.
    Takes the issue field's number or a changelog's string."""
    if value is None or value == "":
        return None
    value = float(value)
    return int(value) if value.is_integer() else value


def as_of(sprint, fetched_at):
    """The moment the report describes: when a closed sprint closed, else when
    the data was fetched."""
    if (sprint.get("state") or "").lower() == "closed":
        return sprint.get("completeDate") or sprint.get("endDate")
    return fetched_at


class History:
    """One issue as it was at any past moment, rebuilt from its current fields
    and the changes in its changelog. Nothing reported about an issue comes
    from its current state unless the changelog says it held then too, so a
    report on a past sprint gives the same figures whenever it is run."""

    def __init__(self, raw, changes, categories, flagged_field, points_field):
        self.fields = raw.get("fields") or {}
        self.key = raw["key"]
        self.changes = changes
        self.categories = categories
        self.flagged_field, self.points_field = flagged_field, points_field

    def _current(self, path):
        return nested(self.fields, path)

    def _at(self, field, instant, current):
        return value_at(self.changes, field, instant, current)

    def category(self, status_id):
        category = self.categories.get(str(status_id))
        if category is None and str(status_id) == str(self._current(["status", "id"])):
            category = self._current(["status", "statusCategory", "key"])
        if category is None:
            raise SystemExit(f"{self.key}: status {status_id} is not in Jira's list of statuses; "
                             "fetch the sprint again")
        return category

    def status_at(self, instant):
        """(status name, status category key) at the instant."""
        status_id, name = self._at("status", instant, (self._current(["status", "id"]),
                                                       self._current(["status", "name"])))
        return name, self.category(status_id)

    def done_at(self, instant):
        return self.status_at(instant)[1] == "done"

    def completed_at(self, instant):
        """When the issue last moved into the Done category, if it was Done at
        the instant, else None. An issue created Done completed when created."""
        if not self.done_at(instant):
            return None
        completed = self.fields.get("created")
        for change in self.changes:
            if change["field"] != "status" or parse_ts(change["created"]) > instant:
                continue
            if self.category(change["from"]) != "done" and self.category(change["to"]) == "done":
                completed = change["created"]
        return completed

    def reopened_at(self, after, until):
        """When the issue first moved out of the Done category after `after`,
        up to `until`, or None."""
        for change in sorted(self.changes, key=lambda c: parse_ts(c["created"])):
            if change["field"] != "status" or not after < parse_ts(change["created"]) <= until:
                continue
            if self.category(change["from"]) == "done" and self.category(change["to"]) != "done":
                return change["created"]
        return None

    def state_at(self, instant):
        """Everything the report shows about the issue, as it was at the instant."""
        status, category = self.status_at(instant)
        _, resolution = self._at(
            "resolution", instant, (None, self._current(["resolution", "name"])))
        points = (points_value(self._at("points", instant, (None, self.fields.get(self.points_field)))[1])
                  if self.points_field else None)
        flagged = (bool(self._at("flagged", instant, (None, self.fields.get(self.flagged_field)))[1])
                   if self.flagged_field else False)
        _, priority = self._at("priority", instant,
                               (None, self._current(["priority", "name"])))
        parent_id, parent_key = self._at("parent", instant, (self._current(["parent", "id"]),
                                                             self._current(["parent", "key"])))
        return {"status": status, "statusCategory": category, "resolution": resolution or None,
                "storyPoints": points, "flagged": flagged, "priority": priority or "",
                "parentId": str(parent_id) if parent_id else None, "parentKey": parent_key or None}


def split_ids(value):
    return {piece.strip() for piece in (value or "").split(",") if piece.strip()}


def add_and_remove_events(changes, sprint_id):
    """(added, removed) timestamps for this sprint, each in time order."""
    added, removed = [], []
    for change in changes:
        if change.get("field") != "sprint":
            continue
        from_ids, to_ids = split_ids(change.get(
            "from")), split_ids(change.get("to"))
        if sprint_id in to_ids and sprint_id not in from_ids:
            added.append(change["created"])
        elif sprint_id in from_ids and sprint_id not in to_ids:
            removed.append(change["created"])
    return sorted(added, key=parse_ts), sorted(removed, key=parse_ts)


def sprint_moves(added, removed, created):
    """An issue's moves into (+1) and out of (-1) the sprint, as (instant, move,
    timestamp) in time order. If the first move isn't an add, the sprint was set
    when the issue was created: Jira logs no change for a field's initial
    value, so the creation counts as the first add."""
    moves = sorted([(parse_ts(t), 1, t) for t in added] +
                   [(parse_ts(t), -1, t) for t in removed])
    if not moves or moves[0][1] < 0:
        moves.insert(0, (parse_ts(created), 1, created))
    return moves


def issue_moves(raw, changes, sprint_id):
    """An issue's moves into and out of the sprint (see sprint_moves), from its
    changelog."""
    added, removed = add_and_remove_events(changes, sprint_id)
    return sprint_moves(added, removed, nested(raw.get("fields"), ["created"]))


def in_sprint_at(moves, instant):
    """Membership at an instant, from the complete, ordered sprint moves."""
    state = False
    for when, move, _ in moves:
        if when > instant:
            break
        state = move > 0
    return state


def report_file(label):
    return f"{label}_Sprint_Report.md"


def load_json(path):
    if not os.path.exists(path):
        raise SystemExit(f"missing {path}")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def write_json(path, payload):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)


def report_label(project_key, sprint_name):
    """File-safe label such as PROJ_Sprint_3. The project key is prefixed
    because Jira sprint names ("Sprint 3") often don't carry it."""
    name = sprint_name or "Sprint"
    if project_key and not name.upper().startswith(project_key.upper()):
        name = f"{project_key} {name}"
    return re.sub(r"[^A-Za-z0-9.-]+", "_", name).strip("_")


def number(value):
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def plural(count, one, many):
    """The word for `count` things: `one` for exactly 1, else `many`."""
    return one if count == 1 else many


def unit(count):
    return plural(count, "story", "stories")


def pts(points):
    return f"{number(points)} {plural(points, 'pt', 'pts')}"


def points_text(points):
    return f"{number(points)} {plural(points, 'point', 'points')}"


def qty(count, points):
    """The one quantity format used in every table cell."""
    return f"{count} {unit(count)} / {pts(points)}"


def percentage(part, whole):
    if not whole:
        return "n/a"
    return f"{number(round(part * 100 / whole, 1))}%"


def display_date(iso_date):
    return datetime.strptime(iso_date, "%Y-%m-%d").strftime("%d/%m/%Y")


def target_completion(data):
    """(closed_keys, pool_keys, excluded_keys) for the sprint target metric:
    original-commitment tickets (not points) closed within the sprint.

    Tickets already Done at the start are left out of the pool, because Jira's
    own burndown starts without them. Original tickets removed while still
    open stay in the pool as not closed."""
    excluded, pool = [], []
    for issue in data["issues"] + data["removed_issues"]:
        if not issue["addedMidSprint"]:
            (excluded if issue["startState"]["done"]
             else pool).append(issue["key"])
    credited = {key for row in data["scope_timeline"]
                for key in row["completed_original_keys"]}
    closed = [key for key in pool if key in credited]
    return closed, pool, sorted(excluded, key=key_order)
