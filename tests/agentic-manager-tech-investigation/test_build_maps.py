# Unit tests for skills/agentic-manager-tech-investigation/scripts/build_maps.py.
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
sys.path.insert(0, os.path.join(REPO_ROOT, "skills", os.path.basename(TEST_DIR), "scripts"))
import build_maps  # noqa: E402
import output_diagram  # noqa: E402
sys.path.insert(0, TEST_DIR)
from investigation_fixture import INVESTIGATION, spec, svg, temp_output  # noqa: E402

NODES = [("U", 10, 10), ("A", 50, 10), ("D", 90, 10)]


class ValidateTest(unittest.TestCase):
    def test_valid_spec(self):
        self.assertEqual(build_maps.validate(spec()), [])

    def test_problems(self):
        def change(edit):
            data = spec()
            edit(data)
            return data
        # name: (edit to the spec, expected in an error)
        cases = [
            ("reserved id", lambda s: s["nodes"][1].update(id="end"), "Mermaid keyword"),
            ("unknown status", lambda s: s["nodes"][1].update(status="Live"), "status must be one of"),
            ("unknown kind", lambda s: s["nodes"][1].update(kind="service"), "kind must be one of"),
            ("unknown group", lambda s: s["nodes"][1].update(group="nope"), "unknown group"),
            ("duplicate name", lambda s: s["nodes"][2].update(name="Search API"), "names must be unique"),
            ("unknown end", lambda s: s["connections"][0].update(to="Z"), "unknown to node"),
            ("duplicate pair", lambda s: s["connections"].append(dict(s["connections"][0])), "give an \"id\""),
            ("missing stage", lambda s: s["stages"].pop("target"), "stages must be exactly"),
            ("person carried", lambda s: s["stages"]["current"]["carried"].append("U"), "never in the outline"),
            ("unknown style", lambda s: s["stages"]["current"]["connections"].update({"U->A": "live"}),
             "implemented or proposed"),
            ("unknown connection", lambda s: s["stages"]["current"]["connections"].update({"A->X": "proposed"}),
             "unknown connection"),
            ("bad decommissioning", lambda s: s["stages"]["next"]["decommissioned"].update(L="Gone"),
             "decommissioning must be one of"),
            ("dropped from outline", lambda s: s["stages"]["next"]["carried"].remove("A"),
             "A was carried at the preceding stage"),
            ("revived", lambda s: s["stages"]["target"]["decommissioned"].pop("L"), "must stay so"),
        ]
        for name, edit, expected in cases:
            with self.subTest(name):
                errors = build_maps.validate(change(edit))
                self.assertTrue(any(expected in e for e in errors), errors)

    def test_current_map_alone(self):
        data = spec()
        for key in ("next", "target"):
            data["stages"].pop(key)
        self.assertEqual(build_maps.validate(data), [])
        self.assertEqual(list(build_maps.sources(data)), ["current"])
        data["stages"]["next"] = spec()["stages"]["next"]
        self.assertIn("or current alone", " ".join(build_maps.validate(data)))

    def test_replaced_components(self):
        def replaced(edit=None):
            data = spec()
            for key in ("next", "target"):
                data["stages"][key].pop("decommissioned")
                data["stages"][key]["replaced"] = {"L": "J"}
            if edit:
                edit(data)
            return data
        self.assertEqual(build_maps.validate(replaced()), [])
        # name: (edit to a valid spec with L replaced by J, expected in an error)
        cases = [
            ("at the current stage", lambda s: s["stages"]["current"].update(replaced={"A": "D"}),
             "nothing is replaced at the current stage"),
            ("replacement not carried", lambda s: s["stages"]["next"].update(replaced={"L": "X"}),
             "which must be carried"),
            ("also labelled", lambda s: s["stages"]["next"]["labels"].update(L="Retained"), "its label names"),
            ("person replaced", lambda s: s["stages"]["next"]["replaced"].update(U="A"), "known component or store"),
            ("back in the design", lambda s: s["stages"]["target"].update(replaced={}), "keep it replaced"),
        ]
        for name, edit, expected in cases:
            with self.subTest(name):
                errors = build_maps.validate(replaced(edit))
                self.assertTrue(any(expected in e for e in errors), errors)
        target = build_maps.sources(replaced())["target"]
        self.assertIn('L["Legacy indexer<br/>Legacy or superseded<br/>Replaced by Publish job"]', target)
        self.assertIn("class L retired", target)
        self.assertNotIn("decommissioned", target)

    def test_transferred_component_may_leave_the_outline(self):
        data = spec()
        data["stages"]["next"]["carried"].remove("A")
        data["stages"]["next"]["transferred"] = {"A": "Moves to the platform team's system"}
        data["stages"]["target"]["carried"].remove("A")
        self.assertEqual(build_maps.validate(data), [])


