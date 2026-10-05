"""Renders a Mermaid diagram, such as the architecture map, to SVG in the
skill's output folder (see the agentic-manager-utils-lib skill's
output_folder.py), so the document shows it the same way in every viewer, and
checks its connection lines.

    python3 output_diagram.py --name <folder name> --path <relative .svg path> [--theme dark] < diagram.mmd

--name and --path are as for the library's output_file.py; the path must end
in .svg. The diagram is read from standard input as UTF-8 and rendered with the
Mermaid CLI, pinned to MERMAID_CLI, through npx, so it needs Node.js 22.13+. Mermaid's
default look gives each subgraph its own colour. --theme "default" keeps it on
white; "dark" draws it on a dark background, with each subgraph tinted in its
own colour and the nodes, text and lines restyled to suit (see dark_style()).

Every connection line must keep to these rules, or nothing is written:
straight segments only horizontal, vertical or at 45 degrees, and every change
of direction a short rounded corner whose two legs are at those angles too.
Mermaid draws lines that pass with the "rounded" curve and line hops drawn as
gaps, not arcs:
`%%{init: {"flowchart": {"curve": "rounded"}, "elk": {"lineHops": "gap"}}}%%`.

Prints one line of JSON: {"path": ..., "temporary": bool}. Fails with a message
on stderr: exit 3 if Node.js (npx) isn't available, so the caller can fall back
to the Mermaid source; exit 1 if the diagram doesn't render, breaks the line
rules, or the path or config is wrong.
"""
import argparse
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile

# The agentic-manager-utils-lib skill, installed next to this one.
LIB_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)),
                       "..", "..", "agentic-manager-utils-lib")
sys.path.insert(0, LIB_DIR)
from agentic_manager.output_file import target, write_output_file  # noqa: E402
from agentic_manager.output_folder import folder_name, output_folder  # noqa: E402

# The Mermaid CLI the rules were checked against; it knows the "rounded" curve.
MERMAID_CLI = "@mermaid-js/mermaid-cli@12.0.0"
RENDER_TIMEOUT = 300
# {theme: the background the rendered diagram is drawn on}.
THEMES = {"default": "white", "dark": "#1e1e1e"}
# The dark theme's colours, and how strongly a subgraph is tinted with its own.
DARK = {"text": "#e4e4e7", "node": "#27272a", "node_border": "#71717a",
        "line": "#a1a1aa", "label": "#3f3f46"}
DARK_TINT = 0.14
# Mermaid's rule for a subgraph's colour: its id and its border colour.
CLUSTER_COLOR = re.compile(
    r'\[data-color-id="(color-\d+)"\]\.cluster:not\(\.swimlane\) rect\{stroke:(#[0-9A-Fa-f]{3,8});')

# Directions a line may take, in degrees from horizontal, and how far off counts.
ANGLES = (0, 45, 90)
TOLERANCE = 1.0
# Ignore slivers shorter than this: rounding leaves them at the ends of lines.
MIN_SEGMENT = 0.5
# The longest chord of a rounded corner; anything longer is a curved line.
MAX_CORNER = 20.0

PATH = re.compile(r"<path\b[^>]*>")
TOKEN = re.compile(r"[A-Za-z]|-?\d*\.?\d+(?:[eE][-+]?\d+)?")


class NodeMissing(SystemExit):
    """Node.js (npx) isn't available. Exits with code 3, so a caller can fall
    back to the Mermaid source."""
    MESSAGE = "Node.js (npx) is not available, so the diagram can't be rendered"

    def __init__(self):
        super().__init__(3)


def angle(start, end):
    """The direction from start to end, in degrees from horizontal (0-90)."""
    return math.degrees(math.atan2(abs(end[1] - start[1]), abs(end[0] - start[0])))


def allowed(start, end):
    if math.hypot(end[0] - start[0], end[1] - start[1]) < MIN_SEGMENT:
        return True
    return min(abs(angle(start, end) - a) for a in ANGLES) <= TOLERANCE


