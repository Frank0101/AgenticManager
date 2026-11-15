"""Finishes a prep's report from data.json: writes the report and draws its charts, then checks them.

The one command of the step: each part is a module of its own, the report
make_report.py's, the charts make_charts.py's and the check check_report.py's,
and this script runs them in order, so each does one thing. It prints only
what needs attention.
"""
import argparse
import json
import os

from check_report import report_problems
from common import CHARTS_DIR, DATA, PERSON, prep_dir, read_json, stops_on_failure
from make_charts import write_charts
from make_report import write_report


def finish(prep):
    """Write the prep `prep`'s report and charts from data.json, then check
    them; returns {report, problems}, the report's path and what the check
    found."""
    folder = prep_dir(prep)
    person, data = read_json(os.path.join(folder, PERSON)), read_json(
        os.path.join(folder, DATA))
    write_charts(prep, data)
    path, report = write_report(prep, person, data)
    return {"report": path, "problems": report_problems(report, data, os.listdir(os.path.join(folder, CHARTS_DIR)))}


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Write the prep's report, <Person>_Review_Prep.md, and its charts from data.json, then check them.",
        epilog="Prints one line of JSON: report, the report's path, and problems, what the check found, "
        "empty when it passes. Exits 1 when it finds any.")
    parser.add_argument("--prep", required=True,
                        help="the prep's folder, <Person>_<YY-MM-DD>, as init_prep.py printed it")
    args = parser.parse_args(argv)
    with stops_on_failure():
        result = finish(args.prep)
    print(json.dumps(result, ensure_ascii=False))
    return 1 if result["problems"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
