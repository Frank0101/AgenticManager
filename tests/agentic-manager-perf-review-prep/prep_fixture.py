"""What the skill's tests share: an invented person, with the review's period
and who they are in each source, the current manager feedback, other feedback, previous feedback, notes, work, Slack and company
values, a Slack conversation a reading lists, and an output folder of the
test's own."""
import json
import os
import tempfile
from datetime import date, timedelta
from urllib.parse import quote
from unittest import mock

import common  # noqa: F401  (puts the library on the path)
import make_report
from agentic_manager import config, output_folder

PREP = "Jane-Doe_26-11-10"
JIRA_ACCOUNT = {"id": "5b10ac8d82e05b22cc7d4ef5",
                "name": "Jane Doe", "email": "jane@acme.test"}
PERSON = {"person": "Jane Doe", "start": "2026-08-10", "end": "2026-11-10",
          "sources": {"jira-api": JIRA_ACCOUNT, "github-cli": {"id": "janedoe", "name": "Jane Doe"},
                      "notion-mcp": {"id": "2a4c1e8f-1234-4abc-9def-0123456789ab", "name": "Jane Doe"},
                      "slack-mcp": {"id": "U012AB3CD", "name": "Jane Doe"},
                      "logseq-fs": {"links": ["Jane", "Jane Promotion"]}}}
# The current manager feedback and the other feedback of the period, whose
# points join the observations: the manager's name no value, so they come
# after the others, their context empty so the context points keep their
# ids; and the previous feedback, the step change's baseline.
MANAGER_FEEDBACK = {"going_well": [{"point": "Has led the billing migration well since May", "values": []}],
                    "to_improve": [{"point": "Could share progress with the wider team more often", "values": []}],
                    "context": []}
OTHER_FEEDBACK = {"going_well": [{"point": "Agreed to own the billing migration and has kept to its plan",
                                  "values": ["Ownership"]}],
                  "to_improve": [{"point": "Could raise risks earlier in planning", "values": ["Ownership"]}],
                  "context": ["Is preparing a promotion case with the manager"]}
PREVIOUS_FEEDBACK = {"going_well": [{"point": "Delivered the billing migration on time", "values": ["Ownership"]}],
                     "to_improve": [{"point": "Could lead a design review alone", "values": ["Teamwork"]},
                                    {"point": "Flagged delays only when asked", "values": ["Ownership"]}],
                     "context": []}
NOTES = {"going_well": [{"point": "Presented the migration to the wider team", "values": ["Teamwork", "Ownership"],
                         "evidence": [{"date": "2026-09-02", "link": "/vault/journals/2026_09_02.md"}]}],
         "to_improve": [{"point": "Didn't flag delays until asked, many times", "values": ["Ownership"],
                         "evidence": [{"date": "2026-10-01", "link": "/vault/journals/2026_10_01.md"},
                                      {"date": "2026-08-20", "link": "/vault/journals/2026_08_20.md"}]}],
         "context": [{"point": "Moved to the payments team in the summer",
                      "evidence": [{"date": None, "link": "/vault/pages/Jane.md"}]}]}
# The work's items, as data.json records them, in PERSON's period.
WORK_ITEMS = {"jira": {"created": [{"key": "PROJ-13", "title": "Retire old billing", "type": "Task", "epic": None,
                                    "status": "In Progress", "url": "https://acme.atlassian.net/browse/PROJ-13",
                                    "date": "2026-08-20", "points": None}],
                       "resolved": [{"key": "PROJ-12", "title": "Migrate billing", "type": "Story",
                                     "epic": {"key": "PROJ-1", "title": "Billing",
                                              "url": "https://acme.atlassian.net/browse/PROJ-1"}, "status": "Done",
                                     "url": "https://acme.atlassian.net/browse/PROJ-12", "date": "2026-09-01",
                                     "points": 3}]},
              "github": {"opened": [{"repo": "acme/billing", "number": 1, "title": "Migrate billing",
                                     "url": "https://github.com/acme/billing/pull/1", "date": "2026-08-28",
                                     "lines": 150, "files": 4}],
                         "merged": [{"repo": "acme/billing", "number": 1, "title": "Migrate billing",
                                     "url": "https://github.com/acme/billing/pull/1", "date": "2026-09-01",
                                     "lines": 150, "files": 4}]},
              "notion": {"created": [{"title": "Billing plan", "url": "https://www.notion.so/billing-plan",
                                      "path": "Engineering / Billing", "space": "Engineering",
                                      "between": ["2026-08-10", "2026-08-16"]}]}}
