"""What the skill's scripts share: the deck folder's fixed file names and the
closed set of files it holds, the slide's fixed size, the runtime libraries a
deck may load, the HTML elements without a closing tag, what counts as a
remote file, the tokens that place a chart, a ring, an image or the page
number in a slide, the stand-in for a real image, the placeholder format, how
to find a deck's folder, and the examples and images every deck shares, read
from their descriptions.
Scripts import the shared library's names from here, so they don't depend on
the order of their imports.

Chart.js and Mermaid.js are the only code a deck loads from outside: they run
in the viewer's browser, never while the deck is built, so nothing the skill
runs depends on them. They are pinned, so a deck draws the same way every time
it is opened.

Images (logos, screenshots, photos) live once in _assets, next to the decks, and every deck links to them there rather than holding a copy, so
the HTML stays small; a deck shared on its own is exported to PDF, which
carries its images. Each image is a folder of its own, like an example: the
image, image.<type>, and a description.md saying what it shows, so a later
deck can find and reuse it, and adding or deleting an image is adding or
deleting its folder. A downloaded image's description also holds its credit,
so every slide that shows it can credit it and no deck can lose the credit.
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
from agentic_manager.output_folder import DAY_FOLDER, EXAMPLE_DESCRIPTION, clear_folder, day_folder, output_folder  # noqa: E402,F401
from agentic_manager.text import NAME, SLUG, free_name, slug  # noqa: E402,F401
from agentic_manager.web import ssl_context  # noqa: E402,F401

FOLDER_NAME = "slide-decks"
ASSETS = "_assets"
# An image in _assets is a folder named in lowercase words joined by hyphens,
# holding the image as image.<a type a browser shows> and its description.
IMAGE_TYPES = ("png", "jpg", "jpeg", "gif", "svg", "webp")
ASSET_IMAGE = re.compile(r"image\.(?:" + "|".join(IMAGE_TYPES) + ")")
# The description's labelled lines: what the image shows, then, for an image
# downloaded from the internet, its credit line, license, the page that states
# the license and the image's own address. An image the user gave has no
# credit: it is theirs.
SHOWS = "Shows"
CREDIT_FIELDS = {"credit": "Credit", "license": "License",
                 "source": "Source", "image": "Image"}
# A description, an example's or an image's: its title, then labelled lines
# such as **Use for:** or **Shows:**.
TITLE = re.compile(r"# (.+)")
LABELLED_LINE = re.compile(r"^\*\*([A-Za-z ]+):\*\* (.+)$", re.M)
# A drawing standing in for a real image still to find, by what that image
# shows, such as <figure data-image='the Earth seen from space'>.
STAND_IN = "data-image"
SLIDES = "slides.json"
DECK_SUFFIX = "_Slides.html"

# Every slide is this size; content that doesn't fit is clipped.
SLIDE_WIDTH, SLIDE_HEIGHT = 1100, 618

CHART_JS = "https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.js"
MERMAID_JS = "https://cdn.jsdelivr.net/npm/mermaid@11.4.1/dist/mermaid.min.js"

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


def deck_file(deck):
    """The deck's HTML file name, <Name>_Slides.html, from its folder name."""
    match = DAY_FOLDER.fullmatch(deck)
    if not match:
        raise SystemExit(
            f"{deck!r} is not a deck folder, <Name>_<YY-MM-DD>")
    return match["subject"] + DECK_SUFFIX


def expected_files(deck):
    """The closed set of files the deck folder `deck` holds."""
    return {SLIDES, deck_file(deck)}


# The examples, each a folder of its own: the skill's, real slides each kept as
# a description and a layout-only wireframe, and the user's, slides of their
# decks kept in _examples beside the decks as a description, the slide's
# slides.json and its page. Their list is read from the descriptions each
# time, so it can't go stale as examples are added or removed; a name that
# starts with _ is a note, not an example.
EXAMPLES_DIR = os.path.join(os.path.dirname(
    os.path.realpath(__file__)), "..", "examples")
USER_EXAMPLES = "_examples"
WIREFRAME, EXAMPLE_PAGE = "wireframe.svg", "slide.html"
USE_FOR = "Use for"


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
            with open(path, encoding="utf-8") as f:
                text = f.read()
            title = TITLE.match(text)
            found.append({"folder": os.path.realpath(example), "source": source,
                          "title": title[1] if title else "",
                          "use_for": dict(LABELLED_LINE.findall(text)).get(USE_FOR, "")})
    return found


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


def assets_dir():
    """The absolute path of _assets in the skill's output folder; it may not
    exist yet."""
    return os.path.join(output_folder(FOLDER_NAME)[0], ASSETS)


def user_examples_dir():
    """The absolute path of _examples, the slides the user kept, in the skill's
    output folder; it may not exist yet."""
    return os.path.join(output_folder(FOLDER_NAME)[0], USER_EXAMPLES)


def asset_names():
    """The names of the images in _assets, none if it doesn't exist yet."""
    folder = assets_dir()
    return frozenset(name for name in (os.listdir(folder) if os.path.isdir(folder) else ())
                     if SLUG.fullmatch(name) and asset_image(name))


def describe_asset(title, shows, credit=None):
    """The description.md of an image titled `title` that shows `shows`, with
    its `credit` ({"credit", "license", "source", "image"}) if downloaded."""
    lines = [f"# {title}", f"**{SHOWS}:** {shows}"]
    lines += [f"**{label}:** {credit[key]}" for key,
              label in CREDIT_FIELDS.items()] if credit else []
    return "\n\n".join(lines) + "\n"


def read_asset(name):
    """{"name", "title", "shows", "credit"} of the image `name` in _assets, from
    its description: empty text if it has none, and credit None unless it was
    downloaded."""
    path = os.path.join(assets_dir(), name, EXAMPLE_DESCRIPTION)
    text = ""
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as f:
            text = f.read()
    title = TITLE.match(text)
    fields = dict(LABELLED_LINE.findall(text))
    credit = {key: fields.get(label, "")
              for key, label in CREDIT_FIELDS.items()}
    return {"name": name, "title": title[1].strip() if title else "", "shows": fields.get(SHOWS, ""),
            "credit": credit if credit["credit"] else None}


def assets():
    """Every image in _assets, by name, as read_asset() reads it."""
    return [read_asset(name) for name in sorted(asset_names())]


def credits():
    """{name: {"credit", "license", "source", "image"}} of the images in
    _assets downloaded from the internet, none if there are none."""
    return {asset["name"]: asset["credit"] for asset in assets() if asset["credit"]}


def placed_images(text):
    """The images a slide's HTML `text` places, each once, in order."""
    return list(dict.fromkeys(match[2] for match in TOKEN.finditer(text) if match[1] == "asset"))


def credit_line(entry):
    """The text that credits a downloaded image on a slide, from its credit."""
    return f"{entry['credit']} · {entry['license']}"


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
