"""Everything before the agent writes: fetch the sprint, build data.json, then
brief.json.

The steps stay modules of their own, fetch_sprint.py's, build_data.py's and
make_brief.py's, each testable on its own and rerunnable by hand; this only
saves the agent running them one by one, in order, in one process. It stops at
the first failure with that step's message, as each step needs the previous
one.
"""
import json
import os
import sys

from build_data import build_data
from common import CONTENT_FILE
from fetch_sprint import fetch_sprint, parse_args, selector_parser
from make_brief import write_brief

# What this script prints, shown in --help.
PRINTS = """Prints one line of JSON on stdout: fetch_sprint.py's, plus `brief`, the file to
read, and `content_path`, the path to give output_file.py for content.json.
Progress goes to stderr."""


def prepare(args):
    """Fetch the sprint the selectors `args` name, build its data.json, then
    its brief.json: fetch_sprint's result, plus `brief`, the brief's path, and
    `content_path`, content.json's path for output_file.py. The build's
    summary goes to stderr, as progress."""
    fetched = fetch_sprint(args)
    report_dir = fetched["report_dir"]
    data, summary = build_data(report_dir)
    sys.stderr.write("".join(f"{line}\n" for line in [
                     *summary, f"wrote {data}"]))
    return {**fetched, "brief": write_brief(report_dir),
            "content_path": f"{os.path.basename(report_dir)}/{CONTENT_FILE}"}


def main():
    args = parse_args(selector_parser(
        (__doc__ or "").split("\n\n")[0], PRINTS))
    print(json.dumps(prepare(args)))


if __name__ == "__main__":
    main()
