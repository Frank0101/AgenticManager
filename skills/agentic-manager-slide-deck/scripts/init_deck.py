"""Prepares a deck's new folder, replacing one of the same name and day.

    python3 init_deck.py --name <Name>

<Name> is short and filename-safe: capitalised words or acronyms joined by
hyphens, such as Acme-Q3-Review. The deck's folder is <Name>_<YY-MM-DD>,
today's date, in the skill's output folder. Every run starts from scratch: a
folder of the same name and day is deleted first, so a deck is always built
from this conversation, never from the leftovers of an earlier one, and
nothing an earlier run left, on this or another day, is read or reused. The
_examples and _assets folders beside it are created if missing, so the user
sees where kept slides and their images go before using either.

Prints one line of JSON:
  folder, temporary   the skill's output folder, and whether it is temporary
  deck                the folder's name, for --deck and the slides' path
  deck_dir            its absolute path
  slides_path         where slides.json goes, relative to `folder`
  replaced            whether a folder of the same name and day was deleted
  examples            every example, the skill's and the user's: its folder,
                      source, title and what it is good for, so the agent
                      picks which to read
  assets              every image in _assets: its name, title, what it shows
                      and, if downloaded, its license, so the agent reuses one
                      before drawing or searching for another
"""
import argparse
from datetime import date
import json
import os

from common import ASSETS, FOLDER_NAME, NAME, SLIDES, USER_EXAMPLES, assets, clear_folder, day_folder, examples, output_folder


def init(name, today=None):
    if not NAME.fullmatch(name):
        raise SystemExit(f"{name!r} must be words of letters and digits joined by hyphens, "
                         "such as Acme-Q3-Review")
    folder, temporary = output_folder(FOLDER_NAME)
    deck = day_folder(name, today or date.today())
    path = os.path.join(folder, deck)
    replaced = clear_folder(path)
    os.makedirs(path)
    for shared in (USER_EXAMPLES, ASSETS):
        os.makedirs(os.path.join(folder, shared), exist_ok=True)
    return {"folder": folder, "temporary": temporary, "deck": deck, "deck_dir": path,
            "slides_path": f"{deck}/{SLIDES}", "replaced": replaced, "examples": examples(),
            "assets": [{"name": asset["name"], "title": asset["title"], "shows": asset["shows"],
                        "license": asset["credit"]["license"] if asset["credit"] else None}
                       for asset in assets()]}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Prepare a deck's folder.")
    parser.add_argument("--name", required=True, help="such as Acme-Q3-Review")
    print(json.dumps(init(parser.parse_args(argv).name)))


if __name__ == "__main__":
    main()
