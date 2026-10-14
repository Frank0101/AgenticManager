"""Prepares an investigation's new folder, replacing any earlier one of the same day.

    python3 init_investigation.py --topic <Topic> [--format <format>]

<Topic> is short and filename-safe: capitalised words or acronyms joined by
hyphens, such as Payments-Retry-Service. The investigation's folder is
<Topic>_<YY-MM-DD>, today's date, in the skill's output folder. Every run starts
from scratch: a folder of the same topic and day is deleted first, so a report
is always built from fresh research, never from the leftovers of an earlier one,
and nothing an earlier run left, on this or another day, is read or reused. The
new folder gets the ledger's skeleton, with its fixed sections and tables, so
the agent starts by filling it in. The _examples folder beside it is created
if missing, so the user sees where approved documents go before saving one.

Prints one line of JSON:
  folder, temporary   the skill's output folder, and whether it is temporary
  investigation       the folder's path relative to `folder`, for --path
  investigation_dir   its absolute path
  replaced            whether a folder of the same topic and day was deleted
  examples            with --format, the approved examples of that format,
                      newest first: their folder, documents and the note on
                      what makes each good, read from its description.md
"""
import argparse
from datetime import date
import json
import os
import re

from common import (EXAMPLE_DESCRIPTION, EXAMPLES, WHY_GOOD, TABLE_HEADINGS, FOLDER_NAME, INVESTIGATION, LEDGER, LEDGER_SECTIONS,
                    QUEUE_HEADER, QUEUE_SUBSECTIONS, SOURCE_HEADER, TOPIC, clear_folder, day_folder,
                    output_folder, table, write_output_file)
import output_diagram


def init(topic, wanted=None, today=None):
    if not TOPIC.fullmatch(topic):
        raise SystemExit(f"{topic!r} must be words of letters and digits joined by hyphens, "
                         "such as Payments-Retry-Service")
    folder, temporary = output_folder(FOLDER_NAME)
    relative = day_folder(topic, today or date.today())
    path = os.path.join(folder, relative)
    replaced = clear_folder(path)
    os.makedirs(os.path.join(folder, EXAMPLES), exist_ok=True)
    write_output_file(
        FOLDER_NAME, f"{relative}/{LEDGER}", ledger_skeleton(topic).encode("utf-8"))
    result = {"folder": folder, "temporary": temporary, "investigation": relative,
              "investigation_dir": path, "replaced": replaced}
    if wanted:
        result["examples"] = examples(folder, wanted)
    return result


def ledger_skeleton(topic):
    """The ledger's fixed sections and tables, empty."""
    parts = [f"# {topic.replace('-', ' ')} research ledger"]
    for section in LEDGER_SECTIONS:
        parts.append(f"## {section}")
        if section == "Research action queue":
            for subsection in QUEUE_SUBSECTIONS:
                parts += [f"### {subsection}",
                          table(QUEUE_HEADER, []), "None."]
        elif section == "Revisions and source register":
            parts += [table(SOURCE_HEADER, []),
                      TABLE_HEADINGS["file-coverage"], "None yet."]
        else:
            parts.append("None yet.")
    return "\n\n".join(parts) + "\n"


# An example's folder: its investigation's, then --<format>, and --<n> for a
# later copy of the same day's example, as save_example.py names it.
EXAMPLE = re.compile(
    rf"{INVESTIGATION.pattern}--(?P<format>.+?)(?:--(?P<copy>\d+))?")


def examples(folder, wanted):
    """[{folder, documents, note}] of the approved examples of format
    `wanted`, newest first: by date, then by copy."""
    root = os.path.join(folder, EXAMPLES)
    found = []
    for name in os.listdir(root) if os.path.isdir(root) else []:
        match = EXAMPLE.fullmatch(name)
        path = os.path.join(root, name)
        if match and match["format"] == wanted and os.path.isdir(path):
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
    parser.add_argument("--format", help="the output asked for, such as long-analysis or exec-summary, "
                                         "to list its approved examples")
    args = parser.parse_args(argv)
    # The sequence diagrams are drawn and checked with Node.js: ask for it
    # now, before any research, rather than when the report is built.
    output_diagram.find_npx()
    print(json.dumps(init(args.topic, args.format)))


if __name__ == "__main__":
    main()