def path_problems(d):
    """What breaks the line rules in one SVG path's `d`, as messages."""
    tokens = TOKEN.findall(d)
    if not tokens or re.sub(TOKEN, "", d).strip(" ,\t\r\n"):
        return ["has an empty or invalid path"]
    problems, current, command, i, direction = [], None, None, 0, None

    def turn(first, second):
        lengths = math.hypot(*first) * math.hypot(*second)
        if not lengths:
            return 0
        cosine = sum(a * b for a, b in zip(first, second)) / lengths
        return math.degrees(math.acos(max(-1, min(1, cosine))))

    def vector(start, end):
        return end[0] - start[0], end[1] - start[1]

    while i < len(tokens):
        if tokens[i].isalpha():
            command = tokens[i]
            i += 1
            if command.upper() not in "MLQ":
                problems.append(
                    f"uses the {command} command, which draws a curve")
                return problems
            if i == len(tokens):
                return problems + ["has an incomplete path command"]
        if command not in ("M", "L", "Q"):
            problems.append("uses relative coordinates")
            return problems
        count = 4 if command == "Q" else 2
        if i + count > len(tokens) or any(t.isalpha() for t in tokens[i:i + count]):
            return problems + ["has an incomplete path command"]
        if current is None and command != "M":
            return problems + ["does not start with a move"]
        if command in ("M", "L"):
            point = (float(tokens[i]), float(tokens[i + 1]))
            i += 2
            if command == "L":
                segment = vector(current, point)
                if not allowed(current, point):
                    problems.append(
                        f"has a straight segment at {angle(current, point):.0f}°")
                if math.hypot(*segment) >= MIN_SEGMENT:
                    if direction and turn(direction, segment) > TOLERANCE:
                        problems.append("has an unrounded change of direction")
                    direction = segment
            else:
                direction = None
                # Additional pairs after M are implicit L commands in SVG.
                command = "L"
            current = point
        else:
            control = (float(tokens[i]), float(tokens[i + 1]))
            end = (float(tokens[i + 2]), float(tokens[i + 3]))
            i += 4
            chord = math.hypot(end[0] - current[0], end[1] - current[1])
            if chord > MAX_CORNER:
                problems.append(f"has a {chord:.0f}px curve, not a corner")
            elif not (allowed(current, control) and allowed(control, end)):
                problems.append(
                    "has a corner at an angle other than 90° or 45°")
            incoming, outgoing = vector(current, control), vector(control, end)
            if min(abs(turn(incoming, outgoing) - a) for a in (45, 90)) > TOLERANCE:
                problems.append("has a corner whose turn is not 90° or 45°")
            if direction and turn(direction, incoming) > TOLERANCE:
                problems.append(
                    "has an unrounded change of direction before a corner")
            direction = outgoing
            current = end
    return problems


def line_problems(svg):
    """Every connection line in a rendered Mermaid SVG that breaks the rules,
    as messages. Connection lines are the paths of class flowchart-link."""
    problems = []
    for number, tag in enumerate((t for t in PATH.findall(svg) if "flowchart-link" in t), 1):
        match = re.search(r'\sd="([^"]*)"', tag)
        ident = re.search(r'\sid="([^"]*)"', tag)
        name = ident.group(1) if ident else f"connection {number}"
        problems += [f"{name} {p}" for p in path_problems(
            match.group(1) if match else "")]
    return problems


