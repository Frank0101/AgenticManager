"""Unit tests for skills/agentic-manager-slides-deck/scripts/snap_deck.py, and,
where Chrome is installed and can take a picture headless, a run that pictures
a real deck. Chrome that hangs, such as one whose sign-in a company policy
forces, is found by picturing a blank page first, so the run is skipped with
the reason rather than failing after snap_deck.py's own wait.
Run with: python3 tests/run.py agentic-manager-slides-deck
"""

import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(TEST_DIR))
sys.path.insert(0, os.path.join(REPO_ROOT, "skills",
                os.path.basename(TEST_DIR), "scripts"))
import common  # noqa: E402
import make_deck  # noqa: E402
import snap_deck  # noqa: E402
sys.path.insert(0, TEST_DIR)
from deck_fixture import DECK, content, temp_output, write_slides  # noqa: E402

MAC = snap_deck.CHROME_PATHS[0]
# How long Chrome has to picture a blank page before the real run is skipped.
PROBE_SECONDS = 5


class FindChromeTest(unittest.TestCase):
    def test_finds_chrome_at_its_install_path_or_by_name(self):
        cases = [
            ("installed in its default place", {MAC}, {}, MAC),
            ("on the PATH", set(), {
             "google-chrome": "/usr/bin/google-chrome"}, "/usr/bin/google-chrome"),
            ("missing", set(), {}, None),
        ]
        for name, files, on_path, found in cases:
            with self.subTest(name), \
                    mock.patch.object(snap_deck.os.path, "isfile", lambda p: p in files), \
                    mock.patch.object(snap_deck.shutil, "which", on_path.get):
                self.assertEqual(snap_deck.find_chrome(), found)

    def test_without_chrome_it_says_to_skip_the_check(self):
        with mock.patch.object(snap_deck, "find_chrome", return_value=None), \
                self.assertRaisesRegex(SystemExit, "skip the slide check"):
            snap_deck.snap(DECK)

    def test_a_chrome_that_hangs_says_to_skip_the_check(self):
        write_slides(temp_output(self), content())
        make_deck.make_deck(DECK)
        hang = subprocess.TimeoutExpired("chrome", 60)
        with mock.patch.object(snap_deck, "find_chrome", return_value="/chrome"), \
                mock.patch.object(snap_deck.subprocess, "run", side_effect=hang), \
                self.assertRaisesRegex(SystemExit, "Chrome took over 60 seconds .* skip the slide check"):
            snap_deck.snap(DECK)


class OneSlidePageTest(unittest.TestCase):
    def test_shows_one_slide_with_links_from_the_decks_folder(self):
        page = "<html><head><title>T</title></head><body></body></html>"
        shown = snap_deck.one_slide_page(
            page, "/decks/Acme-Q3-Review_26-10-05", 2)
        self.assertIn(
            '<base href="file:///decks/Acme-Q3-Review_26-10-05/">', shown)
        self.assertIn(".slides-wrapper > .slide:not(:nth-child(2))", shown)
        self.assertLess(shown.index("<base"), shown.index("<title>"))

    def test_chrome_shoots_the_page_at_the_slides_size(self):
        command = snap_deck.chrome_command(
            "chrome", "/p", "/out/slide-1.png", "/out/slide-1.html")
        self.assertEqual(command[0], "chrome")
        for part in ("--headless", "--user-data-dir=/p", "--screenshot=/out/slide-1.png",
                     f"--window-size={common.SLIDE_WIDTH},{common.SLIDE_HEIGHT}", "file:///out/slide-1.html"):
            with self.subTest(part):
                self.assertIn(part, command)


class SheetPageTest(unittest.TestCase):
    def test_lays_out_the_slides_numbered_in_columns(self):
        page, size = snap_deck.sheet_page(
            [f"slide-{n}.png" for n in range(1, 5)])
        self.assertEqual(re.findall(r'<figcaption>(\d+)</figcaption><img src="(.*?)">', page),
                         [(str(n), f"slide-{n}.png") for n in range(1, 5)])
        rows = 2  # four slides in three columns
        self.assertEqual(size, (snap_deck.SHEET_COLUMNS * snap_deck.THUMB_WIDTH + 4 * snap_deck.GAP,
                                rows * (snap_deck.LABEL +
                                        snap_deck.THUMB_HEIGHT + snap_deck.GAP)
                                + snap_deck.GAP))


def chrome_cannot_picture():
    """Why Chrome can't picture a blank page on this machine, or None when it can."""
    with tempfile.TemporaryDirectory() as folder:
        page, picture = Path(folder) / "blank.html", Path(folder) / "blank.png"
        page.write_text("<html><body>blank</body></html>", encoding="utf-8")
        command = snap_deck.chrome_command(snap_deck.find_chrome(), Path(folder) / "profile",
                                           picture, page, (200, 100))
        try:
            subprocess.run(command, capture_output=True, timeout=PROBE_SECONDS)
        except subprocess.TimeoutExpired:
            return f"Chrome took over {PROBE_SECONDS} seconds to picture a blank page"
        if not picture.exists():
            return "Chrome made no picture of a blank page"
    return None


@unittest.skipUnless(snap_deck.find_chrome(), "Chrome isn't installed")
class SnapTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        reason = chrome_cannot_picture()
        if reason:
            raise unittest.SkipTest(
                f"{reason}: it can't run headless on this machine")

    def test_pictures_every_slide_at_its_size_and_the_sheet(self):
        folder = temp_output(self)
        write_slides(folder, content())
        make_deck.make_deck(DECK)
        sheet, pictures = snap_deck.snap(DECK)
        self.addCleanup(shutil.rmtree, os.path.dirname(sheet))
        self.assertEqual([Path(p).name for p in pictures],
                         ["slide-1.png", "slide-2.png", "slide-3.png"])
        _, sheet_size = snap_deck.sheet_page(pictures)
        for picture, size in [(p, (common.SLIDE_WIDTH, common.SLIDE_HEIGHT)) for p in pictures] + \
                [(sheet, sheet_size)]:
            with self.subTest(picture), open(picture, "rb") as f:
                header = f.read(24)
                self.assertEqual(header[:8], b"\x89PNG\r\n\x1a\n")
                self.assertEqual(struct.unpack(">II", header[16:24]), size)
        self.assertEqual(sorted(os.listdir(os.path.dirname(sheet))),
                         ["sheet.png", "slide-1.png", "slide-2.png", "slide-3.png"])


if __name__ == "__main__":
    unittest.main()
