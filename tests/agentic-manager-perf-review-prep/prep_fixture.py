"""What the skill's tests share: an invented person, with the review's period
and who they are in each source, orientation, previous reviews, feedback, notes, work, Slack and company
values and ratings, two synopses a reading of the notes answers with, and an
output folder of the test's own."""
import json
import os
import tempfile
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
# The work's items, and its facts and commentary worked out by hand, over
# PERSON's period, 10/08/2026 to 10/11/2026.
WORK_ITEMS = {"jira": {"resolved": [{"key": "PROJ-12", "title": "Migrate billing", "type": "Story",
                                     "parent": {"key": "PROJ-1", "title": "Billing", "type": "Epic"}, "status": "Done",
                                     "url": "https://acme.atlassian.net/browse/PROJ-12", "date": "2026-09-01"}],
                       "open": [{"key": "PROJ-13", "title": "Retire old billing", "type": "Task", "parent": None,
                                 "status": "In Progress", "url": "https://acme.atlassian.net/browse/PROJ-13"}]},
              "github": {"opened": [{"repo": "acme/billing", "number": 1, "title": "Migrate billing",
                                     "url": "https://github.com/acme/billing/pull/1", "date": "2026-08-28",
                                     "issue": "PROJ-12"}],
                         "merged": [{"repo": "acme/billing", "number": 1, "title": "Migrate billing",
                                     "url": "https://github.com/acme/billing/pull/1", "date": "2026-09-01",
                                     "issue": "PROJ-12"}]},
              "notion": {"created": [{"title": "Billing plan", "url": "https://www.notion.so/billing-plan",
                                      "path": "Engineering / Billing", "between": ["2026-08-10", "2026-08-31"]}],
                         "edited": [{"title": "Billing plan", "url": "https://www.notion.so/billing-plan",
                                     "path": "Engineering / Billing", "date": "2026-09-02"}]}}
WORK_FACTS = {
    "jira": {"by_month": [{"month": "2026-08", "resolved": 0, "areas": 0, "main_areas": []},
                          {"month": "2026-09", "resolved": 1, "areas": 1,
                           "main_areas": [{"area": "Billing", "items": 1}]},
                          {"month": "2026-10", "resolved": 0,
                              "areas": 0, "main_areas": []},
                          {"month": "2026-11", "resolved": 0, "areas": 0, "main_areas": []}],
             "by_area": [{"kind": "Epic", "key": "PROJ-1", "title": "Billing", "resolved": 1, "open": 0},
                         {"kind": "no parent", "key": None, "title": None, "resolved": 0, "open": 1}]},
    "github": {"by_month": [{"month": "2026-08", "opened": 1, "merged": 0, "areas": 1,
                             "main_areas": [{"area": "Billing", "items": 1}]},
                            {"month": "2026-09", "opened": 0, "merged": 1, "areas": 1,
                             "main_areas": [{"area": "Billing", "items": 1}]},
                            {"month": "2026-10", "opened": 0,
                                "merged": 0, "areas": 0, "main_areas": []},
                            {"month": "2026-11", "opened": 0, "merged": 0, "areas": 0, "main_areas": []}],
               "by_area": [{"kind": "Epic", "key": "PROJ-1", "title": "Billing", "opened": 1, "merged": 1}]},
    "notion": {"by_month": [{"month": "2026-08", "created": 1, "edited": 0, "areas": 1,
                             "main_areas": [{"area": "Engineering / Billing", "items": 1}]},
                            {"month": "2026-09", "created": 0, "edited": 1, "areas": 1,
                             "main_areas": [{"area": "Engineering / Billing", "items": 1}]},
                            {"month": "2026-10", "created": 0,
                                "edited": 0, "areas": 0, "main_areas": []},
                            {"month": "2026-11", "created": 0, "edited": 0, "areas": 0, "main_areas": []}],
               "by_area": [{"kind": "location", "key": None, "title": "Engineering / Billing", "created": 1,
                            "edited": 1}]}}
COMMENTARY = {"jira": "Resolved one issue, in September, on the billing epic, with one more still open.",
              "github": "Opened one pull request on the billing epic in August, merged in September.",
              "notion": "Wrote the billing plan in August and edited it in September."}
WORK = {**WORK_ITEMS, "facts": WORK_FACTS, "commentary": COMMENTARY}
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
               reviews=REVIEWS, feedback=FEEDBACK, notes=NOTES, work=WORK, slack=SLACK):
    """Writes the prep `prep` in the output folder `folder`, holding `person`,
    `orientation`, `reviews`, `feedback`, `notes`, `work`,
    and `slack`, each left out when None, and the _raw folder the readings
    write."""
    os.makedirs(os.path.join(folder, prep, "_raw"), exist_ok=True)
    for name, value in (("person.json", person),
                        ("orientation.json", orientation), ("reviews.json", reviews),
                        ("feedback.json", feedback), ("notes.json", notes),
                        ("work.json", work), ("slack.json", slack)):
        if value is not None:
            with open(os.path.join(folder, prep, name), "w", encoding="utf-8") as f:
                json.dump(value, f)
