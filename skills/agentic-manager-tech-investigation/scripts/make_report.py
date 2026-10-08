"""Writes the investigation's <Topic>_Report.md from <investigation>/content.json,
then checks it with check_report.py.

    python3 make_report.py --investigation <Topic>_<YY-MM-DD>

The report has one fixed template; this script owns it: the title and evidence
snapshot line, every ## and ### heading, table headers and the roadmap's rows,
the fixed opening sentences, each architecture section's layout (summary, map,
titled sequences, shared commentary), the References labels and the ledger
links. content.json holds only what needs judgment:

{
  "title": "Acme search",
  "skip": [],
  "evidence_snapshot": "2026-10-05",
  "problem": ["Paragraph, about 100 words in all."],
  "roadmap": {"current": {"outcome": "...", "commitment": "...", "dependencies": "..."},
              "next": {...}, "broader": {...}},
  "deep_dive": ["Paragraphs, about 200 words in all."],
  "key_decisions": [{"item": "...", "why": "...", "role": "Not established"}],
  "architecture": {
    "current": {"summary": ["About 300 words."],
                "map_gap": "Only when no map can be evidenced.",
                "sequences": [{"title": "Search API — query",
                               "lines": ["actor U as Client / operator", "participant A as Search API",
                                         "U->>A: Query", "A-->>U: Results"],
                               "constrain_to": "Optional: the title of a correctly displayed peer"}],
                "flow_gap": "Only when no flow can be evidenced.",
                "commentary": ["**Search API:** steps 1–2 ..."]},
    "next": {...}, "target": {...}
  },
  "technical_decisions": [{"decision": "...", "position": "...", "evidence": "...",
                           "status": "Open", "owner": "Not established"}],
  "discrepancies": "How material discrepancies were resolved by evidence level.",
  "remaining_gaps": "The precise remaining gaps, by ledger ID.",
  "references": {"implementation": ["[Service README](https://...)"],
                 "delivery": [{"text": "[PROJ-1](https://...)", "historical": true}],
                 "vision": []}
}

Text is Markdown. Link to the ledger as [text](ledger:F03): the script
resolves the ID to its heading's anchor, or to the section whose table or bold
label defines it. A sequence's lines are its body: the script adds
`sequenceDiagram` and `autonumber`, matches its participants and calls to the
stage's map (maps.json), renders every sequence in one run to check its syntax
and measure its width, and wraps a sequence with "constrain_to" in a container
sized by the measured ratio to that peer.

Prints one line of JSON: the report's path, whether the folder is temporary,
whether the report passes the check ("ok"), its errors and warnings, and each
sequence's rendered width. Exits 1 if content.json is invalid (writing
nothing) or the written report fails the check.
"""
import argparse
from datetime import date
import json
import os
import re

from common import (CONTENT, COMMENTARY_HEADING, FOLDER_NAME, LEDGER, MAPS_SPEC,
                    MERMAIDS, REPORT_SUFFIX, ROADMAP_ROWS, SKIPS, STAGES, headings, markdown, report_stages,
                    investigation_dir, load_json, table, topic_of, write_output_file)
import check_report
import output_diagram

STAGE_KEYS = [key for key, _, _ in STAGES]
MONTHS = ["January", "February", "March", "April", "May", "June", "July",
          "August", "September", "October", "November", "December"]
NOT_ESTABLISHED = "not established"
# Approximate prose lengths, in words: warn outside half to one and a half.
TARGETS = {"problem": 100, "deep_dive": 200, "summary": 300, "commentary": 100}
# Sequences whose widths differ by more than this display text at
# materially different sizes when fitted to one page width.
WIDTH_SPREAD = 1.15

PARTICIPANT = re.compile(
    r"^\s*(?:create\s+)?(participant|actor)\s+(\S+)(?:\s+as\s+(.+?))?\s*$")
MESSAGE = re.compile(
    r"^\s*([^\s:+\-<>]+)\s*(-->>|->>|-->|->|--x|-x|--\)|-\))\s*[+-]?\s*([^\s:+\-<>]+)\s*:(.*)$")
