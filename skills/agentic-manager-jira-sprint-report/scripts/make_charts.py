"""
Draw the report's three charts as SVG from <report_dir>/data.json, using
only the standard library.

Usage:
    python3 make_charts.py --report-dir <report_dir>
    python3 make_charts.py --report-dir <report_dir> --print-series   # burndown numbers only

Writes outcome-stories.svg, outcome-points.svg and burndown.svg.

Outcome charts: two bars on one shared scale, the original commitment and the
extra scope added later, each split into Completed and Not completed. They
cover issues currently in the sprint; removed scope lives in the timeline
table. "Completed" is counted as in Jira's sprint report. The points chart's
title notes partial estimation when some issues have no points.

Burndown: points remaining for every calendar day of the sprint (through the
close date, if it closed after its end date), four series.

  Committed (blue, solid)          remaining original commitment.
  Committed + extra (violet, dash) the same plus scope added later; never
                                   below blue.
  Ideal (green, dashed)            the commitment, held through the start day,
                                   then burned evenly per later weekday to zero
                                   by sprint end; flat over weekends.
  Spread (red, dotted)             committed minus ideal: positive is behind.

Rules the burndown follows, checked by validate_series before drawing:

  * The baseline is the original commitment still to do: what was in the
    sprint at its start (issues with `addedMidSprint` false), less what was
    already Done then, with estimates as they stood at the start.
  * Blue and violet are end-of-day readings. The start day gets two points at
    the same x: the baseline, then that day's close, drawn as a vertical movement
    reflecting closures, removals, reopening and estimate changes that day.
  * The ideal assumes no burn on the start day; it starts sloping on the next
    weekday.
  * Each day has one x position: its values, its tick and its weekend band
    share it. A weekend day's band runs from the previous day's tick to its
    own, because the space between two ticks is the later day passing.
  * Actuals stop at today (active), or at the end date if an active sprint
    has run past it, or at the close date (closed). For a closed
    sprint the last value is what was carried over: work finished after the
    close, even later the same day, still counts as open. Each earlier day
    uses its end-of-day status, estimate and membership; reopening and
    re-estimation appear on the day they happened. An active snapshot uses
    the fetch instant for the current day.

Colours were checked for colour-blind separation; blue and violet are close
for deuteranopia, so each series also has its own dash pattern, repeated in
the legend. Keep the four patterns distinct.
"""
import argparse
import html
import os
from datetime import date, timedelta

from common import CHART_FILES, DATA_FILE, display_date, load_json, plural, unit

FONT = "-apple-system, 'Segoe UI', Helvetica, Arial, sans-serif"
SURFACE = "#fcfcfb"
INK = "#1a1a1a"
MUTED = "#6b6b6b"
GRID = "#e8e7e4"
WEEKEND = "#e7e4dc"

SERIES = {
    "committed": {"label": "Committed", "color": "#2a78d6", "width": 2.4, "dash": None},
    "total": {"label": "Committed + extra", "color": "#9c27b0", "width": 2.0, "dash": "14 4"},
    "ideal": {"label": "Ideal (committed)", "color": "#1a7f37", "width": 1.8, "dash": "7 5"},
    "spread": {"label": "Spread vs ideal", "color": "#d92d20", "width": 1.8, "dash": "2 4"},
}
OUTCOME_ROWS = [("original", "Original commitment"),
                ("extra", "Extra (added mid-sprint)")]
OUTCOME_SEGMENTS = [
    ("completed", "Completed", "#0ca30c", "#ffffff"),
    ("not_completed", "Not completed", "#fab219", INK),
]


def esc(text):
    return html.escape(str(text), quote=True)


def fmt(value):
    return f"{value:g}"


def text_width(text, size, bold=False):
    """Rough rendered width; enough to decide whether a label fits a bar."""
    return len(str(text)) * size * (0.62 if bold else 0.56)


def text(x, y, content, size=12, color=INK, anchor="start", bold=False, extra=""):
    weight = ' font-weight="bold"' if bold else ""
    return (f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" fill="{color}" '
            f'text-anchor="{anchor}"{weight}{extra}>{esc(content)}</text>')


def svg(width, height, body):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width:.0f}" height="{height:.0f}" '
            f'viewBox="0 0 {width:.0f} {height:.0f}" font-family="{FONT}">\n'
            f'<rect width="100%" height="100%" fill="{SURFACE}"/>\n' + "\n".join(body) + "\n</svg>\n")


# --- outcome charts

def unit_label(n, is_points):
    return f"story {plural(n, 'point', 'points')}" if is_points else unit(n)