# Notion's searches for PERSON's period, 10/08/2026, a Monday, to
# 10/11/2026, a week at a time, the last of two days: the first finds the
# billing plan, a database and a database's row, as the search returns them.
PLAN_RESULT = {"id": "1a2b", "title": "Billing plan", "url": "https://www.notion.so/billing-plan", "type": "page",
               "timestamp": "2026-09-02T10:00:00.000Z", "path": "Engineering / Billing"}
NOTION_SEARCHES = [{"start": (monday := date(2026, 8, 10) + timedelta(weeks=n)).isoformat(),
                    "end": min(monday + timedelta(days=6), date(2026, 11, 10)).isoformat(),
                    "results": [PLAN_RESULT, {**PLAN_RESULT, "id": "3c4d", "title": "Tasks", "type": "database",
                                              "url": "https://www.notion.so/tasks"},
                                {**PLAN_RESULT, "id": "5e6f", "title": "Fix the build", "url": "https://www.notion.so/fix",
                                 "parent_data_source_url": "collection://7a8b"}] if n == 0 else []}
                   for n in range(14)]
# The raw files data.json is built from: what Jira and gh return, with the
# period and the searches, and Notion's pages as recorded.
JIRA_ID = PERSON["sources"]["jira-api"]["id"]
JIRA_BASE = "https://acme.atlassian.net"
JQL = {"resolved": f'assignee = "{JIRA_ID}" AND statusCategory = Done AND resolutiondate >= "2026-08-10" '
       'AND resolutiondate <= "2026-11-10 23:59"',
       "created": f'reporter = "{JIRA_ID}" AND created >= "2026-08-10" AND created <= "2026-11-10 23:59"'}
QUERY = {"opened": "is:pr author:janedoe created:2026-08-10..2026-11-10 org:acme",
         "merged": "is:pr is:merged author:janedoe merged:2026-08-10..2026-11-10 org:acme"}
PULL = {"number": 1, "title": "Migrate billing", "repository": {"nameWithOwner": "acme/billing"},
        "url": "https://github.com/acme/billing/pull/1", "createdAt": "2026-08-28T10:00:00Z",
        "mergedAt": "2026-09-01T10:00:00Z", "additions": 120, "deletions": 30, "changedFiles": 4,
        "author": {"login": "janedoe"}, "updatedAt": "2026-09-01T10:00:00Z"}
POINTS = "customfield_10016"
WORK_RAW = {"jira": {"start": "2026-08-10", "end": "2026-11-10", "base_url": JIRA_BASE, "points_fields": [POINTS],
                     "resolved_jql": JQL["resolved"], "created_jql": JQL["created"], "parents": [],
                     "resolved": [{"key": "PROJ-12", "fields": {
                         "summary": "Migrate billing", "issuetype": {"name": "Story", "subtask": False}, "status": {"name": "Done"},
                         "created": "2026-08-12T10:00:00.000+0100", "resolutiondate": "2026-09-01T10:00:00.000+0100",
                         "parent": {"key": "PROJ-1", "fields": {"summary": "Billing", "issuetype": {"name": "Epic", "subtask": False}}},
                         "assignee": {"accountId": JIRA_ID}, "reporter": {"accountId": "a2"}, POINTS: 3,
                         "updated": "2026-09-01T10:00:00.000+0100"}}],
                     "created": [{"key": "PROJ-13", "fields": {
                         "summary": "Retire old billing", "issuetype": {"name": "Task", "subtask": False},
                         "status": {"name": "In Progress"}, "created": "2026-08-20T10:00:00.000+0100",
                         "resolutiondate": None, "assignee": None, "reporter": {"accountId": JIRA_ID},
                         "updated": "2026-08-20T10:00:00.000+0100"}}]},
            "github": {"start": "2026-08-10", "end": "2026-11-10", "orgs": ["acme"],
                       "opened_query": QUERY["opened"], "merged_query": QUERY["merged"],
                       "opened": [PULL], "merged": [PULL]},
            "notion": {"created": NOTION_SEARCHES}}
