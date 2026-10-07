# End-to-end test of the skill's scripts in the order the skill runs them:
# init_investigation.py, then the agent's maps.json, content.json and ledger,
# build_maps.py, make_report.py, check_report.py --handover, make_summary.py and
# save_example.py.
# Run with: python3 tests/run.py agentic-manager-tech-investigation
#
# HOME points at a temporary folder holding the test's own config, and TMPDIR at
# the same folder. A fake npx put first on PATH writes SVGs instead of running the
# Mermaid CLI, one per diagram of a Markdown batch, so no Node.js is needed.
import json
import os
import subprocess
import sys
import tempfile
import unittest

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(TEST_DIR))
SCRIPTS = os.path.join(REPO_ROOT, "skills", os.path.basename(TEST_DIR), "scripts")
LIB = os.path.join(REPO_ROOT, "skills", "agentic-manager-utils-lib", "agentic_manager")
sys.path.insert(0, SCRIPTS)
sys.path.insert(0, TEST_DIR)
from investigation_fixture import LEDGER, content, spec  # noqa: E402

FAKE_NPX = """#!{python}
import os, sys
args = sys.argv[1:]
source, out = args[args.index("-i") + 1], args[args.index("-o") + 1]
svg = ('<svg id="my-svg" viewBox="0 0 600 300"><g class="node default" id="my-svg-flowchart-A-0" '
       'transform="translate(10, 10)"><rect/></g>'
       '<path id="L_A_B_0" class="flowchart-link" d="M10,10L10,50Q10,60 20,60L80,60"/></svg>')
if source.endswith(".md"):
    with open(source) as f:
        count = f.read().count("```mermaid")
    for number in range(1, count + 1):
        with open(out[:-3] + f"-{{number}}.svg", "w") as f:
            f.write(svg)
with open(out, "w") as f:
    f.write(svg)
"""


class PipelineTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = os.path.realpath(self.tmp.name)
        config = os.path.join(self.root, ".config", "agentic-manager", "config.json")
        os.makedirs(os.path.dirname(config))
        with open(config, "w", encoding="utf-8") as f:
            json.dump({"sources": {}, "output": {"root": os.path.join(self.root, "out")}}, f)
        bin_dir = os.path.join(self.root, "bin")
        os.makedirs(bin_dir)
        npx = os.path.join(bin_dir, "npx")
        with open(npx, "w", encoding="utf-8") as f:
            f.write(FAKE_NPX.format(python=sys.executable))
        os.chmod(npx, 0o755)
        self.env = dict(os.environ, HOME=self.root, TMPDIR=self.root,
                        PATH=bin_dir + os.pathsep + os.environ["PATH"])

    def run_script(self, path, *args, stdin=""):
        proc = subprocess.run([sys.executable, path, *args], env=self.env, input=stdin.encode("utf-8"),
                              capture_output=True)
        self.assertEqual(proc.returncode, 0, proc.stderr.decode() + proc.stdout.decode())
        return json.loads(proc.stdout)

    def write(self, relative, text):
        self.run_script(os.path.join(LIB, "output_file.py"), "--name", "tech-investigations",
                        "--path", relative, stdin=text)

    def test_pipeline(self):
        started = self.run_script(os.path.join(SCRIPTS, "init_investigation.py"), "--topic", "Acme-Search")
        investigation = started["investigation"]
        self.assertTrue(investigation.startswith("Acme-Search_"))
        data = content()
        data["evidence_snapshot"] = "20" + investigation.split("_")[1]
        self.write(f"{investigation}/ledgers.md", LEDGER)
        self.write(f"{investigation}/maps.json", json.dumps(spec()))
        self.write(f"{investigation}/content.json", json.dumps(data))

        maps = self.run_script(os.path.join(SCRIPTS, "build_maps.py"), "--investigation", investigation)
        self.assertEqual(sorted(maps["maps"]), ["current", "next", "target"])
        report = self.run_script(os.path.join(SCRIPTS, "make_report.py"), "--investigation", investigation)
        self.assertTrue(report["ok"], report)
        self.assertEqual(report["path"], os.path.join(started["investigation_dir"], "Acme-Search_Report.md"))
        checked = self.run_script(os.path.join(SCRIPTS, "check_report.py"), "--report", report["path"],
                                  "--handover")
        self.assertTrue(checked["ok"], checked)

        self.write(f"{investigation}/exec-summary.json",
                   json.dumps({"max_words": 100, "body": ["Search is merged [F01](ledger:F01)."]}))
        summary = self.run_script(os.path.join(SCRIPTS, "make_summary.py"), "--investigation", investigation,
                                  "--format", "exec-summary")
        self.assertEqual(summary["words"], 4)

        example = self.run_script(os.path.join(SCRIPTS, "save_example.py"), "--investigation", investigation,
                                  "--file", "Acme-Search_Report.md", "--format", "long-analysis",
                                  "--note", "Clear current milestone.")
        self.assertEqual(sorted(os.listdir(example["example"])),
                         ["Acme-Search_Report.md", "architecture-as-is.svg", "architecture-next.svg",
                          "architecture-to-be.svg", "ledgers.md"])


if __name__ == "__main__":
    unittest.main()
