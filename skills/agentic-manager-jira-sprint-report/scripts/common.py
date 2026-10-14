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
import subprocess
import sys
from datetime import date
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

LIB_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)),
                       "..", "..", "agentic-manager-utils-lib")
sys.path.insert(0, LIB_DIR)
from agentic_manager.output_file import read_json, write_output_file  # noqa: E402,F401
from agentic_manager.text import DISPLAY_DATE, INLINE_LINK, link_text, word_count  # noqa: E402,F401
from agentic_manager.output_folder import clear_folder, day_folder, output_folder  # noqa: E402,F401
from agentic_manager.json_path import nested  # noqa: E402,F401
from agentic_manager.jira import (ISSUE_KEY, JiraClient, browse_url, key_order,  # noqa: E402,F401
                                  parse_ts, plain_text, value_at)

# The skill's output folder, which holds the report folders (see output_folder.py).
REPORTS_FOLDER = "jira-sprint-reports"

# Files inside a report folder. fetch_sprint.py creates the folder; each later
# step reads and writes here.
RAW_DIR = "_raw"
# The raw files inside RAW_DIR, as Jira returned them, and the fetch's own
# facts (META_FILE). Changelogs and comments hold one <KEY>.json per issue.
META_FILE = "_meta.json"
SPRINT_FILE = "sprint.json"
PREVIOUS_SPRINT_FILE = "previous_sprint.json"
SPRINT_ISSUES_FILE = "sprint_issues.json"
SPRINT_REPORT_FILE = "sprint_report.json"
PUNTED_ISSUES_FILE = "punted_issues.json"
STATUSES_FILE = "statuses.json"
PARENTS_FILE = "parents.json"
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


def spell_epic(spell):
    """(key, name) of a spell's epic, NO_EPIC and NO_EPIC_NAME without one."""
    return (spell["parentKey"], spell["parentSummary"]) if spell["parentKey"] else (NO_EPIC, NO_EPIC_NAME)


def epic_title(epic):
    """An epic's label in the report and the brief: "KEY: Name", or the bare
    name of the tickets without an epic."""
    return epic["name"] if epic["key"] == NO_EPIC else f"{epic['key']}: {epic['name']}"


def report_timezone(name):
    """The named timezone saved from the Jira API account's profile."""
    if not isinstance(name, str) or not name.strip():
        raise SystemExit(
            "no reporting timezone: check the Jira API account's timezone and fetch the sprint again")
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        raise SystemExit("reporting timezone is unavailable: check the Jira API account's timezone, "
                         "install timezone data with python3 -m pip install tzdata if needed, "
                         "and fetch the sprint again")


# Blocker candidates: flagged, in a blocked-type status, or high priority and
# still open. Teams mark impediments in different ways, often with a workflow
# status rather than Jira's Flagged field, so status names count too.
HIGH_PRIORITIES = {"highest", "high"}
BLOCKED_STATUSES = {"blocked", "impeded",
                    "on hold", "waiting", "waiting for support"}


def is_blocker_candidate(flagged, status, status_category, priority):
    """Whether a ticket's flag, status and priority make it a blocker candidate."""
    if flagged or (status or "").lower() in BLOCKED_STATUSES:
        return True
    return status_category != "done" and (priority or "").lower() in HIGH_PRIORITIES


def standard_issues(issues):
    """The issues that aren't sub-tasks: Jira's sprint report and board totals
    count only these, with sub-task work rolled into the parent."""
    return [i for i in issues if not nested(i.get("fields"), ["issuetype", "subtask"])]


def blocker_candidate_keys(issues, changes, categories, flagged_field, points_field, sprint_id, moment):
    """The keys of the standard issues in the sprint at `moment` that were
    flagged, blocked or high priority and not done then. One definition for
    the tickets whose comments are fetched and those data.json names, so the
    two are the same tickets."""
    keys = []
    for issue in standard_issues(issues):
        if not in_sprint_at(issue_moves(issue, changes[issue["key"]], sprint_id), moment):
            continue
        then = History(issue, changes[issue["key"]], categories,
                       flagged_field, points_field).state_at(moment)
        if is_blocker_candidate(then["flagged"], then["status"], then["statusCategory"], then["priority"]):
            keys.append(issue["key"])
    return keys


