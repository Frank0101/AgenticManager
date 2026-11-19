"""Check a finished sprint report against the data it was built from and
against the report's formatting rules.

It shares only the format helpers and constants with make_report.py, recomputes
every figure from the spells' events, and reads a stored fact only once a check
here has verified it against the events, so a generator bug can't pass by
agreeing with itself. Every rule here exists because a table drifted when corrected by hand:
prose guidance didn't stop it, a failing check does.
"""
import argparse
import html
import os
import re
import sys
from datetime import date

from common import (folder_problem, days, BLOCKED_STATUSES, GOAL_VERDICTS, HIGH_PRIORITIES, CHARTS_DIR, CHART_IMAGE, HEADING, INLINE_LINK, SENTENCE_BREAK, link_text, BANNED_WORDS, expected_files, CHART_FILES, COMMENTARY_WORDS, DATA_FILE, FIELD_HEADER, ISSUE_KEY,
                    BOLD_RULE, DATE_RULE, ESTIMATE_RULE, FORMAT_RULES, GITHUB_CELL, JIRA_CELL, KEY_LIST, LEFT_OUT_REASONS, LIST_RULE,
                    EPICS_HEADING, METRICS_HEADING, NOTHING_TO_VERIFY, NOTHING_UNTRACKED, RETRO_HEADING, STATUS_HEADING, TIMELINE_HEADING, UNTRACKED_HEADING, UNTRACKED_OPEN_PULLS, UNTRACKED_SUBTITLE,
                    TICKET_ESTIMATE,
                    TICKET_EVENT_TYPES,
                    NO_EPIC, OUTCOME_ROWS, OUTCOMES, ai_marked, no_work_text, sprint_key, text_rule_problems,
                    display_date, epic_groups, estimate, key_order, known_sum, read_json, parse_ts, plural, pts, qty,
                    ratio, report_file, report_timezone, repository_url, scope_group_label, spell_epic, whole_percentage, word_count)


# The event kinds of a spell.
EVENT_KINDS = {"committed", "joined", "completed",
               "reopened", "reestimated", "removed"}

# What each kind of ticket event holds besides its instant, date, source and type.
TICKET_EVENT_FIELDS = {"created": ("values",), "status_changed": ("from", "to", "fromCategory", "toCategory"),
                       "parent_changed": ("from", "to", "fromId", "toId")}

# The values a ticket's creation holds, one per tracked field and the status's
# category and the parent's id.
CREATED_VALUES = {"sprint", "status", "statusCategory", "resolution", "priority", "parent", "parentId", "points",
                  "flagged"}

# The rows of the report's field tables, in order: the table at the top, then
# the one under Sprint Metrics.
HEADER_LABELS = ["Dates", "Goal", ai_marked("Goal outcome"), ai_marked("Key Achievements"),
                 ai_marked("Blockers & Risks"), "Sprint target completion"]


# The report's title line, plain text the checks set apart from the rest.
TITLE = re.compile(r"^# Sprint Summary:.*$", re.M)
# The commentary's caveats, which its word limit doesn't count.
CAVEATS = ("resolved without delivery",
           "is reconstructed from changelogs")


def check_report(report_dir):
    """Every check of the report in `report_dir`, against its data.json: the
    Checker holding what passed and what failed."""
    data = read_json(os.path.join(report_dir, DATA_FILE))
    with open(os.path.join(report_dir, report_file(data["label"])), encoding="utf-8") as f:
        md = f.read()
    return run_checks(md, data, report_dir)


def run_checks(md, data, report_dir):
    """Every check of the report `md`, built from `data`, in `report_dir`:
    the Checker holding what passed and what failed."""
    tables = {table_kind(t): t for t in html_tables(md)}
    c = Checker()
    check_model(c, data)
    check_header(c, md, data)
    check_commentary(c, md, data)
    check_framing(c, md)
    check_images(c, md, report_dir)
    check_files(c, report_dir, data)
    check_timeline(c, tables.get("timeline"), data)
    check_epics(c, tables.get("epics"), data)
    check_untracked_section(c, md, tables.get("untracked"), data)
    check_status_section(c, md, tables.get("status"), data)
    check_style(c, md, data)
    check_vocabulary(c, md, data)
    return c


class Checker:
    """The checks' results: what passed and what failed, each named."""

    def __init__(self):
        self.failures, self.passes = [], []

    def check(self, ok, name, detail):
        (self.passes if ok else self.failures).append(f"{name}: {detail}")
        return ok

    def report(self):
        """Print every check, then the summary; returns the exit code, 1 if
        any failed."""
        for line in self.passes:
            print(f"  ok    {line}")
        for line in self.failures:
            print(f"  FAIL  {line}")
        print()
        print(self.summary())
        return 1 if self.failures else 0

    def summary(self):
        """How many checks failed, or that all passed."""
        if self.failures:
            return f"{len(self.failures)} check(s) failed"
        return f"all {len(self.passes)} checks passed"


def html_tables(md):
    return re.findall(r"<table.*?</table>", md, re.S)


def table_kind(table):
    if rows_of(table)[0] == FIELD_HEADER:
        return "fields"
    header = strip_tags(rows_of(table)[0]).lower()
    if "date" in header and "events" in header and "end of day" in header:
        return "timeline"
    if "epic" in header and "commentary" in header:
        return "epics"
    if "repository" in header and "pull requests" in header:
        return "untracked"
    if "ticket" in header and "pull requests" in header:
        return "status"
    return None


def rows_of(table):
    return re.findall(r"<tr\b[^>]*>(.*?)</tr>", table, re.S)


def strip_tags(text):
    return re.sub(r"<[^>]+>", " ", text).strip()


