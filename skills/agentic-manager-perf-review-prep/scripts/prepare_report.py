"""Prepares everything a prep's report needs before its summaries are written: builds data.json, then the four briefs, then the tasks, the one that writes the work and its impact, the one that lists the work before the period, the one that writes the summaries and the one that writes the step change.

Everything the report is built from was gathered in the steps before, so
what is left is the model, the briefs and the tasks. Each stays a module of
its own, build_data.py's and make_brief.py's, testable and rerunnable alone;
this only saves the agent running them in order. The four tasks are
independent subagents', as their rules and examples are long: each protocol
holds its own, and each agent reads only its brief, while the work and its
impact's agent, where it needs to, opens the links in it.
"""
import argparse
import json

from build_data import build_data
from common import (EARLIER_WORK_SHAPE, EARLIER_WORK_TASK, FOLDER_NAME, MAX_EARLIER_BULLETS, PROTOCOL,
                    OBSERVATIONS_SHAPE, OBSERVATIONS_TASK, WORDS, STEP_CHANGE_SHAPE, STEP_CHANGE_TASK, WORK_IMPACT_SHAPE,
                    WORK_IMPACT_TASK, fill_protocol, link_commands, script_command, read_json, submit_section, work_folder,
                    write_task_file)
from make_brief import RECENT_ITEMS, write_briefs
from reading import person_section
from set_earlier_work import set_earlier_work
from set_step_change import set_step_change


def prepare(prep):
    """Build the prep `prep`'s data.json, then its briefs, then write the
    work and its impact's task, the work before the period's, the
    observations' and the step change's, or, with no previous feedback,
    record the work before the period and the step change as null; returns
    {briefs, tasks}: the briefs' paths and the lines that hand the tasks out,
    'Task work-impact: <path>', 'Task earlier-work: <path>', 'Task
    observations: <path>' and 'Task step-change: <path>'."""
    data = read_json(build_data(prep))
    briefs = write_briefs(prep)
    observations_brief, step_change_brief, work_impact_brief, earlier_work_brief = briefs
    previous = bool(data["previous"])
    # Null needs no judgement: no agent is started to write it.
    if not previous:
        set_earlier_work(prep, None)
        set_step_change(prep, None)
    texts = [(WORK_IMPACT_TASK, work_impact_task(prep, work_impact_brief)),
             *([(EARLIER_WORK_TASK, earlier_work_task(prep,
               earlier_work_brief))] if previous else []),
             (OBSERVATIONS_TASK, observations_task(prep, observations_brief)),
             *([(STEP_CHANGE_TASK, step_change_task(prep, step_change_brief))] if previous else [])]
    tasks = [write_task_file(work_folder(FOLDER_NAME, prep, name), name, text)
             for name, text in texts]
    return {"briefs": briefs, "tasks": tasks}


def work_impact_task(prep, brief):
    """The text of the task that writes the prep `prep`'s work and its
    impact from the brief at `brief`: its protocol, the person, the brief and
    how to submit."""
    # It may open the links the brief holds.
    return task_text(prep, WORK_IMPACT_TASK, {"work_impact_words": WORDS["work_impact"],
                                              "recent_items": RECENT_ITEMS,
                                              "work_impact_line_words": WORDS["work_impact_line"], **link_commands()},
                     brief, "set_work_impact.py", WORK_IMPACT_SHAPE)


def earlier_work_task(prep, brief):
    """The text of the task that lists the prep `prep`'s work before the
    period from the brief at `brief`: its protocol, the person, the brief
    and how to submit."""
    return task_text(prep, EARLIER_WORK_TASK, {"earlier_work_words": WORDS["earlier_work"],
                                               "max_bullets": MAX_EARLIER_BULLETS},
                     brief, "set_earlier_work.py", EARLIER_WORK_SHAPE)


def observations_task(prep, brief):
    """The text of the task that writes the prep `prep`'s observations'
    summaries from the brief at `brief`: its protocol, the person, the brief
    and how to submit."""
    words = {"value_words": WORDS["value"],
             "context_words": WORDS["context"]}
    return task_text(prep, OBSERVATIONS_TASK, words, brief, "set_observations.py", OBSERVATIONS_SHAPE)


def step_change_task(prep, brief):
    """The text of the task that writes the prep `prep`'s step change from
    the brief at `brief`: its protocol, the person, the brief and how to
    submit."""
    return task_text(prep, STEP_CHANGE_TASK, {"step_change_words": WORDS["step_change"]},
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
        description="Build the prep's data.json from what was gathered, then its briefs, observations_brief.json, "
        "step_change_brief.json, work_impact_brief.json and earlier_work_brief.json, then the tasks: the one that "
        "writes the person's work and its impact, the one that lists their work before the period, the one that "
        "writes the summary of each table of observations and the one that writes the step change from the previous "
        "feedback.",
        epilog="Prints one line of JSON: briefs, the four briefs' paths, and tasks, the lines that hand the "
        "tasks out, 'Task work-impact: <path>', 'Task earlier-work: <path>', 'Task observations: <path>' and 'Task "
        "step-change: <path>'. With no previous feedback, the work before the period and the step change are "
        "recorded as null and have no task.")
    parser.add_argument("--prep", required=True,
                        help="the prep's folder, <Person>_<YY-MM-DD>, as init_prep.py printed it")
    args = parser.parse_args(argv)
    print(json.dumps(prepare(args.prep), ensure_ascii=False))


if __name__ == "__main__":
    main()
