"""Unit tests for skills/agentic-manager-jira-sprint-report/scripts/make_charts.py.
Run with: python3 tests/run.py agentic-manager-jira-sprint-report

A two-week sprint, Monday 02/03/2026 to Friday 13/03/2026, small enough to
work its burndown out by hand:
  PROJ-1  original, 4 pts, done Thursday 05/03, carried over from Sprint 6
  PROJ-2  original, 2 pts, never done
  PROJ-3  extra,    3 pts, added Wednesday 04/03, done Monday 09/03
  PROJ-4  original, 1 pt,  already Done at the start
Baseline 7 pts, the whole commitment at the start, including what was already
Done, so the start day drops to 6 by its end; the ideal burns the 7 over 9
later weekdays.
"""

import contextlib
import html
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
    last = data["today"] if data["sprint_status"] == "active" else data["sprint_complete_date"]
    if last > "2026-03-13":
        data["burndown"] += [{"date": f"2026-03-{day:02d}", "committed": 2, "total": 2}
                             for day in range(14, int(last[-2:]) + 1)]
    data["burndown"] = [row for row in data["burndown"] if row["date"] <= last]
    return data


def by_day(series):
    """The end-of-day rows by ISO date (the start's baseline row left out)."""
    return {r["date"].isoformat(): r for r in series["rows"][1:]}


def single_row(row, values, extra=(1, 0, 0)):
    """A ticket breakdown with all the commitment in one row (carried_in or
    new) and a small extra row, to set one bar's segments exactly."""
    rows = {"carried_in": (0, 0, 0), "new": (0, 0, 0)}
    rows[row] = values
    return breakdown(original=values, extra=extra, **rows)


def bar_widths(chart):
    return [float(w) for w in re.findall(r'width="([\d.]+)" height="40"', chart)]


class HelpersTest(unittest.TestCase):
    def test_helpers(self):
        days = list(charts.daterange(date(2026, 3, 6), date(2026, 3, 9)))
        cases = [
            ("fmt, a whole number", charts.fmt(3.0), "3"),
            ("fmt, a fraction", charts.fmt(2.5), "2.5"),
            ("esc", charts.esc('<a "b">'), "&lt;a &quot;b&quot;&gt;"),
            ("unit_label", [charts.unit_label(n, p) for n, p in ((1, True), (2, True), (1, False), (2, False))],
             ["pt", "pts", "ticket", "tickets"]),
            ("nice_step", [charts.nice_step(s)
             for s in (5, 12, 30, 300, 20000)], [1, 2, 5, 50, 3000]),
            ("daterange, both ends included", [
             d.day for d in days], [6, 7, 8, 9]),
            ("is_weekday", [charts.is_weekday(d)
             for d in days], [True, False, False, True]),
        ]
        for name, got, expected in cases:
            with self.subTest(name):
                self.assertEqual(got, expected)

    def test_text_width(self):
        # Wide letters measure wider than narrow ones, and bold wider still:
        # the label column and the fit-inside-a-bar decisions rely on it.
        self.assertGreater(charts.text_width("WWW", 12),
                           charts.text_width("iii", 12))
        self.assertAlmostEqual(charts.text_width("Done", 12, bold=True),
                               charts.text_width("Done", 12) * 1.08)


