"""Tests for skills/agentic-manager-slide-deck/examples/: every example is
a description with the parts SKILL.md says it has and a wireframe drawn at the
slide's size, and the list init_deck.py prints holds every example once.
Run with: python3 tests/run.py agentic-manager-slide-deck

How a wireframe looks next to its original slide can't be tested: that was
checked by eye when it was drawn.
"""

import glob
import os
import re
import sys
import unittest
import xml.etree.ElementTree as ElementTree

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(TEST_DIR))
sys.path.insert(0, os.path.join(REPO_ROOT, "skills",
                os.path.basename(TEST_DIR), "scripts"))
import common  # noqa: E402
sys.path.insert(0, TEST_DIR)
from deck_fixture import temp_output  # noqa: E402

EXAMPLES = os.path.join(REPO_ROOT, "skills",
                        os.path.basename(TEST_DIR), "examples")
PARTS = ["**Use for:**", "**Layout.**", "**Style.**", "**Density.**"]


def examples():
    """Every example's folder name."""
    return sorted(os.path.basename(p) for p in glob.glob(os.path.join(EXAMPLES, "*"))
                  if os.path.isdir(p) and not os.path.basename(p).startswith("_"))


class ExamplesTest(unittest.TestCase):
    def test_every_example_has_its_parts_and_a_wireframe(self):
        self.assertTrue(examples())
        size = f"0 0 {common.SLIDE_WIDTH} {common.SLIDE_HEIGHT}"
        for name in examples():
            with self.subTest(name):
                folder = os.path.join(EXAMPLES, name)
                self.assertEqual(sorted(os.listdir(folder)), [
                                 common.EXAMPLE_DESCRIPTION, common.WIREFRAME])
                with open(os.path.join(folder, common.EXAMPLE_DESCRIPTION), encoding="utf-8") as f:
                    text = f.read()
                self.assertRegex(text, r"\A# \S")
                positions = [text.find(part) for part in PARTS]
                self.assertTrue(all(p > 0 for p in positions),
                                f"missing one of {PARTS}")
                self.assertEqual(positions, sorted(positions))
                self.assertTrue(text.rstrip().endswith(f"]({common.WIREFRAME})"),
                                "the wireframe ends the example")
                svg = ElementTree.parse(os.path.join(
                    folder, common.WIREFRAME)).getroot()
                self.assertEqual((svg.tag, svg.get("viewBox")),
                                 ("{http://www.w3.org/2000/svg}svg", size))

    def test_the_list_holds_every_example_with_what_it_is_for(self):
        temp_output(self)
        listed = common.examples()
        self.assertEqual([os.path.basename(e["folder"])
                         for e in listed], examples())
        self.assertEqual({e["source"] for e in listed}, {"built-in"})
        for example in listed:
            with self.subTest(example["folder"]):
                self.assertTrue(example["title"]
                                and example["use_for"], example)


if __name__ == "__main__":
    unittest.main()
