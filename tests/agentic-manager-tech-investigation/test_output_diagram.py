"""Unit tests for skills/agentic-manager-tech-investigation/scripts/output_diagram.py.
The whole script has end-to-end tests in test_e2e_output_diagram.py.
Run with: python3 tests/run.py agentic-manager-tech-investigation

The Mermaid CLI is never run here: render() or mmdc() is patched, or npx is made missing.
"""

import os
import subprocess
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

SIZED_SVG = '<svg viewBox="0 0 640.5 300"/>'


class CommandLineTest(unittest.TestCase):
    def test_command_line(self):
        self.assertFalse(output_diagram.parse_args([]).png)
        self.assertTrue(output_diagram.parse_args(["--png"]).png)
        for argv in (["--theme", "dark"], ["--name", "maps"]):
            with self.subTest(argv=argv), self.assertRaises(SystemExit), mock.patch("sys.stderr"):
                output_diagram.parse_args(argv)


class CheckTest(unittest.TestCase):
    """check_diagram() renders a diagram and reports its size, writing nothing."""

    def check(self, source, png=False):
        with mock.patch.object(output_diagram, "render", return_value=SIZED_SVG) as render:
            return output_diagram.check_diagram(source.encode("utf-8"), png), render

    def test_reports_the_size(self):
        result, render = self.check("sequenceDiagram\n  A->>B: Hi\n")
        self.assertEqual(result, {"width": 640.5, "height": 300.0})
        self.assertEqual(render.call_args.args[1:], (None,))

    def test_png_preview_goes_to_the_temp_folder(self):
        # The temp folder is the test's own, so no preview folder is left behind.
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(tempfile, "tempdir", tmp):
            result, render = self.check(
                "sequenceDiagram\n  A->>B: Hi\n", png=True)
            self.assertEqual(os.path.dirname(
                os.path.dirname(result["png"])), tmp)
        self.assertEqual(os.path.basename(result["png"]), "preview.png")
        self.assertEqual(render.call_args.args[1], result["png"])

    def test_refuses_empty_or_binary_input(self):
        for source in (b"  ", b"\xff\xfe"):
            with self.subTest(source=source), self.assertRaises(SystemExit):
                output_diagram.check_diagram(source)


class RenderTest(unittest.TestCase):
    def test_without_node(self):
        # Node.js is required, with no unchecked fallback: the message asks for it.
        for name, call in (("render", lambda: output_diagram.render("sequenceDiagram")),
                           ("render_many", lambda: output_diagram.render_many(["sequenceDiagram"]))):
            with self.subTest(name), mock.patch.object(output_diagram.shutil, "which", return_value=None):
                with self.assertRaisesRegex(SystemExit, "Node.js 22.13 or newer is needed"):
                    call()

    def test_render_failures(self):
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
                    output_diagram.render("sequenceDiagram")


class RenderManyTest(unittest.TestCase):
    """render_many() renders a batch in one Mermaid CLI run; mmdc is patched."""

    def batch(self, npx, source_path, out_path, source):
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
        svgs = output_diagram.render_many(
            ["sequenceDiagram\n A->>B: x", "sequenceDiagram\n B->>A: y"])
        self.assertEqual([output_diagram.svg_size(s)[0]
                         for s in svgs], [100.0, 200.0])
        self.assertEqual(len(self.runs), 1)
        self.assertEqual(output_diagram.render_many([]), [])

    def test_failure_names_the_diagram(self):
        def render(source, png=None):
            if "BROKEN" in source:
                raise SystemExit("the diagram doesn't render: Parse error")
            return SIZED_SVG
        with mock.patch.object(output_diagram, "render", side_effect=render):
            with self.assertRaises(SystemExit) as raised:
                output_diagram.render_many(
                    ["sequenceDiagram\n A->>B: x", "BROKEN"])
        self.assertTrue(str(raised.exception).startswith("diagram 2: "))


if __name__ == "__main__":
    unittest.main()
