"""Checks a prep's report against data.json: that it shows every GitHub and Jira figure, each main focus, the charts' series and the Notion pages created as the items give them, and holds only its charts.

It reads each figure back from the report and works it out again from the
items, apart from data.json's facts and from make_report.py, with which it
shares only the report's constants and how a figure is written, in common.py:
so a bug in the model or in the report can't pass by agreeing with itself.
"""
from datetime import date, timedelta
import html
import re

from common import (BINS_PER_DECADE, CHART_FILES, CHARTS_DIR, FOCUS_SHARE, GITHUB_CELLS, JIRA_CELLS, MAX_GROUPS, PAGES_HEADING,
                    average_text, project_of, repo_code, repos_text, size_text, types_text, week_text)

# Where the Jira section starts, after the GitHub one, and the Notion one
# after it.
JIRA_HEADING, NOTION_HEADING = "\n## Jira\n", "\n## Notion\n"
# The Notion section's count of the pages created, and each page's row: its
# week's cell, on the first row of the week only, with how many rows it
# spans, then its link and title, and its area.
PAGES_COUNT = re.compile(rf"<b>{re.escape(PAGES_HEADING)}</b> \((\d+)\)")
PAGE_ROW = re.compile(r'<tr valign="top">(?:<td rowspan="(\d+)"><small><small>([^<]*)</small></small></td>)?'
                      r'<td><small><small><a href="([^"]+)">([^<]*)</a></small></small></td>'
                      r'<td><small><small>([^<]*)</small></small></td></tr>')
# A Jira main focus entry as the report writes it: its epic's link, key and
# title, or the link of the issues with no epic, or a project's key alone,
# and how many resolved issues it holds. The title holds no tag, so it can't
# run on into the next entry.
FOCUS_ENTRY = re.compile(
    r'<li>(?:<a href="([^"]+)">([^<]+)</a>(?: ([^<]*?))?|([^<]+?)) \((\d+)\)</li>')
# A GitHub main focus entry: its repository's code, when it has one, link and
# name, and how many merged pull requests it holds.
REPO_ENTRY = re.compile(
    r'<li>(?:([A-Z]) )?<a href="([^"]+)">([^<]+)</a> \((\d+)\)</li>')
# A figure's cell and a chart's, as the report writes them.
FIGURE = re.compile(
    r'<td>(?:<a href="([^"]+)">([\d.]+)</a>|([\d.]+)) \((.*?)\)</td>')
CHART = re.compile(
    rf'<td><a href="{CHARTS_DIR}/([^"]+)" target="_blank"><img src="{CHARTS_DIR}/\1"')


def report_problems(report, data, charts):
    """Why `report`, the report's text, doesn't show `data`, data.json, or
    `charts`, the files in the charts folder, those starting with a dot
    aside, aren't its charts, empty when they are: each count, total, average
    and median, each breakdown and each link to its search, each main focus,
    the series the charts draw, and the Notion pages created."""
    charts = [name for name in charts if not name.startswith(".")]
    problems = [] if sorted(charts) == sorted(CHART_FILES) else [
        f"the charts folder must hold only {', '.join(CHART_FILES)}: run finish_report.py again"]
    if "\n## GitHub\n" not in report.split(JIRA_HEADING, 1)[0] or JIRA_HEADING not in report or \
            NOTION_HEADING not in report.split(JIRA_HEADING, 1)[1]:
        return problems + ["the report must have its GitHub section, then its Jira one, then its Notion one: run "
                           "finish_report.py again"]
    github_text, rest = report.split(JIRA_HEADING, 1)
    jira_text, notion_text = rest.split(NOTION_HEADING, 1)
    return problems + _jira_problems(jira_text, data["jira"], data["weeks"]) + \
        _github_problems(github_text, data["github"], data["weeks"]) + \
        _notion_problems(
            notion_text, data["notion"], (data["weeks"][0][0], data["weeks"][-1][1]))


# Jira.

