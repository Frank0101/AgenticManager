"""Builds a prep's data.json from its raw files and the summaries of the current manager feedback, the other feedback, the previous feedback, the notes and Slack: the one model its report reads, every item and every fact worked out from them, once.

The report and its charts read these facts and never work them out again,
and the final check rebuilds the file from the same files and works the
report's figures out again from the items and the summaries' points, apart
from this code. It needs no network, so rerunning it rebuilds the model
from what was gathered. Weeks are calendar weeks, clipped to the period and
never grouped: a short week at an edge counts its own days, so its lower
value is for the charts to show by where they place it, not to change.
"""
import argparse
import json
import math
import os
import statistics
from collections import Counter

from common import (BINS_PER_DECADE, calendar_week, calendar_weeks, latest_day, newest_key, DATA, FOCUS_SHARE, MAX_GROUPS, OBSERVATION_HEADINGS, SUMMARY_FILES, SUMMARY_PARTS, VALUED_PARTS, VALUES, PREVIOUS_ID, point_id, project_of, PERSON, WORK_LISTS, company_names, epic_of, jira_search_url, pull_search_url, period_days, prep_dir, raw_work_problems,
                    is_sub_task, read_json, read_raw_work, work_items, write_prep_file)

# The searches data.json links to, by what they find: each list's, and the
# resolved issues that are estimated, whose points are summed.
SEARCH_URLS = {"jira": ("created", "resolved",
                        "resolved_points"), "github": ("opened", "merged")}


def build_data(prep):
    """Build the prep `prep`'s data.json from its raw files and the summaries
    of the current manager feedback, the other feedback, the previous feedback, the
    notes and Slack; returns its path. Exits, writing
    nothing, when a raw file is missing or breaks a rule, or a summary is
    missing."""
    person = read_json(os.path.join(prep_dir(prep), PERSON))
    raws = read_raw_work(prep)
    if problems := raws_problems(raws, period_days(person)):
        raise SystemExit("; ".join(problems))
    summaries = read_summaries(prep)
    if missing := [name for name, summary in summaries.items() if summary is None]:
        raise SystemExit(f"{', '.join(SUMMARY_FILES[name] for name in missing)} missing: record the manager's "
                         "feedback, the other feedback and the previous feedback and read the notes and Slack "
                         "first")
    return write_prep_file(prep, DATA, build(raws, person, summaries, company_names(VALUES)))


def read_summaries(prep):
    """The summaries the report's observations and step change are built from, in the prep `prep`, by SUMMARY_FILES' names, each None while it is
    missing."""
    folder = prep_dir(prep)
    return {name: read_json(os.path.join(folder, file)) if os.path.exists(os.path.join(folder, file)) else None
            for name, file in SUMMARY_FILES.items()}


def raws_problems(raws, days):
    """Why `raws`, every source's raw file or None while one is missing,
    can't be built from, empty when they can."""
    if raws is None:
        return ["the work's raw files are missing: run fetch_work.py and set_notion.py first"]
    return [problem for source, raw in raws.items() for problem in raw_work_problems(source, raw, days)]


def build(raws, person, summaries, values):
    """data.json from `raws`, every source's raw file, for the period in
    `person`: weeks, the period's calendar weeks, and for each
    source its items, its facts and its searches' addresses; a Notion page
    with its calendar week, by calendar_week(), as its search may span only
    part of one; observations, the points of `summaries`' current manager
    feedback, other feedback, notes and Slack, by observations(), with `values`, the company's;
    previous, the previous feedback, by baseline_parts(), null when it has
    no points."""
    weeks = calendar_weeks(person["start"], person["end"])
    data: dict = {"weeks": weeks}
    for source, raw in raws.items():
        lists = work_items(source, raw)
        if source == "notion":
            lists = {"created": [{**page, "week": calendar_week(page["between"][0], person["start"], person["end"])}
                                 for page in lists["created"]]}
        data[source] = {
            **lists, **source_facts(source, lists, weeks), **search_urls(source, raw)}
    data["observations"] = observations(summaries, values)
    data["previous"] = baseline_parts(summaries["previous"])
    return data


def data_problems(data, raws, person, summaries, values):
    """Why `data` isn't data.json as build() makes it from `raws`, every
    source's raw file or None while one is missing, and `summaries`, with
    `values`, empty when it is."""
    if problems := raws_problems(raws, period_days(person)):
        return problems
    if data != build(raws, person, summaries, values):
        return ["data.json doesn't match the raw files and summaries it is built from: run prepare_report.py again"]
    return []


