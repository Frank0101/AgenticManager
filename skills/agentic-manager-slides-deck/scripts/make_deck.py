"""Writes the deck's <Name>_Slides.html from <deck>/slides.json, once its
`problems` finds none.

The page around the slides is fixed, and this module owns it: the slide's
size, the grey page behind the slides, the toolbar with zoom and PDF export,
the print rules that put one slide on each PDF page, and the scripts that zoom
and draw the charts. slides.json holds only what needs judgment: the title,
the deck's own CSS, each slide's HTML and the data of its charts and rings,
which `problems` checks field by field.
"""
import html
import json
import re
from html.parser import HTMLParser

from common import (CHART_JS, ELEMENT_ID, FOLDER_NAME, PAGE, SLIDE_HEIGHT, SLIDE_WIDTH, TOKEN, URL_ATTRIBUTES, VOID,
                    arc_segment, asset_link, coordinate, credit_line, deck_file, is_number, link_kind,
                    placed_images, write_output_file)

FIELDS = {"title", "style", "slides", "charts", "rings"}
SLIDE_FIELDS = {"html", "class"}
CHART_FIELDS = {"type", "data", "options", "format"}
FORMAT_FIELDS = {"prefix", "suffix", "decimals"}
RING_FIELDS = {"size", "outer", "inner", "gap", "start", "segments"}
SEGMENT_FIELDS = {"color", "value"}
CHART_TYPES = ("bar", "line", "pie", "doughnut",
               "radar", "polarArea", "bubble", "scatter")
CLASS_NAMES = re.compile(r"-?[A-Za-z_][\w-]*(?: -?[A-Za-z_][\w-]*)*")

# Elements a slide can't hold: they load code or styles, or belong to the page.
FORBIDDEN = {"script", "style", "link", "meta", "base", "iframe", "object", "embed", "frame", "frameset",
             "html", "head", "body", "title"}
# CSS that loads a file: a url() to anything but inline data or a fragment of
# the page, such as an SVG gradient, or an @import. An image goes in an <img>,
# whose link the check sees and the credits list, never in a CSS background.
CSS_URL = re.compile(r"""url\(\s*['"]?\s*([^'")\s]*)""", re.I)
IMAGE_IN_IMG = "an image goes in <img src='{{asset:<name>}}'>"
# An image token as the whole value of an attribute that links an image: the
# one place the page's links, and so the check, can see it.
PLACED_ASSET = re.compile(
    rf"""\b(?:{"|".join(URL_ATTRIBUTES)})\s*=\s*(["'])\{{\{{asset:[^{{}}]*\}}\}}\1""", re.I)


BASE_CSS = f"""      * {{
        box-sizing: border-box;
        margin: 0;
        padding: 0;
      }}

      body {{
        background: #e8e8e8;
        font-family:
          system-ui,
          -apple-system,
          sans-serif;
        padding: 40px 20px;
      }}

      .slide {{
        background: #fff;
        position: relative;
        width: {SLIDE_WIDTH}px;
        height: {SLIDE_HEIGHT}px;
        margin: 0 auto 40px;
        padding: 48px 56px;
        box-shadow: 0 2px 16px rgba(0, 0, 0, 0.12);
        overflow: hidden;
      }}

      .asset-credit {{
        position: absolute;
        right: 14px;
        bottom: 8px;
        max-width: 60%;
        font-size: 10px;
        line-height: 1.3;
        text-align: right;
        color: #6b7280;
      }}

      .chart {{
        position: relative;
        width: 100%;
        height: 100%;
      }}

      .toolbar {{
        position: fixed;
        left: 12px;
        top: 50%;
        transform: translateY(-50%);
        display: flex;
        flex-direction: column;
        gap: 6px;
        background: #fff;
        border: 1px solid #ddd;
        border-radius: 8px;
        padding: 8px 6px;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
        z-index: 100;
      }}
      .toolbar button {{
        width: 32px;
        height: 32px;
        border: none;
        background: none;
        border-radius: 6px;
        font-size: 1rem;
        cursor: pointer;
        color: #444;
        display: flex;
        align-items: center;
        justify-content: center;
        transition: background 0.15s;
      }}
      .toolbar button:hover {{
        background: #f0f0f0;
      }}
      .toolbar .divider {{
        height: 1px;
        background: #eee;
        margin: 2px 0;
      }}

      @media print {{
        @page {{
          size: {SLIDE_WIDTH}px {SLIDE_HEIGHT}px;
          margin: 0;
        }}
        * {{
          -webkit-print-color-adjust: exact;
          print-color-adjust: exact;
        }}
        html,
        body {{
          margin: 0;
          padding: 0;
          background: white;
        }}
        .toolbar {{
          display: none;
        }}
        .slides-wrapper {{
          transform: none !important;
        }}
        .slide {{
          width: {SLIDE_WIDTH}px;
          height: {SLIDE_HEIGHT}px;
          page-break-after: always;
          break-after: page;
          box-shadow: none;
          margin: 0 !important;
          overflow: hidden;
        }}
      }}"""

