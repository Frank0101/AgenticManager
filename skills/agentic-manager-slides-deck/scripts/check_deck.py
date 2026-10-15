"""Checks a finished deck, <Name>_Slides.html, against the slides.json it was
built from, read-only.

    python3 check_deck.py --deck <Name>_<YY-MM-DD>

It shares only common.py with make_deck.py: it reads the page back as a
browser would and counts what slides.json says must be there (the slides,
each chart with its data, each ring with its segments), so a generator bug
can't pass by agreeing with itself. It also checks the page's fixed parts
(the toolbar, zoom, the print rules), that it loads nothing but the pinned
Chart.js, only when a slide holds a chart, that every image it
links is in _assets, as slides.json places them, that every slide showing a
downloaded image shows its credit, and that the folder holds only the deck's
files.

Placeholders, such as [IMAGE: team photo], aren't errors: they are content the
user hasn't given yet, listed so the agent can say what is missing. Neither
are stand-ins, drawings marked as waiting for a real image, listed so the
agent can offer to find them.

Prints one line of JSON: "ok", "errors", "placeholders" and "stand_ins". Exits
1 if any check fails.
"""
import argparse
import json
import os
import re
from html.parser import HTMLParser

from common import (ASSETS, CHART_JS, PAGE, PLACEHOLDER, REMOTE, SLIDE_HEIGHT, SLIDE_WIDTH, SLIDES, STAND_IN,
                    TOKEN, URL_ATTRIBUTES, VOID, asset_link, asset_names, credit_line, credits, deck_dir, deck_file,
                    expected_files, placed_images, read_json)

TOOLBAR_BUTTONS = ["Zoom in", "Zoom out", "Export PDF"]
CHARTS_DATA = re.compile(r"const charts = (.*);\n")


def check_deck(deck):
    """{"ok", "errors", "placeholders", "stand_ins"} of the deck folder `deck`."""
    folder = deck_dir(deck)
    errors, placeholders, stand_ins = check(
        folder, deck, read_json(os.path.join(folder, SLIDES)))
    return {"ok": not errors, "errors": errors, "placeholders": placeholders, "stand_ins": stand_ins}


def check(folder, deck, content):
    """(errors, placeholders, stand-ins) of the deck in `folder` against
    `content`, the slides.json it was built from."""
    errors = []
    files = {name for name in os.listdir(folder) if not name.startswith(".")}
    wanted = expected_files(deck)
    if files != wanted:
        extra, missing = sorted(files - wanted), sorted(wanted - files)
        errors.append("the folder must hold only " + ", ".join(sorted(wanted))
                      + (f"; remove {', '.join(extra)}" if extra else "")
                      + (f"; missing {', '.join(missing)}" if missing else ""))
    path = os.path.join(folder, deck_file(deck))
    if not os.path.isfile(path):
        return errors, [], []
    page, raw = read_page(path)
    if page.title.strip() != content["title"].strip():
        errors.append(
            f"the page's title is {page.title.strip()!r}, not slides.json's title")
    if page.slides != len(content["slides"]):
        errors.append(f"the page has {page.slides} slides; slides.json has "
                      f"{len(content['slides'])}")
    if page.buttons != TOOLBAR_BUTTONS:
        errors.append(
            f"the toolbar's buttons are {page.buttons}, not {TOOLBAR_BUTTONS}")
    if not any("function zoom(" in script for script in page.scripts):
        errors.append("the page has no zoom script")
    if "@media print" not in page.style or f"size: {SLIDE_WIDTH}px {SLIDE_HEIGHT}px" not in page.style:
        errors.append(
            f"the page has no print rules for {SLIDE_WIDTH}x{SLIDE_HEIGHT} pages")
    charts, rings = content.get("charts", {}), content.get("rings", {})
    wanted_sources = [CHART_JS] if charts else []
    if page.sources != wanted_sources:
        errors.append(
            f"the page loads {page.sources}, but its charts need {wanted_sources}")
    if page.remote or page.links:
        errors.append("the page loads remote files: " +
                      ", ".join(page.remote + ["<link>"] * page.links))
    if sorted(page.canvases) != sorted(f"chart-{ident}" for ident in charts):
        errors.append(f"the page's charts are {sorted(page.canvases)}; slides.json has "
                      f"{sorted(charts)}")
    found = [CHARTS_DATA.search(script) for script in page.scripts]
    data = [json.loads(match[1]) for match in found if match]
    if charts and data != [charts]:
        errors.append(
            "the page's chart data differs from slides.json's charts")
    wanted_rings = {f"ring-{ident}": len(ring["segments"])
                    for ident, ring in rings.items()}
    if page.rings != wanted_rings:
        errors.append(f"the page's rings and their segments are {page.rings}; "
                      f"slides.json has {wanted_rings}")
    placed = sorted(match[2] for slide in content["slides"]
                    for match in TOKEN.finditer("\n".join(slide["html"])) if match[1] == "asset")
    if sorted(page.files) != [asset_link(name) for name in placed]:
        errors.append(
            f"the page links the images {page.files}; slides.json places {placed} from {ASSETS}")
    missing = sorted(set(placed) - asset_names())
    if missing:
        errors.append(f"{ASSETS} has no {', '.join(missing)}")
    known = credits()
    for number, slide in enumerate(content["slides"], 1):
        shown = "".join(page.slide_text[number - 1]
                        ) if number <= len(page.slide_text) else ""
        for name in placed_images("\n".join(slide["html"])):
            if name in known and credit_line(known[name]) not in shown:
                errors.append(
                    f"slide {number} shows {name} without its credit: {credit_line(known[name])}")
    token = TOKEN.search(raw)
    if token or PAGE in raw:
        errors.append(
            f"the page still holds a token: {token[0] if token else PAGE}")
    return errors, PLACEHOLDER.findall("".join(page.text)), page.stand_ins


