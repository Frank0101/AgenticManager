"""Checks a prep folder, read-only: that it holds only the prep's files, and that each follows the rules it was written by.

It reads each file back, as a later step does, and applies its rules through
the same function the script that writes it checks it with first, so the two
can't differ and a file written any other way is still caught.
"""
import argparse
from datetime import date
import json
import os

from common import IDENTITIES, REQUEST, expected_files, identities_problems, prep_dir, read_json, request_problems


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
    if REQUEST in files:
        errors += [f"{REQUEST}: {problem}" for problem in
                   request_problems(read_json(os.path.join(folder, REQUEST)), today or date.today())]
    if IDENTITIES in files:
        errors += [f"{IDENTITIES}: {problem}" for problem in
                   identities_problems(read_json(os.path.join(folder, IDENTITIES)))]
    return {"ok": not errors, "errors": errors}


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Check a prep folder: that it holds only the prep's files, that its request names the "
        "person and a period that can be reported on, and that its identities say who the person is in each "
        "source. Prints one line of JSON: ok and errors. Exits 1 if any check fails.")
    parser.add_argument("--prep", required=True,
                        help="the prep's folder, <Person>_<YY-MM-DD>, inside perf-review-preps")
    result = check_prep(parser.parse_args(argv).prep)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
