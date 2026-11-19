"""Unit tests for skills/agentic-manager-slides-deck/scripts/common.py.
Run with: python3 tests/run.py agentic-manager-slides-deck
"""

import os
import sys
import unittest

# tests/<skill>/ mirrors skills/<skill>/.
TEST_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(TEST_DIR))
sys.path.insert(0, os.path.join(REPO_ROOT, "skills",
                os.path.basename(TEST_DIR), "scripts"))
import common  # noqa: E402
sys.path.insert(0, TEST_DIR)
from deck_fixture import temp_output, write_asset  # noqa: E402


class DeckFolderTest(unittest.TestCase):
    def test_deck_file_and_expected_files(self):
        # A deck folder's HTML file is named after the deck, and the folder
        # holds it and slides.json only.
        self.assertEqual(common.deck_file(
            "Acme-Q3_26-10-05"), "Acme-Q3_Slides.html")
        self.assertEqual(common.expected_files("Acme-Q3_26-10-05"),
                         {"slides.json", "Acme-Q3_Slides.html"})

    def test_deck_dir(self):
        # A deck's folder is in the skill's output folder, slides-decks.
        folder = temp_output(self)
        os.makedirs(os.path.join(folder, "Acme_26-10-05"))
        self.assertEqual(common.deck_dir("Acme_26-10-05"),
                         os.path.join(folder, "Acme_26-10-05"))


class AssetsTest(unittest.TestCase):
    def test_the_asset_list_reads_every_folder_with_an_image(self):
        # An image put there by hand, without a description, is listed with
        # nothing in what it shows; a folder without an image isn't listed.
        folder = temp_output(self)
        write_asset(folder)
        write_asset(folder, "by-hand", "")
        os.makedirs(os.path.join(folder, "_assets", "no-image"))
        self.assertEqual(common.assets(), [
            {"name": "acme-logo", "title": "Acme logo",
                "shows": "the Acme logo, wide", "credit": None},
            {"name": "by-hand", "title": "", "shows": "", "credit": None}])


if __name__ == "__main__":
    unittest.main()
