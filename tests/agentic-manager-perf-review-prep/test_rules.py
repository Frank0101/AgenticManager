"""Unit tests for skills/agentic-manager-perf-review-prep/scripts/rules.py.
Run as a script, it has end-to-end tests in test_e2e_init.py.
Run with: python3 tests/run.py agentic-manager-perf-review-prep
"""

import os
import sys
import unittest

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(TEST_DIR))
sys.path.insert(0, os.path.join(REPO_ROOT, "skills",
                os.path.basename(TEST_DIR), "scripts"))
import common  # noqa: E402
import rules  # noqa: E402
sys.path.insert(0, TEST_DIR)
from prep_fixture import PREP, RATINGS, VALUES, temp_output, write_prep  # noqa: E402


class RulesTest(unittest.TestCase):
    def test_rules(self):
        # The parts, the company's values and ratings as the config lists
        # them, and the first day feedback may end on for the prep's period,
        # which starts on 10/08/2026.
        write_prep(temp_output(self))
        self.assertEqual(rules.rules(PREP), {"parts": common.SUMMARY_PARTS, "valued_parts": ["going_well", "to_improve"],
                                             "values": VALUES, "ratings": RATINGS, "earliest_end": "2024-08-10"})


if __name__ == "__main__":
    unittest.main()