def read_page(path):
    reader = PageReader()
    with open(path, encoding="utf-8") as f:
        page = f.read()
    reader.feed(page)
    reader.close()
    return reader, page


class PageReader(HTMLParser):
    """What a finished deck holds, read as a browser would."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.open = []  # (tag, classes, id) of the elements still open
        self.title, self.style, self.scripts, self.text = "", "", [], []
        self.slides, self.buttons, self.sources, self.remote = 0, [], [], []
        self.files = []  # the local files the page links, by their link
        self.canvases, self.rings, self.links = [], {}, 0
        self.slide_text = []  # each slide's text, in pieces
        self.stand_ins = []  # "slide <n>: <the image it stands in for>"

    def inside(self, tag, cls):
        return any(t == tag and cls in c for t, c, _ in self.open)

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        self.read_tag(tag, attributes)
        if tag not in VOID:
            self.open.append((tag, (attributes.get("class") or "").split(),
                              attributes.get("id")))

    def handle_startendtag(self, tag, attrs):
        self.read_tag(tag, dict(attrs))

    def read_tag(self, tag, attrs):
        classes = (attrs.get("class") or "").split()
        parent = self.open[-1] if self.open else None
        if tag == "div" and "slide" in classes and parent and "slides-wrapper" in parent[1]:
            self.slides += 1
            self.slide_text.append([])
        if STAND_IN in attrs:
            self.stand_ins.append(f"slide {self.slides}: {attrs[STAND_IN]}")
        if tag == "button" and self.inside("div", "toolbar"):
            self.buttons.append(attrs.get("title"))
        if tag == "script" and attrs.get("src"):
            self.sources.append(attrs["src"])
        elif tag == "link":
            self.links += 1
        else:
            for name in URL_ATTRIBUTES:
                value = (attrs.get(name) or "").strip()
                if REMOTE.match(value):
                    self.remote.append(f"<{tag} {name}>")
                elif value and not value.startswith("data:"):
                    self.files.append(value)
        if tag == "canvas":
            self.canvases.append(attrs.get("id"))
        if tag == "path" and parent and parent[0] == "svg" and "ring" in parent[1]:
            self.rings[parent[2]] = self.rings.get(parent[2], 0) + 1
        if tag == "svg" and "ring" in classes:
            self.rings.setdefault(attrs.get("id"), 0)

    def handle_endtag(self, tag):
        if tag not in VOID:
            while self.open and self.open.pop()[0] != tag:
                pass

    def handle_data(self, data):
        tag = self.open[-1][0] if self.open else None
        if tag == "title":
            self.title += data
        elif tag == "style":
            self.style += data
        elif tag == "script":
            self.scripts.append(data)
        else:
            self.text.append(data)
            if self.slide_text and self.inside("div", "slide"):
                self.slide_text[-1].append(data)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Check a finished deck against its slides.json.")
    parser.add_argument("--deck", required=True,
                        help="the deck's folder, <Name>_<YY-MM-DD>, inside slides-decks")
    result = check_deck(parser.parse_args(argv).deck)
    print(json.dumps(result))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
