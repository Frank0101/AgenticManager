"""Fetch everything a sprint report needs from Jira and GitHub into a new report
folder.

Nothing is computed here beyond choosing what to fetch: the previous sprint,
the epics, whose comments and where to look for pull requests. The raw files
keep what was fetched, today's values included, and build_sprint_data.py
rebuilds the sprint as at its end from them. Everything is fetched before the
report folder is touched, so a Jira or gh failure, which stops the fetch with
the library's failures.py, leaves the earlier report in place.
"""
import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone

from common import (CHANGELOGS_DIR, COMMENTS_DIR, META_FILE, PARENTS_FILE, PREVIOUS_SPRINT_FILE, PULL_REQUESTS_FILE,
                    PUNTED_ISSUES_FILE, RAW_DIR, REPORTS_FOLDER, SPRINT_FILE, SPRINT_ISSUES_FILE,
                    SPRINT_REPORT_FILE, STATUSES_FILE, GH_UNAVAILABLE, GITHUB_FAILED, JiraClient, as_of, blocker_candidate_keys,
                    clear_folder, day_folder, gather, gh_available, history_fields, nested, output_folder, parse_ts,
                    project_of, pulls_by_ticket, read_events, report_label, report_timezone,
                    standard_issues, status_categories, stops_on_failure, write_json)

# Issue fields the report needs, besides the site's Flagged and story points fields.
BASE_FIELDS = [
    "summary", "status", "issuetype", "created", "resolution", "priority", "parent",
    "description",
]
# What a GitHub failure's message starts with.
NO_REPORT = f"{GITHUB_FAILED}, so no report was written"
# How the sprint is named on the command line, shown in --help.
SELECTOR_EXAMPLES = """examples, with exactly one sprint selector:
  %(prog)s --sprint-id 123 [--board 42]
  %(prog)s --project PROJ               the last closed sprint
  %(prog)s --project PROJ --active      the sprint in progress
  %(prog)s --board 42 [--active]
  %(prog)s --sprint-name "Sprint 3" --project PROJ    (or --board 42)
  %(prog)s --sprint-name "PROJ Sprint 3"              its first word tried as the project key"""
# What this script prints, shown in --help.
PRINTS = """Prints one line of JSON on stdout: the sprint, its report folder and whether that
folder is temporary; progress goes to stderr. Only an active or closed sprint can
be reported."""


def prepare_report_dir(report_dir, sprint_id):
    """Delete the report already in the destination folder (the same sprint and
    day), then return a new, empty _raw folder. Every run starts from scratch,
    so there is no stale state to reuse; earlier days' folders are left, since
    their names can't clash with today's."""
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


def stored_sprint_id(report_dir):
    """An earlier report's sprint id, or None if it can't be read."""
    try:
        with open(os.path.join(report_dir, RAW_DIR, SPRINT_FILE), encoding="utf-8") as f:
            return str(json.load(f).get("id"))
    except (OSError, ValueError, AttributeError):
        return None


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


def read_changelogs(client, issues, fields):
    """{key: its changes} of each of `issues`, from which the sprint is
    rebuilt as at its end. One Jira now says it has none of, such as one
    deleted meanwhile, is Jira's answer, as the library's failures.py sets
    out: said on stderr, it gets [], so its current values stand for its
    history, as for a ticket never changed."""
    changelogs, gone = client.batched_field_changes(issues, fields)
    for why in gone.values():
        log(
            f"no changelog read, so its current values stand for its history: {why}")
    return {issue["key"]: changelogs.get(issue["key"], []) for issue in issues}


def project_key_of(args, issues):
    if args.project:
        return args.project
    return project_of(issues[0]["key"]) if issues else None


def pull_requests(client, issues, run=subprocess.run):
    """What pull_requests.json holds: {tickets: {key: the ticket's pull
    requests from the Development panels of it and its sub-tasks, each with
    `via`, the ticket it was found through}, events: {url: when GitHub says it was opened,
    merged and closed}, skipped: [{url, via: [the tickets it was found
    through], message}] of those GitHub says don't exist, left out of
    `tickets`}. Raises GhError when gh fails otherwise.

    Sub-tasks are left out of the report, but their pull requests are their
    ticket's, as a ticket removed from the sprint takes its sub-tasks with it.
    One GitHub says doesn't exist, such as one deleted that Jira still links,
    is skipped, as there is nothing to read and nothing to fix; any other
    failure stops the fetch, as a pull request it couldn't read would
    otherwise be taken for work without times."""
    found = pulls_by_ticket(client, issues)
    every = [pr for prs in found.values() for pr in prs]
    events, gone = read_events(every, run)
    skipped = [{"url": url, "via": list(dict.fromkeys(pr["via"] for pr in every if pr["url"] == url)),
                "message": message} for url, message in gone.items()]
    for skip in skipped:
        log(f"skipped a pull request GitHub says doesn't exist, found through {', '.join(skip['via'])}: "
            f"{skip['message']}")
    gone = {skip["url"] for skip in skipped}
    tickets = {key: [pr for pr in prs if pr["url"] not in gone]
               for key, prs in found.items()}
    return {"tickets": tickets, "events": events, "skipped": skipped}


