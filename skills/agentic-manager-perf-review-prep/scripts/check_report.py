"""Checks a prep's report against data.json: that it shows every GitHub and Jira figure, each main focus, the charts' series and the Notion pages created as the items give them, the observations' points, going well, to improve and context, as the summaries give them, each table under content.json's summary of it, then the step change, step_change.json's, as it reads against the previous reviews and the period's points, and the view check, view_check.json's, as it reads against the manager's view.

It reads each figure back from the report and works it out again from the
items, apart from data.json's facts and from make_report.py, with which it
shares only the report's constants and how a figure is written, in common.py:
so a bug in the model or in the report can't pass by agreeing with itself.
"""
from collections import Counter
from datetime import date, timedelta
import html
import re

from common import (BINS_PER_DECADE, CHARTS_DIR, OBSERVATION_HEADINGS, OBSERVATIONS_SUBTITLE, OBSERVATION_SOURCES, FOCUS_SHARE, GITHUB_CELLS, JIRA_CELLS, MAX_GROUPS, NO_VALUE,
                    PAGES_HEADING, REVIEW_ID, STEP_CHANGE_COMPARISON, SUMMARY_PARTS, VALUED_PARTS, VIEW_CHECK_COMPARISON, VIEW_ID, ai_marked, average_text, details_text, display_date, link_href, point_id, reference_text, project_of, repo_code, repos_text, size_text, step_change_problems, types_text,
                    view_check_problems, week_text)

# The report's sections, in order, each where its heading starts it, the
# heading marked as the agent's when the agent wrote its text, as the step
# change's is when there is a previous review, and the view check's always.
COMPARISONS = (STEP_CHANGE_COMPARISON, VIEW_CHECK_COMPARISON)
SECTION_HEADINGS = ("Observations", *(comparison.heading for comparison in COMPARISONS),
                    "GitHub", "Jira", "Notion")
SECTION = re.compile(
    rf"\n## ({'|'.join(map(re.escape, SECTION_HEADINGS))})({re.escape(ai_marked(''))})?\n")
# The start of a row of a table grouped as the Notion pages and the Observations
# points are: its group's cell, on the group's first row only, with how many
# rows it spans and the group's name.
GROUP_CELL = r'<tr valign="top">(?:<td rowspan="(\d+)">([^<]*)</td>)?'
# The Notion section's count of the pages created, and each page's row: its
# week's cell, then its link and title, and its area.
PAGES_COUNT = re.compile(rf"<b>{re.escape(PAGES_HEADING)}</b> \((\d+)\)")
PAGE_ROW = re.compile(GROUP_CELL + r'<td><a href="([^"]+)">([^<]*)</a></td>'
                      r'<td>([^<]*)</td></tr>')
# An Observations part: its heading and what follows it, up
# to the next part; and each valued point's row: its value's cell, then the
# second value it names, its text, its source and its reference.
OBSERVATION_PART = re.compile(r"<b>([^<]+)</b>((?:(?!<b>).)*)", re.S)
DETAILS = re.compile(r"<details><summary>([^<]*)</summary>")
OBSERVATION_ROW = re.compile(GROUP_CELL + r'<td>([^<]*)</td><td>([^<]*)</td><td>([^<]*)</td>'
                             r'<td>(.*?)</td></tr>')
# A context point's row, not grouped: its text, its source and its reference;
# a comparison's row is read the same way: its baseline point, its kind and
# its evidence, each cited point's text, then its source and reference in
# brackets, one to a line.
CONTEXT_ROW = re.compile(
    r'<tr valign="top"><td>([^<]*)</td><td>([^<]*)</td><td>(.*?)</td></tr>')
CITED = re.compile(
    rf"(.*) \(({'|'.join(map(re.escape, OBSERVATION_SOURCES.values()))}): (.*)\)", re.S)
LINK = re.compile(r'<a href="([^"]+)">([^<]*)</a>')
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


