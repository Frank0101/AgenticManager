"""
Draw the report's three charts as SVG from <report_dir>/data.json, using only
the standard library.

Usage:
    python3 make_charts.py --report-dir <report_dir>
    python3 make_charts.py --report-dir <report_dir> --print-series   # burndown numbers only

Outcome charts (tickets and pts): how the counted spells ended (see
build_sprint_data.py), as Completed, Not completed (Open while running) and
Descoped, in three bars on one scale: carry-over, new commitment and extra. A
bracket joins the first two as the commitment. Both charts share one layout so
they read as a pair.

Burndown: four series, checked by validate_series before drawing.

  Commitment          open pts of the original commitment
  Commitment + extra  the same plus later scope; never below the commitment
  Ideal               from the same baseline, flat on the start day and over
                      weekends, then even per weekday to zero at the end
  Spread              commitment minus ideal: positive is behind

  * Both lines replay the same events as every other part of the report, at
    each day's estimates, so the burndown can't contradict the timeline.
  * The start day has two points at the same x: the whole commitment at the
    start, Done or not, then that day's reading. The drop between them is work
    already Done and that day's changes, not delivery pace, so it is vertical.
  * Readings are end of day, except the last: the exact close, or the fetch.
    For a closed sprint, work finished after the close still counts as open.
  * A running sprint past its end date continues through the fetch date;
    the ideal keeps its final planned value. With no weekday after the start,
    it stays at the baseline rather than inventing a daily burn rate.

Blue and violet are close for deuteranopia, so each series also has its own
dash pattern, repeated in the legend; keep the four patterns distinct.
"""
import argparse
import html
import math
import os
from datetime import date, timedelta

from common import CHART_FILES, DATA_FILE, display_date, load_json, plural, unit, whole_percentage, write_report_file

FONT = "-apple-system, 'Segoe UI', Helvetica, Arial, sans-serif"
SURFACE = "#fcfcfb"
INK = "#1a1a1a"
MUTED = "#6b6b6b"
GRID = "#e8e7e4"
WEEKEND = "#e7e4dc"

SERIES = {
    "committed": {"label": "Commitment", "color": "#2a78d6", "width": 2.4, "dash": None},
    "total": {"label": "Commitment + extra", "color": "#9c27b0", "width": 2.0, "dash": "14 4"},
    "ideal": {"label": "Ideal (commitment)", "color": "#1a7f37", "width": 1.8, "dash": "7 5"},
    "spread": {"label": "Spread vs ideal", "color": "#d92d20", "width": 1.8, "dash": "2 4"},
}
# The outcome rows that split the original commitment; the third is the extra
# scope.
ORIGINAL_ROWS = ("carried_in", "new")
# Both outcome charts share one layout: this width (more only if the labels
# need it), with the bars taking this share of it, flush with the right margin.
OUTCOME_WIDTH = 960
OUTCOME_MIN_BAR_SHARE = 0.5
OUTCOME_MARGIN = 20
OUTCOME_SEGMENTS = [
    ("completed", "Completed", "#0ca30c", "#ffffff"),
    ("not_completed", "Not completed", "#fab219", INK),
    ("removed", "Descoped", "#b5b2aa", INK),
]


def esc(text):
    return html.escape(str(text), quote=True)


def fmt(value):
    return f"{value:g}"


# Character widths in em, after Helvetica and Arial; anything else counts as a
# lower-case letter.
CHAR_WIDTHS = {**dict.fromkeys("ijl|", 0.23), **dict.fromkeys(" ftI.,:;'!/", 0.28),
               **dict.fromkeys("r()-", 0.34), **dict.fromkeys("cksvxyz", 0.5),
               **dict.fromkeys("FTZ", 0.61), **dict.fromkeys("ABEKPSVXY", 0.67),
               **dict.fromkeys("CDHNRUw", 0.72), **dict.fromkeys("GOQ", 0.78),
               **dict.fromkeys("mM", 0.84), "%": 0.89, "W": 0.95, "→": 1.0}


def text_width(text, size, bold=False):
    """Estimated rendered width, close enough to size the label column and to
    decide whether a label fits a bar."""
    return sum(CHAR_WIDTHS.get(c, 0.56) for c in str(text)) * size * (1.08 if bold else 1)


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
    return plural(n, "pt", "pts") if is_points else unit(n)


def outcome_segments(data):
    """The outcome segments, with the not-completed one called Open while the
    sprint runs."""
    return [(seg, ("Open" if seg == "not_completed" and data["sprint_status"] == "active" else label), color, ink)
            for seg, label, color, ink in OUTCOME_SEGMENTS]


def outcome_rows(data):
    """[(row key, label)]: the original commitment split into carry-over and
    new work, then the extra scope."""
    previous = data["previous_sprint"]
    carried = f"Carried over from {previous['name']}" if previous else "Carried over (no previous sprint)"
    return [("carried_in", carried), ("new", "New commitment"), ("extra", "Extra")]