def _jira_problems(text, jira, weeks):
    """Why `text`, the report's Jira section, doesn't show `jira`, data.json's,
    or its series don't count its issues over `weeks`, empty when they do."""
    estimated = [issue["points"]
                 for issue in jira["resolved"] if issue["points"] is not None]
    total = round(sum(estimated), 1)
    expected = {"resolved": (len(jira["resolved"]), types_text(_types(jira["resolved"]))),
                "resolved_points": (total, average_text(round(total / len(estimated), 1) if estimated else None)),
                "created": (len(jira["created"]), types_text(_types(jira["created"])))}
    problems = _series_problems(
        jira, weeks) + _cells_problems(text, "Jira", JIRA_CELLS, expected, jira)
    shown = [(html.unescape(url) or None, html.unescape(key or project), html.unescape(title) or None, int(n))
             for url, key, title, project, n in FOCUS_ENTRY.findall(text)]
    focus = _focus(jira["resolved"], {
                   **jira["epic_search_urls"], "no epic": jira["no_epic_search_url"]})
    if shown != focus:
        problems.append("the report's Jira main focus doesn't show the epics, or projects, of the resolved issues: "
                        "run finish_report.py again")
    if [entry["share"] for entry in jira["focus"]] != _shares([n for *_, n in focus], len(jira["resolved"])):
        problems.append(
            "the shares the Jira pie shows aren't the main focus's: run build_data.py again")
    return problems


def _series_problems(jira, weeks):
    """Why the series the charts draw, in `jira`, data.json's, don't count
    its issues, worked out again from them over `weeks`, empty when they do:
    the epics coloured, each week's created and resolved issues, in all, by
    epic, of other epics and with none, the resolved issues by epic, those
    with none ranked as one more, and by story points and epic."""
    def epic(issue):
        return issue["epic"]["key"] if issue["epic"] else None
    resolved = _counts(jira["resolved"], epic)
    order = _order(resolved, {epic(issue)
                   for issue in jira["created"]} - {None})
    problems = [] if jira["epic_order"] == order else [
        "the epics the charts colour aren't those with the most resolved issues: run build_data.py again"]
    for name in ("created", "resolved"):
        counts = _weekly(jira[name], weeks, epic, order)
        series = jira[f"{name}_by_week"]
        if (series["total"], dict(series["epics"]), series["other"], series["no_epic"]) != counts:
            problems.append(
                f"the chart of the issues {name} doesn't count them week by week: run build_data.py again")
    pie = jira["resolved_by_epic"]
    shown, other, none = _split(resolved, order, sum(
        1 for issue in jira["resolved"] if not issue["epic"]))
    slices: list[tuple[str | None, int]] = [
        *shown.items(), *([(None, none)] if none else [])]
    slices.sort(key=lambda pair: (-pair[1], pair[0] is None, pair[0] or ""))
    if ([(entry["key"], entry["issues"]) for entry in pie["epics"]], pie["other"]) != (slices, other):
        problems.append(
            "the chart of the resolved issues by epic doesn't count them: run build_data.py again")
    estimated = [issue for issue in jira["resolved"]
                 if issue["points"] is not None]
    stacks = {value: (len(at), *_split(_counts(at, epic), order, sum(1 for issue in at if not issue["epic"])))
              for value in {issue["points"] for issue in estimated}
              for at in [[issue for issue in estimated if issue["points"] == value]]}
    shown = {row["points"]: (row["issues"], dict(row["epics"]), row["other"], row["no_epic"])
             for row in jira["points_by_epic"]}
    if shown != stacks or [row["points"] for row in jira["points_by_epic"]] != sorted(stacks):
        problems.append(
            "the chart of the story points doesn't count the resolved issues: run build_data.py again")
    return problems


def _focus(resolved, urls):
    """[(url, key, title, issues)]: the main focus of the issues `resolved`
    as the report lists it, worked out apart from focus(): the epics, those
    with no epic as one more, "no epic", holding the most of them, until
    FOCUS_SHARE of them, every one tied with the last one too, each linked to
    its search in `urls`; or, when none has an epic, their projects the same
    way, with no link or title."""
    titles = {issue["epic"]["key"]: issue["epic"]["title"]
              for issue in resolved if issue["epic"]}
    counts = _counts(
        resolved, lambda issue: issue["epic"]["key"] if issue["epic"] else "no epic")
    if not titles:
        counts = _counts(resolved, lambda issue: project_of(issue["key"]))
    # The issues with no epic come after the epics they tie with.
    ranked = sorted(_covered(counts),
                    key=lambda key: (-counts[key], key == "no epic", key))
    return [(urls.get(key) if titles else None, key, titles.get(key) or None, counts[key]) for key in ranked]


