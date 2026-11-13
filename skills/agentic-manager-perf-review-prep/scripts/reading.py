"""Runs a reading done by subagents: one task per part of a source, such as a month, then a merge into one summary.

Notes and messages are too many to read in one go: a fresh subagent writes a
synopsis of everything in a part, and judges nothing, so the merge sees all
there is and alone decides what is feedback, with one threshold for the
period: only the merge sees a small thing repeat into a pattern. Notes are
numbered, so a reader can't skip one. What differs by source is a Source;
the flow lives here once, writing to the prep's _raw folder, which keeps
what each subagent was shown and wrote, an answer a file of its own.
"""
import json
import os
from dataclasses import dataclass, field
from typing import Callable

from common import (PERSON, RAW_DIR, SUMMARY_PARTS, VALUES, clear_folder, company_names, company_setting,
                    fill_protocol, prep_dir, script_command, read_json, stdin_json, summary_problems, word_count, write_raw,
                    write_prep_file)

MATERIAL = "material.json"
TASK_FILE = "task.md"
ANSWER = "answer.json"
MERGE = "merge"
SYNOPSIS_WORDS = 60
MAX_SYNOPSIS_WORDS = 120
PROTOCOL = os.path.join(os.path.dirname(
    os.path.realpath(__file__)), "..", "protocol")


@dataclass
class Source:
    """What a reading needs to know about its source. `gather(prep)` returns
    the material, with `tasks`, the reading tasks in order; `task_text(prep,
    task, material)` the protocol and body of a reading task;
    `merge_days(material)` the days a merged point may cite. A reading
    task's items are either numbered, when `task_notes(material, task)`
    gives the day of each note it shows, null for an undated one, or else
    dated, each a day of `task_days(material, task)`; `linked` whether every
    item and point carries the links it rests on."""
    name: str
    script: str
    output: str
    what: str
    gather: Callable
    task_text: Callable
    merge_days: Callable
    task_notes: Callable | None = None
    task_days: Callable | None = None
    linked: bool = False
    answers: dict = field(default_factory=dict)


# The commands.

def command_line(source, description, argv=None):
    """The command line of a reading: start, submit, finished and remerge."""
    import argparse
    parser = argparse.ArgumentParser(description=description)
    commands = parser.add_subparsers(dest="command", required=True)
    for name, help in (("start", f"gather the {source.what}'s source, emptying the working folder, and write the "
                        "reading tasks; prints one line of JSON: what was gathered, tasks, a line 'Task <name>: "
                        "<path>' for each, and merge, the merge task's line"),
                       ("submit", "check a task's answer, JSON on stdin, and write it; the task's file shows its "
                        "shape and the command to copy. Prints one line of JSON: the task, and its items or, for "
                        f"the merge, the {source.name} file's path"),
                       ("finished", f"once the merge is submitted: prints one line of JSON: {source.name}, the "
                        "summary's path, in_doubt, what the merge left out in doubt, and correct, the command that "
                        "submits a correction"),
                       ("remerge", "once every reading task is answered: write the merge task again, from the "
                        "synopses kept in _raw and the merge's protocol as it is now, dropping the merge's earlier "
                        "answer; prints one line of JSON: merge, the merge task's line")):
        command = commands.add_parser(name, help=help, description=help)
        command.add_argument("--prep", required=True,
                             help="the prep's folder, <Person>_<YY-MM-DD>, as init_prep.py printed it")
        if name == "submit":
            command.add_argument("--task", required=True,
                                 help="the task's name, as start printed it, such as month:2026-07")
    args = parser.parse_args(argv)
    if args.command == "start":
        print(json.dumps(start(source, args.prep), ensure_ascii=False))
    elif args.command == "finished":
        if not answered(work_dir(source, args.prep), MERGE) and load_material(source, args.prep)["tasks"]:
            raise SystemExit(
                "The merge isn't submitted yet: run finished once its subagent has finished")
        print(json.dumps(finished(source, args.prep), ensure_ascii=False))
    elif args.command == "remerge":
        print(json.dumps(remerge(source, args.prep), ensure_ascii=False))
    else:
        answer = stdin_json("The answer's shape:\n" +
                            answer_shape(source, args.task))
        print(json.dumps(submit(source, args.prep,
              args.task, answer), ensure_ascii=False))


def start(source, prep):
    """Gather the source of the prep `prep` into its working folder, emptied
    first, and write every reading task, as they are independent and few;
    returns what was gathered, a line for each task, 'Task <name>: <path>',
    and the merge task's line, its file written once every reading task is
    answered. With nothing to read, it records the empty summary and returns
    what finished() says."""
    material = source.gather(prep)
    work = work_dir(source, prep)
    clear_folder(work)
    write_raw(prep, os.path.join(source.name, MATERIAL), json.dumps(
        material, ensure_ascii=False, indent=1))
    result = {key: value for key, value in material.items()
              if key not in ("tasks", "content")}
    if not material["tasks"]:
        write_prep_file(prep, source.output, {
                        part: [] for part in SUMMARY_PARTS})
        return {**result, **finished(source, prep)}
    return {**result, "tasks": [write_task(source, prep, task, reading_task(source, prep, task, material))
                                for task in material["tasks"]],
            "merge": f"Task {MERGE}: {task_path(work, MERGE)}"}


