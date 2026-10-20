"""What the skill's scripts share: the investigation's fixed file names, the
report's fixed structure and the ledger's, the values the ledger's cells
accept, the rules for a row that ledger.py applies on write and check_report.py
at handover, the one reader of the ledger's tables, the anchors every recorded
ID carries and the links to them, the linking of tickets and pull requests,
and how to find an investigation's folder. Scripts import the shared library's
names from here, so they don't depend on the order of their imports.
"""
import json
import os
import re
import sys

# The agentic-manager-utils-lib skill, installed next to this one.
LIB_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)),
                       "..", "..", "agentic-manager-utils-lib")
sys.path.insert(0, LIB_DIR)
from agentic_manager.batch import gather  # noqa: E402,F401
from agentic_manager.config import enabled_sources, is_enabled  # noqa: E402,F401
from agentic_manager.github import PULL_URL, GhError, gh_available, gh_found  # noqa: E402,F401
from agentic_manager.failures import stops_on_failure  # noqa: E402,F401
from agentic_manager.jira import PROJECT_KEY, JiraClient, JiraError, browse_url, plain_text  # noqa: E402,F401
from agentic_manager.json_path import nested  # noqa: E402,F401
from agentic_manager.output_file import read_json, target, write_output_file  # noqa: E402,F401
from agentic_manager.output_folder import DAY_FOLDER, EXAMPLE_DESCRIPTION, clear_folder, day_folder, output_folder  # noqa: E402,F401
from agentic_manager.text import DEFINITION, FENCE, HEADING, INLINE_LINK, NAME, REFERENCE_LINK, free_name, heading_anchor, headings, link_definitions, link_text, links, local_link, markdown, reference_key, slug, word_count  # noqa: E402,F401
from agentic_manager.ticket_pulls import COMMITS, PANEL, SEARCH, first_found, holding_pulls, panel_commits, panel_pulls, search_pulls  # noqa: E402,F401

FOLDER_NAME = "tech-investigations"
EXAMPLES = "_examples"
# An example's own description, beside its copied documents: what makes it
# good, as the agent wrote it when the user approved it.
WHY_GOOD_LABEL = "**Why it's good:**"
WHY_GOOD = re.compile(rf"^{re.escape(WHY_GOOD_LABEL)} (.+)$", re.M)
LEDGER = "ledger.md"
CONTENT = "content.json"
REPORT_SUFFIX = "_Report.md"

# <Topic>_<YY-MM-DD>: words joined by hyphens, capitalised by the agent, or
# as the user named it.
TOPIC, INVESTIGATION = NAME, DAY_FOLDER

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

# The ledger's sections, in order, and the queue's subsections. Each title is
# named once, here: one typed differently elsewhere would leave a check reading
# an empty section.
QUEUE = "Research action queue"
BOUNDARY = "Boundary, method and access"
REGISTER = "Revisions and source register"
FINDINGS = "Findings and validation chains"
INVENTORY = "Component inventory and evolution"
DECISIONS = "Open decisions"
GAPS = "Evidence gaps"
REFLECTION = "Reflection"
LINKS = "Links"
LEDGER_SECTIONS = [QUEUE, BOUNDARY, REGISTER, FINDINGS,
                   INVENTORY, DECISIONS, GAPS, REFLECTION, LINKS]
# An action is ready until someone starts it, so that after a break, or with
# work shared out, what is under way shows apart from what is waiting.
QUEUE_SUBSECTIONS = ["Ready", "In progress", "Blocked", "Completed"]
QUEUE_TABLES = ["queue-ready", "queue-in-progress",
                "queue-blocked", "queue-completed"]
# The heading each of the ledger's tables sits under, by the name ledger.py's
# commands use: one place, since a heading typed differently elsewhere would
# leave a check reading an empty table.
TABLE_HEADINGS = {**{table: f"### {title}" for table, title in zip(QUEUE_TABLES, QUEUE_SUBSECTIONS)},
                  "sources": f"## {REGISTER}", "file-coverage": "### File reading coverage",
                  "decisions": f"## {DECISIONS}", "gaps": f"## {GAPS}",
                  "components": f"## {INVENTORY}"}
