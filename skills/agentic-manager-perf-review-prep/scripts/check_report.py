"""Checks a prep's report against data.json: that it shows every Jira figure, the main focus and the charts' series as the issues give them, and holds only its charts.

It reads each figure back from the report and works it out again from the
issues, apart from data.json's facts and from make_report.py, with which it
shares only the report's constants and how a figure is written, in common.py:
so a bug in the model or in the report can't pass by agreeing with itself.
"""
import html
import re

from common import (CHART_FILES, CHARTS_DIR, FOCUS_SHARE,
                    JIRA_CELLS, average_text, types_text)

# A main focus entry as the report writes it: its epic's link and key, its
# title and how many resolved issues it holds.
FOCUS_ENTRY = re.compile(
    r'<li><a href="([^"]+)">([^<]+)</a> (.*?) \((\d+)\)</li>')
# A Jira figure's cell and a chart's, as the report writes them.
JIRA_FIGURE = re.compile(
    r'<td>(?:<a href="([^"]+)">([\d.]+)</a>|([\d.]+)) \((.*?)\)</td>')
JIRA_CHART = re.compile(rf'<td><img src="{CHARTS_DIR}/([^"]+)"')


def report_problems(report, data, charts):
    """Why `report`, the report's text, doesn't show `data`, data.json, or
    `charts`, the files in the charts folder, those starting with a dot
    aside, aren't its charts, empty when they are: each count, the story
    points' total and average, each breakdown by type and each link to its
    search, the main focus, and the series the charts draw."""
    charts = [name for name in charts if not name.startswith(".")]
    problems = [] if sorted(charts) == sorted(CHART_FILES) else [
        f"the charts folder must hold only {', '.join(CHART_FILES)}: run make_report.py again"]
    jira = data["jira"]
    problems += _series_problems(jira, data["weeks"])
    estimated = [issue["points"]
                 for issue in jira["resolved"] if issue["points"] is not None]
    total = round(sum(estimated), 1)
    expected = {"resolved": (len(jira["resolved"]), types_text(_types(jira["resolved"]))),
                "resolved_points": (total, average_text(round(total / len(estimated), 1) if estimated else None)),
                "created": (len(jira["created"]), types_text(_types(jira["created"])))}
    figures, charts_shown = JIRA_FIGURE.findall(
        report), JIRA_CHART.findall(report)
    if (len(figures), len(charts_shown)) != (len(JIRA_CELLS), len(JIRA_CELLS)):
        return problems + ["the report's Jira table must have a row of three figures and one of their charts: "
                           "run make_report.py again"]
    for (name, chart), (url, linked, plain, made_of), shown in zip(JIRA_CELLS, figures, charts_shown):
        if (float(linked or plain), html.unescape(url) or None, html.unescape(made_of), shown) != (
                expected[name][0], jira[f"{name}_search_url"], expected[name][1], chart):
            problems.append(
                f"the report's Jira cell for {name} doesn't show data.json: run make_report.py again")
    shown = [(html.unescape(url), html.unescape(key), html.unescape(title), int(n))
             for url, key, title, n in FOCUS_ENTRY.findall(report)]
    if shown != _focus(jira["resolved"], jira["epic_search_urls"]):
        problems.append("the report's main focus doesn't show the epics of the resolved issues: run make_report.py "
                        "again")
    return problems


def _series_problems(jira, weeks):
    """Why the series the charts draw, in `jira`, data.json's, don't count
    its issues, worked out again from them over `weeks`, empty when they do:
    each week's created and resolved issues, in all, by epic and with none,
    and the resolved issues by story points and epic."""
    problems = []
    for name in ("created", "resolved"):
        counts = {"total": [0] * len(weeks),
                  "epics": {}, "no_epic": [0] * len(weeks)}
        for issue in jira[name]:
            index = next(n for n, (first, last) in enumerate(
                weeks) if first <= issue["date"] <= last)
            counts["total"][index] += 1
            if issue["epic"]:
                counts["epics"].setdefault(issue["epic"]["key"], [
                                           0] * len(weeks))[index] += 1
            else:
                counts["no_epic"][index] += 1
        series = jira[f"{name}_by_week"]
        if (series["total"], dict(series["epics"]), series["no_epic"]) != (counts["total"], counts["epics"],
                                                                           counts["no_epic"]):
            problems.append(
                f"the chart of the issues {name} doesn't count them week by week: run build_data.py again")
    stacks = {}
    for issue in jira["resolved"]:
        if issue["points"] is not None:
            row = stacks.setdefault(
                issue["points"], {"issues": 0, "epics": {}, "no_epic": 0})
            row["issues"] += 1
            if issue["epic"]:
                row["epics"][issue["epic"]["key"]] = row["epics"].get(
                    issue["epic"]["key"], 0) + 1
            else:
                row["no_epic"] += 1
    shown = {row["points"]: {"issues": row["issues"], "epics": dict(row["epics"]), "no_epic": row["no_epic"]}
             for row in jira["points_by_epic"]}
    if shown != stacks or [row["points"] for row in jira["points_by_epic"]] != sorted(stacks):
        problems.append(
            "the chart of the story points doesn't count the resolved issues: run build_data.py again")
    return problems


def _focus(resolved, urls):
    """[(url, key, title, issues)]: the main focus of the issues `resolved`
    as the report lists it, each linked to its search in `urls`, worked out
    apart from focus(): the epics holding the most of those with one, until
    FOCUS_SHARE of them, every epic tied with the last one too."""
    counts, epics = {}, {}
    for issue in resolved:
        if issue["epic"]:
            key = issue["epic"]["key"]
            counts[key] = counts.get(key, 0) + 1
            epics[key] = issue["epic"]
    ranked = sorted(counts, key=lambda key: (-counts[key], key))
    total, covered = sum(counts.values()), 0
    for key in ranked:
        covered += counts[key]
        if covered >= FOCUS_SHARE * total:
            ranked = [other for other in ranked if counts[other] >= counts[key]]
            break
    return [(urls.get(key), key, epics[key]["title"], counts[key]) for key in ranked]


def _types(issues):
    """[{type, issues}]: how many of `issues` there are of each type, most
    first, then by type, worked out apart from by_type()."""
    types = {}
    for issue in issues:
        types[issue["type"]] = types.get(issue["type"], 0) + 1
    return [{"type": kind, "issues": n} for kind, n in sorted(types.items(), key=lambda pair: (-pair[1], pair[0]))]
