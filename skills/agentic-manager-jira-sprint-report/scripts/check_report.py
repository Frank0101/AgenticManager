"""
Check a finished sprint report against the data it was built from and against
the report's formatting rules.

Usage:
    python3 check_report.py --report-dir <report_dir>

Prints every check and exits non-zero if any fails. make_report.py validates
the agent's text (content.json) before writing; this checks what the generator
produced from data.json. It shares only the format helpers with make_report.py
and recomputes every figure from the spells' events, so a generator bug can't
pass by agreeing with itself. Every rule here exists because a table drifted
when corrected by hand: prose guidance didn't stop it, a failing check does.
"""
import argparse
import html
import os
import re
import sys
from datetime import date, timedelta

from common import (BANNED_WORDS, expected_files, CHART_FILES, COMMENTARY_WORDS, DATA_FILE, ISSUE_KEY,
                    NO_EPIC, OUTCOME_ROWS, OUTCOMES, ai, banned_words,
                    display_date, epic_groups, estimate, key_order, load_json, number, parse_ts, plural, pts, qty,
                    ratio, report_file, report_timezone, scope_group_label, whole_percentage, word_count)


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


def rows_of(table):
    return re.findall(r"<tr>(.*?)</tr>", table, re.S)


def cells_of(row):
    return re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.S)


def strip_tags(text):
    return re.sub(r"<[^>]+>", " ", text).strip()


def table_kind(table):
    header = strip_tags(rows_of(table)[0]).lower()
    if "date" in header and "events" in header and "end of day" in header:
        return "timeline"
    if "epic" in header and "commentary" in header:
        return "epics"
    return None


HEADER_START = "| Field | Detail |\n|---|---|\n"
HEADER_LABELS = ["Dates", "Goal", ai(
    "Goal outcome"), "Sprint target completion"]


def header_rows(md):
    """[(label, value)] of the table above the charts, or None if it's missing."""
    if HEADER_START not in md:
        return None
    body = md.split(HEADER_START, 1)[1].split("\n\n", 1)[0]
    rows = []
    for line in body.splitlines():
        cells = re.fullmatch(r"\| (.+?) \| (.*) \|", line)
        rows.append((cells.group(1), cells.group(2))
                    if cells else (line, None))
    return rows


def check_header(c, md, data):
    rows = header_rows(md)
    if not c.check(rows is not None, "header", "table above the charts found") or rows is None:
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
    oc = data["outcome_breakdown_counts"]
    charted = (sum(oc[f"original_{outcome}"]
               for outcome in OUTCOMES), oc["original_completed"])
    c.check(charted == (len(original_spells), len(done)), "header",
            f"the charts' original commitment, {charted[0]} with {charted[1]} completed, is the target's "
            f"{len(original_spells)} with {len(done)} completed")


def charted(data, row, outcome=None):
    """(count, points) of an outcome_breakdown row, or of one outcome in it."""
    counts, points = data["outcome_breakdown_counts"], data["outcome_breakdown_points"]
    outcomes = [outcome] if outcome else OUTCOMES
    return (sum(counts[f"{row}_{o}"] for o in outcomes), sum(points[f"{row}_{o}"] for o in outcomes))


# The commentary's caveats, which its word limit doesn't count.
CAVEATS = ("resolved as Duplicate or Won't Do",
           "is reconstructed from changelogs")


def check_figures(c, data):
    """The breakdown's carry-over and new work add up to the original commitment."""
    for outcome in OUTCOMES:
        split = tuple(a + b for a, b in zip(charted(data,
                      "carried_in", outcome), charted(data, "new", outcome)))
        c.check(split == charted(data, "original", outcome), "figures",
                f"carry-over and new work add up to the original commitment's {outcome.replace('_', ' ')}")


def commentary_of(md):
    """The paragraph right after the timeline table, as plain text, or None."""
    table = next((t for t in html_tables(
        md) if table_kind(t) == "timeline"), None)
    if table is None:
        return None
    after = [p for p in md.split(table, 1)[1].split("\n\n") if p.strip()]
    if not after or after[0].startswith("#"):
        return None
    return re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", after[0].strip())


