"""Writes the investigation's <Topic>_Report.md from <investigation>/content.json,
then checks it with check_report.py.

The script owns the template: headings, tables, fixed sentences, the title, the
evidence date and the references, which it reads from the ledger, so content.json
holds only the sections that need judgment. A claim links the ledger as
[text](ledger:F03), resolved to the record's anchor; ticket keys and
owner/repo#123 are linked from the ledger's links, and a key it can't link is
written as code rather than guessed.
"""
import argparse
from datetime import date
import json
import os
import re

from common import (CONTENT, FENCE, INVESTIGATION, REFERENCE_LINK, TABLE_HEADINGS, ledger_rows, reference_key, FOLDER_NAME, HEADING, HEADINGS, LEDGER, RECORD_DEFINITION,
                    REPORT_SUFFIX, anchor_tag, autolink, headings, investigation_dir, link_definitions, markdown, read_json, table, topic_of, unresolved_message, word_count, write_output_file)
import check_report

# Approximate prose lengths, in words: room to articulate, not quotas. Warn above
# one and a half times, or far below, under a third, which is a stub.
TARGETS = {"purpose": 150, "current_status": 200,
           "direction": 200, "summary": 300}

LEDGER_LINK = re.compile(r"\]\(ledger:([A-Za-z]+\d+)?\)")
# A decisions table's fields in content.json, and its columns after the first,
# which names the decision.
DECISION_FIELDS = ("decision", "why", "position", "evidence")
DECISION_COLUMNS = ["Why it matters", "Established position", "Evidence"]
# Each of the template's headings as written, by its id.
HEADING_LINE = {ident: "#" * level + " " +
                title for level, title, ident in HEADINGS}


def make_report(relative):
    """Writes the report and checks it; returns the JSON result, or exits
    with the problems if content.json is invalid."""
    folder, _, temporary = investigation_dir(relative)
    topic = topic_of(folder)
    content = Content(read_json(os.path.join(folder, CONTENT)),
                      Ledger(os.path.join(folder, LEDGER)), folder)
    text = build(content)
    if content.errors:
        raise SystemExit("content.json has problems, so nothing was written:\n  - "
                         + "\n  - ".join(content.errors))
    path, _ = write_output_file(
        FOLDER_NAME, f"{relative}/{topic}{REPORT_SUFFIX}", text.encode("utf-8"))
    check = check_report.check_report(path)
    return {"path": path, "temporary": temporary, "ok": check["ok"], "errors": check["errors"],
            "warnings": content.warnings + check["warnings"]}


