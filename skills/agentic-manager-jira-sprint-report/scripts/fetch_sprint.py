"""
Fetch everything a sprint report needs from Jira into a new report folder.

Usage (exactly one sprint selector):
    python3 fetch_sprint.py --sprint-id 123 [--board 42]   (the board whose sprint report is read)
    python3 fetch_sprint.py --project PROJ            # most recently closed sprint
    python3 fetch_sprint.py --project PROJ --active   # the sprint in progress
    python3 fetch_sprint.py --board 42 [--active]
    python3 fetch_sprint.py --sprint-name "Sprint 3" --project PROJ   (or --board 42)
    python3 fetch_sprint.py --sprint-name "PROJ Sprint 3"   (the first word is tried as the project key)

Prints one line of JSON on stdout (the sprint, its report folder and whether
that folder is temporary); progress goes to stderr. The raw data goes to
<report_dir>/_raw.

Every run starts from scratch: once the sprint is fetched, the report folder
of the same sprint and day is deleted, so there is no stale state to reuse.
Earlier days' folders are left, since their names can't clash with today's.
Only active and closed sprints can be reported; a future one fails before
anything is deleted.

The report is as at the close, or the fetch for an active sprint, so changelogs
are fetched, not current values (see build_sprint_data.py). Comments created or
edited after that moment are excluded because their earlier text isn't
fetched. Nothing is computed here beyond choosing what to fetch: the previous
sprint (for the carry-over), and which comments and epics; build_sprint_data.py
does the rest.
"""
import argparse
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from common import (CHANGELOGS_DIR, COMMENTS_DIR, META_FILE, PARENTS_FILE, PREVIOUS_SPRINT_FILE, PUNTED_ISSUES_FILE,
                    RAW_DIR, REPORTS_FOLDER, SPRINT_FILE, SPRINT_ISSUES_FILE, SPRINT_REPORT_FILE, STATUSES_FILE, JiraClient, as_of, blocker_candidate_keys, clear_folder, day_folder,
                    history_fields, nested, output_folder, parse_ts, report_label, report_timezone, status_categories, write_json)

MAX_WORKERS = 8
# Issue fields the report needs, besides the site's Flagged and story points fields.
BASE_FIELDS = [
    "summary", "status", "issuetype", "created", "resolution", "priority", "parent",
    "description",
]


def log(message):
    print(message, file=sys.stderr)


def stored_sprint_id(report_dir):
    """An earlier report's sprint id, or None if it can't be read."""
    try:
        with open(os.path.join(report_dir, RAW_DIR, SPRINT_FILE), encoding="utf-8") as f:
            return str(json.load(f).get("id"))
    except (OSError, ValueError, AttributeError):
        return None


def prepare_report_dir(report_dir, sprint_id, log):
    """Delete the report already in the destination folder (the same sprint and
    day), then return a new, empty _raw folder."""
    if os.path.lexists(report_dir):
        other = stored_sprint_id(report_dir)
        if other is not None and other != str(sprint_id):
            raise SystemExit(
                f"refusing to delete {report_dir}: it holds the report of sprint {other}")
        log(f"replacing the report of the same sprint and day: {report_dir}")
        clear_folder(report_dir)
    raw_dir = os.path.join(report_dir, RAW_DIR)
    os.makedirs(raw_dir)
    return raw_dir


def previous_sprint(sprint, board_sprints):
    """The closed sprint, of those the board lists, that started last before
    `sprint`, or None. Work still in it when it closed and in `sprint` at its
    start is carried over. The board's own sprints aren't told apart from
    others it lists: after a team moves to a new board, its earlier sprints
    keep the old board as their origin."""
    start = sprint.get("startDate")
    if not start:
        return None
    candidates = [
        s for s in board_sprints
        if (s.get("state") or "").lower() == "closed"
        and s.get("startDate") and s.get("completeDate") and parse_ts(s["startDate"]) < parse_ts(start)
    ]
    return max(candidates, key=lambda s: parse_ts(s["startDate"]), default=None)


def project_key_of(args, issues):
    if args.project:
        return args.project
    return issues[0]["key"].rsplit("-", 1)[0] if issues else None


def comments_as_of(comments, moment):
    """Keep comments whose creation and latest edit do not follow the cutoff.
    Without an updated timestamp, creation alone determines inclusion."""
    return [c for c in comments
            if all(not c.get(field) or parse_ts(c[field]) <= moment
                   for field in ("created", "updated"))]


def parse_args():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--sprint-id", help="numeric Jira sprint id")
    parser.add_argument(
        "--sprint-name", help="exact sprint name; with neither --project nor --board, "
        "its first word is tried as the project key")
    parser.add_argument("--project", help="project key, e.g. PROJ")
    parser.add_argument("--board", help="numeric board id; with --sprint-id, the board whose "
                        "sprint report is read")
    parser.add_argument("--active", action="store_true",
                        help="with --project or --board: the sprint in progress, not the last closed one")
    args = parser.parse_args()

    # Conflicting selectors fail rather than one silently winning.
    if args.sprint_name:
        if args.sprint_id:
            parser.error("--sprint-name can't be combined with --sprint-id")
        if args.project and args.board:
            parser.error(
                "--sprint-name takes at most one of --project or --board")
        if args.active:
            parser.error("--active can't be combined with --sprint-name")
    elif args.sprint_id:
        if args.project:
            parser.error("--sprint-id can't be combined with --project")
        if args.active:
            parser.error("--active can't be combined with --sprint-id")
    elif (args.project is None) == (args.board is None):
        parser.error("pass exactly one of --sprint-id, --project or --board")
    return args


