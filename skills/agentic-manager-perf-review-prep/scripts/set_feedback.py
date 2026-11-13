"""Records a prep's person's previous feedback in feedback.json.

The agent writes the feedback as JSON on stdin, a quoted here-document, so
nothing in it needs escaping. A rating and a point's values must be the
company's, as rules.py prints them. Feedback is checked before anything is
written, by the rules the final check applies, and written whole each time,
so a correction from the manager is one more call with every piece in it.
"""
import argparse
import json
import os

from common import (FEEDBACK, PERSON, RATINGS, SUMMARY_HELP, VALUES, company_names, feedback_problems, pieces_order,
                    prep_dir, read_json, stdin_json, write_prep_file)

INPUT = """Input, on stdin: every piece of previous feedback, such as:

  python3 set_feedback.py --prep Jane-Doe_26-11-10 <<'END_OF_INPUT'
  {"pieces": [
    {"start": "2026-01-01", "end": "2026-06-30", "rating": "Meets",
     "going_well": [{"point": "Delivered the billing migration on time", "values": ["Ownership"]}],
     "to_improve": [{"point": "Could lead a design review alone", "values": []}],
     "context": ["Moved to the payments team in March"]},
    {"start": null, "end": null, "rating": null,
     "going_well": [{"point": "Built a community of practice that reaches other teams",
                     "values": ["Teamwork", "Ownership"]}],
     "to_improve": [], "context": []}
  ]}
  END_OF_INPUT

  start, end  the period the feedback covers, as YYYY-MM-DD, or null when
              it gives no day
  rating      the rating it gave, one of the company's, as rules.py prints
              them, or null when it gives none of them
""" + SUMMARY_HELP + """

Each part is a list of points, [] when the feedback says nothing of it.
Write {"pieces": []} when the person has no previous feedback. It's written
with what has days first, oldest first, then the rest in the order given.

Prints one line of JSON: path, the file written, and feedback.
"""


def set_feedback(prep, feedback):
    """Write the previous feedback `feedback` to the prep `prep`'s
    feedback.json, in pieces_order(), after checking it; returns the file's
    path. Exits, writing nothing, with every problem."""
    person = read_json(os.path.join(prep_dir(prep), PERSON))
    if problems := feedback_problems(feedback, person, company_names(RATINGS), company_names(VALUES)):
        raise SystemExit("; ".join(problems) + "\n\n" + INPUT)
    pieces = sorted(feedback["pieces"], key=pieces_order)
    return write_prep_file(prep, FEEDBACK, {"pieces": pieces})


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Record the prep's person's previous feedback.",
        epilog=INPUT, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--prep", required=True,
                        help="the prep's folder, <Person>_<YY-MM-DD>, as init_prep.py printed it")
    args = parser.parse_args(argv)
    feedback = stdin_json(INPUT)
    path = set_feedback(args.prep, feedback)
    print(json.dumps(
        {"path": path, "feedback": read_json(path)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
