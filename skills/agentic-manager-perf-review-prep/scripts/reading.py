"""Runs a reading done by subagents: the source's items are listed, by the script or by readers, and one judge writes the summary, each point citing the items it rests on.

Notes and messages are many and mostly not feedback, so fresh subagents read
them, never the main agent, whose context stays small. A long source is read
in parts, one reader each, who list everything that could matter and judge
nothing: only the judge sees every part, so only it sees a small thing repeat
into a pattern. The summary is checked as the manager's are; what a point
cites decides its evidence, each with its day and link, which the script adds.
What differs by source is a Source; the flow lives here once.
"""
import argparse
import json
import os
from dataclasses import dataclass
from typing import Callable

from common import (FOLDER_NAME, DESCRIPTION_WORDS, MAX_DESCRIPTION_WORDS, PERSON, PROTOCOL, POINT_LIMITS, RAW_DIR, SUMMARY_HELP,
                    SUMMARY_PARTS, VALUES, WEB_LINK, clear_folder, company_names, company_setting, days_between,
                    fill_protocol, is_point, json_text, latest_day, library_command, newest_key, period_days, point_fields,
                    point_shape, prep_dir, read_json, script_command, stdin_json, submit_section, summary_problems,
                    task_line, word_count, work_folder, write_prep_file, write_task_file)

ANSWER = "answer.json"
CITES_HELP = ("  cites       the numbers of what the point rests on, {what}, at least one, each once: the script "
              "adds each one's day and link")


@dataclass
class Source:
    """What a reading needs to know about its source. The judge's task, or
    the only task, reads the items, each {number, date, link} and what it
    shows, the date null for a page, numbered from 1 and kept in the prep's
    _raw: `gather(prep)` lists them when the script can, returning `empty`,
    whether there is nothing to read, `content`, {items}, and any fact start
    prints; else `readers` list them. `task_text(prep, content)` returns the
    protocol and body of the judge's task; `answer_shape` its answer's JSON
    shape; `cites` what a number cites, for its help; `terms` the words the
    shared parts of its protocol take, `cited`, what a point cites, and
    `citations_more`, what else to say of it; `undated_context` whether a context
    point may rest on an undated item, as one from a page; `days(person)` the
    days its items may be dated on, from person.json; `until_today(prep)`, when
    given, what start's --until-today does: records that the items run to
    today."""
    name: str
    script: str
    output: str
    what: str
    task_text: Callable
    answer_shape: str
    cites: str
    terms: dict
    gather: Callable | None = None
    readers: "Readers | None" = None
    undated_context: bool = False
    days: Callable = period_days
    until_today: Callable | None = None


@dataclass
class Readers:
    """How a source is read in parts, each by a subagent that lists items and
    declares what it searched. `parts(prep)` returns {task: {start, end}},
    the days each part covers; `task_text(prep, task, part)` a part's
    protocol and body; `answer_shape` and `help` what a part submits;
    `coverage_problems(searched, days)` why what a part declares searched
    isn't all of its `days`."""
    parts: Callable
    task_text: Callable
    answer_shape: str
    help: str
    coverage_problems: Callable


# The commands.

