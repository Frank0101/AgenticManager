"""Helpers shared by the sprint-report scripts: the report's files and scripts, a
ticket's events and what they say at a past moment (its state, sprint moves,
whether it was a blocker candidate), the report's vocabulary and formats, goal
verdicts, epics and commentary groups, and a description's pieces.

It also puts the agentic-manager-utils-lib skill, installed next to this one, on
sys.path and imports what the scripts need from it. The scripts import those
names from here, never from agentic_manager directly, so they don't depend on
the order of their imports."""
import json
import os
import re
import subprocess
import sys
from datetime import date, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

LIB_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)),
                       "..", "..", "agentic-manager-utils-lib")
sys.path.insert(0, LIB_DIR)
from agentic_manager.output_file import read_json, write_output_file  # noqa: E402,F401
from agentic_manager.text import HEADING, INLINE_LINK, display_date, link_text, word_count  # noqa: E402,F401
from agentic_manager.output_folder import clear_folder, day_folder, output_folder  # noqa: E402,F401
from agentic_manager.json_path import nested  # noqa: E402,F401
from agentic_manager.jira import (ISSUE_KEY, JiraClient, browse_url, key_order,  # noqa: E402,F401
                                  parse_ts, plain_text, project_of)
from agentic_manager.batch import gather  # noqa: E402,F401
from agentic_manager.failures import GITHUB_FAILED, stops_on_failure  # noqa: E402,F401
from agentic_manager.github import GH_UNAVAILABLE, gh_available  # noqa: E402,F401
from agentic_manager.ticket_pulls import pulls_by_ticket, read_events  # noqa: E402,F401

# The skill's output folder, which holds the report folders (see output_folder.py).
REPORTS_FOLDER = "jira-sprint-reports"

# Files inside a report folder. fetch_sprint.py creates the folder; each later
# step reads and writes here.
RAW_DIR = "_raw"
# The raw files inside RAW_DIR, as Jira and GitHub returned them, and the
# fetch's own facts (META_FILE). Changelogs and comments hold one <KEY>.json
# per ticket, sub-tasks left out; PULL_REQUESTS_FILE every ticket's pull requests, how each was
# found and through which ticket, the ticket or a sub-task, when it was
# opened, merged and closed, and those skipped as GitHub says they don't exist.
META_FILE = "_meta.json"
SPRINT_FILE = "sprint.json"
PREVIOUS_SPRINT_FILE = "previous_sprint.json"
SPRINT_ISSUES_FILE = "sprint_issues.json"
SPRINT_REPORT_FILE = "sprint_report.json"
PUNTED_ISSUES_FILE = "punted_issues.json"
STATUSES_FILE = "statuses.json"
PARENTS_FILE = "parents.json"
PULL_REQUESTS_FILE = "pull_requests.json"
CHANGELOGS_DIR = "changelogs"
COMMENTS_DIR = "comments"
DATA_FILE = "data.json"
CONTENT_FILE = "content.json"
BRIEF_FILE = "brief.json"
CHART_FILES = {
    "outcome_tickets": "outcome-tickets.svg",
    "outcome_pts": "outcome-pts.svg",
    "burndown": "burndown.svg",
}

# data.json's key for the tickets without an epic.
NO_EPIC = "__no_epic__"
# The name the report and the brief give the tickets without an epic.
NO_EPIC_NAME = "(no epic)"


# Blocker candidates: flagged, in a blocked-type status, or high priority and
# still open. Teams mark impediments in different ways, often with a workflow
# status rather than Jira's Flagged field, so status names count too.
HIGH_PRIORITIES = {"highest", "high"}
BLOCKED_STATUSES = {"blocked", "impeded",
                    "on hold", "waiting", "waiting for support"}

# Where a sentence ends, for the commentary and the agent's one-sentence texts.
SENTENCE_BREAK = re.compile(r"(?<=[.!?]) +(?=[A-Z0-9])")

