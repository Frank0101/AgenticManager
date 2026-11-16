"""Writes a prep's brief.json from data.json: what the agent reads to write content.json, its summary of what is going well, what to improve and the context.

Like the report, it is a view of data.json, so the agent writes from the
points the tables show: each table's points, each with its values, source
and when it was seen, and the company values with their meanings. The tables
order points by value, not weight, so it also gives the work's main focus in
GitHub and Jira: a measure of volume, not impact, that helps the summary open
with what matters most.
"""
import argparse
import json
import os

from common import (BRIEF, DATA, OBSERVATION_SOURCES, PERSON, VALUED_PARTS, VALUES, company_setting, prep_dir,
                    read_json, write_prep_file)


def write_brief(prep):
    """Write the prep `prep`'s brief.json from its person.json and
    data.json; returns its path."""
    folder = prep_dir(prep)
    person, data = (read_json(os.path.join(folder, name))
                    for name in (PERSON, DATA))
    return write_prep_file(prep, BRIEF, build_brief(person, data, company_setting(VALUES)))


def build_brief(person, data, values):
    """The brief, from `person`, person.json, `data`, data.json, and
    `values`, the company's, each with its meaning: the person, the values,
    focus, the main focus of their pull requests and of their resolved
    issues, each entry with its share, and for each part of
    OBSERVATION_HEADINGS its table's points, in its order, each {point,
    values, source, when}: in VALUED_PARTS the values it names, the first
    the one its row sits under, none in context, which names none; its
    source as the report names it, and when it was seen, its piece's period
    as the source names it or its latest evidence's day, null when none is
    dated."""
    def entry(point, values=None):
        return {"point": point["point"], **({} if values is None else {"values": values}),
                "source": OBSERVATION_SOURCES[point["source"]],
                "when": point["period"] if point["source"] == "feedback" else point["date"]}
    observations = data["observations"]
    return {"person": person["person"], "values": values,
            "focus": {"github": [{"repo": entry["repo"], "prs": entry["prs"], "share": entry["share"]}
                                 for entry in data["github"]["focus"]],
                      "jira": [{"key": entry["key"], "title": entry["title"], "issues": entry["issues"],
                                "share": entry["share"]} for entry in data["jira"]["focus"]]},
            **{part: [entry(point, [value for value in (group["value"], point["also"]) if value])
                      for group in observations[part] for point in group["points"]]
               for part in VALUED_PARTS},
            "context": [entry(point) for point in observations["context"]]}


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Write the prep's brief.json from data.json: the points of each table of observations, going "
        "well, to improve and context, which the agent summarises in content.json.",
        epilog="Prints one line of JSON: brief, brief.json's path.")
    parser.add_argument("--prep", required=True,
                        help="the prep's folder, <Person>_<YY-MM-DD>, as init_prep.py printed it")
    args = parser.parse_args(argv)
    print(json.dumps({"brief": write_brief(args.prep)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
