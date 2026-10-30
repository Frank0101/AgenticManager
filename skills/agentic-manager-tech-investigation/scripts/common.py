"""What the skill's scripts share: the investigation's fixed file names, the
report's fixed structure and the ledger's, the values the ledger's cells
accept, the rules for a row that ledger.py applies on write and check_report.py
at handover, the one reader of the ledger's tables, the anchors every recorded
ID carries and the links to them, the linking of tickets and pull requests,
and how to find an investigation's folder. Scripts import the shared library's
names from here, so they don't depend on the order of their imports.
"""
import os
import re
import sys

# The agentic-manager-utils-lib skill, installed next to this one.
LIB_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)),
                       "..", "..", "agentic-manager-utils-lib")
sys.path.insert(0, LIB_DIR)
from agentic_manager.batch import gather  # noqa: E402,F401
from agentic_manager.config import enabled_sources, is_enabled  # noqa: E402,F401
from agentic_manager.github import NAME as GITHUB_CLI, GH_UNAVAILABLE, GhError, gh_available, gh_found, gh_signed_in, pull_parts  # noqa: E402,F401
from agentic_manager.failures import stops_on_failure  # noqa: E402,F401
from agentic_manager.jira import BROWSE_URL as TICKET_URL, GROUP as JIRA_GROUP, NAME as JIRA_API, PROJECT_KEY, JiraClient, JiraError, browse_url, plain_text, project_of  # noqa: E402,F401
from agentic_manager.json_path import nested  # noqa: E402,F401
from agentic_manager.output_file import read_json, target, write_output_file  # noqa: E402,F401
from agentic_manager.output_folder import DAY_FOLDER, EXAMPLE_DESCRIPTION, KEPT_EXAMPLES, description, read_description, clear_folder, day_folder, output_folder  # noqa: E402,F401
from agentic_manager.text import DEFINITION, DISPLAY_DATE, FENCE, HEADING, INLINE_LINK, NAME, REFERENCE_LINK, free_name, headings, inline_links, link_definitions, link_text, links, local_link, markdown, reference_key, same_document, slug, word_count  # noqa: E402,F401
from agentic_manager.ticket_pulls import pulls_by_ticket  # noqa: E402,F401

FOLDER_NAME = "tech-investigations"
# What a ticket shows in place of its pull requests when gh can't be used.
PULLS_UNREAD = f"{GH_UNAVAILABLE}, so pull requests weren't read"
# An example's own description, beside its copied documents: what makes it
# good, as the agent wrote it when the user approved it.
WHY_GOOD = "Why it's good"
LEDGER = "ledger.md"
CONTENT = "content.json"
REPORT_SUFFIX = "_Report.md"

# <Topic>_<YY-MM-DD>: words joined by hyphens, capitalised by the agent, or
# as the user named it.
TOPIC, INVESTIGATION = NAME, DAY_FOLDER

# The report's headings: (level, title, id); the script names a heading by its id.
HEADINGS = [
    (2, "Executive / product summary", "exec"),
    (3, "Problem and purpose", "exec.purpose"),
    (3, "Current status", "exec.current"),
    (3, "Direction", "exec.direction"),
    (3, "Key decisions and risks", "exec.decisions"),
    (2, "Architect summary", "arch"),
    (3, "How it works today", "arch.today"),
    (3, "Target design", "arch.target"),
    (3, "Open technical choices and gaps", "arch.decisions"),
    (2, "References", "references"),
]
# The ledger's sections, in order, and the queue's subsections. Each title is
# named once, here: one typed differently elsewhere would leave a check reading
# an empty section.
QUEUE = "Research questions"
REVIEWS = "Independent reviews"
SCOPE = "Scope boundaries"
SOURCES = "Sources"
FINDINGS = "Findings"
DESIGN = "System design"
DECISIONS = "Open decisions"
GAPS = "Evidence gaps"
LINKS = "Links"
LEDGER_SECTIONS = [QUEUE, SCOPE, REVIEWS, SOURCES, FINDINGS,
                   DESIGN, DECISIONS, GAPS, LINKS]
# A question is ready until someone starts it, so that after a break, or with
# work shared out, what is under way shows apart from what is waiting.
QUEUE_SUBSECTIONS = ["Ready", "In progress", "Completed", "Blocked"]
QUEUE_TABLES = ["queue-ready", "queue-in-progress",
                "queue-completed", "queue-blocked"]
