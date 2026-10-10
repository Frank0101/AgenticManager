"""Unit tests for skills/agentic-manager-tech-investigation/scripts/ledger.py.
Run with: python3 tests/run.py agentic-manager-tech-investigation

Each test starts a new investigation in a temporary output folder, edits its
ledger through main(), and reads the ledger back.
"""

import contextlib
import io
import json
import os
import re
import sys
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(TEST_DIR))
sys.path.insert(0, os.path.join(REPO_ROOT, "skills",
                os.path.basename(TEST_DIR), "scripts"))
import check_report  # noqa: E402
import init_investigation  # noqa: E402
import ledger  # noqa: E402
sys.path.insert(0, TEST_DIR)
from investigation_fixture import temp_output  # noqa: E402

INVESTIGATION = "Acme-Search_26-10-05"
QUEUE_ROW = ["Request", "Read the code", "Code", "None", "High", "Ready", ""]


class LedgerTest(unittest.TestCase):
    def setUp(self):
        self.folder = temp_output(self)
        init_investigation.init("Acme-Search", today=date(2026, 10, 5))
        self.path = Path(self.folder) / INVESTIGATION / "ledgers.md"

    def run_ledger(self, *args, cells=None, text=None):
        stdin = io.StringIO(text if text is not None else json.dumps(
            cells) if cells is not None else "")
        out = io.StringIO()
        with mock.patch("sys.stdin", stdin), contextlib.redirect_stdout(out):
            ledger.main([args[0], "--investigation", INVESTIGATION, *args[1:]])
        return json.loads(out.getvalue())

    def read_ledger(self, *args):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            ledger.main([args[0], "--investigation", INVESTIGATION, *args[1:]])
        return out.getvalue()

    def text(self):
        return self.path.read_text(encoding="utf-8")

    def rows(self, heading):
        """The first column of the data rows of the first table under `heading`."""
        text = self.text()
        start = text.index(heading)
        end = text.find("\n#", start + 1)
        table = [line for line in text[start:end if end >
                                       0 else None].splitlines() if line.startswith("|")]
        return [line.split(" | ")[0].strip("| ") for line in table[2:]]

    def test_next_id_per_kind(self):
        self.assertEqual(self.run_ledger(
            "next-id", "--kind", "S")["id"], "S01")
        self.run_ledger("row", "--table", "sources", "--id",
                        "S01", cells=["a", "b", "c", "d", "e", "Architecture"])
        self.run_ledger("row", "--table", "sources", "--id",
                        "S02", cells=["a", "b", "c", "d", "e", ""])
        self.run_ledger("row", "--table", "gaps", "--id",
                        "G01", cells=["a", "b", "c", "d", "e", "Delivery"])
        for kind, expected in (("S", "S03"), ("G", "G02"), ("D", "D01"), ("Q", "Q01"), ("C", "C01"), ("F", "F01")):
            with self.subTest(kind):
                self.assertEqual(self.run_ledger(
                    "next-id", "--kind", kind)["id"], expected)

    def test_rows_are_added_replaced_and_sorted(self):
        for row_id, kind in (("S10", "x"), ("S02", "y"), ("S10", "z")):
            self.run_ledger("row", "--table", "sources", "--id",
                            row_id, cells=[kind, "r", "v", "m", "l", ""])
        self.assertEqual(
            self.rows("## Revisions and source register"), ["S02", "S10"])
        self.assertIn("| S10 | z |", self.text())
        self.assertNotIn("| S10 | x |", self.text())

    def test_a_table_is_created_where_there_was_a_placeholder(self):
        self.assertIn("## Open decisions\n\nNone yet.", self.text())
        self.run_ledger("row", "--table", "decisions", "--id",
                        "D01", cells=["a", "b", "c", "d", "e"])
        text = self.text()
        self.assertIn("| ID | Decision |", text)
        self.assertNotIn("## Open decisions\n\nNone yet.", text)
        self.run_ledger("row", "--table", "file-coverage",
                        cells=["S01", "[a](https://example.com/a)", "Full", "F01"])
        self.run_ledger("row", "--table", "file-coverage",
                        cells=["S01", "[b](https://example.com/b)", "Full", "F01"])
        self.assertEqual(
            self.rows("### File reading coverage"), ["S01", "S01"])

    def test_wrong_columns_and_ids_are_refused(self):
        cases = [(["row", "--table", "sources", "--id", "S01"], ["too few"], "columns"),
                 (["row", "--table", "sources", "--id", "Q01"],
                  ["a", "b", "c", "d", "e"], "IDs start with S"),
                 (["row", "--table", "sources"], ["a"], "needs --id"),
                 (["row", "--table", "file-coverage", "--id", "S01"], ["a"], "has no IDs")]
        for args, cells, expected in cases:
            with self.subTest(expected), self.assertRaisesRegex(SystemExit, expected):
                self.run_ledger(*args, cells=cells)

    def test_move_a_queue_row_between_subsections(self):
        self.run_ledger("row", "--table", "queue-ready",
                        "--id", "Q01", cells=QUEUE_ROW)
        self.run_ledger("row", "--table", "queue-ready",
                        "--id", "Q02", cells=QUEUE_ROW)
        self.run_ledger("move", "--id", "Q01", "--to", "completed", "--set",
                        "Status=Answered", "--set", "Outcome / finding IDs=F01")
        self.assertEqual(self.rows("### Ready / in progress"), ["Q02"])
        self.assertEqual(self.rows("### Completed"), ["Q01"])
        self.assertIn("| Answered | F01 |", self.text())
        self.run_ledger("move", "--id", "Q02", "--to", "blocked")
        self.assertEqual(self.rows("### Ready / in progress"), [])
        self.assertIn("### Ready / in progress", self.text())
        ready = self.text().split(
            "### Ready / in progress")[1].split("### Blocked")[0]
        self.assertIn("None.", ready)
        blocked = self.text().split("### Blocked")[1].split("### Completed")[0]
        self.assertNotIn("None.", blocked)
        with self.assertRaisesRegex(SystemExit, "no queue row Q09"):
            self.run_ledger("move", "--id", "Q09", "--to", "completed")
        with self.assertRaisesRegex(SystemExit, "no column"):
            self.run_ledger("move", "--id", "Q01", "--to",
                            "ready", "--set", "Nope=1")

    def test_links_are_defined_once_and_sorted(self):
        self.run_ledger("link", "--key", "b-doc",
                        "--url", "https://example.com/b")
        self.run_ledger("link", "--key", "a-doc",
                        "--url", "https://example.com/a")
        self.run_ledger("link", "--key", "b-doc",
                        "--url", "https://example.com/b2")
        links = self.text().split("## Links")[1]
        self.assertEqual([line for line in links.splitlines() if line.startswith("[")],
                         ["[a-doc]: https://example.com/a", "[b-doc]: https://example.com/b2"])
        self.assertNotIn("None yet.", links)
        with self.assertRaisesRegex(SystemExit, "--key is"):
            self.run_ledger("link", "--key", "bad key",
                            "--url", "https://example.com")

    def finding(self, title, evidence="S01: [doc][doc]", ident=None):
        fields = {"title": title, "Claim": "A claim.", "Kind": "observed implementation", "Evidence": evidence,
                  "Validation and limits": "code read; high"}
        args = ["finding"] + (["--id", ident] if ident else [])
        return self.run_ledger(*args, cells=fields)["id"]

    def test_findings_are_added_replaced_sorted_and_checked(self):
        self.assertEqual([self.finding("One"), self.finding(
            "Two"), self.finding("Three")], ["F01", "F02", "F03"])
        self.assertEqual(self.finding("Two again", ident="F02"), "F02")
        self.finding("Ten", ident="F10")
        self.finding("Zero", ident="F04")
        text = self.text()
        self.assertNotIn("None yet.", text.split(
            "## Findings and validation chains")[1].split("\n## ")[0])
        self.assertEqual([line[:7] for line in text.splitlines() if re.match(r"### F\d", line)],
                         ["### F01", "### F02", "### F03", "### F04", "### F10"])
        self.assertIn("### F02 — Two again", text)
        self.assertNotIn("### F02 — Two\n", text)
        self.assertIn("- **Claim:** A claim.", text)
        self.assertEqual(self.run_ledger(
            "next-id", "--kind", "F")["id"], "F11")
        self.finding("Optional line", ident="F20")
        self.run_ledger("finding", "--id", "F20", cells={
            "title": "Optional line", "Claim": "c", "Kind": "k", "Evidence": "e", "Validation and limits": "v",
            "Supersedes or contradicted by": "Superseded by F21."})
        self.assertIn(
            "- **Supersedes or contradicted by:** Superseded by F21.", self.text())
        self.assertNotIn("Related actions", self.text())
        for fields, expected in (({"title": "x"}, "missing Claim"),
                                 ({**{"title": "x", "Claim": "c", "Kind": "k", "Evidence": "e",
                                      "Validation and limits": "v"}, "Extra": "y"}, "unknown Extra")):
            with self.subTest(expected), self.assertRaisesRegex(SystemExit, expected):
                self.run_ledger("finding", cells=fields)

    def test_rows_findings_and_links_are_removed(self):
        for row_id in ("S01", "S02"):
            self.run_ledger("row", "--table", "sources", "--id",
                            row_id, cells=["a", "b", "c", "d", "e", ""])
        self.run_ledger("remove", "--table", "sources", "--id", "S01")
        self.assertEqual(
            self.rows("## Revisions and source register"), ["S02"])
        self.run_ledger("remove", "--table", "sources", "--id", "S02")
        self.assertIn("None.", self.text().split(
            "## Revisions and source register")[1].split("###")[0])
        self.run_ledger("row", "--table", "file-coverage",
                        cells=["[a][a]", "x", "Full", "F01"])
        self.run_ledger("row", "--table", "file-coverage",
                        cells=["[b][b]", "x", "Full", "F01"])
        self.run_ledger("remove", "--table", "file-coverage", "--match", "[a]")
        self.assertEqual(self.rows("### File reading coverage"), ["[b][b]"])
        self.finding("One")
        self.run_ledger("remove", "--table", "findings", "--id", "F01")
        self.assertIn(
            "## Findings and validation chains\n\nNone yet.", self.text())
        self.run_ledger("link", "--key", "doc", "--url",
                        "https://example.com/doc")
        self.run_ledger("unlink", "--key", "doc")
        self.assertNotIn("[doc]:", self.text())
        cases = [(["remove", "--table", "sources", "--id", "S09"], "no sources row S09"),
                 (["remove", "--table", "findings", "--id", "F09"], "no finding F09"),
                 (["remove", "--table", "file-coverage",
                  "--match", "zzz"], "no file-coverage row"),
                 (["remove", "--table", "sources", "--match", "x"], "takes --id"),
                 (["unlink", "--key", "nope"], "no link")]
        for args, expected in cases:
            with self.subTest(expected), self.assertRaisesRegex(SystemExit, expected):
                self.run_ledger(*args)

    def test_sources_take_their_findings_from_the_evidence_lines(self):
        for row_id in ("S01", "S02", "S03"):
            self.run_ledger("row", "--table", "sources", "--id",
                            row_id, cells=["a", "[x][x]", "d", "Read.", "e", ""])
        self.finding("One", evidence="S01 and S02: [doc][doc]")
        self.finding("Two", evidence="S02: [doc][doc]")
        self.run_ledger("sync-sources")
        self.run_ledger("sync-sources")
        text = self.text()
        self.assertIn("| Read. Findings: F01. |", text)
        self.assertIn("| Read. Findings: F01, F02. |", text)
        self.assertEqual(text.count("Findings: F01."), 1)
        self.run_ledger("remove", "--table", "findings", "--id", "F01")
        self.run_ledger("sync-sources")
        self.assertNotIn("Findings: F01.", self.text())
        self.assertEqual(check_report.source_finding_problems(self.text()), [])
        self.finding("Three", evidence="S03: [doc][doc]")
        self.assertEqual(check_report.source_finding_problems(self.text()),
                         ["S03 lists none, its findings are F03"])

    def test_text_sections_are_replaced(self):
        self.run_ledger("text", "--section", "Resume here",
                        text="Scope.\n\nNext: read it.\n")
        self.assertIn(
            "## Resume here\n\nScope.\n\nNext: read it.\n\n## Research action queue", self.text())
        self.run_ledger("text", "--section", "Reflection",
                        text="What changed.\n")
        self.run_ledger("text", "--section", "Reflection", text="Final.\n")
        reflection = self.text().split("## Reflection")[1].split("\n## ")[0]
        self.assertIn("Final.", reflection)
        self.assertNotIn("What changed.", reflection)
        with self.assertRaisesRegex(SystemExit, "--section is one of"):
            self.run_ledger("text", "--section", "Links", text="x")

    def test_areas_are_checked_and_counted(self):
        for row_id, group, areas in (("S01", "documentation: vision", "Architecture, Delivery"),
                                     ("S02", "source_control: code", "Architecture"),
                                     ("S03", "search record", "")):
            self.run_ledger("row", "--table", "sources", "--id", row_id,
                            cells=[group, "[x][x]", "d", "Read.", "e", areas])
        self.run_ledger("row", "--table", "gaps", "--id", "G01",
                        cells=["a", "b", "c", "d", "e", "Architecture"])
        status = self.read_ledger("status")
        self.assertIn(
            "Architecture: 1 / 0 / 1, 1 gaps  (none from workflow)", status)
        self.assertIn(
            "Delivery: 1 / 0 / 0, 0 gaps  (none from workflow, source_control)", status)
        self.assertNotIn("sources with no Areas", status)
        self.run_ledger("row", "--table", "sources", "--id", "S04",
                        cells=["workflow: ticket", "[x][x]", "d", "Read.", "e", ""])
        self.assertIn("sources with no Areas: S04", self.read_ledger("status"))
        with self.assertRaisesRegex(SystemExit, "Areas must be some of.*not Billing"):
            self.run_ledger("row", "--table", "sources", "--id", "S05",
                            cells=["workflow", "[x][x]", "d", "Read.", "e", "Delivery, Billing"])

    def test_reading_commands_show_find_and_summarise(self):
        status = self.read_ledger("status")
        self.assertIn("queue: 0 ready, 0 blocked, 0 completed", status)
        self.assertIn(
            "Architecture: 0 / 0 / 0, 0 gaps  (none from documentation, workflow, source_control)", status)
        self.assertIn(
            "not started: Resume here, Boundary, method and access", status)
        self.run_ledger("row", "--table", "queue-ready",
                        "--id", "Q01", cells=QUEUE_ROW)
        self.run_ledger("row", "--table", "sources", "--id", "S01",
                        cells=["documentation", "[the search page][doc]", "today", "Read.", "none", "Architecture, Delivery"])
        self.run_ledger("link", "--key", "doc", "--url",
                        "https://example.com/search-page")
        self.finding("Search is slow", evidence="S01: [doc][doc]")
        status = self.read_ledger("status")
        self.assertIn("queue: 1 ready, 0 blocked, 0 completed", status)
        self.assertIn("  ready Q01 [High] Read the code", status)
        self.assertIn("1 findings, 1 sources", status)
        self.assertIn("Architecture: 1 / 0 / 0", status)
        found = self.read_ledger("find", "--text", "SEARCH").splitlines()
        self.assertEqual([line.split(":")[0] for line in found],
                         ["sources S01", "finding F01", "link [doc]"])
        self.assertIn("no match", self.read_ledger("find", "--text", "zzz"))
        self.assertTrue(self.read_ledger(
            "show", "--id", "F01").startswith("### F01 — Search is slow"))
        self.assertIn("Material read and findings: Read.",
                      self.read_ledger("show", "--id", "s01"))
        self.assertIn("F01 — Search is slow", self.read_ledger(
            "show", "--table", "findings"))
        self.assertIn("| Q01 |", self.read_ledger(
            "show", "--table", "queue-ready"))
        for args, expected in ((["show"], "takes --id or --table"), (["show", "--id", "F09"], "no finding F09"),
                               (["show", "--id", "Z9"], "no record Z9")):
            with self.subTest(expected), self.assertRaisesRegex(SystemExit, expected):
                self.read_ledger(*args)

    def test_an_edited_ledger_still_passes_the_structure_check(self):
        self.run_ledger("row", "--table", "queue-ready",
                        "--id", "Q01", cells=QUEUE_ROW)
        self.run_ledger("move", "--id", "Q01", "--to", "completed")
        self.run_ledger("row", "--table", "sources", "--id", "S01",
                        cells=["documentation", "[doc][doc]", "today", "Full", "none", ""])
        self.run_ledger("link", "--key", "doc", "--url",
                        "https://example.com/doc")
        self.assertEqual(check_report.check_ledger(self.path), ([], []))


if __name__ == "__main__":
    unittest.main()
