"""Writes a prep's four briefs from data.json: observations_brief.json, what the agent reads to write observations_content.json, its summary of what is going well, what to improve and the context, step_change_brief.json, what it reads to write step_change_content.json, the step change from the previous feedback, and work_impact_brief.json, what it reads to write work_impact_content.json, the person's work and its impact, and earlier_work_brief.json, what it reads to write earlier_work_content.json, the work before the period.

Like the report, each is a view of data.json, and holds only what its task
needs. The summaries need the company values and, as the tables order points
by value, not weight, the work's main focus: a measure of volume, not
impact, that helps a summary open with what matters most. The step change
needs the previous feedback and every point's id, so it cites points by id
rather than retyping them. The work before the period needs only the
previous feedback's points, as a reminder cites nothing.
"""
import argparse
import json
import os

from common import (EARLIER_WORK_BRIEF, OBSERVATIONS_BRIEF, DATA, OBSERVATION_HEADINGS, OBSERVATION_SOURCES, PERSON, STEP_CHANGE_BRIEF,
                    VALUED_PARTS, VALUES, WORK_IMPACT_BRIEF, company_setting, observation_points, prep_dir, read_json,
                    write_prep_file)

# The most recent items a group of the work lists in the work and its
# impact's brief, beside how many it holds: a person can have hundreds,
# which would fill the agent's context and tell it little more than a
# sample of their titles; data.json keeps them all, so any can still be
# cited by its link.
RECENT_ITEMS = 10


def write_briefs(prep):
    """Write the prep `prep`'s observations_brief.json, step_change_brief.json,
    work_impact_brief.json and earlier_work_brief.json from its person.json
    and data.json; returns their paths, in that order."""
    folder = prep_dir(prep)
    person, data = (read_json(os.path.join(folder, name))
                    for name in (PERSON, DATA))
    return [write_prep_file(prep, OBSERVATIONS_BRIEF, build_brief(person, data, company_setting(VALUES))),
            write_prep_file(prep, STEP_CHANGE_BRIEF,
                            build_step_change_brief(person, data)),
            write_prep_file(prep, WORK_IMPACT_BRIEF,
                            build_work_impact_brief(person, data)),
            write_prep_file(prep, EARLIER_WORK_BRIEF, build_earlier_work_brief(person, data))]


def build_brief(person, data, values):
    """The brief of the observations' summaries, from `person`, person.json,
    `data`, data.json, and `values`, the company's, each with its meaning:
    the person, the values, focus, the main focus of their pull requests and
    of their resolved issues, each entry with its share, and each table's
    points by period_entries(), without their ids, which no summary cites."""
    return {"person": person["person"], "values": values,
            "focus": {"github": [{"repo": entry["repo"], "prs": entry["prs"], "share": entry["share"]}
                                 for entry in data["github"]["focus"]],
                      "jira": [{"key": entry["key"], "title": entry["title"], "issues": entry["issues"],
                                "share": entry["share"]} for entry in data["jira"]["focus"]]},
            **{part: [{key: value for key, value in entry.items() if key != "id"} for entry in entries]
               for part, entries in period_entries(data["observations"]).items()}}


def build_step_change_brief(person, data):
    """The brief of the step change, from `person`, person.json, and `data`,
    data.json: the person, each table's points by period_entries(), with
    their ids, and previous, data.json's previous feedback, its points with
    their ids, or null when it has none."""
    return {"person": person["person"], **period_entries(data["observations"]), "previous": data["previous"]}