def check_model(c, data):
    """Each spell's events are well formed, and its outcome, latest estimate
    and whether it's counted are what its events give; the charts' breakdown
    and its totals, the non-delivery closures, the ticket counts, the
    burndown, the timeline, the commentary's scope changes, and the epics'
    commentary groups, left-out counts and completed pts are built from the
    same spells."""
    seen_keys = set()
    for t in data["spells"]:
        events, key = t["events"], t["key"]
        kinds = [e["type"] for e in events]
        c.check(bool(events) and kinds[0] == ("committed" if t["scope"] == "original" else "joined")
                and all(k in EVENT_KINDS for k in kinds)
                and all(k not in ("committed", "joined") for k in kinds[1:]) and "removed" not in kinds[:-1]
                and (t["scope"] == "extra" or key not in seen_keys),
                "model", f"{key}'s events are well formed ({', '.join(kinds)})")
        flags = {"doneAtStart": bool(events and events[0]["done"]), "reopened": "reopened" in kinds,
                 "reestimated": "reestimated" in kinds, "cameBack": key in seen_keys,
                 "firstEstimate": events[0]["points"] if events else None}
        c.check(all(t[name] == value for name, value in flags.items()), "model",
                f"{key}'s doneAtStart, reopened, reestimated and cameBack flags and first estimate are what its "
                "events give")
        seen_keys.add(key)
        done, flips = events[0]["done"] if events else False, True
        for e in events[1:]:
            if e["type"] in ("completed", "reopened"):
                flips = flips and e["done"] == (
                    e["type"] == "completed") != done
            done = e["done"]
        outcome = "descoped" if kinds and kinds[-1] == "removed" else (
            "completed" if done else "not_completed")
        counted = not (t["scope"] == "extra" and outcome == "descoped")
        c.check(flips and t["outcome"] == outcome and t["counted"] == counted
                and t["points"] == (events[-1]["points"] if events else None),
                "model", f"{key} ends {outcome}{'' if counted else ', not counted'}, as its events give")

    estimates = {}
    for t in (t for t in data["spells"] if t["counted"]):
        rows = ["extra"] if t["scope"] == "extra" else [
            "original", "carried_in" if t["carriedIn"] else "new"]
        for row in rows:
            estimates.setdefault(
                f"{row}_{t['outcome']}", []).append(t["points"])
    for row in OUTCOME_ROWS:
        for outcome in OUTCOMES:
            got = (data["outcome_breakdown_counts"][f"{row}_{outcome}"],
                   data["outcome_breakdown_points"][f"{row}_{outcome}"])
            found = estimates.get(f"{row}_{outcome}", [])
            c.check(got == (len(found), known_sum(found)), "model",
                    f"the charts' {row} {outcome.replace('_', ' ')} is the counted spells' {qty(*got)}")
    in_row = {row: [p for outcome in OUTCOMES for p in estimates.get(f"{row}_{outcome}", [])]
              for row in OUTCOME_ROWS}
    in_row["all"] = in_row["original"] + in_row["extra"]
    c.check((data["outcome_totals_counts"], data["outcome_totals_points"])
            == ({row: len(found) for row, found in in_row.items()},
                {row: known_sum(found) for row, found in in_row.items()}), "model",
            "the charts' totals per row, and of the commitment and the extra together, are the counted spells'")

    counted = [t for t in data["spells"] if t["counted"]]
    closures = [t for t in counted
                if t["outcome"] == "completed" and t["closedAsNonDelivery"]]
    c.check(data["non_delivery_closures"] == {
        "count": len(closures), "points": known_sum(t["points"] for t in closures),
        "keys": sorted({t["key"] for t in closures}, key=key_order),
        "issues": [{"key": t["key"], "status": t["status"], "resolution": t["resolution"],
                    "storyPoints": t["points"], "marker": t["closedAsNonDelivery"], "summary": t["summary"]}
                   for t in closures]}, "model",
            "the non-delivery closures are the counted spells completed without delivery")
    c.check((data["points_estimated_issue_count"], data["points_total_issue_count"])
            == (sum(1 for t in counted if t["points"] is not None), len(counted)), "model",
            "the estimated and total ticket counts are the counted spells'")

    original = [t for t in data["spells"] if t["scope"] == "original"]
    done = [t for t in original if t["outcome"] == "completed"]
    c.check(data["target_completion"] == {
        "completed": len(done), "total": len(original),
        "completed_points": known_sum(t["points"] for t in done),
        "total_points": known_sum(t["points"] for t in original)}, "model",
        "the sprint target is the original commitment's spells, and those completed")
    baseline = known_sum(t["events"][0]["points"] for t in original)
    c.check(data["burndown_baseline"] == baseline, "model",
            f"the burndown starts at the whole commitment, {estimate(baseline)}")
    first = date.fromisoformat(data["sprint_start"])
    last = parse_ts(data["as_of_instant"]).astimezone(
        report_timezone(data["report_timezone"])).date()
    expected_dates = [day.isoformat() for day in days(first, last)]
    c.check([row["date"] for row in data["burndown"]] == expected_dates, "model",
            "the burndown covers every day from the sprint start through the report cutoff, in order")
    for row in data["burndown"]:
        committed, total = [], []
        for t in data["spells"]:
            seen = [e for e in t["events"] if e["date"] <= row["date"]]
            if seen and seen[-1]["type"] != "removed" and not seen[-1]["done"]:
                total.append(seen[-1]["points"])
                if t["scope"] == "original":
                    committed.append(seen[-1]["points"])
        c.check((row["committed"], row["total"], row["committed_stories"], row["total_stories"])
                == (known_sum(committed), known_sum(total), len(committed), len(total)), "model",
                f"the burndown on {display_date(row['date'])} is the spells' open tickets and pts")

    logged = sorted((e["key"], e["type"], row["date"])
                    for row in data["timeline"] for e in row["events"])
    replayed = sorted((t["key"], e["type"], e["date"])
                      for t in data["spells"] for e in t["events"])
    c.check(logged == replayed, "model",
            "the timeline holds exactly the spells' events")
    latest = latest_estimates(data)
    c.check(data["latest_points"] == latest, "model",
            "each ticket's latest estimate is its last spell's, as its events give")
    excluded = data["membership_cross_check_excluded"]
    keys = excluded["keys"]
    c.check(excluded == {"count": len(keys), "points": known_sum(latest.get(k) for k in keys),
                         "keys": sorted(set(keys), key=key_order)}, "model",
            "the membership caveat counts its tickets, sorted, at their latest estimates")
    c.check(data["scope_changes"] == scope_change_figures(data), "model",
            "the commentary's scope changes are the spells' that their events give")
    check_commentary_groups(c, data)
    check_epic_points(c, data)
    check_ticket_events(c, data)
    check_pull_requests(c, data)
    check_untracked_pulls(c, data)
    check_burndown_ideal(c, data)
    check_goal_facts(c, data)
    check_carried_in(c, data)
    check_blocker_candidates(c, data)


def check_epic_points(c, data):
    """Each epic's completed pts are its completed spells' estimates, by the
    estimates rule."""
    figures = epic_figures(data)
    for epic in data["epics"]:
        done_points = known_sum(scope[2] for scope in figures.get(
            epic["key"], {}).values() if scope[0])
        c.check(epic["points_done"] == done_points, "model",
                f"{epic['key']}'s completed pts are its completed spells' {pts(done_points)}")


def check_commentary_groups(c, data):
    """Each epic's commentary groups, and the work left out of them with
    why, hold the counted spells their outcomes and events give."""
    expected = commentary_groups(data)
    for epic in data["epics"]:
        stored = {group: [t["key"] for t in tickets]
                  for group, tickets in epic["scope_groups"].items() if tickets}
        for t in epic["left_out"]:
            stored.setdefault(t["reason"], []).append(t["key"])
        c.check(stored == expected.get(epic["key"], {}), "model",
                f"{epic['key']}'s commentary groups hold the tickets their outcomes give")
        left_out = {reason: len(expected.get(epic["key"], {}).get(reason, []))
                    for reason in LEFT_OUT_REASONS}
        c.check(epic["left_out_counts"] == left_out, "model",
                f"{epic['key']}'s left-out counts are its tickets' that their outcomes give")


def latest_estimates(data):
    """{key: pts} of each ticket's latest estimate, recomputed from the last
    event of its last spell."""
    return {s["key"]: s["events"][-1]["points"] for s in data["spells"]}