QUEUE_HEADER = ["ID", "Trigger / linked finding", "Question or check",
                "Sources and validation required", "Depends on",
                "Priority / severity", "Outcome / finding IDs"]
# The evidence areas a source or a gap is tagged with; `ledger.py status` counts
# them across the source groups, so no table of its own holds that grid.
AREAS = ["Architecture", "Delivery", "Implementation", "Security and data",
         "Identity and credentials", "Runtime and operations"]
# The source groups in their order of authority, each with the name the ledger
# and the output give it: when two disagree, the earlier one wins, so the first
# actions search them in it.
GROUPS = {"source_control": "code", "workflow": "tracker",
          "documentation": "documentation"}
SOURCE_HEADER = ["Source ID", "Group / evidence kind", "Exact reference",
                 "Revision / environment / date checked",
                 "Material read and findings", "Access limits / superseded by",
                 "Areas"]
FILE_HEADER = ["Source", "Material", "Depth"]
DECISION_HEADER = ["ID", "Decision", "Established position or unresolved choice",
                   "Candidates, constraints", "Source authority and status",
                   "Owner and next check"]
# What a gap can be blocked by. Anything else is work the agent can do, so it is
# a ready action in the queue and not a gap. A question the user was asked and
# didn't answer is a valid blocker: what to leave out is theirs to decide, so
# the agent leaves the gap open and says it asked.
BLOCKERS = ("No access", "Waiting on decision",
            "Out of scope, approved by the user", "Asked the user, no answer")
GAP_HEADER = ["ID", "Gap", "What is established and what is missing",
              "What would close it", "Blocked by", "Source authority and status",
              "Owner and next check",
              "Areas"]
COMPONENT_HEADER = ["ID", "Name and type", "Responsibility", "Repository, paths, revision",
                    "Status", "Deployment evidence and how much was read", "Callers → outgoing",
                    "Evidence", "Current → next steps"]
# A component's implementation status: the Status cell starts with one of these.
# Code is the source of truth, so the two that claim code exists need the code
# read (READ_DEPTHS below); the others say what the evidence can't establish.
STATUSES = [("🟩 Implemented", "merged code establishes it; this doesn't imply deployment"),
            ("🟨 Implemented, needs significant work",
             "it exists but doesn't meet the proposed capability"),
            ("🟦 In development",
             "unmerged or development-branch code, or an experiment branch with no pull request"),
            ("🟥 No implementation found",
             "a search outcome, not proof of absence: say where you searched"),
            ("⬜ Unverified",
             "access or evidence is insufficient; a ticket or document alone can't establish code"),
            ("⚫ Legacy or superseded", "code establishes an older implementation")]
CODE_STATUSES = ("🟩", "🟨")
# How deeply a file or folder was read: the Depth cell of file coverage starts
# with one of these. A README or a listing says what the authors meant, not
# what the code does.
DEPTHS = ["full", "entrypoints and routes",
          "partial", "README", "listing", "search hit"]