# data.json as built from them, its facts worked out by hand: PERSON's period,
# 10/08/2026, a Monday, to 10/11/2026, is fourteen weeks, the last of two days.
WEEKS = [[(monday := date(2026, 8, 10) + timedelta(weeks=n)).isoformat(),
          min(monday + timedelta(days=6), date(2026, 11, 10)).isoformat()] for n in range(14)]


def weekly(*indexes):
    """A week-by-week series over WEEKS, one item for each time a week's
    index is in `indexes`."""
    return [indexes.count(n) for n in range(len(WEEKS))]


# The Observations section's points, worked out by hand from
# OTHER_FEEDBACK, NOTES and SLACK, each with its id by its place: going
# well, under Teamwork, which has the most, Slack's, of 3 September, before
# the notes', of 2 September, then under Ownership the other feedback's; to
# improve, under Ownership, the other feedback's, which has no date, first,
# then the notes' point, its evidence the most recent first; context, not
# grouped, the other feedback's point first, undated, then the notes' point,
# as its one evidence, a page's, is undated, then Slack's, of 20 August.
OBSERVATIONS = {
    "going_well": [
        {"value": "Teamwork", "points": [
            {"id": "G1", "point": "Explained the outage's cause in the incident channel, and colleagues thanked them", "also": None,
             "source": "slack", "date": "2026-09-03",
             "evidence": [{"date": "2026-09-03", "link": "https://acme.slack.com/archives/C1/p1"}]},
            {"id": "G2", "point": "Presented the migration to the wider team", "also": "Ownership", "source": "notes", "date": "2026-09-02",
             "evidence": [{"date": "2026-09-02", "link": "/vault/journals/2026_09_02.md"}]}]},
        {"value": "Ownership", "points": [
            {"id": "G3", "point": "Agreed to own the billing migration and has kept to its plan", "also": None, "source": "other",
             "date": None, "evidence": []}]},
        {"value": None, "points": [
            {"id": "G4", "point": "Has led the billing migration well since May", "also": None, "source": "manager",
             "date": None, "evidence": []}]}],
    "to_improve": [
        {"value": "Ownership", "points": [
            {"id": "I1", "point": "Could raise risks earlier in planning", "also": None, "source": "other",
             "date": None, "evidence": []},
            {"id": "I2", "point": "Didn't flag delays until asked, many times", "also": None, "source": "notes", "date": "2026-10-01",
             "evidence": [{"date": "2026-10-01", "link": "/vault/journals/2026_10_01.md"},
                          {"date": "2026-08-20", "link": "/vault/journals/2026_08_20.md"}]}]},
        {"value": None, "points": [
            {"id": "I3", "point": "Could share progress with the wider team more often", "also": None, "source": "manager",
             "date": None, "evidence": []}]}],
    "context": [
        {"id": "C1", "point": "Is preparing a promotion case with the manager", "source": "other", "date": None,
         "evidence": []},
        {"id": "C2", "point": "Moved to the payments team in the summer", "source": "notes", "date": None,
         "evidence": [{"date": None, "link": "/vault/pages/Jane.md"}]},
        {"id": "C3", "point": "Posted the billing rollout plan in a cross-team channel", "source": "slack", "date": "2026-08-20",
         "evidence": [{"date": "2026-08-20", "link": "https://acme.slack.com/archives/C2/p2"}]}]}
