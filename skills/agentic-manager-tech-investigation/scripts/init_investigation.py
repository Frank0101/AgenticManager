"""Prepares an investigation's new folder, replacing any earlier one of the same day.

    python3 init_investigation.py --topic <Topic> [--format <format>]

<Topic> is short and filename-safe: capitalised words or acronyms joined by
hyphens, such as Payments-Retry-Service. The investigation's folder is
<Topic>_<YY-MM-DD>, today's date, in the skill's output folder. Every run starts
from scratch: a folder of the same topic and day is deleted first, so a report
is always built from fresh research, never from the leftovers of an earlier one,
and nothing an earlier run left, on this or another day, is read or reused. The
new folder gets the ledger's skeleton, with its fixed sections and tables, so
the agent starts by filling it in. The examples' index,
_examples/README.md, is written if missing.

Prints one line of JSON:
  folder, temporary   the skill's output folder, and whether it is temporary
  investigation       the folder's path relative to `folder`, for --path
  investigation_dir   its absolute path
  replaced            whether a folder of the same topic and day was deleted
  examples            with --format, the approved examples of that format,
                      newest first: their folder and documents
"""
import argparse
from datetime import date
import json
import os
import re
import shutil

from common import (EXAMPLES, FOLDER_NAME, INVESTIGATION, LEDGER, LEDGER_SECTIONS,
                    QUEUE_HEADER, QUEUE_SUBSECTIONS, SOURCE_HEADER, TOPIC, output_folder,
                    table, write_output_file)
import output_diagram

EXAMPLES_INDEX = """# Examples

Tech investigations the user approved, kept for their tone, structure and style only. They are never evidence: the topics they describe may have changed since.

Each example has its own `<Topic>_<YY-MM-DD>--<format>` folder, with a numeric suffix when needed. One line per example, newest first: a link to its document and what makes it a good example.

## Index
"""


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
                      "### File reading coverage", "None yet."]
        else:
            parts.append("None yet.")
    return "\n\n".join(parts) + "\n"


def sort_key(name):
    """Newest first: a folder's date as YYYY-MM-DD."""
    match = INVESTIGATION.fullmatch(name.split("--")[0])
    return "20" + match["date"] if match else ""


def examples(folder, wanted):
    """[{folder, documents}] of the approved examples of format `wanted`,
    newest first."""
    root = os.path.join(folder, EXAMPLES)
    found = []
    for name in os.listdir(root) if os.path.isdir(root) else []:
        match = re.fullmatch(
            r".+_\d\d-\d\d-\d\d--(?P<format>.+?)(?:--\d+)?", name)
        path = os.path.join(root, name)
        if match and match["format"] == wanted and os.path.isdir(path):
            documents = sorted(f for f in os.listdir(path)
                               if f.endswith(".md"))
            found.append({"folder": path, "documents": documents})

    def newest(example):
        # A later copy of the same day's example has a higher --<n>.
        name = os.path.basename(example["folder"])
        suffix = re.search(r"--(\d+)$", name)
        return sort_key(name), int(suffix[1]) if suffix else 1
    return sorted(found, key=newest, reverse=True)


def init(topic, wanted=None, today=None):
    if not TOPIC.fullmatch(topic):
        raise SystemExit(f"{topic!r} must be words of letters and digits joined by hyphens, "
                         "such as Payments-Retry-Service")
    folder, temporary = output_folder(FOLDER_NAME)
    relative = f"{topic}_{(today or date.today()).strftime('%y-%m-%d')}"
    path = os.path.join(folder, relative)
    replaced = os.path.lexists(path)
    if replaced:
        if os.path.islink(path) or not os.path.isdir(path):
            os.unlink(path)
        else:
            shutil.rmtree(path)
    write_output_file(
        FOLDER_NAME, f"{relative}/{LEDGER}", ledger_skeleton(topic).encode("utf-8"))
    if not os.path.isfile(os.path.join(folder, EXAMPLES, "README.md")):
        write_output_file(
            FOLDER_NAME, f"{EXAMPLES}/README.md", EXAMPLES_INDEX.encode("utf-8"))
    result = {"folder": folder, "temporary": temporary, "investigation": relative,
              "investigation_dir": path, "replaced": replaced}
    if wanted:
        result["examples"] = examples(folder, wanted)
    return result


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