READ_DEPTHS = ("full", "entrypoints and routes")
# What closes a research action: the findings, decision or gap that answer it,
# or the user's explicit choice not to pursue it. "Out of scope" on its own is
# not an answer.
REJECTED = "Rejected by the user:"
# The independent review is recorded as a completed action with this question,
# by `ledger.py review`; it answers with the actions it raised, or with
# REVIEW_NONE. Its row is what tells the phases that the review took place.
# A strict reviewer can keep finding something, so after REVIEW_BACKSTOP rounds
# the user decides whether to go on; their choice to stop ends the review like
# a round that raised nothing, as a review row answered REVIEW_STOPPED.
REVIEW_QUESTION = "Independent review of the ledger and report"
REVIEW_NONE = "Nothing doable found"
REVIEW_STOPPED = "Stopped by the user:"
REVIEW_BACKSTOP = 3
FINDING_FIELDS = ["Claim", "Kind", "Evidence", "Validation and limits"]
# A finding holds one claim, of about 80 words; a claim far past that, here
# about twice it, usually bundles several, which are then cited and corrected
# as one. It is a warning, never a refusal: a single claim can need the room.
# Warning when the finding is written, not only at the end, splits it before
# other rows cite it.
CLAIM_WORDS_MAX = 150
FINDING_OPTIONAL = ["Supersedes or contradicted by"]
FINDING_HEADING = re.compile(r"^### (F\d+) — \S.*$", re.M)
# Where a finding's block starts, whatever its title.
FINDING_START = re.compile(r"^### (F\d+) ", re.M)
# A finding's Evidence line: what follows its label.
EVIDENCE_LINE = re.compile(r"- \*\*Evidence:\*\*(.*)")
# A pipe that separates table cells: one escaped as \| stays inside its cell.
CELL_PIPE = re.compile(r"(?<!\\)\|")
# Ticket keys and pull requests, written as links. A ticket key is linked to
# the Jira site of its project: the one the ledger's links give, else the one
# that has the project, looked up on the Jira site. Any other key-shaped text,
# such as a ticket of a project neither knows or SHA-256, stays visible as
# code, `PROJ-123`, so nothing forces a link and no non-ticket gets one. A
# pull request names its repository, owner/repo#123, since a bare #123 is
# ambiguous once two repositories are involved.
# The key's shape is the Jira library's; the context around it is the skill's:
# not inside a URL path, a link's text or a longer hyphenated word.
TICKET = re.compile(rf"(?<![\w/\[-])({PROJECT_KEY})-\d+(?![\w\]-])")
REPO_PR = re.compile(
    r"(?<![\w/.\[-])([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)#(\d{1,6})\b")
BARE_PR = re.compile(r"(?<![\w/&#\[])#\d{1,6}\b")
TICKET_URL = re.compile(
    rf"(https?://[^/\s()<>]+)/browse/({PROJECT_KEY})-\d+")
REPO_URL = re.compile(
    r"^(https?://[^/\s]+)/([\w.-]+/[\w.-]+)/(?:pull|issues|blob|tree|commit|commits)\b")
# What a reference inside them is already part of: code, links and bare URLs.
PROTECTED = re.compile(
    r"`[^`\n]*`|!?\[[^\]\n]*\]\([^)\n]*\)|!?\[[^\]\n]+\]\[[^\]\n]*\]|https?://\S+")
ANY_REFERENCE = re.compile(
    rf"{REPO_PR.pattern}|{TICKET.pattern}|{BARE_PR.pattern}")
# How to fix a row that breaks a rule, worded once for ledger.py's refusal and
# check_report.py's error.
SOURCE_LINK_FIX = ("link the Exact reference at its pinned revision, or, for a search, give it as "
                   '{"query": "<the exact query>"} and the script writes it')
GAP_FIX = ("Blocked by starts with one of: " + "; ".join(BLOCKERS) + ". A gap nothing blocks is a ready action in "
           "the queue: do it. Never write a blocker that is not true: write 'approved by the user' only after the "
           "user has said so, and 'Asked the user, no answer' only after you asked")
# A link, inline or by reference, or a bare URL: where a claim's trail ends.
LINK = re.compile(r"\]\(https?://[^)\s]+\)|\]\[[^\]]*\]|https?://\S+")
# A search has no URL to pin, so its exact query, between backticks, stands in.
QUERY = re.compile(r"`[^`\n]+`")
# Every recorded ID has an anchor, so any citation of it can link to it: a
# table row carries an HTML anchor in its ID cell, which Markdown viewers such
# as VS Code and GitHub render, and a finding one under its heading. A heading's
# own anchor would change with its title; these don't.
ID = re.compile(r"\b[SQFCDG]\d{2,}\b")
ANCHOR_ID = r"[a-z]+\d+"
ID_ANCHOR = re.compile(rf'<a id="{ANCHOR_ID}"></a>')
# The start of a table row, before its ID and the anchor that may precede it.
ROW_START = rf"^\|\s*(?:{ID_ANCHOR.pattern})?"
RECORD = re.compile(r"\b[SQDGC]\d{2,}\b")
RECORD_DEFINITION = re.compile(
    rf"(?:{ROW_START}|^[-*]\s+\*\*|^#{{3}}\s+)({RECORD.pattern})", re.M)
# The Findings a source row lists, which ledger.py writes and check_report.py reads.
SOURCE_FINDINGS = re.compile(r"\s*Findings: ([^.]*)\.\s*$")


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


