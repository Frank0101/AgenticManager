"""Reads the manager's notes on a prep's person: start gathers them and writes the tasks, submit takes each answer, finished reports the result.

The notes are many and mostly not feedback, so subagents judge them, a month
of journals or the person's pages a task, and a last one merges what they
found, so a pattern across months becomes one point. A note is a journal block
that links the person, shown in the block it sits in, with its siblings,
dated by its journal day; pages have no date, so they give only context. The
flow is fixed: the reading tasks, then the merge, once they are all
answered; only the merged summary goes to the prep, as notes.json.
"""
import argparse
import json
import os
import re
import shutil
import sys
import tempfile
from datetime import date

from common import (FOLDER_NAME, IDENTITIES, MAX_POINT_WORDS, NOTES, REQUEST, SUMMARY_PARTS, VALUED_PARTS, VALUES,
                    company_names, company_setting, fill_protocol, graph_path, links, notes, notes_problems, prep_dir,
                    read_json, stdin_json, write_prep_file)

PROTOCOL = os.path.join(os.path.dirname(
    os.path.realpath(__file__)), "..", "protocol")
MATERIAL = "material.json"
TASK_FILE = "task.md"
ANSWER = "answer.json"
PAGES, MERGE = "pages", "merge"
# A journal's file name, such as 2026_07_22, and a block's first line.
JOURNAL = re.compile(r"(\d{4})_(\d{2})_(\d{2})")
BLOCK = re.compile(r"^(\s*)- ")
# What marks a line that links the person in the block a note is shown in.
MARK = "→ "
DAY_ANSWER = """{"items": [
  {"part": "going_well", "point": "Presented the billing migration to the wider team, with many follow-ups",
   "value": "<a company value, or null>", "date": "YYYY-MM-DD"},
  {"part": "context", "point": "On leave for two weeks", "value": null, "date": "YYYY-MM-DD"}
 ],
 "in_doubt": ["YYYY-MM-DD: what the note says, and why you left it out"]}"""
PAGES_ANSWER = """{"items": [
  {"part": "context", "point": "On the promotion track since the spring", "value": null, "date": null}
 ],
 "in_doubt": ["what the page says, and why you left it out"]}"""
MERGE_ANSWER = """{"going_well": [{"point": "...", "value": "<a company value, or null>", "dates": ["YYYY-MM-DD", ...]}],
 "to_improve": [{"point": "...", "value": null, "dates": ["YYYY-MM-DD"]}],
 "context": ["..."],
 "promoted": [{"line": "<the in-doubt line, exactly as listed>", "settled_by": "<what settled it>"}]}"""


# The commands.

def start(prep):
    """Gather the notes of the prep `prep` into its working folder, emptied
    first, and write every reading task, as they are independent and few, a
    month each; returns how many notes there are, a line for each task,
    'Task <name>: <path>', and the merge task's line, its file written once
    every reading task is answered. With nothing to read, it records the
    empty summary and returns what finished() says."""
    material = gather(prep)
    work = work_dir(prep)
    shutil.rmtree(work, ignore_errors=True)
    os.makedirs(work)
    with open(os.path.join(work, MATERIAL), "w", encoding="utf-8") as f:
        json.dump(material, f, ensure_ascii=False, indent=1)
    result = {"journal_notes": sum(len(batch) for batch in material["months"].values()),
              "months": sorted(material["months"]), "pages": [page["title"] for page in material["pages"]]}
    if not reading_names(material):
        write_prep_file(prep, NOTES, {part: [] for part in SUMMARY_PARTS})
        return {**result, **finished(prep)}
    return {**result, "tasks": [write_task(prep, task, reading_task(prep, task, material))
                                for task in reading_names(material)],
            "merge": f"Task {MERGE}: {task_path(work, MERGE)}"}


def submit(prep, task, answer):
    """Check the answer `answer` to the task `task` of the prep `prep`, and
    write it; the answer to the last reading task also writes the merge
    task, and the merge's summary goes to the prep as notes.json. Exits,
    writing nothing, with every problem."""
    material, values = load_material(prep), company_names(VALUES)
    promoted = []
    if task == MERGE:
        # A point may come from a note left out in doubt, so its days are
        # those of every note read, not only of the items.
        days = sorted(
            {note["date"] for notes_of in material["months"].values() for note in notes_of})
        if isinstance(answer, dict):
            promoted = answer.pop("promoted", [])
        problems = notes_problems(answer, values, days) + \
            promoted_problems(promoted, doubts(prep, material))
    elif task in reading_names(material):
        problems = items_problems(answer, values, task_days(material, task))
    else:
        raise SystemExit(
            f"{task!r} isn't a task of this prep: start printed them")
    if problems:
        raise SystemExit("; ".join(problems) +
                         "\n\nThe answer's shape:\n" + answer_shape(task))
    work = work_dir(prep)
    path = os.path.join(work, *task.split(":"), ANSWER)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({**answer, "promoted": promoted} if task ==
                  MERGE else answer, f, ensure_ascii=False, indent=1)
    if task == MERGE:
        write_prep_file(prep, NOTES, answer)
        return {"task": task, "notes": os.path.join(prep_dir(prep), NOTES)}
    if all(answered(work, name) for name in reading_names(material)):
        write_task(prep, MERGE, merge_task(prep, material))
    return {"task": task, "items": len(answer["items"])}


