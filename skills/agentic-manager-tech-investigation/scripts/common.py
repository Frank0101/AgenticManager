"""What the skill's scripts share: the investigation's fixed file names, the
report's fixed structure and the ledger's, the values the ledger's cells
accept, its tables, the rules for a row that the scripts apply on write and
check_report.py at handover, the one reader of the ledger's tables, the anchors every recorded
ID carries and the links to them, the linking of tickets and pull requests,
and how to find an investigation's folder. Scripts import the shared library's
names from here, so they don't depend on the order of their imports.
"""
import os
import re
import sys
from typing import Any

# The agentic-manager-utils-lib skill, installed next to this one.
LIB_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)),
                       "..", "..", "agentic-manager-utils-lib")
sys.path.insert(0, LIB_DIR)
from agentic_manager.batch import gather  # noqa: E402,F401
from agentic_manager.config import enabled_sources, is_enabled  # noqa: E402,F401
from agentic_manager.github import NAME as GITHUB_CLI, GH_UNAVAILABLE, GhError, gh_available, gh_found, gh_hosts, gh_signed_in, pull_parts  # noqa: E402,F401
from agentic_manager.failures import stops_on_failure  # noqa: E402,F401
from agentic_manager.jira import BROWSE_URL as TICKET_URL, GROUP as JIRA_GROUP, NAME as JIRA_API, PROJECT_KEY, JiraClient, browse_url, plain_text, project_of  # noqa: E402,F401
from agentic_manager.json_path import nested  # noqa: E402,F401
from agentic_manager.output_file import read_json, target, write_output_file  # noqa: E402,F401
from agentic_manager.protocol import fill as fill_protocol  # noqa: E402,F401
from agentic_manager.output_folder import DAY_FOLDER, clear_folder, day_folder, folder_day, output_folder  # noqa: E402,F401
from agentic_manager.text import DEFINITION, FENCE, HEADING, INLINE_LINK, NAME, REFERENCE_LINK, display_date, free_name, headings, inline_links, link_definitions, link_text, links, local_link, markdown, reference_key, same_document, slug, word_count  # noqa: E402,F401
from agentic_manager.ticket_pulls import pulls_by_ticket  # noqa: E402,F401

FOLDER_NAME = "tech-investigations"
# What a ticket shows in place of its pull requests when gh can't be used.
PULLS_UNREAD = f"{GH_UNAVAILABLE}, so pull requests weren't read"
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
]
# The ledger's sections, in order, and the queue's subsections. Each title is
# named once, here: one typed differently elsewhere would leave a check reading
# an empty section.
QUEUE = "Research questions"
SCOPE = "Scope boundaries"
SOURCES = "Sources"
FINDINGS = "Findings"
DESIGN = "System design"
DECISIONS = "Open decisions"
GAPS = "Evidence gaps"
LINKS = "Links"
LEDGER_SECTIONS = [QUEUE, SCOPE, SOURCES, FINDINGS,
                   DESIGN, DECISIONS, GAPS, LINKS]
# A question is ready until someone starts it, so that after a break, or with
# work shared out, what is under way shows apart from what is waiting.
QUEUE_SUBSECTIONS = ["Ready", "In progress", "Completed", "Blocked"]
QUEUE_TABLES = ["queue-ready", "queue-in-progress",
                "queue-completed", "queue-blocked"]
# The system design, one table each under its own heading, so the design is
# recorded as rows, never pieced together from prose. They come in the order
# a diagram is read, each citing only those above it: where things live, what
# runs there, the credentials, what calls what with them, and the walks across
# those calls; so it is also the order they are written in.
DESIGN_ORDER = ["boundaries", "components",
                "identities", "connections", "flows"]
DESIGN_SUBSECTIONS = [table.capitalize() for table in DESIGN_ORDER]
# The heading each of the ledger's tables sits under, by the name ledger.py
# gives it: one place, since a heading typed differently elsewhere would
# leave a check reading an empty table.
TABLE_HEADINGS = {**{table: f"### {title}" for table, title in zip(QUEUE_TABLES, QUEUE_SUBSECTIONS)},
                  "scope": f"## {SCOPE}", "sources": f"## {SOURCES}", "findings": f"## {FINDINGS}",
                  "decisions": f"## {DECISIONS}", "gaps": f"## {GAPS}",
                  **{table: f"### {title}" for table, title in zip(DESIGN_ORDER, DESIGN_SUBSECTIONS)}}
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
# How much of a source was read: its Coverage starts with one of these, and
# the script writes it from a submission's fields, so its form never varies. A
# listing or a search hit says where to look, not what the code does, so only
# the first two count as read. A partial read names what was read
# (coverage_problem): the lines of a code file, the files of a pull request or
# a folder, the sections of a document, which with the pinned revision find it
# again however the source changes since; the report marks every source not
# read in full as limited. A source that can't be accessed, such
# as a private repository or a path not on the main branch, is still where
# the agent looked.
COVERAGE = ["full", "partial", "listing", "search hit", "can't access"]
READ_COVERAGE = ("full", "partial")
# Every read but a full one leaves a part unread, so each finding citing it
# says why the rest can't change its claim; can't access reads nothing.
PART_COVERAGE = ("partial", "listing", "search hit")
LINE_RANGE = re.compile(r"\blines? \d+\s*[-–]\s*\d+")
# The lines a Coverage names, as coverage_text() writes them, and a range or
# single line a finding cites, such as "120-160" or "95".
COVERAGE_LINES = re.compile(r"lines (\d+-\d+(?:, \d+-\d+)*)(?: of (\d+))?")
CITED_LINES = re.compile(r"(\d+)(?:\s*[-–]\s*(\d+))?")
# A file written for people beside the code, such as a README: it helps to
# read the code but isn't code, so reading it never shows what the code does.
DOC_FILE = re.compile(
    r"/(?:readme[^/]*|[^/]+\.(?:md|markdown|rst|adoc|txt))$", re.I)
