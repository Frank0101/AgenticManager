"""
Build <report_dir>/data.json from the _raw files fetch_sprint.py wrote.
Reads no network: the same raw files always give the same output,
so a report's numbers can be audited against the payloads they came from.

Usage:
    python3 build_sprint_data.py --report-dir <report_dir>

The report date comes from the saved fetch timestamp in the reporting timezone,
so the calculation is explicit and testable without reading the clock.

One model for the whole report: each ticket's spells in the sprint, each with
its dated events, worked out once from its changelog. Every figure the report
shows is built from them and nothing else. The history (the timeline table and
the burndown) shows every spell's events; the final situation (the outcome
charts, the header, the epic table and the generated prose) counts each spell
by where it ended. check_report.py replays the events itself and requires
every part of the report to agree.

A spell is one stretch of time a ticket spent in the sprint, as at the moment
the report describes (when a closed sprint closed, or the fetch for an active
one; later moves are ignored):

  * The original commitment is the spell of every ticket in the sprint at its
    start instant (`startDate` as Jira records it), Done or not. A ticket
    already Done then is committed work completed from the start; if it is
    reopened, its points move back to not completed.
  * Every time a ticket leaves the sprint, its spell ends: it is descoped, at
    its estimate then. Every time a ticket joins after the start, including
    when it comes back, a new spell begins: extra work, at its estimate and
    state then, as they may have changed while it was out.
  * An extra spell that ends with the ticket leaving was never part of the
    commitment: the history shows it, but the final situation doesn't count it
    (`counted` false). Tickets that joined and left before the start have no
    spell and are in no part of the report (`left_before_start_keys`).

An issue whose Sprint-field changes for this sprint don't start with an add
(none at all, or a removal first) got the sprint when it was created: Jira
logs no change for a field's initial value, so its `created` time is when it
joined.

A spell's events, in time order, each with the estimate and the Done state
right after it:

  committed    in the sprint at the start (the original spell)
  joined       joined after the start, or came back (an extra spell)
  completed    moved into Jira's Done category
  reopened     moved out of it
  reestimated  its story points changed (`fromPoints`)
  removed      left the sprint: the spell ends, descoped

Its outcome is its state after the last event: `completed` or
`not_completed` if it is in the sprint at the end, `removed` (descoped) if it
isn't. Its `points` are its latest estimate: at the end, or when it left.
Completed means in Jira's Done category, as in Jira's sprint report, so
duplicates and Won't Do count too; `non_delivery_closures` names them, as an
annotation, never a subtraction.

Carried over (`carriedIn`) is the original spell of a ticket that was also in
the previous sprint (the board's closed sprint that started last before this
one) at the instant that sprint closed. Being in it at some point isn't
enough.

Every field that describes a spell (status, resolution, flag, priority, epic)
is as it was at the end, or when the ticket left, rebuilt from its changelog,
never as it is today. Run on the same sprint at any later date, the report gives the
same figures.

Each epic in `epics` also sorts its counted spells into the groups its
commentary describes in scope terms (`scope_groups`): completed, in review
(not completed, with a status at the end whose name contains "review"), not
completed, and descoped, each ticket with its scope (original or extra),
summary and description. Work
the sprint didn't do is left out (`left_out`): tickets resolved as Duplicate
or Won't Do, and tickets never completed during their spell, as they were
already Done when it began, whether they then stayed or were descoped. The
figures still count them, as completed or descoped.
Descriptions are as they read at the fetch, the only text not rebuilt to the
end.

The in-scope, completed and removed sets are also cross-checked against
Jira's own sprint report. If the check can't run or finds a discrepancy, the
script exits non-zero without writing data.json. Jira's sprint report shows
today's membership, so issues moved after the moment the report describes
are left out of that comparison and listed in
`membership_cross_check_excluded_keys`.
"""
import argparse
import os
from datetime import datetime, time, timedelta, timezone

