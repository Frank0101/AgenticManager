# Unit tests for skills/agentic-manager-tech-investigation/scripts/build_maps.py.
# The whole pipeline has end-to-end tests in test_e2e_pipeline.py.
# Run with: python3 tests/run.py agentic-manager-tech-investigation
#
# The Mermaid CLI is never run here: render_many() is patched. The config's path
# is patched to the test's own config, in a temporary folder.
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(TEST_DIR))
sys.path.insert(0, os.path.join(REPO_ROOT, "skills",
                os.path.basename(TEST_DIR), "scripts"))
import build_maps  # noqa: E402
import output_diagram  # noqa: E402
sys.path.insert(0, TEST_DIR)
from investigation_fixture import INVESTIGATION, spec, svg, temp_output  # noqa: E402

NODES = [("U", 10, 10), ("A", 50, 10), ("D", 90, 10)]


class ValidateTest(unittest.TestCase):
    def test_malformed_field_types(self):
        cases = [
            ("nodes", lambda s: s.update(nodes=None)),
            ("groups", lambda s: s.update(groups={})),
            ("connections", lambda s: s.update(connections=None)),
            ("nodes[0]", lambda s: s["nodes"].__setitem__(0, "node")),
            ("id", lambda s: s["nodes"][0].update(id=[])),
            ("name", lambda s: s["nodes"][0].update(name=None)),
            ("kind", lambda s: s["nodes"][0].update(kind={})),
            ("group", lambda s: s["nodes"][0].update(group=[])),
            ("id", lambda s: s["groups"][0].update(id=[])),
            ("label", lambda s: s["groups"][0].update(label=None)),
            ("from", lambda s: s["connections"][0].update({"from": []})),
            ("id", lambda s: s["connections"][0].update(id={})),
            ("label_width", lambda s: s.update(label_width=0)),
            ("label_width", lambda s: s.update(label_width="260")),
            ("notes", lambda s: s.update(notes=[None])),
            ("compact", lambda s: s.update(compact="false")),
            ("current", lambda s: s["stages"].update(current=[])),
            ("carried", lambda s: s["stages"]["current"].update(carried=[[]])),
            ("labels", lambda s: s["stages"]["current"].update(labels=[])),
            ("replaced", lambda s: s["stages"]
             ["next"].update(replaced={"L": []})),
            ("transferred", lambda s: s["stages"]
             ["next"].update(transferred=None)),
            ("decommissioned", lambda s: s["stages"]
             ["next"].update(decommissioned=[])),
            ("connections", lambda s: s["stages"]
             ["next"].update(connections=[])),
        ]
        for expected, edit in cases:
            with self.subTest(expected=expected, edit=edit):
                data = spec()
                edit(data)
                self.assertIn(expected, " ".join(build_maps.validate(data)))

    def test_missing_connections_means_no_connections(self):
        data = spec()
        data.pop("connections")
        for stage in data["stages"].values():
            stage.pop("connections")
        self.assertEqual(build_maps.validate(data), [])
        self.assertNotIn("-->", build_maps.sources(data)["current"])

    def test_conflicting_dispositions_and_noncomponent_lifecycle(self):
        cases = [
            ("carried and decommissioned", lambda s: s["carried"].append("L")),
            ("carried and transferred", lambda s: s.update(
                transferred={"A": "New owner"})),
            ("decommissioned and transferred", lambda s: s.update(
                transferred={"L": "New owner"})),
            ("replaced and transferred", lambda s: (s.update(replaced={"L": "J"},
                                                             transferred={"L": "New owner"}),
                                                    s["decommissioned"].clear())),
            ("component or store", lambda s: s["decommissioned"].update(
                U="Decommissioned")),
            ("component or store", lambda s: s.update(
                transferred={"U": "New owner"})),
        ]
        for expected, edit in cases:
            with self.subTest(expected=expected):
                data = spec()
                edit(data["stages"]["next"])
                self.assertIn(expected, " ".join(build_maps.validate(data)))

    def test_valid_specs(self):
        def transferred(data):
            data["stages"]["next"]["carried"].remove("A")
            data["stages"]["next"]["transferred"] = {
                "A": "Moves to the platform team's system"}
            data["stages"]["target"]["carried"].remove("A")

        def current_alone(data):
            for key in ("next", "target"):
                data["stages"].pop(key)
        cases = [("the fixture", lambda data: None),
                 ("a transferred component leaving the outline", transferred),
                 ("the current map alone", current_alone)]
        for name, edit in cases:
            with self.subTest(name):
                data = spec()
                edit(data)
                self.assertEqual(build_maps.validate(data), [])

    def test_problems(self):
        def change(edit):
            data = spec()
            edit(data)
            return data
        # name: (edit to the spec, expected in an error)
        cases = [
            ("reserved id", lambda s: s["nodes"][1].update(
                id="end"), "Mermaid keyword"),
            ("unknown status", lambda s: s["nodes"][1].update(
                status="Live"), "status must be one of"),
            ("unknown kind", lambda s: s["nodes"][1].update(
                kind="service"), "kind must be one of"),
            ("unknown group", lambda s: s["nodes"][1].update(
                group="nope"), "unknown group"),
            ("duplicate group id", lambda s: s["groups"].append(
                dict(s["groups"][0])), "group ids must be unique"),
            ("duplicate name", lambda s: s["nodes"][2].update(
                name="Search API"), "names must be unique"),
            ("unknown end", lambda s: s["connections"]
             [0].update(to="Z"), "unknown to node"),
            ("duplicate pair", lambda s: s["connections"].append(
                dict(s["connections"][0])), "give an \"id\""),
            ("missing stage", lambda s: s["stages"].pop(
                "target"), "stages must be exactly"),
            ("person carried", lambda s: s["stages"]["current"]["carried"].append(
                "U"), "never in the outline"),
            ("unknown style", lambda s: s["stages"]["current"]["connections"].update({"U->A": "live"}),
             "implemented or proposed"),
            ("unknown connection", lambda s: s["stages"]["current"]["connections"].update({"A->X": "proposed"}),
             "unknown connection"),
            ("transfer without a reason", lambda s: s["stages"]["next"].setdefault("transferred", {}).update(A=" "),
             "with a reason"),
            ("bad decommissioning", lambda s: s["stages"]["next"]["decommissioned"].update(L="Gone"),
             "decommissioning must be one of"),
            ("dropped from outline", lambda s: s["stages"]["next"]["carried"].remove("A"),
             "A was carried at the preceding stage"),
            ("revived", lambda s: s["stages"]["target"]
             ["decommissioned"].pop("L"), "must stay so"),
        ]
        for name, edit, expected in cases:
            with self.subTest(name):
                errors = build_maps.validate(change(edit))
                self.assertTrue(any(expected in e for e in errors), errors)

    def test_current_map_alone(self):
        # One map only, and no next stage without its target.
        data = spec()
        for key in ("next", "target"):
            data["stages"].pop(key)
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
            ("also labelled", lambda s: s["stages"]["next"]["labels"].update(
                L="Retained"), "its label names"),
            ("person replaced", lambda s: s["stages"]["next"]["replaced"].update(
                U="A"), "known component or store"),
            ("back in the design", lambda s: s["stages"]["target"].update(
                replaced={}), "keep it replaced"),
        ]
        for name, edit, expected in cases:
            with self.subTest(name):
                errors = build_maps.validate(replaced(edit))
                self.assertTrue(any(expected in e for e in errors), errors)
        target = build_maps.sources(replaced())["target"]
        self.assertIn(
            'L["Legacy indexer<br/>Legacy or superseded<br/>Replaced by Publish job"]', target)
        self.assertIn("class L retired", target)
        self.assertNotIn("decommissioned", target)