# A link to code at a revision on a code host: (repository, blob or tree, ref,
# path), GitHub's …/blob/<ref>/<path> or GitLab's …/-/blob/<ref>/<path>; and a
# pull request, GitHub's …/pull/12 or GitLab's …/-/merge_requests/12, whose
# files a Coverage names from the repository's root.
CODE_LINK = re.compile(
    r"(https?://[^/]+/.+?)(?:/-)?/(blob|tree)/([^/]+)(?:/(.*))?")
PULL_LINK = re.compile(
    r"(https?://[^/]+/.+?)(?:/-)?/(?:pull|merge_requests)/\d+")
# A commit, as a pinned link names it: a branch can move, so what it shows
# today may not be what was read.
COMMIT = re.compile(r"[0-9a-f]{7,40}", re.I)
# The files a Coverage names, as coverage_text() writes them.
FILES_READ = re.compile(r"files: ([^;]*)")
FINDING_HEADER = ["ID", "Claim", "Sources", "Limits"]
# A decision's Position is the established one, or "Unresolved:" with the
# candidates and their constraints, which is what an open position is; its
# owner, as a gap's, is a role, since the report names roles, never people.
DECISION_HEADER = ["ID", "Decision", "Position",
                   "Owner and next check", "Evidence"]
# What a gap can be blocked by. Anything else is work the agent can do, so it is
# a ready question in the queue and not a gap; whether the investigation covers
# something is a scope question in the queue, so no gap waits on the user.
BLOCKERS = ("No access", "Waiting on decision")
# A gap says what is missing and why it matters; what would close it is the
# reverse of what blocks it, so it isn't written twice.
GAP_HEADER = ["ID", "Gap", "Blocked by", "Owner and next check", "Evidence"]
BLOCKED_BY = GAP_HEADER.index("Blocked by")
COMPONENT_HEADER = ["ID", "Name", "Kind", "Boundary", "Responsibility", "Repository, paths, revision",
                    "State", "In the target", "Evidence"]
# What a component is, the kind its Kind starts with: a fixed list, so every
# investigation names the same kinds alike and a diagram can draw each its way.
COMPONENT_TYPES = ("service", "application", "job", "script", "library", "store", "queue",
                   "external", "person", "role", "unknown")
# The kinds whose code isn't read, because it can't be or isn't researched:
# one is live once a finding shows it exists; whether the topic uses it yet is its connections' state.
OUTSIDE_KINDS = ("external", "person", "role")
# How a connection is made, the kind its How starts with, and whether its
# caller waits: fixed values, so connections read alike and a diagram can draw
# each kind its way; any detail follows.
CONNECTION_KINDS = ("HTTP", "queue", "file", "SDK", "in-process",
                    "command line", "UI", "unknown")
WAITS = ("yes", "no", "unknown")
# What an identity is, the kind its Kind starts with, for the same reasons.
IDENTITY_KINDS = ("service account", "cloud role", "person's access", "user session",
                  "app installation", "API key", "secret", "agent principal", "unknown")
# What a boundary groups by, the kind its Kind starts with, for the same reasons.
BOUNDARY_KINDS = ("network", "cluster", "namespace", "cloud account", "environment", "trust zone", "team",
                  "workstation", "external service")
# The kind of source a status other than code rests on: what is planned is in
# the tracker, a vision in the documentation. 🟩 and 🟦 have their own checks,
# unread_components and connection_code_problem, and ⬜ rests on what explains
# it. Only a source read full or partial (READ_COVERAGE) counts: a search hit or
# a listing says where to look, not what a page says.
STATUS_GROUPS = {"🟨": "workflow", "🟪": "documentation"}
BOUNDARY_HEADER = ["ID", "Name", "Kind", "Within", "Evidence"]
CONNECTION_HEADER = ["ID", "From", "To", "How", "Data", "Waits for reply", "Identity", "State",
                     "In the target", "Evidence"]
IDENTITY_HEADER = ["ID", "Name", "Kind", "What it can reach", "State", "In the target",
                   "Evidence"]
# An identity's State is the script's: the most advanced state of the
# connections that use it, since an identity is live once a live connection
# uses it; the agent never writes it, so it can't disagree with them. A flow's
# State is the least advanced of its verified connections', since it works
# only once every step does, naming any step left unverified.
UNUSED = "None: no connection uses it"
FLOW_HEADER = ["ID", "Entry point", "Connections in order", "State", "In the target",
               "Evidence"]
# table name: (heading it sits under, default header, ID letter)
TABLES = {
    **{table: (TABLE_HEADINGS[table], QUEUE_HEADER, "Q") for table in QUEUE_TABLES},
    "scope": (TABLE_HEADINGS["scope"], SCOPE_HEADER, "U"),
    "sources": (TABLE_HEADINGS["sources"], SOURCE_HEADER, "S"),
    "findings": (TABLE_HEADINGS["findings"], FINDING_HEADER, "F"),
    "decisions": (TABLE_HEADINGS["decisions"], DECISION_HEADER, "D"),
    "gaps": (TABLE_HEADINGS["gaps"], GAP_HEADER, "G"),
    "components": (TABLE_HEADINGS["components"], COMPONENT_HEADER, "C"),
    "boundaries": (TABLE_HEADINGS["boundaries"], BOUNDARY_HEADER, "B"),
    "connections": (TABLE_HEADINGS["connections"], CONNECTION_HEADER, "E"),
    "identities": (TABLE_HEADINGS["identities"], IDENTITY_HEADER, "I"),
    "flows": (TABLE_HEADINGS["flows"], FLOW_HEADER, "P"),
}
# A component's or a connection's state: its State cell starts with one of these.
# Code is the source of truth, so the two that claim code exists need the code
# read (READ_COVERAGE above); the others say what the evidence can't establish.
# A row found not to exist is kept as ruled out, not removed, since a question
# that checked it may cite it; it counts for no identity's or flow's state.
STATUSES = [("🟩 Live", "merged to the main branch, or, for an external part, a person, a role or a part of a mention-only topic, shown to exist"),
            ("🟦 In development",
             "code written but not merged: an open pull request or a branch"),
            ("🟨 Planned", "in the tracker, with no code"),
            ("🟪 Vision", "only in the documentation"),
            ("⬜ Unverified", "not established: name the gap, or the scope decision, that explains it"),
            ("✖ Ruled out", "shown not to exist today, whether never built or since removed: the finding showing it is in its evidence")]
