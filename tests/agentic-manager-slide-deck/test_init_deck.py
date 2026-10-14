"""Unit tests for skills/agentic-manager-slide-deck/scripts/init_deck.py.
The whole pipeline has end-to-end tests in test_e2e_pipeline.py.
Run with: python3 tests/run.py agentic-manager-slide-deck

The config's path is patched to the test's own config, in a temporary folder.
"""

import os
import sys
import unittest
from datetime import date

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(TEST_DIR))
sys.path.insert(0, os.path.join(REPO_ROOT, "skills",
                os.path.basename(TEST_DIR), "scripts"))
import common  # noqa: E402
import init_deck  # noqa: E402
sys.path.insert(0, TEST_DIR)
from deck_fixture import temp_output  # noqa: E402

TODAY = date(2026, 10, 5)


class InitTest(unittest.TestCase):
    def setUp(self):
        self.folder = temp_output(self)

    def test_new_deck_then_a_rerun_replaces_it(self):
        # A new deck starts as an empty folder; running it again the same day
        # starts from scratch, but leaves the folders of other days.
        result = init_deck.init("Acme-Q3-Review", today=TODAY)
        path = os.path.join(self.folder, "Acme-Q3-Review_26-10-05")
        self.assertEqual(result.pop("examples"), common.examples())
        self.assertEqual(result, {"folder": self.folder, "temporary": False,
                                  "deck": "Acme-Q3-Review_26-10-05", "deck_dir": path,
                                  "slides_path": "Acme-Q3-Review_26-10-05/slides.json",
                                  "replaced": False})
        self.assertEqual(os.listdir(path), [])
        # The examples and assets folders are there from the first deck, empty.
        for shared in ("_examples", "_assets"):
            self.assertEqual(os.listdir(os.path.join(self.folder, shared)), [])
        with open(os.path.join(path, "slides.json"), "w", encoding="utf-8") as f:
            f.write("{}")
        earlier = os.path.join(self.folder, "Acme-Q3-Review_26-10-04")
        os.makedirs(earlier)
        self.assertTrue(init_deck.init(
            "Acme-Q3-Review", today=TODAY)["replaced"])
        self.assertEqual(os.listdir(path), [])
        self.assertTrue(os.path.isdir(earlier))

    def test_refuses_a_name_that_isnt_words_joined_by_hyphens(self):
        for name in ("Acme Q3", "Acme_Q3", "../Acme", "", "Acme-"):
            with self.subTest(name), self.assertRaisesRegex(SystemExit, "joined by hyphens"):
                init_deck.init(name, today=TODAY)
        self.assertFalse(os.path.exists(self.folder))


if __name__ == "__main__":
    unittest.main()
