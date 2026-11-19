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
from prep_fixture import VALUES, temp_output  # noqa: E402


class RulesTest(unittest.TestCase):
    def test_rules(self):
        # The parts, the company's values as the config lists
        # them, and the protocol's rules for a feedback's points: how to write
        # a point and its values, the shared part the judges' tasks hold too,
        # and the one line a feedback adds, filled in whole.
        temp_output(self)
        found = rules.rules()
        self.assertEqual({key: value for key, value in found.items() if key != "rules"},
                         {"parts": common.SUMMARY_PARTS, "valued_parts": ["going_well", "to_improve"],
                          "values": VALUES})
        self.assertTrue(found["rules"].startswith(
            "# Summarise a feedback into points\n\n## Points\n\n### Writing a point\n\n"))
        rules_text = found["rules"]
        self.assertLess(rules_text.index("### Writing a point"),
                        rules_text.index("### Values"))
        self.assertLess(rules_text.index("### Values"),
                        rules_text.index("### Context"))
        self.assertIn(
            "A `going_well` point names every company value", found["rules"])
        self.assertIn("quarter's plan on time", found["rules"])
        self.assertIn(
            "The same thing said more than once in the feedback is one point.", found["rules"])
        self.assertIn("A reminder or a to-do about the review's process",
                      found["rules"])
        self.assertNotIn("never one per mention", found["rules"])
        self.assertNotIn("{{", found["rules"])


if __name__ == "__main__":
    unittest.main()
