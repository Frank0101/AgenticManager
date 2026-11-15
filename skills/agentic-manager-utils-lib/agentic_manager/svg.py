"""Helpers for charts drawn as SVG by hand, shared by every skill: the frame, text, its estimated width, an axis's step, a legend and a ring's or pie's segment.

Skills have no install step, so a chart is plain SVG text, with no plotting
library. Every chart shares one font and palette, so charts from different
skills read as one family. Text width is estimated from per-character widths
after Helvetica and Arial, close enough to size a label column or decide
whether a label fits.
"""
import html
import math

FONT = "-apple-system, 'Segoe UI', Helvetica, Arial, sans-serif"
SURFACE = "#fcfcfb"
INK = "#1a1a1a"
MUTED = "#6b6b6b"
GRID = "#e8e7e4"
# Character widths in em; anything else counts as a lower-case letter.
CHAR_WIDTHS = {**dict.fromkeys("ijl|", 0.23), **dict.fromkeys(" ftI.,:;'!/", 0.28),
               **dict.fromkeys("r()-", 0.34), **dict.fromkeys("cksvxyz", 0.5),
               **dict.fromkeys("FTZ", 0.61), **dict.fromkeys("ABEKPSVXY", 0.67),
               **dict.fromkeys("CDHNRUw", 0.72), **dict.fromkeys("GOQ", 0.78),
               **dict.fromkeys("mM", 0.84), "%": 0.89, "W": 0.95, "→": 1.0}


def svg(width, height, body):
    """An SVG document of `width` by `height` on the shared surface, holding
    the elements of `body`, each a line."""
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width:.0f}" height="{height:.0f}" '
            f'viewBox="0 0 {width:.0f} {height:.0f}" font-family="{FONT}">\n'
            f'<rect width="100%" height="100%" fill="{SURFACE}"/>\n' + "\n".join(body) + "\n</svg>\n")


def legend(entries, left, right, top, size=11, line_length=30):
    """(elements, bottom): a chart's legend of `entries`, each (label,
    colour, line), its mark a box of the colour when `line` is None, else a
    line `line_length` long, `line` being its (width, dash pattern or None
    for a solid line), laid out in rows from (`left`, `top`) that wrap before
    `right`, and the y below its last row."""
    elements, x, y = [], left, top
    for label, colour, line in entries:
        mark = line_length if line else size - 1
        width = mark + size // 2 + text_width(label, size) + size + 3
        if x + width > right and x > left:
            x, y = left, y + size + 5
        if line:
            stroke, dash = line
            pattern = f' stroke-dasharray="{dash}"' if dash else ""
            middle = y + (size - 1) / 2
            elements.append(f'<line x1="{x:.1f}" y1="{middle:.1f}" x2="{x + mark:.1f}" y2="{middle:.1f}" '
                            f'stroke="{colour}" stroke-width="{stroke}" stroke-linecap="round"{pattern}/>')
        else:
            elements.append(
                f'<rect x="{x:.1f}" y="{y:.1f}" width="{mark}" height="{mark}" fill="{colour}"/>')
        elements.append(text(x + mark + size // 2, y +
                        size - 2, label, size=size))
        x += width
    return elements, y + size + 7


def text(x, y, content, size=12, color=INK, anchor="start", bold=False, extra=""):
    """A text element at (`x`, `y`) holding `content`, escaped; `extra` adds
    attributes as written."""
    weight = ' font-weight="bold"' if bold else ""
    return (f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" fill="{color}" '
            f'text-anchor="{anchor}"{weight}{extra}>{esc(content)}</text>')


def esc(content):
    """`content` as text safe inside an SVG element or attribute."""
    return html.escape(str(content), quote=True)


def text_width(content, size, bold=False):
    """The estimated rendered width of `content` at font `size`."""
    return sum(CHAR_WIDTHS.get(c, 0.56) for c in str(content)) * size * (1.08 if bold else 1)


def nice_step(span):
    """A round step for an axis covering `span`, so it has at most eight
    steps."""
    for step in (1, 2, 5, 10, 20, 25, 50, 100, 200, 250, 500, 1000):
        if span / step <= 8:
            return step
    return 1000 * (int(span / 8000) + 1)


def arc_segment(cx, cy, outer, inner, start, end):
    """The SVG path of one segment of a ring centred on (`cx`, `cy`), from
    `start` to `end` degrees clockwise from 12 o'clock, between the radii
    `inner` and `outer`; with `inner` 0, a pie's slice."""
    def point(radius, degrees):
        angle = math.radians(degrees - 90)
        return coordinate(cx + radius * math.cos(angle)), coordinate(cy + radius * math.sin(angle))
    (ox1, oy1), (ox2, oy2) = point(outer, start), point(outer, end)
    (ix2, iy2), (ix1, iy1) = point(inner, end), point(inner, start)
    large = 1 if end - start > 180 else 0
    R, r = coordinate(outer), coordinate(inner)
    return (f"M{ox1},{oy1} A{R},{R},0,{large},1,{ox2},{oy2} "
            f"L{ix2},{iy2} A{r},{r},0,{large},0,{ix1},{iy1} Z")


def coordinate(value):
    """A coordinate for SVG: at most 2 decimals, no trailing zeros."""
    text = f"{value:.2f}".rstrip("0").rstrip(".")
    return "0" if text == "-0" else text
