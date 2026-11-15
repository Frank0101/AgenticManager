"""Finishes the deck: checks slides.json field by field, writes the deck from it
with make_deck.py, then checks the deck with check_deck.py.

The one command of the step, so the agent fixes slides.json and runs it again
until the deck passes; nothing is written while slides.json has a problem.
"""
import argparse
import json
import os
import webbrowser
from pathlib import Path

from common import SLIDES, asset_names, credits, deck_dir, placed_images, read_json
import check_deck
from make_deck import problems, write_deck


def finish(deck, open_page=False):
    """Writes the deck and checks it, opening it in the default browser when
    `open_page` and it passes; returns the JSON result, or exits with the
    problems if slides.json is invalid."""
    content = read_json(os.path.join(deck_dir(deck), SLIDES))
    errors, texts = problems(content, asset_names())
    if errors:
        raise SystemExit("slides.json has problems, so nothing was written:\n  - "
                         + "\n  - ".join(errors))
    known = credits()
    path, temporary = write_deck(deck, content, texts, known)
    result = {"path": path, "temporary": temporary,
              **check_deck.check_deck(deck)}
    result["credits"] = [{"asset": name, "license": known[name]["license"], "source": known[name]["source"]}
                         for name in sorted({name for text in texts for name in placed_images(text)})
                         if name in known]
    # The user's own browser, not one a tool drives, so they review the deck
    # where they will present it; only on request, since every revision after
    # the first is a refresh of the page already open.
    result["opened"] = bool(open_page and result["ok"]
                            and webbrowser.open(Path(path).as_uri()))
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Write the deck from slides.json, then check it. Prints one line of JSON: the deck's "
        "path, whether the folder is temporary, what check_deck.py reports (ok, errors, placeholders, "
        "stand_ins), the credits of the downloaded images it shows and whether it was opened. Exits 1 "
        "if slides.json is invalid, writing nothing, or the deck fails the check.")
    parser.add_argument("--deck", required=True,
                        help="the deck's folder, <Name>_<YY-MM-DD>, inside slides-decks")
    parser.add_argument("--open", action="store_true",
                        help="open the deck in the default browser if it passes the check")
    args = parser.parse_args(argv)
    result = finish(args.deck, args.open)
    print(json.dumps(result))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
