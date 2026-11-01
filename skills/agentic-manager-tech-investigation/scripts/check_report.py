"""Checks a report and its ledger, read-only: their structure, links and local
files, and, at handover, the rules a finished investigation meets. It checks
the form of the evidence, not whether it is true.

It recognizes the skill's ordinary Markdown output, not every Markdown
extension.
"""
import os
from pathlib import Path
import re

from common import (CELL_PIPE, CITATION, DECISION_HEADER, DEFINITION, DESIGN_ORDER, FLOW_HEADER, GAP_HEADER, HEADING,
                    IDENTITY_HEADER, LEDGER, LEDGER_SECTIONS, LINKS, QUERY, QUEUE, QUEUE_HEADER, QUEUE_SUBSECTIONS,
                    REFERENCE_LINK, SOURCE_FINDINGS_COLUMN, TABLE_HEADINGS, UNUSED, anchor_ids, backtick_error,
                    blocked_problem, cited_evidence_problem, cited_sources, claim_length_problem, design_evidence,
                    design_row_problem, expected_files, finding_problem, flow_states, gap_problem, headings, id_order,
                    identity_states, ids, ledger_rows, link_definitions, links, listed, local_link, markdown,
                    outcome_problem, partial_read_problem, read_in_part, records, reference_key, report_headings,
                    review_problem, scope_problem, section_span, source_problem, strip_anchors, table_cells,
                    unlinked_backticks, unlinked_references, unrecorded_ids)


def check_report(report, handover=False):
    """The result of checking `report` and its ledger, {ok, errors, warnings};
    with `handover`, the handover rules too."""
    report = Path(report)
    errors, warnings = [], []
    result = {"ok": False, "errors": errors, "warnings": warnings}
    if not report.is_absolute():
        errors.append("The report's path must be absolute.")
        return result
    try:
        text = report.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        errors.append("Cannot read report as UTF-8 Markdown.")
        return result
    prose, fences, unclosed = markdown(text)
    if unclosed:
        errors.append("Report has an unclosed code fence.")
    found = [match for match in HEADING.finditer(
        prose) if len(match[1]) in (2, 3)]
    actual = [(len(match[1]), match[2]) for match in found]
    expected = report_headings()
    if actual != expected:
        errors.append("H2/H3 headings must occur exactly in this order: " +
                      " → ".join("#" * level + " " + title for level, title in expected))
    definitions = link_definitions(prose)
    all_links = list(links(prose, definitions))
    checked, headings_of = set(), {}
    for start, _, _, target in all_links:
        line = text.count("\n", 0, start) + 1
        if target is None:
            errors.append(f"Line {line}: unresolved Markdown link reference.")
            continue
        local = local_link(report, target)
        if local is None or local[0] == report:
            continue
        path, anchor = local
        if anchor and path.suffix.lower() == ".md" and path.is_file():
            if path not in headings_of:
                try:
                    headings_of[path] = anchors(path)
                except (OSError, UnicodeError):
                    headings_of[path] = set()
            if anchor not in headings_of[path]:
                file, _, fragment = target.partition("#")
                errors.append(
                    f"Line {line}: {file} has no heading for #{fragment}")
        if path in checked:
            continue
        checked.add(path)
        if not path.exists():
            errors.append(
                f"Line {line}: local link target is missing: {target}")
    if not (report.parent / LEDGER).is_file():
        errors.append(f"Missing research artifact: {LEDGER}.")
    else:
        ledger_errors, ledger_warnings = check_ledger(
            report.parent / LEDGER, handover)
        errors += ledger_errors
        warnings += ledger_warnings
    # Every table row carries its evidence: a source link or a ledger link.
    for line, row in report_table_rows(prose):
        citations = [target for _, _, image, target in links(
            row, definitions) if not image and target]
        if not citations and not re.search(r"https?://[^\s<>]+", row):
            errors.append(
                f"Line {line}: table row needs a point-of-use source link or a ledger link.")
    if handover:
        extra = sorted(name for name in os.listdir(report.parent)
                       if not name.startswith(".") and name not in expected_files(report.name))
        if extra:
            errors.append("Unexpected files in the investigation folder: " + ", ".join(extra)
                          + ". It holds only the skill's files; keep working files in the working folder the task names.")
        try:
            ledger_text = (report.parent / LEDGER).read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            ledger_text = ""
        # The report's tickets are linked from the ledger's links, so those say
        # which projects a ticket key can be linked to.
        spans = unlinked_backticks(prose, ledger_text)
        if spans:
            errors.append(backtick_error(report.name, spans))
    if unlinked := unlinked_references(prose):
        errors.append(reference_error(report.name, unlinked))
    result["ok"] = not errors
    return result


