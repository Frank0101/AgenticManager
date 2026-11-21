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
from prep_fixture import (STEP_CHANGE_CONTENT, OBSERVATIONS, PREVIOUS, NOTES, VALUE_NAMES, MANAGER_FEEDBACK, PERSON, PREP, SLACK, NOTION_SEARCHES, PLAN_RESULT, WORK_ITEMS, WORK_RAW,  # noqa: E402
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
                 ("a date not as YYYY-MM-DD", {"end": "20261110"},
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

    def test_person_problems_notes_end(self):
        # The notes' last day, set once a change to the finished prep read
        # them to today: (its value, expected in the problems on 21/11, or
        # None for none).
        today = date(2026, 11, 21)
        for value, expected in {"2026-11-21": None, "2026-11-11": None,
                                "2026-11-10": "notes' last day", "2026-11-22": "notes' last day",
                                "today": "notes' last day", "20261121": "notes' last day"}.items():
            with self.subTest(value):
                problems = common.person_problems(
                    {**PERSON, "notes_end": value}, today)
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
        # name: (the check, the summary, or a value instead of it, expected
        # in its problems, or None for none). Every summary follows one rule,
        # summary_problems(): a feedback, named after its kind, may
        # have no points, as the text may say nothing of the person; a
        # reading's, the notes' or Slack's, has every point's evidence, each
        # {date, link}, the date one of the days given, or null in a notes
        # context point, from a page, and it may be empty.
        def feedback(kind):
            return lambda summary: common.feedback_problems(summary, kind, VALUE_NAMES)
        manager, note_days, slack_days = feedback("manager"), ["2026-08-20", "2026-09-02", "2026-10-01"], \
            common.period_days(PERSON)

        def notes(summary):
            return common.summary_problems(summary, "the notes summary", VALUE_NAMES, note_days, undated_context=True)

        def slack(summary):
            return common.summary_problems(summary, "the Slack summary", VALUE_NAMES, slack_days)

        def changed(base, changes):
            # `base` with `changes`, a part set to None left out.
            return {key: value for key, value in {**base, **changes}.items() if value is not None}

        def evidence(*dates):
            return [{"date": date, "link": f"/vault/{date}.md"} for date in dates]
        long_point = " ".join(["word"] * (common.MAX_POINT_WORDS + 1))
        empty = {"going_well": [], "to_improve": [], "context": []}
        slack_link = "https://acme.slack.com/archives/C2/p2"
        cases = [("valid", manager, MANAGER_FEEDBACK, None),
                 ("parts left empty", manager, changed(
                     MANAGER_FEEDBACK, {"to_improve": [], "context": []}), None),
                 ("a point at the limit", manager,
                  changed(MANAGER_FEEDBACK, {"context": [" ".join(["word"] * common.MAX_POINT_WORDS)]}), None),
                 ("a part missing", manager, changed(MANAGER_FEEDBACK, {"context": None}),
                  "must have the parts going_well, to_improve, context"),
                 ("not an object", manager,
                  "Strong half overall.", "must have the parts"),
                 ("text, not a list", manager, changed(MANAGER_FEEDBACK, {"going_well": "Strong half"}),
                  "going_well must be a list of points"),
                 ("a blank point", manager, changed(MANAGER_FEEDBACK, {"to_improve": [{"point": " ", "values": []}]}),
                  'to_improve must be a list of points, each {"point": "...", "values": ["...", ...] or []}'),
                 ("a point twice", manager, changed(MANAGER_FEEDBACK, {"context": ["Back in May", "Back in May"]}),
                  "more than once"),
                 ("a valued point twice", manager,
                  changed(MANAGER_FEEDBACK, {"going_well": [{"point": "Led it", "values": ["Ownership"]},
                                                            {"point": "Led it", "values": []}]}), "more than once"),
                 ("a point too long", manager,
                  changed(MANAGER_FEEDBACK, {"going_well": [
                          {"point": long_point, "values": []}]}),
                  f"up to {common.POINT_WORDS}"),
                 ("a value left out", manager,
                  changed(MANAGER_FEEDBACK, {"going_well": [{"point": "Led it", "values": []}]}), None),
                 ("two values", manager,
                  changed(MANAGER_FEEDBACK, {"going_well": [
                          {"point": "Led it", "values": ["Teamwork", "Ownership"]}]}),
                  None),
                 ("a value twice", manager,
                  changed(MANAGER_FEEDBACK, {"going_well": [
                          {"point": "Led it", "values": ["Ownership", "Ownership"]}]}),
                  "listed once, at most 2"),
                 ("three values", manager,
                  changed(MANAGER_FEEDBACK, {"going_well": [{"point": "Led it",
                                                             "values": ["Ownership", "Teamwork", "Grit"]}]}),
                  "listed once, at most 2"),
                 ("a value not the company's", manager,
                  changed(MANAGER_FEEDBACK, {"going_well": [
                          {"point": "Led it", "values": ["Grit"]}]}),
                  "['Grit'], must each be one of the company's: Ownership, Teamwork, listed once, at most 2, or [] "
                  "when none fits"),
                 ("a value's field missing", manager, changed(MANAGER_FEEDBACK, {"going_well": [{"point": "Led it"}]}),
                  "going_well must be a list of points"),
                 ("text where a value is due", manager, changed(MANAGER_FEEDBACK, {"to_improve": ["Could share more"]}),
                  "to_improve must be a list of points"),
                 ("a value on context", manager,
                  changed(MANAGER_FEEDBACK, {"context": [
                          {"point": "Back in May", "values": []}]}),
                  "context must be a list of points, each a sentence"),
                 ("a feedback with no points", feedback("other"), empty, None),
                 ("a feedback named after its kind", feedback("previous"), {"going_well": []},
                  "the previous feedback must have the parts going_well, to_improve, context"),
                 ("a feedback's value named after its kind", feedback("other"),
                  {**empty,
                      "going_well": [{"point": "Led it", "values": ["Grit"]}]},
                  "the other feedback's going_well: 'Led it'...'s values"),
                 ("notes valid", notes, NOTES, None),
                 ("notes empty", notes, empty, None),
                 ("notes with no evidence", notes,
                  changed(NOTES, {"going_well": [
                          {"point": "Presented it", "values": []}]}),
                  'going_well must be a list of points, each {"point": "...", "values": ["...", ...] or [], '
                  '"evidence": [{"date": "YYYY-MM-DD", "link"'),
                 ("notes' evidence empty", notes,
                  changed(NOTES, {"going_well": [
                          {"point": "Presented it", "values": [], "evidence": []}]}),
                  "going_well must be a list of points"),
                 ("a link not a file's or a web page's", notes,
                  changed(NOTES, {"going_well": [{"point": "Presented it", "values": [],
                                                  "evidence": [{"date": "2026-09-02", "link": "journals/x.md"}]}]}),
                  "going_well must be a list of points"),
                 ("a file:// address", notes,
                  changed(NOTES, {"going_well": [{"point": "Presented it", "values": [],
                                                  "evidence": [{"date": "2026-09-02", "link": "file:///vault/x.md"}]}]}),
                  "going_well must be a list of points"),
                 ("a day no note was taken on", notes,
                  changed(NOTES, {"going_well": [{"point": "Presented it", "values": [],
                                                  "evidence": evidence("2026-09-03")}]}),
                  "evidence must each be of a day the source was read on, each link once"),
                 ("a link twice", notes,
                  changed(NOTES, {"to_improve": [{"point": "Late", "values": [],
                                                  "evidence": evidence("2026-08-20", "2026-08-20")}]}),
                  "each link once"),
                 ("a valued notes point undated", notes,
                  changed(NOTES, {"going_well": [
                          {"point": "Presented it", "values": [], "evidence": evidence(None)}]}),
                  "must each be of a day the source was read on, each link once"),
                 ("a notes context point dated", notes,
                  changed(NOTES, {"context": [{"point": "Moved", "evidence": evidence("2026-08-20")}]}), None),
                 ("a notes context point undated", notes,
                  changed(NOTES, {"context": [{"point": "Moved", "evidence": evidence(None)}]}), None),
                 ("a notes context point a sentence alone", notes, changed(NOTES, {"context": ["Moved"]}),
                  "context must be a list of points"),
                 ("Slack valid", slack, SLACK, None),
                 ("a Slack point with no evidence", slack,
                  changed(SLACK, {"context": [{**SLACK["context"][0], "evidence": []}]}), "must be a list of points"),
                 ("a Slack context point undated, as a message always has a day", slack,
                  changed(SLACK, {"context": [
                          {**SLACK["context"][0], "evidence": [{"date": None, "link": slack_link}]}]}),
                  "must each be of a day the source was read on")]
        for name, check, summary, expected in cases:
            with self.subTest(name):
                problems = check(summary)
                if expected is None:
                    self.assertEqual(problems, [])
                else:
                    self.assertIn(expected, " ".join(problems))

    def test_day_ranges(self):
        # Consecutive days make one range, a day alone stays alone, and the
        # ranges are named in order.
        cases = [([], ""), (["2026-09-01"], "2026-09-01"), (["2026-09-01", "2026-09-02"], "2026-09-01 to 2026-09-02"),
                 (["2026-08-31", "2026-09-01", "2026-09-02", "2026-09-05", "2026-10-01", "2026-10-02"],
                  "2026-08-31 to 2026-09-02, 2026-09-05, 2026-10-01 to 2026-10-02")]
        for days, expected in cases:
            with self.subTest(days):
                self.assertEqual(common.day_ranges(days), expected)

    def test_period_days(self):
        # Every day of the period, its first and last too.
        days = common.period_days(PERSON)
        self.assertEqual((days[0], days[1], days[-1], len(days)),
                         ("2026-08-10", "2026-08-11", "2026-11-10", 93))

    def test_notes_days(self):
        # (the notes' last day, if set): the notes' first and last day, the
        # period's unless a change to the finished prep read them further.
        for notes_end, expected in {None: ("2026-08-10", "2026-11-10"),
                                    "2026-11-21": ("2026-08-10", "2026-11-21")}.items():
            with self.subTest(notes_end):
                person = {**PERSON, **
                          ({"notes_end": notes_end} if notes_end else {})}
                days = common.notes_days(person)
                self.assertEqual((days[0], days[-1]), expected)

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
                  "the Notion searches don't cover 2026-08-24 to 2026-08-30: search those days, and add them"),
                 ("two gaps", S[1:5] + S[6:],
                  "don't cover 2026-08-10 to 2026-08-16, 2026-09-14 to 2026-09-20: search those days"),
                 ("an overlap", S + [{**S[1], "results": []}],
                  "overlap on 2026-08-17 to 2026-08-23: each day is in one search only"),
                 ("beyond the period", S + [{"start": "2026-11-11", "end": "2026-11-11", "results": []}],
                  "go beyond the period, on 2026-11-11"),
                 ("a full search", [{**S[0], "results": full}, *S[1:]],
                  "search that range again in shorter ranges"),
                 ("a page found twice", [S[0], {**S[1], "results": [PLAN_RESULT]}, *S[2:]],
                  "found by two Notion searches, so the creation filter can't be trusted"),
                 ("a row found twice", [
                  S[0], {**S[1], "results": S[0]["results"][2:]}, *S[2:]], None),
                 ("a page without its url", [{**S[0], "results": [
                     {k: v for k, v in PLAN_RESULT.items() if k != "url"}]}, *S[1:]], "its title and url"),
                 ("a result without its type", [{**S[0], "results": [
                     {k: v for k, v in PLAN_RESULT.items() if k != "type"}]}, *S[1:]], "must have its type"),
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

    def test_observations_content_problems(self):
        # name: (observations_content.json, going well's and to improve's
        # groups, by value or None, and context's points, expected in its
        # problems, or None for none): in a valued table, a summary for each
        # value worth saying, of the values its table groups points under, at
        # least one when it has any, and also only when it has points under
        # no value; each within its words, naming no id; context empty exactly
        # when its table holds no point.
        def part(values, also=None):
            return {"values": values, "also": also}
        summaries = {"going_well": part({"Teamwork": "Good."}), "to_improve": part({}, "Better."),
                     "context": "Moved team."}
        groups = (["Teamwork", None], [None], 1)
        long = "word " * (common.MAX_WORDS["value"] + 1)
        cases = [("all summarised", summaries, groups, None),
                 ("some values only", {**summaries, "going_well": part({"Teamwork": "Good."})},
                  (["Teamwork", "Ownership"], [None], 1), None),
                 ("no value summarised", {
                  **summaries, "going_well": part({})}, groups, "summarises no value"),
                 ("a value its table doesn't hold", {**summaries, "going_well": part({"Craft": "Good."})}, groups,
                  "summarises Craft, which its table groups no point under"),
                 ("also with no point under no value", {**summaries, "to_improve": part({"Ownership": "Better."},
                                                                                        "And more.")},
                  (["Teamwork", None], ["Ownership"], 1), "also must be null"),
                 ("a value too long", {**summaries, "going_well": part({"Teamwork": long})}, groups,
                  f"more than {common.WORDS['value']}: cut it"),
                 ("an id in a value", {**summaries, "going_well": part({"Teamwork": "Good, as G3 says."})}, groups,
                  "names G3"),
                 ("an empty value", {
                  **summaries, "going_well": part({"Teamwork": " "})}, groups, "is empty"),
                 ("no point to improve", {
                  **summaries, "to_improve": part({})}, (["Teamwork", None], [], 1), None),
                 ("context too long", {**summaries, "context": "word " * (common.MAX_WORDS["context"] + 1)},
                  groups, f"more than {common.WORDS['context']}: cut it"),
                 ("a field missing", {"going_well": summaries["going_well"], "to_improve": summaries["to_improve"]},
                  groups, 'must be {"going_well"'),
                 ("a part as a text", {
                  **summaries, "going_well": "Good."}, groups, 'must be {"going_well"'),
                 ("context not summarised", {
                  **summaries, "context": ""}, groups, "context is empty"),
                 ("context of no point", summaries,
                  (["Teamwork", None], [None], 0), "context must be empty"),
                 ("no context", {**summaries, "context": ""}, (["Teamwork", None], [None], 0), None)]
        for name, content, counts, expected in cases:
            with self.subTest(name):
                *valued, context = counts
                observations = {**{name: [{"value": value} for value in values]
                                   for name, values in zip(("going_well", "to_improve"), valued)},
                                "context": [{"point": "Moved team"}] * context}
                problems = " ".join(common.observations_content_problems(
                    content, {"observations": observations}))
                if expected is None:
                    self.assertEqual(problems, "")
                else:
                    self.assertIn(expected, problems)

    def test_step_change_content_problems(self):
        # name: (a change to the fixture's step change, the previous
        # feedback, expected in its problems, or None for none): against the
        # previous feedback, each to-improve point has at least one row,
        # improved, still_to_improve or worsened, a row for each aspect that
        # went differently, which may conflict; a going-well point held or worsened;
        # a previous context point context_change; a row with no previous point
        # new_context, citing a period context point; each change but improved cites period
        # points by id, each once; the summary not
        # empty nor over its ceiling; null exactly when there is no previous point.
        step = STEP_CHANGE_CONTENT
        rows = step["rows"]

        def row(previous_point, change, *evidence):
            return {"previous_point": previous_point, "change": change, "evidence": list(evidence)}
        context_review = {
            **PREVIOUS, "context": [{"id": "P-C1", "point": "Was new to billing"}]}
        long = "word " * (common.MAX_WORDS["step_change"] + 1)
        cases = [("as written", step, PREVIOUS, None),
                 ("only the to-improve rows", {**step, "rows": [row("P-I1", "improved"),
                                                                row("P-I2", "worsened", "I2")]},
                  PREVIOUS, None),
                 ("improved with evidence", {**step, "rows": [row("P-I1", "improved", "G2"),
                                                              row("P-I2", "improved")]}, PREVIOUS, None),
                 ("a previous context point", {**step, "rows": [*rows, row("P-C1", "context_change", "C2")]},
                  context_review, None),
                 ("a previous context point new", {**step, "rows": [*rows, row("P-C1", "new_context", "C2")]},
                  context_review, "row 5's change, 'new_context', must be context_change for a context point"),
                 ("two rows with no previous point", {**step, "rows": [*rows, row(None, "new_context", "C2")]},
                  PREVIOUS, None),
                 ("no previous feedback, null", None, None, None),
                 ("no previous feedback, a step change", step, None, "must be null"),
                 ("a previous feedback, null", None,
                  PREVIOUS, "must be {\"summary\""),
                 ("a to-improve point with no row", {**step, "rows": rows[:1]}, PREVIOUS,
                  "no row for P-I1, P-I2"),
                 ("a to-improve point held", {**step, "rows": [*rows[:3], row("P-I1", "held", "G1")]},
                  PREVIOUS, "row 4's change, 'held', must be improved or still_to_improve or worsened"),
                 ("a going-well point improved", {**step, "rows": [row("P-G1", "improved"), *rows[1:]]},
                  PREVIOUS, "row 1's change, 'improved', must be held or worsened"),
                 ("a row with no previous point not context", {**step, "rows": [*rows, row(None, "worsened", "I1")]},
                  PREVIOUS, "must be new_context for a row with no previous_point"),
                 ("a row with no previous point changed", {**step, "rows": [*rows, row(None, "context_change", "C2")]},
                  PREVIOUS, "row 5's change, 'context_change', must be new_context for a row with no "
                  "previous_point"),
                 ("a row with no previous point citing no context",
                  {**step, "rows": [*rows,
                                    row(None, "new_context", "G1")]}, PREVIOUS,
                  "row 5 has no previous_point, so its evidence must cite the period context point"),
                 ("still to improve with no evidence", {**step, "rows": [*rows[:1], row("P-I2", "still_to_improve"),
                                                                         *rows[2:]]},
                  PREVIOUS, "row 2's evidence is empty"),
                 ("held with no evidence", {**step, "rows": [row("P-G1", "held"), *rows[1:]]},
                  PREVIOUS, "row 1's evidence is empty"),
                 ("an id that isn't a period point", {**step, "rows": [row("P-G1", "held", "G9"), *rows[1:]]},
                  PREVIOUS, "row 1's evidence names G9, not points of the period"),
                 ("an id cited twice", {**step, "rows": [row("P-G1", "held", "G3", "G3"), *rows[1:]]},
                  PREVIOUS, "row 1's evidence names a point more than once"),
                 ("a previous point that isn't one", {**step, "rows": [*rows, row("P-G2", "held", "G1")]},
                  PREVIOUS, "row 5's previous_point, 'P-G2', must be one of the previous feedback's points"),
                 ("a previous point twice, an aspect each", {**step, "rows": [
                     row("P-I1", "improved", "G2"), row("P-I1", "still_to_improve", "I1"), *rows[1:3]]},
                  PREVIOUS, None),
                 ("a previous point twice, the same change", {**step, "rows": [*rows, row("P-I1", "improved")]},
                  PREVIOUS, None),
                 ("a previous point twice, one with no evidence to cite", {**step, "rows": [
                     *rows, row("P-I1", "still_to_improve")]}, PREVIOUS, "row 5's evidence is empty"),
                 ("a to-improve point with only the other's rows", {**step, "rows": [
                     row("P-I1", "improved", "G2"), row("P-I1", "still_to_improve", "I1"), rows[0]]},
                  PREVIOUS, "no row for P-I2"),
                 ("a row's field missing", {**step, "rows": [*rows, {"previous_point": "P-I1", "change": "improved"}]},
                  PREVIOUS, "row 5 must be"),
                 ("an empty summary", {**step, "summary": " "},
                  PREVIOUS, "summary is empty"),
                 ("a summary too long", {**step, "summary": long}, PREVIOUS,
                  f"summary has {common.MAX_WORDS['step_change'] + 1} words, more than "
                  f"{common.WORDS['step_change']}: cut it to about "
                  f"{common.WORDS['step_change']}")]
        for name, step_change, previous, expected in cases:
            with self.subTest(name):
                problems = " ".join(common.step_change_content_problems(
                    step_change, {"observations": OBSERVATIONS, "previous": previous}))
                if expected is None:
                    self.assertEqual(problems, "")
                else:
                    self.assertIn(expected, problems)
                    self.assertNotIn(
                        str(common.MAX_WORDS["step_change"]), problems)

    def test_point_ids(self):
        # name: (part, place, prefix, id): by part and place, a previous
        # feedback's prefixed.
        cases = [("going well", "going_well", 1, "", "G1"), ("to improve", "to_improve", 2, "", "I2"),
                 ("context", "context", 3, "", "C3"), ("a previous feedback's",
                                                       "to_improve", 1, common.PREVIOUS_ID, "P-I1")]
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