# The observations.

def observations(summaries, values):
    """The points of `summaries`, the current manager feedback's, the other
    feedback's, the notes' summary and Slack's, for each
    part of OBSERVATION_HEADINGS, by part_points(), each with its id, by
    point_id(), in its table's order: a
    part of VALUED_PARTS as a group for each of `values` that a point names
    first, those with the most points first, in their order when as many,
    then one, its value null, of the points that name none, each point
    {id, point, also, source, date, evidence}, also the second value it
    names, null when it names one or none, so it shows though the point sits
    under its first; context, which names no value, as its points alone."""
    result = {}
    for part in OBSERVATION_HEADINGS:
        points = part_points(summaries, part)
        if part not in VALUED_PARTS:
            result[part] = numbered(points, part)
            continue
        counts = Counter(point["value"] for point in points)
        ranked = [*sorted((value for value in values if counts[value]), key=lambda value: -counts[value]),
                  *([None] if counts[None] else [])]
        ordered = numbered(
            [point for value in ranked for point in points if point["value"] == value], part)
        result[part] = [{"value": value, "points": [{key: field for key, field in point.items() if key != "value"}
                                                    for point in ordered if point["value"] == value]}
                        for value in ranked]
    return result


def numbered(points, part, prefix=""):
    """`points` of `part`, each with its id first, by point_id(), in their
    order, after `prefix`, such as PREVIOUS_ID for the previous
    feedback's."""
    return [{"id": point_id(part, number, prefix), **point} for number, point in enumerate(points, 1)]


def part_points(summaries, part):
    """The points of `part` in `summaries`, the current manager feedback's,
    the other feedback's, the notes' and Slack's, the most recent first,
    those with no date first, as
    the most recent of all, by the latest of their dated evidence's: each
    {point, source, date, evidence}, and in VALUED_PARTS its also and its
    value, the first it names or null; its source a key of SUMMARY_FILES,
    and its evidence a reading's, the most recent first the same way, those
    of a day in the order given, empty for the feedbacks'."""
    points = [{**point_text(point, part), "source": source, "date": None, "evidence": []}
              for source in ("manager", "other") for point in summaries[source][part]]
    points += [{**point_text(point, part), "source": source,
                "date": latest_day(point["evidence"]),
                "evidence": newest(point["evidence"])}
               for source in ("notes", "slack") for point in summaries[source][part]]
    return newest(points)


def point_text(point, part):
    """{point}, the text of `point`, a point of `part`, and in VALUED_PARTS
    {also, value}: the second company value it names and the first, each
    null when it names fewer. A feedback's context point is a sentence alone."""
    if part not in VALUED_PARTS:
        return {"point": summary_text(point)}
    return {"point": point["point"], "also": point["values"][1] if len(point["values"]) > 1 else None,
            "value": next(iter(point["values"]), None)}


def newest(dated):
    """`dated`, each with a date, the most recent first, those with none
    first, as the most recent of all, those of a day in the order given."""
    return sorted(dated, key=lambda item: newest_key(item["date"]), reverse=True)


def baseline_parts(summary):
    """{part: points}: each part of SUMMARY_PARTS of `summary`, the previous
    feedback the period is compared with, each point with its id, by
    numbered(), after PREVIOUS_ID, its text and, in VALUED_PARTS, its values;
    null when it has no points, as there is then nothing to compare."""
    if not any(summary.values()):
        return None
    return {part: numbered([{"point": summary_text(point), **({"values": point["values"]}
                                                              if part in VALUED_PARTS else {})}
                            for point in summary[part]], part, PREVIOUS_ID)
            for part in SUMMARY_PARTS}


def summary_text(point):
    """The text of `point`, a summary's: a context point is a sentence
    alone."""
    return point if isinstance(point, str) else point["point"]


# The facts.

