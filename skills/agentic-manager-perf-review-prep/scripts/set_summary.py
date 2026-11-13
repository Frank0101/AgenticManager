"""Records a summary of what the manager gives: their view of a prep's person, the person's previous reviews, or the period's feedback.

One script serves the three, as they are recorded the same way and differ
only in their file and rules. The agent writes the summary as JSON on stdin,
a quoted here-document, so nothing in it needs escaping. A point's values,
and a review's rating, must be the company's, as rules.py prints them. It is
checked before anything is written, by the rules the final check applies,
and written whole each time, in the order given, so a correction is one
more call with all of it.
"""
import argparse
import json

from common import (FEEDBACK, ORIENTATION, RATINGS, REVIEWS, SUMMARY_HELP, VALUES, company_names, feedback_problems,
                    orientation_problems, prep_dir, reviews_problems, stdin_json, write_prep_file)

PIECES_HELP = """
Each part is a list of points, [] when the piece says nothing of it. Write
{"pieces": []} when the manager has none. List them from the most recent,
those with no period first: they're written in the order given."""
# Each kind: the file it's written to, why a value isn't one, and its input.
KINDS = {
    "orientation": (ORIENTATION, lambda value: orientation_problems(value, company_names(VALUES)), """\
the manager's view, summarised in its parts, such as:

  python3 set_summary.py --prep Jane-Doe_26-11-10 --of orientation <<'END_OF_INPUT'
  {
    "going_well": [{"point": "Has led the billing migration well since May", "values": ["Ownership"]}],
    "to_improve": [{"point": "Could share progress with the wider team more often", "values": ["Teamwork"]}],
    "context": ["Came back from a long leave in May"]
  }
  END_OF_INPUT

""" + SUMMARY_HELP + """

Each part is a list of points, [] when the manager said nothing of it."""),
    "reviews": (REVIEWS, lambda value: reviews_problems(value, company_names(RATINGS), company_names(VALUES)), """\
every previous review, such as:

  python3 set_summary.py --prep Jane-Doe_26-11-10 --of reviews <<'END_OF_INPUT'
  {"pieces": [
    {"period": "Mid Year Review 2026", "rating": "Meets",
     "going_well": [{"point": "Delivered the billing migration on time", "values": ["Ownership"]}],
     "to_improve": [{"point": "Could lead a design review alone", "values": []}],
     "context": ["Moved to the payments team in March"]},
    {"period": null, "rating": null,
     "going_well": [{"point": "Built a community of practice that reaches other teams",
                     "values": ["Teamwork", "Ownership"]}],
     "to_improve": [], "context": []}
  ]}
  END_OF_INPUT

  period      the period the review covers, as it names it, such as a date
              or "Mid Year Review 2026", or null when it names none
  rating      the rating it gave, one of the company's, as rules.py prints
              them, or null when it gives none of them
""" + SUMMARY_HELP + PIECES_HELP),
    "feedback": (FEEDBACK, lambda value: feedback_problems(value, company_names(VALUES)), """\
every piece of the period's feedback, such as:

  python3 set_summary.py --prep Jane-Doe_26-11-10 --of feedback <<'END_OF_INPUT'
  {"pieces": [
    {"period": "Q3 2026",
     "going_well": [{"point": "Agreed to own the billing migration and has kept to its plan",
                     "values": ["Ownership"]}],
     "to_improve": [{"point": "Agreed to share progress with the wider team every week",
                     "values": ["Teamwork"]}],
     "context": []},
    {"period": null,
     "going_well": [{"point": "Was thanked by the support team for fixing a billing bug the same day",
                     "values": ["Ownership"]}],
     "to_improve": [], "context": []}
  ]}
  END_OF_INPUT

  period      the period the piece covers, as it names it, such as a date,
              "Q3 2026" or "1:1 of 08/10/2026", or null when it names none
""" + SUMMARY_HELP + PIECES_HELP),
}
OUTPUT = "Prints one line of JSON: path, the file written."


def set_summary(prep, kind, value):
    """Write `value`, the summary of the kind `kind`, one of KINDS, to the
    prep `prep`'s file for it, after checking it; returns the file's path.
    Exits, writing nothing, with every problem."""
    prep_dir(prep)  # exits if the prep isn't there
    name, problems_of, _ = KINDS[kind]
    if problems := problems_of(value):
        raise SystemExit("; ".join(problems) + "\n\n" + input_help(kind))
    return write_prep_file(prep, name, value)


def input_help(kind):
    """What to send on stdin for the kind `kind`, with a command to copy."""
    return f"Input, on stdin, for --of {kind}: {KINDS[kind][2]}\n\n{OUTPUT}"


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Record a summary of what the manager gave: their view of the prep's person "
        "(orientation), the person's previous reviews (reviews), or the period's feedback (feedback).",
        epilog="\n\n".join(input_help(kind) for kind in KINDS), formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--prep", required=True,
                        help="the prep's folder, <Person>_<YY-MM-DD>, as init_prep.py printed it")
    parser.add_argument("--of", required=True, choices=list(KINDS),
                        help="what the summary is of: orientation, the manager's view; reviews, the previous reviews; or "
                        "feedback, the period's feedback")
    args = parser.parse_args(argv)
    value = stdin_json(input_help(args.of))
    print(json.dumps({"path": set_summary(
        args.prep, args.of, value)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