# The words the report's vocabulary bans (see "The report's vocabulary and
# formats" below), with what to write instead.
BANNED_WORDS = (("story or stories", r"\bstor(?:y|ies)\b"), ("issue or issues", r"\bissues?\b"),
                ("points (write pts)", r"\bpoints?\b"),
                ("spelled-out numbers (write digits)",
                 r"\b(?:one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|"
                 r"fifteen|sixteen|seventeen|eighteen|nineteen|twenty)\b"),
                ("closed (write completed, or at the close)", r"\bclosed\b"))

# The formats the report's vocabulary sets for prose, each named as the final
# check reports it.
PERCENT_RULE = "whole percentages only"
RATIO_RULE = "ratios only as N/M tickets (N/M pts)"
AMOUNT_RULE = "amounts only as N tickets (N pts)"
BOLD_RULE = "bold only for labels"
DATE_RULE = "no ISO dates"
ESTIMATE_RULE = "a single ticket reads KEY (N pts), its latest estimate"

# The format rules, in the order they are reported.
FORMAT_RULES = (PERCENT_RULE, RATIO_RULE, AMOUNT_RULE, BOLD_RULE, DATE_RULE)

# A ticket key with the estimate that may follow it: "KEY (N pts)", "KEY
# (old → N pts)" or "KEY (– pts)"; group 1 is the key, group 2 the estimate
# shown, None for a bare key.
TICKET_ESTIMATE = re.compile(r"(" + ISSUE_KEY.pattern +
                             r")(?: \((?:(?:\d+(?:\.\d+)?|–) → )?((?:\d+(?:\.\d+)?)|–) pts?\))?")

# Ticket keys in brackets, such as "(PROJ-2, PROJ-3)": a list names tickets
# without their estimates; group 1 is the keys.
KEY_LIST = re.compile(
    r"\((" + ISSUE_KEY.pattern + r"(?:, " + ISSUE_KEY.pattern + r")*)\)")

# The goal verdicts the agent chooses from, word for word. A running sprint
# can't be judged before its halfway day: too little is done to tell.
GOAL_VERDICTS = {"closed": ("Fully met", "Partially met", "Not met"),
                 "early": ("Too early to tell",),
                 "active": ("On track", "At risk"),
                 "no_goal": ("No goal set in Jira for this sprint",)}

# How each piece of work in the outcome charts ended, and their rows: the
# original commitment, split into carry-over and new work, and the extra scope.
OUTCOMES = ("completed", "not_completed", "descoped")
OUTCOME_ROWS = ("original", "carried_in", "new", "extra")

# Each outcome's (background, text) colours, shared by the outcome charts and
# the timeline's tags, so an outcome looks the same wherever it shows.
OUTCOME_COLOURS = {"completed": ("#0ca30c", "#ffffff"), "not_completed": ("#fab219", "#1a1a1a"),
                   "descoped": ("#b5b2aa", "#1a1a1a")}

# The groups of an epic's commentary, in the order it shows them (see
# build_sprint_data.py's scope_group).
SCOPE_GROUPS = ("completed", "in_review", "not_completed", "descoped")

# A pull request's states as at the end, in the order the section counts them.
PULL_STATES = ("merged", "open", "declined")

# The heading of the Status to Verify section, and the class of its cells
# that hold text copied from Jira (epic names and statuses), which the
# report's vocabulary doesn't apply to.
STATUS_HEADING = "Status to Verify"
JIRA_CELL = "jira"

# A description reaches the agent in pieces of at most this many characters, so
# the brief stays small and the rest is read only when it could matter.
DESCRIPTION_CHUNK_CHARS = 2000

# Word limits, so the report stays short enough for an exec to read: the
# timeline's commentary before its caveats, the goal verdict's reason, each
# sentence of an epic's commentary, and the Key Achievements and Blockers &
# Risks paragraphs; and the most retro notes. Words are counted as the
# library's word_count counts them.
COMMENTARY_WORDS = 100
GOAL_REASON_WORDS = 25
EPIC_COMMENTARY_WORDS = 40
ACHIEVEMENTS_WORDS = 150
BLOCKERS_WORDS = 100
RETRO_NOTES = 5