# The previous feedback as data.json holds it: PREVIOUS_FEEDBACK, each point
# with its id by its part and place.
PREVIOUS = {
    "going_well": [{"id": "P-G1", "point": "Delivered the billing migration on time",
                    "values": ["Ownership"]}],
    "to_improve": [{"id": "P-I1", "point": "Could lead a design review alone", "values": ["Teamwork"]},
                   {"id": "P-I2", "point": "Flagged delays only when asked", "values": ["Ownership"]}],
    "context": []}
DATA = {"weeks": WEEKS,
        "jira": {**WORK_ITEMS["jira"], "counts": {"created": 1, "resolved": 1},
                 "epic_order": ["PROJ-1"],
                 "created_by_week": {"total": weekly(1), "epics": {}, "other": weekly(), "no_epic": weekly(1)},
                 "resolved_by_week": {"total": weekly(3), "epics": {"PROJ-1": weekly(3)}, "other": weekly(),
                                      "no_epic": weekly()},
                 "points_by_epic": [{"points": 3, "issues": 1, "epics": {"PROJ-1": 1}, "other": 0, "no_epic": 0}],
                 "created_by_type": [{"type": "Task", "issues": 1}],
                 "resolved_by_type": [{"type": "Story", "issues": 1}],
                 "resolved_by_epic": {"epics": [{"key": "PROJ-1", "title": "Billing",
                                                 "url": f"{JIRA_BASE}/browse/PROJ-1", "issues": 1}], "other": 0},
                 "focus": [{"key": "PROJ-1", "title": "Billing", "url": f"{JIRA_BASE}/browse/PROJ-1", "issues": 1,
                            "share": 100}],
                 "resolved_points": {"total": 3, "estimated": 1, "average": 3.0},
                 "epic_search_urls": {"PROJ-1": f"{JIRA_BASE}/issues/?jql={quote(JQL['resolved'] + ' AND (parent = PROJ-1)')}"},
                 "no_epic_search_url": None,
                 "resolved_points_search_url":
                     f"{JIRA_BASE}/issues/?jql={quote(JQL['resolved'] + ' AND (cf[10016] is not EMPTY)')}",
                 **{f"{name}_search_url": f"{JIRA_BASE}/issues/?jql={quote(jql)}" for name, jql in JQL.items()}},
        "github": {**WORK_ITEMS["github"], "counts": {"opened": 1, "merged": 1},
                   "merged_by_repo": {"repos": [{"repo": "acme/billing", "prs": 1}], "other": 0},
                   "focus": [{"repo": "acme/billing", "prs": 1, "share": 100}], "repo_order": ["acme/billing"],
                   "repo_counts": {"opened": 1, "merged": 1},
                   "opened_by_week": {"total": weekly(2), "repos": {"acme/billing": weekly(2)}, "other": weekly()},
                   "merged_by_week": {"total": weekly(3), "repos": {"acme/billing": weekly(3)}, "other": weekly()},
                   "merged_lines": {"median": 150},
                   # 150 lines: 10 ** 2.17, in the ninth of twelve bins, four
                   # to each power of ten up to 1,000.
                   "lines_distribution": {"total": [int(n == 8) for n in range(12)],
                                          "repos": {"acme/billing": [int(n == 8) for n in range(12)]},
                                          "other": [0] * 12},
                   **{f"{name}_search_url": f"https://github.com/search?q={quote(query)}&type=pullrequests"
                      for name, query in QUERY.items()}, "merged_lines_search_url": None,
                   "repo_search_urls": {"acme/billing": "https://github.com/search?q="
                                        f"{quote(QUERY['merged'].replace(' org:acme', '') + ' repo:acme/billing')}"
                                        "&type=pullrequests"}},
        "notion": {"created": [{**page, "week": ["2026-08-10", "2026-08-16"]} for page in WORK_ITEMS["notion"]["created"]],
                   "counts": {"created": 1}},
        "observations": OBSERVATIONS, "previous": PREVIOUS}
