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
from prep_fixture import IDENTITIES, NOTE, NOTES, ORIENTATION, PIECE, PREP, REQUEST, temp_output, write_prep  # noqa: E402

TODAY = date(2026, 11, 10)
VALUE_NAMES = ["Ownership", "Teamwork"]


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
                 ("a blank point", {"to_improve": [{"point": " ", "value": None}]},
                  'to_improve must be a list of points, each {"point": "...", "value": "..." or null}'),
                 ("a point twice", {"context": [
                  "Back in May", "Back in May"]}, "more than once"),
                 ("a valued point twice", {"going_well": [{"point": "Led it", "value": "Ownership"},
                                                          {"point": "Led it", "value": None}]}, "more than once"),
                 ("a point too long", {"going_well": [{"point": long_point, "value": None}]},
                  f"at most {common.MAX_POINT_WORDS}"),
                 ("a value left out", {"going_well": [
                  {"point": "Led it", "value": None}]}, None),
                 ("a value not the company's", {"going_well": [{"point": "Led it", "value": "Grit"}]},
                  "'Grit', must be one of the company's: Ownership, Teamwork, or null when none fits"),
                 ("a value's field missing", {"going_well": [{"point": "Led it"}]},
                  "going_well must be a list of points"),
                 ("text where a value is due", {
                  "to_improve": ["Could share more"]}, "to_improve must be a list of points"),
                 ("a value on context", {"context": [{"point": "Back in May", "value": None}]},
                  "context must be a list of points, each a sentence")]
        for name, changes, expected in cases:
            with self.subTest(name):
                summary = {key: value for key, value in {**ORIENTATION, **changes}.items() if value is not None} \
                    if isinstance(changes, dict) else changes
                problems = common.summary_problems(
                    summary, "the orientation", VALUE_NAMES)
                if expected is None:
                    self.assertEqual(problems, [])
                else:
                    self.assertIn(expected, " ".join(problems))
        # The orientation is a summary, by the same rule.
        self.assertEqual(common.orientation_problems(
            ORIENTATION, VALUE_NAMES), [])

    def test_notes_problems(self):
        # The notes summary is a summary whose valued points have the days
        # they were seen on, each one of the days given, and which may be
        # empty. name: (changes to it, expected in its problems, or None).
        days = ["2026-08-20", "2026-09-02", "2026-10-01"]
        cases = [("valid", {}, None),
                 ("empty", {"going_well": [], "to_improve": [],
                  "context": []}, None),
                 ("no dates", {"going_well": [{"point": "Presented it", "value": None}]},
                  'going_well must be a list of points, each {"point": "...", "value": "..." or null, '
                  '"dates": ["YYYY-MM-DD", ...]}'),
                 ("dates empty", {"going_well": [{"point": "Presented it", "value": None, "dates": []}]},
                  "going_well must be a list of points"),
                 ("a day no note was taken on", {"going_well": [
                     {"point": "Presented it", "value": None, "dates": ["2026-09-03"]}]},
                  "must each be a day a note was taken on, listed once"),
                 ("a day twice", {"to_improve": [{"point": "Late", "value": None,
                                                  "dates": ["2026-08-20", "2026-08-20"]}]}, "listed once"),
                 ("dates on context", {"context": [{"point": "Moved", "value": None, "dates": ["2026-08-20"]}]},
                  "context must be a list of points, each a sentence")]
        for name, changes, expected in cases:
            with self.subTest(name):
                problems = common.notes_problems(
                    {**NOTES, **changes}, VALUE_NAMES, days)
                if expected is None:
                    self.assertEqual(problems, [])
                else:
                    self.assertIn(expected, " ".join(problems))

    def test_earliest_feedback_end(self):
        # Two years before the period starts; a 29 February has none, so the
        # 28th.
        for start, expected in [("2026-08-10", date(2024, 8, 10)), ("2028-02-29", date(2026, 2, 28))]:
            with self.subTest(start):
                self.assertEqual(common.earliest_feedback_end(
                    {**REQUEST, "start": start}), expected)

    def test_feedback_problems(self):
        # name: (the feedback, expected in its problems, or None for none).
        # REQUEST starts on 10/08/2026, so dated feedback may end from
        # 10/08/2024 to its end, 10/11/2026.
        ratings = ["Below", "Meets", "Exceeds"]
        undated = {**PIECE, "start": None, "end": None, "rating": None}
        cases = [("one piece", [PIECE], None), ("none", [], None),
                 ("no days and no rating", [undated], None),
                 ("only an end day", [{**undated, "end": "2026-06-30"}], None),
                 ("only a start day", [
                  {**undated, "start": "2026-01-01"}], None),
                 ("only an end day, too old", [
                  {**undated, "end": "2024-08-09"}], "ends on 09/08/2024"),
                 ("two undated", [
                  undated, {**undated, "context": ["Mentors new joiners"]}], None),
                 ("ending on the first day allowed", [
                  {**PIECE, "start": "2024-01-01", "end": "2024-08-10"}], None),
                 ("ending inside the period", [
                  {**PIECE, "end": "2026-09-30"}], None),
                 ("too old", [{**PIECE, "start": "2024-01-01", "end": "2024-08-09"}],
                  "ends on 09/08/2024: only feedback that ends from 10/08/2024 to 10/11/2026 counts"),
                 ("ending after the period", [
                  {**PIECE, "end": "2026-12-31"}], "ends on 31/12/2026"),
                 ("starting after it ends", [
                  {**PIECE, "start": "2026-07-01"}], "starts after it ends"),
                 ("not a date", [{**PIECE, "end": "30/06/2026"}],
                  "must be a date as YYYY-MM-DD"),
                 ("a rating not the company's", [{**PIECE, "rating": "Good"}],
                  "'Good', must be one of the company's: Below, Meets, Exceeds, or null"),
                 ("a field missing", [
                  {k: v for k, v in PIECE.items() if k != "rating"}], "must have the fields"),
                 ("a summary that breaks a rule", [{**PIECE, "going_well": [], "to_improve": []}],
                  "feedback 1 has no points"),
                 ("the same period twice", [PIECE, {**PIECE, "rating": "Exceeds"}], "record each once")]
        for name, pieces, expected in cases:
            with self.subTest(name):
                problems = common.feedback_problems(
                    {"pieces": pieces}, REQUEST, ratings, VALUE_NAMES)
                if expected is None:
                    self.assertEqual(problems, [])
                else:
                    self.assertIn(expected, " ".join(problems))
        for name, feedback in [("a list", [PIECE]), ("a key more", {"pieces": [], "notes": "x"})]:
            with self.subTest(name):
                self.assertIn('must be {"pieces": [...]}',
                              " ".join(common.feedback_problems(feedback, REQUEST, ratings, VALUE_NAMES)))

    def test_check_ins_problems(self):
        # name: (the notes, expected in their problems, or None for none). The
        # rules all pieces share are tested with the feedback's; a dated note
        # must overlap REQUEST's period, 10/08/2026 to 10/11/2026.
        undated = {**NOTE, "start": None, "end": None}
        cases = [("one note", [NOTE], None), ("none", [], None), ("undated", [undated], None),
                 ("overlapping its start", [
                  {**NOTE, "start": "2026-07-01", "end": "2026-08-10"}], None),
                 ("only a start day inside it", [
                  {**undated, "start": "2026-11-10"}], None),
                 ("only an end day inside it", [
                  {**undated, "end": "2026-08-10"}], None),
                 ("before it", [{**NOTE, "start": "2026-07-01", "end": "2026-08-09"}],
                  "check-in 1 covers no day of the period, 10/08/2026 to 10/11/2026"),
                 ("only an end day before it", [
                  {**undated, "end": "2026-08-09"}], "covers no day"),
                 ("only a start day after it", [
                  {**undated, "start": "2026-11-11"}], "covers no day"),
                 ("a rating", [{**NOTE, "rating": None}],
                  "must have the fields start, end, going_well"),
                 ("the same days twice", [NOTE, {**NOTE, "context": ["Moved team"]}],
                  "two pieces of the check-ins cover 01/08/2026 to 30/09/2026")]
        for name, notes, expected in cases:
            with self.subTest(name):
                problems = common.check_ins_problems(
                    {"pieces": notes}, REQUEST, VALUE_NAMES)
                if expected is None:
                    self.assertEqual(problems, [])
                else:
                    self.assertIn(expected, " ".join(problems))
        self.assertIn('the check-ins must be {"pieces": [...]}',
                      " ".join(common.check_ins_problems([NOTE], REQUEST, VALUE_NAMES)))

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
