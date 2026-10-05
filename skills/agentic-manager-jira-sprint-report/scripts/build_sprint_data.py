"""
Build <report_dir>/data.json from the _raw files fetch_sprint.py wrote.
Reads no network: the same raw files always give the same output,
so a report's numbers can be audited against the payloads they came from.

Usage:
    python3 build_sprint_data.py --report-dir <report_dir>

The report date comes from the saved fetch timestamp in the reporting timezone,
so the calculation is explicit and testable without reading the clock.

What it computes:

  * Outcome of the issues in the sprint: `completed` and `carried_over`, by
    count and points, as Jira's sprint report counts them. Completed means in
    Jira's Done status category when the sprint closed (or, for an active one,
    at the fetch), including duplicates and Won't Do (also listed in
    `non_delivery_closures`, as an annotation, never a subtraction). Work
    finished after the close is carried over.
  * Original commitment vs scope added later (see below).
  * Removed issues, split into open descopes, issues already Done when they
    entered the sprint and were tidied out (only a removal, never a
    completion), and work completed in this sprint before removal.
  * Per-epic totals, including epics whose only issues were removed, and a
    "(no epic)" row for issues without a parent.
  * A day-by-day scope timeline with every cross-day departure and return.
    Its quantities use each issue's estimate at the moment the report
    describes (or at its removal). An issue that leaves and returns on the
    same day is omitted: the moves cancel before the end of the day.
  * A cross-check of the in-scope, completed and removed sets against Jira's
    own sprint report. If it can't run or finds a discrepancy, the script
    exits non-zero without writing data.json.
  * Daily burndown readings rebuilt from each day's status, estimates and
    membership. Days end at local 23:59:59.999999, except that the closing
    day stops at the exact close and the current day at the fetch instant.
    The opening baseline uses status and estimates at the sprint start.

Original commitment is what was in the sprint at the sprint's start (its
startDate, as Jira records it now, even if someone edited it), whenever it was
added. Anything that joined after that instant is extra, even on the same day.
A later return never changes this: original work stays original even if it
leaves and returns. Issues that joined and left before the start were never
part of the sprint and are left out.

An issue whose Sprint-field changes for this sprint don't start with an add
(none at all, or a removal first) got the sprint when it was created: Jira
logs no change for a field's initial value. Its `created` time is when it
joined.

Every field that describes an issue's progress (status, its category,
resolution, story points, flag, priority and epic) is as it was at the time,
rebuilt from the issue's changelog, never as it is today: an issue in the
sprint as at the moment the report describes (the close, or the fetch for an
active sprint), a removed issue as at its last removal before that moment.
Sprint moves after that moment are ignored. Run on the same sprint at any
later date, the report gives the same figures.

An issue in Jira's Done category when it entered the sprint (at the start for
original work, when it joined for extra work), and not reopened through that
moment, gets `alreadyDoneOnArrival`: it was never outstanding work here, so
it isn't delivery. If it stays in the sprint, its completion is credited to
the day it entered (`effectiveCompletionDate`), as Jira's sprint report
counts it as completed; if it is removed, it is only a removal.

An original issue that was Done at the start and is reopened while it is in
the sprint (by the moment the report describes) was never outstanding work at
the start, so it isn't initial commitment: it counts as extra scope
(`addedMidSprint`) from the moment it was reopened. It is then delivery if it
is Done again, carried over if not, and a removal if it leaves the sprint.

`startState` holds an issue's story points and whether it was Done at the
sprint's start, even if it was re-estimated later. The burndown's baseline and
the planning baseline are built from it.

Sprint moves after the moment the report describes can't be checked against
Jira's sprint report, which shows today's membership. The issues they concern
are left out of that comparison and listed in
`membership_cross_check_excluded_keys`.
"""
import argparse
import os
from datetime import datetime, time, timedelta, timezone

from common import (DATA_FILE, NO_EPIC, RAW_DIR, History, add_and_remove_events, as_of, in_sprint_at, is_blocker_candidate,
                    issue_moves, key_order, load_json, nested, parse_ts, sprint_moves, status_categories, report_timezone,
                    write_json)

# Terms meaning an issue was closed without delivering it (duplicate, won't do,
# cancelled...), matched against both the status and the resolution: a
# "Duplicate" status can carry the default "Done" resolution.
NON_DELIVERY_MARKERS = {
    "won't do", "wont do", "won’t do",
    "won't fix", "wont fix", "won’t fix",
    "cancelled", "canceled", "duplicate", "obsolete", "rejected", "declined",
}


