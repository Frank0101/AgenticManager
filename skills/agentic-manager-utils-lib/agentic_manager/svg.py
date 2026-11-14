"""Helpers for charts drawn as SVG by hand, shared by every skill: the frame, text, its estimated width and an axis's step.

Skills have no install step, so a chart is plain SVG text, with no plotting
library. Every chart shares one font and palette, so charts from different
skills read as one family. Text width is estimated from per-character widths
after Helvetica and Arial, close enough to size a label column or decide
whether a label fits.
"""
import html

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
