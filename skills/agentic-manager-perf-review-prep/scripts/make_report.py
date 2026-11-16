"""Writes a prep's report, <Person>_Review_Prep.md, from data.json: for now, the person's GitHub, Jira and Notion figures, and the observations, by company value.

Every figure is one of data.json's facts, and every link one of its search
addresses, so the report can't count differently from the model; the charts
it shows are make_charts.py's.
"""
from common import (CHARTS_DIR, EPICS_CHART, OBSERVATION_HEADINGS, OBSERVATION_SOURCES, FOCUS_SHARE, FOLDER_NAME, GITHUB_CELLS, HEADINGS, JIRA_CELLS, NO_VALUE, PAGES_HEADING, REFERENCE_NAMES, REPOS_CHART,
                    SMALL_TYPE, ai_marked, average_text, day_text, details_text, esc, link_href, number, prep_dir, report_name, repo_code, repos_text, shown, size_text, types_text, week_text,
                    write_output_file)


def write_report(prep, person, data, content):
    """Write the prep `prep`'s report from `person`, its person.json, `data`,
    its data.json, and `content`, its content.json; returns its path."""
    path, _ = write_output_file(
        FOLDER_NAME, f"{prep}/{report_name(prep)}", render(person, data, prep_dir(prep), content).encode("utf-8"))
    return path


# The report.

def render(person, data, folder, content):
    """The report's text: the person and the period, then the Observations,
    what is going well and what to improve, first, as what the review is
    about, each summarised as `content`, content.json, says, a note it cites
    linked relative to `folder`, the report's, then
    their GitHub work and their Jira work, each its main focus,
    then its figures, then the Notion pages they created. GitHub comes before
    Jira: with agents writing much
    of the code, pull requests stay the plainest trace of what someone did,
    while tickets grow more generic."""
    return "\n".join([f"# {person['person']}: performance review prep", "",
                      f"Period: {shown(person['start'], person['end'])}", "", "## Observations", "",
                      *observations_section(data["observations"],
                                            folder, content), "", "## GitHub", "",
                      *repos_section(data["github"]), "", *
                      github_section(data["github"]), "", "## Jira", "",
                      *focus_section(data["jira"]), "", *
                      jira_section(data["jira"]), "", "## Notion", "",
                      *notion_section(data["notion"])]) + "\n"


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
    return table(heads, values, charts)


def table(*rows, small=False):
    """A report table's lines: the full width, each of `rows`, its cells
    already written, aligned to the top, as HTML centres them by default;
    with `small`, in SMALL_TYPE, for a table of many rows."""
    style = f' style="{SMALL_TYPE}"' if small else ""
    return [f'<table width="100%"{style}>', *(f'<tr valign="top">{cells}</tr>' for cells in rows), "</table>"]


def figure(value, url):
    """`value` as the report writes it, linked to `url` unless it is null."""
    return f'<a href="{esc(url)}">{number(value)}</a>' if url else number(value)


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
    return [f'<b>{PAGES_HEADING}</b> ({notion["counts"]["created"]})', "", *table(heads, *rows, small=True)]


def observations_section(observations, folder, content):
    """The Observations section's lines: for each part of OBSERVATION_HEADINGS,
    a divider apart from the one before, its heading, marked as the agent's, as
    its summary, `content`'s, follows, then, folded under it as the detail,
    with how many points it holds, a table of them, in small type, its columns
    as wide in both, so the two read alike, by company
    value, each value named once beside its points, the most recent first,
    each with its source and its reference: a piece's period, as the source
    names it, or the days of a reading's evidence, the most recent first,
    each linked to its note or message."""
    lines = []
    for part, heading in OBSERVATION_HEADINGS.items():
        groups = observations[part]
        rows = grouped_rows((esc(group["value"] or NO_VALUE),
                             [f'<td>{esc(point["also"] or "")}</td><td>{esc(point["point"])}</td>'
                              f'<td>{OBSERVATION_SOURCES[point["source"]]}</td>'
                              f'<td>{reference(point, folder)}</td>' for point in group["points"]])
                            for group in groups)
        heads = "".join(f'<th width="{width}%">{head}</th>' for head, width in (
            ("Value", 10), ("Also", 10), (ai_marked("Point"), 50), ("Source", 10), ("References", 20)))
        count = sum(len(group["points"]) for group in groups)
        lines += [*(["", "---", ""] if lines else []), ai_marked(f"<b>{heading}</b>") if rows else f"<b>{heading}</b>",
                  *(["", content[part].strip(), "", f"<details><summary>{details_text(count)}</summary>", "",
                     *table(heads, *rows, small=True), "", "</details>"] if rows else [])]
    return lines


def reference(point, folder):
    """Where an observation comes from, as its row writes it: its piece's
    period, – when the piece names none, or its evidence, each its source
    and day, such as "Slack 14 Oct", linked to its message or note."""
    if point["source"] == "feedback":
        return esc(point["period"] or "–")
    return ", ".join(f'<a href="{esc(link_href(item["link"], folder))}">{REFERENCE_NAMES[point["source"]]} {day_text(item["date"])}</a>'
                     for item in point["evidence"])


def grouped_rows(groups):
    """A grouped table's rows, each group (name, rows), its name written as
    HTML and each row its cells: the name in a cell beside the group's first
    row, spanning all of them."""
    return [(f'<td rowspan="{len(rows)}">{name}</td>' if index == 0 else "") + cells
            for name, rows in groups for index, cells in enumerate(rows)]


def focus_table(chart, description, note, entries):
    """A main focus's lines: `chart`, described as `description`, and beside
    it the main focus, with its `note`, its `entries` numbered."""
    return table(f'<td width="50%">{image(chart, description)}</td>'
                 f'<td width="50%"><b>Main focus</b> ({note}):<ol>{entries}</ol></td>')


def image(chart, description):
    """The chart `chart`, described as `description`, as wide as its cell
    and linked to itself, so a click opens it full size in a new tab."""
    return (f'<a href="{CHARTS_DIR}/{chart}" target="_blank"><img src="{CHARTS_DIR}/{chart}" width="100%" '
            f'alt="{description}"></a>')