def scope_change_figures(data):
    """{change: {count, points, keys}} of the ways the sprint departed from
    the ideal one, recomputed from the spells' events: the commitment's work
    already Done when committed, at its first estimate, and removed; the extra
    work that stayed, with how much is unestimated, and that was removed; the
    reopened and re-estimated spells, the latter with their first estimates;
    and the spells that joined after an earlier spell of their ticket."""
    spells = data["spells"]
    original = [s for s in spells if s["events"][0]["type"] == "committed"]
    joined = [s for s in spells if s["events"][0]["type"] == "joined"]

    def removed(s):
        return s["events"][-1]["type"] == "removed"

    def kinds(s):
        return {e["type"] for e in s["events"]}

    def group(found, first=False):
        return {"count": len(found),
                "points": known_sum(s["events"][0 if first else -1]["points"] for s in found),
                "keys": sorted({s["key"] for s in found}, key=key_order)}
    extra = [s for s in joined if not removed(s)]
    reestimated = [s for s in spells if "reestimated" in kinds(s)]
    return {
        "done_at_start": group([s for s in original if s["events"][0]["done"]], first=True),
        "descoped": group([s for s in original if removed(s)]),
        "extra": {**group(extra), "unestimated": sum(1 for s in extra if s["events"][-1]["points"] is None)},
        "dropped": group([s for s in joined if removed(s)]),
        "reopened": group([s for s in spells if "reopened" in kinds(s)]),
        "reestimated": {**group(reestimated), "first_points": group(reestimated, first=True)["points"]},
        "came_back": group([s for i, s in enumerate(spells) if s in joined
                            and any(o["key"] == s["key"] for o in spells[:i])]),
    }


def commentary_groups(data):
    """{epic key: {group: [ticket keys]}}, recomputed from the counted
    spells: descoped work is always described, and completed work only if
    the sprint did it, the rest under one of LEFT_OUT_REASONS."""
    expected = {}
    for t in (t for t in data["spells"] if t["counted"]):
        if t["outcome"] == "descoped":
            group = "descoped"
        elif t["outcome"] == "not_completed":
            group = "in_review" if "review" in (
                t["status"] or "").lower() else "not_completed"
        elif t["closedAsNonDelivery"]:
            group = "non_delivery"
        elif not any(e["type"] == "completed" for e in t["events"]):
            group = "done_at_start"
        else:
            group = "completed"
        epic = expected.setdefault(spell_epic(t)[0], {})
        epic.setdefault(group, []).append(t["key"])
    return expected


def check_ticket_events(c, data):
    """Each ticket with a spell, and no other, has its events, well formed,
    dated, as at the end and in time order; and its spells' events are what
    its events give. The spells are worked out from those events, so the
    checker replays them on their own, with its own membership and state
    rules, and fails a spell event they don't give, or one they give that a
    spell misses."""
    tickets = data["ticket_events"]
    c.check(set(tickets) == {s["key"] for s in data["spells"]}, "model",
            "every ticket with a spell has its events, and no other ticket")
    zone, cutoff = report_timezone(
        data["report_timezone"]), parse_ts(data["as_of_instant"])
    for key, events in tickets.items():
        problems = ticket_event_problems(events, zone, cutoff)
        c.check(not problems, "model",
                f"{key}'s ticket events are well formed, dated and as at the end {problems[:2] or ''}".strip())
        if problems:
            continue
        instants = [parse_ts(e["at"]) for e in events]
        c.check(instants == sorted(instants), "model",
                f"{key}'s ticket events are in time order")
    sprint_id, sound = str(data["sprint_id"]), sound_events(data)
    for spell in data["spells"]:
        if spell["key"] not in sound:
            continue
        wrong = spell_event_problems(
            spell, sound[spell["key"]], sprint_id, cutoff)
        c.check(not wrong, "model",
                f"{spell['key']}'s spell events are what its ticket events give {wrong[:2] or ''}".strip())


def ticket_event_problems(events, zone, cutoff):
    """What is wrong with a ticket's events, as short descriptions: an
    unknown source or type, a missing field, a date that isn't its instant's
    in the reporting timezone, an instant after the end, or not exactly one
    creation."""
    problems = []
    for e in events:
        kind = e.get("type")
        if kind not in TICKET_EVENT_TYPES.get(e.get("source"), ()):
            problems.append(f"{e.get('source')} {kind}")
            continue
        fields = TICKET_EVENT_FIELDS.get(kind, ("from", "to"))
        missing = [f for f in ("at", "date", *fields) if f not in e]
        if missing:
            problems.append(f"{kind} without {', '.join(missing)}")
        elif parse_ts(e["at"]).astimezone(zone).date().isoformat() != e["date"]:
            problems.append(f"{kind} at {e['at']} dated {e['date']}")
        elif parse_ts(e["at"]) > cutoff:
            problems.append(f"{kind} after the end")
        elif kind == "created" and set(e["values"]) != CREATED_VALUES:
            problems.append("created without each tracked field's value")
    kinds = [e.get("type") for e in events]
    if kinds.count("created") != 1:
        problems.append(f"{kinds.count('created')} creations")
    return problems


def spell_event_problems(spell, events, sprint_id, cutoff):
    """The events of a spell its ticket's events don't give, as 'type at
    instant', and 'end' if the spell, still in the sprint at the end, doesn't
    end in the ticket's state then."""
    wrong = []
    for e in spell["events"]:
        at = parse_ts(e["at"])
        same = {t["type"] for t in events if parse_ts(t["at"]) == at}
        moves = {move for when, move in sprint_changes(
            events, sprint_id) if when == at}
        given = {"committed": in_sprint(events, sprint_id, at),
                 "joined": in_sprint(events, sprint_id, at) and (1 in moves or "created" in same),
                 "removed": -1 in moves,
                 "completed": "status_changed" in same,
                 "reopened": "status_changed" in same,
                 "reestimated": "points_changed" in same}.get(e["type"], False)
        if not given or ticket_state(events, at) != (e["done"], e["points"]):
            wrong.append(f"{e['type']} at {e['at']}")
    last = spell["events"][-1]
    if last["type"] != "removed" and (not in_sprint(events, sprint_id, cutoff)
                                      or ticket_state(events, cutoff) != (last["done"], last["points"])):
        wrong.append("end")
    return wrong


def sprint_changes(events, sprint_id):
    """(instant, +1 or -1) of each change of the ticket's sprints that adds it
    to the sprint or removes it, in time order, a removal first at one
    instant."""
    return sorted((parse_ts(e["at"]), 1 if sprint_id in e["to"] else -1) for e in events
                  if e["type"] == "sprint_changed" and (sprint_id in e["to"]) != (sprint_id in e["from"]))


def in_sprint(events, sprint_id, instant):
    """Whether the ticket was in the sprint at `instant`: from its creation if
    it was in it then, then as each sprint change up to the instant leaves it."""
    created = next(e for e in events if e["type"] == "created")
    inside = sprint_id in created["values"]["sprint"] and parse_ts(
        created["at"]) <= instant
    for when, move in sprint_changes(events, sprint_id):
        if when > instant:
            break
        inside = move > 0
    return inside


def ticket_state(events, instant):
    """(Done, estimate) of the ticket at `instant`, from its fields then."""
    fields = ticket_fields(events, instant)
    return fields["statusCategory"] == "done", fields["points"]


