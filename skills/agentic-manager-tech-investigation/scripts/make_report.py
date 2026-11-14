"""Writes the investigation's <Topic>_Report.md from <investigation>/content.json;
check_report.py checks it at handover.

The script owns the template: headings, tables, fixed sentences, the title and
the evidence date, which it reads from the ledger, so content.json
holds only the sections that need judgment. A claim links the ledger as
[text](ledger:F03), resolved to the record's anchor; ticket keys and
owner/repo#123 are linked from the ledger's links, and a key it can't link is
written as code rather than guessed.
"""
from datetime import date
import os
import re

from common import (CONTENT, folder_day, display_date, FENCE, backtick_error, TABLE_HEADINGS, ledger_rows, FOLDER_NAME, HEADING, HEADINGS, LEDGER,
                    REPORT_SUFFIX, anchor_tag, autolink, investigation_dir, link_definitions, markdown, read_json, table, topic_of, unlinked_backticks, unresolved_message, word_count, write_output_file)

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
    """Writes the report; returns its path, whether the folder is temporary
    and content.json's warnings, or exits with the problems if content.json
    is invalid."""
    folder, _, temporary = investigation_dir(relative)
    topic = topic_of(folder)
    content, text = _built(folder)
    if content.errors:
        raise SystemExit("content.json has problems, so nothing was written:\n  - "
                         + "\n  - ".join(content.errors))
    path, _ = write_output_file(
        FOLDER_NAME, f"{relative}/{topic}{REPORT_SUFFIX}", text.encode("utf-8"))
    return {"path": path, "temporary": temporary, "warnings": content.warnings}


def content_problems(relative):
    """The problems of the investigation's content.json, as make_report would
    list them, without writing anything."""
    folder, _, _ = investigation_dir(relative)
    return _built(folder)[0].errors


def _built(folder):
    """(the investigation's content.json in `folder`, read against its
    ledger, the report built from it)."""
    content = Content(read_json(os.path.join(folder, CONTENT)),
                      Ledger(os.path.join(folder, LEDGER)), folder)
    return content, build(content)


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
        value = self.links(self.linked(value.strip(), where), where)
        # The handover check's backtick rule, applied here so it fails first.
        if spans := unlinked_backticks(value, self.ledger.text):
            self.errors.append(backtick_error(where, spans))
        return value

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
                    f"{where}: ledger:{ident} matches no table row in {LEDGER}")
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
    write the evidence date."""

    def __init__(self, path):
        try:
            with open(path, encoding="utf-8") as f:
                self.text = f.read()
        except OSError:
            self.text = ""
        self.prose = markdown(self.text)[0]
        self.definitions = link_definitions(self.prose)
        self.sources = ledger_rows(self.text, TABLE_HEADINGS["sources"])

    def anchor(self, ident):
        """The anchor of the ledger row that records `ident`, outside a code
        fence, or None: ledger.py writes every record as a row carrying it."""
        return ident.lower() if anchor_tag(ident) in self.prose else None


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
             "commits; ticket, PR and document links may display later changes. Each source's revision "
             f"and how much of it was read are recorded in the [Research ledger]({LEDGER}).",
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
    """The lines under one Architect summary heading: its text."""
    where = f"architecture.{key}"
    summary = content.paragraphs(stage.get("summary"), f"{where}.summary")
    content.length(summary, TARGETS["summary"], f"{where}.summary")
    return summary


def snapshot(content):
    """The day of the evidence: the latest date in the Revision of the
    ledger's sources, such as a page's last edit, or the investigation's own day
    when none records one."""
    days = [date.fromisoformat(day) for row in content.ledger.sources if len(row) > 3
            for day in re.findall(r"\b\d{4}-\d{2}-\d{2}\b", row[3]) if valid_day(day)]
    if days:
        day = max(days)
    else:
        day = folder_day(os.path.basename(os.path.normpath(content.folder)))
        assert day, "make_report checked the folder's name with topic_of"
    return display_date(day)


def valid_day(text):
    """Whether `text` is a date as YYYY-MM-DD."""
    try:
        date.fromisoformat(text)
    except ValueError:
        return False
    return True


def key_decisions(content):
    """The Key decisions and risks section's lines, from content.json's key_decisions."""
    items = content.data.get("key_decisions")
    if not isinstance(items, list):
        content.errors.append(
            "key_decisions: needs a list, empty when no item is evidenced")
        return []
    if not items:
        return ["No decision, blocker or risk in the inspected evidence warrants technical-leadership attention."]
    return ["These items describe implications of the linked evidence.",
            table(["Decision or risk"] + DECISION_COLUMNS, decision_rows(content, "key_decisions", items))]