def load_optional(path, default):
    return load_json(path) if os.path.exists(path) else default


def sprint_date(ts, offset, end_of_period=False):
    """Calendar date of a timestamp in the reporting timezone, including its
    daylight-saving rules.

    With `end_of_period`, a boundary exactly on midnight names the last day
    worked rather than the next day: an end of 00:00 on the 8th means the sprint
    ran through the 7th."""
    if not ts:
        return None
    moment = parse_ts(ts).astimezone(offset)
    if end_of_period and moment.time() == time.min:
        moment -= timedelta(seconds=1)
    return moment.date().isoformat()


class Context:
    """What every issue is built with: the sprint, the site's fields and
    statuses, and the epics' names."""

    def __init__(self, sprint_id, start_ts, start_date, categories, fields, epic_names, reporting_zone=timezone.utc):
        self.sprint_id, self.start_ts, self.start_date = sprint_id, start_ts, start_date
        self.reporting_zone = reporting_zone
        self.categories = categories
        self.flagged_field, self.points_field = fields
        # {epic id: (key, summary)}
        self.epic_names = epic_names


def epic_names(raw_issues, parents):
    """{epic id: (key, summary)} from the issues' current parents and the
    epics fetched because an issue belonged to them before."""
    names = {}
    for raw in raw_issues:
        parent = nested(raw.get("fields"), ["parent"])
        if parent and parent.get("id"):
            names[str(parent["id"])] = (parent.get("key"),
                                        nested(parent, ["fields", "summary"]))
    for parent in parents:
        names[str(parent["id"])] = (parent.get("key"),
                                    nested(parent, ["fields", "summary"]))
    return names


def membership(added, removed, created, start, until=None):
    """How an issue relates to the sprint window, from its Sprint-field changes.

    Returns None if it was never in the sprint after the start. Otherwise
    (entered, extra, returns, departures): when it entered the sprint for this
    report (the start itself for original work), whether it is extra, and the
    returns and departures after it entered, through `until` when supplied."""
    moves = sprint_moves(added, removed, created)
    if until is not None:
        moves = [move for move in moves if move[0] <= until]
    at_start = False
    for when, move, _ in moves:
        if when <= start:
            at_start = move > 0
    window = [(move, ts) for when, move, ts in moves if when > start]
    if not at_start:
        adds = [ts for move, ts in window if move > 0]
        if not adds:
            return None
        window = window[window.index((1, adds[0])) + 1:]
        entered = adds[0]
    else:
        entered = None
    returns = [ts for move, ts in window if move > 0]
    departures = [ts for move, ts in window if move < 0]
    return entered, not at_start, returns, departures


def non_delivery_marker(status, resolution):
    for value in ((status or "").lower(), (resolution or "").lower()):
        if value in NON_DELIVERY_MARKERS:
            return value
    return None


def load_changelogs(changelog_dir, raw_issues):
    """{key: the changes fetch_sprint.py stored for it}."""
    changes, missing = {}, []
    for raw in raw_issues:
        path = os.path.join(changelog_dir, f"{raw['key']}.json")
        if os.path.exists(path):
            changes[raw["key"]] = load_json(path)
        else:
            missing.append(raw["key"])
    if missing:
        raise SystemExit("missing changelogs for " + ", ".join(sorted(missing)) +
                         "; fetch the sprint again rather than guessing when they joined")
    return changes


