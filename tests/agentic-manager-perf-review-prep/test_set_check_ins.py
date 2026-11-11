"""Unit tests for skills/agentic-manager-perf-review-prep/scripts/set_check_ins.py.
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
import set_check_ins  # noqa: E402
sys.path.insert(0, TEST_DIR)
from prep_fixture import NOTE, PREP, temp_output, write_prep  # noqa: E402


class SetCheckInsTest(unittest.TestCase):
    def setUp(self):
        self.folder = temp_output(self)
        write_prep(self.folder, check_ins=None)
        self.path = os.path.join(self.folder, PREP, "check-ins.json")

    def read(self):
        with open(self.path, encoding="utf-8") as f:
            return json.load(f)

    def test_writes_dated_notes_first_and_a_correction_replaces_them(self):
        # Those with days oldest first, then the undated in the order given,
        # by common.pieces_order().
        undated = {**NOTE, "start": None, "end": None}
        earlier = {**NOTE, "start": "2026-08-10", "end": "2026-08-31"}
        self.assertEqual(set_check_ins.set_check_ins(
            PREP, {"pieces": [undated, NOTE, earlier]}), self.path)
        self.assertEqual(self.read(), {"pieces": [NOTE, earlier, undated]})
        set_check_ins.set_check_ins(PREP, {"pieces": []})
        self.assertEqual(self.read(), {"pieces": []})

    def test_refuses_notes_that_break_a_rule(self):
        # The rules are common.check_ins_problems(), tested in
        # test_common.py: notes that break them write nothing, and the message
        # shows the input to send.
        with self.assertRaisesRegex(SystemExit, "covers no day of the period(.|\n)*END_OF_INPUT"):
            set_check_ins.set_check_ins(
                PREP, {"pieces": [{**NOTE, "start": None, "end": "2026-01-31"}]})
        self.assertFalse(os.path.exists(self.path))


if __name__ == "__main__":
    unittest.main()