# Marks the parts of the report the agent writes, on their heading or label;
# everything else is generated from data.json and checked.
AI_LABEL = "[AI Gen.]"

# The head of the report's two-column tables of (label, value) rows: the one at
# the top and the one under Sprint Metrics.
FIELD_TABLE_HEAD = "| Field | Detail |\n|---|---|\n"


def report_label(project_key, sprint_name):
    """File-safe label such as PROJ_Sprint_3. The project key is prefixed
    because Jira sprint names ("Sprint 3") often don't carry it."""
    name = sprint_name or "Sprint"
    if project_key and not name.upper().startswith(project_key.upper()):
        name = f"{project_key} {name}"
    return re.sub(r"[^A-Za-z0-9.-]+", "_", name).strip("_")


def expected_files(label):
    """Every file a report folder holds, and nothing else: the fetched _raw
    folder, the three data files, the charts and the report."""
    return {RAW_DIR, DATA_FILE, CONTENT_FILE, BRIEF_FILE,
            *CHART_FILES.values(), report_file(label)}


def report_file(label):
    """The report's file name for a label."""
    return f"{label}_Sprint_Report.md"


def write_json(path, payload):
    """Writes a value as indented JSON inside the skill's output folder."""
    write_report_file(path, json.dumps(payload, indent=2))


def write_report_file(path, text):
    """Writes `text` to `path`, creating missing folders, through the shared
    writer, which exits, writing nothing, if `path` isn't inside the skill's
    output folder."""
    folder, _ = output_folder(REPORTS_FOLDER)
    relative = os.path.relpath(
        os.path.realpath(path), os.path.realpath(folder))
    write_output_file(REPORTS_FOLDER, relative, text.encode("utf-8"))


def run_script(script, *args, **kwargs):
    """Runs a script of this skill with the current Python and returns the
    finished process, its stdout captured as text; `kwargs` go to
    subprocess.run, such as stderr=subprocess.STDOUT to capture both."""
    return subprocess.run([sys.executable, os.path.join(os.path.dirname(os.path.realpath(__file__)), script),
                           *args], stdout=subprocess.PIPE, text=True, **kwargs)


def report_timezone(name):
    """The reporting timezone named by the Jira API account's profile, as
    fetched or as saved in the raw files and data.json."""
    if not isinstance(name, str) or not name.strip():
        raise SystemExit(
            "no reporting timezone: check the Jira API account's timezone and fetch the sprint again")
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        raise SystemExit("reporting timezone is unavailable: check the Jira API account's timezone, "
                         "install timezone data with python3 -m pip install tzdata if needed, "
                         "and fetch the sprint again")


def blocker_candidates(events_of, sprint_id, moment):
    """The keys of the tickets in the sprint at `moment` that were flagged,
    blocked or high priority and not done then (is_blocker_candidate), from
    their events (`events_of`, {key: ticket_events()}), in `events_of`'s order: the
    tickets whose comments the fetch reads and data.json's blocker
    candidates, so the two are the same tickets."""
    cutoff, keys = parse_ts(moment), []
    for key, events in events_of.items():
        if not in_sprint_at(sprint_moves_of(events, sprint_id), cutoff):
            continue
        then = state_at(key, events, cutoff)
        if is_blocker_candidate(then["flagged"], then["status"], then["statusCategory"], then["priority"]):
            keys.append(key)
    return keys


def is_blocker_candidate(flagged, status, status_category, priority):
    """Whether a ticket's flag, status and priority make it a blocker candidate."""
    if flagged or (status or "").lower() in BLOCKED_STATUSES:
        return True
    return status_category != "done" and (priority or "").lower() in HIGH_PRIORITIES


