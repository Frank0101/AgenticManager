"""Writes one file in a skill's output folder (see output_folder.py), so an agent
that writes a skill's files itself does it through a command the skill
pre-approves, rather than through its own file tools. read_json() reads such a
file back for a script.

    python3 output_file.py --name <folder name> --path <relative path> [--patch] < content
    python3 output_file.py --name <folder name> --path <relative path> --set "<field>=<text>" ...

--name is the name of the skill's output folder, as for output_folder.py.
--path is where the file goes inside it, such as
"Payments-Retry_26-03-29/content.json": missing folders on the way are created,
and an existing file is replaced. The content is read from standard input as
UTF-8.

With --patch, stdin is a nonempty JSON array of {"old": "...", "new": "..."}
replacements for an existing UTF-8 file, applied in sequence, each old string
nonempty and matching exactly once. A patch whose expected text a concurrent
edit changed is rejected rather than merged.

With --set, each "field=text" sets one text field of an existing JSON file,
the field named by its path, keys and list positions joined by dots, such as
architecture.current.summary.0, with no JSON escaping to get right. The parent must exist; a key may be new, a list
position must be there.

It never writes outside the skill's output folder: an absolute path, a ".."
step or a symbolic link leading out of it is refused. Only output.root is read
from the config.

Prints one line of JSON: {"path": ..., "temporary": bool}, the file's absolute
path and whether the folder is the temporary one. Fails with a message on
stderr, writing nothing, if the path isn't inside the folder, the content isn't
UTF-8, a patch or a --set doesn't apply or the config can't be read.
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
from agentic_manager.output_folder import add_name_argument, output_folder  # noqa: E402

# Commands to copy, shown by --help and by an error for a malformed patch: the
# input goes in a quoted here-document, so nothing in it needs escaping.
_WRITE_EXAMPLE = """  python3 <lib>/output_file.py --name <folder name> --path '<subject>/content.json' <<'EOF'
  {"title": "..."}
  EOF"""
_PATCH_EXAMPLE = """  python3 <lib>/output_file.py --name <folder name> --path '<subject>/content.json' --patch <<'EOF'
  [{"old": "unique text in the file", "new": "its replacement"}]
  EOF"""
_SET_EXAMPLE = ("  python3 <lib>/output_file.py --name <folder name> --path '<subject>/content.json' \\\n"
                '    --set "architecture.current.summary.0=The new first paragraph." --set "title=Search API"')


def write_output_file(name, relative, content):
    """(path, temporary): writes `content` (bytes) to `relative` inside the
    skill's output folder `name`, and returns the file's absolute path and
    whether the folder is the temporary one."""
    try:
        content.decode("utf-8")
    except UnicodeDecodeError:
        raise SystemExit("the content is not UTF-8 text")
    folder, temporary = output_folder(name)
    path = target(folder, relative)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(content)
    return path, temporary


def patch_output_file(name, relative, content):
    """(path, temporary): applies the replacements `content` (bytes of a JSON
    array) holds to the existing file `relative` inside the skill's output
    folder `name`, as write_output_file() would write it. Every replacement is
    checked before anything is written, so a later failed one can't leave an
    earlier one applied. Error messages never include the file's content."""
    try:
        edits = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise SystemExit(
            "patch must be UTF-8 JSON, such as:\n" + _PATCH_EXAMPLE)
    if not isinstance(edits, list) or not edits:
        raise SystemExit(
            "patch must be a nonempty array of replacements, such as:\n" + _PATCH_EXAMPLE)
    folder, temporary = output_folder(name)
    path = target(folder, relative)
    try:
        with open(path, "rb") as f:
            text = f.read().decode("utf-8")
    except (OSError, UnicodeDecodeError):
        raise SystemExit(
            "patch target must be an existing readable UTF-8 file")
    for index, edit in enumerate(edits, 1):
        if (not isinstance(edit, dict) or set(edit) != {"old", "new"}
                or not isinstance(edit["old"], str) or not edit["old"]
                or not isinstance(edit["new"], str)):
            raise SystemExit(
                f"replacement {index} needs nonempty old and string new fields only, such as:\n" + _PATCH_EXAMPLE)
        start = text.find(edit["old"])
        if start < 0 or text.find(edit["old"], start + 1) >= 0:
            raise SystemExit(
                f"replacement {index} must match exactly once; reread the target")
        text = text.replace(edit["old"], edit["new"], 1)
    try:
        result = text.encode("utf-8")
    except UnicodeEncodeError:
        raise SystemExit("patch result is not UTF-8 text")
    with open(path, "wb") as f:
        f.write(result)
    return path, temporary


