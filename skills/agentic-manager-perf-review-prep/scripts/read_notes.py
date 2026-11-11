"""Reads the manager's notes on a prep's person: start gathers them and writes the tasks, submit takes each answer, finished reports the result.

A note is a journal block that links the person, shown in the block it sits
in, with its siblings, dated by its journal day; the person's pages have no
date, so they give only context. Subagents write a synopsis of each, a month
of journals or the pages a task, and a last one judges and merges them, as
reading.py runs every reading; this script knows only where the notes are
and what each task shows, each note numbered so none goes without a synopsis.
"""
import os
import re
from datetime import date

from common import IDENTITIES, NOTES, REQUEST, graph_path, links, notes, prep_dir, read_json
import reading
from reading import MERGE

PAGES = "pages"
# A journal's file name, such as 2026_07_22, and a block's first line.
JOURNAL = re.compile(r"(\d{4})_(\d{2})_(\d{2})")
BLOCK = re.compile(r"^(\s*)- ")
# What marks a line that links the person in the block a note is shown in.
MARK = "→ "
READING_ANSWER = """{"items": [
  {"note": 1, "synopsis": "Presented the billing migration to the wider team; Sam asked for the slides, and Jane..."},
  {"note": 2, "synopsis": "..."}
 ]}"""
MERGE_ANSWER = """{"going_well": [{"point": "...", "values": ["<each company value it clearly shows, at most two>"],
                 "dates": ["YYYY-MM-DD", ...]}],
 "to_improve": [{"point": "...", "values": [], "dates": ["YYYY-MM-DD"]}],
 "context": ["..."],
 "in_doubt": ["YYYY-MM-DD: what the note says, and why you left it out"]}"""


# Gathering the notes.

def gather(prep):
    """The material of the notes: how many notes there are, the months and
    the pages, the reading tasks, a month each, then the pages, and the
    content, {months: {YYYY-MM: [{date, text}]}, pages: [{title, text}]}:
    the notes of the period that link the person and the person's pages,
    from the links the manager confirmed."""
    folder = prep_dir(prep)
    request = read_json(os.path.join(folder, REQUEST))
    found = read_json(os.path.join(folder, IDENTITIES))["logseq-fs"]
    wanted = {link.casefold() for link in found.get("links", [])}
    first, last = date.fromisoformat(
        request["start"]), date.fromisoformat(request["end"])
    months, pages = {}, []
    if not wanted:
        return material(months, pages)
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
    return material(months, pages)


def material(months, pages):
    """What gather() returns for the notes `months` and the pages `pages`."""
    return {"journal_notes": sum(len(batch) for batch in months.values()), "months": sorted(months),
            "pages": [page["title"] for page in pages],
            "tasks": [f"month:{month}" for month in sorted(months)] + ([PAGES] if pages else []),
            "content": {"months": months, "pages": pages}}


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

def task_text(prep, task, material):
    """(protocol, body) of the reading task `task`: a month of notes, or the
    person's pages, each numbered."""
    content = material["content"]
    if task == PAGES:
        return "pages", "## The notes\n\n" + "\n\n".join(
            f"### Note {number}, page {page['title']}\n\n{page['text']}"
            for number, page in enumerate(content["pages"], 1))
    return "notes", "## The notes\n\n" + "\n\n".join(
        f"### Note {number}, {note['date']}\n\n{note['text']}"
        for number, note in enumerate(content["months"][task.split(":")[1]], 1))


def task_notes(material, task):
    """The day of each note of the reading task `task`, in order, null for
    each of the pages."""
    if task == PAGES:
        return [None] * len(material["content"]["pages"])
    return [note["date"] for note in material["content"]["months"][task.split(":")[1]]]


def merge_days(material):
    """The days a merged point may cite: those of every note read."""
    return sorted({note["date"] for notes_of in material["content"]["months"].values() for note in notes_of})


SOURCE = reading.Source(name="notes", script="read_notes.py", output=NOTES, what="notes summary", gather=gather,
                        task_text=task_text, merge_days=merge_days, task_notes=task_notes,
                        answers={"reading": READING_ANSWER, MERGE: MERGE_ANSWER})


def main(argv=None):
    reading.command_line(SOURCE, "Read the manager's notes on the prep's person: start writes a task for each month and "
                         "the person's pages, each for a subagent that writes a synopsis of every note, and names the merge task, written once they are all "
                         "answered; finished says what the merge made of them.", argv)


if __name__ == "__main__":
    main()
