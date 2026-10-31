"""Build <report_dir>/data.json from the _raw files fetch_sprint.py wrote: the
one model every part of the report is built from.

No network and no clock: the report date comes from the saved fetch time, so the
same raw files always give the same figures and can be audited against them.
Each ticket's events come from the raw files, and its spells from its events
alone, so its history and its spells can't tell different stories; every figure
is built from the spells, and check_report.py replays the events. Separate
calculations per view drifted apart before; one model can't.
"""
import argparse
import os
from datetime import date, datetime, time, timedelta

from common import (CHANGELOGS_DIR, COMMENTS_DIR, DATA_FILE, META_FILE, OUTCOME_ROWS, OUTCOMES, PARENTS_FILE,
                    PREVIOUS_SPRINT_FILE, PUNTED_ISSUES_FILE, RAW_DIR, SPRINT_FILE,
                    SPRINT_ISSUES_FILE, SPRINT_REPORT_FILE, STATUSES_FILE, SCOPE_GROUPS, Context, add_and_remove_events,
                    as_of, blocker_candidates, PULL_REQUESTS_FILE, PULL_STATES, ISSUE_KEY, in_sprint_at, key_order, known_sum,
                    read_json, nested, outcome_total, parse_ts, plain_text, report_timezone, spell_epic, sprint_date,
                    sprint_moves_of, standard_issues, state_at, status_categories, ticket_events, write_json)

# Terms meaning an issue was closed without delivering it (duplicate, won't do,
# cancelled...), matched against both the status and the resolution: a
# "Duplicate" status can carry the default "Done" resolution. Completed means
# Jira's Done category, these included, to match Jira's own report;
# non_delivery_closures names them as a caveat.
NON_DELIVERY_MARKERS = {
    "won't do", "wont do", "won’t do",
    "won't fix", "wont fix", "won’t fix",
    "cancelled", "canceled", "duplicate", "obsolete", "rejected", "declined",
}

# When changes share an instant: estimates, then status, then sprint moves, so
# a ticket completed and removed in one edit is completed, then removed.
CHANGE_ORDER = {"points": 0, "status": 1, "move": 2}


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


def epic_descriptions(parents):
    """{epic key: its description} from parents.json."""
    return {p["key"]: description(p.get("fields")) for p in parents if p.get("key")}


def description(fields):
    """An issue's description as plain text, whole, so its every chunk can be
    read, not only the first. It is today's, unlike every other field: Jira
    keeps no usable history of descriptions."""
    return plain_text((fields or {}).get("description"))


def load_changelogs(changelog_dir, raw_issues):
    """{key: the changes fetch_sprint.py stored for it}."""
    changes, missing = {}, []
    for raw in raw_issues:
        path = os.path.join(changelog_dir, f"{raw['key']}.json")
        if os.path.exists(path):
            changes[raw["key"]] = read_json(path)
        else:
            missing.append(raw["key"])
    if missing:
        raise SystemExit("missing changelogs for " + ", ".join(sorted(missing)) +
                         "; fetch the sprint again rather than guessing when they joined")
    return changes