def report_problems(report, data, summaries, values, folder, content, step_change, view_check):
    """Why `report`, the report's text, doesn't show `data`, data.json, and
    `summaries`, the manager's view, the feedback's pieces, the notes'
    summary and Slack's, by SUMMARY_FILES' names, the reviews among them,
    with `values`, the company's, empty when it does:
    each count, total, average and median, each
    breakdown and each link to its search, each main focus, the series the
    charts draw, the Notion pages created and the observations' points, a note's
    link relative to `folder`, the report's, each table under its summary in
    `content`, content.json, the step change, `step_change`,
    step_change.json, and the view check, `view_check`, view_check.json."""
    sections = SECTION.split(report)
    if tuple(sections[1::3]) != SECTION_HEADINGS:
        return ["the report must have its Observations section, then its Step change one, its Manager view check "
                "one, its GitHub one, its Jira one and its Notion one: run finish_report.py again"]
    observations_text, step_text, view_text, github_text, jira_text, notion_text = sections[
        3::3]
    step_marked, view_marked = (
        mark is not None for mark in sections[2::3][1:3])
    span = (data["weeks"][0][0], data["weeks"][-1][1])
    problems = _jira_problems(jira_text, data["jira"], data["weeks"]) + \
        _github_problems(github_text, data["github"], data["weeks"]) + \
        _notion_problems(notion_text, data["notion"], span)
    if _subtitle(observations_text) != OBSERVATIONS_SUBTITLE:
        problems.append(f"the report's Observations must start with its subtitle, {OBSERVATIONS_SUBTITLE}: run "
                        "finish_report.py again")
    observed, cited = _observations_problems(
        observations_text, summaries, values, folder, content, span)
    if observed:
        return problems + observed
    # Each baseline worked out again from the summaries: the latest review
    # before the period, the first by date, undated first, and the view.
    previous = sorted((piece for piece in summaries["reviews"]["pieces"]
                       if not piece["date"] or piece["date"] < span[0]),
                      key=lambda piece: piece["date"] or "~", reverse=True)
    view = summaries["orientation"]
    return problems + _comparison_problems(
        STEP_CHANGE_COMPARISON, (step_text, step_marked), _baseline_labels(
            previous[0], REVIEW_ID) if previous else None,
        cited, step_change, step_change_problems(
            step_change, data["observations"], data["reviews"]),
        _review_name(previous[0]) if previous else "") + \
        _comparison_problems(
            VIEW_CHECK_COMPARISON, (view_text, view_marked), _baseline_labels(view, VIEW_ID), cited, view_check, view_check_problems(view_check, data["observations"], data["view"]), "")


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
            "the shares the Jira pie shows aren't the main focus's: run prepare_report.py again")
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
        "the epics the charts colour aren't those with the most resolved issues: run prepare_report.py again"]
    for name in ("created", "resolved"):
        counts = _weekly(jira[name], weeks, epic, order)
        series = jira[f"{name}_by_week"]
        if (series["total"], dict(series["epics"]), series["other"], series["no_epic"]) != counts:
            problems.append(
                f"the chart of the issues {name} doesn't count them week by week: run prepare_report.py again")
    pie = jira["resolved_by_epic"]
    shown, other, none = _split(resolved, order, sum(
        1 for issue in jira["resolved"] if not issue["epic"]))
    slices: list[tuple[str | None, int]] = [
        *shown.items(), *([(None, none)] if none else [])]
    slices.sort(key=lambda pair: (-pair[1], pair[0] is None, pair[0] or ""))
    if ([(entry["key"], entry["issues"]) for entry in pie["epics"]], pie["other"]) != (slices, other):
        problems.append(
            "the chart of the resolved issues by epic doesn't count them: run prepare_report.py again")
    estimated = [issue for issue in jira["resolved"]
                 if issue["points"] is not None]
    stacks = {value: (len(at), *_split(_counts(at, epic), order, sum(1 for issue in at if not issue["epic"])))
              for value in {issue["points"] for issue in estimated}
              for at in [[issue for issue in estimated if issue["points"] == value]]}
    shown = {row["points"]: (row["issues"], dict(row["epics"]), row["other"], row["no_epic"])
             for row in jira["points_by_epic"]}
    if shown != stacks or [row["points"] for row in jira["points_by_epic"]] != sorted(stacks):
        problems.append(
            "the chart of the story points doesn't count the resolved issues: run prepare_report.py again")
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
            "the shares the GitHub pie shows aren't the main focus's: run prepare_report.py again")
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
        "the repositories the charts colour aren't those with the most merged pull requests: run prepare_report.py "
        "again"]
    for name in ("opened", "merged"):
        series = github[f"{name}_by_week"]
        if (series["total"], dict(series["repos"]), series["other"]) != _weekly(github[name], weeks, repo, order)[:3]:
            problems.append(
                f"the chart of the pull requests {name} doesn't count them week by week: run prepare_report.py again")
    pie = github["merged_by_repo"]
    if ({entry["repo"]: entry["prs"] for entry in pie["repos"]}, pie["other"]) != _split(merged, order, 0)[:2]:
        problems.append(
            "the chart of the merged pull requests by repository doesn't count them: run prepare_report.py again")
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
            "the chart of the merged pull requests' size doesn't count them: run prepare_report.py again")
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
    rows, spans = _grouped_rows(PAGE_ROW, text)
    shown = [(week, html.unescape(url), html.unescape(title), html.unescape(area))
             for week, url, title, area in rows]
    newest = sorted(pages, key=lambda page: (
        page["between"][0], page["url"]), reverse=True)
    expected = [(week_of(page), page["url"],
                 page["title"], space(page) or "") for page in newest]
    if not count or int(count[1]) != len(pages) or shown != expected or spans != _spans(expected):
        problems.append(
            "the report's Notion pages don't show data.json's: run finish_report.py again")
    return problems


