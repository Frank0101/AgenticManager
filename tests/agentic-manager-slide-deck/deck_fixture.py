"""An invented deck shared by the tests: its slides.json, with a chart, a ring,
a Mermaid diagram and a placeholder, and an output folder of the test's own."""
import copy
import json
import os
import tempfile
from unittest import mock

from agentic_manager import config, output_folder

DECK = "Acme-Q3-Review_26-10-05"

CONTENT = {
    "title": "Acme Q3 Review",
    "style": [".title { font-size: 40px; }", ".slide.dark { background: #1d2433; }"],
    "slides": [
        {"class": "dark", "html": [
            "<h1 class='title'>Acme Q3 Review</h1>", "<p>Platform team</p>"]},
        {"html": ["<h2 class='title'>Revenue</h2>",
                  "<div style='height: 380px'>{{chart:revenue}}</div>",
                  "<div>{{ring:phases}}<p>[IMAGE: team photo]</p></div>"]},
        {"html": ["<h2>Flow</h2>",
                  "<pre class='mermaid'>graph LR; A[Plan]-->B[Ship]</pre>"]},
    ],
    "charts": {"revenue": {"type": "bar", "data": {
        "labels": ["Q1", "Q2"], "datasets": [{"label": "Revenue", "data": [3, 5]}]}}},
    "rings": {"phases": {"size": 240, "outer": 88, "inner": 44, "gap": 3, "start": -90,
                         "segments": [{"color": "#3e9c8f"}, {"color": "#7b5ea7", "value": 2},
                                      {"color": "#3a8a50"}]}},
}


def content():
    return copy.deepcopy(CONTENT)


def temp_output(test):
    """The skill's output folder in a temporary folder, for `test`: a config
    of its own setting the output root, never the developer's."""
    tmp = tempfile.TemporaryDirectory()
    test.addCleanup(tmp.cleanup)
    root = os.path.realpath(tmp.name)
    path = os.path.join(root, "config.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"sources": {}, "output": {
                  "root": os.path.join(root, "out")}}, f)
    for target, attribute, value in ((config, "CONFIG_PATH", path),
                                     (output_folder, "TEMP_ROOT", os.path.join(root, "temp"))):
        patcher = mock.patch.object(target, attribute, value)
        patcher.start()
        test.addCleanup(patcher.stop)
    return os.path.join(root, "out", "slide-decks")


def write_asset(folder, name="acme-logo", description="# Acme logo\n\n**Shows:** the Acme logo, wide\n"):
    """Puts the image `name`, an SVG, with its description in _assets in the
    output folder `folder`."""
    os.makedirs(os.path.join(folder, "_assets", name), exist_ok=True)
    with open(os.path.join(folder, "_assets", name, "image.svg"), "w", encoding="utf-8") as f:
        f.write("<svg/>")
    with open(os.path.join(folder, "_assets", name, "description.md"), "w", encoding="utf-8") as f:
        f.write(description)


def write_slides(folder, data, deck=DECK):
    """Writes slides.json for `deck` in the output folder `folder`."""
    os.makedirs(os.path.join(folder, deck), exist_ok=True)
    with open(os.path.join(folder, deck, "slides.json"), "w", encoding="utf-8") as f:
        json.dump(data, f)


CREDIT = {"credit": "Example Agency", "license": "CC BY 4.0",
          "source": "https://example.org/wiki/File:Earth.jpg", "image": "https://example.org/files/earth.jpg"}
CREDITED = ("# The Earth\n\n**Shows:** the Earth from space\n\n**Credit:** Example Agency\n\n"
            "**License:** CC BY 4.0\n\n**Source:** https://example.org/wiki/File:Earth.jpg\n\n"
            "**Image:** https://example.org/files/earth.jpg\n")


def write_credited_asset(folder, name="earth"):
    """Puts the image `name` in _assets in the output folder `folder` as if
    downloaded, its description holding CREDIT."""
    write_asset(folder, name, CREDITED)
