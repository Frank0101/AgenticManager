"""Prepares everything a prep's report needs before its summaries are written: builds data.json, then the three briefs, then the three tasks, the one that writes the summaries, the one that writes the step change and the one that checks the manager's view.

Everything the report is built from was gathered in the steps before, so
what is left is the model, the briefs and the tasks. Each stays a module of
its own, build_data.py's and make_brief.py's, testable and rerunnable alone;
this only saves the agent running them in order. The summaries, the step
change and the view check are independent subagents' tasks, as their rules
and examples are long: each protocol holds its own, and each agent reads
only its brief.
"""
import argparse
import json

from build_data import build_data
from common import (FOLDER_NAME, PROTOCOL, OBSERVATIONS_WORDS, STEP_CHANGE_COMPARISON, VIEW_CHECK_COMPARISON,
                    fill_protocol, script_command, read_json, submit_section, work_folder, write_task_file)
from make_brief import write_briefs
from reading import person_section
from set_comparison import set_comparison

OBSERVATIONS_TASK = "observations"


def prepare(prep):
    """Build the prep `prep`'s data.json, then its briefs, then write the
    summaries' task, the step change's and the view check's, or, with no
    previous review, record the step change as null; returns {briefs,
    tasks}: the briefs' paths and the lines that hand the tasks out, 'Task
    observations: <path>', 'Task step-change: <path>' and 'Task view-check:
    <path>'."""
    data = read_json(build_data(prep))
    brief, step_change_brief, view_check_brief = write_briefs(prep)
    texts = [(OBSERVATIONS_TASK, summary_task(prep, brief))]
    # Null needs no judgement: no agent is started to write it.
    if data["reviews"]:
        texts.append((STEP_CHANGE_COMPARISON.task, comparison_task(
            prep, STEP_CHANGE_COMPARISON, step_change_brief)))
    else:
        set_comparison(prep, STEP_CHANGE_COMPARISON, None)
    texts.append((VIEW_CHECK_COMPARISON.task, comparison_task(
        prep, VIEW_CHECK_COMPARISON, view_check_brief)))
    tasks = [write_task_file(work_folder(FOLDER_NAME, prep, name), name, text)
             for name, text in texts]
    return {"briefs": [brief, step_change_brief, view_check_brief], "tasks": tasks}


def summary_task(prep, brief):
    """The text of the task that writes the prep `prep`'s summaries from
    the brief at `brief`: its protocol, the person, the brief and how to
    submit."""
    words = {"observations_words": OBSERVATIONS_WORDS["going_well"],
             "context_words": OBSERVATIONS_WORDS["context"]}
    return task_text(prep, OBSERVATIONS_TASK, words, brief, "set_content.py",
                     '{"going_well": "...", "to_improve": "...", "context": "..."}')


def comparison_task(prep, comparison, brief):
    """The text of the task that writes `comparison`, a Comparison, of the
    prep `prep` from the brief at `brief`: its protocol, the person, the
    brief and how to submit."""
    return task_text(prep, comparison.task, {f"{comparison.words}_words": OBSERVATIONS_WORDS[comparison.words]},
                     brief, f"set_comparison.py --of {comparison.task}", comparison.shape)


def task_text(prep, name, words, brief, script, answer):
    """The text of the task `name` of the prep `prep`: its protocol, filled
    with `words`, the person, the brief at `brief`, and how to submit
    `answer`, its shape, with `script`."""
    command = f"{script_command(__file__, script)} --prep {prep}"
    return "\n\n".join([fill_protocol(PROTOCOL, name, words), person_section(prep), f"## The brief\n\n{brief}",
                        submit_section(command, answer)])


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Build the prep's data.json from what was gathered, then its briefs, brief.json, "
        "step_change_brief.json and view_check_brief.json, then the three tasks: the one that writes the summary "
        "of each table of observations, the one that writes the step change from the latest previous review, "
        "and the one that checks the manager's view against the period's evidence.",
        epilog="Prints one line of JSON: briefs, the three briefs' paths, and tasks, the lines that hand the "
        "tasks out, 'Task observations: <path>', 'Task step-change: <path>' and 'Task view-check: <path>'. With "
        "no previous review, the step change is recorded as null and has no task.")
    parser.add_argument("--prep", required=True,
                        help="the prep's folder, <Person>_<YY-MM-DD>, as init_prep.py printed it")
    args = parser.parse_args(argv)
    print(json.dumps(prepare(args.prep), ensure_ascii=False))


if __name__ == "__main__":
    main()
