"""Draws a prep's report charts as SVG from data.json: for Jira, the issues created and resolved week by week, the story points of the resolved ones and the resolved issues by epic; for GitHub, the pull requests opened and merged week by week, the merged ones' size and their repositories.

It draws data.json's series and works none out, as the model's facts are
worked out once and checked. A week's point sits at its last day's date on a
scale over the period, so a clipped week at an edge sits near its neighbour
and its lower count reads as partial. An epic, or a repository, has one colour in
every chart of its source, its pie slice's, by data.json's order, so one
legend reads them all; those beyond it are drawn together as others. They
are drawn as SVG by hand, as skills install nothing.
"""
import math
from datetime import date

from common import (BINS_PER_DECADE, months_of, CHARTS_DIR, EPICS_CHART, FOLDER_NAME, GITHUB_CELLS, GRID, HEADINGS, INK, JIRA_CELLS, MUTED,
                    REPOS_CHART, SURFACE, arc_segment, legend, repo_code, nice_step, number, svg, text, text_width, write_output_file)

# A chart's size, its plot's height, below which its legend adds rows; the
# report fits it to its column.
WIDTH, HEIGHT = 440, 170
# The pie fills half the row, the table's charts a third: one and a half
# times as wide, at the same height, it shows as tall as they do.
EPICS_WIDTH = WIDTH * 3 // 2
LEFT, RIGHT, TOP, BOTTOM = 30, 12, 12, 36
# The table's charts' text, small, so the plot has the room: the axes', the
# caption under them and the legend's. A pie keeps its own, larger.
AXIS_FONT, CAPTION_FONT, LEGEND_FONT = 10, 11, 9
# Each point's or bar's value written over it, smaller still, and none for a
# zero, which would only crowd the axis.
VALUE_FONT = 6
# The total's line and area are grey, as the groups' lines take the colours.
LINE, AREA, AVERAGE = "#3d3d3d", "#e4e2dd", "#d92d20"
# The groups' colours, one for each of at most MAX_GROUPS.
PALETTE = ("#4a72b0", "#e08a2c", "#3f9c6c", "#c4524a",
           "#8a6bbf", "#2a9fb0", "#b38b2e", "#d16fa6", "#5c7d2e")
# Dark enough to show as a line over the total's grey area, and apart from
# each other: the work in no group, such as issues with no epic, and that of
# every other group.
NO_EPIC, OTHER = "#5f5a52", "#948c80"
# A pie's title, above it.
TITLE_HEIGHT = 20


def write_charts(prep, data):
    """Write every chart of the prep `prep`'s report, from `data`, its
    data.json, to its _charts folder."""
    for name, content in draw(data).items():
        write_output_file(
            FOLDER_NAME, f"{prep}/{CHARTS_DIR}/{name}", content.encode("utf-8"))


def draw(data):
    """{file name: SVG}: every chart of the report, from `data`, its
    data.json. Every chart has one height, its tallest legend's, so the
    sections' charts show alike, and each pie it too, one and a half times
    as wide, so on the page it shows as tall as they do."""
    jira, github, weeks = data["jira"], data["github"], data["weeks"]
    keys = jira_legends(jira)
    repos = github_legends(github)
    height = max(chart_legend(entries)[1]
                 for entries in (*keys[1:], *repos[1:]))
    return {**jira_charts(jira, weeks, keys, height), **github_charts(github, weeks, repos, height)}


def jira_legends(jira):
    """(colours, lines, bars): each epic's colour, by data.json's epic order,
    and the legends of the line charts and of the story points' bars, each
    epic named by its key alone, as the pie names it with its title."""
    colours = {key: PALETTE[index]
               for index, key in enumerate(jira["epic_order"])}
    # The others, and those with no epic, are in the legends only when some
    # issue is.

    def some(part):
        return any(any(jira[f"{name}_by_week"][part]) for name in ("created", "resolved"))
    groups = [*((key, colour) for key, colour in colours.items()),
              *([("other epics", OTHER)] if some("other") else []),
              *([("no epic", NO_EPIC)] if some("no_epic") else [])]
    return (colours, [("total", LINE, False), *((label, colour, False) for label, colour in groups)],
            [*((label, colour, False) for label, colour in groups), ("average", AVERAGE, True)])


