"""Writes a prep's two briefs from data.json: brief.json, what the agent reads to write content.json, its summary of what is going well, what to improve and the context, and step_change_brief.json, what it reads to write step_change.json, the step change from the latest previous review.

Like the report, each is a view of data.json, and holds only what its task
needs. The summaries need the company values and, as the tables order points
by value, not weight, the work's main focus: a measure of volume, not
impact, that helps a summary open with what matters most. The step change
needs the previous reviews and every point's id, so it cites points by id
rather than retyping them.
"""
import argparse
import json
import os

from common import (BRIEF, DATA, OBSERVATION_HEADINGS, OBSERVATION_SOURCES, PERSON, PIECE_SOURCES, STEP_CHANGE_BRIEF,
                    VALUED_PARTS, VALUES, company_setting, observation_points, prep_dir, read_json, write_prep_file)


def write_briefs(prep):
    """Write the prep `prep`'s brief.json and step_change_brief.json from
    its person.json and data.json; returns their paths, in that order."""
    folder = prep_dir(prep)
    person, data = (read_json(os.path.join(folder, name))
                    for name in (PERSON, DATA))
    return [write_prep_file(prep, BRIEF, build_brief(person, data, company_setting(VALUES))),
            write_prep_file(prep, STEP_CHANGE_BRIEF, build_step_change_brief(person, data))]


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
    their ids, and reviews, data.json's previous reviews, the latest with
    its points' ids, or null when there are none."""
    return {"person": person["person"], **period_entries(data["observations"]), "reviews": data["reviews"]}


def period_entries(observations):
    """{part: points}: for each part of OBSERVATION_HEADINGS, the points of
    its table in `observations`, data.json's, in its order, each {id, point,
    values, source, when}: in VALUED_PARTS the values it names, the first
    the one its row sits under, none in context, which names none; its
    source as the report names it, and when it was seen, its piece's period
    as the source names it or its latest evidence's day, null when none is
    dated."""
    def entry(point, values=None):
        return {"id": point["id"], "point": point["point"], **({} if values is None else {"values": values}),
                "source": OBSERVATION_SOURCES[point["source"]],
                "when": point["period"] if point["source"] in PIECE_SOURCES else point["date"]}
    return {part: [entry(point, [value for value in (group["value"], point["also"]) if value])
                   for group in observations[part] for point in group["points"]]
            if part in VALUED_PARTS else [entry(point) for point in observation_points(observations, part)]
            for part in OBSERVATION_HEADINGS}


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Write the prep's briefs from data.json: brief.json, the points of each table of "
        "observations, going well, to improve and context, which the agent summarises in content.json, and "
        "step_change_brief.json, those points with their ids and the previous reviews, which it compares in "
        "step_change.json.",
        epilog="Prints one line of JSON: briefs, the two briefs' paths.")
    parser.add_argument("--prep", required=True,
                        help="the prep's folder, <Person>_<YY-MM-DD>, as init_prep.py printed it")
    args = parser.parse_args(argv)
    print(json.dumps({"briefs": write_briefs(args.prep)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
