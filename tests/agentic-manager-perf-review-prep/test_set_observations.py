"""Unit tests for skills/agentic-manager-perf-review-prep/scripts/set_observations.py.
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
import set_observations  # noqa: E402
sys.path.insert(0, TEST_DIR)
from prep_fixture import OBSERVATIONS_CONTENT, PREP, temp_output, write_prep  # noqa: E402


class SetObservationsTest(unittest.TestCase):
    def test_set_observations(self):
        # Written once it summarises data.json's tables; refused, writing
        # nothing, with every problem.
        folder = temp_output(self)
        write_prep(folder, observations_content=None, report=False)
        cases = [("a summary empty", {**OBSERVATIONS_CONTENT, "to_improve": ""}, "to_improve is empty"),
                 ("a step change too", {**OBSERVATIONS_CONTENT, "step_change": None}, "observations_content.json must be")]
        for name, value, expected in cases:
            with self.subTest(name), self.assertRaisesRegex(SystemExit, f"{expected}(.|\n)*END_OF_INPUT"):
                set_observations.set_observations(PREP, value)
        self.assertFalse(os.path.exists(
            os.path.join(folder, PREP, "observations_content.json")))
        self.assertEqual(common.read_json(
            set_observations.set_observations(PREP, OBSERVATIONS_CONTENT)), OBSERVATIONS_CONTENT)


if __name__ == "__main__":
    unittest.main()