from common import (DATA_FILE, NO_EPIC, OUTCOME_ROWS, OUTCOMES, RAW_DIR, SCOPE_GROUPS, History,
                    add_and_remove_events, as_of, in_sprint_at, is_blocker_candidate, issue_moves, key_order,
                    load_json, nested, outcome_total, parse_ts, plain_text, report_timezone, split_ids, sprint_moves,
                    status_categories, write_json)

# Terms meaning an issue was closed without delivering it (duplicate, won't do,
# cancelled...), matched against both the status and the resolution: a
# "Duplicate" status can carry the default "Done" resolution.
NON_DELIVERY_MARKERS = {
    "won't do", "wont do", "won’t do",
    "won't fix", "wont fix", "won’t fix",
    "cancelled", "canceled", "duplicate", "obsolete", "rejected", "declined",
}
# Descriptions longer than this are cut, to keep data.json readable.
DESCRIPTION_CHARS = 2000

# When changes share an instant: estimates, then status, then sprint moves, so
# a ticket completed and removed in one edit is completed, then removed.
CHANGE_ORDER = {"points": 0, "status": 1, "move": 2}


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
    """What every ticket is built with: the sprint, the site's fields and
    statuses, and the epics' names."""

    def __init__(self, sprint_id, start_ts, start_date, categories, fields, epic_names, reporting_zone=timezone.utc,
                 previous=None):
        self.sprint_id, self.start_ts, self.start_date = sprint_id, start_ts, start_date
        self.reporting_zone = reporting_zone
        self.categories = categories
        self.flagged_field, self.points_field = fields
        # {epic id: (key, summary)}
        self.epic_names = epic_names
        # The previous sprint, as previous_sprint.json holds it, or None.
        self.previous = previous


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


def description(fields):
    """An issue's description as plain text, cut at DESCRIPTION_CHARS."""
    text = plain_text((fields or {}).get("description"))
    return text if len(text) <= DESCRIPTION_CHARS else text[:DESCRIPTION_CHARS].rstrip() + "…"


def epic_descriptions(parents):
    """{epic key: its description} from parents.json."""
    return {p["key"]: description(p.get("fields")) for p in parents if p.get("key")}


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


def in_sprint_when_closed(changes, created, sprint):
    """Whether the issue was in `sprint`, a closed sprint, at the instant it
    closed. Jira keeps a closed sprint in the Sprint field of the issues it
    held, so an issue whose changes never name the sprint was never in it; one
    whose first change already has it was in it from its creation."""
    if not sprint:
        return False
    sprint_id = str(sprint["id"])
    if not any(sprint_id in split_ids(c.get("from")) | split_ids(c.get("to"))
               for c in changes if c.get("field") == "sprint"):
        return False
    added, removed = add_and_remove_events(changes, sprint_id)
    return in_sprint_at(sprint_moves(added, removed, created), parse_ts(sprint["completeDate"]))


def event(at, kind, points, done, offset, **extra):
    return {"at": at, "date": sprint_date(at, offset), "type": kind, "points": points, "done": done, **extra}


def spell_events(history, moves, start_ts, in_at_start, changes, cutoff, offset):
    """A ticket's spells in the sprint, as lists of events (see the module
    docstring), from the start to the cutoff."""
    start = parse_ts(start_ts)
    spells, inside, points, done = [], False, None, False

    def enter(ts, kind):
        nonlocal inside, points, done
        state = history.state_at(parse_ts(ts))
        inside, points, done = True, state["storyPoints"], state["statusCategory"] == "done"
        spells.append([event(ts, kind, points, done, offset)])
    if in_at_start:
        enter(start_ts, "committed")
    steps = [(when, CHANGE_ORDER["move"], ts, "move", move)
             for when, move, ts in moves if start < when <= cutoff]
    steps += [(parse_ts(c["created"]), CHANGE_ORDER[c["field"]], c["created"], c["field"], None)
              for c in changes if c["field"] in ("points", "status") and start < parse_ts(c["created"]) <= cutoff]
    for when, _, ts, kind, move in sorted(steps, key=lambda s: (s[0], s[1])):
        if kind == "move":
            if move < 0 and inside:
                inside = False
                spells[-1].append(event(ts, "removed", points, done, offset))
            elif move > 0 and not inside:
                enter(ts, "joined")
            continue
        if not inside:
            continue
        state = history.state_at(when)
        if kind == "points" and state["storyPoints"] != points:
            spells[-1].append(event(ts, "reestimated",
                              state["storyPoints"], done, offset, fromPoints=points))
            points = state["storyPoints"]
        elif kind == "status" and (state["statusCategory"] == "done") != done:
            done = not done
            spells[-1].append(event(ts, "completed" if done else "reopened",
                              points, done, offset))
    return spells


