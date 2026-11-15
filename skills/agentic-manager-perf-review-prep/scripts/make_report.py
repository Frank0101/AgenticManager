"""Writes a prep's report, <Person>_Review_Prep.md, from data.json: for now, the person's Jira figures.

Every figure is one of data.json's facts, and every link one of its search
addresses, so the report can't count differently from the model; the charts
it shows are make_charts.py's.
"""
from common import (CHARTS_DIR, EPICS_CHART, FOCUS_SHARE, FOLDER_NAME, JIRA_CELLS, average_text, esc, number,
                    report_name, shown, types_text, write_output_file)


def write_report(prep, person, data):
    """Write the prep `prep`'s report from `person`, its person.json, and
    `data`, its data.json; returns its path."""
    path, _ = write_output_file(
        FOLDER_NAME, f"{prep}/{report_name(prep)}", render(person, data).encode("utf-8"))
    return path


# The report.

def render(person, data):
    """The report's text: the person and the period, then their Jira work:
    the main focus, then the figures."""
    return "\n".join([f"# {person['person']}: performance review prep", "",
                      f"Period: {shown(person['start'], person['end'])}", "", "## Jira", "",
                      *focus_section(data["jira"]), "", *jira_section(data["jira"])]) + "\n"


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
    beside it, numbered, the epics that hold most of them, each with its
    title and how many it holds, linked to the search of those issues."""
    entries = "".join(f'<li><a href="{esc(jira["epic_search_urls"][entry["key"]])}">{esc(entry["key"])}</a> '
                      f'{esc(entry["title"] or "")} ({entry["issues"]})</li>' if entry["url"] else
                      f'<li>{esc(entry["key"])} ({entry["issues"]})</li>' for entry in jira["focus"])
    note = (f"the epics with the most resolved issues, which together hold at least "
            f"{round(FOCUS_SHARE * 100)}% of the issues that have an epic" if any(entry["url"] for entry in jira["focus"])
            else f"no resolved issue has an epic: the projects with the most of them, which together hold at least "
            f"{round(FOCUS_SHARE * 100)}% of them")
    return table(f'<td width="50%"><img src="{CHARTS_DIR}/{EPICS_CHART}" width="100%" alt="Resolved issues by epic">'
                 f'</td><td width="50%"><b>Main focus</b> ({note}):<ol>{entries}</ol></td>')
