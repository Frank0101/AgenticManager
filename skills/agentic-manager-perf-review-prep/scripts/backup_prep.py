"""Keeps a copy of a finished prep as the skill first made it, and puts it back, so the manager can undo the changes made to the prep after it was done.

Only that first version is kept: a save once a copy exists does nothing, so
running it before every change keeps the original without the agent having
to know whether a change came before. The copy lives in the system's
temporary folder, beside the prep's other working files, so the prep folder
holds only its own files; it is lost if that folder is cleared, which is
enough to undo changes within a working session. Restoring puts back the
whole prep, as its files depend on one another.
"""
import argparse
import json
import os
import shutil

from common import clear_folder, original_dir, prep_dir


def save(prep):
    """Copy the prep `prep` to original_dir(), unless a copy is already
    there; returns the copy's path and whether this call made it."""
    original = original_dir(prep)
    if os.path.exists(original):
        return {"original": original, "saved": False}
    shutil.copytree(prep_dir(prep), original)
    return {"original": original, "saved": True}


def restore(prep):
    """Put the prep `prep` back as the copy in original_dir() keeps it,
    replacing what it holds now; returns its path. Exits when no copy was
    saved."""
    original, folder = original_dir(prep), prep_dir(prep)
    if not os.path.exists(original):
        raise SystemExit(f"no original of {prep} was saved, so there is nothing to go back to: run save before a "
                         "change to a finished prep")
    clear_folder(folder)
    shutil.copytree(original, folder)
    return {"prep_dir": folder}


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Keep a copy of a finished prep as the skill first made it, and put it back.")
    commands = parser.add_subparsers(dest="command", required=True)
    for name, help in (("save", "copy the prep before a change, unless its original is already kept; prints one "
                        "line of JSON: original, the copy's path, and saved, whether this call made it"),
                       ("restore", "put the prep back as it was first made; prints one line of JSON: prep_dir, "
                        "the prep's path")):
        command = commands.add_parser(name, help=help, description=help)
        command.add_argument("--prep", required=True,
                             help="the prep's folder, <Person>_<YY-MM-DD>, as init_prep.py printed it")
    args = parser.parse_args(argv)
    print(json.dumps((save if args.command == "save" else restore)
          (args.prep), ensure_ascii=False))


if __name__ == "__main__":
    main()