def build_issue(raw, changes, context, until=None):
    """One issue's facts as they were at `until` (the moment the report
    describes; for a removed issue, None, meaning when it last left), or None
    if it was never in the sprint after the start."""
    added, removed = add_and_remove_events(changes, context.sprint_id)
    until = until or removed[-1]
    cutoff = parse_ts(until)
    fields = raw.get("fields") or {}
    facts = membership(added, removed, fields.get(
        "created"), parse_ts(context.start_ts), cutoff)
    if facts is None:
        return None
    entered, extra, returns, departures = facts
    history = History(raw, changes, context.categories,
                      context.flagged_field, context.points_field)
    start = parse_ts(context.start_ts)
    start_state = history.state_at(start)
    if not extra and start_state["statusCategory"] == "done":
        # Done at the start, so not outstanding work: if it is reopened while
        # in the sprint, it counts as scope added then.
        reopened = history.reopened_at(start, cutoff)
        if reopened and in_sprint_at(issue_moves(raw, changes, context.sprint_id), parse_ts(reopened)):
            entered, extra = reopened, True
            returns = [ts for ts in returns if parse_ts(
                ts) > parse_ts(reopened)]
            departures = [ts for ts in departures if parse_ts(
                ts) > parse_ts(reopened)]
    entered_ts = entered or context.start_ts
    entered_on = sprint_date(
        entered, context.reporting_zone) if extra else context.start_date
    state = history.state_at(cutoff)
    parent_id = state.pop("parentId")
    parent_key, parent_summary = (context.epic_names.get(parent_id, (state["parentKey"], state["parentKey"]))
                                  if parent_id else (None, None))
    completed = history.completed_at(cutoff)
    # Keep the baseline independent of later reopening and re-estimation.
    baseline = {"storyPoints": start_state["storyPoints"],
                "done": start_state["statusCategory"] == "done"}
    # Done when it entered and not reopened since: never outstanding work here.
    already = bool(completed) and parse_ts(completed) <= parse_ts(entered_ts)
    return {
        "key": raw["key"],
        "summary": fields.get("summary"),
        "type": nested(fields, ["issuetype", "name"]),
        "assignee": nested(fields, ["assignee", "displayName"]),
        "created": fields.get("created"),
        "labels": fields.get("labels") or [],
        **state,
        "parentKey": parent_key,
        "parentSummary": parent_summary,
        # The moment the fields above describe.
        "stateAt": until,
        "startState": baseline,
        # When it last moved into the Done category, if it was Done then.
        "completedAt": completed,
        "addedMidSprint": extra,
        # When it entered the sprint for this report: the start for original
        # work, the moment it joined for extra work.
        "enteredSprintAt": entered_ts,
        "enteredSprintOn": entered_on,
        # Returns and departures after it entered, for the timeline, and
        # whether it was Done at each departure.
        "returnEvents": returns,
        "departureEvents": departures,
        "doneAtDepartures": [history.done_at(parse_ts(ts)) for ts in departures],
        # Sprint-field changes up to the issue snapshot, for audit.
        "sprintAddEvents": [ts for ts in added if parse_ts(ts) <= cutoff],
        "sprintRemoveEvents": [ts for ts in removed if parse_ts(ts) <= cutoff],
        "alreadyDoneOnArrival": already,
        "effectiveCompletionDate": entered_on if already else sprint_date(completed, context.reporting_zone),
    }


def build_current_issues(raw_issues, changes, context, moment):
    """moment is the instant the report describes: when a closed sprint
    closed, or the fetch for an active one."""
    issues = []
    for raw in raw_issues:
        issue = build_issue(raw, changes[raw["key"]], context, moment)
        if issue is None:
            raise SystemExit(f"{raw['key']} is in the sprint but its changelog says it isn't; "
                             "fetch the sprint again")
        issue["carriedOver"] = issue["statusCategory"] != "done"
        issue["closedAsNonDelivery"] = (None if issue["carriedOver"]
                                        else non_delivery_marker(issue["status"], issue["resolution"]))
        issues.append(issue)
    return issues


def build_removed_issues(raw_issues, changes, context, moment=None):
    """(removed issues, keys left out because they left before the start)."""
    removed_issues, before_start = [], []
    for raw in raw_issues:
        removals = add_and_remove_events(
            changes[raw["key"]], context.sprint_id)[1]
        if moment is not None:
            removals = [ts for ts in removals if parse_ts(
                ts) <= parse_ts(moment)]
        if not removals:
            raise SystemExit(f"{raw['key']} is in Jira's removed list but its changelog has no removal "
                             f"from sprint {context.sprint_id}; inspect it before reporting")
        issue = build_issue(raw, changes[raw["key"]], context, removals[-1])
        if issue is None:
            before_start.append(raw["key"])
            continue
        issue["removedFromSprintAt"] = issue["sprintRemoveEvents"][-1]
        issue["wasDoneAtRemoval"] = issue["statusCategory"] == "done"
        removed_issues.append(issue)
    return removed_issues, before_start