TOOLBAR = """    <div class="toolbar">
      <button onclick="zoom(1)" title="Zoom in">+</button>
      <button onclick="zoom(-1)" title="Zoom out">−</button>
      <div class="divider"></div>
      <button onclick="window.print()" title="Export PDF">⎙</button>
    </div>"""

ZOOM_SCRIPT = """    <script>
      let scale = 1;
      function zoom(dir) {
        scale = Math.min(2, Math.max(0.4, scale + dir * 0.1));
        const w = document.querySelector(".slides-wrapper");
        w.style.transform = `scale(${scale})`;
        w.style.transformOrigin = "top center";
      }
    </script>"""

# Charts are drawn without animation, so a PDF never catches one half drawn.
# Their settings are data, never code: how values read ("£3.5m") is a
# `format`, which the page's script turns into the label functions Chart.js
# needs.
CHART_SCRIPT = """    <script src="{src}"></script>
    <script>
      Chart.defaults.animation = false;
      Chart.defaults.maintainAspectRatio = false;
      const charts = {charts};
      // A chart's format: its values, on the value axis and in tooltips, as
      // prefix + number + suffix, with a fixed number of decimals if set.
      const formatted = (format, value) => (format.prefix || "") + Number(value).toLocaleString(undefined,
        format.decimals === undefined ? {{}} : {{ minimumFractionDigits: format.decimals,
          maximumFractionDigits: format.decimals }}) + (format.suffix || "");
      for (const [id, {{ format, ...config }}] of Object.entries(charts)) {{
        if (format) {{
          const options = (config.options ??= {{}});
          const axis = ["radar", "polarArea"].includes(config.type) ? "r"
            : options.indexAxis === "y" ? "x" : "y";
          const tooltip = ((options.plugins ??= {{}}).tooltip ??= {{}});
          (tooltip.callbacks ??= {{}}).label = (item) =>
            (item.dataset.label || item.label || "") + ": "
            + formatted(format, typeof item.parsed === "number" ? item.parsed : item.parsed[axis]);
          if (!["pie", "doughnut"].includes(config.type)) {{
            const scale = ((options.scales ??= {{}})[axis] ??= {{}});
            (scale.ticks ??= {{}}).callback = (value) => formatted(format, value);
          }}
        }}
        new Chart(document.getElementById("chart-" + id), config);
      }}
    </script>"""


def write_deck(deck, content, texts, image_credits):
    """Writes the deck `deck` from slides.json's `content`, whose slides' HTML
    `problems` returned as `texts`, crediting the downloaded images by
    `image_credits`; returns (path, temporary) as output_file.py does."""
    return write_output_file(FOLDER_NAME, f"{deck}/{deck_file(deck)}",
                             build(content, texts, image_credits).encode("utf-8"))


