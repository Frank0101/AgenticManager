"""
Fetch everything a sprint report needs from Jira into a new report folder.

Usage (exactly one sprint selector):
    python3 fetch_sprint.py --sprint-id 123
    python3 fetch_sprint.py --project PROJ            # most recently closed sprint
    python3 fetch_sprint.py --project PROJ --active   # the sprint in progress
    python3 fetch_sprint.py --board 42 [--active]
    python3 fetch_sprint.py --sprint-name "Sprint 3" --project PROJ   (or --board 42)

Report folders go in the skill's output folder: <output root>/jira-sprint-reports
if the config sets output.root, else <system temp>/agentic-manager/jira-sprint-reports
(see output_folder.py).

The report folder is <label>_<YY-MM-DD> in it, where label is the project key and
sprint name (e.g. PROJ_Sprint_3). Every run starts from scratch: once the sprint is
fetched, any earlier report folder there for the same sprint is deleted, then the
new one is written. There is no reuse mode.

Only active and closed sprints can be reported; a future sprint fails before
anything is deleted.

Prints one line of JSON on stdout:
    {"sprint_id": ..., "sprint_name": ..., "sprint_state": ..., "label": ..., "report_dir": ...,
     "temporary": ...}
"temporary" is true when output.root isn't set, so report folders go to the system
temp folder.
Progress goes to stderr.

Writes into <report_dir>/_raw:
    _meta.json             what was fetched, when, from where, and the field ids used
    sprint.json            the sprint
    previous_sprint.json   the closed sprint, of those the board lists, that started
                           last before this one, or null if there is none
    sprint_issues.json     issues currently in the sprint
    sprint_report.json     Jira's own sprint report
    punted_issues.json     issues removed from the sprint, same shape as sprint_issues
    statuses.json          every status of the site, with its category
    changelogs/<KEY>.json  every change, of every current and removed issue, to the
                           fields the report reads (sprint, status, resolution,
                           points, flag, priority, parent)
    parents.json           every epic the issues belong to, or belonged to before a
                           change of parent, with its description
    comments/<KEY>.json    comments of blocker candidates, up to the moment the
                           report describes

The report describes the sprint as it was when it closed, or, for an active
sprint, at the fetch: issues' fields are rebuilt from their changelogs, so a
later edit changes nothing. Descriptions are the exception: Jira keeps no
usable history of them, so they are as they read at the fetch. Nothing is
computed here beyond choosing which comments and epics to fetch;
build_sprint_data.py does the rest from these files.
"""
import argparse
import json
import os
import shutil
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from common import (RAW_DIR, REPORTS_FOLDER, History, JiraClient, as_of, history_fields, in_sprint_at,
                    is_blocker_candidate, issue_moves, nested, output_folder, parse_ts, report_label,
                    report_timezone, status_categories, write_json)

MAX_WORKERS = 8
# Issue fields the report needs, besides the site's Flagged and story points fields.
BASE_FIELDS = [
    "summary", "status", "issuetype", "assignee", "created", "resolution",
    "priority", "parent", "labels", "description",
]


def log(message):
    print(message, file=sys.stderr)


def stored_sprint_id(report_dir):
    """An earlier report's sprint id, or None if it can't be read."""
    try:
        with open(os.path.join(report_dir, RAW_DIR, "sprint.json"), encoding="utf-8") as f:
            return str(json.load(f).get("id"))
    except (OSError, ValueError, AttributeError):
        return None


def prepare_report_dir(out_root, report_dir, sprint_id, log):
    """Delete earlier reports of this sprint, and the destination itself, then
    return a new, empty _raw folder."""
    matches = {
        os.path.abspath(entry.path) for entry in os.scandir(out_root)
        if entry.is_dir(follow_symlinks=False) and stored_sprint_id(entry.path) == str(sprint_id)
    }
    if os.path.lexists(report_dir):
        other = stored_sprint_id(report_dir)
        if other is not None and other != str(sprint_id):
            raise SystemExit(
                f"refusing to delete {report_dir}: it holds the report of sprint {other}")
        matches.add(os.path.abspath(report_dir))
    for path in sorted(matches):
        log(f"deleting earlier report: {path}")
        if os.path.islink(path) or not os.path.isdir(path):
            os.unlink(path)
        else:
            shutil.rmtree(path)
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
        if (s.get("state") or "").lower() == "closed" and str(s["id"]) != str(sprint["id"])
        and s.get("startDate") and s.get("completeDate") and parse_ts(s["startDate"]) < parse_ts(start)
    ]
    return max(candidates, key=lambda s: parse_ts(s["startDate"]), default=None)


