"""Unit tests for skills/agentic-manager-perf-review-prep/scripts/make_charts.py.
Run with: python3 tests/run.py agentic-manager-perf-review-prep
"""

import os
import re
import sys
import unittest
from datetime import date

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
        # Every chart of the report, each an SVG of one height, an epic or a
        # repository in its slice's colour, by data.json's order.
        charts = make_charts.draw(DATA)
        self.assertEqual((sorted(charts), all(chart.startswith("<svg ") for chart in charts.values())),
                         (sorted(common.CHART_FILES), True))
        self.assertIn(
            f'fill="{make_charts.PALETTE[0]}"', charts[common.EPICS_CHART])
        self.assertIn(
            f'fill="{make_charts.PALETTE[0]}"', charts[common.REPOS_CHART])
        self.assertEqual(
            len({re.findall(r'height="(\d+)"', chart)[0] for chart in charts.values()}), 1)

    def test_jira_legends(self):
        # name: (the created issues' week-by-week series, the groups the
        # line charts' legend names): each epic coloured, then other epics
        # and no epic only when some issue is in them.
        series = DATA["jira"]["created_by_week"]
        cases = [("an issue with no epic", series, ["total", "PROJ-1", "no epic"]),
                 ("every issue in an epic", {**series, "no_epic": [0] * len(series["no_epic"])},
                  ["total", "PROJ-1"]),
                 ("an issue in another epic", {**series, "other": series["no_epic"]},
                  ["total", "PROJ-1", "other epics", "no epic"])]
        for name, created, expected in cases:
            with self.subTest(name):
                _, lines, bars = make_charts.jira_legends(
                    {**DATA["jira"], "created_by_week": created})
                self.assertEqual(([label for label, _, _ in lines], [label for label, _, _ in bars]),
                                 (expected, [*expected[1:], "average"]))

    def test_over_time_chart(self):
        # A point per week, each month named in the middle of its days, even
        # when the period starts mid-week; a thin line for each group, in its
        # colour, those with none left out, under the total's.
        chart = make_charts.over_time_chart([1, 0, 1], [("#123456", [1, 0, 0]), (make_charts.OTHER, [0, 0, 0]),
                                                        (make_charts.NO_EPIC, [0, 0, 1])],
                                            WEEKS, "resolved", [("total", make_charts.LINE, False)], 200)
        lines = re.findall(
            r'<polyline points="([^"]+)" fill="none" stroke="([^"]+)"', chart)
        self.assertEqual([(len(points.split()), colour) for points, colour in lines],
                         [(3, "#123456"), (3, make_charts.NO_EPIC), (3, make_charts.LINE)])
        self.assertEqual(re.findall(r">(Jul|Aug)<", chart), ["Jul", "Aug"])
        # A dashed line sets August apart from July, none before July.
        self.assertEqual(len(re.findall(r'stroke-dasharray="3 3"', chart)), 1)
        self.assertIn('height="200"', chart)

    def test_bars_chart(self):
        # A bar for each row, its parts stacked in their colours, those of
        # none left out; with an average, its line between the two values it
        # lies between; a legend below; a note when no row holds any.
        rows = [("1", [("#123456", 1), (make_charts.NO_EPIC, 0)]),
                ("3", [("#123456", 1), (make_charts.NO_EPIC, 1)])]
        entries = [("PROJ-1", "#123456", False), ("no epic", make_charts.NO_EPIC, False),
                   ("average", make_charts.AVERAGE, True)]
        chart = make_charts.bars_chart(rows, "story points", "No estimated issues", entries, 220,
                                       marker=make_charts.value_position(7 / 3, [1, 3]))
        self.assertEqual(re.findall(r'<rect x="[^"]+" y="[^"]+" width="[^"]+" height="[^"]+" fill="([^"]+)" stroke',
                                    chart), ["#123456", "#123456", make_charts.NO_EPIC])
        self.assertIn('stroke-dasharray="5 4"', chart)
        self.assertIn(">average<", chart)
        self.assertNotIn('stroke-dasharray="5 4"',
                         make_charts.bars_chart(rows, "lines", "", entries[:2], 220))
        self.assertIn("No estimated issues", make_charts.bars_chart(
            [("1", [("#123456", 0)])], "story points", "No estimated issues", entries, 220))
        # A position in bars, each bar's middle its value: between two
        # values in proportion.
        self.assertEqual(make_charts.value_position(2, [1, 3]), 1.0)

    def test_pie_chart(self):
        # Its title, a slice for each group holding any, and a legend of
        # each with its count; a note when none holds any.
        chart = make_charts.pie_chart("Merged PRs by repository", [("api", 3, "#123456", None), ("other", 0, "#654321", None),
                                                                   ("web", 1, "#abcdef", None)], "None", 230)
        self.assertIn(">Merged PRs by repository<", chart)
        self.assertEqual(re.findall(
            r'<path d="[^"]+" fill="([^"]+)"', chart), ["#123456", "#abcdef"])
        self.assertEqual(re.findall(r">(\w+) \((\d+)\)<", chart),
                         [("api", "3"), ("web", "1")])
        # A slice of the main focus shows its share; the others none.
        shared = make_charts.pie_chart(
            "Title", [("api", 3, "#123456", 75), ("web", 1, "#abcdef", None)], "None", 230)
        self.assertEqual(re.findall(
            rf'font-size="{make_charts.VALUE_FONT}"[^>]*>([^<]+)<', shared), ["75%"])
        self.assertIn(">None<", make_charts.pie_chart(
            "Title", [("api", 0, "#123456", None)], "None", 230))
        self.assertIn('height="230"', chart)

    def test_distribution_chart(self):
        # A point in the middle of each bin, each power of ten named under
        # the axis at its place, and the median's dashed line on the log
        # scale: 10 lines at the middle of eight bins, two powers of ten, up
        # to 100.
        series = {"total": [0, 1, 0, 0, 2, 0, 0, 0], "repos": {"acme/api": [0, 1, 0, 0, 2, 0, 0, 0]},
                  "other": [0] * 8}
        chart = make_charts.distribution_chart(series, 10, "lines", {"acme/api": "#123456"},
                                               [("total", make_charts.LINE, False)], 220)
        self.assertEqual(re.findall(
            r'text-anchor="middle">(\d+)<', chart), ["1", "10", "100"])
        self.assertEqual([make_charts.power_label(power) for power in range(8)],
                         ["1", "10", "100", "1k", "10k", "100k", "1M", "10M"])
        line = re.search(r'<line x1="([\d.]+)" y1="[^"]+" x2="[^"]+" y2="[^"]+" stroke="[^"]+" stroke-width="1.5" '
                         r'stroke-dasharray="5 4"', chart)
        assert line
        plot = make_charts.WIDTH - make_charts.LEFT - make_charts.RIGHT
        self.assertAlmostEqual(
            float(line[1]), make_charts.LEFT + plot / 2, places=0)

    def test_over_time_points_sit_at_their_week_ends_on_a_date_scale(self):
        # name: (the period's first and last day, the places of the points, of
        # the month separators and of the month names, each as a day's offset
        # from the first day, over the period's span): a point at the date of
        # its week's last day, so a short week at an edge is close to its
        # neighbour; a separator at each month's first day, on the same scale;
        # each month named in the middle of its days in the period.
        plot = make_charts.WIDTH - make_charts.LEFT - make_charts.RIGHT

        def x(offset, span):
            return make_charts.LEFT + plot * offset / span
        cases = [("a clipped first and last week", "2026-07-01", "2026-08-05",
                  [4, 11, 18, 25, 32, 35], [31], [15, 33]),
                 ("whole weeks over a month's turn", "2026-07-27", "2026-08-09",
                  [6, 13], [5], [2, 9]),
                 ("a one-day last week", "2026-07-06", "2026-07-20", [6, 13, 14], [], [7])]
        for name, first, last, points, separators, names in cases:
            with self.subTest(name):
                weeks = common.calendar_weeks(first, last)
                chart = make_charts.over_time_chart(
                    [1] * len(weeks), [], weeks, "created", [], 200)
                span = (date.fromisoformat(last) -
                        date.fromisoformat(first)).days
                found = re.search(
                    r'<polyline points="([^"]+)" fill="none" stroke="#3d3d3d"', chart)
                assert found is not None, "the chart has no total line"
                line = found[1]
                self.assertEqual([float(point.split(",")[0]) for point in line.split()],
                                 [round(x(offset, span), 1) for offset in points])
                dividers = re.findall(
                    r'<line x1="([\d.]+)" y1="12" [^>]*stroke-dasharray="3 3"', chart)
                self.assertEqual([float(place) for place in dividers],
                                 [round(x(offset, span), 1) for offset in separators])
                named = re.findall(
                    r'<text x="([\d.]+)"[^>]*>(?:Jul|Aug)<', chart)
                self.assertEqual([float(place) for place in named],
                                 [round(x(offset, span), 1) for offset in names])
        # A lone week is centred, as a single point has no scale.
        lone = make_charts.over_time_chart(
            [3], [], [["2026-07-06", "2026-07-12"]], "created", [], 200)
        self.assertIn(f'{make_charts.LEFT + plot / 2:.1f},', lone)

    def test_value_labels(self):
        # Each point of the total and each bar has its value written over
        # it, small, a zero none.
        def values(chart):
            return re.findall(rf'font-size="{make_charts.VALUE_FONT}"[^>]*>(\d+)<', chart)
        line = make_charts.over_time_chart(
            [2, 0, 5], [], WEEKS, "created", [], 200)
        bars = make_charts.bars_chart([("1", [("#123456", 1), ("#654321", 2)]), ("3", [("#123456", 0)])],
                                      "story points", "None", [], 200)
        self.assertEqual((values(line), values(bars)), (["2", "5"], ["3"]))


if __name__ == "__main__":
    unittest.main()
