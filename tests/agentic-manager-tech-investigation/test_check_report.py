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
import re
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

LEDGER = ledger_skeleton("Acme").replace(
    "## Evidence gaps\n\nNone yet.",
    "## Evidence gaps\n\n### G1\n\nEvidence unavailable.")


class CheckReportTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.report = self.folder / "Acme_Report.md"
        (self.folder / "ledgers.md").write_text(LEDGER, encoding="utf-8")
        parts = [
            "# Acme\n\nEvidence snapshot: today. [Research ledger](ledgers.md).\n"]
        for level, title, ident in HEADINGS:
            parts.append("#" * level + " " + title + "\n\n")
            if ident in ("arch.current", "arch.next"):
                parts.append("Architect text with [code](https://example.com/code).\n\n"
                             "#### Search flow\n\n"
                             "```mermaid\nsequenceDiagram\nautonumber\n"
                             "Client->>Service: Search\n```\n\n")
            elif ident == "arch.decisions":
                parts.append("| Decision | Options and tradeoffs | Rationale and evidence | Status |\n"
                             "| --- | --- | --- | --- |\n"
                             "| Storage | Cache or index | [Proposal](https://example.com/proposal) | Open |\n")
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
        row = "| Storage | Cache or index | [Proposal](https://example.com/proposal) | Open |"
        sequence = self.text[self.text.index("#### Search flow"):self.text.index(
            "```\n\n", self.text.index("```mermaid")) + 5]
        (self.folder / "extra evidence.md").write_text("Evidence", encoding="utf-8")
        cases = [
            ("the complete report", self.text, 0),
            ("a shortcut reference link citing a table row",
             self.text.replace(proposal, "[Proposal]") + "\n[Proposal]: https://example.com/proposal\n", 0),
            ("an unknown row", self.text.replace(
                row, "| Storage | Not established | Evidence unavailable | Unverified |"), 0),
            ("a row citing a ledger gap", self.text.replace(
                row, "| Storage | Cache or index | [G1](ledgers.md#g1) | Open |"), 0),
            ("reference links, encoded paths and fences", self.text.replace(proposal, "[Proposal][proof]")
             + "\n[proof]: https://example.com/proposal\n[Local](<extra%20evidence.md>)\n"
             "```text\n## Fake heading\n[Not a link](missing.md)\n```\n", 0),
            ("an explicit flow gap instead of the sequence", self.text.replace(
                sequence, "Flow evidence gap: sequence not established. [G1](ledgers.md#g1).\n\n", 1), 0),
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
        sequence = "```mermaid\nsequenceDiagram\nautonumber\nClient->>Service: Search\n```"
        text_before = "Architect text with [code](https://example.com/code).\n\n"
        flowchart = "\n```mermaid\nflowchart LR\nA --> B\n```"
        cases = [
            # Structure
            ("missing section", self.text.replace(
                "### Key decisions and risks", "#### Key decisions and risks"), "H2/H3"),
            ("extra section", self.text + "\n## Engineering\n", "H2/H3"),
            # Citations: an unknown owner doesn't excuse a row from its link.
            ("a row without a source", self.text.replace(
                "[Proposal](https://example.com/proposal)", "Lower latency"), "point-of-use source link"),
            ("an undefined shortcut reference", self.text.replace(
                "[Proposal](https://example.com/proposal)", "[Proposal]"), "table row needs"),
            # Local files
            ("missing image", self.text +
             "\n![Picture](missing.png)", "local link target is missing"),
            ("missing document", self.text +
             "\n[Details](absent.md#section)", "local link target is missing"),
            ("unresolved reference", self.text +
             "\n[Details][absent]", "unresolved Markdown"),
            # The architect summary: text, then one sequence
            ("missing sequence", self.text.replace(
                sequence, "", 1), "native Mermaid sequence"),
            ("two sequences", self.text.replace(
                sequence, sequence + "\n\n#### Second flow\n\n" + sequence, 1), "expected one sequence"),
            ("no text before the sequence", self.text.replace(
                text_before, "", 1), "add the text before the sequence"),
            ("a map", self.text + flowchart, "sequence diagrams only"),
        ]
        for name, text, expected in cases:
            with self.subTest(name):
                result = self.check(text)
                self.assertFalse(result["ok"])
                self.assertIn(expected, " ".join(result["errors"]))

    def test_links_into_the_ledger_must_name_a_heading(self):
        (self.folder / "ledgers.md").write_text(
            "# Research\n\n## G1\nGap.\n\n### F03 — Delivery is exploration\n\n## Repeat\n\n## Repeat\n", encoding="utf-8")
        cases = [("[F03](ledgers.md#f03--delivery-is-exploration)", True), ("[gap](ledgers.md#g1)", True),
                 ("[second](ledgers.md#repeat-1)", True), ("[gone](ledgers.md#f99--missing)", False)]
        for link, ok in cases:
            with self.subTest(link=link):
                errors = self.check(self.text.replace(
                    "[Research ledger](ledgers.md)", link))["errors"]
                self.assertEqual(
                    any("has no heading for" in e for e in errors), not ok, errors)

    def test_skipped_sections_follow_content_json(self):
        content = self.folder / "content.json"
        content.write_text('{"skip": ["evolution"]}', encoding="utf-8")
        self.assertIn("H2/H3 headings", " ".join(self.check()["errors"]))
        text = re.sub(
            r"### Next steps and evolution\n.*?(?=\n#{2,3} )", "", self.text, flags=re.S)
        text = text.replace("\n\n\n", "\n\n")
        self.assertTrue(self.check(text)["ok"], self.check(text))
        content.unlink()
        self.assertIn("H2/H3 headings", " ".join(self.check(text)["errors"]))

    def test_ledger_structure(self):
        ledger = self.folder / "ledgers.md"
        finding = ("### F01 — Search is merged\n\n" +
                   "\n".join(f"**{field}:** text." for field in check_report.FINDING_FIELDS))
        complete = LEDGER.replace("## Findings and validation chains\n\nNone yet.",
                                  "## Findings and validation chains\n\n" + finding)
        cases = [
            ("complete", complete, None, None),
            ("section order", complete.replace("## Resume here",
             "## Summary"), "sections must be exactly", None),
            ("queue subsections", complete.replace(
                "### Blocked", "### Waiting"), "queue needs exactly", None),
            ("duplicate finding", complete + "\n" +
             finding, "duplicate findings: F01", None),
            ("undefined finding", complete.replace(
                "None yet.", "See F07.", 1), "never written: F07", None),
            ("missing fields", complete.replace(
                "**Kind:** text.", ""), None, "F01 lacks Kind"),
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
        ledger = self.folder / "ledgers.md"
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

    def test_handover_needs_empty_ready_queue_and_reflection(self):
        ledger = self.folder / "ledgers.md"
        ready = LEDGER.replace("### Ready / in progress\n\n", "### Ready / in progress\n\n"
                               "| Q01 | Start | Read code | Code | — | High | In progress | — |\n\n", 1)
        reflected = LEDGER.replace("## Reflection\n\nNone yet.",
                                   "## Reflection\n\nConverged.")
        cases = [(LEDGER, False, "Reflection"), (reflected, True, None),
                 (ready.replace("## Reflection\n\nNone yet.",
                                "## Reflection\n\nConverged."), False, "still ready")]
        for text, ok, expected in cases:
            with self.subTest(expected=expected):
                ledger.write_text(text, encoding="utf-8")
                self.assertTrue(check_report.check_report(self.report)["ok"])
                result = check_report.check_report(self.report, handover=True)
                self.assertEqual(result["ok"], ok, result)
                if expected:
                    self.assertIn(expected, " ".join(result["errors"]))

    def test_handover_allows_only_the_skills_files(self):
        reflected = LEDGER.replace("## Reflection\n\nNone yet.",
                                   "## Reflection\n\nConverged.")
        (self.folder / "ledgers.md").write_text(reflected, encoding="utf-8")
        for name in ("content.json", ".DS_Store", "exec-summary.json", "exec-summary.md"):
            (self.folder / name).write_text("{}", encoding="utf-8")
        self.assertTrue(check_report.check_report(
            self.report, handover=True)["ok"])
        for stray in ("notes.md", "draft.json", "diagram.mmd"):
            with self.subTest(stray):
                (self.folder / stray).write_text("x", encoding="utf-8")
                self.assertTrue(check_report.check_report(self.report)["ok"])
                result = check_report.check_report(self.report, handover=True)
                self.assertFalse(result["ok"])
                self.assertIn(f"Unexpected files in the investigation folder: {stray}", " ".join(
                    result["errors"]))
                (self.folder / stray).unlink()
        # The maps are gone: their files are unexpected now.
        for name in ("maps.json", "mermaids.md", "architecture-as-is.svg"):
            (self.folder / name).write_text("x", encoding="utf-8")
        self.assertIn("maps.json", " ".join(
            check_report.check_report(self.report, handover=True)["errors"]))

    def test_handover_needs_links_to_sources(self):
        # A register row links its exact reference, a coverage row the material read; a search record is exempt.
        reflected = LEDGER.replace("## Reflection\n\nNone yet.",
                                   "## Reflection\n\nConverged.")
        header = "| Source ID | Group / evidence kind | Exact reference | Revision | Read | Limits |\n| --- | --- | --- | --- | --- | --- |\n"
        coverage = "### File reading coverage\n\n| Source | Material | Depth | Findings |\n| --- | --- | --- | --- |\n"
        cases = [
            ("linked rows", "| S01 | source_control / implementation | [repo](https://github.com/acme/app/tree/abc123) | abc123 | x | y |\n"
             "| S02 | source_control / search record | a GitHub code search | today | x | y |\n",
             "| S01 | [`a.md`](https://github.com/acme/app/blob/abc123/a.md) | Full | G1 |\n", None),
            ("an unlinked source", "| S01 | source_control / implementation | `acme/app` | abc123 | x | y |\n",
             "| S01 | [`a.md`](https://github.com/acme/app/blob/abc123/a.md) | Full | G1 |\n", "register rows without a link"),
            ("an unlinked file", "| S01 | source_control / implementation | [repo](https://github.com/acme/app/tree/abc123) | abc123 | x | y |\n",
             "| S01 | `a.md` | Full | G1 |\n", "File reading coverage rows without a link"),
        ]
        for name, register, files, expected in cases:
            with self.subTest(name):
                text = reflected.replace("## Revisions and source register\n\n",
                                         "## Revisions and source register\n\n" + header + register, 1)
                text = text.replace(
                    "### File reading coverage\n\nNone yet.", coverage + files)
                (self.folder / "ledgers.md").write_text(text, encoding="utf-8")
                self.assertTrue(check_report.check_report(self.report)["ok"])
                result = check_report.check_report(self.report, handover=True)
                self.assertEqual(result["ok"], expected is None, result)
                if expected:
                    self.assertIn(expected, " ".join(result["errors"]))

    def test_handover_rejects_unlinked_backticks(self):
        # A backticked reference is a link to its revision; plain words and the text of a link are fine.
        reflected = LEDGER.replace("## Reflection\n\nNone yet.",
                                   "## Reflection\n\nConverged.")
        cases = [
            ("a linked reference",
             "[`app.py`](https://github.com/acme/app/blob/abc123/app.py) holds it.", None),
            ("plain words", "The master branch holds it.", None),
            ("an unlinked reference", "See `app.py` and `acme/app`.",
             "references in backticks without a link: `app.py`, `acme/app`"),
        ]
        for name, sentence, expected in cases:
            with self.subTest(name):
                (self.folder / "ledgers.md").write_text(
                    reflected.replace("## Boundary, method and access\n\nNone yet.",
                                      "## Boundary, method and access\n\n" + sentence), encoding="utf-8")
                self.report.write_text(
                    self.text + "\n" + sentence + "\n", encoding="utf-8")
                self.assertTrue(check_report.check_report(self.report)["ok"])
                result = check_report.check_report(self.report, handover=True)
                self.assertEqual(result["ok"], expected is None, result)
                if expected:
                    self.assertEqual(
                        sum(expected in e for e in result["errors"]), 2, result)

    def test_handover_rejects_unlinked_tickets_and_pull_requests(self):
        reflected = LEDGER.replace("## Reflection\n\nNone yet.",
                                   "## Reflection\n\nConverged.")
        link = "[PROJ-1](https://example.atlassian.net/browse/PROJ-1) and [#2](https://github.com/acme/app/pull/2)"
        cases = [
            ("linked", link, None),
            ("a ticket key", "See PROJ-1.", "PROJ-1"),
            ("a pull request", "See PR #2.", "#2"),
            ("a heading is left alone", "#### Flow for PROJ-1", None),
        ]
        for name, sentence, expected in cases:
            with self.subTest(name):
                (self.folder / "ledgers.md").write_text(
                    reflected.replace("## Boundary, method and access\n\nNone yet.",
                                      "## Boundary, method and access\n\n" + sentence), encoding="utf-8")
                self.report.write_text(
                    self.text + "\n" + sentence + "\n", encoding="utf-8")
                result = check_report.check_report(self.report, handover=True)
                self.assertEqual(result["ok"], expected is None, result)
                if expected:
                    self.assertEqual(
                        sum("without a link" in e and expected in e for e in result["errors"]), 2, result)

    def test_reference_links_need_definitions(self):
        # `[text][key]` takes its URL from a definition in ## Links: an undefined key is an error, an unused one a warning.
        ledger = self.folder / "ledgers.md"
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
                text = text.replace("## Boundary, method and access\n\nNone yet.",
                                    "## Boundary, method and access\n\n" + body.split("\n\n## Links")[0])
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
        reflected = LEDGER.replace("## Reflection\n\nNone yet.",
                                   "## Reflection\n\nConverged.")
        sentence = "See [`app.py`][app], [PROJ-1][proj-1] and [#2][pr-2]."
        links = "[app]: https://github.com/acme/app/blob/abc/app.py\n[pr-2]: https://github.com/acme/app/pull/2\n[proj-1]: https://example.atlassian.net/browse/PROJ-1"
        text = reflected.replace("## Boundary, method and access\n\nNone yet.",
                                 "## Boundary, method and access\n\n" + sentence)
        text = text.replace("## Links\n\nNone yet.", "## Links\n\n" + links)
        (self.folder / "ledgers.md").write_text(text, encoding="utf-8")
        result = check_report.check_report(self.report, handover=True)
        self.assertTrue(result["ok"], result)

    def test_long_claims_warn_and_unrecorded_ids_fail_at_handover(self):
        reflected = LEDGER.replace("## Reflection\n\nNone yet.",
                                   "## Reflection\n\nConverged.")
        ledger = self.folder / "ledgers.md"
        finding = "### F01 — Search is merged\n\n" + "\n".join(
            f"- **{field}:** " + ("word " * 160 if field == "Claim" else "text.") for field in check_report.FINDING_FIELDS)
        ledger.write_text(reflected.replace("## Findings and validation chains\n\nNone yet.",
                                            "## Findings and validation chains\n\n" + finding), encoding="utf-8")
        _, warnings = check_report.check_ledger(ledger)
        self.assertIn("claim is 160 words", " ".join(warnings))
        ledger.write_text(reflected.replace("## Boundary, method and access\n\nNone yet.",
                                            "## Boundary, method and access\n\nSee S07 and Q03; Q4 is a quarter."), encoding="utf-8")
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
