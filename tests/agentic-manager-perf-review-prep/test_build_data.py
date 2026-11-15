"""Unit tests for skills/agentic-manager-perf-review-prep/scripts/build_data.py.
Run with: python3 tests/run.py agentic-manager-perf-review-prep
"""

import os
import sys
import unittest

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(TEST_DIR))
sys.path.insert(0, os.path.join(REPO_ROOT, "skills",
                os.path.basename(TEST_DIR), "scripts"))
import build_data  # noqa: E402
import common  # noqa: E402
sys.path.insert(0, TEST_DIR)
from prep_fixture import DATA, PERSON, PREP, WEEKS, WORK_RAW, temp_output, write_prep  # noqa: E402


class BuildDataTest(unittest.TestCase):
    def test_build(self):
        # The fixture's data.json, worked out by hand from its raw files: the
        # weeks, each source's items without the fields kept only to check
        # them, its facts, such as the main focus of its one resolved issue,
        # the charts' series and each search's address.
        self.assertEqual(build_data.build(WORK_RAW, PERSON), DATA)

    def test_build_data(self):
        # Written once every raw file is in and follows its rules; refused,
        # writing nothing, while one is missing or from another period.
        folder = temp_output(self)
        write_prep(folder, data=None, report=False, raw_work={
                   "jira": WORK_RAW["jira"], "github": WORK_RAW["github"]})
        with self.assertRaisesRegex(SystemExit, "raw files are missing"):
            build_data.build_data(PREP)
        write_prep(folder, data=None, report=False, raw_work={**WORK_RAW, "github": {**WORK_RAW["github"],
                                                                                     "start": "2026-08-01"}})
        with self.assertRaisesRegex(SystemExit, "the github raw file is for 2026-08-01"):
            build_data.build_data(PREP)
        write_prep(folder, data=None, report=False)
        self.assertEqual(common.read_json(build_data.build_data(PREP)), DATA)

    def test_week_groups(self):
        # Calendar weeks, Monday to Sunday, the first and last clipped to the
        # period; a long period groups them, always the same weeks, so there
        # are at most twenty.
        self.assertEqual(build_data.week_groups(
            "2026-08-10", "2026-11-10"), WEEKS)
        self.assertEqual(build_data.week_groups(
            "2026-09-02", "2026-09-02"), [["2026-09-02", "2026-09-02"]])
        year = build_data.week_groups("2026-01-01", "2026-12-31")
        self.assertLessEqual(len(year), build_data.MAX_POINTS)
        self.assertEqual((year[0][0], year[-1][1]),
                         ("2026-01-01", "2026-12-31"))

    def test_series(self):
        # Each week's issues in all, by epic in the epics' order and with
        # none; the resolved issues by points and epic; and the epics'
        # order, the resolved ones' first.
        weeks = [["2026-07-01", "2026-07-05"], ["2026-07-06", "2026-07-12"]]
        a, b = {"key": "PROJ-1"}, {"key": "PROJ-2"}
        items = [{"date": "2026-07-02", "epic": a, "points": 3}, {"date": "2026-07-07", "epic": b, "points": 3},
                 {"date": "2026-07-08", "epic": None, "points": None}]
        self.assertEqual(build_data.by_week(items, weeks, ["PROJ-2", "PROJ-1", "PROJ-9"]),
                         {"total": [1, 2], "epics": {"PROJ-2": [0, 1], "PROJ-1": [1, 0]}, "no_epic": [0, 1]})
        self.assertEqual(build_data.points_by_epic(items, ["PROJ-1", "PROJ-2"]),
                         [{"points": 3, "issues": 2, "epics": {"PROJ-1": 1, "PROJ-2": 1}, "no_epic": 0}])
        self.assertEqual(build_data.epic_order({"epics": [{"key": "PROJ-2"}], "no_epic": 0},
                                               [{"epic": {"key": "PROJ-9"}}, {"epic": b}, {"epic": None}]),
                         ["PROJ-2", "PROJ-9"])

    def test_points(self):
        # name: (the issues' points, {total, estimated, average}): an
        # unestimated issue counts toward neither the total nor the average.
        cases = [("none estimated", [None, None], {"total": 0, "estimated": 0, "average": None}),
                 ("some estimated", [3, None, 5, 1], {
                  "total": 9, "estimated": 3, "average": 3.0}),
                 ("halves", [0.5, 2, 1], {"total": 3.5, "estimated": 3, "average": 1.2})]
        for name, points, expected in cases:
            with self.subTest(name):
                self.assertEqual(build_data.points(
                    [{"points": value} for value in points]), expected)

    def test_focus(self):
        # name: (parents of the resolved issues, by key, None for none, the
        # focus expected as (key, issues)): the fewest parents covering 80%
        # of the issues with one, those tied with the last one too; with no
        # parent at all, the projects.
        def issues(*epics):
            return [{"key": f"PROJ-{n}", "epic": {"key": epic, "title": epic.title(), "url": f"https://acme.test/{epic}"}
                     if epic else None}
                    for n, epic in enumerate(epics)]
        cases = [("nothing", [], []),
                 ("one parent", issues("billing"), [("billing", 1)]),
                 ("80% covered", issues(
                     *["a"] * 5, *["b"] * 3, "c", "d"), [("a", 5), ("b", 3)]),
                 ("tied at the cutoff", issues(*["a"] * 4, *["b"] * 2, *["c"] * 2, *["d"] * 2),
                  [("a", 4), ("b", 2), ("c", 2), ("d", 2)]),
                 ("no parent left out", issues("a", "a", None, None, None), [("a", 2)])]
        for name, resolved, expected in cases:
            with self.subTest(name):
                self.assertEqual([(entry["key"], entry["issues"])
                                 for entry in build_data.focus(resolved)], expected)
        projects = [{"key": key, "epic": None}
                    for key in ("PROJ-1", "PROJ-2", "OPS-3")]
        self.assertEqual(build_data.focus(projects), [{"key": "PROJ", "title": None, "url": None, "issues": 2},
                                                      {"key": "OPS", "title": None, "url": None, "issues": 1}])
        self.assertEqual(build_data.by_epic(issues("a", None, "b", "a")), {
            "epics": [{"key": "a", "title": "A", "url": "https://acme.test/a", "issues": 2},
                      {"key": "b", "title": "B", "url": "https://acme.test/b", "issues": 1}], "no_epic": 1})


if __name__ == "__main__":
    unittest.main()
