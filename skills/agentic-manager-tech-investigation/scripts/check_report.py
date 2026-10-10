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
from urllib.parse import unquote, urlsplit

import os

from common import (FINDING_FIELDS, FINDING_HEADING, LEDGER, LEDGER_SECTIONS, QUEUE_SUBSECTIONS,
                    DEFINITION, expected_files, headings, links, markdown, read_skip,
                    report_headings, short_formats)

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


LINK = re.compile(r"\]\(https?://[^)\s]+\)|\]\[[^\]]*\]|https?://\S+")
# A reference-style link, `[text][key]`, takes its URL from a definition in the Links section.
REFERENCE = re.compile(r"\[([^\]]+)\]\[([^\]]*)\]")
INLINE_LINK = re.compile(r"\[[^\]]*\]\([^)]*\)")


def strip_links(text):
    """`text` without its links, inline or by reference, and without the
    definition lines the references use."""
    text = re.sub(r"^ {0,3}\[[^\]]+\]:\s*\S+.*$", " ", text, flags=re.M)
    return REFERENCE.sub(" ", INLINE_LINK.sub(" ", text))


def reference_problems(body):
    """(keys used but not defined, keys defined but never used) of the reference links in `body`."""
    defined = {key.casefold() for key, _ in DEFINITION.findall(body)}
    used = {(key or text).casefold()
            for text, key in REFERENCE.findall(re.sub(DEFINITION, " ", body))}
    return sorted(used - defined), sorted(defined - used)


RECORD = re.compile(r"\b[SQDGC]\d{2,}\b")
RECORD_DEFINITION = re.compile(
    r"^(?:\|\s*|[-*]\s+\*\*|#{3}\s+)([SQDGC]\d{2,})\b", re.M)


def unrecorded_ids(body):
    """The source, action, decision, gap and component IDs the ledger cites but
    never records in a table row, a bold label or a heading."""
    return sorted(set(RECORD.findall(body)) - set(RECORD_DEFINITION.findall(body)))


def source_finding_problems(body):
    """Source rows whose `Findings:` differ from the findings whose Evidence line names them."""
    cited = {}
    for block in re.split(r"(?m)^(?=### F\d+ )", body):
        head = re.match(r"### (F\d+) ", block)
        evidence = re.search(r"- \*\*Evidence:\*\*(.*)", block)
        if head and evidence:
            for source in set(re.findall(r"\bS(\d+)\b", evidence[1])):
                cited.setdefault(int(source), set()).add(head[1])
    start = body.find("## Revisions and source register")
    end = body.find("### File reading coverage")
    problems = []
    for line in body[start:end].splitlines() if start >= 0 and end > start else []:
        cells = [c.strip()
                 for c in re.split(r"(?<!\\)\|", line.strip().strip("|"))]
        if len(cells) < 5 or not re.fullmatch(r"S\d+", cells[0]):
            continue
        listed = re.search(r"Findings: ([^.]*)\.\s*$", cells[4])
        have = set(re.findall(r"F\d+", listed[1])) if listed else set()
        want = cited.get(int(cells[0][1:]), set())
        if have != want:
            problems.append(f"{cells[0]} lists {', '.join(sorted(have)) or 'none'}, "
                            f"its findings are {', '.join(sorted(want)) or 'none'}")
    return problems


def claim_words(entry):
    claim = re.search(r"\*\*Claim:?\*\*:?(.*?)(?=\n- \*\*|\Z)", entry, re.S)
    return len(re.findall(r"\w+", claim[1])) if claim else 0


def unlinked_backticks(prose):
    """The backticked spans of `prose` that sit outside a link, in order. Backticks
    mark a reference to code or a source, so each is a link to its pinned
    revision; anything else is written as plain words."""
    return re.findall(r"`([^`\n]+)`", strip_links(prose))


PLAIN_REFERENCE = re.compile(
    r"(?<![\w/\[-])[A-Z][A-Z0-9]{1,9}-\d{1,6}(?![\w\]-])|(?<![\w/&#\[])#\d{1,5}\b")


def unlinked_references(prose):
    """The ticket keys and pull request numbers of `prose` written outside a
    link, in order. Headings are left alone: a link there would change
    their anchor."""
    found = []
    for line in strip_links(prose).splitlines():
        if not line.lstrip().startswith("#"):
            found += PLAIN_REFERENCE.findall(line)
    return found


def reference_error(where, found):
    shown = ", ".join(
        found[:6]) + (f" and {len(found) - 6} more" if len(found) > 6 else "")
    return (f"{where}: tickets and pull requests written without a link: {shown}. "
            "Link each to its source")


def backtick_error(where, spans):
    shown = ", ".join(
        f"`{s}`" for s in spans[:6]) + (f" and {len(spans) - 6} more" if len(spans) > 6 else "")
    return (f"{where}: references in backticks without a link: {shown}. Link each to its pinned revision, "
            "or write it as plain words")


