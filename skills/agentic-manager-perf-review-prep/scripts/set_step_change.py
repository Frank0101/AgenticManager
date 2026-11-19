"""Records the step change of a prep, how the period compares with the previous feedback, in its step_change_content.json, which the report shows after the observations.

It is checked against data.json, the previous feedback and the period's
points it cites, before anything is written, by the rule the final check
applies, so a row that cites a point that isn't there, or a previous
feedback point left without a row, is refused while it is being written,
not at the end. It is written whole each time, so a correction is one more
call with every row.
"""
import argparse
import json
import os

from common import (DATA, OBSERVATIONS_WORDS, STEP_CHANGE_CONTENT, STEP_CHANGE_PARTS,
                    step_change_content_problems, prep_dir, read_json, stdin_json, write_prep_file)

INPUT = f"""Input, on stdin: the step change, such as:

  python3 set_step_change.py --prep Jane-Doe_26-11-10 <<'END_OF_INPUT'
  {{"summary": "One or more paragraphs.",
   "rows": [{{"previous_point": "P-I1", "change": "improved", "evidence": ["G2"]}},
            {{"previous_point": "P-I2", "change": "improved", "evidence": []}},
            {{"previous_point": "P-G1", "change": "worsened", "evidence": ["I1", "I3"]}},
            {{"previous_point": null, "change": "new_context", "evidence": ["C1"]}}]}}
  END_OF_INPUT

  summary       how the period compares with the brief's previous feedback,
                about {OBSERVATIONS_WORDS["step_change"]} words, fewer when little changed
  rows          at least a row per to-improve point of the previous feedback, the others only as change says, each:
    previous_point  the id of a point of the previous feedback, such as P-I1, or null
                  for a period context point it didn't have; a point whose aspects
                  went differently may have a row for each
    change        for a to-improve point, {", ".join(STEP_CHANGE_PARTS["to_improve"])}: every
                  one has a row; for a going-well point, {" or ".join(STEP_CHANGE_PARTS["going_well"])},
                  only when the period shows it; for a context point that
                  changed, {", ".join(STEP_CHANGE_PARTS["context"])}; for a row with no
                  previous_point, {", ".join(STEP_CHANGE_PARTS[None])}
    evidence      the ids of the period's points that show it, such as G2,
                  at least one, but [] for an improved point no longer raised;
                  a period context point among them when previous_point is null

Prints one line of JSON: path, {STEP_CHANGE_CONTENT}'s path."""


def set_step_change(prep, value):
    """Write `value`, the step change, to the prep `prep`'s
    step_change_content.json, after checking it against its data.json;
    returns the file's path. Exits, writing nothing, with every problem and
    the input."""
    data = read_json(os.path.join(prep_dir(prep), DATA))
    if problems := step_change_content_problems(value, data):
        raise SystemExit("; ".join(problems) + "\n\n" + INPUT)
    return write_prep_file(prep, STEP_CHANGE_CONTENT, value)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Record the step change from the previous feedback in the prep's step_change_content.json.",
        epilog=INPUT, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--prep", required=True,
                        help="the prep's folder, <Person>_<YY-MM-DD>, as init_prep.py printed it")
    args = parser.parse_args(argv)
    value = stdin_json(INPUT)
    print(json.dumps({"path": set_step_change(
        args.prep, value)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
