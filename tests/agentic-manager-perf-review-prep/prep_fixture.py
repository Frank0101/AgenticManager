"""What the skill's tests share: an invented person, with the review's period
and who they are in each source, orientation, previous reviews, feedback, notes, work, Slack and company
values and ratings, two synopses a reading of the notes answers with, and an
output folder of the test's own."""
import json
import os
import tempfile
from datetime import date, timedelta
from urllib.parse import quote
from unittest import mock

import common  # noqa: F401  (puts the library on the path)
from agentic_manager import config, output_folder

PREP = "Jane-Doe_26-11-10"
JIRA_ACCOUNT = {"id": "5b10ac8d82e05b22cc7d4ef5",
                "name": "Jane Doe", "email": "jane@acme.test"}
PERSON = {"person": "Jane Doe", "start": "2026-08-10", "end": "2026-11-10",
          "sources": {"jira-api": JIRA_ACCOUNT, "github-cli": {"id": "janedoe", "name": "Jane Doe"},
                      "notion-mcp": {"id": "2a4c1e8f-1234-4abc-9def-0123456789ab", "name": "Jane Doe"},
                      "slack-mcp": {"id": "U012AB3CD", "name": "Jane Doe"},
                      "logseq-fs": {"links": ["Jane", "Jane Promotion"]}}}
ORIENTATION = {"going_well": [{"point": "Has led the billing migration well since May", "values": ["Ownership"]}],
               "to_improve": [{"point": "Could share progress with the wider team more often", "values": []}],
               "context": ["Came back from a long leave in May"]}
PIECE = {"period": "Mid Year Review 2026", "rating": "Meets",
         "going_well": [{"point": "Delivered the billing migration on time", "values": ["Ownership"]}],
         "to_improve": [{"point": "Could lead a design review alone", "values": ["Teamwork"]}], "context": []}
REVIEWS = {"pieces": [PIECE]}
NOTE = {"period": "Q3 2026",
        "going_well": [{"point": "Agreed to own the billing migration and has kept to its plan",
                        "values": ["Ownership"]}],
        "to_improve": [], "context": []}
FEEDBACK = {"pieces": [NOTE]}
NOTES = {"going_well": [{"point": "Presented the migration to the wider team", "values": ["Teamwork"],
                         "evidence": [{"date": "2026-09-02", "link": "file:///vault/journals/2026_09_02.md"}]}],
         "to_improve": [{"point": "Didn't flag delays until asked, many times", "values": ["Ownership"],
                         "evidence": [{"date": "2026-10-01", "link": "file:///vault/journals/2026_10_01.md"},
                                      {"date": "2026-08-20", "link": "file:///vault/journals/2026_08_20.md"}]}],
         "context": [{"point": "Moved to the payments team in the summer",
                      "evidence": [{"date": None, "link": "file:///vault/pages/Jane.md"}]}]}
# The work's items, as work.json records them, in PERSON's period.
WORK_ITEMS = {"jira": {"resolved": [{"key": "PROJ-12", "title": "Migrate billing", "type": "Story",
                                     "parent": {"key": "PROJ-1", "title": "Billing", "type": "Epic"}, "status": "Done",
                                     "url": "https://acme.atlassian.net/browse/PROJ-12", "date": "2026-09-01"}],
                       "created": [{"key": "PROJ-13", "title": "Retire old billing", "type": "Task", "parent": None,
                                    "status": "In Progress", "url": "https://acme.atlassian.net/browse/PROJ-13",
                                    "date": "2026-08-20"}]},
              "github": {"opened": [{"repo": "acme/billing", "number": 1, "title": "Migrate billing",
                                     "url": "https://github.com/acme/billing/pull/1", "date": "2026-08-28"}],
                         "merged": [{"repo": "acme/billing", "number": 1, "title": "Migrate billing",
                                     "url": "https://github.com/acme/billing/pull/1", "date": "2026-09-01"}]},
              "notion": {"created": [{"title": "Billing plan", "url": "https://www.notion.so/billing-plan",
                                      "path": "Engineering / Billing", "between": ["2026-08-10", "2026-08-16"]}]}}
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
# The raw files work.json is built from: what Jira and gh return, with the
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
        "closedAt": "2026-09-01T10:00:00Z", "author": {"login": "janedoe"}, "updatedAt": "2026-09-01T10:00:00Z"}