CODE_STATUSES = ("🟩", "🟦")
UNVERIFIED, RULED_OUT = STATUSES[-2][0], STATUSES[-1][0]
# The statuses with what each means, as the protocol and the errors list them.
STATUS_MEANINGS = "; ".join(
    f"{label} ({meaning})" for label, meaning in STATUSES)
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
# The code host, as code_host() found it: asked of gh once per run.
CODE_HOST = {}
# What a reference inside them is already part of: code, links and bare URLs.
PROTECTED = re.compile(
    r"`[^`\n]*`|!?\[[^\]\n]*\]\([^)\n]*\)|!?\[[^\]\n]+\]\[[^\]\n]*\]|https?://\S+")
ANY_REFERENCE = re.compile(
    rf"{REPO_PR.pattern}|{TICKET.pattern}|{BARE_PR.pattern}")
# How to fix a row that breaks a rule, worded once for ledger.py's refusal and
# check_report.py's error.
SOURCE_LINK_FIX = ("link the Reference at its pinned revision, or, for a search, give it as "
                   '{"query": "<the exact query>"} and the script writes it')
GAP_FIX = ("Blocked by starts with one of: " + "; ".join(BLOCKERS) + ", naming the decision it waits on (D01). A gap "
           "nothing blocks is a ready question in the queue: do it")
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
# Where an ID is recorded: the first cell of a table row, the one form
# ledger.py writes a record in.
RECORD_DEFINITION = re.compile(rf"{ROW_START}({ID.pattern})", re.M)
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
    as code. A pull request links to code_host(); a bare #123, or any while
    there is no code host, can't be resolved."""
    sites = ticket_sites(definitions.values())
    unresolved = []

    def ticket(match):
        site = sites.get(match[1]) or (site_of(match[1]) if site_of else None)
        if site is None:
            return f"`{match[0]}`"
        return f"[{match[0]}]({browse_url(site, match[0])})"

    def pull(match):
        host = code_host()
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


def code_host():
    """The address of the code host pull requests link to, such as
    https://github.com, or None: the one host gh is signed in to, with the
    github-cli source enabled. Asked once, when the first pull request is
    linked; never hard-coded, so a GitHub Enterprise site works alike. Raises
    GhError when gh fails, which stops the write."""
    if "host" not in CODE_HOST:
        hosts = gh_hosts() if gh_available() else []
        CODE_HOST["host"] = f"https://{hosts[0]}" if len(hosts) == 1 else None
    return CODE_HOST["host"]


def unresolved_message(unresolved):
    """Why pull requests couldn't be linked, and how to fix them: a bare #123
    names no repository; owner/repo#123 needs the code host."""
    bare = [u for u in dict.fromkeys(unresolved) if u.startswith("#")]
    hostless = [u for u in dict.fromkeys(unresolved) if not u.startswith("#")]
    reasons = []
    if bare:
        reasons.append(f"{', '.join(bare)}: a pull request names its repository, as owner/repo#123, also in a "
                       "range")
    if hostless:
        reasons.append(f"{', '.join(hostless)}: a pull request links to the host gh is signed in to, so it needs "
                       "the github-cli source enabled and gh signed in to one host (gh auth status)")
    return "; ".join(reasons)


# The rules below are each defined once: ledger.py applies them to a row as it
# is written, and check_report.py to the whole ledger, which also catches a
# ledger edited without the script.


def row_problem(name, row, evidence, blocked):
    """Why a row of the ledger table `name` breaks a rule of its table, or
    None: the one list of which rules each table's rows meet, for the row
    written and for the ledger handed over alike. `evidence` is the ledger as
    design_evidence() reads it, `blocked` the IDs of the blocked questions."""
    if name in DESIGN_ORDER:
        return design_row_problem(name, row, evidence)
    if name == "findings":
        sources = evidence["sources"]
        partial = {ident for ident, source in sources.items()
                   if read_in_part(source)}
        return (finding_problem(row) or partial_read_problem(row, partial)
                or unread_lines_problem(row, sources))
    if name == "gaps":
        return gap_problem(row) or cited_evidence_problem(row[0], row[GAP_HEADER.index("Evidence")])
    if name == "decisions":
        return cited_evidence_problem(row[0], row[DECISION_HEADER.index("Evidence")])
    if name == "scope":
        return scope_problem(row)
    # The trail from a claim to its source ends in a link, or, for a search,
    # which has no URL to pin, in its exact query between backticks.
    if name == "sources":
        return source_problem(row, evidence["definitions"])
    if name == "queue-completed":
        return outcome_problem(row[0], row[-1], row[2], evidence["scope"])
    if name == "queue-blocked":
        return blocked_problem(row[0], row[QUEUE_HEADER.index("Depends on")], blocked)
    return None


def partial_read_problem(row, partial):
    """Why a finding row doesn't say, for each source it cites that was read
    only in part, why the unread part can't change its claim, or None;
    `partial` holds the IDs of the sources read in part."""
    missing = unexplained_partial_reads(row, partial)
    if not missing:
        return None
    return (f"{row[0]}: cites {', '.join(missing)}, read only in part, and its Limits doesn't say why the unread "
            f"part can't change the claim ({missing[0]} read in part: …): read the rest, or give the reason in "
            f"partial, for {', '.join(missing)}")


def unexplained_partial_reads(row, partial):
    """The sources a finding row cites, of those read only in part (`partial`,
    their IDs), whose Limits doesn't give the reason the unread part can't
    change the claim, as "S01 read in part: …", the form partial_limits()
    writes it in."""
    limits = plain(row[3])
    return [s for s in dict.fromkeys(ids(row[2], "S"))
            if s in partial and not re.search(rf"\b{s} read in part: [^\s.]", limits)]