class MermaidTest(unittest.TestCase):
    def setUp(self):
        self.maps = build_maps.sources(spec())

    def test_every_stage_has_the_same_nodes_and_connections(self):
        def skeleton(source):
            return [line.split("[")[0].split("|")[0].replace("-.->", "-->")
                    for line in source.splitlines()[1:] if not line.lstrip().startswith(("class", "linkStyle"))]
        self.assertEqual(
            skeleton(self.maps["current"]), skeleton(self.maps["next"]))
        self.assertEqual(
            skeleton(self.maps["next"]), skeleton(self.maps["target"]))

    def test_layout_directives(self):
        current = self.maps["current"]
        init = json.loads(current.splitlines()[
                          0][len("%%{init: "):-len("}%%")])
        self.assertEqual(init["flowchart"], {"curve": "rounded"})
        self.assertEqual(init["elk"], {"lineHops": "gap"})
        self.assertIn("width:260px", init["themeCSS"])
        self.assertIn(
            ".edge-pattern-dotted{stroke-dasharray:6 4 !important}", init["themeCSS"])
        self.assertEqual(current.splitlines()[1], "flowchart LR")
        self.assertIn('subgraph grp_app["APP CLUSTER · configured"]', current)
        compact = spec()
        compact["compact"] = True
        self.assertIn("NETWORK_SIMPLEX",
                      build_maps.sources(compact)["current"])

    def test_labels_have_three_lines(self):
        cases = [("current", 'U["Client / operator<br/>Person<br/>&nbsp;"]'),
                 ("current",
                  'D[("Search index<br/>Implemented<br/>Current")]'),
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
                self.assertEqual(
                    text in self.maps[key], present, self.maps[key])

    def test_edits_to_the_spec(self):
        # name: (edit to the spec, stage, expected in its source)
        cases = [
            ("a connection changing style is red",
             lambda s: s["stages"]["target"]["connections"].update(
                 {"J->D": "implemented"}),
             "target", "linkStyle 3 stroke:#e5484d"),
            ("quotes are escaped", lambda s: s["nodes"][1].update(name='Search "API"'),
             "current", "Search #quot;API#quot;"),
        ]
        for name, edit, key, expected in cases:
            with self.subTest(name):
                data = spec()
                edit(data)
                self.assertIn(expected, build_maps.sources(data)[key])

    def test_preparation_names_each_stage_and_file(self):
        text = build_maps.preparation(spec(), self.maps)
        for title, filename in (("Current architecture", "architecture-as-is.svg"),
                                ("Next evolution", "architecture-next.svg"),
                                ("Target architecture", "architecture-to-be.svg")):
            self.assertIn(
                f"## {title} — System map\n\nOutput: `{filename}`\n\n```mermaid\n%%{{init", text)
        self.assertIn("The app cluster groups", text)


class CheckRenderedTest(unittest.TestCase):
    def test_positions_and_ratio(self):
        same = {key: svg(200, 100, NODES)
                for key in ("current", "next", "target")}
        self.assertEqual(build_maps.check_rendered(same)[:2], ([], []))
        moved = dict(same, target=svg(
            200, 100, [("U", 10, 10), ("A", 60, 10), ("D", 90, 10)]))
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

    def test_png_previews_go_to_the_temp_folder(self):
        # --png renders each map once more, for a look at it: the previews are
        # in the temp folder (here the test's own), never the investigation's.
        rendered = [svg(200, 100, NODES)] * 3
        before = self.files()
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(tempfile, "tempdir", tmp), \
                mock.patch.object(output_diagram, "render_many", return_value=rendered), \
                mock.patch.object(output_diagram, "render") as render:
            result = build_maps.build(INVESTIGATION, png=True)
            self.assertEqual(set(result["png"]), set(result["maps"]))
            for stage, preview in result["png"].items():
                self.assertEqual(os.path.dirname(
                    os.path.dirname(preview)), tmp, stage)
                self.assertEqual(os.path.basename(preview), f"{stage}.png")
        self.assertEqual(render.call_count, 3)
        self.assertEqual(sorted(os.listdir(self.folder)),
                         sorted(before + ["architecture-as-is.svg", "architecture-next.svg",
                                          "architecture-to-be.svg", "mermaids.md"]))

    def test_invalid_spec_or_layout_writes_nothing(self):
        moved = [svg(200, 100, NODES)] * 2 + [svg(200, 100, NODES[:1])]
        with mock.patch.object(output_diagram, "render_many", return_value=moved):
            with self.assertRaises(SystemExit) as raised:
                build_maps.build(INVESTIGATION)
        self.assertIn("A moves", str(raised.exception))
        self.assertEqual(self.files(), ["maps.json"])

    def test_malformed_spec_is_rejected_before_rendering(self):
        data = spec()
        data["nodes"] = None
        with open(os.path.join(self.folder, "maps.json"), "w", encoding="utf-8") as f:
            json.dump(data, f)
        with mock.patch.object(output_diagram, "render_many") as render:
            with self.assertRaisesRegex(SystemExit, "nodes: must be an array"):
                build_maps.build(INVESTIGATION)
        render.assert_not_called()
        self.assertEqual(self.files(), ["maps.json"])

    def test_without_node_writes_nothing(self):
        # Node.js is required: without it nothing is drawn or checked, so
        # nothing is written, and the error asks for it.
        with mock.patch.object(output_diagram.shutil, "which", return_value=None):
            with self.assertRaisesRegex(SystemExit, "Node.js 22.13 or newer is needed"):
                build_maps.build(INVESTIGATION)
        self.assertEqual(self.files(), ["maps.json"])


if __name__ == "__main__":
    unittest.main()