def spells_from_events(raw, events, context, moment):
    """The ticket's spells during the reported period, or [] if it had none,
    worked out from its events (ticket_events) alone. The commitment is what
    was in the sprint at its start instant, Done or not, as Jira's sprint
    report counts it. A ticket that leaves ends its spell as descoped; one
    that joins later, even coming back the same day, starts an extra spell."""
    cutoff, key = parse_ts(moment), raw["key"]
    moves = [m for m in sprint_moves_of(
        events, context.sprint_id) if m[0] <= cutoff]
    in_at_start = in_sprint_at(moves, parse_ts(context.start_ts))
    fields = raw.get("fields") or {}
    carried = in_at_start and in_sprint_when_closed(events, context.previous)
    spells = []
    for spell in spell_events(key, events, moves, context.start_ts, in_at_start, cutoff,
                              context.reporting_zone):
        last = spell[-1]
        inside = last["type"] != "removed"
        outcome = ("completed" if last["done"]
                   else "not_completed") if inside else "descoped"
        scope = "original" if spell[0]["type"] == "committed" else "extra"
        state = state_at(
            key, events, cutoff if inside else parse_ts(last["at"]))
        parent_id = state.pop("parentId")
        # An epic that couldn't be fetched is named by its key rather than
        # left blank, so its row in the epic table can still be found.
        parent_key, parent_summary = (context.epic_names.get(parent_id, (state["parentKey"], state["parentKey"]))
                                      if parent_id else (None, None))
        spells.append({
            "key": key,
            "summary": fields.get("summary"),
            "description": description(fields),
            **state,
            "parentKey": parent_key,
            "parentSummary": parent_summary,
            "scope": scope,
            "carriedIn": scope == "original" and carried,
            "events": spell,
            # What the events say, stored so no view derives it again.
            "doneAtStart": spell[0]["done"],
            "reopened": any(e["type"] == "reopened" for e in spell),
            "reestimated": any(e["type"] == "reestimated" for e in spell),
            # A later spell of a ticket that left and returned.
            "cameBack": len(spells) > 0,
            "outcome": outcome,
            # Its latest estimate: at the end, or when it left.
            "points": last["points"],
            # Its estimate when the spell began, before any re-estimate.
            "firstEstimate": spell[0]["points"],
            # Whether the final-situation figures count it: an extra spell
            # that ended with the ticket leaving was never part of the sprint.
            "counted": not (scope == "extra" and outcome == "descoped"),
            "closedAsNonDelivery": (non_delivery_marker(state["status"], state["resolution"])
                                    if outcome == "completed" else None),
        })
    return spells


def in_sprint_when_closed(events, sprint):
    """Whether the ticket was in `sprint`, a closed sprint, at the instant it
    closed, not merely at some point, from its events. Jira keeps a closed
    sprint in the Sprint field of the issues it held, so a ticket whose
    changes never name the sprint was never in it."""
    if not sprint:
        return False
    return in_sprint_at(sprint_moves_of(events, str(sprint["id"])), parse_ts(sprint["completeDate"]))


def spell_events(key, events, moves, start_ts, in_at_start, cutoff, zone):
    """A ticket's spells in the sprint, as lists of dated events (committed or
    joined, then completed, reopened, reestimated and removed), from the start
    to the cutoff."""
    start = parse_ts(start_ts)
    spells, inside, points, done = [], False, None, False

    def enter(ts, kind):
        nonlocal inside, points, done
        state = state_at(key, events, parse_ts(ts))
        inside, points, done = True, state["storyPoints"], state["statusCategory"] == "done"
        spells.append([event(ts, kind, points, done, zone)])
    if in_at_start:
        enter(start_ts, "committed")
    steps = [(when, CHANGE_ORDER["move"], ts, "move", move)
             for when, move, ts in moves if start < when <= cutoff]
    steps += [(parse_ts(e["at"]), CHANGE_ORDER[kind], e["at"], kind, None) for e in events
              if (kind := e["type"].removesuffix("_changed")) in ("points", "status")
              and start < parse_ts(e["at"]) <= cutoff]
    for when, _, ts, kind, move in sorted(steps, key=lambda s: (s[0], s[1])):
        if kind == "move":
            if move < 0 and inside:
                inside = False
                spells[-1].append(event(ts, "removed", points, done, zone))
            elif move > 0 and not inside:
                enter(ts, "joined")
            continue
        if not inside:
            continue
        state = state_at(key, events, when)
        if kind == "points" and state["storyPoints"] != points:
            spells[-1].append(event(ts, "reestimated",
                              state["storyPoints"], done, zone, fromPoints=points))
            points = state["storyPoints"]
        elif kind == "status" and (state["statusCategory"] == "done") != done:
            done = not done
            spells[-1].append(event(ts, "completed" if done else "reopened",
                              points, done, zone))
    return spells


def event(at, kind, points, done, zone, **extra):
    return {"at": at, "date": sprint_date(at, zone), "type": kind, "points": points, "done": done, **extra}


def non_delivery_marker(status, resolution):
    for value in ((status or "").lower(), (resolution or "").lower()):
        if value in NON_DELIVERY_MARKERS:
            return value
    return None


