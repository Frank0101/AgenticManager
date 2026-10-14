"""Unit tests for skills/agentic-manager-slide-deck/scripts/save_example.py.
Run with: python3 tests/run.py agentic-manager-slide-deck

The config's path is patched to the test's own config, in a temporary folder.
"""

import json
import os
import sys
import unittest

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(TEST_DIR))
sys.path.insert(0, os.path.join(REPO_ROOT, "skills",
                os.path.basename(TEST_DIR), "scripts"))
import common  # noqa: E402
import save_example  # noqa: E402
sys.path.insert(0, TEST_DIR)
from deck_fixture import DECK, content, temp_output, write_asset, write_slides  # noqa: E402


class SaveExampleTest(unittest.TestCase):
    def setUp(self):
        self.folder = temp_output(self)
        write_slides(self.folder, content())

    def test_keeps_one_slide_with_what_it_places(self):
        # Slide 2 places the chart and the ring: the example keeps them, the
        # deck's CSS, and nothing of the other slides, in a folder of its own.
        write_asset(self.folder, "logo.svg")
        data = content()
        data["slides"][1]["html"].append("<img src='{{asset:logo.svg}}'>")
        write_slides(self.folder, data)
        result = save_example.save(
            DECK, 2, "Revenue  at a glance", "a chart beside a ring")
        folder = os.path.join(self.folder, "_examples", "revenue-at-a-glance")
        self.assertEqual(result, {"example": "revenue-at-a-glance", "folder": folder,
                                  "page": os.path.join(folder, "slide.html"), "temporary": False})
        self.assertEqual(sorted(os.listdir(folder)), [
                         "description.md", "slide.html", "slides.json"])
        with open(os.path.join(folder, "slides.json"), encoding="utf-8") as f:
            kept = json.load(f)
        self.assertEqual(kept, {"title": "Revenue at a glance", "style": data["style"],
                                "slides": [data["slides"][1]], "charts": data["charts"],
                                "rings": data["rings"]})
        with open(result["page"], encoding="utf-8") as f:
            page = f.read()
        # The page links the chart and the shared image, two folders up.
        self.assertIn('<canvas id="chart-revenue">', page)
        self.assertIn("<img src='../../_assets/logo.svg'>", page)
        listed = [e for e in common.examples() if e["source"] == "yours"]
        self.assertEqual(listed, [{"folder": os.path.realpath(folder), "source": "yours",
                                   "title": "Revenue at a glance", "use_for": "a chart beside a ring"}])
        # Keeping the first slide drops the chart and ring it doesn't place,
        # and a taken name gets the next number, never overwriting.
        again = save_example.save(
            DECK, 1, "Revenue at a glance", "a title slide")
        self.assertEqual(again["example"], "revenue-at-a-glance-2")
        with open(os.path.join(again["folder"], "slides.json"), encoding="utf-8") as f:
            self.assertEqual(json.load(f)["charts"], {})

    def test_refuses_what_it_cant_keep(self):
        cases = [((DECK, 4, "T", "u"), "--slide must be from 1 to 3"),
                 ((DECK, 1, " ", "u"), "must not be empty"),
                 ((DECK, 1, "---", "u"), "--title must hold letters or digits")]
        for args, expected in cases:
            with self.subTest(expected), self.assertRaisesRegex(SystemExit, expected):
                save_example.save(*args)
        self.assertFalse(os.path.exists(
            os.path.join(self.folder, "_examples")))


if __name__ == "__main__":
    unittest.main()
