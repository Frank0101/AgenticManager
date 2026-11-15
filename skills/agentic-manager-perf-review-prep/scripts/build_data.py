"""Builds a prep's data.json from its raw files: the one model its report reads, every item and every fact worked out from them, once.

The report and its charts read these facts and never work them out again,
and the final check rebuilds the file from the raw files and works the
report's figures out again from the items, apart from this code. It needs no network, so rerunning it
rebuilds the model from what step 7 fetched. Weeks are calendar weeks, Monday
to Sunday, counted from a fixed Monday, so a day falls in the same week
whatever the period, a few at a time when there would be more than MAX_POINTS.
"""
import argparse
import json
import math
import os
import statistics
from collections import Counter
from datetime import date, timedelta

from common import (BINS_PER_DECADE, DATA, FOCUS_SHARE, MAX_GROUPS, project_of, PERSON, WORK_LISTS, epic_of, jira_search_url, pull_search_url, period_days, prep_dir, raw_work_problems,
                    read_json, read_raw_work, stops_on_failure, work_items, write_prep_file)

# The searches data.json links to, by what they find: each list's, and the
# resolved issues that are estimated, whose points are summed.
SEARCH_URLS = {"jira": ("created", "resolved",
                        "resolved_points"), "github": ("opened", "merged")}
EPOCH_MONDAY = date(2001, 1, 1)
MAX_POINTS = 20


def build_data(prep):
    """Build the prep `prep`'s data.json from its raw files; returns its
    path. Exits, writing nothing, when a raw file is missing or breaks a
    rule."""
    person = read_json(os.path.join(prep_dir(prep), PERSON))
    raws = read_raw_work(prep)
    if problems := raws_problems(raws, period_days(person)):
        raise SystemExit("; ".join(problems))
    return write_prep_file(prep, DATA, build(raws, person))


def raws_problems(raws, days):
    """Why `raws`, every source's raw file or None while one is missing,
    can't be built from, empty when they can."""
    if raws is None:
        return ["the work's raw files are missing: run fetch_work.py and set_notion.py first"]
    return [problem for source, raw in raws.items() for problem in raw_work_problems(source, raw, days)]


def build(raws, person):
    """data.json from `raws`, every source's raw file, for the period in
    `person`: weeks, the period's weeks as the charts group it, and for each
    source its items, its facts and its searches' addresses."""
    weeks = week_groups(person["start"], person["end"])
    data: dict = {"weeks": weeks}
    for source, raw in raws.items():
        lists = work_items(source, raw)
        data[source] = {
            **lists, **source_facts(source, lists, weeks), **search_urls(source, raw)}
    return data


def data_problems(data, raws, person):
    """Why `data` isn't data.json as build() makes it from `raws`, every
    source's raw file or None while one is missing, empty when it is."""
    if problems := raws_problems(raws, period_days(person)):
        return problems
    if data != build(raws, person):
        return ["data.json doesn't match the raw files it is built from: run build_data.py again"]
    return []


# The facts.

def source_facts(source, lists, weeks):
    """The facts of `lists`, the items of `source`, over `weeks`: counts, how
    many items each list holds; for Jira, created_by_type and
    resolved_by_type, the issues of each type, most first, resolved_by_epic,
    the resolved issues by epic, focus, their main focus, resolved_points,
    the resolved issues' points, their total, how many are estimated and
    their average, null when none is, an unestimated issue counting toward
    neither; for GitHub, merged_by_repo, the merged pull requests by
    repository, focus, the repositories that hold most of them,
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
                  "focus": focus(lists["resolved"]), "resolved_points": points(lists["resolved"]),
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
                  "focus": cover(ranked, "prs"), "repo_order": order,
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


def week_groups(start, end):
    """[[start, end]]: the calendar weeks, Monday to Sunday, from the day
    `start` to the day `end`, as YYYY-MM-DD, a few at a time when there would be
    more than MAX_POINTS of them, each group always the same weeks, the first
    and last clipped to `start` and `end`."""
    first, last = date.fromisoformat(start), date.fromisoformat(end)

    def week(day):
        return (day - EPOCH_MONDAY).days // 7
    width = 1
    while week(last) // width - week(first) // width + 1 > MAX_POINTS:
        width += 1
    return [[max(first, EPOCH_MONDAY + timedelta(weeks=group * width)).isoformat(),
             min(last, EPOCH_MONDAY + timedelta(weeks=(group + 1) * width, days=-1)).isoformat()]
            for group in range(week(first) // width, week(last) // width + 1)]


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
        if fields["issuetype"].get("subtask"):
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
        description="Build the prep's data.json, the model its report reads, from the raw files step 7 wrote.",
        epilog="Prints one line of JSON: data, data.json's path. Needs no network: run it again to rebuild it.")
    parser.add_argument("--prep", required=True,
                        help="the prep's folder, <Person>_<YY-MM-DD>, as init_prep.py printed it")
    args = parser.parse_args(argv)
    with stops_on_failure():
        print(json.dumps({"data": build_data(args.prep)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