def submit(source, prep, task, answer):
    """Check the answer `answer` to the task `task` of the prep `prep`, and
    write it, a numbered note's item with its note's day; the answer to the last
    reading task also writes the merge task, and the merge's summary goes to
    the prep. Exits, writing nothing, with every problem."""
    material, notes, in_doubt = load_material(source, prep), None, None
    if task == MERGE:
        in_doubt = answer.pop("in_doubt", None) if isinstance(
            answer, dict) else None
        problems = summary_problems(answer, f"the {source.what}", company_names(VALUES), source.merge_days(material),
                                    source.linked) + in_doubt_problems(in_doubt)
    elif task in material["tasks"]:
        notes = source.task_notes(
            material, task) if source.task_notes else None
        problems = items_problems(answer, notes, None if source.task_days is None
                                  else source.task_days(material, task), source.linked)
    else:
        raise SystemExit(
            f"{task!r} isn't a task of this prep: start printed them")
    if problems:
        raise SystemExit("; ".join(problems) +
                         "\n\nThe answer's shape:\n" + answer_shape(source, task))
    if task == MERGE:
        stored = {**answer, "in_doubt": in_doubt}
    elif notes is not None:
        stored = {"items": [{"date": notes[item["note"] - 1], "synopsis": item["synopsis"]}
                            for item in sorted(answer["items"], key=lambda item: item["note"])]}
    else:
        stored = answer
    write_raw(prep, os.path.join(source.name, *task.split(":"), ANSWER),
              json.dumps(stored, ensure_ascii=False, indent=1))
    if task == MERGE:
        write_prep_file(prep, source.output, answer)
        return {"task": task, source.name: os.path.join(prep_dir(prep), source.output)}
    if all(answered(work_dir(source, prep), name) for name in material["tasks"]):
        write_task(source, prep, MERGE, merge_task(source, prep, material))
    return {"task": task, "items": len(answer["items"])}


def finished(source, prep):
    """What the agent tells the manager once the source is merged: where the
    summary is, what the merge left out in doubt, as it wrote it, and the
    command that submits a correction."""
    in_doubt = read_answer(source, prep, MERGE)["in_doubt"] if answered(
        work_dir(source, prep), MERGE) else []
    return {"finished": True, source.name: os.path.join(prep_dir(prep), source.output),
            "in_doubt": in_doubt, "correct": f"{call(source)} submit --prep {prep} --task {MERGE}"}


def remerge(source, prep):
    """Write the merge task of the prep `prep` again, from the synopses its
    reading tasks wrote and the merge's protocol as it is now, so a change to
    the merge's rules is tried without reading the source again; drops the
    merge's earlier answer, so finished waits for the new one. Exits when a
    reading task isn't answered."""
    material, work = load_material(source, prep), work_dir(source, prep)
    if missing := [task for task in material["tasks"] if not answered(work, task)]:
        raise SystemExit(
            f"{', '.join(missing)} not answered yet: the merge is written once every reading task is")
    clear_folder(os.path.join(work, MERGE))
    return {"merge": write_task(source, prep, MERGE, merge_task(source, prep, material))}


# The tasks.

def reading_task(source, prep, task, material):
    """The text of the reading task `task`: its protocol, the person, how to
    read a linked ticket, the source's part and how to submit."""
    protocol, body = source.task_text(prep, task, material)
    return "\n\n".join([read_protocol(protocol), person_section(prep), links_section(source),
                        body, submit_section(f"{call(source)} submit --prep {prep} --task {task}",
                                             answer_shape(source, task))])


def merge_task(source, prep, material):
    """The text of the merge task: its protocol, the person, the company's
    values and every synopsis the reading tasks wrote, to judge and merge
    into one summary."""
    found = [json.dumps(item, ensure_ascii=False)
             for name in material["tasks"] for item in read_answer(source, prep, name)["items"]]
    return "\n\n".join([read_protocol(f"{source.name}-merge"), person_section(prep), values_section(),
                        "## What the reading found\n\n" +
                        ("\n".join(found) or "Nothing."),
                        submit_section(f"{call(source)} submit --prep {prep} --task {MERGE}",
                                       answer_shape(source, MERGE))])


def person_section(prep):
    """The person the prep is for, for a task."""
    return f"## The person\n\n{read_json(os.path.join(prep_dir(prep), PERSON))['person']}"


def values_section():
    """The company's values, each with what it means, for a task."""
    return "## The company's values\n\n" + "\n".join(f"- {entry['value']}: {entry['meaning']}"
                                                     for entry in company_setting(VALUES))