class BuildSeriesTest(unittest.TestCase):
    def test_closed_sprint(self):
        series = charts.build_series(sprint())
        self.assertEqual((series["baseline"], series["weekdays"], series["last_actual"]),
                         (7, 9, date(2026, 3, 13)))
        # The start day has two points: the whole commitment, PROJ-4 already
        # Done included, then that day's reading without it.
        self.assertEqual([(r["date"], r["label"], r["committed"], r["ideal"]) for r in series["rows"][:2]],
                         [(date(2026, 3, 2), "start", 7, 7), (date(2026, 3, 2), "close", 6, 7)])
        rows = by_day(series)
        self.assertEqual([(d, rows[d]["committed"], rows[d]["total"]) for d in
                          ("2026-03-04", "2026-03-05", "2026-03-09", "2026-03-13")],
                         [("2026-03-04", 6, 9), ("2026-03-05", 2, 5),
                          ("2026-03-09", 2, 2), ("2026-03-13", 2, 2)])

    def test_reads_historical_actuals_from_data(self):
        # The lines replay data.json's burndown, the same events as the rest
        # of the report, rather than recomputing from the spells.
        data = sprint()
        data["burndown"][4].update(committed=4, total=7)
        self.assertEqual(by_day(charts.build_series(data))
                         ["2026-03-06"]["committed"], 4)

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

    def test_a_one_day_sprint_holds_the_ideal(self):
        # No weekday after the start: no pace to divide by, so the ideal stays
        # at the baseline instead of failing.
        data = sprint(sprint_start="2026-03-13")
        data["burndown"] = data["burndown"][-1:]
        series = charts.build_series(data)
        self.assertEqual(series["weekdays"], 0)
        self.assertEqual([r["ideal"] for r in series["rows"]], [7, 7])

    def test_where_the_actuals_and_the_chart_end(self):
        # Actuals stop at the close or fetch; the chart runs at least to the
        # planned end, and later actuals keep an ideal of zero.
        active = {"sprint_status": "active", "sprint_complete_date": None}
        cases = [
            ("closed on its end date", {}, date(2026, 3, 13), date(2026, 3, 13)),
            ("closed after its end", {"sprint_complete_date": "2026-03-16"},
             date(2026, 3, 16), date(2026, 3, 16)),
            ("running", {**active, "today": "2026-03-05"},
             date(2026, 3, 5), date(2026, 3, 13)),
            ("running past its end", {**active, "today": "2026-03-18"},
             date(2026, 3, 18), date(2026, 3, 18)),
        ]
        for name, changes, last_actual, last_day in cases:
            with self.subTest(name):
                series = charts.build_series(sprint(**changes))
                self.assertEqual(
                    (series["last_actual"], series["days"][-1]), (last_actual, last_day))
                last = series["rows"][-1]
                self.assertEqual(last["ideal"], 0)
                self.assertEqual(last["committed"] is None,
                                 last_actual < last_day)