def jira_charts(jira, weeks, legends, height):
    """{file name: SVG}: the Jira charts, from `jira`, data.json's, over
    `weeks`, with `legends`, jira_legends()'s, `height` tall."""
    chart = dict(JIRA_CELLS)
    colours, lines, bars = legends

    def thin(series):
        return [*((colours[key], values) for key, values in series["epics"].items()),
                (OTHER, series["other"]), (NO_EPIC, series["no_epic"])]
    # The main focus's epics, and the issues with no epic, by key, with
    # their shares; a project's, when no issue has an epic, has no slice.
    focus = {entry["key"]: entry["share"] for entry in jira["focus"]}
    pie = jira["resolved_by_epic"]
    return {chart["created"]: over_time_chart(jira["created_by_week"]["total"], thin(jira["created_by_week"]), weeks,
                                              HEADINGS["created"], lines, height),
            chart["resolved"]: over_time_chart(jira["resolved_by_week"]["total"], thin(jira["resolved_by_week"]), weeks,
                                               HEADINGS["resolved"], lines, height),
            chart["resolved_points"]: bars_chart(
                [(number(row["points"]), [*((colours[key], n) for key, n in row["epics"].items()),
                                          (OTHER, row["other"]), (NO_EPIC, row["no_epic"])])
                 for row in jira["points_by_epic"]],
                HEADINGS["resolved_points"], "No estimated issues", bars, height,
                marker=value_position(jira["resolved_points"]["average"], [row["points"] for row in jira["points_by_epic"]])),
            EPICS_CHART: pie_chart("Resolved issues by epic",
                                   [*((f'{entry["key"]} {entry["title"]}' if entry["key"] else "no epic", entry["issues"],
                                       colours[entry["key"]] if entry["key"] else NO_EPIC, focus.get(entry["key"]))
                                      for entry in pie["epics"]), ("other epics", pie["other"], OTHER, None)],
                                   "No resolved issues", height)}


def github_legends(github):
    """(colours, lines, sizes): each repository's colour, by data.json's
    repository order, and the legends of the charts over time and of the
    sizes' distribution, each repository named by its code alone, as the pie
    names it with its name."""
    order = github["repo_order"]
    colours = {repo: PALETTE[index] for index, repo in enumerate(order)}
    others = any(any(github[f"{name}_by_week"]["other"])
                 for name in ("opened", "merged"))
    groups = [*((repo_code(repo, order), colour) for repo, colour in colours.items()),
              *([("other repositories", OTHER)] if others else [])]
    lines = [("total", LINE, False), *((label, colour, False)
                                       for label, colour in groups)]
    return colours, lines, [*lines, ("median", AVERAGE, True)]


def github_charts(github, weeks, legends, height):
    """{file name: SVG}: the GitHub charts, from `github`, data.json's, over
    `weeks`, with `legends`, github_legends()'s, `height` tall; the pie names
    each repository by its code and its name without its owner, the person's
    organisation."""
    chart = dict(GITHUB_CELLS)
    colours, lines, sizes = legends

    def thin(series):
        return [*((colours[repo], values) for repo, values in series["repos"].items()), (OTHER, series["other"])]
    focus = {entry["repo"]: entry["share"] for entry in github["focus"]}
    pie = github["merged_by_repo"]
    return {chart["opened"]: over_time_chart(github["opened_by_week"]["total"], thin(github["opened_by_week"]), weeks,
                                             HEADINGS["opened"], lines, height),
            chart["merged"]: over_time_chart(github["merged_by_week"]["total"], thin(github["merged_by_week"]), weeks,
                                             HEADINGS["merged"], lines, height),
            chart["merged_lines"]: distribution_chart(github["lines_distribution"], github["merged_lines"]["median"],
                                                      HEADINGS["merged_lines"] + " (lines changed)", colours, sizes, height),
            REPOS_CHART: pie_chart("Merged PRs by repository",
                                   [*((f'{repo_code(entry["repo"], github["repo_order"])} {entry["repo"].split("/")[-1]}',
                                       entry["prs"], colours[entry["repo"]], focus.get(entry["repo"]))
                                      for entry in pie["repos"]), ("other repositories", pie["other"], OTHER, None)],
                                   "No merged pull requests", height)}


