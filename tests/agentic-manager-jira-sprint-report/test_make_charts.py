# Unit tests for skills/agentic-manager-jira-sprint-report/scripts/make_charts.py.
# Run with: python3 tests/run.py agentic-manager-jira-sprint-report
#
# A two-week sprint, Monday 02/03/2026 to Friday 13/03/2026, small enough to
# work its burndown out by hand:
#   PROJ-1  original, 4 pts, done Thursday 05/03
#   PROJ-2  original, 2 pts, never done
#   PROJ-3  extra,    3 pts, added Wednesday 04/03, done Monday 09/03
#   PROJ-4  original, 1 pt,  already Done at the start
# Baseline 6 pts, the commitment less what was already Done; the ideal burns it
# over 9 later weekdays.
import contextlib
import io
import os
import sys
import unittest
from datetime import date

# tests/<skill>/ mirrors skills/<skill>/.
TEST_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(TEST_DIR))
sys.path.insert(0, os.path.join(REPO_ROOT, "skills",
                os.path.basename(TEST_DIR), "scripts"))
import make_charts as charts  # noqa: E402


def issue(key, points, extra=False, already=False):
    return {"key": key, "storyPoints": points, "addedMidSprint": extra,
            "startState": {"storyPoints": points, "done": already}}


def sprint(**changes):
    data = {
        "sprint_name": "Sprint 7", "sprint_status": "closed", "sprint_start": "2026-03-02",
        "sprint_end": "2026-03-13", "sprint_complete_date": "2026-03-13", "today": "2026-03-16",
        "issues": [issue("PROJ-1", 4), issue("PROJ-2", 2),
                   issue("PROJ-3", 3, extra=True),
                   issue("PROJ-4", 1, already=True)],
        "removed_issues": [],
        "burndown": [{"date": f"2026-03-{day:02d}", "committed": committed, "total": total}
                     for day, committed, total in [(2, 6, 6), (3, 6, 6), (4, 6, 9), (5, 2, 5),
                                                   (6, 2, 5), (7, 2, 5), (8,
                                                                          2, 5), (9, 2, 2),
                                                   (10, 2, 2), (11, 2, 2), (12, 2, 2), (13, 2, 2)]],
        "scope_timeline": [{"date": "2026-03-02", "added_keys": ["PROJ-1", "PROJ-2", "PROJ-4"]}],
        "commitment_breakdown_counts": {"original_completed": 2, "original_not_completed": 1,
                                        "extra_completed": 1, "extra_not_completed": 0},
        "commitment_breakdown_points": {"original_completed": 5, "original_not_completed": 2,
                                        "extra_completed": 3, "extra_not_completed": 0},
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
                         ["story point", "story points", "story", "stories"])

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
                         (6, 9, date(2026, 3, 13)))
        start = series["rows"][0]
        self.assertEqual(
            (start["label"], start["committed"], start["ideal"]), ("start", 6, 6))
        rows = by_day(series)
        self.assertEqual([(d, rows[d]["committed"], rows[d]["total"]) for d in
                          ("2026-03-02", "2026-03-04", "2026-03-05", "2026-03-09", "2026-03-13")],
                         [("2026-03-02", 6, 6), ("2026-03-04", 6, 9), ("2026-03-05", 2, 5),
                          ("2026-03-09", 2, 2), ("2026-03-13", 2, 2)])

    def test_ideal_holds_the_start_day_and_weekends_then_reaches_zero(self):
        rows = by_day(charts.build_series(sprint()))
        self.assertEqual(rows["2026-03-02"]["ideal"], 6)
        self.assertEqual(rows["2026-03-03"]["ideal"], round(6 * 8 / 9, 2))
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

    def test_work_done_before_it_entered_is_never_in_the_baseline(self):
        data = sprint(removed_issues=[issue("PROJ-5", 5, already=True)])
        data["scope_timeline"][0]["added_keys"].append("PROJ-5")
        series = charts.build_series(data)
        self.assertEqual((series["baseline"], by_day(series)[
                         "2026-03-02"]["committed"]), (6, 6))


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
        data["scope_timeline"][0]["added_keys"].remove("PROJ-2")
        self.assert_fails(
            "baseline 6 differs from the open commitment added at the start 4", series, data)

    def test_broken_series(self):
        def broken(change):
            series = charts.build_series(sprint())
            change(series["rows"])
            return series
        cases = {
            "the start day needs a baseline point": lambda rows: rows.pop(1),
            "ideal must hold the baseline through the start day": lambda rows: rows[1].update(ideal=5),
            "ideal rises on 2026-03-04": lambda rows: rows[3].update(ideal=6),
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
        self.assertIn("Sprint 7: Sprint Outcome (4 stories)", stories)
        self.assertIn("(3 stories)", stories)
        points = charts.outcome_chart(sprint(), is_points=True)
        self.assertIn("Sprint 7: Sprint Outcome (10 story points)", points)
        self.assertIn("5 (71%)", points)

    def test_outcome_chart_notes_partial_estimation(self):
        chart = charts.outcome_chart(
            sprint(points_estimated_issue_count=3), is_points=True)
        self.assertIn("(3/4 issues estimated)", chart)

    def test_outcome_labels_join_beside_a_bar_too_narrow_for_them(self):
        data = sprint(commitment_breakdown_counts={"original_completed": 100, "original_not_completed": 1,
                                                   "extra_completed": 0, "extra_not_completed": 0})
        self.assertIn("Completed: 100 (99%); Not completed: 1 (1%)",
                      charts.outcome_chart(data, is_points=False))

    def test_burndown_chart(self):
        data = sprint()
        chart = charts.burndown_chart(data, charts.build_series(data))
        self.assertEqual(chart.count("<polyline "), 4)
        self.assertIn("Sprint 7: Burndown", chart)
        self.assertIn("Committed 6 pts at the start on 02/03/2026", chart)
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
            "baseline 6 pts committed at the start on 2026-03-02"))
        self.assertEqual(lines[2].split(), ["2026-03-02",
                         "Mon", "start", "6", "6", "6", "0"])
        self.assertEqual(lines[-1].split(), ["2026-03-13",
                         "Fri", "close", "2", "2", "0", "2"])


if __name__ == "__main__":
    unittest.main()
