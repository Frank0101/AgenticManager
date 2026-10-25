"""Reads and writes the research ledger's tables, text and links by ID.

The ledger is long, and a hand-made patch has to match its text exactly once, so
every write goes through here: IDs, order, anchors and links are mechanical;
what goes in the cells is the agent's judgment, which reaches it through
investigate.py's submissions. A row is checked as it is written, with the rules
check_report.py applies to the whole ledger at handover.
"""
import os
import re

from common import (BOUNDARY, read_in_part, CITATION, citation, DESIGN, BOUNDARY_HEADER, COMPONENT_HEADER, CONNECTION_HEADER, DECISION_HEADER, DESIGN_TABLES,
                    FINDING_HEADER, FLOW_HEADER, FOLDER_NAME, GAP_FIX, GAP_HEADER, ID_LETTERS,
                    IDENTITY_HEADER, INLINE_LINK, JIRA_API, JIRA_GROUP, LEDGER, LINKS, QUERY, QUEUE_HEADER,
                    QUEUE_TABLES, REVIEW_HEADER, REVIEW_NONE, REVIEW_STOPPED, ROW_START, SOURCE_FINDINGS_COLUMN,
                    SOURCE_HEADER, SOURCE_LINK_FIX, TABLE_HEADINGS, JiraClient, anchored, autolink, backtick_error,
                    blocked_problem, cited_sources, coverage_problem, design_problem, finding_problem, free_name,
                    gap_problem, group_problem, h2_span, id_order, ids, inline_links, investigation_dir, is_enabled,
                    ledger_rows, link_definitions, link_text, links, outcome_problem, same_document,
                    section_span, slug, source_reference_missing, status_problem, strip_anchors, superseded_problem,
                    table, table_cells, table_row, ticket_sites, unlinked_backticks, unread_components,
                    unread_message, unrecorded_citations, unresolved_message, upgraded_tickets, write_output_file)

