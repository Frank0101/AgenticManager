"""Records the account of a prep's person's work and its impact in its work_impact_content.json, which the report shows first, a paragraph for each initiative.

It is checked against data.json, every point and item it cites, before
anything is written, by the rule the final check applies, so a citation
that isn't there, or a paragraph that runs too long, is refused while it is
being written, not at the end. The initiatives are ordered here, most
recent first by their evidence, so the order is the script's, never the
agent's. It is written whole each time, so a correction is one more call
with every initiative.
"""
import argparse
import json
import os

from common import (DATA, WORDS, WORK_IMPACT_CONTENT, by_recency, prep_dir, read_json, stdin_json,
                    work_evidence, work_impact_content_problems, write_prep_file)

INPUT = f"""Input, on stdin: the initiatives, in any order, such as:

  python3 set_work_impact.py --prep Jane-Doe_26-11-10 <<'END_OF_INPUT'
  {{"initiatives": [
    {{"title": "Billing migration",
     "impact": "One line on the initiative's impact: what it is for, its value, and what changed.",
     "paragraph": "One paragraph on the person's part in it: what they did and how it went.",
     "evidence": ["G3", "https://acme.atlassian.net/browse/PROJ-1",
                  "https://github.com/acme/billing/pull/1", "https://www.notion.so/billing-plan"]}}]}}
  END_OF_INPUT

  initiatives   at least one, each:
    title       the initiative's name, short, each its own
    impact      the initiative's impact: what it is for, its value and what
                changed because of it, not the person's part, one line of
                about {WORDS["work_impact_line"]} words, naming no id
    paragraph   the person's own part in it, what they did and how it went
                as the points put it, about {WORDS["work_impact"]} words, fewer when
                the evidence is thin, naming no id
    evidence    what it rests on, each once, at least one: a period point by
                its id, such as G3, or a Jira issue or epic, a pull request or
                a Notion page by its link, as the brief gives it

The initiatives are recorded most recent first, by their evidence's latest day.

Prints one line of JSON: path, work_impact_content.json's path."""


def set_work_impact(prep, value):
    """Write `value`, the initiatives, to the prep `prep`'s
    work_impact_content.json, most recent first, after checking them against
    its data.json; returns the file's path. Exits, writing nothing, with every
    problem."""
    data = read_json(os.path.join(prep_dir(prep), DATA))
    if problems := work_impact_content_problems(value, data, ordered=False):
        raise SystemExit("; ".join(problems) + "\n\n" + INPUT)
    ordered = {"initiatives": by_recency(
        value["initiatives"], work_evidence(data))}
    return write_prep_file(prep, WORK_IMPACT_CONTENT, ordered)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Record the account of the person's work and its impact in the prep's work_impact_content.json.",
        epilog=INPUT, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--prep", required=True,
                        help="the prep's folder, <Person>_<YY-MM-DD>, as init_prep.py printed it")
    args = parser.parse_args(argv)
    value = stdin_json(INPUT)
    print(json.dumps({"path": set_work_impact(
        args.prep, value)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
