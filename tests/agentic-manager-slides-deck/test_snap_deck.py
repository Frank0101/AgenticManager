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
import finish_deck  # noqa: E402
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
        finish_deck.finish(DECK)
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
            "chrome", "/p", "/out/slide-1.html", (common.SLIDE_WIDTH, common.SLIDE_HEIGHT), "--screenshot=/out/slide-1.png")
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
                                           page, (200, 100), f"--screenshot={picture}")
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
        finish_deck.finish(DECK)
        sheet, pictures, layout = snap_deck.snap(DECK)
        self.assertEqual(layout, [])
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


# Each case is one slide: what it holds, and the problems it must report, by
# the start of their text. The problems are the faults found in real decks;
# the free cases are overlaps a design makes on purpose.
ABS = "position:absolute; left:57px;"
CARD = "border:1px solid #888; padding:10px; width:300px;"
LAYOUT_CASES = [
    ("a label under the title it sits on",
     f"<div style='{ABS} top:120px; font-size:14px'>FIELD MANUAL FM-ENG 1</div>"
     f"<h1 style='{ABS} top:110px; margin:0; font-size:60px'>SIMPLE, SECURE</h1>",
     ["'FIELD MANUAL FM-ENG 1' overlaps 'SIMPLE, SECURE'"]),
    ("a title wrapping onto the text below it",
     f"<h2 style='{ABS} top:40px; width:500px; margin:0; font-size:36px; line-height:1'>The platform: cloud native, standard, repeatable</h2>"
     f"<p style='{ABS} top:84px; margin:0'>The platform is the ecosystem we build</p>",
     ["'The platform: cloud native, standard"]),
    ("a note laid over a card's text",
     f"<div style='{ABS} top:100px; {CARD}'><p>Reference architecture and design review once mature</p></div>"
     f"<div style='{ABS} top:128px; width:600px; background:#334'>More details are in the governance process</div>",
     ["'Reference architecture and design review"]),
    ("text spilling out of a card of fixed height",
     f"<div style='{ABS} top:100px; height:18px; {CARD}'><p style='margin:0'>Simplicity is our overriding desire to avoid unnecessary complexity: clean code, refactor as we go</p></div>",
     ["'Simplicity is our overriding desire to a"]),
    ("text cut off by the slide's right edge",
     "<p style='position:absolute; left:1000px; top:100px; white-space:nowrap'>Owned by all of us, every day</p>",
     ["'Owned by all of us, every day' is cut off by the slide's edge"]),
    ("gradient text still counts",
     f"<div style='{ABS} top:100px; font-size:30px'>Plain words here</div>"
     f"<div style='{ABS} top:104px; font-size:30px; background:linear-gradient(90deg, red, blue); -webkit-background-clip:text; background-clip:text; color:transparent'>Gradient words</div>",
     ["'Plain words here' overlaps 'Gradient words'"]),
    ("free: an outlined ghost word behind the title",
     "<div style='position:absolute; right:-14px; top:-34px; font-size:150px; color:transparent; -webkit-text-stroke:1.5px #888'>SECURE</div>"
     f"<h2 style='{ABS} top:40px; margin:0; font-size:34px'>Reinforcing trust in every interaction</h2>"
     "<p style='position:absolute; right:60px; top:40px'>2026&ndash;2028</p>", []),
    ("free: a faint watermark behind the text",
     f"<div style='{ABS} top:80px; font-size:120px; opacity:0.2'>DRAFT</div><p style='{ABS} top:120px'>Real content over it</p>", []),
    ("free: decorative text marked aria-hidden",
     f"<div aria-hidden='true' style='{ABS} top:80px; font-size:120px'>01</div><p style='{ABS} top:120px'>Real content over it</p>", []),
    ("free: a badge placed over a card's corner",
     f"<div style='{ABS} top:100px; {CARD}'><span style='position:absolute; right:-20px; top:-12px; background:gold'>NEW</span><p>Card text</p></div>", []),
    ("free: a stamp rotated across its box",
     f"<div style='{ABS} top:100px; {CARD}'><div style='transform:rotate(-8deg) translateX(40px); white-space:nowrap'>SECTION III, rotated across</div></div>", []),
    ("free: text laid over a shape and an image",
     "<div style='position:absolute; left:100px; top:100px; width:300px; height:200px; background:#246'></div>"
     "<svg style='position:absolute; left:100px; top:100px' width='300' height='200'><circle cx='150' cy='100' r='90' fill='#a33'/></svg>"
     "<p style='position:absolute; left:130px; top:180px; margin:0; color:#fff'>Caption over the picture</p>", []),
    ("free: a title in two tight lines",
     f"<h1 style='{ABS} top:150px; margin:0; font-size:70px; line-height:0.9'>HOW WE<br>ENGINEER</h1>", []),
    ("free: tightly stacked blocks and wrapping chips",
     f"<div style='{ABS} top:100px; width:260px'><h3 style='margin:0; font-size:20px; line-height:1'>Heading</h3><p style='margin:0; line-height:1.1'>Text right under it</p>"
     "<div style='display:flex; flex-wrap:wrap; gap:4px'>" + "".join(f"<span style='border:1px solid #999; padding:1px 6px'>chip {n}</span>" for n in range(12)) + "</div></div>", []),
]


@unittest.skipUnless(snap_deck.find_chrome(), "Chrome isn't installed")
class LayoutTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        reason = chrome_cannot_picture()
        if reason:
            raise unittest.SkipTest(
                f"{reason}: it can't run headless on this machine")

    def test_reports_only_text_no_one_can_read(self):
        slides = "".join(
            f"<div class='slide'>{html}</div>" for _, html, _ in LAYOUT_CASES)
        page = ("<html><head><style>.slide { position: relative; width: 1100px; height: 618px; overflow: hidden;"
                " font: 16px sans-serif; }</style></head><body><div class='slides-wrapper'>"
                f"{slides}</div></body></html>")
        with tempfile.TemporaryDirectory() as folder:
            found = snap_deck.layout_problems(
                snap_deck.find_chrome(), page, folder, folder)
        for number, (name, _, expected) in enumerate(LAYOUT_CASES, 1):
            with self.subTest(name):
                prefix = f"slide {number}: "
                problems = [p[len(prefix):]
                            for p in found if p.startswith(prefix)]
                self.assertEqual(len(problems), len(expected), problems)
                for problem, start in zip(problems, expected):
                    self.assertTrue(problem.startswith(
                        start), f"{problem!r} doesn't start with {start!r}")

    def test_a_page_the_script_never_measured_fails(self):
        with self.assertRaisesRegex(SystemExit, "look at the pictures instead"):
            snap_deck.read_layout("<html><body></body></html>")


if __name__ == "__main__":
    unittest.main()
