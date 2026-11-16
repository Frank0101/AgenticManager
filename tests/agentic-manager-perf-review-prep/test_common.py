"""Unit tests for skills/agentic-manager-perf-review-prep/scripts/common.py.
Run with: python3 tests/run.py agentic-manager-perf-review-prep
"""

import os
import sys
import tempfile
import unittest
from datetime import date, timedelta
from unittest import mock

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(TEST_DIR))
sys.path.insert(0, os.path.join(REPO_ROOT, "skills",
                os.path.basename(TEST_DIR), "scripts"))
import common  # noqa: E402
sys.path.insert(0, TEST_DIR)
from prep_fixture import (STEP_CHANGE, VIEW, VIEW_CHECK, OBSERVATIONS, PREVIOUS_REVIEWS, NOTE, NOTES, VALUE_NAMES, ORIENTATION, PERSON, PIECE, PREP, SLACK, NOTION_SEARCHES, PLAN_RESULT, DATA, WORK_ITEMS, WORK_RAW,  # noqa: E402
                           temp_output, write_prep)  # noqa: E402

TODAY = date(2026, 11, 10)


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
        # The notes summary is a reading's: every point has its evidence,
        # each {date, link}, the date one of the days given, or null in a
        # context point, from a page, and it may be empty. name: (changes to
        # it, expected in its problems, or None).
        def evidence(*dates):
            return [{"date": date, "link": f"/vault/{date}.md"} for date in dates]
        days = ["2026-08-20", "2026-09-02", "2026-10-01"]
        cases = [("valid", {}, None),
                 ("empty", {"going_well": [], "to_improve": [],
                  "context": []}, None),
                 ("no evidence", {"going_well": [{"point": "Presented it", "values": []}]},
                  'going_well must be a list of points, each {"point": "...", "values": ["...", ...] or [], '
                  '"evidence": [{"date": "YYYY-MM-DD", "link"'),
                 ("evidence empty", {"going_well": [{"point": "Presented it", "values": [], "evidence": []}]},
                  "going_well must be a list of points"),
                 ("a link not a file's or a web page's", {"going_well": [
                     {"point": "Presented it", "values": [],
                      "evidence": [{"date": "2026-09-02", "link": "journals/x.md"}]}]},
                  "going_well must be a list of points"),
                 ("a file:// address", {"going_well": [
                     {"point": "Presented it", "values": [],
                      "evidence": [{"date": "2026-09-02", "link": "file:///vault/x.md"}]}]},
                  "going_well must be a list of points"),
                 ("a day no note was taken on", {"going_well": [
                     {"point": "Presented it", "values": [], "evidence": evidence("2026-09-03")}]},
                  "evidence must each be of a day the source was read on, each link once"),
                 ("a link twice", {"to_improve": [{"point": "Late", "values": [],
                                                   "evidence": evidence("2026-08-20", "2026-08-20")}]}, "each link once"),
                 ("valued undated", {"going_well": [{"point": "Presented it", "values": [], "evidence": evidence(None)}]},
                  "must each be of a day the source was read on, each link once"),
                 ("context dated", {"context": [
                  {"point": "Moved", "evidence": evidence("2026-08-20")}]}, None),
                 ("context undated", {"context": [
                  {"point": "Moved", "evidence": evidence(None)}]}, None),
                 ("context a sentence alone", {"context": ["Moved"]}, "context must be a list of points")]
        for name, changes, expected in cases:
            with self.subTest(name):
                problems = common.notes_problems(
                    {**NOTES, **changes}, VALUE_NAMES, days)
                if expected is None:
                    self.assertEqual(problems, [])
                else:
                    self.assertIn(expected, " ".join(problems))

    def test_reviews_problems(self):
        # name: (the reviews, expected in their problems, or None for none).
        # A period is a label, never checked against the prep's, nor is a
        # review's age: what the manager gives counts.
        ratings = ["Below", "Meets", "Exceeds"]
        unnamed = {**PIECE, "period": None, "rating": None}
        cases = [("one review", [PIECE], None), ("none", [], None),
                 ("no period and no rating", [unnamed], None),
                 ("a date as period", [
                  {**PIECE, "period": "30/06/2020"}], None),
                 ("the same period twice", [
                  PIECE, {**PIECE, "rating": "Exceeds"}], None),
                 ("a blank period", [
                  {**PIECE, "period": " "}], "must be a text"),
                 ("a period not a text", [
                  {**PIECE, "period": 2026}], "must be a text"),
                 ("no date", [{**PIECE, "date": None}], None),
                 ("a date not a day", [
                  {**PIECE, "date": "2026-06"}], "must be the last day of its period"),
                 ("a rating not the company's", [{**PIECE, "rating": "Good"}],
                  "'Good', must be one of the company's: Below, Meets, Exceeds, or null"),
                 ("a field missing", [
                  {k: v for k, v in PIECE.items() if k != "rating"}], "must have the fields"),
                 ("a summary that breaks a rule", [{**PIECE, "going_well": [], "to_improve": []}],
                  "review 1 has no points")]
        for name, pieces, expected in cases:
            with self.subTest(name):
                problems = common.reviews_problems(
                    {"pieces": pieces}, ratings, VALUE_NAMES)
                if expected is None:
                    self.assertEqual(problems, [])
                else:
                    self.assertIn(expected, " ".join(problems))
        for name, feedback in [("a list", [PIECE]), ("a key more", {"pieces": [], "notes": "x"})]:
            with self.subTest(name):
                self.assertIn('must be {"pieces": [...]}',
                              " ".join(common.reviews_problems(feedback, ratings, VALUE_NAMES)))

    def test_feedback_problems_of_the_period(self):
        # name: (the feedback, expected in its problems, or None for none).
        # The rules all pieces share are tested with the reviews'.
        cases = [("one piece", [NOTE], None), ("none", [], None),
                 ("no period", [{**NOTE, "period": None}], None),
                 ("a rating", [{**NOTE, "rating": None}],
                  "must have the fields period, date, going_well")]
        for name, notes, expected in cases:
            with self.subTest(name):
                problems = common.feedback_problems(
                    {"pieces": notes}, VALUE_NAMES)
                if expected is None:
                    self.assertEqual(problems, [])
                else:
                    self.assertIn(expected, " ".join(problems))
        self.assertIn('the feedback must be {"pieces": [...]}',
                      " ".join(common.feedback_problems([NOTE], VALUE_NAMES)))

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
        # Every point, context too, has its evidence, each of a day: a
        # message always has one.
        days = common.period_days(PERSON)
        self.assertEqual(common.slack_problems(SLACK, VALUE_NAMES, days), [])
        link = "https://acme.slack.com/archives/C2/p2"
        for name, change, expected in [("no evidence", {"evidence": []}, "must be a list of points"),
                                       ("undated", {"evidence": [{"date": None, "link": link}]},
                                        "must each be of a day the source was read on")]:
            with self.subTest(name):
                broken = {
                    **SLACK, "context": [{**SLACK["context"][0], **change}]}
                self.assertIn(expected, " ".join(
                    common.slack_problems(broken, VALUE_NAMES, days)))

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
                problems = common.items_problems("jira", {"resolved": [
                    {**WORK_ITEMS["jira"]["resolved"][0], "url": url}]}, days)
                self.assertEqual(problems == [], accepted, problems)

    def test_raw_work_problems(self):
        # name: (the source, a change to its raw file, expected in its
        # problems, or None for none).
        issue = WORK_RAW["jira"]["resolved"][0]
        cases = [("valid", "jira", {}, None),
                 ("an issue without its status", "jira", {"resolved": [
                     {**issue, "fields": {k: v for k, v in issue["fields"].items() if k != "status"}}]},
                  "lacks fields.status.name"),
                 ("a parent without its fields", "jira", {"resolved": [
                     {**issue, "fields": {**issue["fields"], "parent": {"key": "PROJ-1", "fields": {}}}}]},
                  "lacks fields.parent.fields.summary"),
                 ("a pull request without its author", "github", {"opened": [
                     {k: v for k, v in WORK_RAW["github"]["opened"][0].items() if k != "author"}]}, "lacks author"),
                 ("a pull request without its size", "github", {"merged": [
                     {k: v for k, v in WORK_RAW["github"]["merged"][0].items() if k != "deletions"}]}, "lacks deletions"),
                 ("another period", "github", {"start": "2026-08-01"},
                  "is for 2026-08-01 to 2026-11-10, not the period"),
                 ("no search", "jira", {
                  "created_jql": None, "resolved": "PROJ-12"}, "must hold"),
                 ("an issue resolved outside the period", "jira", {"resolved": [
                     {**issue, "fields": {**issue["fields"], "resolutiondate": "2026-07-01T10:00:00.000+0100"}}]},
                  "the work's jira resolved")]
        days = common.period_days(PERSON)
        for name, source, change, expected in cases:
            with self.subTest(name):
                problems = " ".join(common.raw_work_problems(
                    source, {**WORK_RAW[source], **change}, days))
                if expected is None:
                    self.assertEqual(problems, "")
                else:
                    self.assertIn(expected, problems)

    def test_notion_searches_problems(self):
        # name: (the searches, expected in their problems, or None for none).
        S = NOTION_SEARCHES
        full = [{**PLAN_RESULT, "url": f"https://www.notion.so/{n}"}
                for n in range(common.NOTION_LIMIT)]
        cases = [("valid", S, None),
                 ("a gap", S[:2] + S[3:],
                  "the Notion searches must cover 2026-08-10 to 2026-11-10 day by day"),
                 ("an overlap", S + [{**S[1], "results": []}], "must cover"),
                 ("a full search", [{**S[0], "results": full}, *S[1:]],
                  "search that range again in shorter ranges"),
                 ("a page found twice", [S[0], {**S[1], "results": [PLAN_RESULT]}, *S[2:]],
                  "found by two Notion searches, so the creation filter can't be trusted"),
                 ("a row found twice", [
                  S[0], {**S[1], "results": S[0]["results"][2:]}, *S[2:]], None),
                 ("a page without its url", [{**S[0], "results": [
                     {k: v for k, v in PLAN_RESULT.items() if k != "url"}]}, *S[1:]], "its title and url"),
                 ("pages instead of results", [{**S[0], "pages": [], "results": None}, *S[1:]],
                  "its results as it returned them"),
                 ("a month at once", [{**S[0], "end": "2026-09-06"}, *S[4:]],
                  "spans more than a calendar week"),
                 ("a single day still full", [{"start": "2026-08-10", "end": "2026-08-10", "results": S[0]["results"],
                                               "full": True}, {**S[0], "start": "2026-08-11", "results": []}, *S[1:]], None),
                 ("full over more than a day", [{**S[0], "full": True}, *S[1:]],
                  "only a search of a single day may be"),
                 ("not a day", [{**S[0], "start": "10/08/2026"}, *S[1:]], "must be days")]
        days = common.period_days(PERSON)
        for name, searches, expected in cases:
            with self.subTest(name):
                problems = " ".join(
                    common.notion_searches_problems(searches, days))
                if expected is None:
                    self.assertEqual(problems, "")
                else:
                    self.assertIn(expected, problems)

    def test_name_words(self):
        for name, words in [("Jane Doe", ["jane", "doe"]), ("José  Núñez-Ruiz", ["jose", "nunez", "ruiz"]),
                            ("Meeting with Jane Doe", ["meeting", "with", "jane", "doe"]), ("..", [])]:
            with self.subTest(name):
                self.assertEqual(common.name_words(name), words)

    def test_report_name(self):
        # The report is named after the prep's person.
        self.assertEqual(common.report_name(PREP), "Jane-Doe_Review_Prep.md")
        with self.assertRaisesRegex(SystemExit, "not a prep folder, <Person>_<YY-MM-DD>"):
            common.report_name("Jane-Doe")

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

    def test_content_problems(self):
        # name: (content.json, the tables' points, going well's and to
        # improve's groups and context's points, expected in its problems, or
        # None for none): each table's summary, empty exactly when the table
        # holds no point, not longer than MAX_OBSERVATIONS_WORDS words, and a
        # valued table's naming each value it groups points under; context
        # names none, so none is checked.
        long = "word " * (common.MAX_OBSERVATIONS_WORDS["going_well"] + 1)
        summaries = {"going_well": "Good.",
                     "to_improve": "Better.", "context": "Moved team."}
        cases = [("all summarised", summaries, (1, 1, 1), None),
                 ("no point to improve", {
                  **summaries, "to_improve": ""}, (1, 0, 1), None),
                 ("a table not summarised", {**summaries, "going_well": " "}, (1, 1, 1),
                  "going_well is empty"),
                 ("a summary of no point", summaries, (1, 0, 1),
                  "to_improve must be empty"),
                 ("too long", {**summaries, "going_well": long},
                  (1, 1, 1), f"more than {common.OBSERVATIONS_WORDS['going_well']}: cut it"),
                 ("context too long", {**summaries, "context": "word " * (common.MAX_OBSERVATIONS_WORDS["context"] + 1)},
                  (1, 1, 1), f"more than {common.OBSERVATIONS_WORDS['context']}: cut it"),
                 ("a field missing", {"going_well": "Good.", "to_improve": "Better."}, (1, 1, 1),
                  'must be {"going_well"'),
                 ("a field too many", {**summaries, "step_change": None}, (1, 1, 1),
                  'must be {"going_well"'),
                 ("a value not named", {**summaries, "going_well": "Good teamwork.", "to_improve": ""},
                  (["Teamwork", "Ownership", None], 0, 1), "doesn't name Ownership"),
                 ("context not summarised", {**summaries, "context": ""}, (1, 1, 1),
                  "context is empty"),
                 ("context of no point", summaries, (1, 1, 0),
                  "context must be empty"),
                 ("no context", {**summaries, "context": ""}, (1, 1, 0), None)]
        for name, content, counts, expected in cases:
            with self.subTest(name):
                *valued, context = counts
                groups = [[{"value": value} for value in n] if isinstance(n, list) else [{"value": None}] * n
                          for n in valued]
                observations = {**dict(zip(("going_well", "to_improve"), groups)),
                                "context": [{"point": "Moved team"}] * context}
                problems = " ".join(common.content_problems(
                    content, observations))
                if expected is None:
                    self.assertEqual(problems, "")
                else:
                    self.assertIn(expected, problems)

    def test_step_change_problems(self):
        # name: (a change to the fixture's step change, the previous
        # reviews, expected in its problems, or None for none): against the
        # latest review, each to-improve point has a row, improved,
        # still_to_improve or worsened; a going-well point held or worsened;
        # a review context point context_change; a row with no review point
        # new_context, citing a period context point; each change but improved cites period
        # points by id, each once; no review point twice; the summary not
        # empty nor over its ceiling; null exactly when there is no review.
        step = STEP_CHANGE
        rows = step["rows"]

        def row(review_point, change, *evidence):
            return {"review_point": review_point, "change": change, "evidence": list(evidence)}
        context_review = {**PREVIOUS_REVIEWS, "latest": {**PREVIOUS_REVIEWS["latest"],
                                                         "context": [{"id": "R-C1", "point": "Was new to billing"}]}}
        long = "word " * (common.MAX_OBSERVATIONS_WORDS["step_change"] + 1)
        cases = [("as written", step, PREVIOUS_REVIEWS, None),
                 ("only the to-improve rows", {**step, "rows": [row("R-I1", "improved"),
                                                                row("R-I2", "worsened", "I2")]},
                  PREVIOUS_REVIEWS, None),
                 ("improved with evidence", {**step, "rows": [row("R-I1", "improved", "G2"),
                                                              row("R-I2", "improved")]}, PREVIOUS_REVIEWS, None),
                 ("a review context point", {**step, "rows": [*rows, row("R-C1", "context_change", "C2")]},
                  context_review, None),
                 ("a review context point new", {**step, "rows": [*rows, row("R-C1", "new_context", "C2")]},
                  context_review, "row 5's change, 'new_context', must be context_change for a context point"),
                 ("two rows with no review point", {**step, "rows": [*rows, row(None, "new_context", "C2")]},
                  PREVIOUS_REVIEWS, None),
                 ("no previous review, null", None, None, None),
                 ("no previous review, a step change", step, None, "must be null"),
                 ("a previous review, null", None,
                  PREVIOUS_REVIEWS, "must be {\"summary\""),
                 ("a to-improve point with no row", {**step, "rows": rows[:1]}, PREVIOUS_REVIEWS,
                  "no row for R-I1, R-I2"),
                 ("a to-improve point held", {**step, "rows": [*rows[:3], row("R-I1", "held", "G1")]},
                  PREVIOUS_REVIEWS, "row 4's change, 'held', must be improved or still_to_improve or worsened"),
                 ("a going-well point improved", {**step, "rows": [row("R-G1", "improved"), *rows[1:]]},
                  PREVIOUS_REVIEWS, "row 1's change, 'improved', must be held or worsened"),
                 ("a row with no review point not context", {**step, "rows": [*rows, row(None, "worsened", "I1")]},
                  PREVIOUS_REVIEWS, "must be new_context for a row with no review_point"),
                 ("a row with no review point changed", {**step, "rows": [*rows, row(None, "context_change", "C2")]},
                  PREVIOUS_REVIEWS, "row 5's change, 'context_change', must be new_context for a row with no "
                  "review_point"),
                 ("a row with no review point citing no context",
                  {**step, "rows": [*rows,
                                    row(None, "new_context", "G1")]}, PREVIOUS_REVIEWS,
                  "row 5 has no review_point, so its evidence must cite the period context point"),
                 ("still to improve with no evidence", {**step, "rows": [*rows[:1], row("R-I2", "still_to_improve"),
                                                                         *rows[2:]]},
                  PREVIOUS_REVIEWS, "row 2's evidence is empty"),
                 ("held with no evidence", {**step, "rows": [row("R-G1", "held"), *rows[1:]]},
                  PREVIOUS_REVIEWS, "row 1's evidence is empty"),
                 ("an id that isn't a period point", {**step, "rows": [row("R-G1", "held", "G9"), *rows[1:]]},
                  PREVIOUS_REVIEWS, "row 1's evidence names G9, not points of the period"),
                 ("an id cited twice", {**step, "rows": [row("R-G1", "held", "G3", "G3"), *rows[1:]]},
                  PREVIOUS_REVIEWS, "row 1's evidence names a point more than once"),
                 ("a review point that isn't one", {**step, "rows": [*rows, row("R-G2", "held", "G1")]},
                  PREVIOUS_REVIEWS, "row 5's review_point, 'R-G2', must be one of the latest review's points"),
                 ("a review point twice", {**step, "rows": [*rows, row("R-I1", "improved")]},
                  PREVIOUS_REVIEWS, "row 5's review_point, R-I1, has a row already"),
                 ("a row's field missing", {**step, "rows": [*rows, {"review_point": "R-I1", "change": "improved"}]},
                  PREVIOUS_REVIEWS, "row 5 must be"),
                 ("an empty summary", {**step, "summary": " "},
                  PREVIOUS_REVIEWS, "summary is empty"),
                 ("a summary too long", {**step, "summary": long}, PREVIOUS_REVIEWS,
                  f"summary has {common.MAX_OBSERVATIONS_WORDS['step_change'] + 1} words, more than "
                  f"{common.OBSERVATIONS_WORDS['step_change']}: cut it to about "
                  f"{common.OBSERVATIONS_WORDS['step_change']}")]
        for name, step_change, reviews, expected in cases:
            with self.subTest(name):
                problems = " ".join(common.step_change_problems(
                    step_change, OBSERVATIONS, reviews))
                if expected is None:
                    self.assertEqual(problems, "")
                else:
                    self.assertIn(expected, problems)
                    self.assertNotIn(
                        str(common.MAX_OBSERVATIONS_WORDS["step_change"]), problems)

    def test_view_check_problems(self):
        # name: (a change to the fixture's view check, the manager's view,
        # expected in its problems, or None for none): every point of the
        # view, context too, has one row, confirmed, little_support or
        # contradicted; a row with no view point not_in_view; each check but
        # little_support cites period points by id, each once; no view
        # point twice; the summary not empty nor over its ceiling; never
        # null, as the view always has points.
        check = VIEW_CHECK
        rows = check["rows"]

        def row(view_point, kind, *evidence):
            return {"view_point": view_point, "check": kind, "evidence": list(evidence)}
        long = "word " * (common.MAX_OBSERVATIONS_WORDS["view_check"] + 1)
        cases = [("as written", check, VIEW, None),
                 ("an id in the summary", {**check, "summary": "Jane's ownership is confirmed (G1, G3)."}, VIEW,
                  "summary names G1, G3"),
                 ("little support citing the little there is", {**check, "rows": [
                     *rows[:2], row("V-C1", "little_support", "C2"), *rows[3:]]}, VIEW, None),
                 ("no theme missing from the view", {
                  **check, "rows": [rows[0], *rows[2:]]}, VIEW, None),
                 ("null", None,
                  VIEW, 'must be {"summary"'),
                 ("a context point with no row", {**check, "rows": [*rows[:2], rows[3]]}, VIEW,
                  "no row for V-C1: give every point of the manager's view one"),
                 ("a point of the view not_in_view", {**check, "rows": [*rows[:3], row("V-G1", "not_in_view", "G3")]},
                  VIEW, "row 4's check, 'not_in_view', must be confirmed or little_support or contradicted for a "
                  "going_well point of the view"),
                 ("a row with no view point confirmed", {**check, "rows": [*rows, row(None, "confirmed", "G1")]},
                  VIEW, "row 5's check, 'confirmed', must be not_in_view for a row with no view_point"),
                 ("confirmed with no evidence", {**check, "rows": [*rows[:3], row("V-G1", "confirmed")]},
                  VIEW, "row 4's evidence is empty"),
                 ("contradicted with no evidence", {**check, "rows": [row("V-I1", "contradicted"), *rows[1:]]},
                  VIEW, "row 1's evidence is empty"),
                 ("not in view with no evidence", {**check, "rows": [rows[0], row(None, "not_in_view"), *rows[2:]]},
                  VIEW, "row 2's evidence is empty"),
                 ("an id that isn't a period point", {**check, "rows": [row("V-I1", "contradicted", "G9"), *rows[1:]]},
                  VIEW, "row 1's evidence names G9, not points of the period"),
                 ("a view point cited as evidence", {**check, "rows": [row("V-I1", "contradicted", "V-G1"),
                                                                       *rows[1:]]},
                  VIEW, "row 1's evidence names V-G1, not points of the period"),
                 ("an id cited twice", {**check, "rows": [row("V-I1", "contradicted", "G2", "G2"), *rows[1:]]},
                  VIEW, "row 1's evidence names a point more than once"),
                 ("a view point that isn't one", {**check, "rows": [*rows, row("V-G2", "confirmed", "G1")]},
                  VIEW, "row 5's view_point, 'V-G2', must be one of the view's points: V-G1, V-I1, V-C1"),
                 ("a review point", {**check, "rows": [*rows, row("R-I1", "confirmed", "G1")]},
                  VIEW, "row 5's view_point, 'R-I1', must be one of the view's points"),
                 ("a view point twice", {**check, "rows": [*rows, row("V-C1", "little_support")]},
                  VIEW, "row 5's view_point, V-C1, has a row already"),
                 ("a row's field missing", {**check, "rows": [*rows, {"view_point": "V-I1", "check": "confirmed"}]},
                  VIEW, "row 5 must be"),
                 ("an empty summary", {
                  **check, "summary": " "}, VIEW, "summary is empty"),
                 ("a summary too long", {**check, "summary": long}, VIEW,
                  f"summary has {common.MAX_OBSERVATIONS_WORDS['view_check'] + 1} words, more than "
                  f"{common.OBSERVATIONS_WORDS['view_check']}: cut it to about "
                  f"{common.OBSERVATIONS_WORDS['view_check']}")]
        for name, view_check, view, expected in cases:
            with self.subTest(name):
                problems = " ".join(common.view_check_problems(
                    view_check, OBSERVATIONS, view))
                if expected is None:
                    self.assertEqual(problems, "")
                else:
                    self.assertIn(expected, problems)
                    self.assertTrue(problems.startswith("view_check.json"))
                    self.assertNotIn(
                        str(common.MAX_OBSERVATIONS_WORDS["view_check"]), problems)

    def test_point_ids(self):
        # name: (part, place, prefix, id): by part and place, a review's
        # and a view's prefixed.
        cases = [("going well", "going_well", 1, "", "G1"), ("to improve", "to_improve", 2, "", "I2"),
                 ("context", "context", 3, "", "C3"), ("a review's",
                                                       "to_improve", 1, common.REVIEW_ID, "R-I1"),
                 ("a view's", "context", 1, common.VIEW_ID, "V-C1")]
        for name, part, number, prefix, expected in cases:
            with self.subTest(name):
                self.assertEqual(common.point_id(
                    part, number, prefix), expected)