# Two more Jira models, worked out by hand, each changing DATA's resolved
# issues and the facts they give. In the first, the issues with no epic hold
# the most, so the main focus lists them before the epic: PROJ-12 and PROJ-14
# in PROJ-1, PROJ-15 to PROJ-17 in none, all resolved in the fourth week, and
# 80% of the five is four, which takes both.
BILLING = WORK_ITEMS["jira"]["resolved"][0]
NO_EPIC_FIRST = [BILLING, {**BILLING, "key": "PROJ-14", "url": f"{JIRA_BASE}/browse/PROJ-14", "points": None},
                 *({**BILLING, "key": f"PROJ-{n}", "type": "Task", "epic": None, "url": f"{JIRA_BASE}/browse/PROJ-{n}",
                    "points": None} for n in (15, 16, 17))]
DATA_NO_EPIC_FIRST = {**DATA, "jira": {
    **DATA["jira"], "resolved": NO_EPIC_FIRST, "counts": {"created": 1, "resolved": 5},
    "resolved_by_week": {"total": weekly(3, 3, 3, 3, 3), "epics": {"PROJ-1": weekly(3, 3)}, "other": weekly(),
                         "no_epic": weekly(3, 3, 3)},
    "resolved_by_type": [{"type": "Task", "issues": 3}, {"type": "Story", "issues": 2}],
    "resolved_by_epic": {"epics": [{"key": None, "title": None, "url": None, "issues": 3},
                                   {"key": "PROJ-1", "title": "Billing", "url": f"{JIRA_BASE}/browse/PROJ-1",
                                    "issues": 2}], "other": 0},
    "focus": [{"key": None, "title": None, "url": None, "issues": 3, "share": 60},
              {"key": "PROJ-1", "title": "Billing", "url": f"{JIRA_BASE}/browse/PROJ-1", "issues": 2, "share": 40}],
    "no_epic_search_url": f"{JIRA_BASE}/issues/?jql={quote(JQL['resolved'] + ' AND key in (PROJ-15, PROJ-16, PROJ-17)')}"}}
# In the second, no resolved issue has an epic, so the main focus lists their
# project, and no epic is coloured.
DATA_BY_PROJECT = {**DATA, "jira": {
    **DATA["jira"], "resolved": [{**BILLING, "epic": None}], "epic_order": [],
    "resolved_by_week": {"total": weekly(3), "epics": {}, "other": weekly(), "no_epic": weekly(3)},
    "points_by_epic": [{"points": 3, "issues": 1, "epics": {}, "other": 0, "no_epic": 1}],
    "resolved_by_epic": {"epics": [{"key": None, "title": None, "url": None, "issues": 1}], "other": 0},
    "focus": [{"key": "PROJ", "title": None, "url": None, "issues": 1, "share": 100}], "epic_search_urls": {},
    "no_epic_search_url": f"{JIRA_BASE}/issues/?jql={quote(JQL['resolved'] + ' AND key in (PROJ-12)')}"}}
SLACK = {"going_well": [{"point": "Explained the outage's cause in the incident channel, and colleagues thanked them",
                         "values": ["Teamwork"],
                         "evidence": [{"date": "2026-09-03", "link": "https://acme.slack.com/archives/C1/p1"}]}],
         "to_improve": [],
         "context": [{"point": "Posted the billing rollout plan in a cross-team channel",
                      "evidence": [{"date": "2026-08-20", "link": "https://acme.slack.com/archives/C2/p2"}]}]}
# A conversation a Slack reading lists: its day, link and description.
SLACK_LINK = "https://acme.slack.com/archives/C1/p1"
SLACK_ITEM = {"date": "2026-08-20", "link": SLACK_LINK,
              "description": "In a cross-team channel, posted the billing rollout plan; three people asked follow-ups"}
VALUES = [{"value": "Ownership", "meaning": "Sees work through to its end"},
          {"value": "Teamwork", "meaning": "Succeeds with others"}]
VALUE_NAMES = [value["value"] for value in VALUES]
# Where the report is written, beside the vault, for the links to notes,
# which it writes relative to it.
REPORT_FOLDER = "/vault/.out/perf-review-preps/Jane-Doe_26-11-10"
# The summaries data.json is built from, by their name.
SUMMARIES = {"manager": MANAGER_FEEDBACK, "other": OTHER_FEEDBACK, "previous": PREVIOUS_FEEDBACK,
             "notes": NOTES, "slack": SLACK}
