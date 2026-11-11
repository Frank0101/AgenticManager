"""Records a prep's person's check-ins, their OKRs and 1:1 notes, in check-ins.json.

The agent writes the check-ins as JSON on stdin, a quoted here-document, so
nothing in them needs escaping. A point's values must be the company's, as
rules.py prints them. They are checked before anything is written,
by the rules the final check applies, and written whole each time, so a
correction from the manager is one more call with every piece in it.
"""
import argparse
import json
import os

from common import (CHECK_INS, REQUEST, SUMMARY_HELP, VALUES, check_ins_problems, company_names, pieces_order,
                    prep_dir, read_json, stdin_json, write_prep_file)

INPUT = """Input, on stdin: every piece shared with the person, such as:

  python3 set_check_ins.py --prep Jane-Doe_26-11-10 <<'END_OF_INPUT'
  {"pieces": [
    {"start": "2026-07-01", "end": "2026-09-30",
     "going_well": [{"point": "Agreed to own the billing migration and has kept to its plan",
                     "values": ["Ownership"]}],
     "to_improve": [{"point": "Agreed to share progress with the wider team every week",
                     "values": ["Teamwork"]}],
     "context": []},
    {"start": null, "end": null,
     "going_well": [], "to_improve": [],
     "context": ["Plans to move to the payments team next year"]}
  ]}
  END_OF_INPUT

  start, end  the period the piece covers, as YYYY-MM-DD, or null when it
              gives no day; a dated piece must overlap the prep's period
""" + SUMMARY_HELP + """

Each part is a list of points, [] when the piece says nothing of it. Write
{"pieces": []} when the manager has none. It's written with what has days
first, oldest first, then the rest in the order given.

Prints one line of JSON: path, the file written, and check_ins.
"""


def set_check_ins(prep, check_ins):
    """Write the check-ins `check_ins` to the prep `prep`'s check-ins.json,
    in pieces_order(), after checking them; returns the file's path. Exits,
    writing nothing, with every problem."""
    request = read_json(os.path.join(prep_dir(prep), REQUEST))
    if problems := check_ins_problems(check_ins, request, company_names(VALUES)):
        raise SystemExit("; ".join(problems) + "\n\n" + INPUT)
    pieces = sorted(check_ins["pieces"], key=pieces_order)
    return write_prep_file(prep, CHECK_INS, {"pieces": pieces})


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Record the prep's person's check-ins: their OKRs and 1:1 notes.",
        epilog=INPUT, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--prep", required=True,
                        help="the prep's folder, <Person>_<YY-MM-DD>, as init_prep.py printed it")
    args = parser.parse_args(argv)
    check_ins = stdin_json(INPUT)
    path = set_check_ins(args.prep, check_ins)
    print(json.dumps(
        {"path": path, "check_ins": read_json(path)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