class OutcomeChartTest(unittest.TestCase):
    def test_labels(self):
        # Titles, row sublabels and the bracket's lines: each original row as
        # a share of the commitment, the extra and the commitment as shares of
        # the total.
        empty = breakdown(original=(0, 0, 0), carried_in=(
            0, 0, 0), new=(0, 0, 0), extra=(0, 0, 0))
        no_previous = sprint(previous_sprint=None, outcome_breakdown_counts=breakdown(
            original=(1, 1, 1), carried_in=(0, 0, 0), new=(1, 1, 1), extra=(1, 0, 0)))
        running = {"sprint_status": "active",
                   "sprint_complete_date": None, "today": "2026-03-05"}
        cases = [
            ("tickets", sprint(), False,
             ["Sprint 7: Sprint Outcome (4 tickets)</text>", ">3 tickets</text>", ">(75% of total)</text>",
              "1 ticket (33% of commitment)", "1 ticket (25% of total)", ">Not completed</text>"],
             ["estimated"]),
            ("pts", sprint(), True,
             ["Sprint 7: Sprint Outcome (10 pts)</text>", "4 pts (57% of commitment)", "3 pts (30% of total)",
              ">(70% of total)</text>"], ["estimated"]),
            # Points read low when some tickets have no estimate, so the title
            # says how many do.
            ("partial estimation", sprint(points_estimated_issue_count=3), True,
             ["Sprint 7: Sprint Outcome (10 pts) (3/4 tickets estimated)"], []),
            ("tickets ignore estimation", sprint(
                points_estimated_issue_count=3), False, [], ["estimated"]),
            ("no previous sprint", no_previous, False,
             ["Carried over (no previous sprint)", "0 tickets (0% of commitment)"], []),
            # Work not done yet isn't "not completed" while the sprint runs.
            ("running sprint", sprint(**running), False,
             [">Open</text>"], ["Not completed"]),
            # Nothing to share out: no percentages rather than "n/a".
            ("empty sprint", sprint(outcome_breakdown_counts=empty), False,
             ["Sprint Outcome (0 tickets)", ">0 tickets</text>"], ["% of", "n/a"]),
        ]
        for name, data, is_points, present, absent in cases:
            with self.subTest(name):
                chart = charts.outcome_chart(data, is_points=is_points)
                self.assertTrue(chart.startswith("<svg "))
                for label in present:
                    self.assertIn(label, chart)
                for label in absent:
                    self.assertNotIn(label, chart)

    def test_rows_split_the_commitment_under_a_bracket(self):
        chart = charts.outcome_chart(sprint(), is_points=False)
        labels = ["Carried over from Sprint 6", "1 ticket (33% of commitment)",
                  "New commitment", "2 tickets (67% of commitment)", "Extra"]
        positions = [chart.index(label) for label in labels]
        self.assertEqual(positions, sorted(positions))
        self.assertIn(">Commitment</text>", chart)
        # From the top of the first bar to the bottom of the second.
        self.assertRegex(chart, r'<path d="M [\d.]+ 56 H [\d.]+ V 152 ')
        legend = re.findall(
            r'height="12" fill="[^"]+"/>\n<text [^>]*>([^<]+)<', chart)
        self.assertEqual(legend, ["Completed", "Not completed", "Descoped"])

    def test_bars_share_one_scale(self):
        # The longest row spans the full bar width and sets the scale for the
        # others, also when it's a fraction; zero segments draw nothing.
        cases = [
            # New commitment (2 tickets) is the longest.
            ("tickets", sprint(), False, [1, 1, 1, 1], 2),
            # Carry-over (4 pts) is the longest.
            ("pts", sprint(), True, [4, 2, 1, 3], 4),
            ("fractional", sprint(outcome_breakdown_points=breakdown(
                original=(0.5, 0, 0), carried_in=(0, 0, 0), new=(0.5, 0, 0), extra=(0.25, 0, 0))),
             True, [0.5, 0.25], 0.5),
        ]
        for name, data, is_points, values, longest in cases:
            with self.subTest(name):
                width, _, left = charts.outcome_layout(data)
                bar_w = width - charts.OUTCOME_MARGIN - left
                self.assertEqual(bar_widths(charts.outcome_chart(data, is_points=is_points)),
                                 [round(v * bar_w / longest, 1) for v in values])

    def test_both_charts_share_one_layout(self):
        def layout(chart):
            width_match = re.search(r'<svg [^>]*width="([\d.]+)"', chart)
            assert width_match is not None, "chart has no SVG width"
            width = float(width_match.group(1))
            bars = [(float(x), float(w)) for x, w in
                    re.findall(r'<rect x="([\d.]+)" y="[\d.]+" width="([\d.]+)" height="40"', chart)]
            bracket_match = re.search(r'<path d="M ([\d.]+)', chart)
            assert bracket_match is not None, "chart has no commitment bracket"
            bracket = bracket_match.group(1)
            return width, min(x for x, _ in bars), max(x + w for x, w in bars), bracket
        long_name = sprint(previous_sprint={
                           "id": 6, "name": "A sprint with a much longer name than usual"})
        # A long label narrows the bars down to their minimum share, then
        # widens the chart; otherwise the chart keeps its standard width.
        for name, data, grows in (("usual", sprint(), False), ("long name", long_name, True)):
            with self.subTest(name):
                stories = layout(charts.outcome_chart(data, is_points=False))
                points = layout(charts.outcome_chart(data, is_points=True))
                self.assertEqual(stories, points)
                width, start, end, _ = stories
                self.assertGreaterEqual(
                    end - start, charts.OUTCOME_MIN_BAR_SHARE * width - 1)  # the longest bar
                self.assertAlmostEqual(width - end, charts.OUTCOME_MARGIN)
                if grows:
                    self.assertGreater(width, charts.OUTCOME_WIDTH)
                    self.assertAlmostEqual(
                        end - start, charts.OUTCOME_MIN_BAR_SHARE * width, delta=1)
                else:
                    self.assertEqual(width, charts.OUTCOME_WIDTH)

    def test_the_label_column_fits_its_labels(self):
        # The bracket sits 10 px left of the widest row label, of either
        # chart, and the bars start 12 px right of the labels.
        data = sprint()
        _, bracket_x, left = charts.outcome_layout(data)
        widest = max(max(charts.text_width(label, 12), charts.text_width(sub, 11))
                     for is_points in (False, True) for _, label, sub in charts.outcome_labels(data, is_points)[3])
        self.assertAlmostEqual(left - bracket_x, 10 + widest + 12, delta=1)

    def test_segment_label_placement(self):
        # (x relative to the bar's start, label) of the new-commitment row.
        # Inside every segment if all fit; else joined beside the bar; else,
        # with no room beside it (the longest bar), each kept inside, as the
        # bare number if only that fits, and the rest joined over its start.
        cases = [
            ("all inside", single_row("new", (8, 8, 0), extra=(
                16, 0, 0)), ["inside 8 (50%)", "inside 8 (50%)"]),
            ("joined beside the bar", single_row("new", (100, 1, 0), extra=(400, 0, 0)),
             ["beside Completed: 100 (99%); Not completed: 1 (1%)"]),
            ("shortened inside", single_row("new", (8, 7, 1)),
             ["inside 8 (50%)", "inside 7 (44%)", "inside 1"]),
            ("joined over the start", single_row("new", (60, 1, 0)),
             ["inside 60 (98%)", "start Not completed: 1 (2%)"]),
            # Neither share rounds to all or nothing: <1% and >99%, never 0% or 100%.
            ("tiny share", single_row("new", (199, 1, 0), extra=(800, 0, 0)),
             ["beside Completed: 199 (&gt;99%); Not completed: 1 (&lt;1%)"]),
        ]
        for name, counts, expected in cases:
            with self.subTest(name):
                data = sprint(outcome_breakdown_counts=counts)
                chart = charts.outcome_chart(data, is_points=False)
                _, _, left = charts.outcome_layout(data)
                rects = [(float(x), float(w)) for x, w in
                         re.findall(r'<rect x="([\d.]+)" y="112.0" width="([\d.]+)" height="40"', chart)]
                end = rects[-1][0] + rects[-1][1]
                placed = []
                for x, content in re.findall(r'<text x="([\d.]+)" y="136.0"[^>]*>([^<]*)</text>', chart):
                    x = float(x)
                    if abs(x - (left + 8)) < 0.2:
                        placed.append(f"start {content}")
                    elif abs(x - (end + 8)) < 0.2:
                        placed.append(f"beside {content}")
                    else:
                        self.assertTrue(
                            any(abs(x - (rx + rw / 2)) < 0.2 for rx, rw in rects), x)
                        placed.append(f"inside {content}")
                self.assertEqual(placed, expected)

    def test_fallback_labels_do_not_overlap_retained_labels(self):
        for name in ("Sprint 6", "A sprint with a much longer name than usual"):
            for values in ((60, 1, 1), (1, 60, 1), (1, 1, 60)):
                for is_points in (False, True):
                    with self.subTest(name=name, values=values, is_points=is_points):
                        field = "outcome_breakdown_points" if is_points else "outcome_breakdown_counts"
                        data = sprint(previous_sprint={"id": 6, "name": name},
                                      **{field: single_row("new", values)})
                        chart = charts.outcome_chart(data, is_points)
                        labels = []
                        for x, y, anchor, label in re.findall(
                                r'<text x="([\d.]+)" y="([\d.]+)" font-size="12" '
                                r'fill="[^"]+" text-anchor="(\w+)" font-weight="bold">([^<]+)</text>', chart):
                            x, y = float(x), float(y)
                            if not 112 <= y <= 152:
                                continue
                            label = html.unescape(label)
                            width = charts.text_width(label, 12, True)
                            left = x - width / 2 if anchor == "middle" else x
                            labels.append((left, left + width, y, label))
                        self.assertEqual(len(labels), 2)
                        a, b = labels
                        self.assertTrue(a[1] <= b[0] or b[1] <= a[0] or abs(a[2] - b[2]) >= 16,
                                        labels)
                        joined = " ".join(label for *_, label in labels)
                        self.assertIn("60 (97%)", joined)
                        self.assertEqual(joined.count("1 (2%)"), 2)


