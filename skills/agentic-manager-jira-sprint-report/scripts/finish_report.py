"""Everything after the agent writes content.json: write the report, draw the
charts and check it.

It prints only what needs attention, as the agent would otherwise read hundreds
of passing checks to find the one to fix.
"""
import argparse
import os
import subprocess
import sys

from common import DATA_FILE, read_json, report_file, run_script


def main():
    parser = argparse.ArgumentParser(
        description=(__doc__ or "").split("\n\n")[0],
        epilog="Prints content.json's problems, or the checks that failed, then the report's path.\n"
        "Exits non-zero unless the report passes.",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--report-dir", required=True,
                        help="report folder holding data.json and content.json")
    args = parser.parse_args()
    for script in ("make_report.py", "make_charts.py"):
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
