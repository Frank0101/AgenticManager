"""Unit tests for skills/agentic-manager-perf-review-prep/scripts/find_jira_account.py.
Run as a script, it has end-to-end tests in test_e2e_init.py.
Run with: python3 tests/run.py agentic-manager-perf-review-prep

Jira is a fake client, so nothing reaches it.
"""

import os
import sys
import unittest

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(TEST_DIR))
sys.path.insert(0, os.path.join(REPO_ROOT, "skills",
                os.path.basename(TEST_DIR), "scripts"))
import find_jira_account  # noqa: E402

JANE = {"accountId": "a1", "displayName": "Jane Doe",
        "emailAddress": "jane@acme.test", "active": True}
JANET = {"accountId": "a2", "displayName": "Janet Doe",
         "emailAddress": None, "active": True}


class FakeJira:
    """Answers users() from `found`, {query: accounts}, recording each query."""

    def __init__(self, found):
        self.found, self.queries = found, []

    def users(self, query):
        self.queries.append(query)
        return self.found.get(query, [])


class FindJiraAccountTest(unittest.TestCase):
    def test_jira_candidates(self):
        # name: (Jira's answers by query, the accounts expected, the queries
        # expected): the full name first; each word of it only when that
        # finds no one, each account once.
        cases = [("the full name", {"Jane Doe": [JANE]}, [JANE], ["Jane Doe"]),
                 ("each word", {"jane": [JANE], "doe": [JANE, JANET]}, [JANE, JANET],
                  ["Jane Doe", "jane", "doe"]),
                 ("no one", {}, [], ["Jane Doe", "jane", "doe"])]
        for name, found, expected, queries in cases:
            with self.subTest(name):
                client = FakeJira(found)
                self.assertEqual(find_jira_account.jira_candidates(
                    client, "Jane Doe"), expected)
                self.assertEqual(client.queries, queries)

    def test_find(self):
        # The name as given, its spaces tidied, and the accounts it finds.
        self.assertEqual(find_jira_account.find("  Jane   Doe ", client=FakeJira({"Jane Doe": [JANE]})),
                         {"person": "Jane Doe", "accounts": [JANE]})


if __name__ == "__main__":
    unittest.main()
