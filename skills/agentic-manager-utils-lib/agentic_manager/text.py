"""Helpers for Markdown text, shared by every skill: word counts, names, links, the document a link reaches, headings, fenced code, Markdown and HTML tables, charts in a page, the dates, numbers and plural words reports show, and the mark of what the AI wrote.

A word count counts words as a reader would, the same in every skill: a link
as its text, and only tokens with a letter or a digit ("don't" and "3.14" are
one each). A name from free text is a slug, or a NAME keeping a person's case,
numbered when taken. An anchor is GitHub's, so a checked link works where it is
read; fenced code is blanked first. Two links reach one document when they name
the same page in another form; a link is only compared so, never rewritten.
"""
from datetime import date
import re
import unicodedata
from pathlib import Path
from urllib.parse import parse_qsl, unquote, urlencode, urlsplit

# Marks a part of a document the AI wrote, on its heading or label, so a
# reader tells judgment from what was generated from data and checked.
AI_LABEL = "[AI Gen.]"
# The type of a report's table of many rows, small enough to scan it whole,
# the same in every skill.
SMALL_TYPE = "font-size:75%"

# A chart as chart_image() places it, so a check reads back what it wrote;
# group 1 is its path.
CHART_IMAGE = re.compile(
    r'<a href="([^"]+)" target="_blank"><img src="\1" width="100%" alt="[^"]*"></a>')

# Markdown links, defined once for every skill: (image mark, text, URL) of an
# inline link, (image mark, text, key) of a reference link, and (key, URL) of
# the definition line a reference uses, matched to the end of its line.
INLINE_LINK = re.compile(
    r'(!?)\[([^\]\n]*)\]\(\s*(<[^>\n]+>|[^\s)]+)(?:\s+"[^"\n]*")?\s*\)')
REFERENCE_LINK = re.compile(r"(!?)\[([^\]\n]+)\]\[([^\]\n]*)\]")
DEFINITION = re.compile(r"^ {0,3}\[([^\]\n]+)\]:\s*(<[^>]+>|\S+).*$", re.M)
# [text] alone, a link when a definition names it: not part of an inline,
# full reference or definition line.
SHORTCUT_LINK = re.compile(r"(?<![\]\\])(!?)\[([^\]\n]+)\](?![(\[:])")
# A name the agent gives: words of letters and digits joined by hyphens, such
# as Acme-Q3-Review; a SLUG is the same in lowercase, such as exec-summary.
NAME = re.compile(r"[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*")
SLUG = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
# A date as a report shows it, such as 05/03/2026.
DISPLAY_DATE = "%d/%m/%Y"
# A Notion page's ID, 32 hexadecimal digits, with or without dashes, in any of
# the URL forms Notion gives one page.
NOTION_PAGE = re.compile(
    r"([0-9a-f]{8}-?[0-9a-f]{4}-?[0-9a-f]{4}-?[0-9a-f]{4}-?[0-9a-f]{12})(?![0-9a-f])", re.I)
NOTION_HOST = re.compile(r"(^|\.)notion\.(so|site|com)$")
# A repository's folder path in GitHub's form, /owner/repo/tree/..., which
# names the same files as its /blob/ path.
TREE_PATH = re.compile(r"^(/[^/]+/[^/]+)/tree/")
# Query parameters that say how a page was reached, not which page it is.
TRACKING = re.compile(r"^(pvs|utm_\w+)$")
# A Markdown heading: its # marks and its title.
HEADING = re.compile(r"^ {0,3}(#{1,6})\s+(.+?)\s*#*\s*$", re.M)
# A line that opens or closes fenced code: its marker, three or more backticks
# or tildes, and what follows it, such as the language.
FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)", re.M)
# A pipe that separates table cells: one escaped as \| stays inside its cell,
# so a table cell's text, kept on one line, never splits its row.
CELL_PIPE = re.compile(r"(?<!\\)\|")
# A cell of a table's separator line: dashes, a colon at either end aligning
# the column.
SEPARATOR_CELL = re.compile(r":?-+:?")


def word_count(text):
    """The words of `text` as a reader counts them: links as their text, and
    only tokens that hold a letter or a digit."""
    return sum(1 for token in link_text(text).split() if re.search(r"[^\W_]", token))


def link_text(text):
    """`text` with every Markdown link, inline or by reference, as its text,
    and without the definition lines the references use."""
    return REFERENCE_LINK.sub(r"\2", INLINE_LINK.sub(r"\2", DEFINITION.sub(" ", text)))


