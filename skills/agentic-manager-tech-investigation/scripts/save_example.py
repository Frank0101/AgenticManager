"""Keeps a document the user approved as an example, exactly as approved.

    python3 save_example.py --investigation <Topic>_<YY-MM-DD> --file <document> --format <format> --note "<why it's good>"

Copies <investigation>/<document> into _examples/<Topic>_<YY-MM-DD>--<format>/,
or --2, --3... when that folder exists, never overwriting an earlier example,
with the local files it links (images, the ledger, and what those link in
turn), at the same relative paths, so the example stays whole after the
investigation changes. Beside them, description.md holds the note on what
makes it good, which the agent writes, and a link to the approved document:
the example carries everything about itself, so deleting its folder removes
it whole, and no index can go stale.

Prints one line of JSON: the example's folder, the files copied, and whether
the output folder is temporary.
"""
import argparse
import json
import os
import shutil

from common import (EXAMPLE_DESCRIPTION, EXAMPLES, FOLDER_NAME, WHY_GOOD_LABEL, check_format, free_name, investigation_dir, link_definitions, links, local_link, markdown,
                    target, write_output_file)


def save(relative, document, wanted, note):
    check_format(wanted)
    if not note.strip() or "\n" in note.strip():
        raise SystemExit("--note is one line on what makes it a good example")
    source, folder, temporary = investigation_dir(relative)
    document_path = target(source, document)
    if not os.path.isfile(document_path):
        raise SystemExit(f"{document!r} isn't in {relative}")
    name = free_name(f"{os.path.basename(os.path.normpath(source))}--{wanted}",
                     lambda name: os.path.exists(os.path.join(folder, EXAMPLES, name)), "--")
    copied = []
    for path in local_links(source, document):
        destination = target(folder, f"{EXAMPLES}/{name}/{path}")
        os.makedirs(os.path.dirname(destination), exist_ok=True)
        shutil.copyfile(os.path.join(source, path), destination)
        copied.append(path)
    description = (f"# {name}\n\n{WHY_GOOD_LABEL} {note.strip()}\n\n"
                   f"The approved document: [{document}]({document}).\n")
    write_output_file(
        FOLDER_NAME, f"{EXAMPLES}/{name}/{EXAMPLE_DESCRIPTION}", description.encode("utf-8"))
    return {"example": os.path.join(folder, EXAMPLES, name), "files": copied, "temporary": temporary}


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
        description="Keep an approved document as an example.")
    parser.add_argument("--investigation", required=True,
                        help="<Topic>_<YY-MM-DD>")
    parser.add_argument("--file", required=True,
                        help="the approved document, inside the investigation")
    parser.add_argument("--format", required=True,
                        help="long-analysis, exec-summary or another short label")
    parser.add_argument("--note", required=True,
                        help="what makes it a good example, one line")
    args = parser.parse_args(argv)
    print(json.dumps(save(args.investigation, args.file, args.format, args.note)))


if __name__ == "__main__":
    main()