def problems(content, assets=frozenset()):
    """(errors, slides' HTML) of slides.json's content, `assets` being the
    images in _assets; errors name the field to fix."""
    errors, texts = [], []
    if not isinstance(content, dict):
        return ["slides.json: must be a JSON object"], texts
    unknown(content, FIELDS, "slides.json", errors)
    title = content.get("title")
    if not isinstance(title, str) or not title.strip() or "\n" in title:
        errors.append("title: must be one nonempty line")
    style = lines(content.get("style", []), "style", errors, required=False)
    if style and (css_loads_file(style) or re.search(r"</style", style, re.I)):
        errors.append(f"style: must not load files (a url() of a file, or @import), {IMAGE_IN_IMG}, "
                      "or close the style element")
    if style and TOKEN.search(style):
        errors.append(
            "style: holds a {{...}} token, which only a slide's html can")
    elements = {}
    for kind, check in (("chart", check_chart), ("ring", check_ring)):
        field = kind + "s"
        items = content.get(field, {})
        if not isinstance(items, dict):
            errors.append(f"{field}: must be an object of {kind}s by id")
            continue
        for ident, item in items.items():
            if not ELEMENT_ID.fullmatch(ident):
                errors.append(
                    f"{field}.{ident}: an id is lowercase words joined by hyphens, such as revenue-by-quarter")
            check(item, f"{field}.{ident}", errors)
            elements[(kind, ident)] = 0
    slides = content.get("slides")
    if not isinstance(slides, list) or not slides:
        errors.append("slides: must be a nonempty list")
        slides = []
    for number, slide in enumerate(slides):
        where = f"slides[{number}]"
        if not isinstance(slide, dict):
            errors.append(f"{where}: must be an object with `html`")
            continue
        unknown(slide, SLIDE_FIELDS, where, errors)
        classes = slide.get("class", "")
        if not isinstance(classes, str) or (classes and not CLASS_NAMES.fullmatch(classes)):
            errors.append(
                f"{where}.class: must be class names separated by spaces")
        text = lines(slide.get("html"), f"{where}.html", errors)
        if text is None:
            continue
        texts.append(text)
        for match in TOKEN.finditer(text):
            key = (match[1], match[2])
            if match[1] == "asset":
                if match[2] not in assets:
                    errors.append(f"{where}.html: {match[0]} names no image in _assets: add it with "
                                  "add_asset.py, which prints its name")
            elif key in elements:
                elements[key] += 1
            else:
                errors.append(
                    f"{where}.html: {match[0]} names no {match[1]} in `{match[1]}s`")
        for match in TOKEN.finditer(PLACED_ASSET.sub("", text)):
            if match[1] == "asset":
                errors.append(f"{where}.html: {match[0]} goes only in an image's link, as "
                              f"<img src='{match[0]}'>")
        bare = TOKEN.sub("", text).replace(PAGE, "")
        if "{{" in bare:
            errors.append(
                f"{where}.html: `{{{{` starts no token: write {{{{chart:<id>}}}}, {{{{ring:<id>}}}}, "
                "{{asset:<name>}} or {{page}}")
        problem = read_slide(bare)
        if problem:
            errors.append(f"{where}.html: {problem}")
    for (kind, ident), count in elements.items():
        if count != 1:
            errors.append(f"{kind}s.{ident}: must be placed exactly once, as {{{{{kind}:{ident}}}}} "
                          f"in a slide's html, not {count} times")
    return errors, texts


def css_loads_file(css):
    """Whether the CSS `css` loads a file, by @import or a url() of
    anything but inline data or a fragment of the page."""
    return bool(re.search("@import", css, re.I)) or any(
        not target.startswith("#") and link_kind(target) for target in CSS_URL.findall(css))


def unknown(item, allowed, where, errors):
    """Adds to `errors` the fields of `item`, at `where`, that aren't in `allowed`."""
    extra = sorted(set(item) - allowed)
    if extra:
        errors.append(f"{where}: unknown field(s) {', '.join(extra)} "
                      f"(allowed: {', '.join(sorted(allowed))})")


def lines(value, where, errors, required=True):
    """The text of a field written as a list of lines, or None."""
    if not isinstance(value, list) or not all(isinstance(line, str) for line in value):
        errors.append(f"{where}: must be a list of lines (strings)")
        return None
    text = "\n".join(value)
    if required and not text.strip():
        errors.append(f"{where}: is empty")
        return None
    return text


def check_chart(chart, where, errors):
    """Adds to `errors` the problems of the chart `chart`, at `where`."""
    if not isinstance(chart, dict):
        errors.append(f"{where}: must be an object")
        return
    unknown(chart, CHART_FIELDS, where, errors)
    if chart.get("type") not in CHART_TYPES:
        errors.append(f"{where}.type: must be one of {', '.join(CHART_TYPES)}")
    data = chart.get("data")
    datasets = data.get("datasets") if isinstance(data, dict) else None
    if not isinstance(data, dict) or not isinstance(data.get("labels", []), list):
        errors.append(
            f"{where}.data: must be an object with `labels` (a list) and `datasets`")
    elif (not isinstance(datasets, list) or not datasets
          or not all(isinstance(d, dict) and isinstance(d.get("data"), list) for d in datasets)):
        errors.append(
            f"{where}.data.datasets: must be a nonempty list of objects, each with a `data` list")
    if not isinstance(chart.get("options", {}), dict):
        errors.append(f"{where}.options: must be an object")
    form = chart.get("format", {})
    if not isinstance(form, dict):
        errors.append(f"{where}.format: must be an object, such as "
                      '{"prefix": "£", "suffix": "m", "decimals": 1}')
        return
    unknown(form, FORMAT_FIELDS, f"{where}.format", errors)
    for field in ("prefix", "suffix"):
        if not isinstance(form.get(field, ""), str) or "\n" in form.get(field, ""):
            errors.append(f"{where}.format.{field}: must be text on one line")
    decimals = form.get("decimals", 0)
    if not isinstance(decimals, int) or isinstance(decimals, bool) or not 0 <= decimals <= 6:
        errors.append(
            f"{where}.format.decimals: must be a whole number from 0 to 6")


