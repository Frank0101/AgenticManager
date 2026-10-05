"""Writes one file in a skill's output folder (see output_folder.py), so an agent
that writes a skill's files itself does it through a command the skill
pre-approves, rather than through its own file tools.

    python3 output_file.py --name <folder name> --path <relative path> < content

--name is the skill's own folder, as for output_folder.py. --path is where the
file goes inside it, such as "2026-03-29--payments/ledgers.md": missing folders
on the way are created, and an existing file is replaced. The content is read
from standard input as UTF-8.

With --patch, stdin is a nonempty JSON array of {"old": "...", "new": "..."}
replacements for an existing UTF-8 file. Each nonempty old string must match
exactly once, in sequence. All replacements are validated before writing;
a malformed, missing or ambiguous match leaves the file unchanged.

It never writes outside the skill's folder: an absolute path, a ".." step or a
symbolic link leading out of it is refused. Only output.root is read from the
config.

Prints one line of JSON: {"path": ..., "temporary": bool}, the file's absolute
path and whether the folder is the temporary one. Fails with a message on
stderr, writing nothing, if the path isn't inside the folder, the content isn't
UTF-8 or the config can't be read.
"""
import argparse
import json
import os
import sys

if not __package__:
    # Run as a script: import the package from the folder that holds it.
    sys.path.insert(0, os.path.dirname(
        os.path.dirname(os.path.realpath(__file__))))
from agentic_manager.output_folder import folder_name, output_folder  # noqa: E402


def target(folder, relative):
    """The absolute path of `relative` inside `folder`. Exits if it would lead
    outside the folder."""
    if not relative or os.path.isabs(relative) or os.pardir in relative.replace("\\", "/").split("/"):
        raise SystemExit(
            f"{relative!r} must be a relative path inside the output folder, without ..")
    path = os.path.join(folder, relative)
    root, resolved = os.path.realpath(folder), os.path.realpath(path)
    if os.path.commonpath([root, resolved]) != root or resolved == root:
        raise SystemExit(f"{relative!r} leads outside the output folder")
    return path


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


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Write standard input to a file in a skill's output folder.")
    parser.add_argument("--name", type=folder_name, required=True,
                        help="the skill's own folder, such as tech-investigations")
    parser.add_argument("--path", required=True,
                        help="where the file goes inside that folder")
    parser.add_argument("--patch", action="store_true",
                        help="apply exact JSON replacements from standard input")
    return parser.parse_args(argv)


def patch_output_file(name, relative, content):
    """Apply exact replacements inside the same boundary as full writes.

    Read/validate every edit before writing, so a later failed edit cannot
    leave an earlier edit applied. Error messages never include file content.
    """
    try:
        edits = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise SystemExit("patch must be UTF-8 JSON")
    if not isinstance(edits, list) or not edits:
        raise SystemExit("patch must be a nonempty array of replacements")
    folder, temporary = output_folder(name)
    path = target(folder, relative)
    try:
        with open(path, "rb") as f:
            text = f.read().decode("utf-8")
    except (OSError, UnicodeDecodeError):
        raise SystemExit("patch target must be an existing readable UTF-8 file")
    for index, edit in enumerate(edits, 1):
        if (not isinstance(edit, dict) or set(edit) != {"old", "new"}
                or not isinstance(edit["old"], str) or not edit["old"]
                or not isinstance(edit["new"], str)):
            raise SystemExit(f"replacement {index} needs nonempty old and string new fields only")
        start = text.find(edit["old"])
        if start < 0 or text.find(edit["old"], start + 1) >= 0:
            raise SystemExit(f"replacement {index} must match exactly once; reread the target")
        text = text.replace(edit["old"], edit["new"], 1)
    try:
        result = text.encode("utf-8")
    except UnicodeEncodeError:
        raise SystemExit("patch result is not UTF-8 text")
    with open(path, "wb") as f:
        f.write(result)
    return path, temporary


def main():
    args = parse_args()
    writer = patch_output_file if args.patch else write_output_file
    path, temporary = writer(
        args.name, args.path, sys.stdin.buffer.read())
    print(json.dumps({"path": path, "temporary": temporary}))


if __name__ == "__main__":
    main()