def expected_files(report_name):
    """Every file an investigation folder holds, and nothing else: the ledger,
    content.json and the report."""
    return {LEDGER, CONTENT, report_name}


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
    return match["subject"]


def table(header, rows):
    """A Markdown table, each cell on one line with its pipes escaped."""
    lines = [table_row(header), table_row(["---"] * len(header))]
    lines += [table_row([" ".join(str(cell).split()) for cell in row])
              for row in rows]
    return "\n".join(lines)


def table_row(cells):
    """A Markdown table row from its cells, each pipe in one escaped as \\|."""
    return "| " + " | ".join(CELL_PIPE.sub(r"\\|", str(cell)) for cell in cells) + " |"


def unlinked_references(text):
    """The ticket keys and pull requests of `text` written outside a link, in order."""
    found = []

    def collect(part):
        found.extend(m[0] for m in ANY_REFERENCE.finditer(part))
        return part
    for line in text.splitlines():
        if not _skipped(line):
            _map_open(line, collect)
    return found


def _skipped(line):
    """Headings, whose anchor a link would change, and link definitions."""
    return bool(HEADING.match(line) or DEFINITION.match(line))


def _map_open(line, transform):
    """`line` with `transform` applied to each part outside code, links and URLs."""
    out, at = [], 0
    for match in PROTECTED.finditer(line):
        out += [transform(line[at:match.start()]), match[0]]
        at = match.end()
    out.append(transform(line[at:]))
    return "".join(out)


def autolink(text, definitions, site_of=None):
    """(`text` with each ticket key and owner/repo#123 written as an inline link,
    [what couldn't be linked]). The Jira site of a key's project comes from the
    links already defined, else from `site_of(project)`, which gives the site
    that has the project, or None; a key of a project neither knows is written
    as code. A pull request's host comes from the links: one on a host nothing
    links yet, or a bare #123, can't be resolved."""
    sites = ticket_sites(definitions.values())
    hosts, repos = set(), {}
    for url in definitions.values():
        if match := REPO_URL.match(url):
            hosts.add(match[1])
            repos[match[2].casefold()] = match[1]
    unresolved = []

    def ticket(match):
        site = sites.get(match[1]) or (site_of(match[1]) if site_of else None)
        if site is None:
            return f"`{match[0]}`"
        return f"[{match[0]}]({browse_url(site, match[0])})"

    def pull(match):
        host = repos.get(match[1].casefold()) or (
            next(iter(hosts)) if len(hosts) == 1 else None)
        if host is None:
            unresolved.append(match[0])
            return match[0]
        return f"[{match[0]}]({host}/{match[1]}/pull/{match[2]})"

    def transform(part):
        unresolved.extend(BARE_PR.findall(part))
        # Pull requests first, then tickets outside the links just made.
        return _map_open(REPO_PR.sub(pull, part), lambda rest: TICKET.sub(ticket, rest))

    lines = [line if _skipped(line) else _map_open(line, transform)
             for line in text.split("\n")]
    return "\n".join(lines), unresolved


def ticket_sites(urls):
    """{project: Jira site} of the ticket links among `urls`."""
    return {match[2]: match[1] for url in urls if (match := TICKET_URL.fullmatch(url))}


def upgraded_tickets(line, sites):
    """`line` with each ticket key written as code, `PROJ-7`, as an inline link
    when `sites` now knows its project: a key written before its project was
    linked becomes a link once it is."""
    if _skipped(line):
        return line

    def upgrade(match):
        key, project = match[1], match[2]
        site = sites.get(project)
        return f"[{key}]({browse_url(site, key)})" if site else match[0]
    return re.sub(rf"`(({PROJECT_KEY})-\d+)`", upgrade, line)


def unresolved_message(unresolved):
    """Why pull requests couldn't be linked, and how to fix them."""
    return (f"{', '.join(dict.fromkeys(unresolved))}: write a pull request as owner/repo#123, "
            "after linking any page of that host once")