def check_pull_requests(c, data):
    """Each ticket in the sprint at the end, and no other, has its pull
    requests, each opened by the end, its merge and closing left out after
    it, and its ownership and state what its title, branch and times give,
    naming a ticket only by a key of the sprint's projects;
    and the Status to Verify rows are the tickets those and their statuses
    flag (not started with work, Done with one open), recomputed here with
    the checker's own rules."""
    cutoff = parse_ts(data["as_of_instant"])
    present = {s["key"]: s for s in data["spells"]
               if s["counted"] and s["outcome"] != "descoped"}
    pulls_of = data["ticket_pull_requests"]
    keys = sprint_key(data)
    c.check(set(pulls_of) == set(present), "model",
            "every ticket in the sprint at the end has its pull requests, and no other ticket")
    for key, pulls in pulls_of.items():
        wrong = []
        for pr in pulls:
            named = set(keys.findall(pr["title"] + " " + pr["branch"]))
            own = not named or key in named or pr["via"] in named
            state = "merged" if pr["mergedAt"] else "declined" if pr["closedAt"] else "open"
            in_time = parse_ts(pr["createdAt"]) <= cutoff and all(
                not pr[f] or parse_ts(pr[f]) <= cutoff for f in ("mergedAt", "closedAt"))
            if pr["own"] != own or pr["state"] != state or not in_time:
                wrong.append(pr["url"])
        c.check(not wrong, "model",
                f"{key}'s pull requests are as at the end, with the ownership and state they give {wrong[:2] or ''}"
                .strip())
    expected = []
    for key, spell in present.items():
        own = [pr for pr in pulls_of.get(key, []) if pr["own"]]
        states = [pr["state"] for pr in own]
        flag = None
        if spell["statusCategory"] == "new" and ("open" in states or "merged" in states):
            flag = "work_started"
        elif spell["statusCategory"] == "done" and "open" in states:
            flag = "open_after_done"
        if flag:
            every = [pr["state"] for pr in pulls_of.get(key, [])]
            expected.append((key, spell_epic(spell)[0], spell["status"], flag, states.count("open"),
                             every.count("merged"), every.count(
                                 "open"), every.count("declined"),
                             len(every) - len(states)))
    stored = [(r["key"], r["epicKey"], r["status"], r["flag"], r["ownOpen"], r["linked"]["merged"],
               r["linked"]["open"], r["linked"]["declined"], r["otherTickets"]) for r in data["status_checks"]]
    c.check(sorted(stored) == sorted(expected), "model",
            f"the Status to Verify rows are the tickets their pull requests and statuses flag ({len(expected)})")
    order = {e["key"]: i for i, e in enumerate(data["epics"])}
    c.check([r["key"] for r in data["status_checks"]] == [r["key"] for r in sorted(
        data["status_checks"], key=lambda r: (order.get(r["epicKey"], len(order)), key_order(r["key"])))],
        "model", "the Status to Verify rows are in the epics' order, then by key")


def check_burndown_ideal(c, data):
    """The burndown's ideal runs from the start through the planned end or
    the last reading, whichever is later, holding on the start day and at
    weekends and burning the baseline evenly over the later weekdays to the
    planned end; each reading's spread is the commitment open minus it."""
    first, end = date.fromisoformat(
        data["sprint_start"]), date.fromisoformat(data["sprint_end"])
    last = max(end, date.fromisoformat(data["burndown"][-1]["date"]))
    every = days(first, last)
    pace = [day for day in every if first < day <= end and day.weekday() < 5]
    level = data["burndown_baseline"] or 0
    expected = [(day.isoformat(), day.weekday() >= 5,
                 level * (len(pace) - sum(1 for p in pace if p <= day)) / len(pace) if pace else level)
                for day in every]
    stored = [(row["date"], row["weekend"], row["ideal"])
              for row in data["burndown_ideal"]]
    c.check(data["burndown_weekdays"] == len(pace) and len(stored) == len(expected)
            and all(s[:2] == e[:2] and abs(s[2] - e[2]) <= 0.01 for s, e in zip(stored, expected)), "model",
            f"the burndown's ideal burns {estimate(data['burndown_baseline'])} over {len(pace)} later weekdays")
    ideal = {day: value for day, _, value in expected}
    wrong = [row["date"] for row in data["burndown"]
             if abs(row["spread"] - ((row["committed"] or 0) - ideal.get(row["date"], 0))) > 0.01]
    c.check(not wrong, "model",
            f"each burndown reading's spread is its open commitment minus the ideal {wrong[:2] or ''}".strip())


def check_goal_facts(c, data):
    """The goal verdicts offered are the sprint's: none to choose without a
    goal, the closed ones at the close, and while it runs, only too early to
    tell before its halfway day; and a running sprint's days left are to its
    planned end."""
    start, end, today = (date.fromisoformat(data[k])
                         for k in ("sprint_start", "sprint_end", "today"))
    running = data["sprint_status"] == "active"
    if not data["sprint_goal"].strip():
        kind = "no_goal"
    elif not running:
        kind = "closed"
    else:
        kind = "early" if (
            today - start).days < (end - start).days // 2 else "active"
    c.check(data["goal_verdicts"] == list(GOAL_VERDICTS[kind]), "model",
            f"the goal verdicts offered are {GOAL_VERDICTS[kind]}")
    left = (end - today).days if running else None
    c.check(data["days_left"] == left, "model",
            f"the days left are {left}, to the planned end" if running else "a closed sprint has no days left")


def check_carried_in(c, data):
    """A spell of the commitment is carried over exactly when its ticket was
    in the previous sprint at the instant that sprint closed, by its events."""
    previous, sound = data["previous_sprint"], sound_events(data)
    wrong = []
    for spell in data["spells"]:
        events = sound.get(spell["key"])
        if events is None:
            continue
        carried = bool(previous) and spell["scope"] == "original" and in_sprint(
            events, str(previous["id"]), parse_ts(previous["complete_instant"]))
        if spell["carriedIn"] != carried:
            wrong.append(spell["key"])
    c.check(not wrong, "model",
            f"the carried-over tickets are those in the previous sprint when it closed {wrong[:3] or ''}".strip())


def check_blocker_candidates(c, data):
    """The blocker candidates are the tickets in the sprint at the end that
    were then flagged, in a blocked status, or high priority and not Done,
    by their events; a ticket whose events are malformed is
    check_ticket_events' failure, so it is left out here."""
    sprint_id, cutoff = str(data["sprint_id"]), parse_ts(data["as_of_instant"])
    sound, expected = sound_events(data), []
    for key, events in sound.items():
        if not in_sprint(events, sprint_id, cutoff):
            continue
        fields = ticket_fields(events, cutoff)
        if (fields["flagged"] or (fields["status"] or "").lower() in BLOCKED_STATUSES
                or (fields["statusCategory"] != "done" and (fields["priority"] or "").lower() in HIGH_PRIORITIES)):
            expected.append(key)
    stored = [key for key in data["blocker_candidate_keys"]
              if key in sound or key not in data["ticket_events"]]
    c.check(sorted(stored, key=key_order) == sorted(expected, key=key_order), "model",
            f"the blocker candidates are the tickets flagged, blocked or high priority at the end "
            f"{sorted(expected, key=key_order)}")


def sound_events(data):
    """{key: its events} of each ticket whose events are well formed, which
    the checks replaying them can read."""
    zone, cutoff = report_timezone(
        data["report_timezone"]), parse_ts(data["as_of_instant"])
    return {key: events for key, events in data["ticket_events"].items()
            if not ticket_event_problems(events, zone, cutoff)}


