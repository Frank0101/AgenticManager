"""Records a comparison of a prep, the step change from the latest previous review in step_change.json or the check of the manager's view in view_check.json, which the report shows after the observations.

A comparison is checked against data.json, its baseline and the period's
points it cites, before anything is written, by the rule the final check
applies, so a row that cites a point that isn't there, or a baseline point
left without a row, is refused while it is being written, not at the end.
It is written whole each time, so a correction is one more call with every
row. The two differ only by their Comparison, so one script records both,
each by its task's name.
"""
import argparse
import json
import os

from common import (DATA, OBSERVATIONS_WORDS, STEP_CHANGE_COMPARISON, STEP_CHANGE_PARTS,
                    VIEW_CHECK_COMPARISON, VIEW_CHECK_PARTS, data_comparison_problems, prep_dir, read_json,
                    stdin_json, write_prep_file)

# Each comparison's input, by its task's name, as --of takes it.
INPUTS = {STEP_CHANGE_COMPARISON.task: f"""Input, with --of {STEP_CHANGE_COMPARISON.task}, on stdin: the step change, such as:

  python3 set_comparison.py --of {STEP_CHANGE_COMPARISON.task} --prep Jane-Doe_26-11-10 <<'END_OF_INPUT'
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

Prints one line of JSON: path, {STEP_CHANGE_COMPARISON.file}'s path.""",
          VIEW_CHECK_COMPARISON.task: f"""Input, with --of {VIEW_CHECK_COMPARISON.task}, on stdin: the view check, such as:

  python3 set_comparison.py --of {VIEW_CHECK_COMPARISON.task} --prep Jane-Doe_26-11-10 <<'END_OF_INPUT'
  {{"summary": "One or more paragraphs.",
   "rows": [{{"view_point": "V-G1", "check": "confirmed", "evidence": ["G2", "G3"]}},
            {{"view_point": "V-I1", "check": "contradicted", "evidence": ["G1"]}},
            {{"view_point": "V-C1", "check": "little_support", "evidence": []}},
            {{"view_point": null, "check": "not_in_view", "evidence": ["I1", "I2"]}}]}}
  END_OF_INPUT

  summary       how the period's evidence bears on the brief's manager's view,
                about {OBSERVATIONS_WORDS["view_check"]} words, fewer when there is little to say
  rows          a row per point of the view, and one per strong theme it misses, each:
    view_point    the id of a point of the view, such as V-I1, once,
                  or null for a strong theme of the period the view doesn't mention
    check         for a point of the view, {", ".join(VIEW_CHECK_PARTS["going_well"])}: every
                  one has a row; for a row with no view_point, {", ".join(VIEW_CHECK_PARTS[None])}
    evidence      the ids of the period's points that show it, such as G2,
                  at least one, but the little there is, or [], for little_support

Prints one line of JSON: path, {VIEW_CHECK_COMPARISON.file}'s path."""}
BY_TASK = {comparison.task: comparison for comparison in (
    STEP_CHANGE_COMPARISON, VIEW_CHECK_COMPARISON)}


def set_comparison(prep, comparison, value):
    """Write `value` to the file of `comparison`, a Comparison, in the prep
    `prep`, after checking it against its data.json; returns the file's
    path. Exits, writing nothing, with every problem and the comparison's
    input."""
    data = read_json(os.path.join(prep_dir(prep), DATA))
    if problems := data_comparison_problems(comparison, value, data):
        raise SystemExit("; ".join(problems) + "\n\n" +
                         INPUTS[comparison.task])
    return write_prep_file(prep, comparison.file, value)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Record a comparison in the prep: the step change from the latest previous review in "
        "step_change.json, or the check of the manager's view against the period's evidence in view_check.json.",
        epilog="\n\n".join(INPUTS.values()), formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--of", required=True, choices=list(BY_TASK),
                        help="the comparison: step-change, from the latest previous review, or view-check, of the "
                        "manager's view")
    parser.add_argument("--prep", required=True,
                        help="the prep's folder, <Person>_<YY-MM-DD>, as init_prep.py printed it")
    args = parser.parse_args(argv)
    value = stdin_json(INPUTS[args.of])
    print(json.dumps({"path": set_comparison(
        args.prep, BY_TASK[args.of], value)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
