"""Unit tests for skills/agentic-manager-perf-review-prep/scripts/read_slack.py.
The flow every reading shares is tested in test_read_notes.py; here, what is
Slack's: its months, its tasks and the links on every item and point.
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
import read_slack  # noqa: E402
import reading  # noqa: E402
sys.path.insert(0, TEST_DIR)
from prep_fixture import PREP, temp_output, write_prep  # noqa: E402

LINK = "https://acme.slack.com/archives/C1/p1"
ITEM = {"date": "2026-08-20", "link": LINK,
        "synopsis": "In a cross-team channel, posted the billing rollout plan; three people asked follow-ups"}
POINT = "Posted the billing rollout plan in a cross-team channel"


class ReadSlackTest(unittest.TestCase):
    def setUp(self):
        self.folder = temp_output(self)
        write_prep(self.folder, slack=None)

    def test_runs_the_months_then_merges(self):
        # A task a month with its searches bounded; every item linked; the
        # merge links every point, context too.
        started = reading.start(read_slack.SOURCE, PREP)
        self.assertEqual([line.split(": ")[0] for line in started["tasks"]],
                         ["Task month:2026-08", "Task month:2026-09", "Task month:2026-10", "Task month:2026-11"])
        with open(started["tasks"][0].split(": ", 1)[1], encoding="utf-8") as f:
            task = f.read()
        for expected in ("# Read a month of a person's Slack messages", "From 2026-08-10 to 2026-08-31",
                         "`from:<@U012AB3CD> after:2026-08-09 before:2026-09-01`", "exclude the day they name", "search the days one didn't reach again", "submit --prep Jane-Doe_26-11-10"):
            self.assertIn(expected, task)
        with self.assertRaisesRegex(SystemExit, "link, None, must be the address(.|\n)*The answer's shape"):
            reading.submit(read_slack.SOURCE, PREP, "month:2026-08",
                           {"items": [{**ITEM, "link": None}]})
        for month in ("2026-08", "2026-09", "2026-10", "2026-11"):
            reading.submit(read_slack.SOURCE, PREP, f"month:{month}",
                           {"items": [ITEM] if month == "2026-08" else []})
        with open(started["merge"].split(": ", 1)[1], encoding="utf-8") as f:
            self.assertIn(json.dumps(ITEM, ensure_ascii=False), f.read())
        summary = {"going_well": [], "to_improve": [],
                   "context": [{"point": POINT, "dates": ["2026-08-20"], "links": [LINK]}]}
        with self.assertRaisesRegex(SystemExit, "context must be a list of points"):
            reading.submit(read_slack.SOURCE,
                           PREP, "merge", {**summary, "context": [POINT], "in_doubt": []})
        reading.submit(read_slack.SOURCE, PREP, "merge",
                       {**summary, "in_doubt": []})
        done = reading.finished(read_slack.SOURCE, PREP)
        with open(done["slack"], encoding="utf-8") as f:
            self.assertEqual(json.load(f), summary)


if __name__ == "__main__":
    unittest.main()
