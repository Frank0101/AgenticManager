"""Unit tests for skills/agentic-manager-perf-review-prep/scripts/common.py.
Run with: python3 tests/run.py agentic-manager-perf-review-prep
"""

import os
import sys
import tempfile
import unittest
from datetime import date
from unittest import mock

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(TEST_DIR))
sys.path.insert(0, os.path.join(REPO_ROOT, "skills",
                os.path.basename(TEST_DIR), "scripts"))
import common  # noqa: E402
sys.path.insert(0, TEST_DIR)
from prep_fixture import NOTE, NOTES, ORIENTATION, PERSON, PIECE, PREP, SLACK, WORK_FACTS, WORK_ITEMS, temp_output, write_prep  # noqa: E402

TODAY = date(2026, 11, 10)
VALUE_NAMES = ["Ownership", "Teamwork"]


class CommonTest(unittest.TestCase):
    def test_person_problems(self):
        # name: (changes to the person, or a value instead of it, expected
        # in its problems, or None for none)
        fields = "fields must be person, start, end, sources"
        cases = [("valid", {}, None),
                 ("one day", {"start": "2026-11-10"}, None),
                 ("not an object", ["Jane Doe"], "must be a JSON object"),
                 ("a field missing", {"end": None}, fields),
                 ("no sources", {"sources": None}, fields),
                 ("a field more", {
                  "shown": "10/08/2026 to 10/11/2026"}, fields),
                 ("no name", {"person": " "}, "must name the person"),
                 ("a name that isn't text", {
                  "person": 7}, "must name the person"),
                 ("not a date", {"start": "10/08/2026"},
                  "must be a date as YYYY-MM-DD"),
                 ("ends after today", {"end": "2026-12-31"}, "after today"),
                 ("starts after it ends", {
                  "start": "2026-11-10", "end": "2026-08-10"}, "after it ends")]
        for name, change, expected in cases:
            with self.subTest(name):
                person = change if isinstance(change, list) else {
                    k: v for k, v in {**PERSON, **change}.items() if v is not None}
                problems = common.person_problems(person, TODAY)
                if expected is None:
                    self.assertEqual(problems, [])
                else:
                    self.assertIn(expected, " ".join(problems))

    def test_sources_problems(self):
        # name: (the sources, the sources wanted, expected in their
        # problems, or None for none): after step 1 only Jira's, once the
        # prep is complete every one.
        def changed(change):
            return {k: v for k, v in {**PERSON["sources"], **change}.items() if v is not None}
        jira = {"jira-api": PERSON["sources"]["jira-api"]}
        every = tuple(common.SOURCES)
        cases = [("valid", changed({}), every, None),
                 ("Jira's alone after step 1", jira, ("jira-api",), None),
                 ("not an object", ["janedoe"],
                  every, "must be a JSON object"),
                 ("a source missing", changed({"slack-mcp": None}), every,
                  "must be jira-api, github-cli, notion-mcp, slack-mcp, logseq-fs"),
                 ("Jira's alone once complete", jira, every, "not jira-api"),
                 ("a source more after step 1", changed({}),
                  ("jira-api",), "must be jira-api, not"),
                 ("a hidden email", changed({"jira-api": {**jira["jira-api"], "email": None}}), every,
                  'jira-api must be {"id": "...", "name": "...", "email": "..."}'),
                 ("an account field more", changed({"jira-api": {**jira["jira-api"], "active": True}}), every,
                  "jira-api must be"),
                 ("no name", changed({"github-cli": {"id": "janedoe"}}), every,
                  'github-cli must be {"id": "...", "name": "..."}'),
                 ("a blank id", changed({"slack-mcp": {"id": " ",
                  "name": "Jane Doe"}}), every, "slack-mcp must be"),
                 ("no links", changed({"logseq-fs": {"links": []}}), every,
                  'logseq-fs must be {"links": ["...", ...]}'),
                 ("a blank link", changed({
                  "logseq-fs": {"links": ["Jane", " "]}}), every, "logseq-fs must be"),
                 ("a link twice", changed({
                  "logseq-fs": {"links": ["Jane", "Jane"]}}), every, "logseq-fs must be"),
                 ("links that aren't a list", changed({
                  "logseq-fs": {"links": "Jane"}}), every, "logseq-fs must be"),
                 ("an id for the vault", changed({"logseq-fs": {"id": "Jane", "name": "Jane"}}), every,
                  "logseq-fs must be")]
        for name, sources, names, expected in cases:
            with self.subTest(name):
                problems = common.sources_problems(sources, names)
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
                 ("a blank point", {"to_improve": [{"point": " ", "values": []}]},
                  'to_improve must be a list of points, each {"point": "...", "values": ["...", ...] or []}'),
                 ("a point twice", {"context": [
                  "Back in May", "Back in May"]}, "more than once"),
                 ("a valued point twice", {"going_well": [{"point": "Led it", "values": ["Ownership"]},
                                                          {"point": "Led it", "values": []}]}, "more than once"),
                 ("a point too long", {"going_well": [{"point": long_point, "values": []}]},
                  f"at most {common.MAX_POINT_WORDS}"),
                 ("a value left out", {"going_well": [
                  {"point": "Led it", "values": []}]}, None),
                 ("two values", {"going_well": [
                  {"point": "Led it", "values": ["Teamwork", "Ownership"]}]}, None),
                 ("a value twice", {"going_well": [{"point": "Led it", "values": ["Ownership", "Ownership"]}]},
                  "listed once, at most 2"),
                 ("three values", {"going_well": [{"point": "Led it", "values": ["Ownership", "Teamwork", "Grit"]}]},
                  "listed once, at most 2"),
                 ("a value not the company's", {"going_well": [{"point": "Led it", "values": ["Grit"]}]},
                  "['Grit'], must each be one of the company's: Ownership, Teamwork, listed once, at most 2, or [] when none fits"),
                 ("a value's field missing", {"going_well": [{"point": "Led it"}]},
                  "going_well must be a list of points"),
                 ("text where a value is due", {
                  "to_improve": ["Could share more"]}, "to_improve must be a list of points"),
                 ("a value on context", {"context": [{"point": "Back in May", "values": []}]},
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
                 ("no dates", {"going_well": [{"point": "Presented it", "values": []}]},
                  'going_well must be a list of points, each {"point": "...", "values": ["...", ...] or [], '
                  '"dates": ["YYYY-MM-DD", ...]}'),
                 ("dates empty", {"going_well": [{"point": "Presented it", "values": [], "dates": []}]},
                  "going_well must be a list of points"),
                 ("a day no note was taken on", {"going_well": [
                     {"point": "Presented it", "values": [], "dates": ["2026-09-03"]}]},
                  "must each be a day the source was read on, listed once"),
                 ("a day twice", {"to_improve": [{"point": "Late", "values": [],
                                                  "dates": ["2026-08-20", "2026-08-20"]}]}, "listed once"),
                 ("dates on context", {"context": [{"point": "Moved", "values": [], "dates": ["2026-08-20"]}]},
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
                    {**PERSON, "start": start}), expected)

    def test_feedback_problems(self):
        # name: (the feedback, expected in its problems, or None for none).
        # PERSON starts on 10/08/2026, so dated feedback may end from
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
                    {"pieces": pieces}, PERSON, ratings, VALUE_NAMES)
                if expected is None:
                    self.assertEqual(problems, [])
                else:
                    self.assertIn(expected, " ".join(problems))
        for name, feedback in [("a list", [PIECE]), ("a key more", {"pieces": [], "notes": "x"})]:
            with self.subTest(name):
                self.assertIn('must be {"pieces": [...]}',
                              " ".join(common.feedback_problems(feedback, PERSON, ratings, VALUE_NAMES)))

    def test_check_ins_problems(self):
        # name: (the notes, expected in their problems, or None for none). The
        # rules all pieces share are tested with the feedback's; a dated note
        # must overlap PERSON's period, 10/08/2026 to 10/11/2026.
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
                    {"pieces": notes}, PERSON, VALUE_NAMES)
                if expected is None:
                    self.assertEqual(problems, [])
                else:
                    self.assertIn(expected, " ".join(problems))
        self.assertIn('the check-ins must be {"pieces": [...]}',
                      " ".join(common.check_ins_problems([NOTE], PERSON, VALUE_NAMES)))

    def test_months_of(self):
        # Each month of the period, clipped to it.
        self.assertEqual(common.months_of(date(2026, 8, 10), date(2026, 10, 3)), {
            "2026-08": {"start": "2026-08-10", "end": "2026-08-31"},
            "2026-09": {"start": "2026-09-01", "end": "2026-09-30"},
            "2026-10": {"start": "2026-10-01", "end": "2026-10-03"}})

    def test_period_days(self):
        # Every day of the period, its first and last too.
        days = common.period_days(PERSON)
        self.assertEqual((days[0], days[1], days[-1], len(days)),
                         ("2026-08-10", "2026-08-11", "2026-11-10", 93))

    def test_slack_problems(self):
        # Every point, context too, has its days and links.
        days = common.period_days(PERSON)
        self.assertEqual(common.slack_problems(SLACK, VALUE_NAMES, days), [])
        unlinked = {**SLACK, "context": [{**SLACK["context"][0], "links": []}]}
        self.assertIn("must be a list of points", " ".join(
            common.slack_problems(unlinked, VALUE_NAMES, days)))

    def test_work_problems_links(self):
        # name: (a resolved issue's url, whether the work is accepted): a
        # link is a web address, http too, as a self-hosted Jira site may
        # serve its pages over http.
        cases = [("https", "https://acme.atlassian.net/browse/PROJ-12", True),
                 ("http", "http://jira.acme.test/browse/PROJ-12", True),
                 ("no scheme", "jira.acme.test/browse/PROJ-12", False),
                 ("not a web address", "ftp://jira.acme.test/PROJ-12", False)]
        days = common.period_days(PERSON)
        for name, url, accepted in cases:
            with self.subTest(name):
                work = {**WORK_ITEMS, "jira": {**WORK_ITEMS["jira"], "resolved": [
                    {**WORK_ITEMS["jira"]["resolved"][0], "url": url}]}}
                problems = common.work_problems(work, days, final=False)
                self.assertEqual(problems == [], accepted, problems)

    def test_work_facts(self):
        # name: (the work, the facts expected): a pull request's area is its
        # issue's parent, "no parent" when the issue has none, or its
        # repository when no issue lists it; most work first.
        days = common.period_days(PERSON)
        pr = {"repo": "acme/billing", "title": "PR", "date": "2026-09-02"}
        github = {"opened": [{**pr, "number": 1, "url": "https://github.com/acme/billing/pull/1", "issue": "PROJ-12"},
                             {**pr, "number": 2, "url": "https://github.com/acme/billing/pull/2",
                                 "issue": "PROJ-13"},
                             {**pr, "number": 3, "url": "https://github.com/acme/billing/pull/3", "issue": None,
                              "date": "2026-10-01"}],
                  "merged": [{**pr, "number": 1, "url": "https://github.com/acme/billing/pull/1", "issue": "PROJ-12"}]}
        months = [{"month": "2026-08", "opened": 0, "merged": 0, "areas": 0, "main_areas": []},
                  {"month": "2026-09", "opened": 2, "merged": 1, "areas": 2,
                   "main_areas": [{"area": "Billing", "items": 2}, {"area": "no parent", "items": 1}]},
                  {"month": "2026-10", "opened": 1, "merged": 0, "areas": 1,
                   "main_areas": [{"area": "acme/billing", "items": 1}]},
                  {"month": "2026-11", "opened": 0, "merged": 0, "areas": 0, "main_areas": []}]
        cases = [("the fixture", WORK_ITEMS, WORK_FACTS),
                 ("pull requests", {**WORK_ITEMS, "github": github}, {**WORK_FACTS, "github": {
                     "by_month": months,
                     "by_area": [{"kind": "Epic", "key": "PROJ-1", "title": "Billing", "opened": 1, "merged": 1},
                                 {"kind": "no parent", "key": None,
                                     "title": None, "opened": 1, "merged": 0},
                                 {"kind": "repository", "key": None, "title": "acme/billing", "opened": 1,
                                  "merged": 0}]}}),
                 ("nothing", {source: dict.fromkeys(lists, []) for source, lists in common.WORK_LISTS.items()},
                  {source: {"by_month": [{"month": month, **dict.fromkeys((name for name in lists if name != "open"), 0),
                                          "areas": 0, "main_areas": []}
                                         for month in ("2026-08", "2026-09", "2026-10", "2026-11")],
                            "by_area": []} for source, lists in common.WORK_LISTS.items()})]
        for name, work, expected in cases:
            with self.subTest(name):
                self.assertEqual(common.work_facts(work, days), expected)

    def test_name_words(self):
        for name, words in [("Jane Doe", ["jane", "doe"]), ("José  Núñez-Ruiz", ["jose", "nunez", "ruiz"]),
                            ("Meeting with Jane Doe", ["meeting", "with", "jane", "doe"]), ("..", [])]:
            with self.subTest(name):
                self.assertEqual(common.name_words(name), words)

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

    def test_script_command(self):
        # By the folder the agent ran one of the skill's scripts from, even
        # through a symlink, as the skill pre-approves it; by the skill's own
        # folder otherwise.
        scripts = os.path.dirname(os.path.realpath(common.__file__))
        with tempfile.TemporaryDirectory() as folder:
            link = os.path.join(folder, "scripts")
            os.symlink(scripts, link)
            # name: (sys.argv[0], the folder expected in the command)
            cases = [("the script itself", os.path.join(link, "jira_ticket.py"), link),
                     ("another of the skill's scripts", os.path.join(
                         link, "read_notes.py"), link),
                     ("not one of the skill's scripts", os.path.join(folder, "run.py"), scripts)]
            for name, ran, expected in cases:
                with self.subTest(name), mock.patch.object(sys, "argv", [ran]):
                    self.assertEqual(common.script_command("jira_ticket.py"),
                                     f"python3 {os.path.join(expected, 'jira_ticket.py')}")


if __name__ == "__main__":
    unittest.main()
