"""Prepares everything a prep's report needs before its summaries are written: builds data.json, then brief.json, then the task that writes the summaries.

Everything the report is built from was gathered in the steps before, so
what is left is the model, the brief and the task. Each stays a module of
its own, build_data.py's and make_brief.py's, testable and rerunnable alone;
this only saves the agent running them one by one, in order, as the brief
reads the model. The summaries are a subagent's task, as their rules and
examples are long: the protocol holds them, so the skill's instructions
don't.
"""
import argparse
import json

from build_data import build_data
from common import (FOLDER_NAME, PROTOCOL, OBSERVATIONS_WORDS, fill_protocol, script_command,
                    submit_section, work_folder, write_task_file)
from make_brief import write_brief
from reading import person_section

OBSERVATIONS_TASK = "observations"


def prepare(prep):
    """Build the prep `prep`'s data.json, then its brief.json, then write
    the summaries' task; returns {brief, task}: the brief's path and the
    line that hands the task out, 'Task observations: <path>'."""
    build_data(prep)
    brief = write_brief(prep)
    task = write_task_file(work_folder(FOLDER_NAME, prep, OBSERVATIONS_TASK), OBSERVATIONS_TASK,
                           summary_task(prep, brief))
    return {"brief": brief, "task": task}


def summary_task(prep, brief):
    """The text of the task that writes the prep `prep`'s summaries from
    the brief at `brief`: its protocol, the person, the brief and how to
    submit."""
    command = f"{script_command(__file__, 'set_content.py')} --prep {prep}"
    return "\n\n".join([fill_protocol(PROTOCOL, OBSERVATIONS_TASK, {"observations_words": OBSERVATIONS_WORDS["going_well"], "context_words": OBSERVATIONS_WORDS["context"]}), person_section(prep),
                        f"## The brief\n\n{brief}",
                        submit_section(command, '{"going_well": "...", "to_improve": "...", "context": "..."}')])


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Build the prep's data.json from what was gathered, then brief.json, then the task that "
        "writes the summary of each table of observations.",
        epilog="Prints one line of JSON: brief, brief.json's path, and task, the line that hands the summaries' "
        "task out, 'Task observations: <path>'.")
    parser.add_argument("--prep", required=True,
                        help="the prep's folder, <Person>_<YY-MM-DD>, as init_prep.py printed it")
    args = parser.parse_args(argv)
    print(json.dumps(prepare(args.prep), ensure_ascii=False))


if __name__ == "__main__":
    main()