# The agent's summaries of the three tables and its step change, and the
# briefs it writes them from, worked out by hand from DATA: the work's main
# focus, and each table's points in its order, with the values each names, its
# source and when it was seen, and for the step change their ids and the
# previous feedback.
OBSERVATIONS_CONTENT = {"going_well": {"values": {
    "Teamwork": "Jane explains outages to the teams around them and presented the billing migration to the wider team.",
    "Ownership": "Jane has owned the billing migration and kept to its plan."}, "also": None},
    "to_improve": {"values": {"Ownership": "Jane flagged delays only when asked, many times, and should raise them early."},
                   "also": "Jane could share progress with the wider team more often."},
    "context": "Jane moved to the payments team in the summer and is preparing a promotion case with the manager."}
# The design review is no longer raised; flagging delays, raised in
# the previous feedback, still is; the migration held; and the move to
# payments, a period context point, is new since it.
STEP_CHANGE_CONTENT = {"summary": "Jane no longer needs support to lead a design review, but still flags delays only when "
                       "asked, as the previous feedback said.",
                       "rows": [{"previous_point": "P-G1", "change": "held", "evidence": ["G3"]},
                                {"previous_point": "P-I2", "change": "still_to_improve",
                                 "evidence": ["I2", "I1"]},
                                {"previous_point": None, "change": "new_context",
                                 "evidence": ["C2"]},
                                {"previous_point": "P-I1", "change": "improved", "evidence": []}]}
# A variant whose previous feedback has a context point, P-C1, that changed
# in the period, C1: its row, context_change, comes before the new context's.
CONTEXT_POINT = "Had no promotion case planned yet"
CONTEXT_SUMMARIES = {**SUMMARIES, "previous": {**
                                               PREVIOUS_FEEDBACK, "context": [CONTEXT_POINT]}}
CONTEXT_DATA = {**DATA, "previous": {**PREVIOUS,
                                     "context": [{"id": "P-C1", "point": CONTEXT_POINT}]}}
CONTEXT_STEP_CHANGE = {**STEP_CHANGE_CONTENT, "rows": [
    *STEP_CHANGE_CONTENT["rows"], {"previous_point": "P-C1", "change": "context_change", "evidence": ["C1"]}]}
STEP_CHANGE_BRIEF = {"person": "Jane Doe",
                     "going_well": [{"id": "G1", "point": "Explained the outage's cause in the incident channel, and colleagues "
                                     "thanked them", "values": ["Teamwork"], "source": "Slack", "when": "2026-09-03"},
                                    {"id": "G2", "point": "Presented the migration to the wider team",
                                     "values": ["Teamwork", "Ownership"], "source": "Manager's notes", "when": "2026-09-02"},
                                    {"id": "G3", "point": "Agreed to own the billing migration and has kept to its plan",
                                     "values": ["Ownership"], "source": "Other feedback", "when": None},
                                    {"id": "G4", "point": "Has led the billing migration well since May", "values": [],
                                     "source": "Manager feedback", "when": None}],
                     "to_improve": [{"id": "I1", "point": "Could raise risks earlier in planning", "values": ["Ownership"],
                                     "source": "Other feedback", "when": None},
                                    {"id": "I2", "point": "Didn't flag delays until asked, many times", "values": ["Ownership"],
                                     "source": "Manager's notes", "when": "2026-10-01"},
                                    {"id": "I3", "point": "Could share progress with the wider team more often", "values": [],
                                     "source": "Manager feedback", "when": None}],
                     "context": [{"id": "C1", "point": "Is preparing a promotion case with the manager",
                                  "source": "Other feedback", "when": None},
                                 {"id": "C2", "point": "Moved to the payments team in the summer", "source": "Manager's notes",
                                  "when": None},
                                 {"id": "C3", "point": "Posted the billing rollout plan in a cross-team channel", "source": "Slack",
                                  "when": "2026-08-20"}],
                     "previous": PREVIOUS}
