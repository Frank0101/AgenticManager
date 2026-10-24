"""Check a finished sprint report against the data it was built from and
against the report's formatting rules.

It shares only the format helpers with make_report.py and recomputes every
figure from the spells' events, so a generator bug can't pass by agreeing with
itself. Every rule here exists because a table drifted when corrected by hand:
prose guidance didn't stop it, a failing check does.
"""
import argparse
import html
import os
import re
import sys
from datetime import date, timedelta

from common import (INLINE_LINK, SENTENCE_BREAK, link_text, BANNED_WORDS, expected_files, CHART_FILES, COMMENTARY_WORDS, DATA_FILE, FIELD_TABLE_HEAD, ISSUE_KEY,
                    BOLD_RULE, DATE_RULE, ESTIMATE_RULE, FORMAT_RULES, KEY_LIST, TICKET_ESTIMATE,
                    TICKET_EVENT_TYPES,
                    NO_EPIC, OUTCOME_ROWS, OUTCOMES, ai, text_rule_problems,
                    display_date, epic_groups, estimate, key_order, known_sum, read_json, parse_ts, plural, pts, qty,
                    ratio, report_file, report_timezone, scope_group_label, spell_epic, whole_percentage, word_count)


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
HEADER_LABELS = ["Dates", "Goal", ai("Goal outcome"), ai("Key Achievements"),
                 ai("Blockers & Risks"), "Sprint target completion"]

# The commentary's caveats, which its word limit doesn't count.
CAVEATS = ("resolved as Duplicate or Won't Do",
           "is reconstructed from changelogs")


def run_checks(md, data, report_dir):
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
    check_style(c, md)
    check_vocabulary(c, md, data)
    return c


class Checker:
    def __init__(self):
        self.failures, self.passes = [], []

    def check(self, ok, name, detail):
        (self.passes if ok else self.failures).append(f"{name}: {detail}")
        return ok

    def report(self):
        for line in self.passes:
            print(f"  ok    {line}")
        for line in self.failures:
            print(f"  FAIL  {line}")
        print()
        if self.failures:
            print(f"{len(self.failures)} check(s) failed")
            return 1
        print(f"all {len(self.passes)} checks passed")
        return 0


def html_tables(md):
    return re.findall(r"<table.*?</table>", md, re.S)


def table_kind(table):
    header = strip_tags(rows_of(table)[0]).lower()
    if "date" in header and "events" in header and "end of day" in header:
        return "timeline"
    if "epic" in header and "commentary" in header:
        return "epics"
    return None


def rows_of(table):
    return re.findall(r"<tr>(.*?)</tr>", table, re.S)


def strip_tags(text):
    return re.sub(r"<[^>]+>", " ", text).strip()


