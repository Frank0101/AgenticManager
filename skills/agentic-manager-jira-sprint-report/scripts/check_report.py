"""
Check a finished sprint report against the data it was built from and against
the report's formatting rules.

Usage:
    python3 check_report.py --report-dir <report_dir>

Prints every check and exits non-zero if any fails. make_report.py generates
the mechanical structure and content.json supplies judgment prose; this is the
independent contract test for both. Every rule here exists because the same
table drifted when it was corrected by hand; prose guidance alone didn't stop
the regressions, a failing check does.

  figures      headline numbers in the prose match data.json
  movements    every cross-day departure and return is visible in the table
  images       embedded charts exist; the burndown sits under Scope Timeline
  headings     each table has a heading directly above it
  commentary   each table is followed by a prose paragraph
  timeline     the scope timeline table is there
  columns      the Total row matches data.json and the day cells sum to it
  cell shapes  every timeline cell is FLAT or SUBCATEGORISED
  subgroups    a subcategorised cell's groups sum to its total
  totals row   only the total, plus the in-scope figure on Completed columns
               when it differs
  quantities   one format everywhere: "N stories / N pts"
  spacing      a single <br> between a quantity and its own list
  epics        epic table cells match data.json
  retro        the sprint-health notes cover scope, completion and quality
  dates        DD/MM/YYYY only
  em dashes    none
  links        every Jira key is a link
"""
import argparse
import os
import re
import sys

from common import (CHART_FILES, DATA_FILE, ISSUE_KEY, NO_EPIC, display_date, load_json, number, percentage, points_text,
                    qty, report_file, target_completion)

QTY = r"(\d+) (?:stories|story) / (\d+(?:\.\d+)?) pts?"
RETRO_HEADING = "## Notes for Sprint Retro"
NUMBER_WORDS = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
                "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen",
                "nineteen", "twenty"]


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


def has_key(cell, key):
    """True if the cell links exactly this key (PROJ-1 isn't PROJ-10)."""
    return f">{key}</a>" in cell


def strip_tags(text):
    return re.sub(r"<[^>]+>", " ", text).strip()


def parsed_number(text):
    value = float(text)
    return int(value) if value.is_integer() else value


def table_kind(table):
    header = strip_tags(rows_of(table)[0]).lower()
    if "date" in header and "added to sprint" in header:
        return "timeline"
    if "epic" in header and "commentary" in header:
        return "epics"
    return None


def prose_has(md, count, points):
    """Accepts wording such as "5 (14 points)", "5 incomplete stories worth 14
    points" or "five stories, 14 pts", outside the tables."""
    forms = [str(count)] + ([NUMBER_WORDS[count]]
                            if count < len(NUMBER_WORDS) else [])
    pattern = (
        rf"\b(?:{'|'.join(forms)})\b[^\n]{{0,100}}?\b{re.escape(number(points))}\s*(?:points?|pts)\b")
    return re.search(pattern, re.sub(r"<table.*?</table>", "", md, flags=re.S), re.I) is not None


def check_figures(c, md, data):
    oc, op = data["outcome_counts"], data["outcome_points"]
    open_word = "still open" if data["sprint_status"] == "active" else "carried over"
    in_scope = f"{data['points_total_issue_count']} issues ({points_text(sum(op.values()))})"
    c.check(in_scope in md, "figures", f"in scope {in_scope} stated")
    c.check(f"{oc['completed']} completed ({points_text(op['completed'])})" in md,
            "figures", f"completed {oc['completed']} ({points_text(op['completed'])}) stated")
    c.check(f"{oc['carried_over']} {open_word} ({points_text(op['carried_over'])})" in md,
            "figures", f"{open_word} {oc['carried_over']} ({points_text(op['carried_over'])}) stated")
    descoped = data["removed_summary"]["descoped_incomplete"]
    c.check(prose_has(md, descoped["count"],
            descoped["points"]), "figures", "descope stated")
    if data.get("membership_cross_check_excluded_keys"):
        c.check("later sprint moves prevent comparison with Jira's current membership buckets" in md,
                "figures", "historical membership comparison limitation stated")


