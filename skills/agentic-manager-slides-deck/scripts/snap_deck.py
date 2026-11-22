"""Takes a picture of each slide of a deck with headless Chrome, so the agent
can see what the user will see before handing it over, and lists the text
laid out where no one can read it.

Only a browser can lay out a page, so overflowing text, overlaps and a font
that renders other than intended are invisible to check_deck.py; Chrome, run
headless, is the one browser the skill relies on. The deck is never changed:
each slide is shot from a copy of its page, the pictures laid out in one sheet,
and the text measured on another copy, since a small fault hides in a sheet.
"""
import argparse
import html
import json
import math
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from check_deck import read_page
from common import FOLDER_NAME, SLIDE_HEIGHT, SLIDE_WIDTH, clear_folder, deck_dir, deck_file, gather, work_folder

# Where Chrome is installed by default on macOS and Windows; on Linux, and
# anywhere it is on the PATH, it is found by name.
CHROME_PATHS = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
]
CHROME_NAMES = ["google-chrome", "google-chrome-stable", "chrome"]
# The sheet: slides in columns, each a third of its size, numbered above it.
SHEET_COLUMNS = 3
THUMB_WIDTH = 360
THUMB_HEIGHT = round(THUMB_WIDTH * SLIDE_HEIGHT / SLIDE_WIDTH)
GAP, LABEL = 16, 22
# How long, in page time, scripts get to draw before the picture is taken, so
# charts, drawn by Chart.js loaded from the internet, are there when it is.
PAGE_TIME_MS = 5000
# The element the layout script writes its findings into, as JSON, for
# --dump-dom to carry back.
LAYOUT_OUTPUT = "layout-problems"
# Measures every slide's readable text, and reports only what is never meant:
# text over other text, spilling out of the box that holds it, or cut off by
# the slide's edge. Shapes overlapping, text over a shape or an image, and
# anything placed on purpose stay free: text whose element, or one between it
# and its box, is positioned or transformed was put there deliberately, so it
# isn't measured against that box; decorative text (faint, under half opacity;
# an outline with no fill; or marked aria-hidden='true') is left out. A line
# overlaps another, or leaves its box or the slide, only by more than SLACK
# pixels and, across lines, by more than a quarter of the shorter line's
# height, the spare space a tight line height leaves above and below letters.
LAYOUT_SCRIPT = r"""
<script>
function measureLayout() {
  const SLACK = 3;
  const clear = c => c === 'transparent' || /rgba\(.*,\s*0\)$/.test(c);
  const chain = el => { const all = []; for (let e = el; e && e.nodeType === 1; e = e.parentElement) all.push(e); return all; };
  function decorative(el) {
    const up = chain(el);
    if (up.some(e => e.getAttribute('aria-hidden') === 'true')) return true;
    if (up.reduce((o, e) => o * parseFloat(getComputedStyle(e).opacity), 1) < 0.5) return true;
    const s = getComputedStyle(el);
    const clipped = up.some(e => { const c = getComputedStyle(e); return c.backgroundClip === 'text' || c.webkitBackgroundClip === 'text'; });
    return clear(s.webkitTextFillColor || s.color) && !clipped;
  }
  const blockOf = el => chain(el).find(e => !getComputedStyle(e).display.startsWith('inline')) || el;
  const placed = e => { const s = getComputedStyle(e); return s.position === 'absolute' || s.position === 'fixed' || s.transform !== 'none'; };
  function drawsBox(e) {
    const s = getComputedStyle(e);
    const edge = ['Top', 'Right', 'Bottom', 'Left'].some(k => parseFloat(s['border' + k + 'Width']) > 0 && s['border' + k + 'Style'] !== 'none' && !clear(s['border' + k + 'Color']));
    return edge || !clear(s.backgroundColor) || s.backgroundImage !== 'none';
  }
  // The box the text sits in, or null when something between was placed on purpose.
  function boxOf(el, slide) {
    for (let e = el; e && e !== slide; e = e.parentElement) {
      if (drawsBox(e)) return e;
      if (placed(e)) return null;
    }
    return null;
  }
  const snippet = el => { const t = el.textContent.replace(/\s+/g, ' ').trim(); return t.length > 40 ? t.slice(0, 40) + '…' : t; };
  const out = [];
  document.querySelectorAll('.slides-wrapper > .slide').forEach((slide, index) => {
    const number = index + 1, edge = slide.getBoundingClientRect(), lines = [], cut = new Set(), spilt = new Set();
    const once = (seen, block, text) => { if (!seen.has(block)) { seen.add(block); out.push(`slide ${number}: ${text}`); } };
    const walker = document.createTreeWalker(slide, NodeFilter.SHOW_TEXT);
    for (let node = walker.nextNode(); node; node = walker.nextNode()) {
      const el = node.parentElement;
      if (!node.textContent.trim() || decorative(el)) continue;
      const range = document.createRange();
      range.selectNodeContents(node);
      const block = blockOf(el), box = boxOf(el, slide);
      for (const r of range.getClientRects()) {
        if (r.width < 1 || r.height < 1) continue;
        lines.push({ r, block });
        const by = (a, b) => a - b > Math.max(SLACK, r.height / 4);
        if (by(edge.left, r.left) || by(r.right, edge.right) || by(edge.top, r.top) || by(r.bottom, edge.bottom))
          once(cut, block, `'${snippet(block)}' is cut off by the slide's edge`);
        else if (box) {
          const b = box.getBoundingClientRect();
          const past = Math.max(b.left - r.left, r.right - b.right, b.top - r.top, r.bottom - b.bottom);
          if (past > Math.max(SLACK, r.height / 4))
            once(spilt, block, `'${snippet(block)}' spills ${Math.round(past)}px out of its box`);
        }
      }
    }
    const ids = new Map(), met = new Set();
    const id = block => { if (!ids.has(block)) ids.set(block, ids.size); return ids.get(block); };
    for (let i = 0; i < lines.length; i++) for (let j = i + 1; j < lines.length; j++) {
      const a = lines[i], b = lines[j];
      if (a.block === b.block || a.block.contains(b.block) || b.block.contains(a.block)) continue;
      const x = Math.min(a.r.right, b.r.right) - Math.max(a.r.left, b.r.left);
      const y = Math.min(a.r.bottom, b.r.bottom) - Math.max(a.r.top, b.r.top);
      const pair = [id(a.block), id(b.block)].sort().join();
      if (x > SLACK && y > Math.max(SLACK, Math.min(a.r.height, b.r.height) / 4) && !met.has(pair)) {
        met.add(pair);
        out.push(`slide ${number}: '${snippet(a.block)}' overlaps '${snippet(b.block)}'`);
      }
    }
  });
  const pre = document.createElement('pre');
  pre.id = '%s';
  pre.textContent = JSON.stringify(out);
  document.body.appendChild(pre);
}
window.addEventListener('load', () => document.fonts.ready.then(measureLayout));
</script>
""".replace("%s", LAYOUT_OUTPUT)


