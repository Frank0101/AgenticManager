"""End-to-end tests for skills/agentic-manager-perf-review-prep/scripts/init_prep.py,
set_identities.py, set_orientation.py, set_feedback.py and check_prep.py: they
run each as a script, as the agent does once the manager confirms the person
and the period, then who the person is in each source, their view and the
person's previous feedback. Their functions have unit tests in
test_init_prep.py, test_set_identities.py, test_set_orientation.py,
test_set_feedback.py and test_check_prep.py.
Run with: python3 tests/run.py agentic-manager-perf-review-prep

HOME points at a temporary folder holding the test's own config, and TMPDIR at
the same folder, so nothing falls back to the system temp folder.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import date

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(TEST_DIR))
SCRIPTS = os.path.join(REPO_ROOT, "skills",
                       os.path.basename(TEST_DIR), "scripts")
INIT_SCRIPT = os.path.join(SCRIPTS, "init_prep.py")
CHECK_SCRIPT = os.path.join(SCRIPTS, "check_prep.py")
IDENTITIES_SCRIPT = os.path.join(SCRIPTS, "set_identities.py")
ORIENTATION_SCRIPT = os.path.join(SCRIPTS, "set_orientation.py")
FEEDBACK_SCRIPT = os.path.join(SCRIPTS, "set_feedback.py")
IDENTITIES = {"jira-api": {"id": "5b10ac8d82e05b22cc7d4ef5", "name": "Jane Doe"},
              "github-cli": {"absent": True}, "notion-mcp": {"absent": True},
              "slack-mcp": {"id": "U012AB3CD", "name": "Jane Doe (she/her)"},
              "logseq-fs": {"links": ["Jane", "Jane Promotion"]}}
ORIENTATION = {"going_well": ["Has \"led\" the billing migration well since May, $quoted"],
               "to_improve": [], "context": ["Came back from a long leave in May"]}
RATINGS = [{"rating": "Below", "meaning": "Misses most expectations"},
           {"rating": "Meets", "meaning": "Meets every expectation"}]
REVIEW = {"start": "2025-07-01", "end": "2025-12-31", "rating": "Meets",
          "going_well": ["Delivered the billing migration on time"], "to_improve": [], "context": []}


class ScriptsTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = os.path.realpath(tmp.name)
        path = os.path.join(self.root, ".config",
                            "agentic-manager", "config.json")
        os.makedirs(os.path.dirname(path))
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"sources": {}, "output": {"root": os.path.join(self.root, "out")},
                       "company": {"perf-review-ratings": RATINGS}}, f)

    def run_script(self, script, *args, stdin=""):
        """(exit code, stdout, stderr) of the script, given `stdin`."""
        env = dict(os.environ, HOME=self.root, TMPDIR=self.root)
        proc = subprocess.run([sys.executable, script, *args], env=env, input=stdin,
                              capture_output=True, text=True)
        return proc.returncode, proc.stdout, proc.stderr

    def test_starts_the_prep_and_checks_it(self):
        # As the skill runs them: init_prep.py starts the prep,
        # set_identities.py records who the person is, set_orientation.py the
        # summary of the manager's view, and set_feedback.py prints the rules
        # of the previous feedback and records it; check_prep.py passes it,
        # and fails it once the folder holds a file of the agent's.
        today = date.today()
        code, out, err = self.run_script(INIT_SCRIPT, "--person", "Jane Doe", "--start", "2026-01-01",
                                         "--end", today.isoformat())
        self.assertEqual(code, 0, err)
        result = json.loads(out)
        self.assertEqual(result["prep"], f"Jane-Doe_{today:%y-%m-%d}")
        self.assertEqual(result["request"]["person"], "Jane Doe")
        code, out, err = self.run_script(IDENTITIES_SCRIPT, "--prep", result["prep"],
                                         stdin=json.dumps(IDENTITIES))
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(out)["identities"], IDENTITIES)
        code, out, err = self.run_script(
            ORIENTATION_SCRIPT, "--prep", result["prep"], stdin=json.dumps(ORIENTATION))
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(out)["orientation"], ORIENTATION)
        code, out, err = self.run_script(
            FEEDBACK_SCRIPT, "rules", "--prep", result["prep"])
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(out)["ratings"], RATINGS)
        code, out, err = self.run_script(FEEDBACK_SCRIPT, "write", "--prep", result["prep"],
                                         stdin=json.dumps({"reviews": [REVIEW]}))
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(out)["feedback"], {"reviews": [REVIEW]})
        code, out, err = self.run_script(
            CHECK_SCRIPT, "--prep", result["prep"])
        self.assertEqual((code, json.loads(out)),
                         (0, {"ok": True, "errors": []}), err)
        open(os.path.join(result["prep_dir"], "draft.md"), "w").close()
        code, out, err = self.run_script(
            CHECK_SCRIPT, "--prep", result["prep"])
        self.assertEqual(code, 1)
        self.assertIn("draft.md", out)

    def test_failures(self):
        # name: (script, arguments, exit code, expected on stderr)
        cases = [("no person", INIT_SCRIPT, ["--start", "2026-01-01", "--end", "2026-06-30"], 2, "--person"),
                 ("not a date", INIT_SCRIPT, ["--person", "Jane Doe", "--start", "01/01/2026",
                                              "--end", "2026-06-30"], 2, "YYYY-MM-DD"),
                 ("ends after today", INIT_SCRIPT, ["--person", "Jane Doe", "--start", "2026-01-01",
                                                    "--end", "2999-01-01"], 1, "after today"),
                 ("no such prep", CHECK_SCRIPT, [
                  "--prep", "Jane-Doe_26-01-01"], 1, "run init_prep.py first"),
                 ("identities that aren't JSON", IDENTITIES_SCRIPT, ["--prep", "Jane-Doe_26-01-01"], 1,
                  "the input isn't JSON"),
                 ("an orientation that isn't JSON", ORIENTATION_SCRIPT, ["--prep", "Jane-Doe_26-01-01"], 1,
                  "the input isn't JSON"),
                 ("feedback that isn't JSON", FEEDBACK_SCRIPT, ["write", "--prep", "Jane-Doe_26-01-01"], 1,
                  "the input isn't JSON"),
                 ("rules for no prep", FEEDBACK_SCRIPT, ["rules", "--prep", "Jane-Doe_26-01-01"], 1,
                  "run init_prep.py first"),
                 ("no command", FEEDBACK_SCRIPT, ["--prep", "Jane-Doe_26-01-01"], 2, "rules,write")]
        for name, script, args, expected_code, expected in cases:
            with self.subTest(name):
                code, out, err = self.run_script(
                    script, *args, stdin="{not json")
                self.assertEqual((code, out), (expected_code, ""))
                self.assertIn(expected, err)


if __name__ == "__main__":
    unittest.main()