def unread_lines_problem(row, sources):
    """Why a finding row cites lines of a source that its Coverage doesn't
    include, or None; `sources` is {ID: row}."""
    cell = plain(row[2])
    cited = list(re.finditer(IDS_OF.format("S"), cell))
    for number, match in enumerate(cited):
        source = sources.get(match[0])
        if source is None:
            continue
        coverage = coverage_fields(plain(source[4]))
        if coverage["read"] != "partial" or not coverage.get("lines"):
            continue
        after = cell[match.end():cited[number + 1].start()
                     if number + 1 < len(cited) else len(cell)]
        spans = [(int(first), int(last or first)) for first, last in CITED_LINES.findall(
            " ".join(m[1] for m in re.finditer(r"\blines? ([\d\s,–-]+)", after)))]
        unread = [f"{first}-{last}" if last != first else str(first) for first, last in spans
                  if not any(a <= first and last <= b for a, b in coverage["lines"])]
        if unread:
            return (f"{row[0]}: cites lines {', '.join(unread)} of {match[0]}, which its Coverage doesn't include: "
                    "read them and submit the source again with them, or cite only the lines read")
    return None


def coverage_fields(text):
    """The fields of a Coverage as the ledger writes it: its read, then each
    part it named, so a source read again can add to it and a finding's cited
    lines can be checked against it."""
    read, _, rest = text.partition(": ")
    fields: dict[str, Any] = {"read": read.strip()}
    for part in rest.split("; ") if rest else []:
        if match := COVERAGE_LINES.fullmatch(part):
            fields["lines"] = [[int(n) for n in span.split("-")]
                               for span in match[1].split(", ")]
            if match[2]:
                fields["of"] = int(match[2])
        elif part.startswith(("sections: ", "files: ")):
            name, _, items = part.partition(": ")
            fields[name] = items.split(", ")
    return fields


def design_row_problem(name, row, evidence):
    """Why a system design row breaks a rule of the design, or None: every
    rule a row of the table `name` meets, given `evidence`, the ledger as
    design_evidence() reads it. The one entry point, for the row written and
    for the ledger handed over alike."""
    findings, sources = evidence["findings"], evidence["sources"]
    definitions = evidence["definitions"]
    return (design_problem(name, row, evidence["scope"])
            or row_evidence_problem(name, row, findings, sources)
            or (name == "components" and (component_pin_problem(row, definitions)
                                          or unread_problem(row, evidence)))
            or (name == "connections" and (connection_code_problem(row, findings, sources, definitions)
                                           or connection_scope_problem(row, evidence["components"],
                                                                       mention_only_ids(evidence["scope"]))
                                           or connection_ruled_out_problem(row, evidence["components"])))
            or (name == "flows" and (flow_ruled_out_problem(row, evidence["connections"])
                                     or flow_order_problem(row, list(evidence["connections"].values()))))
            or None)


def unread_problem(row, evidence):
    """Why a component claiming code has none of it read, or None: the rule
    unread_components() applies, to one row, given `evidence` as
    design_evidence() reads it."""
    unread = unread_components([row], evidence["findings"], evidence["sources"], evidence["definitions"],
                               mention_only_ids(evidence["scope"]))
    return f"{row[0]}: {unread_message(unread)}" if unread else None


def design_evidence(body):
    """What the rules of a design row read in the ledger `body`: its
    findings, sources, components and connections, each {ID: row}, its scope
    decisions, {U01: decision}, and its link definitions."""
    def by_id(table):
        return {row[0]: row for row in records(body, table)}
    return {"findings": by_id("findings"), "sources": by_id("sources"), "components": by_id("components"),
            "connections": by_id("connections"), "scope": scope_answers(records(body, "scope")),
            "definitions": link_definitions(body)}


def scope_answers(scope):
    """{scope decision ID: the user's decision} of the scope rows `scope`."""
    return {row[0]: row[2] for row in scope}


def outcome_problem(row_id, outcome, question, scope):
    """Why a completed question's outcome doesn't close it, or None: the
    findings that answer it, the scope boundary that leaves it out, or for a
    scope question, the boundary the user decided. `scope` is {scope decision
    ID: the user's decision}."""
    if question.startswith(SCOPE_QUESTION):
        if outcome.startswith(USER_DECIDED) and ids(outcome, "U"):
            return None
        return f"{row_id}: a scope question is closed by the boundary the user decided ({USER_DECIDED}U01)"
    # A question is completed by the findings that answer it, or by the scope
    # boundary that leaves it out; one a gap or a decision stops is blocked,
    # never completed.
    if outcome.startswith(OUTSIDE_SCOPE):
        if any(leaves_out(scope, u) for u in ids(outcome, "U")):
            return None
        return f"{row_id}: a question outside the scope cites the scope boundary decided as mention only or exclude (U01)"
    if ids(outcome, "F"):
        return None
    return (f"{row_id}: a completed question names the findings that answer it (F01, F02) in Findings; a "
            "question a gap or a decision stops is blocked by it instead")


def leaves_out(scope, ident):
    """Whether the scope decision `ident` leaves its topic out of the
    research, decided as mention only or exclude; `scope` is {scope decision
    ID: the user's decision}."""
    return scope.get(ident) in LEFT_OUT


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


def backtick_error(where, spans):
    """The error for references in backticks outside a link."""
    return (f"{where}: references in backticks without a link: {listed([f'`{s}`' for s in spans])}. "
            "Link each to its pinned revision, or write it as plain words")


def listed(items):
    """`items` for a message: the first six, then how many more."""
    return ", ".join(items[:6]) + (f" and {len(items) - 6} more" if len(items) > 6 else "")


def gap_problem(row):
    """Why a gap row's Blocked by isn't allowed, and how to fix it, or None. A
    gap nothing blocks is work to do now, so it belongs in the queue; a
    decision must be named."""
    blocked_by = row[BLOCKED_BY]
    blocker = next(
        (b for b in BLOCKERS if blocked_by.lower().startswith(b.lower())), None)
    if blocker is None:
        return f"{row[0]} is blocked by '{blocked_by}'. {GAP_FIX}"
    if blocker == "Waiting on decision" and not ids(blocked_by, "D"):
        return f"{row[0]} waits on a decision but names none. {GAP_FIX}"
    return None