class MermaidTest(unittest.TestCase):
    def setUp(self):
        self.maps = build_maps.sources(spec())

    def test_every_stage_has_the_same_nodes_and_connections(self):
        def skeleton(source):
            return [line.split("[")[0].split("|")[0].replace("-.->", "-->")
                    for line in source.splitlines()[1:] if not line.lstrip().startswith(("class", "linkStyle"))]
        self.assertEqual(skeleton(self.maps["current"]), skeleton(self.maps["next"]))
        self.assertEqual(skeleton(self.maps["next"]), skeleton(self.maps["target"]))

    def test_layout_directives(self):
        current = self.maps["current"]
        init = json.loads(current.splitlines()[0][len("%%{init: "):-len("}%%")])
        self.assertEqual(init["flowchart"], {"curve": "rounded"})
        self.assertEqual(init["elk"], {"lineHops": "gap"})
        self.assertIn("width:260px", init["themeCSS"])
        self.assertIn(".edge-pattern-dotted{stroke-dasharray:6 4 !important}", init["themeCSS"])
        self.assertEqual(current.splitlines()[1], "flowchart LR")
        self.assertIn('subgraph grp_app["APP CLUSTER · configured"]', current)
        compact = spec()
        compact["compact"] = True
        self.assertIn("NETWORK_SIMPLEX", build_maps.sources(compact)["current"])

    def test_labels_have_three_lines(self):
        cases = [("current", 'U["Client / operator<br/>Person<br/>&nbsp;"]'),
                 ("current", 'D[("Search index<br/>Implemented<br/>Current")]'),
                 ("next", 'L["Legacy indexer<br/>Legacy or superseded<br/>Planned decommissioning"]'),
                 ("next", 'X["Embedding API<br/>External<br/>&nbsp;"]')]
        for key, label in cases:
            with self.subTest(label=label):
                self.assertIn(label, self.maps[key])

    def test_hidden_proposed_and_changed_connections(self):
        cases = [
            ("current", "[data-id=L_J_D_0]{opacity:0}", True),
            ("current", "[data-id=L_L_D_0]{opacity:0}", False),
            ("next", "[data-id=L_L_D_0]{opacity:0}", True),
            ("next", 'J -.->|"publish"| D', True),
            ("current", "linkStyle", False),
            ("next", "linkStyle 3,4 stroke:#e5484d", True),
            ("target", "linkStyle", False),
            ("next", "class A,D,J carried", True),
            ("next", "class L retired\n  class L decommissioned", True),
            ("current", "decommissioned", False),
        ]
        for key, text, present in cases:
            with self.subTest(key=key, text=text):
                self.assertEqual(text in self.maps[key], present, self.maps[key])

    def test_style_change_is_red(self):
        data = spec()
        data["stages"]["target"]["connections"]["J->D"] = "implemented"
        self.assertIn("linkStyle 3 stroke:#e5484d", build_maps.sources(data)["target"])

    def test_quotes_are_escaped(self):
        data = spec()
        data["nodes"][1]["name"] = 'Search "API"'
        self.assertIn("Search #quot;API#quot;", build_maps.sources(data)["current"])

    def test_preparation_names_each_stage_and_file(self):
        text = build_maps.preparation(spec(), self.maps)
        for title, filename in (("Current architecture", "architecture-as-is.svg"),
                                ("Next evolution", "architecture-next.svg"),
                                ("Target architecture", "architecture-to-be.svg")):
            self.assertIn(f"## {title} — System map\n\nOutput: `{filename}`\n\n```mermaid\n%%{{init", text)
        self.assertIn("The app cluster groups", text)


class CheckRenderedTest(unittest.TestCase):
    def test_positions_and_ratio(self):
        same = {key: svg(200, 100, NODES) for key in ("current", "next", "target")}
        self.assertEqual(build_maps.check_rendered(same)[:2], ([], []))
        moved = dict(same, target=svg(200, 100, [("U", 10, 10), ("A", 60, 10), ("D", 90, 10)]))
        errors, _, _ = build_maps.check_rendered(moved)
        self.assertEqual(len(errors), 1)
        self.assertIn("target: A moves", errors[0])
        tall = {key: svg(100, 100, NODES) for key in same}
        self.assertEqual(len(build_maps.check_rendered(tall)[1]), 3)


class BuildTest(unittest.TestCase):
    def setUp(self):
        self.folder = os.path.join(temp_output(self), INVESTIGATION)
        os.makedirs(self.folder)
        with open(os.path.join(self.folder, "maps.json"), "w", encoding="utf-8") as f:
            json.dump(spec(), f)

    def files(self):
        return sorted(os.listdir(self.folder))

    def test_writes_preparation_and_maps(self):
        rendered = [svg(200, 100, NODES)] * 3
        with mock.patch.object(output_diagram, "render_many", return_value=rendered) as render:
            result = build_maps.build(INVESTIGATION)
        self.assertEqual(render.call_args[0][1], "dark")
        self.assertEqual(self.files(), ["architecture-as-is.svg", "architecture-next.svg",
                                        "architecture-to-be.svg", "maps.json", "mermaids.md"])
        self.assertEqual(result["maps"]["next"]["width"], 200)
        self.assertEqual(result["warnings"], [])

    def test_invalid_spec_or_layout_writes_nothing(self):
        moved = [svg(200, 100, NODES)] * 2 + [svg(200, 100, NODES[:1])]
        with mock.patch.object(output_diagram, "render_many", return_value=moved):
            with self.assertRaises(SystemExit) as raised:
                build_maps.build(INVESTIGATION)
        self.assertIn("A moves", str(raised.exception))
        self.assertEqual(self.files(), ["maps.json"])

    def test_without_node_writes_preparation_and_removes_stale_maps(self):
        with open(os.path.join(self.folder, "architecture-as-is.svg"), "w") as f:
            f.write("<svg/>")
        with mock.patch.object(output_diagram, "render_many", side_effect=output_diagram.NodeMissing()), \
                mock.patch("sys.stderr"):
            with self.assertRaises(SystemExit) as raised:
                build_maps.build(INVESTIGATION)
        self.assertEqual(raised.exception.code, 3)
        self.assertEqual(self.files(), ["maps.json", "mermaids.md"])


if __name__ == "__main__":
    unittest.main()
