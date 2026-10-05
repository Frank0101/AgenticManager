# Unit tests for skills/agentic-manager-jira-sprint-report/scripts/make_charts.py.
# Run with: python3 tests/run.py agentic-manager-jira-sprint-report
#
# A two-week sprint, Monday 02/03/2026 to Friday 13/03/2026, small enough to
# work its burndown out by hand:
#   PROJ-1  original, 4 pts, done Thursday 05/03, carried over from Sprint 6
#   PROJ-2  original, 2 pts, never done
#   PROJ-3  extra,    3 pts, added Wednesday 04/03, done Monday 09/03
#   PROJ-4  original, 1 pt,  already Done at the start
# Baseline 7 pts, the whole commitment at the start, including what was already
# Done, so the start day drops to 6 by its end; the ideal burns the 7 over 9
# later weekdays.
import contextlib
import io
import os
import re
import sys
import unittest
from datetime import date

# tests/<skill>/ mirrors skills/<skill>/.
TEST_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(TEST_DIR))
sys.path.insert(0, os.path.join(REPO_ROOT, "skills",
                os.path.basename(TEST_DIR), "scripts"))
import make_charts as charts  # noqa: E402


def ticket(key, points, extra=False, already=False):
    """A ticket with only its entry event, which the burndown checks read."""
    return {"key": key, "scope": "extra" if extra else "original",
            "events": [{"type": "joined" if extra else "committed", "points": points, "done": already}]}


def breakdown(**rows):
    """An outcome breakdown from (completed, not completed, removed) per row."""
    return {f"{row}_{outcome}": value for row, values in rows.items()
            for outcome, value in zip(("completed", "not_completed", "removed"), values)}


def sprint(**changes):
    data = {
        "sprint_name": "Sprint 7", "sprint_status": "closed", "sprint_start": "2026-03-02",
        "sprint_end": "2026-03-13", "sprint_complete_date": "2026-03-13", "today": "2026-03-16",
        "spells": [ticket("PROJ-1", 4), ticket("PROJ-2", 2), ticket("PROJ-3", 3, extra=True),
                   ticket("PROJ-4", 1, already=True)],
        "burndown_baseline": 7,
        "burndown": [{"date": f"2026-03-{day:02d}", "committed": committed, "total": total}
                     for day, committed, total in [(2, 6, 6), (3, 6, 6), (4, 6, 9), (5, 2, 5),
                                                   (6, 2, 5), (7, 2, 5), (8,
                                                                          2, 5), (9, 2, 2),
                                                   (10, 2, 2), (11, 2, 2), (12, 2, 2), (13, 2, 2)]],
        "previous_sprint": {"id": 6, "name": "Sprint 6"},
        # Independent outcome fixture: 3 original tickets (1 completed,
        # 1 open, 1 descoped) and 1 completed extra ticket.
        "outcome_breakdown_counts": breakdown(original=(1, 1, 1), carried_in=(1, 0, 0), new=(0, 1, 1),
                                              extra=(1, 0, 0)),
        "outcome_breakdown_points": breakdown(original=(4, 2, 1), carried_in=(4, 0, 0), new=(0, 2, 1),
                                              extra=(3, 0, 0)),
        "points_estimated_issue_count": 4, "points_total_issue_count": 4,
    }
    data.update(changes)
    last = min(data["today"], data["sprint_end"]
               ) if data["sprint_status"] == "active" else data["sprint_complete_date"]
    if last > "2026-03-13":
        data["burndown"] += [{"date": f"2026-03-{day:02d}", "committed": 2, "total": 2}
                             for day in range(14, int(last[-2:]) + 1)]
    data["burndown"] = [row for row in data["burndown"] if row["date"] <= last]
    return data


def by_day(series):
    """The end-of-day rows by ISO date (the start's baseline row left out)."""
    return {r["date"].isoformat(): r for r in series["rows"][1:]}


class HelpersTest(unittest.TestCase):
    def test_formatting(self):
        self.assertEqual(charts.fmt(3.0), "3")
        self.assertEqual(charts.fmt(2.5), "2.5")
        self.assertEqual(charts.esc('<a "b">'), "&lt;a &quot;b&quot;&gt;")
        self.assertEqual([charts.unit_label(n, p) for n, p in ((1, True), (2, True), (1, False), (2, False))],
                         ["pt", "pts", "ticket", "tickets"])

    def test_nice_step(self):
        self.assertEqual([charts.nice_step(s)
                         for s in (5, 12, 30, 300, 20000)], [1, 2, 5, 50, 3000])

    def test_days(self):
        days = list(charts.daterange(date(2026, 3, 6), date(2026, 3, 9)))
        self.assertEqual([d.day for d in days], [6, 7, 8, 9])
        self.assertEqual([charts.is_weekday(d)
                         for d in days], [True, False, False, True])