def slug(text):
    """`text` as lowercase words joined by hyphens, such as cafe-menu for
    "Café Menu": as_name()'s, lowercase. Empty if it holds no letter or
    digit."""
    return as_name(text).lower()


def as_name(text):
    """`text` as a NAME, such as Jose-Nunez for "José Núñez": its letters
    and digits, accents dropped, words joined by hyphens, case kept. Empty
    if it holds neither."""
    plain = unicodedata.normalize("NFKD", text).encode(
        "ascii", "ignore").decode("ascii")
    return re.sub(r"[^A-Za-z0-9]+", "-", plain).strip("-")


def free_name(base, taken):
    """`base`, or the first numbered name after it for which `taken(name)` is
    false: base-2, base-3 and so on."""
    name, number = base, 1
    while taken(name):
        number += 1
        name = f"{base}-{number}"
    return name


def link_definitions(text):
    """{key in lower case: URL} of the link definitions in `text`, as links() resolves them."""
    return {key.casefold(): url.strip("<>") for key, url in DEFINITION.findall(text)}


def links(prose, definitions):
    """Yield (start, end, image, target) of each link in `prose`: inline, full
    and collapsed reference links, and shortcut links whose text a definition
    in `definitions` names; a reference nothing defines yields target None."""
    for match in INLINE_LINK.finditer(prose):
        yield match.start(), match.end(), bool(match[1]), match[3].strip("<>")
    for match in REFERENCE_LINK.finditer(prose):
        yield match.start(), match.end(), bool(match[1]), definitions.get(reference_key(match))
    for match in SHORTCUT_LINK.finditer(prose):
        if match[2].casefold() in definitions:
            yield match.start(), match.end(), bool(match[1]), definitions[match[2].casefold()]


def inline_links(text, definitions):
    """`text` with each reference link that `definitions` (as link_definitions()
    returns them) defines written inline; the others stay as they are."""
    def inline(match):
        url = definitions.get(reference_key(match))
        return f"{match[1]}[{match[2]}]({url})" if url else match[0]
    return REFERENCE_LINK.sub(inline, text)


def reference_key(match):
    """The key a REFERENCE_LINK match names, in lower case as link_definitions()
    stores it: its own, or its text for a collapsed reference, [text][]."""
    return (match[3] or match[2]).casefold()


def same_document(url):
    """What identifies the document `url` reaches, so two links to one
    document compare equal: a Notion page by its ID, whatever its URL form,
    the row opened in a database's side peek (?p=) included; otherwise the URL
    in lower-case scheme and host, without its #fragment, tracking parameters
    or a trailing slash, and a repository's tree path in GitHub's form,
    /owner/repo/tree/..., as the blob path it names."""
    parts = urlsplit(url.strip())
    host = parts.netloc.casefold().removeprefix("www.")
    if NOTION_HOST.search(host.split(":")[0]):
        peek = dict(parse_qsl(parts.query)).get("p", "")
        if page := NOTION_PAGE.fullmatch(peek) or NOTION_PAGE.search(parts.path):
            return "notion:" + page[1].replace("-", "").casefold()
    path = TREE_PATH.sub(r"\1/blob/", parts.path.rstrip("/"))
    query = urlencode([(k, v) for k, v in parse_qsl(
        parts.query, keep_blank_values=True) if not TRACKING.match(k)])
    return f"{parts.scheme.casefold()}://{host}{path}" + (f"?{query}" if query else "")


def local_link(document, target):
    """(path, anchor) a link `target` in the Markdown file `document` points to:
    a path relative to the document's folder, or the document itself for a
    bare #anchor, and the anchor unquoted in lower case ('' when it has none).
    None for a web link."""
    parsed = urlsplit(target)
    if parsed.scheme or parsed.netloc:
        return None
    document = Path(document)
    path = document.parent / unquote(parsed.path) if parsed.path else document
    return path, unquote(parsed.fragment).lower()


def headings(text):
    """[(level, title, anchor)] of a Markdown text's headings, with -1, -2...
    on repeated anchors, as viewers number them."""
    seen, found = {}, []
    for match in HEADING.finditer(markdown(text)[0]):
        base = heading_anchor(match[2])
        count = seen.get(base, 0)
        seen[base] = count + 1
        found.append((len(match[1]), match[2],
                     base if count == 0 else f"{base}-{count}"))
    return found


def heading_anchor(heading):
    """The anchor a Markdown viewer gives a heading, GitHub style: lower case,
    punctuation dropped, each space a hyphen."""
    return re.sub(r"[^\w\- ]", "", heading.strip().lower()).replace(" ", "-")


