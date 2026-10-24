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
from datetime import date, datetime, time, timedelta, tzinfo

from common import (CHANGELOGS_DIR, COMMENTS_DIR, DATA_FILE, META_FILE, OUTCOME_ROWS, OUTCOMES, PARENTS_FILE,
                    PREVIOUS_SPRINT_FILE, PUNTED_ISSUES_FILE, RAW_DIR, SPRINT_FILE,
                    SPRINT_ISSUES_FILE, SPRINT_REPORT_FILE, STATUSES_FILE, SCOPE_GROUPS, add_and_remove_events, as_of,
                    in_sprint_at, history_fields, is_blocker_candidate, key_order, read_json, nested, outcome_total,
                    parse_ts, plain_text, points_value, report_timezone, spell_epic, split_ids, standard_issues,
                    status_categories, status_category, write_json)

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


class Context:
    """What every ticket is built with: the sprint and the previous one, the
    site's fields and statuses, the epics' names and the reporting timezone."""

    def __init__(self, sprint_id, start_ts, categories, fields, epic_names, reporting_zone: tzinfo,
                 previous):
        self.sprint_id, self.start_ts = sprint_id, start_ts
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


def ticket_events(raw, changes, context, moment):
    """A ticket's events up to `moment`, the end (the close, or the fetch for
    a running sprint), in time order: its creation, with each tracked field's
    value then, and every change of a tracked field. Later events are left
    out, never read as Jira shows the ticket today, so a report run later
    gives the same figures. They are kept per ticket, not per spell: a ticket
    has one history however often it left and came back. Changes at one
    instant keep the changelog's order."""
    cutoff, zone = parse_ts(moment), context.reporting_zone
    tracked = {name for name, ident in history_fields(
        context.flagged_field, context.points_field).items() if ident}
    mine = sorted((c for c in changes if c["field"] in tracked),
                  key=lambda c: parse_ts(c["created"]))
    category = status_category(raw, context.categories)
    events = [created_event(raw, mine, context, category)]
    events += [change_event(c, category, zone)
               for c in mine if parse_ts(c["created"]) <= cutoff]
    return sorted(events, key=lambda e: parse_ts(e["at"]))


def created_event(raw, changes, context, category):
    """The ticket's creation, with each tracked field's value then: the old
    value of its first change, else today's, since Jira logs no change for a
    value set at creation. Read from the whole changelog, later changes
    included: they are when Jira logged what the value was at creation."""
    fields = raw.get("fields") or {}
    today = {
        "status": (nested(fields, ["status", "id"]), nested(fields, ["status", "name"])),
        "resolution": (None, nested(fields, ["resolution", "name"])),
        "priority": (None, nested(fields, ["priority", "name"])),
        "parent": (nested(fields, ["parent", "id"]), nested(fields, ["parent", "key"])),
        "points": (None, fields.get(context.points_field) if context.points_field else None),
        "flagged": (None, fields.get(context.flagged_field) if context.flagged_field else None),
    }
    values = {"sprint": initial_sprints(changes, context.sprint_id)}
    for field, current in today.items():
        first = next((c for c in changes if c["field"] == field), None)
        ident, text = (first["from"], first["fromString"]
                       ) if first else current
        values |= {field: field_value(field, ident, text),
                   **field_extra(field, "", ident, category)}
    return ticket_event(fields.get("created"), "jira", "created", context.reporting_zone, values=values)


def initial_sprints(changes, sprint_id):
    """The sprints the ticket was in when it was created, as sorted ids: each
    sprint its changes name whose first move isn't an add (a removal comes
    first at one instant), and the reported sprint when no change names it,
    since it is in it now (see common.sprint_moves)."""
    named = {sprint_id}.union(*(split_ids(c["from"]) | split_ids(c["to"])
                                for c in changes if c["field"] == "sprint"))
    initial = []
    for sprint in named:
        added, removed = add_and_remove_events(changes, sprint)
        first = min([(parse_ts(t), 1) for t in added] +
                    [(parse_ts(t), -1) for t in removed], default=None)
        if first is None or first[1] < 0:
            initial.append(sprint)
    return field_value("sprint", ", ".join(initial), None)