def build_spells(raw, changes, context, moment):
    """The ticket's spells during the reported period, or [] if it had none."""
    cutoff = parse_ts(moment)
    moves = [m for m in issue_moves(
        raw, changes, context.sprint_id) if m[0] <= cutoff]
    history = History(raw, changes, context.categories,
                      context.flagged_field, context.points_field)
    in_at_start = in_sprint_at(moves, parse_ts(context.start_ts))
    fields = raw.get("fields") or {}
    carried = in_at_start and in_sprint_when_closed(
        changes, fields.get("created"), context.previous)
    spells = []
    for events in spell_events(history, moves, context.start_ts, in_at_start, changes, cutoff,
                               context.reporting_zone):
        last = events[-1]
        inside = last["type"] != "removed"
        outcome = ("completed" if last["done"]
                   else "not_completed") if inside else "removed"
        scope = "original" if events[0]["type"] == "committed" else "extra"
        state = history.state_at(cutoff if inside else parse_ts(last["at"]))
        parent_id = state.pop("parentId")
        parent_key, parent_summary = (context.epic_names.get(parent_id, (state["parentKey"], state["parentKey"]))
                                      if parent_id else (None, None))
        spells.append({
            "key": raw["key"],
            "summary": fields.get("summary"),
            "description": description(fields),
            "type": nested(fields, ["issuetype", "name"]),
            "assignee": nested(fields, ["assignee", "displayName"]),
            "created": fields.get("created"),
            "labels": fields.get("labels") or [],
            **state,
            "parentKey": parent_key,
            "parentSummary": parent_summary,
            "scope": scope,
            "carriedIn": scope == "original" and carried,
            "events": events,
            "outcome": outcome,
            # Its latest estimate: at the end, or when it left.
            "points": last["points"],
            # Whether the final-situation figures count it: an extra spell
            # that ended with the ticket leaving was never part of the sprint.
            "counted": not (scope == "extra" and outcome == "removed"),
            "closedAsNonDelivery": (non_delivery_marker(state["status"], state["resolution"])
                                    if outcome == "completed" else None),
        })
    return spells


def replay(events, until):
    """(in the sprint, Done, points) after a spell's events up to `until`, or
    None before it began."""
    state = None
    for e in events:
        if parse_ts(e["at"]) > until:
            break
        state = (e["type"] != "removed", e["done"], e["points"])
    return state


def outcome_breakdown(spells):
    """(counts, points) of the counted spells by row (original, its carried_in
    and new parts, extra) and outcome, at each spell's latest estimate."""
    keys = [f"{row}_{outcome}" for row in OUTCOME_ROWS for outcome in OUTCOMES]
    counts, points = {k: 0 for k in keys}, {k: 0 for k in keys}
    for spell in (s for s in spells if s["counted"]):
        rows = (["extra"] if spell["scope"] == "extra"
                else ["original", "carried_in" if spell["carriedIn"] else "new"])
        for row in rows:
            counts[f"{row}_{spell['outcome']}"] += 1
            points[f"{row}_{spell['outcome']}"] += spell["points"] or 0
    return counts, points


