"""Records a prep's person's previous feedback in feedback.json, and prints the rules it follows.

A rating must be one of the company's, read from the config here, so the agent
learns the scale from the rules this prints rather than from the config;
ratings hold no secrets. Feedback is checked before anything is written, by
the rules the final check applies, and written whole each time, so a
correction from the manager is one more call with every piece in it.
"""
import argparse
import json
import os

from common import (FEEDBACK, RATINGS, REQUEST, SUMMARY_PARTS, company_setting, earliest_review_end, feedback_order,
                    feedback_problems, prep_dir, read_json, stdin_json, write_prep_file)

INPUT = """Input to write, on stdin: every piece of previous feedback, such as:

  python3 set_feedback.py write --prep Jane-Doe_26-11-10 <<'END_OF_INPUT'
  {"reviews": [
    {"start": "2026-01-01", "end": "2026-06-30", "rating": "Meets",
     "going_well": ["Delivered the billing migration on time"],
     "to_improve": ["Lead a design review on her own"],
     "context": ["Moved to the payments team in March"]},
    {"start": null, "end": null, "rating": null,
     "going_well": ["Built a community of practice that reaches other teams"],
     "to_improve": [], "context": []}
  ]}
  END_OF_INPUT

  start, end  the period the feedback covers, as YYYY-MM-DD, or null when
              it gives no day
  rating      the rating it gave, one of the company's, as rules prints them,
              or null when it gives none of them
""" + "\n".join(f"  {part:<11} {meaning}" for part, meaning in SUMMARY_PARTS.items()) + """

Each part is a list of points, [] when the feedback says nothing of it.
Write {"reviews": []} when the person has no previous feedback. It's written
with what has days first, oldest first, then the rest in the order given.

Prints one line of JSON: path, the file written, and feedback.
"""
RULES = """rules prints one line of JSON:
  ratings        the company's ratings, lowest first: rating and meaning
  earliest_end   the first day dated feedback may end on, YYYY-MM-DD, 2
                 years before the period starts: older feedback is left out,
                 and undated feedback is never checked
  latest_end     the last, the period's end
  parts          each part of a piece's summary, with what it holds
"""


def rules(prep):
    """{ratings, earliest_end, latest_end, parts}: what the previous
    feedback of the prep `prep` must follow."""
    request = read_json(os.path.join(prep_dir(prep), REQUEST))
    return {"ratings": company_setting(RATINGS), "earliest_end": earliest_review_end(request).isoformat(),
            "latest_end": request["end"], "parts": SUMMARY_PARTS}


def set_feedback(prep, feedback):
    """Write the previous feedback `feedback` to the prep `prep`'s
    feedback.json, in feedback_order(), after checking it; returns the file's
    path. Exits, writing nothing, with every problem."""
    request = read_json(os.path.join(prep_dir(prep), REQUEST))
    ratings = [entry["rating"] for entry in company_setting(RATINGS)]
    if problems := feedback_problems(feedback, request, ratings):
        raise SystemExit("; ".join(problems) + "\n\n" + INPUT)
    reviews = sorted(feedback["reviews"], key=feedback_order)
    return write_prep_file(prep, FEEDBACK, {"reviews": reviews})


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Record the prep's person's previous feedback, or print the rules it follows.",
        epilog=RULES + "\n" + INPUT, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    for name, help in (("rules", "print the company's ratings, the days feedback may end on and the parts of "
                        "its summary"), ("write", "record all previous feedback, read as JSON on stdin")):
        command = commands.add_parser(name, help=help)
        command.add_argument("--prep", required=True,
                             help="the prep's folder, <Person>_<YY-MM-DD>, as init_prep.py printed it")
    args = parser.parse_args(argv)
    if args.command == "rules":
        print(json.dumps(rules(args.prep), ensure_ascii=False))
        return
    feedback = stdin_json(INPUT)
    path = set_feedback(args.prep, feedback)
    print(json.dumps(
        {"path": path, "feedback": read_json(path)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