def outcome_problem(row_id, outcome, question=""):
    """Why a completed action's outcome doesn't close it, or None. The review's
    own row is answered by the actions it raised."""
    if question == REVIEW_QUESTION:
        if re.search(r"\bQ\d{2,}\b", outcome) or outcome.strip() == REVIEW_NONE \
                or outcome.strip().startswith(REVIEW_STOPPED):
            return None
        return (f"{row_id}: the review's outcome names the actions it raised (Q14, Q15), is '{REVIEW_NONE}' "
                f"or starts '{REVIEW_STOPPED}'")
    if re.search(r"\b[FDG]\d{2,}\b", outcome) or outcome.strip().startswith(REJECTED):
        return None
    return (f"{row_id}: a completed action names the findings, decision or gap that answer it "
            f"(F01, D01, G01) in Outcome / finding IDs, or starts '{REJECTED} <what they said>' "
            "when the user chose not to pursue it. Ask the user before writing that")


def claim_length_warning(ident, claim):
    """A warning when a finding's claim is far past its length, or None."""
    words = word_count(claim)
    if words <= CLAIM_WORDS_MAX:
        return None
    return f"{ident}'s claim is {words} words; split it into findings of one claim each"


def review_rounds(completed):
    """How many independent review rounds ran: the review rows, apart from
    one recording the user's choice to stop."""
    return sum(1 for outcome in _review_outcomes(completed) if not outcome.startswith(REVIEW_STOPPED))


def _review_outcomes(completed):
    """The outcomes of the independent review's rows among the completed
    rows, in order."""
    return [row[-1].strip() for row in completed if len(row) > 2 and row[2] == REVIEW_QUESTION]


def review_problem(completed):
    """What the review still needs, or None once a round raised no action."""
    if last_review(completed) is None:
        return "no independent review is recorded: run it, then record it with ledger.py review"
    if not reviewed(completed):
        return ("the last review round raised actions: once they are done, run another round with the same "
                "brief, until one raises no action or the user chooses to stop")
    return None


def last_review(completed):
    """The outcome of the latest independent review among the completed
    rows, or None."""
    outcomes = _review_outcomes(completed)
    return outcomes[-1] if outcomes else None


def reviewed(completed):
    """Whether the review is finished: rounds repeat until one raises no
    action, since the actions a round raises change the ledger and the report
    the next round reads. Record fixes, which change nothing in the report,
    raise no action, so they don't keep the rounds going. The user's choice
    to stop also ends it."""
    outcome = last_review(completed)
    return outcome is not None and (outcome == REVIEW_NONE or outcome.startswith(REVIEW_STOPPED))


# The rules below are each defined once: ledger.py applies them to a row as it
# is written, and check_report.py to the whole ledger, which also catches a
# ledger edited without the script.


def backtick_error(where, spans):
    """The error for references in backticks outside a link."""
    return (f"{where}: references in backticks without a link: {listed([f'`{s}`' for s in spans])}. "
            "Link each to its pinned revision, or write it as plain words")


def listed(items):
    """`items` for a message: the first six, then how many more."""
    return ", ".join(items[:6]) + (f" and {len(items) - 6} more" if len(items) > 6 else "")


def gap_problem(row):
    """Why a gap row's Blocked by isn't allowed, or None. A gap nothing blocks is
    work to do now, so it belongs in the queue; a decision must be named."""
    blocker = next(
        (b for b in BLOCKERS if row[4].lower().startswith(b.lower())), None)
    if blocker is None:
        return f"{row[0]} is blocked by '{row[4]}'"
    if blocker == "Waiting on decision" and not re.search(r"\bD\d{2,}\b", row[4]):
        return f"{row[0]} waits on a decision but names none (D01...)"
    return None


def source_reference_missing(row):
    """Whether a source row's Exact reference holds neither a link nor a query."""
    return not LINK.search(row[2]) and not QUERY.search(row[2])


def coverage_material_missing(row):
    """Whether a file coverage row's Material holds no link to what was read."""
    return not LINK.search(row[1])


def unlinked_backticks(prose, linked_text=""):
    """The backticked spans of `prose` that sit outside a link, in order. Backticks
    mark a reference to code or a source, so each is a link to its pinned
    revision; anything else is written as plain words. A ticket key is the
    exception when nothing in `prose` or `linked_text` links a ticket of its
    project: with no site to link it to, it stays as code."""
    urls = [m[0] for m in TICKET_URL.finditer(prose + "\n" + linked_text)]
    projects = ticket_sites(urls)
    spans = [span[1:-1] for span in QUERY.findall(_strip_links(prose))]
    return [s for s in spans if not (TICKET.fullmatch(s) and s.split("-")[0] not in projects)]


