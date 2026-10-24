"""An invented investigation shared by the generator tests: its content.json and
ledger."""
import copy
import json
import os
import tempfile
from unittest import mock

from common import COMPONENT_HEADER, FINDING_FIELDS, QUEUE_HEADER, SOURCE_HEADER, table
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

FINDING = ("### F01 — Search API is merged\n\n"
           + "\n".join(f"**{field}:** text." for field in FINDING_FIELDS))
# The fixture's components.
COMPONENTS = table(COMPONENT_HEADER, [
    [ident, name, "Role", "—", status, "None", "G01" if status.startswith("⬜") else "F01", "Unchanged",
     "None"]
    for ident, name, status in (("C01", "Search API (service)", "🟨 Planned"),
                                ("C02", "Search index (store)", "⬜ Unverified"),
                                ("C03", "Publish job (job)",
                                 "🟨 Planned"),
                                ("C04", "Embedding API (external product)", "⬜ Unverified"))])
# The sources the report's references and evidence date come from: code read
# on the day, and a ticket since replaced, so historical.
SOURCES_READ = table(SOURCE_HEADER, [
    ["S01", "source_control", "[Search API](https://example.com/code)", "abc, 2026-10-05", "Routes read.", "None",
     "Implementation"],
    ["S02", "workflow", "[PROJ-1](https://example.com/PROJ-1)", "read 2026-10-04", "Read in full.",
     "Superseded by a newer ticket", "Delivery"]])
LEDGER = (with_queue(ledger_skeleton("Acme-Search"), "Completed", [
    ["Q01", "Start", "Read code", "Code", "—", "F01"],
    ["Q02", "Independent review", "Independent review of the ledger", "Subagent", "None", "No issue raised"]])
    .replace(table(SOURCE_HEADER, []), SOURCES_READ, 1)
    .replace("## Findings and validation chains\n\nNone yet.",
             "## Findings and validation chains\n\n" + FINDING)
    .replace("## Component inventory and evolution\n\nNone yet.",
             "## Component inventory and evolution\n\n" + COMPONENTS)
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