def scope_group(spell):
    """(the commentary group of a counted spell, or None, why it is left out).
    Work Done when its spell began and never reopened was done before it,
    even if it was then descoped."""
    if spell["outcome"] == "removed":
        done_throughout = spell["events"][0]["done"] and not any(
            e["type"] == "reopened" for e in spell["events"])
        return (None, "done_at_start") if done_throughout else ("descoped", None)
    if spell["outcome"] == "not_completed":
        return ("in_review" if "review" in (spell["status"] or "").lower() else "not_completed"), None
    if spell["closedAsNonDelivery"]:
        return None, "non_delivery"
    if not any(e["type"] == "completed" for e in spell["events"]):
        return None, "done_at_start"
    return "completed", None


def build_epics(spells, descriptions=None):
    """Per-epic delivery of the counted spells: done is completed; the total
    adds not completed and descoped. Descoped original work is also counted
    apart. Each epic also carries its description and its spells sorted into
    the commentary's groups (see scope_group)."""
    descriptions = descriptions or {}
    epics = {}
    for spell in (s for s in spells if s["counted"]):
        key, name = ((spell["parentKey"], spell["parentSummary"]) if spell["parentKey"]
                     else (NO_EPIC, "(no epic)"))
        epic = epics.setdefault(key, {
            "key": key, "name": name,
            "original_stories_done": 0, "original_stories_total": 0,
            "original_points_done": 0, "original_points_total": 0,
            "extra_stories_done": 0, "extra_stories_total": 0,
            "extra_points_done": 0, "extra_points_total": 0,
            "removed_stories": 0, "removed_points": 0,
            "description": descriptions.get(key, ""),
            "scope_groups": {group: [] for group in SCOPE_GROUPS},
            "left_out": [],
        })
        group, reason = scope_group(spell)
        ticket = {"key": spell["key"], "scope": spell["scope"], "summary": spell["summary"],
                  "description": spell.get("description", "")}
        if group:
            epic["scope_groups"][group].append(ticket)
        else:
            epic["left_out"].append({**ticket, "reason": reason})
        points, scope = spell["points"] or 0, spell["scope"]
        epic[f"{scope}_stories_total"] += 1
        epic[f"{scope}_points_total"] += points
        if spell["outcome"] == "completed":
            epic[f"{scope}_stories_done"] += 1
            epic[f"{scope}_points_done"] += points
        elif spell["outcome"] == "removed":
            epic["removed_stories"] += 1
            epic["removed_points"] += points
    return sorted(epics.values(),
                  key=lambda e: (-(e["original_points_total"] + e["extra_points_total"]), key_order(e["key"])))


def build_timeline(spells, status, start, end, complete, today):
    """Every spell's events by day, counted or not, plus the start, today or
    close rows."""
    rows = {}

    def row(day):
        return rows.setdefault(day, {"date": day, "labels": [], "events": []})
    row(start)["labels"].append("sprint_start")
    if status == "active":
        row(today)["labels"].append("today")
    elif complete or end:
        row(complete or end)["labels"].append("sprint_closed")
    for spell in spells:
        for e in spell["events"]:
            row(e["date"])["events"].append({"key": spell["key"], "scope": spell["scope"], **{
                k: e[k] for k in ("at", "type", "points", "done", "fromPoints") if k in e}})
    for entry in rows.values():
        entry["events"].sort(key=lambda e: (
            key_order(e["key"]), parse_ts(e["at"])))
    return [rows[day] for day in sorted(rows)]


def build_burndown(spells, start_date, last_date, moment, offset):
    """Open stories and points at the end of each local day, from the
    events of every spell, counted or not: the original commitment's, and with
    the extra work's too.
    The closing day stops at the exact close, an active snapshot's current day
    at the fetch."""
    rows = []
    day = datetime.strptime(start_date, "%Y-%m-%d").date()
    end = datetime.strptime(last_date, "%Y-%m-%d").date()
    while day <= end:
        cutoff = min(datetime.combine(
            day, time.max, tzinfo=offset), parse_ts(moment))
        committed = total = committed_stories = total_stories = 0
        for spell in spells:
            state = replay(spell["events"], cutoff)
            if state and state[0] and not state[1]:
                total += state[2] or 0
                total_stories += 1
                if spell["scope"] == "original":
                    committed += state[2] or 0
                    committed_stories += 1
        rows.append({"date": day.isoformat(), "committed": committed, "total": total,
                     "committed_stories": committed_stories, "total_stories": total_stories})
        day += timedelta(days=1)
    return rows


