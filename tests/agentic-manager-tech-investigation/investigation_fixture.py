"""What the skill's tests share: an invented investigation, its content.json
and a ledger ready for handover, the output folder and config each test runs
in, a new investigation started there, and builders and helpers for ledgers,
their rows and the problems the rules find in them."""
import copy
import json
import os
import re
import tempfile
from datetime import date
from pathlib import Path
from unittest import mock

import common
from common import (COMPONENT_HEADER, FINDING_HEADER, GAP_HEADER, ID_LETTERS, QUEUE_HEADER, REVIEW_HEADER, SOURCE_HEADER, TABLES,
                    anchored, section_span, table)
from agentic_manager import config, output_folder
from init_investigation import init, ledger_skeleton

INVESTIGATION = "Acme-Search_26-10-05"
# One enabled source per group the skill needs; the code through a cli source
# other than gh, so no test needs gh signed in.
SOURCES = {"documentation": {"notion-mcp": {"enabled": True}},
           "workflow": {"jira-api": {"enabled": True}},
           "source_control": {"gitlab-cli": {"enabled": True}}}


# The code host pull requests link to in the tests.
CODE_HOST = "https://git.example"


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


def with_prose(ledger, text):
    """`ledger` with `text` in its empty Scope boundaries section: prose in
    the ledger, for the checks that read all of it."""
    empty = "## Scope boundaries\n\nNone yet."
    assert empty in ledger
    return ledger.replace(empty, "## Scope boundaries\n\n" + text, 1)


def with_rows(ledger, name, rows):
    """`ledger` with the section of its table `name` holding only `rows`,
    each a row's cells, under the table's header."""
    heading, header, _ = TABLES[name]
    lines = ledger.split("\n")
    span = section_span(lines, heading)
    assert span, heading
    start, end = span
    lines[start + 1:end] = ["", *table(header, rows).split("\n"), ""]
    return "\n".join(lines)


def source_row(ident="S01", kind="code", reference="[x](https://example.com/x)", revision="abc", coverage="full",
               findings="None", superseded="None"):
    """A source row's cells, as the ledger holds them."""
    return [ident, kind, reference, revision, coverage, findings, superseded]


def plain(text):
    """The ledger `text` without the anchors and ID links the script adds,
    for tests about something else."""
    return re.sub(rf"\[([{ID_LETTERS}]\d+)\]\(#[a-z]+\d+\)", r"\1", re.sub(r'<a id="[^"]+"></a>', "", text))


def assert_problem(test, problem, expected):
    """Assert that `problem`, what a rule found, is None when `expected` is,
    else names `expected`."""
    if expected is None:
        test.assertIsNone(problem)
    else:
        test.assertIn(expected, problem or "")


# A gap blocking a question, as a submission gives it.
GAP = {"gap": "Billing callers", "missing": "The API is merged; its callers aren't read",
       "would_close": "Read access", "blocked_by": "No access (billing repository)", "evidence": "[[F01]]",
       "owner_and_next_check": "Billing team"}


def finding(key="[[f1]]", claim="Search reads the index.", sources="[[S01]]", partial=None, **more):
    """A finding as a submission gives it; `partial` gives, for each source
    it cites read only in part, why the part unread can't change it."""
    return {"key": key, "claim": claim, "sources": sources, "limits": "None",
            **({"partial": partial} if partial else {}), **more}


# A finding's partial when it cites S02, the source read in part that the
# answers of investigate.py's tests rest on.
UNREAD = {"[[S02]]": "the unread sections can't change it"}


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

# The fixture's findings: one read in the code, one in the tracker, which the
# planned components rest on.
FINDING_ROWS = [[anchored("F01"), "The search API is merged.", "S01", "Routes read in full."],
                [anchored("F02"), "The publish job is planned.", "S02", "None"]]
FINDINGS = table(FINDING_HEADER, FINDING_ROWS)
# The fixture's components.
COMPONENTS = table(COMPONENT_HEADER, [
    [ident, name, kind, "None", "Role", "—", state, "Unchanged",
     "G01" if state.startswith("⬜") else "F02"]
    for ident, name, kind, state in (("C01", "Search API", "service", "🟨 Planned"),
                                     ("C02", "Search index",
                                      "store", "⬜ Unverified"),
                                     ("C03", "Publish job",
                                      "job", "🟨 Planned"),
                                     ("C04", "Embedding API", "external product", "⬜ Unverified"))])
# The sources the report's references come from: code read in full, a ticket
# replaced by a newer one, so superseded, and the newer one read in part, so
# limited. None records a date, so the evidence date is the investigation's.
SOURCE_ROWS = [source_row("S01", "code", "[Search API](https://example.com/code)", "abc", "full", "F01"),
               source_row("S02", "tracker", "[PROJ-1](https://example.com/PROJ-1)",
                          "Done", "full", "F02", "S03"),
               source_row("S03", "tracker", "[PROJ-2](https://example.com/PROJ-2)", "In progress",
                          "partial: description only")]
SOURCES_READ = table(SOURCE_HEADER, SOURCE_ROWS)
# The fixture's gap, as ledger.py writes it, which C02 and C04 rest on.
GAPS = table(GAP_HEADER, [[anchored("G01"), "Billing callers", "The API is merged; its callers aren't read",
                           "Read access", "No access (billing repository)", "Billing team", "F01"]])
# The ledger with its one question answered, before any review, and as handed
# over, its review finished.
UNREVIEWED = (with_queue(ledger_skeleton("Acme-Search"), "Completed", [
    ["Q01", "Start", "Read code", "—", "F01"]])
    .replace("## Sources\n\nNone yet.", "## Sources\n\n" + SOURCES_READ, 1)
    .replace("## Findings\n\nNone yet.", "## Findings\n\n" + FINDINGS)
    .replace("### Components\n\nNone yet.", "### Components\n\n" + COMPONENTS)
    .replace("## Evidence gaps\n\nNone yet.",
             "## Evidence gaps\n\n" + GAPS))
LEDGER = with_reviews(UNREVIEWED, [["1", "No issue raised"]])


def content():
    return copy.deepcopy(CONTENT)


def temp_output(test):
    """The skill's output folder in a temporary folder, for `test`: a config
    of its own setting the output root, never the developer's, a system
    temporary folder of its own, for the run's working folder, and CODE_HOST
    as the code host, so no test asks gh."""
    tmp = tempfile.TemporaryDirectory()
    test.addCleanup(tmp.cleanup)
    root = os.path.realpath(tmp.name)
    path = os.path.join(root, "config.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"sources": SOURCES, "output": {
                  "root": os.path.join(root, "out")}}, f)
    for target, attribute, value in ((config, "CONFIG_PATH", path),
                                     (output_folder, "TEMP_ROOT",
                                      os.path.join(root, "temp")),
                                     (common, "CODE_HOST", {
                                      "host": CODE_HOST}),
                                     (tempfile, "tempdir", os.path.join(root, "system-temp"))):
        patcher = mock.patch.object(target, attribute, value)
        patcher.start()
        test.addCleanup(patcher.stop)
    return os.path.join(root, "out", common.FOLDER_NAME)


def start(test):
    """The ledger of a new investigation, Acme-Search, started in `test`'s
    own output folder (temp_output) on 5 October 2026."""
    folder = temp_output(test)
    init("Acme-Search", today=date(2026, 10, 5))
    return Path(folder) / INVESTIGATION / "ledger.md"
