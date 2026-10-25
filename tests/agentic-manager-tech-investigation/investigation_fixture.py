"""An invented investigation shared by the generator tests: its content.json and
ledger."""
import copy
import json
import os
import tempfile
from unittest import mock

from common import COMPONENT_HEADER, FINDING_HEADER, QUEUE_HEADER, REVIEW_HEADER, SOURCE_HEADER, anchored, table
from agentic_manager import config, output_folder
from init_investigation import ledger_skeleton

INVESTIGATION = "Acme-Search_26-10-05"
# One enabled source per group the skill needs; the code through a cli source
# other than gh, so no test needs gh signed in.
SOURCES = {"documentation": {"notion-mcp": {"enabled": True}},
           "workflow": {"jira-api": {"enabled": True}},
           "source_control": {"gitlab-cli": {"enabled": True}}}


def with_queue(ledger, subsection, rows):
    """`ledger` with the empty queue table under `### <subsection>` holding `rows`."""
    empty = f"### {subsection}\n\n{table(QUEUE_HEADER, [])}\n\nNone."
    assert empty in ledger, subsection
    return ledger.replace(empty, f"### {subsection}\n\n{table(QUEUE_HEADER, rows)}", 1)


def with_reviews(ledger, rounds):
    """`ledger` with its empty reviews section holding `rounds`, as [round, raised]."""
    empty = "## Independent reviews\n\nNone yet."
    assert empty in ledger
    return ledger.replace(empty, "## Independent reviews\n\n" + table(REVIEW_HEADER, rounds), 1)


def words(count):
    return " ".join(["word"] * count)


CONTENT = {
    "purpose": [words(90) + " [doc](https://example.com/doc) [F01](ledger:F01)."],
    "current_status": [words(190) + " [code](ledger:F01)."],
    "direction": [words(190) + " [code](ledger:F01)."],
    "key_decisions": [{"decision": "Index choice", "why": "Affects cost",
                       "position": "Unresolved", "evidence": "[proposal](https://example.com/p) [F01](ledger:F01)"}],
    "architecture": {
        "today": {"summary": [words(290) + " [code](ledger:F01)."]},
        "target": {"summary": [words(290) + " [code](ledger:F01)."]},
    },
    "open_choices_and_gaps": [{"decision": "Index", "why": "Sets the cost", "position": "Unresolved",
                               "evidence": "[gap](ledger:G01)"}],
}

# The fixture's one finding, read in the code source.
FINDINGS = table(FINDING_HEADER, [
    [anchored("F01"), "The search API is merged.", "S01", "Routes read in full."]])
# The fixture's components.
COMPONENTS = table(COMPONENT_HEADER, [
    [ident, name, "Role", "—", status, "None", "G01" if status.startswith("⬜") else "F01", "Unchanged",
     "None"]
    for ident, name, status in (("C01", "Search API (service)", "🟨 Planned"),
                                ("C02", "Search index (store)", "⬜ Unverified"),
                                ("C03", "Publish job (job)",
                                 "🟨 Planned"),
                                ("C04", "Embedding API (external product)", "⬜ Unverified"))])
# The sources the report's references come from: code read in full, a ticket
# replaced by a newer one, so superseded, and the newer one read in part, so
# limited. None records a date, so the evidence date is the investigation's.
SOURCES_READ = table(SOURCE_HEADER, [
    ["S01", "code",
        "[Search API](https://example.com/code)", "abc", "full", "F01", "None"],
    ["S02", "tracker",
        "[PROJ-1](https://example.com/PROJ-1)", "Done", "full", "None", "S03"],
    ["S03", "tracker", "[PROJ-2](https://example.com/PROJ-2)", "In progress", "partial: description only",
     "None", "None"]])
LEDGER = (with_reviews(with_queue(ledger_skeleton("Acme-Search"), "Completed", [
    ["Q01", "Start", "Read code", "—", "F01"]]), [["1", "No issue raised"]])
    .replace("## Sources\n\nNone yet.", "## Sources\n\n" + SOURCES_READ, 1)
    .replace("## Findings\n\nNone yet.", "## Findings\n\n" + FINDINGS)
    .replace("### Components\n\nNone yet.", "### Components\n\n" + COMPONENTS)
    .replace("## Evidence gaps\n\nNone yet.",
             "## Evidence gaps\n\n- **G01** Billing callers unverified."))


def content():
    return copy.deepcopy(CONTENT)


def temp_output(test):
    """The skill's output folder in a temporary folder, for `test`: a config
    of its own setting the output root, never the developer's."""
    tmp = tempfile.TemporaryDirectory()
    test.addCleanup(tmp.cleanup)
    root = os.path.realpath(tmp.name)
    path = os.path.join(root, "config.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"sources": SOURCES, "output": {
                  "root": os.path.join(root, "out")}}, f)
    for target, attribute, value in ((config, "CONFIG_PATH", path),
                                     (output_folder, "TEMP_ROOT", os.path.join(root, "temp"))):
        patcher = mock.patch.object(target, attribute, value)
        patcher.start()
        test.addCleanup(patcher.stop)
    return os.path.join(root, "out", "tech-investigations")
