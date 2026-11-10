"""Unit tests for skills/agentic-manager-perf-review-prep/scripts/set_orientation.py.
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
import set_orientation  # noqa: E402
sys.path.insert(0, TEST_DIR)
from prep_fixture import ORIENTATION, PREP, temp_output, write_prep  # noqa: E402


class SetOrientationTest(unittest.TestCase):
    def setUp(self):
        self.folder = temp_output(self)
        write_prep(self.folder, orientation=None, feedback=None)
        self.path = os.path.join(self.folder, PREP, "orientation.json")

    def test_writes_it_and_a_correction_replaces_it(self):
        self.assertEqual(set_orientation.set_orientation(
            PREP, ORIENTATION), self.path)
        with open(self.path, encoding="utf-8") as f:
            self.assertEqual(json.load(f), ORIENTATION)
        corrected = {**ORIENTATION, "context": []}
        set_orientation.set_orientation(PREP, corrected)
        with open(self.path, encoding="utf-8") as f:
            self.assertEqual(json.load(f), corrected)

    def test_refuses_a_summary_that_breaks_a_rule(self):
        # The rule is common.summary_problems(), tested in test_common.py: a
        # summary that breaks it writes nothing, and the message shows the
        # input to send.
        with self.assertRaisesRegex(SystemExit, "orientation must have the parts(.|\n)*END_OF_INPUT"):
            set_orientation.set_orientation(
                PREP, {"text": "Strong half overall."})
        self.assertFalse(os.path.exists(self.path))


if __name__ == "__main__":
    unittest.main()
