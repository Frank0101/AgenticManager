"""The folder a skill writes its files to: <name> in the output root the user's
config sets (output.root), or in <system temp>/agentic-manager if it sets none.
output_folder() creates it if missing, and keeps what is already in it.

As a script, it prints the folder, so the folder can be known without reading
the config:

    python3 output_folder.py --name <folder name>

--name is the name of the skill's output folder, such as "tech-investigations":
one folder name, not a path. It prints one line of JSON, {"folder": ...,
"temporary": bool}, and fails with a message on stderr if the config can't be
read or the name isn't a single folder name.

"temporary" is true when the config sets no output root, so the folder is in the
system temp folder and may be cleared; the skill tells the user. Only
output.root is read from the config, never a source's settings.
"""
import argparse
import json
import os
import sys
import tempfile

if not __package__:
    # Run as a script: import the package from the folder that holds it.
    sys.path.insert(0, os.path.dirname(
        os.path.dirname(os.path.realpath(__file__))))
from agentic_manager.config import is_filled, load_config  # noqa: E402

# Where skills write their files when the config sets no output root.
TEMP_ROOT = os.path.join(tempfile.gettempdir(), "agentic-manager")


def output_root():
    """The folder where skills write their files, with ~ expanded, or None if
    the config doesn't set one. Exits if the config can't be read."""
    output = load_config().get("output")
    root = output.get("root") if isinstance(output, dict) else None
    if not isinstance(root, str) or not is_filled(root):
        return None
    return os.path.expanduser(root.strip())


def output_folder(name):
    """(folder, temporary): the absolute folder a skill writes its files to,
    `name` in the user's output root, or in TEMP_ROOT if the config doesn't set
    one, created if missing, and whether it is that temporary one. Exits if the
    config can't be read."""
    try:
        name = folder_name(name)
    except argparse.ArgumentTypeError as error:
        raise SystemExit(str(error))
    root = output_root()
    folder, temporary = (root, False) if root else (TEMP_ROOT, True)
    folder = os.path.abspath(os.path.join(folder, name))
    os.makedirs(folder, exist_ok=True)
    return folder, temporary


def folder_name(value):
    name = value.strip()
    if not name or name in (".", "..") or os.sep in name or (os.altsep and os.altsep in name):
        raise argparse.ArgumentTypeError(
            f"{value!r} must be a single folder name, not a path")
    return name


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Print, and create, the folder a skill writes its files to.")
    parser.add_argument("--name", type=folder_name, required=True,
                        help="the name of the skill's output folder, such as tech-investigations")
    return parser.parse_args(argv)


def main():
    folder, temporary = output_folder(parse_args().name)
    print(json.dumps({"folder": folder, "temporary": temporary}))


if __name__ == "__main__":
    main()
