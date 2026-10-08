# Unit tests for skills/agentic-manager-tech-investigation/scripts/make_report.py.
# The whole pipeline has end-to-end tests in test_e2e_pipeline.py.
# Run with: python3 tests/run.py agentic-manager-tech-investigation
#
# The Mermaid CLI is never run here: render_many() is patched. The config's path
# is patched to the test's own config, in a temporary folder.
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
from common import STAGE_FILES  # noqa: E402
sys.path.insert(0, TEST_DIR)
from investigation_fixture import (INVESTIGATION, LEDGER, PUBLISH, QUERY, content, spec,  # noqa: E402
                                   svg, temp_output)

MAPS = list(STAGE_FILES.values())


class MakeReportTest(unittest.TestCase):
    def setUp(self):
        self.folder = os.path.join(temp_output(self), INVESTIGATION)
        os.makedirs(self.folder)
        self.write("ledgers.md", LEDGER)
        self.write("maps.json", json.dumps(spec()))
        self.write("mermaids.md", "# Maps\n\n" + "".join(
            f"## {title} — System map\n\nOutput: `{name}`\n\n```mermaid\nflowchart LR\n  A --> B\n```\n\n"
            for title, name in zip(("Current architecture", "Next evolution", "Target architecture"), MAPS)))
        for name in MAPS:
            self.write(name, '<svg xmlns="http://www.w3.org/2000/svg"/>')
        self.widths = {}

    def write(self, name, text):
        with open(os.path.join(self.folder, name), "w", encoding="utf-8") as f:
            f.write(text)

    def render(self, sources, theme="default"):
        return [svg(self.widths.get(source.splitlines()[2].strip(), 600)) for source in sources]

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
        self.assertEqual([s["title"] for s in result["sequences"]],
                         [QUERY["title"], QUERY["title"], PUBLISH["title"], QUERY["title"]])

    def test_template(self):
        self.make()
        text = self.report()
        for expected in [
            "# Acme search\n\nEvidence snapshot: 5 October 2026. Code links pin inspected commits;",
            "| Stage | Intended outcome | Commitment and evidence | Dependencies |\n| --- | --- | --- | --- |\n"
            "| Current milestone | Outcome current |",
            "These items describe implications of the linked evidence. Decision ownership is not established "
            "in the inspected sources.\n\n| Decision or risk | Why it matters | Deciding role |",
            "![Current architecture](architecture-as-is.svg)\n\n#### Search API — query\n\n"
            "```mermaid\nsequenceDiagram\n    autonumber\n    actor U as Client / operator\n",
            "```\n\n#### Reading the design and flows together\n\n**Search API:** steps 1–4",
            "[code](ledgers.md#f01--search-api-is-merged)",
            "[G01](ledgers.md#decisions-and-precise-evidence-gaps)",
            "The table records source-backed differences and unresolved decisions. It does not select an "
            "option or assign an owner.\n\n| Decision | Established position / unresolved choice |",
            "**Delivery**\n\n- [PROJ-1](https://example.com/PROJ-1) (historical)",
            "**Vision, rationale and reported operational gaps**\n\nNone in the inspected sources.",
            "The [research ledger](ledgers.md) holds the full validation trail",
        ]:
            with self.subTest(expected=expected[:40]):
                self.assertIn(expected, text)

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
            ("fence in prose", lambda d: d["deep_dive"].append(
                "```mermaid\nflowchart LR\n```"), "no code fences"),
            ("multi-line cell", lambda d: d["roadmap"]
             ["next"].update(outcome="a\nb"), "one line"),
            ("missing field", lambda d: d["key_decisions"][0].pop(
                "why"), "key_decisions 1.why: needs text"),
            ("unknown ledger ID", lambda d: d["problem"].append(
                "[x](ledger:F09)"), "ledger:F09 matches no heading"),
            ("bad date", lambda d: d.update(
                evidence_snapshot="5/10/2026"), "evidence_snapshot"),
            ("title without flow", lambda d: stage(d)["sequences"][0].update(title="Search"),
             "<Component> — <flow>"),
            ("semicolon", lambda d: stage(d)["sequences"][0]["lines"].append("A->>D: read; write"),
             "raw semicolon"),
            ("manual number", lambda d: stage(d)["sequences"][0]["lines"].append("A->>D: 5. Read"),
             "numbers its step"),
            ("participant off the map", lambda d: stage(d)["sequences"][0]["lines"].insert(0, "participant Q as Cache"),
             "participant 'Cache' is not a node of the current map"),
            ("call without connection", lambda d: stage(d)["sequences"][0]["lines"].append("U->>D: Read directly"),
             "no connection between U and D on the current map"),
            ("hidden connection", lambda d: stage(d)["sequences"].append(PUBLISH),
             "no connection between J and X on the current map"),
            ("step beyond the flow", lambda d: stage(d).update(commentary=["**Search API:** steps 1–9."]),
             "names step 9, but Search API has 4"),
            ("step zero", lambda d: stage(d).update(commentary=["**Search API:** step 0."]),
             "step range 0–0 must start at 1 or later and run forwards"),
            ("reversed range", lambda d: stage(d).update(commentary=["**Search API:** steps 9–1."]),
             "step range 9–1 must start at 1 or later and run forwards"),
            ("unknown flow label", lambda d: stage(d).update(commentary=["**Search AP:** step 99."]),
             "step references need a matching flow"),
            ("unlabeled steps among multiple flows", lambda d: stage(d, "next").update(commentary=["Step 99."]),
             "step references need a matching flow"),
            ("no flow nor gap", lambda d: stage(d).update(
                sequences=[]), "needs a sequence, or a flow_gap"),
            ("constrain to self", lambda d: stage(d)["sequences"][0].update(constrain_to=QUERY["title"]),
             "constrain_to names no other sequence"),
        ]
        for name, edit, expected in cases:
            with self.subTest(name):
                self.assertIn(expected, self.problems(change(edit)))

    def test_multiline_sequence_statements_are_all_checked(self):
        data = content()
        data["architecture"]["current"]["sequences"] = [
            {"title": QUERY["title"], "lines": ["\n".join(QUERY["lines"])]}]
        self.assertTrue(self.make(data)["ok"])
        self.assertIn("U->>A: Query\n    A->>D: Read rows", self.report())
        original = self.report()
        cases = [
            ("call", "U->>D: Read directly", "no connection between U and D"),
            ("participant", "participant Q as Cache\nparticipant R as Unknown",
             "participant 'Cache' is not a node"),
            ("manual number", "A-->>U: 5. Results", "numbers its step"),
        ]
        for name, extra, expected in cases:
            with self.subTest(name=name):
                data["architecture"]["current"]["sequences"][0]["lines"] = [
                    "\n".join(QUERY["lines"]) + "\n" + extra]
                with self.assertRaisesRegex(SystemExit, expected):
                    self.make(data)
                self.assertEqual(self.report(), original)

    def test_shown_maps_need_their_stage_specification(self):
        self.make()
        original = self.report()
        for key in ("current", "next", "target"):
            with self.subTest(key=key):
                maps = spec()
                maps["stages"].pop(key)
                self.write("maps.json", json.dumps(maps))
                with self.assertRaisesRegex(SystemExit, f"maps.json has no {key} stage for the shown map"):
                    self.make()
                self.assertEqual(self.report(), original)
        # Even without a flow, retained map artifacts cannot stand in for
        # the omitted stage's specification.
        data = content()
        data["architecture"]["target"].update(
            sequences=[], flow_gap="No target flow is established.")
        with self.assertRaisesRegex(SystemExit, "maps.json has no target stage for the shown map"):
            self.make(data)
        self.assertEqual(self.report(), original)

    def test_missing_stage_correspondence_is_disclosed_for_map_gaps(self):
        maps = spec()
        maps["stages"].pop("next")
        self.write("maps.json", json.dumps(maps))
        for with_flow in (False, True):
            with self.subTest(with_flow=with_flow):
                data = content()
                stage = data["architecture"]["next"]
                stage["map_gap"] = "Next architecture placement is unavailable."
                stage["commentary"] = [
                    "Future interactions remain unverified."]
                if with_flow:
                    stage["sequences"] = [{"title": "Worker — invocation", "lines": [
                        "participant P as Unknown worker", "participant Z as Unknown endpoint", "P->>Z: Invoke"]}]
                else:
                    stage.update(
                        sequences=[], flow_gap="No next flow is established.")
                result = self.make(data)
                self.assertTrue(result["ok"], result)
                self.assertEqual(any("no next stage: sequences aren't checked" in w
                                     for w in result["warnings"]), with_flow)

    def test_current_only_maps_match_skipped_evolution(self):
        maps = spec()
        maps["stages"] = {"current": maps["stages"]["current"]}
        self.write("maps.json", json.dumps(maps))
        result = self.make(self.skipping(["evolution"]))
        self.assertTrue(result["ok"], result)
        self.assertFalse(
            any("aren't checked" in w for w in result["warnings"]))

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

    def test_commentary_without_step_references(self):
        for paragraph in ("The design preserves the existing entry paths.",
                          "**Context:** the map shows the hosting boundary."):
            with self.subTest(paragraph=paragraph):
                data = content()
                data["architecture"]["next"]["commentary"] = [paragraph]
                self.assertTrue(self.make(data)["ok"])

    def test_invalid_collections_preserve_existing_report(self):
        self.make()
        original = self.report()
        for field in ("sequences", "references", "skip"):
            for value in (1, "wrong", {}):
                with self.subTest(field=field, value=value):
                    data = content()
                    if field == "sequences":
                        data["architecture"]["current"][field] = value
                        expected = "architecture.current.sequences: needs a list"
                    elif field == "references":
                        data[field]["implementation"] = value
                        expected = "references.implementation: needs a list"
                    else:
                        data[field] = value
                        expected = "skip: must list the dimensions"
                    with self.assertRaisesRegex(SystemExit, expected):
                        self.make(data)
                    self.assertEqual(self.report(), original)

    def test_role_qualifier_and_reply_ride_on_the_connection(self):
        data = content()
        data["architecture"]["current"]["sequences"][0]["lines"][
            0] = "actor U as Client / operator (source owner)"
        self.assertTrue(self.make(data)["ok"])

    def test_implicit_self_messages_need_a_map_participant(self):
        for name, valid in (("Cache", False), ("Search index", True)):
            with self.subTest(name=name):
                checked = make_report.Content({}, make_report.Ledger(
                    os.path.join(self.folder, "ledgers.md")))
                # Implicit Mermaid names cannot contain spaces; use a map
                # node with the same short name as the message endpoint.
                endpoint = name.replace(" ", "")
                maps = spec()
                if valid:
                    maps["nodes"][2]["name"] = endpoint
                flow = make_report.Sequence(
                    f"{endpoint} — refresh", [f"{endpoint}->>{endpoint}: Refresh"], None)
                make_report.check_against_map(checked, flow, maps, "current")
                if valid:
                    self.assertEqual(checked.errors, [])
                else:
                    self.assertIn("'Cache' is not a node of the current map",
                                  " ".join(checked.errors))

    def test_key_decisions_sentence(self):
        cases = [
            (["Not established"],
             "Decision ownership is not established in the inspected sources."),
            (["Platform lead"],
             "The inspected sources establish the deciding role for each item."),
            (["Platform lead", "Not established"],
             "establish the deciding role for some items only"),
            ([], "No decision, blocker or risk in the inspected evidence warrants technical-leadership attention."),
        ]
        for roles, expected in cases:
            with self.subTest(roles=roles):
                data = content()
                data["key_decisions"] = [{"item": "Choice", "why": "Cost [p](https://example.com/p)", "role": role}
                                         for role in roles]
                self.make(data)
                self.assertIn(expected, self.report())

    def test_gaps_replace_map_and_flow(self):
        data = content()
        data["architecture"]["target"] = {"summary": ["x " * 300], "map_gap": "Target placement is unavailable.",
                                          "flow_gap": "No target flow is established.",
                                          "commentary": ["Nothing to read together. " * 10]}
        self.assertTrue(self.make(data)["ok"])
        text = self.report()
        self.assertIn(
            "**Map evidence gap:** Target placement is unavailable.", text)
        self.assertIn(
            "**Flow evidence gap:** No target flow is established.", text)

    def test_width_container_and_spread_warning(self):
        self.widths = {"participant J as Publish job": 400}
        data = content()
        data["architecture"]["next"]["sequences"][1]["constrain_to"] = QUERY["title"]
        result = self.make(data)
        self.assertTrue(result["ok"], result)
        self.assertIn(
            '<div style="width:66.67%; margin:0 auto;">\n\n```mermaid\nsequenceDiagram', self.report())
        self.assertTrue(
            any("differ by more than 15%" in w for w in result["warnings"]))

    def test_missing_map(self):
        # Without Node.js, the map's source from mermaids.md stands in for its
        # SVG, unchecked, and so do the sequences; without mermaids.md too,
        # the report can't be written.
        os.remove(os.path.join(self.folder, MAPS[0]))
        result = self.make(render=output_diagram.NodeMissing())
        self.assertTrue(result["ok"], result)
        text = self.report()
        self.assertIn("```mermaid\nflowchart LR\n  A --> B\n```", text)
        self.assertIn("Map layout is unchecked", text)
        self.assertEqual(text.count("Sequence syntax is unchecked"), 3)
        os.remove(os.path.join(self.folder, "Acme-Search_Report.md"))
        os.remove(os.path.join(self.folder, "mermaids.md"))
        self.assertIn(
            "architecture-as-is.svg is missing: run build_maps.py", self.problems(content()))

    def test_sequence_that_does_not_render(self):
        def broken(sources, theme="default"):
            raise SystemExit(
                "diagram 3: the diagram doesn't render: Parse error")
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
            data.pop("roadmap")
            for key in ("next", "target"):
                data["architecture"].pop(key)
        if "architecture" in skip:
            for key in ("architecture", "technical_decisions", "discrepancies", "remaining_gaps", "references"):
                data.pop(key)
        return data

    def test_skipped_sections(self):
        architect = ["Architect summary", "Current architecture", "Next evolution", "Target architecture",
                     "Technical decisions and gaps", "References"]
        # skip: headings left out
        cases = [(["architecture"], architect),
                 (["evolution"], ["Roadmap", "Next evolution", "Target architecture"]),
                 (["architecture", "evolution"], architect + ["Roadmap"])]
        for skip, absent in cases:
            with self.subTest(skip=skip):
                if "architecture" in skip:
                    os.remove(os.path.join(self.folder, "maps.json"))
                    for name in MAPS:
                        os.remove(os.path.join(self.folder, name))
                result = self.make(self.skipping(skip))
                self.assertTrue(result["ok"], result)
                text = self.report()
                for title in absent:
                    self.assertNotIn(f" {title}\n", text)
                for title in ("Problem and intended outcome", "Current milestone - deep dive",
                              "Key decisions and risks"):
                    self.assertIn(f"### {title}\n", text)
                self.assertNotIn("Scope:", text)
                self.setUp()

    def test_skip_problems(self):
        evolution = ["evolution"]
        cases = [
            ({"skip": ["design"]},
             "only architecture or evolution can be skipped"),
            ({"skip": {"evolution": "Reason."}},
             "skip: must list the dimensions"),
            (dict(self.skipping(evolution), roadmap=content()
             ["roadmap"]), "the report has no roadmap"),
            (dict(self.skipping(["architecture"]), references=content()["references"]),
             "references: architecture is skipped"),
            (dict(self.skipping(evolution), architecture=content()["architecture"]),
             "architecture.next: the report doesn't show this stage"),
        ]
        for data, expected in cases:
            with self.subTest(expected=expected):
                full = content()
                full.update(data)
                self.assertIn(expected, self.problems(full))

    def test_word_count_warnings(self):
        data = content()
        data["problem"] = ["Too short [doc](https://example.com/doc)."]
        result = self.make(data)
        self.assertIn("problem: 3 words; the target is about 100",
                      result["warnings"])


if __name__ == "__main__":
    unittest.main()