def outcome_labels(data, is_points):
    """What one outcome chart writes beside its bars: (breakdown, totals,
    grand total, [(row, label, sublabel)], the bracket's lines)."""
    breakdown = data["outcome_breakdown_points" if is_points else "outcome_breakdown_counts"]
    rows = outcome_rows(data)
    totals = {row: sum(breakdown[f"{row}_{seg}"] for seg, *_ in OUTCOME_SEGMENTS)
              for row in ("original", *(r for r, _ in rows))}
    grand = totals["original"] + totals["extra"]

    def sublabel(row):
        text_ = f"{fmt(totals[row])} {unit_label(totals[row], is_points)}"
        if row in ORIGINAL_ROWS and totals["original"]:
            text_ += f" ({whole_percentage(totals[row], totals['original'])} of commitment)"
        elif row == "extra" and grand:
            text_ += f" ({whole_percentage(totals[row], grand)} of total)"
        return text_

    group_lines = [("Commitment", 12, INK),
                   (f"{fmt(totals['original'])} {unit_label(totals['original'], is_points)}", 11, MUTED)]
    if grand:
        group_lines.append(
            (f"({whole_percentage(totals['original'], grand)} of total)", 11, MUTED))
    return breakdown, totals, grand, [(row, label, sublabel(row)) for row, label in rows], group_lines


def outcome_layout(data):
    """(width, bracket position, bar start), shared by the tickets and points
    charts so they look alike: the label column fits the longer labels of
    either chart and the bars take the rest of the width. The width grows past
    OUTCOME_WIDTH only to keep the bars at OUTCOME_MIN_BAR_SHARE of it."""
    group_w = label_w = 0
    for is_points in (False, True):
        *_, rows, group_lines = outcome_labels(data, is_points)
        group_w = max(group_w, *(text_width(t, size, i == 0)
                      for i, (t, size, _) in enumerate(group_lines)))
        label_w = max(label_w, *(max(text_width(label, 12),
                      text_width(sub, 11)) for _, label, sub in rows))
    bracket_x = math.ceil(OUTCOME_MARGIN + group_w + 8)
    left = math.ceil(bracket_x + 10 + label_w + 12)
    width = max(OUTCOME_WIDTH, math.ceil(
        (left + OUTCOME_MARGIN) / (1 - OUTCOME_MIN_BAR_SHARE)))
    return width, bracket_x, left


