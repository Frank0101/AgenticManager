"""Writes a prep's report, <Person>_Review_Prep.md, and its charts from data.json, then checks them: for now, the person's Jira figures.

Every figure is one of data.json's facts, and every link one of its search
addresses, so the report can't count differently from the model; the charts
are make_charts.py's.
"""
import argparse
import json
import os

from check_report import report_problems
from common import (CHARTS_DIR, FOCUS_SHARE, JIRA_CELLS, EPICS_CHART, DATA, FOLDER_NAME, PERSON, average_text, esc,
                    number, prep_dir, read_json, report_name, shown, stops_on_failure, types_text, write_output_file)
from make_charts import draw


def make_report(prep):
    """Write the prep `prep`'s report and its charts from data.json, then
    check them; returns {report, problems}, the report's path and what the
    check found."""
    folder = prep_dir(prep)
    person = read_json(os.path.join(folder, PERSON))
    data = read_json(os.path.join(folder, DATA))
    for name, content in draw(data).items():
        write_output_file(
            FOLDER_NAME, f"{prep}/{CHARTS_DIR}/{name}", content.encode("utf-8"))
    report = render(person, data)
    path, _ = write_output_file(
        FOLDER_NAME, f"{prep}/{report_name(prep)}", report.encode("utf-8"))
    return {"report": path, "problems": report_problems(report, data, os.listdir(os.path.join(folder, CHARTS_DIR)))}


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
    return ['<table width="100%">', f"<tr>{heads}</tr>", f"<tr>{values}</tr>", f"<tr>{charts}</tr>",
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
            f"<td width=\"50%\" valign=\"top\"><b>Main focus</b> ({note}):<ol>{entries}</ol></td></tr>",
            "</table>"]


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Write the prep's report, <Person>_Review_Prep.md, and its charts from data.json, then check them.",
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