def source_facts(source, lists, weeks):
    """The facts of `lists`, the items of `source`, over `weeks`: counts, how
    many items each list holds; for Jira, created_by_type and
    resolved_by_type, the issues of each type, most first, resolved_by_epic,
    the resolved issues by epic, focus, their main focus, each with its share, resolved_points,
    the resolved issues' points, their total, how many are estimated and
    their average, null when none is, an unestimated issue counting toward
    neither; for GitHub, merged_by_repo, the merged pull requests by
    repository, focus, the repositories that hold most of them, each with
    its share,
    repo_counts, how many repositories each list's pull requests are in, and
    merged_lines, the median of the merged ones' lines changed. For the
    charts, epic_order or repo_order, the epics or repositories they colour,
    by chart_order(), the others counted together as other in
    resolved_by_epic, whose epics hold the issues with no epic as one more,
    by with_no_epic(), in merged_by_repo and in the series, each grouped():
    Jira's created_by_week and resolved_by_week, and points_by_epic, GitHub's
    opened_by_week and merged_by_week, and lines_distribution."""
    facts: dict = {"counts": {name: len(items)
                              for name, items in lists.items()}}
    if source == "jira":
        ranked = by_epic(lists["resolved"])
        order = chart_order([entry["key"] for entry in ranked["epics"]],
                            {issue["epic"]["key"] for issue in lists["created"] if issue["epic"]})
        shown = [entry for entry in ranked["epics"] if entry["key"] in order]
        facts |= {"created_by_type": by_type(lists["created"]), "resolved_by_type": by_type(lists["resolved"]),
                  "resolved_by_epic": {"epics": with_no_epic(shown, ranked["no_epic"]),
                                       "other": sum(entry["issues"] for entry in ranked["epics"])
                                       - sum(entry["issues"] for entry in shown)},
                  "focus": with_shares(focus(lists["resolved"]), "issues", len(lists["resolved"])),
                  "resolved_points": points(lists["resolved"]),
                  "epic_order": order,
                  **{f"{name}_by_week": grouped(lists[name], order, epic_key, lambda found: weekly(found, weeks),
                                                "epics", "no_epic") for name in ("created", "resolved")},
                  "points_by_epic": points_by_epic(lists["resolved"], order)}
    if source == "github":
        ranked = by_repo(lists["merged"])
        order = chart_order([entry["repo"] for entry in ranked], {
                            pr["repo"] for pr in lists["opened"]})
        shown = [entry for entry in ranked if entry["repo"] in order]
        facts |= {"merged_by_repo": {"repos": shown, "other": len(lists["merged"]) - sum(entry["prs"] for entry in shown)},
                  "focus": with_shares(cover(ranked, "prs"), "prs", len(lists["merged"])), "repo_order": order,
                  "repo_counts": {name: len({pr["repo"] for pr in prs}) for name, prs in lists.items()},
                  **{f"{name}_by_week": grouped(lists[name], order, repo_key, lambda found: weekly(found, weeks),
                                                "repos") for name in ("opened", "merged")},
                  "merged_lines": lines(lists["merged"]),
                  "lines_distribution": lines_distribution(lists["merged"], order)}
    return facts


def points(issues):
    """{total, estimated, average}: the points of the estimated `issues`,
    summed, how many they are and their average, null when there are none,
    to one decimal."""
    estimated = [issue["points"]
                 for issue in issues if issue["points"] is not None]
    return {"total": round(sum(estimated), 1), "estimated": len(estimated),
            "average": round(sum(estimated) / len(estimated), 1) if estimated else None}


def by_type(issues):
    """[{type, issues}]: how many of `issues` there are of each type, most
    first, then by type."""
    return [{"type": kind, "issues": count} for kind, count in ranked_counts(issue["type"] for issue in issues)]


def by_epic(resolved):
    """{epics, no_epic}: the issues `resolved` by their epic, each {key,
    title, url, issues}, the most issues first, then by key; and how many
    have none."""
    epics = {issue["epic"]["key"]: issue["epic"]
             for issue in resolved if issue["epic"]}
    return {"epics": [{**epics[key], "issues": count}
                      for key, count in ranked_counts(issue["epic"]["key"] for issue in resolved if issue["epic"])],
            "no_epic": sum(1 for issue in resolved if not issue["epic"])}


