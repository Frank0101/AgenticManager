# End-to-end tests for skills/agentic-manager-utils-refactoring/scripts/precheck.py:
# they run the whole script, as the skill does. Its functions have unit tests in
# test_precheck.py.
# Run with: python3 tests/run.py agentic-manager-utils-refactoring
#
# The script runs on a made-up git repository in a temporary folder. A fake npx
# put first on PATH prints pyright's JSON instead of running pyright, so no
# Node.js or network is needed.
import json
import os
import subprocess
import sys
import tempfile
import unittest

# tests/<skill>/ mirrors skills/<skill>/.
TEST_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(TEST_DIR))
SCRIPT = os.path.join(REPO_ROOT, "skills", os.path.basename(
    TEST_DIR), "scripts", "precheck.py")

# Stands in for npx: prints one pyright error in the repo it runs in.
FAKE_NPX = """#!{python}
import json, os
print(json.dumps({{"generalDiagnostics": [{{"file": os.path.join(os.getcwd(), "tool.py"), "severity": "error",
    "message": "bad type", "range": {{"start": {{"line": 1}}}}}}]}}))
"""
FILES = {
    "tool.py": "import os\n\n\ndef main():\n    pass\n",
    "tests/test_tool.py": "def test_run():\n    pass\n\n\ndef test_run_errors():\n    pass\n",
    "README.md": "Run `tool.py --fast`; see [the guide](guide.md) and test_old.\n",
}


class PrecheckScriptTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = os.path.realpath(tmp.name)
        self.repo = os.path.join(self.root, "repo")
        for path, text in FILES.items():
            os.makedirs(os.path.dirname(
                os.path.join(self.repo, path)), exist_ok=True)
            with open(os.path.join(self.repo, path), "w", encoding="utf-8") as f:
                f.write(text)
        subprocess.run(["git", "init", "-q", self.repo], check=True)
        bin_dir = os.path.join(self.root, "bin")
        os.makedirs(bin_dir)
        with open(os.path.join(bin_dir, "npx"), "w", encoding="utf-8") as f:
            f.write(FAKE_NPX.format(python=sys.executable))
        os.chmod(os.path.join(bin_dir, "npx"), 0o755)
        self.path = bin_dir + os.pathsep + os.environ["PATH"]

    def run_script(self, *args, cwd=None):
        return subprocess.run([sys.executable, SCRIPT, *args], cwd=cwd or self.repo, capture_output=True, text=True,
                              env=dict(os.environ, PATH=self.path, HOME=self.root, TMPDIR=self.root))

    def test_leads_of_every_check(self):
        # From the repo's own folder or with --root, the same one line of JSON,
        # and the repo is left as it was.
        before = subprocess.run(
            ["git", "-C", self.repo, "status", "--short"], capture_output=True, text=True).stdout
        for name, args, cwd in (("in the repo", [], None), ("with --root", ["--root", self.repo], self.root)):
            with self.subTest(name):
                proc = self.run_script(*args, cwd=cwd)
                self.assertEqual(proc.returncode, 0, proc.stderr)
                self.assertEqual(len(proc.stdout.splitlines()), 1, proc.stdout)
                out = json.loads(proc.stdout)
                self.assertEqual([(lead["check"], lead["file"], lead["line"]) for lead in out["leads"]], [
                    ("missing-file", "README.md",
                     1), ("unknown-flag", "README.md", 1),
                    ("unknown-test", "README.md",
                     1), ("similar-tests", "tests/test_tool.py", 5),
                    ("unused-import", "tool.py", 1), ("type", "tool.py", 2)])
                self.assertEqual(out["tests"], {
                                 "tests/test_tool.py": [[1, "test_run"], [5, "test_run_errors"]]})
                self.assertEqual(out["skipped"], [])
        self.assertEqual(subprocess.run(["git", "-C", self.repo, "status", "--short"],
                                        capture_output=True, text=True).stdout, before)

    def test_outside_a_repository(self):
        proc = self.run_script(cwd=self.root)
        self.assertEqual((proc.returncode, proc.stdout), (1, ""))
        self.assertIn("not in a git repository: pass --root", proc.stderr)


if __name__ == "__main__":
    unittest.main()
