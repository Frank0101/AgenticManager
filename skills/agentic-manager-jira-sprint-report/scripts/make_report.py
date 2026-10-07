"""
Write the sprint report Markdown from <report_dir>/data.json and the
judgment text in <report_dir>/content.json.

Usage:
    python3 make_report.py --report-dir <report_dir>

Writes <report_dir>/<label>_Sprint_Report.md. build_sprint_data.py owns the
numbers and this script owns the formatting: every figure, table cell, total,
date, link and the generated notes come from data.json. content.json holds only
what needs judgment:

{
  "goal_verdict": "Partially met",
  "epic_commentary": {"PROJ-10": {"completed": "One sentence on the scope completed.",
                                  "in_review": "...", "not_completed": "...", "descoped": "..."}},
  "key_achievements": "A paragraph on the scope completed across the epics.",
  "blockers_risks": "A paragraph on the commitment still open, and why where stated.",
  "retro_notes": ["A fact the report shows, then a question for the team?"]
}

Bare Jira keys in content.json are linked here. Em dashes are replaced by
commas in judgment text only; copied Jira goals and names retain their wording.
"""
import argparse
import html
import os
import re
from datetime import date
from typing import cast

from common import (CHART_FILES, CONTENT_FILE, DATA_FILE, ISSUE_KEY, NO_EPIC, RETRO_NOTES, SCOPE_GROUPS, ai,
                    allowed_verdicts,
                    display_date, epic_groups, estimate, key_order, parse_ts, load_json, outcome_total, plural, pts, qty, ratio,
                    report_file, scope_group_label, target_completion, ticket_ref, unit, whole_percentage,
                    write_report_file)


# The timeline's event tags: (label, background, text colour). Each sets both
# colours, so it reads the same in light and dark previews; the colours follow
# the outcome charts where they share a meaning.
TAGS = {
    "added": ("Added", "#2a78d6", "#ffffff"),
    "already_done": ("Already done", "#1a7f37", "#ffffff"),
    "completed": ("Completed", "#0ca30c", "#ffffff"),
    "reopened": ("Reopened", "#fab219", "#1a1a1a"),
    "removed": ("Descoped", "#b5b2aa", "#1a1a1a"),
    "reestimated": ("Re-estimated", "#9c27b0", "#ffffff"),
}


def tag(kind, suffix=""):
    label, background, colour = TAGS[kind]
    return (f'<span style="background:{background};color:{colour};border-radius:10px;padding:1px 7px;'
            f'margin:1px 3px 1px 0;font-size:90%;white-space:nowrap;display:inline-block">'
            f'{html.escape(label + suffix)}</span>')


# The timeline commentary's length, before its caveats.
COMMENTARY_WORDS = 100


def amount(spells):
    """The amount of work of some spells: "N tickets (N pts)", "– pts" if
    none has an estimate."""
    estimates = [s["points"] for s in spells if s["points"] is not None]
    return qty(len(spells), sum(estimates) if estimates else None)


def plain_words(text):
    """The words of Markdown text as a reader sees them: links as their text."""
    return re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text).split()


def were(count):
    return plural(count, "was", "were")


def strip_em_dashes(value):
    if isinstance(value, str):
        return re.sub(r"\s*—\s*", ", ", value)
    if isinstance(value, dict):
        return {k: strip_em_dashes(v) for k, v in value.items()}
    if isinstance(value, list):
        return [strip_em_dashes(v) for v in value]
    return value