def finished(prep):
    """What the agent tells the manager once the notes are merged: where the
    summary is, what the reading tasks left out in doubt and is still out,
    each as they wrote it, those the merge made points, and the command that
    submits a correction."""
    material = load_material(prep)
    promoted = read_answer(prep, MERGE).get(
        "promoted", []) if answered(work_dir(prep), MERGE) else []
    made_points = {entry["line"] for entry in promoted}
    return {"finished": True, "notes": os.path.join(prep_dir(prep), NOTES),
            "in_doubt": [doubt for doubt in doubts(prep, material) if doubt not in made_points],
            "promoted": promoted, "correct": f"{call()} submit --prep {prep} --task {MERGE}"}


# Gathering the notes.

def gather(prep):
    """{months: {YYYY-MM: [{date, text}]}, pages: [{title, text}]}:
    the notes of the period that link the person, by month, and the
    person's pages, from the links the manager confirmed."""
    folder = prep_dir(prep)
    request = read_json(os.path.join(folder, REQUEST))
    found = read_json(os.path.join(folder, IDENTITIES))["logseq-fs"]
    wanted = {link.casefold() for link in found.get("links", [])}
    first, last = date.fromisoformat(
        request["start"]), date.fromisoformat(request["end"])
    months, pages = {}, []
    if not wanted:
        return {"months": months, "pages": pages}
    for folder_name, title, text in notes(graph_path()):
        if folder_name == "pages":
            if title.casefold() in wanted:
                pages.append({"title": title, "text": text.strip()})
            continue
        day = journal_day(title)
        if day is None or not first <= day <= last:
            continue
        for note in linking_blocks(text, wanted):
            months.setdefault(f"{day:%Y-%m}", []).append(
                {"date": day.isoformat(), **note})
    return {"months": months, "pages": pages}


def journal_day(title):
    """The day of the journal whose file is `title`, such as 2026_07_22, or
    None when it isn't a journal's name."""
    match = JOURNAL.fullmatch(title)
    if not match:
        return None
    try:
        return date(int(match[1]), int(match[2]), int(match[3]))
    except ValueError:
        return None


def linking_blocks(text, wanted):
    """[{text}]: each block of the journal `text` that links a page of
    `wanted`, casefolded, shown inside the block it sits in, with that
    block's other nested blocks, so the note keeps the context its siblings
    give; a block at the top shows itself and its nested blocks. Each line
    that links the person starts with MARK, and a block shown already isn't
    shown again."""
    blocks = parse_blocks(text)
    linking = [number for number, block in enumerate(blocks)
               if any(link.casefold() in wanted for link in links(block["text"]))]
    shown, found = set(), []
    for number in linking:
        if number in shown:
            continue
        parent = blocks[number]["parent"]
        root = number if parent is None else parent
        tree = [root] + descendants(blocks, root)
        shown.update(tree)
        found.append({"text": "\n".join(
            (MARK if n in linking else "") + blocks[n]["line"] for n in tree)})
    return found


def parse_blocks(text):
    """The blocks of an outline, in order: {depth, parent, text, line}, line
    the block as written, with its indent, and text without it."""
    blocks, stack = [], []
    for raw in text.split("\n"):
        match = BLOCK.match(raw)
        if not match:
            if blocks and raw.strip():
                blocks[-1]["text"] += "\n" + raw.strip()
                blocks[-1]["line"] += "\n" + raw.rstrip()
            continue
        depth = len(match[1].replace("    ", "\t").replace("  ", "\t"))
        while stack and blocks[stack[-1]]["depth"] >= depth:
            stack.pop()
        blocks.append({"depth": depth, "parent": stack[-1] if stack else None,
                       "text": raw[match.end():].strip(), "line": raw.rstrip()})
        stack.append(len(blocks) - 1)
    return blocks


def descendants(blocks, number):
    """The numbers of the blocks nested under block `number`, in order."""
    found = []
    for later in range(number + 1, len(blocks)):
        if blocks[later]["depth"] <= blocks[number]["depth"]:
            break
        found.append(later)
    return found


# The tasks.

