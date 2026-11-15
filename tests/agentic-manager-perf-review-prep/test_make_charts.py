"""Unit tests for skills/agentic-manager-perf-review-prep/scripts/make_charts.py.
Run with: python3 tests/run.py agentic-manager-perf-review-prep
"""

import os
import re
import sys
import unittest

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(TEST_DIR))
sys.path.insert(0, os.path.join(REPO_ROOT, "skills",
                os.path.basename(TEST_DIR), "scripts"))
import common  # noqa: E402
import make_charts  # noqa: E402
sys.path.insert(0, TEST_DIR)
from prep_fixture import DATA  # noqa: E402

WEEKS = [["2026-07-01", "2026-07-05"],
         ["2026-07-06", "2026-07-12"], ["2026-08-03", "2026-08-09"]]


class MakeChartsTest(unittest.TestCase):
    def test_draw(self):
        # Every chart of the report, each an SVG, an epic in its slice's
        # colour, by data.json's epic order.
        charts = make_charts.draw(DATA)
        self.assertEqual((sorted(charts), all(chart.startswith("<svg ") for chart in charts.values())),
                         (sorted(common.CHART_FILES), True))
        self.assertIn(
            f'fill="{make_charts.PALETTE[0]}"', charts[common.EPICS_CHART])

    def test_over_time_chart(self):
        # A point per week, each month named once, under its first week, even
        # when the period starts mid-week; a thin line per epic, in its
        # colour, and one for the issues with no epic, under the total's.
        series = {"total": [1, 0, 1], "epics": {
            "PROJ-1": [1, 0, 0]}, "no_epic": [0, 0, 1]}
        chart = make_charts.over_time_chart(series, WEEKS, "resolved", {"PROJ-1": "#123456"},
                                            [("total", make_charts.LINE, False)], 200)
        lines = re.findall(
            r'<polyline points="([^"]+)" fill="none" stroke="([^"]+)"', chart)
        self.assertEqual([(len(points.split()), colour) for points, colour in lines],
                         [(3, "#123456"), (3, make_charts.NO_EPIC), (3, make_charts.LINE)])
        self.assertEqual(re.findall(r">(Jul|Aug)<", chart), ["Jul", "Aug"])
        self.assertIn('height="200"', chart)

    def test_points_chart(self):
        # A bar for each number of points, split by epic in its colour, the
        # issues with no epic on top; the average's line between the two
        # values it lies between; a legend below; a note when nothing is
        # estimated.
        rows = [{"points": 1, "issues": 1, "epics": {"PROJ-1": 1}, "no_epic": 0},
                {"points": 3, "issues": 2, "epics": {"PROJ-1": 1}, "no_epic": 1}]
        entries = [("PROJ-1", "#123456", False), ("no epic", make_charts.NO_EPIC, False),
                   ("average", make_charts.AVERAGE, True)]
        chart = make_charts.points_chart(
            rows, 7 / 3, {"PROJ-1": "#123456"}, entries, 220)
        self.assertEqual(re.findall(r'<rect x="[^"]+" y="[^"]+" width="[^"]+" height="[^"]+" fill="([^"]+)" stroke',
                                    chart), ["#123456", "#123456", make_charts.NO_EPIC])
        self.assertIn('stroke-dasharray="5 4"', chart)
        self.assertIn(">average<", chart)
        self.assertIn("No estimated issues", make_charts.points_chart(
            [], None, {}, entries, 220))
        self.assertAlmostEqual(
            make_charts.average_x(2, [1, 3], [100, 200]), 150)


if __name__ == "__main__":
    unittest.main()