class Context:
    """What every ticket is built with: the sprint and the previous one, the
    site's fields and statuses, the epics' names and the reporting timezone.
    A ticket's events (ticket_events) need only the sprint, the fields, the
    statuses and the timezone."""

    def __init__(self, sprint_id, start_ts, categories, fields, epic_names, reporting_zone: tzinfo,
                 previous):
        self.sprint_id, self.start_ts = sprint_id, start_ts
        self.reporting_zone = reporting_zone
        self.categories = categories
        self.flagged_field, self.points_field = fields
        # {epic id: (key, summary)}
        self.epic_names = epic_names
        # The previous sprint, as previous_sprint.json holds it, or None.
        self.previous = previous


def ticket_events(raw, changes, context, moment):
    """A ticket's events up to `moment`, the end (the close, or the fetch for
    a running sprint), in time order: its creation, with each tracked field's
    value then, and every change of a tracked field. Later events are left
    out, never read as Jira shows the ticket today, so a report run later
    gives the same figures. They are kept per ticket, not per spell: a ticket
    has one history however often it left and came back. Changes at one
    instant keep their stored order, which the library's tracked_changes
    sets by field."""
    cutoff, zone = parse_ts(moment), context.reporting_zone
    tracked = {name for name, ident in history_fields(
        context.flagged_field, context.points_field).items() if ident}
    mine = sorted((c for c in changes if c["field"] in tracked),
                  key=lambda c: parse_ts(c["created"]))
    category = status_category(raw, context.categories)
    events = [created_event(raw, mine, context, category)]
    events += [change_event(c, category, zone)
               for c in mine if parse_ts(c["created"]) <= cutoff]
    return sorted(events, key=lambda e: parse_ts(e["at"]))


def created_event(raw, changes, context, category):
    """The ticket's creation, with each tracked field's value then: the old
    value of its first change, else today's, since Jira logs no change for a
    value set at creation. Read from the whole changelog, later changes
    included: they are when Jira logged what the value was at creation."""
    fields = raw.get("fields") or {}
    today = {
        "status": (nested(fields, ["status", "id"]), nested(fields, ["status", "name"])),
        "resolution": (None, nested(fields, ["resolution", "name"])),
        "priority": (None, nested(fields, ["priority", "name"])),
        "parent": (nested(fields, ["parent", "id"]), nested(fields, ["parent", "key"])),
        "points": (None, fields.get(context.points_field) if context.points_field else None),
        "flagged": (None, fields.get(context.flagged_field) if context.flagged_field else None),
    }
    values = {"sprint": initial_sprints(changes, context.sprint_id)}
    for field, current in today.items():
        first = next((c for c in changes if c["field"] == field), None)
        ident, text = (first["from"], first["fromString"]
                       ) if first else current
        values |= {field: field_value(field, ident, text),
                   **field_extra(field, "", ident, category)}
    return ticket_event(fields.get("created"), "jira", "created", context.reporting_zone, values=values)


def initial_sprints(changes, sprint_id):
    """The sprints the ticket was in when it was created, as sorted ids: each
    sprint its changes name that was set at creation, and the reported sprint
    when no change names it, since it is in it now."""
    named = {sprint_id}.union(*(split_ids(c["from"]) | split_ids(c["to"])
                                for c in changes if c["field"] == "sprint"))
    initial = []
    for sprint in named:
        if set_at_creation(*add_and_remove_events(changes, sprint)):
            initial.append(sprint)
    return field_value("sprint", ", ".join(initial), None)


def change_event(change, category, zone):
    """A change of a tracked field, from and to the values the report reads,
    named <field>_changed."""
    field = change["field"]
    return ticket_event(change["created"], "jira", f"{field}_changed", zone,
                        **{"from": field_value(field, change["from"], change["fromString"]),
                           "to": field_value(field, change["to"], change["toString"])},
                        **field_extra(field, "from", change["from"], category),
                        **field_extra(field, "to", change["to"], category))


def field_value(field, ident, text):
    """The value of a tracked field that the report reads, from a changelog's
    id and string: the sprint ids, the estimate as a number, whether it is
    flagged, and otherwise the name (an epic's key for the parent)."""
    if field == "sprint":
        return sorted(split_ids(ident), key=lambda i: (len(i), i))
    if field == "points":
        return points_value(text)
    if field == "flagged":
        return bool(text)
    return text or None