def ticket_fields(events, instant):
    """The ticket's tracked fields at `instant`: its creation's values, then
    each change's new value up to the instant, the status's with its
    category."""
    values = dict(next(e for e in events if e["type"] == "created")["values"])
    for e in events:
        field = e["type"].removesuffix("_changed")
        if e["type"] == "created" or field == "sprint" or parse_ts(e["at"]) > instant:
            continue
        values[field] = e["to"]
        if field == "status":
            values["statusCategory"] = e["toCategory"]
    return values


def check_header(c, md, data):
    rows = header_rows(md)
    if not c.check(rows is not None, "header", "table at the top found") or rows is None:
        return
    labels = [label for label, _ in rows]
    if not c.check(labels == HEADER_LABELS, "header", f"rows are exactly {HEADER_LABELS} (got {labels})"):
        return
    values = dict(rows)

    dates = f"{display_date(data['sprint_start'])}–{display_date(data['sprint_end'])}"
    if data["sprint_complete_date"] and data["sprint_complete_date"] != data["sprint_end"]:
        dates += f" (completed {display_date(data['sprint_complete_date'])})"
    c.check(values["Dates"] == dates, "header", f"Dates is {dates!r}")

    goal = values["Goal"]
    shown = re.sub(
        r'<a href="[^"]*">(' + ISSUE_KEY.pattern + r")</a>", r"\1", goal)
    lines = [line.strip()
             for line in data["sprint_goal"].splitlines() if line.strip()]
    expected_goal = "<br>".join(html.escape(line, quote=False)
                                for line in lines) if lines else "<i>No goal was set in Jira for this sprint</i>"
    c.check(shown == expected_goal, "header",
            "Goal is Jira's goal, one line per <br>")

    original_spells = [t for t in data["spells"] if t["scope"] == "original"]
    done = [t for t in original_spells if t["outcome"] == "completed"]
    so_far = " so far" if data["sprint_status"] == "active" else ""
    target = "No commitment" if not original_spells else (
        f"{whole_percentage(len(done), len(original_spells))}, "
        + ratio(len(done), len(original_spells), known_sum(t["points"] for t in done),
                known_sum(t["points"] for t in original_spells))
        + f" completed{so_far}")
    c.check(values["Sprint target completion"] == target,
            "header", f"Sprint target completion is {target!r}")
    metrics = md.split(f"## {METRICS_HEADING}\n\n", 1)
    first = html_tables(metrics[1])[:1] if len(metrics) == 2 else []
    c.check(bool(first) and metrics[1].startswith(first[0]) and table_kind(first[0]) == "fields"
            and [label for label, _ in field_rows(first[0])] == ["Sprint target completion"],
            "header", "Sprint target completion is a table of its own under Sprint Metrics")


def header_rows(md):
    """[(label, value)] of the report's tables of fields, the one at the top
    and the one under Sprint Metrics, in order, or None if there are none."""
    tables = [t for t in html_tables(md) if table_kind(t) == "fields"]
    return [row for table in tables for row in field_rows(table)] if tables else None


def field_rows(table):
    """[(label, value)] of a table of fields' rows below its headings; a row
    that isn't 2 cells as (its HTML, None)."""
    rows = []
    for row in rows_of(table)[1:]:
        cells = [content for _, content in cells_with_attributes(row)]
        rows.append((cells[0], cells[1]) if len(cells) == 2 else (row, None))
    return rows


def cells_with_attributes(row):
    """[(attributes, content)] of a row's <td> or <th> cells."""
    return re.findall(r"<t[dh]\b([^>]*)>(.*?)</t[dh]>", row, re.S)


def check_commentary(c, md, data):
    """The timeline's commentary states, from the spells, every way the sprint
    departed from the ideal and no other, within the word limit before its
    caveats, and the caveats whenever they apply."""
    text = commentary_of(md)
    if not c.check(text is not None, "commentary", "the timeline is followed by its commentary") or text is None:
        return
    sentences = SENTENCE_BREAK.split(text)
    core = " ".join(s for s in sentences if not any(m in s for m in CAVEATS))
    c.check(word_count(core) <= COMMENTARY_WORDS, "commentary",
            f"at most {COMMENTARY_WORDS} words before its caveats (got {word_count(core)})")
    spells, changes = data["spells"], scope_change_figures(data)
    original = [s for s in spells if s["scope"] == "original"]
    committed = qty(len(original), data["burndown_baseline"])
    c.check((f"{committed} in the commitment" if original else "Nothing was committed at the start") in text,
            "commentary", f"states the commitment, {committed}" if original else "states that nothing was committed")
    for kind, group in (("descoped", changes["descoped"]), ("added as extra", changes["extra"])):
        if group["count"] > 1:
            amount = qty(group["count"], group["points"])
            c.check(f"{amount} {plural(group['count'], 'was', 'were')} {kind}" in text,
                    "commentary", f"states {amount} {kind}")
    departures = [
        ("already Done at the start", r"already Done at the start", "done_at_start"),
        ("descoped from the commitment", r"\b(?:was|were) descoped", "descoped"),
        ("added as extra", r"\b(?:was|were) added as extra", "extra"),
        ("added and descoped again", r"added and descoped again", "dropped"),
        ("reopened", r"\breopened\b", "reopened"),
        ("re-estimated", r"\bre-estimated\b", "reestimated"),
        ("left and came back", r"left the sprint and came back", "came_back"),
    ]
    for name, pattern, change in departures:
        happened = changes[change]["count"] > 0
        c.check(bool(re.search(pattern, core)) == happened, "commentary",
                f"{'mentions' if happened else 'does not mention'} {name}")
    open_spells = [s for s in spells if s["counted"]
                   and s["outcome"] == "not_completed"]
    if open_spells:
        amount = qty(len(open_spells), known_sum(
            s["points"] for s in open_spells))
        # In the sentence that says what is open, not anywhere: the
        # commitment's sentence can hold the same amount.
        c.check(bool(re.search(rf"{re.escape(amount)} (?:is|are) open|At the close, {re.escape(amount)} "
                               r"(?:was|were) not completed", core)), "commentary",
                f"states what is still open, {amount}")
    else:
        expected = "Nothing is open" if data["sprint_status"] == "active" else "Everything in the sprint was completed by the close"
        c.check(expected in core, "commentary",
                "states that nothing is still open")
    keys = {s["key"] for s in spells}
    excluded = set(data["membership_cross_check_excluded"]["keys"])
    c.check(all(set(ISSUE_KEY.findall(sentence)) <=
                (keys | excluded if CAVEATS[1] in sentence else keys)
                for sentence in sentences), "commentary", "names only tickets of the sprint or its membership caveat")
    non_delivery = data["non_delivery_closures"]["count"]
    c.check((CAVEATS[0] in text) == bool(non_delivery), "commentary",
            "states the non-delivery closures" if non_delivery else "states no non-delivery closures")
    c.check((CAVEATS[1] in text) == bool(excluded), "commentary",
            "states the membership cross-check limitation" if excluded else "states no cross-check limitation")
    caveat_keys = [(CAVEATS[0], {s["key"] for s in spells
                                 if s["counted"] and s["closedAsNonDelivery"]}),
                   (CAVEATS[1], excluded)]
    for marker, expected_keys in caveat_keys:
        shown_keys = {key for sentence in sentences if marker in sentence
                      for key in ISSUE_KEY.findall(sentence)}
        c.check(shown_keys == expected_keys, "commentary",
                f"the {marker} caveat names every affected ticket and no others")


