"""
Everything before the agent writes: fetch the sprint, build data.json, then
brief.json.

Usage (exactly one sprint selector, passed on to fetch_sprint.py):
    python3 prepare_report.py --sprint-id 123 [--board 42]   (the board whose sprint report is read)
    python3 prepare_report.py --project PROJ            # most recently closed sprint
    python3 prepare_report.py --project PROJ --active   # the sprint in progress
    python3 prepare_report.py --board 42 [--active]
    python3 prepare_report.py --sprint-name "Sprint 3" --project PROJ   (or --board 42)
    python3 prepare_report.py --sprint-name "PROJ Sprint 3"   (the first word is tried as the project key)

Prints one line of JSON on stdout: fetch_sprint.py's, plus `brief`, the file to
read, and `content_path`, the path to give output_file.py for content.json.
Progress goes to stderr.

The steps stay separate scripts, each testable on its own and rerunnable by
hand; this only saves the agent running them one by one. It stops at the first
failure with that script's message, as each step needs the previous one.
"""
import json
import os
import sys

from common import BRIEF_FILE, CONTENT_FILE, run_script


def run(script, *args):
    """Run a sibling script, its progress on stderr; its stdout, or exit with
    its code."""
    result = run_script(script, *args)
    if result.returncode:
        sys.stderr.write(result.stdout)
        sys.exit(result.returncode)
    return result.stdout


def main():
    if sys.argv[1:2] in (["-h"], ["--help"]):
        print(__doc__)
        return
    fetched = json.loads(run("fetch_sprint.py", *sys.argv[1:]))
    report_dir = fetched["report_dir"]
    sys.stderr.write(run("build_sprint_data.py", "--report-dir", report_dir))
    run("make_brief.py", "--report-dir", report_dir)
    print(json.dumps({**fetched, "brief": os.path.join(report_dir, BRIEF_FILE),
                      "content_path": f"{os.path.basename(report_dir)}/{CONTENT_FILE}"}))


if __name__ == "__main__":
    main()
