"""End-to-end tests for skills/agentic-manager-utils-lib/agentic_manager/output_folder.py
and output_file.py: they run each as a script, as an agent that writes a skill's files
itself does. Their functions have unit tests in test_output_folder.py and
test_output_file.py.
Run with: python3 tests/run.py agentic-manager-utils-lib

HOME points at a temporary folder holding the test's own config, and TMPDIR at
the same folder, so a folder that falls back to the system temp folder stays
inside it.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest

# tests/<skill>/ mirrors skills/<skill>/.
TEST_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(TEST_DIR))
PACKAGE = os.path.join(REPO_ROOT, "skills",
                       os.path.basename(TEST_DIR), "agentic_manager")
FOLDER_SCRIPT = os.path.join(PACKAGE, "output_folder.py")
FILE_SCRIPT = os.path.join(PACKAGE, "output_file.py")
TOKEN = "s3cret-token"
CONTENT = "# Payments retry\n\n🟩 Existing, as 'quoted' and \"double\" text\n"


class OutputScriptsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        # The temp folder as the scripts see it, symlinks resolved (macOS's /var).
        self.root = os.path.realpath(self.tmp.name)
        self.config = os.path.join(
            self.root, ".config", "agentic-manager", "config.json")
        self.reports = os.path.join(self.root, "my reports")
        # name: (output settings, the skill's output folder, whether it is temporary)
        temp = os.path.join(self.root, "agentic-manager",
                            "tech-investigations")
        self.folders = [
            ("in the output root", {"root": self.reports},
             os.path.join(self.reports, "tech-investigations"), False),
            ("in the temp folder without an output root", None, temp, True),
            ("in the temp folder with the placeholder",
             {"root": "<path>"}, temp, True),
        ]

    def write_config(self, output=None):
        config = {"sources": {"workflow": {"jira-api": {
            "enabled": True, "base-url": "https://acme.test", "email": "me@acme.test",
            "api-token": TOKEN}}}}
        if output is not None:
            config["output"] = output
        os.makedirs(os.path.dirname(self.config), exist_ok=True)
        with open(self.config, "w", encoding="utf-8") as f:
            json.dump(config, f)

    def run_script(self, script, *args, content="", **env_changes):
        """(exit code, stdout, stderr) of the script, given `content` on its input."""
        env = dict(os.environ, HOME=self.root, TMPDIR=self.root, **env_changes)
        proc = subprocess.run([sys.executable, script, *args], env=env, input=content.encode("utf-8"),
                              capture_output=True)
        out, err = proc.stdout.decode(), proc.stderr.decode()
        self.assertNotIn(TOKEN, out + err)
        return proc.returncode, out, err

    def test_scripts_in_each_folder(self):
        # As a skill uses them: output_folder.py prints and creates the folder,
        # output_file.py writes a file in it, then patches it, and refuses the
        # same patch again, as its old text is gone.
        relative = "Payments-Retry_26-03-29/ledgers.md"
        patch = json.dumps(
            [{"old": "# Payments retry", "new": "# Updated report"}])
        for name, output, folder, temporary in self.folders:
            with self.subTest(name):
                self.write_config(output)
                code, out, err = self.run_script(
                    FOLDER_SCRIPT, "--name", "tech-investigations")
                self.assertEqual(code, 0, err)
                self.assertEqual(json.loads(out), {
                                 "folder": folder, "temporary": temporary})
                self.assertTrue(os.path.isdir(folder))
                args = ("--name", "tech-investigations", "--path", relative)
                written = {"path": os.path.join(
                    folder, relative), "temporary": temporary}
                for extra, content in (((), CONTENT), (("--patch",), patch)):
                    code, out, err = self.run_script(
                        FILE_SCRIPT, *args, *extra, content=content)
                    self.assertEqual(code, 0, err)
                    self.assertEqual(json.loads(out), written)
                code, out, err = self.run_script(
                    FILE_SCRIPT, *args, "--patch", content=patch)
                self.assertEqual((code, out), (1, ""))
                self.assertIn("match exactly once", err)
                with open(written["path"], encoding="utf-8") as f:
                    self.assertEqual(f.read(), CONTENT.replace(
                        "# Payments retry", "# Updated report"))

    def test_failures(self):
        # name: (script, whether a config exists, arguments, exit code,
        # expected on stderr)
        cases = [
            ("folder without a config", FOLDER_SCRIPT, False, ["--name", "x"], 1,
             "agentic-manager-utils-check-config"),
            ("folder named by a path", FOLDER_SCRIPT, True,
             ["--name", "../x"], 2, "must be a single folder name"),
            ("folder without a name", FOLDER_SCRIPT, True, [], 2, "--name"),
            ("file without a config", FILE_SCRIPT, False, ["--name", "x", "--path", "a.md"], 1,
             "agentic-manager-utils-check-config"),
            ("file out of the folder", FILE_SCRIPT, True, ["--name", "x", "--path", "../a.md"], 1,
             "without .."),
            ("file in a folder named by a path", FILE_SCRIPT, True, ["--name", "../x", "--path", "a.md"], 2,
             "must be a single folder name"),
            ("file without a path", FILE_SCRIPT,
             True, ["--name", "x"], 2, "--path"),
        ]
        for name, script, config, args, code, expected in cases:
            with self.subTest(name):
                if config:
                    self.write_config()
                elif os.path.exists(self.config):
                    os.remove(self.config)
                returncode, out, err = self.run_script(
                    script, *args, content=CONTENT)
                self.assertEqual(returncode, code)
                self.assertIn(expected, err)
                self.assertEqual(out, "")
        for folder in (self.root, os.path.join(self.root, "agentic-manager")):
            self.assertFalse(os.path.exists(os.path.join(folder, "a.md")))


if __name__ == "__main__":
    unittest.main()
