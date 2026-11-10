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
from prep_fixture import IDENTITIES, PREP, temp_output, write_prep  # noqa: E402


class SetIdentitiesTest(unittest.TestCase):
    def setUp(self):
        self.folder = temp_output(self)
        write_prep(self.folder, identities=None)
        self.path = os.path.join(self.folder, PREP, "identities.json")

    def test_writes_them_and_a_correction_replaces_them(self):
        self.assertEqual(set_identities.set_identities(
            PREP, IDENTITIES), self.path)
        corrected = {**IDENTITIES,
                     "slack-mcp": {"id": "U012AB3CD", "name": "Jane Doe"}}
        set_identities.set_identities(PREP, corrected)
        with open(self.path, encoding="utf-8") as f:
            self.assertEqual(json.load(f), corrected)

    def test_refuses_identities_that_break_a_rule(self):
        # The rules are common.identities_problems(), tested in
        # test_common.py: identities that break one write nothing, and the
        # message shows the input to send.
        with self.assertRaisesRegex(SystemExit, "slack-mcp must be(.|\n)*END_OF_INPUT"):
            set_identities.set_identities(
                PREP, {**IDENTITIES, "slack-mcp": {}})
        self.assertFalse(os.path.exists(self.path))


if __name__ == "__main__":
    unittest.main()
