"""Writes a prep's report, <Person>_Review_Prep.md, from data.json, observations_content.json and step_change_content.json: the observations, going well and to improve by company value, then the context, then the step change from the previous feedback, each table under its summary, then the person's GitHub, Jira and Notion figures.

Every figure is one of data.json's facts, and every link one of its search
addresses, so the report can't count differently from the model; the charts
it shows are make_charts.py's.
"""
from common import (CHARTS_DIR, EPICS_CHART, OBSERVATION_HEADINGS, OBSERVATIONS_SUBTITLE, OBSERVATION_SOURCES, FOCUS_SHARE, FOLDER_NAME, GITHUB_CELLS, HEADINGS, JIRA_CELLS, NO_VALUE, PAGES_HEADING, REPOS_CHART,
                    NOT_RAISED, STEP_CHANGE_HEADING, STEP_CHANGE_NOT_APPLICABLE, STEP_CHANGE_ROW, STEP_CHANGE_SUBTITLE, STEP_CHANGES, VALUED_PARTS, ai_marked, chart_image, html_table, period_points, baseline_points, average_text, details_text, esc, link_href, reference_text, number, prep_dir, report_name, repo_code, repos_text, shown, size_text, types_text, week_text,
                    write_output_file)


def write_report(prep, person, data, observations_content, step_change_content):
    """Write the prep `prep`'s report from `person`, its person.json, `data`,
    its data.json, `observations_content`, its observations_content.json, and `step_change_content`, its
    step_change_content.json; returns its path."""
    path, _ = write_output_file(FOLDER_NAME, f"{prep}/{report_name(prep)}",
                                render(person, data, prep_dir(prep), observations_content, step_change_content).encode("utf-8"))
    return path


# The report.

def render(person, data, folder, observations_content, step_change_content):
    """The report's text: the person and the period, then the Observations,
    under OBSERVATIONS_SUBTITLE, what is going well, what to improve and the
    context, each summarised as
    `observations_content`, observations_content.json, says, then the step change, `step_change_content`,
    step_change_content.json, these first, as what the review is about, a note
    they cite linked relative to `folder`, the report's, then
    their GitHub work and their Jira work, each its main focus,
    then its figures, then the Notion pages they created. GitHub comes before
    Jira: with agents writing much
    of the code, pull requests stay the plainest trace of what someone did,
    while tickets grow more generic."""
    return "\n".join([f"# {person['person']}: performance review prep", "",
                      f"Period: {shown(person['start'], person['end'])}", "", "## Observations", "",
                      OBSERVATIONS_SUBTITLE, "", *observations_section(data["observations"],
                                                                       folder, observations_content), "",
                      *step_change_section(step_change_content, data["observations"],
                                           data["previous"], folder),
                      "", "## GitHub", "",
                      *repos_section(data["github"]), "", *
                      github_section(data["github"]), "", "## Jira", "",
                      *focus_section(data["jira"]), "", *
                      jira_section(data["jira"]), "", "## Notion", "",
                      *notion_section(data["notion"])]) + "\n"


def observations_section(observations, folder, observations_content):
    """The Observations section's lines: for each part of OBSERVATION_HEADINGS,
    a divider apart from the one before, its heading, marked as the agent's, as
    its summary, `observations_content`'s, follows, then, folded under it as the detail,
    with how many points it holds, a table of them, in small type, by
    observation_rows(), the most recent first, each with its source and its
    reference: – for a feedback, which has none, or a reading's
    evidence, the most recent first, each linked to its note or message."""
    lines = []
    for part, heading in OBSERVATION_HEADINGS.items():
        heads, rows, count = observation_rows(part, observations[part], folder)
        lines += [*(["", "---", ""] if lines else []), ai_marked(f"<b>{heading}</b>") if rows else f"<b>{heading}</b>",
                  *(["", observations_content[part].strip(), "", f"<details><summary>{details_text(count)}</summary>", "",
                     *html_table(heads, *rows, small=True), "", "</details>"] if rows else [])]
    return lines


def observation_rows(part, points, folder):
    """(heads, rows, count): the headings, rows and number of points of the
    table of `part`, whose `points` are data.json's. A part of VALUED_PARTS
    is grouped by company value, each value named once beside its points,
    the second value a point names beside it, its columns as wide in both, so
    the two read alike; context names none, so it is its points alone, its
    point given the room the values take. Each point shows its id, by which
    the manager can name it."""
    if part not in VALUED_PARTS:
        rows = [f'<td>{esc(point["point"])}</td><td>{OBSERVATION_SOURCES[point["source"]]}</td>'
                f'<td>{reference(point, folder)}</td><td>{point["id"]}</td>' for point in points]
        return observation_heads(((ai_marked("Point"), 65), ("Source", 10), ("References", 20), ("ID", 5))), rows, len(rows)
    rows = grouped_rows((esc(group["value"] or NO_VALUE),
                         [f'<td>{esc(point["also"] or "")}</td><td>{esc(point["point"])}</td>'
                          f'<td>{OBSERVATION_SOURCES[point["source"]]}</td>'
                          f'<td>{reference(point, folder)}</td><td>{point["id"]}</td>' for point in group["points"]])
                        for group in points)
    return observation_heads(((ai_marked("Value"), 10), (ai_marked("Also"), 10), (ai_marked("Point"), 45),
                              ("Source", 10), ("References", 20), ("ID", 5))), rows, len(rows)