def focus(resolved):
    """The main focus of the issues `resolved`: the fewest of their epics,
    the issues with no epic counted as one more, its key null, ranked by how
    many each holds, whose issues are at least FOCUS_SHARE of them all, with
    every one tied with the last one, each {key, title, url, issues}; or,
    when none has an epic, their projects the same way, the title and url
    null. A fixed number of epics would give someone who works on two as
    long a list as someone who works on eight, and leaving the issues with
    no epic out would hide work no epic tracks."""
    epics = by_epic(resolved)
    ranked = with_no_epic(
        epics["epics"], epics["no_epic"]) if epics["epics"] else []
    if not ranked:
        ranked = [{"key": key, "title": None, "url": None, "issues": count}
                  for key, count in ranked_counts(project_of(issue["key"]) for issue in resolved)]
    return cover(ranked, "issues")


def with_no_epic(epics, no_epic):
    """`epics`, by_epic()'s, with the `no_epic` issues with no epic as one
    more, its key null, unless there are none, ranked by how many each holds,
    the issues with no epic after the epics they tie with."""
    entries = [*epics, *([{"key": None, "title": None,
                         "url": None, "issues": no_epic}] if no_epic else [])]
    return sorted(entries, key=lambda entry: (-entry["issues"], entry["key"] is None, entry["key"] or ""))


def with_shares(entries, count, total):
    """`entries`, each with its share, the percentage of the `total` its
    `count` makes, rounded, which its pie slice shows."""
    return [{**entry, "share": round(100 * entry[count] / total)} for entry in entries]


def cover(ranked, count):
    """The fewest of `ranked`, entries the most first by their `count`, whose
    counts are at least FOCUS_SHARE of all of them, with every entry tied
    with the last one."""
    total, covered, cutoff = sum(entry[count] for entry in ranked), 0, 0
    for entry in ranked:
        covered += entry[count]
        if covered >= FOCUS_SHARE * total:
            cutoff = entry[count]
            break
    return [entry for entry in ranked if entry[count] >= cutoff]


def points_by_epic(resolved, order):
    """[{points, issues, epics, other, no_epic}]: for each number of story
    points the `resolved` issues have, how many have it, how many of them
    belong to each epic of `order`, to any other epic, and to none."""
    estimated = [issue for issue in resolved if issue["points"] is not None]
    rows = []
    for value in sorted({issue["points"] for issue in estimated}):
        counts = grouped([issue for issue in estimated if issue["points"] == value], order, epic_key, len,
                         "epics", "no_epic")
        rows.append({"points": value, "issues": counts.pop("total"), **counts})
    return rows


def by_repo(prs):
    """[{repo, prs}]: how many of the pull requests `prs` each repository
    holds, the most first, then by name."""
    return [{"repo": repo, "prs": n} for repo, n in ranked_counts(pr["repo"] for pr in prs)]


def lines(merged):
    """{median}: the median of the lines each of the `merged` pull requests
    changed, null when there are none: unlike the average, a few huge ones,
    such as generated code, don't drag it."""
    return {"median": statistics.median(pr["lines"] for pr in merged) if merged else None}


def lines_distribution(merged, order):
    """{total, repos, other}: how many of the `merged` pull requests changed
    lines in each bin of a log scale, BINS_PER_DECADE to each power of ten,
    from 1 to the power of ten above the largest, a pull request of none in
    the first: in all, for each repository of `order` that holds any, and for
    those of any other."""
    decades = int(math.log10(
        max([pr["lines"] for pr in merged if pr["lines"] >= 1], default=1))) + 1

    def counts(prs):
        found = [0] * (decades * BINS_PER_DECADE)
        for pr in prs:
            found[int(BINS_PER_DECADE * math.log10(pr["lines"]))
                  if pr["lines"] >= 1 else 0] += 1
        return found
    return grouped(merged, order, repo_key, counts, "repos")


# How the facts group and rank items.

def ranked_counts(keys):
    """[(key, how many)]: how many times each of `keys` comes, the most
    first, then by key."""
    return sorted(Counter(keys).items(), key=lambda pair: (-pair[1], pair[0]))


def chart_order(ranked, others):
    """[key]: the groups the charts colour, at most MAX_GROUPS: the keys
    `ranked`, then `others` not among them, sorted, so each chart lists them
    in one order."""
    return (ranked + sorted(set(others) - set(ranked)))[:MAX_GROUPS]


