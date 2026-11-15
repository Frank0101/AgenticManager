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
                 "focus": [{"key": "PROJ-1", "title": "Billing", "url": f"{JIRA_BASE}/browse/PROJ-1", "issues": 1}],
                 "resolved_points": {"total": 3, "estimated": 1, "average": 3.0},
                 "epic_search_urls": {"PROJ-1": f"{JIRA_BASE}/issues/?jql={quote(JQL['resolved'] + ' AND (parent = PROJ-1)')}"},
                 "no_epic_search_url": None,
                 "resolved_points_search_url":
                     f"{JIRA_BASE}/issues/?jql={quote(JQL['resolved'] + ' AND (cf[10016] is not EMPTY)')}",
                 **{f"{name}_search_url": f"{JIRA_BASE}/issues/?jql={quote(jql)}" for name, jql in JQL.items()}},
        "github": {**WORK_ITEMS["github"], "counts": {"opened": 1, "merged": 1},
                   "merged_by_repo": {"repos": [{"repo": "acme/billing", "prs": 1}], "other": 0},
                   "focus": [{"repo": "acme/billing", "prs": 1}], "repo_order": ["acme/billing"],
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
        "notion": {**WORK_ITEMS["notion"], "counts": {"created": 1}}}
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
    "focus": [{"key": None, "title": None, "url": None, "issues": 3},
              {"key": "PROJ-1", "title": "Billing", "url": f"{JIRA_BASE}/browse/PROJ-1", "issues": 2}],
    "no_epic_search_url": f"{JIRA_BASE}/issues/?jql={quote(JQL['resolved'] + ' AND key in (PROJ-15, PROJ-16, PROJ-17)')}"}}
# In the second, no resolved issue has an epic, so the main focus lists their
# project, and no epic is coloured.
DATA_BY_PROJECT = {**DATA, "jira": {
    **DATA["jira"], "resolved": [{**BILLING, "epic": None}], "epic_order": [],
    "resolved_by_week": {"total": weekly(3), "epics": {}, "other": weekly(), "no_epic": weekly(3)},
    "points_by_epic": [{"points": 3, "issues": 1, "epics": {}, "other": 0, "no_epic": 1}],
    "resolved_by_epic": {"epics": [{"key": None, "title": None, "url": None, "issues": 1}], "other": 0},
    "focus": [{"key": "PROJ", "title": None, "url": None, "issues": 1}], "epic_search_urls": {},
    "no_epic_search_url": f"{JIRA_BASE}/issues/?jql={quote(JQL['resolved'] + ' AND key in (PROJ-12)')}"}}
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
               reviews=REVIEWS, feedback=FEEDBACK, notes=NOTES, data=DATA, slack=SLACK, raw_work=WORK_RAW, report=True):
    """Writes the prep `prep` in the output folder `folder`, holding `person`,
    `orientation`, `reviews`, `feedback`, `notes`, `data`,
    and `slack`, each left out when None, the _raw folder, with
    `raw_work`, each source's raw file, unless None, and, with `report` and
    both a person and data, the report as finish_report.py writes it, with its
    charts, each an empty drawing."""
    os.makedirs(os.path.join(folder, prep, "_raw"), exist_ok=True)
    for source, lists in (raw_work or {}).items():
        with open(os.path.join(folder, prep, "_raw", f"{source}.json"), "w", encoding="utf-8") as f:
            json.dump(lists, f)
    for name, value in (("person.json", person),
                        ("orientation.json", orientation), ("reviews.json", reviews),
                        ("feedback.json", feedback), ("notes.json", notes),
                        ("data.json", data), ("slack.json", slack)):
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
            f.write(make_report.render(person, data))