def observation_heads(columns):
    """A table of observations' row of headings, each of `columns`, (heading,
    width as a percentage)."""
    return "".join(f'<th width="{width}%">{head}</th>' for head, width in columns)


def reference(point, folder):
    """Where an observation comes from, as its row writes it: its evidence,
    each by reference_text(), such as "Slack 14 Oct", linked to its message
    or note, or – when it has none, as a feedback."""
    return ", ".join(f'<a href="{esc(link_href(item["link"], folder))}">{esc(reference_text(point["source"], item))}</a>'
                     for item in point["evidence"]) or "–"


def step_change_section(value, observations, previous, folder):
    """The step change section's lines: its heading, marked as the agent's,
    its subtitle, the script's, unmarked, its summary, `value`'s, step_change_content.json's, then,
    folded under it with how many rows it holds, a table, in small type, of
    its rows by step_change_rows(); with no `previous`, data.json's previous
    feedback, the heading, unmarked, and STEP_CHANGE_NOT_APPLICABLE alone, as
    there is nothing to compare."""
    if previous is None:
        return [f"## {STEP_CHANGE_HEADING}", "", STEP_CHANGE_NOT_APPLICABLE]
    rows = step_change_rows(value["rows"], observations, previous, folder)
    return [f"## {ai_marked(STEP_CHANGE_HEADING)}", "", STEP_CHANGE_SUBTITLE, "",
            value["summary"].strip(),
            *(["", f"<details><summary>{details_text(len(rows), ('change', 'changes'))}</summary>", "",
               *html_table(observation_heads(((ai_marked("Previous feedback point"), 35),
                                              (ai_marked("Change"), 15), (ai_marked("Evidence"), 50))),
                           *rows, small=True), "", "</details>"] if rows else [])]


def step_change_rows(rows, observations, previous, folder):
    """The step change table's rows, each of `rows`, step_change_content.json's: the point of
    `previous` it names, after its part, such as "To improve: …", or – for
    none; its change's label; and each period point it cites, by its id in
    `observations`, data.json's, its text, source and references as its own
    row gives them, or, citing none, NOT_RAISED. Ordered
    by change, in the order of STEP_CHANGES, then by the previous point's order,
    those with none last, in the order given."""
    point_field, change_field, _ = STEP_CHANGE_ROW
    points, period = baseline_points(previous), period_points(observations)
    order = [*points, None]
    ordered = sorted(rows, key=lambda row: (list(STEP_CHANGES).index(row[change_field]),
                                            order.index(row[point_field])))

    def cited(point):
        # A feedback has no reference: its source alone says where it is from.
        source = OBSERVATION_SOURCES[point["source"]]
        if point["evidence"]:
            source += f": {reference(point, folder)}"
        return f'{esc(point["point"])} ({source})'
    return [f'<td>{esc(point_label(*points[row[point_field]])) if row[point_field] else "–"}</td>'
            f'<td>{STEP_CHANGES[row[change_field]]}</td>'
            f'<td>{"<br>".join(cited(period[item][1]) for item in row["evidence"]) or NOT_RAISED}</td>'
            for row in ordered]


def point_label(part, point):
    """A point of the previous feedback as the step change table names it, after its
    part: "To improve: Could lead a design review alone"."""
    return f'{OBSERVATION_HEADINGS[part]}: {point["point"]}'


def github_section(github):
    """The GitHub section's lines: a table of the pull requests opened, those
    merged and their size, the median lines a merged one changed, in the
    order of GITHUB_CELLS, as the Jira section's."""
    figures = {"opened": (HEADINGS["opened"], github["counts"]["opened"], repos_text(github["repo_counts"]["opened"]),
                          "Pull requests opened over time"),
               "merged": (HEADINGS["merged"], github["counts"]["merged"], repos_text(github["repo_counts"]["merged"]),
                          "Pull requests merged over time"),
               "merged_lines": (HEADINGS["merged_lines"], github["merged_lines"]["median"] or 0,
                                size_text(
                                    github["merged_lines"]["median"], github["counts"]["merged"]),
                                "Size of the merged pull requests")}
    return cells_table(GITHUB_CELLS, figures, github)


def repos_section(github):
    """The GitHub main focus's lines: the chart of the merged pull requests
    by repository, and beside it, numbered, the repositories that hold most
    of them, each with its code, as the charts name it, and how many it
    holds, linked to the search of those pull requests."""
    entries = "".join(f'<li>{code + " " if (code := repo_code(entry["repo"], github["repo_order"])) else ""}'
                      f'<a href="{esc(github["repo_search_urls"][entry["repo"]])}">{esc(entry["repo"])}</a> '
                      f'({entry["prs"]})</li>' for entry in github["focus"])
    note = (f"the repositories with the most merged pull requests, which together hold at least "
            f"{round(FOCUS_SHARE * 100)}% of them")
    return focus_table(REPOS_CHART, "Merged pull requests by repository", note, entries)


