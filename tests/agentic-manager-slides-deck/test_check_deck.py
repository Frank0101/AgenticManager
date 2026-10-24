"""Unit tests for skills/agentic-manager-slides-deck/scripts/check_deck.py.
Run with: python3 tests/run.py agentic-manager-slides-deck

Each test builds the fixture's deck with make_deck.py, then breaks the page or
the folder the way a generator bug or a stray file would, and expects the
check to say so.
"""

import os
import shutil
import sys
import unittest

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(TEST_DIR))
sys.path.insert(0, os.path.join(REPO_ROOT, "skills",
                os.path.basename(TEST_DIR), "scripts"))
import check_deck  # noqa: E402
import common  # noqa: E402
import make_deck  # noqa: E402
sys.path.insert(0, TEST_DIR)
from deck_fixture import DECK, content, temp_output, write_asset, write_credited_asset, write_slides  # noqa: E402

PAGE = "Acme-Q3-Review_Slides.html"


class CheckDeckTest(unittest.TestCase):
    def setUp(self):
        self.folder = temp_output(self)
        self.deck = os.path.join(self.folder, DECK)
        write_slides(self.folder, content())
        self.assertTrue(make_deck.make_deck(DECK)["ok"])
        with open(os.path.join(self.deck, PAGE), encoding="utf-8") as f:
            self.page = f.read()

    def errors_of(self, page):
        """The check's errors once the deck's page is `page`."""
        with open(os.path.join(self.deck, PAGE), "w", encoding="utf-8") as f:
            f.write(page)
        return check_deck.check_deck(DECK)["errors"]

    def test_a_built_deck_passes_and_lists_its_placeholders(self):
        self.assertEqual(check_deck.check_deck(DECK),
                         {"ok": True, "errors": [], "placeholders": ["[IMAGE: team photo]"], "stand_ins": []})

    def test_broken_pages_fail(self):
        # Each case: a change to the page, and the error it raises.
        cases = [
            ("a slide lost", lambda p: p.replace('<div class="slide">', "<div>", 1),
             "the page has 2 slides; slides.json has 3"),
            ("another title", lambda p: p.replace(
                "<title>Acme Q3 Review", "<title>Acme"), "the page's title is 'Acme'"),
            ("a toolbar button lost", lambda p: p.replace(
                '<button onclick="zoom(-1)" title="Zoom out">−</button>', ""), "the toolbar's buttons are"),
            ("no zoom", lambda p: p.replace(
                "function zoom(", "function z("), "the page has no zoom script"),
            ("no print rules", lambda p: p.replace(
                "@media print", "@media screen"), "the page has no print rules for 1100x618 pages"),
            ("another library", lambda p: p.replace(
                common.CHART_JS, "https://cdn.example.com/chart.js"), "the page loads"),
            ("a remote image", lambda p: p.replace(
                "<p>Platform team</p>", "<img src='https://example.com/a.png'>"), "loads remote files: <img src>"),
            ("a stylesheet", lambda p: p.replace(
                "</head>", "<link rel='stylesheet' href='x.css'></head>"), "loads remote files: <link>"),
            ("a chart lost", lambda p: p.replace(
                '<canvas id="chart-revenue">', "<canvas>"), "the page's charts are"),
            ("other chart data", lambda p: p.replace(
                '"data": [3, 5]', '"data": [3, 6]'), "chart data differs"),
            ("a ring segment lost", lambda p: p.replace('<path d="', '<g d="', 1),
             "the page's rings and their segments are {'ring-phases': 2}"),
            ("a token left", lambda p: p.replace(
                "<p>Platform team</p>", "<p>{{ring:phases}}</p>"), "the page still holds a token: {{ring:phases}}"),
            ("a page number left", lambda p: p.replace(
                "<p>Platform team</p>", "<p>{{page}}</p>"), "the page still holds a token: {{page}}"),
        ]
        for name, change, expected in cases:
            with self.subTest(name):
                broken = change(self.page)
                self.assertNotEqual(broken, self.page)
                errors = self.errors_of(broken)
                self.assertTrue(any(expected in error for error in errors),
                                f"{expected!r} not in {errors}")

    def test_linked_images_are_the_placed_ones_and_exist(self):
        write_asset(self.folder)
        data = content()
        data["slides"][0]["html"].append("<img src='{{asset:acme-logo}}'>")
        write_slides(self.folder, data)
        self.assertTrue(make_deck.make_deck(DECK)["ok"])
        with open(os.path.join(self.deck, PAGE), encoding="utf-8") as f:
            page = f.read()
        cases = [("another image", lambda p: p.replace("acme-logo/image.svg", "other/image.svg"),
                  "the page links the images ['../_assets/other/image.svg']; slides.json places ['acme-logo']"),
                 ("an image by its path", lambda p: p.replace("../_assets/acme-logo/image.svg", "/tmp/acme-logo.svg"),
                  "the page links the images ['/tmp/acme-logo.svg']")]
        for name, change, expected in cases:
            with self.subTest(name):
                errors = self.errors_of(change(page))
                self.assertTrue(any(expected in error for error in errors),
                                f"{expected!r} not in {errors}")
        shutil.rmtree(os.path.join(self.folder, "_assets", "acme-logo"))
        self.assertIn("_assets has no acme-logo", self.errors_of(page))

    def test_images_whose_names_share_a_start_pass(self):
        # acme sorts before acme-logo, but its link sorts after it.
        data = content()
        for name in ("acme", "acme-logo"):
            write_asset(self.folder, name)
            data["slides"][0]["html"].append(
                f"<img src='{{{{asset:{name}}}}}'>")
        write_slides(self.folder, data)
        self.assertTrue(make_deck.make_deck(DECK)["ok"])

    def test_a_downloaded_image_needs_its_credit_on_its_slide(self):
        write_credited_asset(self.folder)
        data = content()
        data["slides"][1]["html"].append("<img src='{{asset:earth}}'>")
        write_slides(self.folder, data)
        self.assertTrue(make_deck.make_deck(DECK)["ok"])
        with open(os.path.join(self.deck, PAGE), encoding="utf-8") as f:
            page = f.read()
        self.assertEqual(self.errors_of(page.replace("Example Agency", "Someone")),
                         ["slide 2 shows earth without its credit: Example Agency · CC BY 4.0"])

    def test_stand_ins_are_listed_by_slide(self):
        data = content()
        data["slides"][2]["html"].append(
            "<figure data-image='the Earth seen from space'><svg viewBox='0 0 4 4'></svg></figure>")
        write_slides(self.folder, data)
        self.assertEqual(make_deck.make_deck(DECK)["stand_ins"],
                         ["slide 3: the Earth seen from space"])

    def test_the_folder_holds_only_the_decks_files(self):
        # A stray file fails, a hidden one such as .DS_Store doesn't.
        for name in (".DS_Store", "notes.md"):
            with open(os.path.join(self.deck, name), "w", encoding="utf-8") as f:
                f.write("x")
        self.assertEqual(check_deck.check_deck(DECK)["errors"],
                         [f"the folder must hold only {PAGE}, slides.json; move notes.md to your own scratch folder"])
        os.remove(os.path.join(self.deck, "notes.md"))
        os.remove(os.path.join(self.deck, PAGE))
        self.assertEqual(check_deck.check_deck(DECK)["errors"],
                         [f"the folder must hold only {PAGE}, slides.json; missing {PAGE}"])


if __name__ == "__main__":
    unittest.main()
