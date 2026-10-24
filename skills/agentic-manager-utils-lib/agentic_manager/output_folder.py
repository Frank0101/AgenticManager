"""The folder a skill writes its files to: <name> in the output root the user's
config sets (output.root), or in <system temp>/agentic-manager if it sets none.
output_folder() creates it if missing, and keeps what is already in it.

As a script it prints the folder, so the agent knows it without reading the
config, of which only output.root is read. A skill keeping a folder per
subject names it with day_folder() and empties its place with clear_folder():
a rerun for the same subject and day starts from scratch, and earlier days'
folders, whose names can't clash, stay; the skill picks the day and the path.
"""
import argparse
import json
import os
import re
import shutil
import sys
import tempfile

if not __package__:
    # Run as a script: import the package from the folder that holds it.
    sys.path.insert(0, os.path.dirname(
        os.path.dirname(os.path.realpath(__file__))))
from agentic_manager.config import is_filled, load_config  # noqa: E402

# Where skills write their files when the config sets no output root.
TEMP_ROOT = os.path.join(tempfile.gettempdir(), "agentic-manager")
# The file that says what a folder of the user's own material holds, such as
# an example or an image, named here so every skill names it the same way.
EXAMPLE_DESCRIPTION = "description.md"
# The folder beside a skill's runs that holds the examples the user kept.
KEPT_EXAMPLES = "_examples"
# A description's title, and its labelled lines, such as **Shows:** text.
DESCRIPTION_TITLE = re.compile(r"# (.+)")
LABELLED_LINE = re.compile(r"^\*\*([^*\n]+):\*\* (.+)$", re.M)
# The name day_folder() gives, read back: its subject and its YY-MM-DD date.
DAY_FOLDER = re.compile(r"(?P<subject>.+)_(?P<date>\d\d-\d\d-\d\d)")


def output_folder(name):
    """(folder, temporary): the absolute folder a skill writes its files to,
    `name` in the user's output root, or in TEMP_ROOT if the config doesn't set
    one, created if missing, and whether it is that temporary one. Exits if
    `name` isn't a single folder name or the config can't be read."""
    try:
        name = folder_name(name)
    except argparse.ArgumentTypeError as error:
        raise SystemExit(str(error))
    root = output_root()
    folder, temporary = (root, False) if root else (TEMP_ROOT, True)
    folder = os.path.abspath(os.path.join(folder, name))
    os.makedirs(folder, exist_ok=True)
    return folder, temporary


def output_root():
    """The folder where skills write their files, with ~ expanded, or None if
    the config doesn't set one. Exits if the config can't be read."""
    output = load_config().get("output")
    root = output.get("root") if isinstance(output, dict) else None
    if not is_filled(root):
        return None
    return os.path.expanduser(root.strip())


def folder_name(value):
    """`value`, trimmed, if it is a single folder name, not a path; else an
    argparse error, so --name can use it as its type."""
    name = value.strip()
    if not name or name in (".", "..") or os.sep in name or (os.altsep and os.altsep in name):
        raise argparse.ArgumentTypeError(
            f"{value!r} must be a single folder name, not a path")
    return name


def day_folder(subject, day):
    """The name of a subject's folder for a day, <subject>_<YY-MM-DD>, such as
    PROJ_Sprint_3_26-03-16; `day` is a date or a datetime."""
    return f"{subject}_{day.strftime('%y-%m-%d')}"


def clear_folder(path):
    """Deletes `path`, a folder with everything in it, or only the link or file
    found there instead, and returns whether there was anything to delete."""
    if not os.path.lexists(path):
        return False
    if os.path.islink(path) or not os.path.isdir(path):
        os.unlink(path)
    else:
        shutil.rmtree(path)
    return True


def read_description(path):
    """(title, {label: text}) of the description.md at `path`, such as an
    example's or an image's: empty when there is none."""
    text = ""
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as f:
            text = f.read()
    title = DESCRIPTION_TITLE.match(text)
    return (title[1].strip() if title else "",
            {label: value.strip() for label, value in LABELLED_LINE.findall(text)})


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Print, and create, the folder a skill writes its files to.",
        epilog='Prints one line of JSON, {"folder": ..., "temporary": bool}. "temporary" is true when '
        "the config sets no output root, so the folder is in the system temp folder and may be "
        "cleared, which the skill tells the user. Fails with a message on stderr if the config "
        "can't be read or the name isn't a single folder name.")
    add_name_argument(parser)
    return parser.parse_args(argv)


def add_name_argument(parser):
    """Adds --name, the skill's output folder, to the command line `parser`."""
    parser.add_argument("--name", type=folder_name, required=True,
                        help="the name of the skill's output folder, such as tech-investigations")


def main():
    folder, temporary = output_folder(parse_args().name)
    print(json.dumps({"folder": folder, "temporary": temporary}))


if __name__ == "__main__":
    main()