class Report:
    def __init__(self, data, content):
        self.data = data
        self.content = content

    # --- links and cells

    def url(self, key):
        return f"{self.data['base_url']}/browse/{key}"

    def md_key(self, key):
        return f"[{key}]({self.url(key)})"

    def html_key(self, key):
        return f'<a href="{self.url(key)}">{html.escape(key)}</a>'

    def linkify(self, text):
        return ISSUE_KEY.sub(lambda m: self.md_key(m.group(0)), text)

    def table_text(self, text):
        return self.linkify(str(text).replace("\n", " ").replace("|", "\\|"))

    # --- tables

    def tags(self, event):
        """An event as its tags (see TAGS), in the order they happened."""
        if event["type"] in ("committed", "joined"):
            return tag("added") + (tag("already_done") if event["done"] else "")
        if event["type"] == "reestimated":
            return tag("reestimated", f": {estimate(event['fromPoints'])} → {pts(event['points'])}")
        return tag(event["type"])

    def end_of_day(self, row):
        """The day's figures: on the first day, the whole commitment; on every
        day of the burndown, what was open at its end, as the burndown shows."""
        d, parts = self.data, []
        if "sprint_start" in row["labels"]:
            original = [t for t in d["spells"] if t["scope"] == "original"]
            parts.append(
                f"<b>Commitment:</b><br>{qty(len(original), d['burndown_baseline'])}")
        reading = next(
            (r for r in d["burndown"] if r["date"] == row["date"]), None)
        if reading:
            parts.append(f"<b>Open:</b><br>{qty(reading['committed_stories'], reading['committed'])} of the "
                         f"commitment<br>{qty(reading['total_stories'], reading['total'])} with extra")
        return "<br><br>".join(parts) or "–"

    def timeline_table(self):
        """Every spell's events by day: one row per ticket with events that
        day, its estimate at the end of the day and its events as tags in time
        order; the day's date and end-of-day figures span its rows."""
        lines = ['<table style="font-size:75%">', '<tr>', '<th style="width:14%">Date</th>',
                 '<th style="width:14%">Ticket</th>', '<th style="width:46%">Events</th>',
                 '<th style="width:26%">End of day</th>', '</tr>']
        names = {"sprint_start": "sprint start",
                 "today": "today", "sprint_closed": "sprint closed"}
        for row in self.data["timeline"]:
            stories = {}
            for e in row["events"]:
                stories.setdefault(e["key"], []).append(e)
            date = display_date(
                row["date"]) + "".join(f"<br>({names[l]})" for l in row["labels"])
            span = max(len(stories), 1)
            first = [
                f'<td rowspan="{span}" style="vertical-align:top">{date}</td>']
            last = [
                f'<td rowspan="{span}" style="vertical-align:top">{self.end_of_day(row)}</td>']
            if not stories:
                lines.append(
                    "<tr>" + first[0] + '<td colspan="2">–</td>' + last[0] + "</tr>")
                continue
            for index, key in enumerate(sorted(stories, key=key_order)):
                events = sorted(stories[key], key=lambda e: parse_ts(e["at"]))
                cells = [f'<td style="white-space:nowrap">{ticket_ref(self.html_key(key), events[-1]["points"])}</td>',
                         "<td>" + "".join(self.tags(e) for e in events) + "</td>"]
                lines.append("<tr>" + "".join((first if index == 0 else []) + cells
                                              + (last if index == 0 else [])) + "</tr>")
        lines.append("</table>")
        return "\n".join(lines)

    def epic_commentary(self, epic):
        """One labelled sentence per group the epic has tickets in, or "–"."""
        text = self.content["epic_commentary"].get(epic["key"]) or {}
        lines = [f"<b>{scope_group_label(g, self.data['sprint_status'])}:</b> {html.escape(text[g])}"
                 for g in epic_groups(epic)]
        return "<br>".join(lines) or "–"

    def epic_table(self):
        """Per epic, the commitment's and the extra work's tickets completed,
        out of all of them: "N/M tickets (N/M pts)", and the scope it covers."""
        lines = ['<table>', '<tr>', '<th style="width:20%">Epic</th>', '<th style="width:14%">Commitment</th>',
                 '<th style="width:14%">Extra</th>', f'<th style="width:52%">{ai("Commentary")}</th>', '</tr>']
        for epic in self.data["epics"]:
            name = html.escape(epic["name"] or "")
            title = name if epic["key"] == NO_EPIC else \
                f'<a href="{self.url(epic["key"])}">{html.escape(epic["key"])}: {name}</a>'

            def done_of(kind):
                if epic[f"{kind}_stories_total"] == 0:
                    return "–"
                return ratio(epic[f"{kind}_stories_done"], epic[f"{kind}_stories_total"],
                             epic[f"{kind}_points_done"], epic[f"{kind}_points_total"])
            cells = [title, done_of("original"), done_of(
                "extra"), self.epic_commentary(epic)]
            lines += ["<tr>"] + [f"<td>{c}</td>" for c in cells] + ["</tr>"]
        lines.append("</table>")
        return "\n".join(lines)

    def header_table(self):
        """The table above the charts: always these rows, in this order (see
        the skill's Header table section)."""
        d = self.data
        dates = f"{display_date(d['sprint_start'])}–{display_date(d['sprint_end'])}"
        if d["sprint_complete_date"] and d["sprint_complete_date"] != d["sprint_end"]:
            dates += f" (completed {display_date(d['sprint_complete_date'])})"
        goal = ("<br>".join(self.table_text(line.strip()) for line in d["sprint_goal"].splitlines() if line.strip())
                if d["sprint_goal"] else "*No goal was set in Jira for this sprint*")
        rows = [("Dates", dates), ("Goal", goal),
                (ai("Goal outcome"), self.table_text(
                    self.content["goal_verdict"])),
                ("Sprint target completion", self.target_completion_value()),
                self.carry_over_row()]
        return "| Field | Detail |\n|---|---|\n" + "\n".join(f"| {label} | {value} |" for label, value in rows)

    def target_completion_value(self):
        """The original commitment's spells completed: their whole percentage,
        then the ratios."""
        closed, pool = target_completion(self.data)
        original = [s for s in self.data["spells"] if s["scope"] == "original"]
        done_points = sum(
            s["points"] or 0 for s in original if s["outcome"] == "completed")
        so_far = " so far" if self.data["sprint_status"] == "active" else ""
        return (f"{whole_percentage(len(closed), len(pool))}, "
                f"{ratio(len(closed), len(pool), done_points, sum(s['points'] or 0 for s in original))} "
                f"completed{so_far}")

    def carry_over_row(self):
        """(label, value): the part of the original commitment carried over
        from the previous sprint."""
        d = self.data
        previous = d["previous_sprint"]
        if not previous:
            return "Carried over", "None: no earlier sprint on this board"
        counts, points = d["outcome_breakdown_counts"], d["outcome_breakdown_points"]
        carried = (outcome_total(counts, "carried_in"),
                   outcome_total(points, "carried_in"))
        original = (outcome_total(counts, "original"),
                    outcome_total(points, "original"))
        done = (counts["carried_in_completed"], points["carried_in_completed"])
        so_far = " so far" if d["sprint_status"] == "active" else ""
        return (f"Carried over from {self.table_text(previous['name'])}",
                f"{carried[0]} {unit(carried[0])} \\| {whole_percentage(carried[0], original[0])} of commitment "
                f"({pts(carried[1])} \\| {whole_percentage(carried[1], original[1])}); "
                f"{qty(*done)} completed{so_far}")

    # --- generated prose

    def commentary(self):
        """The timeline's commentary: everything that departed from the ideal
        sprint (all of it committed on the first day, completed steadily,
        nothing left at the end), from the spells alone, in at most
        COMMENTARY_WORDS words before its caveats. A kind of departure names
        its tickets when it has up to three, else counts them; if the text is
        still too long, all are counted."""
        text = self.commentary_text(name_up_to=3)
        if len(plain_words(text)) > COMMENTARY_WORDS:
            text = self.commentary_text(name_up_to=0)
            text = text.replace(
                "counting as descoped and then as extra", "descoped, then extra")
            text = text.replace("of them without an estimate", "unestimated")
        return " ".join([text] + self.commentary_caveats())

    def mentioned(self, spells, one, many, name_up_to=3):
        """Tickets in running text: one ticket as "KEY (N pts) <one>", a list
        as "N tickets (N pts) <many> (KEY, KEY)", the keys left out above
        `name_up_to`. A "{keys}" in `many` places the list there instead of
        at the end."""
        keys = sorted({s["key"] for s in spells}, key=key_order)
        if len(spells) == 1 and name_up_to:
            return f"{ticket_ref(self.md_key(keys[0]), spells[0]['points'])} {one}"
        listed = f" ({', '.join(self.md_key(k) for k in keys)})" if len(
            keys) <= name_up_to else ""
        phrase = (one if len(spells) == 1 else many).replace("{keys}", "")
        if "{keys}" in many and len(spells) > 1:
            return f"{amount(spells)} {many.replace('{keys}', listed)}"
        return f"{amount(spells)} {phrase}{listed}"

    def reestimates(self, spells, name_up_to):
        """Re-estimated tickets: one as "KEY (old → new pts) was re-estimated",
        a list as "N tickets (old → new pts) were re-estimated (KEY, KEY)",
        from the estimates before the first re-estimate to the latest."""
        def before(spell):
            return next(e["fromPoints"] for e in spell["events"] if e["type"] == "reestimated")

        def total(values):
            known = [v for v in values if v is not None]
            return estimate(sum(known)) if known else "–"
        keys = sorted({s["key"] for s in spells}, key=key_order)
        known = [s['points'] for s in spells if s['points'] is not None]
        change = f"{total(before(s) for s in spells)} → {pts(sum(known) if known else None)}"
        if len(spells) == 1 and name_up_to:
            return f"{self.md_key(keys[0])} ({change}) was re-estimated"
        listed = f" ({', '.join(self.md_key(k) for k in keys)})" if len(
            keys) <= name_up_to else ""
        return f"{len(spells)} {unit(len(spells))} ({change}) {plural(len(spells), 'was', 'were')} re-estimated{listed}"

    def commentary_text(self, name_up_to):
        d, spells = self.data, self.data["spells"]

        def say(found, one, many):
            return self.mentioned(found, one, many, name_up_to)
        original = [s for s in spells if s["scope"] == "original"]
        sentences = []

        already = [dict(s, points=s["events"][0]["points"])
                   for s in original if s["events"][0]["done"]]
        descoped = [s for s in original if s["outcome"] == "removed"]
        parts = []
        if already:
            parts.append(say(already, "was already Done at the start",
                         "were already Done at the start"))
        if descoped:
            parts.append(say(descoped, "was descoped", "were descoped"))
        committed = qty(len(original), d["burndown_baseline"])
        sentences.append(f"Of the {committed} in the commitment, " + ", and ".join(parts) if parts
                         else f"{'The' if len(original) == 1 else 'All'} {committed} in the commitment stayed in the "
                         "sprint")

        extra = [s for s in spells if s["scope"] == "extra" and s["counted"]]
        dropped = [s for s in spells if not s["counted"]]
        parts = []
        if extra:
            unestimated = [s for s in extra if s["points"] is None]
            parts.append(say(extra, "was added as extra", "were added as extra")
                         + (f", {qty(len(unestimated), None)} of them without an estimate"
                            if unestimated and len(extra) > 1 else ""))
        if dropped:
            parts.append(say(dropped, "was added and descoped again, so it doesn't count",
                             "were added and descoped again{keys}, so they don't count"))
        if parts:
            sentences.append("; ".join(parts))

        returns = [s for i, s in enumerate(spells)
                   if s["events"][0]["type"] == "joined" and any(o["key"] == s["key"] for o in spells[:i])]
        reopened = [s for s in spells if any(
            e["type"] == "reopened" for e in s["events"])]
        reestimated = [s for s in spells if any(
            e["type"] == "reestimated" for e in s["events"])]
        parts = []
        if reopened:
            parts.append(say(reopened, "was reopened", "were reopened"))
        if reestimated:
            parts.append(self.reestimates(reestimated, name_up_to))
        if returns:
            parts.append(say(returns, "left the sprint and came back, counting as descoped and then as extra",
                             "left the sprint and came back, counting as descoped and then as extra"))
        if parts:
            sentence = ", ".join(
                parts[:-1]) + (" and " if len(parts) > 1 else "") + parts[-1]
            sentences.append(sentence[0].upper() + sentence[1:])

        open_spells = [s for s in spells if s["counted"]
                       and s["outcome"] == "not_completed"]
        open_original = [s for s in open_spells if s["scope"] == "original"]
        total = qty(len(open_spells), sum(
            s["points"] or 0 for s in open_spells))
        if len(open_original) == len(open_spells):
            of_them = ""
        elif not open_original:
            of_them = ", all of it extra"
        else:
            committed_open = qty(len(open_original), sum(
                s["points"] or 0 for s in open_original))
            of_them = f", {committed_open} of them from the commitment"
        if d["sprint_status"] == "active":
            left = self.days_left(", with ")
            sentences.append(f"{total} {plural(len(open_spells), 'is', 'are')} open{of_them}{left}"
                             if open_spells else f"Nothing is open{left}")
        else:
            sentences.append(f"At the close, {total} {were(len(open_spells))} not completed{of_them}"
                             if open_spells else "Everything in the sprint was completed by the close")
        return " ".join(s + "." for s in sentences)

    def commentary_caveats(self):
        """Data-quality warnings, never cut for length."""
        d, caveats = self.data, []
        non_delivery = [s for s in d["spells"]
                        if s["counted"] and s["closedAsNonDelivery"]]
        if non_delivery:
            caveats.append(self.mentioned(non_delivery, "was resolved as Duplicate or Won't Do and counts as completed",
                                          "were resolved as Duplicate or Won't Do and count as completed", 99) + ".")
        excluded = d.get("membership_cross_check_excluded_keys", [])
        if excluded:
            found = [next((s for s in reversed(d["spells"]) if s["key"] == k), {"key": k, "points": None})
                     for k in excluded]
            caveats.append("The membership of " + self.mentioned(found, "is reconstructed from changelogs",
                                                                 "is reconstructed from changelogs", 99)
                           + ", as later sprint moves prevent checking it against Jira.")
        return caveats

    def days_left(self, prefix):
        if self.data["sprint_status"] != "active":
            return ""
        days = (date.fromisoformat(
            self.data["sprint_end"]) - date.fromisoformat(self.data["today"])).days
        if days == 0:
            return f"{prefix}no days left"
        if days > 0:
            return f"{prefix}{days} {plural(days, 'day', 'days')} left"
        return f"{prefix}{-days} {plural(-days, 'day', 'days')} past the end date"

    # --- the report

    def bullets(self, heading, items):
        return f"{heading}\n\n" + "\n".join(f"- {self.linkify(item)}" for item in items)

    def build(self):
        d, c = self.data, self.content
        # Jira has no page for a sprint, so the title links nothing.
        parts = [f"# Sprint Summary: {d['sprint_name']}"]
        if d["sprint_status"] == "active":
            parts.append(f"This is a mid-sprint snapshot as at {display_date(d['today'])}"
                         f"{self.days_left(', with ')}. \"Open\" means not completed yet.")
        parts += [
            self.header_table(),
            f"![Sprint outcome in tickets]({CHART_FILES['outcome_stories']})",
            f"![Sprint outcome in pts]({CHART_FILES['outcome_points']})",
            "## Scope Timeline",
            f"![Sprint burndown]({CHART_FILES['burndown']})",
            self.timeline_table(),
            self.commentary(),
        ]
        parts += [
            "## Delivery by Epic",
            self.epic_table(),
            f"## {ai('Key Achievements')}",
            self.linkify(c["key_achievements"]),
            f"## {ai('Blockers & Risks')}",
            self.linkify(c["blockers_risks"]),
            self.bullets(
                f"## {ai('Notes for Sprint Retro')}", c["retro_notes"]),
        ]
        return "\n\n".join(parts).rstrip() + "\n"