def check_model(c, data):
    """Each spell's events are well formed, and its outcome, latest estimate
    and whether it's counted are what its events give; the charts' breakdown,
    the non-delivery closures, the ticket counts, the burndown, the timeline
    and the epics' commentary groups are built from the same spells."""
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
                 "reestimated": "reestimated" in kinds, "cameBack": key in seen_keys}
        c.check(all(t[name] == value for name, value in flags.items()), "model",
                f"{key}'s doneAtStart, reopened, reestimated and cameBack flags are what its events give")
        seen_keys.add(key)
        done, flips = events[0]["done"] if events else False, True
        for e in events[1:]:
            if e["type"] in ("completed", "reopened"):
                flips = flips and e["done"] == (
                    e["type"] == "completed") != done
            done = e["done"]
        outcome = "removed" if kinds and kinds[-1] == "removed" else (
            "completed" if done else "not_completed")
        counted = not (t["scope"] == "extra" and outcome == "removed")
        c.check(flips and t["outcome"] == outcome and t["counted"] == counted
                and t["points"] == (events[-1]["points"] if events else None),
                "model", f"{key} ends {outcome}{'' if counted else ', not counted'}, as its events give")

    expected = {}
    for t in (t for t in data["spells"] if t["counted"]):
        rows = ["extra"] if t["scope"] == "extra" else [
            "original", "carried_in" if t["carriedIn"] else "new"]
        for row in rows:
            count, points = expected.get(f"{row}_{t['outcome']}", (0, 0))
            expected[f"{row}_{t['outcome']}"] = (
                count + 1, points + (t["points"] or 0))
    for row in OUTCOME_ROWS:
        for outcome in OUTCOMES:
            got = (data["outcome_breakdown_counts"][f"{row}_{outcome}"],
                   data["outcome_breakdown_points"][f"{row}_{outcome}"])
            c.check(got == expected.get(f"{row}_{outcome}", (0, 0)), "model",
                    f"the charts' {row} {outcome.replace('_', ' ')} is the counted spells' {qty(*got)}")

    counted = [t for t in data["spells"] if t["counted"]]
    closures = [t for t in counted
                if t["outcome"] == "completed" and t["closedAsNonDelivery"]]
    c.check(data["non_delivery_closures"] == {
        "count": len(closures), "points": sum(t["points"] or 0 for t in closures),
        "issues": [{"key": t["key"], "status": t["status"], "resolution": t["resolution"],
                    "storyPoints": t["points"], "marker": t["closedAsNonDelivery"], "summary": t["summary"]}
                   for t in closures]}, "model",
            "the non-delivery closures are the counted spells completed as Duplicate or Won't Do")
    c.check((data["points_estimated_issue_count"], data["points_total_issue_count"])
            == (sum(1 for t in counted if t["points"] is not None), len(counted)), "model",
            "the estimated and total ticket counts are the counted spells'")

    original = [t for t in data["spells"] if t["scope"] == "original"]
    done = [t for t in original if t["outcome"] == "completed"]
    c.check(data["target_completion"] == {
        "completed": len(done), "total": len(original),
        "completed_points": sum(t["points"] or 0 for t in done),
        "total_points": sum(t["points"] or 0 for t in original)}, "model",
        "the sprint target is the original commitment's spells, and those completed")
    baseline = sum(t["events"][0]["points"] or 0 for t in original)
    c.check(data["burndown_baseline"] == baseline, "model",
            f"the burndown starts at the whole commitment, {baseline}")
    first = date.fromisoformat(data["sprint_start"])
    last = parse_ts(data["as_of_instant"]).astimezone(
        report_timezone(data["report_timezone"])).date()
    expected_dates = [(first + timedelta(days=offset)).isoformat()
                      for offset in range((last - first).days + 1)]
    c.check([row["date"] for row in data["burndown"]] == expected_dates, "model",
            "the burndown covers every day from the sprint start through the report cutoff, in order")
    for row in data["burndown"]:
        committed = total = committed_stories = total_stories = 0
        for t in data["spells"]:
            seen = [e for e in t["events"] if e["date"] <= row["date"]]
            if seen and seen[-1]["type"] != "removed" and not seen[-1]["done"]:
                total += seen[-1]["points"] or 0
                total_stories += 1
                if t["scope"] == "original":
                    committed += seen[-1]["points"] or 0
                    committed_stories += 1
        c.check((row["committed"], row["total"], row["committed_stories"], row["total_stories"])
                == (committed, total, committed_stories, total_stories), "model",
                f"the burndown on {display_date(row['date'])} is the spells' open tickets and pts")

    logged = sorted((e["key"], e["type"], row["date"])
                    for row in data["timeline"] for e in row["events"])
    replayed = sorted((t["key"], e["type"], e["date"])
                      for t in data["spells"] for e in t["events"])
    c.check(logged == replayed, "model",
            "the timeline holds exactly the spells' events")
    check_commentary_groups(c, data)
    check_ticket_events(c, data)


