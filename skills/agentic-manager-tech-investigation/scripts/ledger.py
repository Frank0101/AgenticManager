"""Edits the research ledger's tables, findings, text and links by ID, and reads it back.

Why a script: the ledger is long, and a patch has to match text exactly once, so
every new row, finding, status change or move cost a hand-built edit. IDs and
ordering are mechanical, so they are the script's; what goes in the cells and the
findings is the agent's judgment. The reading commands (show, find, status) exist
so the agent never opens the whole ledger to check what it already holds, and they
print plain text, which costs fewer tokens than JSON, as does help. `brief` prints
what writing the report reads, without the queue, coverage and research notes,
which are for research and review and make up much of a long ledger. Every other
command prints one line of JSON.

Rows of a table with no ID (file coverage) append, and are replaced or removed
by text only that row contains.

`batch` writes many rows and findings in one call, with the same checks, since
reading a part of the code records dozens at once. It is all or nothing: the
ledger is saved only after every item is written, so a bad item leaves no half.

The ledger stores IDs as links to their anchors and links by reference, so
`show --raw` and `show --section` print a record or a section as the input its
writing command reads: an edit is read, change, write back, and what it didn't
change is stored unchanged.

The allowed values (areas, statuses, depths, blockers) and the rules for a row
live in common.py and are checked as a row is written; check_report.py applies
the same rules to the whole ledger. A cited ID the ledger doesn't hold is
refused too, once every record of the call is written, so records that cite
each other go in one batch and nothing ever points at a record that isn't
there; for the same reason a record still cited elsewhere can't be removed.

`help` prints each command's input and a command to copy, and each table's
columns, values and a worked row: the script is their one source, so SKILL.md
doesn't repeat them. Ticket keys and owner/repo#123 are linked on write, so
none needs a separate step: a key to the Jira site the ledger's links give its
project, else to the site that has the project; anything else key-shaped is
written as code.
"""
import argparse
import glob
import json
import os
import re
import sys

from common import (ID, JiraClient, is_enabled, AREAS, BLOCKERS, BOUNDARY, CODE_STATUSES, claim_length_warning,
                    COMPONENT_HEADER, DECISION_HEADER, DEFINITION, DEPTHS, EVIDENCE_LINE, FILE_HEADER, FINDINGS,
                    FINDING_FIELDS, FINDING_OPTIONAL, FINDING_START, FOLDER_NAME, GAP_FIX, GAP_HEADER, GROUPS, ID_ANCHOR,
                    INLINE_LINK, LEDGER, LINKS, QUEUE_HEADER, QUEUE_TABLES, READ_DEPTHS, REFERENCE_LINK, REFLECTION,
                    REJECTED, REPORT_SUFFIX, REVIEW_BACKSTOP, REVIEW_NONE, REVIEW_QUESTION, REVIEW_STOPPED, ROW_START,
                    SOURCE_FINDINGS, SOURCE_HEADER, SOURCE_LINK_FIX, STATUSES, TABLE_HEADINGS, anchor_tag, anchored,
                    areas_of, areas_problem, autolink, backtick_error, cited_sources, free_name, coverage_material_missing,
                    depth_problem, finding_blocks, gap_problem, id_order, investigation_dir, last_review, ledger_rows,
                    link_definitions, link_text, linked_ids, outcome_problem, read_in_full, recorded_ids,
                    review_rounds, reviewed, h2_span, section_span, slug, source_reference_missing, status_problem,
                    strip_anchors, table_cells, table_row, ticket_sites, unlinked_backticks, unread_components,
                    unread_message, unrecorded_citations, unresolved_message, upgraded_tickets, write_output_file)

# table name: (heading it sits under, default header, ID letters, or None when
# rows have no ID and append)
TABLES = {
    **{table: (TABLE_HEADINGS[table], QUEUE_HEADER, "Q") for table in QUEUE_TABLES},
    "sources": (TABLE_HEADINGS["sources"], SOURCE_HEADER, "S"),
    "file-coverage": (TABLE_HEADINGS["file-coverage"], FILE_HEADER, None),
    "decisions": (TABLE_HEADINGS["decisions"], DECISION_HEADER, "D"),
    "gaps": (TABLE_HEADINGS["gaps"], GAP_HEADER, "G"),
    "components": (TABLE_HEADINGS["components"], COMPONENT_HEADER, "C"),
}
SHA = "<sha>"
# A worked row per table, its cells after the ID, printed by `help` and with a
# wrong column count.
ROW_EXAMPLES = {
    "queue-ready": ["S03 names a deploy job", "Is the deploy job live?", "Workflow runs at a pinned commit",
                    "None", "High", ""],
    "queue-in-progress": ["S03 names a deploy job", "Is the deploy job live?", "Workflow runs at a pinned commit",
                          "None", "High", ""],
    "queue-blocked": ["F04", "Is the cluster config deployed?", "Cluster read access", "G01", "High", ""],
    "queue-completed": ["Request", "Which service serves search?", "Routes at a pinned commit", "None", "High",
                        "F02, F03"],
    "sources": ["source_control", f"[api server.py](https://github.com/acme/api/blob/{SHA}/server.py)",
                f"{SHA}, 2026-10-05", "Routes read in full.", "None", "Implementation, Architecture"],
    "file-coverage": ["S04", f"[api server.py](https://github.com/acme/api/blob/{SHA}/server.py)",
                      "entrypoints and routes: lines 1-200 of 900"],
    "decisions": ["Which queue to use", "Unresolved: the design names two options", "SQS or Kafka; replay needed",
                  "Design doc, proposed", "Owner not named; next check: design review"],
    "gaps": ["Production config", "Code merged; deployed config not read", "Read access to the cluster",
             "No access (cluster)", "Code; deployment reported", "Platform team; once access exists",
             "Runtime and operations"],
    "components": ["search-api (service)", "Serves search queries",
                   f"[services/search](https://github.com/acme/api/tree/{SHA}/services/search)", "🟩 Implemented",
                   "Declared in the manifest, live state not read", "Web app → search-api → index", "F02, F03",
                   "Unchanged in the next milestone"],
}
# The allowed values of a table's cells, by column.
ALLOWED = {
    "sources": {"Exact reference": 'a link at the pinned revision, or for a search {"query": "<the exact query>"}, '
                                   "which is written as the query between backticks",
                "Areas": "comma separated, from: " + ", ".join(AREAS)},
    "gaps": {"Areas": "comma separated, from: " + ", ".join(AREAS),
             "Blocked by": "starts with one of: " + "; ".join(BLOCKERS)
             + " (a gap nothing blocks is a ready action instead)"},
    "file-coverage": {"Depth": "starts with one of: " + ", ".join(DEPTHS)},
    "components": {"Name and type": "the name, then its type in brackets, such as 'Search API (service)'; the "
                   "report's flows name it so, and a store, queue, topic, stream or external product type sets "
                   "its shape",
                   "Status": "starts with one of: " + "; ".join(f"{label} ({meaning})" for label, meaning in STATUSES)
                   + f". {' and '.join(CODE_STATUSES)} need file coverage at depth {' or '.join(READ_DEPTHS)} "
                   "of the linked path, a file under it or a folder above it"},
    "queue-blocked": {"Depends on": "the gap or decision that blocks it, such as G01 or D01"},
    "queue-completed": {"Outcome / finding IDs": f"names F, D or G IDs, or starts '{REJECTED} <what they said>'; "
                        "the review's own row, written by `review`, names the actions it raised"},
}
PLACEHOLDERS = {"None yet.", "None."}
LINKS_HEADING = f"## {LINKS}"
FINDINGS_HEADING = f"## {FINDINGS}"
TEXT_SECTIONS = [BOUNDARY, REFLECTION]
# How every help entry calls the script: the path the skill pre-approves.
CALL = "<scripts>/ledger.py"
# How text names what it rests on, which every writing command reads the same way.
LINKING = ("links: write a link as [text](url), a ticket key plainly (PROJ-123), a pull request as owner/repo#123, "
           "never a bare #123, and a recorded ID plainly (F03): the script links each one")