def outcome_chart(data, is_points):
    breakdown, totals, grand, rows, group_lines = outcome_labels(
        data, is_points)
    title = f"{data['sprint_name']}: Sprint Outcome ({fmt(grand)} {unit_label(grand, is_points)})"
    estimated, total_issues = data["points_estimated_issue_count"], data["points_total_issue_count"]
    if is_points and estimated < total_issues:
        title += f" ({estimated}/{total_issues} tickets estimated)"

    # Columns, left to right: the bracket's label; the bracket; the row
    # labels; the bars, ending at the right margin. Bars share one scale, set
    # by the longest, which spans the full bar width.
    width, bracket_x, left = outcome_layout(data)
    bar_w = width - OUTCOME_MARGIN - left
    row_h, top, bar_h = 56, 56, 40
    scale = bar_w / (max(totals[row] for row, *_ in rows) or 1)
    body = [text(OUTCOME_MARGIN, 30, title, size=16, bold=True)]
    for index, (row, row_label, sub) in enumerate(rows):
        y = top + index * row_h
        body.append(text(left - 12, y + 16, row_label, anchor="end"))
        body.append(text(left - 12, y + 32, sub,
                    size=11, color=MUTED, anchor="end"))
        x, segments = left, []
        for seg, seg_label, color, label_color in outcome_segments(data):
            value = breakdown[f"{row}_{seg}"]
            if not value:
                continue
            seg_w = value * scale
            pct = whole_percentage(value, totals[row])
            segments.append(
                (x, seg_w, value, pct, seg_label, color, label_color))
            x += seg_w
        for sx, seg_w, *_rest, color, _ in segments:
            body.append(f'<rect x="{sx:.1f}" y="{y:.1f}" width="{seg_w:.1f}" height="{bar_h}" fill="{color}" '
                        f'stroke="{SURFACE}" stroke-width="2"/>')
        labels = [f"{fmt(v)} ({p})" for _, _, v, p, *_ in segments]
        joined = "; ".join(f"{s[4]}: {lbl}" for lbl,
                           s in zip(labels, segments))
        # Labels go inside their segments if every one of them fits; otherwise
        # the row's labels are joined to the right of the bar. A bar leaving
        # no room for them keeps each label inside its segment, shortened to
        # the bare number where the full one doesn't fit, and joins only those
        # that fit neither way to the right of the bar or over its start.
        if all(text_width(lbl, 12, True) + 8 <= s[1] for lbl, s in zip(labels, segments)):
            inside, outside = list(zip(labels, segments)), []
        elif x + 8 + text_width(joined, 12, True) <= width - OUTCOME_MARGIN:
            inside, outside = [], list(zip(labels, segments))
        else:
            inside, outside = [], []
            for lbl, seg in zip(labels, segments):
                short = fmt(seg[2])
                if text_width(lbl, 12, True) + 8 <= seg[1]:
                    inside.append((lbl, seg))
                elif text_width(short, 12, True) + 8 <= seg[1]:
                    inside.append((short, seg))
                else:
                    outside.append((lbl, seg))
        inside_y = outside_y = y + 24
        outside_x = x + 8
        if outside:
            joined = "; ".join(f"{seg[4]}: {lbl}" for lbl, seg in outside)
            fits = x + 8 + text_width(joined, 12,
                                      True) <= width - OUTCOME_MARGIN
            if not fits:
                outside_x = left + 8
            outside_end = outside_x + text_width(joined, 12, True)
            # A fallback over the bar can meet a retained label. Give them
            # separate lines within the same row when their bounds overlap.
            if any(outside_x < seg[0] + seg[1] / 2 + text_width(lbl, 12, True) / 2
                   and outside_end > seg[0] + seg[1] / 2 - text_width(lbl, 12, True) / 2
                   for lbl, seg in inside):
                inside_y, outside_y = y + 16, y + 36
        for lbl, (sx, seg_w, *_rest, label_color) in inside:
            body.append(text(sx + seg_w / 2, inside_y, lbl,
                        anchor="middle", bold=True, color=label_color))
        if outside:
            body.append(text(outside_x, outside_y, joined, bold=True))

    # The bracket joins the two original rows, from the top of the first bar
    # to the bottom of the second.
    y1, y2 = top, top + row_h + bar_h
    body.append(f'<path d="M {bracket_x + 8:.1f} {y1} H {bracket_x:.1f} V {y2} H {bracket_x + 8:.1f}" '
                f'fill="none" stroke="{MUTED}" stroke-width="1.5"/>')
    middle = (y1 + y2) / 2
    for i, (line, size, color) in enumerate(group_lines):
        body.append(text(bracket_x - 8, middle + 4 + (i - (len(group_lines) - 1) / 2) * 15, line, size=size, color=color, anchor="end",
                         bold=i == 0))

    legend_y = top + len(rows) * row_h + 14
    lx = left
    for _, seg_label, color, _ in outcome_segments(data):
        body.append(
            f'<rect x="{lx:.1f}" y="{legend_y - 10}" width="12" height="12" fill="{color}"/>')
        body.append(text(lx + 18, legend_y, seg_label))
        lx += 18 + text_width(seg_label, 12) + 24
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
    actuals = {parse_date(row["date"]): row for row in data["burndown"]}
    sprint_start, sprint_end = parse_date(
        data["sprint_start"]), parse_date(data["sprint_end"])
    if not actuals:
        raise SystemExit(
            "data.json has no burndown readings; build the sprint data again")
    last_actual = max(actuals)

    baseline = data["burndown_baseline"]
    weekdays = sum(1 for d in daterange(
        sprint_start + timedelta(days=1), sprint_end) if is_weekday(d))

    rows = [{"date": sprint_start, "label": "start", "committed": baseline, "total": baseline,
             "ideal": baseline, "spread": 0}]
    # Actuals after the planned end run to the close or fetch; the ideal keeps
    # its final planned value (the baseline when there were no later weekdays).
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
    # The baseline is the whole original commitment at the start: its
    # committed events, Done or not, at the estimate they had then.
    committed = sum(e["points"] or 0 for t in data["spells"] for e in t["events"][:1]
                    if e["type"] == "committed")
    if committed != baseline:
        problems.append(
            f"baseline {fmt(baseline)} differs from the commitment at the start {fmt(committed)}")
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
    end_row = next(
        (r for r in closes if r["date"] == series["sprint_end"]), None)
    if end_row is None:
        problems.append("no point on the sprint's end date")
    elif series["weekdays"] and end_row["ideal"] != 0:
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
        text(left, 52, f"Commitment of {fmt(series['baseline'])} pts at the start on "
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
    body.append(text(16, top + plot_h / 2, "Remaining pts", size=12, anchor="middle",
                     extra=f' transform="rotate(-90 16 {top + plot_h / 2:.1f})"'))

    cutoff = x_of(series["last_actual"])
    body.append(f'<line x1="{cutoff:.1f}" x2="{cutoff:.1f}" y1="{top}" y2="{top + plot_h}" '
                f'stroke="{MUTED}" stroke-width="1" stroke-dasharray="2 3"/>')
    if data["sprint_status"] != "active":
        cutoff_label = "sprint closed"
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
        "outcome_tickets": outcome_chart(data, is_points=False),
        "outcome_pts": outcome_chart(data, is_points=True),
        "burndown": burndown_chart(data, series),
    }
    for name, content in charts.items():
        path = os.path.join(args.report_dir, CHART_FILES[name])
        write_report_file(path, content)
        print("wrote", path)


if __name__ == "__main__":
    main()
