"""Checks a prep folder, read-only: that it holds only the prep's files, and that each follows the rules it was written by.

It reads each file back, as a later step does, and applies its rules through
the same function the script that writes it checks it with first, so the two
can't differ and a file written any other way is still caught.
"""
import argparse
from datetime import date, timedelta
import json
import os

from common import (CHECK_INS, FEEDBACK, IDENTITIES, NOTES, ORIENTATION, RATINGS, REQUEST, VALUES, check_ins_problems,
                    company_names, expected_files, feedback_problems, identities_problems, notes_problems,
                    orientation_problems, prep_dir, read_json, request_problems)


def check_prep(prep, today=None):
    """{"ok", "errors"} of the prep folder `prep`."""
    folder = prep_dir(prep)
    errors = []
    files = {name for name in os.listdir(folder) if not name.startswith(".")}
    wanted = expected_files()
    if files != wanted:
        extra, missing = sorted(files - wanted), sorted(wanted - files)
        errors.append("the folder must hold only " + ", ".join(sorted(wanted))
                      + (f"; move {', '.join(extra)} to your own scratch folder" if extra else "")
                      + (f"; missing {', '.join(missing)}" if missing else ""))
    read = {name: read_json(os.path.join(folder, name))
            for name in wanted & files}
    request = read.get(REQUEST)
    request_errors = request_problems(
        request, today or date.today()) if REQUEST in read else []
    values = company_names(VALUES)
    rules = {REQUEST: lambda _: request_errors, IDENTITIES: identities_problems,
             ORIENTATION: lambda value: orientation_problems(value, values)}
    # The feedback, the check-ins and the notes are checked against the
    # request's period, so only once the request itself is valid: a note's
    # day, which the prep doesn't keep, is checked at least to be in it.
    if request is not None and not request_errors:
        if FEEDBACK in read:
            ratings = company_names(RATINGS)
            rules[FEEDBACK] = lambda value: feedback_problems(
                value, request, ratings, values)
        rules[CHECK_INS] = lambda value: check_ins_problems(
            value, request, values)
        first = date.fromisoformat(request["start"])
        days = [(first + timedelta(n)).isoformat()
                for n in range((date.fromisoformat(request["end"]) - first).days + 1)]
        rules[NOTES] = lambda value: notes_problems(value, values, days)
    for name, problems in rules.items():
        if name in read:
            errors += [
                f"{name}: {problem}" for problem in problems(read[name])]
    return {"ok": not errors, "errors": errors}


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Check a prep folder: that it holds only the prep's files, that its request names the "
        "person and a period that can be reported on, that its identities say who the person is in each "
        "source, that its orientation summarises the manager's view, that its feedback holds the person's previous feedback, that its check-ins hold the person's OKRs and 1:1 notes, and that its notes summarise the manager's notes. Prints one line of JSON: ok and errors. Exits 1 if any check fails.")
    parser.add_argument("--prep", required=True,
                        help="the prep's folder, <Person>_<YY-MM-DD>, inside perf-review-preps")
    result = check_prep(parser.parse_args(argv).prep)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
