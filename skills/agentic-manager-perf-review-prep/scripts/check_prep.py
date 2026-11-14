"""Checks a prep folder, read-only: that it holds only the prep's files, and that each follows the rules it was written by.

It reads each file back, as a later step does, and applies its rules through
the same function the script that writes it checks it with first, so the two
can't differ and a file written any other way is still caught.
"""
import argparse
from datetime import date
import json
import os

from common import (FEEDBACK, NOTES, ORIENTATION, PERSON, RATINGS, RAW_DIR, REVIEWS, SLACK, SOURCES, VALUES, WORK,
                    company_names, expected_files, feedback_problems, notes_problems, orientation_problems,
                    period_days, person_problems, prep_dir, read_json, read_raw_work, reviews_problems,
                    slack_problems, sources_problems, work_from_raw_problems, work_problems)


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
            for name in (wanted & files) - {RAW_DIR}}
    person = read.get(PERSON)
    person_errors = person_problems(
        person, today or date.today()) if PERSON in read else []
    values = company_names(VALUES)
    # Once the prep is complete, the person is in every source.
    rules = {PERSON: lambda value: person_errors + (
        sources_problems(value.get("sources"), SOURCES) if isinstance(value, dict) else []),
        ORIENTATION: lambda value: orientation_problems(value, values),
        FEEDBACK: lambda value: feedback_problems(value, values)}
    if REVIEWS in read:
        ratings = company_names(RATINGS)
        rules[REVIEWS] = lambda value: reviews_problems(
            value, ratings, values)
    # Everything gathered is checked against the review's period, so only
    # once the person and period are valid: a day a point of the notes or
    # the Slack summary cites, or an item of work is dated, must be in it.
    if person is not None and not person_errors:
        days = period_days(person)
        rules[NOTES] = lambda value: notes_problems(value, values, days)
        rules[SLACK] = lambda value: slack_problems(value, values, days)
        rules[WORK] = lambda value: work_problems(value, days) or work_from_raw_problems(
            value, read_raw_work(prep), days)
    for name, problems in rules.items():
        if name in read:
            errors += [
                f"{name}: {problem}" for problem in problems(read[name])]
    return {"ok": not errors, "errors": errors}


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Check a prep folder: that it holds only the prep's files, that its person.json names the "
        "person, a period that can be reported on and who the person is in each source, that its orientation summarises the manager's view, that its reviews hold the person's previous reviews, that its feedback holds what the person heard during the period, that its notes summarise the manager's notes, that its Slack summary holds what the person's messages show, and that its work holds the data points. Prints one line of JSON: ok and errors. Exits 1 if any check fails.")
    parser.add_argument("--prep", required=True,
                        help="the prep's folder, <Person>_<YY-MM-DD>, inside perf-review-preps")
    result = check_prep(parser.parse_args(argv).prep)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