def outcome_breakdown(spells):
    """(counts, points) of the counted spells by row (original, its carried_in
    and new parts, extra) and outcome, at each spell's latest estimate, the
    pts by known_sum's rule."""
    keys = [f"{row}_{outcome}" for row in OUTCOME_ROWS for outcome in OUTCOMES]
    estimates = {k: [] for k in keys}
    for spell in (s for s in spells if s["counted"]):
        rows = (["extra"] if spell["scope"] == "extra"
                else ["original", "carried_in" if spell["carriedIn"] else "new"])
        for row in rows:
            estimates[f"{row}_{spell['outcome']}"].append(spell["points"])
    return ({k: len(found) for k, found in estimates.items()},
            {k: known_sum(found) for k, found in estimates.items()})


def non_delivery_closures(spells):
    """The counted spells completed as a non-delivery (Duplicate, Won't Do...):
    how many, their pts and each one's key, status, resolution, estimate,
    marker and summary."""
    closures = [s for s in spells if s["counted"] and s["closedAsNonDelivery"]]
    return {"count": len(closures), "points": known_sum(s["points"] for s in closures),
            "issues": [{"key": s["key"], "status": s["status"], "resolution": s["resolution"],
                        "storyPoints": s["points"], "marker": s["closedAsNonDelivery"], "summary": s["summary"]}
                       for s in closures]}


def target_completion(spells):
    """The sprint target: the original commitment's spells, and those that
    ended completed. Each counts by how its spell ended: one reopened and done
    again counts as completed; one that left the sprint, never, even if it
    came back."""
    original = [s for s in spells if s["scope"] == "original"]
    done = [s for s in original if s["outcome"] == "completed"]
    return {"completed": len(done), "total": len(original),
            "completed_points": known_sum(s["points"] for s in done),
            "total_points": known_sum(s["points"] for s in original)}


def build_epics(spells, descriptions=None):
    """Per-epic delivery of the counted spells: done is completed; the total
    adds not completed and descoped. The pts follow known_sum's rule. Each epic also carries its
    description and its spells sorted into the commentary's groups (see
    scope_group)."""
    descriptions = descriptions or {}
    epics, estimates = {}, {}
    for spell in (s for s in spells if s["counted"]):
        key, name = spell_epic(spell)
        epic = epics.setdefault(key, {
            "key": key, "name": name,
            "original_stories_done": 0, "original_stories_total": 0,
            "original_points_done": None, "original_points_total": None,
            "extra_stories_done": 0, "extra_stories_total": 0,
            "extra_points_done": None, "extra_points_total": None,
            # Completed pts, commitment and extra together.
            "points_done": None,
            "description": descriptions.get(key, ""),
            "scope_groups": {group: [] for group in SCOPE_GROUPS},
            "left_out": [],
        })
        group, reason = scope_group(spell)
        ticket = {"key": spell["key"], "scope": spell["scope"], "carriedIn": spell["carriedIn"],
                  "points": spell["points"], "status": spell["status"],
                  "flagged": spell["flagged"], "summary": spell["summary"],
                  "description": spell["description"]}
        if group:
            epic["scope_groups"][group].append(ticket)
        else:
            epic["left_out"].append({**ticket, "reason": reason})
        # The estimates each pts field adds up, by epic and field.
        mine = estimates.setdefault(key, {field: [] for field in (
            "original_points_done", "original_points_total", "extra_points_done", "extra_points_total",
            "points_done")})
        points, scope = spell["points"], spell["scope"]
        epic[f"{scope}_stories_total"] += 1
        mine[f"{scope}_points_total"].append(points)
        if spell["outcome"] == "completed":
            epic[f"{scope}_stories_done"] += 1
            mine[f"{scope}_points_done"].append(points)
            mine["points_done"].append(points)
    for key, epic in epics.items():
        epic |= {field: known_sum(found)
                 for field, found in estimates[key].items()}
    # Largest first, unestimated work weighing nothing.
    return sorted(epics.values(),
                  key=lambda e: (-((e["original_points_total"] or 0) + (e["extra_points_total"] or 0)),
                                 key_order(e["key"])))