def change_event(change, category, zone):
    """A change of a tracked field, from and to the values the report reads,
    named <field>_changed."""
    field = change["field"]
    return ticket_event(change["created"], "jira", f"{field}_changed", zone,
                        **{"from": field_value(field, change["from"], change["fromString"]),
                           "to": field_value(field, change["to"], change["toString"])},
                        **field_extra(field, "from", change["from"], category),
                        **field_extra(field, "to", change["to"], category))


def field_value(field, ident, text):
    """The value of a tracked field that the report reads, from a changelog's
    id and string: the sprint ids, the estimate as a number, whether it is
    flagged, and otherwise the name (an epic's key for the parent)."""
    if field == "sprint":
        return sorted(split_ids(ident), key=lambda i: (len(i), i))
    if field == "points":
        return points_value(text)
    if field == "flagged":
        return bool(text)
    return text or None


def field_extra(field, side, ident, category):
    """What a status or a parent adds to its value: the status's category,
    None for one Jira doesn't list, and the parent's id, which names the epic
    when its key changes. `side` is "from", "to", or "" for the creation."""
    if field == "status":
        return {f"{side}Category" if side else "statusCategory": category(ident)}
    if field == "parent":
        return {f"{side}Id" if side else "parentId": str(ident) if ident else None}
    return {}


def ticket_event(at, source, kind, zone, **extra):
    return {"at": at, "date": sprint_date(at, zone), "source": source, "type": kind, **extra}


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
                   else "not_completed") if inside else "removed"
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
            # Whether the final-situation figures count it: an extra spell
            # that ended with the ticket leaving was never part of the sprint.
            "counted": not (scope == "extra" and outcome == "removed"),
            "closedAsNonDelivery": (non_delivery_marker(state["status"], state["resolution"])
                                    if outcome == "completed" else None),
        })
    return spells


def sprint_moves_of(events, sprint_id):
    """The ticket's moves into (+1) and out of (-1) a sprint, as (instant,
    move, timestamp) in time order, from its events: its creation, if it was
    in the sprint then, and its sprint changes."""
    created = next(e for e in events if e["type"] == "created")
    moves = sorted([(parse_ts(e["at"]), 1 if sprint_id in e["to"] else -1, e["at"]) for e in events
                    if e["type"] == "sprint_changed" and (sprint_id in e["to"]) != (sprint_id in e["from"])])
    if sprint_id in created["values"]["sprint"]:
        moves.insert(0, (parse_ts(created["at"]), 1, created["at"]))
    return moves


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


def state_at(key, events, instant):
    """The ticket's tracked fields at `instant`, replayed from its events: its
    creation's values, then each change up to the instant. Fails on a status
    Jira's list of statuses doesn't hold, since its category is unknown."""
    values = dict(next(e["values"] for e in events if e["type"] == "created"))
    for e in events:
        field = e["type"].removesuffix("_changed")
        if e["source"] != "jira" or field in ("created", "sprint") or parse_ts(e["at"]) > instant:
            continue
        values[field] = e["to"]
        values |= {name: e[f"to{suffix}"] for name, suffix in (("statusCategory", "Category"), ("parentId", "Id"))
                   if f"to{suffix}" in e}
    if values["statusCategory"] is None:
        raise SystemExit(f"{key}: status {values['status']!r} is not in Jira's list of statuses; "
                         "fetch the sprint again")
    return {"status": values["status"], "statusCategory": values["statusCategory"],
            "resolution": values["resolution"], "storyPoints": values["points"], "flagged": values["flagged"],
            "priority": values["priority"] or "", "parentId": values["parentId"], "parentKey": values["parent"]}


def event(at, kind, points, done, zone, **extra):
    return {"at": at, "date": sprint_date(at, zone), "type": kind, "points": points, "done": done, **extra}


def sprint_date(ts, zone):
    """Calendar date of a timestamp in the reporting timezone, including its
    daylight-saving rules. An end at 00:00 names the day Jira shows, which
    teams read as the sprint's last day, included: an end of 00:00 on the
    8th means the sprint runs through the 8th."""
    if not ts:
        return None
    return parse_ts(ts).astimezone(zone).date().isoformat()


