"""Writes a prep's report, <Person>_Review_Prep.md, and its charts from work.json: for now, the person's Jira figures.

Every figure is one of work.json's facts, and every link one of its search
addresses, so the report can't count differently from the model. The charts
group the items by calendar week, Monday to Sunday, counted from a fixed
Monday, so a day falls in the same week whatever the period, a few weeks at a
time when there would be more than MAX_POINTS of them. They are drawn as SVG
by hand, as skills install nothing.
"""
import argparse
import json
import math
import os
from datetime import date, timedelta

from common import (CHARTS_DIR, EPICS_CHART, FOCUS_SHARE, JIRA_CELLS, FOLDER_NAME, GRID, INK, MUTED, PERSON, WORK, number,
                    average_text, esc, nice_step, prep_dir, read_json, report_name, report_problems, shown, stops_on_failure, svg, text, text_width,
                    types_text, write_output_file)

EPOCH_MONDAY = date(2001, 1, 1)
MAX_POINTS = 20
# A chart's size; the report fits it to its column. The epics' chart is wider,
# for its legend, and only as tall as the legend needs.
WIDTH, HEIGHT = 440, 170
EPICS_WIDTH = 760
LEFT, RIGHT, TOP, BOTTOM = 34, 12, 14, 44
LINE, AREA, AVERAGE = "#4a72b0", "#d3dcec", "#d92d20"
# The epics' slices, then the issues' with no epic.
PALETTE = ("#4a72b0", "#e08a2c", "#3f9c6c", "#c4524a", "#8a6bbf", "#2a9fb0", "#b38b2e", "#d16fa6", "#5c7d2e",
           "#6f6f9c")
NO_EPIC = "#dcd9d2"


def make_report(prep):
    """Write the prep `prep`'s report and its charts from work.json, then
    check them; returns {report, problems}, the report's path and what the
    check found."""
    folder = prep_dir(prep)
    person = read_json(os.path.join(folder, PERSON))
    work = read_json(os.path.join(folder, WORK))
    weeks = week_groups(person["start"], person["end"])
    jira = work["jira"]
    chart = dict(JIRA_CELLS)
    charts = {chart["created"]: over_time_chart(jira["created"], weeks, "created"),
              chart["resolved"]: over_time_chart(jira["resolved"], weeks, "resolved"),
              chart["resolved_points"]: points_chart(jira["resolved"], jira["resolved_points"]["average"]),
              EPICS_CHART: epics_chart(jira["resolved_by_epic"])}
    for name, content in charts.items():
        write_output_file(
            FOLDER_NAME, f"{prep}/{CHARTS_DIR}/{name}", content.encode("utf-8"))
    report = render(person, work)
    path, _ = write_output_file(
        FOLDER_NAME, f"{prep}/{report_name(prep)}", report.encode("utf-8"))
    return {"report": path, "problems": report_problems(report, work, os.listdir(os.path.join(folder, CHARTS_DIR)))}


# The report.

def render(person, work):
    """The report's text: the person and the period, then their Jira
    figures."""
    return "\n".join([f"# {person['person']}: performance review prep", "",
                      f"Period: {shown(person['start'], person['end'])}", "",
                      *jira_section(work["jira"]), "", *focus_section(work["jira"])]) + "\n"


def jira_section(jira):
    """The Jira section's lines: a table of the issues created, the issues
    resolved and their story points, in the order of JIRA_CELLS, a row of
    figures, each linked to its search with what it is made of, then a row of
    their charts, so the charts line up however the figures wrap. It is
    HTML, as Markdown can't give columns one width."""
    points = jira["resolved_points"]
    figures = {"created": ("Issues created", jira["counts"]["created"], types_text(jira["created_by_type"]),
                           "Issues created over time"),
               "resolved": ("Issues resolved", jira["counts"]["resolved"], types_text(jira["resolved_by_type"]),
                            "Issues resolved over time"),
               "resolved_points": ("SP resolved", points["total"], average_text(points["average"]),
                                   "Story points of the resolved issues")}
    width = f"{100 // len(JIRA_CELLS)}%"
    heads = "".join(
        f'<th width="{width}">{figures[name][0]}</th>' for name, _ in JIRA_CELLS)
    values = "".join(f"<td>{figure(figures[name][1], jira[f'{name}_search_url'])} ({esc(figures[name][2])})</td>"
                     for name, _ in JIRA_CELLS)
    charts = "".join(f'<td><img src="{CHARTS_DIR}/{chart}" width="100%" alt="{figures[name][3]}"></td>'
                     for name, chart in JIRA_CELLS)
    return ["## Jira", "", '<table width="100%">', f"<tr>{heads}</tr>", f"<tr>{values}</tr>", f"<tr>{charts}</tr>",
            "</table>"]


def figure(value, url):
    """`value` as the report writes it, linked to `url` unless it is null."""
    return f'<a href="{esc(url)}">{number(value)}</a>' if url else number(value)