OBSERVATIONS_BRIEF = {"person": "Jane Doe", "values": VALUES,
                      "focus": {"github": [{"repo": "acme/billing", "prs": 1, "share": 100}],
                                "jira": [{"key": "PROJ-1", "title": "Billing", "issues": 1, "share": 100}]},
                      **{part: [{key: value for key, value in point.items() if key != "id"} for point in STEP_CHANGE_BRIEF[part]]
                          for part in ("going_well", "to_improve", "context")}}


def temp_output(test):
    """The skill's output folder in a temporary folder, for `test`: a config
    of its own setting the output root, never the developer's."""
    tmp = tempfile.TemporaryDirectory()
    test.addCleanup(tmp.cleanup)
    root = os.path.realpath(tmp.name)
    os.makedirs(os.path.join(root, "system-temp"))
    path = os.path.join(root, "config.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"sources": {}, "output": {"root": os.path.join(root, "out")},
                   "company": {"values": VALUES}}, f)
    for target, attribute, value in ((config, "CONFIG_PATH", path),
                                     (output_folder, "TEMP_ROOT",
                                      os.path.join(root, "temp")),
                                     (tempfile, "tempdir", os.path.join(root, "system-temp"))):
        patcher = mock.patch.object(target, attribute, value)
        patcher.start()
        test.addCleanup(patcher.stop)
    return os.path.join(root, "out", "perf-review-preps")


# The agent's account of the work and its impact, from DATA: the billing
# migration, whose latest evidence is G2, seen on 2 September, comes before
# the retirement of the old billing, an issue created on 20 August; and the
# brief it is written from, worked out by hand: the issues by epic, those
# with none as one more group, the pull requests by repository and the
# pages, each group by its latest item, then every point with its id.
BILLING_EVIDENCE = [f"{JIRA_BASE}/browse/PROJ-1", "https://github.com/acme/billing/pull/1",
                    "https://www.notion.so/billing-plan", "G3", "G2"]
WORK_IMPACT_CONTENT = {"initiatives": [
    {"title": "Billing migration", "impact": "The payments team moved off the old billing system.", "paragraph": "Jane led the billing migration from its plan to its rollout, "
     "keeping to the plan the payments team relied on.", "evidence": BILLING_EVIDENCE},
    {"title": "Old billing retirement", "impact": "The old billing system began to wind down.", "paragraph": "Jane started retiring the old billing system.",
     "evidence": [f"{JIRA_BASE}/browse/PROJ-13"]}]}
# A work and impact that cites a point alone, for a data.json whose items
# differ from DATA's.
POINT_WORK_IMPACT = {"initiatives": [{"title": "Outages", "impact": "The teams around Jane understood the outage.", "paragraph": "Jane explained an outage's cause to the teams "
                                      "around them.", "evidence": ["G1"]}]}
# The work before the period, from PREVIOUS_FEEDBACK as DATA holds it, and
# its brief.
EARLIER_WORK_CONTENT = {"bullets": [
    "Jane delivered the billing migration on time, as the previous feedback recorded."]}
EARLIER_WORK_BRIEF = {"person": "Jane Doe",
                      "previous": {"going_well": ["Delivered the billing migration on time"],
                                   "to_improve": ["Could lead a design review alone", "Flagged delays only when asked"],
                                   "context": []}}
WORK_IMPACT_BRIEF = {"person": "Jane Doe",
                     "epics": [{"key": "PROJ-1", "title": "Billing", "url": f"{JIRA_BASE}/browse/PROJ-1", "items": 1,
                                "recent": [{"key": "PROJ-12", "title": "Migrate billing",
                                            "url": f"{JIRA_BASE}/browse/PROJ-12", "status": "Done",
                                            "date": "2026-09-01"}]},
                               {"key": None, "title": None, "url": None, "items": 1,
                                "recent": [{"key": "PROJ-13", "title": "Retire old billing",
                                            "url": f"{JIRA_BASE}/browse/PROJ-13", "status": "In Progress",
                                            "date": "2026-08-20"}]}],
                     "pull_requests": [{"repo": "acme/billing", "search_url": DATA["github"]["repo_search_urls"]["acme/billing"],
                                        "items": 1, "recent": [{"title": "Migrate billing",
                                                                "url": "https://github.com/acme/billing/pull/1",
                                                                "date": "2026-09-01"}]}],
                     "notion": [{"title": "Billing plan", "url": "https://www.notion.so/billing-plan",
                                 "path": "Engineering / Billing", "date": "2026-08-16"}],
                     **{part: STEP_CHANGE_BRIEF[part] for part in ("going_well", "to_improve", "context")}}


