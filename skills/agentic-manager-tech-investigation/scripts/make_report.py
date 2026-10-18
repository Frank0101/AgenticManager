"""Writes the investigation's <Topic>_Report.md from <investigation>/content.json,
then checks it with check_report.py.

    python3 make_report.py --investigation <Topic>_<YY-MM-DD>

The report has one fixed template; this script owns it: the title and evidence
snapshot line, every ## and ### heading, table headers, the fixed opening
sentences, each architect section's layout (text, then a titled flow: the
components it crosses, drawn by flow_components.py, and its sequence) and the
References labels and ledger links. content.json holds only what needs
judgment; its fields, with their length targets, are in SKILL.md (The report).

Text is Markdown. Link to the ledger as [text](ledger:F03): the script resolves
the ID to the anchor ledger.py gives its row or finding, or else to the heading
or section that defines it. Ticket keys and owner/repo#123 are linked from the
ledger's links: a ticket of a project the ledger doesn't link is written as
code, and a pull request that can't be linked is a problem in content.json. A
sequence's lines are its body: the script adds `sequenceDiagram` and
`autonumber`, and renders both diagrams with the Mermaid CLI to check their
syntax.

Prints one line of JSON: the report's path, whether the folder is temporary,
whether the report passes the check ("ok"), its errors and warnings, and the
titles of its sequences. Exits 1 if content.json is invalid (writing nothing)
or the written report fails the check.
"""
import argparse
from datetime import date
import json
import os
import re

from common import (CONTENT, FOLDER_NAME, HEADINGS, INVENTORY, LEDGER, RECORD_DEFINITION, REPORT_SUFFIX, SKIPS, anchor_tag, component_rows,
                    autolink, headings, investigation_dir, link_definitions, markdown, read_json, heading_anchor, table,
                    topic_of, unresolved_message, word_count, write_output_file)
import check_report
import flow_components
import output_diagram

# Approximate prose lengths, in words: room to articulate, not quotas. Warn above
# one and a half times, or far below, under a third, which is a stub.
TARGETS = {"problem": 150, "current_status": 200,
           "next_steps": 200, "summary": 300}

LEDGER_LINK = re.compile(r"\]\(ledger:([A-Za-z]+\d+)?\)")
# Each of the template's headings as written, by its id.
HEADING_LINE = {ident: "#" * level + " " +
                title for level, title, ident in HEADINGS}


def make_report(relative):
    """Writes the report and checks it; returns the JSON result, or exits
    with the problems if content.json is invalid."""
    folder, _, temporary = investigation_dir(relative)
    topic = topic_of(folder)
    content = Content(read_json(os.path.join(folder, CONTENT)),
                      Ledger(os.path.join(folder, LEDGER)))
    text, flows = build(content)
    if content.errors:
        raise SystemExit("content.json has problems, so nothing was written:\n  - "
                         + "\n  - ".join(content.errors))
    path, _ = write_output_file(
        FOLDER_NAME, f"{relative}/{topic}{REPORT_SUFFIX}", text.encode("utf-8"))
    check = check_report.check_report(path)
    return {"path": path, "temporary": temporary, "ok": check["ok"], "errors": check["errors"],
            "warnings": content.warnings + check["warnings"],
            "sequences": [s.title for s in flows]}


class Content:
    """content.json, checked as it is read: problems collect in `errors`."""

    def __init__(self, data, ledger):
        self.data = data if isinstance(data, dict) else {}
        self.ledger = ledger
        self.errors, self.warnings = [], []
        if not isinstance(data, dict):
            self.errors.append("content.json must be a JSON object")

    def text(self, value, where, inline=False, trace=False):
        if not isinstance(value, str) or not value.strip():
            self.errors.append(f"{where}: needs text")
            return ""
        # Every claim carries a link to a ledger record, which links the original sources.
        if trace and not any(match[1] for match in LEDGER_LINK.finditer(value)):
            self.errors.append(
                f"{where}: needs a ledger link such as [F03](ledger:F03), so the claim traces to the ledger and its sources")
        if re.search(r"^ {0,3}#{1,3}\s", value, re.M):
            self.errors.append(
                f"{where}: no # to ### headings; the template sets them (#### is fine)")
        if re.search(r"<div\b|^ {0,3}(```|~~~)", value, re.M | re.I):
            self.errors.append(
                f"{where}: no code fences or <div> wrappers; a sequence goes in \"sequence\"")
        if inline and "\n" in value.strip():
            self.errors.append(
                f"{where}: one line, for a table cell or list item")
        return self.links(self.linked(value.strip(), where), where)

    def linked(self, value, where):
        """`value` with its tickets and pull requests linked from the ledger's links."""
        value, unresolved = autolink(value, self.ledger.definitions)
        if unresolved:
            self.errors.append(
                f"{where}: couldn't link {unresolved_message(unresolved)}")
        return value

    def paragraphs(self, value, where):
        if not isinstance(value, list) or not value:
            self.errors.append(f"{where}: needs a list of paragraphs")
            return []
        return [self.text(p, f"{where} paragraph {i}", trace=True) for i, p in enumerate(value, 1)]

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

    def length(self, texts, target, where):
        count = sum(word_count(t) for t in texts)
        if count < target / 3 or count > target * 1.5:
            self.warnings.append(
                f"{where}: {count} words; the target is about {target}")


