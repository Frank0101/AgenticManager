# Unit tests for skills/agentic-manager-tech-investigation/scripts/output_diagram.py.
# The whole script has end-to-end tests in test_e2e_output_diagram.py.
# Run with: python3 tests/run.py agentic-manager-tech-investigation
#
# The Mermaid CLI is never run here: render() is patched, or npx is made missing.
import os
import sys
import tempfile
import unittest
from unittest import mock

# tests/<skill>/ mirrors skills/<skill>/.
TEST_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(TEST_DIR))
sys.path.insert(0, os.path.join(
    REPO_ROOT, "skills", os.path.basename(TEST_DIR), "scripts"))
import output_diagram  # noqa: E402
from agentic_manager import output_file  # noqa: E402
sys.path.insert(0, TEST_DIR)
from diagram_fixture import BAD_SVG, GOOD_SVG  # noqa: E402


class LinesTest(unittest.TestCase):
    def test_path_problems(self):
        # name: (path d, expected problem or None)
        cases = [
            ("sharp corner", "M10,10L10,50L80,50", "unrounded"),
            ("45 degrees", "M0,0L30,30", None),
            ("rounded 90-degree corner", "M10,10L10,50Q10,60 20,60L80,60", None),
            ("rounded 45-degree corner", "M0,0L0,40Q0,45 3,48L30,75", None),
            ("a sliver at an odd angle", "M10,10L10.3,10.2L10.3,40", None),
            ("a straight line at 30 degrees",
             "M0,0L52,30", "straight segment at 30°"),
            ("a long curve", "M0,0Q0,60 60,60", "85px curve"),
            ("a corner at an odd angle", "M0,0Q4,2 10,10", "corner at an angle"),
            ("an arc", "M0,0L0,10A6,6 0 0 1 0,22L0,40", "A command"),
            ("a cubic curve", "M0,0C10,0 10,10 20,10", "C command"),
            ("implicit line after move", "M0,0 52,30", "straight segment"),
            ("135-degree turn", "M0,0Q0,10 10,0", "turn is not"),
            ("missing path", "", "empty or invalid"),
            ("truncated coordinates", "M0,0L10", "incomplete"),
            ("trailing command", "M0,0L", "incomplete"),
            ("missing move", "Q0,10 10,10", "does not start"),
            ("relative coordinates", "M0,0l10,0", "relative coordinates"),
        ]
        for name, d, expected in cases:
            with self.subTest(name):
                problems = output_diagram.path_problems(d)
                if expected is None:
                    self.assertEqual(problems, [])
                else:
                    self.assertTrue(
                        any(expected in p for p in problems), problems)

    def test_line_problems_reads_only_connection_lines(self):
        svg = ('<svg><path class="node" d="M0,0L52,30"/>'
               + BAD_SVG[5:-6] + '<path class="flowchart-link" d="M0,0L0,10"/></svg>')
        self.assertEqual(output_diagram.line_problems(svg),
                         ["L_A_B_0 has a straight segment at 34°"])
        self.assertEqual(output_diagram.line_problems(GOOD_SVG), [])


class DarkStyleTest(unittest.TestCase):
    STYLED = ('<svg id="my-svg"><style>#my-svg [data-look="neo"][data-color-id="color-0"]'
              '.cluster:not(.swimlane) rect{stroke:#E879F9;fill:#FDF4FF;}</style><g/></svg>')

    def test_tints_each_subgraph_in_its_own_colour(self):
        styled = output_diagram.dark_style(self.STYLED)
        self.assertIn('#my-svg [data-color-id="color-0"].cluster:not(.swimlane) rect'
                      '{fill:#E879F9 !important;fill-opacity:0.14 !important;', styled)
        self.assertIn("#my-svg text{fill:#e4e4e7 !important;}", styled)
        self.assertTrue(styled.endswith("</style><g/></svg>"))

    def test_leaves_an_svg_without_styles_alone(self):
        self.assertEqual(output_diagram.dark_style(GOOD_SVG), GOOD_SVG)

    def test_edge_default_preserves_authored_colour_cascade(self):
        for custom in ('#my-svg .changed{stroke:#ef4444;}',
                       '#my-svg .flowchart-link{stroke:#ef4444;}',
                       '#my-svg .changed{stroke:#ef4444 !important;}'):
            with self.subTest(custom=custom):
                edge = '<path class="flowchart-link changed" style="stroke:#ef4444;stroke-width:3px" d="M0,0L10,0"/>'
                svg = ('<svg id="my-svg"><style>'
                       '#my-svg .flowchart-link{stroke:#000000;fill:none;}'
                       + custom + '</style>' + edge + '</svg>')
                styled = output_diagram.dark_style(svg)
                self.assertIn('#my-svg .flowchart-link{stroke:#a1a1aa;fill:none;}' + custom, styled)
                self.assertIn(edge, styled)
                self.assertNotIn('.flowchart-link{stroke:#a1a1aa !important;', styled)


