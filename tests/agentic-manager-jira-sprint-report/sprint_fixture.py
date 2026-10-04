# A made-up closed sprint for the sprint-report tests, as Jira's API returns it.
#
# Sprint 7 of project PROJ started on Wednesday 04/03/2026 at 12:00. Most of its
# backlog was loaded that morning, some the day before. Its issues cover each case
# the report has to tell apart:
#
#   PROJ-1   original, 3 pts, completed 06/03                         epic PROJ-100
#   PROJ-2   original (added 03/03), 5 pts, still In Progress         epic PROJ-100
#   PROJ-3   original, 2 pts, Done before it arrived, removed 05/03   epic PROJ-101
#   PROJ-4   original, 3 pts, open, removed 09/03 (descoped)          epic PROJ-101
#   PROJ-5   extra (added 04/03 after the start), 2 pts, completed 10/03, no epic
#   PROJ-6   original, 1 pt, left 05/03, back 06/03, closed as Duplicate 11/03
#   PROJ-7   extra, created in the running sprint 10/03, 1 pt, Blocked
#   PROJ-8   original, 2 pts, completed 05/03, removed 06/03
#   PROJ-9   a sub-task of PROJ-1, which the report leaves out
#   PROJ-10  original (added 03/03), 1 pt, Done 03/03 before the start   epic PROJ-100
#   PROJ-11  added and removed 03/03, before the start, so not reported
#
# Each issue's fields are as Jira returns them today, and its changelog holds
# how it got there: its moves in and out of the sprint and its status changes.
SPRINT_ID = 7
BOARD_ID = 42
POINTS_FIELD = "customfield_10016"
FLAGGED_FIELD = "customfield_10021"

SPRINT = {
    "id": SPRINT_ID, "self": "https://acme.test/rest/agile/1.0/sprint/7", "state": "closed",
    "name": "Sprint 7", "startDate": "2026-03-04T12:00:00.000Z", "endDate": "2026-03-13T17:00:00.000Z",
    "completeDate": "2026-03-13T16:00:00.000Z", "originBoardId": BOARD_ID,
    "goal": "Ship the import flow\n- Harden the export",
}


def ts(day, time="10:00"):
    return f"2026-03-{day:02d}T{time}:00.000+0000"


# The site's statuses: {name: (id, category)}.
STATUS = {
    "To Do": ("1", "new"), "In Progress": ("3", "indeterminate"), "Blocked": ("4", "indeterminate"),
    "Done": ("10", "done"), "Duplicate": ("11", "done"),
}
STATUSES = [{"id": i, "name": name, "statusCategory": {"key": category}}
            for name, (i, category) in STATUS.items()]


def status_field(name):
    return {"id": STATUS[name][0], "name": name, "statusCategory": {"key": STATUS[name][1]}}


def issue(key, points, status, created, resolution=None, parent=None, priority="Medium", subtask=False):
    fields = {
        "summary": f"Work item {key}",
        "status": status_field(status),
        "issuetype": {"name": "Sub-task" if subtask else "Story", "subtask": subtask},
        "assignee": {"displayName": "Alex Example"},
        "created": created,
        "resolution": {"name": resolution} if resolution else None,
        "priority": {"name": priority},
        "parent": ({"id": parent[2], "key": parent[0], "fields": {"summary": parent[1]}}
                   if parent else None),
        "labels": [],
        POINTS_FIELD: points,
        FLAGGED_FIELD: None,
    }
    return {"key": key, "fields": fields}


IMPORT = ("PROJ-100", "Import flow", "1100")
EXPORT = ("PROJ-101", "Export hardening", "1101")

CURRENT = [
    issue("PROJ-1", 3.0, "Done", ts(1), "Done", IMPORT),
    issue("PROJ-2", 5.0, "In Progress", ts(1), parent=IMPORT),
    issue("PROJ-5", 2.0, "Done", ts(1), "Done"),
    issue("PROJ-6", 1.0, "Duplicate", ts(1), "Done", IMPORT),
    issue("PROJ-7", 1.0, "Blocked", ts(10, "11:00"), parent=EXPORT),
    issue("PROJ-9", 1.0, "Done", ts(4), "Done", subtask=True),
    issue("PROJ-10", 1.0, "Done", ts(1), "Done", IMPORT),
]
REMOVED = [
    issue("PROJ-3", 2.0, "Done", ts(1), "Done", EXPORT),
    issue("PROJ-4", 3.0, "To Do", ts(1), parent=EXPORT),
    issue("PROJ-8", 2.0, "Done", ts(1), "Done", IMPORT),
    issue("PROJ-11", 2.0, "To Do", ts(1)),
]