def check_ledger(path, handover=False):
    """(errors, warnings) of the ledger's structure: its sections and the
    queue's in order, findings written once and every one cited written, every
    ticket and pull request linked, and, at handover, a queue with nothing left
    ready or in progress, the review finished, completed questions answered,
    blocked ones naming what blocks them, the rows of scope boundaries,
    sources, findings, gaps, decisions, components and the system design within their rules, code read for every
    component claiming it, and linked sources."""
    errors, warnings = [], []
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        errors.append(
            f"{LEDGER}: cannot read research ledger as UTF-8 Markdown.")
        return errors, warnings
    body, _, _ = markdown(text)
    found = [(level, title)
             for level, title, _ in headings(text) if level in (2, 3)]
    sections = [title for level, title in found if level == 2]
    if sections != LEDGER_SECTIONS:
        errors.append(
            f"{LEDGER}: ## sections must be exactly, in order: " + " → ".join(LEDGER_SECTIONS))
    queue = []
    if QUEUE in sections:
        start = found.index((2, QUEUE)) + 1
        for level, title in found[start:]:
            if level == 2:
                break
            queue.append(title)
    if queue != QUEUE_SUBSECTIONS:
        errors.append(f"{LEDGER}: the queue needs exactly these ### subsections, in order: "
                      + " → ".join(QUEUE_SUBSECTIONS))
    findings = [row for row in ledger_rows(
        body, TABLE_HEADINGS["findings"]) if len(row) > 1]
    written = [row[0] for row in findings]
    duplicates = sorted(
        {f for f in written if written.count(f) > 1}, key=id_order)
    if duplicates:
        errors.append(f"{LEDGER}: findings written more than once: " +
                      ", ".join(duplicates) + "; keep one row each")
    for row in findings:
        too_long = claim_length_problem(row[0], row[1])
        if too_long:
            errors.append(f"{LEDGER}: {too_long}")
    # Only a citation refers to a finding; a bare F-shaped word is prose.
    undefined = sorted({m[1] for m in CITATION.finditer(body) if m[1].startswith("F")} - set(written),
                       key=id_order)
    if undefined:
        errors.append(
            f"{LEDGER}: findings cited but never written: " + ", ".join(undefined))
    missing_keys, unused_keys = reference_problems(body)
    if missing_keys:
        errors.append(
            f"{LEDGER}: reference links without a definition in ## {LINKS}: " + ", ".join(missing_keys))
    if unused_keys:
        warnings.append(
            f"{LEDGER}: definitions in ## {LINKS} never used: " + ", ".join(unused_keys))
    if unlinked := unlinked_references(without_queries(body)):
        errors.append(reference_error(LEDGER, unlinked))
    if handover:
        errors += [f"{LEDGER}: {p}" for p in closing_problems(body)]
        # Findings are checked against their own table above, once.
        unrecorded = [i for i in unrecorded_ids(body) if not i.startswith("F")]
        if unrecorded:
            errors.append(
                f"{LEDGER}: IDs cited but never recorded: " + ", ".join(unrecorded))
        if any(row[0].startswith("Q") for table in ("queue-ready", "queue-in-progress")
               for row in ledger_rows(body, TABLE_HEADINGS[table])):
            errors.append(
                f"{LEDGER}: questions are still ready or in progress; answer or block them before handover")
        mismatched = source_finding_problems(
            body) + derived_state_problems(body)
        if mismatched:
            errors.append(f"{LEDGER}: a column the script writes differs from what it is written from ("
                          + "; ".join(mismatched) + "). The ledger was edited by hand: change it only through investigate.py submit, "
                          "which keeps them in step")
        spans = unlinked_backticks(without_queries(body))
        if spans:
            errors.append(backtick_error(LEDGER, spans))
    return errors, warnings


def report_table_rows(prose):
    """(line number, line) of each data row of the pipe tables with a Markdown
    separator line."""
    lines = prose.splitlines()
    active = False
    for index, line in enumerate(lines):
        cells = table_cells(line)
        separator = len(cells) > 1 and all(
            re.fullmatch(r":?-+:?", cell) for cell in cells)
        if separator and index and "|" in lines[index - 1]:
            active = True
            continue
        if active and "|" in line and line.strip():
            yield index + 1, line
        else:
            active = False


