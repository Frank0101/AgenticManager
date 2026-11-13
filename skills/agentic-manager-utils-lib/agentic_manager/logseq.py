"""Reads the user's notes in Logseq, the logseq-fs source: each journal and page, and the pages they link to.

Only the source's `path`, the graph's folder, is read from the config, and
the notes are only read, never changed. Links are read as Logseq writes them:
[[Page]], #[[Page]] and #Page all link one page, whatever their case, and a
page's alias:: property names other links to it. A page's file name holds
its title as the :triple-lowbar file name format writes it, ___ for each /,
with what a file name can't hold percent-encoded.
"""
import os
import re
from urllib.parse import unquote

from agentic_manager.config import read_source

GROUP, NAME = "local_vault", "logseq-fs"
SOURCE = f"sources.{GROUP}.{NAME}"
# The graph's folders of notes: a file a day, and a file a page.
FOLDERS = ("journals", "pages")
# A link, [[Page]] or #[[Page]], and a tag, #Page: a tag ends at a space or
# punctuation, and a # inside a word or a URL, such as a fragment, isn't one.
LINK = re.compile(r"\[\[([^\[\]\n]+)\]\]")
TAG = re.compile(r"(?<![\w#&/=])#([^\s#\[\]()\"',.;:!?]+)")
# A property line, key:: value, as a page's properties are written before its
# first block.
PROPERTY = re.compile(r"([\w-]+)::\s*(.*)")


def graph_path():
    """The graph's folder, the source's `path` with ~ expanded. Exits, naming
    the setting, never its value, when it holds neither journals nor pages."""
    path = os.path.expanduser(read_source(GROUP, NAME, ("path",))["path"])
    if not any(os.path.isdir(os.path.join(path, folder)) for folder in FOLDERS):
        raise SystemExit(f"The `path` setting of {SOURCE} isn't a Logseq graph's folder, one holding journals or "
                         "pages: set it to your graph's folder")
    return path


def notes(path):
    """(folder, title, text) of each note of the graph at `path`, the journals
    then the pages, each in name order: a journal's title is its file's name,
    such as 2026_07_22, a page's its page_title()."""
    for folder in FOLDERS:
        where = os.path.join(path, folder)
        if not os.path.isdir(where):
            continue
        for name in sorted(os.listdir(where)):
            if not name.endswith(".md"):
                continue
            with open(os.path.join(where, name), encoding="utf-8", errors="replace") as f:
                text = f.read()
            stem = name[:-len(".md")]
            yield folder, page_title(stem) if folder == "pages" else stem, text


def page_title(stem):
    """The title of the page whose file name, without .md, is `stem`."""
    return unquote(stem.replace("___", "/"))


def links(text):
    """The pages `text` links to, each time it does, in order: [[Page]],
    #[[Page]] and #Page, as written."""
    found = [(m.start(), m[1].strip()) for m in LINK.finditer(text)]
    found += [(m.start(), m[1]) for m in TAG.finditer(text)]
    return [name for _, name in sorted(found)]


def page_aliases(text):
    """The aliases the page `text` declares in its alias:: property, each
    written plain, as a link or as a tag, in order: the property lines before
    its first block are the page's; one inside a block is the block's."""
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        match = PROPERTY.fullmatch(line)
        if not match:
            return []
        if match[1].casefold() == "alias":
            names = (name.strip().lstrip("#").removeprefix("[[").removesuffix("]]").strip()
                     for name in match[2].split(","))
            return [name for name in names if name]
    return []