def check_commentary_groups(c, data):
    """Each epic's commentary groups, and the work left out of them, hold
    the counted spells their outcomes and events give: descoped work is
    always described, and completed work only if the sprint did it."""
    expected = {}
    for t in (t for t in data["spells"] if t["counted"]):
        if t["outcome"] == "removed":
            group = "descoped"
        elif t["outcome"] == "not_completed":
            group = "in_review" if "review" in (
                t["status"] or "").lower() else "not_completed"
        elif t["closedAsNonDelivery"] or not any(e["type"] == "completed" for e in t["events"]):
            group = "left_out"
        else:
            group = "completed"
        epic = expected.setdefault(spell_epic(t)[0], {})
        epic.setdefault(group, []).append(t["key"])
    for epic in data["epics"]:
        groups = {**epic["scope_groups"], "left_out": epic["left_out"]}
        stored = {group: [t["key"] for t in tickets]
                  for group, tickets in groups.items() if tickets}
        c.check(stored == expected.get(epic["key"], {}), "model",
                f"{epic['key']}'s commentary groups hold the tickets their outcomes give")


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
    sprint_id = str(data["sprint_id"])
    for spell in data["spells"]:
        events = tickets.get(spell["key"])
        if events is None or ticket_event_problems(events, zone, cutoff):
            continue
        wrong = spell_event_problems(spell, events, sprint_id, cutoff)
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
        fields = TICKET_EVENT_FIELDS.get(
            kind, ("from", "to") if kind != "created" else ())
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
    """(Done, estimate) of the ticket at `instant`: its creation's, then as
    each status and points change up to the instant leaves them."""
    created = next(e for e in events if e["type"] == "created")["values"]
    done, points = created["statusCategory"] == "done", created["points"]
    for e in events:
        if parse_ts(e["at"]) > instant:
            continue
        if e["type"] == "status_changed":
            done = e["toCategory"] == "done"
        elif e["type"] == "points_changed":
            points = e["to"]
    return done, points


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
    shown = re.sub(r"\[(" + ISSUE_KEY.pattern + r")\]\([^)]*\)",
                   r"\1", goal).replace("\\|", "|")
    lines = [line.strip()
             for line in data["sprint_goal"].splitlines() if line.strip()]
    expected_goal = "<br>".join(html.escape(line, quote=False)
                                for line in lines) if lines else "*No goal was set in Jira for this sprint*"
    c.check(shown == expected_goal, "header",
            "Goal is Jira's goal, one line per <br>")

    original_spells = [t for t in data["spells"] if t["scope"] == "original"]
    done = [t for t in original_spells if t["outcome"] == "completed"]
    so_far = " so far" if data["sprint_status"] == "active" else ""
    target = "No commitment" if not original_spells else (
        f"{whole_percentage(len(done), len(original_spells))}, "
        + ratio(len(done), len(original_spells), sum(t["points"] or 0 for t in done),
                sum(t["points"] or 0 for t in original_spells))
        + f" completed{so_far}")
    c.check(values["Sprint target completion"] == target,
            "header", f"Sprint target completion is {target!r}")
    c.check(f"## Sprint Metrics\n\n{FIELD_TABLE_HEAD}| Sprint target completion |" in md,
            "header", "Sprint target completion is a table of its own under Sprint Metrics")


