"""End-to-end tests for skills/agentic-manager-tech-investigation/scripts/tickets.py:
they run the whole script, as the skill does, with a fake gh on the PATH, so
nothing reaches GitHub. Its functions have unit tests in test_tickets.py.
Run with: python3 tests/run.py agentic-manager-tech-investigation

HOME and TMPDIR point at a temporary folder holding the test's own config,
with github-cli enabled.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(TEST_DIR))
SCRIPT = os.path.join(REPO_ROOT, "skills", os.path.basename(
    TEST_DIR), "scripts", "tickets.py")

PR = "https://github.com/acme/api/pull/41"
# A fake gh that fails every command with FAKE_GH_ERROR on stderr.
FAKE_GH = """#!/usr/bin/env python3
import os, sys
sys.stderr.write(os.environ["FAKE_GH_ERROR"] + "\\n")
sys.exit(1)
"""


class TicketsCommandTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.home = tmp.name
        config = os.path.join(self.home, ".config", "agentic-manager")
        os.makedirs(config)
        with open(os.path.join(config, "config.json"), "w", encoding="utf-8") as f:
            json.dump(
                {"sources": {"source_control": {"github-cli": {"enabled": True}}}}, f)
        self.bin_dir = os.path.join(self.home, "bin")
        os.makedirs(self.bin_dir)
        with open(os.path.join(self.bin_dir, "gh"), "w", encoding="utf-8") as f:
            f.write(FAKE_GH)
        os.chmod(os.path.join(self.bin_dir, "gh"), 0o755)

    def run_tickets(self, message, *args):
        """The finished process of tickets.py run with `args`, its fake gh
        failing every command with `message`."""
        return subprocess.run(
            [sys.executable, SCRIPT, *args],
            env={**os.environ, "HOME": self.home, "TMPDIR": self.home, "FAKE_GH_ERROR": message,
                 "PATH": self.bin_dir + os.pathsep + os.environ["PATH"]},
            capture_output=True, text=True, check=False)

    def test_a_pull_request_github_has_none_of(self):
        # GitHub's answer, printed for its URL, and the command ends well.
        gone = "GraphQL: Could not resolve to a PullRequest with the number of 41. (repository.pullRequest)"
        process = self.run_tickets(gone, "pr", PR)
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertEqual(process.stdout,
                         f"{PR}: GitHub has no such pull request, or this account can't see it: {gone}\n")

    def test_a_gh_failure_stops(self):
        # The command stops with a non-zero exit, gh's words and the
        # library's advice on stderr, and prints nothing: no partial output.
        # name: (gh's message, the advice)
        cases = [("rate limit", "HTTP 403: API rate limit exceeded for user ID 1.",
                  "Wait a minute and run it again."),
                 ("not signed in", "HTTP 401: Bad credentials",
                  "Check that gh works (gh auth status) and run it again, or disable the github-cli source to "
                  "go on without GitHub.")]
        for name, message, advice in cases:
            with self.subTest(name):
                process = self.run_tickets(message, "pr", PR)
                self.assertEqual(process.returncode, 1, process.stderr)
                self.assertEqual(process.stdout, "")
                self.assertEqual(process.stderr.splitlines()[-1],
                                 f"GitHub couldn't be read: gh pr view {PR} --json title,state,author,body,"
                                 "reviews,comments,createdAt,mergedAt,baseRefName,headRefName,mergeCommit,url: "
                                 f"{message.rstrip('.')}. {advice}")


if __name__ == "__main__":
    unittest.main()
