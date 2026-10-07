"""Keeps a document the user approved as an example, exactly as approved.

    python3 save_example.py --investigation <Topic>_<YY-MM-DD> --file <document> --format <format> --note "<why it's good>"

Copies <investigation>/<document> into _examples/<Topic>_<YY-MM-DD>--<format>/,
or --2, --3... when that folder exists, never overwriting an earlier example,
with the local files it links (images, the ledger, and what those link in
turn), at the same relative paths, so the example stays whole after the
investigation changes. Then adds a line for it at the top of the index in
_examples/README.md: its link and the note, which the agent writes.

Prints one line of JSON: the example's folder, the files copied, and whether
the output folder is temporary.
"""
import argparse
import json
import os
import re
import shutil
from urllib.parse import unquote, urlsplit

from common import EXAMPLES, FOLDER_NAME, investigation_dir, target, write_output_file

LINK = re.compile(r"!?\[[^\]\n]*\]\(\s*<?([^\s)>]+)>?(?:\s+\"[^\"\n]*\")?\s*\)")
FORMAT = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")


def local_links(folder, relative):
    """The local files `relative` links, recursively for Markdown, as paths
    relative to `folder`, in the order found."""
    found, pending = [], [relative]
    while pending:
        current = pending.pop(0)
        if current in found:
            continue
        found.append(current)
        if not current.endswith(".md"):
            continue
        with open(os.path.join(folder, current), encoding="utf-8") as f:
            text = f.read()
        for link in LINK.findall(text):
            parts = urlsplit(link)
            if parts.scheme or parts.netloc or not parts.path:
                continue
            path = os.path.normpath(os.path.join(os.path.dirname(current), unquote(parts.path)))
            if path.startswith(os.pardir) or os.path.isabs(path):
                continue
            if os.path.isfile(os.path.join(folder, path)):
                pending.append(path)
    return found


def save(relative, document, wanted, note):
    if not FORMAT.fullmatch(wanted):
        raise SystemExit(f"{wanted!r}: the format is a short lower-case label, such as exec-summary")
    if not note.strip() or "\n" in note.strip():
        raise SystemExit("--note is one line on what makes it a good example")
    source, folder, temporary = investigation_dir(relative)
    if not os.path.isfile(os.path.join(source, document)):
        raise SystemExit(f"{document!r} isn't in {relative}")
    base = f"{os.path.basename(os.path.normpath(source))}--{wanted}"
    name, number = base, 1
    while os.path.exists(os.path.join(folder, EXAMPLES, name)):
        number += 1
        name = f"{base}--{number}"
    copied = []
    for path in local_links(source, document):
        destination = target(folder, f"{EXAMPLES}/{name}/{path}")
        os.makedirs(os.path.dirname(destination), exist_ok=True)
        shutil.copyfile(os.path.join(source, path), destination)
        copied.append(path)
    index_path = os.path.join(folder, EXAMPLES, "README.md")
    with open(index_path, encoding="utf-8") as f:
        index = f.read()
    line = f"- [{name}/{document}]({name}/{document}) — {note.strip()}"
    if not re.search(r"^## Index\s*$", index, re.M):
        raise SystemExit("_examples/README.md has no ## Index heading")
    index = re.sub(r"^(## Index\s*?\n)\n?", lambda m: m[1] + "\n" + line + "\n", index, count=1, flags=re.M)
    write_output_file(FOLDER_NAME, f"{EXAMPLES}/README.md", index.encode("utf-8"))
    return {"example": os.path.join(folder, EXAMPLES, name), "files": copied, "temporary": temporary}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Keep an approved document as an example.")
    parser.add_argument("--investigation", required=True, help="<Topic>_<YY-MM-DD>")
    parser.add_argument("--file", required=True, help="the approved document, inside the investigation")
    parser.add_argument("--format", required=True, help="long-analysis, exec-summary or another short label")
    parser.add_argument("--note", required=True, help="what makes it a good example, one line")
    args = parser.parse_args(argv)
    print(json.dumps(save(args.investigation, args.file, args.format, args.note)))


if __name__ == "__main__":
    main()
