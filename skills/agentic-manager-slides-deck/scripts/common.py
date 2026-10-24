"""What the skill's scripts share: the deck folder's file names and the closed
set of files it holds, the slide's size, the one library a deck loads, what a
slide may hold and the tokens that place a chart, a ring, an image or the page
number in it, how to find a deck's folder, and the examples and images every
deck shares, listed from their descriptions each time so the lists can't go
stale. Scripts import the shared library's names from here, so they don't
depend on the order of their imports.
"""
import glob
import os
import re
import sys

# The agentic-manager-utils-lib skill, installed next to this one.
LIB_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)),
                       "..", "..", "agentic-manager-utils-lib")
sys.path.insert(0, LIB_DIR)
from agentic_manager.output_file import read_json, target, write_output_file  # noqa: E402,F401
from agentic_manager.output_folder import DAY_FOLDER, EXAMPLE_DESCRIPTION, KEPT_EXAMPLES, read_description, clear_folder, day_folder, output_folder  # noqa: E402,F401
from agentic_manager.text import NAME, SLUG, free_name, slug  # noqa: E402,F401
from agentic_manager.web import ssl_context  # noqa: E402,F401

# The skill's output folder, and a deck folder's files in it: the slides the
# agent writes and the deck built from them, <Name>_Slides.html.
FOLDER_NAME = "slides-decks"
SLIDES = "slides.json"
DECK_SUFFIX = "_Slides.html"

# Images (logos, screenshots, photos) live once in _assets, next to the decks,
# and every deck links to them rather than holding a copy, so the HTML stays
# small; a deck shared on its own is exported to PDF, which carries them. Each
# is a folder named in lowercase words joined by hyphens, like an example,
# holding image.<a type a browser shows> and a description of what it shows,
# so a later deck can find and reuse it; a downloaded image's description also
# holds its credit, so no deck that shows it can lose the credit.
ASSETS = "_assets"
IMAGE_TYPES = ("png", "jpg", "jpeg", "gif", "svg", "webp")
ASSET_IMAGE = re.compile(r"image\.(?:" + "|".join(IMAGE_TYPES) + ")")
# The description's labelled lines: what the image shows, then, for an image
# downloaded from the internet, its credit line, license, the page that states
# the license and the image's own address. An image the user gave has no
# credit: it is theirs.
SHOWS = "Shows"
CREDIT_FIELDS = {"credit": "Credit", "license": "License",
                 "source": "Source", "image": "Image"}
# A drawing standing in for a real image still to find, by what that image
# shows, such as <figure data-image='the Earth seen from space'>.
STAND_IN = "data-image"

# Every slide is this size; content that doesn't fit is clipped.
SLIDE_WIDTH, SLIDE_HEIGHT = 1100, 618

# Chart.js is the only code a deck loads from outside: it runs in the viewer's
# browser, never while the deck is built, so nothing the skill runs depends on
# it. It is pinned, so a deck draws the same way every time it is opened.
CHART_JS = "https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.js"

# {{chart:<id>}} or {{ring:<id>}} in a slide's HTML, replaced by the chart or
# ring of that id; {{asset:<name>}}, by the link to that image in _assets.
ELEMENT_ID = SLUG
TOKEN = re.compile(r"\{\{(chart|ring|asset):([^{}]*)\}\}")
# {{page}}, replaced by the slide's number, so adding, removing or moving a
# slide never leaves a page number to correct by hand.
PAGE = "{{page}}"

# HTML elements that never have a closing tag.
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source",
        "track", "wbr"}
# The attributes that load a file, and a URL leading off the page, which a deck
# opened offline can't load.
URL_ATTRIBUTES = ("src", "srcset", "poster")
REMOTE = re.compile(r"(?:https?:)?//", re.I)

# Content still missing, such as [IMAGE: team photo].
PLACEHOLDER = re.compile(
    r"\[(?:CHART|IMAGE|DIAGRAM|TABLE|PLACEHOLDER): [^\]\n]+\]")

# The examples, each a folder of its own: the skill's, real slides each kept as
# a description and a layout-only wireframe, and the user's, slides of their
# decks kept in _examples beside the decks as a description, the slide's
# slides.json and its page. Their list is read from the descriptions each
# time, so it can't go stale as examples are added or removed; a name that
# starts with _ is a note, not an example.
EXAMPLES_DIR = os.path.join(os.path.dirname(
    os.path.realpath(__file__)), "..", "examples")
WIREFRAME, EXAMPLE_PAGE = "wireframe.svg", "slide.html"
USE_FOR = "Use for"


def expected_files(deck):
    """The closed set of files the deck folder `deck` holds."""
    return {SLIDES, deck_file(deck)}