def history_fields(flagged_field, points_field):
    """The fields whose history the report reads, by the name changelogs/<KEY>.json
    stores their changes under, and how Jira's changelog names them. The story
    points and Flagged fields are the site's own custom fields."""
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
    """An issue's tracked fields used for figures and blocker classification,
    rebuilt at a past moment from current values and changelog changes.
    These fields use current values only when the changelog shows they held
    then too, so past sprint figures stay the same when the report is rerun."""

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

    def state_at(self, instant):
        """Tracked fields for figures and blocker classification at the instant."""
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
    """The set of IDs in a comma-separated changelog value."""
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


def run_script(script, *args, **kwargs):
    """Runs a script of this skill with the current Python and returns the
    finished process, its stdout captured as text; `kwargs` go to
    subprocess.run, such as stderr=subprocess.STDOUT to capture both."""
    return subprocess.run([sys.executable, os.path.join(os.path.dirname(os.path.realpath(__file__)), script),
                           *args], stdout=subprocess.PIPE, text=True, **kwargs)


def report_file(label):
    """The report's file name for a label."""
    return f"{label}_Sprint_Report.md"


def expected_files(label):
    """Every file a report folder holds, and nothing else: the fetched _raw
    folder, the three data files, the charts and the report."""
    return {RAW_DIR, DATA_FILE, CONTENT_FILE, BRIEF_FILE,
            *CHART_FILES.values(), report_file(label)}


def write_report_file(path, text):
    """Writes `text` to `path`, creating missing folders, through the shared
    writer, which exits, writing nothing, if `path` isn't inside the skill's
    output folder."""
    folder, _ = output_folder(REPORTS_FOLDER)
    relative = os.path.relpath(
        os.path.realpath(path), os.path.realpath(folder))
    write_output_file(REPORTS_FOLDER, relative, text.encode("utf-8"))


def write_json(path, payload):
    """Writes a value as indented JSON inside the skill's output folder."""
    write_report_file(path, json.dumps(payload, indent=2))


def report_label(project_key, sprint_name):
    """File-safe label such as PROJ_Sprint_3. The project key is prefixed
    because Jira sprint names ("Sprint 3") often don't carry it."""
    name = sprint_name or "Sprint"
    if project_key and not name.upper().startswith(project_key.upper()):
        name = f"{project_key} {name}"
    return re.sub(r"[^A-Za-z0-9.-]+", "_", name).strip("_")


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
#   Tickets     one as "KEY (N pts)", or "KEY (– pts)" with no estimate; several
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

# Where a sentence ends, for the commentary and the agent's one-sentence texts.
SENTENCE_BREAK = re.compile(r"(?<=[.!?]) +(?=[A-Z0-9])")


def number(value):
    """A number as text: a whole one without a decimal point, and a fraction
    rounded to two decimals, so a sum of fractional estimates never shows
    floating-point noise such as 0.30000000000000004."""
    if isinstance(value, float):
        value = round(value, 2)
        if value.is_integer():
            return str(int(value))
    return str(value)


def plural(count, one, many):
    """The word for `count` things: `one` for exactly 1, else `many`."""
    return one if count == 1 else many


def unit(count):
    """"ticket" or "tickets" for a count."""
    return plural(count, "ticket", "tickets")


def pts(points):
    """Story points: "3 pts", "1 pt", or "– pts" when there's no estimate."""
    if points is None:
        return "– pts"
    return f"{number(points)} {plural(points, 'pt', 'pts')}"


def known_sum(estimates):
    """The sum of the estimates that are set, or None if none is, so work with
    no estimate shows as "– pts", never "0 pts"."""
    known = [e for e in estimates if e is not None]
    return sum(known) if known else None


def qty(count, points):
    """An amount of work: "7 tickets (7 pts)"."""
    return f"{count} {unit(count)} ({pts(points)})"


def ratio(done, total, done_points, total_points):
    """Done out of total: "11/22 tickets (34/74 pts)"."""
    return f"{done}/{total} {unit(total)} ({number(done_points)}/{number(total_points)} pts)"


def ticket_ref(key, points):
    """One ticket: "PROJ-20 (2 pts)", or "PROJ-13 (– pts)" with no estimate."""
    return f"{key} ({pts(points)})"