class BurndownChartTest(unittest.TestCase):
    def test_burndown_chart(self):
        data = sprint()
        chart = charts.burndown_chart(data, charts.build_series(data))
        self.assertTrue(chart.startswith("<svg "))
        self.assertIn("Sprint 7: Burndown", chart)
        self.assertIn("Commitment of 7 pts at the start on 02/03/2026 · ideal paced over 9 later weekdays · "
                      "actuals to 13/03/2026 (sprint closed)", chart)
        self.assertEqual(chart.count(
            f'fill="{charts.WEEKEND}"'), 2)  # one weekend
        self.assertEqual(
            # a date per day
            len(re.findall(r'<text [^>]*rotate\(-45', chart)), 12)

    def test_series_lines_and_legend(self):
        # Blue and violet are close for deuteranopia, so each series has its
        # own dash pattern, and the legend repeats it.
        dashes = [spec["dash"] for spec in charts.SERIES.values()]
        self.assertEqual(len(set(dashes)), len(dashes))
        data = sprint()
        chart = charts.burndown_chart(data, charts.build_series(data))
        lines = re.findall(r'<polyline points="([^"]*)" fill="none" stroke="([^"]+)"[^>]*?(?: stroke-dasharray="([^"]+)")?/>',
                           chart)
        legend = re.findall(r'<line [^>]*stroke="([^"]+)" stroke-width="[\d.]+" stroke-linecap="round"'
                            r'(?: stroke-dasharray="([^"]+)")?/>', chart)
        expected = [(spec["color"], spec["dash"] or "")
                    for spec in charts.SERIES.values()]
        self.assertEqual([(color, dash) for _, color, dash in lines], expected)
        self.assertEqual(legend, expected)
        for spec in charts.SERIES.values():
            self.assertIn(f">{spec['label']}</text>", chart)
        # The start day's drop is vertical: its two points share an x.
        committed = [p.split(",") for p in lines[0][0].split()]
        self.assertEqual(committed[0][0], committed[1][0])
        self.assertNotEqual(committed[0][1], committed[1][1])

    def test_point_values(self):
        # The commitment's value on every actual point, the start's baseline
        # to the left; the total's only where it differs (04/03 to 08/03).
        data = sprint()
        chart = charts.burndown_chart(data, charts.build_series(data))

        def values(key):
            return re.findall(rf'fill="{charts.SERIES[key]["color"]}" text-anchor="(\w+)" font-weight="bold">'
                              r'([\d.]+)</text>', chart)
        committed = values("committed")
        self.assertEqual(committed[0], ("end", "7"))
        self.assertEqual([v for _, v in committed[1:]], [
                         "6", "6", "6", "2", "2", "2", "2", "2", "2", "2", "2", "2"])
        self.assertEqual([v for _, v in values("total")],
                         ["9", "5", "5", "5", "5"])

    def test_cutoff(self):
        # The label names why the actuals stop, right of the line or, near
        # the chart's right edge, left of it.
        active = {"sprint_status": "active", "sprint_complete_date": None}
        cases = [
            ("closed", {}, "sprint closed", "end"),
            ("running", {**active, "today": "2026-03-05"}, "today", "start"),
            ("running past its end", {
             **active, "today": "2026-03-18"}, "today", "start"),
        ]
        for name, changes, label, anchor in cases:
            with self.subTest(name):
                data = sprint(**changes)
                chart = charts.burndown_chart(data, charts.build_series(data))
                found = re.findall(r'font-size="10" fill="[^"]+" text-anchor="(\w+)">'
                                   r'(sprint closed|today|sprint end)</text>', chart)
                self.assertEqual(found, [(anchor, label)])