def cross_check(report, in_scope, completed, removed, later_moves=()):
    """Compare our in-scope, completed and removed key sets with Jira's
    sprint report, which buckets the same issues independently. Returns None
    if the report has no contents, else a list of discrepancies (empty when
    they agree). Issues moved after the cutoff are excluded from this
    comparison: Jira's current membership buckets cannot verify their
    historical membership."""
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
    for name, ours, theirs in (("in-scope", set(in_scope), jira_in), ("completed", set(completed), jira_done),
                               ("removed", set(removed), keys_in("puntedIssues"))):
        ours -= set(later_moves)
        if ours - theirs:
            problems.append(
                f"{name}: {sorted(ours - theirs)} in our data but not in Jira's sprint report")
        if theirs - ours:
            problems.append(
                f"{name}: {sorted(theirs - ours)} in Jira's sprint report but not in our data")
    return problems


def membership_sets(raw_issues, changes, context, moment):
    """(in scope, completed, removed) keys as Jira's sprint report buckets
    them, from membership at the cutoff: removed is every issue that left
    before it, including extra work and work that left before the start."""
    in_scope, completed, removed = [], [], []
    cutoff = parse_ts(moment)
    for raw in raw_issues:
        moves = issue_moves(raw, changes[raw["key"]], context.sprint_id)
        if in_sprint_at(moves, cutoff):
            in_scope.append(raw["key"])
            history = History(raw, changes[raw["key"]], context.categories,
                              context.flagged_field, context.points_field)
            if history.done_at(cutoff):
                completed.append(raw["key"])
        elif any(move < 0 and when <= cutoff for when, move, _ in moves):
            removed.append(raw["key"])
    return in_scope, completed, removed


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
    if not os.path.exists(os.path.join(raw_dir, "previous_sprint.json")):
        raise SystemExit(
            "no previous_sprint.json, so carry-over can't be told apart; fetch the sprint again")
    previous = load_json(os.path.join(raw_dir, "previous_sprint.json"))
    start = sprint_date(sprint.get("startDate"), offset)
    end = sprint_date(sprint.get("endDate"), offset, end_of_period=True)
    complete = sprint_date(sprint.get("completeDate"), offset)

    parents = load_optional(os.path.join(raw_dir, "parents.json"), [])
    changes = load_changelogs(os.path.join(
        raw_dir, "changelogs"), current_raw + removed_raw)
    context = Context(sprint_id, sprint["startDate"], start,
                      status_categories(load_json(os.path.join(
                          raw_dir, "statuses.json"))), fields,
                      epic_names(current_raw + removed_raw, parents), offset, previous)
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
    later_moves = sorted({raw["key"] for raw in all_raw
                          for events in add_and_remove_events(changes[raw["key"]], context.sprint_id)
                          for ts in events if parse_ts(ts) > parse_ts(moment)},
                         key=key_order)
    for raw in current_raw:
        moves = issue_moves(raw, changes[raw["key"]], sprint_id)
        if raw["key"] not in later_moves and not in_sprint_at(moves, parse_ts(moment)):
            raise SystemExit(f"{raw['key']} is in the sprint but its changelog says it isn't; "
                             "fetch the sprint again")
    for raw in removed_raw:
        if not add_and_remove_events(changes[raw["key"]], sprint_id)[1]:
            raise SystemExit(f"{raw['key']} is in Jira's removed list but its changelog has no removal "
                             f"from sprint {sprint_id}; inspect it before reporting")

    in_scope, completed, removed = membership_sets(
        all_raw, changes, context, moment)
    problems = cross_check(report, in_scope, completed, removed, later_moves)
    if problems is None:
        raise SystemExit("Jira's sprint report is missing, so the scope can't be cross-checked; "
                         "no data written. Fetch the sprint again.")
    if problems:
        raise SystemExit("data differs from Jira's sprint report; no data written. Unless said otherwise "
                         "below, the sprint changed during the fetch: fetch it again.\n  - "
                         + "\n  - ".join(problems))

    spells, left_before_start = [], []
    for raw in all_raw:
        found = build_spells(raw, changes[raw["key"]], context, moment)
        spells += found
        if not found and any(parse_ts(ts) <= parse_ts(context.start_ts)
                             for ts in add_and_remove_events(
                                 changes[raw["key"]], sprint_id)[1]):
            left_before_start.append(raw["key"])
    spells.sort(key=lambda t: (
        key_order(t["key"]), parse_ts(t["events"][0]["at"])))
    counted = [t for t in spells if t["counted"]]
    counts, points = outcome_breakdown(spells)
    non_delivery = [t for t in counted if t["closedAsNonDelivery"]]
    original = [t for t in spells if t["scope"] == "original"]

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
        # The moment the spells' events and fields run to: the close, or the fetch.
        "as_of_instant": moment,
        "report_timezone": offset.key,
        "today": today,
        "previous_sprint": previous and {
            "id": previous["id"], "name": previous.get("name"),
            "complete_instant": previous["completeDate"],
            "complete_date": sprint_date(previous["completeDate"], offset)},
        "spells": spells,
        # Issues that joined and left before the start: in no part of the report.
        "left_before_start_keys": sorted(left_before_start, key=key_order),
        "outcome_breakdown_counts": counts,
        "outcome_breakdown_points": points,
        "non_delivery_closures": {
            "count": len(non_delivery), "points": sum(t["points"] or 0 for t in non_delivery),
            "issues": [{"key": t["key"], "status": t["status"], "resolution": t["resolution"],
                        "storyPoints": t["points"], "marker": t["closedAsNonDelivery"], "summary": t["summary"]}
                       for t in non_delivery]},
        "points_estimated_issue_count": sum(1 for t in counted if t["points"] is not None),
        "points_total_issue_count": len(counted),
        # Jira's current buckets cannot independently verify these issues'
        # historical membership, which is reconstructed from their changes.
        "membership_cross_check_excluded_keys": later_moves,
        "blocker_candidate_keys": [
            t["key"] for t in counted if t["outcome"] != "removed"
            and is_blocker_candidate(t["flagged"], t["status"], t["statusCategory"], t["priority"])],
        "epics": build_epics(spells, epic_descriptions(parents)),
        "timeline": build_timeline(spells, status, start, end, complete, today),
        # The burndown's first point: the whole commitment at the start, Done or
        # not; the start day's end-of-day reading then shows what was open.
        "burndown_baseline": sum(t["events"][0]["points"] or 0 for t in original),
        "burndown": build_burndown(spells, start, min(today, end) if status == "active"
                                   else sprint_date(moment, offset), moment, offset),
    }
    out = os.path.join(args.report_dir, DATA_FILE)
    write_json(out, data)

    print(f"original commitment: {outcome_total(counts, 'original')} spell(s), "
          f"{counts['original_completed']} completed, {counts['original_not_completed']} not completed, "
          f"{counts['original_removed']} descoped; extra: {outcome_total(counts, 'extra')} spell(s), "
          f"{counts['extra_completed']} completed "
          + ("[matches Jira's sprint report for comparable issues]" if later_moves
             else "[matches Jira's sprint report]"))
    if later_moves:
        print("membership reconstructed from history, excluded from Jira bucket comparison: "
              + ", ".join(later_moves))
    if previous:
        print(f"carried over from {previous.get('name')}: {outcome_total(counts, 'carried_in')}"
              f" of {outcome_total(counts, 'original')} original spell(s)")
    else:
        print("no previous sprint on the board, so nothing carried over")
    uncounted = [t["key"] for t in spells if not t["counted"]]
    print("extra spells that ended descoped, shown but not counted: " +
          (", ".join(uncounted) or "none"))
    print("left before the start, not reported: " +
          (", ".join(left_before_start) or "none"))
    print("wrote", out)


if __name__ == "__main__":
    main()
