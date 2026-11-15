"""Writes a prep's report, <Person>_Review_Prep.md, from data.json: for now, the person's Jira and GitHub figures.

Every figure is one of data.json's facts, and every link one of its search
addresses, so the report can't count differently from the model; the charts
it shows are make_charts.py's.
"""
from common import (CHARTS_DIR, EPICS_CHART, FOCUS_SHARE, FOLDER_NAME, GITHUB_CELLS, HEADINGS, JIRA_CELLS, REPOS_CHART,
                    average_text, esc, number, report_name, repo_code, repos_text, shown, size_text, types_text,
                    write_output_file)


def write_report(prep, person, data):
    """Write the prep `prep`'s report from `person`, its person.json, and
    `data`, its data.json; returns its path."""
    path, _ = write_output_file(
        FOLDER_NAME, f"{prep}/{report_name(prep)}", render(person, data).encode("utf-8"))
    return path


# The report.

def render(person, data):
    """The report's text: the person and the period, then their Jira work and
    their GitHub work, each its main focus, then its figures."""
    return "\n".join([f"# {person['person']}: performance review prep", "",
                      f"Period: {shown(person['start'], person['end'])}", "", "## Jira", "",
                      *focus_section(data["jira"]), "", *
                      jira_section(data["jira"]), "", "## GitHub", "",
                      *repos_section(data["github"]), "", *github_section(data["github"])]) + "\n"


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


def table(*rows):
    """A report table's lines: the full width, each of `rows`, its cells
    already written, aligned to the top, as HTML centres them by default."""
    return ['<table width="100%">', *(f'<tr valign="top">{cells}</tr>' for cells in rows), "</table>"]


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
