"""Unit tests for skills/agentic-manager-perf-review-prep/scripts/make_brief.py.
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
import make_brief  # noqa: E402
sys.path.insert(0, TEST_DIR)
from prep_fixture import BRIEF, DATA, PERSON, PREP, VALUES, temp_output, write_prep  # noqa: E402


class MakeBriefTest(unittest.TestCase):
    def test_build_brief(self):
        # The fixture's brief, worked out by hand from its data.json: each
        # table's points in its order, a point naming two values with both.
        self.assertEqual(make_brief.build_brief(PERSON, DATA, VALUES), BRIEF)

    def test_write_brief(self):
        # Written to the prep folder, with the config's company values.
        folder = temp_output(self)
        write_prep(folder, brief=None, report=False)
        self.assertEqual(common.read_json(make_brief.write_brief(PREP)), BRIEF)


if __name__ == "__main__":
    unittest.main()