def field_extra(field, side, ident, category):
    """What a status or a parent adds to its value: the status's category,
    None for one Jira doesn't list, and the parent's id, which names the epic
    when its key changes. `side` is "from", "to", or "" for the creation."""
    if field == "status":
        return {f"{side}Category" if side else "statusCategory": category(ident)}
    if field == "parent":
        return {f"{side}Id" if side else "parentId": str(ident) if ident else None}
    return {}


def ticket_event(at, source, kind, zone, **extra):
    """An event of a ticket's history: when, its local date, its source and
    type, and what `extra` adds."""
    return {"at": at, "date": sprint_date(at, zone), "source": source, "type": kind, **extra}


def state_at(key, events, instant):
    """The ticket's tracked fields at `instant`, replayed from its events: its
    creation's values, then each change up to the instant. Fails on a status
    Jira's list of statuses doesn't hold, since its category is unknown."""
    values = dict(next(e["values"] for e in events if e["type"] == "created"))
    for e in events:
        field = e["type"].removesuffix("_changed")
        if e["source"] != "jira" or field in ("created", "sprint") or parse_ts(e["at"]) > instant:
            continue
        values[field] = e["to"]
        values |= {name: e[f"to{suffix}"] for name, suffix in (("statusCategory", "Category"), ("parentId", "Id"))
                   if f"to{suffix}" in e}
    if values["statusCategory"] is None:
        raise SystemExit(f"{key}: status {values['status']!r} is not in Jira's list of statuses; "
                         "fetch the sprint again")
    return {"status": values["status"], "statusCategory": values["statusCategory"],
            "resolution": values["resolution"], "storyPoints": values["points"], "flagged": values["flagged"],
            "priority": values["priority"] or "", "parentId": values["parentId"], "parentKey": values["parent"]}


def sprint_moves_of(events, sprint_id):
    """The ticket's moves into (+1) and out of (-1) a sprint, as (instant,
    move, timestamp) in time order, from its events: its creation, if it was
    in the sprint then, and its sprint changes."""
    created = next(e for e in events if e["type"] == "created")
    moves = sorted([(parse_ts(e["at"]), 1 if sprint_id in e["to"] else -1, e["at"]) for e in events
                    if e["type"] == "sprint_changed" and (sprint_id in e["to"]) != (sprint_id in e["from"])])
    if sprint_id in created["values"]["sprint"]:
        moves.insert(0, (parse_ts(created["at"]), 1, created["at"]))
    return moves


def in_sprint_at(moves, instant):
    """Membership at an instant, from the complete, ordered sprint moves."""
    state = False
    for when, move, _ in moves:
        if when > instant:
            break
        state = move > 0
    return state


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


def split_ids(value):
    """The set of IDs in a comma-separated changelog value."""
    return {piece.strip() for piece in (value or "").split(",") if piece.strip()}


def set_at_creation(added, removed):
    """Whether the sprint was set when the issue was created: its first move,
    of the timestamps `added` and `removed`, isn't an add, a removal coming
    first at one instant."""
    first = min([(parse_ts(t), 1) for t in added] +
                [(parse_ts(t), -1) for t in removed], default=None)
    return first is None or first[1] < 0


def status_category(raw, categories):
    """A function giving a status id's category: from Jira's list of statuses
    (`categories`, as status_categories() gives it), else the issue's current
    status's own when it is that status, else None, since a status no longer
    in the list can still be in old history."""
    fields = raw.get("fields") or {}

    def category(status_id):
        found = categories.get(str(status_id))
        if found is None and str(status_id) == str(nested(fields, ["status", "id"])):
            found = nested(fields, ["status", "statusCategory", "key"])
        return found
    return category


