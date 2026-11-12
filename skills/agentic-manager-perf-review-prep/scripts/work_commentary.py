"""Writes the commentary on a prep's person's work: start works out its facts and writes the task, submit takes the commentary.

Volume, focus and how they shifted are a reading of figures, so the figures
are worked out once, from the items, and stored in work.json as its facts; a
fresh subagent, which hasn't heard the manager's view, writes a paragraph on
each source from them and cites no figure they don't hold. The task shows
the issues' and pages' titles by area too, so the commentary can name the
work; pull requests are too many to list, and their areas are named already.
"""
import argparse
import json
import os

from common import (ABSENT, COMMENTARY, COMMENTARY_WORDS, FACTS, MAX_COMMENTARY_WORDS, REQUEST, WORK, WORK_LISTS,
                    commentary_problems, fill_protocol, period_days, prep_dir, read_json, script_command, stdin_json,
                    work_facts, work_problems, write_prep_file, write_raw)
from reading import PROTOCOL, person_section, submit_section

TASK = os.path.join("work", "task.md")
ANSWER = """{"jira": "<a paragraph on the Jira work, or null when the person isn't in Jira>",
 "github": "<a paragraph on the pull requests, or null>",
 "notion": "<a paragraph on the Notion pages, or null>"}"""
SCRIPTS = {"jira": "fetch_work.py",
           "github": "fetch_work.py", "notion": "set_notion.py"}


def start(prep):
    """Work out the facts of the prep `prep`'s work, store them in work.json
    and write the commentary's task; returns the line that hands it out,
    'Task work: <path>'. Exits when a source isn't gathered yet."""
    folder = prep_dir(prep)
    path, days = os.path.join(folder, WORK), period_days(
        read_json(os.path.join(folder, REQUEST)))
    work = read_json(path) if os.path.exists(path) else {}
    if missing := [source for source in WORK_LISTS if source not in work]:
        scripts = sorted({SCRIPTS[source] for source in missing})
        raise SystemExit(
            f"{', '.join(missing)} not gathered yet: run {' and '.join(scripts)} first")
    work = {source: work[source] for source in WORK_LISTS}
    facts = work_facts(work, days)
    write_prep_file(prep, WORK, {**work, FACTS: facts})
    return {"task": f"Task work: {write_raw(prep, TASK, task_text(prep, work, facts))}"}


def submit(prep, commentary):
    """Check the commentary `commentary` on the prep `prep`'s work and store
    it in work.json; returns the file's path. Exits, writing nothing, with
    every problem."""
    folder = prep_dir(prep)
    path = os.path.join(folder, WORK)
    work = read_json(path) if os.path.exists(path) else {}
    if FACTS not in work:
        raise SystemExit(f"The work's facts aren't worked out: run {script_command('work_commentary.py')} start "
                         f"--prep {prep} first")
    if problems := commentary_problems(commentary, work):
        raise SystemExit("; ".join(problems) +
                         "\n\nThe answer's shape:\n" + ANSWER)
    work = {**work, COMMENTARY: commentary}
    if problems := work_problems(work, period_days(read_json(os.path.join(folder, REQUEST)))):
        raise SystemExit("; ".join(problems))
    return {"path": write_prep_file(prep, WORK, work)}


def task_text(prep, work, facts):
    """The commentary's task: its protocol, the person, the facts, the
    titles of the issues and pages by area, and how to submit."""
    protocol = fill_protocol(PROTOCOL, "work", {"commentary_words": COMMENTARY_WORDS,
                                                "max_commentary_words": MAX_COMMENTARY_WORDS})
    return "\n\n".join([protocol, person_section(prep),
                        "## The facts\n\n```json\n" +
                        json.dumps(facts, ensure_ascii=False,
                                   indent=1) + "\n```",
                        "## The issues and pages\n\n" + titles(work),
                        submit_section(f"{script_command('work_commentary.py')} submit --prep {prep}", ANSWER)])


def titles(work):
    """The titles of the Jira issues, by parent, and of the Notion pages, by
    where they sit, one line each."""
    lines = []
    if work["jira"] != ABSENT:
        for name in WORK_LISTS["jira"]:
            lines += [f"- Jira {name}, {(item.get('parent') or {}).get('title') or 'no parent'}: {item['title']}"
                      for item in work["jira"][name]]
    if work["notion"] != ABSENT:
        for name in WORK_LISTS["notion"]:
            lines += [f"- Notion {name}, {item['path'] or 'no location'}: {item['title']}"
                      for item in work["notion"][name]]
    return "\n".join(lines) or "None."


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Write the commentary on the prep's person's work in Jira, GitHub and Notion, once all three are "
        "in work.json.")
    commands = parser.add_subparsers(dest="command", required=True)
    for name, help in (("start", "work out the facts of the work, store them in work.json, and write the "
                        "commentary's task, for a subagent; prints one line of JSON: task, 'Task work: <path>'"),
                       ("submit", "check the commentary, JSON on stdin, and store it in work.json; the task's file "
                        "shows its shape. Prints one line of JSON: path, the file written")):
        command = commands.add_parser(name, help=help, description=help)
        command.add_argument("--prep", required=True,
                             help="the prep's folder, <Person>_<YY-MM-DD>, as init_prep.py printed it")
    args = parser.parse_args(argv)
    if args.command == "start":
        print(json.dumps(start(args.prep), ensure_ascii=False))
    else:
        print(json.dumps(submit(args.prep, stdin_json(
            "The answer's shape:\n" + ANSWER)), ensure_ascii=False))


if __name__ == "__main__":
    main()
