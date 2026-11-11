"""Unit tests for skills/agentic-manager-perf-review-prep/scripts/jira_ticket.py.
Run with: python3 tests/run.py agentic-manager-perf-review-prep

Jira is a fake client, so nothing reaches a service.
"""

import os
import sys
import unittest

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(TEST_DIR))
sys.path.insert(0, os.path.join(REPO_ROOT, "skills",
                os.path.basename(TEST_DIR), "scripts"))
import jira_ticket  # noqa: E402


class FakeJira:
    """Answers issue() and comments() for the one ticket it holds."""

    def issue(self, key, fields):
        if key != "PROJ-1":
            return None, f"{key}: no such ticket"
        return {"key": "PROJ-1", "fields": {"summary": "Migrate billing", "status": {"name": "Done"},
                                            "assignee": {"displayName": "Jane Doe"},
                                            "description": "Move billing to the new service"}}, None

    def comments(self, key):
        return [{"author": {"displayName": "Sam Roe"}, "created": "2026-08-20T10:00:00.000+0100",
                 "body": "Great work, shipped early"}]


class JiraTicketTest(unittest.TestCase):
    def test_ticket_text(self):
        self.assertEqual(jira_ticket.ticket_text(FakeJira(), "PROJ-1"), "\n".join([
            "PROJ-1: Migrate billing", "Status: Done", "Assignee: Jane Doe", "", "Description:",
            "Move billing to the new service", "", "Comment by Sam Roe, 2026-08-20:", "Great work, shipped early"]))
        # A ticket that can't be read is answered with why.
        self.assertEqual(jira_ticket.ticket_text(
            FakeJira(), "PROJ-2"), "PROJ-2: no such ticket")


if __name__ == "__main__":
    unittest.main()