def write_prep(folder, person=PERSON, prep=PREP, manager=MANAGER_FEEDBACK,
               other=OTHER_FEEDBACK, previous=PREVIOUS_FEEDBACK, notes=NOTES, data=DATA, slack=SLACK, raw_work=WORK_RAW,
               observations_brief=OBSERVATIONS_BRIEF, observations_content=OBSERVATIONS_CONTENT, step_change_brief=STEP_CHANGE_BRIEF, step_change_content=STEP_CHANGE_CONTENT,
               work_impact_brief=WORK_IMPACT_BRIEF, work_impact_content=WORK_IMPACT_CONTENT,
               earlier_work_brief=EARLIER_WORK_BRIEF, earlier_work_content=EARLIER_WORK_CONTENT, report=True):
    """Writes the prep `prep` in the output folder `folder`, holding `person`,
    `manager`, `other`, `previous`, `notes`, `data`, `slack`, `observations_brief`,
    `observations_content`, `step_change_brief`, `step_change_content`, `work_impact_brief`,
    `work_impact_content`, `earlier_work_brief` and `earlier_work_content`, each left out when None, the _raw folder, with
    `raw_work`, each source's raw file, unless None, and, with `report` and
    both a person and data, the report as finish_report.py writes it, with
    its charts, each an empty drawing, its summaries OBSERVATIONS_CONTENT's when
    `observations_content` is None, its step change STEP_CHANGE_CONTENT's when `step_change_content` is
    its work and impact WORK_IMPACT_CONTENT's when `work_impact_content` is, and its work before the
    period EARLIER_WORK_CONTENT's when `earlier_work_content` is, as if they went after the report
    was written."""
    os.makedirs(os.path.join(folder, prep, "_raw"), exist_ok=True)
    for source, lists in (raw_work or {}).items():
        with open(os.path.join(folder, prep, "_raw", f"{source}.json"), "w", encoding="utf-8") as f:
            json.dump(lists, f)
    for name, value in (("person.json", person),
                        ("manager_feedback.json",
                         manager), ("other_feedback.json", other),
                        ("previous_feedback.json", previous), ("notes.json", notes),
                        ("data.json", data), ("slack.json",
                                              slack), ("observations_brief.json", observations_brief),
                        ("observations_content.json", observations_content), ("step_change_brief.json",
                                                                              step_change_brief),
                        ("step_change_content.json", step_change_content),
                        ("work_impact_brief.json", work_impact_brief), (
                            "work_impact_content.json", work_impact_content),
                        ("earlier_work_brief.json", earlier_work_brief),
                        ("earlier_work_content.json", earlier_work_content)):
        if value is not None:
            with open(os.path.join(folder, prep, name), "w", encoding="utf-8") as f:
                json.dump(value, f)
    if report and person is not None and data is not None:
        os.makedirs(os.path.join(
            folder, prep, common.CHARTS_DIR), exist_ok=True)
        for name in common.CHART_FILES:
            with open(os.path.join(folder, prep, common.CHARTS_DIR, name), "w", encoding="utf-8") as f:
                f.write("<svg/>")
        with open(os.path.join(folder, prep, common.report_name(prep)), "w", encoding="utf-8") as f:
            f.write(make_report.render(
                person, data, os.path.join(
                    folder, prep), observations_content or OBSERVATIONS_CONTENT,
                step_change_content or STEP_CHANGE_CONTENT, work_impact_content or WORK_IMPACT_CONTENT,
                earlier_work_content or EARLIER_WORK_CONTENT))