def header_rows(md):
    """[(label, value)] of the report's tables of fields, the one at the top
    and the one under Sprint Metrics, in order, or None if there are none."""
    if FIELD_TABLE_HEAD not in md:
        return None
    rows = []
    for table in md.split(FIELD_TABLE_HEAD)[1:]:
        for line in table.split("\n\n", 1)[0].splitlines():
            cells = re.fullmatch(r"\| (.+?) \| (.*) \|", line)
            rows.append((cells.group(1), cells.group(2))
                        if cells else (line, None))
    return rows


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
    spells = data["spells"]
    original = [s for s in spells if s["scope"] == "original"]
    committed = qty(len(original), data["burndown_baseline"])
    c.check((f"{committed} in the commitment" if original else "Nothing was committed at the start") in text,
            "commentary", f"states the commitment, {committed}" if original else "states that nothing was committed")
    descoped = [s for s in original if s["outcome"] == "removed"]
    extra = [s for s in spells if s["scope"] == "extra" and s["counted"]]
    for kind, items in (("descoped", descoped), ("added as extra", extra)):
        if len(items) > 1:
            amount = qty(len(items), known_sum(s["points"] for s in items))
            c.check(f"{amount} {plural(len(items), 'was', 'were')} {kind}" in text,
                    "commentary", f"states {amount} {kind}")
    returns = [s for i, s in enumerate(spells)
               if s["events"][0]["type"] == "joined" and any(o["key"] == s["key"] for o in spells[:i])]
    departures = [
        ("already Done at the start", r"already Done at the start",
         any(s["events"][0]["done"] for s in original)),
        ("descoped from the commitment", r"\b(?:was|were) descoped", bool(descoped)),
        ("added as extra", r"\b(?:was|were) added as extra", bool(extra)),
        ("added and descoped again", r"added and descoped again",
         any(not s["counted"] for s in spells)),
        ("reopened", r"\breopened\b", any(
            e["type"] == "reopened" for s in spells for e in s["events"])),
        ("re-estimated", r"\bre-estimated\b",
         any(e["type"] == "reestimated" for s in spells for e in s["events"])),
        ("left and came back", r"left the sprint and came back", bool(returns)),
    ]
    for name, pattern, happened in departures:
        c.check(bool(re.search(pattern, core)) == happened, "commentary",
                f"{'mentions' if happened else 'does not mention'} {name}")
    open_spells = [s for s in spells if s["counted"]
                   and s["outcome"] == "not_completed"]
    if open_spells:
        amount = qty(len(open_spells), known_sum(
            s["points"] for s in open_spells))
        c.check(amount in core, "commentary",
                f"states what is still open, {amount}")
    else:
        expected = "Nothing is open" if data["sprint_status"] == "active" else "Everything in the sprint was completed by the close"
        c.check(expected in core, "commentary",
                "states that nothing is still open")
    keys = {s["key"] for s in spells}
    excluded = set(data["membership_cross_check_excluded_keys"])
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
    """Each big table has a heading directly above it (only charts may sit in
    between). The paragraph after the timeline is check_commentary's."""
    for table in html_tables(md):
        kind = table_kind(table)
        if kind is None:
            continue
        before = md.partition(table)[0]
        headings = list(re.finditer(r"^##+ +(.+)$", before, re.M))
        if c.check(bool(headings), "headings", f"{kind} table has a heading above it"):
            between = "\n".join(
                line for line in before[headings[-1].end():].splitlines()
                if line.strip() and not ((m := INLINE_LINK.fullmatch(line.strip())) and m[1]))
            c.check(between.strip() == "", "headings",
                    f"{kind} table directly follows '{headings[-1].group(1).strip()}'")


def check_images(c, md, report_dir):
    embedded = [m[3] for m in INLINE_LINK.finditer(md) if m[1]]
    for name in CHART_FILES.values():
        c.check(name in embedded, "images", f"{name} embedded")
    for src in embedded:
        c.check(os.path.exists(os.path.join(report_dir, src)),
                "images", f"{src} exists")
    for heading, charts in (("Sprint Metrics", ("outcome_tickets", "outcome_pts")), ("Scope Timeline", ("burndown",))):
        section = md.split(f"## {heading}", 1)
        under = re.split(r"^## ", section[1], maxsplit=1, flags=re.M)[0] if len(
            section) == 2 else ""
        for chart in charts:
            c.check(CHART_FILES[chart] in under, "images",
                    f"{CHART_FILES[chart]} sits under the {heading} heading")


def check_files(c, report_dir, data):
    extra = sorted(name for name in os.listdir(report_dir)
                   if not name.startswith(".") and name not in expected_files(data["label"]))
    c.check(not extra, "files",
            f"only the report's files are in the folder (unexpected: {extra or 'none'})")