FINDING_EXAMPLE = {"title": "Search API serves queries from the index",
                   "Claim": "The search API answers /search from the index, never the primary database.",
                   "Kind": "observed implementation", "Evidence": "S04",
                   "Validation and limits": "Routes read in full at the pinned commit; deployment not read.",
                   "Supersedes or contradicted by": "Contradicts the design note in S02"}
# A file or folder path in a finding's evidence, such as app/server.ts.
PATH = re.compile(
    r"(?<![\w/.-])[\w.-]+(?:/[\w.-]+)*\.[A-Za-z]\w*\b|(?<![\w/.-])[\w.-]+(?:/[\w.-]+)+")
# The Jira site of each project looked up in this call, or None: a key-shaped
# word such as SHA-256 is no ticket, so a key is linked only when the site has
# its project, and each project is asked about once.
SITES = {}
# A recorded ID's citation as stored: a link to its anchor.
ID_CITATION = re.compile(r"\[([A-Z]\d+)\]\(#[a-z]\d+\)")
# How a review round is recorded, as next_step tells it.
RECORD_ROUND = "ledger.py review --raised <the ready actions its real issues became, or none>"


def heredoc(command, body):
    """A command to copy, its input in a quoted here-document, so nothing in
    the input, such as a link's brackets or quotes, needs escaping."""
    return "\n".join([f"  {CALL} {command} <<'EOF'", *(f"  {line}" for line in body.split("\n")), "  EOF"])


# The commands other than `row`: their input and a command to copy. A command
# whose input is long or holds links reads it from a here-document.
COMMAND_HELP = {
    "findings": "\n".join([
        "finding: a JSON object on standard input; leave --id out to add the next one, or give it to replace one",
        f"  fields, each text: title, {', '.join(FINDING_FIELDS)}; optional: {', '.join(FINDING_OPTIONAL)}",
        heredoc("finding --investigation <investigation>",
                json.dumps(FINDING_EXAMPLE, ensure_ascii=False, indent=2)),
        f'  to change fields of a finding already written: {CALL} finding --investigation <investigation> --id F07 '
        '--set "Validation and limits=<new value>" (repeat --set for more)']),
    "batch": "\n".join([
        "batch: writes many rows and findings in one call, from a JSON list on standard input, in order; "
        "each row as `row` takes it, each finding as `finding` does, with the same checks. If one item "
        "can't be written, nothing is",
        "  a row: {\"table\": ..., \"id\": ..., \"match\": ..., \"cells\": [...]}, leaving out an id or match "
        "it doesn't take; a finding: {\"finding\": {...}, \"id\": ...}, leaving out id to add the next one",
        heredoc("batch --investigation <investigation>", json.dumps([
            {"table": "sources", "id": "S04",
                "cells": ROW_EXAMPLES["sources"]},
            {"table": "file-coverage", "cells": ROW_EXAMPLES["file-coverage"]},
            {"finding": {k: v for k, v in FINDING_EXAMPLE.items() if k != "Supersedes or contradicted by"}}],
            ensure_ascii=False, indent=2))]),
    "show": "\n".join([
        "show: prints a finding or a row by --id, a table by --table, or a text section by --section; "
        "with --raw, a finding or row is printed as the input its writing command reads, and a section "
        "is always printed so: IDs plain and links inline, so an edit is read, change, write back",
        f"  {CALL} show --investigation <investigation> --raw --id F07",
        f'  {CALL} show --investigation <investigation> --section Reflection']),
    "brief": "\n".join([
        "brief: prints what writing the report reads, from the ledger as it stands: the boundary, "
        "each source's exact reference with its limits, every finding, and the components, decisions and gaps; not the queue, "
        "the coverage or the research notes",
        f"  {CALL} brief --investigation <investigation>"]),
    "text": "\n".join([
        f"text: replaces a section's text, read as Markdown from standard input; --section is "
        f"{', '.join(TEXT_SECTIONS)}",
        heredoc('text --investigation <investigation> --section Reflection',
                "The first draft assumed ...; the code showed ..."),
        "  to change part of it, --replace the exact text, as show --section prints it, and its replacement:",
        f'  {CALL} text --investigation <investigation> --section Reflection --replace "old text" "new text"']),
    "move": "\n".join([
        'move: moves an action to ready, in-progress, blocked or completed; each --set "Column=value" sets a cell',
        f'  {CALL} move --investigation <investigation> --id Q05 --to in-progress',
        f'  {CALL} move --investigation <investigation> --id Q05 --to completed --set "Outcome / finding IDs=F03, G01"']),
    "review": "\n".join([
        "review: records an independent review round, with the ready actions its real issues became, or none",
        f"  {CALL} review --investigation <investigation> --raised Q08,Q09",
        f"  {CALL} review --investigation <investigation> --raised none",
        "  after the user, asked whether to go on, chose to stop the review:",
        f"  {CALL} review --investigation <investigation> --stopped '<what they said>'"]),
    "link": "\n".join([
        f"link and unlink: add or remove a link definition under ## {LINKS}",
        f"  {CALL} link --investigation <investigation> --key api-server --url https://github.com/acme/api/blob/<sha>/server.py",
        f"  {CALL} unlink --investigation <investigation> --key api-server"]),
    "next-id": "\n".join([
        "next-id: prints the next free ID of a kind, S, Q, F, C, D or G, for a row you are about to write",
        f"  {CALL} next-id --investigation <investigation> --kind S"]),
    "sync-sources": "\n".join([
        "sync-sources: rewrites each source's Findings from the findings' Evidence lines; row and finding keep "
        "them in step, so it is needed only after the ledger was edited without the script",
        f"  {CALL} sync-sources --investigation <investigation>"]),
    "remove": "\n".join([
        "remove: deletes a row by --id, a finding by --id, or a file coverage row by text it contains; "
        "refused while anything else in the ledger cites it",
        f"  {CALL} remove --investigation <investigation> --table gaps --id G02",
        f"  {CALL} remove --investigation <investigation> --table findings --id F07",
        f"  {CALL} remove --investigation <investigation> --table file-coverage --match server.py"]),
}