def estimate(points):
    """An estimate for display: "–" when there is none."""
    return "–" if points is None else number(points)


def whole_percentage(part, whole):
    """A share as a whole percentage, "<1%" or ">99%" where rounding would
    show a share as none or all of the whole."""
    if not whole:
        return "n/a"
    share = part * 100 / whole
    rounded = f"{share:.0f}"
    if share > 0 and rounded == "0":
        return "<1%"
    if share < 100 and rounded == "100":
        return ">99%"
    return f"{rounded}%"


def display_date(iso_date):
    """An ISO date as the report shows it, DD/MM/YYYY."""
    return date.fromisoformat(iso_date).strftime(DISPLAY_DATE)


# The words the rules above ban, with what to write instead.
BANNED_WORDS = (("story or stories", r"\bstor(?:y|ies)\b"), ("issue or issues", r"\bissues?\b"),
                ("points (write pts)", r"\bpoints?\b"),
                ("spelled-out numbers (write digits)",
                 r"\b(?:one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|"
                 r"fifteen|sixteen|seventeen|eighteen|nineteen|twenty)\b"),
                ("closed (write completed, or at the close)", r"\bclosed\b"))


def banned_words(text):
    """[(rule, words found)] for each banned word the text uses."""
    found = []
    for rule, pattern in BANNED_WORDS:
        words = re.findall(pattern, text, re.I)
        if words:
            found.append((rule, words))
    return found


# The formats the rules above set for prose, each named as the final check
# reports it.
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


def text_rule_problems(text, latest=None):
    """[(rule, found)] for each rule of the report's vocabulary and formats
    that the text breaks: banned words first, as "no <rule>", then the formats.
    With `latest`, {key: latest estimate}, a ticket of the sprint must also
    read KEY (N pts) at that estimate, outside a bracketed list of keys. One function for the agent's text when
    it is written and the report's when it is checked, so the two can't
    differ."""
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


# The goal verdicts the agent chooses from, word for word. A running sprint
# can't be judged before its halfway day: too little is done to tell.
GOAL_VERDICTS = {"closed": ("Fully met", "Partially met", "Not met"),
                 "early": ("Too early to tell",),
                 "active": ("On track", "At risk"),
                 "no_goal": ("No goal set in Jira for this sprint",)}


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


# How each piece of work in the outcome charts ended, and their rows: the
# original commitment, split into carry-over and new work, and the extra scope.
OUTCOMES = ("completed", "not_completed", "removed")
OUTCOME_ROWS = ("original", "carried_in", "new", "extra")
# Each outcome's (background, text) colours, shared by the outcome charts and
# the timeline's tags, so an outcome looks the same wherever it shows.
OUTCOME_COLOURS = {"completed": ("#0ca30c", "#ffffff"), "not_completed": ("#fab219", "#1a1a1a"),
                   "removed": ("#b5b2aa", "#1a1a1a")}


# The groups of an epic's commentary, in the order it shows them (see
# build_sprint_data.py's scope_group).
SCOPE_GROUPS = ("completed", "in_review", "not_completed", "descoped")

# A description reaches the agent in pieces of at most this many characters, so
# the brief stays small and the rest is read only when it could matter.
DESCRIPTION_CHUNK_CHARS = 2000


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


# Word limits, so the report stays short enough for an exec to read: the
# timeline's commentary before its caveats, each epic's commentary, and the
# Key Achievements and Blockers & Risks paragraphs; and the most retro notes.
# Words are counted as the library's word_count counts them.
COMMENTARY_WORDS = 100
EPIC_COMMENTARY_WORDS = 60
SUMMARY_WORDS = 80
RETRO_NOTES = 5

# Marks the parts of the report the agent writes, on their heading or label;
# everything else is generated from data.json and checked.
AI_LABEL = "[AI Gen.]"


def ai(title):
    """A heading or label of an AI-written part. The label is a small superscript
    after the title it marks: a note for the reader, not part of the title. Its
    size is in rem, so it reads the same after a heading and in a table cell."""
    return f'{title} <sup style="font-size:0.6rem;font-weight:normal">{AI_LABEL}</sup>'


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


def outcome_total(breakdown, row):
    """All the work of an outcome_breakdown row, however it ended."""
    return sum(breakdown[f"{row}_{outcome}"] for outcome in OUTCOMES)
