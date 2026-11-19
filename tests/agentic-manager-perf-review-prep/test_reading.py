"""Unit tests for skills/agentic-manager-perf-review-prep/scripts/reading.py.
Its flow, start to submit, is tested through each source, in
test_read_notes.py and test_read_slack.py.
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
import read_notes  # noqa: E402
import read_slack  # noqa: E402
import reading  # noqa: E402
sys.path.insert(0, TEST_DIR)
from prep_fixture import SLACK_ITEM, temp_output  # noqa: E402

SOURCES = {"notes": read_notes.SOURCE, "slack": read_slack.SOURCE}
DAYS = ["2026-08-20"]
# The items of a reading of notes: a note of the period, and a page, which has no day.
ITEMS = [{"number": 1, "date": "2026-08-20", "link": "/vault/journals/2026_08_20.md", "text": "- note"},
         {"number": 2, "date": None, "link": "/vault/pages/Jane.md", "text": "- page", "page": "Jane"}]
PARTS = {"going_well": [{"point": "Presented the migration to the team", "values": ["Teamwork"], "cites": [1]}],
         "to_improve": [], "context": [{"point": "Moved to the payments team", "cites": [2]}]}


class ReadingTest(unittest.TestCase):
    def setUp(self):
        temp_output(self)

    def test_listed_items_problems(self):
        # name: (the items, expected in its problems, or None for none)
        cases = [("valid", [SLACK_ITEM], None),
                 ("a description at the hidden limit", [{**SLACK_ITEM, "description": "word " * common.MAX_DESCRIPTION_WORDS}],
                  None),
                 ("a description past the told words but within the limit",
                  [{**SLACK_ITEM, "description": "word " * (common.DESCRIPTION_WORDS + 1)}], None),
                 ("nothing found", [], None),
                 ("not a list", {"items": []}, 'must hold "items"'),
                 ("a field missing", [{"date": "2026-08-20", "link": SLACK_ITEM["link"]}],
                  "must have the fields date, link, description"),
                 ("another day", [{**SLACK_ITEM, "date": "2026-09-01"}],
                  "must be the day of what it comes from"),
                 ("no link", [{**SLACK_ITEM, "link": None}],
                  "link, None, must be the address"),
                 ("blank", [{**SLACK_ITEM, "description": " "}],
                  "description must be a text"),
                 ("too long", [{**SLACK_ITEM, "description": "word " * (common.MAX_DESCRIPTION_WORDS + 1)}],
                  f"keep it to up to {common.DESCRIPTION_WORDS}"),
                 ("a link twice", [SLACK_ITEM, SLACK_ITEM], "listed more than once")]
        for name, items, expected in cases:
            with self.subTest(name):
                problems = reading.listed_items_problems(items, DAYS)
                if expected is None:
                    self.assertEqual(problems, [])
                else:
                    self.assertIn(expected, " ".join(problems))

    def test_answer_problems(self):
        # name: (changes to the parts, expected in its problems, or None for
        # none): the points of notes, citing numbers from 1 of the items, a
        # page's undated, so it can back only context.
        cases = [("valid", {}, None),
                 ("nothing to keep", {"going_well": [], "context": []}, None),
                 ("not parts", None, "must have the parts"),
                 ("no cites", {"going_well": [
                  {"point": "Presented", "values": []}]}, "must be a list of points"),
                 ("cites nothing", {"going_well": [{"point": "Presented", "values": [], "cites": []}]},
                  "must be a list of points"),
                 ("a number twice", {"going_well": [{"point": "Presented", "values": [], "cites": [1, 1]}]},
                  "must be a list of points"),
                 ("a number that isn't there", {"going_well": [{"point": "Presented", "values": [], "cites": [3]}]},
                  "must each be the number of what it rests on, 1 to 2"),
                 ("a page backing going well", {"going_well": [{"point": "Presented", "values": [], "cites": [2]}]},
                  "must each be of a day the source was read on"),
                 ("a value that isn't the company's",
                  {"going_well": [{"point": "Presented", "values": ["Kindness"], "cites": [1]}]}, "must each be one of the company's"),
                 ("a point too long", {"context": [{"point": "word " * (common.MAX_POINT_WORDS + 1), "cites": [1]}]},
                  f"sentence of up to {common.POINT_WORDS}")]
        for name, changes, expected in cases:
            with self.subTest(name):
                parts = None if changes is None else {**PARTS, **changes}
                problems = reading.answer_problems(
                    read_notes.SOURCE, parts, ITEMS, DAYS)
                if expected is None:
                    self.assertEqual(problems, [])
                else:
                    self.assertIn(expected, " ".join(problems))

    def test_with_evidence_and_order(self):
        # Each cite becomes its item's day and link, and the most recent
        # comes first, the undated, a page's, before all.
        parts = {"going_well": [], "to_improve": [],
                 "context": [{"point": "Moved to the payments team", "cites": [1, 2]}]}
        self.assertEqual(reading.order(reading.with_evidence(parts, ITEMS))["context"],
                         [{"point": "Moved to the payments team", "evidence": [
                             {"date": None, "link": "/vault/pages/Jane.md"},
                             {"date": "2026-08-20", "link": "/vault/journals/2026_08_20.md"}]}])

    def test_order_ranks_points_by_their_latest_dated_evidence(self):
        # A page has no day, so a point it backs ranks by its dated evidence,
        # as build_data ranks it; only a point with none dated comes first.
        page = {"date": None, "link": "/vault/pages/Jane.md"}

        def note(day):
            return {"date": day, "link": f"/vault/journals/{day}.md"}
        # name: ({point: its evidence}, in the order given, the points expected in order)
        cases = [("a page and an older note rank by the note",
                  {"page and old note": [page, note(
                      "2026-08-10")], "newer note": [note("2026-08-20")]},
                  ["newer note", "page and old note"]),
                 ("a page alone ranks first",
                  {"note": [note("2026-08-20")], "page": [page]}, ["page", "note"]),
                 ("the latest of several dated",
                  {"one": [note("2026-08-15")], "two": [note("2026-08-01"), note("2026-08-25")]}, ["two", "one"]),
                 ("as recent keep the order given",
                  {"first": [note("2026-08-20")], "second": [note("2026-08-20")]}, ["first", "second"])]
        for name, points, expected in cases:
            with self.subTest(name):
                summary = {"going_well": [], "to_improve": [],
                           "context": [{"point": point, "evidence": evidence} for point, evidence in points.items()]}
                self.assertEqual(
                    [point["point"] for point in reading.order(summary)["context"]], expected)

    def test_two_notes_of_one_day_cite_their_link_once(self):
        items = [{"number": 1, "date": "2026-08-20", "link": "/vault/j.md"},
                 {"number": 2, "date": "2026-08-20", "link": "/vault/j.md"}]
        parts = {"going_well": [{"point": "Presented", "values": [
        ], "cites": [1, 2]}], "to_improve": [], "context": []}
        self.assertEqual(reading.with_evidence(parts, items)["going_well"][0]["evidence"],
                         [{"date": "2026-08-20", "link": "/vault/j.md"}])

    def test_every_protocol_file_is_filled(self):
        # A placeholder nothing fills would reach a subagent as {{name}}; the
        # shared rules on people and on saying a fact once reach every task.
        for name in ("notes-judge", "slack-judge", "slack-reader"):
            with self.subTest(name):
                text = reading.read_protocol(
                    name, SOURCES[name.split("-")[0]].terms)
                self.assertNotIn("{{", text)
                self.assertIn('never "he", "she"', text)
                # The words a task is told are a target; the limit the check
                # applies is a margin the agent never sees.
                told, hidden = (common.DESCRIPTION_WORDS, common.MAX_DESCRIPTION_WORDS) if name == "slack-reader" \
                    else (common.POINT_WORDS, common.MAX_POINT_WORDS)
                self.assertIn(f"up to {told} words", text)
                self.assertNotIn(str(hidden), text)
                if name == "slack-reader":
                    # A reader lists, and is inclusive: no points, no merge rules,
                    # and no count of reactions, which a search doesn't show.
                    self.assertNotIn("cites", text)
                    self.assertNotIn("reactions", text)
                    self.assertNotIn(str(common.POINT_WORDS), text)
                    continue
                self.assertIn("never one per mention", text)
                # What both sources share is said once, in a shared part, with
                # the source's own words in it.
                cited = SOURCES[name.split("-")[0]].terms["cited"]
                for expected in (f"the numbers of the {cited} it rests on", "submit every part empty"):
                    self.assertEqual(text.count(expected), 1, expected)
                # The citing is said once, by its part, not by the task's too.
                self.assertEqual(text.count(f"it rests on"), 1)

    def test_headings_never_skip_a_level_and_examples_come_last(self):
        # A part embedded in a protocol keeps the levels below the heading it
        # sits under, and a section's examples come after its rules, so the
        # Links of a task come before its Examples.
        import re
        for name in ("notes-judge", "slack-judge", "slack-reader", "feedback"):
            with self.subTest(name):
                source = SOURCES.get(name.split("-")[0], read_notes.SOURCE)
                text = reading.read_protocol(name, source.terms)
                levels = [len(found)
                          for found in re.findall(r"^(#+) ", text, re.M)]
                self.assertEqual(levels[0], 1)
                for before, after in zip(levels, levels[1:]):
                    self.assertLessEqual(after, before + 1, name)
        for name in ("notes-judge", "slack-reader"):
            with self.subTest(name + " links"):
                text = reading.read_protocol(
                    name, SOURCES[name.split("-")[0]].terms)
                self.assertLess(text.index("\n## Links\n"),
                                text.index("\n## Examples\n"))

    def test_input_help_shows_the_answer_and_a_command_to_copy(self):
        for source in (read_notes.SOURCE, read_slack.SOURCE):
            with self.subTest(source.name):
                text = reading.input_help(source)
                for expected in (f"python3 {source.script} submit --prep Jane-Doe_26-11-10 <<'END_OF_INPUT'",
                                 "END_OF_INPUT", '"cites"', "going_well  what is going well"):
                    self.assertIn(expected, text)
        # A part's input is shown with its own command, the task named.
        part = reading.input_help(read_slack.SOURCE, "month:2026-09")
        self.assertIn(
            "submit --prep Jane-Doe_26-11-10 --task month:2026-09 <<'END_OF_INPUT'", part)
        self.assertIn('"searched"', part)
        self.assertNotIn('"cites"', part)


if __name__ == "__main__":
    unittest.main()
