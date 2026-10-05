"""Renders a Mermaid diagram, such as the architecture map, to SVG in the
skill's output folder (see the agentic-manager-utils-lib skill's
output_folder.py), so the document shows it the same way in every viewer, and
checks its connection lines.

    python3 output_diagram.py --name <folder name> --path <relative .svg path> [--theme dark] < diagram.mmd
    python3 output_diagram.py --check [--theme dark] [--png] < diagram.mmd

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

--check renders the diagram, a map or a sequence, without writing anything to
the output folder: it applies the line rules to a flowchart, and prints one
line of JSON with the rendered "width" and "height", and for a flowchart each
node's position, as "nodes": {id: [x, y]}, to check that a map's components
stay in place across stages. With --png it also writes
a PNG preview to the system temp folder and adds its "png" path, to inspect
the layout visually; the preview has Mermaid's own colours, not the dark
theme's restyling or the retirement crosses.

Otherwise prints one line of JSON: {"path": ..., "temporary": bool}. Fails with a message
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
# How much larger than the SVG the --png preview is drawn, so edge labels read.
PNG_SCALE = 2
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
            chord = math.hypot(*vector(current, end))
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
    # Mermaid emits its default edge rule before authored themeCSS/class rules.
    # Change that default in place: a late !important override masks linkStyle
    # colours and can leave a changed edge grey while its arrowhead stays red.
    # Keeping the rule's position and specificity preserves the CSS cascade.
    svg = re.sub(
        r'(' + re.escape(root) + r'\s+\.flowchart-link\s*\{[^}]*?\bstroke\s*:\s*)[^;}]+',
        lambda match: match.group(1) + DARK['line'], svg, count=1)
    rules = [f'{root} [data-color-id="{ident}"].cluster:not(.swimlane) rect'
             f'{{fill:{color} !important;fill-opacity:{DARK_TINT} !important;stroke:{color} !important;}}'
             for ident, color in CLUSTER_COLOR.findall(svg)]
    rules += [
        f"{root} .node rect,{root} .node polygon,{root} .node path,{root} .node circle"
        f"{{fill:{DARK['node']} !important;stroke:{DARK['node_border']} !important;}}",
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


def render(source, theme="default", png=None):
    """The SVG Mermaid draws from `source` in `theme`, and, given a `png`
    path, a PNG of it there too. Exits if Node.js is missing or the diagram
    doesn't render."""
    npx = shutil.which("npx")
    if not npx:
        raise NodeMissing()
    with tempfile.TemporaryDirectory() as folder:
        source_path = os.path.join(folder, "diagram.mmd")
        svg_path = os.path.join(folder, "diagram.svg")
        if png:
            mmdc(npx, source_path, png, theme, source)
        mmdc(npx, source_path, svg_path, theme, source)
        with open(svg_path, encoding="utf-8") as f:
            svg = f.read()
    return retirement_crosses(dark_style(svg) if theme == "dark" else svg)


