"""Keeps a copy of a finished prep before a change the manager asks for, and puts it back, so the manager can undo the last change.

Each save replaces the copy, so it is always the prep before the last change:
one step back, which is what undoing a change needs, with nothing to choose
between. The copy lives in the system's temporary folder, beside the prep's
other working files, so the prep folder holds only its own files; it is lost
if that folder is cleared, which is enough to undo a change within a working
session. Restoring puts back the whole prep, as its files depend on one
another.
"""
import argparse
import json
import os
import shutil

from common import clear_folder, previous_dir, prep_dir


def save(prep):
    """Copy the prep `prep` to previous_dir(), replacing the copy there;
    returns {previous}, the copy's path."""
    previous = previous_dir(prep)
    clear_folder(previous)
    shutil.copytree(prep_dir(prep), previous)
    return {"previous": previous}


def restore(prep):
    """Put the prep `prep` back as the copy in previous_dir() keeps it,
    replacing what it holds now; returns {prep_dir}, the prep's path. Exits when no copy was
    saved."""
    previous, folder = previous_dir(prep), prep_dir(prep)
    if not os.path.exists(previous):
        raise SystemExit(f"no copy of {prep} was saved, so there is nothing to go back to: run save before a "
                         "change to a finished prep")
    clear_folder(folder)
    shutil.copytree(previous, folder)
    return {"prep_dir": folder}


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Keep a copy of a finished prep before a change, and put it back.")
    commands = parser.add_subparsers(dest="command", required=True)
    for name, help in (("save", "copy the prep before a change, replacing the last copy; prints one line of JSON: "
                        "previous, the copy's path"),
                       ("restore", "put the prep back as it was before the last change; prints one line of JSON: "
                        "prep_dir, the prep's path")):
        command = commands.add_parser(name, help=help, description=help)
        command.add_argument("--prep", required=True,
                             help="the prep's folder, <Person>_<YY-MM-DD>, as init_prep.py printed it")
    args = parser.parse_args(argv)
    print(json.dumps((save if args.command == "save" else restore)
          (args.prep), ensure_ascii=False))


if __name__ == "__main__":
    main()
