"""Draws a prep's report charts as SVG from data.json: the Jira issues created and resolved week by week, the story points of the resolved ones, and the resolved issues by epic.

It draws data.json's series and works none out, as the model's facts are
worked out once and checked. An epic has one colour in every chart, its pie
slice's, by data.json's epic order, so one legend reads them all. They are
drawn as SVG by hand, as skills install nothing.
"""
import math
from datetime import date

from common import (EPICS_CHART, GRID, INK, JIRA_CELLS,
                    MUTED, nice_step, number, svg, text, text_width)

# A chart's size, its plot's height, below which its legend adds rows; the
# report fits it to its column.
WIDTH, HEIGHT = 440, 170
# The pie fills half the row, the table's charts a third: one and a half
# times as wide, at the same height, it shows as tall as they do.
EPICS_WIDTH = WIDTH * 3 // 2
LEFT, RIGHT, TOP, BOTTOM = 34, 12, 14, 44
# The total's line and area are grey, as the epics' lines take the colours.
LINE, AREA, AVERAGE = "#3d3d3d", "#e4e2dd", "#d92d20"
# The epics' slices, then the issues' with no epic.
PALETTE = ("#4a72b0", "#e08a2c", "#3f9c6c", "#c4524a", "#8a6bbf", "#2a9fb0", "#b38b2e", "#d16fa6", "#5c7d2e",
           "#6f6f9c")
# Dark enough to show as a line over the total's grey area.
NO_EPIC = "#a8a399"


def draw(data):
    """{file name: SVG}: every chart of the report, from `data`, its
    data.json."""
    jira, weeks = data["jira"], data["weeks"]
    chart = dict(JIRA_CELLS)
    colours = {key: PALETTE[index % len(PALETTE)]
               for index, key in enumerate(jira["epic_order"])}
    # The table's charts share one legend's rows and so one height, which the
    # pie beside the main focus takes too.
    lines = [("total", LINE, False), *((key, colour, False) for key, colour in colours.items()),
             ("no epic", NO_EPIC, False)]
    bars = [*((key, colour, False) for key, colour in colours.items()), ("no epic", NO_EPIC, False),
            ("average", AVERAGE, True)]
    height = max(legend(entries, HEIGHT)[1] for entries in (lines, bars))
    return {chart["created"]: over_time_chart(jira["created_by_week"], weeks, "created", colours, lines, height),
            chart["resolved"]: over_time_chart(jira["resolved_by_week"], weeks, "resolved", colours, lines, height),
            chart["resolved_points"]: points_chart(jira["points_by_epic"], jira["resolved_points"]["average"],
                                                   colours, bars, height),
            EPICS_CHART: epics_chart(jira["resolved_by_epic"], colours, height)}


def over_time_chart(series, weeks, label, colours, entries, height):
    """A line chart of `series`, by_week()'s, over `weeks`: the total, bold
    over its area, and each epic's, thin, in its colour from `colours`, and
    the issues' with no epic; each month named under its first week, `label`
    under the axis, and below it the legend of `entries`, the chart `height`
    tall."""
    counts = series["total"]
    step, top = scale(max(counts, default=0))
    plot_width, plot_height = WIDTH - LEFT - RIGHT, HEIGHT - TOP - BOTTOM
    xs = [LEFT + (plot_width * index / (len(weeks) - 1) if len(weeks) > 1 else plot_width / 2)
          for index in range(len(weeks))]

    def points(values):
        return " ".join(f"{x:.1f},{TOP + plot_height * (1 - value / top):.1f}" for x, value in zip(xs, values))
    line = points(counts)
    thin = [(colours[key], points(values))
            for key, values in series["epics"].items()]
    if any(series["no_epic"]):
        thin.append((NO_EPIC, points(series["no_epic"])))
    body = [*y_axis(step, top), f'<polygon points="{xs[0]:.1f},{TOP + plot_height:.1f} {line} '
            f'{xs[-1]:.1f},{TOP + plot_height:.1f}" fill="{AREA}"/>',
            *(f'<polyline points="{values}" fill="none" stroke="{colour}" stroke-width="1.3"/>'
              for colour, values in thin),
            f'<polyline points="{line}" fill="none" stroke="{LINE}" stroke-width="2.5"/>', *axes()]
    starts = [date.fromisoformat(first) for first, _ in weeks]
    months = [(x, first) for index, (x, first) in enumerate(zip(xs, starts))
              if index == 0 or first.month != starts[index - 1].month]
    body += [text(x, HEIGHT - BOTTOM + 16,
                  f"{first:%b}", size=12, anchor="middle") for x, first in months]
    body.append(text(LEFT + plot_width / 2, HEIGHT -
                6, label, size=13, anchor="middle"))
    return svg(WIDTH, height, body + legend(entries, HEIGHT)[0])


