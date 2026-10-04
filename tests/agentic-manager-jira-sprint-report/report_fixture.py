"""A hand-written data.json and content.json for the make_report and check_report
unit tests: a closed sprint, 02/03/2026 to 13/03/2026.

  PROJ-1  original, 3 pts, delivered 04/03                 epic PROJ-100
  PROJ-2  original, 2 pts, In Progress, carried over       epic PROJ-100
  PROJ-3  extra,    1 pt,  added 05/03, delivered 06/03    no epic
  PROJ-4  original, 1 pt,  already Done at the start       epic PROJ-100
  PROJ-5  original, 2 pts, closed as Duplicate 05/03       epic PROJ-100
  PROJ-6  original, 2 pts, descoped while open 04/03       epic PROJ-100
"""
import os
import sys

# tests/<skill>/ mirrors skills/<skill>/.
TEST_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(TEST_DIR))
sys.path.insert(0, os.path.join(REPO_ROOT, "skills",
                os.path.basename(TEST_DIR), "scripts"))
from common import NO_EPIC  # noqa: E402

BASE = "https://acme.test"


def issue(key, points, extra=False, carried=False, already=False, status="Done"):
    return {"key": key, "storyPoints": points, "addedMidSprint": extra, "carriedOver": carried,
            "startState": {"storyPoints": points, "done": already},
            "alreadyDoneOnArrival": already, "status": status}


def row(day, labels=(), **keys):
    """A timeline row: every *_keys field empty and every *_points field 0
    unless given."""
    entry = {"date": day, "labels": list(labels)}
    for field in ("added", "readded", "departure", "completed_original", "completed_extra",
                  "already_done_original", "already_done_extra"):
        entry[f"{field}_keys"] = keys.get(field, [])
        entry[f"{field}_points"] = keys.get(f"{field}_points", 0)
    entry["removed_done_keys"] = keys.get("removed_done", [])
    return entry


def totals(count, points):
    return {"count": count, "points": points}


def sprint_data(**changes):
    data = {
        "base_url": BASE, "label": "PROJ_Sprint_7", "sprint_name": "Sprint 7", "sprint_status": "closed",
        "sprint_goal": "Ship login", "sprint_start": "2026-03-02", "sprint_end": "2026-03-13",
        "sprint_complete_date": "2026-03-13", "today": "2026-03-16",
        "issues": [issue("PROJ-1", 3), issue("PROJ-2", 2, carried=True, status="In Progress"),
                   issue("PROJ-3", 1, extra=True), issue("PROJ-4", 1, already=True), issue("PROJ-5", 2)],
        "removed_issues": [issue("PROJ-6", 2, status="To Do")],
        "scope_timeline": [
            row("2026-03-02", ["sprint_start"], added=["PROJ-1", "PROJ-2", "PROJ-4", "PROJ-5", "PROJ-6"], added_points=10,
                already_done_original=["PROJ-4"], already_done_original_points=1),
            row("2026-03-04", departure=["PROJ-6"], departure_points=2,
                completed_original=["PROJ-1"], completed_original_points=3),
            row("2026-03-05", added=["PROJ-3"], added_points=1,
                completed_original=["PROJ-5"], completed_original_points=2),
            row("2026-03-06",
                completed_extra=["PROJ-3"], completed_extra_points=1),
            row("2026-03-13", ["sprint_closed"]),
        ],
        "commitment_breakdown_counts": {"original_completed": 3, "original_not_completed": 1,
                                        "extra_completed": 1, "extra_not_completed": 0},
        "commitment_breakdown_points": {"original_completed": 6, "original_not_completed": 2,
                                        "extra_completed": 1, "extra_not_completed": 0},
        "outcome_counts": {"completed": 4, "carried_over": 1},
        "outcome_points": {"completed": 7, "carried_over": 2},
        "points_total_issue_count": 5,
        "removed_summary": {"descoped_incomplete": totals(1, 2), "already_done_on_arrival": totals(0, 0),
                            "completed_before_removal": totals(0, 0), "total": totals(1, 2)},
        "already_done_on_arrival": {**totals(1, 1), "issues": [{"key": "PROJ-4", "storyPoints": 1, "stillInSprint": True}]},
        "non_delivery_closures": {**totals(1, 2), "issues": [{"key": "PROJ-5", "marker": "duplicate"}]},
        "blocker_candidate_keys": ["PROJ-2", "PROJ-3"],
        "epics": [
            {"key": "PROJ-100", "name": "Login <beta>", "original_stories_done": 3, "original_stories_total": 5,
             "original_points_done": 6, "original_points_total": 10, "extra_stories_done": 0,
             "extra_stories_total": 0, "extra_points_done": 0, "extra_points_total": 0},
            {"key": NO_EPIC, "name": "(no epic)", "original_stories_done": 0, "original_stories_total": 0,
             "original_points_done": 0, "original_points_total": 0, "extra_stories_done": 1,
             "extra_stories_total": 1, "extra_points_done": 1.0, "extra_points_total": 1.0},
        ],
    }
    data.update(changes)
    return data


CONTENT = {
    "goal_verdict": "Partially met",
    "epic_commentary": {"PROJ-100": "Most of PROJ-100 shipped.", NO_EPIC: "One small extra."},
    "scope_notes": ["PROJ-3 was added for the demo."],
    "delivery_commentary": "Delivery centred on PROJ-100.",
    "key_achievements": ["Login shipped (PROJ-1)."],
    "blockers_risks": ["PROJ-2 waited on review."],
    "retro_notes": [],
}
