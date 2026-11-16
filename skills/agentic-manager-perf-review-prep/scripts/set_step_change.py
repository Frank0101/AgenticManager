"""Records the step change from the latest previous review in a prep's step_change.json, which the report shows after the observations.

The step change is checked against data.json, the previous reviews and the
period's points it cites, before anything is written, by the rule the final
check applies, so a row that cites a point that isn't there, or a to-improve
point of the review left without a row, is refused while it is being
written, not at the end. It is written whole each time, so a correction is
one more call with every row.
"""
import argparse
import json
import os

from common import (DATA, OBSERVATIONS_WORDS, STEP_CHANGE, STEP_CHANGE_PARTS, prep_dir, read_json, stdin_json,
                    step_change_problems, write_prep_file)

INPUT = f"""Input, on stdin: the step change, such as:

  python3 set_step_change.py --prep Jane-Doe_26-11-10 <<'END_OF_INPUT'
  {{"summary": "One or more paragraphs.",
   "rows": [{{"review_point": "R-I1", "change": "improved", "evidence": ["G2"]}},
            {{"review_point": "R-I2", "change": "improved", "evidence": []}},
            {{"review_point": "R-G1", "change": "worsened", "evidence": ["I1", "I3"]}},
            {{"review_point": null, "change": "new_context", "evidence": ["C1"]}}]}}
  END_OF_INPUT

  summary       how the period compares with the brief's latest previous review,
                about {OBSERVATIONS_WORDS["step_change"]} words, fewer when little changed
  rows          a row per review point, as change says which, each:
    review_point  the id of a point of the latest review, such as R-I1, once,
                  or null for a period context point the review didn't have
    change        for a to-improve point, {", ".join(STEP_CHANGE_PARTS["to_improve"])}: every
                  one has a row; for a going-well point, {" or ".join(STEP_CHANGE_PARTS["going_well"])},
                  only when the period shows it; for a context point that
                  changed, {", ".join(STEP_CHANGE_PARTS["context"])}; for a row with no
                  review_point, {", ".join(STEP_CHANGE_PARTS[None])}
    evidence      the ids of the period's points that show it, such as G2,
                  at least one, but [] for an improved point no longer raised;
                  a period context point among them when review_point is null

Prints one line of JSON: path, step_change.json's path."""


def set_step_change(prep, value):
    """Write `value`, the step change, to the prep `prep`'s
    step_change.json, after checking it against its data.json; returns the
    file's path. Exits, writing nothing, with every problem."""
    data = read_json(os.path.join(prep_dir(prep), DATA))
    if problems := step_change_problems(value, data["observations"], data["reviews"]):
        raise SystemExit("; ".join(problems) + "\n\n" + INPUT)
    return write_prep_file(prep, STEP_CHANGE, value)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Record the step change from the latest previous review in the prep's step_change.json.",
        epilog=INPUT, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--prep", required=True,
                        help="the prep's folder, <Person>_<YY-MM-DD>, as init_prep.py printed it")
    args = parser.parse_args(argv)
    value = stdin_json(INPUT)
    print(json.dumps({"path": set_step_change(
        args.prep, value)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