def sprint_date(ts, zone):
    """Calendar date of a timestamp in the reporting timezone, including its
    daylight-saving rules. An end at 00:00 names the day Jira shows, which
    teams read as the sprint's last day, included: an end of 00:00 on the
    8th means the sprint runs through the 8th."""
    if not ts:
        return None
    return parse_ts(ts).astimezone(zone).date().isoformat()


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


def history_fields(flagged_field, points_field):
    """The fields whose history the report reads, by the name changelogs/<KEY>.json
    stores their changes under, and how Jira's changelog names them. The story
    points and Flagged fields are the site's own custom fields."""
    return {"sprint": "Sprint", "status": "status", "resolution": "resolution",
            "priority": "priority", "parent": "IssueParentAssociation",
            "points": points_field, "flagged": flagged_field}


# A ticket's event types (data.json's ticket_events), by source: Jira's
# creation of the ticket and each change of a tracked field.
TICKET_EVENT_TYPES = {"jira": (
    "created", *(f"{field}_changed" for field in history_fields(None, None)))}


def standard_issues(issues):
    """The issues that aren't sub-tasks: Jira's sprint report and board totals
    count only these, with sub-task work rolled into the parent."""
    return [i for i in issues if not nested(i.get("fields"), ["issuetype", "subtask"])]


def as_of(sprint, fetched_at):
    """The moment the report describes: when a closed sprint closed, else when
    the data was fetched."""
    if (sprint.get("state") or "").lower() == "closed":
        return sprint.get("completeDate") or sprint.get("endDate")
    return fetched_at


def outcome_total(breakdown, row, counts=None):
    """All the work of an outcome_breakdown row, however it ended. For the pts
    breakdown, `counts` is the tickets breakdown: the pts add up by known_sum's
    rule, over the outcomes that hold tickets, so a row of unestimated tickets
    totals None."""
    cells = [f"{row}_{outcome}" for outcome in OUTCOMES]
    if counts is None:
        return sum(breakdown[cell] for cell in cells)
    return known_sum(breakdown[cell] for cell in cells if counts[cell])


# --- The report's vocabulary and formats
#
# Exec readers compare reports sprint to sprint, so each idea has one word and
# each figure one shape; a synonym reads as a different thing. make_report.py
# writes every figure with the helpers below, check_report.py fails a report
# that breaks a rule, and make_report.py rejects the agent's text that does.
#
#   Words       a work item is a ticket (never story or issue); the unit is pts
#               (never points); tickets are completed (never closed: "closed"
#               appears only in the timeline's "(sprint closed)" label).
#   Labels      Commitment (in the sprint at its start), Extra (added after
#               it), Descoped, and Not completed, or Open while the sprint runs.
#               Capitalised in labels and tags, lower case in running text.
#   Amounts     "7 tickets (7 pts)"; done out of total "11/22 tickets
#               (34/74 pts)", never a bare ratio; a share "6 tickets (27% of
#               commitment)" or "13 pts (18% of commitment)"; inside a chart
#               bar, for space only, "3 (50%)".
#   Estimates   one unestimated ticket is "– pts"; pts of several add up the
#               set estimates, an unestimated ticket counting as 0, and are
#               "– pts" when none is set, with "–" for them in a ratio or a
#               share: "0/2 tickets (0/– pts)" (known_sum).
#   Tickets    one as "KEY (N pts)", or "KEY (– pts)" with no estimate; several
#               as the amount then the keys, sorted: "3 tickets (5 pts) were
#               descoped (PROJ-11, PROJ-12, PROJ-13)"; a re-estimate as
#               "PROJ-15 (5 → 3 pts)". The timeline's commentary quotes each
#               ticket at its estimate when its stay in the sprint ended (work
#               already Done at the start, at its estimate then); anywhere else
#               a ticket has its latest estimate, as a reader looking it up
#               would see.
#   Epics       "KEY: Name", or "(no epic)".
#   Numbers     digits, never "one" to "twenty"; whole percentages, "<1%" for a
#               share above zero that would round to 0%, and ">99%" for one
#               below the whole that would round to 100%: rounding must never
#               show work as none or all done when it isn't.
#   Dates       DD/MM/YYYY.
#   Style       bold only for a label that introduces a value ("Open:"); no em
#               dashes. Copied Jira text (the goal, sprint and epic names) keeps
#               its own wording and is exempt from these rules.