def check_movements(c, timeline, data):
    if timeline is None:
        return
    issues = {i["key"]: i for i in data["issues"] + data["removed_issues"]}
    rendered = [cells_of(r) for r in rows_of(timeline)[1:]]
    for row in data["scope_timeline"]:
        label = display_date(row["date"])
        cells = next(
            (r for r in rendered if r and label in strip_tags(r[0])), None)
        if not c.check(cells is not None, "movements", f"{label} has a row") or cells is None:
            continue
        for key in row["readded_keys"]:
            c.check("Reinstated" in cells[1] and has_key(cells[1], key),
                    "movements", f"{key} return shown as Reinstated on {label}")
        for key in row["departure_keys"]:
            if key not in row["removed_done_keys"]:
                expected = "Descoped"
            elif issues[key]["alreadyDoneOnArrival"]:
                expected = "Already done"
            else:
                expected = "Removed after completion"
            c.check(expected in cells[2] and has_key(cells[2], key),
                    "movements", f"{key} departure shown as {expected} on {label}")


def check_framing(c, md):
    """Each big table has a heading directly above it (only charts may sit in
    between) and a prose paragraph after it."""
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
        following = re.split(r"^##+ ", after, maxsplit=1, flags=re.M)[0]
        prose = "\n".join(line for line in following.splitlines()
                          if line.strip() and not line.lstrip().startswith(("<", "!", "|", "#")))
        c.check(len(prose.strip()) > 40, "commentary",
                f"{kind} table is followed by a paragraph")