def check_commentary(c, md, data):
    """The timeline's commentary states, from the spells, every way the sprint
    departed from the ideal and no other, within the word limit before its
    caveats, and the caveats whenever they apply."""
    text = commentary_of(md)
    if not c.check(text is not None, "commentary", "the timeline is followed by its commentary") or text is None:
        return
    sentences = re.split(r"(?<=\.) (?=[A-Z0-9])", text)
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
            estimates = [s["points"] for s in items if s["points"] is not None]
            amount = qty(len(items), sum(estimates) if estimates else None)
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
        amount = qty(len(open_spells), sum(
            s["points"] or 0 for s in open_spells))
        c.check(amount in core, "commentary",
                f"states what is still open, {amount}")
    else:
        expected = "Nothing is open" if data["sprint_status"] == "active" else "Everything in the sprint was completed by the close"
        c.check(expected in core, "commentary",
                "states that nothing is still open")
    keys = {s["key"] for s in spells}
    excluded = set(data.get("membership_cross_check_excluded_keys") or [])
    c.check(all(set(ISSUE_KEY.findall(sentence)) <=
                (keys | excluded if "is reconstructed from changelogs" in sentence else keys)
                for sentence in sentences), "commentary", "names only tickets of the sprint or its membership caveat")
    non_delivery = data["non_delivery_closures"]["count"]
    c.check(("resolved as Duplicate or Won't Do" in text) == bool(non_delivery), "commentary",
            "states the non-delivery closures" if non_delivery else "states no non-delivery closures")
    c.check(("is reconstructed from changelogs" in text) == bool(excluded), "commentary",
            "states the membership cross-check limitation" if excluded else "states no cross-check limitation")
    caveat_keys = [(CAVEATS[0], {s["key"] for s in spells
                                 if s["counted"] and s["closedAsNonDelivery"]}),
                   (CAVEATS[1], excluded)]
    for marker, expected_keys in caveat_keys:
        shown_keys = {key for sentence in sentences if marker in sentence
                      for key in ISSUE_KEY.findall(sentence)}
        c.check(shown_keys == expected_keys, "commentary",
                f"the {marker} caveat names every affected ticket and no others")


def check_framing(c, md):
    """Each big table has a heading directly above it (only charts may sit in
    between); the timeline also has a prose paragraph after it."""
    for table in html_tables(md):
        kind = table_kind(table)
        if kind is None:
            continue
        before, _, after = md.partition(table)
        headings = list(re.finditer(r"^##+ +(.+)$", before, re.M))
        if c.check(bool(headings), "headings", f"{kind} table has a heading above it"):
            between = "\n".join(
                line for line in before[headings[-1].end():].splitlines()
                if line.strip() and not re.fullmatch(r"!\[[^\]]*\]\([^)]*\)", line.strip()))
            c.check(between.strip() == "", "headings",
                    f"{kind} table directly follows '{headings[-1].group(1).strip()}'")
        if kind != "timeline":
            continue
        following = re.split(r"^##+ ", after, maxsplit=1, flags=re.M)[0]
        prose = "\n".join(line for line in following.splitlines()
                          if line.strip() and not line.lstrip().startswith(("<", "!", "|", "#")))
        c.check(len(prose.strip()) > 40, "commentary",
                f"{kind} table is followed by a paragraph")


def epic_figures(data):
    """{epic key: {scope: [completed, all, completed pts, all pts]}} recomputed
    from the counted spells, so a ticket under the wrong epic can't pass by
    agreeing with data.json's own epic figures."""
    figures = {}
    for spell in (s for s in data["spells"] if s["counted"]):
        row = figures.setdefault(spell["parentKey"] or NO_EPIC, {
                                 "original": [0] * 4, "extra": [0] * 4})[spell["scope"]]
        points = spell["points"] or 0
        row[1] += 1
        row[3] += points
        if spell["outcome"] == "completed":
            row[0] += 1
            row[2] += points
    return figures


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
            expected.append(ratio(done, total, done_pts,
                            total_pts) if total else "–")
        c.check(cells == expected, "epics",
                f"{epic['key']} shows {' '.join(expected)} (got {' '.join(cells)})")
        check_epic_commentary(c, epic, cells_of(row)[3], data["sprint_status"])
    for kind in ("original", "extra"):
        totals = tuple(sum(e[f"{kind}_{unit}_{part}"] for e in data["epics"])
                       for part in ("done", "total") for unit in ("stories", "points"))
        expected = charted(data, kind, "completed") + charted(data, kind)
        c.check(totals == expected, "epics",
                f"{kind} epic totals match the charts")


def check_epic_commentary(c, epic, cell, status):
    """The labels of the groups the epic has tickets to describe in, in order;
    "–" if there are none. The sentences are the agent's, checked when the
    report is written."""
    labels = [scope_group_label(g, status) for g in epic_groups(epic)]
    if not labels:
        c.check(cell.strip() == "–", "epics",
                f"{epic['key']} has no scope to describe, so its commentary is –")
        return
    lines = [re.match(r"<b>([^<]+):</b> (.+)", line.strip())
             for line in cell.split("<br>")]
    found = [m.group(1) if m else None for m in lines]
    c.check(found == labels, "epics",
            f"{epic['key']} commentary has {', '.join(labels)} (got {found})")


