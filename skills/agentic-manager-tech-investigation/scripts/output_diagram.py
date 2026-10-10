"""Renders a Mermaid diagram, such as a sequence, with the Mermaid CLI, so it is
known to draw and shows the same way in every viewer. make_report.py uses its
functions; run as a script, it tries one diagram:

    python3 output_diagram.py [--png] < diagram.mmd

The diagram is read from standard input as UTF-8 and rendered with the Mermaid
CLI, pinned to MERMAID_CLI, through npx, so it needs Node.js 22.13+. It prints one
line of JSON with the rendered "width" and "height" and writes nothing to the
output folder. With --png it also writes a PNG preview to the system temp folder
and adds its "png" path, to inspect the layout visually.

Fails with a message on stderr and exit 1 if Node.js (npx) isn't available or the
diagram doesn't render. Node.js is required, not optional: there is no unchecked
fallback, because a diagram nobody has rendered can't be known to draw.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

# The Mermaid CLI the diagrams are checked against.
MERMAID_CLI = "@mermaid-js/mermaid-cli@12.0.0"
RENDER_TIMEOUT = 300
# How much larger than the SVG the --png preview is drawn, so labels read.
PNG_SCALE = 2


def find_npx():
    """The npx that runs the Mermaid CLI, or an exit asking for Node.js: the
    diagrams are drawn and checked only through it, so without it there is
    nothing to continue with."""
    npx = shutil.which("npx")
    if not npx:
        raise SystemExit("Node.js 22.13 or newer is needed to draw and check the diagrams: "
                         "install it, then run this again")
    return npx


def mmdc(npx, source_path, out_path, source):
    """Runs the pinned Mermaid CLI on `source`, writing `out_path` (its
    extension sets the format; a PNG is drawn at PNG_SCALE, to read labels)."""
    with open(source_path, "w", encoding="utf-8") as f:
        f.write(source)
    scale = ["-s", str(PNG_SCALE)] if out_path.lower().endswith(".png") else []
    try:
        run = subprocess.run([npx, "-y", "-p", MERMAID_CLI, "mmdc", "-i", source_path,
                              "-o", out_path, "-b", "white", *scale],
                             capture_output=True, text=True, timeout=RENDER_TIMEOUT)
    except subprocess.TimeoutExpired:
        raise SystemExit(
            f"the Mermaid CLI took more than {RENDER_TIMEOUT}s")
    if run.returncode != 0 or not os.path.exists(out_path):
        detail = (run.stderr or run.stdout).strip().splitlines()
        detail = [
            line for line in detail if not line.lstrip().startswith("at ")][:12]
        raise SystemExit(
            "the diagram doesn't render: " + " / ".join(detail))


def render(source, png=None):
    """The SVG Mermaid draws from `source`, and, given a `png` path, a PNG of it
    there too. Exits if Node.js is missing or the diagram doesn't render."""
    npx = find_npx()
    with tempfile.TemporaryDirectory() as folder:
        source_path = os.path.join(folder, "diagram.mmd")
        svg_path = os.path.join(folder, "diagram.svg")
        if png:
            mmdc(npx, source_path, png, source)
        mmdc(npx, source_path, svg_path, source)
        with open(svg_path, encoding="utf-8") as f:
            return f.read()


def render_many(sources):
    """[SVG] of each source in `sources`, rendered in one Mermaid CLI run (a
    Markdown file of their blocks), which saves starting a browser per
    diagram. If the batch fails, each is rendered alone, so the error names
    the diagram that doesn't render: SystemExit's message starts with its
    index, "diagram <n>: ..."."""
    if not sources:
        return []
    npx = find_npx()
    with tempfile.TemporaryDirectory() as folder:
        source_path = os.path.join(folder, "diagrams.md")
        out_path = os.path.join(folder, "out.md")
        blocks = "\n".join(
            f"```mermaid\n{source.rstrip()}\n```\n" for source in sources)
        try:
            mmdc(npx, source_path, out_path, blocks)
            svgs = []
            for number in range(1, len(sources) + 1):
                with open(os.path.join(folder, f"out-{number}.svg"), encoding="utf-8") as f:
                    svgs.append(f.read())
        except (SystemExit, OSError):
            svgs = None
    if svgs is None:
        svgs = []
        for number, source in enumerate(sources, 1):
            try:
                svgs.append(render(source))
            except SystemExit as error:
                raise SystemExit(f"diagram {number}: {error}")
    return svgs


def svg_size(svg):
    """(width, height) from the SVG's viewBox, or (None, None)."""
    found = re.search(r'viewBox="[-\d.]+ [-\d.]+ ([\d.]+) ([\d.]+)"', svg)
    return (float(found.group(1)), float(found.group(2))) if found else (None, None)


def check_diagram(source, png=False):
    """{width, height[, png]} of `source` rendered, without writing to any
    output folder; exits if it doesn't render."""
    try:
        text = source.decode("utf-8")
    except UnicodeDecodeError:
        raise SystemExit("the diagram is not UTF-8 text")
    if not text.strip():
        raise SystemExit("the diagram is empty")
    preview = os.path.join(tempfile.mkdtemp(
        prefix="diagram-"), "preview.png") if png else None
    width, height = svg_size(render(text, preview))
    return {"width": width, "height": height, **({"png": preview} if preview else {})}


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Render a Mermaid diagram from standard input, check it and print its size.")
    parser.add_argument("--png", action="store_true",
                        help="also write a PNG preview to the system temp folder")
    return parser.parse_args(argv)


def main():
    args = parse_args()
    print(json.dumps(check_diagram(sys.stdin.buffer.read(), args.png)))


if __name__ == "__main__":
    main()
