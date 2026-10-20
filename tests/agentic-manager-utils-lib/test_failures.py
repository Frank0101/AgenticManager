"""Unit tests for skills/agentic-manager-utils-lib/agentic_manager/failures.py.
Run with: python3 tests/run.py agentic-manager-utils-lib
"""

import os
import sys
import unittest

# tests/<skill>/ mirrors skills/<skill>/.
TEST_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(TEST_DIR))
sys.path.insert(0, os.path.join(
    REPO_ROOT, "skills", os.path.basename(TEST_DIR)))
from agentic_manager.failures import stops_on_failure  # noqa: E402
from agentic_manager.github import GH_BROKEN, GhError  # noqa: E402
from agentic_manager.jira import JiraError  # noqa: E402
from agentic_manager.retry import RATE_LIMITED  # noqa: E402


class StopsOnFailureTest(unittest.TestCase):
    def test_stops_with_the_message(self):
        # A Jira or gh failure stops the program, its message the line shown
        # on stderr, as SystemExit shows it, with exit code 1.
        # name: (what the block raises, the lead given or None, the message)
        cases = [
            ("Jira, with advice", JiraError("Jira returned 401 Unauthorized for /rest/api/3/myself.",
                                            "Check your `api-token`."), None,
             "Jira returned 401 Unauthorized for /rest/api/3/myself. Check your `api-token`."),
            ("Jira, without", JiraError("Jira returned 500 for /rest/api/3/myself."), None,
             "Jira returned 500 for /rest/api/3/myself."),
            ("gh", GhError(["pr", "view", "https://github.com/acme/api/pull/1", "--json", "url"],
                           "HTTP 401: Bad credentials"), None,
             f"GitHub couldn't be read: gh pr view: HTTP 401: Bad credentials. {GH_BROKEN}"),
            ("gh, with a lead", GhError(["api", "graphql"], "API rate limit exceeded."),
             "GitHub couldn't be read, so no report was written",
             f"GitHub couldn't be read, so no report was written: gh api graphql: API rate limit exceeded. "
             f"{RATE_LIMITED}"),
        ]
        for name, error, lead, expected in cases:
            with self.subTest(name), self.assertRaises(SystemExit) as stopped:
                with stops_on_failure(*([lead] if lead else [])):
                    raise error
            self.assertEqual(stopped.exception.code, expected)

    def test_anything_else_passes(self):
        # A block that ends is left alone, and any other error is raised as it is.
        with stops_on_failure():
            done = True
        self.assertTrue(done)
        for error in (ValueError("bad"), SystemExit("usage")):
            with self.subTest(error=error), self.assertRaises(type(error)) as raised:
                with stops_on_failure():
                    raise error
            self.assertIs(raised.exception, error)


if __name__ == "__main__":
    unittest.main()