def reading_task(prep, task, material):
    """The text of the reading task `task`: a month of notes, or the
    person's pages."""
    person = read_json(os.path.join(prep_dir(prep), REQUEST))["person"]
    if task == PAGES:
        notes_text = "\n\n".join(
            f"### Page {page['title']}\n\n{page['text']}" for page in material["pages"])
        protocol = "pages"
    else:
        notes_text = "\n\n".join(f"### {note['date']}\n\n{note['text']}"
                                 for note in material["months"][task.split(":")[1]])
        protocol = "notes"
    return "\n\n".join([read_protocol(protocol), f"## The person\n\n{person}", values_section(),
                        links_section(), f"## The notes\n\n{notes_text}", submit_section(prep, task)])


def merge_task(prep, material):
    """The text of the merge task: every item the reading tasks found, to
    merge into one summary, and what they left out in doubt, which another
    month's note may settle. The doubts themselves aren't merged: finished()
    hands them to the manager as written."""
    person = read_json(os.path.join(prep_dir(prep), REQUEST))["person"]
    found = [json.dumps(item, ensure_ascii=False)
             for name in reading_names(material) for item in read_answer(prep, name)["items"]]
    return "\n\n".join([read_protocol("merge"), f"## The person\n\n{person}", values_section(),
                        "## What the reading found\n\n" +
                        ("\n".join(found) or "Nothing."),
                        "## What the reading left out in doubt\n\n" +
                        ("\n".join(
                            f"- {doubt}" for doubt in doubts(prep, material)) or "Nothing."),
                        submit_section(prep, MERGE)])


def values_section():
    """The company's values, each with what it means, for a task."""
    return "## The company's values\n\n" + "\n".join(f"- {entry['value']}: {entry['meaning']}"
                                                     for entry in company_setting(VALUES))


def links_section():
    """How a task reads a Jira ticket a note links to: the command, by the
    path the skill pre-approves."""
    script = os.path.join(os.path.dirname(
        os.path.abspath(call().split(" ", 1)[1])), "jira_ticket.py")
    return f"## Reading links\n\nA Jira ticket: `python3 {script} --key <key>`, such as PROJ-123."


def submit_section(prep, task):
    """How a task submits its answer: the command, and the answer's shape."""
    return (f"## Submit\n\nSubmit your answer, as JSON in a quoted here-document:\n\n```bash\n"
            f"{call()} submit --prep {prep} --task {task} <<'END_OF_INPUT'\n{answer_shape(task)}\nEND_OF_INPUT\n```\n\n"
            "If the script refuses it, fix every problem it names and submit again, until it is accepted.")


def answer_shape(task):
    """The shape of the answer to `task`."""
    return {MERGE: MERGE_ANSWER, PAGES: PAGES_ANSWER}.get(task, DAY_ANSWER)


def write_task(prep, task, text):
    """Write the task `task`'s text to its file; returns the line that hands
    it out, 'Task <name>: <path>'."""
    path = task_path(work_dir(prep), task)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text + "\n")
    return f"Task {task}: {path}"


# Checking the answers.

def items_problems(answer, values, days):
    """Why `answer` isn't a reading task's answer, empty when it is: items,
    each a part of SUMMARY_PARTS, a point of a sentence, a value null or one
    of `values`, null for context, and a date, one of `days`, or, with no
    days, as for the person's pages, null and only context; and in_doubt, a
    list of texts."""
    if not (isinstance(answer, dict) and sorted(answer) == ["in_doubt", "items"] and isinstance(answer["items"], list)
            and isinstance(answer["in_doubt"], list) and all(isinstance(doubt, str) for doubt in answer["in_doubt"])):
        return ['the answer must be {"items": [...], "in_doubt": [...]}, each list [] when it has none']
    problems = []
    for number, item in enumerate(answer["items"], 1):
        what = f"item {number}"
        if not (isinstance(item, dict) and sorted(item) == ["date", "part", "point", "value"]):
            problems.append(
                f"{what} must have the fields part, point, value, date")
            continue
        if item["part"] not in SUMMARY_PARTS or (not days and item["part"] != "context"):
            problems.append(f"{what}'s part, {item['part']!r}, must be "
                            + (", ".join(SUMMARY_PARTS) if days else "context: pages give only context"))
        if not (isinstance(item["point"], str) and item["point"].strip()) or len(str(item["point"]).split()) > MAX_POINT_WORDS:
            problems.append(
                f"{what}'s point must be a sentence of at most {MAX_POINT_WORDS} words")
        if item["value"] is not None and (item["part"] not in VALUED_PARTS or item["value"] not in values):
            problems.append(f"{what}'s value, {item['value']!r}, must be one of the company's: {', '.join(values)}, "
                            "or null when none fits; context has none")
        if (item["date"] not in days) if days else item["date"] is not None:
            problems.append(f"{what}'s date, {item['date']!r}, must be "
                            + ("the day of the note it comes from" if days else "null: pages have no date"))
    return problems