def added(day, time="10:00", previous=""):
    return {"created": ts(day, time), "field": "sprint", "from": previous, "to": "7",
            "fromString": None, "toString": None}


def removed(day, time="10:00", to=""):
    return {"created": ts(day, time), "field": "sprint", "from": "7", "to": to,
            "fromString": None, "toString": None}


def moved(created, old, new):
    """A status change; `created` is a day of March 2026 or a full timestamp."""
    when = ts(*created) if isinstance(created, tuple) else created
    return {"created": when, "field": "status", "from": STATUS[old][0], "fromString": old,
            "to": STATUS[new][0], "toString": new}


def completed(created, status="Done"):
    return moved(created, "In Progress", status)


# The changes fetch_sprint.py stores per issue: its moves in and out of the
# sprint, and the status changes that took it from In Progress to where it is.
CHANGELOGS = {
    "PROJ-1": [added(4), completed((6,))],
    "PROJ-2": [added(3)],
    "PROJ-3": [completed("2026-02-27T10:00:00.000+0000"), added(4, "10:02", previous="6"), removed(5, to="8")],
    "PROJ-4": [added(4, "10:03"), removed(9, to="8")],
    "PROJ-5": [added(4, "15:00"), completed((10,))],
    "PROJ-6": [added(4, "10:04"), removed(5, "11:00"), added(6, "09:00"), completed((11,), "Duplicate")],
    "PROJ-7": [],
    "PROJ-8": [added(4, "10:05"), completed((5, "12:00")), removed(6, "16:00")],
    "PROJ-9": [added(4, "10:06"), completed((5,))],
    "PROJ-10": [added(3, "10:00"), completed((3, "15:00"))],
    "PROJ-11": [added(3, "09:00"), removed(3, "17:00")],
}


def entry(key):
    return {"key": key}


SPRINT_REPORT = {"contents": {
    "completedIssues": [entry(k) for k in ("PROJ-1", "PROJ-5", "PROJ-6", "PROJ-10")],
    "issuesNotCompletedInCurrentSprint": [entry(k) for k in ("PROJ-2", "PROJ-7")],
    "issuesCompletedInAnotherSprint": [],
    "puntedIssues": [entry(k) for k in ("PROJ-3", "PROJ-4", "PROJ-8", "PROJ-11")],
}}

COMMENTS = {"PROJ-7": [{"id": "1", "body": "Waiting on a dependency."}]}

# Judgment text the agent would write for this sprint.
CONTENT = {
    "goal_verdict": "Partially met",
    "epic_commentary": {
        "PROJ-100": "Import closed 4 of 5 original stories; PROJ-2 carried over.",
        "PROJ-101": "Export work was descoped or tidied out; PROJ-7 is blocked.",
        "__no_epic__": "PROJ-5 was added mid-sprint and delivered.",
    },
    "scope_notes": ["PROJ-5 was added to fix a regression found in testing."],
    "delivery_commentary": "Delivery concentrated on the import flow, while export work was mostly removed.",
    "key_achievements": ["The import flow shipped with PROJ-1."],
    "blockers_risks": ["PROJ-7 is blocked on an external dependency."],
    "retro_notes": ["Why was PROJ-4 descoped so late?"],
}


def raw_files():
    """{relative path: payload} of the _raw folder fetch_sprint.py writes."""
    files = {
        "_meta.json": {
            "fetched_at": "2026-03-16T09:00:00+00:00", "base_url": "https://acme.atlassian.net",
            "fetched_by": "Alex Example", "board_id": BOARD_ID, "project_key": "PROJ",
            "label": "PROJ_Sprint_7", "flagged_field": FLAGGED_FIELD, "story_points_field": POINTS_FIELD,
            "blocker_candidate_keys": ["PROJ-7"],
        },
        "sprint.json": SPRINT,
        "sprint_issues.json": CURRENT,
        "sprint_report.json": SPRINT_REPORT,
        "punted_issues.json": REMOVED,
        "statuses.json": STATUSES,
        "parents.json": [],
    }
    files.update({f"changelogs/{k}.json": v for k, v in CHANGELOGS.items()})
    files.update({f"comments/{k}.json": v for k, v in COMMENTS.items()})
    return files
