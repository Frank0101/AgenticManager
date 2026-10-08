"""Read-only checks of report structure and local artifacts, not evidence truth.

    python3 check_report.py --report <absolute report path> [--handover]

This deliberately recognizes the skill's ordinary Markdown output, not every
Markdown extension. Sequence syntax and visual layout still need their own review.

Prints one line of JSON: "ok", and the "errors" and "warnings" found. Exits 1
unless the report passes.
"""
import argparse
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET
from urllib.parse import unquote, urlsplit

from common import (FINDING_FIELDS, FINDING_HEADING, LEDGER, LEDGER_SECTIONS, MERMAIDS, QUEUE_SUBSECTIONS,
                    ROADMAP_ROWS, STAGES, DEFINITION, headings, links, markdown, read_skip, report_headings)

ROADMAP_STAGES = [label for _, label in ROADMAP_ROWS]
MAPS = {title: filename for _, title, filename in STAGES}
GAP = re.compile(
    r"\b(evidence gap|not established|unavailable|unverified|insufficient evidence|no evidence)\b", re.I)


def table_rows(prose):
    """Find data rows only in pipe tables with a Markdown separator line."""
    lines = prose.splitlines()
    active = False
    for index, line in enumerate(lines):
        cells = [part.strip() for part in re.split(
            r"(?<!\\)\|", line.strip().strip("|"))]
        separator = len(cells) > 1 and all(
            re.fullmatch(r":?-+:?", cell) for cell in cells)
        if separator and index and "|" in lines[index - 1]:
            active = True
            continue
        if active and "|" in line and line.strip():
            yield index + 1, cells, line
        else:
            active = False


def diagram_kind(source):
    # Init directives and Mermaid comments may precede the diagram declaration.
    match = re.search(r"^\s*(flowchart|graph|sequenceDiagram)\b", source, re.M)
    return match[1] if match else None


def has_gap(text, subject):
    return any(GAP.search(paragraph) and re.search(subject, paragraph, re.I)
               for paragraph in re.split(r"\n\s*\n", text))


def anchors(path):
    """Every heading anchor of a Markdown file, with -1, -2... for repeats."""
    return {anchor for _, _, anchor in headings(path.read_text(encoding="utf-8"))}


