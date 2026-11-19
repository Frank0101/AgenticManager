"""Writes the task that finds the Notion pages a prep's person created, for a subagent, which records them with set_notion.py.

Only the agent reaches Notion, through its MCP, and a weak agent that has to
work out the searches gets them wrong, so the task lists each week's exact
arguments, worked out here from the period and the person's Notion id in
person.json: it copies them. The searches are the same for every run of a
period, and nothing is read from the config.
"""
import argparse
import json
import os

from common import FOLDER_NAME, NOTION_LIMIT, PERSON, calendar_weeks, prep_dir, read_json, script_command, submit_section, work_folder, write_task_file
from reading import person_section, read_protocol

ANSWER = """{"created": [
  {"start": "YYYY-MM-DD", "end": "YYYY-MM-DD", "results": [<the search's results, unchanged>]},
  {"start": "YYYY-MM-DD", "end": "YYYY-MM-DD", "results": [...], "full": true}
 ]}"""


def start(prep):
    """Write the task of the prep `prep` to its working folder; returns the
    line that hands it out, 'Task notion: <path>', and how many searches it
    lists."""
    person = read_json(os.path.join(prep_dir(prep), PERSON))
    lines = search_lines(person)
    folder = work_folder(FOLDER_NAME, prep, "notion")
    return {"task": write_task_file(folder, "notion", task_text(prep, person, lines)), "searches": len(lines)}


def task_text(prep, person, lines):
    """The text of the task of the prep `prep`: its protocol, the person,
    `person`, person.json's, the searches, `lines`, one for each week, and
    how to record them."""
    searches = (f"## The searches\n\nFrom {person['start']} to {person['end']}, {len(lines)} weeks: copy each one's "
                "arguments as listed.\n\n" + "\n".join(lines))
    command = f"{script_command(__file__, 'set_notion.py')} --prep {prep}"
    return "\n\n".join([read_protocol("notion", {"search_limit": NOTION_LIMIT}), person_section(prep), searches, submit_section(command, ANSWER)])


def search_lines(person):
    """The lines of the searches of `person`, person.json's: one for each
    calendar week of the period, 'first to last: <the search's arguments, as
    JSON>', to copy as they are."""
    notion_id = person["sources"]["notion-mcp"]["id"]
    return [f"- {first} to {last}: `" + json.dumps(
        {"query": "", "filters": {"created_by_user_ids": [notion_id],
                                  "created_date_range": {"start_date": first, "end_date": last}},
         "page_size": NOTION_LIMIT, "max_highlight_length": 0}) + "`"
        for first, last in calendar_weeks(person["start"], person["end"])]


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Write the task for the subagent that finds the Notion pages the prep's person created: "
        "one search for each week of the period, listed with the exact arguments to copy. Prints one line of "
        "JSON: task, 'Task notion: <path>', and searches, how many it lists.")
    commands = parser.add_subparsers(dest="command", required=True)
    command = commands.add_parser(
        "start", help="write the task", description="write the task")
    command.add_argument("--prep", required=True,
                         help="the prep's folder, <Person>_<YY-MM-DD>, as init_prep.py printed it")
    print(json.dumps(start(parser.parse_args(argv).prep), ensure_ascii=False))


if __name__ == "__main__":
    main()