QUALIFIER = re.compile(r"\s*\([^()]*\)\s*$")
LEDGER_LINK = re.compile(r"\]\(ledger:([A-Za-z]+\d+)?\)")
STEPS = re.compile(r"\bsteps?\s+(\d+)(?:\s*[–-]\s*(\d+))?", re.I)
FLOW_LABEL = re.compile(r"\*\*([^*\n]+?):\*\*")


def snapshot(content, value):
    try:
        day = date.fromisoformat(str(value))
    except ValueError:
        content.errors.append("evidence_snapshot: must be a date, YYYY-MM-DD")
        return str(value)
    return f"{day.day} {MONTHS[day.month - 1]} {day.year}"


def words(text):
    text = re.sub(r"\]\([^)]*\)", "]", text)
    return len(re.findall(r"\w[\w'’.-]*", text))


class Content:
    """content.json, checked as it is read: problems collect in `errors`."""

    def __init__(self, data, ledger):
        self.data = data if isinstance(data, dict) else {}
        self.ledger = ledger
        self.errors, self.warnings = [], []
        if not isinstance(data, dict):
            self.errors.append("content.json must be a JSON object")

    def text(self, value, where, inline=False):
        if not isinstance(value, str) or not value.strip():
            self.errors.append(f"{where}: needs text")
            return ""
        if re.search(r"^ {0,3}#{1,3}\s", value, re.M):
            self.errors.append(
                f"{where}: no # to ### headings; the template sets them (#### is fine)")
        if re.search(r"<div\b|^ {0,3}(```|~~~)", value, re.M | re.I):
            self.errors.append(
                f"{where}: no code fences or <div> wrappers; sequences go in \"sequences\"")
        if inline and "\n" in value.strip():
            self.errors.append(
                f"{where}: one line, for a table cell or list item")
        return self.links(value.strip(), where)

    def paragraphs(self, key, where, value=None):
        value = self.data.get(key) if value is None else value
        if not isinstance(value, list) or not value:
            self.errors.append(f"{where}: needs a list of paragraphs")
            return []
        return [self.text(p, f"{where} paragraph {i}") for i, p in enumerate(value, 1)]

    def links(self, text, where):
        def resolve(match):
            ident = match[1]
            if not ident:
                return f"]({LEDGER})"
            anchor = self.ledger.anchor(ident)
            if anchor is None:
                self.errors.append(
                    f"{where}: ledger:{ident} matches no heading, table row or bold label in {LEDGER}")
                return match[0]
            return f"]({LEDGER}#{anchor})"
        return LEDGER_LINK.sub(resolve, text)

    def length(self, texts, target, where, upper=True):
        count = sum(words(t) for t in texts)
        if count < target / 2 or (upper and count > target * 1.5):
            self.warnings.append(
                f"{where}: {count} words; the target is about {target}")


class Ledger:
    """The ledger's anchors, to resolve ledger:<ID> links."""

    def __init__(self, path):
        try:
            with open(path, encoding="utf-8") as f:
                self.text = f.read()
        except OSError:
            self.text = ""
        self.headings = headings(self.text)
        self.prose = markdown(self.text)[0]

    def anchor(self, ident):
        for _, title, anchor in self.headings:
            if re.match(rf"{re.escape(ident)}\b", title):
                return anchor
        # Defined in a table's first cell or as a bold label: its section.
        definition = re.search(rf"^\s*(?:\|\s*{re.escape(ident)}\s*\||[-*]\s+\*\*{re.escape(ident)}\b)",
                               self.prose, re.M)
        if not definition:
            return None
        before = headings(self.text[:definition.start()])
        return before[-1][2] if before else None


class Sequence:
    def __init__(self, title, lines, constrain_to):
        self.title, self.lines, self.constrain_to = title, lines, constrain_to
        self.source = "sequenceDiagram\n    autonumber\n" + \
            "".join(f"    {line}\n" for line in lines)
        self.steps = sum(1 for line in lines if MESSAGE.match(line))
        self.width = None

    @property
    def component(self):
        return self.title.split(" — ", 1)[0].strip()


