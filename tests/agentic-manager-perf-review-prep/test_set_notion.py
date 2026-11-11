"""Unit tests for skills/agentic-manager-perf-review-prep/scripts/set_notion.py.
Run with: python3 tests/run.py agentic-manager-perf-review-prep
"""

import json
import os
import sys
import unittest

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(TEST_DIR))
sys.path.insert(0, os.path.join(REPO_ROOT, "skills",
                os.path.basename(TEST_DIR), "scripts"))
import set_notion  # noqa: E402
sys.path.insert(0, TEST_DIR)
from prep_fixture import IDENTITIES, PREP, REQUEST, temp_output, write_prep  # noqa: E402

PLAN = {"title": "Billing plan", "url": "https://www.notion.so/billing-plan"}
# REQUEST's period, 10/08/2026 to 10/11/2026: created pages a month at a
# time, edited ones in one search.
CREATED = [{"start": "2026-08-10", "end": "2026-08-31", "pages": [PLAN]},
           {"start": "2026-09-01", "end": "2026-09-30", "pages": []},
           {"start": "2026-10-01", "end": "2026-10-31", "pages": []},
           {"start": "2026-11-01", "end": "2026-11-10", "pages": []}]
EDITED = [{"start": "2026-08-10", "end": "2026-11-10",
           "pages": [{**PLAN, "date": "2026-09-02"}]}]


class SetNotionTest(unittest.TestCase):
    def setUp(self):
        self.folder = temp_output(self)
        write_prep(self.folder, notion=None)

    def test_writes_created_pages_with_their_range(self):
        path = set_notion.set_notion(
            PREP, {"created": CREATED, "edited": EDITED})
        with open(path, encoding="utf-8") as f:
            self.assertEqual(json.load(f), {"created": [{**PLAN, "between": ["2026-08-10", "2026-08-31"]}],
                                            "edited": [{**PLAN, "date": "2026-09-02"}]})

    def test_searches_problems(self):
        # name: (the searches, expected in their problems, or None for none).
        full = [{**PLAN, "url": f"https://www.notion.so/{n}"}
                for n in range(set_notion.SEARCH_LIMIT)]
        cases = [("valid", {"created": CREATED, "edited": EDITED}, None),
                 ("a gap", {"created": CREATED[:2] + CREATED[3:], "edited": EDITED},
                  "the created searches must cover 2026-08-10 to 2026-11-10 day by day"),
                 ("an overlap", {"created": CREATED, "edited": EDITED + [{**EDITED[0], "pages": []}]},
                  "the edited searches must cover"),
                 ("a full list", {"created": [{**CREATED[0], "pages": full}, *CREATED[1:]], "edited": EDITED},
                  "search that range again in shorter ranges"),
                 ("an edited page outside its range",
                  {"created": CREATED, "edited": [
                      {**EDITED[0], "pages": [{**PLAN, "date": "2026-12-01"}]}]},
                  "isn't dated within it"),
                 ("a created page found twice",
                  {"created": [CREATED[0], {
                      **CREATED[1], "pages": [PLAN]}, *CREATED[2:]], "edited": EDITED},
                  "found by two created searches, so the creation filter can't be trusted"),
                 ("a page without its url", {"created": CREATED, "edited": [
                     {**EDITED[0], "pages": [{"title": "Billing plan", "link": PLAN["url"], "date": "2026-09-02"}]}]},
                  "each page must be {\"title\", \"url\""),
                 ("not a day", {"created": [{**CREATED[0], "start": "10/08/2026"}, *CREATED[1:]], "edited": EDITED},
                  "must be days")]
        for name, found, expected in cases:
            with self.subTest(name):
                problems = set_notion.searches_problems(found, REQUEST)
                if expected is None:
                    self.assertEqual(problems, [])
                else:
                    self.assertIn(expected, " ".join(problems))

    def test_absent(self):
        # Absent only when the manager said the person isn't in Notion.
        with self.assertRaisesRegex(SystemExit, "must be searched"):
            set_notion.set_notion(PREP, {"absent": True})
        write_prep(self.folder, identities={
                   **IDENTITIES, "notion-mcp": {"absent": True}}, notion=None)
        with open(set_notion.set_notion(PREP, {"absent": True}), encoding="utf-8") as f:
            self.assertEqual(json.load(f), {"absent": True})


if __name__ == "__main__":
    unittest.main()