def _types(issues):
    """[{type, issues}]: how many of `issues` there are of each type, most
    first, then by type, worked out apart from by_type()."""
    types = _counts(issues, lambda issue: issue["type"])
    return [{"type": kind, "issues": types[kind]} for kind in _ranked(types)]


# GitHub.

def _github_problems(text, github, weeks):
    """Why `text`, the report's GitHub section, doesn't show `github`,
    data.json's, or its series don't count its pull requests over `weeks`,
    empty when they do."""
    merged, opened = github["merged"], github["opened"]
    changed = sorted(pr["lines"] for pr in merged)
    middle = len(changed) // 2
    median = (changed[middle] if len(changed) % 2 else (changed[middle - 1] + changed[middle]) / 2) if changed \
        else None
    expected = {"opened": (len(opened), repos_text(len({pr["repo"] for pr in opened}))),
                "merged": (len(merged), repos_text(len({pr["repo"] for pr in merged}))),
                "merged_lines": (median or 0, size_text(median, len(merged)))}
    counts = _counts(merged, lambda pr: pr["repo"])
    order = _order(counts, {pr["repo"] for pr in opened})
    problems = _pulls_problems(github, weeks, counts, order) + _cells_problems(
        text, "GitHub", GITHUB_CELLS, expected, github)
    shown = [(code or None, html.unescape(url), html.unescape(repo), int(n))
             for code, url, repo, n in REPO_ENTRY.findall(text)]
    if shown != [(repo_code(repo, order), github["repo_search_urls"].get(repo), repo, counts[repo])
                 for repo in _covered(counts)]:
        problems.append("the report's GitHub main focus doesn't show the repositories of the merged pull requests: "
                        "run finish_report.py again")
    if [entry["share"] for entry in github["focus"]] != _shares([counts[repo] for repo in _covered(counts)],
                                                                len(merged)):
        problems.append(
            "the shares the GitHub pie shows aren't the main focus's: run build_data.py again")
    return problems


def _pulls_problems(github, weeks, merged, order):
    """Why the series the charts draw, in `github`, data.json's, don't count
    its pull requests, worked out again from them over `weeks`, with
    `merged`, how many merged ones each repository holds, and `order`, the
    repositories to colour, empty when they do: the repositories coloured,
    each week's opened and merged pull requests, in all, by repository and of
    other repositories, the merged ones by repository, and their sizes'
    distribution by repository."""
    def repo(pr):
        return pr["repo"]
    problems = [] if github["repo_order"] == order else [
        "the repositories the charts colour aren't those with the most merged pull requests: run build_data.py "
        "again"]
    for name in ("opened", "merged"):
        series = github[f"{name}_by_week"]
        if (series["total"], dict(series["repos"]), series["other"]) != _weekly(github[name], weeks, repo, order)[:3]:
            problems.append(
                f"the chart of the pull requests {name} doesn't count them week by week: run build_data.py again")
    pie = github["merged_by_repo"]
    if ({entry["repo"]: entry["prs"] for entry in pie["repos"]}, pie["other"]) != _split(merged, order, 0)[:2]:
        problems.append(
            "the chart of the merged pull requests by repository doesn't count them: run build_data.py again")
    sizes = [pr["lines"] for pr in github["merged"]]
    bins = BINS_PER_DECADE * \
        len(str(max([size for size in sizes if size >= 1], default=1)))

    def counts(prs):
        found = [0] * bins
        for pr in prs:
            found[sum(1 for edge in range(1, bins) if pr["lines"]
                      >= 10 ** (edge / BINS_PER_DECADE))] += 1
        return found
    series = github["lines_distribution"]
    expected = (counts(github["merged"]), {repo: counts([pr for pr in github["merged"] if pr["repo"] == repo])
                                           for repo in order if repo in merged},
                counts([pr for pr in github["merged"] if pr["repo"] not in order]))
    if (series["total"], dict(series["repos"]), series["other"]) != expected:
        problems.append(
            "the chart of the merged pull requests' size doesn't count them: run build_data.py again")
    return problems


# Notion.

