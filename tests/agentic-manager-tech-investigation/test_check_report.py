"""Unit tests for skills/agentic-manager-tech-investigation/scripts/check_report.py.
The whole script has end-to-end tests in test_e2e_check_report.py.
Run with: python3 tests/run.py agentic-manager-tech-investigation

Each test writes an invented report and ledger to a temporary folder;
check_report() reads no config.
"""

import contextlib
import io
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
from common import HEADINGS  # noqa: E402
from init_investigation import ledger_skeleton  # noqa: E402
sys.path.insert(0, TEST_DIR)
from investigation_fixture import with_queue  # noqa: E402

# A ledger as handover needs it: its gap, its queue worked and its review finished.
LEDGER = with_queue(ledger_skeleton("Acme").replace(
    "## Evidence gaps\n\nNone yet.",
    "## Evidence gaps\n\n### G01\n\nEvidence unavailable."), "Completed", [
    ["Q01", "Start", "Read code", "Code", "—", "G01"],
    ["Q02", "Independent review", "Independent review of the ledger", "Subagent", "None", "Nothing doable found"]])


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
            ("a row citing a ledger gap", self.text.replace(
                row, "| Storage | Cache or index | Open | [G01](ledger.md#g01) |"), 0),
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
        finding = ("### F01 — Search is merged\n\n" +
                   "\n".join(f"**{field}:** text." for field in check_report.FINDING_FIELDS))
        complete = LEDGER.replace("## Findings and validation chains\n\nNone yet.",
                                  "## Findings and validation chains\n\n" + finding)
        cases = [
            ("complete", complete, None, None),
            ("section order", complete.replace("## Links",
             "## Summary"), "sections must be exactly", None),
            ("queue subsections", complete.replace(
                "### Blocked", "### Waiting"), "queue needs exactly", None),
            ("duplicate finding", complete + "\n" +
             finding, "duplicate findings: F01", None),
            ("undefined finding", complete.replace(
                "None yet.", "See F07.", 1), "never written: F07", None),
            ("missing fields", complete.replace(
                "**Evidence:** text.", ""), None, "F01 lacks Evidence"),
        ]
        for name, text, error, warning in cases:
            with self.subTest(name=name):
                ledger.write_text(text, encoding="utf-8")
                result = self.check()
                self.assertEqual(any(error in e for e in result["errors"]) if error else result["errors"] == [],
                                 True, result)
                if warning:
                    self.assertIn(warning, " ".join(result["warnings"]))

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

    def test_handover_gaps_need_a_valid_blocker_and_areas(self):
        # A gap nothing blocks is work to do, so it must be an action in the
        # queue and not a gap; its Areas are some of the allowed ones.
        ledger = self.folder / "ledger.md"
        gap = "| G01 | Gap | Missing | Read it | {} | Code | Owner | {} |\n"
        cases = [("no access", "No access to the cluster", "Delivery", None),
                 ("a decision", "Waiting on decision D01", "Delivery", None),
                 ("a decision with no ID", "Waiting on decision",
                  "Delivery", "Blocked by"),
                 ("approved scope cut",
                  "Out of scope, approved by the user", "Delivery", None),
                 ("an unanswered question",
                  "Asked the user, no answer: include the gateway?", "Delivery", None),
                 ("nothing blocks it", "Not done yet", "Delivery", "Blocked by"),
                 ("empty", "", "Delivery", "Blocked by"),
                 ("an unknown area", "No access to the cluster", "Delivery, Billing",
                  "G01: Areas must be some of: Architecture, Delivery")]
        for name, blocker, areas, expected in cases:
            with self.subTest(name):
                text = LEDGER.replace(
                    "## Evidence gaps\n\n", "## Evidence gaps\n\n" +
                    gap.format(blocker, areas), 1
                ).replace("## Open decisions\n\nNone yet.",
                          "## Open decisions\n\n| D01 | Choice | Open | A, B | Doc | Owner |")
                ledger.write_text(text, encoding="utf-8")
                result = check_report.check_report(self.report, handover=True)
                self.assertEqual(result["ok"], expected is None, result)
                if expected:
                    self.assertIn(expected, " ".join(result["errors"]))

    def test_handover_needs_the_queue_worked_and_reviewed(self):
        # At handover nothing is left ready or in progress, and the last
        # review round raised nothing, or the user chose to stop.
        review = ("| Q02 | Independent review | Independent review of the ledger | Subagent | None"
                  " | Nothing doable found |\n")
        raised = ("| Q02 | Independent review | Independent review of the ledger | Subagent | None"
                  " | Raised Q03 |\n| Q03 | Q02 | Read the job | Code | None | G01 |\n")
        open_action = ["Q01", "Start", "Read code", "Code", "—", "—"]
        cases = [
            ("an action, reviewed", LEDGER, None),
            ("a ready action", with_queue(LEDGER, "Ready", [open_action]),
             "still ready or in progress"),
            ("an action in progress", with_queue(LEDGER, "In progress", [open_action]),
             "still ready or in progress"),
            ("no review recorded", LEDGER.replace(review, ""),
             "no independent review is recorded"),
            ("the last round raised actions", LEDGER.replace(review, raised),
             "the last review round raised actions"),
            ("a later round raised nothing", LEDGER.replace(review, raised + review.replace("Q02", "Q04")),
             None),
            ("the user chose to stop", LEDGER.replace(review, raised + review.replace("Q02", "Q04").replace(
                "Subagent", "The user").replace("Nothing doable found", "Stopped by the user: wrap up")),
             None)]
        for name, text, expected in cases:
            with self.subTest(name):
                (self.folder / "ledger.md").write_text(text, encoding="utf-8")
                self.assertTrue(check_report.check_report(self.report)["ok"])
                result = check_report.check_report(self.report, handover=True)
                self.assertEqual(result["ok"], expected is None, result)
                if expected:
                    self.assertIn(expected, " ".join(result["errors"]))

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
        # A register row links its exact reference, a coverage row the material read; a search is recorded by its exact query between backticks instead.
        header = ("| Source ID | Group / evidence kind | Exact reference | Revision | Read | Limits | Areas |\n"
                  "| --- | --- | --- | --- | --- | --- | --- |\n")
        coverage = "### File reading coverage\n\n| Source | Material | Depth |\n| --- | --- | --- |\n"
        cases = [
            ("linked rows", "| S01 | source_control / implementation | [repo](https://github.com/acme/app/tree/abc123) | abc123 | x | y | Implementation |\n"
             "| S02 | source_control / search | `gh search code --repo acme/app PROJ-1` | today | x | y | Implementation |\n",
             "| S01 | [`a.md`](https://github.com/acme/app/blob/abc123/a.md) | Full |\n", None),
            ("a search described in words", "| S01 | source_control / search | a GitHub code search | today | x | y | Implementation |\n",
             "| S01 | [`a.md`](https://github.com/acme/app/blob/abc123/a.md) | Full |\n", "register rows without a link"),
            ("an unlinked source", "| S01 | source_control / implementation | acme/app | abc123 | x | y | Implementation |\n",
             "| S01 | [`a.md`](https://github.com/acme/app/blob/abc123/a.md) | Full |\n", "register rows without a link"),
            ("an unlinked file", "| S01 | source_control / implementation | [repo](https://github.com/acme/app/tree/abc123) | abc123 | x | y | Implementation |\n",
             "| S01 | `a.md` | Full |\n", "File reading coverage rows without a link"),
            # Rows as ledger.py writes them: anchored IDs and linked citations.
            ("an anchored search", '| <a id="s02"></a>S02 | source_control / search | `gh search code --repo acme/app PROJ-1` | today | x | y | Implementation |\n',
             "| [S02](#s02) | [`a.md`](https://github.com/acme/app/blob/abc123/a.md) | Full |\n", None),
            ("a linked citation with no material link",
             '| <a id="s01"></a>S01 | source_control / implementation | [repo](https://github.com/acme/app/tree/abc123) | abc123 | x | y | Implementation |\n',
             "| [S01](#s01) | a.md | Full |\n", "File reading coverage rows without a link to the material read: S01"),
        ]
        for name, register, files, expected in cases:
            with self.subTest(name):
                text = LEDGER.replace("## Revisions and source register\n\n",
                                      "## Revisions and source register\n\n" + header + register, 1)
                text = text.replace(
                    "### File reading coverage\n\nNone yet.", coverage + files)
                (self.folder / "ledger.md").write_text(text, encoding="utf-8")
                self.assertTrue(check_report.check_report(self.report)["ok"])
                result = check_report.check_report(self.report, handover=True)
                self.assertEqual(result["ok"], expected is None, result)
                if expected:
                    self.assertIn(expected, " ".join(result["errors"]))

    def test_handover_rejects_unlinked_backticks(self):
        # A backticked reference is a link to its revision; plain words and the text of a link are fine.
        cases = [
            ("a linked reference",
             "[`app.py`](https://github.com/acme/app/blob/abc123/app.py) holds it.", None),
            ("plain words", "The master branch holds it.", None),
            ("an unlinked reference", "See `app.py` and `acme/app`.",
             "references in backticks without a link: `app.py`, `acme/app`"),
            ("a ticket key of a project nothing links", "`PROJ-12` tracks it.", None),
            ("a ticket key of a linked project", "[PROJ-1](https://acme.example/browse/PROJ-1) and `PROJ-12`.",
             "references in backticks without a link: `PROJ-12`"),
        ]
        for name, sentence, expected in cases:
            with self.subTest(name):
                (self.folder / "ledger.md").write_text(
                    LEDGER.replace("## Boundary\n\nNone yet.",
                                   "## Boundary\n\n" + sentence), encoding="utf-8")
                self.report.write_text(
                    self.text + "\n" + sentence + "\n", encoding="utf-8")
                self.assertTrue(check_report.check_report(self.report)["ok"])
                result = check_report.check_report(self.report, handover=True)
                self.assertEqual(result["ok"], expected is None, result)
                if expected:
                    self.assertEqual(
                        sum(expected in e for e in result["errors"]), 2, result)

    def test_unlinked_tickets_and_pull_requests_fail_every_check(self):
        # In the ledger and the report alike, at handover or not: the scripts
        # link them, so one left bare is an error at once.
        link = "[PROJ-1](https://example.atlassian.net/browse/PROJ-1) and [#2](https://github.com/acme/app/pull/2)"
        cases = [
            ("linked", link, None),
            ("a ticket key", "See PROJ-1.", "PROJ-1"),
            ("a bare pull request", "See PR #2.", "#2"),
            ("a pull request with its repository", "See acme/app#3.", "acme/app#3"),
            ("a heading is left alone", "#### Flow for PROJ-1", None),
        ]
        for handover in (False, True):
            for name, sentence, expected in cases:
                with self.subTest(name, handover=handover):
                    (self.folder / "ledger.md").write_text(
                        LEDGER.replace(
                            "## Boundary\n\nNone yet.",
                            "## Boundary\n\n" + sentence), encoding="utf-8")
                    self.report.write_text(
                        self.text + "\n" + sentence + "\n", encoding="utf-8")
                    result = check_report.check_report(
                        self.report, handover=handover)
                    self.assertEqual(result["ok"], expected is None, result)
                    if expected:
                        self.assertEqual(
                            sum("without a link" in e and expected in e for e in result["errors"]), 2, result)

    def test_handover_closing_rules(self):
        # A completed action names its answer; a component's status is an allowed one, and one claiming
        # code rests on code read under its path.
        tree = "https://github.com/acme/app/tree/abc/services/search"
        component = ("## Component inventory and evolution\n\n| ID | Name | Responsibility | Repository | Status |"
                     " Read | Evidence | Next |\n| --- | --- | --- | --- | --- | --- | --- | --- |\n"
                     "| C01 | search | Serves | [search][search] | {} | d | G01 | n |\n")
        coverage = ("### File reading coverage\n\n| Source | Material | Depth |\n| --- | --- | --- |\n"
                    "| S01 | [routes](https://github.com/acme/app/blob/abc/services/search/{}) | {} |\n")
        cases = [
            ("an answered action", "G01", "⬜ Unverified",
             ("README.md", "README"), None),
            ("an action with no answer", "—", "⬜ Unverified",
             ("README.md", "README"), "Q01: a completed action"),
            ("a user rejection", "Rejected by the user: not needed", "⬜ Unverified",
             ("README.md", "README"), None),
            ("a status not allowed", "G01", "Done",
             ("README.md", "README"), "C01: Status starts with"),
            ("code claimed from a README", "G01", "🟩 Implemented", ("README.md", "README"),
             "C01 links acme/app: services/search"),
            ("code claimed from its routes", "G01", "🟩 Implemented",
             ("src/routes.py", "entrypoints and routes"), None),
        ]
        for name, outcome, status, (path, depth), expected in cases:
            with self.subTest(name):
                text = (LEDGER.replace("| G01 |", f"| {outcome} |")
                        .replace("## Component inventory and evolution\n\nNone yet.", component.format(status))
                        .replace("### File reading coverage\n\nNone yet.", coverage.format(path, depth))
                        .replace("## Links\n\nNone yet.", f"## Links\n\n[search]: {tree}"))
                (self.folder / "ledger.md").write_text(text, encoding="utf-8")
                result = check_report.check_report(self.report, handover=True)
                self.assertEqual(result["ok"], expected is None, result)
                if expected:
                    self.assertIn(expected, " ".join(result["errors"]))

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
                text = text.replace("## Boundary\n\nNone yet.",
                                    "## Boundary\n\n" + body.split("\n\n## Links")[0])
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
        text = LEDGER.replace("## Boundary\n\nNone yet.",
                              "## Boundary\n\n" + sentence)
        text = text.replace("## Links\n\nNone yet.", "## Links\n\n" + links)
        (self.folder / "ledger.md").write_text(text, encoding="utf-8")
        result = check_report.check_report(self.report, handover=True)
        self.assertTrue(result["ok"], result)

    def test_long_claims_warn_and_unrecorded_ids_fail_at_handover(self):
        ledger = self.folder / "ledger.md"
        finding = "### F01 — Search is merged\n\n" + "\n".join(
            f"- **{field}:** " + ("word " * 160 if field == "Claim" else "text.") for field in check_report.FINDING_FIELDS)
        ledger.write_text(LEDGER.replace("## Findings and validation chains\n\nNone yet.",
                                         "## Findings and validation chains\n\n" + finding), encoding="utf-8")
        _, warnings = check_report.check_ledger(ledger)
        self.assertIn("claim is 160 words", " ".join(warnings))
        ledger.write_text(LEDGER.replace("## Boundary\n\nNone yet.",
                                         "## Boundary\n\nSee S07 and Q03; Q4 is a quarter."), encoding="utf-8")
        self.assertEqual(check_report.check_ledger(
            ledger, handover=False)[0], [])
        errors, _ = check_report.check_ledger(ledger, handover=True)
        self.assertIn("IDs cited but never recorded: Q03, S07",
                      " ".join(errors))

    def test_unreadable_missing_and_relative_report(self):
        for path in ("relative.md", self.folder / "missing.md"):
            with self.subTest(path=str(path)):
                self.assertFalse(check_report.check_report(path)["ok"])
        self.report.write_bytes(b"\xff")
        self.assertIn("UTF-8", " ".join(self.check()["errors"]))

    def test_cli_json_and_exit_status(self):
        for path, status in ((self.report, 0), (self.folder / "missing.md", 1)):
            with self.subTest(status=status), contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(check_report.main(
                    ["--report", str(path)]), status)
                self.assertEqual(json.loads(output.getvalue())
                                 ["ok"], status == 0)


if __name__ == "__main__":
    unittest.main()
