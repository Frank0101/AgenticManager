"""Unit tests for skills/agentic-manager-perf-review-prep/scripts/check_prep.py.
Run with: python3 tests/run.py agentic-manager-perf-review-prep
"""

import os
import sys
import unittest
from datetime import date

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(TEST_DIR))
sys.path.insert(0, os.path.join(REPO_ROOT, "skills",
                os.path.basename(TEST_DIR), "scripts"))
import check_prep  # noqa: E402
sys.path.insert(0, TEST_DIR)
from prep_fixture import (FEEDBACK, REVIEWS, NOTE, NOTES, ORIENTATION, PERSON, PIECE, PREP,
                          SLACK, WORK, temp_output, write_prep)  # noqa: E402

TODAY = date(2026, 11, 10)


class CheckTest(unittest.TestCase):
    def setUp(self):
        self.folder = temp_output(self)

    def test_a_prep_the_scripts_wrote_passes(self):
        write_prep(self.folder)
        # Names starting with a dot, such as .DS_Store, aren't the prep's.
        open(os.path.join(self.folder, PREP, ".DS_Store"), "w").close()
        self.assertEqual(check_prep.check_prep(
            PREP, today=TODAY), {"ok": True, "errors": []})

    def test_failures(self):
        # name: (changes to the prep's files, by write_prep()'s arguments,
        # each None when missing, extra file, expected in the errors)
        cases = [("a file more", {}, "notes.md", "move notes.md to your own scratch folder"),
                 ("no person", {"person": None},
                  None, "missing person.json"),
                 ("no orientation", {"orientation": None},
                  None, "missing orientation.json"),
                 ("no reviews", {"reviews": None},
                  None, "missing reviews.json"),
                 ("no feedback", {"feedback": None},
                  None, "missing feedback.json"),
                 ("no notes", {"notes": None}, None, "missing notes.json"),
                 ("no Slack summary", {"slack": None},
                  None, "missing slack.json"),
                 ("a period that breaks a rule", {"person": {**PERSON, "end": "2026-12-31"}}, None,
                  "person.json: the period ends on 31/12/2026"),
                 ("only the source of step 1", {"person": {**PERSON, "sources": {
                     "jira-api": PERSON["sources"]["jira-api"]}}},
                  None, "person.json: the sources must be jira-api, github-cli, notion-mcp, slack-mcp, logseq-fs"),
                 ("a source that breaks a rule", {"person": {**PERSON, "sources": {
                     **PERSON["sources"], "slack-mcp": {}}}}, None, "person.json: slack-mcp must be"),
                 ("an orientation that breaks a rule", {"orientation": {"text": "Strong"}}, None,
                  "orientation.json: the orientation must have the parts"),
                 ("reviews that break a rule", {"reviews": {"pieces": [{**PIECE, "rating": "Good"}]}}, None,
                  "reviews.json: review 1's rating, 'Good', must be one of the company's"),
                 ("feedback that breaks a rule", {"feedback": {"pieces": [{**NOTE, "period": ""}]}},
                  None, "feedback.json: feedback piece 1's period, '', must be a text"),
                 ("notes dated outside the period", {"notes": {**NOTES, "going_well": [
                     {**NOTES["going_well"][0], "dates": ["2026-06-30"]}]}},
                  None, "notes.json: the notes summary's going_well"),
                 ("no work", {"work": None}, None, "missing work.json"),
                 ("work dated outside the period", {"work": {**WORK, "jira": {**WORK["jira"], "resolved": [
                     {**WORK["jira"]["resolved"][0], "date": "2026-07-01"}]}}},
                  None, "work.json: the work's jira resolved"),
                 ("Notion pages twice", {"work": {**WORK, "notion": {**WORK["notion"],
                                                                     "edited": WORK["notion"]["edited"] * 2}}},
                  None, "work.json: the work's notion edited lists"),
                 ("facts that don't match the items", {"work": {**WORK, "facts": {**WORK["facts"], "github": {}}}},
                  None, "work.json: the work's facts don't match its items"),
                 ("no commentary", {"work": {k: v for k, v in WORK.items() if k != "commentary"}},
                  None, "work.json: the work is missing commentary"),
                 ("a source with no commentary", {"work": {**WORK, "commentary": {**WORK["commentary"],
                                                                                  "github": None}}},
                  None, "work.json: the commentary's github must be a paragraph"),
                 ("a Slack point with no link", {"slack": {**SLACK, "going_well": [
                     {**SLACK["going_well"][0], "links": []}]}},
                  None, "slack.json: the Slack summary's going_well must be a list of points")]
        for i, (name, changes, extra, expected) in enumerate(cases):
            with self.subTest(name):
                prep = f"Case-{i}_26-11-10"
                files = {"person": PERSON, "orientation": ORIENTATION,
                         "reviews": REVIEWS, "feedback": FEEDBACK, "notes": NOTES, "work": WORK, "slack": SLACK,
                         **changes}
                write_prep(self.folder, prep=prep, **files)
                if extra:
                    open(os.path.join(self.folder, prep, extra), "w").close()
                result = check_prep.check_prep(prep, today=TODAY)
                self.assertFalse(result["ok"])
                self.assertIn(expected, " ".join(result["errors"]))


if __name__ == "__main__":
    unittest.main()
