"""Unit tests for skills/agentic-manager-slides-deck/scripts/finish_deck.py.
The whole pipeline has end-to-end tests in test_e2e_pipeline.py.
Run with: python3 tests/run.py agentic-manager-slides-deck
"""

import os
import sys
import unittest
from pathlib import Path
from unittest import mock

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(TEST_DIR))
sys.path.insert(0, os.path.join(REPO_ROOT, "skills",
                os.path.basename(TEST_DIR), "scripts"))
import finish_deck  # noqa: E402
sys.path.insert(0, TEST_DIR)
from deck_fixture import CREDIT, DECK, content, slide, temp_output, write_asset, write_credited_asset, write_slides  # noqa: E402


class FinishDeckTest(unittest.TestCase):
    def setUp(self):
        self.folder = temp_output(self)

    def test_invalid_slides_write_nothing(self):
        data = content()
        data["title"] = ""
        write_slides(self.folder, data)
        with self.assertRaisesRegex(SystemExit, "nothing was written:\n  - title: must be one"):
            finish_deck.finish(DECK)
        self.assertEqual(os.listdir(os.path.join(
            self.folder, DECK)), ["slides.json"])

    def test_an_image_links_to_assets(self):
        # The page links the image in _assets, beside the deck's folder,
        # rather than holding a copy.
        write_asset(self.folder)
        data = content()
        data["slides"][0] = slide("<img src='{{asset:acme-logo}}'>")
        write_slides(self.folder, data)
        result = finish_deck.finish(DECK)
        self.assertTrue(result["ok"], result)
        with open(result["path"], encoding="utf-8") as f:
            self.assertIn(
                "<img src='../_assets/acme-logo/image.svg'>", f.read())

    def test_valid_slides_write_a_deck_that_passes(self):
        write_slides(self.folder, content())
        result = finish_deck.finish(DECK)
        self.assertEqual(result, {"path": os.path.join(self.folder, DECK, "Acme-Q3-Review_Slides.html"),
                                  "temporary": False, "ok": True, "errors": [],
                                  "placeholders": ["[IMAGE: team photo]"], "stand_ins": [],
                                  "credits": [], "opened": False})

    def test_a_downloaded_image_is_credited_on_every_slide_that_shows_it(self):
        write_credited_asset(self.folder)
        data = content()
        for number in (0, 2):
            data["slides"][number]["html"].append(
                "<img src='{{asset:earth}}'>")
        write_slides(self.folder, data)
        result = finish_deck.finish(DECK)
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["credits"], [{"asset": "earth", "license": CREDIT["license"],
                                              "source": CREDIT["source"]}])
        with open(result["path"], encoding="utf-8") as f:
            slides = f.read().split('<div class="slide')[2:]
        self.assertEqual([slide.count('<p class="asset-credit">Example Agency · CC BY 4.0</p>')
                          for slide in slides], [1, 0, 1])

    def test_open_shows_a_passing_deck_in_the_browser(self):
        write_slides(self.folder, content())
        for open_page, browser_opened, opened in ((False, True, False), (True, True, True),
                                                  (True, False, False)):
            with self.subTest(open_page=open_page, browser_opened=browser_opened), \
                    mock.patch.object(finish_deck.webbrowser, "open", return_value=browser_opened) as browser:
                result = finish_deck.finish(DECK, open_page)
                self.assertEqual(result["opened"], opened)
                self.assertEqual(browser.call_args_list,
                                 [mock.call(Path(result["path"]).as_uri())] if open_page else [])


if __name__ == "__main__":
    unittest.main()
