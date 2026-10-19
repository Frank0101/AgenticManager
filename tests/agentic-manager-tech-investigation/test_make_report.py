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
        self.write("ledger.md", LEDGER)

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
            # The flow's components, drawn from the sequence, then the sequence.
            "\n\n#### Search API — query\n\nThe components this flow crosses, coloured by their status in the "
            "[component inventory](ledger.md#component-inventory-and-evolution): 🟦 In development, "
            "⬜ Unverified. A person is drawn rounded. Arrows are its requests; the sequence below shows "
            "them in order.\n\n```mermaid\n%%{init: ",
            "```\n\n```mermaid\nsequenceDiagram\n    autonumber\n    actor U as Client / operator\n",
            "### Next steps and evolution\n\n",
            "\n\n#### Publish job — publication\n\nThe components this flow crosses",
            "[code](ledger.md#f01--search-api-is-merged)",
            "[gap](ledger.md#evidence-gaps)",
            "### Key decisions and gaps\n\nThe table records source-backed decisions and evidence gaps. It does "
            "not select an option.\n\n| Decision or gap | Why it matters | Established position | Evidence |\n"
            "| --- | --- | --- | --- |\n| Index | Sets the cost | Unresolved | [gap](ledger.md#evidence-gaps) |",
            "\n\n## References\n\n**Implementation and configuration**",
            "**Delivery**\n\n- [PROJ-1](https://example.com/PROJ-1) (historical)",
            "**Vision, rationale and reported operational gaps**\n\nNone in the inspected sources.",
            "The [research ledger](ledger.md) holds the full validation trail",
        ]:
            with self.subTest(expected=expected[:40]):
                self.assertIn(expected, text)
        self.assertEqual(text.count("### Current status\n"), 2)
        self.assertEqual(text.count("### Next steps and evolution\n"), 2)

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
            ("missing field", lambda d: d["key_decisions"][0].pop(
                "why"), "key_decisions 1.why: needs text"),
            ("unknown ledger ID", lambda d: d["problem"].append(
                "[x](ledger:F09)"), "ledger:F09 matches no heading"),
            ("bad date", lambda d: d.update(
                evidence_snapshot="5/10/2026"), "evidence_snapshot"),
            ("summary without a ledger link", lambda d: stage(d).update(summary=["No trace."]),
             "architecture.current.summary paragraph 1: needs a ledger link"),
            ("manual number", lambda d: stage(d)["sequence"]["lines"].append("A->>D: 5. Read"),
             "numbers its step"),
            # Every participant but a person is a component of the ledger.
            ("participant not in the ledger", lambda d: stage(d)["sequence"]["lines"].append(
                "participant Q as Queue"), "'Queue' is no component of the ledger"),
            ("title missing", lambda d: stage(d)["sequence"].update(
                title=""), "needs a one-line title"),
            ("lines not a list", lambda d: stage(d)["sequence"].update(lines="U->>A: Query"),
             "lines must be a list of Mermaid lines"),
            ("sequence not an object", lambda d: stage(d).update(sequence="U->>A: Query"),
             "architecture.current.sequence: must be an object"),
            ("unknown fields", lambda d: stage(d).update(notes=["x"]),
             "unknown notes"),
            ("no sequence nor gap", lambda d: stage(d).pop(
                "sequence"), "needs a sequence, or a flow_gap"),
            ("stage missing", lambda d: d["architecture"].pop(
                "next"), "architecture.next: missing"),
            ("architecture empty", lambda d: d.update(architecture={}),
             "architecture: needs current and next"),
            ("unknown section", lambda d: d["architecture"].update(target=stage(d)),
             "architecture.target: the report doesn't show this section"),
        ]
        for name, edit, expected in cases:
            with self.subTest(name):
                self.assertIn(expected, self.problems(change(edit)))

    def test_tickets_and_pull_requests_are_linked_from_the_ledger(self):
        # The ledger links one ticket of the project and one page of the host;
        # content.json may then name others plainly. A ticket of a project the
        # ledger doesn't link is written as code.
        self.write("ledger.md", LEDGER.replace("## Links\n\nNone yet.",
                                               "## Links\n\n[proj-1]: https://acme.example/browse/PROJ-1\n"
                                               "[code]: https://git.example/acme/api/blob/abc/x.py"))
        data = content()
        data["current_status"][0] += " PROJ-7 tracks acme/api#12, OPS-3 does not."
        self.make(data)
        self.assertIn("[PROJ-7](https://acme.example/browse/PROJ-7) tracks "
                      "[acme/api#12](https://git.example/acme/api/pull/12), `OPS-3` does not.", self.report())
        data["current_status"][0] += " See #4."
        os.remove(os.path.join(self.folder, "Acme-Search_Report.md"))
        self.assertIn("current_status paragraph 1: couldn't link #4: write a pull request as owner/repo#123",
                      self.problems(data))

    def test_ledger_links_reach_a_row_by_its_anchor(self):
        # A row written by ledger.py carries an anchor, so the report links to the
        # row itself, not only to its section.
        self.write("ledger.md", LEDGER.replace("- **G01** Deployment unverified.",
                                               '| ID | Gap |\n| --- | --- |\n| <a id="g01"></a>G01 | Deployment unverified |'))
        self.assertTrue(self.make(content())["ok"])
        self.assertIn("[gap](ledger.md#g01)", self.report())

    def test_multiline_sequence_statements_are_all_checked(self):
        data = content()
        data["architecture"]["current"]["sequence"] = {
            "title": QUERY["title"], "lines": ["\n".join(QUERY["lines"])]}
        self.assertTrue(self.make(data)["ok"])
        self.assertIn("U->>A: Query\n    A->>D: Read rows", self.report())
        original = self.report()
        data["architecture"]["current"]["sequence"]["lines"] = [
            "\n".join(QUERY["lines"]) + "\nA-->>U: 5. Results"]
        with self.assertRaisesRegex(SystemExit, "numbers its step"):
            self.make(data)
        self.assertEqual(self.report(), original)

    def test_semicolons_are_escaped(self):
        # Mermaid reads a raw semicolon as the end of a statement, so the
        # script writes it as #59;, leaving entities such as #quot; whole.
        cases = [("A->>U: One; two", "A->>U: One#59; two"), ("A->>U: #quot;x#quot;; y", "A->>U: #quot;x#quot;#59; y"),
                 ("A->>U: plain", "A->>U: plain")]
        for line, expected in cases:
            with self.subTest(line):
                self.assertEqual(
                    make_report.semicolons_escaped(line), expected)
        data = content()
        data["architecture"]["current"]["sequence"]["lines"] = QUERY["lines"] + \
            ["A-->>U: One; two"]
        self.assertTrue(self.make(data)["ok"])
        self.assertIn("A-->>U: One#59; two", self.report())

    def test_ledger_definitions_exclude_fences(self):
        for definition in ("| G99 | Evidence |", "- **G99** Evidence."):
            for fence, closing in (("```markdown", "```"), ("~~~~", "~~~~")):
                for genuine in (False, True):
                    with self.subTest(definition=definition, fence=fence, genuine=genuine):
                        text = (LEDGER + "\n\n### Illustration\n\n" + fence + "\n"
                                + definition + "\n" + closing + "\n")
                        if genuine:
                            text += "\n### Actual gap\n\n" + definition + "\n"
                        self.write("ledger.md", text)
                        ledger = make_report.Ledger(
                            os.path.join(self.folder, "ledger.md"))
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

    def test_diagram_that_does_not_render(self):
        # Each flow renders its components diagram, then its sequence; an
        # error without a diagram number is reported as it is.
        cases = [
            ("diagram 1: the diagram doesn't render: Parse error",
             "Search API — query: the components diagram doesn't render: the diagram"),
            ("diagram 4: the diagram doesn't render: Parse error",
             "Publish job — publication: the sequence doesn't render: the diagram"),
            ("Node.js is needed", "\n  - Node.js is needed"),
        ]
        for error, expected in cases:
            with self.subTest(error):
                def broken(sources):
                    raise SystemExit(error)
                self.write("content.json", json.dumps(content()))
                with mock.patch.object(output_diagram, "render_many", side_effect=broken):
                    with self.assertRaises(SystemExit) as raised:
                        make_report.make_report(INVESTIGATION)
                self.assertIn(expected, str(raised.exception))

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
