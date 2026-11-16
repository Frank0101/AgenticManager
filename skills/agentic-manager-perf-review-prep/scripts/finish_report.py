"""Finishes a prep's report: checks the agent's content.json, step_change.json and view_check.json, writes the report and draws its charts from data.json, then checks the whole prep.

The one command of the step: each part is a module of its own, the report
make_report.py's, the charts make_charts.py's and the check check_prep.py's, which reads back every file of the prep, the
report as check_report.py does, and this script runs them in order, so each
does one thing. It prints only
what needs attention.
"""
import argparse
import json
import os

from check_prep import check_prep
from common import (CONTENT, DATA, PERSON, STEP_CHANGE, STEP_CHANGE_COMPARISON, VIEW_CHECK, VIEW_CHECK_COMPARISON,
                    content_problems, data_comparison_problems, prep_dir, read_json)
from make_charts import write_charts
from make_report import write_report


def finish(prep):
    """Write the prep `prep`'s report and charts from data.json,
    content.json, step_change.json and view_check.json, then check the whole
    prep; returns {report, problems}, the report's path and what the check
    found. With one of the agent's files missing or breaking a rule, it
    writes nothing, and the report is null and the problems theirs, each
    naming its field."""
    folder = prep_dir(prep)
    person, data = read_json(os.path.join(folder, PERSON)), read_json(
        os.path.join(folder, DATA))
    missing = [f"{name} is missing: write it, as step 8's {task} task says"
               for name, task in ((CONTENT, "observations"),
                                  *((comparison.file, comparison.task) for comparison in (STEP_CHANGE_COMPARISON, VIEW_CHECK_COMPARISON)))
               if not os.path.exists(os.path.join(folder, name))]
    if missing:
        return {"report": None, "problems": missing}
    content, step_change, view_check = (read_json(os.path.join(folder, name))
                                        for name in (CONTENT, STEP_CHANGE, VIEW_CHECK))
    if problems := (content_problems(content, data["observations"])
                    + data_comparison_problems(STEP_CHANGE_COMPARISON, step_change, data)
                    + data_comparison_problems(VIEW_CHECK_COMPARISON, view_check, data)):
        return {"report": None, "problems": problems}
    write_charts(prep, data)
    path = write_report(prep, person, data, content,
                        step_change, view_check)
    return {"report": path, "problems": check_prep(prep)["errors"]}


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Check the prep's content.json, step_change.json and view_check.json, write its report, "
        "<Person>_Review_Prep.md, and its charts from data.json and those three, then check "
        "the whole prep: that its folder holds only the prep's files, each following the rules it was written by, "
        "and that the report shows data.json.",
        epilog="Prints one line of JSON: report, the report's path, and problems, what the check found, "
        "empty when it passes. Exits 1 when it finds any.")
    parser.add_argument("--prep", required=True,
                        help="the prep's folder, <Person>_<YY-MM-DD>, as init_prep.py printed it")
    args = parser.parse_args(argv)
    result = finish(args.prep)
    print(json.dumps(result, ensure_ascii=False))
    return 1 if result["problems"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
