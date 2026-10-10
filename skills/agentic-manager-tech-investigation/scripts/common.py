"""What the skill's scripts share: the investigation's fixed file names, the
report's fixed structure and the ledger's, and how to find an investigation's
folder. Scripts import the shared library's names from here, so they don't
depend on the order of their imports.
"""
import json
import os
import re
import sys

# The agentic-manager-utils-lib skill, installed next to this one.
LIB_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)),
                       "..", "..", "agentic-manager-utils-lib")
sys.path.insert(0, LIB_DIR)
from agentic_manager.output_file import target, write_output_file  # noqa: E402,F401
from agentic_manager.output_folder import output_folder  # noqa: E402,F401

FOLDER_NAME = "tech-investigations"
EXAMPLES = "_examples"
LEDGER = "ledgers.md"
CONTENT = "content.json"
REPORT_SUFFIX = "_Report.md"

# <Topic>_<YY-MM-DD>: words joined by hyphens, capitalised by the agent, or
# as the user named it.
TOPIC = re.compile(r"[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*")
INVESTIGATION = re.compile(r"(?P<topic>.+)_(?P<date>\d\d-\d\d-\d\d)")
# The label of an output's shape, such as long-analysis or exec-summary.
FORMAT = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")

# The report's headings: (level, title, id). The architect summary repeats the
# executive layer's two section titles, so a skip names headings by id.
HEADINGS = [
    (2, "Executive / product summary", "exec"),
    (3, "Problem and intended outcome", "exec.problem"),
    (3, "Current status", "exec.current"),
    (3, "Next steps and evolution", "exec.next"),
    (3, "Key decisions and risks", "exec.decisions"),
    (2, "Architect summary", "arch"),
    (3, "Current status", "arch.current"),
    (3, "Next steps and evolution", "arch.next"),
    (3, "Key decisions and gaps", "arch.decisions"),
    (2, "References", "references"),
]
# What a report may leave out, when the research shows it doesn't apply:
# {dimension: the heading ids it removes}. Skipping shapes the output only; the
# research covers every group either way.
SKIPS = {
    "architecture": ["arch", "arch.current", "arch.next", "arch.decisions"],
    "evolution": ["exec.next", "arch.next"],
}

# The ledger's sections, in order, and the queue's subsections.
LEDGER_SECTIONS = [
    "Resume here",
    "Research action queue",
    "Boundary, method and access",
    "Revisions and source register",
    "Findings and validation chains",
    "Component inventory and evolution",
    "Open decisions",
    "Evidence gaps",
    "Reflection",
    "Links",
]
QUEUE_SUBSECTIONS = ["Ready / in progress", "Blocked", "Completed"]
QUEUE_HEADER = ["ID", "Trigger / linked finding", "Question or check",
                "Sources and validation required", "Depends on",
                "Priority / severity", "Status", "Outcome / finding IDs"]
# The evidence areas a source or a gap is tagged with; `ledger.py status` counts
# them across the three groups, so no table of its own holds that grid.
AREAS = ["Architecture", "Delivery", "Implementation", "Security and data",
         "Identity and credentials", "Runtime and operations"]
GROUPS = ["documentation", "workflow", "source_control"]
SOURCE_HEADER = ["Source ID", "Group / evidence kind", "Exact reference",
                 "Revision / environment / date checked",
                 "Material read and findings", "Access limits / superseded by",
                 "Areas"]
FILE_HEADER = ["Source", "Material", "Depth", "Findings"]
DECISION_HEADER = ["ID", "Decision", "Established position or unresolved choice",
                   "Candidates, constraints", "Source authority and status",
                   "Owner and next check"]
GAP_HEADER = ["ID", "Gap", "What is established and what is missing",
              "What would close it", "Source authority and status",
              "Owner and next check",
              "Areas"]
COMPONENT_HEADER = ["ID", "Name and type", "Responsibility", "Repository, paths, revision",
                    "Status", "Deployment evidence and how much was read", "Callers → outgoing",
                    "Evidence", "Current → next steps"]
FINDING_FIELDS = ["Claim", "Kind", "Evidence", "Validation and limits"]
FINDING_OPTIONAL = ["Supersedes or contradicted by"]
FINDING_HEADING = re.compile(r"^### (F\d+) — \S.*$", re.M)


def report_headings(skip=()):
    """The report's (level, title) headings, without those `skip` removes."""
    removed = {ident for dimension in skip for ident in SKIPS[dimension]}
    return [(level, title) for level, title, ident in HEADINGS if ident not in removed]


def read_skip(folder):
    """The dimensions content.json skips in `folder`, or () without one."""
    try:
        with open(os.path.join(folder, CONTENT), encoding="utf-8") as f:
            skip = json.load(f).get("skip")
    except (OSError, UnicodeError, ValueError, AttributeError):
        return ()
    return tuple(d for d in SKIPS if isinstance(skip, list) and d in skip)