def validate_content(content, data):
    problems = []
    if "scope_notes" in content:
        problems.append(
            "scope_notes is no longer used: the timeline's commentary is generated from the data")
    for field in ("key_achievements", "blockers_risks"):
        if not isinstance(content.get(field), str) or not content[field].strip():
            problems.append(
                f"{field} must be a non-empty string: one paragraph")
    notes = content.get("retro_notes")
    if (not isinstance(notes, list) or not 1 <= len(notes) <= RETRO_NOTES
            or any(not isinstance(n, str) or not n.strip().endswith("?") for n in notes)):
        problems.append(
            f"retro_notes must be a list of 1-{RETRO_NOTES} notes, each ending with a question")
    if "delivery_commentary" in content:
        problems.append(
            "delivery_commentary is no longer used: each epic's commentary says what it delivered")
    if content.get("goal_verdict") not in allowed_verdicts(data):
        problems.append("goal_verdict must be one of: " +
                        ", ".join(f'"{v}"' for v in allowed_verdicts(data)))
    commentary = content.get("epic_commentary")
    if not isinstance(commentary, dict):
        problems.append(
            "epic_commentary must map each epic key to its groups' sentences")
    else:
        for epic in data["epics"]:
            groups, given = epic_groups(
                epic), commentary.get(epic["key"]) or {}
            if not isinstance(given, dict):
                problems.append(
                    f"epic_commentary.{epic['key']} must map each group to a sentence")
                continue
            written = [g for g in SCOPE_GROUPS if isinstance(
                given.get(g), str) and given[g].strip()]
            if written != groups or set(given) - set(groups):
                problems.append(f"epic_commentary.{epic['key']} needs a sentence for exactly these groups: "
                                + (", ".join(groups) or "none"))
    if problems:
        raise SystemExit("content.json:\n  - " + "\n  - ".join(problems))


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--report-dir", required=True,
                        help="report folder holding data.json and content.json")
    args = parser.parse_args()

    data = load_json(os.path.join(args.report_dir, DATA_FILE))
    content = cast(dict, strip_em_dashes(
        load_json(os.path.join(args.report_dir, CONTENT_FILE))))
    validate_content(content, data)
    out = os.path.join(args.report_dir, report_file(data["label"]))
    write_report_file(out, Report(data, content).build())
    print("wrote", out)


if __name__ == "__main__":
    main()