def links_section(source):
    """How a task reads a Jira ticket a link points to: the command, by the
    path the skill pre-approves."""
    return (f"## Reading links\n\nA Jira ticket: `{script_command('jira_ticket.py')} --key <key>`, "
            "such as PROJ-123.")


def submit_section(command, answer):
    """How a task submits its answer: the command `command` that takes it,
    and `answer`, its shape."""
    return (f"## Submit\n\nSubmit your answer, as JSON in a quoted here-document:\n\n```bash\n"
            f"{command} <<'END_OF_INPUT'\n{answer}\nEND_OF_INPUT\n```\n\nIf the script refuses it, fix every "
            "problem it names and submit again, until it is accepted.")


def answer_shape(source, task):
    """The shape of the answer to `task`: the merge's, or a reading task's."""
    return source.answers[MERGE if task == MERGE else "reading"]


def write_task(source, prep, task, text):
    """Write the task `task`'s text to its file; returns the line that hands
    it out, 'Task <name>: <path>'."""
    path = write_raw(prep, os.path.join(
        source.name, *task.split(":"), TASK_FILE), text)
    return f"Task {task}: {path}"


# Checking the answers.

def items_problems(answer, notes=None, days=None, linked=False):
    """Why `answer` isn't a reading task's answer, empty when it is: items,
    each a synopsis of at most MAX_SYNOPSIS_WORDS words and, with `notes`,
    the days of the task's notes, the number of its note, every note's
    once; else a date, one of `days`, and, when `linked`, a link."""
    if not (isinstance(answer, dict) and sorted(answer) == ["items"] and isinstance(answer["items"], list)):
        return ['the answer must be {"items": [...]}, [] when there is nothing']
    fields = ["note", "synopsis"] if notes is not None else (
        ["date", "link", "synopsis"] if linked else ["date", "synopsis"])
    problems = []
    for number, item in enumerate(answer["items"], 1):
        what = f"item {number}"
        if not (isinstance(item, dict) and sorted(item) == fields):
            problems.append(f"{what} must have the fields {', '.join(fields)}")
            continue
        if not (isinstance(item["synopsis"], str) and item["synopsis"].strip()) \
                or word_count(str(item["synopsis"])) > MAX_SYNOPSIS_WORDS:
            problems.append(f"{what}'s synopsis must be text of about {SYNOPSIS_WORDS} words, at most "
                            f"{MAX_SYNOPSIS_WORDS}")
        if notes is not None:
            continue
        if item["date"] not in (days or []):
            problems.append(
                f"{what}'s date, {item['date']!r}, must be the day of what it comes from")
        if linked and not (isinstance(item["link"], str) and item["link"].startswith("https://")):
            problems.append(
                f"{what}'s link, {item['link']!r}, must be the address of what it comes from")
    if notes is not None and not problems:
        numbers = [item["note"] for item in answer["items"]]
        missing = [str(n)
                   for n in range(1, len(notes) + 1) if n not in numbers]
        if sorted(numbers) != list(range(1, len(notes) + 1)):
            problems.append(f"every note, 1 to {len(notes)}, must have one synopsis, by its number"
                            + (f": missing {', '.join(missing)}" if missing else ""))
    return problems


def in_doubt_problems(in_doubt):
    """Why `in_doubt`, what the merge left out in doubt, isn't a list of
    texts, empty when it is."""
    if not (isinstance(in_doubt, list) and all(isinstance(line, str) and line.strip() for line in in_doubt)):
        return ['"in_doubt" must be a list of texts, [] when nothing was left out in doubt']
    return []


# Where things are.

def work_dir(source, prep):
    """The prep `prep`'s working folder for `source`, in its _raw folder:
    start empties it, never finding what an earlier run left."""
    return os.path.join(prep_dir(prep), RAW_DIR, source.name)


def task_path(work, task):
    """The file of `task` in the working folder `work`."""
    return os.path.join(work, *task.split(":"), TASK_FILE)


def answered(work, task):
    """Whether `task` has an answer in the working folder `work`."""
    return os.path.exists(os.path.join(work, *task.split(":"), ANSWER))


def read_answer(source, prep, task):
    """The answer to `task`, as submitted."""
    return read_json(os.path.join(work_dir(source, prep), *task.split(":"), ANSWER))


def load_material(source, prep):
    """What start gathered for the prep `prep`; exits when it hasn't run."""
    path = os.path.join(work_dir(source, prep), MATERIAL)
    if not os.path.exists(path):
        raise SystemExit(
            f"The {source.what}'s source for {prep} isn't gathered: run {call(source)} start --prep {prep} first")
    return read_json(path)


def read_protocol(name):
    """The protocol file `name`'s text, its shared parts filled in."""
    return fill_protocol(PROTOCOL, name, {"synopsis_words": SYNOPSIS_WORDS,
                                          "max_synopsis_words": MAX_SYNOPSIS_WORDS})


def call(source):
    """The command that runs the source's script, by script_command()."""
    return script_command(source.script)