def sequences(content, stage, where):
    """[Sequence] of a stage, checked for the template's rules."""
    result = []
    items = stage.get("sequences", [])
    if not isinstance(items, list):
        content.errors.append(f"{where}.sequences: needs a list")
        return result
    for index, item in enumerate(items, 1):
        at = f"{where} sequence {index}"
        if not isinstance(item, dict):
            content.errors.append(f"{at}: must be an object")
            continue
        title = item.get("title")
        if not isinstance(title, str) or " — " not in title or "\n" in title:
            content.errors.append(
                f"{at}: title must read \"<Component> — <flow>\"")
            title = str(title)
        lines = item.get("lines")
        if not isinstance(lines, list) or not all(isinstance(line, str) for line in lines) or not lines:
            content.errors.append(
                f"{title}: lines must be a list of Mermaid lines")
            continue
        lines = [line.rstrip() for item in lines for line in item.splitlines()
                 if line.strip() and line.strip() not in ("sequenceDiagram", "autonumber")]
        for line in lines:
            if ";" in re.sub(r"#\w+;", "", line):
                content.errors.append(
                    f"{title}: raw semicolon in {line.strip()!r}; Mermaid reads it as a new statement")
            message = MESSAGE.match(line)
            if message and re.match(r"\s*\d+[.)]\s", message[4]):
                content.errors.append(
                    f"{title}: {line.strip()!r} numbers its step; autonumber does")
        result.append(Sequence(title, lines, item.get("constrain_to")))
    return result


def check_against_map(content, sequence, spec, key):
    """Errors where a sequence leaves its stage's map: every participant is a
    map node (a role qualifier in brackets allowed), every call between two
    of them has a connection the stage shows."""
    names = {node["name"]: node["id"] for node in spec.get("nodes", [])}
    shown = spec["stages"][key].get("connections", {})
    pairs = set()
    for connection in spec.get("connections", []):
        if (connection.get("id") or f"{connection['from']}->{connection['to']}") in shown:
            pairs |= {(connection["from"], connection["to"]),
                      (connection["to"], connection["from"])}
    aliases = {}
    for line in sequence.lines:
        participant = PARTICIPANT.match(line)
        if participant:
            name = QUALIFIER.sub("", participant[3] or participant[2])
            if name not in names:
                content.errors.append(
                    f"{sequence.title}: participant {name!r} is not a node of the {key} map")
            aliases[participant[2]] = names.get(name)
    for line in sequence.lines:
        message = MESSAGE.match(line)
        if not message:
            continue
        for end in (message[1], message[3]):
            if end not in aliases:
                name = QUALIFIER.sub("", end)
                if name not in names:
                    content.errors.append(
                        f"{sequence.title}: {end!r} is not a node of the {key} map")
                aliases[end] = names.get(name)
        first, second = aliases.get(message[1]), aliases.get(message[3])
        if message[1] == message[3]:
            continue
        if first and second and (first, second) not in pairs:
            content.errors.append(f"{sequence.title}: {line.strip()!r} has no connection between "
                                  f"{first} and {second} on the {key} map")


def check_steps(content, flows, commentary, where):
    """Errors where the commentary names a step its flow doesn't have."""
    for paragraph in commentary:
        marks = list(FLOW_LABEL.finditer(paragraph))
        spans = [(None, 0, marks[0].start() if marks else len(paragraph))]
        spans += [(m[1].strip(), m.end(), marks[i + 1].start() if i + 1 < len(marks) else len(paragraph))
                  for i, m in enumerate(marks)]
        for label, start, end in spans:
            steps = list(STEPS.finditer(paragraph[start:end]))
            if not steps:
                continue
            if label is None:
                targets = flows if len(flows) == 1 else []
            else:
                targets = [s for s in flows if s.component == label]
            if not targets:
                content.errors.append(
                    f"{where}: commentary step references need a matching flow; "
                    "use **<Component>:** with a sequence component")
                continue
            most = max(s.steps for s in targets)
            for match in steps:
                first = int(match[1])
                last = int(match[2] or match[1])
                if first < 1 or first > last:
                    content.errors.append(f"{where}: the commentary's step range {first}–{last} "
                                          "must start at 1 or later and run forwards")
                elif last > most:
                    content.errors.append(f"{where}: the commentary names step {last}, but "
                                          f"{label or targets[0].title} has {most}")


