"""End-to-end test of the skill's scripts in the order the skill runs them:
init_investigation.py, then the agent's content.json and ledger,
make_report.py, check_report.py --handover and save_example.py.
Run with: python3 tests/run.py agentic-manager-tech-investigation

HOME points at a temporary folder holding the test's own config, and TMPDIR at
the same folder.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(TEST_DIR))
SCRIPTS = os.path.join(REPO_ROOT, "skills",
                       os.path.basename(TEST_DIR), "scripts")
LIB = os.path.join(REPO_ROOT, "skills",
                   "agentic-manager-utils-lib", "agentic_manager")
sys.path.insert(0, SCRIPTS)
sys.path.insert(0, TEST_DIR)
from investigation_fixture import LEDGER, SOURCES, content  # noqa: E402


class PipelineTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = os.path.realpath(self.tmp.name)
        config = os.path.join(self.root, ".config",
                              "agentic-manager", "config.json")
        os.makedirs(os.path.dirname(config))
        with open(config, "w", encoding="utf-8") as f:
            json.dump({"sources": SOURCES, "output": {
                      "root": os.path.join(self.root, "out")}}, f)
        self.env = dict(os.environ, HOME=self.root, TMPDIR=self.root)

    def run_script(self, path, *args, stdin=""):
        proc = subprocess.run([sys.executable, path, *args], env=self.env, input=stdin.encode("utf-8"),
                              capture_output=True)
        self.assertEqual(proc.returncode, 0,
                         proc.stderr.decode() + proc.stdout.decode())
        return json.loads(proc.stdout)

    def write(self, relative, text):
        self.run_script(os.path.join(LIB, "output_file.py"), "--name", "tech-investigations",
                        "--path", relative, stdin=text)

    def test_pipeline(self):
        # name: whether the user keeps it as an example.
        cases = [("kept", True), ("not kept", False)]
        for name, keep in cases:
            with self.subTest(name):
                started = self.run_script(os.path.join(
                    SCRIPTS, "init_investigation.py"), "--topic", "Acme-Search")
                investigation = started["investigation"]
                self.assertTrue(investigation.startswith("Acme-Search_"))
                data = content()
                self.write(f"{investigation}/ledger.md", LEDGER)
                self.write(f"{investigation}/content.json", json.dumps(data))

                report = self.run_script(os.path.join(
                    SCRIPTS, "make_report.py"), "--investigation", investigation)
                self.assertTrue(report["ok"], report)
                self.assertEqual(report["path"], os.path.join(
                    started["investigation_dir"], "Acme-Search_Report.md"))
                checked = self.run_script(os.path.join(SCRIPTS, "check_report.py"), "--report", report["path"],
                                          "--handover")
                self.assertTrue(checked["ok"], checked)
                self.assertEqual(sorted(os.listdir(started["investigation_dir"])),
                                 ["Acme-Search_Report.md", "content.json", "ledger.md"])
                if keep:
                    example = self.run_script(os.path.join(SCRIPTS, "save_example.py"),
                                              "--investigation", investigation, "--note", "Clear current status.")
                    self.assertEqual(sorted(os.listdir(example["example"])),
                                     ["Acme-Search_Report.md", "description.md", "ledger.md"])


if __name__ == "__main__":
    unittest.main()