def value_position(value, values):
    """Where `value` falls among the bars of `values`, as a bar's index, in
    proportion between the two values it lies between, a bar's middle being
    its value; None for None."""
    if value is None or not values:
        return None
    for index, (low, high) in enumerate(zip(values, values[1:])):
        if low <= value <= high:
            return index + 0.5 + (value - low) / (high - low)
    return 0.5 if value <= values[0] else len(values) - 0.5


def over_time_chart(total, thin, weeks, label, entries, height):
    """A line_chart() over `weeks` of `total` and `thin`, each point at the
    date of its week's last day, on a scale linear from the first day of the
    first week to the last of the last, each month named in the middle of its
    days within the period and set apart from the one before by a dashed line
    at its first day, on the same scale, `label` under the axis, with the
    legend of `entries`, the chart `height` tall. A lone week is centred."""
    first, last = date.fromisoformat(
        weeks[0][0]), date.fromisoformat(weeks[-1][1])
    span = (last - first).days

    def place(day):
        return (day - first).days / span if span else 0.5
    xs = [0.5] if len(weeks) == 1 else [place(
        date.fromisoformat(end)) for _, end in weeks]
    months = [(date.fromisoformat(month["start"]), date.fromisoformat(month["end"]))
              for month in months_of(first, last).values()]
    ticks = [((place(start) + place(end)) / 2,
              f"{start:%b}") for start, end in months]
    return line_chart(total, thin, xs, ticks, label, entries, height,
                      dividers=[place(start) for start, _ in months[1:]])


