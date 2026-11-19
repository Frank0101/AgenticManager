"""Unit tests for skills/agentic-manager-perf-review-prep/scripts/read_notion.py.
Run with: python3 tests/run.py agentic-manager-perf-review-prep

The task lists each week's exact search arguments, worked out from the
period and the person's Notion id in person.json, never read from the config.
"""

import json
import os
import sys
import tempfile
import unittest

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(TEST_DIR))
sys.path.insert(0, os.path.join(REPO_ROOT, "skills",
                os.path.basename(TEST_DIR), "scripts"))
import common  # noqa: E402
import read_notion  # noqa: E402
sys.path.insert(0, TEST_DIR)
from prep_fixture import PERSON, PREP, temp_output, write_prep  # noqa: E402

NOTION_ID = PERSON["sources"]["notion-mcp"]["id"]


def line(first, last):
    """The line of the week from `first` to `last`, as the task lists it."""
    arguments = {"query": "", "filters": {"created_by_user_ids": [NOTION_ID],
                                          "created_date_range": {"start_date": first, "end_date": last}},
                 "page_size": 50, "max_highlight_length": 0}
    return f"- {first} to {last}: `{json.dumps(arguments)}`"


class ReadNotionTest(unittest.TestCase):
    def setUp(self):
        self.folder = temp_output(self)
        write_prep(self.folder)

    def test_a_line_for_each_week_to_copy(self):
        # name: (the period, its weeks): one line for each calendar week,
        # Monday to Sunday, the first and last clipped to the period, each
        # with an empty query, the person's id, the week's range, a page
        # size of 50 and no highlights.
        cases = [("a Wednesday to a Monday", "2026-07-01", "2026-07-20",
                  [("2026-07-01", "2026-07-05"), ("2026-07-06", "2026-07-12"), ("2026-07-13", "2026-07-19"),
                   ("2026-07-20", "2026-07-20")]),
                 ("inside one week", "2026-07-07",
                  "2026-07-09", [("2026-07-07", "2026-07-09")]),
                 ("the fixture's period", "2026-08-10", "2026-11-10",
                  [("2026-08-10", "2026-08-16")] + [(f"{common.calendar_weeks('2026-08-17', '2026-11-08')[n][0]}",
                                                     f"{common.calendar_weeks('2026-08-17', '2026-11-08')[n][1]}")
                                                    for n in range(12)] + [("2026-11-09", "2026-11-10")])]
        for name, start, end, weeks in cases:
            with self.subTest(name):
                person = {**PERSON, "start": start, "end": end}
                self.assertEqual(read_notion.search_lines(person), [
                                 line(first, last) for first, last in weeks])

    def test_the_id_comes_from_the_person(self):
        person = {**PERSON, "sources": {**
                                        PERSON["sources"], "notion-mcp": {"id": "9f8e-acme", "name": "Jane Doe"}}}
        self.assertIn(
            '"created_by_user_ids": ["9f8e-acme"]', read_notion.search_lines(person)[0])
        self.assertNotIn(NOTION_ID, " ".join(read_notion.search_lines(person)))

    def test_start_writes_the_task(self):
        # The task is in the working folder, with the protocol filled, the
        # person, every week's line and how to record the searches.
        started = read_notion.start(PREP)
        name, path = started["task"].split(": ", 1)
        self.assertEqual((name, path), ("Task notion", os.path.join(
            tempfile.gettempdir(), "perf-review-preps", "Jane-Doe_26-11-10", "notion", "task.md")))
        self.assertEqual(started["searches"], len(
            common.calendar_weeks("2026-08-10", "2026-11-10")))
        with open(path, encoding="utf-8") as f:
            task = f.read()
        self.assertNotIn("{{", task)
        for expected in ("# Find the Notion pages a person created", "## The person\n\nJane Doe",
                         "any query text makes Notion silently drop pages", "last edit, not its creation",
                         "fewer than 50", '"full": true', line(
                             "2026-08-10", "2026-08-16"),
                         line("2026-11-09", "2026-11-10"), "set_notion.py --prep Jane-Doe_26-11-10 <<'END_OF_INPUT'"):
            self.assertIn(expected, task)
        self.assertEqual(task.count("\n- 2026-"), started["searches"])


if __name__ == "__main__":
    unittest.main()
