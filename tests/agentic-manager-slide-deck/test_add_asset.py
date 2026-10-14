"""Unit tests for skills/agentic-manager-slide-deck/scripts/add_asset.py.
Run with: python3 tests/run.py agentic-manager-slide-deck

The config's path is patched to the test's own config, in a temporary folder.
"""

import os
import sys
import tempfile
import unittest

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(TEST_DIR))
sys.path.insert(0, os.path.join(REPO_ROOT, "skills",
                os.path.basename(TEST_DIR), "scripts"))
import add_asset  # noqa: E402
sys.path.insert(0, TEST_DIR)
from deck_fixture import temp_output  # noqa: E402


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

    def test_copies_an_image_then_replaces_it_by_name(self):
        path = self.image("Acme Logo (2026).SVG")
        result = add_asset.add_asset(path)
        destination = os.path.join(
            self.folder, "_assets", "acme-logo-2026.svg")
        self.assertEqual(result, {"asset": "acme-logo-2026.svg", "path": destination,
                                  "replaced": False})
        newer = self.image("logo.svg", "<svg>2</svg>")
        self.assertTrue(add_asset.add_asset(
            newer, "acme-logo-2026.svg")["replaced"])
        with open(destination, encoding="utf-8") as f:
            self.assertEqual(f.read(), "<svg>2</svg>")

    def test_refuses_what_isnt_an_image_file(self):
        cases = [(os.path.join(self.source, "missing.png"), None, "is not a file"),
                 (self.image("notes.txt"), None,
                  "must be lowercase words joined by hyphens, then .png"),
                 (self.image("logo.svg"), "../logo.svg", "must be lowercase words")]
        for path, name, expected in cases:
            with self.subTest(expected), self.assertRaisesRegex(SystemExit, expected):
                add_asset.add_asset(path, name)
        self.assertFalse(os.path.exists(os.path.join(self.folder, "_assets")))


if __name__ == "__main__":
    unittest.main()
