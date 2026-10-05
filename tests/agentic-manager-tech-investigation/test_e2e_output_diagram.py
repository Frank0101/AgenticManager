# End-to-end tests for skills/agentic-manager-tech-investigation/scripts/output_diagram.py:
# they run the whole script, as the skill does. Its functions have unit tests in
# test_output_diagram.py.
# Run with: python3 tests/run.py agentic-manager-tech-investigation
#
# HOME points at a temporary folder holding the test's own config, and TMPDIR at the
# same folder. A fake npx put first on PATH writes a given SVG instead of running the
# Mermaid CLI, so no Node.js or network is needed.
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
TOKEN = "s3cret-token"


class OutputDiagramScriptTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        # The temp folder as the script sees it, symlinks resolved (macOS's /var).
        self.root = os.path.realpath(self.tmp.name)
        self.config = os.path.join(
            self.root, ".config", "agentic-manager", "config.json")
        self.reports = os.path.join(self.root, "my reports")
        config = {"sources": {"workflow": {"jira-api": {
            "enabled": True, "base-url": "https://acme.test", "email": "me@acme.test",
            "api-token": TOKEN}}}, "output": {"root": self.reports}}
        os.makedirs(os.path.dirname(self.config))
        with open(self.config, "w", encoding="utf-8") as f:
            json.dump(config, f)

    def run_script(self, *args, content=DIAGRAM, **env_changes):
        """(exit code, stdout, stderr) of the script, given `content` on its input."""
        env = dict(os.environ, HOME=self.root, TMPDIR=self.root, **env_changes)
        proc = subprocess.run([sys.executable, SCRIPT, *args], env=env, input=content.encode("utf-8"),
                              capture_output=True)
        out, err = proc.stdout.decode(), proc.stderr.decode()
        self.assertNotIn(TOKEN, out + err)
        return proc.returncode, out, err

    def fake_npx(self):
        """A folder holding the fake npx, for PATH."""
        bin_dir = os.path.join(self.root, "bin")
        os.makedirs(bin_dir, exist_ok=True)
        npx = os.path.join(bin_dir, "npx")
        with open(npx, "w", encoding="utf-8") as f:
            f.write(FAKE_NPX.format(python=sys.executable))
        os.chmod(npx, 0o755)
        return bin_dir

    def test_renders_and_writes(self):
        args_file = os.path.join(self.root, "npx-args")
        code, out, err = self.run_script("--name", "tech-investigations",
                                         "--path", "2026-03-29--payments-retry/architecture-map.svg", "--theme", "dark",
                                         PATH=self.fake_npx(), FAKE_SVG=GOOD_SVG,
                                         FAKE_ARGS=args_file)
        self.assertEqual(code, 0, err)
        path = os.path.join(self.reports, "tech-investigations",
                            "2026-03-29--payments-retry", "architecture-map.svg")
        self.assertEqual(json.loads(out), {"path": path, "temporary": False})
        with open(path, encoding="utf-8") as f:
            self.assertEqual(f.read(), GOOD_SVG)  # no <style> to restyle
        with open(args_file, encoding="utf-8") as f:
            args = f.read()
        self.assertRegex(
            args, r"^-y -p @mermaid-js/mermaid-cli@[\d.]+ mmdc -i ")
        self.assertIn("-b #1e1e1e", args)
        self.assertNotIn("-t ", args)

    def test_failures(self):
        # name: (PATH, the SVG the fake renders, exit code, expected on stderr)
        empty_bin = os.path.join(self.root, "empty-bin")
        os.makedirs(empty_bin)
        cases = [
            ("without Node.js", empty_bin, GOOD_SVG,
             3, "Node.js (npx) is not available"),
            ("a diagram that doesn't render", None, "",
             1, "doesn't render: Parse error on line 2"),
            ("slanted lines", None, BAD_SVG, 1, "lines break the rules"),
        ]
        for name, path_dir, svg, code, expected in cases:
            with self.subTest(name):
                returncode, out, err = self.run_script(
                    "--name", "maps", "--path", "map.svg",
                    PATH=path_dir or self.fake_npx(), FAKE_SVG=svg,
                    FAKE_ARGS=os.path.join(self.root, "npx-args"))
                self.assertEqual(returncode, code, err)
                self.assertIn(expected, err)
                self.assertEqual(out, "")
                self.assertFalse(os.path.exists(
                    os.path.join(self.reports, "maps", "map.svg")))


if __name__ == "__main__":
    unittest.main()