def project_key_of(args, issues):
    if args.project:
        return args.project
    return issues[0]["key"].rsplit("-", 1)[0] if issues else None


def parse_args():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--sprint-id", help="numeric Jira sprint id")
    parser.add_argument(
        "--sprint-name", help="exact sprint name; needs --project or --board")
    parser.add_argument("--project", help="project key, e.g. PROJ")
    parser.add_argument("--board", help="numeric board id")
    parser.add_argument("--active", action="store_true",
                        help="with --project or --board: the sprint in progress, not the last closed one")
    args = parser.parse_args()

    # Conflicting selectors fail rather than one silently winning.
    if args.sprint_name:
        if args.sprint_id:
            parser.error("--sprint-name can't be combined with --sprint-id")
        if bool(args.project) == bool(args.board):
            parser.error(
                "--sprint-name needs exactly one of --project or --board")
        if args.active:
            parser.error("--active can't be combined with --sprint-name")
    elif sum(v is not None for v in (args.sprint_id, args.project, args.board)) != 1:
        parser.error("pass exactly one of --sprint-id, --project or --board")
    if args.active and args.sprint_id:
        parser.error("--active applies only to --project or --board")
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

    previous = previous_sprint(sprint, client.sprints_for_board(board_id, state="closed"))
    log(f"previous sprint: {previous.get('name')} (id {previous['id']})" if previous
        else "no previous sprint on the board")

    flagged_field, points_field = client.flagged_and_points_fields(board_id)
    if not points_field:
        log("warning: no story points field found; points will read as 0")
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
    # moment the report describes; build_sprint_data.py computes the same list
    # from the same history.
    blocker_keys = []
    for issue in sprint_issues + punted_issues:
        if nested(issue.get("fields"), ["issuetype", "subtask"]):
            continue
        if not in_sprint_at(issue_moves(issue, changelogs[issue["key"]], sprint_id), moment):
            continue
        then = History(issue, changelogs[issue["key"]], categories,
                       flagged_field, points_field).state_at(moment)
        if is_blocker_candidate(then["flagged"], then["status"], then["statusCategory"],
                                then["priority"]):
            blocker_keys.append(issue["key"])
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        comments = dict(
            zip(blocker_keys, pool.map(client.comments, blocker_keys)))
    comments = {key: [c for c in values if not c.get("created") or parse_ts(c["created"]) <= moment]
                for key, values in comments.items()}

    project_key = project_key_of(args, sprint_issues + punted_issues)
    label = report_label(project_key, sprint.get("name"))
    out_root, temporary = output_folder(REPORTS_FOLDER)
    report_dir = os.path.join(
        out_root, f"{label}_{parse_ts(fetched_at).astimezone(reporting_zone).strftime('%y-%m-%d')}")
    raw_dir = prepare_report_dir(out_root, report_dir, sprint_id, log)

    write_json(os.path.join(raw_dir, "sprint.json"), sprint)
    write_json(os.path.join(raw_dir, "previous_sprint.json"), previous)
    write_json(os.path.join(raw_dir, "sprint_issues.json"), sprint_issues)
    write_json(os.path.join(raw_dir, "sprint_report.json"), report)
    write_json(os.path.join(raw_dir, "punted_issues.json"), punted_issues)
    write_json(os.path.join(raw_dir, "statuses.json"), statuses)
    write_json(os.path.join(raw_dir, "parents.json"), parents)
    for key, changes in changelogs.items():
        write_json(os.path.join(raw_dir, "changelogs", f"{key}.json"), changes)
    for key, values in comments.items():
        write_json(os.path.join(raw_dir, "comments", f"{key}.json"), values)
    write_json(os.path.join(raw_dir, "_meta.json"), {
        "fetched_at": fetched_at,
        "report_timezone": reporting_zone.key,
        "base_url": client.base_url,
        "fetched_by": me,
        "board_id": board_id,
        "project_key": project_key,
        "label": label,
        "flagged_field": flagged_field,
        "story_points_field": points_field,
        "blocker_candidate_keys": blocker_keys,
    })
    log(f"raw data written to {raw_dir}")
    print(json.dumps({"sprint_id": sprint["id"], "sprint_name": sprint.get("name"),
                      "sprint_state": state, "label": label, "report_dir": report_dir,
                      "temporary": temporary}))


if __name__ == "__main__":
    main()
