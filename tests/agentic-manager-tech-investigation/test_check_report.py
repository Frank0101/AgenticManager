# Unit tests for skills/agentic-manager-tech-investigation/scripts/check_report.py.
# The whole script has end-to-end tests in test_e2e_check_report.py.
# Run with: python3 tests/run.py agentic-manager-tech-investigation
#
# Each test writes an invented report, ledger and maps to a temporary folder;
# check_report() reads no config.
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

LEDGER = ledger_skeleton("Acme").replace(
    "## Decisions and precise evidence gaps\n\nNone yet.",
    "## Decisions and precise evidence gaps\n\n### G1\n\nEvidence unavailable.")


class CheckReportTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.report = self.folder / "Acme_Report.md"
        (self.folder / "ledgers.md").write_text(LEDGER, encoding="utf-8")
        prep = []
        parts = [
            "# Acme\n\nEvidence snapshot: today. [Research ledger](ledgers.md).\n"]
        for level, title in HEADINGS:
            parts.append("#" * level + " " + title + "\n\n")
            if title == "Roadmap":
                parts.append("| Stage | Intended outcome | Commitment and evidence | Dependencies |\n"
                             "| --- | --- | --- | --- |\n")
                for stage in check_report.ROADMAP_STAGES:
                    parts.append(
                        f"| {stage} | Search improvements | Proposed [document](https://example.com/plan) | Review |\n")
            elif title in check_report.MAPS:
                filename = check_report.MAPS[title]
                (self.folder / filename).write_text(
                    '<svg xmlns="http://www.w3.org/2000/svg"/>', encoding="utf-8")
                parts.append(f"Architecture summary with [code](https://example.com/code).\n\n"
                             f"![{title}]({filename})\n\n"
                             "```mermaid\nsequenceDiagram\nautonumber\n"
                             "Client->>Service: Search\n```\n\n"
                             "The service responds to the client; [code](https://example.com/code) establishes this flow.\n\n")
                prep.append(
                    f"## {title}\n\n{filename}\n\n```mermaid\nflowchart LR\nClient --> Service\n```\n")
            elif title == "Technical decisions and gaps":
                parts.append("| Decision | Options and tradeoffs | Rationale and evidence | Status | Owner |\n"
                             "| --- | --- | --- | --- | --- |\n"
                             "| Storage | Cache or index | [Proposal](https://example.com/proposal) | Open | Not established |\n")
            else:
                parts.append(
                    "Account supported by [source](https://example.com/evidence).\n\n")
        self.text = "".join(parts)
        self.report.write_text(self.text, encoding="utf-8")
        (self.folder / "mermaids.md").write_text("\n".join(prep), encoding="utf-8")

    def check(self, text=None):
        if text is not None:
            self.report.write_text(text, encoding="utf-8")
        return check_report.check_report(self.report)

    def test_accepted_reports(self):
        # Each variant passes, with this many warnings, and the check writes
        # nothing.
        proposal = "[Proposal](https://example.com/proposal)"
        row = "| Storage | Cache or index | [Proposal](https://example.com/proposal) | Open | Not established |"
        image = "![Current architecture](architecture-as-is.svg)"
        start, end = self.text.index(
            "Architecture summary"), self.text.index("### Next evolution")
        (self.folder / "extra evidence.md").write_text("Evidence", encoding="utf-8")
        cases = [
            ("the complete report", self.text, 0),
            ("a shortcut reference link citing a table row",
             self.text.replace(proposal, "[Proposal]") + "\n[Proposal]: https://example.com/proposal\n", 0),
            ("an unknown row", self.text.replace(
                row, "| Storage | Not established | Evidence unavailable | Unverified | Not established |"), 0),
            ("a row citing a ledger gap", self.text.replace(
                row, "| Storage | Cache or index | [G1](ledgers.md#g1) | Open | Not established |"), 0),
            ("reference links, encoded paths and fences", self.text.replace(proposal, "[Proposal][proof]")
             + "\n[proof]: https://example.com/proposal\n[Local](<extra%20evidence.md>)\n"
             "```text\n## Fake heading\n[Not a link](missing.md)\n```\n", 0),
            ("explicit evidence gaps instead of the map and flow", self.text[:start]
             + "Map evidence gap: architecture placement is unavailable.\n\n"
             "Flow evidence gap: sequence not established. [G1](ledgers.md#g1).\n\n" + self.text[end:], 0),
            ("the documented fallback without Node.js", self.text.replace(
                image, "Node.js unavailable; map layout is unchecked.\n\n"
                "```mermaid\nflowchart LR\nClient --> Service\n```"), 1),
            # Between a map and its sequence, a title or a width container is
            # fine; anything else is for the agent to review.
            ("a title after the map", self.text.replace(
                image, image + "\n\n#### Search flow", 1), 0),
            ("a width container after the map", self.text.replace(
                image, image + '\n\n<div style="width:62.42%; margin:0 auto;">', 1), 0),
            ("other HTML after the map", self.text.replace(
                image, image + '\n\n<div style="zoom:2">', 1), 1),
            ("prose after the map", self.text.replace(
                image, image + "\n\nThis paragraph explains the structure.", 1), 1),
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
        image = "![Current architecture](architecture-as-is.svg)"
        sequence = "```mermaid\nsequenceDiagram\nautonumber\nClient->>Service: Search\n```"
        commentary = "The service responds to the client; [code](https://example.com/code) establishes this flow."
        flowchart = "\n```mermaid\nflowchart LR\nA --> B\n```"
        (self.folder / "broken.svg").write_text("<svg>", encoding="utf-8")
        (self.folder / "other.svg").write_text("<document/>", encoding="utf-8")
        cases = [
            # Structure
            ("missing section", self.text.replace(
                "### Key decisions and risks", "#### Key decisions and risks"), "H2/H3"),
            ("extra section", self.text + "\n## Engineering\n", "H2/H3"),
            ("roadmap order", self.text.replace("| Current milestone |",
             "| Next milestones |", 1), "Roadmap table"),
            ("missing roadmap row", "\n".join(line for line in self.text.splitlines(
            ) if not line.startswith("| Next milestones |")), "Roadmap table"),
            # Citations: an unknown owner doesn't excuse a row from its link.
            ("a row without a source", self.text.replace(
                "[Proposal](https://example.com/proposal)", "Lower latency"), "point-of-use source link"),
            ("an undefined shortcut reference", self.text.replace(
                "[Proposal](https://example.com/proposal)", "[Proposal]"), "table row needs"),
            # Local files
            ("missing image", self.text +
             "\n![Map](missing.svg)", "local link target is missing"),
            ("missing document", self.text +
             "\n[Details](absent.md#section)", "local link target is missing"),
            ("unresolved reference", self.text +
             "\n[Details][absent]", "unresolved Markdown"),
            ("bad XML", self.text +
             "\n![Map](broken.svg)", "not valid SVG XML"),
            ("wrong root", self.text +
             "\n![Map](other.svg)", "not valid SVG XML"),
            # Maps, sequences and their commentary
            ("missing sequence", self.text.replace(
                sequence, "", 1), "native Mermaid sequence"),
            ("wrong order", self.text.replace(image + "\n\n" + sequence,
             sequence + "\n\n" + image, 1), "map must precede"),
            ("no commentary", self.text.replace(
                commentary, "", 1), "shared commentary"),
            ("no map", self.text.replace(image, "", 1),
             "embed architecture-as-is.svg"),
            ("duplicate map", self.text.replace(
                image, image + "\n" + flowchart), "duplicated map source"),
            ("appendix map source", self.text +
             flowchart, "not elsewhere in the report"),
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

    def test_preparation_sources(self):
        prep = self.folder / "mermaids.md"
        original = prep.read_text(encoding="utf-8")
        cases = [
            (original.replace("architecture-next.svg", "other.svg"),
             "architecture-next.svg map source"),
            (original + "\n```mermaid\nsequenceDiagram\nA->>B: Search\n```\n",
             "map sources only"),
            (original + "\n```mermaid\nflowchart LR\n", "unclosed code fence"),
        ]
        for text, expected in cases:
            with self.subTest(expected=expected):
                prep.write_text(text, encoding="utf-8")
                self.assertIn(expected, " ".join(self.check()["errors"]))

    def test_skipped_sections_follow_content_json(self):
        content = self.folder / "content.json"
        content.write_text('{"skip": ["evolution"]}', encoding="utf-8")
        self.assertIn("H2/H3 headings", " ".join(self.check()["errors"]))
        text = self.text
        for title in ("Roadmap", "Next evolution", "Target architecture"):
            start = text.index("### " + title + "\n")
            end = text.index("\n### ", start + 4) + 1
            text = text[:start] + text[end:]
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
        reflected = LEDGER.replace("## Correction history\n\nNone yet.",
                                   "## Correction history\n\n### Reflection\n\nConverged.")
        cases = [(LEDGER, False, "Reflection"), (reflected, True, None),
                 (ready.replace("## Correction history\n\nNone yet.",
                                "## Correction history\n\n### Reflection\n\nConverged."), False, "still ready")]
        for text, ok, expected in cases:
            with self.subTest(expected=expected):
                ledger.write_text(text, encoding="utf-8")
                self.assertTrue(check_report.check_report(self.report)["ok"])
                result = check_report.check_report(self.report, handover=True)
                self.assertEqual(result["ok"], ok, result)
                if expected:
                    self.assertIn(expected, " ".join(result["errors"]))

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