def _notion_problems(text, notion, period):
    """Why `text`, the report's Notion section, doesn't show the pages
    `notion`, data.json's, created, the most recent week first, each week
    named once beside its pages, worked out again from the day its search
    began, clipped to `period`, each with its area worked out again from its
    path, empty when it does."""
    pages = notion["created"]

    def space(page):
        return page["path"].split(" / ")[0] or None

    def week_of(page):
        day = date.fromisoformat(page["between"][0])
        monday, sunday = day - \
            timedelta(days=day.weekday()), day + \
            timedelta(days=6 - day.weekday())
        return week_text([max(monday.isoformat(), period[0]), min(sunday.isoformat(), period[1])])
    problems = []
    count = PAGES_COUNT.search(text)
    shown, week, spans = [], None, []
    for span, named, url, title, area in PAGE_ROW.findall(text):
        if named:
            week = named
            spans.append(int(span))
        shown.append((week, html.unescape(url),
                     html.unescape(title), html.unescape(area)))
    newest = sorted(pages, key=lambda page: (
        page["between"][0], page["url"]), reverse=True)
    expected = [(week_of(page), page["url"],
                 page["title"], space(page) or "") for page in newest]
    if not count or int(count[1]) != len(pages) or shown != expected or spans != [
            sum(1 for row in expected if row[0] == named) for named in dict.fromkeys(row[0] for row in expected)]:
        problems.append(
            "the report's Notion pages don't show data.json's: run finish_report.py again")
    return problems


# Shared.

def _cells_problems(text, source, cells, expected, facts):
    """Why `text`, a source's section, doesn't show its table of `cells`, each
    figure and what it is made of as `expected`, by name, and linked to its
    search in `facts`, with its chart below, empty when it does."""
    figures, charts = FIGURE.findall(text), CHART.findall(text)
    if (len(figures), len(charts)) != (len(cells), len(cells)):
        return [f"the report's {source} table must have a row of three figures and one of their charts: "
                "run finish_report.py again"]
    return [f"the report's {source} cell for {name} doesn't show data.json: run finish_report.py again"
            for (name, chart), (url, linked, plain, made_of), shown in zip(cells, figures, charts)
            if (float(linked or plain), html.unescape(url) or None, html.unescape(made_of), shown) !=
            (expected[name][0], facts[f"{name}_search_url"], expected[name][1], chart)]


def _counts(items, group):
    """{key: how many}: how many of `items` each key `group` gives holds,
    those it gives none for left out."""
    counts = {}
    for item in items:
        if (key := group(item)) is not None:
            counts[key] = counts.get(key, 0) + 1
    return counts


def _ranked(counts):
    """The keys of `counts`, the most first, then by key."""
    return sorted(counts, key=lambda key: (-counts[key], key))


def _covered(counts):
    """The fewest keys of `counts`, the most first, holding FOCUS_SHARE of
    them all, every key tied with the last one too."""
    total, covered = sum(counts.values()), 0
    for key in _ranked(counts):
        covered += counts[key]
        if covered >= FOCUS_SHARE * total:
            return [other for other in _ranked(counts) if counts[other] >= counts[key]]
    return []


def _shares(counts, total):
    """Each of `counts` as a percentage of `total`, rounded."""
    return [round(100 * n / total) for n in counts]


def _order(counts, others):
    """The keys the charts colour: those of `counts`, ranked, then `others`,
    by key, at most MAX_GROUPS."""
    return (_ranked(counts) + sorted(set(others) - set(counts)))[:MAX_GROUPS]


def _split(counts, order, none) -> tuple[dict[str, int], int, int]:
    """({key: n}, other, `none`): `counts` of the keys of `order`, and of
    every other key together."""
    return ({key: n for key, n in counts.items() if key in order},
            sum(n for key, n in counts.items() if key not in order), none)


def _weekly(items, weeks, group, order):
    """(total, {key: series}, other, none): how many of `items` fall in each
    of `weeks`, by their day: in all, for each key of `order` `group` gives
    any of them, for every other key, and for none."""
    total, groups, other, none = [
        0] * len(weeks), {}, [0] * len(weeks), [0] * len(weeks)
    for item in items:
        index = next(n for n, (first, last) in enumerate(
            weeks) if first <= item["date"] <= last)
        total[index] += 1
        key = group(item)
        if key is None:
            none[index] += 1
        elif key in order:
            groups.setdefault(key, [0] * len(weeks))[index] += 1
        else:
            other[index] += 1
    return total, {key: groups[key] for key in order if key in groups}, other, none