def commentary_of(md):
    """The paragraph right after the timeline table, as plain text, or None."""
    table = next((t for t in html_tables(
        md) if table_kind(t) == "timeline"), None)
    if table is None:
        return None
    after = [p for p in md.split(table, 1)[1].split("\n\n") if p.strip()]
    if not after or after[0].startswith("#"):
        return None
    return link_text(after[0].strip())


def check_framing(c, md):
    """Each big table has a heading directly above it (only charts, and the
    line saying what a section shows, may sit in between). The paragraph
    after the timeline is check_commentary's."""
    for table in html_tables(md):
        kind = table_kind(table)
        if kind in (None, "fields"):
            continue
        before = md.partition(table)[0]
        # A section heading, ## or deeper: the # title heads the whole report.
        headings = [h for h in HEADING.finditer(before) if len(h[1]) >= 2]
        if c.check(bool(headings), "headings", f"{kind} table has a heading above it"):
            between = "\n".join(
                line for line in before[headings[-1].end():].splitlines()
                if line.strip() and not CHART_IMAGE.fullmatch(line.strip()) and line.strip() != UNTRACKED_SUBTITLE)
            c.check(between.strip() == "", "headings",
                    f"{kind} table directly follows '{headings[-1][2]}'")


def check_images(c, md, report_dir):
    embedded = [m[1] for m in CHART_IMAGE.finditer(md)]
    for name in CHART_FILES.values():
        c.check(name in embedded, "images", f"{name} embedded")
    for src in embedded:
        c.check(os.path.exists(os.path.join(report_dir, src)),
                "images", f"{src} exists")
    for heading, charts in ((METRICS_HEADING, ("outcome_tickets", "outcome_pts")), (TIMELINE_HEADING, ("burndown",))):
        section = md.split(f"## {heading}", 1)
        under = re.split(r"^## ", section[1], maxsplit=1, flags=re.M)[0] if len(
            section) == 2 else ""
        for chart in charts:
            c.check(CHART_FILES[chart] in under, "images",
                    f"{CHART_FILES[chart]} sits under the {heading} heading")


def check_files(c, report_dir, data):
    problem = folder_problem(report_dir, expected_files(data["label"]))
    c.check(not problem, "files",
            problem or "the folder holds the report's files, and only those")
    charts = os.path.join(report_dir, CHARTS_DIR)
    problem = os.path.isdir(charts) and folder_problem(
        charts, {os.path.basename(chart) for chart in CHART_FILES.values()})
    c.check(not problem, "files",
            f"{CHARTS_DIR}: {problem}" if problem else f"{CHARTS_DIR} holds the charts, and only those")


def check_timeline(c, table, data):
    """Each day lists, one row per ticket, the ticket's estimate at the end of
    the day and its events as tags in time order; its end-of-day figures are
    the burndown's; and the days are the timeline's."""
    if not c.check(table is not None, "timeline", "table found") or table is None:
        return
    shown = timeline_days(table)
    expected_dates = [display_date(row["date"]) for row in data["timeline"]]
    c.check([d["date"][:10] for d in shown] == expected_dates, "timeline",
            f"the days are the timeline's, in order ({len(expected_dates)})")
    readings = {row["date"]: row for row in data["burndown"]}
    original = [t for t in data["spells"] if t["scope"] == "original"]
    for row, day in zip(data["timeline"], shown):
        label = display_date(row["date"])
        by_key = {}
        for t in data["spells"]:
            by_key.setdefault(t["key"], []).extend(
                e for e in t["events"] if e["date"] == row["date"])
        tickets = []
        for key, events in by_key.items():
            events.sort(key=lambda e: parse_ts(e["at"]))
            if events:
                tickets.append((f"{key} ({pts(events[-1]['points'])})",
                                [label_ for e in events for label_ in tag_labels(e)]))
        tickets.sort(key=lambda s: key_order(s[0].split()[0]))
        c.check(day["tickets"] == tickets, "timeline",
                f"{label} lists each ticket's events, in time order")
        c.check(day["rowspan"] == max(len(tickets), 1),
                "cell shapes", f"{label} spans its {len(tickets)} tickets")
        parts = []
        if "sprint_start" in row["labels"]:
            parts.append(
                f"Commitment: {qty(len(original), data['burndown_baseline'])}")
        reading = readings.get(row["date"])
        if reading:
            parts.append(f"Still open: {qty(reading['committed_stories'], reading['committed'])} of the commitment "
                         f"{qty(reading['total_stories'], reading['total'])} with extra")
        expected_end = " ".join(parts) or "–"
        c.check(day["end"] == expected_end, "timeline",
                f"{label} end of day is {expected_end!r}")


def timeline_days(table):
    """[{date, rowspan, tickets: [(ticket text, [tags])], end}] from the
    timeline table's rows."""
    days = []
    for row in rows_of(table)[1:]:
        cells = cells_with_attributes(row)
        if cells and "rowspan" in cells[0][0]:
            span = re.search(r'rowspan="(\d+)"', cells[0][0])
            days.append({"date": text_of(cells[0][1]), "rowspan": int(span.group(1)) if span else 1,
                         "end": text_of(cells[-1][1]), "tickets": []})
            cells = cells[1:-1]
        if days and len(cells) == 2:
            days[-1]["tickets"].append((text_of(cells[0][1]),
                                        [html.unescape(t) for t in re.findall(r"<span[^>]*>(.*?)</span>", cells[1][1])]))
    return days


def text_of(cell):
    return " ".join(html.unescape(strip_tags(cell)).split())


def tag_labels(e):
    """The tags the timeline shows for an event."""
    if e["type"] in ("committed", "joined"):
        return ["Added"] + (["Already done"] if e["done"] else [])
    if e["type"] == "reestimated":
        return [f"Re-estimated: {estimate(e['fromPoints'])} → {pts(e['points'])}"]
    return [{"completed": "Completed", "reopened": "Reopened", "removed": "Descoped"}[e["type"]]]


def check_epics(c, table, data):
    if not c.check(table is not None, "epics", "table found"):
        return
    figures, groups = epic_figures(data), commentary_groups(data)
    c.check({e["key"] for e in data["epics"]} == set(figures), "epics",
            f"the epics are the spells' epics {sorted(figures, key=key_order)}")
    for epic in data["epics"]:
        title = f"<td>{epic['name']}</td>" if epic["key"] == NO_EPIC else f">{epic['key']}: "
        row = next((r for r in rows_of(table) if title in r), None)
        if not c.check(row is not None, "epics", f"{epic['key']} has a row"):
            continue
        cells = [content for _, content in cells_with_attributes(row)]
        commentary = cells[3]
        cells = cells[1:3]
        expected = []
        for kind in ("original", "extra"):
            done, total, done_pts, total_pts = figures.get(
                epic["key"], {}).get(kind, [0] * 4)
            share = f"{whole_percentage(done, total)}, " if kind == "original" else ""
            expected.append(share + ratio(done, total, done_pts,
                            total_pts) if total else "–")
        c.check(cells == expected, "epics",
                f"{epic['key']} shows {' '.join(expected)} (got {' '.join(cells)})")
        check_epic_commentary(
            c, epic, commentary, data["sprint_status"], groups.get(epic["key"], {}))