def outcome_chart(data, is_points):
    breakdown = data["commitment_breakdown_points" if is_points else "commitment_breakdown_counts"]
    totals = {row: sum(breakdown[f"{row}_{seg}"]
                       for seg, *_ in OUTCOME_SEGMENTS) for row, _ in OUTCOME_ROWS}
    grand = sum(totals.values())

    title = f"{data['sprint_name']}: Sprint Outcome ({fmt(grand)} {unit_label(grand, is_points)})"
    estimated, total_issues = data["points_estimated_issue_count"], data["points_total_issue_count"]
    if is_points and estimated < total_issues:
        title += f" ({estimated}/{total_issues} issues estimated)"

    left, bar_w, row_h, top = 200, 520, 56, 56
    body = [text(20, 30, title, size=16, bold=True)]
    right_edge = left + bar_w
    for index, (row, row_label) in enumerate(OUTCOME_ROWS):
        y = top + index * row_h
        body.append(text(left - 12, y + 16, row_label, anchor="end"))
        body.append(text(left - 12, y + 32, f"({fmt(totals[row])} {unit_label(totals[row], is_points)})",
                         size=11, color=MUTED, anchor="end"))
        x, segments = left, []
        for seg, seg_label, color, label_color in OUTCOME_SEGMENTS:
            value = breakdown[f"{row}_{seg}"]
            if not value:
                continue
            width = bar_w * value / grand if grand else 0
            pct = 100 * value / totals[row]
            segments.append(
                (x, width, value, pct, seg_label, color, label_color))
            x += width
        for sx, width, *_rest, color, _ in segments:
            body.append(f'<rect x="{sx:.1f}" y="{y:.1f}" width="{width:.1f}" height="40" fill="{color}" '
                        f'stroke="{SURFACE}" stroke-width="2"/>')
        labels = [f"{fmt(v)} ({p:.0f}%)" for _, _, v, p, *_ in segments]
        # Labels go inside their segments only if every one of them fits;
        # otherwise the row's labels are joined to the right of the bar.
        if all(text_width(lbl, 12, True) + 8 <= s[1] for lbl, s in zip(labels, segments)):
            for lbl, (sx, width, *_rest, label_color) in zip(labels, segments):
                body.append(text(sx + width / 2, y + 24, lbl,
                            anchor="middle", bold=True, color=label_color))
        elif segments:
            joined = "; ".join(f"{s[4]}: {lbl}" for lbl,
                               s in zip(labels, segments))
            body.append(text(x + 8, y + 24, joined, bold=True))
            right_edge = max(right_edge, x + 8 + text_width(joined, 12, True))

    legend_y = top + len(OUTCOME_ROWS) * row_h + 14
    lx = left
    for _, seg_label, color, _ in OUTCOME_SEGMENTS:
        body.append(
            f'<rect x="{lx}" y="{legend_y - 10}" width="12" height="12" fill="{color}"/>')
        body.append(text(lx + 18, legend_y, seg_label))
        lx += 18 + text_width(seg_label, 12) + 24
    width = max(right_edge + 20, text_width(title, 16, True) + 40)
    return svg(width, legend_y + 18, body)


# --- burndown

def parse_date(value):
    return date.fromisoformat(value[:10])


def daterange(start, end):
    day = start
    while day <= end:
        yield day
        day += timedelta(days=1)


def is_weekday(day):
    return day.weekday() < 5


def build_series(data):
    issues = data["issues"] + data["removed_issues"]
    actuals = {parse_date(row["date"]): row for row in data["burndown"]}
    sprint_start, sprint_end = parse_date(
        data["sprint_start"]), parse_date(data["sprint_end"])
    last_actual = max(actuals)

    baseline = sum(i["startState"]["storyPoints"] or 0 for i in issues
                   if not i["addedMidSprint"] and not i["startState"]["done"])
    weekdays = sum(1 for d in daterange(
        sprint_start + timedelta(days=1), sprint_end) if is_weekday(d))

    rows = [{"date": sprint_start, "label": "start", "committed": baseline, "total": baseline,
             "ideal": baseline, "spread": 0}]
    # A sprint closed after its end date runs to the close; the ideal is
    # already zero by then.
    last_day = max(sprint_end, last_actual)
    burned = 0
    for day in daterange(sprint_start, last_day):
        if sprint_start < day <= sprint_end and is_weekday(day):
            burned += 1
        ideal = round(baseline * (1 - burned / weekdays),
                      2) if weekdays else baseline
        row = {"date": day, "label": "close", "ideal": ideal,
               "committed": None, "total": None, "spread": None}
        if day <= last_actual:
            row["committed"] = actuals[day]["committed"]
            row["total"] = actuals[day]["total"]
            row["spread"] = round(row["committed"] - ideal, 2)
        rows.append(row)

    return {"rows": rows, "days": list(daterange(sprint_start, last_day)), "baseline": baseline,
            "sprint_start": sprint_start, "sprint_end": sprint_end,
            "last_actual": last_actual, "weekdays": weekdays}


