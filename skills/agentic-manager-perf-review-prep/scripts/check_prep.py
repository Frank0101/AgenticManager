"""Checks a prep folder, read-only: that it holds only the prep's files, its charts folder only the report's charts, and that each follows the rules it was written by, the report included.

It reads each file back, as a later step does, and applies its rules through
the same function the script that writes it checks it with first, so the two
can't differ and a file written any other way is still caught.
"""
from datetime import date
import os

from build_data import data_problems
from check_report import report_problems
from common import (CHART_FILES, CHARTS_DIR, CONTENT, FEEDBACK, content_problems, folder_problem, NOTES, ORIENTATION, PERSON, RATINGS, RAW_DIR, REVIEWS, SLACK, SOURCES,
                    SUMMARY_FILES, VALUES, DATA, company_names, expected_files, feedback_problems, notes_problems,
                    orientation_problems, period_days, person_problems, prep_dir, read_json, read_raw_work,
                    report_name, reviews_problems, slack_problems, sources_problems)


def check_prep(prep, today=None):
    """{"ok", "errors"} of the prep folder `prep`."""
    folder = prep_dir(prep)
    wanted, report = expected_files(prep), report_name(prep)
    errors = [problem] if (problem := folder_problem(folder, wanted)) else []
    files = {name for name in wanted if os.path.exists(
        os.path.join(folder, name))}
    if CHARTS_DIR in files and (problem := folder_problem(os.path.join(folder, CHARTS_DIR), set(CHART_FILES))):
        errors.append(
            f"{CHARTS_DIR}: {problem}, then run finish_report.py again")
    read = {name: read_json(os.path.join(folder, name))
            for name in files - {RAW_DIR, report, CHARTS_DIR}}
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
    for name, problems in rules.items():
        if name in read:
            errors += [
                f"{name}: {problem}" for problem in problems(read[name])]
    # data.json is built from the raw files and the summaries, so it is
    # checked once they are all there and pass, as is the report, which
    # shows them both.
    summaries = {name: read.get(file) for name, file in SUMMARY_FILES.items()}
    built = (NOTES in rules and None not in summaries.values()
             and not any(error.startswith(f"{file}:") for error in errors for file in SUMMARY_FILES.values()))
    if built and DATA in read:
        errors += [f"{DATA}: {problem}" for problem in data_problems(
            read[DATA], read_raw_work(prep), person, summaries, values)]
    # The agent's summaries are checked against the model they summarise.
    data_passes = built and DATA in read and not any(
        error.startswith(DATA) for error in errors)
    if data_passes and CONTENT in read:
        errors += [f"{CONTENT}: {problem}" for problem in content_problems(
            read[CONTENT], read[DATA]["observations"])]
    if data_passes and {report, CHARTS_DIR} <= files and CONTENT in read and not any(
            error.startswith(CONTENT) for error in errors):
        with open(os.path.join(folder, report), encoding="utf-8") as f:
            errors += [f"{report}: {problem}" for problem in report_problems(
                f.read(), read[DATA], summaries, values, folder, read[CONTENT])]
    return {"ok": not errors, "errors": errors}
