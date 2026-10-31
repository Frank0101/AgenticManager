"""End-to-end test of an investigation through investigate.py's command line, as
the agent runs it: start, then next and submit for every task, with the worked
examples each task prints, until it is finished, then save_example.py.
Run with: python3 tests/run.py agentic-manager-tech-investigation

HOME points at a temporary folder holding the test's own config, and TMPDIR at
the same folder.
"""

import json
import os
import re
import subprocess
import sys
import tempfile
import unittest

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(TEST_DIR))
SCRIPTS = os.path.join(REPO_ROOT, "skills",
                       os.path.basename(TEST_DIR), "scripts")
sys.path.insert(0, SCRIPTS)
sys.path.insert(0, TEST_DIR)
import protocol  # noqa: E402
from investigation_fixture import SOURCES  # noqa: E402

INVESTIGATE = os.path.join(SCRIPTS, "investigate.py")


class InvestigationTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = os.path.realpath(self.tmp.name)
        config = os.path.join(self.root, ".config",
                              "agentic-manager", "config.json")
        os.makedirs(os.path.dirname(config))
        # The code through github-cli, answered by a stand-in gh signed in to
        # one host, so pull requests link as they do for the user.
        sources = {**SOURCES,
                   "source_control": {"github-cli": {"enabled": True}}}
        with open(config, "w", encoding="utf-8") as f:
            json.dump({"sources": sources, "output": {
                      "root": os.path.join(self.root, "out")}}, f)
        bin_dir = os.path.join(self.root, "bin")
        os.makedirs(bin_dir)
        gh = os.path.join(bin_dir, "gh")
        with open(gh, "w", encoding="utf-8") as f:
            f.write("#!/bin/sh\necho '" +
                    json.dumps({"hosts": {"github.com": [{"state": "success"}]}}) + "'\n")
        os.chmod(gh, 0o755)
        self.env = dict(os.environ, HOME=self.root, TMPDIR=self.root,
                        PATH=bin_dir + os.pathsep + os.environ["PATH"])

    def run_script(self, path, *args, stdin="", ok=True):
        proc = subprocess.run([sys.executable, path, *args], env=self.env, input=stdin.encode("utf-8"),
                              capture_output=True)
        self.assertEqual(proc.returncode == 0, ok,
                         proc.stderr.decode() + proc.stdout.decode())
        return proc.stdout.decode() if ok else proc.stderr.decode()

    def next(self):
        return self.run_script(INVESTIGATE, "next", "--investigation", self.investigation)

    def submit(self, task, data):
        """The result of submitting `data` to `task`."""
        return json.loads(self.run_script(INVESTIGATE, "submit", "--investigation", self.investigation,
                                          "--task", task, stdin=json.dumps(data)))

    def refused(self, task, data):
        """What submit says when it refuses `data`."""
        return self.run_script(INVESTIGATE, "submit", "--investigation", self.investigation, "--task", task,
                               stdin=json.dumps(data), ok=False)

    def test_an_investigation_from_start_to_handover(self):
        started = json.loads(self.run_script(
            INVESTIGATE, "start", "--topic", "Acme-Search"))
        self.investigation = started["investigation"]
        self.assertIn(
            f"{INVESTIGATE} next --investigation {self.investigation}", started["next"])
        # Each task is answered with the worked example it prints, so an example
        # the script would refuse fails here.
        task = self.next()
        self.assertTrue(task.startswith("# Task research:Q01"))
        self.assertIn(protocol.compact(protocol.example("research")), task)
        result = self.submit("research:Q01", protocol.example("research"))
        self.assertEqual(result["ids"]["[[f1]]"], "F01")
        # The answer raised a scope question, asked before any other task.
        task = self.next()
        self.assertTrue(task.startswith("# Task scope"))
        self.assertIn(protocol.compact(protocol.example("scope")), task)
        self.submit("scope", protocol.example("scope"))
        self.submit("research:Q02", {
                    "outcome": protocol.example("research-blocked")})
        for question in ("Q03", "Q04", "Q05", "Q06"):
            self.assertTrue(self.next().startswith(
                f"# Task research:{question}"))
            self.submit(f"research:{question}", {"findings": [{"key": "[[f1]]", "claim": f"Fact for {question}.",
                                                               "sources": "[[S02]]", "limits": "[[S02]]: the unread sections can't change it."}],
                                                 "outcome": {"answered": "[[f1]]"}})
        # The last finds a fact and then waits on a choice someone has to
        # make: an open decision, which the report's example cites.
        self.assertTrue(self.next().startswith("# Task research:Q08"))
        self.submit("research:Q08", {"findings": [{"key": "[[f1]]", "claim": "Fact for Q08.", "sources": "[[S02]]",
                                                   "limits": "[[S02]]: the unread sections can't change it."}],
                                     "outcome": {"blocked": {"decision": {
                                         "decision": "Which queue to use", "position": "Unresolved: Kafka or SQS",
                                         "candidates_and_constraints": "Kafka keeps replay; SQS costs less", "authority": "The team's design doc",
                                         "owner_and_next_check": "The platform team, at the next design review"}}}})
        task = self.next()
        self.assertTrue(task.startswith("# Task design"))
        self.assertIn(protocol.compact(protocol.example("design")), task)
        self.submit("design", protocol.example("design"))
        # A refused answer lists its problems and writes nothing.
        self.assertTrue(self.next().startswith("# Task review:1"))
        refused = self.refused("review:1", {"raised": [
                               {"key": "q1", "question": "Why?", "depends_on": "None"}]})
        self.assertIn("nothing was written", refused)
        self.assertTrue(self.next().startswith("# Task review:1"))
        self.submit("review:1", {"raised": []})
        task = self.next()
        self.assertTrue(task.startswith("# Task write"))
        self.assertIn(protocol.compact(protocol.example("write")), task)
        text = os.path.join(self.root, "content.json")
        with open(text, "w", encoding="utf-8") as f:
            json.dump(protocol.example("write"), f)
        written = json.loads(self.run_script(INVESTIGATE, "submit", "--investigation", self.investigation,
                                             "--task", "write", "--input", text))
        self.assertTrue(written["ok"], written)
        task = self.next()
        self.assertTrue(task.startswith("# Task finished"))
        self.assertEqual(sorted(os.listdir(started["investigation_dir"])),
                         ["Acme-Search_Report.md", "content.json", "ledger.md"])
        command = re.search(
            r"`(python3 \S+save_example.py) --investigation", task)
        self.assertIsNotNone(command)
        example = json.loads(self.run_script(os.path.join(SCRIPTS, "save_example.py"), "--investigation",
                                             self.investigation, "--note", "Clear current status."))
        self.assertEqual(sorted(os.listdir(example["example"])),
                         ["Acme-Search_Report.md", "description.md", "ledger.md"])


if __name__ == "__main__":
    unittest.main()