def cited_evidence_problem(row_id, evidence):
    """Why a gap's or a decision's Evidence doesn't trace it to the ledger,
    or None: it names the findings or sources it rests on, so what is
    established and how authoritative it is come from them."""
    if ids(evidence, "FS"):
        return None
    return f"{row_id}: Evidence names the findings or sources it rests on (F01, S01)"


def source_problem(row, definitions):
    """Why a source row breaks a rule, or None: its group, its coverage, what
    supersedes it, the revision its code link pins, and a reference that
    links it, or for a search, its exact query. `definitions` are the
    ledger's link definitions."""
    return (group_problem(row) or coverage_problem(row) or superseded_problem(row)
            or source_pin_problem(row, definitions)
            or (f"{row[0]}: {SOURCE_LINK_FIX}" if source_reference_missing(row) else None))


def source_reference_missing(row):
    """Whether a source row's Reference holds no link and isn't a search's
    query: a search, the one source whose Coverage is a search hit, is its
    query between backticks; any other text in backticks links nothing."""
    is_query = QUERY.fullmatch(
        row[2].strip()) and row[4].strip().startswith("search hit")
    return not LINK.search(without_code(row[2])) and not is_query


def without_code(text):
    """`text` with its code spans blanked, for a check that looks for links:
    brackets between backticks, such as a query's `PROJ-6[0-9][0-9]`, are code,
    as a Markdown renderer shows them, never a link."""
    return QUERY.sub(" ", text)


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


def records(body, table):
    """The rows of the ledger table `table` in `body` that are records, IDs
    of its letter with all its cells, leaving out placeholder rows."""
    heading, header, letter = TABLES[table]
    return [row for row in ledger_rows(body, heading)
            if re.fullmatch(rf"{letter}\d+", row[0]) and len(row) == len(header)]


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
    """The IDs the ledger cites but never records in a table row."""
    return sorted({m[1] for m in CITATION.finditer(body)} - recorded_ids(body), key=id_order)


def id_order(ident):
    """A sort key for IDs in number order: S2 before S10."""
    match = re.match(r"([A-Za-z]+)(\d+)", ident)
    return (match[1], int(match[2])) if match else (ident, 0)


def recorded_ids(body):
    """Every ID the ledger `body` records in a table row."""
    return set(RECORD_DEFINITION.findall(body))


def cited_sources(body):
    """{source ID: the findings whose Sources cell cites it} in the ledger `body`."""
    cited = {}
    for row in records(body, "findings"):
        for source in ids(row[2], "S"):
            cited.setdefault(source, set()).add(row[0])
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
    """Why a source row's Coverage breaks the rule COVERAGE states, or None:
    it starts with one of COVERAGE, and a partial read names what was read,
    the lines or files of code, the sections of a document or a ticket."""
    if not any(row[4].strip().casefold().startswith(c) for c in COVERAGE):
        return (f"{row[0]}: Coverage starts with one of: {', '.join(COVERAGE)}, then any detail, such as "
                "'partial: lines 1-80, 200-240 of 352'")
    if not row[4].strip().casefold().startswith("partial"):
        return None
    if group_of(row) == "source_control" and not (LINE_RANGE.search(row[4]) or "files:" in row[4]):
        return (f'{row[0]}: Coverage partial of code names the lines read, "lines": [[1, 80]], or for a '
                'pull request or a folder the files read, "files": [...]')
    if group_of(row) in ("documentation", JIRA_GROUP) and "sections:" not in row[4]:
        return (f'{row[0]}: Coverage partial of a document or a ticket names the sections read, '
                '"sections": ["Description", "Comments"]')
    return None


def superseded_problem(row):
    """Why a source row's Superseded by is neither None nor one other source,
    or None."""
    named = ids(row[6], "S")
    if row[6].strip() == "None" or (len(named) == 1 and named[0] != row[0]):
        return None
    return f"{row[0]}: Superseded by is None, or the one source that replaces it (S07)"


def finding_problem(row):
    """Why a finding row breaks a rule, or None: it holds a claim, names the
    sources it was read in, or the findings an inference rests on, and its
    limits, or None."""
    if not row[1].strip():
        return f"{row[0]}: Claim holds the claim, in your words"
    if not ids(row[2], "SF"):
        return (f"{row[0]}: Sources names the sources the claim was read in (S03), or for an inference the "
                "findings it rests on (F02)")
    if not row[3].strip():
        return f"{row[0]}: Limits says what the claim leaves out, or None"
    return None


