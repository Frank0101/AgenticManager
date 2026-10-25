"""Keeps a report the user approved as an example, exactly as approved.

It copies the report into _examples/<investigation>/, or --2, --3... when that
folder exists, never overwriting an earlier example, with the local files it
links, such as the ledger, and what those link in turn, at the same relative
paths, so the example stays whole after the investigation changes. Beside them,
description.md holds the note on what makes it good: the example carries
everything about itself, so deleting its folder removes it whole, and no index
can go stale.
"""
import argparse
import json
import os
import shutil

from common import (EXAMPLE_DESCRIPTION, KEPT_EXAMPLES, FOLDER_NAME, REPORT_SUFFIX, WHY_GOOD, description, free_name, topic_of, investigation_dir, link_definitions, links, local_link, markdown,
                    target, write_output_file)


def save(relative, note):
    if not note.strip() or "\n" in note.strip():
        raise SystemExit("--note is one line on what makes it a good example")
    source, folder, temporary = investigation_dir(relative)
    document = topic_of(source) + REPORT_SUFFIX
    if not os.path.isfile(target(source, document)):
        raise SystemExit(
            f"{relative} has no {document}: run make_report.py first")
    name = free_name(os.path.basename(os.path.normpath(source)),
                     lambda name: os.path.exists(os.path.join(folder, KEPT_EXAMPLES, name)), "--")
    copied = []
    for path in local_links(source, document):
        destination = target(folder, f"{KEPT_EXAMPLES}/{name}/{path}")
        os.makedirs(os.path.dirname(destination), exist_ok=True)
        shutil.copyfile(os.path.join(source, path), destination)
        copied.append(path)
    text = description(name, {WHY_GOOD: note.strip()},
                       f"The approved report: [{document}]({document}).")
    write_output_file(
        FOLDER_NAME, f"{KEPT_EXAMPLES}/{name}/{EXAMPLE_DESCRIPTION}", text.encode("utf-8"))
    return {"example": os.path.join(folder, KEPT_EXAMPLES, name), "files": copied, "temporary": temporary}


def local_links(folder, relative):
    """The local files `relative` links, recursively for Markdown, as paths
    relative to `folder`, in the order found."""
    found, pending = [], [relative]
    while pending:
        current = pending.pop(0)
        if current in found:
            continue
        source = target(folder, current)
        found.append(current)
        if not current.endswith(".md"):
            continue
        with open(source, encoding="utf-8") as f:
            text = f.read()
        prose, _, _ = markdown(text)
        definitions = link_definitions(prose)
        for _, _, _, link in links(prose, definitions):
            if link is None:
                continue
            local = local_link(current, link)
            if local is None:
                continue
            path = os.path.normpath(local[0])
            if path.startswith(os.pardir) or os.path.isabs(path):
                continue
            if os.path.isfile(target(folder, path)):
                pending.append(path)
    return found


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Keep an approved report as an example.",
        epilog='Prints one line of JSON, {"example": its folder, "files": the files copied, '
        '"temporary": whether the output folder is temporary}.')
    parser.add_argument("--investigation", required=True,
                        help="<Topic>_<YY-MM-DD>")
    parser.add_argument("--note", required=True,
                        help="what makes it a good example, one line")
    args = parser.parse_args(argv)
    print(json.dumps(save(args.investigation, args.note)))


if __name__ == "__main__":
    main()
