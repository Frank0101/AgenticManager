"""Prepares everything a prep's report needs before its summaries are written: builds data.json, then the two briefs, then the tasks, the one that writes the summaries and the one that writes the step change.

Everything the report is built from was gathered in the steps before, so
what is left is the model, the briefs and the tasks. Each stays a module of
its own, build_data.py's and make_brief.py's, testable and rerunnable alone;
this only saves the agent running them in order. The summaries and the step
change are independent subagents' tasks, as their rules and examples are
long: each protocol holds its own, and each agent reads only its brief.
"""
import argparse
import json

from build_data import build_data
from common import (FOLDER_NAME, PROTOCOL, OBSERVATIONS_WORDS, STEP_CHANGE_SHAPE, STEP_CHANGE_TASK,
                    fill_protocol, script_command, read_json, submit_section, work_folder, write_task_file)
from make_brief import write_briefs
from reading import person_section
from set_step_change import set_step_change

OBSERVATIONS_TASK = "observations"


def prepare(prep):
    """Build the prep `prep`'s data.json, then its briefs, then write the
    observations' task and the step change's, or, with no previous feedback,
    record the step change as null; returns {briefs, tasks}: the briefs'
    paths and the lines that hand the tasks out, 'Task observations: <path>'
    and 'Task step-change: <path>'."""
    data = read_json(build_data(prep))
    observations_brief, step_change_brief = write_briefs(prep)
    texts = [(OBSERVATIONS_TASK, observations_task(prep, observations_brief))]
    # Null needs no judgement: no agent is started to write it.
    if data["previous"]:
        texts.append((STEP_CHANGE_TASK,
                     step_change_task(prep, step_change_brief)))
    else:
        set_step_change(prep, None)
    tasks = [write_task_file(work_folder(FOLDER_NAME, prep, name), name, text)
             for name, text in texts]
    return {"briefs": [observations_brief, step_change_brief], "tasks": tasks}


def observations_task(prep, brief):
    """The text of the task that writes the prep `prep`'s observations'
    summaries from the brief at `brief`: its protocol, the person, the brief
    and how to submit."""
    words = {"observations_words": OBSERVATIONS_WORDS["going_well"],
             "context_words": OBSERVATIONS_WORDS["context"]}
    return task_text(prep, OBSERVATIONS_TASK, words, brief, "set_observations.py",
                     '{"going_well": "...", "to_improve": "...", "context": "..."}')


def step_change_task(prep, brief):
    """The text of the task that writes the prep `prep`'s step change from
    the brief at `brief`: its protocol, the person, the brief and how to
    submit."""
    return task_text(prep, STEP_CHANGE_TASK, {"step_change_words": OBSERVATIONS_WORDS["step_change"]},
                     brief, "set_step_change.py", STEP_CHANGE_SHAPE)


def task_text(prep, name, words, brief, script, answer):
    """The text of the task `name` of the prep `prep`: its protocol, filled
    with `words`, the person, the brief at `brief`, and how to submit
    `answer`, its shape, with `script`."""
    command = f"{script_command(__file__, script)} --prep {prep}"
    return "\n\n".join([fill_protocol(PROTOCOL, name, words), person_section(prep), f"## The brief\n\n{brief}",
                        submit_section(command, answer)])


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Build the prep's data.json from what was gathered, then its briefs, observations_brief.json and "
        "step_change_brief.json, then the tasks: the one that writes the summary of each table of observations "
        "and the one that writes the step change from the previous feedback.",
        epilog="Prints one line of JSON: briefs, the two briefs' paths, and tasks, the lines that hand the "
        "tasks out, 'Task observations: <path>' and 'Task step-change: <path>'. With no previous feedback, the "
        "step change is recorded as null and has no task.")
    parser.add_argument("--prep", required=True,
                        help="the prep's folder, <Person>_<YY-MM-DD>, as init_prep.py printed it")
    args = parser.parse_args(argv)
    print(json.dumps(prepare(args.prep), ensure_ascii=False))


if __name__ == "__main__":
    main()