# The event kinds of a spell.
EVENT_KINDS = {"committed", "joined", "completed",
               "reopened", "reestimated", "removed"}


def tag_labels(e):
    """The tags the timeline shows for an event."""
    if e["type"] in ("committed", "joined"):
        return ["Added"] + (["Already done"] if e["done"] else [])
    if e["type"] == "reestimated":
        return [f"Re-estimated: {estimate(e['fromPoints'])} → {pts(e['points'])}"]
    return [{"completed": "Completed", "reopened": "Reopened", "removed": "Descoped"}[e["type"]]]


def text_of(cell):
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", cell)).split())


def check_model(c, data):
    """Each spell's events are well formed, and its outcome, latest estimate
    and whether it's counted are what its events give; the charts' breakdown,
    the burndown and the timeline are built from the same events."""
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


def section_of(md, heading):
    """The text under a "## " heading, up to the next one, or None."""
    parts = md.split(f"## {heading}\n", 1)
    return re.split(r"^## ", parts[1], maxsplit=1, flags=re.M)[0].strip() if len(parts) == 2 else None


def check_images(c, md, report_dir):
    embedded = re.findall(r"!\[[^\]]*\]\(([^)]+)\)", md)
    for name in CHART_FILES.values():
        c.check(name in embedded, "images", f"{name} embedded")
    for src in embedded:
        c.check(os.path.exists(os.path.join(report_dir, src)),
                "images", f"{src} exists")
    section = md.split("## Scope Timeline", 1)
    c.check(len(section) == 2 and CHART_FILES["burndown"] in re.split(r"^## ", section[1], maxsplit=1, flags=re.M)[0],
            "images", "burndown sits under the Scope Timeline heading")


def check_files(c, report_dir, data):
    extra = sorted(name for name in os.listdir(report_dir)
                   if not name.startswith(".") and name not in expected_files(data["label"]))
    c.check(not extra, "files",
            f"only the report's files are in the folder (unexpected: {extra or 'none'})")


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


def historical_references(data):
    """Allowed single-ticket references in the generator's fixed commentary phrases."""
    allowed = set()
    spells = data["spells"]
    latest = {s["key"]: s for s in spells}
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
            old = "–" if changes[0]["fromPoints"] is None else number(
                changes[0]["fromPoints"])
            allowed.add(f"{key} ({old} → {pts(points)}) was re-estimated")
        if events[0]["type"] == "joined" and any(s["key"] == key for s in spells[:index]):
            allowed.add(reference + "left the sprint and came back")
        if spell["counted"] and spell["closedAsNonDelivery"]:
            allowed.add(reference + "was resolved as Duplicate or Won't Do")
    for key in data.get("membership_cross_check_excluded_keys", []):
        allowed.add(
            f"{key} ({pts(latest.get(key, {}).get('points'))}) is reconstructed from changelogs")
    return allowed


