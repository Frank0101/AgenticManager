"""Unit tests for skills/agentic-manager-perf-review-prep/scripts/set_identities.py.
Run as a script, it has end-to-end tests in test_e2e_init.py.
Run with: python3 tests/run.py agentic-manager-perf-review-prep
"""

import json
import os
import sys
import unittest

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(TEST_DIR))
sys.path.insert(0, os.path.join(REPO_ROOT, "skills",
                os.path.basename(TEST_DIR), "scripts"))
import set_identities  # noqa: E402
sys.path.insert(0, TEST_DIR)
from prep_fixture import PERSON, PREP, temp_output, write_prep  # noqa: E402

# person.json as step 1 leaves it, with Jira's source alone, and what the
# manager confirms for the others.
AFTER_STEP_1 = {
    **PERSON, "sources": {"jira-api": PERSON["sources"]["jira-api"]}}
CONFIRMED = {source: account for source,
             account in PERSON["sources"].items() if source != "jira-api"}


class SetIdentitiesTest(unittest.TestCase):
    def setUp(self):
        self.folder = temp_output(self)
        write_prep(self.folder, person=AFTER_STEP_1,
                   orientation=None, reviews=None)
        self.path = os.path.join(self.folder, PREP, "person.json")

    def read(self):
        with open(self.path, encoding="utf-8") as f:
            return json.load(f)

    def test_adds_them_and_a_correction_replaces_them(self):
        # The person, the period and the Jira account are kept as step 1
        # recorded them.
        self.assertEqual(set_identities.set_identities(PREP, CONFIRMED),
                         (self.path, PERSON["sources"]))
        self.assertEqual(self.read(), PERSON)
        corrected = {**CONFIRMED,
                     "slack-mcp": {"id": "U999ZZ9ZZ", "name": "Jane Doe"}}
        set_identities.set_identities(PREP, corrected)
        self.assertEqual(self.read(), {**PERSON, "sources": {
            "jira-api": PERSON["sources"]["jira-api"], **corrected}})

    def test_refuses_sources_it_doesnt_record(self):
        # name: (the input, expected in why it stops): the rules are
        # common.sources_problems(), tested in test_common.py; input that
        # breaks one writes nothing, and the message shows the input to
        # send. The Jira account is step 1's.
        cases = [("a source that breaks a rule", {**CONFIRMED, "slack-mcp": {}}, "slack-mcp must be"),
                 ("the Jira account", PERSON["sources"],
                  "leave jira-api out: the Jira account was confirmed with the period in step 1")]
        for name, identities, expected in cases:
            with self.subTest(name), self.assertRaisesRegex(SystemExit, f"{expected}(.|\n)*END_OF_INPUT"):
                set_identities.set_identities(PREP, identities)
            self.assertEqual(self.read(), AFTER_STEP_1)


if __name__ == "__main__":
    unittest.main()