def distribution_chart(series, median, label, colours, entries, height):
    """A line_chart() of `series`, lines_distribution()'s, a point in the
    middle of each bin of its log scale: the total and, thin, each
    repository's in its colour from `colours` and the others', each power of
    ten named under it, `label` under the axis, a dashed line at the
    `median`, and the legend of `entries`, the chart `height` tall."""
    bins = len(series["total"])
    xs = [(index + 0.5) / bins for index in range(bins)]
    ticks = [(index / bins, power_label(index // BINS_PER_DECADE))
             for index in range(0, bins + 1, BINS_PER_DECADE)]
    thin = [*((colours[repo], values)
              for repo, values in series["repos"].items()), (OTHER, series["other"])]
    marker = BINS_PER_DECADE * \
        math.log10(max(median, 1)) / bins if median is not None else None
    return line_chart(series["total"], thin, xs, ticks, label, entries, height, marker)


def power_label(power):
    """The label of ten to the `power`, short enough for the axis: 1, 10,
    100, 1k, 10k, 100k, 1M and so on."""
    for unit, size in (("M", 6), ("k", 3)):
        if power >= size:
            return f"{10 ** (power - size)}{unit}"
    return str(10 ** power)


def line_chart(total, thin, xs, ticks, label, entries, height, marker=None, dividers=()):
    """A line chart of `total`, bold over its area, and of each of `thin`,
    (colour, values), a thin line, those all zero left out, each value at
    the place of `xs`, from 0 to 1 across the plot; each of `ticks`, (place,
    text), named under the axis, `label` under them, with `marker`, a place,
    a dashed line there, a faint dashed line at each of `dividers`, places,
    under the lines, each point of the total's value over it, none for a
    zero, and below it the legend of `entries`, the chart `height` tall."""
    step, top = scale(max(total, default=0))
    plot_width, plot_height = WIDTH - LEFT - RIGHT, HEIGHT - TOP - BOTTOM
    places = [LEFT + plot_width * x for x in xs]

    def points(values):
        return " ".join(f"{x:.1f},{TOP + plot_height * (1 - value / top):.1f}" for x, value in zip(places, values))
    line = points(total)
    body = [*y_axis(step, top),
            f'<polygon points="{places[0]:.1f},{TOP + plot_height:.1f} {line} '
            f'{places[-1]:.1f},{TOP + plot_height:.1f}" fill="{AREA}"/>',
            *(f'<line x1="{LEFT + plot_width * x:.1f}" y1="{TOP}" x2="{LEFT + plot_width * x:.1f}" '
              f'y2="{TOP + plot_height:.1f}" stroke="{MUTED}" stroke-width="0.8" stroke-dasharray="3 3"/>'
              for x in dividers),
            *(f'<polyline points="{points(values)}" fill="none" stroke="{colour}" stroke-width="1.3"/>'
              for colour, values in thin if any(values)),
            f'<polyline points="{line}" fill="none" stroke="{LINE}" stroke-width="2.5"/>', *axes(),
            *point_labels(places, [TOP + plot_height * (1 - value / top) for value in total], total)]
    if marker is not None:
        x = LEFT + plot_width * marker
        body.append(f'<line x1="{x:.1f}" y1="{TOP:.1f}" x2="{x:.1f}" y2="{TOP + plot_height:.1f}" '
                    f'stroke="{AVERAGE}" stroke-width="1.5" stroke-dasharray="5 4"/>')
    body += [text(LEFT + plot_width * x, HEIGHT - BOTTOM + 14, tick, size=AXIS_FONT, anchor="middle")
             for x, tick in ticks]
    body.append(text(LEFT + plot_width / 2, HEIGHT - 6,
                label, size=CAPTION_FONT, anchor="middle"))
    return svg(WIDTH, height, body + chart_legend(entries)[0])


def point_labels(xs, ys, values):
    """The `values` of a line's points at (`xs`, `ys`) written over them, the
    first and last kept inside the plot; a zero none."""
    return [value_label(x, y - 5, value, "start" if index == 0 else "end" if index == len(values) - 1 else "middle")
            for index, (x, y, value) in enumerate(zip(xs, ys, values)) if value]


def value_label(x, y, value, anchor="middle"):
    """`value`, a number or its text, written small and bold at (`x`, `y`),
    over its point, its bar or in its slice, with a halo of the chart's
    surface, so a line it touches leaves it legible."""
    return text(x, y, value if isinstance(value, str) else number(value), size=VALUE_FONT, color=LINE, anchor=anchor, bold=True,
                extra=f' stroke="{SURFACE}" stroke-width="2" paint-order="stroke"')


def chart_legend(entries):
    """(elements, height): a legend of `entries`, (label, colour, dashed),
    each a box of its colour or, dashed, a dashed line, laid out in rows
    below the plot, wrapping at the chart's width, and the chart's height
    with it."""
    return legend([(fit(label, WIDTH - LEFT - RIGHT - 30, "", LEGEND_FONT), colour, (1.5, "3 2") if dashed else None)
                   for label, colour, dashed in entries], LEFT, WIDTH - RIGHT, HEIGHT + 4, size=LEGEND_FONT,
                  line_length=10)


def bars_chart(rows, label, empty, entries, height, marker=None):
    """A bar chart of `rows`, (bar label, parts), each part (colour, count)
    stacked from the bottom, with `label` under the axis, or `empty` when no
    row holds any; with `marker`, a position across the bars in bars' widths,
    such as an average's, a dashed line there; each bar's total over it,
    none for a zero; and below it the legend of `entries`, the chart
    `height` tall."""
    caption = text(LEFT + (WIDTH - LEFT - RIGHT) / 2,
                   HEIGHT - 6, label, size=CAPTION_FONT, anchor="middle")
    totals = [sum(count for _, count in parts) for _, parts in rows]
    if not any(totals):
        return svg(WIDTH, height, [text(WIDTH / 2, HEIGHT / 2, empty, size=CAPTION_FONT, color=MUTED, anchor="middle"),
                                   caption])
    step, top = scale(max(totals))
    plot_width, plot_height = WIDTH - LEFT - RIGHT, HEIGHT - TOP - BOTTOM
    slot = plot_width / len(rows)
    centres = [LEFT + slot * (index + 0.5) for index in range(len(rows))]
    body = [*y_axis(step, top)]
    for centre, (bar, parts), total in zip(centres, rows, totals):
        base = TOP + plot_height
        for colour, count in parts:
            if count:
                part = plot_height * count / top
                base -= part
                body.append(f'<rect x="{centre - slot * 0.34:.1f}" y="{base:.1f}" width="{slot * 0.68:.1f}" '
                            f'height="{part:.1f}" fill="{colour}" stroke="white" stroke-width="0.5"/>')
        body.append(text(centre, HEIGHT - BOTTOM + 14,
                    bar, size=AXIS_FONT, anchor="middle"))
        if total:
            body.append(value_label(centre, base - 4, total))
    if marker is not None:
        x = LEFT + slot * marker
        body.append(f'<line x1="{x:.1f}" y1="{TOP:.1f}" x2="{x:.1f}" y2="{TOP + plot_height:.1f}" '
                    f'stroke="{AVERAGE}" stroke-width="1.5" stroke-dasharray="5 4"/>')
    return svg(WIDTH, height, [*body, *axes(), caption, *chart_legend(entries)[0]])


def pie_chart(title, slices, empty, height):
    """A pie of `slices`, (label, count, colour, share), those of none left
    out, under `title`, with a legend of each slice's label, cut short to
    fit, and count, or `empty` when there are none, `height` tall; a slice
    with a share, one of the main focus, shows it, written as the other
    charts' values."""
    slices = [entry for entry in slices if entry[1]]
    total = sum(count for _, count, _, _ in slices)
    body = [text(12, 15, title, size=13, bold=True)]
    if not total:
        return svg(EPICS_WIDTH, height, [*body, text(EPICS_WIDTH / 2, height / 2, empty, size=13, color=MUTED,
                                                     anchor="middle")])
    row = min(18, (height - TITLE_HEIGHT - 20) / len(slices))
    radius = (height - TITLE_HEIGHT) / 2 - 10
    cx, cy = radius + 12, TITLE_HEIGHT + (height - TITLE_HEIGHT) / 2
    # The biggest slice ends at 12 o'clock, on the left; the others follow it
    # clockwise from 12.
    start, labels = -360 * slices[0][1] / total, []
    for _, count, colour, share in slices:
        sweep = 360 * count / total
        if count == total:
            body.append(
                f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{radius:.1f}" fill="{colour}"/>')
        else:
            body.append(f'<path d="{arc_segment(cx, cy, radius, 0, start, start + sweep)}" '
                        f'fill="{colour}" stroke="white" stroke-width="1.5"/>')
        if share is not None:
            # Inside the slice, at its middle, two thirds of the way out.
            middle = math.radians(start + sweep / 2)
            labels.append(value_label(cx + radius * 0.66 * math.sin(middle),
                                      cy - radius * 0.66 * math.cos(middle) + 2, f"{share}%"))
        start += sweep
    body += labels
    legend_x, top = cx + radius + 18, cy - row * len(slices) / 2
    for index, (label, count, colour, _) in enumerate(slices):
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
        lines.append(text(LEFT - 5, y + 3, value,
                     size=AXIS_FONT, anchor="end"))
    return lines


def axes():
    """The chart's left and bottom axis lines."""
    bottom = HEIGHT - BOTTOM
    return [f'<line x1="{LEFT}" y1="{TOP}" x2="{LEFT}" y2="{bottom}" stroke="{INK}" stroke-width="1.2"/>',
            f'<line x1="{LEFT}" y1="{bottom}" x2="{WIDTH - RIGHT}" y2="{bottom}" stroke="{INK}" stroke-width="1.2"/>']
