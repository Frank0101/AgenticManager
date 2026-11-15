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
import os
from datetime import date, timedelta

from common import (DATA, FOCUS_SHARE, project_of, PERSON, WORK_LISTS, epic_of, jira_search_url, pull_search_url, period_days, prep_dir, raw_work_problems,
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
    many items each list holds; for Jira, created_by_type and resolved_by_type, the issues of each type, most
    first, resolved_by_epic, the resolved issues by epic, focus, their main
    focus, resolved_points, the resolved issues' points, their total, how many
    are estimated and their average, null when none is, an unestimated issue
    counting toward neither; and for the charts, epic_order, every epic the
    issues belong to, the resolved issues' first, as by_epic() ranks them,
    created_by_week and resolved_by_week, by_week()'s, and points_by_epic."""
    facts: dict = {"counts": {name: len(items)
                              for name, items in lists.items()}}
    if source == "jira":
        facts |= {"created_by_type": by_type(lists["created"]), "resolved_by_type": by_type(lists["resolved"]),
                  "resolved_by_epic": by_epic(lists["resolved"]), "focus": focus(lists["resolved"]),
                  "resolved_points": points(lists["resolved"])}
        order = epic_order(facts["resolved_by_epic"], lists["created"])
        facts |= {"epic_order": order,
                  **{f"{name}_by_week": by_week(lists[name], weeks, order) for name in ("created", "resolved")},
                  "points_by_epic": points_by_epic(lists["resolved"], order)}
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
    types = {}
    for issue in issues:
        types[issue["type"]] = types.get(issue["type"], 0) + 1
    return [{"type": kind, "issues": count} for kind, count in sorted(types.items(), key=lambda pair: (-pair[1], pair[0]))]


def by_epic(resolved):
    """{epics, no_epic}: the issues `resolved` by their epic, each {key,
    title, url, issues}, the most issues first, then by key; and how many
    have none."""
    counts = {}
    for issue in resolved:
        if issue["epic"]:
            entry = counts.setdefault(issue["epic"]["key"], {
                                      **issue["epic"], "issues": 0})
            entry["issues"] += 1
    return {"epics": sorted(counts.values(), key=lambda entry: (-entry["issues"], entry["key"])),
            "no_epic": sum(1 for issue in resolved if not issue["epic"])}


def focus(resolved):
    """The main focus of the issues `resolved`: the fewest of their epics,
    as by_epic() ranks them, whose issues are at least FOCUS_SHARE of those
    with an epic, with every epic tied with the last one, each {key, title,
    url, issues}; or, when none has an epic, their projects the same way,
    the title and url null. A fixed number of epics would give someone who
    works on two as long a list as someone who works on eight."""
    ranked = by_epic(resolved)["epics"]
    if not ranked:
        projects = {}
        for issue in resolved:
            project = project_of(issue["key"])
            projects[project] = projects.get(project, 0) + 1
        ranked = [{"key": key, "title": None, "url": None, "issues": count}
                  for key, count in sorted(projects.items(), key=lambda pair: (-pair[1], pair[0]))]
    total, covered, cutoff = sum(entry["issues"] for entry in ranked), 0, 0
    for entry in ranked:
        covered += entry["issues"]
        if covered >= FOCUS_SHARE * total:
            cutoff = entry["issues"]
            break
    return [entry for entry in ranked if entry["issues"] >= cutoff]


def epic_order(ranked, created):
    """[epic]: every epic of the resolved issues, as `ranked`, by_epic()'s,
    ranks them,
    then every other epic of the `created` issues, by key, so each chart lists
    them in one order."""
    keys = [entry["key"] for entry in ranked["epics"]]
    return keys + sorted({issue["epic"]["key"] for issue in created if issue["epic"]} - set(keys))


def by_week(items, weeks, order):
    """{total, epics, no_epic}: how many of `items` fall in each of `weeks`,
    by their day: in all, for each epic of `order` they belong to, and for
    those with no epic."""
    def weekly(subset):
        return [sum(1 for item in subset if first <= item["date"] <= last) for first, last in weeks]
    return {"total": weekly(items),
            "epics": {key: weekly([item for item in items if item["epic"] and item["epic"]["key"] == key])
                      for key in order if any(item["epic"] and item["epic"]["key"] == key for item in items)},
            "no_epic": weekly([item for item in items if not item["epic"]])}


def points_by_epic(resolved, order):
    """[{points, issues, epics, no_epic}]: for each number of story points
    the `resolved` issues have, how many have it, how many of them belong to
    each epic of `order`, and how many to none."""
    estimated = [issue for issue in resolved if issue["points"] is not None]
    rows = []
    for value in sorted({issue["points"] for issue in estimated}):
        at_value = [issue for issue in estimated if issue["points"] == value]
        epics = {key: sum(
            1 for issue in at_value if issue["epic"] and issue["epic"]["key"] == key) for key in order}
        rows.append({"points": value, "issues": len(at_value), "epics": {key: n for key, n in epics.items() if n},
                     "no_epic": sum(1 for issue in at_value if not issue["epic"])})
    return rows


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
    which finds the same items live; the estimated resolved issues' null
    when the site has no points field; for Jira also epic_search_urls, by
    epic_search_urls(); {} for a source with none."""
    if source == "jira":
        estimated = " OR ".join(f"cf[{field.removeprefix('customfield_')}] is not EMPTY"
                                for field in raw["points_fields"])
        jqls = {"created": raw["created_jql"], "resolved": raw["resolved_jql"],
                "resolved_points": estimated and f"{raw['resolved_jql']} AND ({estimated})"}
        return {**{f"{name}_search_url": jql and jira_search_url(raw["base_url"], jql) for name, jql in jqls.items()},
                "epic_search_urls": epic_search_urls(raw)}
    if source == "github":
        return {f"{name}_search_url": pull_search_url(raw[f"{name}_query"]) for name in WORK_LISTS[source]}
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