def full_help():
    """How text names what it rests on, then every table's entry, then every other command's."""
    return "\n\n".join([LINKING, *(table_help(name) for name in TABLES), *COMMAND_HELP.values()])


def table_help(name):
    """A table's columns, allowed values, a worked row and a command to copy, as text."""
    header = TABLES[name][1]
    letters = TABLES[name][2]
    out = [f"{name}: " + " | ".join(header),
           ("--id " + letters + "01, then " if letters else "no --id, then ")
           + f"{len(header) - bool(letters)} cells on standard input, as a JSON list of strings"]
    out += [f"  {column}: {rule}" for column,
            rule in ALLOWED.get(name, {}).items()]
    out.append("  example: " +
               json.dumps(ROW_EXAMPLES[name], ensure_ascii=False))
    ident = f" --id {letters}01" if letters else ""
    out.append(heredoc(f"row --investigation <investigation> --table {name}{ident}",
                       json.dumps(ROW_EXAMPLES[name], ensure_ascii=False)))
    if not letters:
        out.append(
            "  to replace a row, add --match <text only it contains>, such as its file's name")
    target = f"--id {letters}01" if letters else "--match <text only it contains>"
    out.append(f'  to change cells of a row already written: {CALL} row --investigation <investigation> --table {name} '
               f'{target} --set "{header[-1]}=<new value>" (repeat --set for more)')
    return "\n".join(out)


def brief(lines):
    """What writing the report reads, from the ledger as it stands: the
    boundary, each source's exact reference with its limits, every finding, and the
    components, decisions and gaps. Links show their text, IDs are plain, and a
    source's reference keeps its URL for the report's references."""
    def plain(text):
        return link_text(strip_anchors(text))

    out = []
    start, end = text_span(lines, BOUNDARY)
    out += [f"## {BOUNDARY}", "",
            plain("\n".join(lines[start + 1:end]).strip()), ""]
    out += ["## Sources: exact references", ""]
    # A source's limits or what supersedes it decides a historical reference.
    out += [f"{row[0]}: {as_written(lines, row[2])}" + ("" if row[5].strip() in ("", "None") else
                                                        f" ({plain(row[5])})")
            for row in table_rows(lines, "sources")] or ["None."]
    blocks, _, _ = findings_of(lines)
    out += ["", FINDINGS_HEADING, ""]
    out += ["\n".join(line for line in plain(blocks[k]).split("\n") if line.strip()) + "\n"
            for k in sorted(blocks, key=id_order)] or ["None.", ""]
    for name in ("components", "decisions", "gaps"):
        rows = table_rows(lines, name)
        out += [TABLES[name][0], ""]
        out += ([" | ".join(header_of(lines, name))] + [plain(" | ".join(row)) for row in rows]
                if rows else ["None."])
        out.append("")
    out += partial_lines(lines)
    return "\n".join(out).rstrip() + "\n"


def as_written(lines, text):
    """`text` in the form it was written in: IDs plain and links inline, as
    the writing commands read them. Writing it back stores it unchanged, so an
    edit needs no undoing of the stored form by hand."""
    definitions = links_section(lines)

    def inline(match):
        url = definitions.get((match[3] or match[2]).casefold())
        return f"{match[1]}[{match[2]}]({url})" if url else match[0]
    return REFERENCE_LINK.sub(inline, ID_CITATION.sub(r"\1", strip_anchors(text)))


def show(lines, ident, name):
    if name == "findings":
        blocks, _, _ = findings_of(lines)
        return "\n".join(b.splitlines()[0].removeprefix("### ") for _, b in
                         sorted(blocks.items(), key=lambda kv: id_order(kv[0]))) or "No findings."
    if name:
        return "\n".join(table_markdown(lines, name)) or "None."
    table, found = record(lines, ident)
    if table == "findings":
        return found
    return "\n".join([f"{table} {found[0]}"] + [f"{h}: {c}" for h, c in
                                                zip(header_of(lines, table)[1:], found[1:])])


def record(lines, ident):
    """("findings", the finding's block) or (table, row) of the record
    `ident`; exits if the ledger has none."""
    if re.fullmatch(r"F\d+", ident):
        blocks, _, _ = findings_of(lines)
        if ident not in blocks:
            raise SystemExit(f"no finding {ident}")
        return "findings", blocks[ident]
    for table in TABLES:
        if TABLES[table][2] is None:
            continue
        for row in table_rows(lines, table):
            if row[0].casefold() == ident.casefold():
                return table, row
    raise SystemExit(f"no record {ident}")


def table_markdown(lines, name):
    span = table_span(lines, TABLES[name][0])
    return lines[span[0]:span[1]] if span else []


def find(lines, text):
    needle = text.casefold()
    hits = []
    for table in TABLES:
        for row in table_rows(lines, table):
            cells = " | ".join(row)
            if needle in cells.casefold():
                hits.append(f"{table} {row[0]}: {snippet(cells, needle)}")
    blocks, _, _ = findings_of(lines)
    for ident, block in sorted(blocks.items(), key=lambda kv: id_order(kv[0])):
        if needle in block.casefold():
            line = next(line for line in block.splitlines()
                        if needle in line.casefold())
            hits.append(f"finding {ident}: {snippet(line, needle)}")
    start, end = section(lines, LINKS_HEADING)
    for line in lines[start + 1:end]:
        if line.startswith("[") and needle in line.casefold():
            hits.append(f"link {line}")
    if not hits:
        return f"no match for {text!r}"
    shown = hits[:40]
    return "\n".join(shown + ([f"... and {len(hits) - 40} more"] if len(hits) > 40 else []))


def snippet(text, needle, width=110):
    at = text.casefold().find(needle)
    start = max(0, at - 30)
    return ("..." if start else "") + text[start:start + width].replace("\n", " ")


def status(lines, report=False):
    out = []
    queue = {table: table_rows(lines, table) for table in QUEUE_TABLES}
    out.append(
        "queue: " + ", ".join(f"{len(queue[t])} {t.removeprefix('queue-')}" for t in QUEUE_TABLES))
    for label, table in (("in progress", "queue-in-progress"), ("ready", "queue-ready"),
                         ("blocked", "queue-blocked")):
        for row in queue[table]:
            out.append(f"  {label} {row[0]} [{row[5]}] {row[2][:100]}")
    blocks, _, _ = findings_of(lines)
    totals = [("findings", len(blocks))]
    for table in ("sources", "file-coverage", "components", "decisions", "gaps"):
        totals.append((table, len(table_rows(lines, table))))
    out.append("counts: " + ", ".join(f"{n} {name}" for name, n in totals))
    out += coverage(lines)
    unstarted = []
    for line in lines:
        if line.startswith("## "):
            start, end = h2_section(lines, line[3:].strip())
            body = [x for x in lines[start + 1:end] if x.strip()]
            if body in (["None yet."], []):
                unstarted.append(line[3:])
    out.append("not started: " +
               (", ".join(unstarted) if unstarted else "none"))
    unread = unread_components(table_rows(lines, "components"), table_rows(lines, "file-coverage"),
                               links_section(lines))
    if unread:
        out.append("components claiming code with no code read: " +
                   ", ".join(unread))
    out += partial_lines(lines)
    out.append("next: " + next_step(queue, REFLECTION in unstarted, report))
    return "\n".join(out)