def check_vocabulary(c, md, data):
    """The report's vocabulary and formats (see common.py's "The report's
    vocabulary and formats"), excluding copied Jira fields."""
    md = generated_text(md)
    text = re.sub(r'<a href="[^"]*">([^<]+)</a>', r"\1",
                  re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", md))
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", text)
    words = re.sub(r"<[^>]+>", " ", text)
    found = dict(banned_words(words.replace("(sprint closed)", "")))
    for rule, _ in BANNED_WORDS:
        c.check(rule not in found, "vocabulary",
                f"no {rule} {found.get(rule, [])[:3] or ''}".strip())
    decimals = re.findall(r"\d+\.\d+%", words)
    c.check(not decimals, "vocabulary",
            f"whole percentages only {decimals[:3] or ''}".strip())
    bare = re.findall(
        r"(?<![\d/.])\d+(?:\.\d+)?/\d+(?:\.\d+)?(?![\d/])(?!\.\d)(?! (?:tickets?|pts)\b)", words)
    c.check(not bare, "vocabulary",
            f"ratios only as N/M tickets (N/M pts) {bare[:3] or ''}".strip())
    old = re.findall(r"\d+ (?:tickets?|stories|story) / ", words)
    c.check(not old, "vocabulary",
            f"amounts only as N tickets (N pts) {old[:3] or ''}".strip())
    bold = re.findall(r"\*\*(.+?)\*\*", text) + \
        re.findall(r"<b>(.+?)</b>", text)
    c.check(all(b.endswith(":") for b in bold), "vocabulary",
            f"bold only for labels {[b for b in bold if not b.endswith(':')][:3] or ''}".strip())
    # Tickets in running text: one as KEY (N pts), with its latest estimate;
    # a list as (KEY, KEY), sorted. The timeline's cells are checked apart.
    prose = re.sub(r'<table style="font-size:75%">.*?</table>',
                   "", text, flags=re.S)
    prose = re.sub(r"<[^>]+>", " ", prose)
    latest = {}
    for spell in data["spells"]:
        latest[spell["key"]] = spell["points"]
    lists = re.findall(
        r"\((" + ISSUE_KEY.pattern + r"(?:, " + ISSUE_KEY.pattern + r")+)\)", prose)
    unsorted = [group for group in lists if group.split(
        ", ") != sorted(group.split(", "), key=key_order)]
    c.check(not unsorted, "vocabulary",
            f"ticket lists are sorted {unsorted[:2] or ''}".strip())
    rest = re.sub(
        r"\((" + ISSUE_KEY.pattern + r"(?:, " + ISSUE_KEY.pattern + r")*)\)", "", prose)
    rest = re.sub(r"^\| Goal \|.*$", "", rest, flags=re.M)
    # Commentary has fixed historical phrases; AI text uses the latest estimate.
    commentary = commentary_of(md) or ""
    commentary = re.sub(r"\((" + ISSUE_KEY.pattern +
                        r"(?:, " + ISSUE_KEY.pattern + r")*)\)", "", commentary)
    prose_commentary = commentary_of(text) or ""
    if prose_commentary:
        rest = rest.replace(re.sub(
            r"\((" + ISSUE_KEY.pattern + r"(?:, " + ISSUE_KEY.pattern + r")*)\)", "", prose_commentary), "", 1)
    pattern = r"(" + ISSUE_KEY.pattern + \
        r")(?: \((?:(?:\d+(?:\.\d+)?|–) → )?((?:\d+(?:\.\d+)?)|–) pts?\))?"
    wrong = []
    for found in re.finditer(pattern, rest):
        key, shown = found.group(1), found.group(2)
        if key in latest and shown != ("–" if latest[key] is None else number(latest[key])):
            wrong.append(found.group(0))
    c.check(not wrong, "vocabulary",
            f"a single ticket reads KEY (N pts), its latest estimate {wrong[:3] or ''}".strip())
    allowed = historical_references(data)
    wrong = [found.group(0) for found in re.finditer(pattern, commentary)
             if not any(commentary[found.start():].startswith(reference) for reference in allowed)]
    c.check(not wrong, "vocabulary",
            f"historical ticket estimates match their commentary event {wrong[:3] or ''}".strip())


def check_style(c, md):
    generated = generated_text(md)
    c.check("—" not in generated, "em dashes", "none in generated text")
    iso = re.findall(r"\b\d{4}-\d\d-\d\d\b", generated)
    c.check(not iso, "dates", f"no ISO dates {iso[:3] or ''}".strip())
    # The title is plain text; every other key, including copied fields, is linked.
    md = re.sub(r"^# Sprint Summary:.*$", "", md, flags=re.M)
    stripped = re.sub(r"\[[^\]]*\]\([^)]*\)", "", md)
    stripped = re.sub(r"<a\s[^>]*>.*?</a>", "", stripped, flags=re.S)
    unlinked = sorted(set(ISSUE_KEY.findall(stripped)))
    c.check(not unlinked, "links",
            f"every Jira key is linked (unlinked: {unlinked[:5] or 'none'})")


def run_checks(md, data, report_dir):
    tables = {table_kind(t): t for t in html_tables(md)}
    c = Checker()
    check_model(c, data)
    check_header(c, md, data)
    check_figures(c, data)
    check_commentary(c, md, data)
    check_framing(c, md)
    check_images(c, md, report_dir)
    check_files(c, report_dir, data)
    check_timeline(c, tables.get("timeline"), data)
    check_epics(c, tables.get("epics"), data)
    check_style(c, md)
    check_vocabulary(c, md, data)
    return c


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--report-dir", required=True,
                        help="report folder holding data.json and the report")
    args = parser.parse_args()

    data = load_json(os.path.join(args.report_dir, DATA_FILE))
    with open(os.path.join(args.report_dir, report_file(data["label"])), encoding="utf-8") as f:
        md = f.read()
    sys.exit(run_checks(md, data, args.report_dir).report())


if __name__ == "__main__":
    main()
