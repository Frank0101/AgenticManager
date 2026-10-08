# End-to-end tests for skills/agentic-manager-tech-investigation/scripts/output_diagram.py:
# they run the whole script, as the skill does to try a diagram. Its functions have
# unit tests in test_output_diagram.py.
# Run with: python3 tests/run.py agentic-manager-tech-investigation
#
# HOME and TMPDIR point at a temporary folder. A fake npx put first on PATH writes a
# given SVG instead of running the Mermaid CLI, so no Node.js or network is needed.
import json
import os
import subprocess
import sys
import tempfile
import unittest

# tests/<skill>/ mirrors skills/<skill>/.
TEST_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(TEST_DIR))
SCRIPT = os.path.join(REPO_ROOT, "skills", os.path.basename(TEST_DIR),
                      "scripts", "output_diagram.py")
sys.path.insert(0, TEST_DIR)
from diagram_fixture import BAD_SVG, GOOD_SVG  # noqa: E402

DIAGRAM = "flowchart TB\n  A --> B\n"
SIZED_SVG = GOOD_SVG.replace("<svg>", '<svg viewBox="0 0 640 320">')
# Stands in for npx: records its arguments, then writes $FAKE_SVG to the -o path,
# or fails when $FAKE_SVG is empty.
FAKE_NPX = """#!{python}
import os, sys
with open(os.environ["FAKE_ARGS"], "w") as f:
    f.write(" ".join(sys.argv[1:]))
svg = os.environ.get("FAKE_SVG", "")
if not svg:
    sys.exit("Parse error on line 2")
with open(sys.argv[sys.argv.index("-o") + 1], "w") as f:
    f.write(svg)
"""


class OutputDiagramScriptTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        # The temp folder as the script sees it, symlinks resolved (macOS's /var).
        self.root = os.path.realpath(self.tmp.name)
        self.args_file = os.path.join(self.root, "npx-args")

    def run_script(self, *args, content=DIAGRAM, **env_changes):
        """(exit code, stdout, stderr) of the script, given `content` on its input."""
        env = dict(os.environ, HOME=self.root, TMPDIR=self.root,
                   FAKE_ARGS=self.args_file, **env_changes)
        proc = subprocess.run([sys.executable, SCRIPT, *args], env=env, input=content.encode("utf-8"),
                              capture_output=True)
        return proc.returncode, proc.stdout.decode(), proc.stderr.decode()

    def fake_npx(self):
        """A folder holding the fake npx, for PATH."""
        bin_dir = os.path.join(self.root, "bin")
        os.makedirs(bin_dir, exist_ok=True)
        npx = os.path.join(bin_dir, "npx")
        with open(npx, "w", encoding="utf-8") as f:
            f.write(FAKE_NPX.format(python=sys.executable))
        os.chmod(npx, 0o755)
        return bin_dir

    def test_renders_and_reports_the_size(self):
        before = sorted(os.listdir(self.root))
        code, out, err = self.run_script(
            "--theme", "dark", PATH=self.fake_npx(), FAKE_SVG=SIZED_SVG)
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(out), {
                         "width": 640.0, "height": 320.0, "nodes": {}})
        with open(self.args_file, encoding="utf-8") as f:
            args = f.read()
        self.assertRegex(
            args, r"^-y -p @mermaid-js/mermaid-cli@[\d.]+ mmdc -i ")
        self.assertIn("-b #1e1e1e", args)
        self.assertNotIn("-t ", args)
        # Nothing is written beside the fake npx and its record.
        self.assertEqual(sorted(os.listdir(self.root)),
                         sorted(before + ["bin", "npx-args"]))

    def test_failures(self):
        # name: (PATH, the SVG the fake renders, exit code, expected on stderr)
        empty_bin = os.path.join(self.root, "empty-bin")
        os.makedirs(empty_bin)
        cases = [
            ("without Node.js", empty_bin, SIZED_SVG,
             3, "Node.js (npx) is not available"),
            ("a diagram that doesn't render", None, "",
             1, "doesn't render: Parse error on line 2"),
            ("slanted lines", None, BAD_SVG, 1, "lines break the rules"),
        ]
        for name, path_dir, svg, code, expected in cases:
            with self.subTest(name):
                returncode, out, err = self.run_script(
                    PATH=path_dir or self.fake_npx(), FAKE_SVG=svg)
                self.assertEqual(returncode, code, err)
                self.assertIn(expected, err)
                self.assertEqual(out, "")


if __name__ == "__main__":
    unittest.main()