# The system design: its components, then what joins and groups them, one
# table each under its own heading, so the design is recorded as rows, never
# pieced together from prose. DESIGN_TABLES are those beside the components.
DESIGN_SUBSECTIONS = ["Components", "Boundaries",
                      "Connections", "Identities", "Flows"]
DESIGN_TABLES = ["boundaries", "connections", "identities", "flows"]
# The heading each of the ledger's tables sits under, by the name ledger.py
# gives it: one place, since a heading typed differently elsewhere would
# leave a check reading an empty table.
TABLE_HEADINGS = {**{table: f"### {title}" for table, title in zip(QUEUE_TABLES, QUEUE_SUBSECTIONS)},
                  "scope": f"## {SCOPE}", "reviews": f"## {REVIEWS}", "sources": f"## {SOURCES}", "findings": f"## {FINDINGS}",
                  "decisions": f"## {DECISIONS}", "gaps": f"## {GAPS}",
                  **{table: f"### {title}" for table, title in zip(["components", *DESIGN_TABLES],
                                                                   DESIGN_SUBSECTIONS)}}
# A question, what raised it, the questions it waits for, and the findings that answer it.
QUEUE_HEADER = ["ID", "Trigger", "Question", "Depends on", "Findings"]
# Whether the investigation covers something research has reached is the
# user's to decide: research raises a question starting SCOPE_QUESTION, rather
# than settling scope or reading on. The user's answer is a scope boundary, a
# record of its own, so whatever rests on it cites it: the question it closes,
# whose Findings start with USER_DECIDED, and any research question it leaves
# out, whose Findings start with OUTSIDE_SCOPE.
SCOPE_QUESTION = "Scope boundary: "
USER_DECIDED = "Decided by the user: "
OUTSIDE_SCOPE = "Outside the scope decided in "
SCOPE_HEADER = ["ID", "Topic", "Decision", "Asked in"]
SCOPE_ANSWERS = ("include", "mention only", "exclude")
LEFT_OUT = SCOPE_ANSWERS[1:]
# The source groups, each with the name the ledger and the output give it.
GROUPS = {"source_control": "code", "workflow": "tracker",
          "documentation": "documentation"}
# A source is one thing read, at the grain it was read, so its Coverage says
# how much of it the findings rest on. Its Findings are the script's, from the
# findings that cite it.
SOURCE_HEADER = ["ID", "Kind", "Reference", "Revision", "Coverage", "Findings",
                 "Superseded by"]
SOURCE_FINDINGS_COLUMN = SOURCE_HEADER.index("Findings")
# How much of a source was read: its Coverage starts with one of these. A
# listing, a search hit or a partial read says what the authors meant or where
# to look, not what the code does, so only the first two count as read; the
# report marks every source not read in full as limited.
COVERAGE = ["full", "entry points", "partial",
            "listing", "search hit", "no access"]
READ_COVERAGE = ("full", "entry points")
FINDING_HEADER = ["ID", "Claim", "Sources", "Limits"]
DECISION_HEADER = ["ID", "Decision", "Established position or unresolved choice",
                   "Candidates, constraints", "Source authority and status",
                   "Owner and next check"]
# What a gap can be blocked by. Anything else is work the agent can do, so it is
# a ready question in the queue and not a gap; whether the investigation covers
# something is a scope question in the queue, so no gap waits on the user.
BLOCKERS = ("No access", "Waiting on decision")
GAP_HEADER = ["ID", "Gap", "What is established and what is missing",
              "What would close it", "Blocked by", "Source authority and status",
              "Owner and next check"]
COMPONENT_HEADER = ["ID", "Name and type", "Responsibility", "Repository, paths, revision",
                    "Status", "How much was read",
                    "Evidence", "Current → next steps", "Boundary"]
BOUNDARY_HEADER = ["ID", "Name", "Kind", "Evidence"]
CONNECTION_HEADER = ["ID", "From", "To", "How", "Data",
                     "Waits for reply", "Identity", "State", "Evidence"]