def non_delivery_marker(status, resolution):
    for value in ((status or "").lower(), (resolution or "").lower()):
        if value in NON_DELIVERY_MARKERS:
            return value
    return None


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


def non_delivery_closures(spells):
    """The counted spells completed as a non-delivery (Duplicate, Won't Do...):
    how many, their pts and each one's key, status, resolution, estimate,
    marker and summary."""
    closures = [s for s in spells if s["counted"] and s["closedAsNonDelivery"]]
    return {"count": len(closures), "points": sum(s["points"] or 0 for s in closures),
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
            "completed_points": sum(s["points"] or 0 for s in done),
            "total_points": sum(s["points"] or 0 for s in original)}


def build_epics(spells, descriptions=None):
    """Per-epic delivery of the counted spells: done is completed; the total
    adds not completed and descoped. Descoped original work is also counted
    apart. Each epic also carries its description and its spells sorted into
    the commentary's groups (see scope_group)."""
    descriptions = descriptions or {}
    epics = {}
    for spell in (s for s in spells if s["counted"]):
        key, name = spell_epic(spell)
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
        ticket = {"key": spell["key"], "scope": spell["scope"], "carriedIn": spell["carriedIn"],
                  "points": spell["points"], "status": spell["status"],
                  "flagged": spell["flagged"], "summary": spell["summary"],
                  "description": spell["description"]}
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


def scope_group(spell):
    """(the commentary group of a counted spell, or None, why it is left out).
    Work the sprint didn't do is left out: Duplicates, Won't Do, and work
    already Done when its spell began that stayed in the sprint. The figures
    still count it, but the AI text mustn't describe it. Descoped work is
    always described as descoped, even if it was already Done, since the
    figures count it as descoped."""
    if spell["outcome"] == "removed":
        return "descoped", None
    if spell["outcome"] == "not_completed":
        return ("in_review" if "review" in (spell["status"] or "").lower() else "not_completed"), None
    if spell["closedAsNonDelivery"]:
        return None, "non_delivery"
    if not any(e["type"] == "completed" for e in spell["events"]):
        return None, "done_at_start"
    return "completed", None


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


def build_burndown(spells, start_date, last_date, moment, zone):
    """Open tickets and pts at the end of each local day, from the
    events of every spell, counted or not: the original commitment's, and with
    the extra work's too.
    The closing day stops at the exact close, an active snapshot's current day
    at the fetch."""
    rows = []
    day, end = date.fromisoformat(start_date), date.fromisoformat(last_date)
    while day <= end:
        cutoff = min(datetime.combine(
            day, time.max, tzinfo=zone), parse_ts(moment))
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


def blocker_candidates(events_of, sprint_id, moment):
    """The keys of the tickets in the sprint at the cutoff that were flagged,
    blocked or high priority and not done then (common.is_blocker_candidate),
    from their events (`events_of`, {key: ticket_events()}), in its order:
    the tickets whose comments the fetch read, as it picks them from the
    changelogs by the same rule."""
    cutoff, keys = parse_ts(moment), []
    for key, events in events_of.items():
        if not in_sprint_at(sprint_moves_of(events, sprint_id), cutoff):
            continue
        then = state_at(key, events, cutoff)
        if is_blocker_candidate(then["flagged"], then["status"], then["statusCategory"], then["priority"]):
            keys.append(key)
    return keys


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
    # The pull request data (PULL_REQUESTS_FILE) is fetched for a later use:
    # nothing reads it yet.
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
    original = [t for t in spells if t["scope"] == "original"]

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
        "epics": build_epics(spells, epic_descriptions(parents)),
        "timeline": build_timeline(spells, status, start, end, complete, today),
        # The burndown's first point: the whole commitment at the start, Done or
        # not; the start day's end-of-day reading then shows what was open.
        "burndown_baseline": sum(t["events"][0]["points"] or 0 for t in original),
        "burndown": build_burndown(spells, start, sprint_date(moment, zone), moment, zone),
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
