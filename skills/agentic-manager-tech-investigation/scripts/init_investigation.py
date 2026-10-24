"""Prepares an investigation's new folder, replacing any earlier one of the same day.

Every run starts from scratch, so a report is always built from fresh research:
a folder of the same topic and day is deleted first, and nothing an earlier run
left is read. The script stops before creating anything when a source group has
no usable source, or when the code comes through gh and gh can't be used. Every
investigation starts the same way, so the script writes the ledger's skeleton
with its first questions, and creates _examples, so the user sees where
approved reports go before saving one.
"""
import argparse
from datetime import date
import json
import os
import re
import subprocess

from common import (DESIGN, DESIGN_SUBSECTIONS, EXAMPLE_DESCRIPTION, EXAMPLES, GITHUB_CLI, GROUPS, JIRA_API, JIRA_GROUP, QUEUE, REGISTER,
                    WHY_GOOD, TABLE_HEADINGS, FOLDER_NAME, INVESTIGATION, LEDGER, LEDGER_SECTIONS, QUEUE_HEADER,
                    QUEUE_SUBSECTIONS, SOURCE_HEADER, TOPIC, GhError, anchored, clear_folder, day_folder,
                    enabled_sources, gh_signed_in, output_folder, table, tool_channel, write_output_file)

# An example's folder: its investigation's, and --<n> for a later copy of the
# same day's example, as save_example.py names it.
EXAMPLE = re.compile(rf"{INVESTIGATION.pattern}(?:--(?P<copy>\d+))?")


def init(topic, today=None, run=subprocess.run):
    if not TOPIC.fullmatch(topic):
        raise SystemExit(f"{topic!r} must be words of letters and digits joined by hyphens, "
                         "such as Payments-Retry-Service")
    sources = usable_sources()
    missing = [GROUPS[group] for group, names in sources.items() if not names]
    if missing:
        raise SystemExit(f"No usable source for: {', '.join(missing)}. The investigation needs the code, the "
                         "tracker and the documentation: enable a source for each in the config, as "
                         "check_config.py shows, then run init_investigation.py again")
    check_gh(sources, run)
    folder, temporary = output_folder(FOLDER_NAME)
    relative = day_folder(topic, today or date.today())
    path = os.path.join(folder, relative)
    replaced = clear_folder(path)
    os.makedirs(os.path.join(folder, EXAMPLES), exist_ok=True)
    write_output_file(FOLDER_NAME, f"{relative}/{LEDGER}",
                      ledger_skeleton(topic, first_actions(topic, sources)).encode("utf-8"))
    return {"folder": folder, "temporary": temporary, "investigation": relative,
            "investigation_dir": path, "replaced": replaced,
            "sources": {GROUPS[group]: names for group, names in sources.items()},
            "examples": examples(folder)}


def usable_sources():
    """{group: its enabled sources this skill can use}, in GROUPS' order: an
    mcp or cli source for the documentation and the code, which the agent
    uses directly, and jira-api for the tracker, which tickets.py reads."""
    def usable(group, name):
        return name == JIRA_API if group == JIRA_GROUP else tool_channel(name)[1] in ("mcp", "cli")
    return {group: [name for name in enabled_sources(group) if usable(group, name)] for group in GROUPS}


def check_gh(sources, run=subprocess.run):
    """Exits, saying what to do, when the code comes through gh and gh can't
    be used: not installed, or not signed in."""
    if GITHUB_CLI not in sources["source_control"]:
        return
    try:
        signed_in = gh_signed_in(run)
    except GhError:
        raise SystemExit("github-cli is enabled but gh can't be run: install it, then run init_investigation.py "
                         "again")
    if not signed_in:
        raise SystemExit(
            "gh isn't signed in: run gh auth login, then run init_investigation.py again")


def first_actions(topic, sources):
    """The first research actions: a question about the topic for each group,
    the documentation first, which Define has skimmed, then the tracker, then
    the code."""
    order = ["documentation", JIRA_GROUP, "source_control"]
    return [[f"Q{number:02d}", "Request", f"What does the {GROUPS[group]} say about {topic.replace('-', ' ')}?",
             ", ".join(
                 sources[group]) + (" (tickets.py search)" if group == JIRA_GROUP else ""),
             "None", ""] for number, group in enumerate(order, 1)]


def ledger_skeleton(topic, ready=()):
    """The ledger's fixed sections and tables, empty but for the `ready`
    actions, as rows."""
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
        description="Prepare an investigation's folder, <Topic>_<YY-MM-DD> with today's date, in the skill's "
        "output folder.",
        epilog="Prints one line of JSON: folder and temporary, the skill's output folder and whether it is "
        "temporary; investigation, the folder's name, which the other scripts take as --investigation; "
        "investigation_dir, its absolute path; replaced, whether a folder of the same topic and day was "
        "deleted; sources, {group: the enabled sources the skill uses for it}; and examples, the approved "
        "examples, newest first, each with its folder, documents and the note on what makes it good.")
    parser.add_argument("--topic", required=True,
                        help="short and filename-safe: capitalised words or acronyms joined by hyphens, such as "
                        "Payments-Retry-Service")
    args = parser.parse_args(argv)
    print(json.dumps(init(args.topic)))


if __name__ == "__main__":
    main()
