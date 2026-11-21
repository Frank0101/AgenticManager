"""Reads the manager's notes on a prep's person: start gathers them and writes the task, submit takes the summary the reading gives.

A note is a journal block that links the person, shown as written in the
block it sits in, with its siblings, dated by its journal day; the person's
pages have no date, so they give only context. All of them are numbered, in
one list, so a point cites the numbers it rests on and the script adds each
one's day and link, as reading.py runs every reading; this script knows only
where the notes are and what the task shows.
"""
import os
from datetime import date

from common import (NOTES, NOTES_END, PERSON, descendants, graph_path, journal_day, links, notes, notes_days, parse_blocks,
                    prep_dir, read_json, write_prep_file)
import reading

ANSWER = """{"going_well": [{"point": "Presented the billing migration to the wider team, to a great reception",
                "values": ["<each company value it clearly shows or calls for, at most 2>"], "cites": [3, 7]}],
 "to_improve": [{"point": "...", "values": [], "cites": [12]}],
 "context": [{"point": "...", "cites": [1]}]}"""


# Gathering the notes.

def gather(prep):
    """The material of the notes: how many notes there are and the pages,
    and the content, {items: [{number, date, link, text}]}: the notes of the
    days notes_days() gives that link the person, by day, then the person's pages, from the
    links the manager confirmed, numbered from 1, a page with no date and its
    title as `page`."""
    folder = prep_dir(prep)
    person = read_json(os.path.join(folder, PERSON))
    wanted = {link.casefold()
              for link in person["sources"]["logseq-fs"]["links"]}
    days = set(notes_days(person))
    journal, pages = [], []
    for folder_name, title, text, file in notes(graph_path()):
        link = os.path.abspath(file)
        if folder_name == "pages":
            if title.casefold() in wanted:
                pages.append({"date": None, "link": link,
                              "text": text.strip(), "page": title})
            continue
        day = journal_day(title)
        if day is None or day.isoformat() not in days:
            continue
        journal += [{"date": day.isoformat(), "link": link, **note}
                    for note in linking_blocks(text, wanted)]
    items = [{"number": number, **item} for number, item in enumerate(
        sorted(journal, key=lambda note: note["date"]) + pages, 1)]
    return {"empty": not items, "journal_notes": len(journal), "pages": [page["page"] for page in pages],
            "content": {"items": items}}


def linking_blocks(text, wanted):
    """[{text}]: each block of the journal `text` that links a page of
    `wanted`, casefolded, shown inside the block it sits in, with that
    block's other nested blocks, so the note keeps the context its siblings
    give; a block at the top shows itself and its nested blocks. A block
    shown already isn't shown again."""
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
        found.append({"text": "\n".join(blocks[n]["line"] for n in tree)})
    return found


# The task.

def task_text(prep, content):
    """(protocol, body) of the reading task: how the notes write the person,
    then every note, numbered, with its day, or its page's title."""
    # The links the manager confirmed, so the subagent knows an alias or a tag
    # is the person.
    person = read_json(os.path.join(prep_dir(prep), PERSON))
    wanted = person["sources"]["logseq-fs"]["links"]
    intro = (f"## The notes\n\nThe notes write {person['person']} as "
             f"{' or '.join(f'[[{link}]]' for link in wanted)}, or as a tag, such as #{wanted[0]}.\n\n")
    return "notes-judge", intro + "\n\n".join(
        f"### Note {item['number']}, " +
        (f"page {item['page']}" if item["date"] is None else item["date"])
        + f"\n\n{item['text']}" for item in content["items"])


def until_today(prep):
    """Record that the notes of the prep `prep` run to today, for a change to
    the finished prep: its NOTES_END, today, when later than the period."""
    folder = prep_dir(prep)
    person = read_json(os.path.join(folder, PERSON))
    today = date.today().isoformat()
    if today > person["end"]:
        write_prep_file(prep, PERSON, {**person, NOTES_END: today})


SOURCE = reading.Source(name="notes", script="read_notes.py", output=NOTES, what="notes summary", task_text=task_text,
                        answer_shape=ANSWER, cites="as the task numbers the notes",
                        terms={"cited": "notes",
                               "citations_more": "A page has no day, so it can back only a `context` point."},
                        gather=gather, undated_context=True, days=notes_days,
                        until_today=until_today)


def main(argv=None):
    reading.command_line(SOURCE, "Read the manager's notes on the prep's person: start writes the task for the "
                         "subagent that reads every note, each numbered; submit checks the summary it gives, each "
                         "point citing the notes it rests on, and writes it.", argv)


if __name__ == "__main__":
    main()