def set_output_fields(name, relative, sets):
    """(path, temporary): sets each "field=text" of `sets` in the existing
    JSON file `relative` inside the skill's output folder `name`, the field
    named by its dotted path, and writes it back.
    Every field is checked before anything is written."""
    folder, temporary = output_folder(name)
    path = target(folder, relative)
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, UnicodeError, ValueError):
        raise SystemExit("--set target must be an existing readable JSON file")
    for assignment in sets:
        field, equals, text = assignment.partition("=")
        steps = field.strip().split(".")
        if not equals or not all(steps):
            raise SystemExit(
                f"{assignment!r}: write --set as field=text, such as:\n" + _SET_EXAMPLE)
        parent, last = nested(data, steps[:-1]), steps[-1]
        if isinstance(parent, dict):
            parent[last] = text
        elif isinstance(parent, list) and last.isdigit() and int(last) < len(parent):
            parent[int(last)] = text
        else:
            raise SystemExit(f"{field!r}: there is no such field to set")
    with open(path, "w", encoding="utf-8") as f:
        f.write(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    return path, temporary


def read_json(path):
    """The JSON value in the file at `path`, such as one a skill's script wrote
    to its output folder. Exits naming the file if it is missing or isn't
    readable JSON, so a step run out of order says what it lacks rather than
    printing a traceback."""
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        raise SystemExit(
            f"{os.path.basename(path)} is missing in {os.path.dirname(path)}")
    except (OSError, UnicodeError, ValueError) as error:
        raise SystemExit(
            f"{os.path.basename(path)} is not readable JSON: {error}")


def target(folder, relative):
    """The absolute path of `relative` inside `folder`. Exits if it would lead
    outside the folder."""
    if not relative or os.path.isabs(relative) or os.pardir in relative.replace("\\", "/").split("/"):
        raise SystemExit(
            f"{relative!r} must be a relative path inside the output folder, without ..")
    path = os.path.join(folder, relative)
    root, resolved = os.path.realpath(folder), os.path.realpath(path)
    if resolved == root:
        raise SystemExit(
            f"{relative!r} must name a file inside the output folder")
    if os.path.commonpath([root, resolved]) != root:
        raise SystemExit(f"{relative!r} leads outside the output folder")
    return path


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Write a file in a skill's output folder, or change part of one.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="write a whole file, its content in a quoted here-document:\n" + _WRITE_EXAMPLE
        + "\n\nreplace exact text in an existing file, each old matching exactly once:\n" + _PATCH_EXAMPLE
        + "\n\nset text fields of an existing JSON file, one --set per field:\n" + _SET_EXAMPLE)
    add_name_argument(parser)
    parser.add_argument("--path", required=True,
                        help="where the file goes inside that folder")
    change = parser.add_mutually_exclusive_group()
    change.add_argument("--patch", action="store_true",
                        help="apply exact JSON replacements from standard input")
    change.add_argument("--set", action="append", default=[], metavar="FIELD=TEXT",
                        help="set one text field of an existing JSON file, named by its dotted path; repeat for more")
    return parser.parse_args(argv)


def main():
    args = parse_args()
    if args.set:
        path, temporary = set_output_fields(args.name, args.path, args.set)
    else:
        writer = patch_output_file if args.patch else write_output_file
        path, temporary = writer(args.name, args.path, sys.stdin.buffer.read())
    print(json.dumps({"path": path, "temporary": temporary}))


if __name__ == "__main__":
    main()
