"""Unit tests for skills/agentic-manager-slide-deck/scripts/common.py.
Run with: python3 tests/run.py agentic-manager-slide-deck
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
from deck_fixture import temp_output  # noqa: E402


class DeckFolderTest(unittest.TestCase):
    def test_deck_file_and_expected_files(self):
        # A deck folder's HTML file is named after the deck, and the folder
        # holds it and slides.json only. Anything else isn't a deck folder.
        self.assertEqual(common.deck_file(
            "Acme-Q3_26-10-05"), "Acme-Q3_Slides.html")
        self.assertEqual(common.expected_files("Acme-Q3_26-10-05"),
                         {"slides.json", "Acme-Q3_Slides.html"})
        for name in ("Acme-Q3", "Acme_26-10", "_26-10-05x"):
            with self.subTest(name), self.assertRaisesRegex(SystemExit, "not a deck folder"):
                common.deck_file(name)

    def test_deck_dir(self):
        # A deck's folder is found inside the output folder, never outside it,
        # and only once init_deck.py has made it.
        folder = temp_output(self)
        os.makedirs(os.path.join(folder, "Acme_26-10-05"))
        self.assertEqual(common.deck_dir("Acme_26-10-05"),
                         os.path.join(folder, "Acme_26-10-05"))
        with self.assertRaisesRegex(SystemExit, "run init_deck.py first"):
            common.deck_dir("Other_26-10-05")
        with self.assertRaisesRegex(SystemExit, "without .."):
            common.deck_dir("../Acme_26-10-05")


if __name__ == "__main__":
    unittest.main()