def _strip_links(text):
    """`text` without its links, inline or by reference, and without the
    definition lines the references use."""
    return REFERENCE_LINK.sub(" ", INLINE_LINK.sub(" ", DEFINITION.sub(" ", text)))


def anchored(ident):
    """`ident` after its anchor, as its row's ID cell holds it."""
    return anchor_tag(ident) + ident


def anchor_tag(ident):
    """The HTML anchor of `ident`, which its citations link to."""
    return f'<a id="{ident.lower()}"></a>'


def anchor_ids(text):
    """The IDs of the anchors in `text`, as they are linked: lower case."""
    return set(re.findall(rf'<a id="({ANCHOR_ID})"></a>', text))


def component_rows(body):
    """The component inventory's rows, as cells."""
    return [row for row in ledger_rows(body, TABLE_HEADINGS["components"])
            if re.fullmatch(r"C\d+", row[0]) and len(row) > 4]


def ledger_rows(text, heading):
    """The data rows, as cells, of the tables under `heading` in the ledger
    `text`, up to the next heading, leaving out each header and separator.
    The one reader of the ledger's tables, for the script that edits them and
    the check that reads them alike."""
    lines = text.split("\n")
    span = section_span(lines, heading)
    if span is None:
        return []
    section = lines[span[0] + 1:span[1]]
    separator = [bool(re.match(r"^\|\s*:?-", line)) for line in section]
    return [table_cells(line) for i, line in enumerate(section)
            if line.startswith("|") and not separator[i]
            and not (i + 1 < len(section) and separator[i + 1])]


def section_span(lines, heading):
    """(index of the line `heading`, index of the next heading or the end), or None."""
    start = next((i for i, line in enumerate(lines)
                 if line.strip() == heading), None)
    if start is None:
        return None
    return start, next((i for i in range(start + 1, len(lines)) if lines[i].startswith("#")), len(lines))


def h2_span(lines, title):
    """(index of the line `## title`, index of the next ## heading or the end),
    or None: a ## section with the ### headings inside it."""
    span = section_span(lines, f"## {title}")
    if span is None:
        return None
    return span[0], next((i for i in range(span[0] + 1, len(lines)) if lines[i].startswith("## ")), len(lines))


def table_cells(line, keep_anchors=False):
    """A Markdown table row's cells, trimmed; an ID without its anchor unless
    `keep_anchors`. A pipe escaped as \\| stays inside its cell, read as |."""
    cells = [c.strip().replace("\\|", "|")
             for c in CELL_PIPE.split(line.strip().strip("|"))]
    return cells if keep_anchors else [strip_anchors(c) for c in cells]


def strip_anchors(text):
    """A text without its ID anchors."""
    return ID_ANCHOR.sub("", text)


def linked_ids(text, recorded):
    """`text` with each ID in `recorded` written as a link to its anchor, outside
    code, links and URLs; headings and link definitions are left alone."""
    def link(part):
        return ID.sub(lambda m: f"[{m[0]}](#{m[0].lower()})" if m[0] in recorded else m[0], part)
    return "\n".join(line if _skipped(line) else _map_open(line, link) for line in text.split("\n"))


def unrecorded_ids(body):
    """The source, action, decision, gap and component IDs the ledger cites but
    never records in a table row, a bold label or a heading."""
    return sorted(set(RECORD.findall(body)) - recorded_ids(body), key=id_order)


def id_order(ident):
    """A sort key for IDs in number order: S2 before S10."""
    match = re.match(r"([A-Za-z]+)(\d+)", ident)
    return (match[1], int(match[2])) if match else (ident, 0)


def recorded_ids(body):
    """Every ID the ledger `body` records: table rows, bold labels, headings
    and findings."""
    return set(RECORD_DEFINITION.findall(body)) | set(FINDING_HEADING.findall(body))