# table name: (heading it sits under, default header, ID letter)
TABLES = {
    **{table: (TABLE_HEADINGS[table], QUEUE_HEADER, "Q") for table in QUEUE_TABLES},
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
# The columns the script writes, which a row's input leaves out: a source's
# Findings, from the findings that cite it.
GENERATED = {"sources": SOURCE_HEADER[SOURCE_FINDINGS_COLUMN]}
PLACEHOLDERS = {"None yet.", "None."}
LINKS_HEADING = f"## {LINKS}"
# The Jira site of each project looked up in this run, or None: a key-shaped
# word such as SHA-256 is no ticket, so a key is linked only when the site has
# its project, and each project is asked about once.
SITES = {}
# The line under the System design heading saying what the design was built
# from: research only ever adds findings, gaps and decisions, so when their
# counts no longer match, the design is out of date and is built again.
BASIS = re.compile(
    r"^Built from (\d+) findings, (\d+) gaps and (\d+) decisions\.$")


def brief(lines):
    """What writing the report reads, from the ledger as it stands: the
    boundary, each source's reference with its coverage, every finding, the
    components, the system design, decisions and gaps, and the findings resting
    on a partial read. The queue and the review rounds are for research, and make up much
    of a long ledger. Links show their text, IDs are plain, and a source's
    reference keeps its URL, so the report can link the source itself."""
    def plain(text):
        return link_text(strip_anchors(text))

    out = []
    start, end = h2_section(lines, BOUNDARY)
    out += [f"## {BOUNDARY}", "",
            plain("\n".join(lines[start + 1:end]).strip()), ""]
    out += ["## Sources: references and coverage", ""]
    out += [f"{row[0]}: {as_written(lines, row[2])}, {plain(row[3])}; coverage: {plain(row[4])}"
            + ("" if row[6] == "None" else f"; superseded by {plain(row[6])}")
            for row in table_rows(lines, "sources")] or ["None."]
    out.append("")
    for name in ("findings", "components", *DESIGN_TABLES, "decisions", "gaps"):
        rows = table_rows(lines, name)
        out += [TABLES[name][0], ""]
        out += ([" | ".join(header_of(lines, name))] + [plain(" | ".join(row)) for row in rows]
                if rows else ["None."])
        out.append("")
    out += partial_lines(lines)
    return "\n".join(out).rstrip() + "\n"


def h2_section(lines, title):
    """(index of its heading, index of the next ## heading or the end) of the
    ## section `title`; exits if the ledger has none."""
    span = h2_span(lines, title)
    if span is None:
        raise SystemExit(f"the ledger has no '## {title}' section")
    return span


def partial_lines(lines):
    """The lines naming the findings that rest on a partial read, or []."""
    found = partial_reads(lines)
    return (["findings resting on a partial read (read the rest, or say in the finding why it can't change it):"]
            + [f"  {ident}: {source} {reference} ({coverage})" for ident,
               source, reference, coverage in found]
            if found else [])


def partial_reads(lines):
    """[(finding, source, its reference, its coverage)] of the findings citing
    a source read only in part: a claim, a negative one above all, may rest on
    the part left unread."""
    partial = {row[0]: row for row in table_rows(lines, "sources")
               if read_in_part(row)}
    return [(row[0], source, link_text(strip_anchors(partial[source][2])), partial[source][4])
            for row in table_rows(lines, "findings") for source in dict.fromkeys(ids(row[2], "S"))
            if source in partial]


def table_rows(lines, name):
    """The data rows of the table `name`, as cells; [] while it has none."""
    return ledger_rows("\n".join(lines), TABLES[name][0])


def as_written(lines, text):
    """`text` in the form a submission writes it: citations as [[F07]] and
    links inline. Submitting it back stores it unchanged, so an edit needs no
    undoing of the stored form by hand."""
    return inline_links(CITATION.sub(r"[[\1]]", strip_anchors(text)), links_section(lines))


def links_section(lines):
    """{key: URL} of the Links section, keys in lower case."""
    span = section_span(lines, LINKS_HEADING)
    return link_definitions("\n".join(lines[span[0] + 1:span[1]])) if span else {}


def header_of(lines, name):
    """The header of the table `name` as the ledger writes it, or its default."""
    span = table_span(lines, TABLES[name][0])
    return table_cells(lines[span[0]]) if span else TABLES[name][1]


def table_span(lines, heading):
    """(start, end) of the first table under `heading`, or None."""
    start, end = section(lines, heading)
    first = next((i for i in range(start + 1, end)
                 if lines[i].startswith("|")), None)
    if first is None:
        return None
    last = first
    while last < end and lines[last].startswith("|"):
        last += 1
    return first, last


def section(lines, heading):
    """(index of the heading, index of the next heading or the end); exits if
    the ledger has no such section."""
    span = section_span(lines, heading)
    if span is None:
        raise SystemExit(f"the ledger has no {heading!r} section")
    return span


def put_row(lines, name, row_id, cells):
    """Write the row `row_id` of the table `name`, replacing one with the same
    ID, and return its cells as written; exits on an ID or cells the table
    doesn't take."""
    letters = TABLES[name][2]
    if not re.fullmatch(rf"{letters}\d+", row_id):
        raise SystemExit(
            f"{name} IDs are {letters} and a number, such as {letters}07")
    columns = input_columns(name)
    if not isinstance(cells, list) or not all(isinstance(c, str) for c in cells) or len(cells) != len(columns):
        raise SystemExit(
            f"{name} takes {len(columns)} texts after the ID: {' | '.join(columns)}")
    written = linked(lines, [c.replace("\n", " ") for c in cells])
    if name in GENERATED:
        # Written by sync_sources once the row is in.
        written.insert(TABLES[name][1].index(GENERATED[name]) - 1, "None")
    set_row(lines, name, row_id, written)
    # A question is in one part of the queue: writing it in one takes it out of the others.
    for other in QUEUE_TABLES if name in QUEUE_TABLES else ():
        if other != name and any(row[0] == row_id for row in table_rows(lines, other)):
            write_rows(lines, other, [row for row in table_rows(lines, other) if row[0] != row_id],
                       header_of(lines, other))
    return written


def input_columns(name):
    """The columns a row of the table `name` is written with: after its ID, but
    for those the script writes."""
    return [column for column in TABLES[name][1][1:] if column != GENERATED.get(name)]


def linked(lines, values):
    """`values` with every link written by reference, and ticket keys and
    owner/repo#123 linked, so none needs a separate step. Inline links go
    first, so a ticket or a page of a code host linked in one value lets the
    same project's keys or host's pull requests be linked in the others.
    Exits, writing nothing, if a reference can't be linked."""
    values = [reference_links(lines, v) for v in values]
    out, unresolved = [], []
    for value in values:
        definitions = links_section(lines)
        value, missing = autolink(value, definitions, jira_site)
        # A key the agent wrote as code, of a project the ledger links, is linked too.
        sites = ticket_sites(definitions.values())
        value = "\n".join(upgraded_tickets(line, sites)
                          for line in value.split("\n"))
        unresolved += missing
        out.append(reference_links(lines, value))
    if unresolved:
        raise SystemExit("couldn't link " + unresolved_message(unresolved))
    return out


def reference_links(lines, text):
    """`text` with each inline link [text](url) written as the reference link
    [text][key] the ledger uses, its key defined in the Links section: the
    key the URL already has, else one made from the text, so a URL lives in
    one place however many times it is written."""
    def reference(match):
        image, label, url = match[1], match[2], match[3].strip("<>")
        if image or not re.match(r"https?://", url):
            return match[0]
        definitions = links_section(lines)
        key = next((k for k, v in definitions.items() if v == url), None)
        if key is None:
            key = free_name(slug(label.casefold()) or "link",
                            definitions.__contains__)
            set_link(lines, key, url)
        return f"[{label}][{key}]"
    return INLINE_LINK.sub(reference, text)


def set_link(lines, key, url):
    """Define the link `key` as `url` in the Links section, sorted by key."""
    if LINKS_HEADING not in [line.strip() for line in lines]:
        lines += ["", LINKS_HEADING, "", "None yet."]
    start, end = section(lines, LINKS_HEADING)
    definitions = links_section(lines)
    definitions[key] = url
    body = ["", *(f"[{k}]: {v}" for k, v in sorted(definitions.items(),
                  key=lambda kv: kv[0].casefold())), ""]
    lines[start + 1:end] = body


def jira_site(project):
    """The Jira site that has `project`, or None: without jira-api or with
    its settings not filled in, when the site has no such project, or it is
    one the user excludes. Raises JiraError when Jira fails, which stops the
    write: a key Jira couldn't be asked about isn't taken for no ticket."""
    if project not in SITES:
        SITES[project] = None
        if is_enabled(JIRA_GROUP, JIRA_API):
            try:
                client = JiraClient()
            except SystemExit:
                return None
            if client.project(project) is not None:
                SITES[project] = client.base_url
    return SITES[project]


def set_row(lines, name, row_id, cells):
    """Write the row `row_id` of `name` after checking its cells, replacing
    one with the same ID, rows in ID order."""
    header = header_of(lines, name)
    row = [row_id, *cells]
    check_cells(lines, name, row)
    rows = [r for r in table_rows(lines, name) if r[0] != row_id] + [row]
    rows.sort(key=lambda row: id_order(row[0]))
    write_rows(lines, name, rows, header)


def check_cells(lines, name, row):
    """Exit if a cell holds a value its column doesn't allow."""
    problem = None
    if name == "components":
        problem = status_problem(row[0], row[4]) or design_problem(name, row)
    elif name in DESIGN_TABLES:
        problem = design_problem(name, row)
    elif name == "findings":
        problem = finding_problem(row)
    elif name == "queue-completed":
        problem = outcome_problem(row[0], row[-1], row[2])
    elif name == "queue-blocked":
        problem = blocked_problem(row[0], row[QUEUE_HEADER.index("Depends on")],
                                  {r[0] for r in table_rows(lines, "queue-blocked")})
    elif name == "gaps":
        problem = (blocked := gap_problem(row)) and f"{blocked}. {GAP_FIX}"
    elif name == "sources":
        problem = group_problem(row) or coverage_problem(row) or superseded_problem(row) or (
            source_reference_missing(row) and f"{row[0]}: {SOURCE_LINK_FIX}")
    if problem:
        raise SystemExit(f"{name} {problem}")
    if unread := name == "components" and unread_components([row], table_rows(lines, "sources"),
                                                            links_section(lines)):
        raise SystemExit(unread_message(unread))
    # A search's query is the one backticked text allowed outside a link.
    check_backticks(lines, [c for i, c in enumerate(
        row) if not (name == "sources" and i == 2)], name)


def check_backticks(lines, values, where):
    """Exit if `values` put a reference in backticks outside a link."""
    spans = [span for value in values for span in unlinked_backticks(
        value, "\n".join(lines))]
    if spans:
        raise SystemExit(backtick_error(where, spans))


def write_rows(lines, name, rows, header=None):
    """Put `rows` in the table `name`, creating it under its heading if there is none."""
    heading, default, _ = TABLES[name]
    span = table_span(lines, heading)
    if span is None:
        start, end = section(lines, heading)
        drop_placeholder(lines, start + 1, end)
        # The blank lines that stood around the placeholder go, as the table
        # brings its own.
        while start + 1 < len(lines) and not lines[start + 1].strip() and not lines[start + 1].startswith("#"):
            del lines[start + 1]
        block = ["", render(header or default), render(
            ["---"] * len(header or default))]
        block += [render(r) for r in rows] + [""]
        lines[start + 1:start + 1] = block
        return
    head = lines[span[0]:span[0] + 2]
    lines[span[0]:span[1]] = head + [render(r) for r in rows]
    table_end = span[0] + 2 + len(rows)
    _, end = section(lines, heading)
    if rows:
        drop_placeholder(lines, table_end, end)
    elif not any(line.strip() in PLACEHOLDERS for line in lines[table_end:end]):
        lines[table_end:table_end] = ["", "None."]


def drop_placeholder(lines, after, end):
    """Remove the first non-blank line in lines[after:end] if it is a placeholder."""
    for i in range(after, end):
        if lines[i].strip():
            if lines[i].strip() in PLACEHOLDERS:
                del lines[i]
            return


def render(cells):
    """A table row, its ID carrying the anchor citations link to."""
    if re.fullmatch(r"[A-Z]\d+", cells[0]):
        cells = [anchored(cells[0]), *cells[1:]]
    return table_row(cells)


def search_reference(given):
    """A search's Reference: its query between backticks, as the source rule
    reads it, from {"query": ...}, so no backtick is ever typed in a shell."""
    query = given.get("query") if set(given) == {"query"} else None
    if not isinstance(query, str) or not query.strip() or "`" in query or "\n" in query:
        raise SystemExit('a search\'s Reference is {"query": "<the exact query>"}, on one line, '
                         "without backticks")
    return f"`{query.strip()}`"


def duplicate_of(lines, row):
    """The ID of the source that already holds what the new source `row` does,
    the same document, whatever its link's form, at the same revision, or None: reading more of a source
    extends its Coverage, so each thing read is one row."""
    definitions = links_section(lines)

    def held(cells):
        targets = [same_document(url) for _, _, _, url in links(
            cells[2], definitions) if url] or QUERY.findall(cells[2])
        return tuple(targets), " ".join(link_text(cells[3]).split()).casefold()
    return next((r[0] for r in table_rows(lines, "sources") if r[0] != row[0] and held(r) == held(row)), None)


def next_id(text, kind):
    """The next free ID of the letter `kind` in the ledger `text`."""
    found = re.findall(rf"{ROW_START}{kind}(\d+)\s*\|", text, re.M)
    width = max([2] + [len(n) for n in found])
    return f"{kind}{max([0] + [int(n) for n in found]) + 1:0{width}d}"


def finish_write(lines, written):
    """Bring the ledger in step after a write whose new values are `written`,
    and return the questions it blocked: no question waits on itself in a
    circle, one waiting on a blocked question is blocked, sources name the
    findings citing them, ticket keys are linked, and every record cited exists.
    Run once the write's records are all in, so records may cite each other."""
    check_dependencies(lines)
    blocked = block_dependents(lines)
    sync_sources(lines)
    upgrade_tickets(lines)
    missing = unrecorded_citations(written, "\n".join(lines))
    if missing:
        raise SystemExit(
            f"cites {', '.join(missing)}, which the ledger doesn't hold")
    return blocked


def sync_sources(lines):
    """Write each source row's Findings from the Sources cells of the findings."""
    cited = cited_sources("\n".join(lines))
    rows = table_rows(lines, "sources")
    for row in rows:
        found = sorted(cited.get(id_order(row[0])[1], ()), key=id_order)
        row[SOURCE_FINDINGS_COLUMN] = ", ".join(
            citation(f) for f in found) or "None"
    if rows:
        write_rows(lines, "sources", rows, header_of(lines, "sources"))


def check_dependencies(lines):
    """Exit if a question depends on itself, or questions depend on each other
    in a circle: none of them could ever be worked."""
    needs = {row[0]: depends_on(
        row) for name in QUEUE_TABLES for row in table_rows(lines, name)}

    def circle(ident, path):
        if ident in path:
            return path[path.index(ident):] + [ident]
        return next((found for need in needs.get(ident, []) if (found := circle(need, path + [ident]))), None)
    for ident in needs:
        if found := circle(ident, []):
            raise SystemExit(f"questions depend on each other in a circle: {' → '.join(found)}. "
                             "Nothing was written")


def depends_on(row):
    """The questions a queue row waits for: the Q IDs of its Depends on cell."""
    return ids(row[QUEUE_HEADER.index("Depends on")], "Q")


def block_dependents(lines):
    """Move every ready or in-progress question that depends on a blocked one
    to blocked, until none is left: it can't be answered while what it needs is
    blocked. Its Depends on cell already names that question, so it says why.
    Returns the IDs moved."""
    moved = []
    while True:
        blocked = {row[0] for row in table_rows(lines, "queue-blocked")}
        stuck = [row[0] for name in ("queue-ready", "queue-in-progress") for row in table_rows(lines, name)
                 if blocked & set(depends_on(row))]
        if not stuck:
            return moved
        for ident in stuck:
            move_row(lines, ident, "queue-blocked")
        moved += stuck


def move_row(lines, row_id, target, cells=None):
    """Move the question `row_id` to the queue table `target`, with the cells
    `cells`, {column: value}, set on the way."""
    source, row = find_row(lines, row_id)
    header = header_of(lines, source)
    row = [(cells or {}).get(column, value)
           for column, value in zip(header, row)]
    write_rows(lines, source, [r for r in table_rows(
        lines, source) if r[0] != row_id], header)
    set_row(lines, target, row[0], row[1:])


def find_row(lines, row_id):
    """(queue table, row) of the question `row_id`; exits if there is none."""
    for name in QUEUE_TABLES:
        for row in table_rows(lines, name):
            if row[0] == row_id:
                return name, row
    raise SystemExit(f"no queue row {row_id}")


def upgrade_tickets(lines):
    """Link each ticket key written as code, `PROJ-7`, whose project the ledger
    now links: it was written before a ticket of its project was."""
    sites = ticket_sites(links_section(lines).values())
    if not sites:
        return
    for i in range(len(lines)):
        upgraded = upgraded_tickets(lines[i], sites)
        if upgraded != lines[i]:
            lines[i] = reference_links(lines, upgraded)


def refuse_cited(lines, ident):
    """Exit, writing nothing, while anything else in the ledger cites
    `ident`: removing it would leave a citation of a record that isn't there.
    It looks wherever the handover check does, so the two agree."""
    cited = mentions(lines, ident) + cited_outside_records(lines, ident)
    if cited:
        raise SystemExit(f"{ident} is still cited by {', '.join(cited)}: change those first. "
                         "Nothing was written")


def mentions(lines, ident):
    """The records, other than `ident`'s own, whose text names `ident`: when
    a question closes, what they say while it was open, such as "not
    established yet: see Q06", may need its answer; while any does, `ident`
    can't be removed."""
    found = [table_row_id for table in TABLES
             for table_row_id in (row[0] for row in table_rows(lines, table)
                                  if row[0] != ident and re.search(rf"\b{ident}\b", " | ".join(row[1:])))]
    return sorted(set(found), key=id_order)


def cited_outside_records(lines, ident):
    """The headings of the parts of the ledger outside its records, such as
    the boundary, whose text names `ident`; records, which mentions() names by
    their ID, are left out."""
    found, heading = [], ""
    for line in lines:
        if line.startswith("#"):
            heading = line.lstrip("#").strip()
        elif not re.match(rf"{ROW_START}[{ID_LETTERS}]\d", line) \
                and re.search(rf"\b{ident}\b", line) and heading not in found:
            found.append(heading)
    return [f"the {heading} section" for heading in found]


def record_review(lines, raised=(), stopped=None):
    """Add an independent review round to the reviews table, with the IDs of
    the questions it raised, already in the queue, or what the user said when
    they chose to stop reviewing; returns the round's number."""
    if stopped is not None:
        outcome = f"{REVIEW_STOPPED} {stopped.strip()}"
    else:
        outcome = ", ".join(citation(ident) for ident in raised) or REVIEW_NONE
    heading = TABLE_HEADINGS["reviews"]
    rounds = ledger_rows("\n".join(lines), heading)
    start, end = section(lines, heading)
    rows = rounds + [[str(len(rounds) + 1), linked(lines, [outcome])[0]]]
    lines[start + 1:end] = ["", *table(REVIEW_HEADER, rows).split("\n"), ""]
    return len(rows)


def add_scope(lines, name, answer):
    """Add the user's decision on `name`, include, mention only or exclude, to
    the Boundary section, below those already there; returns the line as
    written."""
    start, end = h2_section(lines, BOUNDARY)
    kept = [line for line in lines[start + 1:end]
            if line.strip() and line.strip() not in PLACEHOLDERS]
    written = linked(lines, [f"- {name}: {answer}."])
    check_backticks(lines, written, BOUNDARY)
    set_text(lines, BOUNDARY, "\n".join([*kept, written[0]]))
    return written


def scope_decisions(lines):
    """The Boundary section's decisions, one line each, as the user made them."""
    start, end = h2_section(lines, BOUNDARY)
    return [link_text(line.strip()) for line in lines[start + 1:end] if line.strip().startswith("- ")]


def set_text(lines, name, text):
    """Replace the text section `name` with `text`."""
    start, end = h2_section(lines, name)
    lines[start + 1:end] = ["", *text.strip().split("\n"), ""]


def basis(lines):
    """(findings, gaps, decisions): how many the ledger holds, what a design
    built now would be built from."""
    return tuple(len(table_rows(lines, name)) for name in ("findings", "gaps", "decisions"))


def design_basis(lines):
    """What the system design was last built from, as basis() counts it, or
    None while it was never built."""
    start, end = h2_section(lines, DESIGN)
    found = next((BASIS.match(line.strip())
                 for line in lines[start + 1:end] if BASIS.match(line.strip())), None)
    return tuple(int(n) for n in found.groups()) if found else None


def set_design_basis(lines, counts):
    """Record under the System design heading what the design was built from."""
    start, _ = h2_section(lines, DESIGN)
    end = next(i for i in range(start + 1, len(lines))
               if lines[i].startswith("#"))
    findings, gaps, decisions = counts
    lines[start + 1:end] = ["",
                            f"Built from {findings} findings, {gaps} gaps and {decisions} decisions.", ""]


def load(relative):
    """The ledger of the investigation `relative`, as text; exits if it has none."""
    path, _, _ = investigation_dir(relative)
    try:
        with open(os.path.join(path, LEDGER), encoding="utf-8") as f:
            return f.read()
    except OSError:
        raise SystemExit(
            f"{relative} has no {LEDGER}: start the investigation with investigate.py start")


def save(relative, lines):
    """Write the ledger `lines` of the investigation `relative`, and return its path."""
    text = "\n".join(lines).rstrip("\n") + "\n"
    path, _ = write_output_file(
        FOLDER_NAME, f"{relative}/{LEDGER}", text.encode("utf-8"))
    return path
