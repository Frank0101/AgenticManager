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
from prep_fixture import (DATA, DATA_BY_PROJECT, DATA_NO_EPIC_FIRST, PERSON, PREP, SUMMARIES, VALUE_NAMES, WEEKS, WORK_RAW,  # noqa: E402
                          temp_output, write_prep)


class BuildDataTest(unittest.TestCase):
    def test_build(self):
        # The fixture's data.json, worked out by hand from its raw files: the
        # weeks, each source's items without the fields kept only to check
        # them, its facts, such as the main focus of its one resolved issue,
        # the charts' series and each search's address.
        self.assertEqual(build_data.build(
            WORK_RAW, PERSON, SUMMARIES, VALUE_NAMES), DATA)

    def test_build_data(self):
        # Written once every raw file is in and follows its rules, and every
        # summary is in; refused, writing nothing, while one is missing or a
        # raw file is from another period.
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
        os.remove(os.path.join(folder, PREP, "slack.json"))
        with self.assertRaisesRegex(SystemExit, "slack.json missing"):
            build_data.build_data(PREP)
        write_prep(folder, data=None, report=False)
        self.assertEqual(common.read_json(build_data.build_data(PREP)), DATA)

    def test_weeks_are_the_calendar_weeks_of_the_period(self):
        # data.json's weeks are the period's calendar weeks, Monday to
        # Sunday, the first and last clipped to it, and never grouped, however
        # long the period: a year is its fifty-three weeks.
        folder = temp_output(self)
        write_prep(folder, data=None, report=False)
        self.assertEqual(common.read_json(
            build_data.build_data(PREP))["weeks"], WEEKS)
        for start, end, count in (("2026-09-02", "2026-09-02", 1), ("2026-01-01", "2026-12-31", 53)):
            with self.subTest(start):
                person = {**PERSON, "start": start, "end": end}
                weeks = build_data.build(
                    {}, person, SUMMARIES, VALUE_NAMES)["weeks"]
                self.assertEqual((weeks, len(weeks)),
                                 (common.calendar_weeks(start, end), count))
                self.assertEqual((weeks[0][0], weeks[-1][1]), (start, end))

    def test_series(self):
        # Each week's issues in all, by epic in the epics' order, of any
        # other epic and with none; the resolved issues by points and epic;
        # and the epics' order, the resolved ones' first, at most MAX_GROUPS.
        weeks = [["2026-07-01", "2026-07-05"], ["2026-07-06", "2026-07-12"]]
        a, b, c = {"key": "PROJ-1"}, {"key": "PROJ-2"}, {"key": "PROJ-3"}
        items = [{"date": "2026-07-02", "epic": a, "points": 3}, {"date": "2026-07-07", "epic": b, "points": 3},
                 {"date": "2026-07-08", "epic": None, "points": None}, {"date": "2026-07-09", "epic": c, "points": 3}]
        self.assertEqual(build_data.grouped(items, ["PROJ-2", "PROJ-1", "PROJ-9"], build_data.epic_key,
                                            lambda found: build_data.weekly(found, weeks), "epics", "no_epic"),
                         {"total": [1, 3], "epics": {"PROJ-2": [0, 1], "PROJ-1": [1, 0]}, "other": [0, 1],
                          "no_epic": [0, 1]})
        self.assertEqual(build_data.points_by_epic(items, ["PROJ-1", "PROJ-2"]),
                         [{"points": 3, "issues": 3, "epics": {"PROJ-1": 1, "PROJ-2": 1}, "other": 1, "no_epic": 0}])
        self.assertEqual(build_data.chart_order(["PROJ-2"], {"PROJ-9", "PROJ-2"}),
                         ["PROJ-2", "PROJ-9"])
        self.assertEqual(build_data.chart_order([f"PROJ-{n}" for n in range(12)], set()), [
                         f"PROJ-{n}" for n in range(common.MAX_GROUPS)])

    def test_github_facts(self):
        # The merged pull requests by repository, the most first, those
        # beyond the coloured ones counted as other; the main focus; how
        # many repositories each list is in; the median of the lines
        # changed; and the merged ones by size, on a log scale, and
        # repository.
        def pull(repo, lines, day="2026-07-02"):
            return {"repo": repo, "lines": lines, "date": day}
        merged = [pull("acme/api", 5), pull("acme/api", 150),
                  pull("acme/api", 2000), pull("acme/web", 80)]
        merged += [pull(f"acme/r{n}", 600) for n in range(10)]
        opened = merged + [pull("acme/docs", 3)]
        facts = build_data.source_facts("github", {"opened": opened, "merged": merged},
                                        [["2026-07-01", "2026-07-05"]])
        self.assertEqual(facts["merged_by_repo"]["repos"][:2],
                         [{"repo": "acme/api", "prs": 3}, {"repo": "acme/r0", "prs": 1}])
        self.assertEqual(
            (len(facts["repo_order"]), facts["merged_by_repo"]["other"]), (common.MAX_GROUPS, 3))
        self.assertEqual(facts["repo_counts"], {"opened": 13, "merged": 12})
        self.assertEqual(facts["merged_lines"], {"median": 600})
        # On a log scale, four bins to each power of ten up to 10,000, above
        # the largest, 2,000: 5 in the third, 10 ** 0.70, 80 in the eighth,
        # 150 in the ninth, 600 in the twelfth and 2,000 in the fourteenth.
        distribution = facts["lines_distribution"]
        self.assertEqual([(index, n) for index, n in enumerate(distribution["total"]) if n],
                         [(2, 1), (7, 1), (8, 1), (11, 10), (13, 1)])
        self.assertEqual(
            (len(distribution["total"]), sum(distribution["other"])), (16, 3))
        self.assertEqual(facts["merged_by_week"]["total"], [14])
        self.assertEqual(build_data.lines(
            [pull("a", 1), pull("a", 4)]), {"median": 2.5})
        self.assertEqual(build_data.lines([]), {"median": None})
        # A pull request of no lines, a rename, in the first bin; a power of
        # ten opens its decade.
        self.assertEqual(build_data.lines_distribution([pull("a", 0), pull("a", 10)], ["a"])["total"],
                         [1, 0, 0, 0, 1, 0, 0, 0])

    def test_pie(self):
        # name: (the resolved issues' epics, None for none, the pie's slices
        # as (key, issues), its other): the issues with no epic are one slice,
        # ranked by how many it holds, after the epics it ties with; the
        # epics beyond the MAX_GROUPS coloured are counted together as other.
        def issues(*epics):
            return [{"key": f"PROJ-{100 + n}", "type": "Task", "date": "2026-07-02", "points": None,
                     "epic": {"key": epic, "title": epic, "url": f"https://acme.test/{epic}"} if epic else None}
                    for n, epic in enumerate(epics)]
        many = [f"PROJ-{n}" for n in range(11, 22)]
        cases = [("no epic ranked first", issues("PROJ-1", None, None), [(None, 2), ("PROJ-1", 1)], 0),
                 ("no epic after a tie", issues("PROJ-1", None),
                  [("PROJ-1", 1), (None, 1)], 0),
                 ("epics beyond the coloured", issues(*many, *many[:3], None),
                  [*((key, 2) for key in many[:3]), *((key, 1) for key in [*many[3:9], None])], 2)]
        for name, resolved, slices, other in cases:
            with self.subTest(name):
                pie = build_data.source_facts("jira", {"created": [], "resolved": resolved},
                                              [["2026-07-01", "2026-07-05"]])["resolved_by_epic"]
                self.assertEqual(([(entry["key"], entry["issues"]) for entry in pie["epics"]], pie["other"]),
                                 (slices, other))

    def test_observations(self):
        # name: (the current manager feedback's going well, the other
        # feedback's, the notes' points going well, the values, (value, point)
        # of each going well, in order): a point under its first value, the
        # company's order, those naming none last; the most recent first, the
        # feedbacks, which have no date, first of all, the manager's before
        # the other's.
        def feedback(point, values):
            return {"point": point, "values": values}

        def note(day, point, values):
            return {"point": point, "values": values, "evidence": [{"date": day, "link": f"/{day}.md"}]}
        cases = [("first value only", [], [feedback("a", ["Teamwork", "Ownership"])], [],
                  ["Ownership", "Teamwork"], [("Teamwork", "a")]),
                 ("the company's order", [], [feedback("a", ["Teamwork"])],
                  [note("2026-08-01", "b", ["Ownership"])
                   ], ["Ownership", "Teamwork"],
                  [("Ownership", "b"), ("Teamwork", "a")]),
                 ("no value last", [], [feedback("a", [])], [note("2026-08-01", "b", ["Teamwork"])],
                  ["Ownership", "Teamwork"], [("Teamwork", "b"), (None, "a")]),
                 ("most recent first, undated first of all", [],
                  [feedback("a", ["Teamwork"])],
                  [note("2026-09-01", "c", ["Teamwork"]),
                   note("2026-08-15", "d", ["Teamwork"])], ["Teamwork"],
                  [("Teamwork", "a"), ("Teamwork", "c"), ("Teamwork", "d")]),
                 ("the manager's before the other's", [feedback("m", ["Teamwork"])], [feedback("a", ["Teamwork"])],
                  [note("2026-08-01", "b", ["Teamwork"])], ["Teamwork"],
                  [("Teamwork", "m"), ("Teamwork", "a"), ("Teamwork", "b")]),
                 ("the manager's with no value last", [feedback("m", [])], [feedback("a", ["Ownership"])], [],
                  ["Ownership", "Teamwork"], [("Ownership", "a"), (None, "m")])]
        for name, managers, others, notes, values, expected in cases:
            with self.subTest(name):
                summaries = {"manager": {"going_well": managers, "to_improve": [], "context": []},
                             "other": {"going_well": others, "to_improve": [], "context": []},
                             "notes": {"going_well": notes, "to_improve": [], "context": []},
                             "slack": {"going_well": [], "to_improve": [], "context": []}}
                groups = build_data.observations(
                    summaries, values)["going_well"]
                self.assertEqual([(group["value"], point["point"]) for group in groups for point in group["points"]],
                                 expected)

    def test_context(self):
        # name: (the current manager feedback's context points, the other
        # feedback's, the notes' context points, the context's points, in
        # order, each (point, source, date, the days of its evidence)): the
        # feedbacks' a sentence alone, undated; a reading's dated by its
        # latest dated evidence, a page's undated; the most recent first,
        # undated first of all, its evidence too.
        def note(point, *days):
            return {"point": point, "evidence": [{"date": day, "link": f"/vault/{day or 'pages/Jane'}.md"}
                                                 for day in days]}
        cases = [("the sentences of the other feedback", [], ["a", "b"], [],
                  [("a", "other", None, []), ("b", "other", None, [])]),
                 ("a page undated, after the other feedback", [], ["a"], [note("b", None)],
                  [("a", "other", None, []), ("b", "notes", None, [None])]),
                 ("dated by the latest dated evidence", [], ["a"], [note("b", "2026-08-01", None, "2026-10-02")],
                  [("a", "other", None, []), ("b", "notes", "2026-10-02", [None, "2026-10-02", "2026-08-01"])]),
                 ("the manager feedback's sentences first", ["m"], ["a"], [note("b", None)],
                  [("m", "manager", None, []), ("a", "other", None, []), ("b", "notes", None, [None])])]
        for name, managers, others, notes, expected in cases:
            with self.subTest(name):
                summaries = {"manager": {"going_well": [], "to_improve": [], "context": managers},
                             "other": {"going_well": [], "to_improve": [], "context": others},
                             "notes": {"going_well": [], "to_improve": [], "context": notes},
                             "slack": {"going_well": [], "to_improve": [], "context": []}}
                points = build_data.observations(summaries, [])["context"]
                self.assertEqual([(point["point"], point["source"], point["date"],
                                   [item["date"] for item in point["evidence"]]) for point in points], expected)

    def test_the_manager_feedback_is_a_source_of_every_part(self):
        # The current manager feedback's points, like the other feedback's,
        # carry their source, no date and no evidence in going well, to
        # improve and context alike.
        feedback = {"going_well": [{"point": "g", "values": []}], "to_improve": [{"point": "i", "values": []}],
                    "context": ["c"]}
        empty = {"going_well": [], "to_improve": [], "context": []}
        observed = build_data.observations(
            {"manager": feedback, "other": empty, "notes": empty, "slack": empty}, [])
        points = [point for part in ("going_well", "to_improve") for group in observed[part] for point in group["points"]
                  ] + observed["context"]
        self.assertEqual([(point["id"], point["point"], point["source"], point["date"], point["evidence"])
                          for point in points],
                         [("G1", "g", "manager", None, []), ("I1", "i", "manager", None, []),
                          ("C1", "c", "manager", None, [])])

    def test_baselines(self):
        # The previous feedback, which the step change compares with the
        # period: its points with ids by part and place, prefixed P-, a context
        # point's text alone; null when it has no points.
        empty = {"going_well": [], "to_improve": [], "context": []}
        feedback = {"going_well": [], "to_improve": [{"point": "b", "values": ["Teamwork"]}],
                    "context": ["b context"]}
        self.assertEqual(build_data.baseline_parts(feedback),
                         {"going_well": [], "to_improve": [{"id": "P-I1", "point": "b", "values": ["Teamwork"]}],
                          "context": [{"id": "P-C1", "point": "b context"}]})
        self.assertIsNone(build_data.baseline_parts(empty))

    def test_model_fixtures(self):
        # name: (a model the report's tests use, worked out by hand): its
        # Jira facts are those its items give.
        for name, data in (("no epic first", DATA_NO_EPIC_FIRST), ("by project", DATA_BY_PROJECT)):
            with self.subTest(name):
                jira = data["jira"]
                facts = build_data.source_facts("jira", {"created": jira["created"], "resolved": jira["resolved"]},
                                                WEEKS)
                self.assertEqual(
                    facts, {key: jira[key] for key in facts})

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

    def test_with_shares(self):
        # Each entry's count as a percentage of the total, rounded.
        self.assertEqual(build_data.with_shares([{"key": "a", "prs": 2}, {"key": "b", "prs": 1}], "prs", 3),
                         [{"key": "a", "prs": 2, "share": 67}, {"key": "b", "prs": 1, "share": 33}])

    def test_focus(self):
        # name: (parents of the resolved issues, by key, None for none, the
        # focus expected as (key, issues)): the fewest parents covering 80%
        # of the issues, those with none counted as one more, of key None,
        # those tied with the last one too; with no parent at all, the
        # projects.
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
                 ("no parent counted as one", issues(
                     "a", "a", None, None, None), [(None, 3), ("a", 2)]),
                 ("no parent after the epics it ties with", issues("a", "a", None, None), [("a", 2), (None, 2)])]
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