def unlinked_rows(body, start, end, cell, exempt=None):
    """The IDs of the table rows between the headings `start` and `end` whose
    `cell` (0 is the first column) holds no link, except rows `exempt` accepts."""
    section = re.search(
        rf"^{re.escape(start)}\s*$(.*?)(?=^{re.escape(end)}|\Z)", body, re.M | re.S)
    found = []
    for line in (section[1] if section else "").splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if re.fullmatch(r"S\d+", cells[0]) and len(cells) > cell:
            if not LINK.search(cells[cell]) and not (exempt and exempt(cells)):
                found.append(cells[0])
    return found


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
        if claim_words(entry) > 150:
            warnings.append(f"ledgers.md: {match[1]}'s claim is {claim_words(entry)} words; "
                            "split it into findings of one claim each")
    cited = set(re.findall(r"\bF\d+\b", re.sub(FINDING_HEADING, "", body)))
    undefined = sorted(cited - set(findings), key=lambda f: int(f[1:]))
    if undefined:
        errors.append(
            "ledgers.md: findings cited but never written: " + ", ".join(undefined))
    missing_keys, unused_keys = reference_problems(body)
    if missing_keys:
        errors.append(
            "ledgers.md: reference links without a definition in ## Links: " + ", ".join(missing_keys))
    if unused_keys:
        warnings.append(
            "ledgers.md: definitions in ## Links never used: " + ", ".join(unused_keys))
    if handover:
        unrecorded = unrecorded_ids(body)
        if unrecorded:
            errors.append(
                "ledgers.md: IDs cited but never recorded: " + ", ".join(unrecorded))
        ready = re.search(
            r"^### Ready / in progress\s*$(.*?)(?=^#{2,3}\s)", body, re.M | re.S)
        if ready and re.search(r"^\|\s*Q\d+", ready[1], re.M):
            errors.append(
                "ledgers.md: actions are still ready or in progress; finish, block or reject them before handover")
        # The trail from a claim to its source ends in a link: a search record has none to give.
        def search(cells): return "search record" in cells[1].lower()  # noqa: E731
        register = unlinked_rows(
            body, "## Revisions and source register", "### File reading coverage", 2, search)
        if register:
            errors.append("ledgers.md: source register rows without a link to their exact reference: "
                          + ", ".join(register) + ". Link each source at its pinned revision, or mark a search a `search record`")
        coverage = unlinked_rows(
            body, "### File reading coverage", "## ", 1)
        if coverage:
            errors.append("ledgers.md: File reading coverage rows without a link to the material read: "
                          + ", ".join(sorted(set(coverage))))
        mismatched = source_finding_problems(body)
        if mismatched:
            errors.append("ledgers.md: a source's Findings differ from the findings whose Evidence names it ("
                          + "; ".join(mismatched) + "). Run ledger.py sync-sources")
        spans = unlinked_backticks(body)
        if spans:
            errors.append(backtick_error("ledgers.md", spans))
        found = unlinked_references(body)
        if found:
            errors.append(reference_error("ledgers.md", found))
        reflection = re.search(
            r"^## Reflection\s*\n(.*?)(?=^## |\Z)", body, re.M | re.S)
        if not reflection or reflection[1].strip() in ("", "None yet."):
            errors.append(
                "ledgers.md: write the ## Reflection section before handover")
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
    architect = next((i for i, (level, title) in enumerate(actual)
                      if level == 2 and title == "Architect summary"), None)
    for i in range(architect + 1 if architect is not None else len(found), len(found)):
        title = found[i][2]
        if title not in ("Current status", "Next steps and evolution"):
            break
        start = found[i].end()
        end = found[i + 1].start() if i + 1 < len(found) else len(text)
        section = prose[start:end]
        sequences = [(a, b) for a, b, language, source in fences
                     if start <= a < end and language == "mermaid" and diagram_kind(source) == "sequenceDiagram"]
        if len(sequences) > 1:
            errors.append(
                f"Architect summary, {title}: expected one sequence, not {len(sequences)}.")
        if not sequences and not has_gap(section, r"\b(flow|sequence|interaction)s?\b"):
            errors.append(
                f"Architect summary, {title}: add a native Mermaid sequence or an explicit flow evidence gap.")
        if sequences:
            before = re.sub(r"^\s*#+.*$", "",
                            prose[start:sequences[0][0]], flags=re.M).strip()
            if not before:
                errors.append(
                    f"Architect summary, {title}: add the text before the sequence.")
    if handover:
        extra = sorted(name for name in os.listdir(report.parent)
                       if not name.startswith(".") and name not in expected_files(
                           report.name, short_formats(report.parent)))
        if extra:
            errors.append("Unexpected files in the investigation folder: " + ", ".join(extra)
                          + ". It holds only the skill's files; keep working files in your own scratch folder.")
        spans = unlinked_backticks(prose)
        if spans:
            errors.append(backtick_error(report.name, spans))
        found = unlinked_references(prose)
        if found:
            errors.append(reference_error(report.name, found))
    result["ok"] = not errors
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True,
                        help="Absolute path of the Markdown report.")
    parser.add_argument("--handover", action="store_true",
                        help="also require what handover needs: no ready actions, a recorded reflection, only the skill's files")
    args = parser.parse_args(argv)
    result = check_report(args.report, args.handover)
    print(json.dumps(result))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
