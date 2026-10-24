"""Checks a report and its ledger, read-only: their structure, links and local
files, and, at handover, the rules a finished investigation meets. It checks
the form of the evidence, not whether it is true.

It recognizes the skill's ordinary Markdown output, not every Markdown
extension.
"""
import argparse
import json
import os
from pathlib import Path
import re

from common import (COMPONENT_HEADER, DESIGN_TABLES, design_problem, CELL_PIPE, DEFINITION, claim_length_warning, FINDING_FIELDS, FINDING_HEADING, FINDINGS, GAP_FIX, HEADING, LEDGER, LEDGER_SECTIONS, LINKS, QUERY, QUEUE, QUEUE_SUBSECTIONS, REFERENCE_LINK, SOURCE_FINDINGS, SOURCE_LINK_FIX, TABLE_HEADINGS, anchor_ids, areas_problem, backtick_error, cited_sources, component_rows, coverage_material_missing,
                    depth_problem, expected_files, finding_blocks, gap_problem, h2_span, headings, id_order, ledger_rows, link_definitions, link_text, links, listed, local_link, markdown, outcome_problem, reference_key, report_headings, review_problem, section_span, source_reference_missing, status_problem, strip_anchors, table_cells, unlinked_backticks, unlinked_references, unread_components, unread_message, unrecorded_ids)


def check_report(report, handover=False):
    """Return actionable JSON-compatible errors/warnings without modifying files."""
    report = Path(report)
    errors, warnings = [], []
    result = {"ok": False, "errors": errors, "warnings": warnings}
    if not report.is_absolute():
        errors.append("--report must be an absolute Markdown path.")
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
    for line, row in table_rows(prose):
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
                          + ". It holds only the skill's files; keep working files in your own scratch folder.")
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
    queue's in order, one heading per finding with its fields, every ticket and
    pull request linked, and, at handover, a queue with nothing left ready or in
    progress, the review finished, completed actions answered, allowed
    statuses, depths and areas, the system design's rules, code read for every
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
    findings = FINDING_HEADING.findall(body)
    duplicates = sorted({f for f in findings if findings.count(f) > 1})
    if duplicates:
        errors.append(f"{LEDGER}: duplicate findings: " +
                      ", ".join(duplicates))
    for ident, entry in finding_blocks(h2_text(body, FINDINGS) or "").items():
        missing = [f for f in FINDING_FIELDS if not re.search(
            rf"\*\*{re.escape(f)}\b[^*]*:?\*\*", entry)]
        if missing:
            warnings.append(
                f"{LEDGER}: {ident} lacks " + ", ".join(missing))
        claim = re.search(
            r"\*\*Claim:?\*\*:?(.*?)(?=\n- \*\*|\Z)", entry, re.S)
        too_long = claim_length_warning(ident, claim[1] if claim else "")
        if too_long:
            warnings.append(f"{LEDGER}: {too_long}")
    cited = set(re.findall(r"\bF\d+\b", re.sub(FINDING_HEADING, "", body)))
    undefined = sorted(cited - set(findings), key=id_order)
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
        unrecorded = unrecorded_ids(body)
        if unrecorded:
            errors.append(
                f"{LEDGER}: IDs cited but never recorded: " + ", ".join(unrecorded))
        blocked = gap_problems(body)
        if blocked:
            errors.append(f"{LEDGER}: " + "; ".join(blocked) +
                          ". A gap's " + GAP_FIX)
        if any(row[0].startswith("Q") for table in ("queue-ready", "queue-in-progress")
               for row in ledger_rows(body, TABLE_HEADINGS[table])):
            errors.append(
                f"{LEDGER}: actions are still ready or in progress; answer or block them before handover")
        # The trail from a claim to its source ends in a link, or, for a search, which has
        # no URL to pin, in its exact query between backticks.
        register = failing_rows(body, TABLE_HEADINGS["sources"], 2,
                                source_reference_missing)
        if register:
            errors.append(f"{LEDGER}: source register rows without a link to their exact reference: "
                          + ", ".join(register) + "; " + SOURCE_LINK_FIX)
        coverage = failing_rows(
            body, TABLE_HEADINGS["file-coverage"], 1, coverage_material_missing)
        if coverage:
            errors.append(f"{LEDGER}: File reading coverage rows without a link to the material read: "
                          + ", ".join(sorted(set(coverage))))
        mismatched = source_finding_problems(body)
        if mismatched:
            errors.append(f"{LEDGER}: a source's Findings differ from the findings whose Evidence names it ("
                          + "; ".join(mismatched) + "). Run ledger.py sync-sources")
        spans = unlinked_backticks(without_queries(body))
        if spans:
            errors.append(backtick_error(LEDGER, spans))
    return errors, warnings