def raw_map(folder, title):
    """The stage's map source in mermaids.md, for the fallback, or None."""
    try:
        with open(os.path.join(folder, MERMAIDS), encoding="utf-8") as f:
            text = f.read()
    except OSError:
        return None
    entry = re.search(
        rf"^## {re.escape(title)} — System map\n(.*?)(?=^## |\Z)", text, re.M | re.S)
    block = entry and re.search(r"```mermaid\n(.*?)```", entry[1], re.S)
    return block[1] if block else None


def parse_stages(content, spec, shown):
    """{stage: (its content, [Sequence])} of the `shown` stages, each
    sequence checked against the stage's map and the template's rules."""
    stages = {}
    architecture = content.data.get("architecture")
    architecture = architecture if isinstance(architecture, dict) else {}
    keys = [key for key, _, _ in shown]
    for key in architecture:
        if key not in keys:
            content.errors.append(f"architecture.{key}: the report doesn't show this stage"
                                  + (", as skip leaves it out" if key in STAGE_KEYS else ""))
    for key, _, _ in shown:
        stage = architecture.get(key)
        if not isinstance(stage, dict):
            content.errors.append(f"architecture.{key}: missing")
            continue
        flows = sequences(content, stage, f"architecture.{key}")
        if spec is not None:
            if key in (spec.get("stages") or {}):
                for sequence in flows:
                    check_against_map(content, sequence, spec, key)
            elif not stage.get("map_gap"):
                content.errors.append(
                    f"architecture.{key}: maps.json has no {key} stage for the shown map; "
                    "add the stage or record a map_gap")
            elif flows:
                content.warnings.append(
                    f"maps.json has no {key} stage: sequences aren't checked against the map")
        stages[key] = (stage, flows)
    return stages


def stage_section(content, folder, key, title, filename, stage, flows, rendered):
    """The lines of one architecture section: summary, map, titled
    sequences, gaps and notes, then the shared commentary."""
    where = f"architecture.{key}"
    summary = content.paragraphs(
        "summary", f"{where}.summary", stage.get("summary"))
    content.length(summary, TARGETS["summary"], f"{where}.summary")
    commentary = content.paragraphs(
        "commentary", f"{where}.commentary", stage.get("commentary"))
    content.length(commentary, TARGETS["commentary"],
                   f"{where}.commentary", upper=len(flows) < 2)
    check_steps(content, flows, commentary, where)
    lines, notes = summary[:], []
    if stage.get("map_gap"):
        lines.append("**Map evidence gap:** " +
                     content.text(stage["map_gap"], f"{where}.map_gap"))
    elif os.path.isfile(os.path.join(folder, filename)):
        lines.append(f"![{title}]({filename})")
    else:
        source = raw_map(folder, title)
        if source is None:
            content.errors.append(
                f"{where}: {filename} is missing: run build_maps.py, or set map_gap")
        else:
            lines.append(f"```mermaid\n{source.rstrip()}\n```")
            notes.append(
                "Map layout is unchecked: Node.js wasn't available to render it.")
    for sequence in flows:
        lines.append(f"#### {sequence.title}")
        fence = f"```mermaid\n{sequence.source}```"
        if sequence.constrain_to:
            peer = next((s for s in flows if s.title ==
                        sequence.constrain_to), None)
            if peer is None or peer is sequence:
                content.errors.append(
                    f"{sequence.title}: constrain_to names no other sequence of this section")
            elif sequence.width and peer.width:
                percent = round(sequence.width / peer.width * 100, 2)
                fence = f'<div style="width:{percent:g}%; margin:0 auto;">\n\n{fence}\n\n</div>'
            else:
                content.warnings.append(
                    f"{sequence.title}: constrain_to needs both widths, so it isn't applied")
        lines.append(fence)
    if stage.get("flow_gap"):
        lines.append("**Flow evidence gap:** " +
                     content.text(stage["flow_gap"], f"{where}.flow_gap"))
    elif not flows:
        content.errors.append(f"{where}: needs a sequence, or a flow_gap")
    if flows and not rendered:
        notes.append(
            "Sequence syntax is unchecked: Node.js wasn't available to render it.")
    return lines + notes + [f"#### {COMMENTARY_HEADING}"] + commentary