def legend(entries, top):
    """(elements, height): a legend of `entries`, (label, colour, dashed),
    each a box of its colour or, dashed, a dashed line, laid out in rows below
    `top`, wrapping at the chart's width, and the chart's height with it."""
    elements, x, y = [], LEFT, top + 4
    for label, colour, dashed in entries:
        width = 11 + 5 + text_width(label, 11) + 14
        if x + width > WIDTH - RIGHT and x > LEFT:
            x, y = LEFT, y + 16
        elements += [f'<line x1="{x:.1f}" y1="{y + 5:.1f}" x2="{x + 10:.1f}" y2="{y + 5:.1f}" stroke="{colour}" '
                     f'stroke-width="1.5" stroke-dasharray="3 2"/>' if dashed else
                     f'<rect x="{x:.1f}" y="{y:.1f}" width="10" height="10" fill="{colour}"/>',
                     text(x + 15, y + 9, label, size=11)]
        x += width
    return elements, y + 18


def points_chart(rows, average, colours, entries, height):
    """A bar chart of `rows`, points_by_epic()'s: a bar for each number of
    story points, split by epic in its colour from `colours`, the issues with
    no epic on top, with a dashed line at their `average`, and below it the
    legend of `entries`, the chart `height` tall."""
    label = text(LEFT + (WIDTH - LEFT - RIGHT) / 2, HEIGHT - 6, "story points (resolved issues)", size=13,
                 anchor="middle")
    if not rows:
        return svg(WIDTH, height, [text(WIDTH / 2, HEIGHT / 2, "No estimated issues", size=13, color=MUTED,
                                        anchor="middle"), label])
    values = [row["points"] for row in rows]
    step, top = scale(max(row["issues"] for row in rows))
    plot_width, plot_height = WIDTH - LEFT - RIGHT, HEIGHT - TOP - BOTTOM
    slot = plot_width / len(rows)
    centres = [LEFT + slot * (index + 0.5) for index in range(len(rows))]
    body = [*y_axis(step, top)]
    for centre, row in zip(centres, rows):
        base = TOP + plot_height
        parts = [(colours[key], count)
                 for key, count in row["epics"].items()] + [(NO_EPIC, row["no_epic"])]
        for colour, count in parts:
            if count:
                part = plot_height * count / top
                base -= part
                body.append(f'<rect x="{centre - slot * 0.34:.1f}" y="{base:.1f}" width="{slot * 0.68:.1f}" '
                            f'height="{part:.1f}" fill="{colour}" stroke="white" stroke-width="0.5"/>')
        body.append(text(centre, HEIGHT - BOTTOM + 16,
                    number(row["points"]), size=12, anchor="middle"))
    x = average_x(average, values, centres)
    body += [f'<line x1="{x:.1f}" y1="{TOP:.1f}" x2="{x:.1f}" y2="{TOP + plot_height:.1f}" stroke="{AVERAGE}" '
             f'stroke-width="1.5" stroke-dasharray="5 4"/>', *axes(), label, *legend(entries, HEIGHT)[0]]
    return svg(WIDTH, height, body)


def epics_chart(by_epic, colours, height):
    """A pie of the resolved issues by epic, a slice for each epic and one
    for the issues with no epic, with a legend of each slice's epic and
    count, each epic named by its key and title, cut short to fit, `height`
    tall, as tall on the page as the table's charts."""
    slices = [(f'{entry["key"]} {entry["title"]}', entry["issues"], colours[entry["key"]])
              for entry in by_epic["epics"]]
    if by_epic["no_epic"]:
        slices.append(("no epic", by_epic["no_epic"], NO_EPIC))
    total = sum(count for _, count, _ in slices)
    row = min(18, (height - 20) / max(len(slices), 1))
    radius = height / 2 - 10
    cx, cy = radius + 12, height / 2
    if not total:
        return svg(EPICS_WIDTH, height, [text(EPICS_WIDTH / 2, height / 2, "No resolved issues", size=13, color=MUTED,
                                              anchor="middle")])
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
    legend_x, top = cx + radius + 18, cy - row * len(slices) / 2
    for index, (label, count, colour) in enumerate(slices):
        y = top + row * index
        body.append(
            f'<rect x="{legend_x:.1f}" y="{y:.1f}" width="10" height="10" fill="{colour}"/>')
        body.append(text(legend_x + 15, y + 9, fit(label, EPICS_WIDTH - legend_x - 15 - RIGHT,
                                                   f" ({count})", 11), size=11))
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