IDENTITY_HEADER = ["ID", "Name", "Kind", "What it can reach", "Evidence"]
FLOW_HEADER = ["ID", "Entry point", "Connections in order", "Evidence"]
# A component's implementation status: the Status cell starts with one of these.
# Code is the source of truth, so the two that claim code exists need the code
# read (READ_COVERAGE above); the others say what the evidence can't establish.
STATUSES = [("🟩 Implemented", "merged to the main branch"),
            ("🟦 In development",
             "code written but not merged: an open pull request or a branch"),
            ("🟨 Planned", "in the tracker, with no code"),
            ("🟪 Vision", "only in the documentation"),
            ("⬜ Unverified", "not established: name the gap that explains it")]
CODE_STATUSES = ("🟩", "🟦")
# Each independent review round is a row of its own table, written when its
# task is submitted: the questions it raised, or REVIEW_NONE. A strict reviewer
# can keep finding something, so after a few rounds the user decides whether to
# go on; their choice to stop ends the review like a round that raised nothing,
# as a round whose Raised starts REVIEW_STOPPED.
REVIEW_HEADER = ["Round", "Raised"]
REVIEW_NONE = "No issue raised"
REVIEW_STOPPED = "Stopped by the user:"
# A finding holds one claim, of about 80 words; a claim far past that, here
# about twice it, bundles several, which are then cited and corrected as one.
# It is refused when the finding is written, so it is split before other rows
# cite it, and the final check refuses it too.
CLAIM_WORDS_MAX = 150
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
REPO_URL = re.compile(
    r"^(https?://[^/\s]+)/([\w.-]+/[\w.-]+)/(?:pull|issues|blob|tree|commit|commits)\b")
# What a reference inside them is already part of: code, links and bare URLs.
PROTECTED = re.compile(
    r"`[^`\n]*`|!?\[[^\]\n]*\]\([^)\n]*\)|!?\[[^\]\n]+\]\[[^\]\n]*\]|https?://\S+")
ANY_REFERENCE = re.compile(
    rf"{REPO_PR.pattern}|{TICKET.pattern}|{BARE_PR.pattern}")
# How to fix a row that breaks a rule, worded once for ledger.py's refusal and
# check_report.py's error.
SOURCE_LINK_FIX = ("link the Reference at its pinned revision, or, for a search, give it as "
                   '{"query": "<the exact query>"} and the script writes it')
GAP_FIX = ("Blocked by starts with one of: " + "; ".join(BLOCKERS) + ". A gap nothing blocks is a ready question in "
           "the queue: do it")
# A link, inline or by reference, or a bare URL: where a claim's trail ends.
LINK = re.compile(r"\]\(https?://[^)\s]+\)|\]\[[^\]]*\]|https?://\S+")
# A search has no URL to pin, so its exact query, between backticks, stands in.
QUERY = re.compile(r"`[^`\n]+`")
# The letters of the recorded IDs: S sources, Q questions, U scope boundaries,
# F findings, C components, D decisions, G gaps, B design boundaries,
# E connections, I identities and P flows.
ID_LETTERS = "SQUFCDGBEIP"
# An ID of the kinds a set of letters names, such as "GD": ID's own pattern.
IDS_OF = r"\b[{}]\d{{2,}}\b"
ID = re.compile(IDS_OF.format(ID_LETTERS))
# Every recorded ID has an anchor, so any citation of it can link to it: a
# table row carries an HTML anchor in its ID cell, which Markdown viewers such
# as VS Code and GitHub render. A heading's anchor would change with its title;
# these don't.
ANCHOR_ID = r"[a-z]+\d+"
ID_ANCHOR = re.compile(rf'<a id="{ANCHOR_ID}"></a>')
# The start of a table row, before its ID and the anchor that may precede it.
ROW_START = rf"^\|\s*(?:{ID_ANCHOR.pattern})?"
# Where an ID is recorded: a table row, a bold label or a heading.
RECORD_DEFINITION = re.compile(
    rf"(?:{ROW_START}|^[-*]\s+\*\*|^#{{3}}\s+)({ID.pattern})", re.M)
# A citation of a record, as the ledger stores it: a link to the record's
# anchor, which the script writes from a submission's [[F07]]. Only a citation
# refers to a record: an ID-shaped word written bare, such as P95 in "P95
# latency", is prose.
CITATION = re.compile(r"\[([A-Z]\d{2,})\]\(#[a-z]+\d+\)")