def scope_at(raw_issues, changes, context, moment):
    """Partition fetched issues by membership at the report cutoff. Later
    moves cannot turn historical scope into a removal, or the reverse."""
    current, removed = [], []
    for raw in raw_issues:
        moves = issue_moves(raw, changes[raw["key"]], context.sprint_id)
        if in_sprint_at(moves, parse_ts(moment)):
            current.append(raw)
        elif any(move < 0 and when <= parse_ts(moment) for when, move, _ in moves):
            removed.append(raw)
    return current, removed


def build_burndown(raw_issues, changes, context, issues, offset, moment, last_date):
    """Remaining work at the end of each local day from the sprint's start to
    `last_date`, never later than the moment the report describes."""
    index = {i["key"]: i for i in issues}
    histories = {}
    moves = {}
    for raw in raw_issues:
        key = raw["key"]
        if key not in index:
            continue
        histories[key] = History(raw, changes[key], context.categories,
                                 context.flagged_field, context.points_field)
        moves[key] = issue_moves(raw, changes[key], context.sprint_id)
    rows = []
    day = datetime.strptime(context.start_date, "%Y-%m-%d").date()
    end = datetime.strptime(last_date, "%Y-%m-%d").date()
    while day <= end:
        cutoff = min(datetime.combine(
            day, time.max, tzinfo=offset), parse_ts(moment))
        committed, total = 0, 0
        for key, history in histories.items():
            if not in_sprint_at(moves[key], cutoff):
                continue
            state = history.state_at(cutoff)
            if state["statusCategory"] != "done":
                points = state["storyPoints"] or 0
                total += points
                if not index[key]["addedMidSprint"]:
                    committed += points
        rows.append({"date": day.isoformat(),
                    "committed": committed, "total": total})
        day += timedelta(days=1)
    return rows


def totals(items):
    return {"count": len(items), "points": sum(i["storyPoints"] or 0 for i in items)}


def bucketed(items, bucket_of, keys):
    counts = {k: 0 for k in keys}
    points = {k: 0 for k in keys}
    for item in items:
        bucket = bucket_of(item)
        counts[bucket] += 1
        points[bucket] += item["storyPoints"] or 0
    return counts, points


def build_epics(current, removed):
    epics = {}

    def epic_for(issue):
        key, name = (issue["parentKey"], issue["parentSummary"]) if issue["parentKey"] \
            else (NO_EPIC, "(no epic)")
        if key not in epics:
            epics[key] = {
                "key": key, "name": name,
                "original_stories_done": 0, "original_stories_total": 0,
                "original_points_done": 0, "original_points_total": 0,
                "extra_stories_done": 0, "extra_stories_total": 0,
                "extra_points_done": 0, "extra_points_total": 0,
                "removed_stories": 0, "removed_points": 0,
                # Removed issues that were Done before removal, whether already
                # Done when they entered the sprint or completed in it.
                "removed_done_stories": 0, "removed_done_points": 0,
            }
        return epics[key]

    def count(epic, issue, done):
        origin = "extra" if issue["addedMidSprint"] else "original"
        points = issue["storyPoints"] or 0
        epic[f"{origin}_stories_total"] += 1
        epic[f"{origin}_points_total"] += points
        if done:
            epic[f"{origin}_stories_done"] += 1
            epic[f"{origin}_points_done"] += points

    for issue in current:
        count(epic_for(issue), issue, not issue["carriedOver"])
    for issue in removed:
        epic = epic_for(issue)
        points = issue["storyPoints"] or 0
        epic["removed_stories"] += 1
        epic["removed_points"] += points
        if issue["wasDoneAtRemoval"]:
            epic["removed_done_stories"] += 1
            epic["removed_done_points"] += points
        # Removed work that wasn't already Done when it entered stays in the
        # delivery denominator: done if completed before removal, otherwise a
        # descope that counts as not done.
        if not issue["alreadyDoneOnArrival"]:
            count(epic, issue, issue["wasDoneAtRemoval"])

    return sorted(epics.values(),
                  key=lambda e: (-(e["original_points_total"] + e["extra_points_total"]), key_order(e["key"])))