def cited_sources(body):
    """{source number: the findings whose Evidence line names it} in the ledger `body`."""
    cited = {}
    for ident, block in finding_blocks(body).items():
        if evidence := EVIDENCE_LINE.search(block):
            for source in set(re.findall(r"\bS(\d+)\b", evidence[1])):
                cited.setdefault(int(source), set()).add(ident)
    return cited


def finding_blocks(text):
    """{finding ID: its block, from its heading to the next finding} in `text`."""
    found = list(FINDING_START.finditer(text))
    ends = [match.start() for match in found[1:]] + [len(text)]
    return {match[1]: text[match.start():end].strip("\n") for match, end in zip(found, ends)}


def unrecorded_citations(values, body):
    """The IDs, findings included, that `values` cite and the ledger `body`
    doesn't record yet."""
    cited = {i for v in values for i in ID.findall(v)}
    return sorted(cited - recorded_ids(body), key=id_order)


def areas_problem(row):
    """Why a source or gap row's Areas cell names something other than AREAS,
    or None."""
    wrong = [a for a in areas_of(row) if a not in AREAS]
    if not wrong:
        return None
    return f"{row[0]}: Areas must be some of: {', '.join(AREAS)}; not {', '.join(wrong)}"


def areas_of(row):
    """The evidence areas a source or gap row names in its last cell, Areas."""
    return [a for a in (x.strip() for x in row[-1].split(",")) if a]


def status_problem(row_id, status):
    """Why a component's Status cell isn't one of STATUSES, or None."""
    if any(status.startswith(label) for label, _ in STATUSES):
        return None
    return (f"{row_id}: Status starts with one of: "
            + "; ".join(f"{label} ({meaning})" for label, meaning in STATUSES))


def depth_problem(depth):
    """Why a file coverage Depth cell doesn't start with one of DEPTHS, or None."""
    if any(depth.casefold().startswith(d.casefold()) for d in DEPTHS):
        return None
    return (f"Depth {depth!r} starts with one of: {', '.join(DEPTHS)}, "
            "then any detail, such as 'partial: lines 1-120 of 400'")


def unread_components(components, coverage, definitions):
    """{component ID: the paths it links} of the components whose Status
    claims code (🟩, 🟨) without file coverage read at READ_DEPTHS of one of
    those paths, of a file or folder under it, or of a folder above it, which
    covers the files in it. `components` are rows (ID, ..., repository cell
    at 3, status at 4); `coverage` rows (source, material, depth)."""
    def urls(cell):
        return [url for _, _, _, url in links(cell, definitions) if url]
    read = [_code_path(url) for row in coverage
            if read_in_full(row[2])
            for url in urls(row[1])]
    found = {}
    for row in components:
        if not row[4].startswith(CODE_STATUSES):
            continue
        paths = [_code_path(url) for url in urls(row[3])]
        if not any(r == p or r.startswith(p + "/") or p.startswith(r + "/") for p in paths for r in read):
            found[row[0]] = [_shown_path(p) for p in paths]
    return found


def read_in_full(depth):
    """Whether a file coverage Depth cell says the material was read at
    READ_DEPTHS, enough to establish what the code does."""
    return any(depth.casefold().startswith(d) for d in READ_DEPTHS)


def _code_path(url):
    """A GitHub-style URL with /tree/ or /blob/ made the same, for prefix matching."""
    return re.sub(r"/(?:tree|blob)/", "/-/", url.rstrip("/"))


def _shown_path(path):
    """A code path as a message names it: owner/repo and the path after the revision."""
    match = re.match(r"https?://[^/]+/([^/]+/[^/]+)/-/[^/]+/?(.*)", path)
    return f"{match[1]}: {match[2] or '/'}" if match else path


def unread_message(found):
    """What to do about components claiming code with no code read, `found`
    as unread_components returns it."""
    return (f"a component marked {' or '.join(CODE_STATUSES)} needs its code read, at depth "
            f"{' or '.join(READ_DEPTHS)}, in a file coverage row of the path it links, of a file under it or "
            "of a folder above it: " + "; ".join(f"{ident} links {', '.join(paths) or 'no code'}"
                                                 for ident, paths in found.items())
            + ". Read it and add the row, then set the status; until then it is ⬜ Unverified")