def check_timeline(c, timeline, data):
    if not c.check(timeline is not None, "timeline", "table found"):
        return
    body = [cs for cs in (cells_of(r) for r in rows_of(timeline)[1:]) if cs]
    total_row = next(
        (cs for cs in body if strip_tags(cs[0]).lower() == "total"), None)
    if not c.check(total_row is not None, "totals row", "present") or total_row is None:
        return

    tl = data["scope_timeline"]

    def column(*fields):
        return (sum(len(r[f"{f}_keys"]) for r in tl for f in fields),
                sum(r[f"{f}_points"] for r in tl for f in fields))
    names = ["Added", "Removed", "Completed (original)", "Completed (extra)"]
    expected = dict(zip(names, [column("added", "readded"), column("departure"),
                                column("completed_original",
                                       "already_done_original"),
                                column("completed_extra", "already_done_extra")]))
    for (name, total), cell in zip(expected.items(), total_row[1:]):
        head = re.match(QTY, re.sub(r"</?b>", "", cell).strip())
        got = (int(head.group(1)), parsed_number(
            head.group(2))) if head else None
        c.check(got == total, "columns",
                f"{name} total is {qty(*total)}")

    scope = (data["points_total_issue_count"],
             sum(data["outcome_points"].values()))
    net = (expected["Added"][0] - expected["Removed"][0],
           expected["Added"][1] - expected["Removed"][1])
    c.check(net == scope, "movements",
            f"gross added minus gross removed equals in scope {qty(*scope)}")

    cc, cp = data["commitment_breakdown_counts"], data["commitment_breakdown_points"]
    in_scope = {"Completed (original)": (cc["original_completed"], cp["original_completed"]),
                "Completed (extra)": (cc["extra_completed"], cp["extra_completed"])}
    for name, cell in zip(names, total_row[1:]):
        inner = re.sub(r"</?b>", "", cell).strip()
        suffix = re.fullmatch(
            QTY + r" \(still in scope: " + QTY + r"\)", inner)
        if name not in in_scope:
            c.check(bool(re.fullmatch(QTY, inner)), "totals row",
                    f"{name} is a bare total ({inner!r})")
            continue
        c.check(bool(re.fullmatch(QTY, inner)) or bool(suffix), "totals row",
                f"{name} is the total, optionally with the in-scope figure ({inner!r})")
        if expected[name] == in_scope[name]:
            c.check(suffix is None, "totals row",
                    f"{name} omits the in-scope figure equal to its total")
        elif c.check(suffix is not None, "totals row", f"{name} shows the in-scope figure") and suffix:
            got = (int(suffix.group(3)), parsed_number(suffix.group(4)))
            c.check(got == in_scope[name], "totals row",
                    f"{name} in-scope figure is {qty(*in_scope[name])}")

    # The visible day cells must add up to the Total row: a cell can lose a
    # group while the total stays right.
    sums = {name: [0, 0.0] for name in names}
    for cells in body:
        if strip_tags(cells[0]).lower() == "total":
            continue
        for name, cell in zip(names, cells[1:]):
            head = re.match(QTY, cell.strip())
            if head:
                sums[name][0] += int(head.group(1))
                sums[name][1] += parsed_number(head.group(2))
    for name in names:
        c.check(tuple(sums[name]) == expected[name], "columns",
                f"{name} cells sum to {qty(*expected[name])} (got {qty(*sums[name])})")

    for cells in body:
        label = strip_tags(cells[0]).split("(")[0].strip()
        if label.lower() == "total":
            continue
        for name, cell in zip(names, cells[1:]):
            where = f"{label} {name}"
            if cell.strip() == "–":
                continue
            blocks = [b for b in cell.split("<br><br>") if b.strip()]
            head = re.match(QTY, blocks[0])
            if not c.check(head is not None, "cell shapes", f"{where} starts with a quantity") or head is None:
                continue
            if len(blocks) == 1:
                clean = len(blocks[0].split(
                    "<br>")) == 2 and "<b>" not in blocks[0] and "<i>" not in blocks[0]
                c.check(clean, "cell shapes",
                        f"{where} is FLAT, with nothing after its list")
                continue
            c.check("<br>" not in blocks[0], "cell shapes",
                    f"{where} total stands alone above its groups")
            groups = [re.match(r"<b>[^,<]+, " + QTY + r"</b><br>", b)
                      for b in blocks[1:]]
            found = [g for g in groups if g]
            if c.check(len(found) == len(groups), "cell shapes",
                       f"{where} groups are '<b>Label, quantity</b>' + list"):
                total = (sum(int(g.group(1)) for g in found), sum(
                    parsed_number(g.group(2)) for g in found))
                c.check(total == (int(head.group(1)), parsed_number(head.group(2))), "subgroups",
                        f"{where} groups sum to the cell total")

    c.check(not re.search(QTY + r"<br><br><a", timeline), "spacing",
            "no blank line between a quantity and its list")
    legacy = re.findall(
        r"\d+ issues?[,:]|\(\d+ pts?\)|\(\d+, \d+ pts?\)", timeline)
    c.check(not legacy, "quantities",
            f"no other quantity formats {legacy or ''}".strip())


def check_epics(c, table, data):
    if not c.check(table is not None, "epics", "table found"):
        return
    for epic in data["epics"]:
        title = f"<td>{epic['name']}</td>" if epic["key"] == NO_EPIC else f">{epic['key']}: "
        row = next((r for r in rows_of(table) if title in r), None)
        if not c.check(row is not None, "epics", f"{epic['key']} has a row"):
            continue
        cells = cells_of(row)[1:5]
        expected = []
        for kind in ("original", "extra"):
            if kind == "extra" and epic["extra_stories_total"] == 0:
                expected += ["–", "–"]
            else:
                expected += [f"{epic[f'{kind}_stories_done']}/{epic[f'{kind}_stories_total']}",
                             f"{number(epic[f'{kind}_points_done'])}/{number(epic[f'{kind}_points_total'])}"]
        c.check(cells == expected, "epics",
                f"{epic['key']} shows {' '.join(expected)} (got {' '.join(cells)})")


