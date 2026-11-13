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
        # them, and the protocol's rules for a point and its values, the ones
        # the subagents' tasks hold, filled in whole.
        write_prep(temp_output(self))
        found = rules.rules(PREP)
        self.assertEqual({key: value for key, value in found.items() if key != "rules"},
                         {"parts": common.SUMMARY_PARTS, "valued_parts": ["going_well", "to_improve"],
                          "values": VALUES, "ratings": RATINGS})
        self.assertEqual(found["rules"], "\n\n".join(
            common.fill_protocol(common.PROTOCOL, name) for name in ("_point", "_value")))


if __name__ == "__main__":
    unittest.main()
