"""Records the summary of each table of observations in a prep's content.json, which the report shows above each table.

The summaries are checked against data.json, the tables they summarise,
before anything is written, by the rule the final check applies, so a
summary that misses a value or runs too long is refused while it is being
written, not at the end. It is written whole each time, so a correction is
one more call with every summary.
"""
import argparse
import json
import os

from common import CONTENT, DATA, OBSERVATIONS_WORDS, content_problems, prep_dir, read_json, stdin_json, write_prep_file

INPUT = f"""Input, on stdin: the summary of each table, such as:

  python3 set_content.py --prep Jane-Doe_26-11-10 <<'END_OF_INPUT'
  {{"going_well": "One or more paragraphs.", "to_improve": "One or more paragraphs.",
   "context": "A paragraph."}}
  END_OF_INPUT

  going_well   the summary of what is going well, about {OBSERVATIONS_WORDS["going_well"]} words, fewer
               for a table of few points,
               naming every company value its table groups points under
  to_improve   the same, of what to improve
  context      the same, of the context, about {OBSERVATIONS_WORDS["context"]} words, naming
               no company value

A summary is empty, "", exactly when its table holds no point.

Prints one line of JSON: path, content.json's path."""


def set_content(prep, value):
    """Write `value`, the summaries, to the prep `prep`'s content.json,
    after checking them against its data.json; returns the file's path.
    Exits, writing nothing, with every problem."""
    data = read_json(os.path.join(prep_dir(prep), DATA))
    if problems := content_problems(value, data["observations"]):
        raise SystemExit("; ".join(problems) + "\n\n" + INPUT)
    return write_prep_file(prep, CONTENT, value)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Record the summary of each table of observations in the prep's content.json.",
        epilog=INPUT, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--prep", required=True,
                        help="the prep's folder, <Person>_<YY-MM-DD>, as init_prep.py printed it")
    args = parser.parse_args(argv)
    value = stdin_json(INPUT)
    print(json.dumps({"path": set_content(
        args.prep, value)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