def report_headings():
    """The report's (level, title) headings, in order."""
    return [(level, title) for level, title, _ in HEADINGS]


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


# The rules below are each defined once: ledger.py applies them to a row as it
# is written, and check_report.py to the whole ledger, which also catches a
# ledger edited without the script.


def outcome_problem(row_id, outcome, question=""):
    """Why a completed question's outcome doesn't close it, or None: the
    findings that answer it, the scope boundary that leaves it out, or for a
    scope question, the boundary the user decided."""
    if question.startswith(SCOPE_QUESTION):
        if outcome.startswith(USER_DECIDED) and ids(outcome, "U"):
            return None
        return f"{row_id}: a scope question is closed by the boundary the user decided ({USER_DECIDED}U01)"
    # A question is completed by the findings that answer it, or by the scope
    # boundary that leaves it out; one a gap or a decision stops is blocked,
    # never completed.
    if ids(outcome, "F") or (outcome.startswith(OUTSIDE_SCOPE) and ids(outcome, "U")):
        return None
    return (f"{row_id}: a completed question names the findings that answer it (F01, F02) in Findings; a "
            "question a gap or a decision stops is blocked by it instead")


def scope_problem(row):
    """Why a scope boundary row breaks a rule, or None: it names a topic, the
    user's decision on it, and the question it was asked in."""
    if not row[1].strip():
        return f"{row[0]}: Topic names what was decided"
    if row[2] not in SCOPE_ANSWERS:
        return f"{row[0]}: Decision is one of: {', '.join(SCOPE_ANSWERS)}"
    if len(ids(row[3], "Q")) != 1:
        return f"{row[0]}: Asked in names the question it was asked in (Q07)"
    return None


def blocked_problem(row_id, depends_on, blocked):
    """Why a blocked question's Depends on doesn't name what blocks it, or None:
    a gap, a decision, or a question of `blocked`, the IDs of the blocked ones."""
    if ids(depends_on, "GD") or set(ids(depends_on, "Q")) & blocked:
        return None
    return (f"{row_id}: a blocked question names what blocks it in Depends on: the gap (G01), the decision "
            "(D01) or the blocked question it needs (Q03)")


def ids(text, letters):
    """The IDs in `text` of the kinds `letters` names, such as "Q" or "GD", in
    order."""
    return re.findall(IDS_OF.format(letters), text)


def claim_length_problem(ident, claim):
    """Why a finding's claim is too long, far past its length, or None."""
    words = word_count(claim)
    if words <= CLAIM_WORDS_MAX:
        return None
    return f"{ident}'s claim is {words} words; split it into findings of one claim each"


def review_problem(rounds):
    """What the review still needs, or None once a round raised no question;
    `rounds` are the review table's rows."""
    if last_review(rounds) is None:
        return "no independent review is recorded: investigate.py next hands it out once research is finished"
    if not reviewed(rounds):
        return ("the last review round raised questions: once they are done, investigate.py next hands out "
                "the next round, until one raises no question or the user chooses to stop")
    return None


def last_review(rounds):
    """What the latest review round raised, or None when no round is recorded."""
    return rounds[-1][-1].strip() if rounds else None


def reviewed(rounds):
    """Whether the review is finished: rounds repeat until one raises no
    question, since the questions a round raises change the ledger the next round
    reads. The user's choice to stop also ends it."""
    outcome = last_review(rounds)
    return outcome is not None and (outcome == REVIEW_NONE or outcome.startswith(REVIEW_STOPPED))


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
    if blocker == "Waiting on decision" and not ids(row[4], "D"):
        return f"{row[0]} waits on a decision but names none (D01...)"
    return None


def source_reference_missing(row):
    """Whether a source row's Reference holds neither a link nor a query."""
    return not LINK.search(row[2]) and not QUERY.search(row[2])


def unlinked_backticks(prose, linked_text=""):
    """The backticked spans of `prose` that sit outside a link, in order. Backticks
    mark a reference to code or a source, so each is a link to its pinned
    revision; anything else is written as plain words. A ticket key is the
    exception when nothing in `prose` or `linked_text` links a ticket of its
    project: with no site to link it to, it stays as code."""
    urls = [m[0] for m in TICKET_URL.finditer(prose + "\n" + linked_text)]
    projects = ticket_sites(urls)
    spans = [span[1:-1] for span in QUERY.findall(_strip_links(prose))]
    return [s for s in spans if not (TICKET.fullmatch(s) and project_of(s) not in projects)]


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
    """The system design's component rows, as cells."""
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


