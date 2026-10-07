"""A hand-written data.json and content.json for the make_report and check_report
unit tests: a closed sprint, 02/03/2026 to 13/03/2026, with these tickets and
events (see build_sprint_data.py for the model):

  PROJ-1  original, 2 pts, re-estimated to 3 on 03/03, completed 04/03   epic PROJ-100
  PROJ-2  original, 2 pts, carried over from Sprint 6, left 04/03
          (descoped); came back 05/03 as extra work, In Progress at the close
                                                                         epic PROJ-100
  PROJ-3  extra, 1 pt, joined 05/03, completed 06/03                     no epic
  PROJ-4  original, 1 pt, already Done at the start                      epic PROJ-100
  PROJ-5  original, 2 pts, closed as Duplicate 05/03                     epic PROJ-100
  PROJ-6  original, 2 pts, removed while open 04/03                      epic PROJ-100

The spells are written by hand; every figure built from them (breakdown,
epics, timeline, burndown) comes from build_sprint_data.py's own functions,
which check_report.py verifies independently.
"""
import copy
import os
import sys
from datetime import timezone

# tests/<skill>/ mirrors skills/<skill>/.
TEST_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(TEST_DIR))
sys.path.insert(0, os.path.join(REPO_ROOT, "skills",
                os.path.basename(TEST_DIR), "scripts"))
import build_sprint_data as build  # noqa: E402
from common import NO_EPIC  # noqa: E402

BASE = "https://acme.test"
START = "2026-03-02T09:00:00.000+0000"


def ev(day, kind, points, done=False, **extra):
    at = START if day == 2 and kind == "committed" else f"2026-03-{day:02d}T10:00:00.000+0000"
    return {"at": at, "date": f"2026-03-{day:02d}", "type": kind, "points": points, "done": done, **extra}


def ticket(key, events, outcome, status="Done", scope="original", carried=False, parent="PROJ-100",
           marker=None, priority="Medium"):
    return {"key": key, "summary": f"Work item {key}", "description": f"What {key} changes.", "status": status,
            "statusCategory": "done" if outcome == "completed" else "indeterminate",
            "resolution": "Done" if outcome == "completed" else None, "flagged": False, "priority": priority,
            "parentKey": parent, "parentSummary": "Login <beta>" if parent else None,
            "scope": scope, "carriedIn": carried, "events": events, "outcome": outcome,
            "points": events[-1]["points"], "closedAsNonDelivery": marker,
            "counted": not (scope == "extra" and outcome == "removed")}


TICKETS = [
    ticket("PROJ-1", [ev(2, "committed", 2), ev(3, "reestimated", 3, fromPoints=2),
                      ev(4, "completed", 3, done=True)], "completed"),
    ticket("PROJ-2", [ev(2, "committed", 2), ev(4, "removed", 2)], "removed", status="In Progress",
           carried=True, priority="High"),
    ticket("PROJ-2", [ev(5, "joined", 2)], "not_completed", status="In Progress", scope="extra", priority="High"),
    ticket("PROJ-3", [ev(5, "joined", 1), ev(6, "completed", 1, done=True)], "completed", scope="extra",
           parent=None),
    ticket("PROJ-4", [ev(2, "committed", 1, done=True)], "completed"),
    ticket("PROJ-5", [ev(2, "committed", 2), ev(5, "completed", 2, done=True)], "completed", status="Duplicate",
           marker="duplicate"),
    ticket("PROJ-6", [ev(2, "committed", 2), ev(4, "removed", 2)], "removed", status="To Do"),
]


def sprint_data(**changes):
    data = {
        "report_timezone": "Europe/London", "base_url": BASE, "label": "PROJ_Sprint_7", "sprint_name": "Sprint 7",
        "sprint_status": "closed", "sprint_goal": "Ship login", "sprint_start": "2026-03-02",
        "sprint_end": "2026-03-13", "sprint_complete_date": "2026-03-13", "today": "2026-03-16",
        "as_of_instant": "2026-03-13T17:00:00.000+0000",
        "previous_sprint": {"id": 6, "name": "Sprint 6", "complete_instant": "2026-03-02T08:00:00.000Z",
                            "complete_date": "2026-03-02"},
        "spells": copy.deepcopy(TICKETS),
        "not_counted": [],
        "membership_cross_check_excluded_keys": [],
        "blocker_candidate_keys": ["PROJ-2"],
    }
    data.update(changes)
    tickets = data["spells"]
    counts, points = build.outcome_breakdown(tickets)
    non_delivery = [t for t in tickets if t["closedAsNonDelivery"]]
    original = [t for t in tickets if t["scope"] == "original"]
    data.update({
        "outcome_breakdown_counts": counts, "outcome_breakdown_points": points,
        "non_delivery_closures": {"count": len(non_delivery), "points": sum(t["points"] or 0 for t in non_delivery),
                                  "issues": [{"key": t["key"], "marker": t["closedAsNonDelivery"]}
                                             for t in non_delivery]},
        "points_estimated_issue_count": sum(1 for t in tickets if t["points"] is not None),
        "points_total_issue_count": len(tickets),
        "epics": build.build_epics(tickets, {"PROJ-100": "Staff sign in with their work account."}),
        "timeline": build.build_timeline(tickets, data["sprint_status"], data["sprint_start"], data["sprint_end"],
                                         data["sprint_complete_date"], data["today"]),
        "burndown_baseline": sum(t["events"][0]["points"] or 0 for t in original),
        "burndown": build.build_burndown(tickets, data["sprint_start"], data["sprint_end"], data["as_of_instant"],
                                         timezone.utc),
    })
    return data


CONTENT = {
    "goal_verdict": "Partially met",
    "epic_commentary": {
        "PROJ-100": {"completed": "Staff can sign in with a password.",
                     "not_completed": "Remembering the last sign-in method is still in progress.",
                     "descoped": "Sign-in audit logging & the admin screen were dropped."},
        NO_EPIC: {"completed": "The export now handles empty files."},
    },
    "key_achievements": "Login shipped: staff can sign in with a password, and the export handles empty files.",
    "blockers_risks": "Nothing from the commitment was left open; the only open ticket is extra work.",
    "retro_notes": ["PROJ-1 (3 pts) grew during the sprint: was it refined enough?",
                    "PROJ-2 (2 pts) left the sprint and came back: should it have stayed out?"],
}
