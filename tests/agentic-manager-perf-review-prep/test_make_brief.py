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
from prep_fixture import EARLIER_WORK_BRIEF, OBSERVATIONS_BRIEF, DATA, PERSON, PREP, STEP_CHANGE_BRIEF, VALUES, WORK_IMPACT_BRIEF, temp_output, write_prep  # noqa: E402


class MakeBriefTest(unittest.TestCase):
    def test_build_briefs(self):
        # The fixture's briefs, worked out by hand from its data.json: each
        # table's points in its order, a point naming two values with both;
        # the observations' with the values and the work's main focus, the
        # step change's with the points' ids and the previous feedback, the
        # work's with its items grouped, each group by its latest, and the
        # points with their ids, the work before the period's with the
        # previous feedback's texts by part; the step change's and the work
        # before the period's previous null when there is none.
        self.assertEqual((make_brief.build_brief(PERSON, DATA, VALUES), make_brief.build_step_change_brief(PERSON, DATA),
                          make_brief.build_work_impact_brief(PERSON, DATA),
                          make_brief.build_earlier_work_brief(PERSON, DATA)),
                         (OBSERVATIONS_BRIEF, STEP_CHANGE_BRIEF, WORK_IMPACT_BRIEF, EARLIER_WORK_BRIEF))
        for build in (make_brief.build_step_change_brief, make_brief.build_earlier_work_brief):
            with self.subTest(build.__name__):
                self.assertIsNone(
                    build(PERSON, {**DATA, "previous": None})["previous"])

    def test_write_briefs(self):
        # All four written to the prep folder, the observations' with the
        # config's company values.
        folder = temp_output(self)
        write_prep(folder, observations_brief=None,
                   step_change_brief=None, work_impact_brief=None, earlier_work_brief=None, report=False)
        self.assertEqual([common.read_json(path) for path in make_brief.write_briefs(PREP)],
                         [OBSERVATIONS_BRIEF, STEP_CHANGE_BRIEF, WORK_IMPACT_BRIEF, EARLIER_WORK_BRIEF])

    def test_a_group_lists_its_most_recent_items(self):
        # A group holding more than RECENT_ITEMS items counts them all but
        # lists only the most recent, the newest first.
        prs = [{"repo": "acme/billing", "number": n, "title": f"Change {n}", "url": f"https://github.com/acme/billing/pull/{n}",
                "date": f"2026-09-{n:02d}", "lines": 1, "files": 1} for n in range(1, 13)]
        data = {**DATA, "github": {**
                                   DATA["github"], "opened": [], "merged": prs}}
        group = make_brief.build_work_impact_brief(PERSON, data)[
            "pull_requests"][0]
        self.assertEqual((group["items"], [pr["title"] for pr in group["recent"]]),
                         (12, [f"Change {n}" for n in range(12, 2, -1)]))


if __name__ == "__main__":
    unittest.main()
