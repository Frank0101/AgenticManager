"""Unit tests for skills/agentic-manager-tech-investigation/scripts/ledger.py.
Run with: python3 tests/run.py agentic-manager-tech-investigation

Each test starts a new investigation in a temporary output folder, writes its
ledger through the module's functions, as a submission does, and reads the
ledger back.
"""

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
from common import ID_LETTERS, JiraError, citation as c  # noqa: E402
sys.path.insert(0, TEST_DIR)
from investigation_fixture import INVESTIGATION, temp_output  # noqa: E402

QUEUE_ROW = ["Request", "Read the code", "None", ""]


def source(reference: str = "[x](https://example.com/x)", kind="code", revision="abc", coverage="full",
           superseded="None"):
    """A source's cells, as put_row takes them."""
    return [kind, reference, revision, coverage, superseded]


class LedgerTest(unittest.TestCase):
    def setUp(self):
        self.folder = temp_output(self)
        init_investigation.init("Acme-Search", today=date(2026, 10, 5))
        self.path = Path(self.folder) / INVESTIGATION / "ledger.md"
        # The functions are tested on an empty ledger; init's own first
        # questions are tested in test_init_investigation.py.
        self.path.write_text(init_investigation.ledger_skeleton(
            "Acme-Search"), encoding="utf-8")

    def write(self, *rows):
        """Write each (table, ID, cells) of `rows`, then bring the ledger in
        step as a submission does; returns the questions it blocked. Nothing is
        saved if any write exits."""
        lines = self.lines()
        written = []
        for table, ident, cells in rows:
            written += ledger.put_row(lines, table, ident, cells)
        blocked = ledger.finish_write(lines, written)
        ledger.save(INVESTIGATION, lines)
        return blocked

    def change(self, action):
        """Run `action` on the ledger's lines and save them, as a submission
        does once it is checked."""
        lines = self.lines()
        result = action(lines)
        ledger.save(INVESTIGATION, lines)
        return result

    def lines(self):
        return self.text().split("\n")

    def text(self):
        return self.path.read_text(encoding="utf-8")

    def plain(self):
        """The ledger without the anchors and ID links the script adds, for
        tests about something else."""
        return re.sub(rf"\[([{ID_LETTERS}]\d+)\]\(#[a-z]+\d+\)", r"\1", re.sub(r'<a id="[^"]+"></a>', "", self.text()))

    def rows(self, heading):
        """The first column of the data rows of the first table under `heading`."""
        text = self.plain()
        start = text.index(heading)
        end = text.find("\n#", start + 1)
        table = [line for line in text[start:end if end >
                                       0 else None].splitlines() if line.startswith("|")]
        return [line.split(" | ")[0].strip("| ") for line in table[2:]]

    def records(self, *ids):
        """Write a minimal record for each of `ids`, so a test can cite it: the
        ledger refuses a citation of a record it doesn't hold. A finding cites
        itself, so it needs nothing else."""
        cells = {"S": lambda ident: ("sources", source(f"[page](https://example.com/{ident.lower()})")),
                 "F": lambda ident: ("findings", ["A claim.", ident, "read"]),
                 "D": lambda ident: ("decisions", ["d", "b", "c", "d", "e"]),
                 "G": lambda ident: ("gaps", ["g", "b", "c", "No access (x)", "e", "f"]),
                 "Q": lambda ident: ("queue-ready", QUEUE_ROW)}
        self.write(*((table, ident, row)
                   for ident in ids for table, row in [cells[ident[0]](ident)]))

    def prose(self, text):
        """Write `text` as a cell of its own, in the decision D09, as a
        submission does: linked, checked."""
        self.write(("decisions", "D09", [text, "b", "c", "d", "e"]))

    def test_next_id_per_kind(self):
        self.assertEqual(ledger.next_id(self.text(), "S"), "S01")
        self.records("S01", "S02", "G01")
        for kind, expected in (("S", "S03"), ("G", "G02"), ("D", "D01"), ("Q", "Q01"), ("C", "C01"), ("F", "F01")):
            with self.subTest(kind):
                self.assertEqual(ledger.next_id(self.text(), kind), expected)

    def test_rows_are_added_replaced_and_sorted(self):
        for row_id, kind in (("S10", "tracker"), ("S02", "documentation"), ("S10", "code")):
            self.write(("sources", row_id, source(
                f"[r](https://example.com/{kind})", kind)))
        self.assertEqual(self.rows("## Sources"), ["S02", "S10"])
        self.assertIn("| S10 | code |", self.plain())
        self.assertNotIn("| S10 | tracker |", self.plain())

    def test_a_table_is_created_where_there_was_a_placeholder(self):
        for section, table, ident, cells in (("Open decisions", "decisions", "D01", ["a", "b", "c", "d", "e"]),
                                             ("Sources", "sources", "S01", source())):
            with self.subTest(table):
                self.assertIn(f"## {section}\n\nNone yet.", self.text())
                self.write((table, ident, cells))
                self.assertNotIn(f"## {section}\n\nNone yet.", self.text())
                self.assertEqual(self.rows(f"## {section}"), [ident])
        # One blank line between the new table and the next heading.
        section = self.text().split("## Sources")[1].split("## Findings")[0]
        self.assertTrue(section.endswith("|\n\n"), repr(section))

    def test_a_source_read_again_is_found_by_its_reference_and_revision(self):
        self.write(("sources", "S01", source("[server.py](https://example.com/server.py)",
                                             coverage="partial: lines 1-80")),
                   ("sources", "S02", source(ledger.search_reference({"query": "gh search code retry"}),
                                             revision="2026-10-05", coverage="search hit")))
        # name: (a new source's cells, the source it repeats or None)
        cases = [("the same link under other words", source("[the server](https://example.com/server.py)"), "S01"),
                 ("the same query", source(
                     "`gh search code retry`", revision="2026-10-05"), "S02"),
                 ("another revision", source(
                     "[server.py](https://example.com/server.py)", revision="def"), None),
                 ("another file", source("[routes.py](https://example.com/routes.py)"), None)]
        for name, cells, expected in cases:
            with self.subTest(name):
                self.assertEqual(ledger.duplicate_of(self.lines(), ["S09", cells[0], cells[1], cells[2], cells[3],
                                                                    "None", cells[4]]), expected)

    def test_the_brief_holds_what_the_report_reads(self):
        self.records("S02")
        self.write(("sources", "S01", source("[api](https://example.com/api)", superseded="S02")),
                   ("findings", "F01", [
                    "Search reads the index.", "S01", "code read"]),
                   ("components", "C01", ["Search API (service)", "Serves search", "[search](https://example.com/search)",
                                          "🟨 Planned", "Manifest only", "F01", "Unchanged", "None"]),
                   ("decisions", "D01", [
                    "Which index", "Unresolved", "Two options", "Design doc", "Owner not named"]),
                   ("queue-ready", "Q01", QUEUE_ROW))
        self.write(("scope", "U01", ["Search", "include", c("Q01")]))
        brief = ledger.brief(self.lines())
        kept = ["## Scope boundaries\n\nID | Topic | Decision | Asked in\nU01 | Search | include | Q01", "S01: [api](https://example.com/api), abc; coverage: full; superseded by S02",
                "## Findings\n\nID | Claim | Sources | Limits\nF01 | Search reads the index. | S01 | code read",
                "C01 | Search API (service) | Serves search | search | 🟨 Planned", "D01 | Which index",
                "## Evidence gaps\n\nNone."]
        # The queue and the link definitions are for research and review.
        left_out = ["Read the code", "[api]:",
                    "## Research questions", "<a id"]
        for text in kept:
            with self.subTest(kept=text):
                self.assertIn(text, brief)
        for text in left_out:
            with self.subTest(left_out=text):
                self.assertNotIn(text, brief)

    def test_the_brief_lists_findings_resting_on_a_partial_read(self):
        self.write(("sources", "S01", source("[app/trace.ts](https://example.com/app/trace.ts)",
                                             coverage="partial: lines 1-80 of 328")),
                   ("sources", "S02", source(
                       "[app/server.ts](https://example.com/app/server.ts)")),
                   ("findings", "F01", [
                    "Traces are unmasked.", "S01 (lines 1-80)", "read"]),
                   ("findings", "F02", ["Routes.", "S02", "read"]))
        brief = ledger.brief(self.lines())
        self.assertIn(
            "  F01: S01 app/trace.ts (partial: lines 1-80 of 328)", brief)
        self.assertNotIn("  F02:", brief)

    def test_a_pipe_in_a_cell_stays_in_its_cell(self):
        # A search query such as grep -E "a|b" is written escaped, so the row
        # keeps its columns, and it reads back as written.
        cells = source('`grep -rE "otlp|mlflow" services`',
                       coverage="search hit")
        self.write(("sources", "S01", cells))
        self.assertIn('`grep -rE "otlp\\|mlflow" services`', self.text())
        row = ledger.table_rows(self.lines(), "sources")[0]
        self.assertEqual(ledger.as_written(self.lines(), row[2]), cells[1])

    def test_rows_that_break_a_rule_are_refused(self):
        # Wrong columns or IDs, and one case of each rule check_report.py
        # applies at handover, refused on write: nothing is written. The
        # rules' own cases are in test_common.py.
        cases = [("sources", "S01", ["too few"], "takes 5 texts"),
                 ("sources", "Q01", source(), "IDs are S and a number"),
                 ("sources", "S01", source("acme/api"), "S01: link the Reference"),
                 ("sources", "S01", source(kind="source_control"),
                  "S01: Kind starts with"),
                 ("sources", "S01", source(coverage="skimmed"),
                  "S01: Coverage starts with one of"),
                 ("sources", "S01", source(superseded="a newer page"),
                  "S01: Superseded by is None, or the one source"),
                 ("findings", "F01", ["A claim.", "the code",
                  "read"], "F01: Sources names the sources"),
                 ("gaps", "G01", ["a", "b", "c", "Not started",
                  "d", "e"], "G01 is blocked by 'Not started'"),
                 ("decisions", "D01", ["See `app.py`", "b", "c", "d", "e"],
                  "references in backticks without a link: `app.py`"),
                 ("components", "C01", [
                  "n", "r", "p", "Done", "d", "F01", "next", "None"], "Status starts with"),
                 ("queue-completed", "Q01",
                  QUEUE_ROW[:-1] + [""], "names the findings")]
        before = self.text()
        for table, ident, cells, expected in cases:
            with self.subTest(expected), self.assertRaisesRegex(SystemExit, expected):
                self.write((table, ident, cells))
        self.assertEqual(self.text(), before)

    def test_dependencies_block_and_never_circle(self):
        # Blocking a question blocks every question that needs it, which says
        # why by what it depends on; a circle could never be worked.
        def question(depends):
            return ["Request", "Read", depends, ""]
        self.records("F01", "G01")
        self.write(("queue-ready", "Q01", question("None")), ("queue-ready", "Q02", question("Q01")),
                   ("queue-ready", "Q03", question("Q02")), ("queue-ready", "Q04", question("None")))
        blocked = self.change(lambda lines: (ledger.move_row(lines, "Q01", "queue-blocked", {"Depends on": "G01"}),
                                             ledger.finish_write(lines, []))[1])
        self.assertEqual(blocked, ["Q02", "Q03"])
        self.assertEqual(self.rows("### Blocked"), ["Q01", "Q02", "Q03"])
        self.assertEqual(self.rows("### Ready"), ["Q04"])
        # A question added that needs a blocked one is blocked as it is written.
        self.assertEqual(self.write(
            ("queue-ready", "Q05", question("Q02"))), ["Q05"])
        for name, rows in [("itself", [("queue-ready", "Q07", question("Q07"))]),
                           ("a circle", [("queue-ready", "Q07", question("Q08")),
                                         ("queue-ready", "Q08", question("Q07"))])]:
            before = self.text()
            with self.subTest(name), self.assertRaisesRegex(SystemExit, "in a circle"):
                self.write(*rows)
            self.assertEqual(self.text(), before)

    def test_the_system_design_is_written_in_its_tables(self):
        self.records("F01", "S01")
        component = ["{} (service)", "Serves", "[x](https://example.com/x)",
                     "🟨 Planned", "d", "F01", "n", "B01"]
        self.write(("boundaries", "B01", ["Production cluster", "network", "F01"]),
                   ("components", "C01", [
                    component[0].format("Web")] + component[1:]),
                   ("components", "C02", [component[0].format(
                       "Search API")] + component[1:]),
                   ("identities", "I01", ["web token",
                    "token", "the search API", "F01"]),
                   ("connections", "E01", [
                    "C01", "C02", "HTTP", "the query", "yes", "I01", "🟨 Planned", "F01"]),
                   ("flows", "P01", ["A user searches", "E01", "F01"]))
        brief = ledger.brief(self.lines())
        for heading in ("### Boundaries", "### Connections", "### Identities", "### Flows"):
            with self.subTest(heading):
                self.assertIn(heading, brief)
        self.assertIn("E01 | C01 | C02 | HTTP", brief)
        # A flow can only walk connections the ledger holds, and a connection
        # joins two components.
        cases = [("an unrecorded connection", ("flows", "P02", ["Admin", c("E09"), "F01"]), "E09"),
                 ("an end that is no component", ("connections", "E02", ["C01", "the index", "SQL", "rows", "yes",
                                                                         "None", "🟨 Planned", "F01"]),
                  "To names one component")]
        for name, row, expected in cases:
            before = self.text()
            with self.subTest(name), self.assertRaisesRegex(SystemExit, expected):
                self.write(row)
            self.assertEqual(self.text(), before)

    def test_the_design_records_what_it_was_built_from(self):
        self.assertIsNone(ledger.design_basis(self.lines()))
        self.records("F01", "F02", "G01")
        self.assertEqual(ledger.basis(self.lines()), (2, 1, 0))
        self.change(lambda lines: ledger.set_design_basis(
            lines, ledger.basis(lines)))
        self.assertEqual(ledger.design_basis(self.lines()), (2, 1, 0))
        self.assertIn("## System design\n\nBuilt from 2 findings, 1 gaps and 0 decisions.\n\n### Components",
                      self.text())
        # Written again, the line is replaced, not added.
        self.records("F03")
        self.change(lambda lines: ledger.set_design_basis(
            lines, ledger.basis(lines)))
        self.assertEqual(self.text().count("Built from"), 1)
        self.assertEqual(check_report.check_ledger(self.path), ([], []))

    def test_move_a_queue_row_between_subsections(self):
        self.records("F01", "G01")
        self.write(("queue-ready", "Q01", QUEUE_ROW),
                   ("queue-ready", "Q02", QUEUE_ROW))
        self.change(lambda lines: ledger.move_row(
            lines, "Q01", "queue-completed", {"Findings": "F01"}))
        self.assertEqual(self.rows("### Ready"), ["Q02"])
        self.assertEqual(self.rows("### Completed"), ["Q01"])
        # A blocked question names what blocks it.
        with self.assertRaisesRegex(SystemExit, "Q02: a blocked question names what blocks it"):
            self.change(lambda lines: ledger.move_row(
                lines, "Q02", "queue-blocked"))
        self.change(lambda lines: ledger.move_row(
            lines, "Q02", "queue-blocked", {"Depends on": "G01"}))
        ready = self.text().split("### Ready")[1].split("### In progress")[0]
        self.assertIn("None.", ready)
        blocked = self.text().split("### Blocked")[1].split("## ")[0]
        self.assertNotIn("None.", blocked)
        with self.assertRaisesRegex(SystemExit, "no queue row Q09"):
            self.change(lambda lines: ledger.move_row(
                lines, "Q09", "queue-completed"))

    def test_inline_links_become_reference_links(self):
        # A URL keeps one key, however many times it is written inline.
        self.write(("sources", "S01", source("[Spec doc](https://example.com/spec)", "documentation", "2026-10-01",
                                             "partial: [Spec doc](https://example.com/spec) and "
                                             "[Other](https://example.com/spec)")),
                   ("sources", "S02", source("[Spec](https://example.com/other)", "documentation")))
        text = self.text()
        self.assertIn("| [Spec doc][spec-doc] |", text)
        self.assertIn("[Other][spec-doc]", text)
        self.assertIn("| [Spec][spec] |", text)
        self.assertEqual([line for line in text.split("## Links")[1].splitlines() if line.startswith("[")], [
            "[spec]: https://example.com/other", "[spec-doc]: https://example.com/spec"])
        # Another URL under a key already taken gets the next free one.
        self.prose("See [Spec](https://example.com/third).")
        self.assertIn("See [Spec][spec-2].", self.text())

    def test_ticket_keys_link_to_the_jira_site_that_has_their_project(self):
        # A key-shaped word whose project the site doesn't have, such as
        # SHA-256, is no ticket, so it stays as code; each project is asked once.
        asked = []

        class Site:
            base_url = "https://acme.atlassian.net"

            def project(self, key):
                asked.append(key)
                return {"key": key} if key == "PROJ" else None
        ledger.SITES.clear()
        self.addCleanup(ledger.SITES.clear)
        with mock.patch.object(ledger, "JiraClient", Site), mock.patch.object(ledger, "is_enabled", return_value=True):
            self.prose("PROJ-7 and PROJ-8 use SHA-256.")
        self.assertIn(
            "| [PROJ-7][proj-7] and [PROJ-8][proj-8] use `SHA-256`. |", self.text())
        self.assertIn(
            "[proj-7]: https://acme.atlassian.net/browse/PROJ-7", self.text())
        self.assertEqual(asked, ["PROJ", "SHA"])

    def test_ticket_keys_without_jira(self):
        # Without jira-api, or with its settings not filled in, every key is
        # written as code; a Jira failure stops the write with Jira's
        # message, writing nothing.
        failed = "Jira returned 500 for /rest/api/3/project/PROJ."

        class Failing:
            base_url = "https://acme.atlassian.net"

            def project(self, key):
                raise JiraError(failed)
        # name: (jira-api enabled, the client, the error it raises or None)
        cases = [("not enabled", False, Failing, None),
                 ("settings not filled in", True, mock.Mock(
                     side_effect=SystemExit("not filled in")), None),
                 ("Jira fails", True, Failing, JiraError)]
        for name, enabled, client, stop in cases:
            with self.subTest(name):
                ledger.SITES.clear()
                self.addCleanup(ledger.SITES.clear)
                before = self.text()
                with mock.patch.object(ledger, "JiraClient", client), \
                        mock.patch.object(ledger, "is_enabled", return_value=enabled):
                    if stop:
                        with self.assertRaises(stop):
                            self.prose("PROJ-7 is done.")
                        self.assertEqual(self.text(), before)
                    else:
                        self.prose("PROJ-7 is done.")
                        self.assertIn("| `PROJ-7` is done. |", self.text())

    def test_tickets_and_pull_requests_are_linked_on_write(self):
        # A ticket links once the ledger links one of its project, else it is code;
        # a pull request links from a page of its host, linked once.
        self.write(("sources", "S01", source("[PROJ-1](https://acme.example/browse/PROJ-1)", "tracker", "Done")),
                   ("sources", "S02", source("[api](https://git.example/acme/api/tree/abc)")))
        cases = [("PROJ-7 is open", "[PROJ-7][proj-7] is open", "[proj-7]: https://acme.example/browse/PROJ-7"),
                 ("OPS-1 and SHA-256", "`OPS-1` and `SHA-256`", None),
                 ("acme/api#12 merged", "[acme/api#12][acme-api-12] merged",
                  "[acme-api-12]: https://git.example/acme/api/pull/12"),
                 ("other/repo#3 open", "[other/repo#3][other-repo-3] open",
                  "[other-repo-3]: https://git.example/other/repo/pull/3"),
                 ("`PROJ-8` in code", "[PROJ-8][proj-8] in code", None)]
        for text, written, definition in cases:
            with self.subTest(text):
                self.prose(text)
                self.assertIn(f"| {written} |", self.text())
                if definition:
                    self.assertIn(definition, self.text())
        self.write(
            ("findings", "F01", ["PROJ-9 is open.", "S01 and PROJ-9", "read"]))
        self.assertIn(
            "| [PROJ-9][proj-9] is open. | S01 and [PROJ-9][proj-9] |", self.plain())
        before = self.text()
        with self.assertRaisesRegex(SystemExit, "#12: write a pull request as owner/repo#123"):
            self.prose("#12 merged")
        self.assertEqual(self.text(), before)

    def test_a_ticket_written_as_code_is_linked_once_its_project_is(self):
        self.prose("PROJ-7 is open")
        self.assertIn("| `PROJ-7` is open |", self.text())
        self.write(("sources", "S01", source(
            "[PROJ-1](https://acme.example/browse/PROJ-1)", "tracker", "Done")))
        self.assertIn("| [PROJ-7][proj-7] is open |", self.text())
        self.assertIn(
            "[proj-7]: https://acme.example/browse/PROJ-7", self.text())

    def test_sources_take_their_findings_from_the_findings(self):
        self.records("S01", "S02", "S03")
        self.write(("findings", "F01", ["One.", "S01 and S02 (lines 1-9)", "read"]),
                   ("findings", "F02", ["Two.", "S02", "read"]))
        text = self.plain()
        self.assertIn("| full | F01 | None |", text)
        self.assertIn("| full | F01, F02 | None |", text)
        self.assertEqual(check_report.source_finding_problems(self.text()), [])

    def test_a_record_still_cited_is_reported(self):
        # Leaving out a design row still cited elsewhere would leave a citation
        # of a record that isn't there.
        self.records("S01", "S02", "F01")
        self.write(("components", "C01", ["n", "r", "p", "🟨 Planned", "d", "F01", "next", "None"]),
                   ("queue-ready", "Q01", ["C01", "Is it live?", "None", ""]))
        self.change(lambda lines: ledger.record_review(lines, raised=["S02"]))
        cases = [("a row", "F01", "F01 is still cited by C01"),
                 ("a question's trigger", "C01", "C01 is still cited by Q01"),
                 ("outside the records", "S02", "S02 is still cited by the Independent reviews section")]
        for name, ident, expected in cases:
            with self.subTest(name), self.assertRaisesRegex(SystemExit, expected):
                ledger.refuse_cited(self.lines(), ident)

    def test_a_citation_names_a_record_the_ledger_holds(self):
        # A record citing one the ledger doesn't hold is refused, writing
        # nothing; records citing each other go in one write, in any order.
        before = self.text()
        gap = ["a", "b", "c",
               f"Waiting on decision ({c('D01')})", c("S02"), "e"]
        with self.assertRaisesRegex(SystemExit, "cites D01, S02, which the ledger doesn't hold"):
            self.write(("gaps", "G01", gap))
        self.assertEqual(self.text(), before)
        self.write(("gaps", "G01", gap),
                   ("decisions", "D01", ["a", c("G01"), "c", "d", "e"]),
                   ("findings", "F01", ["A claim.", c("S02"), "read"]),
                   ("sources", "S02", source(superseded=c("S03"))),
                   ("sources", "S03", source("[y](https://example.com/y)")))
        self.assertEqual(self.rows("## Evidence gaps"), ["G01"])

    def test_every_recorded_id_is_anchored_and_its_citations_link_to_it(self):
        self.write(("sources", "S01", source("[PROJ-1](https://acme.example/browse/PROJ-1)", "tracker", "Done")),
                   ("sources", "S02", source(
                       "[PROJ-2](https://acme.example/browse/PROJ-2)", "tracker", "Done")),
                   ("findings", "F01", ["Search is slow.", f"{c('S01')} and {c('S02')}", "read"]))
        text = self.text()
        self.assertIn('| <a id="s01"></a>S01 | tracker |', text)
        self.assertIn(
            '| <a id="f01"></a>F01 | Search is slow. | [S01](#s01) and [S02](#s02) |', text)
        self.assertIn("| full | [F01](#f01) | None |", text)
        # An ID-shaped word not written as a citation is prose, left as it is.
        self.prose("F01 rests on S01; P95 is a latency.")
        self.assertIn("| F01 rests on S01; P95 is a latency. |", self.text())
        # The next ID counts anchored rows.
        self.assertEqual(ledger.next_id(self.text(), "S"), "S03")
        self.assertEqual(check_report.check_ledger(self.path), ([], []))

    def test_a_code_status_needs_the_code_read(self):
        # A component claiming code needs a code source of its path read in
        # full or in part: one case each way, as test_common.py
        # has the rule's own.
        self.records("F01")
        tree = "https://git.example/acme/api/tree/abc/services/search"
        component = [
            "search", "r", f"[search]({tree})", "🟩 Implemented", "d", "F01", "next", "None"]
        with self.assertRaisesRegex(SystemExit, "C01 links acme/api: services/search"):
            self.write(("components", "C01", component))
        self.write(("sources", "S01", source("[f](https://git.example/acme/api/tree/abc/services/search)",
                                             coverage="listing")))
        with self.assertRaisesRegex(SystemExit, "needs its code read"):
            self.write(("components", "C01", component))
        self.write(
            ("components", "C01", component[:3] + ["🟨 Planned"] + component[4:]))
        self.write(("sources", "S02", source("[f](https://git.example/acme/api/blob/abc/services/search/src/routes.py)",
                                             coverage="partial: lines 1-80")))
        self.write(("components", "C01", component))
        self.assertIn("| 🟩 Implemented |", self.text())

    def test_review_rounds_are_recorded(self):
        self.write(("queue-ready", "Q01", QUEUE_ROW))
        self.assertEqual(self.change(
            lambda lines: ledger.record_review(lines, ["Q01"])), 1)
        self.assertEqual(self.change(
            lambda lines: ledger.record_review(lines, [])), 2)
        self.change(lambda lines: ledger.record_review(
            lines, stopped="wrap up now"))
        # Each round is a row of the reviews table, numbered in order; the
        # queue holds only questions.
        self.assertIn("| 1 | Q01 |\n| 2 | No issue raised |\n| 3 | Stopped by the user: wrap up now |",
                      self.plain())
        self.assertEqual(self.rows("### Completed"), [])


if __name__ == "__main__":
    unittest.main()