WORK_RAW = {"jira": {"start": "2026-08-10", "end": "2026-11-10", "base_url": JIRA_BASE,
                     "resolved_jql": JQL["resolved"], "created_jql": JQL["created"],
                     "resolved": [{"key": "PROJ-12", "fields": {
                         "summary": "Migrate billing", "issuetype": {"name": "Story"}, "status": {"name": "Done"},
                         "created": "2026-08-12T10:00:00.000+0100", "resolutiondate": "2026-09-01T10:00:00.000+0100",
                         "parent": {"key": "PROJ-1", "fields": {"summary": "Billing", "issuetype": {"name": "Epic"}}},
                         "assignee": {"accountId": JIRA_ID}, "reporter": {"accountId": "a2"},
                         "updated": "2026-09-01T10:00:00.000+0100"}}],
                     "created": [{"key": "PROJ-13", "fields": {
                         "summary": "Retire old billing", "issuetype": {"name": "Task"},
                         "status": {"name": "In Progress"}, "created": "2026-08-20T10:00:00.000+0100",
                         "resolutiondate": None, "assignee": None, "reporter": {"accountId": JIRA_ID},
                         "updated": "2026-08-20T10:00:00.000+0100"}}]},
            "github": {"start": "2026-08-10", "end": "2026-11-10", "orgs": ["acme"],
                       "opened_query": QUERY["opened"], "merged_query": QUERY["merged"],
                       "opened": [PULL], "merged": [PULL]},
            "notion": {"created": NOTION_SEARCHES}}
# work.json as built from them, its facts worked out by hand.
WORK = {"jira": {**WORK_ITEMS["jira"], "counts": {"created": 1, "resolved": 1},
                 "created_by_type": [{"type": "Task", "issues": 1}],
                 "resolved_by_type": [{"type": "Story", "issues": 1}],
                 "focus": [{"key": "PROJ-1", "title": "Billing", "issues": 1}],
                 **{f"{name}_search_url": f"{JIRA_BASE}/issues/?jql={quote(jql)}" for name, jql in JQL.items()}},
        "github": {**WORK_ITEMS["github"], "counts": {"opened": 1, "merged": 1},
                   **{f"{name}_search_url": f"https://github.com/search?q={quote(query)}&type=pullrequests"
                      for name, query in QUERY.items()}},
        "notion": {**WORK_ITEMS["notion"], "counts": {"created": 1}}}
SLACK = {"going_well": [{"point": "Explained the outage's cause in the incident channel, and colleagues thanked them",
                         "values": ["Teamwork"],
                         "evidence": [{"date": "2026-09-03", "link": "https://acme.slack.com/archives/C1/p1"}]}],
         "to_improve": [],
         "context": [{"point": "Posted the billing rollout plan in a cross-team channel",
                      "evidence": [{"date": "2026-08-20", "link": "https://acme.slack.com/archives/C2/p2"}]}]}
# A reading task's answer: the synopses of the notes it was shown, by number.
PRESENTED = {
    "note": 1, "synopsis": "Presented the migration to the team, who asked for the slides; Jane shared them"}
DELAY = {"note": 2,
         "synopsis": "Didn't flag a delay until asked, the second time this month"}
VALUES = [{"value": "Ownership", "meaning": "Sees work through to its end"},
          {"value": "Teamwork", "meaning": "Succeeds with others"}]
RATINGS = [{"rating": "Below", "meaning": "Misses most expectations"},
           {"rating": "Meets", "meaning": "Meets every expectation"},
           {"rating": "Exceeds", "meaning": "Goes beyond most expectations"}]


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
                   "company": {"perf-review-ratings": RATINGS, "values": VALUES}}, f)
    for target, attribute, value in ((config, "CONFIG_PATH", path),
                                     (output_folder, "TEMP_ROOT",
                                      os.path.join(root, "temp")),
                                     (tempfile, "tempdir", os.path.join(root, "system-temp"))):
        patcher = mock.patch.object(target, attribute, value)
        patcher.start()
        test.addCleanup(patcher.stop)
    return os.path.join(root, "out", "perf-review-preps")


def write_prep(folder, person=PERSON, prep=PREP, orientation=ORIENTATION,
               reviews=REVIEWS, feedback=FEEDBACK, notes=NOTES, work=WORK, slack=SLACK, raw_work=WORK_RAW):
    """Writes the prep `prep` in the output folder `folder`, holding `person`,
    `orientation`, `reviews`, `feedback`, `notes`, `work`,
    and `slack`, each left out when None, and the _raw folder, with
    `raw_work`, each source's raw file, unless None."""
    os.makedirs(os.path.join(folder, prep, "_raw"), exist_ok=True)
    for source, lists in (raw_work or {}).items():
        with open(os.path.join(folder, prep, "_raw", f"{source}.json"), "w", encoding="utf-8") as f:
            json.dump(lists, f)
    for name, value in (("person.json", person),
                        ("orientation.json", orientation), ("reviews.json", reviews),
                        ("feedback.json", feedback), ("notes.json", notes),
                        ("work.json", work), ("slack.json", slack)):
        if value is not None:
            with open(os.path.join(folder, prep, name), "w", encoding="utf-8") as f:
                json.dump(value, f)