def partial_lines(lines):
    """The lines naming the findings that rest on a partial read, or []."""
    found = partial_reads(lines)
    return (["findings resting on a partial read (read the rest, or say in the finding why it can't change it):"]
            + [f"  {ident}: {material} ({depth})" for ident, material, depth in found]) if found else []


def partial_reads(lines):
    """[(finding, material, depth)] of the findings whose Evidence names a
    file that a coverage row of the same source read below READ_DEPTHS: a
    claim, a negative one above all, may rest on the part left unread."""
    blocks, _, _ = findings_of(lines)
    shallow = [row for row in table_rows(lines, "file-coverage")
               if not read_in_full(row[2])]
    found = []
    for ident, block in sorted(blocks.items(), key=lambda kv: id_order(kv[0])):
        evidence = EVIDENCE_LINE.search(as_written(lines, block))
        if not evidence:
            continue
        paths = PATH.findall(evidence[1])
        for row in shallow:
            material = as_written(lines, row[1])
            source = ID.search(row[0])
            if source and re.search(rf"\b{source[0]}\b", evidence[1]) and any(p in material for p in paths):
                found.append((ident, link_text(strip_anchors(row[1])), row[2]))
    return found


def coverage(lines):
    """Lines counting, per evidence area, the sources of each group and the gaps."""
    sources, gaps = table_rows(lines, "sources"), table_rows(lines, "gaps")
    tally = {a: {g: 0 for g in GROUPS} for a in AREAS}
    untagged = []
    for row in sources:
        group = next(
            (g for g in GROUPS if row[1].casefold().startswith(g)), None)
        tagged = [a for a in areas_of(row) if a in AREAS]
        if group and not tagged:
            untagged.append(row[0])
        for area in tagged:
            if group:
                tally[area][group] += 1
    out = ["coverage (sources per area: " +
           " / ".join(GROUPS.values()) + "; gaps):"]
    for area in AREAS:
        open_gaps = sum(area in areas_of(g) for g in gaps)
        counts = " / ".join(str(tally[area][g]) for g in GROUPS)
        thin = [GROUPS[g] for g in GROUPS if not tally[area][g]]
        out.append(f"  {area}: {counts}, {open_gaps} gaps" +
                   (f"  (none from {', '.join(thin)})" if thin else ""))
    if untagged:
        out.append("  sources with no Areas: " + ", ".join(untagged))
    return out


def next_step(queue, reflection_missing, report):
    """The phase the investigation is in, from the queue, the report and the
    reflection: each phase opens only when the one before is finished, so the
    independent review sees the whole investigation."""
    if queue["queue-in-progress"]:
        return (f"research: finish the actions in progress before starting a ready one: "
                f"{', '.join(row[0] for row in queue['queue-in-progress'])}")
    if queue["queue-ready"]:
        return (f"research: move a ready action to in-progress and work it, such as {queue['queue-ready'][0][0]}. "
                "Ask the user before adding or leaving out a topic outside the one asked")
    if not report:
        return "write: read ledger.py brief in full, write content.json, run make_report.py"
    if not reviewed(queue["queue-completed"]):
        rounds = review_rounds(queue["queue-completed"])
        if rounds >= REVIEW_BACKSTOP:
            return (f"review: {rounds} rounds have run. Before another, show the user in a few lines what "
                    "each round found and ask whether to go on. If they choose to stop, record it with "
                    "ledger.py review --stopped '<what they said>'; otherwise start another round (step 4) "
                    f"and record it with {RECORD_ROUND}")
        round_ = "another round of the independent review" if last_review(queue["queue-completed"]) \
            else "the independent review"
        return (f"review: nothing is left to research and the report is drafted, so start {round_} "
                f"(step 4) now, and change nothing while it runs. Record it with {RECORD_ROUND}")
    if reflection_missing:
        return "hand over: write the Reflection, then run check_report.py --handover"
    return "hand over: run check_report.py --handover"


def section(lines, heading):
    """(index of the heading, index of the next heading or the end); exits if
    the ledger has no such section."""
    span = section_span(lines, heading)
    if span is None:
        raise SystemExit(f"the ledger has no {heading!r} section")
    return span


def text_span(lines, name):
    """(index of its heading, index of the next ## heading or the end) of the
    text section `name`; exits if it isn't one."""
    if name not in TEXT_SECTIONS:
        raise SystemExit("--section is one of: " + ", ".join(TEXT_SECTIONS))
    return h2_section(lines, name)


def h2_section(lines, title):
    """(index of its heading, index of the next ## heading or the end) of the
    ## section `title`; exits if the ledger has none."""
    span = h2_span(lines, title)
    if span is None:
        raise SystemExit(f"the ledger has no '## {title}' section")
    return span


def table_rows(lines, name):
    """The data rows of the table `name`, as cells; [] while it has none."""
    return ledger_rows("\n".join(lines), TABLES[name][0])


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


def header_of(lines, name):
    span = table_span(lines, TABLES[name][0])
    return table_cells(lines[span[0]]) if span else TABLES[name][1]


def findings_of(lines):
    """({ID: block text}, start, end) of the findings section."""
    start, end = h2_section(lines, FINDINGS)
    return finding_blocks("\n".join(lines[start + 1:end])), start, end


def links_section(lines):
    """{key: URL} of the Links section, keys in lower case."""
    span = section_span(lines, LINKS_HEADING)
    return link_definitions("\n".join(lines[span[0] + 1:span[1]])) if span else {}


def put_batch(lines, items, warnings):
    """Write each row and finding of `items` in order and return (every value
    as written, what each item wrote: an ID, or the table of a row without
    one). Exits at the first item that can't be written, naming it; the ledger
    is saved only after every item is, so nothing is written then."""
    if not isinstance(items, list) or not items:
        raise SystemExit(
            "the input must be a non-empty JSON list of rows and findings:\n" + COMMAND_HELP["batch"])
    written, done = [], []
    for number, item in enumerate(items, 1):
        try:
            if not isinstance(item, dict) or ("finding" in item) == ("table" in item):
                raise SystemExit("each item is a row {\"table\", \"id\", \"match\", \"cells\"} or a "
                                 "finding {\"finding\", \"id\"}, its optional keys left out")
            extra = set(item) - ({"finding", "id"} if "finding" in item
                                 else {"table", "id", "match", "cells"})
            if extra:
                raise SystemExit(f"unknown keys {', '.join(sorted(extra))}")
            if "finding" in item:
                ident, values = put_finding(
                    lines, item.get("id"), item["finding"], warnings)
            else:
                if item["table"] not in TABLES:
                    raise SystemExit(
                        "table is one of: " + ", ".join(TABLES))
                ident = item.get("id") or item["table"]
                values = put_row(lines, item["table"], item.get("id"), item.get("match"),
                                 item.get("cells"))
        except SystemExit as error:
            raise SystemExit(
                f"item {number}: {error.code}\nnothing was written")
        written += values
        done.append(ident)
    sync_sources(lines)
    return written, done