class Ledger:
    """The ledger's anchors, link definitions and components, to resolve links
    and draw flows."""

    def __init__(self, path):
        try:
            with open(path, encoding="utf-8") as f:
                self.text = f.read()
        except OSError:
            self.text = ""
        self.headings = headings(self.text)
        self.prose = markdown(self.text)[0]
        self.definitions = link_definitions(self.prose)
        self.components = flow_components.components(
            component_rows(self.prose))

    def anchor(self, ident):
        if anchor_tag(ident) in self.text:
            return ident.lower()
        for _, title, anchor in self.headings:
            if re.match(rf"{re.escape(ident)}\b", title):
                return anchor
        # Defined in a table's first cell or as a bold label: its section.
        definition = next((m for m in RECORD_DEFINITION.finditer(
            self.prose) if m[1] == ident), None)
        if not definition:
            return None
        before = headings(self.text[:definition.start()])
        return before[-1][2] if before else None


def build(content):
    """(report text, [Sequence])."""
    data = content.data
    skip = skipped(content)
    if "evolution" in skip and "next_steps" in data:
        content.errors.append(
            "next_steps: evolution is skipped, so the report has no Next steps and evolution")
    problem = content.paragraphs(data.get("problem"), "problem")
    content.length(problem, TARGETS["problem"], "problem")
    current_status = content.paragraphs(
        data.get("current_status"), "current_status")
    content.length(current_status,
                   TARGETS["current_status"], "current_status")
    next_steps = []
    if "evolution" not in skip:
        next_steps = content.paragraphs(data.get("next_steps"), "next_steps")
        content.length(next_steps, TARGETS["next_steps"], "next_steps")
    architect = "architecture" not in skip
    for key in ("architecture", "decisions_and_gaps"):
        if not architect and key in data:
            content.errors.append(
                f"{key}: architecture is skipped, so the report has no Architect summary")
    decisions = data.get("decisions_and_gaps") if architect else []
    if architect and (not isinstance(decisions, list) or not decisions):
        content.errors.append(
            "decisions_and_gaps: needs a list of decisions and gaps")
        decisions = []
    rows = decision_rows(content, "decisions_and_gaps", decisions)
    shown = ["current"] + ([] if "evolution" in skip else ["next"])
    sections, flows = {}, []
    if architect:
        architecture = data.get("architecture")
        architecture = architecture if isinstance(architecture, dict) else {}
        if not architecture:
            content.errors.append(
                "architecture: needs current" + ("" if "evolution" in skip else " and next"))
        for key in architecture:
            if key not in shown:
                content.errors.append(f"architecture.{key}: the report doesn't show this section"
                                      + (", as evolution is skipped" if key == "next" else ""))
        for key in shown:
            stage = architecture.get(key)
            if not isinstance(stage, dict):
                if architecture:
                    content.errors.append(f"architecture.{key}: missing")
                continue
            sections[key], flow = architect_section(content, key, stage)
            if flow:
                flows.append(flow)
    # Rendering takes a while: only when the content is otherwise valid.
    if not content.errors:
        render_check(content, flows)
    parts = [f"# {content.text(data.get('title'), 'title', inline=True)}",
             f"Evidence snapshot: {snapshot(content, data.get('evidence_snapshot'))}. Code links pin inspected "
             "commits; ticket, PR and document links may display later changes. Evidence revisions and "
             f"access limits are recorded in the [Research ledger]({LEDGER}).",
             HEADING_LINE["exec"], HEADING_LINE["exec.problem"], *problem]
    parts += [HEADING_LINE["exec.current"], *current_status]
    if "evolution" not in skip:
        parts += [HEADING_LINE["exec.next"], *next_steps]
    parts += [HEADING_LINE["exec.decisions"], *key_decisions(content)]
    if architect:
        parts.append(HEADING_LINE["arch"])
        for key in shown:
            parts.append(HEADING_LINE[f"arch.{key}"])
            parts += sections.get(key, [])
        parts += [HEADING_LINE["arch.decisions"],
                  "The table records source-backed decisions and evidence gaps. It does not select an option.",
                  table(["Decision or gap"] + DECISION_COLUMNS, rows)]
    parts += [HEADING_LINE["references"], *references(content)]
    return "\n\n".join(parts) + "\n", flows


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


def decision_rows(content, key, items):
    """The rows of a decisions table: the decision, why it matters, the
    established position and the evidence, which carries the ledger link."""
    rows = []
    for index, item in enumerate(items, 1):
        item = item if isinstance(item, dict) else {}
        rows.append([content.text(item.get(field), f"{key} {index}.{field}",
                                  inline=True, trace=field == "evidence")
                     for field in DECISION_FIELDS])
    return rows