def anchors(path):
    """Every anchor of a Markdown file: its headings', with -1, -2... for
    repeats, and the HTML anchors of the ledger's IDs."""
    text = path.read_text(encoding="utf-8")
    return {anchor for _, _, anchor in headings(text)} | anchor_ids(text)


def reference_problems(body):
    """(keys used but not defined, keys defined but never used) of the reference links in `body`."""
    defined = set(link_definitions(body))
    used = {reference_key(match) for match in REFERENCE_LINK.finditer(
        DEFINITION.sub(" ", body))}
    return sorted(used - defined), sorted(defined - used)


def source_finding_problems(body):
    """Source rows whose Findings differ from the findings whose Sources name them."""
    cited = cited_sources(body)
    problems = []
    for cells in ledger_rows(body, TABLE_HEADINGS["sources"]):
        if len(cells) <= SOURCE_FINDINGS_COLUMN or not re.fullmatch(r"S\d+", cells[0]):
            continue
        have = set(ids(cells[SOURCE_FINDINGS_COLUMN], "F"))
        want = cited.get(id_order(cells[0])[1], set())
        if have != want:
            problems.append(f"{cells[0]} lists {', '.join(sorted(have)) or 'none'}, "
                            f"its findings are {', '.join(sorted(want)) or 'none'}")
    return problems


def derived_state_problems(body):
    """Identity and flow rows whose State differs from their connections'."""
    connections = records(body, "connections")
    flows = records(body, "flows")
    identities = records(body, "identities")
    problems = []
    for rows, header, states in ((identities, IDENTITY_HEADER, identity_states(connections)),
                                 (flows, FLOW_HEADER, flow_states(flows, connections))):
        column = header.index("State")
        problems += [f"{row[0]} has State {row[column]}, its connections give {states.get(row[0], UNUSED)}"
                     for row in rows if row[column].strip() != states.get(row[0], UNUSED)]
    return problems


def without_queries(body):
    """`body` with the queries of the sources' rows blanked. A search
    has no URL to pin, so its reference cell holds its exact query in plain
    text between backticks: visible, and neither a reference to link nor a
    ticket to link."""
    lines = body.split("\n")
    span = section_span(lines, TABLE_HEADINGS["sources"])
    if span is None:
        return body
    for i in range(span[0] + 1, span[1]):
        cells = CELL_PIPE.split(lines[i])
        if len(cells) > 3 and re.fullmatch(r"S\d+", strip_anchors(cells[1]).strip()):
            cells[3] = QUERY.sub("", cells[3])
            lines[i] = "|".join(cells)
    return "\n".join(lines)


def reference_error(where, found):
    """The error for tickets and pull requests found written without a link."""
    return (f"{where}: tickets and pull requests written without a link: {listed(found)}. "
            "Write them through investigate.py submit, which links them, a pull request as owner/repo#123")


def closing_problems(body):
    """The independent review not yet finished, completed questions with no
    answer, blocked questions that don't say what blocks them, and scope
    boundaries, sources, findings, gaps, decisions, components and system
    design rows that break the rules ledger.py applies on write."""
    problems = []
    evidence = design_evidence(body)
    findings, sources = evidence["findings"], evidence["sources"]
    problems.append(review_problem(
        ledger_rows(body, TABLE_HEADINGS["reviews"])))
    problems += [outcome_problem(row[0], row[-1], row[2], evidence["scope"])
                 for row in records(body, "queue-completed")]
    blocked = records(body, "queue-blocked")
    blocked_ids = {row[0] for row in blocked}
    depends = QUEUE_HEADER.index("Depends on")
    problems += [blocked_problem(row[0], row[depends], blocked_ids)
                 for row in blocked]
    # The rules ledger.py applies on write.
    problems += [design_row_problem(table, row, evidence)
                 for table in DESIGN_ORDER for row in records(body, table)]
    # The trail from a claim to its source ends in a link, or, for a search,
    # which has no URL to pin, in its exact query between backticks.
    problems += [source_problem(row, evidence["definitions"])
                 for row in sources.values()]
    partial = {ident for ident, row in sources.items() if read_in_part(row)}
    problems += [finding_problem(row) or partial_read_problem(row, partial)
                 for row in findings.values()]
    problems += [gap_problem(row) or cited_evidence_problem(row[0], row[GAP_HEADER.index("Evidence")])
                 for row in records(body, "gaps")]
    problems += [cited_evidence_problem(row[0], row[DECISION_HEADER.index("Evidence")])
                 for row in records(body, "decisions")]
    problems += [scope_problem(row)
                 for row in records(body, "scope")]
    return [p for p in problems if p]
