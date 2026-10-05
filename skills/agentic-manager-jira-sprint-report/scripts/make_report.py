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
  "epic_commentary": {"PROJ-10": "One sentence on this epic's own numbers."},
  "scope_notes": ["Why later scope was added, using bare Jira keys."],
  "delivery_commentary": "One factual conclusion supported by the epic table.",
  "key_achievements": ["One or two achievement bullets."],
  "blockers_risks": ["One or two blocker or risk bullets."],
  "retro_notes": ["Zero to three extra evidence-backed retro prompts."]
}

Bare Jira keys in content.json are linked here. Em dashes are replaced by
commas everywhere, including text that comes from Jira.
"""
import argparse
import html
import os
import re
from datetime import date
from typing import cast

from common import (CHART_FILES, CONTENT_FILE, DATA_FILE, ISSUE_KEY, NO_EPIC, display_date, load_json, number,
                    percentage, plural, points_text, pts, qty, report_file, target_completion, unit,
                    write_report_file)


def were(count):
    return plural(count, "was", "were")


def they(count):
    return plural(count, "it", "they")


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
        self.issues = {i["key"]: i for i in data["issues"] +
                       data["removed_issues"]}

    # --- links and cells

    def url(self, key):
        return f"{self.data['base_url']}/browse/{key}"

    def md_key(self, key):
        return f"[{key}]({self.url(key)})"

    def html_key(self, key):
        return f'<a href="{self.url(key)}">{html.escape(key)}</a>'

    def linkify(self, text):
        return ISSUE_KEY.sub(lambda m: self.md_key(m.group(0)), text)

    def linkify_html(self, text):
        return ISSUE_KEY.sub(lambda m: self.html_key(m.group(0)), html.escape(text))

    def table_text(self, text):
        return self.linkify(str(text).replace("\n", " ").replace("|", "\\|"))

    def points(self, keys):
        return sum(self.issues[k].get("storyPoints") or 0 for k in keys)

    def cell(self, groups, force_groups=False):
        """One of the two cell shapes the checker accepts. FLAT is a quantity
        and its keys. SUBCATEGORISED is the cell total, then one bold
        "Label, quantity" per group with its keys. groups is [(label, keys)];
        empty groups are skipped."""
        groups = [(label, keys) for label, keys in groups if keys]
        if not groups:
            return "–"
        all_keys = [k for _, keys in groups for k in keys]
        if len(groups) == 1 and not force_groups:
            return f"{qty(len(all_keys), self.points(all_keys))}<br>{self.key_list(all_keys)}"
        parts = [qty(len(all_keys), self.points(all_keys))]
        for label, keys in groups:
            parts.append(f"<b>{html.escape(label)}, {qty(len(keys), self.points(keys))}</b>"
                         f"<br>{self.key_list(keys)}")
        return "<br><br>".join(parts)

    def key_list(self, keys):
        return ", ".join(self.html_key(k) for k in keys)

    def added_cell(self, row):
        return self.cell([("New scope", row["added_keys"]), ("Reinstated", row["readded_keys"])],
                         force_groups=bool(row["readded_keys"]))

    def removed_cell(self, row):
        # Describe only what happened that day: an open issue leaving is
        # Descoped even if it returns later; its return is shown on that day.
        done = set(row["removed_done_keys"])
        departed = row["departure_keys"]
        return self.cell([
            ("Descoped", [k for k in departed if k not in done]),
            ("Already done", [k for k in departed if k in done
                              and self.issues[k]["alreadyDoneOnArrival"]]),
            ("Removed after completion", [k for k in departed if k in done
                                          and not self.issues[k]["alreadyDoneOnArrival"]]),
        ], force_groups=bool(departed))

    def completion_cell(self, row, origin):
        markers = {i["key"]: i["marker"]
                   for i in self.data["non_delivery_closures"]["issues"]}
        completed = row[f"completed_{origin}_keys"]
        arrived_done = row[f"already_done_{origin}_keys"]
        by_marker = {}
        for key in completed:
            if key in markers:
                by_marker.setdefault(markers[key], []).append(key)
        groups = [("Delivered", [k for k in completed if k not in markers])]
        groups += [(f"Closed as {m}", keys)
                   for m, keys in sorted(by_marker.items())]
        groups.append(("Already done", arrived_done))
        return self.cell(groups, force_groups=bool(arrived_done or by_marker))

    # --- tables

    def timeline_table(self):
        lines = ['<table>', '<tr>', '<th style="width:13%">Date</th>',
                 '<th style="width:28%">Added to sprint</th>', '<th style="width:18%">Removed from sprint</th>',
                 '<th style="width:26%">Completed (original)</th>', '<th style="width:15%">Completed (extra)</th>',
                 '</tr>']
        names = {"sprint_start": "sprint start",
                 "today": "today", "sprint_closed": "sprint closed"}
        timeline = self.data["scope_timeline"]
        for row in timeline:
            date_cell = display_date(
                row["date"]) + "".join(f"<br>({names[l]})" for l in row["labels"])
            cells = [date_cell, self.added_cell(row), self.removed_cell(row),
                     self.completion_cell(row, "original"), self.completion_cell(row, "extra")]
            lines += ["<tr>"] + [f"<td>{c}</td>" for c in cells] + ["</tr>"]

        def column(*fields):
            return (sum(len(r[f"{f}_keys"]) for r in timeline for f in fields),
                    sum(r[f"{f}_points"] for r in timeline for f in fields))
        totals = [column("added", "readded"), column("departure"),
                  column("completed_original", "already_done_original"),
                  column("completed_extra", "already_done_extra")]
        counts, points = self.data["commitment_breakdown_counts"], self.data["commitment_breakdown_points"]
        in_scope = [None, None, (counts["original_completed"], points["original_completed"]),
                    (counts["extra_completed"], points["extra_completed"])]
        cells = []
        for total, current in zip(totals, in_scope):
            value = qty(*total)
            # The Completed columns also show the figure still in the sprint
            # when it differs: the column counts completions credited in the
            # sprint window, the board shows what's still in it.
            if current is not None and current != total:
                value += f" (still in scope: {qty(*current)})"
            cells.append(f"<b>{value}</b>")
        lines += ["<tr>", "<td><b>Total</b></td>"] + \
            [f"<td>{c}</td>" for c in cells] + ["</tr>", "</table>"]
        return "\n".join(lines)

    def epic_table(self):
        lines = ['<table>', '<tr>', '<th style="width:20%">Epic</th>',
                 '<th style="width:9%">Original Stories</th>', '<th style="width:9%">Original Points</th>',
                 '<th style="width:9%">Extra Stories</th>', '<th style="width:9%">Extra Points</th>',
                 '<th style="width:44%">Commentary</th>', '</tr>']
        commentary = self.content["epic_commentary"]
        for epic in self.data["epics"]:
            name = html.escape(epic["name"] or "")
            title = name if epic["key"] == NO_EPIC else \
                f'<a href="{self.url(epic["key"])}">{html.escape(epic["key"])}: {name}</a>'

            def ratio(kind):
                if kind == "extra" and epic["extra_stories_total"] == 0:
                    return ["–", "–"]
                return [f'{epic[f"{kind}_stories_done"]}/{epic[f"{kind}_stories_total"]}',
                        f'{number(epic[f"{kind}_points_done"])}/{number(epic[f"{kind}_points_total"])}']
            cells = [title] + ratio("original") + ratio("extra") + \
                [self.linkify_html(commentary[epic["key"]])]
            lines += ["<tr>"] + [f"<td>{c}</td>" for c in cells] + ["</tr>"]
        lines.append("</table>")
        return "\n".join(lines)

    # --- generated prose

    def scope_summary(self):
        d = self.data
        oc, op, removed = d["outcome_counts"], d["outcome_points"], d["removed_summary"]
        open_word = "still open" if d["sprint_status"] == "active" else "carried over"
        descoped = removed["descoped_incomplete"]
        text = (f"**{d['points_total_issue_count']} issues ({points_text(sum(op.values()))})** are in scope: "
                f"{oc['completed']} completed ({points_text(op['completed'])}) and "
                f"{oc['carried_over']} {open_word} ({points_text(op['carried_over'])}). "
                f"The net removals include {descoped['count']} incomplete {unit(descoped['count'])} "
                f"({points_text(descoped['points'])}) genuinely descoped.")
        housekeeping = removed["already_done_on_arrival"]
        if housekeeping["count"]:
            text += (f" {housekeeping['count']} {unit(housekeeping['count'])} ({points_text(housekeeping['points'])}) "
                     f"{were(housekeeping['count'])} already Done when {they(housekeeping['count'])} entered the sprint "
                     "and later removed as housekeeping.")
        delivered = removed["completed_before_removal"]
        if delivered["count"]:
            text += (f" {delivered['count']} {unit(delivered['count'])} ({points_text(delivered['points'])}) "
                     f"{were(delivered['count'])} removed after completion.")
        arrived = [i for i in d["already_done_on_arrival"]
                   ["issues"] if i["stillInSprint"]]
        if arrived:
            arrived_points = sum(i["storyPoints"] or 0 for i in arrived)
            text += (f" The Completed columns include {len(arrived)} {unit(len(arrived))} "
                     f"({points_text(arrived_points)}) already Done when {they(len(arrived))} entered the sprint.")
        non_delivery = d["non_delivery_closures"]
        if non_delivery["count"]:
            keys = ", ".join(self.md_key(i["key"])
                             for i in non_delivery["issues"])
            text += (f" {keys}: {points_text(non_delivery['points'])} closed as non-delivery, "
                     "kept in Jira's Done total.")
        excluded = d.get("membership_cross_check_excluded_keys", [])
        if excluded:
            keys = ", ".join(self.md_key(key) for key in excluded)
            text += (f" Historical membership for {keys} is reconstructed from changelogs; "
                     "later sprint moves prevent comparison with Jira's current membership buckets.")
        return text

    def scope_notes(self):
        timeline, notes = self.data["scope_timeline"], []
        for row in timeline:
            for key in row["readded_keys"]:
                left = next(
                    (r["date"] for r in reversed(timeline)
                     if r["date"] < row["date"] and key in r["departure_keys"]), None)
                if left:
                    notes.append(f"{self.md_key(key)} left the sprint on {display_date(left)} and returned on "
                                 f"{display_date(row['date'])}; both movements are in the timeline totals.")
        return notes

    def health_notes(self):
        """The generated sprint-health review: the same dimensions every time,
        so the retro doesn't depend on which problem stood out."""
        d = self.data
        all_issues = d["issues"] + d["removed_issues"]
        original = [i for i in all_issues if not i["addedMidSprint"]]
        extra = [i for i in all_issues if i["addedMidSprint"]]
        original_points = sum(
            i["startState"]["storyPoints"] or 0 for i in original)
        extra_points = sum(i["storyPoints"] or 0 for i in extra)

        notes = [f"Planning baseline: {qty(len(original), original_points)} "
                 f"{were(len(original))} in the sprint when it started on {display_date(d['sprint_start'])}"]
        done_at_start = [i for i in original if i["startState"]["done"]]
        if done_at_start:
            done_points = sum(i["startState"]["storyPoints"]
                              or 0 for i in done_at_start)
            notes[0] += (f", {qty(len(done_at_start), done_points)} of them already Done, leaving "
                         f"{qty(len(original) - len(done_at_start), original_points - done_points)} to do "
                         "(the burndown's baseline)")
        notes[0] += "."

        closed, pool, excluded = target_completion(d)
        so_far = " so far" if d["sprint_status"] == "active" else ""
        excluded_text = (f"; excludes {len(excluded)} {plural(len(excluded), 'ticket', 'tickets')} "
                         f"already closed when the sprint started ({', '.join(excluded)})" if excluded else "")
        notes.append(f"Sprint target completion: {len(closed)}/{len(pool)} original-commitment tickets "
                     f"closed{so_far} ({percentage(len(closed), len(pool))}){excluded_text}.")

        if d["sprint_goal"]:
            # A multi-line goal is joined so its "- " lines don't become
            # separate list items.
            goal = " / ".join(line.strip().lstrip("-").strip()
                              for line in d["sprint_goal"].splitlines() if line.strip())
            notes.append(f"Goal discipline: Jira recorded the sprint goal as “{goal}”; the report verdict is "
                         f"{self.content['goal_verdict']}.")
        else:
            notes.append("Goal discipline: no sprint goal was set in Jira, so completion and scope decisions "
                         "can't be assessed against an explicit intended outcome.")

        notes.append(f"Scope added after commitment: {qty(len(extra), extra_points)}, equal to "
                     f"{percentage(len(extra), len(original))} of the initial story count and "
                     f"{percentage(extra_points, original_points)} of its points.")

        removed = d["removed_summary"]
        reinstated = [k for r in d["scope_timeline"]
                      for k in r["readded_keys"]]
        descoped = removed["descoped_incomplete"]
        housekeeping = removed["already_done_on_arrival"]
        delivered = removed["completed_before_removal"]
        notes.append(
            f"Scope removed or reversed: {qty(descoped['count'], descoped['points'])} "
            f"{were(descoped['count'])} genuinely descoped "
            f"({percentage(descoped['points'], original_points)} of initial points); "
            f"{qty(housekeeping['count'], housekeeping['points'])} "
            f"{were(housekeeping['count'])} already Done when {they(housekeeping['count'])} entered the sprint "
            "and removed as housekeeping; "
            f"{qty(delivered['count'], delivered['points'])} "
            f"{were(delivered['count'])} removed after completion; and "
            f"{qty(len(reinstated), self.points(reinstated))} {were(len(reinstated))} "
            "reinstated after a cross-day departure.")

        arrived_done = {i["key"]
                        for i in d["already_done_on_arrival"]["issues"]}

        def completion(origin, issues):
            pool = [i for i in issues if i["key"] not in arrived_done]
            keys = {k for r in d["scope_timeline"]
                    for k in r[f"completed_{origin}_keys"]}
            done_points = self.points(keys)
            total_points = sum(i["storyPoints"] or 0 for i in pool)
            return (f"{origin}: {len(keys)}/{len(pool)} stories ({percentage(len(keys), len(pool))}) and "
                    f"{number(done_points)}/{number(total_points)} points ({percentage(done_points, total_points)})")
        notes.append("Actionable completion (excluding work already Done when it entered the sprint): "
                     f"{completion('original', original)}; {completion('extra', extra)}.")

        already, non_delivery = d["already_done_on_arrival"], d["non_delivery_closures"]
        nd_keys = ", ".join(i["key"] for i in non_delivery["issues"]) or "none"
        notes.append(
            f"Board-data quality: {qty(already['count'], already['points'])} {were(already['count'])} "
            f"already Done when {they(already['count'])} entered the sprint, inflating the sprint's totals "
            "without being sprint delivery; "
            f"{qty(non_delivery['count'], non_delivery['points'])} in the Done total "
            f"{plural(non_delivery['count'], 'was a', 'were')} non-delivery "
            f"{plural(non_delivery['count'], 'closure', 'closures')} ({nd_keys}).")

        open_issues = [i for i in d["issues"] if i["carriedOver"]]
        by_status = {}
        for issue in open_issues:
            bucket = by_status.setdefault(issue["status"], [0, 0])
            bucket[0] += 1
            bucket[1] += issue["storyPoints"] or 0
        status_text = ", ".join(f"{n} {status} ({pts(p)})"
                                for status, (n, p) in sorted(by_status.items())) or "none"
        open_keys = {i["key"] for i in open_issues}
        blockers = ", ".join(
            k for k in d["blocker_candidate_keys"] if k in open_keys) or "none"
        state = "remain open" if d["sprint_status"] == "active" else "carried over"
        notes.append(f"Unfinished-work shape: {qty(len(open_issues), sum(i['storyPoints'] or 0 for i in open_issues))}"
                     f" {state}{self.days_left(' with ')}; status mix is {status_text}; "
                     f"blocker candidates are {blockers}.")
        return notes

    def days_left(self, prefix):
        if self.data["sprint_status"] != "active":
            return ""
        days = (date.fromisoformat(
            self.data["sprint_end"]) - date.fromisoformat(self.data["today"])).days
        if days >= 0:
            return f"{prefix}{days} calendar days remaining"
        return f"{prefix}the recorded end date {-days} calendar days overdue"

    # --- the report

    def bullets(self, heading, items):
        return f"{heading}\n\n" + "\n".join(f"- {self.linkify(item)}" for item in items)

    def build(self):
        d, c = self.data, self.content
        start, end = display_date(
            d["sprint_start"]), display_date(d["sprint_end"])
        dates = f"{start}–{end}"
        if d["sprint_complete_date"] and d["sprint_complete_date"] != d["sprint_end"]:
            dates += f" (completed {display_date(d['sprint_complete_date'])})"
        goal = ("<br>".join(self.table_text(line.strip()) for line in d["sprint_goal"].splitlines() if line.strip())
                if d["sprint_goal"] else "*No goal was set in Jira for this sprint*")
        # Jira has no page for a sprint, so the title links nothing.
        parts = [f"# Sprint Summary: {d['sprint_name']}"]
        if d["sprint_status"] == "active":
            parts.append(f"This is a mid-sprint snapshot as at {display_date(d['today'])}"
                         f"{self.days_left(', with ')}. \"Still open\" means unfinished in the active sprint, "
                         "not moved to a future sprint.")
        parts += [
            f"| Field | Detail |\n|---|---|\n| Dates | {dates} |\n| Goal | {goal} |\n"
            f"| Goal outcome | {self.table_text(c['goal_verdict'])} |",
            f"![Sprint outcome by stories]({CHART_FILES['outcome_stories']})",
            f"![Sprint outcome by points]({CHART_FILES['outcome_points']})",
            "## Scope Timeline",
            f"![Sprint burndown]({CHART_FILES['burndown']})",
            self.timeline_table(),
            self.scope_summary(),
        ]
        parts += self.scope_notes()
        parts += [self.linkify(note) for note in c["scope_notes"]]
        parts += [
            "## Delivery by Epic",
            self.epic_table(),
            self.linkify(c["delivery_commentary"]),
            self.bullets("## Key Achievements", c["key_achievements"]),
            self.bullets("## Blockers & Risks", c["blockers_risks"]),
            "## Notes for Sprint Retro",
        ]
        if c["retro_notes"]:
            parts.append(self.bullets(
                "### Discussion Points", c["retro_notes"]))
        parts.append(self.bullets(
            "### Sprint Health Data", self.health_notes()))
        return "\n\n".join(parts).rstrip() + "\n"


