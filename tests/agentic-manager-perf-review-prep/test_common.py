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
from prep_fixture import (NOTE, NOTES, ORIENTATION, PERSON, PIECE, PREP, SLACK, WORK, WORK_ITEMS, WORK_RAW,  # noqa: E402
                           temp_output, write_prep)  # noqa: E402

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
        # The notes summary is a reading's: every point has its evidence,
        # each {date, link}, the date one of the days given, or null in a
        # context point, from a page, and it may be empty. name: (changes to
        # it, expected in its problems, or None).
        def evidence(*dates):
            return [{"date": date, "link": f"file:///vault/{date}.md"} for date in dates]
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
                  "must have the fields period, going_well")]
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

    def test_build_work(self):
        # The fixture's work.json, worked out by hand from its raw files: each
        # source's items without the fields kept only to check them, its
        # facts, such as the main focus of its one resolved issue, and each
        # search's address.
        self.assertEqual(common.build_work(
            WORK_RAW, common.period_days(PERSON)), WORK)

    def test_write_work(self):
        # work.json is built once every source's raw file is in and follows
        # its rules: one in an earlier format waits to be fetched again.
        folder = temp_output(self)
        write_prep(folder, work=None, raw_work={
                   "jira": WORK_RAW["jira"], "github": {"opened": [], "merged": []}})
        days = common.period_days(PERSON)
        self.assertIsNone(common.write_work(
            PREP, "notion", WORK_RAW["notion"], days)["work"])
        written = common.write_work(PREP, "github", WORK_RAW["github"], days)
        self.assertEqual(common.read_json(written["work"]), WORK)

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

    def test_focus(self):
        # name: (parents of the resolved issues, by key, None for none, the
        # focus expected as (key, issues)): the fewest parents covering 80%
        # of the issues with one, those tied with the last one too; with no
        # parent at all, the projects.
        def issues(*parents):
            return [{"key": f"PROJ-{n}", "parent": {"key": parent, "title": parent.title()} if parent else None}
                    for n, parent in enumerate(parents)]
        cases = [("nothing", [], []),
                 ("one parent", issues("billing"), [("billing", 1)]),
                 ("80% covered", issues(
                     *["a"] * 5, *["b"] * 3, "c", "d"), [("a", 5), ("b", 3)]),
                 ("tied at the cutoff", issues(*["a"] * 4, *["b"] * 2, *["c"] * 2, *["d"] * 2),
                  [("a", 4), ("b", 2), ("c", 2), ("d", 2)]),
                 ("no parent left out", issues("a", "a", None, None, None), [("a", 2)])]
        for name, resolved, expected in cases:
            with self.subTest(name):
                self.assertEqual([(entry["key"], entry["issues"])
                                 for entry in common.focus(resolved)], expected)
        projects = [{"key": key, "parent": None}
                    for key in ("PROJ-1", "PROJ-2", "OPS-3")]
        self.assertEqual(common.focus(projects), [{"key": "PROJ", "title": None, "issues": 2},
                                                  {"key": "OPS", "title": None, "issues": 1}])

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