def expected_files(report_name, formats=()):
    """Every file an investigation folder holds, and nothing else: the ledger,
    content.json and the report, and a <format>.json and <format>.md for each
    short output."""
    files = {LEDGER, CONTENT, report_name}
    for wanted in formats:
        files |= {f"{wanted}.json", f"{wanted}.md"}
    return files


def short_formats(folder):
    """The short-output formats in `folder`: each <format>.json with its
    <format>.md. A lone file is not one, so it counts as an unexpected file."""
    names = set(os.listdir(folder))
    reserved = {CONTENT[:-5]}
    return {name[:-5] for name in names
            if name.endswith(".json") and FORMAT.fullmatch(name[:-5])
            and name[:-5] not in reserved and f"{name[:-5]}.md" in names}


def check_format(wanted):
    """`wanted`, the label of an output's shape, or exits if it isn't one."""
    if not FORMAT.fullmatch(wanted):
        raise SystemExit(
            f"{wanted!r}: the format is a short lower-case label, such as exec-summary")
    return wanted


def investigation_dir(relative):
    """(absolute path, output folder, temporary) of the investigation
    `relative` inside the skill's output folder. Exits if it would lead
    outside it."""
    folder, temporary = output_folder(FOLDER_NAME)
    return target(folder, relative), folder, temporary


def topic_of(folder):
    """The <Topic> of an investigation folder's name, or exits."""
    match = INVESTIGATION.fullmatch(os.path.basename(os.path.normpath(folder)))
    if not match:
        raise SystemExit(
            f"{folder!r} is not an investigation folder, <Topic>_<YY-MM-DD>")
    return match["topic"]


def load_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        raise SystemExit(
            f"{os.path.basename(path)} is missing in {os.path.dirname(path)}")
    except (OSError, UnicodeError, ValueError) as error:
        raise SystemExit(
            f"{os.path.basename(path)} is not readable JSON: {error}")


def table_row(cells):
    return "| " + " | ".join(cells) + " |"


def table(header, rows):
    """A Markdown table, with each cell's pipes escaped."""
    lines = [table_row(header), table_row(["---"] * len(header))]
    lines += [table_row([escape_cell(cell) for cell in row]) for row in rows]
    return "\n".join(lines)


def escape_cell(text):
    return re.sub(r"(?<!\\)\|", r"\\|", " ".join(str(text).split()))


def slug(heading):
    """The anchor a Markdown viewer gives a heading, GitHub style: lower case,
    punctuation dropped, each space a hyphen."""
    return re.sub(r"[^\w\- ]", "", heading.strip().lower()).replace(" ", "-")


def headings(text):
    """[(level, title, anchor)] of a Markdown text's headings, with -1, -2...
    on repeated anchors, as viewers number them."""
    seen, found = {}, []
    for match in re.finditer(r"^ {0,3}(#{1,6})\s+(.+?)\s*#*\s*$", markdown(text)[0], re.M):
        base = slug(match[2])
        count = seen.get(base, 0)
        seen[base] = count + 1
        found.append((len(match[1]), match[2],
                     base if count == 0 else f"{base}-{count}"))
    return found


INLINE_LINK = re.compile(
    r'(!?)\[([^\]\n]*)\]\(\s*(<[^>\n]+>|[^\s)]+)(?:\s+"[^"\n]*")?\s*\)')
REFERENCE_LINK = re.compile(r"(!?)\[([^\]\n]+)\]\[([^\]\n]*)\]")
# [text] alone, a link when a definition names it: not part of an inline,
# full reference or definition line.
SHORTCUT_LINK = re.compile(r"(?<![\]\\])(!?)\[([^\]\n]+)\](?![(\[:])")
DEFINITION = re.compile(r"^ {0,3}\[([^\]]+)\]:\s*(<[^>]+>|\S+)", re.M)


def markdown(text):
    """Return prose with fenced code blanked (offsets preserved), plus fences."""
    lines = text.splitlines(keepends=True)
    prose, fences = [], []
    opened = None
    offset = 0
    for line in lines:
        match = re.match(r"^ {0,3}(`{3,}|~{3,})(.*)\s*$", line.rstrip("\n"))
        if opened is None and match:
            opened = (match[1], match[2].strip(), offset, [])
            prose.append("\n" if line.endswith("\n") else "")
            prose[-1] = " " * (len(line) - len(prose[-1])) + prose[-1]
        elif opened is not None:
            marker, language, start, body = opened
            prose.append(" " * (len(line.rstrip("\n"))) +
                         ("\n" if line.endswith("\n") else ""))
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


def links(prose, definitions):
    """Yield (start, end, image, target); support inline, full and collapsed
    reference links, and shortcut links whose text a definition names."""
    for match in INLINE_LINK.finditer(prose):
        yield match.start(), match.end(), bool(match[1]), match[3].strip("<>")
    for match in REFERENCE_LINK.finditer(prose):
        key = (match[3] or match[2]).casefold()
        yield match.start(), match.end(), bool(match[1]), definitions.get(key)
    for match in SHORTCUT_LINK.finditer(prose):
        if match[2].casefold() in definitions:
            yield match.start(), match.end(), bool(match[1]), definitions[match[2].casefold()]