def check_timeline(c, table, data):
    """Each day lists, one row per ticket, the ticket's estimate at the end of
    the day and its events as tags in time order; its end-of-day figures are
    the burndown's; and the days are the timeline's."""
    if not c.check(table is not None, "timeline", "table found") or table is None:
        return
    days = timeline_days(table)
    expected_dates = [display_date(row["date"]) for row in data["timeline"]]
    c.check([d["date"][:10] for d in days] == expected_dates, "timeline",
            f"the days are the timeline's, in order ({len(expected_dates)})")
    readings = {row["date"]: row for row in data["burndown"]}
    original = [t for t in data["spells"] if t["scope"] == "original"]
    for row, day in zip(data["timeline"], days):
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
        cells = re.findall(r"<td([^>]*)>(.*?)</td>", row, re.S)
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
    figures = epic_figures(data)
    c.check({e["key"] for e in data["epics"]} == set(figures), "epics",
            f"the epics are the spells' epics {sorted(figures, key=key_order)}")
    for epic in data["epics"]:
        title = f"<td>{epic['name']}</td>" if epic["key"] == NO_EPIC else f">{epic['key']}: "
        row = next((r for r in rows_of(table) if title in r), None)
        if not c.check(row is not None, "epics", f"{epic['key']} has a row"):
            continue
        cells = cells_of(row)[1:3]
        expected = []
        for kind in ("original", "extra"):
            done, total, done_pts, total_pts = figures.get(
                epic["key"], {}).get(kind, [0] * 4)
            share = f"{whole_percentage(done, total)}, " if kind == "original" else ""
            expected.append(share + ratio(done, total, done_pts,
                            total_pts) if total else "–")
        c.check(cells == expected, "epics",
                f"{epic['key']} shows {' '.join(expected)} (got {' '.join(cells)})")
        check_epic_commentary(c, epic, cells_of(row)[3], data["sprint_status"])


def epic_figures(data):
    """{epic key: {scope: [completed, all, completed pts, all pts]}} recomputed
    from the counted spells, so a ticket under the wrong epic can't pass by
    agreeing with data.json's own epic figures."""
    figures = {}
    for spell in (s for s in data["spells"] if s["counted"]):
        row = figures.setdefault(spell_epic(spell)[0], {
                                 "original": [0] * 4, "extra": [0] * 4})[spell["scope"]]
        points = spell["points"] or 0
        row[1] += 1
        row[3] += points
        if spell["outcome"] == "completed":
            row[0] += 1
            row[2] += points
    return figures


def check_epic_commentary(c, epic, cell, status):
    """The labels of the groups the epic has tickets to describe in, in order
    and a blank line apart; "–" if there are none. The sentences are the
    agent's, checked when the report is written."""
    labels = [scope_group_label(g, status) for g in epic_groups(epic)]
    if not labels:
        c.check(cell.strip() == "–", "epics",
                f"{epic['key']} has no scope to describe, so its commentary is –")
        return
    lines = [re.match(r"<b>([^<]+):</b> (.+)", line.strip())
             for line in cell.split("<br><br>")]
    found = [m.group(1) if m else None for m in lines]
    c.check(found == labels, "epics",
            f"{epic['key']} commentary has {', '.join(labels)} (got {found})")


def cells_of(row):
    return re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.S)


def check_style(c, md):
    generated = generated_text(md)
    c.check("—" not in generated, "em dashes", "none in generated text")
    iso = dict(text_rule_problems(generated)).get(DATE_RULE, [])
    c.check(not iso, "dates", f"{DATE_RULE} {iso[:3] or ''}".strip())
    # The title is plain text; every other key, including copied fields, is linked.
    md = re.sub(r"^# Sprint Summary:.*$", "", md, flags=re.M)
    stripped = INLINE_LINK.sub("", md)
    stripped = re.sub(r"<a\s[^>]*>.*?</a>", "", stripped, flags=re.S)
    unlinked = sorted(set(ISSUE_KEY.findall(stripped)))
    c.check(not unlinked, "links",
            f"every Jira key is linked (unlinked: {unlinked[:5] or 'none'})")


