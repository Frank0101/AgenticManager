"""Prepares everything a prep's report needs before the agent writes: builds data.json, then brief.json.

Everything the report is built from was gathered in the steps before, so
what is left is the model and the brief. Each stays a module of its own,
build_data.py's and make_brief.py's, testable and rerunnable alone; this
only saves the agent running them one by one, in order, as the brief reads
the model.
"""
import argparse
import json

from build_data import build_data
from common import CONTENT, stops_on_failure
from make_brief import write_brief


def prepare(prep):
    """Build the prep `prep`'s data.json, then its brief.json; returns
    {brief, content_path}: the brief's path and where content.json goes,
    inside the skill's output folder."""
    build_data(prep)
    return {"brief": write_brief(prep), "content_path": f"{prep}/{CONTENT}"}


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Build the prep's data.json from what was gathered, then brief.json, which the agent reads to "
        "write content.json.",
        epilog="Prints one line of JSON: brief, brief.json's path, and content_path, the path to give "
        "output_file.py for content.json.")
    parser.add_argument("--prep", required=True,
                        help="the prep's folder, <Person>_<YY-MM-DD>, as init_prep.py printed it")
    args = parser.parse_args(argv)
    with stops_on_failure():
        print(json.dumps(prepare(args.prep), ensure_ascii=False))


if __name__ == "__main__":
    main()
