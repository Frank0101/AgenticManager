"""Records a summary of what the manager gives: the current manager feedback on a prep's person, the other feedback given in the period, or the previous feedback.

One script serves the three, as they are recorded the same way and differ
only in their file. The agent writes the summary as JSON on stdin, a quoted
here-document, so nothing in it needs escaping. A point's values must be the
company's, as rules.py prints them. It is checked before anything is
written, by the rules the final check applies, and written whole each time,
in the order given, so a correction is one more call with all of it.
"""
import argparse
import json

from common import (FEEDBACK_FILES, SUMMARY_HELP, VALUES, company_names, feedback_problems, prep_dir, stdin_json,
                    write_prep_file)

# What each kind is of, as the manager gives it.
KINDS = {"manager": "the current manager feedback on the person",
         "other": "the other feedback given in the period",
         "previous": "the previous feedback, usually the previous official feedback"}
INPUT = """\
the text summarised in its parts, such as:

  python3 set_summary.py --prep Jane-Doe_26-11-10 --of other <<'END_OF_INPUT'
  {
    "going_well": [{"point": "Jane has led the billing migration well since May", "values": ["Ownership"]}],
    "to_improve": [{"point": "Jane could share progress with the wider team more often", "values": ["Teamwork"]}],
    "context": ["Jane came back from a long leave in May"]
  }
  END_OF_INPUT

""" + SUMMARY_HELP + """

Each part is a list of points, [] when the text says nothing of it, all three
when it says nothing of the person.

Prints one line of JSON: path, the file written."""


def set_summary(prep, kind, value):
    """Write `value`, the summary of the kind `kind`, one of KINDS, to the
    prep `prep`'s file for it, after checking it; returns the file's path.
    Exits, writing nothing, with every problem."""
    prep_dir(prep)  # exits if the prep isn't there
    if problems := feedback_problems(value, kind, company_names(VALUES)):
        raise SystemExit("; ".join(problems) + "\n\n" + input_help(kind))
    return write_prep_file(prep, FEEDBACK_FILES[kind], value)


def input_help(kind):
    """What to send on stdin for the kind `kind`, with a command to copy."""
    return f"Input, on stdin, for --of {kind}: {INPUT}"


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Record a summary of what the manager gave: " + "; ".join(
            f"{kind}, {what}" for kind, what in KINDS.items()) + ".",
        epilog=input_help("other"), formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--prep", required=True,
                        help="the prep's folder, <Person>_<YY-MM-DD>, as init_prep.py printed it")
    parser.add_argument("--of", required=True, choices=list(KINDS),
                        help="what the summary is of: " + "; ".join(f"{kind}, {what}" for kind, what in KINDS.items()))
    args = parser.parse_args(argv)
    value = stdin_json(input_help(args.of))
    print(json.dumps({"path": set_summary(
        args.prep, args.of, value)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