def design_problem(name, row, scope):
    """Why a components or system design row breaks a rule of the design, or
    None: each row rests on findings, a gap, an open decision or a decision
    leaving its topic mention only, an unverified one on the gap or the
    mention-only decision that explains it, a ruled-out one on the finding
    that shows it doesn't exist, and none draws what the user
    excluded; a component, a connection, an identity and a flow say how the
    target changes them; a component, a boundary and an identity start their
    Kind with one of their kinds; a component and a boundary name the boundary
    they sit in, or None; an identity names the components it can reach; a
    connection joins two components with a state, an identity, a How of its
    kinds and whether it waits; and a flow walks connections. `scope` is
    {scope decision ID: the user's decision}: an included topic is researched
    like the rest, so its decision explains nothing."""
    cell = dict(zip(TABLES[name][1], row))
    evidence = cell["Evidence"]
    decided = ids(evidence, "U")
    if excluded := [u for u in decided if scope.get(u) == SCOPE_ANSWERS[2]]:
        return (f"{row[0]}: cites {', '.join(excluded)}, which the user excluded from the report: draw nothing "
                "of it")
    left_out = [u for u in decided if scope.get(u) == SCOPE_ANSWERS[1]]
    if not ids(evidence, "FGD") and not left_out:
        return (f"{row[0]}: Evidence names the findings it rests on (F01), or the gap (G01), open decision (D01) "
                "or the scope decision leaving its topic mention only (U01) that explains it")
    # An identity's or a flow's State is the script's, from its connections.
    state = cell.get("State") if name in (
        "components", "connections") else None
    if state is not None and (wrong := status_problem(row[0], state)):
        return wrong
    # Live or in development rests on a finding: code read, or for what has
    # no code of its own, one that shows it exists.
    if state and state.startswith(CODE_STATUSES) and not ids(evidence, "F"):
        return f"{row[0]}: a {state.split(':')[0]} row names in Evidence the finding that shows it (F01)"
    if state and state.startswith(RULED_OUT) and not ids(evidence, "F"):
        return f"{row[0]}: a {RULED_OUT} row names in Evidence the finding that shows it doesn't exist (F01)"
    if state and state.startswith(UNVERIFIED) and not (ids(evidence, "G") or left_out):
        return (f"{row[0]}: an unverified row names the gap (G01), or the scope decision leaving its topic "
                "mention only (U01), that explains it in Evidence")
    target = cell.get("In the target")
    if target is not None and target.strip() != "Unchanged" and not ids(target, "FGDU"):
        return (f"{row[0]}: In the target says how the target changes it, citing the evidence (F01, D01), "
                "or Unchanged")
    if name == "components":
        if not starts_with_one(cell["Kind"], COMPONENT_TYPES):
            return f"{row[0]}: Kind starts with one of: {', '.join(COMPONENT_TYPES)}, then any detail"
        if not (ids(cell["Boundary"], "B") or cell["Boundary"].strip() == "None"):
            return f"{row[0]}: Boundary names the boundary it sits in (B01), or None"
    if name == "boundaries":
        within = ids(cell["Within"], "B")
        if not (within or cell["Within"].strip() == "None") or row[0] in within:
            return f"{row[0]}: Within names the boundary it sits in (B01), another than itself, or None"
        if not starts_with_one(cell["Kind"], BOUNDARY_KINDS):
            return f"{row[0]}: Kind starts with one of: {', '.join(BOUNDARY_KINDS)}, then any detail"
    if name == "identities" and not starts_with_one(cell["Kind"], IDENTITY_KINDS):
        return f"{row[0]}: Kind starts with one of: {', '.join(IDENTITY_KINDS)}, then any detail"
    if name == "identities" and not ids(cell["What it can reach"], "C"):
        return (f"{row[0]}: What it can reach names the components it can reach, such as \"Retrieve on C03\", "
                "so the diagram can show what each credential touches")
    if name == "connections":
        for end in ("From", "To"):
            if len(ids(cell[end], "C")) != 1:
                return f"{row[0]}: {end} names one component (C01)"
        if not (ids(cell["Identity"], "I") or cell["Identity"].strip() in ("None", "Unknown")):
            return f"{row[0]}: Identity names the identity it uses (I01), None or Unknown"
        if not starts_with_one(cell["How"], CONNECTION_KINDS):
            return f"{row[0]}: How starts with one of: {', '.join(CONNECTION_KINDS)}, then any detail"
        if not starts_with_one(cell["Waits for reply"], WAITS):
            return f"{row[0]}: Waits for reply starts with {', '.join(WAITS)}, then any detail"
        return None
    if name == "flows" and not ids(cell["Connections in order"], "E"):
        return f"{row[0]}: Connections in order names the connections it uses (E01, E02)"
    return None


def starts_with_one(text, words):
    """Whether `text` starts with one of `words`, whole, in any case."""
    return any(re.match(rf"{re.escape(word)}(?![\w-])", text.strip(), re.I) for word in words)


def status_problem(row_id, status):
    """Why a component's or a connection's State isn't one of
    STATUSES, or None."""
    if status_rank(status) is not None:
        return None
    return f"{row_id}: State starts with one of: {STATUS_MEANINGS}"


def status_rank(text):
    """The index in STATUSES of the status `text` starts with, or None."""
    return next((i for i, (label, _) in enumerate(STATUSES) if text.strip().startswith(label)), None)


def row_evidence_problem(name, row, findings, sources):
    """Why a component's or a connection's State claims what its
    evidence doesn't reach, or None for any other row. `findings` and
    `sources` are {ID: row}."""
    if name not in ("components", "connections"):
        return None
    cell = dict(zip(TABLES[name][1], row))
    return evidence_problem(row[0], cell["State"], cell["Evidence"], findings, sources)


def evidence_problem(row_id, status, evidence, findings, sources):
    """Why a design row's status claims what its evidence doesn't reach, or
    None: a 🟨 Planned row needs a finding read in the tracker, a 🟪 Vision row
    one read in the documentation, a conclusion followed to the findings it
    rests on. `findings` and `sources` are {ID: row}."""
    group = next((g for mark, g in STATUS_GROUPS.items()
                 if status.strip().startswith(mark)), None)
    if group is None or group in groups_reached(ids(evidence, "F"), findings, sources):
        return None
    return (f"{row_id}: State {status.strip().split(':')[0]} needs a finding read in the {GROUPS[group]} "
            f"among its evidence, from a source read {' or '.join(READ_COVERAGE)}")


def groups_reached(cited, findings, sources):
    """The source groups the findings `cited` were read in, following a
    conclusion to the findings it rests on: of the sources read at
    READ_COVERAGE only."""
    return {group_of(row) for row in sources_reached(cited, findings, sources) if read_enough(row)}


def sources_reached(cited, findings, sources):
    """The source rows the findings `cited` rest on, following a conclusion
    to the findings it rests on: the trail from a design row's evidence to
    what was read. `findings` and `sources` are {ID: row}."""
    reached, seen, todo = {}, set(), list(cited)
    while todo:
        ident = todo.pop()
        if ident in seen or ident not in findings:
            continue
        seen.add(ident)
        cell = findings[ident][2]
        todo += ids(cell, "F")
        reached |= {s: sources[s] for s in ids(cell, "S") if s in sources}
    return [reached[s] for s in sorted(reached, key=id_order)]


def connection_code_problem(row, findings, sources, definitions):
    """Why a connection whose State claims code (🟩, 🟦) has no code read
    among its evidence, or None: a call is made by code, so at least one code
    source read at READ_COVERAGE, not a README or another DOC_FILE, is
    reached through its findings. `findings` and `sources` are {ID: row}."""
    cell = dict(zip(CONNECTION_HEADER, row))
    if not cell["State"].startswith(CODE_STATUSES):
        return None
    reached = sources_reached(ids(cell["Evidence"], "F"), findings, sources)
    if any(code_read(source, definitions) for source in reached):
        return None
    return (f"{row[0]}: State {cell['State'].split(':')[0]} needs a finding read in the code among its evidence, "
            f"from a code source read {' or '.join(READ_COVERAGE)} that isn't a README or another document; "
            "until one is read it is ⬜ Unverified")


