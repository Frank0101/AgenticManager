"""Unit tests for skills/agentic-manager-tech-investigation/scripts/check_report.py.
The whole pipeline, which runs it, has end-to-end tests in test_e2e_investigation.py.
Run with: python3 tests/run.py agentic-manager-tech-investigation

Each test writes an invented report and ledger to a temporary folder;
check_report() reads no config.
"""

import json
import os
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(TEST_DIR))
sys.path.insert(0, os.path.join(REPO_ROOT, "skills",
                os.path.basename(TEST_DIR), "scripts"))
import check_report  # noqa: E402
from common import HEADINGS, table_row  # noqa: E402
sys.path.insert(0, TEST_DIR)
from investigation_fixture import (FINDING_ROWS, LEDGER, SOURCE_ROWS, assert_problem,  # noqa: E402
                                   source_row, with_prose, with_queue, with_rows)

# F01's row as the ledger writes it: a finding resting on the code source S01.
FINDING_ROW = table_row(FINDING_ROWS[0])


def with_sources(rows):
    """LEDGER with `rows`, each a source's cells, in place of its sources of
    the same ID, and next to the others."""
    held = {row[0]: row for row in SOURCE_ROWS} | {row[0]: row for row in rows}
    return with_rows(LEDGER, "sources", [held[ident] for ident in sorted(held)])


class CheckReportTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.report = self.folder / "Acme_Report.md"
        (self.folder / "ledger.md").write_text(LEDGER, encoding="utf-8")
        parts = [
            "# Acme\n\nEvidence snapshot: today. [Research ledger](ledger.md).\n"]
        for level, title, ident in HEADINGS:
            parts.append("#" * level + " " + title + "\n\n")
            if ident in ("arch.today", "arch.target"):
                parts.append(
                    "Architect text with [code](https://example.com/code).\n\n")
            elif ident == "arch.decisions":
                parts.append("| Decision or gap | Why it matters | Established position | Evidence |\n"
                             "| --- | --- | --- | --- |\n"
                             "| Storage | Cache or index | Open | [Proposal](https://example.com/proposal) |\n")
            else:
                parts.append(
                    "Account supported by [source](https://example.com/evidence).\n\n")
        self.text = "".join(parts)
        self.report.write_text(self.text, encoding="utf-8")

    def check(self, text=None):
        if text is not None:
            self.report.write_text(text, encoding="utf-8")
        return check_report.check_report(self.report)

    def test_accepted_reports(self):
        # Each variant passes, with this many warnings, and the check writes
        # nothing.
        proposal = "[Proposal](https://example.com/proposal)"
        row = "| Storage | Cache or index | Open | [Proposal](https://example.com/proposal) |"
        (self.folder / "extra evidence.md").write_text("Evidence", encoding="utf-8")
        cases = [
            ("the complete report", self.text, 0),
            ("a shortcut reference link citing a table row",
             self.text.replace(proposal, "[Proposal]") + "\n[Proposal]: https://example.com/proposal\n", 0),
            ("a row citing a ledger finding", self.text.replace(
                row, "| Storage | Cache or index | Open | [F01](ledger.md#f01) |"), 0),
            ("reference links, encoded paths and fences", self.text.replace(proposal, "[Proposal][proof]")
             + "\n[proof]: https://example.com/proposal\n[Local](<extra%20evidence.md>)\n"
             "```text\n## Fake heading\n[Not a link](missing.md)\n```\n", 0),
            ("a summary with its own subheading", self.text.replace(
                "Architect text with", "#### Entry paths\n\nArchitect text with", 1), 0),
        ]
        for name, text, warnings in cases:
            with self.subTest(name):
                self.report.write_text(text, encoding="utf-8")
                before = {p.name: p.read_bytes()
                          for p in self.folder.iterdir()}
                result = check_report.check_report(self.report)
                self.assertEqual((result["ok"], result["errors"], len(result["warnings"])),
                                 (True, [], warnings), result)
                self.assertEqual(before, {p.name: p.read_bytes()
                                 for p in self.folder.iterdir()})

    def test_rejected_reports(self):
        # Each breakage fails, with an error naming it.
        cases = [
            # Structure
            ("missing section", self.text.replace(
                "### Key decisions and risks", "#### Key decisions and risks"), "H2/H3"),
            ("extra section", self.text + "\n## Engineering\n", "H2/H3"),
            # Citations: every table row links its evidence, even one saying what is unknown.
            ("a row without a source", self.text.replace(
                "[Proposal](https://example.com/proposal)", "Lower latency"), "point-of-use source link"),
            ("a row of unknowns without a source", self.text.replace(
                "| Cache or index | Open | [Proposal](https://example.com/proposal) |",
                "| Not established | Unverified | Evidence unavailable |"), "point-of-use source link"),
            ("an undefined shortcut reference", self.text.replace(
                "[Proposal](https://example.com/proposal)", "[Proposal]"), "table row needs"),
            # Local files
            ("missing image", self.text +
             "\n![Picture](missing.png)", "local link target is missing"),
            ("missing document", self.text +
             "\n[Details](absent.md#section)", "local link target is missing"),
            ("unresolved reference", self.text +
             "\n[Details][absent]", "unresolved Markdown"),
        ]
        for name, text, expected in cases:
            with self.subTest(name):
                result = self.check(text)
                self.assertFalse(result["ok"])
                self.assertIn(expected, " ".join(result["errors"]))

    def test_links_into_the_ledger_must_name_a_heading(self):
        (self.folder / "ledger.md").write_text(
            "# Research\n\n## G1\nGap.\n\n### F03 — Delivery is exploration\n\n## Repeat\n\n## Repeat\n", encoding="utf-8")
        cases = [("[F03](ledger.md#f03--delivery-is-exploration)", True), ("[gap](ledger.md#g1)", True),
                 ("[second](ledger.md#repeat-1)", True), ("[gone](ledger.md#f99--missing)", False)]
        for link, ok in cases:
            with self.subTest(link=link):
                errors = self.check(self.text.replace(
                    "[Research ledger](ledger.md)", link))["errors"]
                self.assertEqual(
                    any("has no heading for" in e for e in errors), not ok, errors)

    def test_ledger_structure(self):
        ledger = self.folder / "ledger.md"
        cases = [
            ("complete", LEDGER, None),
            ("section order", LEDGER.replace("## Links",
             "## Summary"), "sections must be exactly"),
            ("queue subsections", LEDGER.replace(
                "### Blocked", "### Waiting"), "queue needs exactly"),
            ("duplicate finding", LEDGER.replace(FINDING_ROW, FINDING_ROW + "\n" + FINDING_ROW),
             "findings written more than once: F01; keep one row each"),
            ("undefined finding", LEDGER.replace(
                "None yet.", "See [F07](#f07).", 1), "never written: F07"),
        ]
        for name, text, error in cases:
            with self.subTest(name=name):
                ledger.write_text(text, encoding="utf-8")
                result = self.check()
                self.assertEqual(any(error in e for e in result["errors"]) if error else result["errors"] == [],
                                 True, result)

    def test_unreadable_ledger_fails(self):
        ledger = self.folder / "ledger.md"
        for handover in (False, True):
            with self.subTest(handover=handover, cause="UTF-8"):
                ledger.write_bytes(b"\xff")
                result = check_report.check_report(
                    self.report, handover=handover)
                self.assertFalse(result["ok"])
                self.assertIn("cannot read research ledger",
                              " ".join(result["errors"]))
            with self.subTest(handover=handover, cause="I/O"):
                with mock.patch.object(Path, "read_text", side_effect=OSError("unreadable")):
                    errors, _ = check_report.check_ledger(
                        ledger, handover=handover)
                self.assertIn("cannot read research ledger", " ".join(errors))

    def test_handover_gaps_need_a_valid_blocker(self):
        # The gap rules apply at handover: a blocker, and evidence that traces
        # it; the blocker's own cases are in test_common.py.
        ledger = self.folder / "ledger.md"
        cases = [("a decision", "Waiting on decision D01", "F01", None),
                 ("nothing blocks it", "Not done yet",
                  "F01", "Blocked by"),
                 ("evidence that traces nothing", "Waiting on decision D01", "Code",
                  "G01: Evidence names the findings or sources")]
        for name, blocker, evidence, expected in cases:
            with self.subTest(name):
                text = with_rows(with_rows(LEDGER, "gaps", [["G01", "Gap", blocker, "Owner", evidence]]),
                                 "decisions", [["D01", "Choice", "Unresolved: A or B", "Owner", "F01"]])
                ledger.write_text(text, encoding="utf-8")
                result = check_report.check_report(self.report, handover=True)
                assert_problem(self, " ".join(
                    result["errors"]) or None, expected)

    def test_handover_needs_the_queue_worked(self):
        # At handover nothing is left ready or in progress.
        open_question = ["Q01", "Start", "Read code", "—", "—"]
        cases = [
            ("a question answered", LEDGER, None),
            ("a ready question", with_queue(LEDGER, "Ready", [open_question]),
             "still ready or in progress"),
            ("a question in progress", with_queue(LEDGER, "In progress", [open_question]),
             "still ready or in progress")]
        for name, text, expected in cases:
            with self.subTest(name):
                (self.folder / "ledger.md").write_text(text, encoding="utf-8")
                self.assertTrue(check_report.check_report(self.report)["ok"])
                result = check_report.check_report(self.report, handover=True)
                assert_problem(self, " ".join(
                    result["errors"]) or None, expected)

    def test_handover_allows_only_the_skills_files(self):
        (self.folder / "ledger.md").write_text(LEDGER, encoding="utf-8")
        for name in ("content.json", ".DS_Store"):
            (self.folder / name).write_text("{}", encoding="utf-8")
        self.assertTrue(check_report.check_report(
            self.report, handover=True)["ok"])
        for stray in ("notes.md", "draft.json", "diagram.mmd", "exec-summary.md"):
            with self.subTest(stray):
                (self.folder / stray).write_text("x", encoding="utf-8")
                self.assertTrue(check_report.check_report(self.report)["ok"])
                result = check_report.check_report(self.report, handover=True)
                self.assertFalse(result["ok"])
                self.assertIn(f"Unexpected files in the investigation folder: {stray}", " ".join(
                    result["errors"]))
                (self.folder / stray).unlink()

    def test_handover_needs_links_to_sources(self):
        # A source links its reference; a search is recorded by its exact query between backticks instead.
        def search(reference, ident="S04"):
            return source_row(ident, "code: search", reference, "today", "search hit")
        query = "`gh search code --repo acme/app PROJ-1`"
        cases = [
            ("linked rows", [search(query)], None),
            ("a search described in words", [search("a GitHub code search")],
             "S04: link the Reference at its pinned revision"),
            ("an unlinked source", [source_row(reference="acme/app", findings="F01")],
             "S01: link the Reference at its pinned revision"),
            # Rows as ledger.py writes them: anchored IDs and linked citations.
            ("an anchored search", [
             search(query, '<a id="s04"></a>S04')], None),
        ]
        for name, rows, expected in cases:
            with self.subTest(name):
                (self.folder / "ledger.md").write_text(with_sources(rows), encoding="utf-8")
                self.assertTrue(check_report.check_report(self.report)["ok"])
                result = check_report.check_report(self.report, handover=True)
                assert_problem(self, " ".join(
                    result["errors"]) or None, expected)

    def test_unlinked_references_fail(self):
        # In the ledger and the report alike: a backticked reference is a link
        # to its revision, checked at handover; a ticket or a pull request the
        # scripts link, so one left bare fails every check. Plain words and the
        # text of a link are fine.
        backticks = "references in backticks without a link: "
        bare = "tickets and pull requests written without a link: "
        # name: (the sentence, the error expected, or None, and whether only
        # the handover check finds it)
        cases = [
            ("a linked reference",
             "[`app.py`](https://github.com/acme/app/blob/abc1234/app.py) holds it.", None, False),
            ("plain words", "The master branch holds it.", None, False),
            ("an unlinked reference", "See `app.py` and `acme/app`.",
             backticks + "`app.py`, `acme/app`", True),
            ("a ticket key of a project nothing links",
             "`PROJ-12` tracks it.", None, False),
            ("a ticket key of a linked project", "[PROJ-1](https://acme.example/browse/PROJ-1) and `PROJ-12`.",
             backticks + "`PROJ-12`", True),
            ("linked tickets and pull requests", "[PROJ-1](https://example.atlassian.net/browse/PROJ-1) and "
             "[#2](https://github.com/acme/app/pull/2)", None, False),
            ("a ticket key", "See PROJ-1.", bare + "PROJ-1", False),
            ("a bare pull request", "See PR #2.", bare + "#2", False),
            ("a pull request with its repository",
             "See acme/app#3.", bare + "acme/app#3", False),
            ("a heading is left alone", "#### Flow for PROJ-1", None, False),
        ]
        for name, sentence, expected, handover_only in cases:
            (self.folder / "ledger.md").write_text(with_prose(LEDGER,
                                                              sentence), encoding="utf-8")
            self.report.write_text(
                self.text + "\n" + sentence + "\n", encoding="utf-8")
            for handover in (False, True):
                with self.subTest(name, handover=handover):
                    found = expected if handover or not handover_only else None
                    result = check_report.check_report(
                        self.report, handover=handover)
                    self.assertEqual(result["ok"], found is None, result)
                    if found:
                        self.assertEqual(
                            sum(found in e for e in result["errors"]), 2, result)

    def test_handover_rechecks_blocked_questions_sources_and_findings(self):
        # A ledger edited without the script is checked again at handover:
        # one case of each rule, whose own cases are in test_common.py.
        def source(kind="tracker", coverage="partial: sections: Description", superseded="None"):
            return with_sources([source_row("S04", kind, revision="d", coverage=coverage, superseded=superseded)])
        partly = with_sources([source_row(reference="[app](https://github.com/acme/app/blob/abc1234/app.py)", revision="abc1234",
                                          coverage="partial: lines 1-9", findings="F01")])
        # name: (ledger, expected problem, or None)
        cases = [("allowed sources", source(), None),
                 ("a source of no group", source(
                     kind="source_control"), "S04: Kind starts with"),
                 ("a coverage not allowed", source(coverage="skimmed"),
                  "S04: Coverage starts with one of"),
                 ("superseded by words", source(superseded="the 2026 design"),
                  "S04: Superseded by is None, or the one source that replaces it"),
                 ("a finding citing no source", with_rows(LEDGER, "findings", [
                     ["F01", "Search is merged.", "the code", "Read."], FINDING_ROWS[1]]),
                  "F01: Sources names the sources"),
                 ("a question blocked by nothing", with_queue(LEDGER, "Blocked", [
                     ["Q09", "Start", "Read billing", "None", "—"]]),
                  "Q09: a blocked question names what blocks it"),
                 ("code linked at another revision than it was read", with_sources([
                     source_row(reference="[app](https://github.com/acme/app/tree/abc1234)", revision="def1234",
                                findings="F01")]), "S01: Reference links code at abc1234, Revision is def1234"),
                 ("a partial read its finding doesn't explain", partly,
                  "F01: cites S01, read only in part"),
                 ("a partial read its finding explains", partly.replace(
                     "| Routes read in full. |", "| [S01](#s01) read in part: the rest is tests. |"), None)]
        for name, ledger, expected in cases:
            with self.subTest(name):
                assert_problem(self, " ".join(
                    check_report.closing_problems(ledger)) or None, expected)

    def test_handover_closing_rules(self):
        # A completed question names its answer and a component's status is an
        # allowed one, one case each, as test_common.py has the rules' own; one
        # claiming code rests on a code source read under its path, which a
        # finding of its evidence cites, and links its code at a commit.
        def component(status):
            return ["C01", "search", "service", "None", "Serves", "[search][search]", status, "Unchanged",
                    "F01" if status.startswith("🟩") else "G01"]
        # The finding citing the code, never read in full here, says why the
        # rest can't change it.
        explained = FINDING_ROW.replace(
            "Routes read in full. |", "S01 read in part: the unread lines are admin routes. |")

        def read(path, coverage):
            return [source_row(reference=f"[routes](https://github.com/acme/app/blob/abc1234/services/search/{path})",
                               revision="abc1234", coverage=coverage, findings="F01")]
        listing = read("", "listing")
        routes = read("src/routes.py", "partial: lines 1-80")
        # name: (outcome, status, sources, the problem, and the finding row and
        # the code's revision when they differ)
        cases = [
            # A question a gap stops is blocked, never completed.
            ("a question closed on a gap", "G01", "⬜ Unverified",
             listing, "Q01: a completed question"),
            ("a question closed on its finding",
             "F01", "⬜ Unverified", listing, None),
            ("a status not allowed", "F01", "Done",
             listing, "C01: State starts with"),
            ("code claimed from a listing", "F01", "🟩 Live",
             listing, "C01 links acme/app: services/search"),
            ("code claimed from its routes", "F01", "🟩 Live", routes, None),
            ("code read, but by no finding of its evidence", "F01", "🟩 Live",
             routes, "C01 links acme/app: services/search",
             explained.replace("| S01 |", "| F01 |")),
            ("code linked at a branch", "F01", "🟩 Live", routes,
             "C01: Repository, paths, revision links code at main", explained, "main"),
        ]
        for name, outcome, status, sources, expected, *more in cases:
            finding = more[0] if more else explained
            revision = more[1] if len(more) > 1 else "abc1234"
            tree = f"https://github.com/acme/app/tree/{revision}/services/search"
            with self.subTest(name):
                text = (with_rows(with_sources(sources), "components", [component(status)])
                        .replace("| — | F01 |", f"| — | {outcome} |")
                        .replace(FINDING_ROW, finding)
                        .replace("## Links\n\nNone yet.", f"## Links\n\n[search]: {tree}"))
                (self.folder / "ledger.md").write_text(text, encoding="utf-8")
                result = check_report.check_report(self.report, handover=True)
                assert_problem(self, " ".join(
                    result["errors"]) or None, expected)

    def test_the_design_is_checked_again_at_handover(self):
        # The rules applied on write hold in the ledger handed over: a status
        # its evidence reaches, flows in order, and the State the script
        # derives for identities and flows.
        def connection(ident, start, end, identity, state="🟨 Planned", evidence="F02"):
            return [ident, start, end, "HTTP", "q", "yes", identity, state, "Unchanged", evidence]
        connections = [connection("E01", "C01", "C03", "I01"),
                       connection("E02", "C03", "C01", "None")]

        def design(state="🟨 Planned", walked="E01, E02", evidence="F02", connections=connections):
            text = with_rows(with_rows(with_rows(LEDGER, "connections", connections), "identities", [
                ["I01", "token", "service account", "C03", state, "Unchanged", "F02"]]), "flows", [
                ["P01", "A search", walked, "🟨 Planned", "Unchanged", "F02"]])
            return text.replace("| 🟨 Planned | Unchanged | F02 |", f"| 🟨 Planned | Unchanged | {evidence} |", 1)
        # name: (the ledger, a problem it has, or None)
        cases = [("a design that holds", design(), None),
                 ("a planned component resting on code only",
                  design(evidence="F01"), "C01: State 🟨 Planned needs a finding read in the tracker"),
                 ("a flow that comes back", design(walked="E01, E02, E01"), None),
                 ("a flow that jumps", design(walked="E01, E02").replace("| C03 | C01 |", "| C04 | C02 |"),
                  "E02 runs from C04 to C02, neither of which the flow has reached yet"),
                 ("an identity's State edited by hand", design(state="🟩 Live"),
                  "I01 has State 🟩 Live, its connections give 🟨 Planned")]
        # A live connection rests on code read: F01's source, not F02's
        # ticket.
        for evidence, expected in (("F01", None), ("F02", "E01: State 🟩 Live needs a finding read in the code")):
            cases.append((f"a live connection resting on {evidence}",
                          design(state="🟩 Live", connections=[connection("E01", "C01", "C03", "I01", "🟩 Live",
                                                                         evidence), connections[1]]),
                          expected))
        # A part of a mention-only topic, citing that decision, needs no code
        # read, and each connection to it cites the decision too; one citing a
        # decision that included its topic needs its code read.
        scope = [["U01", "Payments", "mention only", "Q01"],
                 ["U02", "Billing", "include", "Q01"]]
        cited = [row[:-1] + ["F02, U01"] for row in connections]
        for name, answer, edges, expected in (
                ("a live part citing U01", "U01", cited, None),
                ("a connection to a mention-only part not citing it", "U01", connections,
                 "E01: From C01 is a part of a topic decided as mention only, so the connection cites U01"),
                ("a live part citing U02", "U02", connections, "C01 links")):
            cases.append((name, with_rows(design(connections=edges), "scope", scope)
                          .replace("| 🟨 Planned | Unchanged | F02 |", f"| 🟩 Live | Unchanged | F02, {answer} |", 1),
                          expected))
        for name, text, expected in cases:
            with self.subTest(name):
                problems = [p for p in check_report.closing_problems(text) if p] + \
                    check_report.derived_state_problems(text)
                assert_problem(self, " ".join(problems) or None, expected)

    def test_brackets_in_code_are_no_reference_link(self):
        # A pattern's brackets in a search's query, `PROJ-6[0-9][0-9]`, are code.
        search = source_row("S04", "code: search", "`grep 'PROJ-6[0-9][0-9]'`",
                            "2026-10-05", "search hit")
        body = with_rows(LEDGER, "sources", SOURCE_ROWS + [search])
        self.assertEqual(check_report.reference_problems(body)[0], [])

    def test_reference_links_need_definitions(self):
        # `[text][key]` takes its URL from a definition in ## Links: an undefined key is an error, an unused one a warning.
        ledger = self.folder / "ledger.md"
        cases = [
            ("defined and used",
             "See [doc][doc].\n\n## Links\n\n[doc]: https://example.com/doc", [], []),
            ("collapsed",
             "See [doc][].\n\n## Links\n\n[doc]: https://example.com/doc", [], []),
            ("undefined", "See [doc][nope].\n\n## Links\n\n[doc]: https://example.com/doc", ["without a definition in ## Links: nope"],
             ["never used: doc"]),
            ("unused",
             "No link.\n\n## Links\n\n[doc]: https://example.com/doc", [], ["never used: doc"]),
        ]
        for name, body, errors, warnings in cases:
            with self.subTest(name):
                text = LEDGER.replace("## Links\n\nNone yet.", body.split(
                    "\n\n## Links\n\n")[1].join(["## Links\n\n", ""]))
                text = with_prose(text, body.split("\n\n## Links")[0])
                ledger.write_text(text, encoding="utf-8")
                found_errors, found_warnings = check_report.check_ledger(
                    ledger)
                for expected in errors:
                    self.assertIn(expected, " ".join(found_errors))
                for expected in warnings:
                    self.assertIn(expected, " ".join(found_warnings))
                if not errors:
                    self.assertEqual(found_errors, [])

    def test_reference_links_count_as_links_at_handover(self):
        sentence = "See [`app.py`][app], [PROJ-1][proj-1] and [#2][pr-2]."
        links = "[app]: https://github.com/acme/app/blob/abc/app.py\n[pr-2]: https://github.com/acme/app/pull/2\n[proj-1]: https://example.atlassian.net/browse/PROJ-1"
        text = with_prose(LEDGER, sentence)
        text = text.replace("## Links\n\nNone yet.", "## Links\n\n" + links)
        (self.folder / "ledger.md").write_text(text, encoding="utf-8")
        result = check_report.check_report(self.report, handover=True)
        self.assertTrue(result["ok"], result)

    def test_long_claims_and_unrecorded_ids_fail(self):
        ledger = self.folder / "ledger.md"
        ledger.write_text(LEDGER.replace(f"| {FINDING_ROWS[0][1]} |", "| " + "word " * 160 + "|"),
                          encoding="utf-8")
        errors, _ = check_report.check_ledger(ledger)
        self.assertIn("claim is 160 words", " ".join(errors))
        # A citation is a link to a record's anchor; a bare ID-shaped word,
        # such as P95 or F150, is prose, a finding's number included.
        ledger.write_text(with_prose(LEDGER, "See [S07](#s07) and [Q03](#q03); P95 is a latency and the F150 a "
                                     "truck."),
                          encoding="utf-8")
        self.assertEqual(check_report.check_ledger(
            ledger, handover=False)[0], [])
        errors, _ = check_report.check_ledger(ledger, handover=True)
        self.assertIn("IDs cited but never recorded: Q03, S07",
                      " ".join(errors))
        # A finding cited but never written is reported once, by its own check.
        ledger.write_text(with_prose(LEDGER, "See [F07](#f07)."),
                          encoding="utf-8")
        errors, _ = check_report.check_ledger(ledger, handover=True)
        self.assertEqual([e for e in errors if "F07" in e], [
                         "ledger.md: findings cited but never written: F07"])

    def test_unreadable_missing_and_relative_report(self):
        for path in ("relative.md", self.folder / "missing.md"):
            with self.subTest(path=str(path)):
                self.assertFalse(check_report.check_report(path)["ok"])
        self.report.write_bytes(b"\xff")
        self.assertIn("UTF-8", " ".join(self.check()["errors"]))


if __name__ == "__main__":
    unittest.main()