class BuildSeriesTest(unittest.TestCase):
    def test_closed_sprint(self):
        series = charts.build_series(sprint())
        self.assertEqual((series["baseline"], series["weekdays"], series["last_actual"]),
                         (7, 9, date(2026, 3, 13)))
        start = series["rows"][0]
        self.assertEqual(
            (start["label"], start["committed"], start["ideal"]), ("start", 7, 7))
        rows = by_day(series)
        self.assertEqual([(d, rows[d]["committed"], rows[d]["total"]) for d in
                          ("2026-03-02", "2026-03-04", "2026-03-05", "2026-03-09", "2026-03-13")],
                         [("2026-03-02", 6, 6), ("2026-03-04", 6, 9), ("2026-03-05", 2, 5),
                          ("2026-03-09", 2, 2), ("2026-03-13", 2, 2)])

    def test_ideal_holds_the_start_day_and_weekends_then_reaches_zero(self):
        rows = by_day(charts.build_series(sprint()))
        self.assertEqual(rows["2026-03-02"]["ideal"], 7)
        self.assertEqual(rows["2026-03-03"]["ideal"], round(7 * 8 / 9, 2))
        self.assertEqual(rows["2026-03-06"]["ideal"],
                         rows["2026-03-07"]["ideal"])
        self.assertEqual(rows["2026-03-07"]["ideal"],
                         rows["2026-03-08"]["ideal"])
        self.assertEqual(rows["2026-03-13"]["ideal"], 0)
        self.assertEqual(rows["2026-03-05"]["spread"],
                         round(2 - rows["2026-03-05"]["ideal"], 2))

    def test_active_sprint_stops_at_today(self):
        rows = by_day(charts.build_series(sprint(sprint_status="active", sprint_complete_date=None,
                                                 today="2026-03-05")))
        self.assertEqual(rows["2026-03-05"]["committed"], 2)
        self.assertIsNone(rows["2026-03-06"]["committed"])
        self.assertIsNotNone(rows["2026-03-06"]["ideal"])

    def test_sprint_closed_after_its_end_runs_to_the_close(self):
        series = charts.build_series(sprint(sprint_complete_date="2026-03-16"))
        self.assertEqual(series["days"][-1], date(2026, 3, 16))
        self.assertEqual(by_day(series)["2026-03-16"]["ideal"], 0)

    def test_reads_historical_actuals_from_data(self):
        data = sprint()
        data["burndown"][4].update(committed=4, total=7)
        self.assertEqual(by_day(charts.build_series(data))
                         ["2026-03-06"]["committed"], 4)

    def test_the_start_day_drops_from_the_whole_commitment_to_its_end_of_day(self):
        # PROJ-4, already Done at the start, is in the baseline but not open
        # at the end of the start day.
        data = sprint()
        series = charts.build_series(data)
        charts.validate_series(series, data)
        self.assertEqual([(r["label"], r["committed"])
                         for r in series["rows"][:2]], [("start", 7), ("close", 6)])


class ValidateSeriesTest(unittest.TestCase):
    def assert_fails(self, expected, series, data=None):
        with self.assertRaises(SystemExit) as raised:
            charts.validate_series(series, data or sprint())
        self.assertIn(expected, str(raised.exception))

    def test_valid_series(self):
        data = sprint()
        charts.validate_series(charts.build_series(data), data)

    def test_baseline_must_match_the_timeline(self):
        data = sprint()
        series = charts.build_series(data)
        data["spells"] = [t for t in data["spells"] if t["key"] != "PROJ-2"]
        self.assert_fails(
            "baseline 7 differs from the commitment at the start 5", series, data)

    def test_broken_series(self):
        def broken(change):
            series = charts.build_series(sprint())
            change(series["rows"])
            return series
        cases = {
            "the start day needs a baseline point": lambda rows: rows.pop(1),
            "ideal must hold the baseline through the start day": lambda rows: rows[1].update(ideal=5),
            "ideal rises on 2026-03-04": lambda rows: rows[3].update(ideal=7),
            "ideal changes over the weekend on 2026-03-07": lambda rows: rows[6].update(ideal=1),
            "ideal doesn't reach zero by sprint end": lambda rows: rows[-1].update(ideal=0.5),
            "committed + extra is below committed on 2026-03-04": lambda rows: rows[3].update(total=1),
            "spread is inconsistent on 2026-03-04": lambda rows: rows[3].update(spread=99),
            "no actual value on 2026-03-04": lambda rows: rows[3].update(committed=None),
        }
        for expected, change in cases.items():
            with self.subTest(expected):
                self.assert_fails(expected, broken(change))

    def test_actuals_must_stop_at_the_cutoff(self):
        data = sprint(sprint_status="active",
                      sprint_complete_date=None, today="2026-03-05")
        series = charts.build_series(data)
        series["rows"][-1].update(committed=1, total=1, spread=1)
        self.assert_fails(
            "actuals continue past the cutoff on 2026-03-13", series, data)


