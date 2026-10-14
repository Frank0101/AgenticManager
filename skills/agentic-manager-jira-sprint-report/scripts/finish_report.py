"""
Everything after the agent writes content.json: draw the charts, write the
report and check it.

Usage:
    python3 finish_report.py --report-dir <report_dir>

Prints only what needs attention: content.json's problems, or the checks that
failed, then the report's path. Exits non-zero unless the report passes.
The passing checks are left out, as the agent would read hundreds of lines to
find the one to fix.
"""
import argparse
import os
import subprocess
import sys

from common import DATA_FILE, read_json, report_file, run_script


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--report-dir", required=True,
                        help="report folder holding data.json and content.json")
    args = parser.parse_args()
    for script in ("make_charts.py", "make_report.py"):
        result = run_script(script, "--report-dir",
                            args.report_dir, stderr=subprocess.STDOUT)
        if result.returncode:
            sys.stdout.write(result.stdout)
            sys.exit(result.returncode)
    result = run_script("check_report.py", "--report-dir",
                        args.report_dir, stderr=subprocess.STDOUT)
    lines = result.stdout.strip().splitlines()
    if result.returncode and not any(line.strip().startswith("FAIL") for line in lines):
        # The check itself crashed: show all of it, as content.json isn't the cause.
        sys.stdout.write(result.stdout)
        sys.exit(result.returncode)
    print("\n".join(
        [line for line in lines if line.strip().startswith("FAIL")] + lines[-1:]))
    report = os.path.join(args.report_dir, report_file(
        read_json(os.path.join(args.report_dir, DATA_FILE))["label"]))
    print(("report: " if not result.returncode else "report (inspect the failed checks before rerunning): ") + report)
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