def build_scope_timeline(current, removed, status, start, complete, end, today, reporting_zone=timezone.utc):
    rows = {}

    def row(day):
        if day is None:
            return None
        if day not in rows:
            rows[day] = {
                "date": day, "labels": [],
                "added_keys": [], "added_points": 0,
                "readded_keys": [], "readded_points": 0,
                # Every cross-day departure, for the table's Removed column.
                "departure_keys": [], "departure_points": 0,
                "removed_done_keys": [],
                "completed_original_keys": [], "completed_original_points": 0,
                "completed_extra_keys": [], "completed_extra_points": 0,
                "already_done_original_keys": [], "already_done_original_points": 0,
                "already_done_extra_keys": [], "already_done_extra_points": 0,
            }
        return rows[day]

    def label(day, name):
        if row(day) is not None:
            rows[day]["labels"].append(name)

    def record(day, key, points, keys_field, points_field=None):
        entry = row(day)
        if entry is not None:
            entry[keys_field].append(key)
            if points_field:
                entry[points_field] += points or 0

    label(start, "sprint_start")
    if status == "active":
        label(today, "today")
    else:
        label(complete or end, "sprint_closed")

    def record_membership(issue):
        """Entry (the start, for original work), plus every cross-day
        departure and return after it."""
        record(issue["enteredSprintOn"], issue["key"],
               issue["storyPoints"], "added_keys", "added_points")
        returns = [sprint_date(t, reporting_zone)
                   for t in issue["returnEvents"]]
        departures = [sprint_date(t, reporting_zone)
                      for t in issue["departureEvents"]]
        cancelled_adds = {d: min(returns.count(
            d), departures.count(d)) for d in set(returns)}
        cancelled_departures = dict(cancelled_adds)
        for day in returns:
            if cancelled_adds.get(day):
                cancelled_adds[day] -= 1
            else:
                record(day, issue["key"], issue["storyPoints"],
                       "readded_keys", "readded_points")
        for ts, done in zip(issue["departureEvents"], issue["doneAtDepartures"]):
            day = sprint_date(ts, reporting_zone)
            if cancelled_departures.get(day):
                cancelled_departures[day] -= 1
                continue
            record(day, issue["key"], issue["storyPoints"],
                   "departure_keys", "departure_points")
            if done:
                record(day, issue["key"], None, "removed_done_keys")

    def record_completion(issue):
        when = issue["effectiveCompletionDate"]
        if not when:
            return
        origin = "extra" if issue["addedMidSprint"] else "original"
        kind = "already_done" if issue["alreadyDoneOnArrival"] else "completed"
        record(when, issue["key"], issue["storyPoints"],
               f"{kind}_{origin}_keys", f"{kind}_{origin}_points")

    for issue in current:
        record_membership(issue)
        record_completion(issue)
    for issue in removed:
        record_membership(issue)
        # Only work completed here before it left counts as a completion. An
        # issue removed while open wasn't delivered here, and one already
        # Done when it entered was never work here: it is only a removal.
        if issue["wasDoneAtRemoval"] and not issue["alreadyDoneOnArrival"]:
            record_completion(issue)

    for entry in rows.values():
        for field, value in entry.items():
            if field.endswith("_keys"):
                value.sort(key=key_order)
    return [rows[day] for day in sorted(rows)]


