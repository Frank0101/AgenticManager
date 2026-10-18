"""Takes a picture of each slide of a deck with headless Chrome, so the agent
can see what the user will see before handing it over.

    python3 snap_deck.py --deck <Name>_<YY-MM-DD>

Only a browser can lay out a page, so overflowing text, overlaps and a font
that renders other than intended are invisible to check_deck.py; Chrome is the
one browser the skill relies on, run headless so no window opens. The deck
itself is never changed: for each slide a copy of its page goes to a
temporary folder, showing that slide alone at its real size, with a <base>
pointing at the deck's folder so its images in _assets still load. Each copy
is shot in its own Chrome with its own throwaway profile, in parallel, and
given a few seconds of page time so charts, drawn by Chart.js loaded from
the internet, are there when it is shot.

The pictures are then laid out, numbered, at a third of their size, in one
sheet, so the whole deck is looked at in a single image and a slide's own
picture is opened only where something looks wrong.

Prints one line of JSON: the `sheet`, then `slides`, the picture of each slide
in order, all in a new temporary folder. Exits 1, saying to skip the check, if
Chrome isn't installed or takes over 60 seconds on a picture; exits too if
Chrome makes no picture.
"""
import argparse
import html
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from common import SLIDE_HEIGHT, SLIDE_WIDTH, deck_dir, deck_file

# Where Chrome is installed by default on macOS and Windows; on Linux, and
# anywhere it is on the PATH, it is found by name.
CHROME_PATHS = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
]
CHROME_NAMES = ["google-chrome", "google-chrome-stable", "chrome"]
# A slide's frame on the deck's page, which the slides wrapper isn't.
SLIDE = re.compile(r'<div class="slide[ "]')
# The sheet: slides in columns, each a third of its size, numbered above it.
SHEET_COLUMNS = 3
THUMB_WIDTH = 360
THUMB_HEIGHT = round(THUMB_WIDTH * SLIDE_HEIGHT / SLIDE_WIDTH)
GAP, LABEL = 16, 22
# How long, in page time, scripts get to draw before the picture is taken.
PAGE_TIME_MS = 5000


def snap(deck):
    """(sheet, pictures): the sheet of the deck `deck` and the picture of every
    slide, in order, in a new temporary folder; exits if Chrome isn't
    installed or a picture fails."""
    chrome = find_chrome()
    if not chrome:
        raise SystemExit(
            "Chrome isn't installed, so the slides can't be pictured: skip the slide check")
    folder = deck_dir(deck)
    with open(os.path.join(folder, deck_file(deck)), encoding="utf-8") as f:
        page = f.read()
    count = len(SLIDE.findall(page))
    out = tempfile.mkdtemp(prefix="slide-pictures-")

    def shoot(name, text, size=(SLIDE_WIDTH, SLIDE_HEIGHT)):
        source, picture = os.path.join(
            out, f"{name}.html"), os.path.join(out, f"{name}.png")
        with open(source, "w", encoding="utf-8") as f:
            f.write(text)
        with tempfile.TemporaryDirectory(prefix="chrome-profile-") as profile:
            try:
                run = subprocess.run(chrome_command(chrome, profile, picture, source, size),
                                     capture_output=True, text=True, timeout=60)
            except subprocess.TimeoutExpired:
                raise SystemExit(
                    f"Chrome took over 60 seconds to picture {name}: skip the slide check")
        os.remove(source)
        if not os.path.isfile(picture):
            raise SystemExit(
                f"Chrome made no picture of {name}: {run.stderr.strip()[-300:]}")
        return picture

    with ThreadPoolExecutor(max_workers=4) as pool:
        pictures = list(pool.map(lambda number: shoot(f"slide-{number}", one_slide_page(page, folder, number)),
                                 range(1, count + 1)))
    text, size = sheet_page([os.path.basename(picture)
                            for picture in pictures])
    return shoot("sheet", text, size), pictures


def find_chrome():
    """The path of Chrome's executable, or None if it isn't installed."""
    for path in CHROME_PATHS:
        if os.path.isfile(path):
            return path
    for name in CHROME_NAMES:
        found = shutil.which(name)
        if found:
            return found
    return None


def sheet_page(pictures):
    """A page laying out the slide pictures `pictures` (file names beside it),
    numbered, at a third of their size, and its (width, height)."""
    rows = math.ceil(len(pictures) / SHEET_COLUMNS)
    width = SHEET_COLUMNS * THUMB_WIDTH + (SHEET_COLUMNS + 1) * GAP
    height = rows * (LABEL + THUMB_HEIGHT + GAP) + GAP
    cells = "".join(f'<figure><figcaption>{number}</figcaption><img src="{html.escape(name)}"></figure>'
                    for number, name in enumerate(pictures, 1))
    page = ("<!doctype html><html><head><meta charset='utf-8'><style>"
            f"body {{ margin: 0; padding: {GAP}px; background: #8b929c; font: 700 15px sans-serif; color: #fff; }}"
            f" main {{ display: grid; grid-template-columns: repeat({SHEET_COLUMNS}, {THUMB_WIDTH}px); gap: {GAP}px; }}"
            f" figure {{ margin: 0; }} figcaption {{ height: {LABEL}px; }}"
            f" img {{ display: block; width: {THUMB_WIDTH}px; height: {THUMB_HEIGHT}px; }}"
            f"</style></head><body><main>{cells}</main></body></html>")
    return page, (width, height)


def chrome_command(chrome, profile, picture, page, size=(SLIDE_WIDTH, SLIDE_HEIGHT)):
    """The command that shoots the page file `page` into the PNG `picture`, at
    the window size `size`, with the throwaway profile folder `profile`."""
    return [chrome, "--headless", f"--user-data-dir={profile}", "--no-first-run", "--hide-scrollbars",
            "--force-device-scale-factor=1", f"--window-size={size[0]},{size[1]}",
            f"--virtual-time-budget={PAGE_TIME_MS}", f"--screenshot={picture}", Path(page).as_uri()]


def one_slide_page(page, folder, number):
    """The deck's page `page` showing only slide `number` (1 for the first),
    at its real size from the window's corner, its links resolved from the
    deck's folder `folder`."""
    base = Path(folder).as_uri() + "/"
    style = ("<style>body { padding: 0 !important; background: none !important; }"
             " .toolbar { display: none !important; }"
             " .slides-wrapper { transform: none !important; }"
             " .slide { margin: 0 !important; box-shadow: none !important; }"
             f" .slides-wrapper > .slide:not(:nth-child({number})) {{ display: none !important; }}</style>")
    return page.replace("<head>", f'<head>\n    <base href="{base}">\n    {style}', 1)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Picture each slide of the deck with headless Chrome.")
    parser.add_argument("--deck", required=True,
                        help="the deck's folder, <Name>_<YY-MM-DD>, inside slides-decks")
    sheet, pictures = snap(parser.parse_args(argv).deck)
    print(json.dumps({"sheet": sheet, "slides": pictures}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