def put_row(lines, name, row_id, match, cells):
    """Write a row of the table `name` and return its cells as written; exits
    on an ID, a --match or cells the table doesn't take."""
    _, _, letters = TABLES[name]
    if bool(letters) != bool(row_id):
        raise SystemExit(
            f"{name} " + ("needs --id" if letters else "has no IDs: leave --id out"))
    if letters and match:
        raise SystemExit(f"{name} rows are replaced by --id, not --match")
    if row_id and row_id[0] not in letters:
        raise SystemExit(f"{name} IDs start with {' or '.join(letters)}")
    if name == "sources" and isinstance(cells, list) and len(cells) > 1 and isinstance(cells[1], dict):
        cells = [cells[0], search_reference(cells[1]), *cells[2:]]
    if not isinstance(cells, list) or not all(isinstance(c, str) for c in cells):
        raise SystemExit(
            "the input must be a JSON list of strings, the row's cells:\n" + table_help(name))
    written = linked(lines, [c.replace("\n", " ") for c in cells])
    set_row(lines, name, row_id, written, match)
    # An action is in one part of the queue: writing it in one takes it out of the others.
    for other in QUEUE_TABLES if name in QUEUE_TABLES else ():
        if other != name and any(row[0] == row_id for row in table_rows(lines, other)):
            write_rows(lines, other, [row for row in table_rows(lines, other) if row[0] != row_id],
                       header_of(lines, other))
    return written


def search_reference(given):
    """A search's Exact reference: its query between backticks, as the source
    rule reads it, from {"query": ...}, so no backtick is ever typed in a shell."""
    query = given.get("query") if set(given) == {"query"} else None
    if not isinstance(query, str) or not query.strip() or "`" in query or "\n" in query:
        raise SystemExit('a search\'s Exact reference is {"query": "<the exact query>"}, on one line, '
                         "without backticks")
    return f"`{query.strip()}`"


def put_finding(lines, ident, fields, warnings):
    """Write a finding, the next one when `ident` is None, and return (its ID,
    its values as written); a claim far past its length adds to `warnings`."""
    if not isinstance(fields, dict):
        raise SystemExit(
            "the input must be a JSON object, the finding's title and fields:\n" + COMMAND_HELP["findings"])
    ident = ident or next_id("\n".join(lines), "F")
    if not re.fullmatch(r"F\d+", ident):
        raise SystemExit("--id is F and its number, such as F07")
    keys = [k for k, v in fields.items() if isinstance(v, str)
            and k != "title"]
    fields.update(zip(keys, linked(lines, [fields[k] for k in keys])))
    if isinstance(fields.get("title"), str):
        # A heading: its links by reference, but no ticket linked, which
        # would change its anchor.
        fields["title"] = reference_links(lines, fields["title"])
    written = [v for v in fields.values() if isinstance(v, str)]
    check_backticks(lines, written, ident)
    set_finding(lines, ident, fields)
    too_long = claim_length_warning(ident, str(fields.get("Claim", "")))
    if too_long:
        warnings.append(too_long)
    return ident, written


def next_id(text, kind):
    if kind == "F":
        found = [ident[1:] for ident in FINDING_START.findall(text)]
    else:
        found = re.findall(rf"{ROW_START}{kind}(\d+)\s*\|", text, re.M)
    width = max([2] + [len(n) for n in found])
    return f"{kind}{max([0] + [int(n) for n in found]) + 1:0{width}d}"


def set_finding(lines, ident, fields):
    blocks, start, end = findings_of(lines)
    blocks[ident] = finding_block(ident, fields)
    write_findings(lines, blocks, start, end)


def finding_block(ident, fields):
    wanted = ["title", *FINDING_FIELDS]
    missing = [f for f in wanted if not isinstance(
        fields.get(f), str) or not fields[f].strip()]
    extra = [f for f in fields if f not in wanted + FINDING_OPTIONAL]
    if missing or extra:
        raise SystemExit("ledger.py help --table findings shows the input and a command to copy. "
                         "A finding needs these fields, each text: " +
                         ", ".join(wanted)
                         + "; it may also have " + ", ".join(FINDING_OPTIONAL)
                         + (f"; missing {', '.join(missing)}" if missing else "")
                         + (f"; unknown {', '.join(extra)}" if extra else ""))
    clean = {k: " ".join(v.split()) for k, v in fields.items()}
    return "\n".join([f"### {ident} — {clean['title']}", "", anchor_tag(ident), "",
                      *(f"- **{f}:** {clean[f]}" for f in FINDING_FIELDS + FINDING_OPTIONAL if f in clean)])


def linked(lines, values):
    """`values` with every link written by reference, and ticket keys and
    owner/repo#123 linked. Inline links go first, so a ticket or a page of a
    code host linked in one value lets the same project's keys or host's pull
    requests be linked in the others.
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


def jira_site(project):
    """The Jira site that has `project`, or None: without jira-api, or when
    the site has no such project, or it is one the user excludes."""
    if project not in SITES:
        SITES[project] = None
        if is_enabled("workflow", "jira-api"):
            try:
                client = JiraClient()
                client.project(project)
                SITES[project] = client.base_url
            except SystemExit:
                pass
    return SITES[project]


def reference_links(lines, text):
    """`text` with each inline link [text](url) written as the reference link
    [text][key] the ledger uses, its key defined in the Links section: the
    key the URL already has, else one made from the text. Writing a link inline
    costs no separate `link` call, and a URL still lives in one place."""
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
    if LINKS_HEADING not in [line.strip() for line in lines]:
        lines += ["", LINKS_HEADING, "", "None yet."]
    start, end = section(lines, LINKS_HEADING)
    definitions = links_section(lines)
    definitions[key] = url
    body = ["", *(f"[{k}]: {v}" for k, v in sorted(definitions.items(),
                  key=lambda kv: kv[0].casefold())), ""]
    lines[start + 1:end] = body


def sync_sources(lines):
    """Write each source row's `Findings: ...` from the Evidence lines of the findings."""
    cited = cited_sources("\n".join(lines))
    rows = table_rows(lines, "sources")
    for row in rows:
        row[4] = SOURCE_FINDINGS.sub("", row[4])
        if id_order(row[0])[1] in cited:
            found = sorted(cited[id_order(row[0])[1]], key=id_order)
            row[4] = f"{row[4].rstrip()} Findings: {', '.join(found)}.".strip()
    write_rows(lines, "sources", rows, header_of(lines, "sources"))


def move_row(lines, row_id, target, sets):
    source, row = find_row(lines, row_id)
    header = header_of(lines, source)
    row = with_sets(header, row, sets)
    write_rows(lines, source, [r for r in table_rows(
        lines, source) if r[0] != row_id], header)
    set_row(lines, target, row[0], row[1:])