def known_sum(estimates):
    """The pts of some work, the rule every amount of pts follows: the sum of
    the estimates that are set, an unestimated ticket counting as 0; None,
    shown as "– pts", when there are estimates to add and none is set, so
    unestimated work never shows as "0 pts"; and 0 for no work at all. A
    partial sum is None only when all its work is unestimated, so sums of the
    partial sums of non-empty parts, such as outcome_total's, follow the same
    rule."""
    estimates = list(estimates)
    known = [e for e in estimates if e is not None]
    return sum(known) if known or not estimates else None


def qty(count, points):
    """An amount of work: "7 tickets (7 pts)"."""
    return f"{count} {unit(count)} ({pts(points)})"


def unit(count):
    """"ticket" or "tickets" for a count."""
    return plural(count, "ticket", "tickets")


def plural(count, one, many):
    """The word for `count` things: `one` for exactly 1, else `many`."""
    return one if count == 1 else many


def pts(points):
    """Story points: "3 pts", "1 pt", or "– pts" when there's no estimate."""
    if points is None:
        return "– pts"
    return f"{number(points)} {plural(points, 'pt', 'pts')}"


def number(value):
    """A number as text: a whole one without a decimal point, and a fraction
    rounded to two decimals, so a sum of fractional estimates never shows
    floating-point noise such as 0.30000000000000004."""
    if isinstance(value, float):
        value = round(value, 2)
        if value.is_integer():
            return str(int(value))
    return str(value)


def ratio(done, total, done_points, total_points):
    """Done out of total: "11/22 tickets (34/74 pts)", with "–" for pts
    that are unestimated (known_sum's None): "0/2 tickets (0/– pts)"."""
    return f"{done}/{total} {unit(total)} ({estimate(done_points)}/{estimate(total_points)} pts)"


def ticket_ref(key, points):
    """One ticket: "PROJ-20 (2 pts)", or "PROJ-13 (– pts)" with no estimate."""
    return f"{key} ({pts(points)})"


def latest_points(spells):
    """{key: pts} of each ticket's latest estimate, its last spell's: the one
    a ticket shows wherever no moment of its own applies, such as running
    text and the Status to Verify table."""
    return {s["key"]: s["points"] for s in spells}


def sprint_key(data):
    """A pattern matching the Jira keys of the sprint's projects, those of its
    spells and epics, so a word shaped like a key, such as UTF-8 or GPT-4, is
    neither linked nor taken for a ticket."""
    projects = {project_of(item["key"])
                for item in data["spells"] + data["epics"]}
    projects = sorted(p for p in projects if p)
    if not projects:
        return re.compile(r"(?!)")
    return re.compile(rf"\b(?:{'|'.join(map(re.escape, projects))})-\d+\b")


def whole_percentage(part, whole):
    """A share as a whole percentage, "<1%" or ">99%" where rounding would
    show a share as none or all of the whole, "–" when either is unestimated
    pts (known_sum's None), and "n/a" when the whole is zero."""
    if part is None or whole is None:
        return "–"
    if not whole:
        return "n/a"
    share = part * 100 / whole
    rounded = f"{share:.0f}"
    if share > 0 and rounded == "0":
        return "<1%"
    if share < 100 and rounded == "100":
        return ">99%"
    return f"{rounded}%"