def dark_style(svg):
    """The SVG restyled for a dark background: each subgraph filled with its
    own border colour, see-through, and nodes, text, lines and their labels
    in DARK. Only styles change, so the layout and its lines stay as checked."""
    found = re.search(r'<svg[^>]*\sid="([^"]+)"', svg)
    if not found or "</style>" not in svg:
        return svg
    root = "#" + found.group(1)
    rules = [f'{root} [data-color-id="{ident}"].cluster:not(.swimlane) rect'
             f'{{fill:{color} !important;fill-opacity:{DARK_TINT} !important;stroke:{color} !important;}}'
             for ident, color in CLUSTER_COLOR.findall(svg)]
    rules += [
        f"{root} .node rect,{root} .node polygon,{root} .node path,{root} .node circle"
        f"{{fill:{DARK['node']} !important;stroke:{DARK['node_border']} !important;}}",
        f"{root} .flowchart-link{{stroke:{DARK['line']} !important;}}",
        f"{root} .marker,{root} .arrowheadPath"
        f"{{fill:{DARK['line']} !important;stroke:{DARK['line']} !important;}}",
        f"{root} .edgeLabel,{root} .edgeLabel p,{root} .labelBkg"
        f"{{background-color:{DARK['label']} !important;}}",
        f"{root} .edgeLabel rect{{fill:{DARK['label']} !important;opacity:1 !important;}}",
        f"{root} span,{root} p,{root} .label{{color:{DARK['text']} !important;}}",
        f"{root} text{{fill:{DARK['text']} !important;}}",
    ]
    end = svg.index("</style>")
    return svg[:end] + "".join(rules) + svg[end:]


def render(source, theme="default"):
    """The SVG Mermaid draws from `source` in `theme`. Exits if Node.js is
    missing or the diagram doesn't render."""
    npx = shutil.which("npx")
    if not npx:
        raise NodeMissing()
    with tempfile.TemporaryDirectory() as folder:
        source_path = os.path.join(folder, "diagram.mmd")
        svg_path = os.path.join(folder, "diagram.svg")
        with open(source_path, "w", encoding="utf-8") as f:
            f.write(source)
        try:
            run = subprocess.run([npx, "-y", "-p", MERMAID_CLI, "mmdc", "-i", source_path,
                                  "-o", svg_path, "-b", THEMES[theme]],
                                 capture_output=True, text=True, timeout=RENDER_TIMEOUT)
        except subprocess.TimeoutExpired:
            raise SystemExit(
                f"the Mermaid CLI took more than {RENDER_TIMEOUT}s")
        if run.returncode != 0 or not os.path.exists(svg_path):
            detail = (run.stderr or run.stdout).strip().splitlines()
            detail = [
                line for line in detail if not line.lstrip().startswith("at ")][:12]
            raise SystemExit(
                "the diagram doesn't render: " + " / ".join(detail))
        with open(svg_path, encoding="utf-8") as f:
            svg = f.read()
    return dark_style(svg) if theme == "dark" else svg


def write_output_diagram(name, relative, source, theme="default"):
    """(path, temporary): renders `source` (bytes of Mermaid text), in
    `theme`, to the SVG `relative` inside the skill's output folder `name`,
    after checking its lines, and returns the file's absolute path and whether
    the folder is the temporary one."""
    if not relative.lower().endswith(".svg"):
        raise SystemExit(f"{relative!r} must end in .svg")
    try:
        text = source.decode("utf-8")
    except UnicodeDecodeError:
        raise SystemExit("the diagram is not UTF-8 text")
    if not text.strip():
        raise SystemExit("the diagram is empty")
    folder, _ = output_folder(name)
    target(folder, relative)
    svg = render(text, theme)
    problems = line_problems(svg)
    if problems:
        raise SystemExit("the diagram's lines break the rules, so nothing was written:\n  - "
                         + "\n  - ".join(problems[:20]))
    return write_output_file(name, relative, svg.encode("utf-8"))


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Render a Mermaid diagram from standard input to an SVG in a skill's output folder.")
    parser.add_argument("--name", type=folder_name, required=True,
                        help="the skill's own folder, such as tech-investigations")
    parser.add_argument("--path", required=True,
                        help="where the .svg goes inside that folder")
    parser.add_argument("--theme", choices=sorted(THEMES), default="default",
                        help="default (on white) or dark (on a dark background)")
    return parser.parse_args(argv)


def main():
    args = parse_args()
    try:
        path, temporary = write_output_diagram(
            args.name, args.path, sys.stdin.buffer.read(), args.theme)
    except NodeMissing:
        print(NodeMissing.MESSAGE, file=sys.stderr)
        raise
    print(json.dumps({"path": path, "temporary": temporary}))


if __name__ == "__main__":
    main()
