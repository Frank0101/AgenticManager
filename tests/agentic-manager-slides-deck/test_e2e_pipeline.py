"""End-to-end test of the skill's scripts in the order the skill runs them:
init_deck.py, the agent's slides.json written and patched through the
library's output_file.py, and make_deck.py, whose check check_deck.py agrees
with when run on its own.
Run with: python3 tests/run.py agentic-manager-slides-deck

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
from deck_fixture import content  # noqa: E402


class PipelineTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = os.path.realpath(self.tmp.name)
        config = os.path.join(self.root, ".config",
                              "agentic-manager", "config.json")
        os.makedirs(os.path.dirname(config))
        with open(config, "w", encoding="utf-8") as f:
            json.dump({"sources": {}, "output": {
                      "root": os.path.join(self.root, "out")}}, f)
        self.env = dict(os.environ, HOME=self.root, TMPDIR=self.root)

    def run_script(self, path, *args, stdin="", code=0):
        proc = subprocess.run([sys.executable, path, *args], env=self.env, input=stdin.encode("utf-8"),
                              capture_output=True)
        self.assertEqual(proc.returncode, code,
                         proc.stderr.decode() + proc.stdout.decode())
        return proc

    def write(self, relative, text, *flags):
        self.run_script(os.path.join(LIB, "output_file.py"), "--name", "slides-decks",
                        "--path", relative, *flags, stdin=text)

    def test_build_fix_and_revise_a_deck(self):
        started = json.loads(self.run_script(
            os.path.join(SCRIPTS, "init_deck.py"), "--name", "Acme-Q3-Review").stdout)
        deck = started["deck"]
        self.assertEqual(started["deck_dir"], os.path.join(
            self.root, "out", "slides-decks", deck))
        # A first draft with a problem: the script names the field and writes nothing.
        data = content()
        data["slides"][0]["html"].append("<div>")
        self.write(started["slides_path"], json.dumps(data, indent=2))
        failed = self.run_script(os.path.join(
            SCRIPTS, "make_deck.py"), "--deck", deck, code=1)
        self.assertIn("slides[0].html: <div> opened on line 3 is never closed",
                      failed.stderr.decode())
        self.assertEqual(os.listdir(started["deck_dir"]), ["slides.json"])
        # Fixed, it builds and passes.
        self.write(started["slides_path"], json.dumps(content(), indent=2))
        built = json.loads(self.run_script(
            os.path.join(SCRIPTS, "make_deck.py"), "--deck", deck).stdout)
        self.assertEqual({k: built[k] for k in ("ok", "errors", "placeholders", "temporary")},
                         {"ok": True, "errors": [], "placeholders": ["[IMAGE: team photo]"],
                          "temporary": False})
        # A revision patches slides.json and rebuilds.
        self.write(started["slides_path"], json.dumps(
            [{"old": "[IMAGE: team photo]", "new": "Team of 6"}]), "--patch")
        revised = json.loads(self.run_script(
            os.path.join(SCRIPTS, "make_deck.py"), "--deck", deck).stdout)
        self.assertEqual(revised["placeholders"], [])
        with open(revised["path"], encoding="utf-8") as f:
            self.assertIn("Team of 6", f.read())
        checked = json.loads(self.run_script(
            os.path.join(SCRIPTS, "check_deck.py"), "--deck", deck).stdout)
        self.assertEqual(
            checked, {"ok": True, "errors": [], "placeholders": [], "stand_ins": []})


if __name__ == "__main__":
    unittest.main()