def validate_series(series, data):
    """Fail before drawing if the series breaks the chart's rules."""
    rows, baseline, problems = series["rows"], series["baseline"], []
    # The timeline's start row adds the original commitment, plus any extra
    # work that joined later that day; the baseline is the part not yet Done.
    issues = {i["key"]: i for i in data["issues"] + data["removed_issues"]}
    start_row = next(
        (r for r in data["scope_timeline"] if r["date"] == data["sprint_start"]), None)
    committed = sum(issues[k]["startState"]["storyPoints"] or 0 for k in (start_row or {}).get("added_keys", [])
                    if not issues[k]["addedMidSprint"] and not issues[k]["startState"]["done"])
    if committed != baseline:
        problems.append(
            f"baseline {fmt(baseline)} differs from the open commitment added at the start {fmt(committed)}")
    if len(rows) < 2 or rows[1]["date"] != series["sprint_start"]:
        problems.append(
            "the start day needs a baseline point and an end-of-day point")
    elif rows[0]["ideal"] != baseline or rows[1]["ideal"] != baseline:
        problems.append("ideal must hold the baseline through the start day")
    closes = rows[1:]
    for previous, row in zip(closes, closes[1:]):
        if row["ideal"] > previous["ideal"]:
            problems.append(f"ideal rises on {row['date']}")
        if not is_weekday(row["date"]) and row["ideal"] != previous["ideal"]:
            problems.append(f"ideal changes over the weekend on {row['date']}")
    end_row = next(r for r in closes if r["date"] == series["sprint_end"])
    if series["weekdays"] and end_row["ideal"] != 0:
        problems.append("ideal doesn't reach zero by sprint end")
    for row in rows:
        if row["committed"] is not None:
            if row["total"] < row["committed"]:
                problems.append(
                    f"committed + extra is below committed on {row['date']}")
            if row["spread"] != round(row["committed"] - row["ideal"], 2):
                problems.append(f"spread is inconsistent on {row['date']}")
        elif row["date"] <= series["last_actual"]:
            problems.append(f"no actual value on {row['date']}")
        if row["date"] > series["last_actual"] and row["committed"] is not None:
            problems.append(
                f"actuals continue past the cutoff on {row['date']}")
    if problems:
        raise SystemExit("burndown check failed:\n  - " +
                         "\n  - ".join(problems))


def nice_step(span):
    for step in (1, 2, 5, 10, 20, 25, 50, 100, 200, 250, 500, 1000):
        if span / step <= 8:
            return step
    return 1000 * (int(span / 8000) + 1)