def validate_content(content, data):
    problems = []
    bounds = {"scope_notes": (0, None), "key_achievements": (1, 2), "blockers_risks": (1, 2),
              "retro_notes": (0, 3)}
    for field, (low, high) in bounds.items():
        value = content.get(field)
        if (not isinstance(value, list) or len(value) < low or (high is not None and len(value) > high)
                or any(not isinstance(v, str) or not v.strip() for v in value)):
            problems.append(
                f"{field} must be a list of {low}{'+' if high is None else f'-{high}'} non-empty strings")
    for field in ("goal_verdict", "delivery_commentary"):
        if not isinstance(content.get(field), str) or not content[field].strip():
            problems.append(f"{field} must be a non-empty string")
    commentary = content.get("epic_commentary")
    if not isinstance(commentary, dict):
        problems.append("epic_commentary must map each epic key to a sentence")
    else:
        missing = [e["key"] for e in data["epics"]
                   if not isinstance(commentary.get(e["key"]), str) or not commentary[e["key"]].strip()]
        if missing:
            problems.append(
                f"epic_commentary is missing: {', '.join(missing)}")
    if problems:
        raise SystemExit("content.json:\n  - " + "\n  - ".join(problems))


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--report-dir", required=True,
                        help="report folder holding data.json and content.json")
    args = parser.parse_args()

    data = cast(dict, strip_em_dashes(
        load_json(os.path.join(args.report_dir, DATA_FILE))))
    content = cast(dict, strip_em_dashes(
        load_json(os.path.join(args.report_dir, CONTENT_FILE))))
    validate_content(content, data)
    out = os.path.join(args.report_dir, report_file(data["label"]))
    write_report_file(out, Report(data, content).build())
    print("wrote", out)


if __name__ == "__main__":
    main()