def markdown(text):
    """(prose, fences, unclosed): `text` with its fenced code blanked, offsets
    preserved; each fence as (start, end, language, body); and whether the
    last fence is left open."""
    prose, fences = [], []
    opened = None
    offset = 0
    for line in text.splitlines(keepends=True):
        content = line.rstrip("\n")
        match = FENCE.match(content)
        blank = " " * len(content) + line[len(content):]
        if opened is None and match:
            opened = (match[1], match[2].strip(), offset, [])
            prose.append(blank)
        elif opened is not None:
            marker, language, start, body = opened
            prose.append(blank)
            if match and match[1][0] == marker[0] and len(match[1]) >= len(marker) and not match[2].strip():
                fences.append((start, offset + len(line),
                              language, "".join(body)))
                opened = None
            else:
                body.append(line)
        else:
            prose.append(line)
        offset += len(line)
    if opened is not None:
        _, language, start, body = opened
        fences.append((start, len(text), language, "".join(body)))
    return "".join(prose), fences, opened is not None


def number(value):
    """A number as text: a whole one without a decimal point, and a fraction
    rounded to two decimals, so a sum of fractional estimates never shows
    floating-point noise such as 0.30000000000000004."""
    if isinstance(value, float):
        value = round(value, 2)
        if value.is_integer():
            return str(int(value))
    return str(value)


def plural(count, one, many):
    """The word for `count` things: `one` for exactly 1, else `many`."""
    return one if count == 1 else many


def display_date(day):
    """A day as reports show it, DD/MM/YYYY, such as 02/03/2026: `day` is a
    date or a datetime, or an ISO date as text, such as 2026-03-02."""
    if isinstance(day, str):
        day = date.fromisoformat(day)
    return day.strftime(DISPLAY_DATE)


def table(header, rows):
    """A Markdown table of `header` and `rows`, each cell on one line, its
    runs of whitespace as one space, and its pipes escaped."""
    lines = [table_row(header), table_row(["---"] * len(header))]
    lines += [table_row([" ".join(str(cell).split()) for cell in row])
              for row in rows]
    return "\n".join(lines)


def table_row(cells):
    """A Markdown table row from its cells, each pipe in one escaped as \\|
    unless it already is."""
    return "| " + " | ".join(CELL_PIPE.sub(r"\\|", str(cell)) for cell in cells) + " |"


def is_separator(line):
    """Whether `line` is a Markdown table's separator line, below its header:
    a pipe, and in each cell only dashes, with a colon at either end to align
    the column."""
    return "|" in line and all(SEPARATOR_CELL.fullmatch(cell) for cell in table_cells(line))


def table_cells(line):
    """The cells of the Markdown table row `line`, trimmed; a pipe escaped
    as \\| stays inside its cell, read as |."""
    return [cell.strip().replace("\\|", "|") for cell in CELL_PIPE.split(line.strip().strip("|"))]


def html_table(*rows, small=False):
    """A report's HTML table, as lines: the full width, each of `rows` its
    cells already written, aligned to the top, as HTML centres them by
    default; with `small`, in SMALL_TYPE, for a table of many rows. HTML, as
    Markdown can't set a table's or a column's width."""
    style = f' style="{SMALL_TYPE}"' if small else ""
    return [f'<table width="100%"{style}>', *(f'<tr valign="top">{cells}</tr>' for cells in rows), "</table>"]


def chart_image(src, description):
    """The chart at `src`, described as `description`, as wide as the page
    or its cell and linked to itself, so a click opens it full size in a new
    tab."""
    return f'<a href="{src}" target="_blank"><img src="{src}" width="100%" alt="{description}"></a>'


def ai_marked(title):
    """`title` marked as a part of a document the AI wrote: AI_LABEL after it
    as a small superscript. The label is a note for the reader, not part of
    the title; its size is in rem, so it reads the same after a heading and
    in a table cell."""
    return f'{title} <sup style="font-size:0.6rem;font-weight:normal">{AI_LABEL}</sup>'


def chunks(text, size):
    """`text` in pieces of at most `size` characters. A piece ends at the last
    line break, else the last space, in its second half, so it stops at the end
    of a line when the text has one to use."""
    pieces = []
    while len(text) > size:
        cut = text.rfind("\n", size // 2, size + 1)
        if cut < 0:
            cut = text.rfind(" ", size // 2, size + 1)
        if cut < 0:
            cut = size
        pieces.append(text[:cut].rstrip())
        text = text[cut:].lstrip()
    return [*pieces, text]
