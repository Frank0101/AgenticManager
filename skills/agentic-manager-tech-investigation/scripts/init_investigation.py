"""Prepares an investigation's new folder, replacing any earlier one of the same day.

    python3 init_investigation.py --topic <Topic>

<Topic> is short and filename-safe: capitalised words or acronyms joined by
hyphens, such as Payments-Retry-Service. The investigation's folder is
<Topic>_<YY-MM-DD>, today's date, in the skill's output folder. Every run starts
from scratch: a folder of the same topic and day is deleted first, so a report
is always built from fresh research, never from the leftovers of an earlier one,
and nothing an earlier run left, on this or another day, is read or reused. The
new folder gets the ledger's skeleton: its fixed sections and tables, the first
research actions (one search of the topic per source group, in the sources'
order of authority: code, then tracker, then documentation), and the sources
used, in its boundary section. How every investigation starts is the same, so
it is the script's, and research begins with the first call. gh being
signed in is checked here, before any work, when the code comes through it.
The _examples folder beside it is created if missing, so the user sees where
approved reports go before saving one.

Prints one line of JSON:
  folder, temporary   the skill's output folder, and whether it is temporary
  investigation       the folder's path relative to `folder`, for --path
  investigation_dir   its absolute path
  replaced            whether a folder of the same topic and day was deleted
  sources             {group: the enabled sources the skill uses for it}: the
                      documentation and the code through an mcp or cli source,
                      the tracker through jira-api
  missing             the groups with no usable source
  examples            the approved examples of the report, newest first: their
                      folder, documents and the note on what makes each good,
                      read from its description.md
"""
import argparse
from datetime import date
import json
import os
import re
import subprocess

from common import (BOUNDARY, EXAMPLE_DESCRIPTION, EXAMPLES, GROUPS, QUEUE, REGISTER, WHY_GOOD, TABLE_HEADINGS, FOLDER_NAME,
                    INVESTIGATION, LEDGER, LEDGER_SECTIONS, QUEUE_HEADER, QUEUE_SUBSECTIONS, SOURCE_HEADER, TOPIC,
                    anchored, clear_folder, day_folder, enabled_sources, output_folder, table, write_output_file)
import output_diagram

# An example's folder: its investigation's, and --<n> for a later copy of the
# same day's example, as save_example.py names it.
EXAMPLE = re.compile(rf"{INVESTIGATION.pattern}(?:--(?P<copy>\d+))?")


def init(topic, today=None, run=subprocess.run):
    if not TOPIC.fullmatch(topic):
        raise SystemExit(f"{topic!r} must be words of letters and digits joined by hyphens, "
                         "such as Payments-Retry-Service")
    sources = usable_sources()
    check_gh(sources, run)
    folder, temporary = output_folder(FOLDER_NAME)
    relative = day_folder(topic, today or date.today())
    path = os.path.join(folder, relative)
    replaced = clear_folder(path)
    os.makedirs(os.path.join(folder, EXAMPLES), exist_ok=True)
    write_output_file(FOLDER_NAME, f"{relative}/{LEDGER}",
                      ledger_skeleton(topic, first_actions(topic, sources), access(sources)).encode("utf-8"))
    return {"folder": folder, "temporary": temporary, "investigation": relative,
            "investigation_dir": path, "replaced": replaced,
            "sources": {GROUPS[group]: names for group, names in sources.items()},
            "missing": [GROUPS[group] for group, names in sources.items() if not names],
            "examples": examples(folder)}


def usable_sources():
    """{group: its enabled sources this skill can use}, in GROUPS' order: an
    mcp or cli source for the documentation and the code, which the agent
    uses directly, and jira-api for the tracker, which tickets.py reads."""
    def usable(group, name):
        return name == "jira-api" if group == "workflow" else name.rpartition("-")[2] in ("mcp", "cli")
    return {group: [name for name in enabled_sources(group) if usable(group, name)] for group in GROUPS}


def check_gh(sources, run=subprocess.run):
    """Exits, saying what to do, when the code comes through gh and gh can't
    be used: not installed, or not signed in."""
    if "github-cli" not in sources["source_control"]:
        return
    try:
        done = run(["gh", "auth", "status"],
                   capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        raise SystemExit("github-cli is enabled but gh can't be run: install it, then run init_investigation.py "
                         "again")
    if done.returncode:
        raise SystemExit(
            "gh isn't signed in: run gh auth login, then run init_investigation.py again")


def first_actions(topic, sources):
    """The first research actions: a search of the topic in each group with a
    usable source, in GROUPS' order."""
    groups = [group for group, names in sources.items() if names]
    return [[f"Q{number:02d}", "Request", f"Search the {GROUPS[group]} for {topic.replace('-', ' ')}",
             ", ".join(
                 sources[group]) + (" (tickets.py search)" if group == "workflow" else ""),
             "None", "High", ""] for number, group in enumerate(groups, 1)]


def access(sources):
    """The boundary section's first lines: the sources used, by group, and the
    groups with none."""
    used = "; ".join(
        f"{GROUPS[group]}: {', '.join(names)}" for group, names in sources.items() if names)
    missing = [GROUPS[group] for group, names in sources.items() if not names]
    return f"Sources used: {used or 'none'}." + (f" No usable source for: {', '.join(missing)}." if missing else "")


def ledger_skeleton(topic, ready=(), boundary=None):
    """The ledger's fixed sections and tables, empty but for the `ready`
    actions, as rows, and the `boundary` section's text."""
    parts = [f"# {topic.replace('-', ' ')} research ledger"]
    for section in LEDGER_SECTIONS:
        parts.append(f"## {section}")
        if section == QUEUE:
            for subsection in QUEUE_SUBSECTIONS:
                rows = [[anchored(row[0]), *row[1:]]
                        for row in ready] if subsection == "Ready" else []
                parts += [f"### {subsection}",
                          table(QUEUE_HEADER, rows)] + ([] if rows else ["None."])
        elif section == BOUNDARY and boundary:
            parts.append(boundary)
        elif section == REGISTER:
            parts += [table(SOURCE_HEADER, []),
                      TABLE_HEADINGS["file-coverage"], "None yet."]
        else:
            parts.append("None yet.")
    return "\n\n".join(parts) + "\n"


def examples(folder):
    """[{folder, documents, note}] of the approved examples, newest first: by
    date, then by copy."""
    root = os.path.join(folder, EXAMPLES)
    found = []
    for name in os.listdir(root) if os.path.isdir(root) else []:
        match = EXAMPLE.fullmatch(name)
        path = os.path.join(root, name)
        if match and os.path.isdir(path):
            documents = sorted(f for f in os.listdir(path)
                               if f.endswith(".md") and f != EXAMPLE_DESCRIPTION)
            note = ""
            if os.path.isfile(os.path.join(path, EXAMPLE_DESCRIPTION)):
                with open(os.path.join(path, EXAMPLE_DESCRIPTION), encoding="utf-8") as f:
                    why = WHY_GOOD.search(f.read())
                note = why[1] if why else ""
            found.append(((match["date"], int(match["copy"] or 1)),
                          {"folder": path, "documents": documents, "note": note}))
    return [example for _, example in sorted(found, key=lambda item: item[0], reverse=True)]


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Prepare an investigation's folder.")
    parser.add_argument("--topic", required=True,
                        help="such as Payments-Retry-Service")
    args = parser.parse_args(argv)
    # The sequence diagrams are drawn and checked with Node.js: ask for it
    # now, before any research, rather than when the report is built.
    output_diagram.find_npx()
    print(json.dumps(init(args.topic)))


if __name__ == "__main__":
    main()