def promoted_problems(promoted, left_out):
    """Why `promoted`, the notes left out in doubt the merge made points,
    isn't a list of {line, settled_by}, each line exactly one of
    `left_out`, empty when it is."""
    if not (isinstance(promoted, list) and all(isinstance(entry, dict) and sorted(entry) == ["line", "settled_by"]
                                               and all(isinstance(value, str) for value in entry.values())
                                               for entry in promoted)):
        return ['"promoted" must be a list of {"line": "...", "settled_by": "..."}, [] when no note left out in '
                'doubt became a point']
    return [f"promoted line {entry['line'][:60]!r}... isn't one of the notes left out in doubt: copy it exactly"
            for entry in promoted if entry["line"] not in left_out]


# Where things are.

def work_dir(prep):
    """The prep `prep`'s working folder for its notes: in the system's
    temporary folder, so the output folder holds only the prep's files, and
    start empties it, never finding what an earlier run left. Each answer is
    a file of its own, so subagents submitting at once never write over each
    other."""
    return os.path.join(tempfile.gettempdir(), FOLDER_NAME, prep, "notes")


def task_path(work, task):
    """The file of `task` in the working folder `work`."""
    return os.path.join(work, *task.split(":"), TASK_FILE)


def answered(work, task):
    """Whether `task` has an answer in the working folder `work`."""
    return os.path.exists(os.path.join(work, *task.split(":"), ANSWER))


def read_answer(prep, task):
    """The answer to `task`, as submitted."""
    return read_json(os.path.join(work_dir(prep), *task.split(":"), ANSWER))


def load_material(prep):
    """What start gathered for the prep `prep`; exits when it hasn't run."""
    path = os.path.join(work_dir(prep), MATERIAL)
    if not os.path.exists(path):
        raise SystemExit(
            f"The notes of {prep} aren't gathered: run {call()} start --prep {prep} first")
    return read_json(path)


def doubts(prep, material):
    """What the reading tasks left out in doubt, each line as they wrote it,
    in the tasks' order."""
    return [doubt for name in reading_names(material) for doubt in read_answer(prep, name)["in_doubt"]]


def reading_names(material):
    """The reading tasks of `material`: each month, then the pages."""
    return [f"month:{month}" for month in sorted(material["months"])] + ([PAGES] if material["pages"] else [])


def task_days(material, task):
    """The days of the notes of the reading task `task`, none for the pages."""
    if task == PAGES:
        return []
    return sorted({note["date"] for note in material["months"][task.split(":")[1]]})


def read_protocol(name):
    """The protocol file `name`'s text, its shared parts filled in."""
    return fill_protocol(PROTOCOL, name)


def call():
    """The command that runs this script, by the path the agent ran it with,
    so every command a task names matches the one the skill pre-approves."""
    path = sys.argv[0] if sys.argv[0].endswith("read_notes.py") else __file__
    return f"python3 {os.path.abspath(path)}"


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Read the manager's notes on the prep's person: start writes a task for each month and the "
        "person's pages, each for a subagent, and names the merge task, written once they are all answered; "
        "finished says what the merge made of them.")
    commands = parser.add_subparsers(dest="command", required=True)
    for name, help in (("start", "gather the notes of the period that link the person, and their pages, emptying "
                        "the working folder, and write the reading tasks; prints one line of JSON: how many notes, "
                        "by month, tasks, a line 'Task <name>: <path>' for each, and merge, the merge task's line"),
                       ("submit", "check a task's answer, JSON on stdin, and write it; the task's file shows its "
                        "shape and the command to copy. Prints one line of JSON: the task, and its items or, for "
                        "the merge, the notes' path"),
                       ("finished", "once the merge is submitted: prints one line of JSON: the notes' path, "
                        "in_doubt, what the reading left out in doubt, promoted, those the merge made points, and "
                        "correct, the command that submits a correction")):
        command = commands.add_parser(name, help=help, description=help)
        command.add_argument("--prep", required=True,
                             help="the prep's folder, <Person>_<YY-MM-DD>, as init_prep.py printed it")
        if name == "submit":
            command.add_argument("--task", required=True,
                                 help="the task's name, as start printed it, such as month:2026-07")
    args = parser.parse_args(argv)
    if args.command == "start":
        print(json.dumps(start(args.prep), ensure_ascii=False))
    elif args.command == "finished":
        if not answered(work_dir(args.prep), MERGE) and reading_names(load_material(args.prep)):
            raise SystemExit(
                "The merge isn't submitted yet: run finished once its subagent has finished")
        print(json.dumps(finished(args.prep), ensure_ascii=False))
    else:
        answer = stdin_json("The answer's shape:\n" + answer_shape(args.task))
        print(json.dumps(submit(args.prep, args.task, answer), ensure_ascii=False))


if __name__ == "__main__":
    main()
