"""Read-only checks of report structure and local artifacts, not evidence truth.

This deliberately recognizes the skill's ordinary Markdown output, not every
Markdown extension. Sequence syntax and visual layout still need their own review.
"""

import argparse
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET
from urllib.parse import unquote, urlsplit


HEADINGS = [
    (2, "Executive / product summary"),
    (3, "Problem and intended outcome"),
    (3, "Roadmap"),
    (3, "Current milestone - deep dive"),
    (3, "Key decisions and risks"),
    (2, "Architect summary"),
    (3, "Current architecture"),
    (3, "Next evolution"),
    (3, "Target architecture"),
    (3, "Technical decisions and gaps"),
    (3, "References"),
]
STAGES = ["Current milestone", "Next milestones", "Broader product direction"]
MAPS = dict(zip(
    ["Current architecture", "Next evolution", "Target architecture"],
    ["architecture-as-is.svg", "architecture-next.svg", "architecture-to-be.svg"],
))
INLINE_LINK = re.compile(r'(!?)\[([^\]\n]*)\]\(\s*(<[^>\n]+>|[^\s)]+)(?:\s+"[^"\n]*")?\s*\)')
REFERENCE_LINK = re.compile(r'(!?)\[([^\]\n]+)\]\[([^\]\n]*)\]')
# [text] alone, a link when a definition names it: not part of an inline,
# full reference or definition line.
SHORTCUT_LINK = re.compile(r'(?<![\]\\])(!?)\[([^\]\n]+)\](?![(\[:])')
DEFINITION = re.compile(r'^ {0,3}\[([^\]]+)\]:\s*(<[^>]+>|\S+)', re.M)
GAP = re.compile(r'\b(evidence gap|not established|unavailable|unverified|insufficient evidence|no evidence)\b', re.I)


def markdown(text):
    """Return prose with fenced code blanked (offsets preserved), plus fences."""
    lines = text.splitlines(keepends=True)
    prose, fences = [], []
    opened = None
    offset = 0
    for line in lines:
        match = re.match(r'^ {0,3}(`{3,}|~{3,})(.*)\s*$', line.rstrip('\n'))
        if opened is None and match:
            opened = (match[1], match[2].strip(), offset, [])
            prose.append('\n' if line.endswith('\n') else '')
            prose[-1] = ' ' * (len(line) - len(prose[-1])) + prose[-1]
        elif opened is not None:
            marker, language, start, body = opened
            prose.append(' ' * (len(line.rstrip('\n'))) + ('\n' if line.endswith('\n') else ''))
            if match and match[1][0] == marker[0] and len(match[1]) >= len(marker) and not match[2].strip():
                fences.append((start, offset + len(line), language, ''.join(body)))
                opened = None
            else:
                body.append(line)
        else:
            prose.append(line)
        offset += len(line)
    if opened is not None:
        _, language, start, body = opened
        fences.append((start, len(text), language, ''.join(body)))
    return ''.join(prose), fences, opened is not None


def links(prose, definitions):
    """Yield (start, end, image, target); support inline, full and collapsed
    reference links, and shortcut links whose text a definition names."""
    for match in INLINE_LINK.finditer(prose):
        yield match.start(), match.end(), bool(match[1]), match[3].strip('<>')
    for match in REFERENCE_LINK.finditer(prose):
        key = (match[3] or match[2]).casefold()
        yield match.start(), match.end(), bool(match[1]), definitions.get(key)
    for match in SHORTCUT_LINK.finditer(prose):
        if match[2].casefold() in definitions:
            yield match.start(), match.end(), bool(match[1]), definitions[match[2].casefold()]


def table_rows(prose):
    """Find data rows only in pipe tables with a Markdown separator line."""
    lines = prose.splitlines()
    active = False
    for index, line in enumerate(lines):
        cells = [part.strip() for part in re.split(r'(?<!\\)\|', line.strip().strip('|'))]
        separator = len(cells) > 1 and all(re.fullmatch(r':?-+:?', cell) for cell in cells)
        if separator and index and '|' in lines[index - 1]:
            active = True
            continue
        if active and '|' in line and line.strip():
            yield index + 1, cells, line
        else:
            active = False


def diagram_kind(source):
    # Init directives and Mermaid comments may precede the diagram declaration.
    match = re.search(r'^\s*(flowchart|graph|sequenceDiagram)\b', source, re.M)
    return match[1] if match else None