def check_retro(c, md, data):
    if not c.check(RETRO_HEADING in md, "retro", "section found"):
        return
    section = md.split(RETRO_HEADING, 1)[1]
    for label in ("Planning baseline:", "Sprint target completion:", "Goal discipline:",
                  "Scope added after commitment:", "Scope removed or reversed:", "Actionable completion",
                  "Board-data quality:", "Unfinished-work shape:"):
        c.check(label in section, "retro", f"{label.rstrip(':')} covered")

    all_issues = data["issues"] + data["removed_issues"]
    original = [i for i in all_issues if not i["addedMidSprint"]]
    extra = [i for i in all_issues if i["addedMidSprint"]]
    original_points = sum(i["startState"]["storyPoints"]
                          or 0 for i in original)
    extra_points = sum(i["storyPoints"] or 0 for i in extra)
    c.check(qty(len(original), original_points) in section,
            "retro", "initial commitment stated")
    done_at_start = [i for i in original if i["startState"]["done"]]
    if done_at_start:
        open_points = original_points - \
            sum(i["startState"]["storyPoints"] or 0 for i in done_at_start)
        c.check(f"leaving {qty(len(original) - len(done_at_start), open_points)} to do" in section,
                "retro", "commitment still to do at the start (the burndown's baseline) stated")
    c.check(qty(len(extra), extra_points) in section and percentage(len(extra), len(original)) in section
            and percentage(extra_points, original_points) in section, "retro", "scope added after commitment stated")

    closed, pool, _ = target_completion(data)
    so_far = " so far" if data["sprint_status"] == "active" else ""
    c.check(f"{len(closed)}/{len(pool)} original-commitment tickets closed{so_far} "
            f"({percentage(len(closed), len(pool))})" in section, "retro", "sprint target completion stated")

    for field in ("descoped_incomplete", "already_done_on_arrival", "completed_before_removal"):
        values = data["removed_summary"][field]
        c.check(qty(values["count"], values["points"]) in section,
                "retro", f"{field.replace('_', ' ')} stated")

    arrived_done = {i["key"]
                    for i in data["already_done_on_arrival"]["issues"]}
    index = {i["key"]: i for i in all_issues}
    for origin, issues in (("original", original), ("extra", extra)):
        pool = [i for i in issues if i["key"] not in arrived_done]
        done = {k for r in data["scope_timeline"]
                for k in r[f"completed_{origin}_keys"]}
        done_points = sum(index[k]["storyPoints"] or 0 for k in done)
        total_points = sum(i["storyPoints"] or 0 for i in pool)
        c.check(f"{len(done)}/{len(pool)} stories ({percentage(len(done), len(pool))}) and "
                f"{number(done_points)}/{number(total_points)} points ({percentage(done_points, total_points)})"
                in section, "retro", f"{origin} actionable completion stated")

    open_issues = [i for i in data["issues"] if i["carriedOver"]]
    c.check(qty(len(open_issues), sum(i["storyPoints"] or 0 for i in open_issues)) in section,
            "retro", "unfinished work stated")


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


def check_style(c, md):
    c.check("—" not in md, "em dashes", "none in the report")
    iso = re.findall(r"\b\d{4}-\d\d-\d\d\b", md)
    c.check(not iso, "dates", f"no ISO dates {iso[:3] or ''}".strip())
    # Remove every link, then look for keys left over.
    stripped = re.sub(r"\[[^\]]*\]\([^)]*\)", "", md)
    stripped = re.sub(r"<a\s[^>]*>.*?</a>", "", stripped, flags=re.S)
    unlinked = sorted(set(ISSUE_KEY.findall(stripped)))
    c.check(not unlinked, "links",
            f"every Jira key is linked (unlinked: {unlinked[:5] or 'none'})")


def run_checks(md, data, report_dir):
    tables = {table_kind(t): t for t in html_tables(md)}
    c = Checker()
    check_figures(c, md, data)
    check_movements(c, tables.get("timeline"), data)
    check_framing(c, md)
    check_images(c, md, report_dir)
    check_timeline(c, tables.get("timeline"), data)
    check_epics(c, tables.get("epics"), data)
    check_retro(c, md, data)
    check_style(c, md)
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