def architect_section(content, key, stage):
    """([lines], Sequence or None) under one Architect summary heading: the
    text, then its titled flow (caption, components diagram, sequence), or a
    flow gap saying why there is none."""
    where = f"architecture.{key}"
    unknown = [k for k in stage if k not in (
        "summary", "sequence", "flow_gap")]
    if unknown:
        content.errors.append(f"{where}: unknown {', '.join(unknown)}; a section has only "
                              "summary, sequence and flow_gap")
    summary = content.paragraphs(stage.get("summary"), f"{where}.summary")
    content.length(summary, TARGETS["summary"], f"{where}.summary")
    flow = sequence_of(content, stage, where)
    lines = summary[:]
    if flow:
        lines += [f"#### {flow.title}", flow.caption,
                  f"```mermaid\n{flow.design}```", f"```mermaid\n{flow.source}```"]
    if stage.get("flow_gap"):
        lines.append("**Flow evidence gap:** " +
                     content.text(stage["flow_gap"], f"{where}.flow_gap", trace=True))
    elif not flow:
        content.errors.append(f"{where}: needs a sequence, or a flow_gap")
    return lines, flow


def sequence_of(content, stage, where):
    """The stage's Sequence, checked for the template's rules, or None."""
    item = stage.get("sequence")
    if item is None:
        return None
    at = f"{where}.sequence"
    if not isinstance(item, dict):
        content.errors.append(
            f"{at}: must be an object with a title and lines")
        return None
    title = item.get("title")
    if not isinstance(title, str) or not title.strip() or "\n" in title:
        content.errors.append(f"{at}: needs a one-line title")
        title = str(title)
    lines = item.get("lines")
    if not isinstance(lines, list) or not lines or not all(isinstance(line, str) for line in lines):
        content.errors.append(f"{at}: lines must be a list of Mermaid lines")
        return None
    lines = [line.rstrip() for item in lines for line in item.splitlines()
             if line.strip() and line.strip() not in ("sequenceDiagram", "autonumber")]
    for line in lines:
        if ";" in re.sub(r"#\w+;", "", line):
            content.errors.append(
                f"{title}: raw semicolon in {line.strip()!r}; Mermaid reads it as a new statement")
        message = flow_components.MESSAGE.match(line)
        if message and re.match(r"\s*\d+[.)]\s", message[4]):
            content.errors.append(
                f"{title}: {line.strip()!r} numbers its step; autonumber does")
    sequence = Sequence(title.strip(), lines, content.ledger)
    for label in flow_components.unknown_participants(sequence.flow, content.ledger.components):
        content.errors.append(f"{title}: {label!r} is no component of the ledger; name it as in the "
                              "component inventory, or declare a person with actor")
    return sequence


class Sequence:
    """A titled sequence and the design view of the components it crosses."""

    def __init__(self, title, lines, ledger):
        self.title = title
        self.source = "sequenceDiagram\n    autonumber\n" + \
            "".join(f"    {line}\n" for line in lines)
        self.flow = flow_components.Flow(lines)
        self.design = flow_components.flowchart(
            self.flow, ledger.components)
        statuses = ", ".join(flow_components.marks(
            self.flow, ledger.components))
        people = any(actor for _, actor, _ in self.flow.participants.values())
        self.caption = (f"The components this flow crosses, coloured by their status in the "
                        f"[component inventory]({LEDGER}#{heading_anchor(INVENTORY)})"
                        + (f": {statuses}" if statuses else "") + "."
                        + (" A person is drawn rounded." if people else "")
                        + " Arrows are its requests; the sequence below shows them in order.")


def render_check(content, flows):
    """Renders every flow's two diagrams in one run, to check their syntax."""
    if not flows:
        return
    try:
        output_diagram.render_many(
            [source for s in flows for source in (s.design, s.source)])
    except SystemExit as error:
        number, _, message = str(error).partition(": ")
        if not number.startswith("diagram "):
            content.errors.append(str(error))
            return
        index = int(number.split()[-1]) - 1
        which = "the components diagram" if index % 2 == 0 else "the sequence"
        content.errors.append(
            f"{flows[index // 2].title}: {which} doesn't render: {message or error}")


DECISION_FIELDS = ("decision", "why", "position", "evidence")
DECISION_COLUMNS = ["Why it matters", "Established position", "Evidence"]


def snapshot(content, value):
    try:
        day = date.fromisoformat(str(value))
    except ValueError:
        content.errors.append("evidence_snapshot: must be a date, YYYY-MM-DD")
        return str(value)
    return f"{day.day} {day:%B %Y}"


def key_decisions(content):
    items = content.data.get("key_decisions")
    if not isinstance(items, list):
        content.errors.append(
            "key_decisions: needs a list, empty when no item is evidenced")
        return []
    if not items:
        return ["No decision, blocker or risk in the inspected evidence warrants technical-leadership attention."]
    return ["These items describe implications of the linked evidence.",
            table(["Decision or risk"] + DECISION_COLUMNS, decision_rows(content, "key_decisions", items))]


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