def h2_text(body, title):
    """The text of the ledger's ## `title` section, up to the next ## heading,
    or None without one."""
    lines = body.split("\n")
    span = h2_span(lines, title)
    return "\n".join(lines[span[0] + 1:span[1]]) if span else None


def table_rows(prose):
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
    """Source rows whose `Findings:` differ from the findings whose Evidence line names them."""
    cited = cited_sources(body)
    problems = []
    for cells in ledger_rows(body, TABLE_HEADINGS["sources"]):
        if len(cells) < 5 or not re.fullmatch(r"S\d+", cells[0]):
            continue
        written = SOURCE_FINDINGS.search(cells[4])
        have = set(re.findall(r"F\d+", written[1])) if written else set()
        want = cited.get(id_order(cells[0])[1], set())
        if have != want:
            problems.append(f"{cells[0]} lists {', '.join(sorted(have)) or 'none'}, "
                            f"its findings are {', '.join(sorted(want)) or 'none'}")
    return problems


def without_queries(body):
    """`body` with the queries of the source register's rows blanked. A search
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
    return (f"{where}: tickets and pull requests written without a link: {listed(found)}. "
            "Write them through ledger.py or make_report.py, which link them, a pull request as owner/repo#123")


def closing_problems(body):
    """The independent review not yet finished, completed actions with no
    answer, coverage depths, component statuses and source or gap areas that
    are not allowed ones, and components claiming code nobody read."""
    problems = []
    completed = ledger_rows(body, TABLE_HEADINGS["queue-completed"])
    problems.append(review_problem(completed))
    for row in completed:
        if re.fullmatch(r"Q\d+", row[0]):
            problems.append(outcome_problem(
                row[0], row[-1], row[2] if len(row) > 2 else ""))
    coverage = [row for row in ledger_rows(body, TABLE_HEADINGS["file-coverage"])
                if len(row) > 2]
    problems += [depth_problem(row[2]) for row in coverage]
    components = component_rows(body)
    problems += [status_problem(row[0], row[4]) for row in components]
    # The system design's rules, as ledger.py applies them on write.
    problems += [design_problem("components", row)
                 for row in components if len(row) == len(COMPONENT_HEADER)]
    problems += [design_problem(table, row) for table in DESIGN_TABLES
                 for row in ledger_rows(body, TABLE_HEADINGS[table]) if re.fullmatch(r"[BEIP]\d+", row[0])]
    problems += [areas_problem(row) for table in ("sources", "gaps")
                 for row in ledger_rows(body, TABLE_HEADINGS[table]) if re.fullmatch(r"[SG]\d+", row[0])]
    definitions = link_definitions(body)
    unread = unread_components(components, coverage, definitions)
    if unread:
        problems.append(unread_message(unread))
    return [p for p in problems if p]


def gap_problems(body):
    """The gaps whose Blocked by isn't allowed (gap_problem)."""
    return [p for cells in ledger_rows(body, TABLE_HEADINGS["gaps"])
            if re.fullmatch(r"G\d+", cells[0]) and len(cells) >= 5 and (p := gap_problem(cells))]


def failing_rows(body, heading, width, failing):
    """The first cell, as plain text, of the rows under `heading` that
    `failing` rejects: a source's ID, or the source a file coverage row cites."""
    return [link_text(cells[0]).strip() for cells in ledger_rows(body, heading)
            if len(cells) > width and failing(cells)]


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Check a report's structure and local files; --handover adds the handover checks.",
        epilog='Prints one line of JSON, {"ok": bool, "errors": [...], "warnings": [...]}, and exits 1 '
        "unless the report passes.")
    parser.add_argument("--report", required=True,
                        help="Absolute path of the Markdown report.")
    parser.add_argument("--handover", action="store_true",
                        help="also apply every handover check")
    args = parser.parse_args(argv)
    result = check_report(args.report, args.handover)
    print(json.dumps(result))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