def connection_scope_problem(row, components, mention_only):
    """Why a connection to or from a part of a mention-only topic doesn't
    cite that scope decision, or None: the user chose not to research it, so
    each connection to it says so. `components` is {ID: row}, `mention_only`
    the IDs of the mention-only decisions."""
    cell = dict(zip(CONNECTION_HEADER, row))
    cited = set(ids(cell["Evidence"], "U"))
    evidence = COMPONENT_HEADER.index("Evidence")
    for end in ("From", "To"):
        for component in ids(cell[end], "C"):
            decided = [u for u in ids(components.get(component, [""] * len(COMPONENT_HEADER))[evidence], "U")
                       if u in mention_only and u not in cited]
            if decided:
                return (f"{row[0]}: {end} {component} is a part of a topic decided as mention only, so the "
                        f"connection cites {', '.join(decided)} in Evidence too")
    return None


def component_pin_problem(row, definitions):
    """Why a component's code links a branch, not a commit, or None: a link to
    code at a revision (CODE_LINK) names the commit, 7 or more hex
    characters, since a branch moves and what it shows later may not be what
    was read."""
    code = COMPONENT_HEADER.index("Repository, paths, revision")
    for url in link_urls(row[code], definitions):
        if (match := CODE_LINK.fullmatch(url)) and not COMMIT.fullmatch(match[3]):
            return (f"{row[0]}: Repository, paths, revision links code at {match[3]}: link it at the commit it was "
                    "read at, 7 or more hex characters")
    return None


def source_pin_problem(row, definitions):
    """Why a code source's link names a branch, not a commit, or another
    revision than its Revision, or None: the link pins what was read, so it
    names the same commit, as component_pin_problem() requires; either may be
    the other's short form."""
    if group_of(row) != "source_control":
        return None
    revision = source_revision(row)
    for url in link_urls(row[2], definitions):
        if (match := CODE_LINK.fullmatch(url)) and not COMMIT.fullmatch(match[3]):
            return (f"{row[0]}: Reference links code at {match[3]}: link it at the commit it was read at, 7 or more "
                    "hex characters")
        if match and not same_revision(match[3], revision):
            return (f"{row[0]}: Reference links code at {match[3]}, Revision is {row[3].strip()}: link it at the "
                    "commit in Revision")
    return None


def source_revision(row):
    """The commit a source row's Revision names, or the cell itself when it
    names none, such as a page's date."""
    match = COMMIT.search(row[3])
    return match[0] if match else row[3].strip()


def same_revision(one, other):
    """Whether two revisions name the same commit: equal, or one the short
    form of the other."""
    one, other = one.casefold(), other.casefold()
    return bool(one and other) and (one.startswith(other) or other.startswith(one))


def link_urls(cell, definitions):
    """The URLs a cell links, inline or by reference, each without its
    #fragment or query, so a link to a line of a file is the file."""
    return [url.split("#")[0].split("?")[0].rstrip("/") for _, _, _, url in links(cell, definitions) if url]


def identity_states(connections):
    """{identity ID: its State} from the connection rows that use it: the
    most advanced of their states."""
    ranks, found = connection_ranks(connections), {}
    for row in connections:
        if (rank := ranks.get(row[0])) is None:
            continue
        for identity in ids(dict(zip(CONNECTION_HEADER, row))["Identity"], "I"):
            found[identity] = min(rank, found.get(identity, rank))
    return {ident: STATUSES[rank][0] for ident, rank in found.items()}


def flow_states(flows, connections):
    """{flow ID: its State} from the flow rows and the connections they walk:
    the least advanced state of those verified, then the unverified ones in
    the flow's order, so a step left unverified, such as one from a mention-only topic,
    doesn't hide how far along the rest is; ⬜ Unverified when none is."""
    ranks = connection_ranks(connections)
    unverified = [label for label, _ in STATUSES].index(UNVERIFIED)
    found = {}
    for row in flows:
        walked = [e for e in dict.fromkeys(ids(row[2], "E")) if e in ranks]
        verified = [ranks[e] for e in walked if ranks[e] != unverified]
        unknown = [e for e in walked if ranks[e] == unverified]
        if not walked:
            continue
        if not verified:
            found[row[0]] = STATUSES[unverified][0]
            continue
        found[row[0]] = STATUSES[max(verified)][0] + \
            (f", unverified: {', '.join(unknown)}" if unknown else "")
    return found


def connection_ranks(connections):
    """{connection ID: the index of its State in STATUSES}, for the rows
    whose State is one of them other than ruled out: a connection that
    doesn't exist makes no identity or flow any more advanced."""
    ranks = {row[0]: status_rank(dict(zip(CONNECTION_HEADER, row)).get("State", ""))
             for row in connections}
    return {ident: rank for ident, rank in ranks.items() if rank not in (None, status_rank(RULED_OUT))}


def connection_ruled_out_problem(row, components):
    """Why a connection to or from a ruled-out component isn't ruled out
    itself, or None: nothing connects to a part that doesn't exist.
    `components` is {ID: row}."""
    cell = dict(zip(CONNECTION_HEADER, row))
    if cell["State"].startswith(RULED_OUT):
        return None
    state = COMPONENT_HEADER.index("State")
    for end in ("From", "To"):
        for component in ids(cell[end], "C"):
            if component in components and components[component][state].startswith(RULED_OUT):
                return (f"{row[0]}: {end} {component} is {RULED_OUT}, so the connection is {RULED_OUT} too, "
                        "citing the finding that shows it, or left out")
    return None


def flow_ruled_out_problem(row, connections):
    """Why a flow walks a ruled-out connection, or None: a flow lists the
    steps that happen. `connections` is {ID: row}."""
    state = CONNECTION_HEADER.index("State")
    ruled_out = [e for e in ids(row[2], "E")
                 if e in connections and connections[e][state].startswith(RULED_OUT)]
    if ruled_out:
        return (f"{row[0]}: {', '.join(ruled_out)} {'is' if len(ruled_out) == 1 else 'are'} {RULED_OUT}: "
                "list only the connections the flow uses")
    return None