def epic_figures(data):
    """{epic key: {scope: [completed, all, completed pts, all pts]}} recomputed
    from the counted spells, so a ticket under the wrong epic can't pass by
    agreeing with data.json's own epic figures; the pts by known_sum's rule."""
    estimates = {}
    for spell in (s for s in data["spells"] if s["counted"]):
        done, every = estimates.setdefault(spell_epic(spell)[0], {
            "original": ([], []), "extra": ([], [])})[spell["scope"]]
        every.append(spell["points"])
        if spell["outcome"] == "completed":
            done.append(spell["points"])
    return {key: {scope: [len(done), len(every), known_sum(done), known_sum(every)]
                  for scope, (done, every) in scopes.items()}
            for key, scopes in estimates.items()}


def check_epic_commentary(c, epic, cell, status, groups):
    """The labels of the groups the epic has tickets to describe in, in order
    and a blank line apart; with none, why its tickets, `groups` as
    commentary_groups() gives them, are left out. The paragraphs are the
    agent's, checked when the report is written."""
    labels = [scope_group_label(g, status) for g in epic_groups(epic)]
    if not labels:
        expected = f"<i>{no_work_text({reason: len(groups.get(reason, [])) for reason in LEFT_OUT_REASONS})}</i>"
        c.check(cell.strip() == expected, "epics",
                f"{epic['key']} has no work to describe, so its commentary is {expected}")
        return
    lines = [re.match(r"<b>([^<]+):</b> (.+)", line.strip())
             for line in cell.split("<br><br>")]
    found = [m.group(1) if m else None for m in lines]
    c.check(found == labels, "epics",
            f"{epic['key']} commentary has {', '.join(labels)} (got {found})")


def check_status_section(c, md, table, data):
    """The Status to Verify section sits above the retro notes and shows the
    model's rows in order, each under its epic, with its status and its
    counts: a ticket not started, every linked pull request and those naming
    other tickets; a Done one, its own still open; with no rows, it says so."""
    section = md.split(f"## {STATUS_HEADING}\n\n", 1)
    after = section[1].split("\n\n## ", 1) if len(section) == 2 else []
    c.check(len(after) == 2 and after[1].startswith(RETRO_HEADING), "status",
            f"a {STATUS_HEADING} section sits right above the retro notes")
    rows = data["status_checks"]
    if not rows:
        c.check(table is None and len(section) == 2 and section[1].startswith(NOTHING_TO_VERIFY),
                "status", "with nothing to verify, the section says so")
        return
    if not c.check(table is not None, "status", "table found") or table is None:
        return
    shown, epic = [], None
    for row in rows_of(table)[1:]:
        cells = cells_with_attributes(row)
        if len(cells) == 4:
            epic = (ISSUE_KEY.findall(text_of(cells[0][1])) or [None])[0]
            cells = cells[1:]
        shown.append((epic, text_of(cells[0][1]), text_of(
            cells[1][1]), text_of(cells[2][1])))
    latest = latest_estimates(data)
    expected = [(None if r["epicKey"] == NO_EPIC else r["epicKey"], f"{r['key']} ({pts(latest.get(r['key']))})",
                 r["status"] or "") for r in rows]
    c.check([s[:3] for s in shown] == expected, "status",
            f"the table lists each flagged ticket under its epic, with its latest estimate and status "
            f"({len(expected)})")
    for row, (_, _, _, text) in zip(rows, shown):
        # A total may carry its one state: "1 merged PR is linked".
        if row["flag"] == "work_started":
            total = sum(row["linked"].values())
            counts = [rf"\b{total} (?:\w+ )?PRs? (?:is|are) linked"] + \
                [rf"\b{row['otherTickets']} of them"] * \
                bool(row["otherTickets"])
        else:
            counts = [
                rf"Done, but {row['ownOpen']} PRs? (?:is|are) still open"]
        c.check(all(re.search(count, text) for count in counts), "status",
                f"{row['key']} shows {', '.join(counts)}")


def check_untracked_section(c, md, table, data):
    """The Untracked Delivery section sits between Delivery by Epic and
    Sprint Metrics and shows the untracked pull requests, recomputed from
    what GitHub gave (untracked_by_repository()): a row per repository, in
    order, its pull requests each its title linked, in an accordion past
    UNTRACKED_OPEN_PULLS, beside a commentary marked as the agent's; under
    the line saying what it shows; with none, it says so."""
    after = md.split(f"## {UNTRACKED_HEADING}\n\n", 1)
    body = after[1].split("\n\n## ", 1) if len(after) == 2 else []
    c.check(bool(re.search(rf"## {EPICS_HEADING}\n\n<table.*?</table>\n\n## {UNTRACKED_HEADING}\n\n", md, re.S))
            and len(body) == 2 and body[1].startswith(METRICS_HEADING),
            "untracked", f"an {UNTRACKED_HEADING} section sits between Delivery by Epic's table and Sprint Metrics")
    c.check(len(body) == 2 and body[0].startswith(f"{UNTRACKED_SUBTITLE}\n\n"), "untracked",
            "the section says what it shows under its heading")
    expected = untracked_by_repository(data)
    if not expected:
        c.check(table is None and len(body) == 2 and body[0] == f"{UNTRACKED_SUBTITLE}\n\n{NOTHING_UNTRACKED}", "untracked",
                "with no untracked pull request, the section says so")
        return
    if not c.check(table is not None, "untracked", "table found") or table is None:
        return
    rows = rows_of(table)
    c.check(ai_marked("Commentary")
            in rows[0], "untracked", "the commentary is marked as the agent's")
    titles = {pr["url"]: pr["title"] for pr in data["other_pull_requests"]}
    shown = []
    for row in rows[1:]:
        cells = [cell for _, cell in cells_with_attributes(row)]
        folded = re.fullmatch(
            r"<details><summary>(\d+) pull requests</summary>(.*)</details>", cells[1], re.S)
        pulls = [(html.unescape(url), html.unescape(title))
                 for url, title in re.findall(r'<a href="([^"]+)">([^<]*)</a>', folded[2] if folded else cells[1])]
        link = re.fullmatch(r'<a href="([^"]+)">[^<]*</a>', cells[0])
        shown.append((text_of(cells[0]), link and html.unescape(link[1]), pulls,
                      int(folded[1]) if folded else None))
    c.check(shown == [(repository, repository_url(urls[0]), [(url, titles[url]) for url in urls],
                       len(urls) if len(urls) > UNTRACKED_OPEN_PULLS else None)
                      for repository, urls in expected], "untracked",
            f"the table lists the untracked pull requests of {len(expected)} repositories, each linked, its pull "
            "requests each its title linked, "
            f"in an accordion past {UNTRACKED_OPEN_PULLS}")


