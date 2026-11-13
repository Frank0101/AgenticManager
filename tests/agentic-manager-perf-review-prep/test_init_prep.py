"""Unit tests for skills/agentic-manager-perf-review-prep/scripts/init_prep.py.
Run as a script, it has end-to-end tests in test_e2e_init.py.
Run with: python3 tests/run.py agentic-manager-perf-review-prep

The config's path is patched to the test's own config, in a temporary folder.
"""

import json
import os
import sys
import unittest
from datetime import date

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(TEST_DIR))
sys.path.insert(0, os.path.join(REPO_ROOT, "skills",
                os.path.basename(TEST_DIR), "scripts"))
import init_prep  # noqa: E402
sys.path.insert(0, TEST_DIR)
from prep_fixture import temp_output  # noqa: E402

TODAY = date(2026, 11, 10)
START, END = date(2026, 8, 10), TODAY
JOSE = {"accountId": "a1", "displayName": "José Núñez",
        "emailAddress": "jose@acme.test", "active": True}


class FakeJira:
    """Answers user() from `accounts`, {accountId: account}, None for any
    other."""

    def __init__(self, *accounts):
        self.accounts = {account["accountId"]: account for account in accounts}

    def user(self, account_id):
        return self.accounts.get(account_id)


class InitTest(unittest.TestCase):
    def setUp(self):
        self.folder = temp_output(self)

    def test_new_prep_then_a_rerun_replaces_it(self):
        # A new prep holds only its person.json, with the Jira account as
        # Jira gives it, its one source until step 2, and is named after it, whatever the manager calls the
        # person; running it again the same day starts from scratch, but
        # leaves the folders of other days.
        client = FakeJira(JOSE)
        result = init_prep.init("  Pepe   ", "a1", START,
                                END, today=TODAY, client=client)
        path = os.path.join(self.folder, "Jose-Nunez_26-11-10")
        person = {"person": "Pepe", "start": "2026-08-10", "end": "2026-11-10",
                  "sources": {"jira-api": {"id": "a1", "name": "José Núñez", "email": "jose@acme.test"}}}
        self.assertEqual(result, {"folder": self.folder, "temporary": False, "prep": "Jose-Nunez_26-11-10",
                                  "prep_dir": path, "replaced": False, "person": person,
                                  "shown": "10/08/2026 to 10/11/2026"})
        self.assertEqual(os.listdir(path), ["person.json"])
        with open(os.path.join(path, "person.json"), encoding="utf-8") as f:
            self.assertEqual(json.load(f), person)
        with open(os.path.join(path, "left-over.md"), "w", encoding="utf-8") as f:
            f.write("from an earlier run")
        earlier = os.path.join(self.folder, "Jose-Nunez_26-11-09")
        os.makedirs(earlier)
        self.assertTrue(init_prep.init(
            "José Núñez", "a1", START, END, today=TODAY, client=client)["replaced"])
        self.assertEqual(os.listdir(path), ["person.json"])
        self.assertTrue(os.path.isdir(earlier))

    def test_refuses_a_prep_it_cant_start(self):
        # name: (person, account, end, expected in why it stops): no account
        # Jira has, one whose email it hides, or a person or period that
        # breaks a rule of common.person_problems(), tested in test_common.py,
        # writes nothing.
        client = FakeJira(
            JOSE, {**JOSE, "accountId": "a2", "emailAddress": None})
        cases = [("no such account", "José", "a9", END, "Jira has no person's account a9"),
                 ("a hidden email", "José", "a2", END,
                  "Jira hides the email of José Núñez's account"),
                 ("no name", "  ", "a1", END, "must name the person"),
                 ("ends after today", "José", "a1", date(2026, 12, 31), "after today")]
        for name, person, account, end, expected in cases:
            with self.subTest(name), self.assertRaisesRegex(SystemExit, expected):
                init_prep.init(person, account, START, end,
                               today=TODAY, client=client)
        self.assertFalse(os.path.exists(self.folder))


if __name__ == "__main__":
    unittest.main()
