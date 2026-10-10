"""Unit tests for skills/agentic-manager-tech-investigation/scripts/make_report.py.
The whole pipeline has end-to-end tests in test_e2e_pipeline.py.
Run with: python3 tests/run.py agentic-manager-tech-investigation

The Mermaid CLI is never run here: render_many() is patched. The config's path
is patched to the test's own config, in a temporary folder.
"""

import json
import os
import sys
import unittest
from unittest import mock

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(TEST_DIR))
sys.path.insert(0, os.path.join(REPO_ROOT, "skills",
                os.path.basename(TEST_DIR), "scripts"))
import make_report  # noqa: E402
import output_diagram  # noqa: E402
sys.path.insert(0, TEST_DIR)
from investigation_fixture import (INVESTIGATION, LEDGER, PUBLISH, QUERY, content,  # noqa: E402
                                   temp_output)


class MakeReportTest(unittest.TestCase):
    def setUp(self):
        self.folder = os.path.join(temp_output(self), INVESTIGATION)
        os.makedirs(self.folder)
        self.write("ledgers.md", LEDGER)

    def write(self, name, text):
        with open(os.path.join(self.folder, name), "w", encoding="utf-8") as f:
            f.write(text)

    def render(self, sources):
        return ['<svg viewBox="0 0 600 100"/>' for _ in sources]

    def make(self, data=None, render=None):
        self.write("content.json", json.dumps(
            content() if data is None else data))
        with mock.patch.object(output_diagram, "render_many", side_effect=render or self.render):
            return make_report.make_report(INVESTIGATION)

    def report(self):
        with open(os.path.join(self.folder, "Acme-Search_Report.md"), encoding="utf-8") as f:
            return f.read()

    def problems(self, data):
        with self.assertRaises(SystemExit) as raised:
            self.make(data)
        self.assertFalse(os.path.exists(os.path.join(
            self.folder, "Acme-Search_Report.md")))
        return str(raised.exception)

    def test_report_passes_the_check(self):
        result = self.make()
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["warnings"], [])
        self.assertEqual(result["sequences"], [
                         QUERY["title"], PUBLISH["title"]])

    def test_template(self):
        self.make()
        text = self.report()
        for expected in [
            "# Acme search\n\nEvidence snapshot: 5 October 2026. Code links pin inspected commits;",
            "These items describe implications of the linked evidence.\n\n"
            "| Decision or risk | Why it matters | Established position | Evidence |\n| --- | --- | --- | --- |\n"
            "| Index choice | Affects cost | Unresolved | [proposal](https://example.com/p)",
            "## Architect summary\n\n### Current status\n\n",
            "\n\n#### Search API — query\n\n"
            "```mermaid\nsequenceDiagram\n    autonumber\n    actor U as Client / operator\n",
            "### Next steps and evolution\n\n",
            "\n\n#### Publish job — publication\n\n```mermaid\nsequenceDiagram",
            "[code](ledgers.md#f01--search-api-is-merged)",
            "[gap](ledgers.md#evidence-gaps)",
            "### Key decisions and gaps\n\nThe table records source-backed decisions and evidence gaps. It does "
            "not select an option.\n\n| Decision or gap | Why it matters | Established position | Evidence |\n"
            "| --- | --- | --- | --- |\n| Index | Sets the cost | Unresolved | [gap](ledgers.md#evidence-gaps) |",
            "\n\n## References\n\n**Implementation and configuration**",
            "**Delivery**\n\n- [PROJ-1](https://example.com/PROJ-1) (historical)",
            "**Vision, rationale and reported operational gaps**\n\nNone in the inspected sources.",
            "The [research ledger](ledgers.md) holds the full validation trail",
        ]:
            with self.subTest(expected=expected[:40]):
                self.assertIn(expected, text)
        self.assertEqual(text.count("### Current status\n"), 2)
        self.assertEqual(text.count("### Next steps and evolution\n"), 2)
        for absent in ("![", "Reading the design and flows", "Current architecture", "Target architecture"):
            self.assertNotIn(absent, text)

    def test_deterministic(self):
        self.make()
        first = self.report()
        self.make()
        self.assertEqual(self.report(), first)

    def test_content_problems(self):
        def change(edit):
            data = content()
            edit(data)
            return data
        stage = lambda data, key="current": data["architecture"][key]  # noqa: E731
        # name: (edit to content.json, expected in the problems)
        cases = [
            ("heading in prose", lambda d: d["problem"].append(
                "### Extra"), "no # to ### headings"),
            ("fence in prose", lambda d: d["current_status"].append(
                "```mermaid\nflowchart LR\n```"), "no code fences"),
            ("multi-line cell",
             lambda d: d["key_decisions"][0].update(decision="a\nb"), "one line"),
            ("claim without a ledger link", lambda d: d["next_steps"].append("A claim with no trace."),
             "next_steps paragraph 2: needs a ledger link"),
            ("a source link is not a ledger link", lambda d: d["key_decisions"][0].update(
                evidence="[p](https://example.com/p)"), "key_decisions 1.evidence: needs a ledger link"),
            ("renamed item", lambda d: d["key_decisions"][0].update(item="x"),
             "key_decisions 1.item: renamed decision"),
            ("removed status", lambda d: d["decisions_and_gaps"][0].update(status="Open"),
             "decisions_and_gaps 1.status: removed"),
            ("removed roadmap", lambda d: d.update(
                roadmap={}), "roadmap: removed"),
            ("renamed deep dive", lambda d: d.update(
                deep_dive=["x"]), "deep_dive: renamed current_status"),
            ("removed role column", lambda d: d["key_decisions"][0].update(role="Platform lead"),
             "key_decisions 1.role: removed"),
            ("missing field", lambda d: d["key_decisions"][0].pop(
                "why"), "key_decisions 1.why: needs text"),
            ("unknown ledger ID", lambda d: d["problem"].append(
                "[x](ledger:F09)"), "ledger:F09 matches no heading"),
            ("bad date", lambda d: d.update(
                evidence_snapshot="5/10/2026"), "evidence_snapshot"),
            ("summary without a ledger link", lambda d: stage(d).update(summary=["No trace."]),
             "architecture.current.summary paragraph 1: needs a ledger link"),
            ("semicolon", lambda d: stage(d)["sequence"]["lines"].append("A->>D: read; write"),
             "raw semicolon"),
            ("manual number", lambda d: stage(d)["sequence"]["lines"].append("A->>D: 5. Read"),
             "numbers its step"),
            ("title missing", lambda d: stage(d)["sequence"].update(
                title=""), "needs a one-line title"),
            ("lines not a list", lambda d: stage(d)["sequence"].update(lines="U->>A: Query"),
             "lines must be a list of Mermaid lines"),
            ("sequence not an object", lambda d: stage(d).update(sequence="U->>A: Query"),
             "architecture.current.sequence: must be an object"),
            ("removed fields", lambda d: stage(d).update(sequences=[QUERY], commentary=["x"], map_gap="y"),
             "unknown sequences, commentary, map_gap"),
            ("no sequence nor gap", lambda d: stage(d).pop(
                "sequence"), "needs a sequence, or a flow_gap"),
            ("stage missing", lambda d: d["architecture"].pop(
                "next"), "architecture.next: missing"),
            ("architecture empty", lambda d: d.update(architecture={}),
             "architecture: needs current and next"),
            ("old stage names", lambda d: d["architecture"].update(target=stage(d)),
             "architecture.target: the report doesn't show this section"),
        ]
        for name, edit, expected in cases:
            with self.subTest(name):
                self.assertIn(expected, self.problems(change(edit)))

    def test_multiline_sequence_statements_are_all_checked(self):
        data = content()
        data["architecture"]["current"]["sequence"] = {
            "title": QUERY["title"], "lines": ["\n".join(QUERY["lines"])]}
        self.assertTrue(self.make(data)["ok"])
        self.assertIn("U->>A: Query\n    A->>D: Read rows", self.report())
        original = self.report()
        for name, extra, expected in (("manual number", "A-->>U: 5. Results", "numbers its step"),
                                      ("semicolon", "A->>U: One; two", "raw semicolon")):
            with self.subTest(name=name):
                data["architecture"]["current"]["sequence"]["lines"] = [
                    "\n".join(QUERY["lines"]) + "\n" + extra]
                with self.assertRaisesRegex(SystemExit, expected):
                    self.make(data)
                self.assertEqual(self.report(), original)

    def test_ledger_definitions_exclude_fences(self):
        for definition in ("| G99 | Evidence |", "- **G99** Evidence."):
            for fence, closing in (("```markdown", "```"), ("~~~~", "~~~~")):
                for genuine in (False, True):
                    with self.subTest(definition=definition, fence=fence, genuine=genuine):
                        text = (LEDGER + "\n\n### Illustration\n\n" + fence + "\n"
                                + definition + "\n" + closing + "\n")
                        if genuine:
                            text += "\n### Actual gap\n\n" + definition + "\n"
                        self.write("ledgers.md", text)
                        ledger = make_report.Ledger(
                            os.path.join(self.folder, "ledgers.md"))
                        self.assertEqual(ledger.anchor("G99"),
                                         "actual-gap" if genuine else None)

    def test_invalid_collections_preserve_existing_report(self):
        self.make()
        original = self.report()
        for field in ("references", "skip"):
            for value in (1, "wrong", {}):
                with self.subTest(field=field, value=value):
                    data = content()
                    if field == "references":
                        data[field]["implementation"] = value
                        expected = "references.implementation: needs a list"
                    else:
                        data[field] = value
                        expected = "skip: must list the dimensions"
                    with self.assertRaisesRegex(SystemExit, expected):
                        self.make(data)
                    self.assertEqual(self.report(), original)

    def test_key_decisions_sentence(self):
        cases = [
            (["Cost"], "These items describe implications of the linked evidence.\n\n| Decision or risk | Why it matters |"),
            ([], "No decision, blocker or risk in the inspected evidence warrants technical-leadership attention."),
        ]
        for items, expected in cases:
            with self.subTest(items=items):
                data = content()
                data["key_decisions"] = [
                    {"decision": item, "why": "Cost", "position": "Open",
                        "evidence": "[F01](ledger:F01)"}
                    for item in items]
                self.make(data)
                self.assertIn(expected, self.report())

    def test_a_flow_gap_replaces_the_sequence(self):
        data = content()
        data["architecture"]["next"] = {"summary": ["x " * 300 + "[F01](ledger:F01)."],
                                        "flow_gap": "No next flow is established [G01](ledger:G01)."}
        result = self.make(data)
        self.assertTrue(result["ok"], result)
        self.assertIn(
            "**Flow evidence gap:** No next flow is established", self.report())
        self.assertEqual(result["sequences"], [QUERY["title"]])

    def test_sequence_that_does_not_render(self):
        def broken(sources):
            raise SystemExit(
                "diagram 2: the diagram doesn't render: Parse error")
        self.write("content.json", json.dumps(content()))
        with mock.patch.object(output_diagram, "render_many", side_effect=broken):
            with self.assertRaises(SystemExit) as raised:
                make_report.make_report(INVESTIGATION)
        self.assertIn("Publish job — publication: doesn't render",
                      str(raised.exception))

    def skipping(self, skip):
        """content.json skipping `skip`, without the parts it leaves out."""
        data = content()
        data["skip"] = skip
        if "evolution" in skip:
            data.pop("next_steps")
            if "architecture" in data:
                data["architecture"].pop("next")
        if "architecture" in skip:
            for key in ("architecture", "decisions_and_gaps"):
                data.pop(key)
        return data

    def test_skipped_sections(self):
        # skip: (how often each section title appears, titles absent)
        cases = [(["architecture"], {"### Current status\n": 1, "### Next steps and evolution\n": 1},
                  ["Architect summary", "Key decisions and gaps"]),
                 (["evolution"], {"### Current status\n": 2, "### Next steps and evolution\n": 0},
                  []),
                 (["architecture", "evolution"], {"### Current status\n": 1, "### Next steps and evolution\n": 0},
                  ["Architect summary", "Key decisions and gaps"])]
        for skip, counts, absent in cases:
            with self.subTest(skip=skip):
                result = self.make(self.skipping(skip))
                self.assertTrue(result["ok"], result)
                text = self.report()
                for heading, count in counts.items():
                    self.assertEqual(text.count(heading), count, heading)
                for title in absent:
                    self.assertNotIn(f" {title}\n", text)
                self.assertIn("### Problem and intended outcome\n", text)
                self.assertIn("### Key decisions and risks\n", text)
                self.assertIn("\n## References\n", text)
                self.setUp()

    def test_skip_problems(self):
        evolution = ["evolution"]
        cases = [
            ({"skip": ["design"]},
             "only architecture or evolution can be skipped"),
            ({"skip": {"evolution": "Reason."}},
             "skip: must list the dimensions"),
            (dict(self.skipping(evolution), next_steps=content()
             ["next_steps"]), "the report has no Next steps and evolution"),
            (dict(self.skipping(["architecture"]), decisions_and_gaps=content()["decisions_and_gaps"]),
             "decisions_and_gaps: architecture is skipped"),
            ({"technical_decisions": []},
             "technical_decisions: renamed decisions_and_gaps"),
            ({"discrepancies": "x"}, "discrepancies: removed"),
            ({"remaining_gaps": "x"}, "remaining_gaps: removed"),
            ({"decisions_and_gaps": [dict(content()["decisions_and_gaps"][0], owner="Platform lead")]},
             "decisions_and_gaps 1.owner: removed"),
            (dict(self.skipping(["architecture"]), architecture=content()["architecture"]),
             "architecture: architecture is skipped"),
            (dict(self.skipping(evolution), architecture=content()["architecture"]),
             "architecture.next: the report doesn't show this section, as evolution is skipped"),
        ]
        for data, expected in cases:
            with self.subTest(expected=expected):
                full = content()
                full.update(data)
                self.assertIn(expected, self.problems(full))

    def test_word_count_warnings(self):
        data = content()
        data["problem"] = ["Too short [F01](ledger:F01)."]
        result = self.make(data)
        self.assertIn("problem: 3 words; the target is about 150",
                      result["warnings"])


if __name__ == "__main__":
    unittest.main()