def jira_section(jira):
    """The Jira section's lines: a table of the issues created, the issues
    resolved and their story points, in the order of JIRA_CELLS, as
    cells_table() lays it out."""
    points = jira["resolved_points"]
    figures = {"created": (HEADINGS["created"], jira["counts"]["created"], types_text(jira["created_by_type"]),
                           "Issues created over time"),
               "resolved": (HEADINGS["resolved"], jira["counts"]["resolved"], types_text(jira["resolved_by_type"]),
                            "Issues resolved over time"),
               "resolved_points": (HEADINGS["resolved_points"], points["total"], average_text(points["average"]),
                                   "Story points of the resolved issues")}
    return cells_table(JIRA_CELLS, figures, jira)


def focus_section(jira):
    """The main focus's lines: the chart of the resolved issues by epic, and
    beside it, numbered, the epics, and the issues with no epic, that hold
    most of them, each with its title and how many it holds, linked to the
    search of those issues."""
    entries = "".join(f'<li><a href="{esc(jira["epic_search_urls"][entry["key"]])}">{esc(entry["key"])}</a> '
                      f'{esc(entry["title"] or "")} ({entry["issues"]})</li>' if entry["url"] else
                      f'<li><a href="{esc(jira["no_epic_search_url"])}">no epic</a> ({entry["issues"]})</li>'
                      if entry["key"] is None else f'<li>{esc(entry["key"])} ({entry["issues"]})</li>'
                      for entry in jira["focus"])
    note = (f"the epics with the most resolved issues, the issues with no epic counted as one, which together "
            f"hold at least {round(FOCUS_SHARE * 100)}% of them" if any(entry["url"] for entry in jira["focus"])
            else f"no resolved issue has an epic: the projects with the most of them, which together hold at least "
            f"{round(FOCUS_SHARE * 100)}% of them")
    return focus_table(EPICS_CHART, "Resolved issues by epic", note, entries)


def notion_section(notion):
    """The Notion section's lines: how many pages were created, then a table
    of them, in small type, by their calendar week, the most recent first, each week named once beside its pages, each page
    linked, with its area. Notion gives no search to link the count to."""
    weeks = {}
    for page in reversed(notion["created"]):
        weeks.setdefault(week_text(page["week"]), []).append(page)
    rows = grouped_rows((week, [f'<td><a href="{esc(page["url"])}">{esc(page["title"])}</a></td>'
                                f'<td>{esc(page["space"] or "")}</td>' for page in pages])
                        for week, pages in weeks.items())
    heads = "".join(
        f"<th>{head}</th>" for head in ("Week", "Page", "Area"))
    return [f'<b>{PAGES_HEADING}</b> ({notion["counts"]["created"]})', "", *html_table(heads, *rows, small=True)]


# Shared by the sections.

def cells_table(cells, figures, facts):
    """A source's table of `cells`, (name, chart): a row of headings, a row
    of figures, each of `figures`, by name, (heading, value, what it is
    made of, its chart's description), linked to its search in `facts`, then
    a row of their charts, so the charts line up however the figures wrap.
    It is HTML, as Markdown can't give columns one width."""
    width = f"{100 // len(cells)}%"
    heads = "".join(
        f'<th width="{width}">{figures[name][0]}</th>' for name, _ in cells)
    values = "".join(f"<td>{figure(figures[name][1], facts[f'{name}_search_url'])} ({esc(figures[name][2])})</td>"
                     for name, _ in cells)
    charts = "".join(
        f"<td>{image(chart, figures[name][3])}</td>" for name, chart in cells)
    return html_table(heads, values, charts)


def figure(value, url):
    """`value` as the report writes it, linked to `url` unless it is null."""
    return f'<a href="{esc(url)}">{number(value)}</a>' if url else number(value)


def focus_table(chart, description, note, entries):
    """A main focus's lines: `chart`, described as `description`, and beside
    it the main focus, with its `note`, its `entries` numbered."""
    return html_table(f'<td width="50%">{image(chart, description)}</td>'
                      f'<td width="50%"><b>Main focus</b> ({note}):<ol>{entries}</ol></td>')


def image(chart, description):
    """The chart `chart` of CHARTS_DIR, described as `description`, as
    chart_image() places it."""
    return chart_image(f"{CHARTS_DIR}/{chart}", description)


def grouped_rows(groups):
    """A grouped table's rows, each group (name, rows), its name written as
    HTML and each row its cells: the name in a cell beside the group's first
    row, spanning all of them."""
    return [(f'<td rowspan="{len(rows)}">{name}</td>' if index == 0 else "") + cells
            for name, rows in groups for index, cells in enumerate(rows)]