def check_ring(ring, where, errors):
    """Adds to `errors` the problems of the ring `ring`, at `where`."""
    if not isinstance(ring, dict):
        errors.append(f"{where}: must be an object")
        return
    unknown(ring, RING_FIELDS, where, errors)
    size, outer, inner = ring.get("size"), ring.get(
        "outer"), ring.get("inner", 0)
    gap, start = ring.get("gap", 0), ring.get("start", 0)
    if not is_number(size) or size <= 0:
        errors.append(f"{where}.size: must be a number above 0")
    elif not is_number(outer) or not 0 < outer <= size / 2:
        errors.append(
            f"{where}.outer: must be a radius above 0 and at most size / 2")
    elif not is_number(inner) or not 0 <= inner < outer:
        errors.append(
            f"{where}.inner: must be a radius from 0 (a pie) to below outer")
    if not is_number(gap) or gap < 0:
        errors.append(f"{where}.gap: must be degrees, 0 or more")
    if not is_number(start):
        errors.append(f"{where}.start: must be degrees")
    segments = ring.get("segments")
    if not isinstance(segments, list) or len(segments) < 2:
        errors.append(f"{where}.segments: must list at least 2 segments")
        return
    for number, segment in enumerate(segments):
        here = f"{where}.segments[{number}]"
        if not isinstance(segment, dict):
            errors.append(f"{here}: must be an object")
            continue
        unknown(segment, SEGMENT_FIELDS, here, errors)
        color = segment.get("color")
        if not isinstance(color, str) or not color.strip() or re.search(r"[\"'<>;]", color):
            errors.append(
                f"{here}.color: must be a CSS colour, such as #3e9c8f")
        value = segment.get("value", 1)
        if not is_number(value) or value <= 0:
            errors.append(f"{here}.value: must be a number above 0")
    values = [s.get("value", 1) for s in segments if isinstance(s, dict)]
    if is_number(gap) and all(is_number(v) and v > 0 for v in values) and len(values) == len(segments):
        narrowest = 360 * min(values) / sum(values)
        if narrowest <= gap:
            errors.append(f"{where}.gap: {gap}° leaves nothing of the narrowest segment, "
                          f"{narrowest:g}° wide")


def read_slide(text):
    """The first problem with one slide's HTML, or None. Every tag it opens
    must close, since one unclosed tag would swallow every slide after it."""
    parser = SlideParser()
    parser.feed(text)
    parser.finish()
    return parser.problem


