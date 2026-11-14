"""Unit tests for skills/agentic-manager-perf-review-prep/scripts/set_notion.py.
Run with: python3 tests/run.py agentic-manager-perf-review-prep
"""

import json
from datetime import date, timedelta
import os
import sys
import unittest

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(TEST_DIR))
sys.path.insert(0, os.path.join(REPO_ROOT, "skills",
                os.path.basename(TEST_DIR), "scripts"))
import set_notion  # noqa: E402
sys.path.insert(0, TEST_DIR)
from prep_fixture import PERSON, PREP, WORK, WORK_ITEMS, temp_output, write_prep  # noqa: E402

PLAN = {"title": "Billing plan", "url": "https://www.notion.so/billing-plan",
        "path": "Engineering / Billing"}
# PERSON's period, 10/08/2026, a Monday, to 10/11/2026, a week at a time,
# the last of two days.
CREATED = [{"start": (monday := date(2026, 8, 10) + timedelta(weeks=n)).isoformat(),
            "end": min(monday + timedelta(days=6), date(2026, 11, 10)).isoformat(), "pages": [PLAN] if n == 0 else []}
           for n in range(14)]


class SetNotionTest(unittest.TestCase):
    def setUp(self):
        self.folder = temp_output(self)
        write_prep(self.folder, work=WORK)

    def test_writes_created_pages_with_their_range(self):
        # Into Notion's raw file, then work.json, built from it and Jira's
        # and GitHub's, already in.
        paths = set_notion.set_notion(
            PREP, {"created": CREATED})
        with open(paths["raw"], encoding="utf-8") as f:
            self.assertEqual(json.load(f), WORK_ITEMS["notion"])
        with open(paths["work"], encoding="utf-8") as f:
            self.assertEqual(json.load(f), WORK)

    def test_searches_problems(self):
        # name: (the searches, expected in their problems, or None for none).
        full = [{**PLAN, "url": f"https://www.notion.so/{n}"}
                for n in range(set_notion.SEARCH_LIMIT)]
        cases = [("valid", {"created": CREATED}, None),
                 ("a gap", {"created": CREATED[:2] + CREATED[3:]},
                  "the searches must cover 2026-08-10 to 2026-11-10 day by day"),
                 ("an overlap", {"created": CREATED + [{**CREATED[1], "pages": []}]},
                  "the searches must cover"),
                 ("a full list", {"created": [{**CREATED[0], "pages": full}, *CREATED[1:]]},
                  "search that range again in shorter ranges"),
                 ("a created page found twice",
                  {"created": [CREATED[0], {
                      **CREATED[1], "pages": [PLAN]}, *CREATED[2:]]},
                  "found by two searches, so the creation filter can't be trusted"),
                 ("a page without its url", {"created": [
                     {**CREATED[0], "pages": [{"title": "Billing plan", "link": PLAN["url"], "path": ""}]}, *CREATED[1:]]},
                  "each page must be {\"title\", \"url\", \"path\"}"),
                 ("a month at once", {"created": [{**CREATED[0], "end": "2026-09-06"}, *CREATED[4:]]},
                  "spans more than a calendar week"),
                 ("a single day still full", {"created": [
                     {"start": "2026-08-10", "end": "2026-08-10",
                         "pages": [PLAN], "full": True},
                     {**CREATED[0], "start": "2026-08-11", "pages": []}, *CREATED[1:]]}, None),
                 ("full over more than a day", {"created": [
                  {**CREATED[0], "full": True}, *CREATED[1:]], }, "only a search of a single day may be"),
                 ("not a day", {"created": [{**CREATED[0], "start": "10/08/2026"}, *CREATED[1:]]},
                  "must be days")]
        for name, found, expected in cases:
            with self.subTest(name):
                problems = set_notion.searches_problems(
                    found, set_notion.period_days(PERSON))
                if expected is None:
                    self.assertEqual(problems, [])
                else:
                    self.assertIn(expected, " ".join(problems))


if __name__ == "__main__":
    unittest.main()