class ChartsTest(unittest.TestCase):
    def test_outcome_chart(self):
        stories = charts.outcome_chart(sprint(), is_points=False)
        self.assertTrue(stories.startswith("<svg "))
        self.assertIn("Sprint 7: Sprint Outcome (4 tickets)", stories)
        self.assertIn(">3 tickets</text>", stories)
        self.assertIn(">(75% of total)</text>", stories)  # the commitment
        self.assertIn("1 ticket (25% of total)", stories)  # the extra scope
        points = charts.outcome_chart(sprint(), is_points=True)
        self.assertIn("Sprint 7: Sprint Outcome (10 pts)", points)
        self.assertIn("4 pts (57% of commitment)", points)
        self.assertIn("3 pts (30% of total)", points)
        self.assertIn(">(70% of total)</text>", points)

    def test_outcome_rows_split_the_commitment(self):
        chart = charts.outcome_chart(sprint(), is_points=False)
        labels = ["Carried over from Sprint 6", "1 ticket (33% of commitment)",
                  "New commitment", "2 tickets (67% of commitment)", "Extra"]
        positions = [chart.index(label) for label in labels]
        self.assertEqual(positions, sorted(positions))
        self.assertIn(">Commitment</text>", chart)
        self.assertIn("<path d=", chart)  # the bracket

    def test_outcome_rows_without_a_previous_sprint(self):
        data = sprint(previous_sprint=None)
        for key in ("outcome_breakdown_counts", "outcome_breakdown_points"):
            breakdown = data[key]
            for outcome in ("completed", "not_completed", "removed"):
                breakdown[f"new_{outcome}"] += breakdown[f"carried_in_{outcome}"]
                breakdown[f"carried_in_{outcome}"] = 0
        chart = charts.outcome_chart(data, is_points=False)
        self.assertIn("Carried over (no previous sprint)", chart)
        self.assertIn("0 tickets (0% of commitment)", chart)

    def test_outcome_bars_share_one_scale(self):
        # New commitment (2 tickets: 1 not completed, 1 removed) is the
        # longest row, so it spans the full bar width; carry-over and extra
        # (1 ticket each) get half of it.
        width, _, left = charts.outcome_layout(sprint())
        bar_w = width - charts.OUTCOME_MARGIN - left
        # pts: carry-over 4 is the longest
        cases = [(False, [1, 1, 1, 1], 2), (True, [4, 2, 1, 3], 4)]
        for is_points, values, longest in cases:
            with self.subTest(is_points=is_points):
                chart = charts.outcome_chart(sprint(), is_points=is_points)
                widths = [float(w) for w in re.findall(
                    r'width="([\d.]+)" height="40"', chart)]
                self.assertEqual(
                    widths, [round(v * bar_w / longest, 1) for v in values])

    def test_fractional_longest_bar_fills_available_width(self):
        data = sprint(outcome_breakdown_points=breakdown(original=(0.5, 0, 0), carried_in=(0, 0, 0),
                                                         new=(0.5, 0, 0), extra=(0.25, 0, 0)))
        width, _, left = charts.outcome_layout(data)
        chart = charts.outcome_chart(data, is_points=True)
        widths = [float(w) for w in re.findall(
            r'width="([\d.]+)" height="40"', chart)]
        available = width - charts.OUTCOME_MARGIN - left
        self.assertEqual(
            widths, [round(available, 1), round(available / 2, 1)])

    def test_both_outcome_charts_share_one_layout(self):
        def layout(chart):
            width = float(
                re.search(r'<svg [^>]*width="([\d.]+)"', chart).group(1))
            bars = [(float(x), float(w)) for x, w in
                    re.findall(r'<rect x="([\d.]+)" y="[\d.]+" width="([\d.]+)" height="40"', chart)]
            bracket = re.search(r'<path d="M ([\d.]+)', chart).group(1)
            return width, min(x for x, _ in bars), max(x + w for x, w in bars), bracket
        long_name = sprint(previous_sprint={
                           "id": 6, "name": "A sprint with a much longer name than usual"})
        for data in (sprint(), long_name):
            with self.subTest(previous=data["previous_sprint"]["name"]):
                stories = layout(charts.outcome_chart(data, is_points=False))
                points = layout(charts.outcome_chart(data, is_points=True))
                self.assertEqual(stories, points)
                width, start, end, _ = stories
                self.assertGreaterEqual(
                    end - start, charts.OUTCOME_MIN_BAR_SHARE * width)  # the longest bar
                self.assertAlmostEqual(width - end, charts.OUTCOME_MARGIN)
        self.assertEqual(layout(charts.outcome_chart(sprint(), is_points=False))[
                         0], charts.OUTCOME_WIDTH)
        # A long label narrows the bars down to their minimum share, then widens the chart.
        width, start, end, _ = layout(
            charts.outcome_chart(long_name, is_points=False))
        self.assertGreater(width, charts.OUTCOME_WIDTH)
        self.assertAlmostEqual(
            end - start, charts.OUTCOME_MIN_BAR_SHARE * width, delta=1)

    def test_the_label_column_fits_its_labels(self):
        # The bracket sits 10 px left of the widest row label, of either
        # chart, and the bars start 12 px right of the labels.
        data = sprint()
        _, bracket_x, left = charts.outcome_layout(data)
        widest = max(max(charts.text_width(label, 12), charts.text_width(sub, 11))
                     for is_points in (False, True) for _, label, sub in charts.outcome_labels(data, is_points)[3])
        self.assertAlmostEqual(left - bracket_x, 10 + widest + 12, delta=1)

    def test_outcome_chart_notes_partial_estimation(self):
        chart = charts.outcome_chart(
            sprint(points_estimated_issue_count=3), is_points=True)
        self.assertIn("(3/4 tickets estimated)", chart)

    def test_outcome_labels_join_beside_a_bar_too_narrow_for_them(self):
        data = sprint(outcome_breakdown_counts=breakdown(original=(100, 1, 0), carried_in=(0, 0, 0),
                                                         new=(100, 1, 0), extra=(400, 0, 0)))
        self.assertIn("Completed: 100 (99%); Not completed: 1 (1%)",
                      charts.outcome_chart(data, is_points=False))

    def test_positive_segment_percentages_never_round_to_zero(self):
        for total in (200, 300):
            with self.subTest(total=total):
                data = sprint(outcome_breakdown_counts=breakdown(
                    original=(total - 1, 1, 0), carried_in=(0, 0, 0),
                    new=(total - 1, 1, 0), extra=(total * 4, 0, 0)))
                chart = charts.outcome_chart(data, is_points=False)
                self.assertIn("Not completed: 1 (&lt;1%)", chart)
                self.assertNotIn("Not completed: 1 (0%)", chart)

    def test_the_longest_bar_keeps_its_labels_inside(self):
        # No room to its right: each label stays in its segment, the bare
        # number where the full label doesn't fit.
        data = sprint(outcome_breakdown_counts=breakdown(original=(8, 7, 1), carried_in=(0, 0, 0),
                                                         new=(8, 7, 1), extra=(1, 0, 0)))
        chart = charts.outcome_chart(data, is_points=False)
        for label in (">8 (50%)</text>", ">7 (44%)</text>", ">1</text>"):
            self.assertIn(label, chart)
        self.assertNotIn("Removed: 1", chart)

    def test_burndown_chart(self):
        data = sprint()
        chart = charts.burndown_chart(data, charts.build_series(data))
        self.assertEqual(chart.count("<polyline "), 4)
        self.assertIn("Sprint 7: Burndown", chart)
        self.assertIn("Commitment of 7 pts at the start on 02/03/2026", chart)
        self.assertEqual(chart.count(f'fill="{charts.WEEKEND}"'), 2)

    def test_cutoff(self):
        active = {"sprint_status": "active", "sprint_complete_date": None}
        cases = [
            ("closed", {}, date(2026, 3, 13), "sprint closed"),
            ("active", {**active, "today": "2026-03-05"},
             date(2026, 3, 5), "today"),
            ("active past its end", {
             **active, "today": "2026-03-18"}, date(2026, 3, 13), "sprint end"),
        ]
        for name, changes, last_actual, label in cases:
            with self.subTest(name):
                data = sprint(**changes)
                series = charts.build_series(data)
                self.assertEqual(series["last_actual"], last_actual)
                chart = charts.burndown_chart(data, series)
                for other in ("sprint closed", "today", "sprint end"):
                    if other == label:
                        self.assertIn(f">{other}<", chart)
                    else:
                        self.assertNotIn(f">{other}<", chart)

    def test_print_series(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            charts.print_series(charts.build_series(sprint()))
        lines = out.getvalue().splitlines()
        self.assertTrue(lines[0].startswith(
            "baseline 7 pts committed at the start on 2026-03-02"))
        self.assertEqual(lines[2].split(), ["2026-03-02",
                         "Mon", "start", "7", "7", "7", "0"])
        self.assertEqual(lines[3].split(), ["2026-03-02",
                         "Mon", "close", "6", "6", "7", "-1"])
        self.assertEqual(lines[-1].split(), ["2026-03-13",
                         "Fri", "close", "2", "2", "0", "2"])


if __name__ == "__main__":
    unittest.main()
