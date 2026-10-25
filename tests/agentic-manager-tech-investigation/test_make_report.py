"""Unit tests for skills/agentic-manager-tech-investigation/scripts/make_report.py.
The whole pipeline has end-to-end tests in test_e2e_pipeline.py.
Run with: python3 tests/run.py agentic-manager-tech-investigation

The config's path is patched to the test's own config, in a temporary folder.
"""

import json
import os
import sys
import unittest

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(TEST_DIR))
sys.path.insert(0, os.path.join(REPO_ROOT, "skills",
                os.path.basename(TEST_DIR), "scripts"))
import make_report  # noqa: E402
sys.path.insert(0, TEST_DIR)
from investigation_fixture import (INVESTIGATION, LEDGER, content,  # noqa: E402
                                   temp_output)


class MakeReportTest(unittest.TestCase):
    def setUp(self):
        self.folder = os.path.join(temp_output(self), INVESTIGATION)
        os.makedirs(self.folder)
        self.write("ledger.md", LEDGER)

    def write(self, name, text):
        with open(os.path.join(self.folder, name), "w", encoding="utf-8") as f:
            f.write(text)

    def make(self, data=None):
        self.write("content.json", json.dumps(
            content() if data is None else data))
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

    def test_template(self):
        self.make()
        text = self.report()
        for expected in [
            "# Acme Search\n\nEvidence snapshot: 05/10/2026. Code links pin inspected commits;",
            "These items describe implications of the linked evidence.\n\n"
            "| Decision or risk | Why it matters | Established position | Evidence |\n| --- | --- | --- | --- |\n"
            "| Index choice | Affects cost | Unresolved | [proposal](https://example.com/p)",
            "## Architect summary\n\n### How it works today\n\n",
            "### Target design\n\n",
            "[code](ledger.md#f01--search-api-is-merged)",
            "[gap](ledger.md#evidence-gaps)",
            "### Open technical choices and gaps\n\nThe table records source-backed decisions and evidence gaps. It does "
            "not select an option.\n\n| Decision or gap | Why it matters | Established position | Evidence |\n"
            "| --- | --- | --- | --- |\n| Index | Sets the cost | Unresolved | [gap](ledger.md#evidence-gaps) |",
            "\n\n## References\n\n**Implementation and configuration**\n\n- [Search API](https://example.com/code)\n\n",
            "**Delivery**\n\n- [PROJ-1](https://example.com/PROJ-1) (superseded)",
            "**Vision, rationale and reported operational gaps**\n\nNone in the inspected sources.",
            "The [research ledger](ledger.md) holds the full validation trail",
        ]:
            with self.subTest(expected=expected[:40]):
                self.assertIn(expected, text)
        for heading in ("### Current status\n", "### Direction\n", "### How it works today\n",
                        "### Target design\n"):
            self.assertEqual(text.count(heading), 1, heading)

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
        stage = lambda data, key="today": data["architecture"][key]  # noqa: E731
        # name: (edit to content.json, expected in the problems)
        cases = [
            ("heading in prose", lambda d: d["purpose"].append(
                "### Extra"), "no # to ### headings"),
            ("fence in prose", lambda d: d["current_status"].append(
                "```mermaid\nflowchart LR\n```"), "no code fences"),
            ("multi-line cell",
             lambda d: d["key_decisions"][0].update(decision="a\nb"), "one line"),
            ("unlinked backticks", lambda d: d["direction"].append("The `worker` retries [F01](ledger:F01)."),
             "direction paragraph 2: references in backticks without a link: `worker`"),
            ("claim without a ledger link", lambda d: d["direction"].append("A claim with no trace."),
             "direction paragraph 2: needs a ledger link"),
            ("a source link is not a ledger link", lambda d: d["key_decisions"][0].update(
                evidence="[p](https://example.com/p)"), "key_decisions 1.evidence: needs a ledger link"),
            ("missing field", lambda d: d["key_decisions"][0].pop(
                "why"), "key_decisions 1.why: needs text"),
            ("unknown ledger ID", lambda d: d["purpose"].append(
                "[x](ledger:F09)"), "ledger:F09 matches no heading"),
            ("summary without a ledger link", lambda d: stage(d).update(summary=["No trace."]),
             "architecture.today.summary paragraph 1: needs a ledger link"),
            ("stage missing", lambda d: d["architecture"].pop(
                "target"), "architecture.target: missing"),
            ("architecture empty", lambda d: d.update(architecture={}),
             "architecture: needs today and target"),
            ("unknown section", lambda d: d["architecture"].update(next=stage(d)),
             "architecture.next: the report doesn't show this section"),
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
        self.write("ledger.md", LEDGER.replace("- **G01** Billing callers unverified.",
                                               '| ID | Gap |\n| --- | --- |\n| <a id="g01"></a>G01 | Billing callers unverified |'))
        self.assertTrue(self.make(content())["ok"])
        self.assertIn("[gap](ledger.md#g01)", self.report())

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

    def test_list_sections_say_when_they_are_empty(self):
        # Nothing is skipped: a section with nothing to say says so.
        decision = {"decision": "Cost", "why": "Cost",
                    "position": "Open", "evidence": "[F01](ledger:F01)"}
        # (field, its items, expected in the report)
        cases = [
            ("key_decisions", [decision],
             "These items describe implications of the linked evidence.\n\n| Decision or risk | Why it matters |"),
            ("key_decisions", [],
             "No decision, blocker or risk in the inspected evidence warrants technical-leadership attention."),
            ("open_choices_and_gaps", [],
             "### Open technical choices and gaps\n\nNo technical choice or evidence gap is open"),
        ]
        for field, items, expected in cases:
            with self.subTest(field=field, items=len(items)):
                data = content()
                data[field] = items
                result = self.make(data)
                self.assertTrue(result["ok"], result)
                self.assertIn(expected, self.report())

    def test_word_count_warnings(self):
        data = content()
        data["purpose"] = ["Too short [F01](ledger:F01)."]
        result = self.make(data)
        self.assertIn("purpose: 3 words; the target is about 150",
                      result["warnings"])


if __name__ == "__main__":
    unittest.main()