class ReferenceTextTest(unittest.TestCase):
    def test_reference_text(self):
        # name: (source, evidence, what its reference says): a dated one by
        # its source and day, an undated page by its title, its file's name
        # unquoted.
        cases = [("a message", "slack", {"date": "2026-10-14", "link": "https://acme.slack.com/archives/C1/p1"},
                  "Slack 14 Oct"),
                 ("a journal", "notes", {"date": "2026-07-02", "link": "/vault/journals/2026_07_02.md"},
                  "Journal 2 Jul"),
                 ("a page", "notes", {
                  "date": None, "link": "/vault/pages/Jane.md"}, "Page Jane"),
                 ("a page's quoted name", "notes", {"date": None, "link": "/vault/pages/Jane%20Promotion.md"},
                  "Page Jane Promotion")]
        for name, source, item, expected in cases:
            with self.subTest(name):
                self.assertEqual(common.reference_text(source, item), expected)


class WeekTextTest(unittest.TestCase):
    def test_week_text(self):
        # The month named once within it, twice across two.
        cases = [(["2026-07-13", "2026-07-19"], "13–19 Jul"), (["2026-07-13", "2026-07-13"], "13 Jul"),
                 (["2026-07-27", "2026-08-02"], "27 Jul–2 Aug")]
        for between, expected in cases:
            with self.subTest(expected):
                self.assertEqual(common.week_text(between), expected)


class RepoCodeTest(unittest.TestCase):
    def test_repo_code(self):
        # A letter by the repository's place in the order, none beyond it.
        order = ["acme/api", "acme/web"]
        self.assertEqual([common.repo_code(repo, order) for repo in ("acme/api", "acme/web", "acme/docs")],
                         ["A", "B", None])


class LinkHrefTest(unittest.TestCase):
    def test_link_href(self):
        # A web address as it is; a file's path relative to the report's
        # folder, escaped, so a space doesn't break the link.
        self.assertEqual([common.link_href(link, "/My Vault/.out/preps/Jane-Doe_26-11-10")
                          for link in ("https://acme.slack.com/archives/C1/p1?a=1", "/My Vault/journals/2026_09_02.md")],
                         ["https://acme.slack.com/archives/C1/p1?a=1", "../../../journals/2026_09_02.md"])
        self.assertEqual(common.link_href(
            "/My Vault/journals/a b.md", "/My Vault"), "journals/a%20b.md")


if __name__ == "__main__":
    unittest.main()
