"""Everything before the agent writes: fetch the sprint, build data.json, then
brief.json.

The steps stay separate scripts, each testable on its own and rerunnable by
hand; this only saves the agent running them one by one. It stops at the first
failure with that script's message, as each step needs the previous one.
"""
import json
import os
import sys

from common import BRIEF_FILE, CONTENT_FILE, run_script
from fetch_sprint import selector_parser

# What this script prints, shown in --help.
PRINTS = """Prints one line of JSON on stdout: fetch_sprint.py's, plus `brief`, the file to
read, and `content_path`, the path to give output_file.py for content.json.
Progress goes to stderr."""


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
        selector_parser((__doc__ or "").split("\n\n")[0], PRINTS).print_help()
        return
    fetched = json.loads(run("fetch_sprint.py", *sys.argv[1:]))
    report_dir = fetched["report_dir"]
    sys.stderr.write(run("build_sprint_data.py", "--report-dir", report_dir))
    run("make_brief.py", "--report-dir", report_dir)
    print(json.dumps({**fetched, "brief": os.path.join(report_dir, BRIEF_FILE),
                      "content_path": f"{os.path.basename(report_dir)}/{CONTENT_FILE}"}))


if __name__ == "__main__":
    main()