def table_cells(line, keep_anchors=False):
    """A Markdown table row's cells, trimmed; an ID without its anchor unless
    `keep_anchors`. A pipe escaped as \\| stays inside its cell, read as |."""
    cells = [c.strip().replace("\\|", "|")
             for c in CELL_PIPE.split(line.strip().strip("|"))]
    return cells if keep_anchors else [strip_anchors(c) for c in cells]


def strip_anchors(text):
    """A text without its ID anchors."""
    return ID_ANCHOR.sub("", text)


def plain(text):
    """A cell as plain text: no anchors, links as their text."""
    return link_text(strip_anchors(text))


def citation(ident):
    """The citation of the record `ident`: a link to its anchor."""
    return f"[{ident}](#{ident.lower()})"


def unrecorded_ids(body):
    """The IDs the ledger cites but never records in a table row, a bold label
    or a heading."""
    return sorted({m[1] for m in CITATION.finditer(body)} - recorded_ids(body), key=id_order)


def id_order(ident):
    """A sort key for IDs in number order: S2 before S10."""
    match = re.match(r"([A-Za-z]+)(\d+)", ident)
    return (match[1], int(match[2])) if match else (ident, 0)


def recorded_ids(body):
    """Every ID the ledger `body` records: table rows, bold labels and headings."""
    return set(RECORD_DEFINITION.findall(body))


def cited_sources(body):
    """{source number: the findings whose Sources cell names it} in the ledger `body`."""
    cited = {}
    for row in ledger_rows(body, TABLE_HEADINGS["findings"]):
        if len(row) > 2:
            for source in set(re.findall(r"\bS(\d+)\b", row[2])):
                cited.setdefault(int(source), set()).add(row[0])
    return cited


def unrecorded_citations(values, body):
    """The IDs that `values` cite and the ledger `body` doesn't record yet."""
    cited = {m[1] for v in values for m in CITATION.finditer(v)}
    return sorted(cited - recorded_ids(body), key=id_order)


def group_problem(row):
    """Why a source row's Kind cell doesn't start with the name of one of
    GROUPS, or None."""
    if group_of(row):
        return None
    return f"{row[0]}: Kind starts with one of: {', '.join(GROUPS.values())}"


def group_of(row):
    """The group of GROUPS whose name a source row's Kind cell starts with, as
    the config names it, or None."""
    return next((g for g, name in GROUPS.items() if row[1].strip().casefold().startswith(name)), None)


def coverage_problem(row):
    """Why a source row's Coverage doesn't start with one of COVERAGE, or None."""
    if any(row[4].strip().casefold().startswith(c) for c in COVERAGE):
        return None
    return (f"{row[0]}: Coverage starts with one of: {', '.join(COVERAGE)}, then any detail, such as "
            "'partial: lines 1-80 of 352'")


def superseded_problem(row):
    """Why a source row's Superseded by is neither None nor one other source,
    or None."""
    named = ids(row[6], "S")
    if row[6].strip() == "None" or (len(named) == 1 and named[0] != row[0]):
        return None
    return f"{row[0]}: Superseded by is None, or the one source that replaces it (S07)"


def source_mark(row):
    """The report's mark for a source row: "limited" unless its Coverage is
    full, "superseded" when another source replaces it, both, or None."""
    marks = [mark for mark, applies in (("limited", not row[4].strip().casefold().startswith("full")),
                                        ("superseded", row[6].strip() != "None")) if applies]
    return ", ".join(marks) or None


def finding_problem(row):
    """Why a finding row breaks a rule, or None: it holds a claim, names the
    sources it was read in, or the findings an inference rests on, and its
    limits."""
    if not row[1].strip():
        return f"{row[0]}: Claim holds the claim, in your words"
    if not ids(row[2], "SF"):
        return (f"{row[0]}: Sources names the sources the claim was read in (S03), or for an inference the "
                "findings it rests on (F02)")
    if not row[3].strip():
        return f"{row[0]}: Limits says how the claim was validated and what it leaves out"
    return None