def measure(content, flows):
    """Renders every sequence in one run to check its syntax and set its
    width. Returns whether they were rendered."""
    if not flows:
        return True
    try:
        svgs = output_diagram.render_many([s.source for s in flows])
    except output_diagram.NodeMissing:
        content.warnings.append(
            "Node.js isn't available: sequence syntax and widths are unchecked")
        return False
    except SystemExit as error:
        number, _, message = str(error).partition(": ")
        index = int(number.split()[-1]) - \
            1 if number.startswith("diagram ") else 0
        content.errors.append(
            f"{flows[index].title}: doesn't render: {message or error}")
        return False
    for sequence, svg in zip(flows, svgs):
        sequence.width, _ = output_diagram.svg_size(svg)
    widths = [s.width for s in flows if s.width]
    if widths and max(widths) / min(widths) > WIDTH_SPREAD:
        content.warnings.append(
            "sequence widths differ by more than 15%: check the report in its viewer, and only if one "
            "displays enlarged, set its constrain_to to a correctly displayed peer")
    return True


def references(content):
    refs = content.data.get("references")
    if not isinstance(refs, dict):
        content.errors.append(
            "references: needs implementation, delivery and vision lists")
        refs = {}
    lines = []
    for key, label in (("implementation", "Implementation and configuration"), ("delivery", "Delivery"),
                       ("vision", "Vision, rationale and reported operational gaps")):
        items = refs.get(key, [])
        if not isinstance(items, list):
            content.errors.append(f"references.{key}: needs a list")
            items = []
        lines.append(f"**{label}**")
        if not items:
            lines.append("None in the inspected sources.")
            continue
        entries = []
        for index, item in enumerate(items, 1):
            text, historical = (item.get("text"), item.get(
                "historical")) if isinstance(item, dict) else (item, False)
            text = content.text(text, f"references.{key} {index}", inline=True)
            entries.append(
                f"- {text}" + (" (historical)" if historical else ""))
        lines.append("\n".join(entries))
    lines.append(f"The [research ledger]({LEDGER}) holds the full validation trail: revisions, searches, "
                 "the component inventory, reconciled findings, decisions and limitations.")
    return lines


def key_decisions(content):
    items = content.data.get("key_decisions")
    if not isinstance(items, list):
        content.errors.append(
            "key_decisions: needs a list, empty when no item is evidenced")
        return []
    if not items:
        return ["No decision, blocker or risk in the inspected evidence warrants technical-leadership attention."]
    rows = []
    for index, item in enumerate(items, 1):
        item = item if isinstance(item, dict) else {}
        rows.append([content.text(item.get(field), f"key_decisions {index}.{field}", inline=True)
                     for field in ("item", "why", "role")])
    unknown = [row[2].strip(" *_").casefold() ==
               NOT_ESTABLISHED for row in rows]
    ownership = ("Decision ownership is not established in the inspected sources." if all(unknown)
                 else "The inspected sources establish the deciding role for each item." if not any(unknown)
                 else "The inspected sources establish the deciding role for some items only; "
                      "the others read Not established.")
    return ["These items describe implications of the linked evidence. " + ownership,
            table(["Decision or risk", "Why it matters", "Deciding role"], rows)]


def skipped(content):
    """The dimensions content.json skips, checked."""
    skip = content.data.get("skip", [])
    if not isinstance(skip, list) or not all(isinstance(d, str) for d in skip):
        content.errors.append(
            "skip: must list the dimensions left out, architecture or evolution")
        return []
    for dimension in skip:
        if dimension not in SKIPS:
            content.errors.append(
                f"skip: only {' or '.join(SKIPS)} can be skipped, not {dimension!r}")
    return [d for d in SKIPS if d in skip]