class RetirementCrossTest(unittest.TestCase):
    def test_crosses_only_marked_rectangles_without_changing_labels(self):
        import xml.etree.ElementTree as ET
        for classes, width, count in (("node default", "100", 0),
                                      ("node decommissioned", "100", 1),
                                      ("node decommissioned", "5", 0),
                                      ("node decommissioned", "100%", 0)):
            with self.subTest(classes=classes, width=width):
                svg = (f'<svg><g class="{classes}" transform="translate(200,100)">'
                       f'<rect x="-50" y="-20" width="{width}" height="40"/>'
                       '<g class="label"><text>Service</text></g></g></svg>')
                result = output_diagram.retirement_crosses(svg)
                group = ET.fromstring(result).find("g")
                self.assertEqual(group.attrib["transform"], "translate(200,100)")
                self.assertEqual(len(group.findall("path")), count)
                self.assertEqual(group.find("g/text").text, "Service")
                self.assertEqual(output_diagram.line_problems(result), [])
                if count:
                    self.assertEqual(group.find("path").attrib["d"],
                                     "M-45,-15L45,15M-45,15L45,-15")
                    self.assertEqual(list(group)[-1].attrib["class"], "label")
                else:
                    self.assertEqual(result, svg)


class WriteTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder = os.path.join(os.path.realpath(self.tmp.name), "maps")
        os.makedirs(self.folder)
        patcher = mock.patch.object(
            output_file, "output_folder", return_value=(self.folder, False))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.render = mock.Mock(return_value=GOOD_SVG)
        for name, value in (("output_folder", mock.Mock(return_value=(self.folder, False))),
                            ("render", self.render)):
            patcher = mock.patch.object(output_diagram, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_writes_the_rendered_svg(self):
        path, temporary = output_diagram.write_output_diagram(
            "maps", "topic/map.svg", b"flowchart TB\n  A --> B\n")
        self.assertEqual((path, temporary),
                         (os.path.join(self.folder, "topic", "map.svg"), False))
        with open(path, encoding="utf-8") as f:
            self.assertEqual(f.read(), GOOD_SVG)
        self.render.assert_called_once_with(
            "flowchart TB\n  A --> B\n", "default")

    def test_refusals_write_nothing(self):
        cases = [
            ("not an svg path", "map.png", b"flowchart TB", None, "must end in .svg"),
            ("not UTF-8", "map.svg", b"\xff\xfe", None, "not UTF-8"),
            ("empty", "map.svg", b"  \n", None, "empty"),
            ("outside the folder", "../map.svg",
             b"flowchart TB", None, "without .."),
            ("lines break the rules", "map.svg", b"flowchart TB", BAD_SVG,
             "lines break the rules, so nothing was written"),
        ]
        for name, relative, source, svg, expected in cases:
            with self.subTest(name):
                if svg:
                    self.render.return_value = svg
                with self.assertRaisesRegex(SystemExit, expected):
                    output_diagram.write_output_diagram(
                        "maps", relative, source)
                self.assertEqual(os.listdir(self.folder), [])

    def test_command_line(self):
        args = output_diagram.parse_args(
            ["--name", "maps", "--path", "a/map.svg"])
        self.assertEqual((args.name, args.path, args.theme),
                         ("maps", "a/map.svg", "default"))
        self.assertEqual(output_diagram.parse_args(
            ["--name", "maps", "--path", "a.svg", "--theme", "dark"]).theme, "dark")
        self.assertTrue(output_diagram.parse_args(["--check", "--png"]).png)
        for argv in (["--name", "../x", "--path", "a.svg"], ["--name", "maps"],
                     ["--name", "maps", "--path", "a.svg", "--theme", "neon"],
                     ["--name", "maps", "--path", "a.svg", "--png"]):
            with self.subTest(argv=argv), self.assertRaises(SystemExit), mock.patch("sys.stderr"):
                output_diagram.parse_args(argv)



class CheckTest(unittest.TestCase):
    """--check renders a diagram and reports its size, writing nothing; the
    line rules apply to flowcharts only."""

    def check(self, source, svg, png=False):
        with mock.patch.object(output_diagram, "render", return_value=svg) as render:
            return output_diagram.check_diagram(source.encode("utf-8"), "dark", png), render

    def test_reports_the_size_and_checks_flowchart_lines(self):
        sized = GOOD_SVG.replace("<svg>", '<svg viewBox="0 0 640.5 300">')
        result, render = self.check('%%{init: {}}%%\nflowchart LR\n  a --> b\n', sized)
        self.assertEqual(result, {"width": 640.5, "height": 300.0, "nodes": {}})
        self.assertEqual(render.call_args.args[1:], ("dark", None))
        bad = BAD_SVG.replace("<svg>", '<svg viewBox="0 0 10 10">')
        with self.assertRaises(SystemExit) as raised:
            self.check("graph TD\n  a --> b\n", bad)
        self.assertIn("break the rules", str(raised.exception))
        # A sequence's arrows aren't held to the map's line rules.
        self.assertEqual(self.check("sequenceDiagram\n  A->>B: 1. Hi\n", bad)[0], {"width": 10.0, "height": 10.0})

    def test_node_positions(self):
        svg = ('<svg><g class="nodes"><g class="node default" id="my-svg-flowchart-api-0" transform="translate(88, 34.5)">'
               '</g><g class="node default" id="flowchart-db_store-12" transform="translate(280.25,-4)"></g>'
               '<g class="cluster" id="edge"></g></g></svg>')
        self.assertEqual(output_diagram.node_positions(svg), {"api": [88.0, 34.5], "db_store": [280.25, -4.0]})

    def test_png_preview_goes_to_the_temp_folder(self):
        result, render = self.check("sequenceDiagram\n  A->>B: 1. Hi\n", '<svg viewBox="0 0 1 1">', png=True)
        self.assertTrue(result["png"].endswith("preview.png"))
        self.assertEqual(render.call_args.args[2], result["png"])

    def test_refuses_empty_or_binary_input(self):
        for source in (b"  ", b"\xff\xfe"):
            with self.subTest(source=source), self.assertRaises(SystemExit):
                output_diagram.check_diagram(source)

class RenderTest(unittest.TestCase):
    def test_render_without_node(self):
        with mock.patch.object(output_diagram.shutil, "which", return_value=None):
            with self.assertRaises(output_diagram.NodeMissing) as raised:
                output_diagram.render("flowchart TB")
        self.assertEqual(raised.exception.code, 3)

    def test_render_failures(self):
        import subprocess
        cases = [
            ("timeout", subprocess.TimeoutExpired("npx", 300), "took more than"),
            ("CLI error", subprocess.CompletedProcess(
                [], 1, "", "Error: browser missing\n    at launch\n    at run\n    at cli"), "browser missing"),
            ("missing SVG", subprocess.CompletedProcess(
                [], 0, "", ""), "doesn't render"),
        ]
        for name, result, expected in cases:
            with self.subTest(name), mock.patch.object(output_diagram.shutil, "which", return_value="npx"), \
                    mock.patch.object(output_diagram.subprocess, "run") as run:
                if isinstance(result, Exception):
                    run.side_effect = result
                else:
                    run.return_value = result
                with self.assertRaisesRegex(SystemExit, expected):
                    output_diagram.render("flowchart TB")



class RenderManyTest(unittest.TestCase):
    """render_many() renders a batch in one Mermaid CLI run; mmdc is patched."""

    def batch(self, npx, source_path, out_path, theme, source):
        self.runs.append(source)
        if "BROKEN" in source:
            raise SystemExit("the diagram doesn't render: Parse error")
        folder = os.path.dirname(out_path)
        for number in range(1, source.count("```mermaid") + 1):
            with open(os.path.join(folder, f"out-{number}.svg"), "w", encoding="utf-8") as f:
                f.write(f'<svg viewBox="0 0 {number}00 50"/>')

    def setUp(self):
        self.runs = []
        for name, value in (("mmdc", self.batch), ("shutil.which", lambda _: "/bin/npx")):
            patcher = mock.patch.object(output_diagram, name, value) if "." not in name \
                else mock.patch(f"output_diagram.{name}", value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_one_run_for_the_batch(self):
        svgs = output_diagram.render_many(["sequenceDiagram\n A->>B: x", "sequenceDiagram\n B->>A: y"])
        self.assertEqual([output_diagram.svg_size(s)[0] for s in svgs], [100.0, 200.0])
        self.assertEqual(len(self.runs), 1)
        self.assertEqual(output_diagram.render_many([]), [])

    def test_failure_names_the_diagram(self):
        with mock.patch.object(output_diagram, "render",
                               side_effect=lambda source, theme: (_ for _ in ()).throw(
                                   SystemExit("the diagram doesn't render: Parse error"))
                               if "BROKEN" in source else GOOD_SVG):
            with self.assertRaises(SystemExit) as raised:
                output_diagram.render_many(["sequenceDiagram\n A->>B: x", "BROKEN"])
        self.assertTrue(str(raised.exception).startswith("diagram 2: "))

    def test_without_node(self):
        with mock.patch("output_diagram.shutil.which", return_value=None):
            with self.assertRaises(output_diagram.NodeMissing):
                output_diagram.render_many(["sequenceDiagram"])

if __name__ == "__main__":
    unittest.main()
