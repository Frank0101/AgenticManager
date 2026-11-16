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
from prep_fixture import BRIEF, DATA, PERSON, PREP, STEP_CHANGE_BRIEF, VALUES, VIEW_CHECK_BRIEF, temp_output, write_prep  # noqa: E402


class MakeBriefTest(unittest.TestCase):
    def test_build_briefs(self):
        # The fixture's briefs, worked out by hand from its data.json: each
        # table's points in its order, a point naming two values with both;
        # the observations' with the values and the work's main focus, the
        # step change's with the points' ids and the previous reviews, or
        # null when there are none, the view check's with the points' ids and
        # the manager's view.
        self.assertEqual((make_brief.build_brief(PERSON, DATA, VALUES), make_brief.build_step_change_brief(PERSON, DATA),
                          make_brief.build_view_check_brief(PERSON, DATA)),
                         (BRIEF, STEP_CHANGE_BRIEF, VIEW_CHECK_BRIEF))
        self.assertIsNone(make_brief.build_step_change_brief(
            PERSON, {**DATA, "reviews": None})["reviews"])

    def test_write_briefs(self):
        # All three written to the prep folder, the observations' with the
        # config's company values.
        folder = temp_output(self)
        write_prep(folder, brief=None, step_change_brief=None,
                   view_check_brief=None, report=False)
        self.assertEqual([common.read_json(path) for path in make_brief.write_briefs(PREP)],
                         [BRIEF, STEP_CHANGE_BRIEF, VIEW_CHECK_BRIEF])


if __name__ == "__main__":
    unittest.main()
