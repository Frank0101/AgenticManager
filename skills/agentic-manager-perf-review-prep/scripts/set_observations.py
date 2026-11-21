"""Records the summaries of the observations in a prep's observations_content.json, which the report shows above each table: by company value in going well and to improve, and one of the context.

The summaries are checked against data.json, the tables they summarise,
before anything is written, by the rule the final check applies, so a
summary of a value its table doesn't hold, or one that runs too long, is
refused while it is being written, not at the end. It is written whole each time, so a correction is
one more call with every summary.
"""
import argparse
import json
import os

from common import OBSERVATIONS_CONTENT, DATA, WORDS, observations_content_problems, prep_dir, read_json, stdin_json, write_prep_file

INPUT = f"""Input, on stdin: the summaries, such as:

  python3 set_observations.py --prep Jane-Doe_26-11-10 <<'END_OF_INPUT'
  {{"going_well": {{"values": {{"Ownership": "A few sentences.", "Teamwork": "A few sentences."}},
                  "also": null}},
   "to_improve": {{"values": {{"Ownership": "A few sentences."}}, "also": "A sentence."}},
   "context": "A paragraph."}}
  END_OF_INPUT

  going_well   what is going well, by company value:
    values     a summary of the points of each value worth saying, by its
               name as the brief gives it, about {WORDS["value"]} words each; at least
               one when its table groups points under a value
    also       a line on the points under no value that matter, about
               {WORDS["value"]} words, only when its table has such points; else null
  to_improve   the same, of what to improve
  context      the summary of the context, about {WORDS["context"]} words, naming
               no company value; "" exactly when its table holds no point

No text names a point's id. The report shows the values in the table's
order, whatever order you give them in.

Prints one line of JSON: path, observations_content.json's path."""


def set_observations(prep, value):
    """Write `value`, the summaries, to the prep `prep`'s observations_content.json,
    after checking them against its data.json; returns the file's path.
    Exits, writing nothing, with every problem."""
    data = read_json(os.path.join(prep_dir(prep), DATA))
    if problems := observations_content_problems(value, data):
        raise SystemExit("; ".join(problems) + "\n\n" + INPUT)
    return write_prep_file(prep, OBSERVATIONS_CONTENT, value)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Record the summary of each table of observations in the prep's observations_content.json.",
        epilog=INPUT, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--prep", required=True,
                        help="the prep's folder, <Person>_<YY-MM-DD>, as init_prep.py printed it")
    args = parser.parse_args(argv)
    value = stdin_json(INPUT)
    print(json.dumps({"path": set_observations(
        args.prep, value)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
