"""Checks a prep folder, read-only: that it holds only the prep's files, and that each follows the rules it was written by.

It reads each file back, as a later step does, and applies its rules through
the same function the script that writes it checks it with first, so the two
can't differ and a file written any other way is still caught.
"""
import argparse
from datetime import date
import json
import os

from common import (FEEDBACK, IDENTITIES, ORIENTATION, RATINGS, REQUEST, company_setting, expected_files,
                    feedback_problems, identities_problems, orientation_problems, prep_dir, read_json,
                    request_problems)


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
    rules = {REQUEST: lambda _: request_errors, IDENTITIES: identities_problems,
             ORIENTATION: orientation_problems}
    # The feedback is checked against the request's period, so only once the
    # request itself is valid.
    if FEEDBACK in read and REQUEST in read and not request_errors:
        ratings = [entry["rating"] for entry in company_setting(RATINGS)]
        rules[FEEDBACK] = lambda value: feedback_problems(
            value, request, ratings)
    for name, problems in rules.items():
        if name in read:
            errors += [
                f"{name}: {problem}" for problem in problems(read[name])]
    return {"ok": not errors, "errors": errors}


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Check a prep folder: that it holds only the prep's files, that its request names the "
        "person and a period that can be reported on, that its identities say who the person is in each "
        "source, that its orientation summarises the manager's view, and that its feedback holds the person's previous feedback. Prints one line of JSON: ok and errors. Exits 1 if any check fails.")
    parser.add_argument("--prep", required=True,
                        help="the prep's folder, <Person>_<YY-MM-DD>, inside perf-review-preps")
    result = check_prep(parser.parse_args(argv).prep)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
