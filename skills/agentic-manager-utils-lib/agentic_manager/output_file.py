"""Writes one file in a skill's output folder (see output_folder.py), so an agent
that writes a skill's files itself does it through a command the skill
pre-approves, rather than through its own file tools.

    python3 output_file.py --name <folder name> --path <relative path> < content

--name is the skill's own folder, as for output_folder.py. --path is where the
file goes inside it, such as "2026-03-29--payments/ledgers.md": missing folders
on the way are created, and an existing file is replaced. The content is read
from standard input as UTF-8.

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
    return parser.parse_args(argv)


def main():
    args = parse_args()
    path, temporary = write_output_file(
        args.name, args.path, sys.stdin.buffer.read())
    print(json.dumps({"path": path, "temporary": temporary}))


if __name__ == "__main__":
    main()