def with_sets(names, values, sets):
    """`values`, a row's cells or a finding's fields in the order of `names`,
    with each "Name=value" of `sets` applied; exits on a name it doesn't have.
    The name is matched in any case, so one call changes one cell."""
    values = list(values)
    folded = [name.casefold() for name in names]
    for assignment in sets:
        name, _, value = assignment.partition("=")
        if name.strip().casefold() not in folded:
            raise SystemExit(
                f"no {name.strip()!r} to set; the names are: " + " | ".join(names))
        values[folded.index(name.strip().casefold())] = value
    return values


def row_with_sets(lines, name, row_id, match, sets):
    """The cells after the ID of a row already written, as written, with
    `sets` applied: the input `put_row` takes to change those cells only."""
    header = header_of(lines, name)
    rows = table_rows(lines, name)
    if row_id:
        found = [r for r in rows if r[0] == row_id]
        if not found:
            raise SystemExit(
                f"no {name} row {row_id} to --set: write it whole first")
        row = found[0]
    elif match:
        row = rows[matching_row(rows, name, match)]
    else:
        raise SystemExit(
            "--set needs the row's --id, or --match for a file-coverage row")
    row = with_sets(header, [as_written(lines, c) for c in row], sets)
    return row[1:] if TABLES[name][2] else row


def finding_with_sets(lines, ident, sets):
    """A finding already written, as written, with `sets` applied: the input
    `put_finding` takes to change those fields only."""
    if not ident:
        raise SystemExit("--set needs the finding's --id")
    fields = json.loads(show_raw(lines, ident, None, None))
    names = ["title", *FINDING_FIELDS, *FINDING_OPTIONAL]
    values = with_sets(names, [fields.get(n, "") for n in names], sets)
    return {n: v for n, v in zip(names, values) if v or n in fields}


def show_raw(lines, ident, name, heading):
    """A section, a finding, a row or a table's rows as the input their writing
    command reads."""
    if heading:
        start, end = text_span(lines, heading)
        return as_written(lines, "\n".join(lines[start + 1:end]).strip())
    if name:
        if name == "findings":
            raise SystemExit("show --raw takes a finding by --id")
        return "\n".join(json.dumps([as_written(lines, c) for c in row[1 if TABLES[name][2] else 0:]],
                                    ensure_ascii=False) for row in table_rows(lines, name)) or "None."
    _, found = record(lines, ident)
    if isinstance(found, list):
        return json.dumps([as_written(lines, c) for c in found[1:]], ensure_ascii=False)
    head, *body = found.split("\n")
    fields = {"title": head.split(" — ", 1)[1]}
    for line in body:
        if field := re.match(r"- \*\*(.+?):\*\* (.*)", line):
            fields[field[1]] = field[2]
    return json.dumps({k: as_written(lines, v) for k, v in fields.items()}, ensure_ascii=False, indent=2)


def replaced_text(lines, section_name, old, new):
    """A text section, as written, with its one `old` replaced by `new`; exits
    unless `old` is in it exactly once."""
    current = show_raw(lines, None, None, section_name)
    count = current.count(old)
    if count != 1:
        raise SystemExit(f"--replace: {old!r} is in {section_name} {count} times, not once; "
                         "copy it from show --section, with enough of the text to be unique")
    return current.replace(old, new)


def find_row(lines, row_id):
    for name in QUEUE_TABLES:
        for row in table_rows(lines, name):
            if row[0] == row_id:
                return name, row
    raise SystemExit(f"no queue row {row_id}")


def set_row(lines, name, row_id, cells, match=None):
    header = header_of(lines, name)
    row = ([row_id] if row_id else []) + list(cells)
    if len(row) != len(header):
        raise SystemExit(f"{name} has {len(header)} columns, counting the ID if it has one; got {len(row)}.\n"
                         + table_help(name))
    check_cells(lines, name, row)
    rows = table_rows(lines, name)
    if row_id:
        rows = [r for r in rows if r[0] != row_id] + [row]
        rows.sort(key=lambda row: id_order(row[0]))
    elif match:
        rows[matching_row(rows, name, match)] = row
    else:
        rows.append(row)
    write_rows(lines, name, rows, header)


