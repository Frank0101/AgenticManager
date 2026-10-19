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
from investigation_fixture import INVESTIGATION, temp_output  # noqa: E402

QUEUE_ROW = ["Request", "Read the code", "Code", "None", "High", ""]


class LedgerTest(unittest.TestCase):
    def setUp(self):
        self.folder = temp_output(self)
        init_investigation.init("Acme-Search", today=date(2026, 10, 5))
        self.path = Path(self.folder) / INVESTIGATION / "ledger.md"
        # The commands are tested on an empty ledger; init's own first actions
        # are tested in test_init_investigation.py.
        self.path.write_text(init_investigation.ledger_skeleton(
            "Acme-Search"), encoding="utf-8")

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

    def plain(self):
        """The ledger without the anchors and ID links the script adds, for
        tests about something else."""
        return re.sub(r"\[([SQFCDG]\d+)\]\(#[a-z]+\d+\)", r"\1", re.sub(r'<a id="[^"]+"></a>', "", self.text()))

    def rows(self, heading):
        """The first column of the data rows of the first table under `heading`."""
        text = self.plain()
        start = text.index(heading)
        end = text.find("\n#", start + 1)
        table = [line for line in text[start:end if end >
                                       0 else None].splitlines() if line.startswith("|")]
        return [line.split(" | ")[0].strip("| ") for line in table[2:]]

    def records(self, *ids):
        """Write a minimal record for each of `ids`, in one batch, so a test can
        cite it: the ledger refuses a citation of a record it doesn't hold."""
        cells = {"S": ("sources", ["source_control", "[x](https://example.com/x)", "abc", "Read.", "None",
                                   "Implementation"]),
                 "D": ("decisions", ["d", "b", "c", "d", "e"]),
                 "G": ("gaps", ["g", "b", "c", "No access (x)", "e", "f", "Implementation"]),
                 "Q": ("queue-ready", QUEUE_ROW)}
        items = [{"finding": {"title": f"Finding {ident}", "Claim": "A claim.", "Kind": "observed implementation",
                              "Evidence": "the code", "Validation and limits": "read"}, "id": ident}
                 if ident.startswith("F") else {"table": cells[ident[0]][0], "id": ident, "cells": cells[ident[0]][1]}
                 for ident in ids]
        self.run_ledger("batch", cells=items)

    def test_next_id_per_kind(self):
        self.assertEqual(self.run_ledger(
            "next-id", "--kind", "S")["id"], "S01")
        self.run_ledger("row", "--table", "sources", "--id",
                        "S01", cells=["a", "[x][x]", "c", "d", "e", "Architecture"])
        self.run_ledger("row", "--table", "sources", "--id",
                        "S02", cells=["a", "[x][x]", "c", "d", "e", ""])
        self.run_ledger("row", "--table", "gaps", "--id",
                        "G01", cells=["a", "b", "c", "No access", "d", "e", "Delivery"])
        for kind, expected in (("S", "S03"), ("G", "G02"), ("D", "D01"), ("Q", "Q01"), ("C", "C01"), ("F", "F01")):
            with self.subTest(kind):
                self.assertEqual(self.run_ledger(
                    "next-id", "--kind", kind)["id"], expected)

    def test_rows_are_added_replaced_and_sorted(self):
        for row_id, kind in (("S10", "x"), ("S02", "y"), ("S10", "z")):
            self.run_ledger("row", "--table", "sources", "--id",
                            row_id, cells=[kind, "[r][r]", "v", "m", "l", ""])
        self.assertEqual(
            self.rows("## Revisions and source register"), ["S02", "S10"])
        self.assertIn("| S10 | z |", self.plain())
        self.assertNotIn("| S10 | x |", self.plain())

    def test_a_table_is_created_where_there_was_a_placeholder(self):
        self.assertIn("## Open decisions\n\nNone yet.", self.text())
        self.run_ledger("row", "--table", "decisions", "--id",
                        "D01", cells=["a", "b", "c", "d", "e"])
        text = self.text()
        self.assertIn("| ID | Decision |", text)
        self.assertNotIn("## Open decisions\n\nNone yet.", text)
        self.records("S01")
        self.run_ledger("row", "--table", "file-coverage",
                        cells=["S01", "[a](https://example.com/a)", "Full"])
        self.run_ledger("row", "--table", "file-coverage",
                        cells=["S01", "[b](https://example.com/b)", "Full"])
        self.assertEqual(
            self.rows("### File reading coverage"), ["S01", "S01"])

    def test_a_coverage_row_is_replaced_by_text_it_contains(self):
        self.records("S07")
        for name in ("server.py", "routes.py"):
            self.run_ledger("row", "--table", "file-coverage",
                            cells=["S07", f"[{name}](https://example.com/{name})", "partial: lines 1-10"])
        self.run_ledger("row", "--table", "file-coverage", "--match", "server.py",
                        cells=["S07", "[server.py](https://example.com/server.py)", "full"])
        rows = self.text().split("### File reading coverage")[
            1].split("\n\n")[1]
        self.assertLess(rows.index("server.py"), rows.index("routes.py"))
        self.assertIn("[server.py][server-py] | full |", rows)
        self.assertNotIn("lines 1-10 |\n| S07 | [server.py]", rows)
        cases = [(["--table", "file-coverage", "--match", "S07"], "matches 2 rows"),
                 (["--table", "file-coverage", "--match", "zzz"],
                  "no file-coverage row"),
                 (["--table", "decisions", "--id", "D01", "--match", "x"], "replaced by --id")]
        for args, expected in cases:
            with self.subTest(expected), self.assertRaisesRegex(SystemExit, expected):
                self.run_ledger("row", *args, cells=["S07", "[x](https://example.com/x)", "full"] if "file-coverage" in args
                                else ["a", "b", "c", "d", "e"])

    BATCH = [
        {"table": "sources", "id": "S01", "cells": ["source_control", "[api](https://example.com/api)", "abc",
                                                    "Read.", "Superseded by S02", "Implementation"]},
        {"table": "file-coverage",
            "cells": ["S01", "[server.py](https://example.com/server.py)", "full"]},
        {"finding": {"title": "Search reads the index", "Claim": "Search reads the index.",
                     "Kind": "observed implementation", "Evidence": "S01", "Validation and limits": "code read"}},
    ]

    def test_batch_writes_rows_and_findings_in_one_call(self):
        self.records("S02")
        result = self.run_ledger("batch", cells=self.BATCH)
        self.assertEqual(result["written"], ["S01", "file-coverage", "F01"])
        self.assertEqual(
            self.rows("## Revisions and source register"), ["S01", "S02"])
        self.assertEqual(self.rows("### File reading coverage"), ["S01"])
        self.assertIn("### F01 — Search reads the index", self.text())
        # A source's Findings come from the findings written in the same batch.
        self.assertIn("| Read. Findings: F01. |", self.plain())

    def test_a_batch_with_a_bad_item_writes_nothing(self):
        before = self.text()
        good = self.BATCH[0]
        cases = [("an unknown table", {"table": "notes", "cells": []}, "table is one of"),
                 ("a row and a finding at once", {
                  "table": "sources", "finding": {}}, "each item is a row"),
                 ("an unknown key", {"table": "file-coverage",
                  "cells": [], "note": "x"}, "unknown keys note"),
                 ("a depth not allowed", {"table": "file-coverage",
                                          "cells": ["S01", "[a](https://example.com/a)", "skimmed"]}, "Depth 'skimmed'"),
                 ("a finding missing fields", {
                  "finding": {"title": "T"}}, "missing Claim"),
                 ("a row needing an ID", {"table": "gaps", "cells": ["a"]}, "gaps needs --id")]
        for name, bad, expected in cases:
            with self.subTest(name), self.assertRaisesRegex(SystemExit, f"item 2: (.|\\n)*{expected}(.|\\n)*nothing was written"):
                self.run_ledger("batch", cells=[good, bad])
            self.assertEqual(self.text(), before)
        for items in ([], {"table": "sources"}):
            with self.subTest(items=items), self.assertRaisesRegex(SystemExit, "non-empty JSON list"):
                self.run_ledger("batch", cells=items)

    def test_the_brief_holds_what_the_report_reads(self):
        self.records("S02")
        self.run_ledger("batch", cells=self.BATCH + [
            {"table": "components", "id": "C01", "cells": ["Search API (service)", "Serves search", "[search](https://example.com/search)",
                                                           "⬜ Unverified", "Manifest only", "Web → Search API", "F01", "Unchanged"]},
            {"table": "decisions", "id": "D01", "cells": [
                "Which index", "Unresolved", "Two options", "Design doc", "Owner not named"]},
            {"table": "queue-ready", "id": "Q01", "cells": QUEUE_ROW}])
        self.run_ledger("text", "--section",
                        "Boundary, method and access", text="Search only.")
        brief = self.read_ledger("brief")
        kept = ["## Boundary, method and access\n\nSearch only.", "S01: [api](https://example.com/api) (Superseded by S02)",
                "### F01 — Search reads the index", "- **Claim:** Search reads the index.", "- **Evidence:** S01",
                "C01 | Search API (service) | Serves search | search | ⬜ Unverified", "D01 | Which index",
                "## Evidence gaps\n\nNone."]
        # The queue, the coverage, the sources' notes and the link definitions are for research and review.
        left_out = ["Read the code", "server.py", "Read.",
                    "[api]:", "## Research action queue", "<a id"]
        for text in kept:
            with self.subTest(kept=text):
                self.assertIn(text, brief)
        for text in left_out:
            with self.subTest(left_out=text):
                self.assertNotIn(text, brief)

    def test_text_read_as_written_writes_back_unchanged(self):
        # Stored text has IDs and links rewritten; show --raw and --section give
        # it back as the writing commands read it, so writing it back changes nothing.
        self.records("S01")
        self.run_ledger("row", "--table", "queue-ready", "--id", "Q01",
                        cells=["Request", "Read [the doc](https://example.com/doc)", "Code", "None", "High", ""])
        fields = {"title": "Docs", "Claim": "See [the doc](https://example.com/doc), per Q01.",
                  "Kind": "observed implementation", "Evidence": "S01", "Validation and limits": "read"}
        self.run_ledger("finding", cells=fields)
        self.run_ledger("text", "--section", "Boundary, method and access",
                        text="Next: Q01, then [the doc](https://example.com/doc).")
        self.assertIn("[the doc][the-doc]", self.text())
        before = self.text()
        finding = json.loads(self.read_ledger("show", "--raw", "--id", "F01"))
        self.assertEqual(finding, fields)
        self.run_ledger("finding", "--id", "F01", cells=finding)
        row = json.loads(self.read_ledger("show", "--raw", "--id", "Q01"))
        self.assertEqual(row[1], "Read [the doc](https://example.com/doc)")
        self.run_ledger("row", "--table", "queue-ready",
                        "--id", "Q01", cells=row)
        section = self.read_ledger(
            "show", "--section", "Boundary, method and access").strip()
        self.assertEqual(
            section, "Next: Q01, then [the doc](https://example.com/doc).")
        self.run_ledger("text", "--section",
                        "Boundary, method and access", text=section)
        self.assertEqual(self.text(), before)
        self.assertEqual(json.loads(self.read_ledger(
            "show", "--raw", "--table", "queue-ready")), row)

    def test_a_pipe_in_a_cell_stays_in_its_cell(self):
        # A search query such as grep -E "a|b" is written escaped, so the row
        # keeps its columns, and it reads back as written.
        cells = ["source_control", '`grep -rE "otlp|mlflow" services`',
                 "abc1234", "m", "None", ""]
        self.run_ledger("row", "--table", "sources",
                        "--id", "S01", cells=cells)
        self.assertIn('`grep -rE "otlp\\|mlflow" services`', self.text())
        self.assertEqual(json.loads(self.read_ledger(
            "show", "--raw", "--id", "S01")), cells)

    def test_rows_that_break_a_rule_are_refused(self):
        # Wrong columns or IDs, and the rules check_report.py applies at
        # handover, refused on write: nothing is written.
        cases = [(["row", "--table", "sources", "--id", "S01"], ["too few"], "columns"),
                 (["row", "--table", "sources", "--id", "Q01"],
                  ["a", "b", "c", "d", "e"], "IDs start with S"),
                 (["row", "--table", "sources"], ["a"], "needs --id"),
                 (["row", "--table", "file-coverage",
                  "--id", "S01"], ["a"], "has no IDs"),
                 (["row", "--table", "sources", "--id", "S01"], ["a", "acme/api", "c", "d", "e", ""],
                  "S01: link the Exact reference"),
                 (["row", "--table", "file-coverage"], ["S01", "server.py", "full"],
                  "for S01: link the material read"),
                 (["row", "--table", "gaps", "--id", "G01"], ["a", "b", "c", "Not started", "d", "e", "Delivery"],
                  "G01 is blocked by 'Not started'"),
                 (["row", "--table", "gaps", "--id", "G01"], ["a", "b", "c", "Waiting on decision", "d", "e", ""],
                  "G01 waits on a decision but names none"),
                 (["row", "--table", "decisions", "--id", "D01"], ["See `app.py`", "b", "c", "d", "e"],
                  "references in backticks without a link: `app.py`"),
                 (["row", "--table", "components", "--id", "C01"],
                  ["n", "r", "p", "Done", "d", "c", "F01", "next"], "Status starts with"),
                 (["row", "--table", "file-coverage"],
                  ["S01", "[a](https://example.com/a)", "skimmed"], "Depth 'skimmed'"),
                 (["row", "--table", "queue-completed", "--id", "Q01"],
                  QUEUE_ROW[:-1] + [""], "names the findings"),
                 (["row", "--table", "queue-completed", "--id", "Q01"],
                  QUEUE_ROW[:-1] + ["Out of scope"], "names the findings")]
        before = self.text()
        for args, cells, expected in cases:
            with self.subTest(expected), self.assertRaisesRegex(SystemExit, expected):
                self.run_ledger(*args, cells=cells)
        self.assertEqual(self.text(), before)

    def test_move_a_queue_row_between_subsections(self):
        self.records("F01")
        self.run_ledger("row", "--table", "queue-ready",
                        "--id", "Q01", cells=QUEUE_ROW)
        self.run_ledger("row", "--table", "queue-ready",
                        "--id", "Q02", cells=QUEUE_ROW)
        self.run_ledger("move", "--id", "Q01", "--to", "completed", "--set",
                        "Outcome / finding IDs=F01")
        self.assertEqual(self.rows("### Ready"), ["Q02"])
        self.assertEqual(self.rows("### Completed"), ["Q01"])
        self.assertIn("| High | [F01](#f01) |", self.text())
        self.run_ledger("move", "--id", "Q02", "--to", "blocked")
        self.assertEqual(self.rows("### Ready"), [])
        self.assertIn("### Ready", self.text())
        ready = self.text().split(
            "### Ready")[1].split("### Blocked")[0]
        self.assertIn("None.", ready)
        blocked = self.text().split("### Blocked")[1].split("### Completed")[0]
        self.assertNotIn("None.", blocked)
        with self.assertRaisesRegex(SystemExit, "no queue row Q09"):
            self.run_ledger("move", "--id", "Q09", "--to", "completed")
        with self.assertRaisesRegex(SystemExit, "no 'Nope' to set"):
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
        # A key is stored in lower case, so another case replaces or removes the same link.
        self.run_ledger("link", "--key", "B-Doc",
                        "--url", "https://example.com/b3")
        links = self.text().split("## Links")[1]
        self.assertEqual([line for line in links.splitlines() if line.startswith("[")],
                         ["[a-doc]: https://example.com/a", "[b-doc]: https://example.com/b3"])
        self.run_ledger("unlink", "--key", "A-DOC")
        self.assertNotIn("[a-doc]:", self.text())
        with self.assertRaisesRegex(SystemExit, "--key is"):
            self.run_ledger("link", "--key", "bad key",
                            "--url", "https://example.com")

    def finding(self, title, evidence="S01: [doc][doc]", ident=None):
        fields = {"title": title, "Claim": "A claim.", "Kind": "observed implementation", "Evidence": evidence,
                  "Validation and limits": "code read; high"}
        args = ["finding"] + (["--id", ident] if ident else [])
        return self.run_ledger(*args, cells=fields)["id"]

    def test_a_long_claim_is_flagged_when_written(self):
        self.records("S01")
        fields = {"title": "Long", "Kind": "observed implementation", "Evidence": "S01",
                  "Validation and limits": "code read"}
        for words, warned in ((150, False), (151, True)):
            with self.subTest(words=words):
                result = self.run_ledger(
                    "finding", cells={**fields, "Claim": "word " * words})
                self.assertEqual(any("split it into findings of one claim each" in w
                                     for w in result.get("warnings", [])), warned, result)

    def test_findings_are_added_replaced_sorted_and_checked(self):
        self.records("S01")
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
        self.records("F21")
        self.run_ledger("finding", "--id", "F20", cells={
            "title": "Optional line", "Claim": "c", "Kind": "k", "Evidence": "e", "Validation and limits": "v",
            "Supersedes or contradicted by": "Superseded by F21."})
        self.assertIn(
            "- **Supersedes or contradicted by:** Superseded by [F21](#f21).", self.text())
        for fields, expected in (({"title": "x"}, "missing Claim"),
                                 ({**{"title": "x", "Claim": "c", "Kind": "k", "Evidence": "e",
                                      "Validation and limits": "v"}, "Extra": "y"}, "unknown Extra")):
            with self.subTest(expected), self.assertRaisesRegex(SystemExit, expected):
                self.run_ledger("finding", cells=fields)

    def test_rows_findings_and_links_are_removed(self):
        for row_id in ("S01", "S02"):
            self.run_ledger("row", "--table", "sources", "--id",
                            row_id, cells=["a", "[x][x]", "c", "d", "e", ""])
        self.run_ledger("remove", "--table", "sources", "--id", "S01")
        self.assertEqual(
            self.rows("## Revisions and source register"), ["S02"])
        self.run_ledger("remove", "--table", "sources", "--id", "S02")
        self.assertIn("None.", self.text().split(
            "## Revisions and source register")[1].split("###")[0])
        self.records("S01", "S02", "S07")
        self.run_ledger("row", "--table", "file-coverage",
                        cells=["S01", "[a][a]", "Full"])
        self.run_ledger("row", "--table", "file-coverage",
                        cells=["S02", "[b][b]", "Full"])
        self.run_ledger("remove", "--table", "file-coverage", "--match", "[a]")
        self.assertEqual(self.rows("### File reading coverage"), ["S02"])
        # Rows of one source are told apart by the rest of the row, such as the file.
        for name in ("server.py", "routes.py"):
            self.run_ledger("row", "--table", "file-coverage",
                            cells=["S07", f"[{name}](https://example.com/{name})", "full"])
        with self.assertRaisesRegex(SystemExit, "matches 2 rows"):
            self.run_ledger("remove", "--table",
                            "file-coverage", "--match", "S07")
        self.run_ledger("remove", "--table", "file-coverage",
                        "--match", "routes.py")
        self.assertIn("[server.py]", self.text())
        self.assertNotIn("[routes.py]", self.text().split("## Links")[0])
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
        text = self.plain()
        self.assertIn("| Read. Findings: F01. |", text)
        self.assertIn("| Read. Findings: F01, F02. |", text)
        self.assertEqual(text.count("Findings: F01."), 1)
        self.run_ledger("remove", "--table", "findings", "--id", "F01")
        self.run_ledger("sync-sources")
        self.assertNotIn("Findings: F01.", self.plain())
        self.assertEqual(check_report.source_finding_problems(self.text()), [])
        # Adding a finding keeps the sources in step without a separate command.
        self.finding("Three", evidence="S03: [doc][doc]")
        self.assertEqual(check_report.source_finding_problems(self.text()), [])
        self.assertIn("Findings: F03.", self.plain())

    def test_removing_a_record_still_cited_is_refused(self):
        # Removing it would leave a citation of a record that isn't there.
        self.run_ledger("row", "--table", "sources", "--id", "S01",
                        cells=["a", "[x][x]", "d", "Read.", "e", ""])
        self.finding("One", evidence="S01: [doc][doc]")
        self.run_ledger("row", "--table", "components", "--id", "C01",
                        cells=["n", "r", "p", "⬜ Unverified", "d", "c", "F01", "next"])
        self.run_ledger("row", "--table", "sources", "--id", "S02",
                        cells=["a", "[y][y]", "d", "Read.", "e", ""])
        self.run_ledger("text", "--section", "Boundary, method and access",
                        text="Searched as S02 says.")
        before = self.text()
        cases = [("a finding", "findings", "F01", "F01 is still cited by C01: change those first"),
                 ("a row", "sources", "S01",
                  "S01 is still cited by F01: change those first"),
                 ("outside the records", "sources", "S02",
                  "S02 is still cited by the Boundary, method and access section")]
        for name, table, ident, expected in cases:
            with self.subTest(name):
                with self.assertRaisesRegex(SystemExit, expected):
                    self.run_ledger("remove", "--table", table, "--id", ident)
                self.assertEqual(self.text(), before)
        self.run_ledger("remove", "--table", "components", "--id", "C01")
        self.run_ledger("remove", "--table", "findings", "--id", "F01")
        self.assertNotIn("Findings: F01.", self.text())

    def test_inline_links_become_reference_links(self):
        # A URL keeps one key, however many times it is written inline.
        self.run_ledger("row", "--table", "sources", "--id", "S01", cells=[
            "a", "[Spec doc](https://example.com/spec)", "d",
            "Read [Spec doc](https://example.com/spec) and [Other](https://example.com/spec).", "e", ""])
        self.run_ledger("row", "--table", "sources", "--id", "S02", cells=[
            "a", "[Spec](https://example.com/other)", "d", "Read.", "e", ""])
        text = self.text()
        self.assertIn("| [Spec doc][spec-doc] |", text)
        self.assertIn("[Other][spec-doc]", text)
        self.assertIn("| [Spec][spec] |", text)
        self.assertEqual([line for line in text.split("## Links")[1].splitlines() if line.startswith("[")], [
            "[spec]: https://example.com/other", "[spec-doc]: https://example.com/spec"])
        # Another URL under a key already taken gets the next free one.
        self.run_ledger("text", "--section", "Boundary, method and access",
                        text="See [Spec](https://example.com/third).")
        self.assertIn("See [Spec][spec-2].", self.text())

    def test_ticket_keys_link_to_the_jira_site_that_has_their_project(self):
        # A key-shaped word whose project the site doesn't have, such as
        # SHA-256, is no ticket, so it stays as code; each project is asked once.
        asked = []

        class Site:
            base_url = "https://acme.atlassian.net"

            def project(self, key):
                asked.append(key)
                if key != "PROJ":
                    raise SystemExit(f"no project {key}")
        ledger.SITES.clear()
        self.addCleanup(ledger.SITES.clear)
        with mock.patch.object(ledger, "JiraClient", Site), mock.patch.object(ledger, "is_enabled", return_value=True):
            self.run_ledger("text", "--section", "Reflection",
                            text="PROJ-7 and PROJ-8 use SHA-256.")
        self.assertIn(
            "[PROJ-7][proj-7] and [PROJ-8][proj-8] use `SHA-256`.", self.text())
        self.assertIn(
            "[proj-7]: https://acme.atlassian.net/browse/PROJ-7", self.text())
        self.assertEqual(asked, ["PROJ", "SHA"])

    def test_one_change_per_call(self):
        # --set changes named cells or fields of what is already written, and
        # --replace one exact text of a section: what isn't named stays as it was.
        self.records("S02")
        self.run_ledger("batch", cells=self.BATCH + [
            {"table": "components", "id": "C01", "cells": ["Search API (service)", "Serves search",
                                                           "[search](https://example.com/search)", "⬜ Unverified",
                                                           "Manifest only", "Web → Search API", "F01", "Unchanged"]}])
        self.run_ledger("row", "--table", "components", "--id", "C01",
                        "--set", "Deployment evidence and how much was read=Declared in gb-production",
                        "--set", "current → next steps=Retired next")
        component = self.read_ledger("show", "--id", "C01")
        for cell in ("Repository, paths, revision: [search][search]", "Status: ⬜ Unverified",
                     "Deployment evidence and how much was read: Declared in gb-production",
                     "Current → next steps: Retired next", "Evidence: [F01](#f01)"):
            with self.subTest(cell):
                self.assertIn(cell, component)
        self.run_ledger("row", "--table", "file-coverage",
                        "--match", "server.py", "--set", "Depth=full")
        self.assertIn("| full |", self.text().split(
            "### File reading coverage")[1].split("##")[0])
        self.run_ledger("finding", "--id", "F01", "--set",
                        "Validation and limits=Routes read in full.")
        finding = self.read_ledger("show", "--id", "F01")
        self.assertIn(
            "- **Validation and limits:** Routes read in full.", finding)
        self.assertIn("- **Claim:** Search reads the index.", finding)
        self.run_ledger("text", "--section", "Reflection",
                        text="The cache was assumed.\nThe code showed none.\n")
        self.run_ledger("text", "--section", "Reflection",
                        "--replace", "assumed", "assumed by the design")
        self.assertIn(
            "## Reflection\n\nThe cache was assumed by the design.\nThe code showed none.", self.text())
        # name: (arguments, expected refusal)
        cases = [("an unknown column", ("row", "--table", "components", "--id", "C01", "--set", "Colour=red"),
                  "no 'Colour' to set"),
                 ("a row not written", ("row", "--table", "components", "--id", "C09", "--set", "Status=x"),
                  "no components row C09"),
                 ("a finding with no --id", ("finding", "--set",
                  "Kind=inference"), "needs the finding's --id"),
                 ("text not there", ("text", "--section", "Reflection",
                  "--replace", "absent", "x"), "0 times"),
                 ("text there twice", ("text", "--section", "Reflection", "--replace", "The", "A"), "2 times")]
        for name, arguments, expected in cases:
            before = self.text()
            with self.subTest(name), self.assertRaisesRegex(SystemExit, expected):
                self.run_ledger(*arguments)
            self.assertEqual(self.text(), before)

    def test_text_sections_are_replaced(self):
        self.run_ledger("text", "--section", "Boundary, method and access",
                        text="Scope.\n\nNext: read it.\n")
        self.assertIn(
            "## Boundary, method and access\n\nScope.\n\nNext: read it.\n\n## Revisions and source register", self.text())
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
                                     ("S03", "reported context", "")):
            self.run_ledger("row", "--table", "sources", "--id", row_id,
                            cells=[group, "[x][x]", "d", "Read.", "e", areas])
        self.run_ledger("row", "--table", "gaps", "--id", "G01",
                        cells=["a", "b", "c", "No access", "d", "e", "Architecture"])
        status = self.read_ledger("status")
        self.assertIn(
            "Architecture: 1 / 0 / 1, 1 gaps  (none from tracker)", status)
        self.assertIn(
            "Delivery: 0 / 0 / 1, 0 gaps  (none from code, tracker)", status)
        self.assertNotIn("sources with no Areas", status)
        self.run_ledger("row", "--table", "sources", "--id", "S04",
                        cells=["workflow: ticket", "[x][x]", "d", "Read.", "e", ""])
        self.assertIn("sources with no Areas: S04", self.read_ledger("status"))
        with self.assertRaisesRegex(SystemExit, "Areas must be some of.*not Billing"):
            self.run_ledger("row", "--table", "sources", "--id", "S05",
                            cells=["workflow", "[x][x]", "d", "Read.", "e", "Delivery, Billing"])

    def test_reading_commands_show_find_and_summarise(self):
        status = self.read_ledger("status")
        self.assertIn(
            "queue: 0 ready, 0 in-progress, 0 blocked, 0 completed", status)
        self.assertIn(
            "Architecture: 0 / 0 / 0, 0 gaps  (none from code, tracker, documentation)", status)
        self.assertIn(
            "not started: Boundary, method and access", status)
        self.run_ledger("row", "--table", "queue-ready",
                        "--id", "Q01", cells=QUEUE_ROW)
        self.run_ledger("row", "--table", "sources", "--id", "S01",
                        cells=["documentation", "[the search page][doc]", "today", "Read.", "none", "Architecture, Delivery"])
        self.run_ledger("link", "--key", "doc", "--url",
                        "https://example.com/search-page")
        self.finding("Search is slow", evidence="S01: [doc][doc]")
        status = self.read_ledger("status")
        self.assertIn(
            "queue: 1 ready, 0 in-progress, 0 blocked, 0 completed", status)
        self.assertIn("  ready Q01 [High] Read the code", status)
        self.assertIn("1 findings, 1 sources", status)
        self.assertIn("Architecture: 0 / 0 / 1", status)
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
        for args, expected in ((["show"], "takes one of --id, --table or --section"), (["show", "--id", "F09"], "no finding F09"),
                               (["show", "--id", "Z9"], "no record Z9")):
            with self.subTest(expected), self.assertRaisesRegex(SystemExit, expected):
                self.read_ledger(*args)

    def test_an_edited_ledger_still_passes_the_structure_check(self):
        self.run_ledger("link", "--key", "doc", "--url",
                        "https://example.com/doc")
        self.run_ledger("row", "--table", "sources", "--id", "S01",
                        cells=["documentation", "[doc][doc]", "today", "Full", "none", ""])
        self.finding("Answer", evidence="S01: [doc][doc]")
        self.run_ledger("row", "--table", "queue-ready",
                        "--id", "Q01", cells=QUEUE_ROW)
        self.run_ledger("move", "--id", "Q01", "--to", "completed",
                        "--set", "Outcome / finding IDs=F01")
        self.assertEqual(check_report.check_ledger(self.path), ([], []))

    def test_tickets_and_pull_requests_are_linked_on_write(self):
        # A ticket links once the ledger links one of its project, else it is code;
        # a pull request links from a page of its host, linked once.
        self.run_ledger("row", "--table", "sources", "--id", "S01", cells=[
            "workflow", "[PROJ-1](https://acme.example/browse/PROJ-1)", "d", "Read.", "e", ""])
        self.run_ledger("row", "--table", "sources", "--id", "S02", cells=[
            "source_control", "[api](https://git.example/acme/api/tree/abc)", "d", "Read.", "e", ""])
        cases = [("PROJ-7 is open", "[PROJ-7][proj-7] is open",
                  "[proj-7]: https://acme.example/browse/PROJ-7"),
                 ("OPS-1 and SHA-256", "`OPS-1` and `SHA-256`", None),
                 ("acme/api#12 merged", "[acme/api#12][acme-api-12] merged",
                  "[acme-api-12]: https://git.example/acme/api/pull/12"),
                 ("other/repo#3 open", "[other/repo#3][other-repo-3] open",
                  "[other-repo-3]: https://git.example/other/repo/pull/3"),
                 ("`PROJ-8` in code", "[PROJ-8][proj-8] in code", None)]
        for text, written, definition in cases:
            with self.subTest(text):
                self.run_ledger("text", "--section",
                                "Boundary, method and access", text=text)
                self.assertIn(f"\n{written}\n", self.text())
                if definition:
                    self.assertIn(definition, self.text())
        self.finding("PROJ-9 title", evidence="S01 and PROJ-9")
        self.assertIn("### F01 — PROJ-9 title", self.text())
        self.assertIn("S01 and [PROJ-9][proj-9]", self.plain())
        before = self.text()
        with self.assertRaisesRegex(SystemExit, "#12: write a pull request as owner/repo#123"):
            self.run_ledger("text", "--section",
                            "Boundary, method and access", text="#12 merged")
        self.assertEqual(self.text(), before)

    def test_text_and_search_queries_are_checked_as_they_are_written(self):
        # A text section is held to the backtick rule rows are.
        before = self.text()
        with self.assertRaisesRegex(SystemExit, "backticks without a link: `app.py`"):
            self.run_ledger("text", "--section", "Boundary, method and access",
                            text="See `app.py`.")
        self.assertEqual(self.text(), before)
        # A search's query is the one backticked reference allowed without a link,
        # and is given as its own field, so no backtick is typed in a shell.
        self.run_ledger("row", "--table", "sources", "--id", "S01",
                        cells=["a", {"query": 'gh search code "acme api"'}, "c", "d", "e", ""])
        self.assertIn('| `gh search code "acme api"` |', self.text())
        for query in ({"query": ""}, {"query": "a `b`"}, {"query": "a", "url": "b"}):
            with self.subTest(query=query), self.assertRaisesRegex(SystemExit, "is {\"query\""):
                self.run_ledger("row", "--table", "sources", "--id",
                                "S02", cells=["a", query, "c", "d", "e", ""])

    def test_findings_resting_on_a_partial_read_are_listed(self):
        # A finding whose evidence names a file its source read only in part is
        # listed in status and the brief; one read in full, or of another
        # source, isn't.
        self.records("S01", "S02")
        self.run_ledger("batch", cells=[
            {"table": "file-coverage", "cells": ["S01", "[app/trace.ts](https://example.com/app/trace.ts)",
                                                 "partial: lines 1-80 of 328"]},
            {"table": "file-coverage",
                "cells": ["S01", "[app/server.ts](https://example.com/app/server.ts)", "full"]},
            {"table": "file-coverage", "cells": ["S02", "[app/trace.ts](https://example.com/b/app/trace.ts)",
                                                 "partial: lines 1-10"]}])
        for title, evidence in (("Traces unmasked", "S01: app/trace.ts lines 1-80"),
                                ("Routes", "S01: app/server.ts"), ("Elsewhere", "S02 notes")):
            self.finding(title, evidence=evidence)
        expected = ["findings resting on a partial read (read the rest, or say in the finding why it can't change it):",
                    "  F01: app/trace.ts (partial: lines 1-80 of 328)"]
        for output in (self.read_ledger("status"), self.read_ledger("brief")):
            with self.subTest(output=output.splitlines()[0]):
                found = output.splitlines()
                start = found.index(expected[0])
                self.assertEqual(found[start:start + 2], expected)
                self.assertNotIn("  F02:", output)
                self.assertNotIn("  F03:", output)

    def test_closing_an_action_lists_the_records_that_name_it(self):
        # What a record said while the action was open may need its answer.
        self.records("Q06", "S01")
        self.finding(
            "Config", evidence="S01; whether it is set is not established yet: Q06")
        self.run_ledger("row", "--table", "decisions", "--id",
                        "D01", cells=["a", "after Q06", "c", "d", "e"])
        result = self.run_ledger(
            "move", "--id", "Q06", "--to", "completed", "--set", "Outcome / finding IDs=F01")
        self.assertEqual(result["update_if_needed"], {"Q06": ["D01", "F01"]})
        # Moving it elsewhere, or closing one nothing names, lists nothing.
        self.records("Q07")
        self.assertNotIn("update_if_needed", self.run_ledger(
            "move", "--id", "Q07", "--to", "in-progress"))
        self.assertNotIn("update_if_needed", self.run_ledger("move", "--id", "Q07", "--to", "completed",
                                                             "--set", "Outcome / finding IDs=F01"))
        # An action may be written straight as completed, and is then in that part only.
        self.records("Q08")
        result = self.run_ledger("batch", cells=[{"table": "queue-completed", "id": "Q08",
                                                  "cells": QUEUE_ROW[:-1] + ["D01"]},
                                                 {"table": "gaps", "id": "G01", "cells": [
                                                     "a", "b", "c", "No access (x)", "Q08 was blocked", "f", ""]}])
        self.assertEqual(result["update_if_needed"], {"Q08": ["G01"]})
        self.assertEqual((self.rows("### Ready"), self.rows(
            "### Completed")), ([], ["Q06", "Q07", "Q08"]))

    def test_a_citation_names_a_record_the_ledger_holds(self):
        # A record citing one the ledger doesn't hold is refused, writing
        # nothing; records citing each other go in one batch, in any order.
        before = self.text()
        with self.assertRaisesRegex(SystemExit, "cites D01, S02, which the ledger doesn't hold"):
            self.run_ledger("row", "--table", "gaps", "--id", "G01",
                            cells=["a", "b", "c", "Waiting on decision (D01)", "S02", "e", ""])
        self.assertEqual(self.text(), before)
        self.run_ledger("batch", cells=[
            {"table": "gaps", "id": "G01", "cells": [
                "a", "b", "c", "Waiting on decision (D01)", "S02", "e", ""]},
            {"table": "decisions", "id": "D01",
                "cells": ["a", "G01", "c", "d", "e"]},
            {"table": "sources", "id": "S02", "cells": ["a", "[x](https://example.com/x)", "c", "d", "e", ""]}])
        self.assertEqual(self.rows("## Evidence gaps"), ["G01"])

    def test_a_ticket_written_as_code_is_linked_once_its_project_is(self):
        self.run_ledger("text", "--section", "Boundary, method and access",
                        text="PROJ-7 is open")
        self.assertIn("\n`PROJ-7` is open\n", self.text())
        self.run_ledger("row", "--table", "sources", "--id", "S01", cells=[
            "workflow", "[PROJ-1](https://acme.example/browse/PROJ-1)", "d", "Read.", "e", ""])
        self.assertIn("\n[PROJ-7][proj-7] is open\n", self.text())
        self.assertIn(
            "[proj-7]: https://acme.example/browse/PROJ-7", self.text())

    def test_every_recorded_id_is_anchored_and_its_citations_link_to_it(self):
        self.run_ledger("row", "--table", "sources", "--id", "S01", cells=[
            "workflow", "[PROJ-1](https://acme.example/browse/PROJ-1)", "d", "Read.", "e", ""])
        self.run_ledger("row", "--table", "sources", "--id", "S02", cells=[
            "workflow", "[PROJ-2](https://acme.example/browse/PROJ-2)", "d", "Read.", "e", ""])
        self.finding("Search is slow", evidence="S01 and S02")
        text = self.text()
        self.assertIn('| <a id="s01"></a>S01 | workflow |', text)
        self.assertIn('### F01 — Search is slow\n\n<a id="f01"></a>\n', text)
        self.assertIn("- **Evidence:** [S01](#s01) and [S02](#s02)\n", text)
        self.assertIn("| Read. Findings: [F01](#f01). |", text)
        self.run_ledger("row", "--table", "file-coverage", cells=[
            "S01", "[server.py](https://example.com/server.py)", "full"])
        self.assertIn(
            "| [S01](#s01) | [server.py][server-py] | full |", self.text())
        self.run_ledger("text", "--section", "Boundary, method and access",
                        text="F01 rests on S01.")
        self.assertIn("\n[F01](#f01) rests on [S01](#s01).\n", self.text())
        # The next ID counts anchored rows, and reading commands show plain IDs.
        self.assertEqual(self.run_ledger(
            "next-id", "--kind", "S")["id"], "S03")
        self.assertIn("sources S01", self.read_ledger("show", "--id", "S01"))
        self.assertNotIn("<a id", self.read_ledger(
            "show", "--table", "sources"))
        self.assertEqual(check_report.check_ledger(self.path), ([], []))

    def test_a_completed_action_names_its_answer(self):
        self.records("F01", "F02", "G01", "D02")
        for outcome in ("F01, F02", "G01", "D02", "Rejected by the user: not needed, 2026-10-05"):
            with self.subTest(outcome):
                self.run_ledger("row", "--table", "queue-completed",
                                "--id", "Q01", cells=QUEUE_ROW[:-1] + [outcome])
        self.run_ledger("row", "--table", "queue-ready",
                        "--id", "Q02", cells=QUEUE_ROW)
        with self.assertRaisesRegex(SystemExit, "names the findings"):
            self.run_ledger("move", "--id", "Q02", "--to",
                            "completed", "--set", "Outcome / finding IDs=Out of scope")

    def test_a_code_status_needs_the_code_read(self):
        self.records("S01", "F01")
        tree = "https://git.example/acme/api/tree/abc/services/search"
        component = ["search", "r", f"[search]({tree})",
                     "🟩 Implemented", "d", "c", "F01", "next"]
        with self.assertRaisesRegex(SystemExit, "C01 links acme/api: services/search"):
            self.run_ledger("row", "--table", "components",
                            "--id", "C01", cells=component)
        for depth, path in (("README", "services/search/README.md"),
                            ("full", "services/other/main.py")):
            self.run_ledger("row", "--table", "file-coverage", cells=[
                "S01", f"[f](https://git.example/acme/api/blob/abc/{path})", depth])
            with self.subTest(depth), self.assertRaisesRegex(SystemExit, "needs its code read"):
                self.run_ledger("row", "--table", "components",
                                "--id", "C01", cells=component)
        self.run_ledger("row", "--table", "components", "--id", "C01",
                        cells=component[:3] + ["⬜ Unverified"] + component[4:])
        self.assertNotIn("components claiming code",
                         self.read_ledger("status"))
        self.run_ledger("row", "--table", "file-coverage", cells=[
            "S01", "[f](https://git.example/acme/api/blob/abc/services/search/src/routes.py)",
            "entrypoints and routes: lines 1-80"])
        self.run_ledger("row", "--table", "components",
                        "--id", "C01", cells=component)
        self.assertIn("| 🟩 Implemented |", self.text())

    def test_help_prints_columns_allowed_values_and_an_example(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            ledger.main(["help", "--table", "components"])
        text = out.getvalue()
        for expected in ("components: ID | Name and type", "--id C01, then 8 cells", "🟥 No implementation found",
                         "example: [\"search-api (service)\""):
            with self.subTest(expected):
                self.assertIn(expected, text)
        # Every command that writes shows a command to copy, its input in a here-document.
        for name in [*ledger.TABLES, *ledger.COMMAND_HELP]:
            with self.subTest(name):
                out = io.StringIO()
                with contextlib.redirect_stdout(out):
                    ledger.main(["help", "--table", name])
                self.assertIn("<scripts>/ledger.py", out.getvalue())
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            ledger.main(["help", "--table", "findings"])
        self.assertIn(
            "finding --investigation <investigation> <<'EOF'\n  {\n    \"title\":", out.getvalue())
        with self.assertRaisesRegex(SystemExit, "example:"):
            self.run_ledger("row", "--table", "gaps",
                            "--id", "G01", cells=["x"])

    def test_status_says_the_next_step(self):
        # Each phase opens when the one before is finished; a review round that
        # raises nothing is what moves the investigation from review to hand over.
        def step():
            return self.read_ledger("status").splitlines()[-1]
        self.records("F01", "F02")
        self.run_ledger("row", "--table", "queue-ready",
                        "--id", "Q01", cells=QUEUE_ROW)
        self.assertIn(
            "next: research: move a ready action to in-progress and work it, such as Q01", step())
        # What is under way is finished before anything new is started.
        self.run_ledger("move", "--id", "Q01", "--to", "in-progress")
        self.assertIn(
            "  in progress Q01 [High] Read the code", self.read_ledger("status"))
        self.assertIn(
            "next: research: finish the actions in progress before starting a ready one: Q01", step())
        self.run_ledger("move", "--id", "Q01", "--to", "completed",
                        "--set", "Outcome / finding IDs=F01")
        (Path(self.folder) / INVESTIGATION /
         "Acme-Search_Report.md").write_text("# r\n", encoding="utf-8")
        self.assertIn("next: review: nothing is left to research", step())
        # A Reflection alone does not count as the review.
        self.run_ledger("text", "--section", "Reflection", text="Done.")
        self.assertIn("next: review:", step())
        # The review raised an action: research again, then another round,
        # and hand over once a round raises nothing.
        self.run_ledger("row", "--table", "queue-ready",
                        "--id", "Q02", cells=QUEUE_ROW)
        self.assertEqual(self.run_ledger(
            "review", "--raised", "Q02")["id"], "Q03")
        self.assertIn(
            "next: research: move a ready action to in-progress and work it, such as Q02", step())
        self.run_ledger("move", "--id", "Q02", "--to", "completed",
                        "--set", "Outcome / finding IDs=F02")
        self.assertIn("next: review: nothing is left to research and the report is drafted, "
                      "so start another round", step())
        self.run_ledger("review", "--raised", "none")
        self.assertIn(
            "next: hand over: run check_report.py --handover", step())

    def test_after_three_rounds_the_user_decides_whether_to_go_on(self):
        def step():
            return self.read_ledger("status").splitlines()[-1]
        (Path(self.folder) / INVESTIGATION /
         "Acme-Search_Report.md").write_text("# r\n", encoding="utf-8")
        self.records("F01")
        for round_ in range(3):
            self.assertNotIn("Before another", step())
            action = f"Q{2 * round_ + 1:02d}"
            self.run_ledger("row", "--table", "queue-ready",
                            "--id", action, cells=QUEUE_ROW)
            self.run_ledger("review", "--raised", action)
            self.run_ledger("move", "--id", action, "--to", "completed",
                            "--set", "Outcome / finding IDs=F01")
        self.assertIn(
            "next: review: 3 rounds have run. Before another, show the user", step())
        with self.assertRaisesRegex(SystemExit, "what the user said"):
            self.run_ledger("review", "--stopped", " ")
        self.run_ledger("review", "--stopped", "wrap up now")
        self.assertIn(
            "| High | Stopped by the user: wrap up now |", self.text())
        self.assertIn("next: hand over:", step())

    def test_review_is_recorded_with_the_actions_it_raised(self):
        with self.assertRaisesRegex(SystemExit, "not in the queue: Q09"):
            self.run_ledger("review", "--raised", "Q09")
        self.run_ledger("row", "--table", "queue-ready",
                        "--id", "Q01", cells=QUEUE_ROW)
        self.run_ledger("review", "--raised", "Q01")
        self.assertIn("| Q02 | Independent review | Independent review of the ledger and report |"
                      " Subagent given the skill's brief | None | High | Raised Q01 |", self.plain())
        self.run_ledger("review", "--raised", "none")
        self.assertIn("| High | Nothing doable found |", self.text())
        # Its row closes on actions raised, not on findings.
        with self.assertRaisesRegex(SystemExit, "the review's outcome names the actions it raised"):
            self.run_ledger("row", "--table", "queue-completed", "--id", "Q09", cells=[
                "Independent review", "Independent review of the ledger and report", "s", "None", "High",
                "F01"])

    def test_input_can_come_from_a_file(self):
        folder = Path(self.folder)
        cells, fields, text = folder / "row.json", folder / \
            "finding.json", folder / "resume.txt"
        cells.write_text(json.dumps(["a", "[x](https://example.com/x)", "d", "It's \"quoted\".", "e", ""]),
                         encoding="utf-8")
        fields.write_text(json.dumps({"title": "From a file", "Claim": "c", "Kind": "k", "Evidence": "S01",
                                      "Validation and limits": "v"}), encoding="utf-8")
        text.write_text("Resumed from a file.\n", encoding="utf-8")
        self.run_ledger("row", "--table", "sources", "--id",
                        "S01", "--input", str(cells))
        self.run_ledger("finding", "--input", str(fields))
        self.run_ledger("text", "--section", "Boundary, method and access",
                        "--input", str(text))
        for expected in ('It\'s "quoted".', "### F01 — From a file", "Resumed from a file."):
            with self.subTest(expected):
                self.assertIn(expected, self.text())
        for path, expected in ((folder / "missing.json", "cannot read"), (text, "not valid JSON")):
            with self.subTest(expected), self.assertRaisesRegex(SystemExit, expected):
                self.run_ledger("row", "--table", "sources",
                                "--id", "S02", "--input", str(path))


if __name__ == "__main__":
    unittest.main()