def snap(deck):
    """(sheet, pictures, layout): the sheet of the deck `deck` and the picture
    of every slide, in order, in the deck's working folder, replaced on every
    run, and the layout problems layout_problems() finds; exits if Chrome
    isn't installed or a picture fails."""
    chrome = find_chrome()
    if not chrome:
        raise SystemExit(
            "Chrome isn't installed, so the slides can't be pictured: skip the slide check")
    folder = deck_dir(deck)
    # The slides are counted as the check reads them, so a slide's own
    # markup can't add one.
    reader, page = read_page(os.path.join(folder, deck_file(deck)))
    count = reader.slides
    out = work_folder(FOLDER_NAME, deck, "pictures")
    clear_folder(out)
    os.makedirs(out)

    def shoot(name, text, size=(SLIDE_WIDTH, SLIDE_HEIGHT)):
        source, picture = os.path.join(
            out, f"{name}.html"), os.path.join(out, f"{name}.png")
        run = run_chrome(chrome, source, text, size,
                         f"--screenshot={picture}", f"picture {name}")
        if not os.path.isfile(picture):
            raise SystemExit(
                f"Chrome made no picture of {name}: {run.stderr.strip()[-300:]}")
        return picture

    # Each copy is shot in its own Chrome, with its own throwaway profile, so
    # they can run in parallel.
    pictures = gather(range(1, count + 1),
                      lambda number: shoot(f"slide-{number}", one_slide_page(page, folder, number)), workers=4)
    text, size = sheet_page([os.path.basename(picture)
                            for picture in pictures])
    return shoot("sheet", text, size), pictures, layout_problems(chrome, page, folder, out)


def layout_problems(chrome, page, folder, out):
    """The layout problems Chrome finds in the deck's page `page`, from the
    deck's folder `folder`, as "slide <n>: <what>": readable text over other
    text, out of its box or cut off by the slide's edge. The page's copy is
    written to `out` and deleted after."""
    run = run_chrome(chrome, os.path.join(out, "layout.html"), layout_page(page, folder),
                     (SLIDE_WIDTH, SLIDE_HEIGHT), "--dump-dom", "measure the slides")
    return read_layout(run.stdout)


def run_chrome(chrome, source, text, size, output, task):
    """Chrome's finished run on the page `text`, written to the file `source`
    for it and deleted after, at the window size `size`, with `output` the
    flag that says what it gives back; exits if it takes over 60 seconds on
    the `task`, such as "picture slide-2"."""
    with open(source, "w", encoding="utf-8") as f:
        f.write(text)
    try:
        with tempfile.TemporaryDirectory(prefix="chrome-profile-") as profile:
            return subprocess.run(chrome_command(chrome, profile, source, size, output),
                                  capture_output=True, text=True, timeout=60)
    except subprocess.TimeoutExpired:
        raise SystemExit(
            f"Chrome took over 60 seconds to {task}: skip the slide check")
    finally:
        os.remove(source)