def scope_group(spell):
    """(the commentary group of a counted spell, or None, why it is left out).
    Work the sprint didn't do is left out: Duplicates, Won't Do, and work
    already Done when its spell began that stayed in the sprint. The figures
    still count it, but the AI text mustn't describe it. Descoped work is
    always described as descoped, even if it was already Done, since the
    figures count it as descoped."""
    if spell["outcome"] == "descoped":
        return "descoped", None
    if spell["outcome"] == "not_completed":
        return ("in_review" if "review" in (spell["status"] or "").lower() else "not_completed"), None
    if spell["closedAsNonDelivery"]:
        return None, "non_delivery"
    if not any(e["type"] == "completed" for e in spell["events"]):
        return None, "done_at_start"
    return "completed", None


def ticket_pulls(raw, key, moment):
    """The pull requests of ticket `key` as at `moment`, from
    pull_requests.json (`raw`): those opened by then, each with the panel's
    title and source branch, the issue it was found through and GitHub's
    times, a merge or closing after `moment` left out, as for the ticket's
    events; then, from those, whether it is the ticket's own and its state
    then. Fails on one GitHub gave no times for, as its state can't be told."""
    pulls, cutoff = [], parse_ts(moment)
    for pr in raw["tickets"].get(key, []):
        times = raw["events"].get(pr["url"])
        if times is None:
            raise SystemExit(f"{key}: no GitHub times for {pr['url']}, so its state can't be told; "
                             "fetch the sprint again")
        if not times.get("createdAt") or parse_ts(times["createdAt"]) > cutoff:
            continue
        record = {"url": pr["url"], "title": pr.get("name") or "", "branch": nested(pr, ["source", "branch"]) or "",
                  "via": pr["via"], "createdAt": times["createdAt"],
                  **{field: times[field] if times.get(field) and parse_ts(times[field]) <= cutoff else None
                     for field in ("mergedAt", "closedAt")}}
        pulls.append({**record, "own": is_own_pull(record, key),
                     "state": pull_state(record)})
    return pulls


def is_own_pull(pr, key):
    """Whether a pull request is the ticket's own work: its title and branch
    name the ticket or the sub-task it was found through, or no ticket at all.
    One that names only other tickets was linked by a mention, such as
    groundwork another ticket owns, so it says nothing of this one's status."""
    named = set(ISSUE_KEY.findall(pr["title"])) | set(
        ISSUE_KEY.findall(pr["branch"]))
    return not named or bool(named & {key, pr["via"]})


def pull_state(pr):
    """A pull request's state as at the moment its times run to: merged,
    declined (closed without a merge) or open."""
    if pr["mergedAt"]:
        return "merged"
    return "declined" if pr["closedAt"] else "open"


def build_status_checks(spells, pulls_of, epics):
    """The rows of the Status to Verify section: each ticket in the sprint at
    the end with a status flag, in the epics' order (`epics`, build_epics())
    and then by key, with its status, how many of its own pull requests are
    open, how many of all those Jira links are in each state, as its
    Development panel shows them, and how many of those name only other
    tickets; `pulls_of` is {key: ticket_pulls()}."""
    order = {epic["key"]: index for index, epic in enumerate(epics)}
    rows = []
    for spell in spells:
        if not spell["counted"] or spell["outcome"] == "descoped":
            continue
        key, pulls = spell["key"], pulls_of.get(spell["key"], [])
        flag = status_flag(spell["statusCategory"], pulls)
        if not flag:
            continue
        rows.append({"key": key, "points": spell["points"], "epicKey": spell_epic(spell)[0], "status": spell["status"],
                     "flag": flag,
                     "ownOpen": sum(pr["own"] and pr["state"] == "open" for pr in pulls),
                     "linked": {state: sum(pr["state"] == state for pr in pulls) for state in PULL_STATES},
                     "otherTickets": sum(not pr["own"] for pr in pulls)})
    return sorted(rows, key=lambda r: (order[r["epicKey"]], key_order(r["key"])))