def generated_text(md):
    """Exclude only the fixed source-text slots, never matching prose by value."""
    md = re.sub(r"^# Sprint Summary:.*$", "# Sprint Summary:", md, flags=re.M)
    md = re.sub(r"^\| Goal \|.*$", "| Goal | |", md, flags=re.M)
    for table in html_tables(md):
        if table_kind(table) == "epics":
            without_names = re.sub(
                r"(<tr>\s*)<td>.*?</td>", r"\1<td></td>", table, flags=re.S)
            md = md.replace(table, without_names, 1)
    return md


def check_vocabulary(c, md, data):
    """The report's vocabulary and formats (see common.py's "The report's
    vocabulary and formats"), excluding copied Jira fields."""
    md = generated_text(md)
    text = link_text(md)
    words = strip_tags(text)
    found = dict(text_rule_problems(words.replace("(sprint closed)", "")))
    found[BOLD_RULE] = dict(text_rule_problems(text)).get(BOLD_RULE, [])
    # Dates are checked with the style, on the whole generated text.
    for rule in [f"no {rule}" for rule, _ in BANNED_WORDS] + [r for r in FORMAT_RULES if r != DATE_RULE]:
        c.check(not found.get(rule), "vocabulary",
                f"{rule} {found.get(rule, [])[:3] or ''}".strip())
    # Tickets in running text: one as KEY (N pts), with its latest estimate;
    # a list as (KEY, KEY), sorted. The timeline's cells are checked apart.
    prose = text
    for table in html_tables(text):
        if table_kind(table) == "timeline":
            prose = prose.replace(table, "", 1)
    prose = strip_tags(prose)
    latest = {s["key"]: s["points"] for s in data["spells"]}
    lists = [group for group in KEY_LIST.findall(prose) if ", " in group]
    unsorted = [group for group in lists if group.split(
        ", ") != sorted(group.split(", "), key=key_order)]
    c.check(not unsorted, "vocabulary",
            f"ticket lists are sorted {unsorted[:2] or ''}".strip())
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
    """Allowed single-ticket references in the generator's fixed commentary phrases."""
    allowed = set()
    spells = data["spells"]
    latest = {s["key"]: s["points"] for s in spells}
    for index, spell in enumerate(spells):
        key, points, events = spell["key"], spell["points"], spell["events"]
        reference = f"{key} ({pts(points)}) "
        if spell["scope"] == "original":
            if events[0]["done"]:
                allowed.add(
                    f"{key} ({pts(events[0]['points'])}) was already Done at the start")
            if spell["outcome"] == "removed":
                allowed.add(reference + "was descoped")
        elif spell["counted"]:
            allowed.add(reference + "was added as extra")
        if not spell["counted"]:
            allowed.add(reference + "was added and descoped again")
        if any(e["type"] == "reopened" for e in events):
            allowed.add(reference + "was reopened")
        changes = [e for e in events if e["type"] == "reestimated"]
        if changes:
            old = estimate(changes[0]["fromPoints"])
            allowed.add(f"{key} ({old} → {pts(points)}) was re-estimated")
        if events[0]["type"] == "joined" and any(s["key"] == key for s in spells[:index]):
            allowed.add(reference + "left the sprint and came back")
        if spell["counted"] and spell["closedAsNonDelivery"]:
            allowed.add(reference + "was resolved as Duplicate or Won't Do")
    for key in data["membership_cross_check_excluded_keys"]:
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

    data = read_json(os.path.join(args.report_dir, DATA_FILE))
    with open(os.path.join(args.report_dir, report_file(data["label"])), encoding="utf-8") as f:
        md = f.read()
    sys.exit(run_checks(md, data, args.report_dir).report())


if __name__ == "__main__":
    main()