def read_layout(dom):
    """The problems the layout script wrote into the page Chrome dumped as
    `dom`; exits if it wrote none, since the measure then never ran."""
    found = re.search(f'<pre id="{LAYOUT_OUTPUT}">(.*?)</pre>', dom, re.S)
    if not found:
        raise SystemExit(
            "Chrome didn't measure the slides: look at the pictures instead")
    return json.loads(html.unescape(found[1]))


def find_chrome():
    """The path of Chrome's executable, or None if it isn't installed."""
    for path in CHROME_PATHS:
        if os.path.isfile(path):
            return path
    for name in CHROME_NAMES:
        found = shutil.which(name)
        if found:
            return found
    return None


def sheet_page(pictures):
    """A page laying out the slide pictures `pictures` (file names beside it),
    numbered, at a third of their size, and its (width, height)."""
    rows = math.ceil(len(pictures) / SHEET_COLUMNS)
    width = SHEET_COLUMNS * THUMB_WIDTH + (SHEET_COLUMNS + 1) * GAP
    height = rows * (LABEL + THUMB_HEIGHT + GAP) + GAP
    cells = "".join(f'<figure><figcaption>{number}</figcaption><img src="{html.escape(name)}"></figure>'
                    for number, name in enumerate(pictures, 1))
    page = ("<!doctype html><html><head><meta charset='utf-8'><style>"
            f"body {{ margin: 0; padding: {GAP}px; background: #8b929c; font: 700 15px sans-serif; color: #fff; }}"
            f" main {{ display: grid; grid-template-columns: repeat({SHEET_COLUMNS}, {THUMB_WIDTH}px); gap: {GAP}px; }}"
            f" figure {{ margin: 0; }} figcaption {{ height: {LABEL}px; }}"
            f" img {{ display: block; width: {THUMB_WIDTH}px; height: {THUMB_HEIGHT}px; }}"
            f"</style></head><body><main>{cells}</main></body></html>")
    return page, (width, height)


def chrome_command(chrome, profile, page, size, output):
    """The command that loads the page file `page` at the window size `size`,
    with the throwaway profile folder `profile`, and once its scripts have run
    gives back what the flag `output` asks: --screenshot=<png> a picture,
    --dump-dom the page as it then is."""
    return [chrome, "--headless", f"--user-data-dir={profile}", "--no-first-run", "--hide-scrollbars",
            "--force-device-scale-factor=1", f"--window-size={size[0]},{size[1]}",
            f"--virtual-time-budget={PAGE_TIME_MS}", output, Path(page).as_uri()]


def layout_page(page, folder):
    """The deck's page `page`, from the deck's folder `folder`, with every
    slide at its real size and the script that measures the text of each."""
    shown = page_copy(page, folder, ".toolbar { display: none !important; }")
    return shown.replace("</body>", LAYOUT_SCRIPT + "</body>", 1)


def one_slide_page(page, folder, number):
    """The deck's page `page`, from the deck's folder `folder`, showing only
    slide `number` (1 for the first), at its real size from the window's
    corner."""
    return page_copy(page, folder, "body { padding: 0 !important; background: none !important; }"
                     " .toolbar { display: none !important; }"
                     " .slide { margin: 0 !important; box-shadow: none !important; }"
                     f" .slides-wrapper > .slide:not(:nth-child({number})) {{ display: none !important; }}")


def page_copy(page, folder, css):
    """The deck's page `page` to load from elsewhere: its links resolved from
    the deck's folder `folder`, so its images in _assets still load, and the
    CSS `css` laid over its own."""
    base = Path(folder).as_uri() + "/"
    return page.replace("<head>", f'<head>\n    <base href="{base}">\n    <style>{css}</style>', 1)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Picture each slide of the deck with headless Chrome. Prints one line of JSON: the "
        "`sheet`, every slide numbered at a third of its size, then `slides`, the picture of each slide in "
        "order, all in the deck's working folder in the system temp folder, replaced on every run, then "
        "`layout`, the text no one can read as laid out: over other text, spilling out of its box or cut off "
        "by the slide's edge, each as 'slide <n>: <what>'. Decorative text (faint, an outline with no fill, or "
        "marked aria-hidden='true') and anything placed by position or transform are left free. Exits 1 if "
        "Chrome makes no picture or measure, saying to skip the check when it isn't installed or takes over "
        "60 seconds on either.")
    parser.add_argument("--deck", required=True,
                        help="the deck's folder, <Name>_<YY-MM-DD>, inside slides-decks")
    sheet, pictures, layout = snap(parser.parse_args(argv).deck)
    print(json.dumps({"sheet": sheet, "slides": pictures, "layout": layout}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