def status_flag(category, pulls):
    """The Status to Verify flag of a ticket in the sprint at the end, from
    its status category then and its own pull requests (ticket_pulls), or
    None: work_started, not started with one open or merged, or
    open_after_done, Done with one open. Only these two: a started ticket's
    work can sit in a branch before any pull request, and one in review can
    gain new ones, so other mismatches are mostly noise. A pull request
    merged before the sprint started counts too: work merged earlier still
    contradicts a ticket left as not started."""
    states = [pr["state"] for pr in pulls if pr["own"]]
    if category == "new" and ("open" in states or "merged" in states):
        return "work_started"
    if category == "done" and "open" in states:
        return "open_after_done"
    return None


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


def burndown_baseline(spells):
    """The burndown's first point: the whole commitment's estimates at the
    start, Done or not, by known_sum's rule; the start day's end-of-day
    reading then shows what was open."""
    return known_sum(t["firstEstimate"] for t in spells if t["scope"] == "original")


def build_burndown(spells, start_date, last_date, moment, zone):
    """Open tickets and pts at the end of each local day, from the
    events of every spell, counted or not: the original commitment's, and with
    the extra work's too, the pts by known_sum's rule.
    The closing day stops at the exact close, an active snapshot's current day
    at the fetch."""
    rows = []
    day, end = date.fromisoformat(start_date), date.fromisoformat(last_date)
    while day <= end:
        cutoff = min(datetime.combine(
            day, time.max, tzinfo=zone), parse_ts(moment))
        committed, total = [], []
        for spell in spells:
            state = replay(spell["events"], cutoff)
            if state and state[0] and not state[1]:
                total.append(state[2])
                if spell["scope"] == "original":
                    committed.append(state[2])
        rows.append({"date": day.isoformat(), "committed": known_sum(committed), "total": known_sum(total),
                     "committed_stories": len(committed), "total_stories": len(total)})
        day += timedelta(days=1)
    return rows


def replay(events, until):
    """(in the sprint, Done, points) after a spell's events up to `until`, or
    None before it began."""
    state = None
    for e in events:
        if parse_ts(e["at"]) > until:
            break
        state = (e["type"] != "removed", e["done"], e["points"])
    return state


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
                "with --sprint-id and --board, using another scrum board of the project"]

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


def membership_sets(events_of, sprint_id, moment):
    """(in scope, completed, removed) keys as Jira's sprint report buckets
    them, from each ticket's events (`events_of`, {key: ticket_events()}) at
    the cutoff: removed is every ticket that left before it, including extra
    work and work that left before the start."""
    in_scope, completed, removed = [], [], []
    cutoff = parse_ts(moment)
    for key, events in events_of.items():
        moves = sprint_moves_of(events, sprint_id)
        if in_sprint_at(moves, cutoff):
            in_scope.append(key)
            if state_at(key, events, cutoff)["statusCategory"] == "done":
                completed.append(key)
        elif any(move < 0 and when <= cutoff for when, move, _ in moves):
            removed.append(key)
    return in_scope, completed, removed


def blocker_comments(comment_dir, keys, moment, zone):
    """{key: its comments} of each blocker candidate of `keys`, from the
    comment files in `comment_dir`: those comments_as_of() keeps, each as
    {at, date, text}, its creation, local date (None without one) and plain
    text, without a blank one. Their authors are left out, as no part of the
    report names colleagues. A candidate whose comments weren't fetched has
    none."""
    found = {}
    for key in keys:
        path = os.path.join(comment_dir, f"{key}.json")
        values = comments_as_of(read_json(path), parse_ts(
            moment)) if os.path.exists(path) else []
        found[key] = [{"at": c.get("created"), "date": sprint_date(c.get("created"), zone), "text": text}
                      for c in values if (text := plain_text(c.get("body"))).strip()]
    return found


def comments_as_of(comments, moment):
    """The comments whose creation and latest edit do not follow `moment`: a
    later edit hides the text the comment had then, which Jira doesn't keep.
    Without an updated timestamp, creation alone decides."""
    return [c for c in comments
            if all(not c.get(field) or parse_ts(c[field]) <= moment
                   for field in ("created", "updated"))]