class SlideParser(HTMLParser):
    """Reads one slide's HTML: the first problem with it."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.open, self.problem = [], None

    def fail(self, message):
        if not self.problem:
            self.problem = f"line {self.getpos()[0]}: {message}"

    def handle_starttag(self, tag, attrs):
        self.read_tag(tag, attrs)
        if tag not in VOID:
            self.open.append((tag, self.getpos()[0]))

    def handle_startendtag(self, tag, attrs):
        # A self-closed tag, such as SVG's <path />.
        self.read_tag(tag, attrs)

    def read_tag(self, tag, attrs):
        if tag in FORBIDDEN:
            self.fail(f"<{tag}> isn't allowed in a slide: put CSS in `style`, and charts and rings "
                      "in their own fields")
        # An image from a path or a URL would show only on one machine or
        # online: it is {{asset:<name>}}, linked to the file in _assets. A
        # diagram is inline SVG in the deck's own look, never Mermaid, whose
        # look a deck can't match and which would load another library.
        for name, value in attrs:
            kind = link_kind(value) if name in URL_ATTRIBUTES else None
            value = (value or "").strip()
            if kind == "remote":
                self.fail(f"<{tag} {name}> loads a remote file, which an offline deck can't show: "
                          "add the image with add_asset.py and write {{asset:<name>}}, or use an "
                          "[IMAGE: ...] placeholder or inline SVG")
            elif kind == "file":
                self.fail(f"<{tag} {name}> loads {value!r}: add the image with add_asset.py "
                          "and write {{asset:<name>}}")
            elif name == "style" and css_loads_file(value):
                self.fail(f"<{tag} style> loads a file: {IMAGE_IN_IMG}")
            elif name == "class" and "mermaid" in value.split():
                self.fail(
                    f"<{tag} class='mermaid'>: draw a diagram as inline SVG, in the deck's look")

    def handle_endtag(self, tag):
        if tag in VOID:
            return
        if not self.open or self.open[-1][0] != tag:
            expected = (f"<{self.open[-1][0]}> opened on line {self.open[-1][1]} is still open"
                        if self.open else "nothing is open")
            self.fail(f"</{tag}> closes nothing: {expected}")
            return
        self.open.pop()

    def finish(self):
        self.close()
        if self.open and not self.problem:
            tag, line = self.open[-1]
            self.problem = f"<{tag}> opened on line {line} is never closed"


def build(content, texts, image_credits, depth=1):
    """The deck's HTML page from valid content and the slides' HTML problems()
    returned for it, crediting each downloaded image in `image_credits` on
    every slide that shows it, for a page `depth` folders below the skill's
    output folder (1 for a deck, 2 for a kept example)."""
    charts, rings = content.get("charts", {}), content.get("rings", {})
    style = "\n".join(content.get("style", []))
    slides = []
    for number, (slide, text) in enumerate(zip(content["slides"], texts), 1):
        classes = " ".join(["slide"] + slide.get("class", "").split())
        body = TOKEN.sub(lambda match: place(match, rings, depth),
                         text.replace(PAGE, str(number)))
        # Credited here, on every slide that shows the image, so none can drop it.
        shown = [name for name in placed_images(text) if name in image_credits]
        if shown:
            line = "; ".join(credit_line(
                image_credits[name]) for name in shown)
            body += f'\n<p class="asset-credit">{html.escape(line)}</p>'
        slides.append(f'      <div class="{classes}">\n{body}\n      </div>')
    scripts = [ZOOM_SCRIPT]
    if charts:
        data = json.dumps(charts, ensure_ascii=False).replace("<", "\\u003c")
        scripts.append(CHART_SCRIPT.format(src=CHART_JS, charts=data))
    return f"""<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>{html.escape(content["title"].strip())}</title>
    <style>
{BASE_CSS}

      /* ── presentation-specific styles below ── */
{style}
    </style>
  </head>
  <body>
{TOOLBAR}

    <div class="slides-wrapper">
{chr(10).join(slides)}
    </div>

{chr(10).join(scripts)}
  </body>
</html>
"""


def place(match, rings, depth):
    """The HTML that a token's `match` stands for: a chart's canvas, a
    ring's SVG from `rings`, or an image linked `depth` folders up."""
    kind, ident = match[1], match[2]
    if kind == "chart":
        return f'<div class="chart"><canvas id="chart-{ident}"></canvas></div>'
    if kind == "asset":
        return html.escape(asset_link(ident, depth))
    return ring_svg(ident, rings[ident])


def ring_svg(ident, ring):
    """The ring as inline SVG, drawn here since its geometry is arithmetic: each
    segment's share of the circle is its value's share of the total, less the
    gap, the first starting at `start`."""
    size, gap = ring["size"], ring.get("gap", 0)
    values = [segment.get("value", 1) for segment in ring["segments"]]
    centre, cursor, paths = size / 2, ring.get("start", 0), []
    for segment, value in zip(ring["segments"], values):
        span = 360 * value / sum(values)
        path = arc_segment(centre, centre, ring["outer"], ring.get("inner", 0),
                           cursor + gap / 2, cursor + span - gap / 2)
        paths.append(
            f'<path d="{path}" fill="{html.escape(segment["color"].strip())}"/>')
        cursor += span
    side = coordinate(size)
    return (f'<svg class="ring" id="ring-{ident}" viewBox="0 0 {side} {side}" width="{side}" '
            f'height="{side}">{"".join(paths)}</svg>')