def command_line(source, description, argv=None):
    """The command line of a reading: start and submit."""
    parser = argparse.ArgumentParser(
        description=description, epilog=input_help(source), formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    start_help = (f"gather the {source.what}'s source and write the tasks, for the subagents that read it; prints one "
                  "line of JSON: what was gathered, and the tasks' lines, 'Task <name>: <path>'"
                  + (", and judge, the judge's, its file written once every part is submitted, unless none listed anything" if source.readers
                     else ", or path, the empty summary's, with nothing to read"))
    submit_help = ("check the answer, JSON on stdin, and write it; prints one line of JSON: path, the summary's"
                   if not source.readers else
                   "check the answer, JSON on stdin: a part's items, or, with no --task, the judge's summary; prints "
                   "one line of JSON: the task, and the judge's line once every part is in, or path, the summary's, "
                   "when the judge's isn't needed")
    for name, help in (("start", start_help), ("submit", submit_help)):
        command = commands.add_parser(name, help=help, description=help)
        command.add_argument("--prep", required=True,
                             help="the prep's folder, <Person>_<YY-MM-DD>, as init_prep.py printed it")
        if name == "start" and source.until_today:
            command.add_argument("--until-today", action="store_true",
                                 help="read up to today, past the period's end, only to change a finished prep")
        if name == "submit" and source.readers:
            command.add_argument("--task", help="a part's task, as start printed it, such as month:2026-09; "
                                 "without it, the answer is the judge's")
    args = parser.parse_args(argv)
    if args.command == "start":
        if getattr(args, "until_today", False):
            source.until_today(args.prep)
        print(json.dumps(start(source, args.prep), ensure_ascii=False))
    else:
        task = getattr(args, "task", None)
        print(json.dumps(submit(source, args.prep, stdin_json(input_help(source, task)), task),
              ensure_ascii=False))


def start(source, prep):
    """Gather the source of the prep `prep` and write its tasks, one for each
    part the readers read, or the judge's alone, with the items the script
    lists written to _raw; returns what was gathered and the tasks' lines,
    'Task <name>: <path>', and the judge's, its file written once every part
    is submitted. With nothing to read, it records the empty summary and
    returns its path instead."""
    material = source.gather(prep) if source.gather else None
    clear_folder(work_dir(source, prep))
    clear_folder(raw_path(source, prep))
    if source.readers:
        parts = source.readers.parts(prep)
        return {"tasks": [write_task_file(task_folder(source, prep, task), task, reader_task(source, prep, task, part))
                          for task, part in parts.items()],
                "judge": task_line(source.name, work_dir(source, prep))}
    assert material is not None  # a source without readers gathers its own
    content = material["content"]
    result = {key: value for key, value in material.items()
              if key not in ("content", "empty")}
    write_prep_file(prep, f"{RAW_DIR}/{raw_name(source)}",
                    {"items": content["items"]})
    if material["empty"]:
        return {**result, "path": write_prep_file(prep, source.output, {part: [] for part in SUMMARY_PARTS})}
    return {**result, "task": write_judge(source, prep, content)}


def submit(source, prep, answer, task=None):
    """Check the answer `answer` to the task `task` of the prep `prep`, a
    part's items or, with no task, the judge's summary, and write it: a part's
    to the working folder, the judge's to the prep, each point's cites turned
    into its evidence, in order(); the last part also writes the judge's
    task; with nothing listed in any part, it records the empty summary
    instead. Returns the task and the judge's line, or the summary's path. Exits,
    writing nothing, with every problem and the answer's shape."""
    parts = source.readers.parts(prep) if source.readers else {}
    if task is None:
        return submit_judge(source, prep, answer)
    if task not in parts:
        raise SystemExit(
            f"{task!r} isn't a task of this prep: start printed them")
    days = days_between(**parts[task])
    problems = reader_problems(source, answer, days)
    if problems:
        raise SystemExit("; ".join(problems) + "\n\n" +
                         input_help(source, task))
    write_work_file(answer_path(source, prep, task), answer)
    result = {"task": task, "items": len(answer["items"])}
    if all(answered(source, prep, name) for name in parts):
        answers = [read_json(answer_path(source, prep, name))
                   for name in parts]
        items = merged_items(answers)
        write_prep_file(prep, f"{RAW_DIR}/{raw_name(source)}", {"items": items, "searched": [
            entry for part in answers for entry in part["searched"]]})
        if items:
            result["judge"] = write_judge(source, prep, {"items": items})
        else:
            result["path"] = write_prep_file(
                prep, source.output, {part: [] for part in SUMMARY_PARTS})
    return result


def submit_judge(source, prep, answer):
    """Check the judge's answer, the summary's parts, each point citing the
    items listed, and write it, each cite turned into its evidence, in
    order(); returns its path."""
    days = source.days(read_json(os.path.join(prep_dir(prep), PERSON)))
    items = load_items(source, prep)
    if problems := answer_problems(source, answer, items, days):
        raise SystemExit("; ".join(problems) + "\n\n" + input_help(source))
    return {"path": write_prep_file(prep, source.output, order(with_evidence(answer, items)))}


def input_help(source, task=None):
    """What to send on stdin to submit the answer of `source`'s reading, with
    a command to copy, in a quoted here-document: a part's, when `task` names
    one, else the judge's, and, with no task, a part's after it."""
    def shown(shape, command):
        example = "\n".join(f"  {line}" for line in shape.splitlines())
        return f"  python3 {source.script} submit --prep Jane-Doe_26-11-10{command} <<'END_OF_INPUT'\n{example}\n  END_OF_INPUT"
    judge = (f"Input, on stdin, for the {source.what}'s summary:\n\n{shown(source.answer_shape, '')}\n\n{SUMMARY_HELP}\n"
             + CITES_HELP.format(what=source.cites)
             + "\n\nEach part is a list of points, [] when there is nothing to keep.")
    if not source.readers:
        return judge + "\n\nPrints one line of JSON: path, the file written."
    reader = (f"Input, on stdin, for a part's task:\n\n{shown(source.readers.answer_shape, ' --task month:2026-09')}"
              f"\n\n{source.readers.help}")
    gives = "the task, and the judge's line once every part is in, or path when no part listed anything"
    if task:
        return f"{reader}\n\nPrints one line of JSON: {gives}."
    return f"{judge}\n\n{reader}\n\nPrints one line of JSON: path, the file written; for a part, {gives}."


# The tasks.

def reader_task(source, prep, task, part):
    """The text of the task of the part `task`, `part` its days: its
    protocol, the person, what to read and how to submit."""
    protocol, body = source.readers.task_text(prep, task, part)
    return "\n\n".join([read_protocol(protocol, source.terms), person_section(prep), body,
                        submit_section(f"{call(source)} submit --prep {prep} --task {task}", source.readers.answer_shape)])


def write_judge(source, prep, content):
    """Write the judge's task of the prep `prep`, from `content`, {items},
    to the working folder: its protocol, the person, the company's values,
    what the source shows and how to submit; returns the line that hands it
    out, 'Task <name>: <path>'."""
    protocol, body = source.task_text(prep, content)
    text = "\n\n".join([read_protocol(protocol, source.terms), person_section(prep), values_section(), body,
                        submit_section(f"{call(source)} submit --prep {prep}", source.answer_shape)])
    return write_task_file(work_dir(source, prep), source.name, text)


def person_section(prep):
    """The person the prep is for, for a task."""
    return f"## The person\n\n{read_json(os.path.join(prep_dir(prep), PERSON))['person']}"


def values_section():
    """The company's values, each with what it means, for a task."""
    return "## The company's values\n\n" + "\n".join(f"- {entry['value']}: {entry['meaning']}"
                                                     for entry in company_setting(VALUES))


# The items and the order.

def merged_items(answers):
    """The items of every part's answer in `answers`, in one list by day,
    each numbered from 1, with its date, link and description; a link listed
    again by a later part is kept once."""
    seen, found = set(), []
    for item in sorted((item for answer in answers for item in answer["items"]),
                       key=lambda item: (item["date"], item["link"])):
        if item["link"] not in seen:
            seen.add(item["link"])
            found.append(item)
    return [{"number": number, **item} for number, item in enumerate(found, 1)]


def order(summary):
    """`summary` with each point's evidence from the most recent, the undated
    first, as the most recent of all, and each part's points by their latest
    dated evidence, those with none dated first: the order every list of the
    prep keeps."""
    def newest(item):
        return newest_key(item["date"])
    return {part: sorted(({**point, "evidence": sorted(point["evidence"], key=newest, reverse=True)}
                          for point in points),
                         key=lambda point: newest_key(latest_day(point["evidence"])), reverse=True)
            for part, points in summary.items()}


# Checking the answers.

def reader_problems(source, answer, days):
    """Why `answer`, a part's, isn't {searched, items}, empty when it is:
    its items by listed_items_problems(), what it declares searched by the source's
    coverage_problems(), both over `days`, the part's."""
    if not (isinstance(answer, dict) and sorted(answer) == ["items", "searched"]):
        return ['the answer must be {"searched": [...], "items": [...]}']
    return listed_items_problems(answer["items"], days) or source.readers.coverage_problems(answer["searched"], days)


def answer_problems(source, parts, items, days):
    """Why `parts` isn't the summary a reading gives, empty when it is: its
    points, each with "cites", at least one, each the number of one of
    `items`, and, its cites turned into evidence, the summary
    summary_problems() takes, over `days`, the days the source was read on."""
    what = f"the {source.what}"
    if not (isinstance(parts, dict) and sorted(parts) == sorted(SUMMARY_PARTS)):
        return summary_problems(parts, what, [])
    problems = []
    for part, points in parts.items():
        fields = point_fields(part, "cites")
        if not (isinstance(points, list) and all(is_point(point, fields) for point in points)):
            problems.append(
                f"{what}'s {part} must be a list of points, each {point_shape(fields)}, or [] for none")
            continue
        problems += [f"{what}'s {part}: {point['point'][:60]!r}...'s cites must each be the number of what it "
                     f"rests on, 1 to {len(items)}" for point in points
                     if not all(number <= len(items) for number in point["cites"])]
    if problems:
        return problems
    return summary_problems(with_evidence(parts, items), what, company_names(VALUES), days, source.undated_context)


def with_evidence(parts, items):
    """`parts`, the summary a reading gives, with each point's cites turned
    into its evidence, each {date, link} of the item cited, `items`, numbered
    from 1: once for a link, as two notes of one journal day share it."""
    def evidence(point):
        cited = [{"date": items[number - 1]["date"], "link": items[number - 1]["link"]}
                 for number in point["cites"]]
        return [item for place, item in enumerate(cited) if item not in cited[:place]]
    return {part: [{**{key: value for key, value in point.items() if key != "cites"}, "evidence": evidence(point)}
                   for point in points] for part, points in parts.items()}


def listed_items_problems(items, days):
    """Why `items`, what a reader found, isn't a list of items, empty when
    it is: each {date, link, description}, the date one of `days`, the link a
    web address, once, and the description of at most MAX_DESCRIPTION_WORDS
    words."""
    if not isinstance(items, list):
        return ['the answer must hold "items": a list, [] when nothing was found']
    problems = []
    for number, item in enumerate(items, 1):
        what = f"item {number}"
        if not (isinstance(item, dict) and sorted(item) == ["date", "description", "link"]):
            problems.append(
                f"{what} must have the fields date, link, description")
            continue
        if item["date"] not in days:
            problems.append(
                f"{what}'s date, {item['date']!r}, must be the day of what it comes from, within the period")
        if not (isinstance(item["link"], str) and item["link"].startswith(WEB_LINK)):
            problems.append(
                f"{what}'s link, {item['link']!r}, must be the address of what it comes from")
        if not (isinstance(item["description"], str) and item["description"].strip()):
            problems.append(f"{what}'s description must be a text")
        elif word_count(item["description"]) > MAX_DESCRIPTION_WORDS:
            problems.append(f"{what}'s description has {word_count(item['description'])} words: keep it to "
                            f"up to {DESCRIPTION_WORDS}")
    links = [item["link"] for item in items if isinstance(item, dict)]
    problems += [f"the link {link!r} is listed more than once: list each once"
                 for link in sorted(set(links)) if links.count(link) > 1]
    return problems


# Where things are.

def work_dir(source, prep):
    """The prep `prep`'s working folder for `source`, in the system's
    temporary folder: its tasks and a part's answer, needed only while a run
    lasts. Exits when the prep isn't there."""
    prep_dir(prep)
    return work_folder(FOLDER_NAME, prep, source.name)


def task_folder(source, prep, task):
    """The folder of the task `task`, which holds its file and answer: the
    working folder for the judge's, or the only task, else a folder for each
    part, such as month/2026-09."""
    work = work_dir(source, prep)
    return work if task == source.name else os.path.join(work, *task.split(":"))


def answer_path(source, prep, task):
    """The file of the answer to the part `task`, in its folder."""
    return os.path.join(task_folder(source, prep, task), ANSWER)


def answered(source, prep, task):
    """Whether the part `task` of the prep `prep` has an answer."""
    return os.path.exists(answer_path(source, prep, task))


def write_work_file(path, value):
    """Write `value` as JSON to the working folder's file `path`."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(json_text(value))


def raw_name(source):
    """The name of `source`'s file in a prep's _raw folder, such as
    notes_items.json: the items it lists, which the summary, notes.json,
    cites."""
    return f"{source.name}_items.json"


def raw_path(source, prep):
    """The path of `source`'s file in the prep `prep`'s _raw folder."""
    return os.path.join(prep_dir(prep), RAW_DIR, raw_name(source))


def load_items(source, prep):
    """The items listed for `source` in the prep `prep`, numbered from 1,
    kept in its _raw folder; exits when they aren't there yet."""
    path = raw_path(source, prep)
    if not os.path.exists(path):
        raise SystemExit(f"The {source.what}'s items aren't listed yet: run {call(source)} start --prep {prep}, "
                         "and submit every part before the judge's answer")
    return read_json(path)["items"]


def read_protocol(name, terms=None):
    """The protocol file `name`'s text, its shared parts filled in, with
    `terms`, a source's words for them, and the command that reads a Jira
    ticket by the path the skill pre-approves."""
    return fill_protocol(PROTOCOL, name, {**POINT_LIMITS, "description_words": DESCRIPTION_WORDS, **(terms or {}),
                                          "jira_ticket": f"{script_command(__file__, 'jira_ticket.py')} --key <key>",
                                          "extract_saved": library_command(__file__, "extract_saved.py")})


def call(source):
    """The command that runs the source's script, by script_command()."""
    return script_command(__file__, source.script)