def check_cells(lines, name, row):
    """Exit if a cell holds a value its column doesn't allow."""
    problem = None
    if name == "components":
        problem = status_problem(row[0], row[4])
    elif name == "file-coverage":
        problem = depth_problem(row[2]) or (
            coverage_material_missing(row) and f"for {row[0]}: link the material read in Material")
    elif name == "queue-completed":
        problem = outcome_problem(row[0], row[-1], row[2])
    elif name == "gaps":
        problem = areas_problem(row) or (
            (blocked := gap_problem(row)) and f"{blocked}. {GAP_FIX}")
    elif name == "sources":
        problem = areas_problem(row) or (
            source_reference_missing(row) and f"{row[0]}: {SOURCE_LINK_FIX}")
    if problem:
        raise SystemExit(f"{name} {problem}")
    if unread := name == "components" and unread_components([row], table_rows(lines, "file-coverage"),
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


def matching_row(rows, name, match):
    """The index of the one row of `rows` containing `match`; exits if none or
    several do. A file coverage row has no ID, so its text identifies it."""
    found = [i for i, r in enumerate(rows) if match in " | ".join(r)]
    if not found:
        raise SystemExit(f"no {name} row containing {match!r}")
    if len(found) > 1:
        raise SystemExit(
            f"{match!r} matches {len(found)} rows; use more of the text")
    return found[0]


def write_rows(lines, name, rows, header=None):
    """Put `rows` in the table `name`, creating it under its heading if there is none."""
    heading, default, letters = TABLES[name]
    anchored_rows = bool(letters)
    span = table_span(lines, heading)
    if span is None:
        start, end = section(lines, heading)
        drop_placeholder(lines, start + 1, end)
        block = ["", render(header or default), render(
            ["---"] * len(header or default))]
        block += [render(r, anchored_rows) for r in rows] + [""]
        lines[start + 1:start + 1] = block
        return
    head = lines[span[0]:span[0] + 2]
    lines[span[0]:span[1]] = head + [render(r, anchored_rows) for r in rows]
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


def render(cells, anchor=False):
    """A table row; with `anchor`, its ID carries the anchor citations link to."""
    if anchor and re.fullmatch(r"[A-Z]\d+", cells[0]):
        cells = [anchored(cells[0]), *cells[1:]]
    return table_row(cells)


def remove_finding(lines, ident):
    """Delete the finding `ident` and the sources' mentions of it; exits,
    writing nothing, while anything else in the ledger cites it."""
    blocks, start, end = findings_of(lines)
    if ident not in blocks:
        raise SystemExit(f"no finding {ident}")
    del blocks[ident]
    write_findings(lines, blocks, start, end)
    sync_sources(lines)
    refuse_cited(lines, ident)


def write_findings(lines, blocks, start, end):
    body = "\n\n".join(blocks[k] for k in sorted(
        blocks, key=id_order)) if blocks else "None yet."
    lines[start + 1:end] = ["", *body.split("\n"), ""]


def refuse_cited(lines, ident):
    """Exit, writing nothing, while anything else in the ledger cites
    `ident`: removing it would leave a citation of a record that isn't there.
    It looks wherever the handover check does, so the two agree."""
    cited = mentions(lines, ident) + cited_outside_records(lines, ident)
    if cited:
        raise SystemExit(f"{ident} is still cited by {', '.join(cited)}: change those first. "
                         "Nothing was written")


def cited_outside_records(lines, ident):
    """The headings of the parts of the ledger outside its records, such as
    the file coverage or the boundary, whose text names `ident`; records,
    which mentions() names by their ID, are left out."""
    found, heading, in_findings = [], "", False
    for line in lines:
        if line.startswith("#"):
            heading = line.lstrip("#").strip()
            in_findings = in_findings and line.startswith(
                "###") or heading == FINDINGS
        elif not in_findings and not re.match(rf"{ROW_START}[SQDGCF]\d", line) \
                and re.search(rf"\b{ident}\b", line) and heading not in found:
            found.append(heading)
    return [f"the {heading} section" for heading in found]


def mentions(lines, ident):
    """The records, other than `ident`'s own, whose text names `ident`: when
    an action closes, what they say while it was open, such as "not
    established yet: see Q06", may need its answer; while any does, `ident`
    can't be removed."""
    found = [table_row_id for table in TABLES if TABLES[table][2]
             for table_row_id in (row[0] for row in table_rows(lines, table)
                                  if row[0] != ident and re.search(rf"\b{ident}\b", " | ".join(row[1:])))]
    blocks, _, _ = findings_of(lines)
    found += [key for key, block in blocks.items()
              if key != ident and re.search(rf"\b{ident}\b", block)]
    return sorted(set(found), key=id_order)


def remove_row(lines, name, row_id, match):
    """Delete a row by its ID, or a file coverage row by `match`; exits,
    writing nothing, while anything else in the ledger cites the row's ID."""
    rows = table_rows(lines, name)
    if row_id:
        kept = [r for r in rows if r[0] != row_id]
        if len(kept) == len(rows):
            raise SystemExit(f"no {name} row {row_id}")
    else:
        index = matching_row(rows, name, match)
        kept = rows[:index] + rows[index + 1:]
    write_rows(lines, name, kept, header_of(lines, name))
    if row_id:
        refuse_cited(lines, row_id)


def remove_link(lines, key):
    start, end = section(lines, LINKS_HEADING)
    kept = [line for line in lines[start + 1:end]
            if not ((match := DEFINITION.match(line)) and match[1].casefold() == key)]
    if len(kept) == len(lines[start + 1:end]):
        raise SystemExit(f"no link {key!r}")
    if not any(line.startswith("[") for line in kept):
        kept = ["", "None yet.", ""]
    lines[start + 1:end] = kept


def record_review(lines, raised="none", stopped=None):
    """Add the independent review as a completed action answered by the
    actions it raised, which must already be in the queue, or by the user's
    choice to stop reviewing."""
    if stopped is not None:
        if not stopped.strip():
            raise SystemExit(
                "--stopped is what the user said when they chose to stop the review")
        by, outcome = "The user, asked whether to go on", f"{REVIEW_STOPPED} {stopped.strip()}"
    else:
        ids = [] if raised.strip().casefold() == "none" else [
            r.strip() for r in raised.split(",") if r.strip()]
        queued = {row[0]
                  for name in QUEUE_TABLES for row in table_rows(lines, name)}
        missing = [i for i in ids if i not in queued]
        if missing:
            raise SystemExit(f"--raised names actions not in the queue: {', '.join(missing)}. "
                             "Add each doable real issue as a ready action first")
        by = "Subagent given the skill's brief"
        outcome = "Raised " + ", ".join(ids) if ids else REVIEW_NONE
    row_id = next_id("\n".join(lines), "Q")
    set_row(lines, "queue-completed", row_id,
            ["Independent review", REVIEW_QUESTION, by, "None", "High", outcome])
    return row_id


def set_text(lines, name, text):
    start, end = text_span(lines, name)
    lines[start + 1:end] = ["", *text.strip().split("\n"), ""]


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


def link_ids(lines):
    """Write every citation of a recorded ID as a link to its anchor, so any ID
    can be followed to its row or finding. An ID cell holds the anchor itself."""
    recorded = recorded_ids("\n".join(lines))
    for i, line in enumerate(lines):
        if line.startswith("|"):
            cells = [c if ID_ANCHOR.search(c) else linked_ids(
                c, recorded) for c in table_cells(line, keep_anchors=True)]
            lines[i] = table_row(cells)
        else:
            lines[i] = linked_ids(line, recorded)


def read_input(args, as_json=False):
    """Standard input, or the file --input names; parsed as JSON when asked."""
    try:
        if args.input:
            with open(args.input, encoding="utf-8") as f:
                text = f.read()
        else:
            text = sys.stdin.read()
        return json.loads(text) if as_json else text
    except OSError as error:
        raise SystemExit(
            f"--input: cannot read {args.input}: {error.strerror}")
    except ValueError as error:
        raise SystemExit(f"the input is not valid JSON: {error}")


def load(relative):
    path, _, _ = investigation_dir(relative)
    try:
        with open(os.path.join(path, LEDGER), encoding="utf-8") as f:
            return f.read()
    except OSError:
        raise SystemExit(
            f"{relative} has no {LEDGER}: run init_investigation.py first")


def save(relative, lines):
    text = "\n".join(lines).rstrip("\n") + "\n"
    path, _ = write_output_file(
        FOLDER_NAME, f"{relative}/{LEDGER}", text.encode("utf-8"))
    return path


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Edit the research ledger's tables, findings, text and links by ID.")
    commands = parser.add_subparsers(dest="command", required=True)
    # What each command does; `help` prints the input each writing one reads.
    names = {
        "next-id": "print the next free ID of a kind",
        "row": "write a table's row, its cells on standard input",
        "batch": "write many rows and findings in one call, all or nothing",
        "move": "move an action between ready, in progress, blocked and completed",
        "remove": "delete a row or a finding",
        "finding": "add or replace a finding, read from standard input",
        "link": "add a link definition under Links",
        "unlink": "remove a link definition",
        "sync-sources": "rewrite each source's findings from the findings' evidence",
        "text": "replace a text section, read from standard input",
        "show": "print a finding, a row, a table or a text section",
        "find": "print every record that mentions a text",
        "status": "print the counts, open work and the next step",
        "brief": "print what writing the report reads",
        "help": "print each table's columns and values, and each writing command's input, with a command to copy",
        "review": "record an independent review round",
    }
    # The commands that read their input from standard input, and the `help`
    # entry that shows its shape.
    shapes = {"row": "<table>", "batch": "batch",
              "finding": "findings", "text": "text"}
    for name, about in names.items():
        description = about + (f". `{CALL} help --table {shapes[name]}` shows the input and a command to copy"
                               if name in shapes else "")
        sub = commands.add_parser(name, help=about, description=description)
        if name == "help":
            sub.add_argument("--table", choices=list(TABLES) + list(COMMAND_HELP),
                             help="a table, or one of the other commands: " + ", ".join(COMMAND_HELP) + "; leave out for all")
            continue
        sub.add_argument("--investigation", required=True,
                         help="<Topic>_<YY-MM-DD>")
        if name in ("row", "batch", "finding", "text"):
            sub.add_argument("--input", help="a file to read instead of standard input, such as one "
                             "written in your scratch folder, so nothing needs quoting in the shell")
        if name == "review":
            choice = sub.add_mutually_exclusive_group(required=True)
            choice.add_argument("--raised",
                                help="the ready actions the review's real issues became, comma separated, or none")
            choice.add_argument("--stopped",
                                help="what the user said when, asked whether to go on, they chose to stop")
        if name == "next-id":
            sub.add_argument("--kind", required=True, choices=list("SQFCDG"),
                             help="the ID's letter")
        if name in ("row", "remove"):
            sub.add_argument("--table", required=True, choices=list(TABLES) +
                             (["findings"] if name == "remove" else []), help="the table")
            sub.add_argument(
                "--id", help="the row's ID; leave out for file-coverage")
            sub.add_argument(
                "--match", help="for file-coverage: text only the row to " + ("replace" if name == "row" else
                                                                              "remove") + " contains, such as its file's name")
        if name == "finding":
            sub.add_argument(
                "--id", help="the finding to replace; leave out to add the next one")
        if name in ("row", "finding"):
            sub.add_argument("--set", action="append", default=[],
                             help='"Name=value": change one cell or field of a row or finding already written, '
                             "instead of reading the whole input; repeat for more")
        if name == "move":
            sub.add_argument("--id", required=True, help="the action's ID")
            sub.add_argument("--to", required=True,
                             choices=[table.removeprefix("queue-") for table in QUEUE_TABLES], help="where it goes")
            sub.add_argument("--set", action="append",
                             default=[], help='"Column=value"')
        if name in ("link", "unlink"):
            sub.add_argument("--key", required=True,
                             help="the link's key, as reference links name it")
        if name == "link":
            sub.add_argument("--url", required=True, help="the link's URL")
        if name == "show":
            sub.add_argument(
                "--id", help="a finding, or a row's ID")
            sub.add_argument("--table", choices=list(TABLES) + ["findings"],
                             help="a whole table")
            sub.add_argument(
                "--section", help="a text section, printed as written: " + " or ".join(TEXT_SECTIONS))
            sub.add_argument("--raw", action="store_true",
                             help="print a finding or rows as the input their writing command reads")
        if name == "find":
            sub.add_argument("--text", required=True,
                             help="the text to look for, such as a source, a file or a term")
        if name == "text":
            sub.add_argument("--section", required=True,
                             help=" or ".join(TEXT_SECTIONS))
            sub.add_argument("--replace", nargs=2, metavar=("OLD", "NEW"),
                             help="replace one exact text of the section, instead of reading the whole of it")
    args = parser.parse_args(argv)
    if args.command == "help":
        if not args.table:
            print(full_help())
        else:
            print(table_help(args.table)
                  if args.table in TABLES else COMMAND_HELP[args.table])
        return
    text = load(args.investigation)
    lines = text.split("\n")
    result, warnings = {}, []
    written, read_batch = [], []
    if args.command == "brief":
        print(brief(lines))
        return
    if args.command in ("show", "find", "status"):
        if args.command == "show" and sum(map(bool, (args.id, args.table, args.section))) != 1:
            raise SystemExit("show takes one of --id, --table or --section")
        if args.command == "show" and (args.raw or args.section):
            print(show_raw(lines, args.id, args.table, args.section))
            return
        folder = investigation_dir(args.investigation)[0]
        report = bool(glob.glob(os.path.join(
            glob.escape(folder), f"*{REPORT_SUFFIX}")))
        # Anchors are for viewers; the plain text costs fewer tokens without them.
        print(strip_anchors({"show": lambda: show(lines, args.id, args.table), "find": lambda: find(lines, args.text),
                             "status": lambda: status(lines, report)}[args.command]()))
        return
    if args.command == "next-id":
        print(json.dumps({"id": next_id(text, args.kind)}))
        return
    if args.command == "row":
        cells = (row_with_sets(lines, args.table, args.id, args.match, args.set) if args.set
                 else read_input(args, as_json=True))
        written = put_row(lines, args.table, args.id, args.match, cells)
        if args.table == "sources":
            sync_sources(lines)
    elif args.command == "batch":
        read_batch = read_input(args, as_json=True)
        written, result["written"] = put_batch(lines, read_batch, warnings)
    elif args.command == "move":
        columns = [s.partition("=")[0] for s in args.set]
        values = written = linked(
            lines, [s.partition("=")[2] for s in args.set])
        move_row(lines, args.id, f"queue-{args.to}",
                 [f"{c}={v}" for c, v in zip(columns, values)])
    elif args.command == "remove":
        if args.table == "findings":
            if not args.id:
                raise SystemExit("findings need --id")
            remove_finding(lines, args.id)
        else:
            _, _, letters = TABLES[args.table]
            if bool(letters) == bool(args.match) or (letters and not args.id):
                raise SystemExit(
                    f"{args.table} " + ("takes --id" if letters else "has no IDs: use --match"))
            remove_row(lines, args.table, args.id, args.match)
    elif args.command == "finding":
        fields = finding_with_sets(
            lines, args.id, args.set) if args.set else read_input(args, as_json=True)
        result["id"], written = put_finding(lines, args.id, fields, warnings)
        sync_sources(lines)
    elif args.command == "link":
        if not re.fullmatch(r"[A-Za-z0-9._-]+", args.key) or not re.match(r"https?://", args.url):
            raise SystemExit(
                "--key is letters, digits, dots, hyphens and underscores; --url starts with http(s)://")
        set_link(lines, args.key.casefold(), args.url)
    elif args.command == "unlink":
        remove_link(lines, args.key.casefold())
    elif args.command == "review":
        result["id"] = record_review(
            lines, args.raised or "none", args.stopped)
    elif args.command == "sync-sources":
        sync_sources(lines)
    elif args.command == "text":
        text = replaced_text(lines, args.section, *
                             args.replace) if args.replace else read_input(args)
        written = linked(lines, [text])
        check_backticks(lines, written, args.section)
        set_text(lines, args.section, written[0])
    # An action closed by this call: the records naming it may need its answer.
    closed = ([args.id] if (args.command == "move" and args.to == "completed")
              or (args.command == "row" and args.table == "queue-completed") else
              [item["id"] for item in read_batch if isinstance(
                  item, dict) and item.get("table") == "queue-completed"]
              if args.command == "batch" else [])
    if named := {ident: found for ident in closed if (found := mentions(lines, ident))}:
        result["update_if_needed"] = named
    upgrade_tickets(lines)
    link_ids(lines)
    # Checked once every record of the call is written, so a batch can hold
    # records that cite each other.
    missing = unrecorded_citations(written, "\n".join(lines))
    if missing:
        raise SystemExit(f"cites {', '.join(missing)}, which the ledger doesn't hold: write each in the same "
                         "call, such as one batch, or before it. Nothing was written")
    if warnings:
        result["warnings"] = warnings
    print(json.dumps({"path": save(args.investigation, lines), **result}))


if __name__ == "__main__":
    main()