def log(message):
    print(message, file=sys.stderr)


def parse_args():
    parser = selector_parser((__doc__ or "").split("\n\n")[0], PRINTS)
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


def selector_parser(description, prints):
    """The command line that names the sprint, whose --help shows
    `description`, the selectors with examples and `prints`, what the script
    prints."""
    parser = argparse.ArgumentParser(description=description, epilog=f"{SELECTOR_EXAMPLES}\n\n{prints}",
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--sprint-id", help="numeric Jira sprint id")
    parser.add_argument(
        "--sprint-name", help="exact sprint name; with neither --project nor --board, "
        "its first word is tried as the project key")
    parser.add_argument("--project", help="project key, e.g. PROJ")
    parser.add_argument("--board", help="numeric board id; with --sprint-id, the board whose "
                        "sprint report is read")
    parser.add_argument("--active", action="store_true",
                        help="with --project or --board: the sprint in progress, not the last closed one")
    return parser


def main():
    args = parse_args()
    # GitHub is required: without it every ticket would seem to have no pull
    # requests, and the report's status checks would pass by finding none.
    if not gh_available():
        raise SystemExit(f"{GH_UNAVAILABLE}, and the report needs GitHub: install gh and enable the "
                         "github-cli source, then run it again")
    with stops_on_failure(NO_REPORT):
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

        flagged_field, points_field = client.flagged_and_points_fields(
            board_id)
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
        # Read in batches: a request for many issues, not one each.
        changelogs = read_changelogs(client, sprint_issues + punted_issues,
                                     history_fields(flagged_field, points_field))

        # Every epic: the issues' current parents, whose descriptions their own
        # fields don't carry, and those they belonged to before a change of
        # parent, which their fields no longer name.
        parent_ids = sorted({str(parent_id) for i in sprint_issues + punted_issues
                             if (parent_id := nested(i.get("fields"), ["parent", "id"]))}
                            | {str(c[side]) for changes in changelogs.values() for c in changes
                               if c["field"] == "parent" for side in ("from", "to") if c[side]})
        parents = client.issues_by_ids(parent_ids, ["summary", "description"])

        # Comments are fetched only for the tickets that were blocker candidates
        # at the moment the report describes, worked out from the changelogs,
        # as no events exist yet.
        blocker_keys = blocker_candidate_keys(sprint_issues + punted_issues, changelogs, categories,
                                              flagged_field, sprint_id, moment)
        comments = dict(
            zip(blocker_keys, gather(blocker_keys, client.comments)))

        pulls = pull_requests(client, standard_issues(
            sprint_issues + punted_issues))
        log(f"{sum(map(len, pulls['tickets'].values()))} pull request(s) found")

        project_key = project_key_of(args, sprint_issues + punted_issues)
        label = report_label(project_key, sprint.get("name"))
        out_root, temporary = output_folder(REPORTS_FOLDER)
        report_dir = os.path.join(out_root, day_folder(
            label, parse_ts(fetched_at).astimezone(reporting_zone)))
        raw_dir = prepare_report_dir(report_dir, sprint_id)

        write_json(os.path.join(raw_dir, SPRINT_FILE), sprint)
        write_json(os.path.join(raw_dir, PREVIOUS_SPRINT_FILE), previous)
        write_json(os.path.join(raw_dir, SPRINT_ISSUES_FILE), sprint_issues)
        write_json(os.path.join(raw_dir, SPRINT_REPORT_FILE), report)
        write_json(os.path.join(raw_dir, PUNTED_ISSUES_FILE), punted_issues)
        write_json(os.path.join(raw_dir, STATUSES_FILE), statuses)
        write_json(os.path.join(raw_dir, PARENTS_FILE), parents)
        write_json(os.path.join(raw_dir, PULL_REQUESTS_FILE), pulls)
        for key, changes in changelogs.items():
            write_json(os.path.join(
                raw_dir, CHANGELOGS_DIR, f"{key}.json"), changes)
        for key, values in comments.items():
            write_json(os.path.join(
                raw_dir, COMMENTS_DIR, f"{key}.json"), values)
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
