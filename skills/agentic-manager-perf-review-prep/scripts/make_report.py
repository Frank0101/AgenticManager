"""Writes a prep's report, report.md, and its charts from work.json: for now, the person's Jira figures.

Every figure is one of work.json's facts, and every link one of its search
addresses, so the report can't count differently from the model. The charts
group the items by calendar week, Monday to Sunday, counted from a fixed
Monday, so a day falls in the same week whatever the period, a few weeks at a
time when there would be more than MAX_POINTS of them. They are drawn as SVG
by hand, as skills install nothing.
"""
import argparse
import json
import os
from datetime import date, timedelta

from common import (CHARTS_DIR, JIRA_CELLS, FOLDER_NAME, GRID, INK, MUTED, PERSON, REPORT, WORK, number,
                    average_text, esc, nice_step, prep_dir, read_json, report_problems, shown, stops_on_failure, svg, text,
                    types_text, write_output_file)

EPOCH_MONDAY = date(2001, 1, 1)
MAX_POINTS = 20
# A chart's size; the report fits it to its column.
WIDTH, HEIGHT = 440, 170
LEFT, RIGHT, TOP, BOTTOM = 34, 12, 14, 44
LINE, AREA, AVERAGE = "#4a72b0", "#d3dcec", "#d92d20"


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
              chart["resolved_points"]: points_chart(jira["resolved"], jira["resolved_points"]["average"])}
    for name, content in charts.items():
        write_output_file(
            FOLDER_NAME, f"{prep}/{CHARTS_DIR}/{name}", content.encode("utf-8"))
    report = render(person, work)
    path, _ = write_output_file(
        FOLDER_NAME, f"{prep}/{REPORT}", report.encode("utf-8"))
    return {"report": path, "problems": report_problems(report, work, os.listdir(os.path.join(folder, CHARTS_DIR)))}


# The report.

def render(person, work):
    """report.md's text: the person and the period, then their Jira
    figures."""
    return "\n".join([f"# {person['person']}: performance review prep", "",
                      f"Period: {shown(person['start'], person['end'])}", "",
                      *jira_section(work["jira"])]) + "\n"


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
        description="Write the prep's report, report.md, and its charts from work.json, then check them.",
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