def flow_order_problem(row, connections):
    """Why a flow's connections are out of order, or None: each after the
    first starts from or ends at a component the flow has already reached.
    Either end will do, since a part that fetches, such as a consumer reading
    a queue or a controller watching resources, joins the flow by calling a
    component it has reached."""
    rows = {row[0]: row for row in connections}
    reached = set()
    for ident in ids(row[2], "E"):
        if ident not in rows:
            continue
        cell = dict(zip(CONNECTION_HEADER, rows[ident]))
        start, end = ids(cell["From"], "C"), ids(cell["To"], "C")
        if reached and not set(start + end) & reached:
            return (f"{row[0]}: {ident} runs from {', '.join(start)} to {', '.join(end)}, neither of which the flow "
                    "has reached yet: list its connections in the order they happen, adding any step that "
                    "links them")
        reached |= set(start) | set(end)
    return None


def mention_only_ids(scope):
    """The IDs of the scope decisions `scope`, {ID: decision} as
    scope_answers() gives them, whose decision is mention only."""
    return {ident for ident, decision in scope.items() if decision == SCOPE_ANSWERS[1]}


def unread_components(components, findings, sources, definitions, mention_only=()):
    """{component ID: the paths it links} of the components whose State
    claims code (🟩, 🟦) without a code source among those its Evidence's
    findings rest on that read, at READ_COVERAGE, one of those paths, a file
    or folder under it, or, read in full, a folder above it; a README or other
    DOC_FILE isn't code. An external part, a person or a role has no code
    the design reads, and a part of a mention-only topic, citing its scope
    decision, one of `mention_only`, has its code left unread: a finding
    shows it exists. `components` are the table's rows, `findings` and
    `sources` {ID: row}."""
    found = {}
    state, code = COMPONENT_HEADER.index("State"), COMPONENT_HEADER.index(
        "Repository, paths, revision")
    kind, evidence = COMPONENT_HEADER.index(
        "Kind"), COMPONENT_HEADER.index("Evidence")
    for row in components:
        if not row[state].startswith(CODE_STATUSES) or starts_with_one(row[kind], OUTSIDE_KINDS) \
                or set(ids(row[evidence], "U")) & set(mention_only):
            continue
        read = [entry for source in sources_reached(ids(row[evidence], "F"), findings, sources)
                for entry in code_read(source, definitions)]
        paths = link_urls(row[code], definitions)
        if not any(_covers(entry, path) for path in paths for entry in read):
            found[row[0]] = [_shown_path(p) for p in paths]
    return found


def code_read(row, definitions):
    """[(repository, revision, path, whole)] of the code a source row read at
    READ_COVERAGE, or [] for a source of another group or not read enough: a
    file, or a folder, `whole` when read in full, so it covers the files in
    it. A folder or a pull request read file by file covers only the files its
    Coverage names: a folder's under its path, a pull request's from its
    repository's root at the source's Revision. A README or other DOC_FILE
    isn't code. Any other link is itself, with no revision."""
    if group_of(row) != "source_control" or not read_enough(row):
        return []
    full = row[4].strip().casefold().startswith("full")
    match = FILES_READ.search(row[4])
    files = [f.strip() for f in match[1].split(",")
             if f.strip()] if match else []
    read = []
    for url in link_urls(row[2], definitions):
        if DOC_FILE.search(url):
            continue
        pull, code = PULL_LINK.fullmatch(url), CODE_LINK.fullmatch(url)
        if code:
            repo, revision, base = code[1], code[3], code[4] or ""
            whole = [] if files else [
                (base, full)] if code[2] == "blob" or full else []
        elif pull:
            repo, revision, base, whole = pull[1], source_revision(row), "", []
        else:
            read.append((same_document(url), None, None, False))
            continue
        entries = [(repo.casefold(), revision, path.strip("/"), covers_all)
                   for path, covers_all in [(f"{base}/{f}", False) for f in files] + whole
                   if not DOC_FILE.search("/" + path.strip("/"))]
        read += entries
        if pull and (entries or not files):
            read.append((same_document(url), None, None, False))
    return read


def _covers(entry, link):
    """Whether the code read `entry`, as code_read() gives it, covers the
    component's code `link`: the same path at the same revision, a file under
    it, or a folder above it read whole."""
    repo, revision, path, whole = entry
    if revision is None:
        return repo == same_document(link)
    code = CODE_LINK.fullmatch(link)
    if not code or code[1].casefold() != repo or not same_revision(code[3], revision):
        return False
    target = (code[4] or "").strip("/")
    return (path == target or not target or path.startswith(target + "/")
            or (whole and (not path or target.startswith(path + "/"))))


def read_in_part(row):
    """Whether a source row's Coverage leaves part of it unread (partial,
    listing or search hit), so a finding citing it must say why the unread part
    can't change the claim."""
    return row[4].strip().casefold().startswith(PART_COVERAGE)


def read_enough(row):
    """Whether a source row's Coverage says it was read at READ_COVERAGE,
    enough to establish what the code does."""
    return row[4].strip().casefold().startswith(READ_COVERAGE)


def _shown_path(path):
    """A code path as a message names it: owner/repo and the path after the revision."""
    match = CODE_LINK.fullmatch(path)
    return f"{match[1].split('/', 3)[-1]}: {match[4] or '/'}" if match else path


def unread_message(found):
    """What to do about components claiming code with no code read, `found`
    as unread_components returns it."""
    return (f"a component marked {' or '.join(CODE_STATUSES)} needs its code read, with Coverage "
            f"{' or '.join(READ_COVERAGE)}, in a code source its Evidence's findings cite, at the commit it links, of the path it "
            "links, of a file under it or, read in full, of a folder above it: " + "; ".join(f"{ident} links {', '.join(paths) or 'no code'}"
                                                                                             for ident, paths in found.items())
            + ". Leave the row out and raise a question for research to read it; draw it once research answers")
