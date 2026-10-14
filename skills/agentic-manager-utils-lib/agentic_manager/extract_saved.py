"""Prints chosen fields of the items in a saved tool result, one line per item.

    python3 extract_saved.py --path <saved JSON file> --fields key,fields.status.name,fields.summary
                             [--items issues.nodes]

When an MCP or CLI result is too large for the chat, the agent's harness saves
it to a file. Reading that file back whole costs the tokens the save avoided,
and writing code on the fly to pick it apart is slow and differs every time, so
this does the one job any skill needs from such a file: list its items with the
fields asked for.

A field is a dotted path inside an item, with numbers for list positions, such
as fields.fixVersions.0.name. --items is the dotted path to the list of items;
left out, it is the longest list of objects in the file, which is the result
list in the tools' usual shapes. A missing field prints as empty; a value that
isn't text prints as compact JSON. Values are joined with " | " and kept on one
line each.

Prints a first line, "<n> items at <path>", then one line per item, as plain
text, which costs fewer tokens than JSON. Exits 1 with a message if the file
can't be read as JSON or holds no such list.
"""
import argparse
import json
import os
import sys

if not __package__:
    # Run as a script: import the package from the folder that holds it.
    sys.path.insert(0, os.path.dirname(
        os.path.dirname(os.path.realpath(__file__))))
from agentic_manager.json_path import nested  # noqa: E402
from agentic_manager.output_file import read_json  # noqa: E402


def _lines(data, fields, items=None):
    """The output's lines: the count and where the items are, then one per item."""
    if items is None:
        items, found = _longest_list(data)
    else:
        found = _at(data, items)
        if not isinstance(found, list):
            raise SystemExit(f"--items {items!r} is not a list in the file")
    if found is None:
        raise SystemExit(
            "the file holds no list of objects; name one with --items")
    return [f"{len(found)} items at {items or '(top level)'}"] + [
        " | ".join(_text_of(_at(item, field)) for field in fields) for item in found]


def _longest_list(node, path=""):
    """(path, list) of the longest list of objects in `node`, or (None, None)."""
    best = (None, None)
    if isinstance(node, list):
        if node and all(isinstance(item, dict) for item in node):
            best = (path, node)
        children = enumerate(node)
    elif isinstance(node, dict):
        children = node.items()
    else:
        return best
    for key, child in children:
        found = _longest_list(child, f"{path}.{key}" if path else str(key))
        if found[1] is not None and (best[1] is None or len(found[1]) > len(best[1])):
            best = found
    return best


def _at(node, path):
    """The value at the dotted `path` in `node`, or None if a step is missing."""
    return nested(node, path.split(".") if path else [])


def _text_of(value):
    if value is None:
        return ""
    if isinstance(value, str):
        return " ".join(value.split())
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=(__doc__ or "").split("\n")[0])
    parser.add_argument("--path", required=True, help="the saved JSON file")
    parser.add_argument("--fields", required=True,
                        help="dotted paths inside an item, comma separated, such as key,fields.status.name")
    parser.add_argument(
        "--items", help="dotted path to the list of items; leave out for the longest list")
    args = parser.parse_args(argv)
    data = read_json(args.path)
    fields = [f.strip() for f in args.fields.split(",") if f.strip()]
    sys.stdout.write("\n".join(_lines(data, fields, args.items)) + "\n")


if __name__ == "__main__":
    main()