def main():
    parser = argparse.ArgumentParser(
        description=(__doc__ or "").split("\n\n")[0],
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Prints a summary of the spells. Writes nothing, and exits non-zero, when the raw files\n"
        "disagree with each other or with Jira's sprint report.")
    parser.add_argument("--report-dir", required=True,
                        help="report folder created by fetch_sprint.py")
    args = parser.parse_args()

    raw_dir = os.path.join(args.report_dir, RAW_DIR)
    meta = read_json(os.path.join(raw_dir, META_FILE))
    fields = (meta.get("flagged_field"), meta.get("story_points_field"))
    sprint = read_json(os.path.join(raw_dir, SPRINT_FILE))
    sprint_id = str(sprint["id"])
    report = read_json(os.path.join(raw_dir, SPRINT_REPORT_FILE))

    # Sub-tasks are left out, as Jira's sprint report leaves them out; the raw
    # files keep them.
    current_raw = standard_issues(
        read_json(os.path.join(raw_dir, SPRINT_ISSUES_FILE)))
    removed_raw = standard_issues(read_json(
        os.path.join(raw_dir, PUNTED_ISSUES_FILE)))
    if not current_raw and not removed_raw:
        raise SystemExit("the sprint has no issues; nothing to report")

    status = sprint["state"].lower()
    zone = report_timezone(meta.get("report_timezone"))
    previous = read_json(os.path.join(raw_dir, PREVIOUS_SPRINT_FILE))
    start = sprint_date(sprint.get("startDate"), zone)
    end = sprint_date(sprint.get("endDate"), zone)
    complete = sprint_date(sprint.get("completeDate"), zone)

    parents = read_json(os.path.join(raw_dir, PARENTS_FILE))
    pull_requests = read_json(os.path.join(raw_dir, PULL_REQUESTS_FILE))
    changes = load_changelogs(os.path.join(
        raw_dir, CHANGELOGS_DIR), current_raw + removed_raw)
    context = Context(sprint_id, sprint["startDate"],
                      status_categories(read_json(os.path.join(
                          raw_dir, STATUSES_FILE))), fields,
                      epic_names(current_raw + removed_raw, parents), zone, previous)
    moment = as_of(sprint, meta["fetched_at"])
    today = sprint_date(meta["fetched_at"], zone)
    overlap = {i["key"] for i in current_raw} & {i["key"] for i in removed_raw}
    if overlap:
        raise SystemExit(
            f"{sorted(overlap)} are both in the sprint and in Jira's removed list")

    all_raw = current_raw + removed_raw
    # Moves after the end, which the events leave out: Jira's sprint report
    # shows today's membership, so it can't vouch for these tickets. These
    # moves, and the check that Jira's removed tickets were removed, are the
    # only reads of the changelogs: membership and blocker candidates come
    # from the ticket events, like the spells.
    later_moves = sorted({raw["key"] for raw in all_raw
                          for events in add_and_remove_events(changes[raw["key"]], sprint_id)
                          for ts in events if parse_ts(ts) > parse_ts(moment)},
                         key=key_order)
    events_of = {raw["key"]: ticket_events(raw, changes[raw["key"]], context, moment)
                 for raw in all_raw}
    for raw in current_raw:
        moves = sprint_moves_of(events_of[raw["key"]], sprint_id)
        if raw["key"] not in later_moves and not in_sprint_at(moves, parse_ts(moment)):
            raise SystemExit(f"{raw['key']} is in the sprint but its changelog says it isn't; "
                             "fetch the sprint again")
    for raw in removed_raw:
        if not add_and_remove_events(changes[raw["key"]], sprint_id)[1]:
            raise SystemExit(f"{raw['key']} is in Jira's removed list but its changelog has no removal "
                             f"from sprint {sprint_id}; inspect it before reporting")

    # Cross-checked against Jira's own sprint report, which buckets the same
    # issues independently: nothing is written on a discrepancy.
    in_scope, completed, removed = membership_sets(
        events_of, sprint_id, moment)
    problems = cross_check(report, in_scope, completed, removed, later_moves)
    if problems is None:
        raise SystemExit("Jira's sprint report is missing, so the scope can't be cross-checked; "
                         "no data written. Fetch the sprint again.")
    if problems:
        raise SystemExit("data differs from Jira's sprint report; no data written. Unless said otherwise "
                         "below, the sprint changed during the fetch: fetch it again.\n  - "
                         + "\n  - ".join(problems))

    spells, left_before_start, with_spells = [], [], []
    for raw in all_raw:
        events = events_of[raw["key"]]
        found = spells_from_events(raw, events, context, moment)
        if found:
            with_spells.append(raw["key"])
        spells += found
        if not found and any(move < 0 and when <= parse_ts(context.start_ts)
                             for when, move, _ in sprint_moves_of(events, sprint_id)):
            left_before_start.append(raw["key"])
    blocker_keys = blocker_candidates(events_of, sprint_id, moment)
    spells.sort(key=lambda t: (
        key_order(t["key"]), parse_ts(t["events"][0]["at"])))
    counted = [t for t in spells if t["counted"]]
    counts, points = outcome_breakdown(spells)
    epics = build_epics(spells, epic_descriptions(parents))
    # The pull requests of each ticket in the sprint at the end, the only
    # tickets whose status the report checks.
    pulls_of = {t["key"]: ticket_pulls(pull_requests, t["key"], moment) for t in counted
                if t["outcome"] != "descoped"}
    data = {
        "sprint_id": sprint["id"],
        "sprint_name": sprint.get("name"),
        "label": meta.get("label"),
        "base_url": meta.get("base_url"),
        "sprint_status": status,
        "sprint_goal": sprint.get("goal") or "",
        "sprint_start": start,
        "sprint_end": end,
        "sprint_complete_date": complete,
        # The moment the spells' events and fields run to: the close, or the fetch.
        "as_of_instant": moment,
        "report_timezone": zone.key,
        "today": today,
        "previous_sprint": previous and {
            "id": previous["id"], "name": previous.get("name"),
            "complete_instant": previous["completeDate"],
            "complete_date": sprint_date(previous["completeDate"], zone)},
        "spells": spells,
        # Each ticket's history as at the end: the spells are worked out from it.
        "ticket_events": {key: events_of[key] for key in sorted(with_spells, key=key_order)},
        # Issues that joined and left before the start: in no part of the report.
        "left_before_start_keys": sorted(left_before_start, key=key_order),
        "outcome_breakdown_counts": counts,
        "outcome_breakdown_points": points,
        "non_delivery_closures": non_delivery_closures(spells),
        "points_estimated_issue_count": sum(1 for t in counted if t["points"] is not None),
        "points_total_issue_count": len(counted),
        # Jira's current buckets cannot independently verify these issues'
        # historical membership, which is reconstructed from their changes.
        "membership_cross_check_excluded_keys": later_moves,
        "blocker_candidate_keys": blocker_keys,
        # Their comments as at the end, as plain text and without authors.
        "blocker_comments": blocker_comments(os.path.join(raw_dir, COMMENTS_DIR), blocker_keys, moment, zone),
        "target_completion": target_completion(spells),
        "epics": epics,
        # Each ticket's pull requests as at the end, as ticket_pulls() gives
        # them, and the rows of the Status to Verify section, worked out from
        # them.
        "ticket_pull_requests": {key: pulls_of[key] for key in sorted(pulls_of, key=key_order)},
        "status_checks": build_status_checks(spells, pulls_of, epics),
        "timeline": build_timeline(spells, status, start, end, complete, today),
        "burndown_baseline": burndown_baseline(spells),
        "burndown": build_burndown(spells, start, sprint_date(moment, zone), moment, zone),
    }
    out = os.path.join(args.report_dir, DATA_FILE)
    write_json(out, data)

    print(f"original commitment: {outcome_total(counts, 'original')} spell(s), "
          f"{counts['original_completed']} completed, {counts['original_not_completed']} not completed, "
          f"{counts['original_descoped']} descoped; extra: {outcome_total(counts, 'extra')} spell(s), "
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