def text_rule_problems(text, latest=None):
    """[(rule, found)] for each rule of the report's vocabulary and formats
    that the text breaks: banned words first, as "no <rule>", then the formats.
    With `latest`, {key: latest estimate}, a ticket of the sprint must also
    read KEY (N pts) at that estimate, outside a bracketed list of keys. One
    function for the agent's text when it is written and the report's when it
    is checked, so the two can't differ."""
    found = [(f"no {rule}", words) for rule, words in banned_words(text)]
    bold = re.findall(r"\*\*(.+?)\*\*", text) + \
        re.findall(r"<b>(.+?)</b>", text)
    breaking = {
        PERCENT_RULE: re.findall(r"\d+\.\d+%", text),
        RATIO_RULE: re.findall(
            r"(?<![\d/.])\d+(?:\.\d+)?/\d+(?:\.\d+)?(?![\d/])(?!\.\d)(?! (?:tickets?|pts)\b)", text),
        AMOUNT_RULE: re.findall(r"\d+ (?:tickets?|stories|story) / ", text),
        BOLD_RULE: [b for b in bold if not b.endswith(":")],
        DATE_RULE: re.findall(r"\b\d{4}-\d\d-\d\d\b", text),
    }
    formats = [(rule, breaking[rule]) for rule in FORMAT_RULES]
    if latest is not None:
        formats.append((ESTIMATE_RULE, [m.group(0) for m in TICKET_ESTIMATE.finditer(KEY_LIST.sub("", text))
                                        if m.group(1) in latest and m.group(2) != estimate(latest[m.group(1)])]))
    return found + [(rule, items) for rule, items in formats if items]


def banned_words(text):
    """[(rule, words found)] for each banned word the text uses."""
    found = []
    for rule, pattern in BANNED_WORDS:
        words = re.findall(pattern, text, re.I)
        if words:
            found.append((rule, words))
    return found


def estimate(points):
    """An estimate for display: "–" when there is none."""
    return "–" if points is None else number(points)


def allowed_verdicts(data):
    """The goal verdicts a sprint allows: with or without a goal, running or closed."""
    if not data["sprint_goal"].strip():
        return GOAL_VERDICTS["no_goal"]
    if data["sprint_status"] == "closed":
        return GOAL_VERDICTS["closed"]
    start, end, today = (date.fromisoformat(data[k]) for k in (
        "sprint_start", "sprint_end", "today"))
    early = today < start + (end - start) / 2
    return GOAL_VERDICTS["early" if early else "active"]


def spell_epic(spell):
    """(key, name) of a spell's epic, NO_EPIC and NO_EPIC_NAME without one."""
    return (spell["parentKey"], spell["parentSummary"]) if spell["parentKey"] else (NO_EPIC, NO_EPIC_NAME)


def epic_title(epic):
    """An epic's label in the report and the brief: "KEY: Name", or the bare
    name of the tickets without an epic."""
    return epic["name"] if epic["key"] == NO_EPIC else f"{epic['key']}: {epic['name']}"


def scope_group_label(group, status):
    """A commentary group's label: the report's outcome words, with "Open"
    for not completed work while the sprint runs."""
    if group == "not_completed" and status == "active":
        return "Open"
    return {"completed": "Completed", "in_review": "In review", "not_completed": "Not completed",
            "descoped": "Descoped"}[group]


def epic_groups(epic):
    """The commentary groups an epic has tickets to describe in, in order."""
    return [g for g in SCOPE_GROUPS if epic["scope_groups"][g]]


def ai(title):
    """A heading or label of an AI-written part. The label is a small superscript
    after the title it marks: a note for the reader, not part of the title. Its
    size is in rem, so it reads the same after a heading and in a table cell."""
    return f'{title} <sup style="font-size:0.6rem;font-weight:normal">{AI_LABEL}</sup>'


def chunks(text, size=DESCRIPTION_CHUNK_CHARS):
    """`text` in pieces of at most `size` characters. A piece ends at the last
    line break, else the last space, in its second half, so it stops at the end
    of a line when the text has one to use."""
    pieces = []
    while len(text) > size:
        cut = text.rfind("\n", size // 2, size + 1)
        if cut < 0:
            cut = text.rfind(" ", size // 2, size + 1)
        if cut < 0:
            cut = size
        pieces.append(text[:cut].rstrip())
        text = text[cut:].lstrip()
    return [*pieces, text]