class PrintSeriesTest(unittest.TestCase):
    def test_print_series(self):
        # {line number: its words}: the header, then each point's date,
        # weekday, point, committed, total, ideal and spread; days past the
        # cutoff show only the ideal.
        running = {"sprint_status": "active",
                   "sprint_complete_date": None, "today": "2026-03-05"}
        cases = [
            ("closed", sprint(), {
                0: "baseline 7 pts committed at the start on 2026-03-02; "
                   "ideal over 9 later weekdays; actuals to 2026-03-13".split(),
                2: ["2026-03-02", "Mon", "start", "7", "7", "7", "0"],
                3: ["2026-03-02", "Mon", "close", "6", "6", "7", "-1"],
                -1: ["2026-03-13", "Fri", "close", "2", "2", "0", "2"]}),
            ("running", sprint(**running),
             {-1: ["2026-03-13", "Fri", "close", "-", "-", "0", "-"]}),
        ]
        for name, data, expected in cases:
            with self.subTest(name):
                out = io.StringIO()
                with contextlib.redirect_stdout(out):
                    charts.print_series(charts.build_series(data))
                lines = out.getvalue().splitlines()
                self.assertEqual({n: lines[n].split()
                                 for n in expected}, expected)


if __name__ == "__main__":
    unittest.main()