def deck_file(deck):
    """The deck's HTML file name, <Name>_Slides.html, from its folder name."""
    match = DAY_FOLDER.fullmatch(deck)
    if not match:
        raise SystemExit(
            f"{deck!r} is not a deck folder, <Name>_<YY-MM-DD>")
    return match["subject"] + DECK_SUFFIX


def deck_dir(deck):
    """The absolute path of the deck folder `deck` inside the skill's output
    folder. Exits if `deck` isn't a deck folder name, would lead outside it or
    doesn't exist."""
    deck_file(deck)
    folder, _ = output_folder(FOLDER_NAME)
    path = target(folder, deck)
    if not os.path.isdir(path):
        raise SystemExit(
            f"{deck} doesn't exist in {folder}: run init_deck.py first")
    return path


def examples():
    """[{folder, source, title, use_for}] of every example, the skill's then
    the user's, each by name: its folder's absolute path, "built-in" or
    "yours", its description's heading and what it is good for."""
    found = []
    folders = (("built-in", EXAMPLES_DIR),
               ("yours", user_examples_dir()))
    for source, folder in folders:
        for path in sorted(glob.glob(os.path.join(folder, "*", EXAMPLE_DESCRIPTION))):
            example = os.path.dirname(path)
            if os.path.basename(example).startswith("_"):
                continue
            title, fields = read_description(path)
            found.append({"folder": os.path.realpath(example), "source": source,
                          "title": title, "use_for": fields.get(USE_FOR, "")})
    return found


def user_examples_dir():
    """The absolute path of _examples, the slides the user kept, in the skill's
    output folder; it may not exist yet."""
    return os.path.join(output_folder(FOLDER_NAME)[0], KEPT_EXAMPLES)


def asset_link(name, depth=1):
    """The link to the image `name` in _assets from a page `depth` folders
    below the skill's output folder: 1 for a deck, 2 for a kept example."""
    return "../" * depth + f"{ASSETS}/{name}/{asset_image(name) or 'image'}"


def asset_image(name):
    """The file name of the image `name` in _assets, such as image.jpg, or
    None if it has none."""
    folder = os.path.join(assets_dir(), name)
    files = sorted(os.listdir(folder)) if os.path.isdir(folder) else []
    return next((file for file in files if ASSET_IMAGE.fullmatch(file)), None)


def link_kind(value):
    """What a file-loading attribute's value links to: "remote" for a URL
    leading off the page, "file" for a local path, None for nothing or inline
    data."""
    value = (value or "").strip()
    if REMOTE.match(value):
        return "remote"
    if value and not value.startswith("data:"):
        return "file"
    return None


def assets_dir():
    """The absolute path of _assets in the skill's output folder; it may not
    exist yet."""
    return os.path.join(output_folder(FOLDER_NAME)[0], ASSETS)


def describe_asset(title, shows, credit=None):
    """The description.md of an image titled `title` that shows `shows`, with
    its `credit` ({"credit", "license", "source", "image"}) if downloaded."""
    lines = [f"# {title}", f"**{SHOWS}:** {shows}"]
    lines += [f"**{label}:** {credit[key]}" for key,
              label in CREDIT_FIELDS.items()] if credit else []
    return "\n\n".join(lines) + "\n"


def credits():
    """{name: {"credit", "license", "source", "image"}} of the images in
    _assets downloaded from the internet, none if there are none."""
    return {asset["name"]: asset["credit"] for asset in assets() if asset["credit"]}


def assets():
    """Every image in _assets, by name, as read_asset() reads it."""
    return [read_asset(name) for name in sorted(asset_names())]


def read_asset(name):
    """{"name", "title", "shows", "credit"} of the image `name` in _assets, from
    its description: empty text if it has none, and credit None unless it was
    downloaded."""
    title, fields = read_description(
        os.path.join(assets_dir(), name, EXAMPLE_DESCRIPTION))
    credit = {key: fields.get(label, "")
              for key, label in CREDIT_FIELDS.items()}
    return {"name": name, "title": title, "shows": fields.get(SHOWS, ""),
            "credit": credit if credit["credit"] else None}


def asset_names():
    """The names of the images in _assets, none if it doesn't exist yet."""
    folder = assets_dir()
    return frozenset(name for name in (os.listdir(folder) if os.path.isdir(folder) else ())
                     if SLUG.fullmatch(name) and asset_image(name))


def placed_images(text):
    """The images a slide's HTML `text` places, each once, in order."""
    return list(dict.fromkeys(match[2] for match in TOKEN.finditer(text) if match[1] == "asset"))


def credit_line(entry):
    """The text that credits a downloaded image on a slide, from its credit."""
    return f"{entry['credit']} · {entry['license']}"