def burndown_chart(data, series):
    days, rows = series["days"], series["rows"]
    width, left, right, top, plot_h = 960, 64, 24, 78, 260
    plot_w = width - left - right
    step_x = plot_w / len(days)
    day_index = {d: i for i, d in enumerate(days)}

    values = [r[k] for r in rows for k in SERIES if r[k] is not None] + [0]
    y_min, y_max = min(values), max(values)
    pad = (y_max - y_min) * 0.12 or 1
    y_lo, y_hi = y_min - pad * 0.4, y_max + pad

    def x_of(day):
        return left + (day_index[day] + 0.5) * step_x

    def y_of(value):
        return top + plot_h * (y_hi - value) / (y_hi - y_lo)

    status_word = "sprint in progress" if data["sprint_status"] == "active" else "sprint closed"
    body = [
        text(left, 30, f"{data['sprint_name']}: Burndown", size=17, bold=True),
        text(left, 52, f"Committed {fmt(series['baseline'])} pts at the start on "
             f"{display_date(series['sprint_start'].isoformat())} · ideal paced over {series['weekdays']} later "
             f"weekdays · actuals to {display_date(series['last_actual'].isoformat())} ({status_word})",
             size=11, color=MUTED),
    ]
    for day in days:
        if not is_weekday(day):
            x1 = x_of(day)
            x0 = x1 - step_x if day_index[day] else left
            body.append(
                f'<rect x="{x0:.1f}" y="{top}" width="{x1 - x0:.1f}" height="{plot_h}" fill="{WEEKEND}"/>')
    step = nice_step(y_hi - y_lo)
    tick = step * -(-y_lo // step)
    while tick <= y_hi:
        y = y_of(tick)
        body.append(f'<line x1="{left}" x2="{left + plot_w}" y1="{y:.1f}" y2="{y:.1f}" '
                    f'stroke="{"#cfcfcb" if tick == 0 else GRID}" stroke-width="1"/>')
        body.append(text(left - 8, y + 4, fmt(tick + 0),
                    size=11, color=MUTED, anchor="end"))
        tick += step
    body.append(text(16, top + plot_h / 2, "Story points remaining", size=12, anchor="middle",
                     extra=f' transform="rotate(-90 16 {top + plot_h / 2:.1f})"'))

    cutoff = x_of(series["last_actual"])
    body.append(f'<line x1="{cutoff:.1f}" x2="{cutoff:.1f}" y1="{top}" y2="{top + plot_h}" '
                f'stroke="{MUTED}" stroke-width="1" stroke-dasharray="2 3"/>')
    if data["sprint_status"] != "active":
        cutoff_label = "sprint closed"
    elif series["last_actual"] < parse_date(data["today"]):
        cutoff_label = "sprint end"
    else:
        cutoff_label = "today"
    # Right of the line, or left of it when it would run off the chart.
    if cutoff + 4 + text_width(cutoff_label, 10) > width - 4:
        body.append(text(cutoff - 4, top + 12, cutoff_label,
                    size=10, color=MUTED, anchor="end"))
    else:
        body.append(text(cutoff + 4, top + 12,
                    cutoff_label, size=10, color=MUTED))

    for key, spec in SERIES.items():
        points = " ".join(
            f"{x_of(r['date']):.1f},{y_of(r[key]):.1f}" for r in rows if r[key] is not None)
        dash = f' stroke-dasharray="{spec["dash"]}"' if spec["dash"] else ""
        body.append(f'<polyline points="{points}" fill="none" stroke="{spec["color"]}" '
                    f'stroke-width="{spec["width"]}" stroke-linecap="round" stroke-linejoin="round"{dash}/>')

    # Values on every actual point of the two "remaining" lines: committed
    # below, total above, total skipped where it equals committed. The
    # start-day baseline goes to the left, clear of that day's close labels.
    for row in rows:
        if row["committed"] is None:
            continue
        x = x_of(row["date"])
        if row["label"] == "start":
            body.append(text(x - 6, y_of(row["committed"]) + 4, fmt(row["committed"]), size=10,
                             color=SERIES["committed"]["color"], anchor="end", bold=True))
            continue
        body.append(text(x, y_of(row["committed"]) + 14, fmt(row["committed"]), size=10,
                         color=SERIES["committed"]["color"], anchor="middle", bold=True))
        if row["total"] != row["committed"]:
            body.append(text(x, y_of(row["total"]) - 7, fmt(row["total"]), size=10,
                             color=SERIES["total"]["color"], anchor="middle", bold=True))

    axis_y = top + plot_h + 14
    for day in days:
        x = x_of(day)
        body.append(text(x, axis_y, day.strftime("%d/%m"), size=10, color=MUTED, anchor="end",
                         extra=f' transform="rotate(-45 {x:.1f} {axis_y:.1f})"'))

    legend_y = axis_y + 48
    lx = left
    for spec in SERIES.values():
        dash = f' stroke-dasharray="{spec["dash"]}"' if spec["dash"] else ""
        body.append(f'<line x1="{lx}" x2="{lx + 30}" y1="{legend_y - 4}" y2="{legend_y - 4}" '
                    f'stroke="{spec["color"]}" stroke-width="{spec["width"]}" stroke-linecap="round"{dash}/>')
        body.append(text(lx + 38, legend_y, spec["label"]))
        lx += 38 + text_width(spec["label"], 12) + 28
    return svg(width, legend_y + 16, body)


def print_series(series):
    print(f"baseline {fmt(series['baseline'])} pts committed at the start on {series['sprint_start']}; "
          f"ideal over {series['weekdays']} later weekdays; actuals to {series['last_actual']}")
    print(f"{'date':<12}{'dow':<5}{'point':<7}{'committed':>10}{'total':>8}{'ideal':>8}{'spread':>8}")
    for r in series["rows"]:
        cells = ["-" if r[k] is None else fmt(r[k])
                 for k in ("committed", "total", "ideal", "spread")]
        print(f"{r['date'].isoformat():<12}{r['date'].strftime('%a'):<5}{r['label']:<7}"
              f"{cells[0]:>10}{cells[1]:>8}{cells[2]:>8}{cells[3]:>8}")


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--report-dir", required=True,
                        help="report folder holding data.json")
    parser.add_argument("--print-series", action="store_true",
                        help="print the burndown numbers and stop")
    args = parser.parse_args()

    data = load_json(os.path.join(args.report_dir, DATA_FILE))
    series = build_series(data)
    validate_series(series, data)
    if args.print_series:
        print_series(series)
        return
    charts = {
        "outcome_stories": outcome_chart(data, is_points=False),
        "outcome_points": outcome_chart(data, is_points=True),
        "burndown": burndown_chart(data, series),
    }
    for name, content in charts.items():
        path = os.path.join(args.report_dir, CHART_FILES[name])
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        print("wrote", path)


if __name__ == "__main__":
    main()
