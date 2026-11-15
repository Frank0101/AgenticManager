"""Everything after the agent writes content.json: write the report, draw the
charts and check it.

The one command of the step: each part is a module of its own, the report
make_report.py's, the charts make_charts.py's and the check check_report.py's,
and this script runs them in order, in one process. It prints only what needs
attention, as the agent would otherwise read hundreds of passing checks to find
the one to fix.
"""
import argparse
import os
import sys

from check_report import check_report
from common import DATA_FILE, read_json
from make_charts import write_charts
from make_report import write_report


def finish(report_dir):
    """Write the report in `report_dir` and its charts, then check them:
    (the report's path, the Checker). Exits, with what to fix on stdout,
    when content.json breaks a rule or the charts can't be drawn."""
    try:
        report = write_report(report_dir)
        write_charts(report_dir, read_json(
            os.path.join(report_dir, DATA_FILE)))
    except SystemExit as stopped:
        if not isinstance(stopped.code, str):
            raise
        print(stopped.code)
        sys.exit(1)
    return report, check_report(report_dir)


def main():
    parser = argparse.ArgumentParser(
        description=(__doc__ or "").split("\n\n")[0],
        epilog="Prints content.json's problems, or the checks that failed, then the report's path.\n"
        "Exits non-zero unless the report passes.",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--report-dir", required=True,
                        help="report folder holding data.json and content.json")
    args = parser.parse_args()
    report, checker = finish(args.report_dir)
    for line in checker.failures:
        print(f"  FAIL  {line}")
    print(checker.summary())
    print(("report (inspect the failed checks before rerunning): " if checker.failures else "report: ") + report)
    sys.exit(1 if checker.failures else 0)


if __name__ == "__main__":
    main()