def check_ledger(path, handover=False):
    """(errors, warnings) of the ledger's structure: its sections and the
    queue's in order, one heading per finding with its fields, and, at
    handover, nothing left ready and a recorded reflection."""
    errors, warnings = [], []
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        errors.append(
            "ledgers.md: cannot read research ledger as UTF-8 Markdown.")
        return errors, warnings
    body, _, _ = markdown(text)
    found = [(len(m[1]), m[2]) for m in re.finditer(
        r"^ {0,3}(#{2,3})\s+(.+?)\s*#*\s*$", body, re.M)]
    sections = [title for level, title in found if level == 2]
    if sections != LEDGER_SECTIONS:
        errors.append(
            "ledgers.md: ## sections must be exactly, in order: " + " → ".join(LEDGER_SECTIONS))
    queue = []
    if "Research action queue" in sections:
        start = found.index((2, "Research action queue")) + 1
        for level, title in found[start:]:
            if level == 2:
                break
            queue.append(title)
    if queue != QUEUE_SUBSECTIONS:
        errors.append("ledgers.md: the queue needs exactly these ### subsections, in order: "
                      + " → ".join(QUEUE_SUBSECTIONS))
    findings = FINDING_HEADING.findall(body)
    duplicates = sorted({f for f in findings if findings.count(f) > 1})
    if duplicates:
        errors.append("ledgers.md: duplicate findings: " +
                      ", ".join(duplicates))
    for match in FINDING_HEADING.finditer(body):
        end = re.compile(r"^#{1,3}\s", re.M).search(body, match.end())
        entry = body[match.end():end.start() if end else len(body)]
        missing = [f for f in FINDING_FIELDS if not re.search(
            rf"\*\*{re.escape(f)}\b[^*]*:?\*\*", entry)]
        if missing:
            warnings.append(
                f"ledgers.md: {match[1]} lacks " + ", ".join(missing))
    cited = set(re.findall(r"\bF\d+\b", re.sub(FINDING_HEADING, "", body)))
    undefined = sorted(cited - set(findings), key=lambda f: int(f[1:]))
    if undefined:
        errors.append(
            "ledgers.md: findings cited but never written: " + ", ".join(undefined))
    if handover:
        ready = re.search(
            r"^### Ready / in progress\s*$(.*?)(?=^#{2,3}\s)", body, re.M | re.S)
        if ready and re.search(r"^\|\s*Q\d+", ready[1], re.M):
            errors.append(
                "ledgers.md: actions are still ready or in progress; finish, block or reject them before handover")
        history = body.find("## Correction history")
        if history < 0 or not re.search(r"^### Reflection\s*$", body[history:], re.M):
            errors.append(
                "ledgers.md: add the ### Reflection subsection under ## Correction history before handover")
    return errors, warnings


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
    found = list(re.finditer(r"^ {0,3}(#{2,3})\s+(.+?)\s*#*\s*$", prose, re.M))
    actual = [(len(match[1]), match[2]) for match in found]
    # Sections content.json skips, because the research showed they don't apply.
    expected = report_headings(read_skip(report.parent))
    if actual != expected:
        errors.append("H2/H3 headings must occur exactly in this order: " +
                      " → ".join("#" * level + " " + title for level, title in expected))
    sections = {match[2]: (match.end(), found[i + 1].start() if i + 1 < len(found) else len(text))
                for i, match in enumerate(found)}
    definitions = {m[1].casefold(): m[2].strip("<>")
                   for m in DEFINITION.finditer(prose)}
    all_links = list(links(prose, definitions))
    checked, headings_of = set(), {}
    for start, _, _, target in all_links:
        line = text.count("\n", 0, start) + 1
        if target is None:
            errors.append(f"Line {line}: unresolved Markdown link reference.")
            continue
        parsed = urlsplit(target)
        if parsed.scheme or parsed.netloc or not parsed.path:
            continue
        path = report.parent / unquote(parsed.path)
        if parsed.fragment and path.suffix.lower() == ".md" and path.is_file():
            if path not in headings_of:
                try:
                    headings_of[path] = anchors(path)
                except (OSError, UnicodeError):
                    headings_of[path] = set()
            if unquote(parsed.fragment).lower() not in headings_of[path]:
                errors.append(
                    f"Line {line}: {parsed.path} has no heading for #{parsed.fragment}")
        if path in checked:
            continue
        checked.add(path)
        if not path.exists():
            errors.append(
                f"Line {line}: local link target is missing: {target}")
        elif path.suffix.lower() == ".svg":
            try:
                root = ET.parse(path).getroot()
                if root.tag not in ("svg", "{http://www.w3.org/2000/svg}svg"):
                    raise ValueError("not SVG")
            except (OSError, ET.ParseError, ValueError):
                errors.append(
                    f"Line {line}: local SVG is not valid SVG XML: {target}")
    if not (report.parent / LEDGER).is_file():
        errors.append(f"Missing research artifact: {LEDGER}.")
    else:
        ledger_errors, ledger_warnings = check_ledger(
            report.parent / LEDGER, handover)
        errors += ledger_errors
        warnings += ledger_warnings
    for line, cells, row in table_rows(prose):
        citations = [target for _, _, image, target in links(
            row, definitions) if not image and target]
        # An unknown owner alone cannot excuse uncited options or tradeoffs.
        unknown_row = all(GAP.search(cell) or cell.strip(" *_`") in ("", "—", "-", "N/A")
                          for cell in cells[1:])
        if not citations and not re.search(r"https?://[^\s<>]+", row) and not unknown_row:
            errors.append(
                f"Line {line}: table row needs a point-of-use source link (or a ledger gap link); an unknown owner does not exempt other claims.")
    if "Roadmap" in sections:
        start, end = sections["Roadmap"]
        labels = [cells[0].strip(" *_`:")
                  for _, cells, _ in table_rows(prose[start:end])]
        if labels != ROADMAP_STAGES:
            errors.append(
                "Roadmap table must have exactly these rows in order: " + " → ".join(ROADMAP_STAGES))
    prep_path = report.parent / MERMAIDS
    prep, prep_fences = "", []
    try:
        prep = prep_path.read_text(
            encoding="utf-8") if any(title in sections for title in MAPS) else ""
        _, prep_fences, prep_unclosed = markdown(prep)
        if prep_unclosed:
            errors.append("mermaids.md has an unclosed code fence.")
        if any(diagram_kind(f[3]) == "sequenceDiagram" for f in prep_fences):
            errors.append(
                "mermaids.md must contain map sources only; keep sequences in the report.")
    except (OSError, UnicodeError):
        prep, prep_fences = "", []
        if any(title in sections for title in MAPS):
            errors.append(
                "Missing or unreadable UTF-8 map preparation artifact: mermaids.md.")
    for title, filename in MAPS.items():
        if title not in sections:
            continue
        start, end = sections[title]
        section = prose[start:end]
        maps = [(a, b) for a, b, image, target in all_links
                if start <= a < end and image and target and unquote(urlsplit(target).path).endswith(filename)]
        sequences = [(a, b) for a, b, language, source in fences
                     if start <= a < end and language == "mermaid" and diagram_kind(source) == "sequenceDiagram"]
        raw_maps = [(a, b) for a, b, language, source in fences
                    if start <= a < end and language == "mermaid" and diagram_kind(source) in ("flowchart", "graph")]
        fallback = bool(raw_maps and not maps and re.search(
            r"layout[^.\n]*unchecked", section, re.I))
        if raw_maps and not fallback:
            errors.append(
                f"{title}: remove duplicated map source from report; keep it in mermaids.md.")
        if fallback:
            maps = raw_maps
            warnings.append(
                f"{title}: unchecked-layout Mermaid map fallback; inspect when rendering becomes available.")
        if not maps and not has_gap(section, r"\b(map|architecture|structure)\b"):
            errors.append(
                f"{title}: embed {filename} before its sequences, or record an explicit map evidence gap.")
        if len(maps) > 1:
            errors.append(f"{title}: expected one system map.")
        if not sequences and not has_gap(section, r"\b(flow|sequence|interaction)s?\b"):
            errors.append(
                f"{title}: add a native Mermaid sequence or an explicit flow evidence gap.")
        if maps and sequences:
            if maps[0][1] > sequences[0][0]:
                errors.append(f"{title}: the map must precede every sequence.")
            if not prose[start:maps[0][0]].strip():
                errors.append(
                    f"{title}: add the opening architecture summary before the map.")
            tail = re.sub(r"^\s*#+.*$", "",
                          prose[sequences[-1][1]:end], flags=re.M).strip()
            if not tail:
                errors.append(
                    f"{title}: add shared commentary after the last sequence.")
            diagrams = sorted(maps + sequences)
            for (_, previous_end), (next_start, _) in zip(diagrams, diagrams[1:]):
                between = prose[previous_end:next_start].strip()
                # Short titles may be headings or bold text. Plain text could
                # also be a title, so flag ambiguity rather than reject it.
                # The one wrapper allowed: a sequence's width container.
                remainder = re.sub(r'^\s*(?:#{4,6}\s+.*|\*\*[^\n]+\*\*|<div style="width:[\d.]+%; margin:0 auto;">|</div>)\s*$',
                                   "", between, flags=re.M).strip()
                if remainder:
                    warnings.append(
                        f"{title}: text between diagrams needs review; keep only flow titles there and put shared commentary after the last sequence.")
                    break
        if maps:
            # Map headings delimit preparation entries; each must name its SVG.
            entries = re.split(r"^#{1,6}\s+", prep, flags=re.M)
            if not any(filename in entry and any(diagram_kind(f[3]) in ("flowchart", "graph")
                       for f in markdown(entry)[1]) for entry in entries):
                errors.append(
                    f"mermaids.md: retain the {filename} map source under its stage heading.")
    architecture_ranges = [sections[title]
                           for title in MAPS if title in sections]
    if any(language == "mermaid" and diagram_kind(source) in ("flowchart", "graph")
           and not any(start <= a < end for start, end in architecture_ranges)
           for a, _, language, source in fences):
        errors.append(
            "Keep map source in mermaids.md, not elsewhere in the report.")
    result["ok"] = not errors
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True,
                        help="Absolute path of the Markdown report.")
    parser.add_argument("--handover", action="store_true",
                        help="also require what handover needs: no ready actions, a recorded reflection")
    args = parser.parse_args(argv)
    result = check_report(args.report, args.handover)
    print(json.dumps(result))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
