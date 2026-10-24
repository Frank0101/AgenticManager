"""Unit tests for skills/agentic-manager-slides-deck/scripts/add_asset.py.
Run with: python3 tests/run.py agentic-manager-slides-deck

The config's path is patched to the test's own config, in a temporary folder.
"""

import os
import sys
import tempfile
import unittest
from unittest import mock

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(TEST_DIR))
sys.path.insert(0, os.path.join(REPO_ROOT, "skills",
                os.path.basename(TEST_DIR), "scripts"))
import add_asset  # noqa: E402
import common  # noqa: E402
sys.path.insert(0, TEST_DIR)
from deck_fixture import CREDIT, temp_output  # noqa: E402

PNG = b"\x89PNG\r\n\x1a\n" + bytes(16)
URL = "https://example.org/files/Blue%20Earth.png"
GIVEN = {"page": CREDIT["source"], "license": CREDIT["license"], "credit": CREDIT["credit"],
         "title": "The Earth", "shows": "the Earth from space"}


class Response:
    """What urlopen returns, holding `data`."""

    def __init__(self, data):
        self.data = data

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self, size):
        return self.data[:size]


def serving(data):
    return mock.patch.object(add_asset.urllib.request, "urlopen", return_value=Response(data))


class AddAssetTest(unittest.TestCase):
    def setUp(self):
        self.folder = temp_output(self)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.source = tmp.name

    def image(self, name, text="<svg/>"):
        path = os.path.join(self.source, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        return path

    def read(self, *parts):
        with open(os.path.join(self.folder, "_assets", *parts), encoding="utf-8") as f:
            return f.read()

    def test_copies_an_image_into_its_described_folder_then_replaces_it_by_name(self):
        result = add_asset.add_asset(self.image(
            "Acme Logo (2026).SVG"), "Acme logo", " the  logo, wide ")
        destination = os.path.join(
            self.folder, "_assets", "acme-logo-2026", "image.svg")
        self.assertEqual(
            result, {"asset": "acme-logo-2026", "path": destination, "replaced": False})
        self.assertEqual(self.read("acme-logo-2026", "description.md"),
                         "# Acme logo\n\n**Shows:** the logo, wide\n")
        self.assertEqual(common.read_asset("acme-logo-2026"),
                         {"name": "acme-logo-2026", "title": "Acme logo", "shows": "the logo, wide", "credit": None})
        with serving(PNG):
            again = add_asset.add_download(URL, **GIVEN, name="acme-logo-2026")
        self.assertTrue(again["replaced"])
        self.assertEqual(sorted(os.listdir(os.path.dirname(destination))), [
                         "description.md", "image.png"])

    def test_downloads_an_image_with_its_credit_in_its_description(self):
        with serving(PNG):
            result = add_asset.add_download(URL, **GIVEN)
        destination = os.path.join(
            self.folder, "_assets", "blue-earth", "image.png")
        self.assertEqual(
            result, {"asset": "blue-earth", "path": destination, "replaced": False})
        with open(destination, "rb") as f:
            self.assertEqual(f.read(), PNG)
        self.assertEqual(common.credits(), {
                         "blue-earth": {**CREDIT, "image": URL}})
        add_asset.redescribe("blue-earth", "Blue Earth", "the Earth, closer")
        self.assertEqual(common.read_asset("blue-earth")
                         ["shows"], "the Earth, closer")
        self.assertEqual(common.credits(), {
                         "blue-earth": {**CREDIT, "image": URL}})

    def test_refuses_what_isnt_a_described_image(self):
        cases = [
            ("a missing file", lambda: add_asset.add_asset(os.path.join(self.source, "missing.png"), "T", "S"),
             "is not a file"),
            ("a file that isn't an image", lambda: add_asset.add_asset(self.image("notes.txt", "notes"), "T", "S"),
             "is not a PNG"),
            ("a name outside _assets", lambda: add_asset.add_asset(self.image("logo.svg"), "T", "S", "../logo"),
             "must be lowercase words"),
            ("no description", lambda: add_asset.add_asset(self.image("logo.svg"), "Logo", " "),
             "--title and --shows must say"),
            ("describing a missing image", lambda: add_asset.redescribe("nothing", "T", "S"),
             "_assets has no image 'nothing'"),
        ]
        for name, call, expected in cases:
            with self.subTest(name), self.assertRaisesRegex(SystemExit, expected):
                call()
        self.assertFalse(os.path.exists(os.path.join(self.folder, "_assets")))

    def test_refuses_a_download_that_isnt_a_credited_image(self):
        cases = [
            ("a page, not an image", URL, GIVEN,
             b"<!doctype html><html>", "is not a PNG"),
            ("not a web address", "file:///etc/earth.png",
             GIVEN, PNG, "--url must be an http"),
            ("no page", URL, {**GIVEN, "page": "earth"},
             PNG, "--page must be an http"),
            ("no license", URL, {**GIVEN, "license": " "},
             PNG, "--license must say"),
            ("too big", URL, GIVEN, PNG + bytes(add_asset.MAX_BYTES), "is over 20 MB"),
        ]
        for name, url, given, data, expected in cases:
            with self.subTest(name), serving(data), self.assertRaisesRegex(SystemExit, expected):
                add_asset.add_download(url, **given)
        self.assertFalse(os.path.exists(os.path.join(self.folder, "_assets")))

    def test_an_images_type_comes_from_its_bytes(self):
        cases = [(PNG, "png"), (b"\xff\xd8\xff\xe0rest", "jpg"), (b"GIF89a rest", "gif"),
                 (b"RIFF\0\0\0\0WEBPVP8 ",
                  "webp"), (b"<?xml version='1.0'?>\n<SVG xmlns=''>", "svg"),
                 (b"<html><body>", None), (b"", None)]
        for data, kind in cases:
            with self.subTest(data[:8]):
                self.assertEqual(add_asset.image_type(data), kind)


if __name__ == "__main__":
    unittest.main()