def has_gap(text, subject):
    return any(GAP.search(paragraph) and re.search(subject, paragraph, re.I)
               for paragraph in re.split(r'\n\s*\n', text))


def slug(heading):
    """The anchor a Markdown viewer gives a heading, GitHub style: lower case,
    punctuation dropped, each space a hyphen."""
    return re.sub(r'[^\w\- ]', '', heading.strip().lower()).replace(' ', '-')


def anchors(path):
    """Every heading anchor of a Markdown file, with -1, -2... for repeats."""
    seen, found = {}, set()
    body, _, _ = markdown(path.read_text(encoding='utf-8'))
    for match in re.finditer(r'^ {0,3}#{1,6}\s+(.+?)\s*#*\s*$', body, re.M):
        base = slug(match[1])
        count = seen.get(base, 0)
        seen[base] = count + 1
        found.add(base if count == 0 else f'{base}-{count}')
    return found


def check_report(report):
    """Return actionable JSON-compatible errors/warnings without modifying files."""
    report = Path(report)
    errors, warnings = [], []
    result = {"ok": False, "errors": errors, "warnings": warnings}
    if not report.is_absolute():
        errors.append('--report must be an absolute Markdown path.')
        return result
    try:
        text = report.read_text(encoding='utf-8')
    except (OSError, UnicodeError):
        errors.append('Cannot read report as UTF-8 Markdown.')
        return result
    prose, fences, unclosed = markdown(text)
    if unclosed:
        errors.append('Report has an unclosed code fence.')
    headings = list(re.finditer(r'^ {0,3}(#{2,3})\s+(.+?)\s*#*\s*$', prose, re.M))
    actual = [(len(match[1]), match[2]) for match in headings]
    if actual != HEADINGS:
        errors.append('H2/H3 headings must occur exactly in this order: ' +
                      ' → '.join('#' * level + ' ' + title for level, title in HEADINGS))
    sections = {match[2]: (match.end(), headings[i + 1].start() if i + 1 < len(headings) else len(text))
                for i, match in enumerate(headings)}
    definitions = {m[1].casefold(): m[2].strip('<>') for m in DEFINITION.finditer(prose)}
    all_links = list(links(prose, definitions))
    checked, headings_of = set(), {}
    for start, _, _, target in all_links:
        line = text.count('\n', 0, start) + 1
        if target is None:
            errors.append(f'Line {line}: unresolved Markdown link reference.')
            continue
        parsed = urlsplit(target)
        if parsed.scheme or parsed.netloc or not parsed.path:
            continue
        path = report.parent / unquote(parsed.path)
        if parsed.fragment and path.suffix.lower() == '.md' and path.is_file():
            if path not in headings_of:
                try:
                    headings_of[path] = anchors(path)
                except (OSError, UnicodeError):
                    headings_of[path] = set()
            if unquote(parsed.fragment).lower() not in headings_of[path]:
                errors.append(f'Line {line}: {parsed.path} has no heading for #{parsed.fragment}')
        if path in checked:
            continue
        checked.add(path)
        if not path.exists():
            errors.append(f'Line {line}: local link target is missing: {target}')
        elif path.suffix.lower() == '.svg':
            try:
                root = ET.parse(path).getroot()
                if root.tag not in ('svg', '{http://www.w3.org/2000/svg}svg'):
                    raise ValueError('not SVG')
            except (OSError, ET.ParseError, ValueError):
                errors.append(f'Line {line}: local SVG is not valid SVG XML: {target}')
    if not (report.parent / 'ledgers.md').is_file():
        errors.append('Missing research artifact: ledgers.md.')
    for line, cells, row in table_rows(prose):
        citations = [target for _, _, image, target in links(row, definitions) if not image and target]
        # An unknown owner alone cannot excuse uncited options or tradeoffs.
        unknown_row = all(GAP.search(cell) or cell.strip(' *_`') in ('', '—', '-', 'N/A')
                          for cell in cells[1:])
        if not citations and not re.search(r'https?://[^\s<>]+', row) and not unknown_row:
            errors.append(f'Line {line}: table row needs a point-of-use source link (or a ledger gap link); an unknown owner does not exempt other claims.')
    if 'Roadmap' in sections:
        start, end = sections['Roadmap']
        labels = [cells[0].strip(' *_`:') for _, cells, _ in table_rows(prose[start:end])]
        if labels != STAGES:
            errors.append('Roadmap table must have exactly these rows in order: ' + ' → '.join(STAGES))
    prep_path = report.parent / 'mermaids.md'
    try:
        prep = prep_path.read_text(encoding='utf-8')
        _, prep_fences, prep_unclosed = markdown(prep)
        if prep_unclosed:
            errors.append('mermaids.md has an unclosed code fence.')
        if any(diagram_kind(f[3]) == 'sequenceDiagram' for f in prep_fences):
            errors.append('mermaids.md must contain map sources only; keep sequences in the report.')
    except (OSError, UnicodeError):
        prep, prep_fences = '', []
        errors.append('Missing or unreadable UTF-8 map preparation artifact: mermaids.md.')
    for title, filename in MAPS.items():
        if title not in sections:
            continue
        start, end = sections[title]
        section = prose[start:end]
        maps = [(a, b) for a, b, image, target in all_links
                if start <= a < end and image and target and unquote(urlsplit(target).path).endswith(filename)]
        sequences = [(a, b) for a, b, language, source in fences
                     if start <= a < end and language == 'mermaid' and diagram_kind(source) == 'sequenceDiagram']
        raw_maps = [(a, b) for a, b, language, source in fences
                    if start <= a < end and language == 'mermaid' and diagram_kind(source) in ('flowchart', 'graph')]
        fallback = bool(raw_maps and not maps and re.search(r'layout[^.\n]*unchecked', section, re.I))
        if raw_maps and not fallback:
            errors.append(f'{title}: remove duplicated map source from report; keep it in mermaids.md.')
        if fallback:
            maps = raw_maps
            warnings.append(f'{title}: unchecked-layout Mermaid map fallback; inspect when rendering becomes available.')
        if not maps and not has_gap(section, r'\b(map|architecture|structure)\b'):
            errors.append(f'{title}: embed {filename} before its sequences, or record an explicit map evidence gap.')
        if len(maps) > 1:
            errors.append(f'{title}: expected one system map.')
        if not sequences and not has_gap(section, r'\b(flow|sequence|interaction)s?\b'):
            errors.append(f'{title}: add a native Mermaid sequence or an explicit flow evidence gap.')
        if maps and sequences:
            if maps[0][1] > sequences[0][0]:
                errors.append(f'{title}: the map must precede every sequence.')
            if not prose[start:maps[0][0]].strip():
                errors.append(f'{title}: add the opening architecture summary before the map.')
            tail = re.sub(r'^\s*#+.*$', '', prose[sequences[-1][1]:end], flags=re.M).strip()
            if not tail:
                errors.append(f'{title}: add shared commentary after the last sequence.')
            diagrams = sorted(maps + sequences)
            for (_, previous_end), (next_start, _) in zip(diagrams, diagrams[1:]):
                between = prose[previous_end:next_start].strip()
                # Short titles may be headings or bold text. Plain text could
                # also be a title, so flag ambiguity rather than reject it.
                remainder = re.sub(r'^\s*(?:#{4,6}\s+.*|\*\*[^\n]+\*\*)\s*$', '', between, flags=re.M).strip()
                if remainder:
                    warnings.append(f'{title}: text between diagrams needs review; keep only flow titles there and put shared commentary after the last sequence.')
                    break
        if maps:
            # Map headings delimit preparation entries; each must name its SVG.
            entries = re.split(r'^#{1,6}\s+', prep, flags=re.M)
            if not any(filename in entry and any(diagram_kind(f[3]) in ('flowchart', 'graph')
                       for f in markdown(entry)[1]) for entry in entries):
                errors.append(f'mermaids.md: retain the {filename} map source under its stage heading.')
    architecture_ranges = [sections[title] for title in MAPS if title in sections]
    if any(language == 'mermaid' and diagram_kind(source) in ('flowchart', 'graph')
           and not any(start <= a < end for start, end in architecture_ranges)
           for a, _, language, source in fences):
        errors.append('Keep map source in mermaids.md, not elsewhere in the report.')
    result['ok'] = not errors
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', required=True, help='Absolute path of the Markdown report.')
    args = parser.parse_args(argv)
    result = check_report(args.report)
    print(json.dumps(result, indent=2))
    return 0 if result['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