# Observations.

def _observations_problems(text, summaries, values, folder, content, span):
    """(problems, cited): why `text`, the report's Observations section, doesn't show the points of
    `summaries` going well and to improve, the reviews dated in `span`,
    its first and last day, among them, each part's table by the first of
    `values` each names, the second it names beside it, those with the most points first, in their order
    when as many, those naming none last, then those of context, not
    grouped, each part's the most recent first, by its piece's date or its
    latest dated evidence's, undated first, and its evidence too, those of a
    day in the order given, a note's link relative to `folder`, the
    report's, each table folded under its summary in `content`, empty when
    it does; and each period point by its id, (text, source, links, period),
    as a comparison's row cites it."""
    reviews = summaries["reviews"]["pieces"]

    def rows(part):
        pieces = [*(("feedback", piece) for piece in summaries["feedback"]["pieces"]),
                  *(("reviews", piece) for piece in reviews if piece["date"] and span[0] <= piece["date"] <= span[1])]
        found = [(piece["date"], value(point), text_of(point), also(point), source, [], piece["period"] or "–")
                 for source, piece in pieces for point in piece[part]]
        for source in ("notes", "slack"):
            for point in summaries[source][part]:
                days = sorted(point["evidence"], key=newest, reverse=True)
                found.append((max((item["date"] for item in days if item["date"]), default=None), value(point),
                              point["point"], also(point), source,
                              [(link_href(item["link"], folder), reference_text(
                                  source, item)) for item in days],
                              ""))
        ordered = sorted(found, key=lambda row: newest(
            {"date": row[0]}), reverse=True)
        if part not in VALUED_PARTS:
            return [(point, OBSERVATION_SOURCES[source], links, period)
                    for _, _, point, _, source, links, period in ordered]
        counts = Counter(row[1] for row in ordered)
        ranked = sorted(
            (name for name in values if counts[name]), key=lambda name: -counts[name])
        return [(name, point, second, OBSERVATION_SOURCES[source], links, period)
                for name in [*ranked, NO_VALUE] for _, group, point, second, source, links, period in ordered
                if group == name]

    def newest(item):
        return "~" if item["date"] is None else item["date"]

    # A piece's context point is a sentence alone, and names no value.
    def text_of(point):
        return point if isinstance(point, str) else point["point"]

    def named(point):
        return point.get("values", []) if isinstance(point, dict) else []

    def value(point):
        return named(point)[0] if named(point) else NO_VALUE

    def also(point):
        return named(point)[1] if len(named(point)) > 1 else ""
    parts = dict(OBSERVATION_PART.findall(text))
    # Each period point by its id, (text, source, links, period), as a
    # comparison row cites it.
    cited = {}
    for part, heading in OBSERVATION_HEADINGS.items():
        expected = rows(part)
        cited |= {point_id(part, number): (row[1], *row[3:]) if part in VALUED_PARTS else row
                  for number, row in enumerate(expected, 1)}
        table = parts.get(heading)
        if table is None:
            return [f"the report's {heading} points don't show the summaries': run finish_report.py again"], cited
        details = DETAILS.search(table)
        if part in VALUED_PARTS:
            found, spans = _grouped_rows(OBSERVATION_ROW, table)
            shown = [(group, html.unescape(point), html.unescape(second), source, *_reference(reference))
                     for group, second, point, source, reference in found]
            grouped = spans == _spans(expected)
        else:
            shown = [(html.unescape(point), source, *_reference(reference))
                     for point, source, reference in CONTEXT_ROW.findall(table)]
            grouped = True
        if not grouped or (details[1] if details else None, shown) != (
                details_text(len(expected)) if expected else None, expected):
            return [f"the report's {heading} points don't show the summaries': run finish_report.py again"], cited
        if expected and content[part].strip() not in table.split("<details>", 1)[0]:
            return [f"the report's {heading} summary isn't content.json's: run finish_report.py again"], cited
    return [], cited