class Content:
    """content.json, checked as it is read: problems collect in `errors`."""

    def __init__(self, data, ledger, folder):
        self.data = data if isinstance(data, dict) else {}
        self.ledger = ledger
        self.folder = folder
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
        if any(len(heading[1]) <= 3 for heading in HEADING.finditer(value)):
            self.errors.append(
                f"{where}: no # to ### headings; the template sets them (#### is fine)")
        if FENCE.search(value) or re.search(r"<div\b", value, re.I):
            self.errors.append(
                f"{where}: no code fences or <div> wrappers")
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
    """The ledger's anchors, link definitions and sources, to resolve links and
    write the evidence date and the references."""

    def __init__(self, path):
        try:
            with open(path, encoding="utf-8") as f:
                self.text = f.read()
        except OSError:
            self.text = ""
        self.headings = headings(self.text)
        self.prose = markdown(self.text)[0]
        self.definitions = link_definitions(self.prose)
        self.sources = ledger_rows(self.text, TABLE_HEADINGS["sources"])

    def inlined(self, text):
        """`text` with its reference links, as the ledger stores them, written inline."""
        def inline(match):
            url = self.definitions.get(reference_key(match))
            return f"{match[1]}[{match[2]}]({url})" if url else match[0]
        return REFERENCE_LINK.sub(inline, text)

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
    """The report's text."""
    data = content.data
    purpose = content.paragraphs(data.get("purpose"), "purpose")
    content.length(purpose, TARGETS["purpose"], "purpose")
    current_status = content.paragraphs(
        data.get("current_status"), "current_status")
    content.length(current_status,
                   TARGETS["current_status"], "current_status")
    direction = content.paragraphs(data.get("direction"), "direction")
    content.length(direction, TARGETS["direction"], "direction")
    decisions = data.get("open_choices_and_gaps")
    if not isinstance(decisions, list):
        content.errors.append(
            "open_choices_and_gaps: needs a list, empty when no choice or gap is open")
        decisions = []
    shown = ["today", "target"]
    sections = {}
    architecture = data.get("architecture")
    architecture = architecture if isinstance(architecture, dict) else {}
    if not architecture:
        content.errors.append("architecture: needs today and target")
    for key in architecture:
        if key not in shown:
            content.errors.append(
                f"architecture.{key}: the report doesn't show this section")
    for key in shown:
        stage = architecture.get(key)
        if not isinstance(stage, dict):
            if architecture:
                content.errors.append(f"architecture.{key}: missing")
            continue
        sections[key] = architect_section(content, key, stage)
    parts = [f"# {topic_of(content.folder).replace('-', ' ')}",
             f"Evidence snapshot: {snapshot(content)}. Code links pin inspected "
             "commits; ticket, PR and document links may display later changes. Evidence revisions and "
             f"access limits are recorded in the [Research ledger]({LEDGER}).",
             HEADING_LINE["exec"], HEADING_LINE["exec.purpose"], *purpose]
    parts += [HEADING_LINE["exec.current"], *current_status]
    parts += [HEADING_LINE["exec.direction"], *direction]
    parts += [HEADING_LINE["exec.decisions"], *key_decisions(content)]
    parts.append(HEADING_LINE["arch"])
    for key in shown:
        parts.append(HEADING_LINE[f"arch.{key}"])
        parts += sections.get(key, [])
    parts.append(HEADING_LINE["arch.decisions"])
    parts += ["The table records source-backed decisions and evidence gaps. It does not select an option.",
              table(["Decision or gap"] + DECISION_COLUMNS,
                    decision_rows(content, "open_choices_and_gaps", decisions))] if decisions else [
        "No technical choice or evidence gap is open in the inspected evidence."]
    parts += [HEADING_LINE["references"], *references(content)]
    return "\n\n".join(parts) + "\n"


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
    """The lines under one Architect summary heading: its text. Diagrams
    are left out until they are designed again."""
    where = f"architecture.{key}"
    summary = content.paragraphs(stage.get("summary"), f"{where}.summary")
    content.length(summary, TARGETS["summary"], f"{where}.summary")
    return summary


def snapshot(content):
    """The day the evidence was last checked: the latest date a source of the
    ledger records, or the investigation's own day when none records one."""
    days = [date.fromisoformat(day) for row in content.ledger.sources if len(row) > 3
            for day in re.findall(r"\b\d{4}-\d{2}-\d{2}\b", row[3]) if valid_day(day)]
    if days:
        day = max(days)
    else:
        match = INVESTIGATION.fullmatch(
            os.path.basename(os.path.normpath(content.folder)))
        assert match, "make_report checked the folder's name with topic_of"
        yy, mm, dd = match["date"].split("-")
        day = date(2000 + int(yy), int(mm), int(dd))
    return f"{day.day} {day:%B %Y}"


def valid_day(text):
    try:
        date.fromisoformat(text)
    except ValueError:
        return False
    return True


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
    """Every source of the ledger with a link, by its group: code, tracker and
    documentation. A source with access limits or a replacement is historical."""
    lines = []
    for group, label in (("source_control", "Implementation and configuration"), ("workflow", "Delivery"),
                         ("documentation", "Vision, rationale and reported operational gaps")):
        entries = []
        for row in content.ledger.sources:
            if len(row) < 6 or not row[1].strip().casefold().startswith(group):
                continue
            reference = content.ledger.inlined(row[2].strip())
            if "](" not in reference:
                continue
            entry = f"- {reference}" + \
                ("" if row[5].strip() in ("", "None") else " (historical)")
            if entry not in entries:
                entries.append(entry)
        lines += [f"**{label}**",
                  "\n".join(entries) if entries else "None in the inspected sources."]
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
