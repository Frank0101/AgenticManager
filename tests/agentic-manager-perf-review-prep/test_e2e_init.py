"""End-to-end tests for skills/agentic-manager-perf-review-prep/scripts/init_prep.py,
set_identities.py, rules.py, set_orientation.py, set_feedback.py,
set_check_ins.py, read_notes.py, fetch_work.py, set_notion.py, read_slack.py and
check_prep.py: they run each as a script,
as the agent does once the manager confirms the person and the period, then
who the person is in each source, their view, the person's previous feedback
and check-ins, and the manager's notes. Their functions have unit tests in
test_init_prep.py, test_set_identities.py, test_rules.py,
test_set_orientation.py, test_set_feedback.py, test_set_check_ins.py,
test_read_notes.py and test_check_prep.py.
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
RULES_SCRIPT = os.path.join(SCRIPTS, "rules.py")
CHECK_INS_SCRIPT = os.path.join(SCRIPTS, "set_check_ins.py")
NOTES_SCRIPT = os.path.join(SCRIPTS, "read_notes.py")
WORK_SCRIPT = os.path.join(SCRIPTS, "fetch_work.py")
NOTION_SCRIPT = os.path.join(SCRIPTS, "set_notion.py")
SLACK_SCRIPT = os.path.join(SCRIPTS, "read_slack.py")
# Absent from every service, so step 7 runs without reaching one.
IDENTITIES = {"jira-api": {"absent": True}, "github-cli": {"absent": True}, "notion-mcp": {"absent": True},
              "slack-mcp": {"absent": True}, "logseq-fs": {"links": ["Jane", "Jane Promotion"]}}
ORIENTATION = {"going_well": [{"point": "Has \"led\" the billing migration well since May, $quoted",
                               "values": ["Ownership"]}],
               "to_improve": [], "context": ["Came back from a long leave in May"]}
VALUES = [{"value": "Ownership", "meaning": "Sees work through to its end"}]
RATINGS = [{"rating": "Below", "meaning": "Misses most expectations"},
           {"rating": "Meets", "meaning": "Meets every expectation"}]
PIECE = {"start": "2025-07-01", "end": "2025-12-31", "rating": "Meets",
         "going_well": [{"point": "Delivered the billing migration on time", "values": []}],
         "to_improve": [], "context": []}


class ScriptsTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = os.path.realpath(tmp.name)
        path = os.path.join(self.root, ".config",
                            "agentic-manager", "config.json")
        os.makedirs(os.path.dirname(path))
        graph = os.path.join(self.root, "graph", "journals")
        os.makedirs(graph)
        with open(os.path.join(graph, "2026_03_10.md"), "w", encoding="utf-8") as f:
            f.write("- [[Jane]] presented the migration to the team\n")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"sources": {"local_vault": {"logseq-fs": {"enabled": True,
                                                                 "path": os.path.dirname(graph)}}},
                       "output": {"root": os.path.join(self.root, "out")},
                       "company": {"perf-review-ratings": RATINGS, "values": VALUES}}, f)

    def run_script(self, script, *args, stdin=""):
        """(exit code, stdout, stderr) of the script, given `stdin`."""
        env = dict(os.environ, HOME=self.root, TMPDIR=self.root)
        proc = subprocess.run([sys.executable, script, *args], env=env, input=stdin,
                              capture_output=True, text=True)
        return proc.returncode, proc.stdout, proc.stderr

    def test_starts_the_prep_and_checks_it(self):
        # As the skill runs them: init_prep.py starts the prep,
        # set_identities.py records who the person is, rules.py prints what
        # the summaries follow, set_orientation.py records the summary of the
        # manager's view, set_feedback.py the previous feedback and
        # set_check_ins.py the check-ins, read_notes.py hands out the notes'
        # tasks and takes their answers; check_prep.py passes the prep, and
        # fails it once the folder holds a file of the agent's.
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
            RULES_SCRIPT, "--prep", result["prep"])
        self.assertEqual(code, 0, err)
        self.assertEqual({key: value for key, value in json.loads(out).items() if key in ("values", "ratings")},
                         {"values": VALUES, "ratings": RATINGS})
        code, out, err = self.run_script(
            ORIENTATION_SCRIPT, "--prep", result["prep"], stdin=json.dumps(ORIENTATION))
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(out)["orientation"], ORIENTATION)
        code, out, err = self.run_script(FEEDBACK_SCRIPT, "--prep", result["prep"],
                                         stdin=json.dumps({"pieces": [PIECE]}))
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(out)["feedback"], {"pieces": [PIECE]})
        notes = {"pieces": [{**PIECE, "start": None, "end": None}]}
        notes["pieces"][0].pop("rating")
        code, out, err = self.run_script(CHECK_INS_SCRIPT, "--prep", result["prep"],
                                         stdin=json.dumps(notes))
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(out)["check_ins"], notes)
        code, out, err = self.run_script(
            NOTES_SCRIPT, "start", "--prep", result["prep"])
        started = json.loads(out)
        self.assertEqual((code, [line.split(": ")[0] for line in started["tasks"]],
                          started["merge"].split(": ")[0]), (0, ["Task month:2026-03"], "Task merge"), err)
        item = {"note": 1, "synopsis": "Presented the migration to the team"}
        merged = {"going_well": [{"point": item["synopsis"], "values": ["Ownership"], "dates": ["2026-03-10"]}],
                  "to_improve": [], "context": [], "in_doubt": []}
        code, out, err = self.run_script(NOTES_SCRIPT, "submit", "--prep", result["prep"], "--task",
                                         "month:2026-03", stdin=json.dumps({"items": [item]}))
        self.assertEqual(code, 0, err)
        self.assertTrue(os.path.exists(started["merge"].split(": ", 1)[1]))
        code, out, err = self.run_script(NOTES_SCRIPT, "submit", "--prep", result["prep"], "--task", "merge",
                                         stdin=json.dumps(merged))
        self.assertEqual(code, 0, err)
        code, out, err = self.run_script(
            NOTES_SCRIPT, "finished", "--prep", result["prep"])
        self.assertEqual((code, json.loads(out)["finished"]), (0, True), err)
        for script, args, stdin in ((WORK_SCRIPT, [], ""), (NOTION_SCRIPT, [], '{"absent": true}'),
                                    (SLACK_SCRIPT, ["start"], "")):
            code, out, err = self.run_script(
                script, *args, "--prep", result["prep"], stdin=stdin)
            self.assertEqual(code, 0, err)
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
                 ("feedback that isn't JSON", FEEDBACK_SCRIPT, ["--prep", "Jane-Doe_26-01-01"], 1,
                  "the input isn't JSON"),
                 ("check-ins that aren't JSON", CHECK_INS_SCRIPT, ["--prep", "Jane-Doe_26-01-01"], 1,
                  "the input isn't JSON"),
                 ("finished before start", NOTES_SCRIPT, ["finished", "--prep", "Jane-Doe_26-01-01"], 1,
                  "isn't gathered"),
                 ("rules for no prep", RULES_SCRIPT, ["--prep", "Jane-Doe_26-01-01"], 1,
                  "run init_prep.py first"),]
        for name, script, args, expected_code, expected in cases:
            with self.subTest(name):
                code, out, err = self.run_script(
                    script, *args, stdin="{not json")
                self.assertEqual((code, out), (expected_code, ""))
                self.assertIn(expected, err)


if __name__ == "__main__":
    unittest.main()