def focus_section(jira):
    """The main focus's lines: the chart of the resolved issues by epic, and
    beside it, numbered, the epics that hold most of them, each with its
    title and how many it holds, linked to the search of those issues."""
    entries = "".join(f'<li><a href="{esc(jira["epic_search_urls"][entry["key"]])}">{esc(entry["key"])}</a> '
                      f'{esc(entry["title"] or "")} ({entry["issues"]})</li>' if entry["url"] else
                      f'<li>{esc(entry["key"])} ({entry["issues"]})</li>' for entry in jira["focus"])
    note = (f"the epics with the most resolved issues, which together hold at least "
            f"{round(FOCUS_SHARE * 100)}% of the issues that have an epic")
    return ['<table width="100%">',
            f'<tr><td width="50%"><img src="{CHARTS_DIR}/{EPICS_CHART}" width="100%" '
            f'alt="Resolved issues by epic"></td>',
            f"<td width=\"50%\"><b>Main focus</b>: {note}<ol>{entries}</ol></td></tr>", "</table>"]


# The charts.

def week_groups(start, end):
    """[(start, end)]: the calendar weeks, Monday to Sunday, from the day
    `start` to the day `end`, as dates, a few at a time when there would be
    more than MAX_POINTS of them, each group always the same weeks, the first
    and last clipped to `start` and `end`."""
    first, last = date.fromisoformat(start), date.fromisoformat(end)

    def week(day):
        return (day - EPOCH_MONDAY).days // 7
    width = 1
    while week(last) // width - week(first) // width + 1 > MAX_POINTS:
        width += 1
    return [(max(first, EPOCH_MONDAY + timedelta(weeks=group * width)),
             min(last, EPOCH_MONDAY + timedelta(weeks=(group + 1) * width, days=-1)))
            for group in range(week(first) // width, week(last) // width + 1)]


def over_time_chart(items, weeks, label):
    """A line chart of how many of `items` fall in each of `weeks`, by their
    day, each month named under its first week, `label` under the axis."""
    counts = [sum(1 for item in items if first.isoformat() <= item["date"] <= last.isoformat())
              for first, last in weeks]
    step, top = scale(max(counts, default=0))
    plot_width, plot_height = WIDTH - LEFT - RIGHT, HEIGHT - TOP - BOTTOM
    xs = [LEFT + (plot_width * index / (len(weeks) - 1) if len(weeks) > 1 else plot_width / 2)
          for index in range(len(weeks))]
    ys = [TOP + plot_height * (1 - count / top) for count in counts]
    line = " ".join(f"{x:.1f},{y:.1f}" for x, y in zip(xs, ys))
    body = [*y_axis(step, top), f'<polygon points="{xs[0]:.1f},{TOP + plot_height:.1f} {line} '
            f'{xs[-1]:.1f},{TOP + plot_height:.1f}" fill="{AREA}"/>',
            f'<polyline points="{line}" fill="none" stroke="{LINE}" stroke-width="2.5"/>', *axes()]
    starts = [first for first, _ in weeks]
    months = [(x, first) for index, (x, first) in enumerate(zip(xs, starts))
              if index == 0 or first.month != starts[index - 1].month]
    body += [text(x, HEIGHT - BOTTOM + 16,
                  f"{first:%b}", size=12, anchor="middle") for x, first in months]
    body.append(text(LEFT + plot_width / 2, HEIGHT -
                6, label, size=13, anchor="middle"))
    return svg(WIDTH, HEIGHT, body)


def points_chart(issues, average):
    """A bar chart of how many of the estimated `issues` have each number of
    story points, with a dashed line at their `average`."""
    values = sorted({issue["points"]
                    for issue in issues if issue["points"] is not None})
    label = text(LEFT + (WIDTH - LEFT - RIGHT) / 2, HEIGHT - 6, "story points (resolved issues)", size=13,
                 anchor="middle")
    if not values:
        return svg(WIDTH, HEIGHT, [text(WIDTH / 2, HEIGHT / 2, "No estimated issues", size=13, color=MUTED,
                                        anchor="middle"), label])
    counts = [sum(1 for issue in issues if issue["points"] == value)
              for value in values]
    step, top = scale(max(counts))
    plot_width, plot_height = WIDTH - LEFT - RIGHT, HEIGHT - TOP - BOTTOM
    slot = plot_width / len(values)
    centres = [LEFT + slot * (index + 0.5) for index in range(len(values))]
    body = [*y_axis(step, top)]
    for centre, value, count in zip(centres, values, counts):
        height = plot_height * count / top
        body.append(f'<rect x="{centre - slot * 0.34:.1f}" y="{TOP + plot_height - height:.1f}" '
                    f'width="{slot * 0.68:.1f}" height="{height:.1f}" fill="{LINE}"/>')
        body.append(text(centre, HEIGHT - BOTTOM + 16,
                    number(value), size=12, anchor="middle"))
    x = average_x(average, values, centres)
    body += [f'<line x1="{x:.1f}" y1="{TOP:.1f}" x2="{x:.1f}" y2="{TOP + plot_height:.1f}" stroke="{AVERAGE}" '
             f'stroke-width="1.5" stroke-dasharray="5 4"/>', *axes(), label]
    return svg(WIDTH, HEIGHT, body)


def epics_chart(by_epic):
    """A pie of the resolved issues by epic, a slice for each epic and one
    for the issues with no epic, with a legend of each slice's epic and
    count, each epic named by its key and title, cut short to fit, as tall
    as the legend needs."""
    slices = [(f'{entry["key"]} {entry["title"]}', entry["issues"], PALETTE[index % len(PALETTE)])
              for index, entry in enumerate(by_epic["epics"])]
    if by_epic["no_epic"]:
        slices.append(("no epic", by_epic["no_epic"], NO_EPIC))
    total = sum(count for _, count, _ in slices)
    row = 18
    height = max(HEIGHT, row * len(slices) + 24)
    radius = height / 2 - 10
    cx, cy = radius + 12, height / 2
    if not total:
        return svg(EPICS_WIDTH, height, [text(EPICS_WIDTH / 2, height / 2, "No resolved issues", size=13,
                                              color=MUTED, anchor="middle")])
    # The biggest slice ends at 12 o'clock, on the left; the others follow it
    # clockwise from 12.
    body, angle = [], -math.pi / 2 - 2 * math.pi * slices[0][1] / total
    for _, count, colour in slices:
        sweep = 2 * math.pi * count / total
        if count == total:
            body.append(
                f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{radius:.1f}" fill="{colour}"/>')
        else:
            end = angle + sweep
            body.append(f'<path d="M{cx:.1f},{cy:.1f} L{cx + radius * math.cos(angle):.1f},'
                        f'{cy + radius * math.sin(angle):.1f} A{radius:.1f},{radius:.1f} 0 '
                        f'{int(sweep > math.pi)} 1 {cx + radius * math.cos(end):.1f},{cy + radius * math.sin(end):.1f} Z" '
                        f'fill="{colour}" stroke="white" stroke-width="1.5"/>')
        angle += sweep
    legend_x, top = cx + radius + 24, cy - row * len(slices) / 2
    for index, (label, count, colour) in enumerate(slices):
        y = top + row * index
        body.append(
            f'<rect x="{legend_x:.1f}" y="{y:.1f}" width="11" height="11" fill="{colour}"/>')
        body.append(text(legend_x + 17, y + 10, fit(label, EPICS_WIDTH - legend_x - 17 - RIGHT,
                                                    f" ({count})", 12), size=12))
    return svg(EPICS_WIDTH, height, body)


def fit(label, room, tail, size):
    """`label` then `tail`, the label cut short with "…" so the whole fits
    `room` at font `size`."""
    if text_width(label + tail, size) <= room:
        return label + tail
    while label and text_width(label + "…" + tail, size) > room:
        label = label[:-1]
    return label.rstrip() + "…" + tail


def average_x(average, values, centres):
    """Where `average` falls among the bars of `values` centred at
    `centres`: between the two values it lies between, in proportion."""
    for (low, left), (high, right) in zip(zip(values, centres), zip(values[1:], centres[1:])):
        if low <= average <= high:
            return left + (right - left) * (average - low) / (high - low)
    return centres[0] if average <= values[0] else centres[-1]


def scale(highest):
    """(step, top): an axis's round step for counts up to `highest`, and its
    top, a whole number of steps, at least one."""
    step = nice_step(max(highest, 1))
    return step, step * max(1, -(-highest // step))


def y_axis(step, top):
    """The y axis's tick labels and grid lines, from 0 to `top` every
    `step`."""
    plot_height = HEIGHT - TOP - BOTTOM
    lines = []
    for value in range(0, int(top) + 1, step):
        y = TOP + plot_height * (1 - value / top)
        lines.append(
            f'<line x1="{LEFT}" y1="{y:.1f}" x2="{WIDTH - RIGHT}" y2="{y:.1f}" stroke="{GRID}"/>')
        lines.append(text(LEFT - 6, y + 4, value, size=11, anchor="end"))
    return lines


def axes():
    """The chart's left and bottom axis lines."""
    bottom = HEIGHT - BOTTOM
    return [f'<line x1="{LEFT}" y1="{TOP}" x2="{LEFT}" y2="{bottom}" stroke="{INK}" stroke-width="1.2"/>',
            f'<line x1="{LEFT}" y1="{bottom}" x2="{WIDTH - RIGHT}" y2="{bottom}" stroke="{INK}" stroke-width="1.2"/>']


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Write the prep's report, <Person>_Review_Prep.md, and its charts from work.json, then check them.",
        epilog="Prints one line of JSON: report, the report's path, and problems, what the check found, "
        "empty when it passes. Exits 1 when it finds any.")
    parser.add_argument("--prep", required=True,
                        help="the prep's folder, <Person>_<YY-MM-DD>, as init_prep.py printed it")
    args = parser.parse_args(argv)
    with stops_on_failure():
        result = make_report(args.prep)
    print(json.dumps(result, ensure_ascii=False))
    return 1 if result["problems"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
