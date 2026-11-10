"""Unit tests for skills/agentic-manager-perf-review-prep/scripts/common.py.
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
import common  # noqa: E402
sys.path.insert(0, TEST_DIR)
from prep_fixture import IDENTITIES, ORIENTATION, PREP, REQUEST, REVIEW, temp_output, write_prep  # noqa: E402

TODAY = date(2026, 11, 10)


class CommonTest(unittest.TestCase):
    def test_request_problems(self):
        # name: (changes to the request, or a value instead of it, expected
        # in its problems, or None for none)
        cases = [("valid", {}, None),
                 ("one day", {"start": "2026-11-10"}, None),
                 ("not an object", ["Jane Doe"], "must be a JSON object"),
                 ("a field missing", {"end": None},
                  "fields must be person, start, end"),
                 ("a field more", {
                  "shown": "10/08/2026 to 10/11/2026"}, "fields must be person, start, end"),
                 ("no name", {"person": " "}, "must name the person"),
                 ("a name that isn't text", {
                  "person": 7}, "must name the person"),
                 ("not a date", {"start": "10/08/2026"},
                  "must be a date as YYYY-MM-DD"),
                 ("ends after today", {"end": "2026-12-31"}, "after today"),
                 ("starts after it ends", {"start": "2026-11-10", "end": "2026-08-10"}, "after it ends")]
        for name, change, expected in cases:
            with self.subTest(name):
                request = change if isinstance(change, list) else {
                    k: v for k, v in {**REQUEST, **change}.items() if v is not None}
                problems = common.request_problems(request, TODAY)
                if expected is None:
                    self.assertEqual(problems, [])
                else:
                    self.assertIn(expected, " ".join(problems))

    def test_identities_problems(self):
        # name: (changes to the identities, or a value instead of them,
        # expected in their problems, or None for none)
        cases = [("valid", {}, None),
                 ("absent everywhere", {source: {"absent": True}
                  for source in IDENTITIES}, None),
                 ("not an object", ["janedoe"], "must be a JSON object"),
                 ("a source missing", {"slack-mcp": None},
                  "must be those of jira-api"),
                 ("a source more", {
                  "confluence-mcp": {"absent": True}}, "must be those of jira-api"),
                 ("no name", {"github-cli": {"id": "janedoe"}},
                  'github-cli must be {"id": "...", "name": "..."}'),
                 ("a blank id", {"jira-api": {"id": " ",
                  "name": "Jane Doe"}}, "jira-api must be"),
                 ("absent false", {
                  "notion-mcp": {"absent": False}}, "notion-mcp must be"),
                 ("no links", {"logseq-fs": {"links": []}},
                  'logseq-fs must be {"links": ["...", ...]}'),
                 ("a blank link", {
                  "logseq-fs": {"links": ["Jane", " "]}}, "logseq-fs must be"),
                 ("a link twice", {
                  "logseq-fs": {"links": ["Jane", "Jane"]}}, "logseq-fs must be"),
                 ("links that aren't a list", {
                  "logseq-fs": {"links": "Jane"}}, "logseq-fs must be"),
                 ("an id for the vault", {"logseq-fs": {"id": "Jane", "name": "Jane"}}, "logseq-fs must be")]
        for name, change, expected in cases:
            with self.subTest(name):
                identities = change if isinstance(change, list) else {
                    k: v for k, v in {**IDENTITIES, **change}.items() if v is not None}
                problems = common.identities_problems(identities)
                if expected is None:
                    self.assertEqual(problems, [])
                else:
                    self.assertIn(expected, " ".join(problems))

    def test_summary_problems(self):
        # name: (changes to the summary, or a value instead of it, expected in
        # its problems, or None for none)
        long_point = " ".join(["word"] * (common.MAX_POINT_WORDS + 1))
        cases = [("valid", {}, None),
                 ("parts left empty", {"to_improve": [], "context": []}, None),
                 ("a point at the limit", {"context": [
                  " ".join(["word"] * common.MAX_POINT_WORDS)]}, None),
                 ("no points", {"going_well": [], "to_improve": [],
                  "context": []}, "has no points"),
                 ("a part missing", {
                  "context": None}, "must have the parts going_well, to_improve, context"),
                 ("not an object", "Strong half overall.", "must have the parts"),
                 ("text, not a list", {
                  "going_well": "Strong half"}, "going_well must be a list of points"),
                 ("a blank point", {"to_improve": [
                  " "]}, "to_improve must be a list of points"),
                 ("a point twice", {"context": [
                  "Back in May", "Back in May"]}, "more than once"),
                 ("a point too long", {"going_well": [long_point]}, f"at most {common.MAX_POINT_WORDS}")]
        for name, changes, expected in cases:
            with self.subTest(name):
                summary = {key: value for key, value in {**ORIENTATION, **changes}.items() if value is not None} \
                    if isinstance(changes, dict) else changes
                problems = common.summary_problems(summary, "the orientation")
                if expected is None:
                    self.assertEqual(problems, [])
                else:
                    self.assertIn(expected, " ".join(problems))
        # The orientation is a summary, by the same rule.
        self.assertEqual(common.orientation_problems(ORIENTATION), [])

    def test_earliest_review_end(self):
        # Two years before the period starts; a 29 February has none, so the
        # 28th.
        for start, expected in [("2026-08-10", date(2024, 8, 10)), ("2028-02-29", date(2026, 2, 28))]:
            with self.subTest(start):
                self.assertEqual(common.earliest_review_end(
                    {**REQUEST, "start": start}), expected)

    def test_feedback_problems(self):
        # name: (the feedback, expected in its problems, or None for none).
        # REQUEST starts on 10/08/2026, so dated feedback may end from
        # 10/08/2024 to its end, 10/11/2026.
        ratings = ["Below", "Meets", "Exceeds"]
        undated = {**REVIEW, "start": None, "end": None, "rating": None}
        cases = [("one review", [REVIEW], None), ("none", [], None),
                 ("no days and no rating", [undated], None),
                 ("only an end day", [{**undated, "end": "2026-06-30"}], None),
                 ("only a start day", [
                  {**undated, "start": "2026-01-01"}], None),
                 ("only an end day, too old", [
                  {**undated, "end": "2024-08-09"}], "ends on 09/08/2024"),
                 ("two undated", [
                  undated, {**undated, "going_well": ["Mentors new joiners"]}], None),
                 ("ending on the first day allowed", [
                  {**REVIEW, "start": "2024-01-01", "end": "2024-08-10"}], None),
                 ("ending inside the period", [
                  {**REVIEW, "end": "2026-09-30"}], None),
                 ("too old", [{**REVIEW, "start": "2024-01-01", "end": "2024-08-09"}],
                  "ends on 09/08/2024: only feedback that ends from 10/08/2024 to 10/11/2026 counts"),
                 ("ending after the period", [
                  {**REVIEW, "end": "2026-12-31"}], "ends on 31/12/2026"),
                 ("starting after it ends", [
                  {**REVIEW, "start": "2026-07-01"}], "starts after it ends"),
                 ("not a date", [{**REVIEW, "end": "30/06/2026"}],
                  "must be a date as YYYY-MM-DD"),
                 ("a rating not the company's", [{**REVIEW, "rating": "Good"}],
                  "'Good', must be one of the company's: Below, Meets, Exceeds, or null"),
                 ("a field missing", [
                  {k: v for k, v in REVIEW.items() if k != "rating"}], "must have the fields"),
                 ("a summary that breaks a rule", [{**REVIEW, "going_well": [], "to_improve": []}],
                  "feedback 1 has no points"),
                 ("the same period twice", [REVIEW, {**REVIEW, "rating": "Exceeds"}], "record each once")]
        for name, reviews, expected in cases:
            with self.subTest(name):
                problems = common.feedback_problems(
                    {"reviews": reviews}, REQUEST, ratings)
                if expected is None:
                    self.assertEqual(problems, [])
                else:
                    self.assertIn(expected, " ".join(problems))
        for name, feedback in [("a list", [REVIEW]), ("a field more", {"reviews": [], "notes": "x"})]:
            with self.subTest(name):
                self.assertIn('must be {"reviews": [...]}',
                              " ".join(common.feedback_problems(feedback, REQUEST, ratings)))

    def test_prep_dir(self):
        folder = temp_output(self)
        write_prep(folder)
        self.assertEqual(common.prep_dir(PREP), os.path.join(folder, PREP))
        # name: (prep, expected in the message)
        cases = [("not a prep folder", "Jane-Doe", "not a prep folder"),
                 ("outside the output folder",
                  "../Jane-Doe_26-11-10", "inside the output folder"),
                 ("not there", "John-Doe_26-11-10", "run init_prep.py first")]
        for name, prep, expected in cases:
            with self.subTest(name), self.assertRaisesRegex(SystemExit, expected):
                common.prep_dir(prep)


if __name__ == "__main__":
    unittest.main()