def main():
    args = parse_args()
    client = JiraClient()
    profile = client.whoami()
    me = profile.get("displayName")
    reporting_zone = report_timezone(profile.get("timeZone"))
    log(f"authenticated as {me}")

    sprint = client.find_sprint(sprint_id=args.sprint_id, board_id=args.board, project=args.project,
                                name=args.sprint_name, active=args.active, log=log)
    state = (sprint.get("state") or "").lower()
    log(f"sprint: {sprint.get('name')} (id {sprint['id']}, {state})")
    if state not in {"active", "closed"}:
        raise SystemExit(
            f"sprint {sprint.get('name')!r} is {state!r}; only active or closed sprints can be reported")
    sprint_id = str(sprint["id"])

    # An explicit --board wins over the sprint's originBoardId: the origin board's
    # sprint report can come back empty while another board of the same project
    # serves the sprint correctly.
    board_id = args.board or sprint.get("originBoardId")
    if not board_id:
        raise SystemExit(
            "can't tell the sprint's board, which Jira's sprint report needs; pass --board")

    previous = previous_sprint(
        sprint, client.sprints_for_board(board_id, state="closed"))
    log(f"previous sprint: {previous.get('name')} (id {previous['id']})" if previous
        else "no previous sprint on the board")

    flagged_field, points_field = client.flagged_and_points_fields(board_id)
    if not points_field:
        log("warning: no story points field found; tickets will have no estimate (– pts)")
    fields = BASE_FIELDS + [f for f in (flagged_field, points_field) if f]

    sprint_issues = client.sprint_issues(sprint_id, fields)
    log(f"{len(sprint_issues)} issue(s) in the sprint")
    report = client.sprint_report(board_id, sprint_id)
    punted_keys = [i["key"] for i in report["contents"]["puntedIssues"]]
    log(f"{len(punted_keys)} issue(s) removed from the sprint")
    # Fetched again through the issue API so they have the same shape as
    # sprint_issues; the sprint report uses an internal one.
    punted_issues = client.issues_by_keys(punted_keys, fields)
    missing = set(punted_keys) - {i["key"] for i in punted_issues}
    if missing:
        raise SystemExit(
            f"removed issue(s) could not be fetched: {sorted(missing)}")

    fetched_at = datetime.now(timezone.utc).isoformat()
    moment = parse_ts(as_of(sprint, fetched_at))
    statuses = client.statuses()
    categories = status_categories(statuses)
    tracked = history_fields(flagged_field, points_field)
    all_keys = [i["key"] for i in sprint_issues + punted_issues]
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        changelogs = dict(zip(all_keys, pool.map(
            lambda key: client.field_changes(key, tracked), all_keys)))

    # Every epic: the issues' current parents, whose descriptions their own
    # fields don't carry, and those they belonged to before a change of
    # parent, which their fields no longer name.
    parent_ids = sorted({str(parent_id) for i in sprint_issues + punted_issues
                         if (parent_id := nested(i.get("fields"), ["parent", "id"]))}
                        | {str(c[side]) for changes in changelogs.values() for c in changes
                           if c["field"] == "parent" for side in ("from", "to") if c[side]})
    parents = client.issues_by_ids(parent_ids, ["summary", "description"])

    # Comments are fetched only for blocker candidates, as they were at the
    # moment the report describes.
    blocker_keys = blocker_candidate_keys(sprint_issues + punted_issues, changelogs, categories,
                                          flagged_field, points_field, sprint_id, moment)
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        comments = dict(
            zip(blocker_keys, pool.map(client.comments, blocker_keys)))
    comments = {key: comments_as_of(values, moment)
                for key, values in comments.items()}

    project_key = project_key_of(args, sprint_issues + punted_issues)
    label = report_label(project_key, sprint.get("name"))
    out_root, temporary = output_folder(REPORTS_FOLDER)
    report_dir = os.path.join(out_root, day_folder(
        label, parse_ts(fetched_at).astimezone(reporting_zone)))
    raw_dir = prepare_report_dir(report_dir, sprint_id, log)

    write_json(os.path.join(raw_dir, SPRINT_FILE), sprint)
    write_json(os.path.join(raw_dir, PREVIOUS_SPRINT_FILE), previous)
    write_json(os.path.join(raw_dir, SPRINT_ISSUES_FILE), sprint_issues)
    write_json(os.path.join(raw_dir, SPRINT_REPORT_FILE), report)
    write_json(os.path.join(raw_dir, PUNTED_ISSUES_FILE), punted_issues)
    write_json(os.path.join(raw_dir, STATUSES_FILE), statuses)
    write_json(os.path.join(raw_dir, PARENTS_FILE), parents)
    for key, changes in changelogs.items():
        write_json(os.path.join(
            raw_dir, CHANGELOGS_DIR, f"{key}.json"), changes)
    for key, values in comments.items():
        write_json(os.path.join(raw_dir, COMMENTS_DIR, f"{key}.json"), values)
    write_json(os.path.join(raw_dir, META_FILE), {
        "fetched_at": fetched_at,
        "report_timezone": reporting_zone.key,
        "base_url": client.base_url,
        "label": label,
        "flagged_field": flagged_field,
        "story_points_field": points_field,
    })
    log(f"raw data written to {raw_dir}")
    print(json.dumps({"sprint_id": sprint["id"], "sprint_name": sprint.get("name"),
                      "sprint_state": state, "label": label, "report_dir": report_dir,
                      "temporary": temporary}))


if __name__ == "__main__":
    main()