def build(content, folder, spec):
    """(report text, [Sequence])."""
    data = content.data
    skip = skipped(content)
    roadmap = data.get("roadmap")
    roadmap = roadmap if isinstance(roadmap, dict) else {}
    if "evolution" in skip and roadmap:
        content.errors.append(
            "roadmap: evolution is skipped, so the report has no roadmap")
    rows = []
    for key, label in ROADMAP_ROWS if "evolution" not in skip else ():
        row = roadmap.get(key)
        row = row if isinstance(row, dict) else {}
        rows.append([label] + [content.text(row.get(field), f"roadmap.{key}.{field}", inline=True)
                               for field in ("outcome", "commitment", "dependencies")])
    problem = content.paragraphs("problem", "problem")
    content.length(problem, TARGETS["problem"], "problem")
    deep_dive = content.paragraphs("deep_dive", "deep_dive")
    content.length(deep_dive, TARGETS["deep_dive"], "deep_dive")
    architect = "architecture" not in skip
    for key in ("technical_decisions", "discrepancies", "remaining_gaps", "references"):
        if not architect and key in data:
            content.errors.append(
                f"{key}: architecture is skipped, so the report has no Architect summary")
    decisions = data.get("technical_decisions") if architect else []
    if architect and (not isinstance(decisions, list) or not decisions):
        content.errors.append("technical_decisions: needs a list of decisions")
        decisions = []
    decision_rows = [[content.text((d if isinstance(d, dict) else {}).get(field),
                                   f"technical_decisions {i}.{field}", inline=True)
                      for field in ("decision", "position", "evidence", "status", "owner")]
                     for i, d in enumerate(decisions, 1)]
    shown = report_stages(skip)
    stages = parse_stages(content, spec, shown)
    flows = [s for _, stage_flows in stages.values() for s in stage_flows]
    # Rendering takes a while: only when the content is otherwise valid.
    rendered = measure(content, flows) if not content.errors else False
    parts = [f"# {content.text(data.get('title'), 'title', inline=True)}",
             f"Evidence snapshot: {snapshot(content, data.get('evidence_snapshot'))}. Code links pin inspected "
             "commits; ticket, PR and document links may display later changes. Evidence revisions and "
             f"access limits are recorded in the [Research ledger]({LEDGER}).",
             "## Executive / product summary",
             "### Problem and intended outcome", *problem]
    if "evolution" not in skip:
        parts += ["### Roadmap",
                  table(["Stage", "Intended outcome", "Commitment and evidence", "Dependencies"], rows)]
    parts += ["### Current milestone - deep dive", *deep_dive,
              "### Key decisions and risks", *key_decisions(content)]
    if not architect:
        return "\n\n".join(parts) + "\n", []
    parts.append("## Architect summary")
    for key, title, filename in shown:
        parts.append(f"### {title}")
        if key in stages:
            parts += stage_section(content, folder, key,
                                   title, filename, *stages[key], rendered)
    parts += ["### Technical decisions and gaps",
              "The table records source-backed differences and unresolved decisions. "
              "It does not select an option or assign an owner.",
              table(["Decision", "Established position / unresolved choice", "Evidence", "Status", "Owner"],
                    decision_rows),
              content.text(data.get("discrepancies"), "discrepancies"),
              content.text(data.get("remaining_gaps"), "remaining_gaps"),
              "### References", *references(content)]
    return "\n\n".join(parts) + "\n", flows


def make_report(relative):
    """Writes the report and checks it; returns the JSON result, or exits
    with the problems if content.json is invalid."""
    folder, _, temporary = investigation_dir(relative)
    topic = topic_of(folder)
    content = Content(load_json(os.path.join(folder, CONTENT)),
                      Ledger(os.path.join(folder, LEDGER)))
    spec_path = os.path.join(folder, MAPS_SPEC)
    spec = load_json(spec_path) if os.path.isfile(spec_path) else None
    skip = content.data.get("skip", [])
    if spec is None and not (isinstance(skip, list) and "architecture" in skip):
        content.warnings.append(
            "maps.json is missing: sequences aren't checked against the maps")
    text, flows = build(content, folder, spec)
    if content.errors:
        raise SystemExit("content.json has problems, so nothing was written:\n  - "
                         + "\n  - ".join(content.errors))
    path, _ = write_output_file(
        FOLDER_NAME, f"{relative}/{topic}{REPORT_SUFFIX}", text.encode("utf-8"))
    check = check_report.check_report(path)
    return {"path": path, "temporary": temporary, "ok": check["ok"], "errors": check["errors"],
            "warnings": content.warnings + check["warnings"],
            "sequences": [{"title": s.title, "width": s.width} for s in flows]}


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Write the report from content.json, then check it.")
    parser.add_argument("--investigation", required=True,
                        help="the investigation's folder, <Topic>_<YY-MM-DD>, inside tech-investigations")
    result = make_report(parser.parse_args(argv).investigation)
    print(json.dumps(result))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