def build_work_impact_brief(person, data):
    """The brief of the work and its impact, from `person`, person.json, and
    `data`, data.json: the person; epics, the Jira issues they created or
    resolved by epic, those with none as one more group, its key null;
    pull_requests, theirs by repository; and notion, the pages they created,
    each group by work_groups(), each page {title, url, path, date}, the last
    day of the range it was found in, the most recent first; then each
    table's points by period_entries(), with their ids."""
    issues = {issue["url"]: issue for issue in (
        *data["jira"]["created"], *data["jira"]["resolved"])}
    prs = {pr["url"]: pr for pr in (
        *data["github"]["opened"], *data["github"]["merged"])}
    pages = sorted(({"title": page["title"], "url": page["url"], "path": page["path"],
                     "date": page["between"][1]} for page in data["notion"]["created"]),
                   key=lambda page: page["date"], reverse=True)
    return {"person": person["person"],
            "epics": [{"key": key, "title": title, "url": url, **group}
                      for (key, title, url), group in work_groups(
                          issues.values(),
                          lambda issue: (
                              issue["epic"]["key"], issue["epic"]["title"], issue["epic"]["url"])
                          if issue["epic"] else (None, None, None),
                          lambda issue: {"key": issue["key"], "title": issue["title"], "url": issue["url"],
                                         "status": issue["status"], "date": issue["date"]})],
            "pull_requests": [{"repo": repo, "search_url": data["github"]["repo_search_urls"].get(repo), **group}
                              for repo, group in work_groups(
                                  prs.values(), lambda pr: pr["repo"],
                                  lambda pr: {"title": pr["title"], "url": pr["url"], "date": pr["date"]})],
            "notion": pages, **period_entries(data["observations"])}


def build_earlier_work_brief(person, data):
    """The brief of the work before the period, from `person`, person.json,
    and `data`, data.json: the person, and previous, the previous feedback's
    points, each part's texts, or null when it has none."""
    previous = data["previous"]
    return {"person": person["person"],
            "previous": None if previous is None else {part: [point["point"]
                                                              for point in points]
                                                       for part, points in previous.items()}}


def work_groups(items, group_of, shown):
    """[(group, {items, recent})]: `items`, each once, by `group_of`, each
    group with how many items it holds and its RECENT_ITEMS most recent, each
    as `shown` gives it, the most recent first; the groups by their latest
    item, the most recent first."""
    groups = {}
    for item in sorted(items, key=lambda item: item["date"], reverse=True):
        groups.setdefault(group_of(item), []).append(item)
    return [(group, {"items": len(found), "recent": [shown(item) for item in found[:RECENT_ITEMS]]})
            for group, found in groups.items()]


def period_entries(observations):
    """{part: points}: for each part of OBSERVATION_HEADINGS, the points of
    its table in `observations`, data.json's, in its order, each {id, point,
    values, source, when}: in VALUED_PARTS the values it names, the first
    the one its row sits under, none in context, which names none; its
    source as the report names it, and when it was seen, its latest
    evidence's day, null when none is dated, as with the feedbacks."""
    def entry(point, values=None):
        return {"id": point["id"], "point": point["point"], **({} if values is None else {"values": values}),
                "source": OBSERVATION_SOURCES[point["source"]],
                "when": point["date"]}
    return {part: [entry(point, [value for value in (group["value"], point["also"]) if value])
                   for group in observations[part] for point in group["points"]]
            if part in VALUED_PARTS else [entry(point) for point in observation_points(observations, part)]
            for part in OBSERVATION_HEADINGS}


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Write the prep's briefs from data.json: observations_brief.json, the points of each table of "
        "observations, going well, to improve and context, which the agent summarises in observations_content.json, "
        "step_change_brief.json, those points with their ids and the previous feedback, which it compares in "
        "step_change_content.json, and work_impact_brief.json, the person's work by epic, repository and page, "
        "with those points, from which it writes work_impact_content.json, and earlier_work_brief.json, the "
        "previous feedback's points, from which it lists the work before the period in earlier_work_content.json.",
        epilog="Prints one line of JSON: briefs, the four briefs' paths.")
    parser.add_argument("--prep", required=True,
                        help="the prep's folder, <Person>_<YY-MM-DD>, as init_prep.py printed it")
    args = parser.parse_args(argv)
    print(json.dumps({"briefs": write_briefs(args.prep)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