def grouped(items, order, group, count, groups, none=None):
    """{total, <groups>, other[, <none>]}: `count` of `items`: of them all,
    by key of `order`, under `groups`, of those `group` gives that key, for
    each key that has any, of those of any other key, and, under `none` when
    it is given, of those it gives no key."""
    counts = {"total": count(items),
              groups: {key: count([item for item in items if group(item) == key])
                       for key in order if any(group(item) == key for item in items)},
              "other": count([item for item in items if group(item) is not None and group(item) not in order])}
    if none:
        counts[none] = count([item for item in items if group(item) is None])
    return counts


def epic_key(issue):
    """The key of the epic `issue` belongs to, None when it has none."""
    return issue["epic"]["key"] if issue["epic"] else None


def repo_key(pr):
    """The repository of the pull request `pr`."""
    return pr["repo"]


def weekly(items, weeks):
    """How many of `items` fall in each of `weeks`, by their day."""
    return [sum(1 for item in items if first <= item["date"] <= last) for first, last in weeks]


# The searches.

def search_urls(source, raw):
    """{<search>_search_url: address}: the address of each of the SEARCH_URLS
    of `source`, Jira's JQL on its site or GitHub's query on github.com,
    which finds the same items live, GitHub's merged_lines null, as no
    search finds a median; the estimated resolved issues' null
    when the site has no points field, and the resolved issues with no epic,
    by their keys, null when there are none; for Jira also epic_search_urls, by
    epic_search_urls(), and for GitHub repo_search_urls, each repository's
    merged pull requests, the merged search with the repository in place of
    the organisations, as GitHub reads its scopes as alternatives; {} for a
    source with none."""
    if source == "jira":
        estimated = " OR ".join(f"cf[{field.removeprefix('customfield_')}] is not EMPTY"
                                for field in raw["points_fields"])
        parents = {parent["key"]: parent for parent in raw["parents"]}
        no_epic = [issue["key"] for issue in raw["resolved"]
                   if not epic_of(issue["fields"], parents)]
        jqls = {"created": raw["created_jql"], "resolved": raw["resolved_jql"],
                "resolved_points": estimated and f"{raw['resolved_jql']} AND ({estimated})",
                "no_epic": f"{raw['resolved_jql']} AND key in ({', '.join(no_epic)})" if no_epic else None}
        return {**{f"{name}_search_url": jql and jira_search_url(raw["base_url"], jql) for name, jql in jqls.items()},
                "epic_search_urls": epic_search_urls(raw)}
    if source == "github":
        # A median has no search that finds it, so its figure links nowhere.
        return {**{f"{name}_search_url": pull_search_url(raw[f"{name}_query"]) for name in WORK_LISTS[source]},
                "merged_lines_search_url": None,
                "repo_search_urls": {repo: pull_search_url(" ".join(
                    [*(term for term in raw["merged_query"].split() if not term.startswith("org:")), f"repo:{repo}"]))
                    for repo in sorted({pr["repository"]["nameWithOwner"] for pr in raw["merged"]})}}
    return {}


def epic_search_urls(raw):
    """{epic: address}: for each epic of the resolved issues in `raw`, Jira's
    raw file, the search that finds the ones counted in it: the resolved
    search, narrowed to the epic's children and to the sub-tasks of its
    stories, as a sub-task counts in its story's epic."""
    parents = {parent["key"]: parent for parent in raw["parents"]}
    children, stories = set(), {}
    for issue in raw["resolved"]:
        fields = issue["fields"]
        if not (epic := epic_of(fields, parents)):
            continue
        if is_sub_task(fields):
            stories.setdefault(epic["key"], set()).add(fields["parent"]["key"])
        else:
            children.add(epic["key"])
    urls = {}
    for epic in sorted({*children, *stories}):
        under = [f"parent = {epic}"] if epic in children else []
        if epic in stories:
            under.append(f"parent in ({', '.join(sorted(stories[epic]))})")
        urls[epic] = jira_search_url(
            raw["base_url"], f"{raw['resolved_jql']} AND ({' OR '.join(under)})")
    return urls


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Build the prep's data.json, the model its report reads, from the raw files fetched from Jira, GitHub and Notion and "
        "the summaries of the current manager feedback, the other feedback, the previous feedback, the notes and Slack.",
        epilog="Prints one line of JSON: data, data.json's path. Needs no network: run it again to rebuild it.")
    parser.add_argument("--prep", required=True,
                        help="the prep's folder, <Person>_<YY-MM-DD>, as init_prep.py printed it")
    args = parser.parse_args(argv)
    print(json.dumps({"data": build_data(args.prep)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