def _comparison_problems(comparison, section, baseline, cited, value, validation, name):
    """Why `section`, (text, marked), the section of `comparison`, a
    Comparison, its heading marked as the agent's or not, doesn't show
    `value`, its file, empty when it does: with no `baseline`, its heading,
    unmarked, and its not_applicable alone; else its heading marked as the
    agent's, its subtitle, `name` the baseline's, its summary, then its
    table, folded, each row the point of `baseline`,
    {id: its part's heading and text}, it names, or – for none, its kind's
    label and each point it cites, by its id in `cited`, or the
    comparison's no_evidence, ordered by kind, then by the baseline point's
    order, those with none last. The file must first have no `validation`
    problems, those of its rules against data.json."""
    if validation:
        return validation
    text, marked = section
    if baseline is None:
        if marked or text.strip() != comparison.not_applicable:
            return [f"the report's {comparison.name} must say {comparison.not_applicable} alone, as "
                    f"{comparison.absent}: run finish_report.py again"]
        return []
    subtitle = comparison.subtitle.format(name=name)
    if _subtitle(text) != subtitle:
        return [f"the report's {comparison.name} must start with its subtitle, {subtitle}: run finish_report.py "
                "again"]
    point_field, kind_field, _ = comparison.row
    order = [*baseline, None]
    expected = [(baseline[row[point_field]] if row[point_field] else "–", comparison.labels[row[kind_field]],
                 [cited[item] for item in row["evidence"]] or comparison.no_evidence)
                for row in sorted(value["rows"], key=lambda row: (list(comparison.labels).index(row[kind_field]),
                                                                  order.index(row[point_field])))]
    shown = [(html.unescape(point), kind, _cited(evidence, comparison.no_evidence))
             for point, kind, evidence in CONTEXT_ROW.findall(text)]
    details = DETAILS.search(text)
    if not marked or value["summary"].strip() not in text.split("<details>", 1)[0]:
        return [f"the report's {comparison.name} summary isn't {comparison.file}'s: run finish_report.py again"]
    if (details[1] if details else None, shown) != (
            details_text(len(expected), comparison.counted) if expected else None, expected):
        return [f"the report's {comparison.name} rows don't show {comparison.file}'s: run finish_report.py again"]
    return []


def _subtitle(text):
    """The first line of `text`, a section's after its heading, where its
    subtitle is, unescaped, as a name in it is written for HTML."""
    return html.unescape(text.strip().split("\n", 1)[0])


def _review_name(review):
    """The name of `review`, the latest previous review's piece, as the step
    change's subtitle gives it after the review: ", " and its period, else
    ", of " and its date, DD/MM/YYYY, else nothing."""
    if review["period"]:
        return f", {review['period']}"
    return f", of {display_date(review['date'])}" if review["date"] else ""


def _baseline_labels(summary, prefix):
    """{id: label}: each point of `summary`, a summary compared with the
    period, by its id after `prefix`, by part and place, its label its
    part's heading and its text, as a comparison's row names it."""
    return {point_id(part, number, prefix): f"{OBSERVATION_HEADINGS[part]}: "
            f"{point if isinstance(point, str) else point['point']}"
            for part in SUMMARY_PARTS for number, point in enumerate(summary[part], 1)}


def _cited(evidence, none):
    """A comparison row's evidence cell, `evidence`, as the report writes
    it: `none`, what a row citing no point says, or each point it cites,
    (text, source, links, period), its reference read by _reference()."""
    if evidence == none:
        return none
    return [(html.unescape(found[1]), found[2], *_reference(found[3])) if (found := CITED.fullmatch(item))
            else (item,) for item in evidence.split("<br>")]


def _reference(reference):
    """(links, period): a row's reference cell, `reference`, as the report
    writes it: its links, each (address, what it says), or, with none, its
    piece's period."""
    links = [(html.unescape(link), html.unescape(label))
             for link, label in LINK.findall(reference)]
    return links, "" if links else html.unescape(reference)


# Shared.

def _grouped_rows(pattern, text):
    """The rows of a grouped table in `text`, as `pattern`, starting with
    GROUP_CELL, reads them: each its group's name, carried down from the row
    that names it, then its other cells; and each group as (name, the rows
    it spans)."""
    rows, spans, group = [], [], None
    for span, named, *cells in pattern.findall(text):
        if named:
            group = html.unescape(named)
            spans.append((group, int(span)))
        rows.append((group, *cells))
    return rows, spans


def _spans(rows):
    """Each group of `rows`, named by their first item, as (name, how many
    rows it holds), in the order they come."""
    return [(name, sum(1 for row in rows if row[0] == name)) for name in dict.fromkeys(row[0] for row in rows)]


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