def design_problem(name, row):
    """Why a components or system design row breaks a rule of the design, or
    None: each row rests on findings or a gap, an unverified one on the gap
    that explains it, a connection joins two components with a state and an
    identity, a flow walks connections, and a component sits in a boundary."""
    header = {"components": COMPONENT_HEADER, "boundaries": BOUNDARY_HEADER, "connections": CONNECTION_HEADER,
              "identities": IDENTITY_HEADER, "flows": FLOW_HEADER}[name]
    cell = dict(zip(header, row))
    evidence = cell["Evidence"]
    if not ids(evidence, "FG"):
        return f"{row[0]}: Evidence names the findings it rests on (F01), or the gap that explains it (G01)"
    state = cell.get("Status") or cell.get("State")
    if state and state.startswith("⬜") and not ids(evidence, "G"):
        return f"{row[0]}: an unverified row names the gap that explains it (G01) in Evidence"
    if name == "components" and not (ids(cell["Boundary"], "B") or cell["Boundary"].strip() == "None"):
        return f"{row[0]}: Boundary names the boundary it sits in (B01), or None"
    if name == "connections":
        for end in ("From", "To"):
            if len(ids(cell[end], "C")) != 1:
                return f"{row[0]}: {end} names one component (C01)"
        if not (ids(cell["Identity"], "I") or cell["Identity"].strip() in ("None", "Unknown")):
            return f"{row[0]}: Identity names the identity it uses (I01), None or Unknown"
        return status_problem(row[0], state, "State")
    if name == "flows" and not ids(cell["Connections in order"], "E"):
        return f"{row[0]}: Connections in order names the connections it uses (E01, E02)"
    return None


def status_problem(row_id, status, column="Status"):
    """Why a component's Status cell, or a connection's State, isn't one of
    STATUSES, or None."""
    if any(status.startswith(label) for label, _ in STATUSES):
        return None
    return (f"{row_id}: {column} starts with one of: "
            + "; ".join(f"{label} ({meaning})" for label, meaning in STATUSES))


def unread_components(components, sources, definitions):
    """{component ID: the paths it links} of the components whose Status
    claims code (🟩, 🟦) without a code source read at READ_COVERAGE of one of
    those paths, of a file or folder under it, or of a folder above it, which
    covers the files in it. `components` are rows (ID, ..., repository cell
    at 3, status at 4); `sources` the sources table's rows."""
    def urls(cell):
        return [url for _, _, _, url in links(cell, definitions) if url]
    read = [same_document(url) for row in sources
            if group_of(row) == "source_control" and read_enough(row)
            for url in urls(row[2])]
    found = {}
    for row in components:
        if not row[4].startswith(CODE_STATUSES):
            continue
        paths = [same_document(url) for url in urls(row[3])]
        if not any(r == p or r.startswith(p + "/") or p.startswith(r + "/") for p in paths for r in read):
            found[row[0]] = [_shown_path(p) for p in paths]
    return found


def read_in_part(row):
    """Whether a source row's Coverage says it was read only in part, so a
    finding citing it must say why the unread part can't change the claim."""
    return row[4].strip().casefold().startswith("partial")


def read_enough(row):
    """Whether a source row's Coverage says it was read at READ_COVERAGE,
    enough to establish what the code does."""
    return row[4].strip().casefold().startswith(READ_COVERAGE)


def _shown_path(path):
    """A code path as a message names it: owner/repo and the path after the revision."""
    match = re.match(r"https?://[^/]+/([^/]+/[^/]+)/blob/[^/]+/?(.*)", path)
    return f"{match[1]}: {match[2] or '/'}" if match else path


def unread_message(found):
    """What to do about components claiming code with no code read, `found`
    as unread_components returns it."""
    return (f"a component marked {' or '.join(CODE_STATUSES)} needs its code read, with Coverage "
            f"{' or '.join(READ_COVERAGE)}, in a code source of the path it links, of a file under it "
            "or of a folder above it: " + "; ".join(f"{ident} links {', '.join(paths) or 'no code'}"
                                                    for ident, paths in found.items())
            + ". Read it and record it as a source, then set the status; until then it is ⬜ Unverified")