def mmdc(npx, source_path, out_path, theme, source):
    """Runs the pinned Mermaid CLI on `source`, writing `out_path` (its
    extension sets the format; a PNG is drawn at PNG_SCALE, to read labels)."""
    with open(source_path, "w", encoding="utf-8") as f:
        f.write(source)
    scale = ["-s", str(PNG_SCALE)] if out_path.lower().endswith(".png") else []
    try:
        run = subprocess.run([npx, "-y", "-p", MERMAID_CLI, "mmdc", "-i", source_path,
                              "-o", out_path, "-b", THEMES[theme], *scale],
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


def is_flowchart(source):
    """Whether `source` is a flowchart (a map), past any init directive and
    comments."""
    for line in source.splitlines():
        line = line.strip()
        if line and not line.startswith("%%"):
            return line.split()[0] in ("flowchart", "graph")
    return False


def svg_size(svg):
    """(width, height) from the SVG's viewBox, or (None, None)."""
    found = re.search(r'viewBox="[-\d.]+ [-\d.]+ ([\d.]+) ([\d.]+)"', svg)
    return (float(found.group(1)), float(found.group(2))) if found else (None, None)


NODE = re.compile(r'<g\b[^>]*\bclass="node\b[^"]*"[^>]*>')


def node_positions(svg):
    """{node id: [x, y]} of a flowchart's nodes, from their translate()."""
    positions = {}
    for tag in NODE.findall(svg):
        found_id = re.search(r'\bid="(?:[^"]*-)?flowchart-(.+)-\d+"', tag)
        found_at = re.search(r'translate\(\s*([-\d.]+)[ ,]+([-\d.]+)\s*\)', tag)
        if found_id and found_at:
            positions[found_id.group(1)] = [float(found_at.group(1)), float(found_at.group(2))]
    return positions


def check_diagram(source, theme="default", png=False):
    """{width, height[, png]} of `source` rendered, without writing to any
    output folder; exits if it doesn't render or a flowchart breaks the line
    rules."""
    try:
        text = source.decode("utf-8")
    except UnicodeDecodeError:
        raise SystemExit("the diagram is not UTF-8 text")
    if not text.strip():
        raise SystemExit("the diagram is empty")
    preview = os.path.join(tempfile.mkdtemp(prefix="diagram-"), "preview.png") if png else None
    svg = render(text, theme, preview)
    if is_flowchart(text):
        problems = line_problems(svg)
        if problems:
            raise SystemExit("the diagram's lines break the rules:\n  - " + "\n  - ".join(problems[:20]))
    width, height = svg_size(svg)
    result = {"width": width, "height": height}
    if is_flowchart(text):
        result["nodes"] = node_positions(svg)
    return {**result, **({"png": preview} if preview else {})}


def retirement_crosses(svg):
    """Cross rectangular Mermaid nodes classed `decommissioned`, without
    changing geometry. Insert behind the label so names remain readable.
    This visual marker does not determine whether retirement is confirmed.
    """
    node_rect = re.compile(
        r'(<g\b[^>]*class="[^"]*\bnode\b[^"]*"[^>]*>\s*<rect\b[^>]*>)')

    def mark(match):
        tag = match.group(1)
        classes = re.search(r'class="([^"]*)"', tag).group(1).split()
        if "decommissioned" not in classes:
            return tag
        rect = tag[tag.index("<rect"):]
        values = {}
        for name in ("x", "y", "width", "height"):
            found = re.search(rf'\b{name}="([^"]+)"', rect)
            try:
                values[name] = float(found.group(1)) if found else 0
            except ValueError:
                return tag
        x, y, w, h = (values[n] for n in ("x", "y", "width", "height"))
        if not all(math.isfinite(v) for v in (x, y, w, h)) or min(w, h) <= 12:
            return tag
        x1, y1, x2, y2 = x + 5, y + 5, x + w - 5, y + h - 5
        cross = (f'<path class="retirement-cross" '
                 f'd="M{x1:g},{y1:g}L{x2:g},{y2:g}M{x1:g},{y2:g}L{x2:g},{y1:g}" '
                 'style="fill:none!important;stroke:#b8b8b8!important;'
                 'stroke-width:4px!important;stroke-opacity:0.65;pointer-events:none"/>')
        return tag + cross

    return node_rect.sub(mark, svg)


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
    parser.add_argument("--name", type=folder_name,
                        help="the skill's own folder, such as tech-investigations")
    parser.add_argument("--path",
                        help="where the .svg goes inside that folder")
    parser.add_argument("--theme", choices=sorted(THEMES), default="default",
                        help="default (on white) or dark (on a dark background)")
    parser.add_argument("--check", action="store_true",
                        help="only render and check the diagram, and print its size; write nothing")
    parser.add_argument("--png", action="store_true",
                        help="with --check, also write a PNG preview to the system temp folder")
    args = parser.parse_args(argv)
    if not args.check and not (args.name and args.path):
        parser.error("--name and --path are required, unless --check")
    if args.png and not args.check:
        parser.error("--png goes with --check")
    return args


def main():
    args = parse_args()
    try:
        if args.check:
            print(json.dumps(check_diagram(sys.stdin.buffer.read(), args.theme, args.png)))
            return
        path, temporary = write_output_diagram(
            args.name, args.path, sys.stdin.buffer.read(), args.theme)
    except NodeMissing:
        print(NodeMissing.MESSAGE, file=sys.stderr)
        raise
    print(json.dumps({"path": path, "temporary": temporary}))


if __name__ == "__main__":
    main()
