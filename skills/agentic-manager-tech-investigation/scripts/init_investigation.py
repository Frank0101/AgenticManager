"""Prepares an investigation's new folder, replacing any earlier one of the same day.

Every run starts from scratch, so a report is always built from fresh research:
a folder of the same topic and day is deleted first, and nothing an earlier run
left is read. The script stops before creating anything when a source group has
no usable source, or when the code comes through gh and gh can't be used. Every
investigation starts the same way, so the script writes the ledger's skeleton
with its first questions, the first orienting the rest, and creates _examples,
so the user sees where approved reports go before saving one.
"""
from datetime import date
import os
import re
import subprocess

from common import (DESIGN, citation, DESIGN_SUBSECTIONS, EXAMPLE_DESCRIPTION, KEPT_EXAMPLES, GITHUB_CLI, GROUPS, JIRA_API, JIRA_GROUP, QUEUE,
                    WHY_GOOD, read_description, FOLDER_NAME, INVESTIGATION, LEDGER, LEDGER_SECTIONS, QUEUE_HEADER,
                    QUEUE_SUBSECTIONS, TOPIC, GhError, anchored, clear_folder, day_folder,
                    enabled_sources, gh_signed_in, output_folder, table, write_output_file)

# An example's folder: its investigation's, and --<n> for a later copy of the
# same day's example, as save_example.py names it.
EXAMPLE = re.compile(rf"{INVESTIGATION.pattern}(?:--(?P<copy>\d+))?")
# The first questions, as (kind of source, question), X the topic in words. The
# first orients: what the topic is and what sits next to it, so the user decides
# the scope on recorded evidence before research goes deep, and every other seed
# waits for it. The rest are each narrow enough to answer from one source, and
# together cover the skill's three aims; the documentation gets two, as the
# purpose and the target design rest on different documents.
SEED_QUESTIONS = [
    ("documentation", "What is X, which documents and systems make it up, and what other projects, platforms or "
                      "names sit next to it?"),
    ("documentation", "What problem does X solve, for whom, and with what impact and success measures?"),
    ("documentation", "What target design and decisions do the documents record for X?"),
    (JIRA_GROUP, "What is done, in progress and planned for X, and what evidence backs each Done ticket?"),
    ("source_control", "What code for X is merged or in an open pull request, and how does it work: components, "
                       "connections, identities?"),
]


def init(topic, today=None, run=subprocess.run):
    """Create the investigation's folder for `topic` and its ledger, after
    checking its sources can be used; returns where it is and what it uses."""
    if not TOPIC.fullmatch(topic):
        raise SystemExit(f"{topic!r} must be words of letters and digits joined by hyphens, "
                         "such as Payments-Retry-Service")
    sources = usable_sources()
    missing = [GROUPS[group] for group, names in sources.items() if not names]
    if missing:
        raise SystemExit(f"No usable source for: {', '.join(missing)}. The investigation needs the code, the "
                         "tracker and the documentation: enable a source for each in the config, as "
                         "check_config.py shows, then run investigate.py start again")
    check_gh(sources, run)
    folder, temporary = output_folder(FOLDER_NAME)
    relative = day_folder(topic, today or date.today())
    path = os.path.join(folder, relative)
    replaced = clear_folder(path)
    os.makedirs(os.path.join(folder, KEPT_EXAMPLES), exist_ok=True)
    write_output_file(FOLDER_NAME, f"{relative}/{LEDGER}",
                      ledger_skeleton(topic, first_questions(topic)).encode("utf-8"))
    return {"folder": folder, "temporary": temporary, "investigation": relative,
            "investigation_dir": path, "replaced": replaced,
            "sources": {GROUPS[group]: names for group, names in sources.items()},
            "examples": examples(folder)}


def usable_sources():
    """{group: its enabled sources this skill can use}, in GROUPS' order: any
    of the code and the documentation, and jira-api for the tracker, which
    tickets.py reads."""
    return {group: [name for name in enabled_sources(group) if group != JIRA_GROUP or name == JIRA_API]
            for group in GROUPS}


def check_gh(sources, run=subprocess.run):
    """Exits, saying what to do, when the code comes through gh and gh can't
    be used: not installed, or not signed in."""
    if GITHUB_CLI not in sources["source_control"]:
        return
    try:
        signed_in = gh_signed_in(run)
    except GhError:
        raise SystemExit("github-cli is enabled but gh can't be run: install it, then run investigate.py start "
                         "again")
    if not signed_in:
        raise SystemExit(
            "gh isn't signed in: run gh auth login, then run investigate.py start again")


def first_questions(topic):
    """The first research questions, as rows: SEED_QUESTIONS about the topic,
    each after the first waiting for it."""
    return [[f"Q{number:02d}", f"Seed ({GROUPS[group]})", question.replace("X", topic.replace("-", " ")),
             "None" if number == 1 else citation("Q01"), ""]
            for number, (group, question) in enumerate(SEED_QUESTIONS, 1)]


def ledger_skeleton(topic, ready=()):
    """The ledger's fixed sections and tables, empty but for the `ready`
    questions, as rows."""
    parts = [f"# {topic.replace('-', ' ')} research ledger"]
    for section in LEDGER_SECTIONS:
        parts.append(f"## {section}")
        if section == QUEUE:
            for subsection in QUEUE_SUBSECTIONS:
                rows = [[anchored(row[0]), *row[1:]]
                        for row in ready] if subsection == "Ready" else []
                parts += [f"### {subsection}",
                          table(QUEUE_HEADER, rows)] + ([] if rows else ["None."])
        elif section == DESIGN:
            for subsection in DESIGN_SUBSECTIONS:
                parts += [f"### {subsection}", "None yet."]
        else:
            parts.append("None yet.")
    return "\n\n".join(parts) + "\n"


def examples(folder):
    """[{folder, documents, note}] of the approved examples, newest first: by
    date, then by copy."""
    root = os.path.join(folder, KEPT_EXAMPLES)
    found = []
    for name in os.listdir(root) if os.path.isdir(root) else []:
        match = EXAMPLE.fullmatch(name)
        path = os.path.join(root, name)
        if match and os.path.isdir(path):
            documents = sorted(f for f in os.listdir(path)
                               if f.endswith(".md") and f != EXAMPLE_DESCRIPTION)
            note = read_description(os.path.join(path, EXAMPLE_DESCRIPTION))[
                1].get(WHY_GOOD, "")
            found.append(((match["date"], int(match["copy"] or 1)),
                          {"folder": path, "documents": documents, "note": note}))
    return [example for _, example in sorted(found, key=lambda item: item[0], reverse=True)]