def cross_check(report, current, removed, before_start, later_moves=()):
    """Compare our in-scope, completed and removed sets with Jira's sprint report, which
    buckets the same issues independently. Returns None if the report has no
    contents, else a list of discrepancies (empty when they agree). Issues
    moved after the cutoff are excluded from this comparison: Jira's current
    membership buckets cannot verify their historical membership."""
    contents = (report or {}).get("contents")
    if not contents:
        return None
    if not any(contents.get(bucket) for bucket in ("completedIssues", "issuesNotCompletedInCurrentSprint",
                                                   "issuesCompletedInAnotherSprint", "puntedIssues")):
        return ["Jira's sprint report is empty: this board doesn't serve it. Fetch the sprint again "
                "with --board, using another scrum board of the project"]

    def keys_in(bucket):
        return {i["key"] for i in contents.get(bucket) or []} - set(later_moves)

    jira_done = keys_in("completedIssues") | keys_in(
        "issuesCompletedInAnotherSprint")
    jira_in = jira_done | keys_in("issuesNotCompletedInCurrentSprint")
    problems = []
    for name, ours, theirs in (("in-scope", {i["key"] for i in current}, jira_in),
                               ("completed", {
                                i["key"] for i in current if not i["carriedOver"]}, jira_done),
                               ("removed", {i["key"] for i in removed}, keys_in("puntedIssues") - set(before_start))):
        ours -= set(later_moves)
        if ours - theirs:
            problems.append(
                f"{name}: {sorted(ours - theirs)} in our data but not in Jira's sprint report")
        if theirs - ours:
            problems.append(
                f"{name}: {sorted(theirs - ours)} in Jira's sprint report but not in our data")
    return problems


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--report-dir", required=True,
                        help="report folder created by fetch_sprint.py")
    args = parser.parse_args()

    raw_dir = os.path.join(args.report_dir, RAW_DIR)
    meta = load_json(os.path.join(raw_dir, "_meta.json"))
    fields = (meta.get("flagged_field"), meta.get("story_points_field"))
    sprint = load_json(os.path.join(raw_dir, "sprint.json"))
    sprint_id = str(sprint["id"])
    report = load_optional(os.path.join(raw_dir, "sprint_report.json"), {})

    # Sub-tasks are left out: Jira's sprint report and board totals count only
    # standard issues, with sub-task work rolled into the parent. The raw files
    # keep them.
    def standard(issues):
        return [i for i in issues if not nested(i.get("fields"), ["issuetype", "subtask"])]
    current_raw = standard(
        load_json(os.path.join(raw_dir, "sprint_issues.json")))
    removed_raw = standard(load_optional(
        os.path.join(raw_dir, "punted_issues.json"), []))
    if not current_raw and not removed_raw:
        raise SystemExit("the sprint has no issues; nothing to report")

    status = (sprint.get("state") or "").lower()
    if status not in {"active", "closed"}:
        raise SystemExit(
            f"sprint state {status!r}: only active and closed sprints can be reported")
    if not sprint.get("startDate"):
        raise SystemExit("the sprint has no start date")
    offset = report_timezone(meta.get("report_timezone"))
    start = sprint_date(sprint.get("startDate"), offset)
    end = sprint_date(sprint.get("endDate"), offset, end_of_period=True)
    complete = sprint_date(sprint.get("completeDate"), offset)

    changes = load_changelogs(os.path.join(
        raw_dir, "changelogs"), current_raw + removed_raw)
    context = Context(sprint_id, sprint["startDate"], start,
                      status_categories(load_json(os.path.join(
                          raw_dir, "statuses.json"))), fields,
                      epic_names(current_raw + removed_raw,
                                 load_optional(os.path.join(raw_dir, "parents.json"), [])), offset)
    moment = as_of(sprint, meta.get("fetched_at"))
    if not moment:
        raise SystemExit("can't tell the moment the report describes (no close date or fetch time); "
                         "fetch the sprint again")
    today = sprint_date(meta.get("fetched_at"), offset)
    if not today:
        raise SystemExit(
            "no fetch timestamp for the report date; fetch the sprint again")
    overlap = {i["key"] for i in current_raw} & {i["key"] for i in removed_raw}
    if overlap:
        raise SystemExit(
            f"{sorted(overlap)} are both in the sprint and in Jira's removed list")

    all_raw = current_raw + removed_raw
    current_raw, removed_raw = scope_at(all_raw, changes, context, moment)
    current = build_current_issues(current_raw, changes, context, moment)
    removed, before_start = build_removed_issues(
        removed_raw, changes, context, moment)

    later_moves = sorted({raw["key"] for raw in all_raw
                          for events in add_and_remove_events(changes[raw["key"]], context.sprint_id)
                          for ts in events if parse_ts(ts) > parse_ts(moment)},
                         key=key_order)
    problems = cross_check(report, current, removed, before_start, later_moves)
    if problems is None:
        raise SystemExit("Jira's sprint report is missing, so the scope can't be cross-checked; "
                         "no data written. Fetch the sprint again.")
    if problems:
        raise SystemExit("data differs from Jira's sprint report; no data written. Unless said otherwise "
                         "below, the sprint changed during the fetch: fetch it again.\n  - "
                         + "\n  - ".join(problems))

    outcome_counts, outcome_points = bucketed(
        current, lambda i: "carried_over" if i["carriedOver"] else "completed",
        ("completed", "carried_over"))
    breakdown_keys = ("original_completed", "original_not_completed",
                      "extra_completed", "extra_not_completed")
    breakdown_counts, breakdown_points = bucketed(
        current, lambda i: ("extra" if i["addedMidSprint"] else "original")
        + ("_not_completed" if i["carriedOver"] else "_completed"), breakdown_keys)

    non_delivery = [i for i in current if i["closedAsNonDelivery"]]
    arrived_done = [i for i in current + removed if i["alreadyDoneOnArrival"]]
    descoped = [i for i in removed if not i["wasDoneAtRemoval"]]
    done_before_removal = [i for i in removed if i["wasDoneAtRemoval"]]
    timeline = build_scope_timeline(
        current, removed, status, start, complete, end, today, offset)
    current_keys = {i["key"] for i in current}

    data = {
        "sprint_id": sprint["id"],
        "sprint_name": sprint.get("name"),
        "board_id": meta.get("board_id"),
        "project_key": meta.get("project_key"),
        "label": meta.get("label"),
        "base_url": meta.get("base_url"),
        "sprint_status": status,
        "sprint_goal": sprint.get("goal") or "",
        "sprint_start": start,
        "sprint_end": end,
        "sprint_complete_date": complete,
        # The raw instants, so the timezone conversion above can be audited.
        "sprint_start_instant": sprint.get("startDate"),
        "sprint_end_instant": sprint.get("endDate"),
        # The moment the issues' fields describe: the close, or the fetch.
        "as_of_instant": moment,
        "report_timezone": offset.key,
        "today": today,
        "issues": current,
        "removed_issues": removed,
        "outcome_counts": outcome_counts,
        "outcome_points": outcome_points,
        "non_delivery_closures": {**totals(non_delivery), "issues": [
            {"key": i["key"], "status": i["status"], "resolution": i["resolution"],
             "storyPoints": i["storyPoints"], "marker": i["closedAsNonDelivery"], "summary": i["summary"]}
            for i in sorted(non_delivery, key=lambda x: key_order(x["key"]))]},
        "already_done_on_arrival": {**totals(arrived_done), "issues": [
            {"key": i["key"], "storyPoints": i["storyPoints"], "summary": i["summary"],
             "completedAt": i["completedAt"], "enteredSprintOn": i["enteredSprintOn"],
             "stillInSprint": i["key"] in current_keys}
            for i in sorted(arrived_done, key=lambda x: key_order(x["key"]))]},
        "removed_summary": {
            "descoped_incomplete": totals(descoped),
            "already_done_on_arrival": totals([i for i in done_before_removal if i["alreadyDoneOnArrival"]]),
            "completed_before_removal": totals([i for i in done_before_removal if not i["alreadyDoneOnArrival"]]),
            "total": totals(removed),
        },
        "points_estimated_issue_count": sum(1 for i in current if i["storyPoints"] is not None),
        "points_total_issue_count": len(current),
        "added_mid_sprint_keys": sorted((i["key"] for i in current if i["addedMidSprint"]), key=key_order),
        # Issues that joined and left before the start, so aren't reported.
        "removed_before_start_keys": sorted(before_start, key=key_order),
        # Jira's current buckets cannot independently verify these issues'
        # historical membership, which is reconstructed from their changes.
        "membership_cross_check_excluded_keys": later_moves,
        "blocker_candidate_keys": sorted(
            (i["key"] for i in current
             if is_blocker_candidate(i["flagged"], i["status"], i["statusCategory"], i["priority"])),
            key=key_order),
        "commitment_breakdown_counts": breakdown_counts,
        "commitment_breakdown_points": breakdown_points,
        "epics": build_epics(current, removed),
        "scope_timeline": timeline,
        "burndown": build_burndown(
            all_raw, changes, context, current + removed, offset, moment,
            min(today, end) if status == "active"
            else sprint_date(moment, offset)),
    }
    out = os.path.join(args.report_dir, DATA_FILE)
    write_json(out, data)

    summary = data["removed_summary"]
    print(f"in scope: {len(current)} issues, {sum(outcome_points.values())} pts "
          f"(completed {outcome_counts['completed']} / {outcome_points['completed']} pts, "
          f"{len(non_delivery)} of them closed as non-delivery) "
          + ("[matches Jira's sprint report for comparable issues]" if later_moves
             else "[matches Jira's sprint report]"))
    if later_moves:
        print("membership reconstructed from history, excluded from Jira bucket comparison: "
              + ", ".join(later_moves))
    print(f"removed: {summary['descoped_incomplete']['count']} descoped, "
          f"{summary['already_done_on_arrival']['count']} already Done when they entered, "
          f"{summary['completed_before_removal']['count']} removed after completion")
    print(f"added after the start: {len(data['added_mid_sprint_keys'])} in-scope issue(s); "
          f"left before the start, not reported: {len(before_start)}")
    print("wrote", out)


if __name__ == "__main__":
    main()