def check_untracked_pulls(c, data):
    """Each pull request no ticket links names the tickets its title and
    branch give and is untracked when none of them is the sprint's;
    the untracked ones are grouped by repository, the most first."""
    keys = sprint_key(data)
    for pr in data["other_pull_requests"]:
        named = sorted(set(keys.findall(pr["title"])) | set(
            keys.findall(pr["branch"])), key=key_order)
        c.check(pr["tickets"] == named, "model",
                f"{pr['url']} names {named or 'no ticket'}")
    untracked = untracked_by_repository(data)
    c.check({pr["url"] for pr in data["other_pull_requests"] if pr["untracked"]}
            == {url for _, urls in untracked for url in urls}, "model",
            "the untracked pull requests are those naming none of the sprint's tickets")
    c.check([(row["repository"], row["url"], row["pulls"]) for row in data["untracked_delivery"]]
            == [(repository, repository_url(urls[0]), urls) for repository, urls in untracked], "model",
            "the untracked delivery holds the untracked pull requests by repository, the most first, each "
            "linked to its repository")


def untracked_by_repository(data):
    """[(repository, [urls in the order merged])] of the pull requests merged
    during the sprint that no ticket links and that name none of its
    tickets, recomputed from their titles and branches, the repository with
    the most first, then by name."""
    keys, sprint_keys = sprint_key(data), {t["key"] for t in data["spells"]}
    found = {}
    for pr in sorted(data["other_pull_requests"], key=lambda pr: (pr["mergedAt"] or "", pr["url"])):
        if not (set(keys.findall(pr["title"])) | set(keys.findall(pr["branch"]))) & sprint_keys:
            found.setdefault(pr["repository"], []).append(pr["url"])
    return sorted(found.items(), key=lambda item: (-len(item[1]), item[0].lower()))


def check_style(c, md, data):
    generated = generated_text(md)
    c.check("—" not in generated, "em dashes", "none in generated text")
    iso = dict(text_rule_problems(generated)).get(DATE_RULE, [])
    c.check(not iso, "dates", f"{DATE_RULE} {iso[:3] or ''}".strip())
    # The title is plain text; every other key of the sprint's projects,
    # including copied fields, is linked.
    md = TITLE.sub("", md)
    stripped = INLINE_LINK.sub("", md)
    stripped = re.sub(r"<a\s[^>]*>.*?</a>", "", stripped, flags=re.S)
    unlinked = sorted(set(sprint_key(data).findall(stripped)))
    c.check(not unlinked, "links",
            f"every Jira key is linked (unlinked: {unlinked[:5] or 'none'})")


def generated_text(md):
    """Exclude only the fixed source-text slots, never matching prose by value."""
    md = TITLE.sub("# Sprint Summary:", md)
    md = re.sub(r"(<td>Goal</td><td>).*?(</td>)", r"\1\2", md, flags=re.S)
    for table in html_tables(md):
        if table_kind(table) == "epics":
            without_names = re.sub(
                r"(<tr\b[^>]*>\s*)<td>.*?</td>", r"\1<td></td>", table, flags=re.S)
            md = md.replace(table, without_names, 1)
        elif table_kind(table) in ("status", "untracked"):
            md = md.replace(table, re.sub(rf'(<td[^>]*class="(?:{JIRA_CELL}|{GITHUB_CELL})"[^>]*>).*?</td>',
                                          r"\1</td>", table, flags=re.S), 1)
    return md


def check_vocabulary(c, md, data):
    """The report's vocabulary and formats (see common.py's "The report's
    vocabulary and formats"), excluding copied Jira fields."""
    md = generated_text(md)
    text = link_text(md)
    words = strip_tags(text)
    found = dict(text_rule_problems(words.replace("(sprint closed)", "")))
    found[BOLD_RULE] = dict(text_rule_problems(text)).get(BOLD_RULE, [])
    # Dates are checked with the style, on the whole generated text, and
    # ticket lists below, on the prose.
    for rule in [f"no {rule}" for rule, _ in BANNED_WORDS] + [r for r in FORMAT_RULES if r not in (DATE_RULE, LIST_RULE)]:
        c.check(not found.get(rule), "vocabulary",
                f"{rule} {found.get(rule, [])[:3] or ''}".strip())
    # Tickets in running text: one as KEY (N pts), with its latest estimate;
    # a list as (KEY, KEY), sorted. The timeline's and the Status to Verify
    # section's ticket cells are checked apart.
    prose = text
    for table in html_tables(text):
        if table_kind(table) in ("timeline", "status"):
            prose = prose.replace(table, "", 1)
    prose = strip_tags(prose)
    latest = latest_estimates(data)
    unsorted = dict(text_rule_problems(prose)).get(LIST_RULE, [])
    c.check(not unsorted, "vocabulary",
            f"{LIST_RULE} {unsorted[:2] or ''}".strip())
    rest = KEY_LIST.sub("", prose)
    # Commentary has fixed historical phrases; AI text uses the latest estimate.
    commentary = commentary_of(md) or ""
    commentary = KEY_LIST.sub("", commentary)
    if commentary:
        rest = rest.replace(commentary, "", 1)
    wrong = dict(text_rule_problems(rest, latest)).get(ESTIMATE_RULE, [])
    c.check(not wrong, "vocabulary",
            f"{ESTIMATE_RULE} {wrong[:3] or ''}".strip())
    allowed = historical_references(data)
    wrong = [found.group(0) for found in TICKET_ESTIMATE.finditer(commentary)
             if not any(commentary[found.start():].startswith(reference) for reference in allowed)]
    c.check(not wrong, "vocabulary",
            f"historical ticket estimates match their commentary event {wrong[:3] or ''}".strip())


def historical_references(data):
    """Allowed single-ticket references in the generator's fixed commentary
    phrases: each scope change of one spell, as scope_change_figures() gives
    it, and each ticket of the two caveats."""
    allowed = set()
    changes = scope_change_figures(data)
    phrases = {"done_at_start": "was already Done at the start", "descoped": "was descoped",
               "extra": "was added as extra", "dropped": "was added and descoped again",
               "reopened": "was reopened", "came_back": "left the sprint and came back"}
    for change, phrase in phrases.items():
        group = changes[change]
        if group["count"] == 1:
            allowed.add(
                f"{group['keys'][0]} ({pts(group['points'])}) {phrase}")
    group = changes["reestimated"]
    if group["count"] == 1:
        allowed.add(f"{group['keys'][0]} ({estimate(group['first_points'])} → {pts(group['points'])}) "
                    "was re-estimated")
    for spell in data["spells"]:
        if spell["counted"] and spell["closedAsNonDelivery"]:
            allowed.add(
                f"{spell['key']} ({pts(spell['points'])}) was resolved without delivery")
    latest = latest_estimates(data)
    for key in data["membership_cross_check_excluded"]["keys"]:
        allowed.add(
            f"{key} ({pts(latest.get(key))}) is reconstructed from changelogs")
    return allowed


def main():
    parser = argparse.ArgumentParser(
        description=(__doc__ or "").split("\n\n")[0],
        epilog="Prints every check and exits non-zero if any fails.")
    parser.add_argument("--report-dir", required=True,
                        help="report folder holding data.json and the report")
    args = parser.parse_args()
    sys.exit(check_report(args.report_dir).report())


if __name__ == "__main__":
    main()
