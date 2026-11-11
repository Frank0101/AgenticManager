"""What the skill's tests share: an invented request, identities,
orientation, previous feedback, check-ins, notes, work, Notion pages, Slack and company values and ratings, and an output folder of the
test's own."""
import json
import os
import tempfile
from unittest import mock

import common  # noqa: F401  (puts the library on the path)
from agentic_manager import config, output_folder

PREP = "Jane-Doe_26-11-10"
REQUEST = {"person": "Jane Doe", "start": "2026-08-10", "end": "2026-11-10"}
IDENTITIES = {"jira-api": {"id": "5b10ac8d82e05b22cc7d4ef5", "name": "Jane Doe"},
              "github-cli": {"id": "janedoe", "name": "Jane Doe"},
              "notion-mcp": {"id": "2a4c1e8f-1234-4abc-9def-0123456789ab", "name": "Jane Doe"},
              "slack-mcp": {"absent": True},
              "logseq-fs": {"links": ["Jane", "Jane Promotion"]}}
ORIENTATION = {"going_well": [{"point": "Has led the billing migration well since May", "values": ["Ownership"]}],
               "to_improve": [{"point": "Could share progress with the wider team more often", "values": []}],
               "context": ["Came back from a long leave in May"]}
PIECE = {"start": "2026-01-01", "end": "2026-06-30", "rating": "Meets",
         "going_well": [{"point": "Delivered the billing migration on time", "values": ["Ownership"]}],
         "to_improve": [{"point": "Could lead a design review alone", "values": ["Teamwork"]}], "context": []}
FEEDBACK = {"pieces": [PIECE]}
NOTE = {"start": "2026-08-01", "end": "2026-09-30",
        "going_well": [{"point": "Agreed to own the billing migration and has kept to its plan",
                        "values": ["Ownership"]}],
        "to_improve": [], "context": []}
CHECK_INS = {"pieces": [NOTE]}
NOTES = {"going_well": [{"point": "Presented the migration to the wider team", "values": ["Teamwork"],
                         "dates": ["2026-09-02"]}],
         "to_improve": [{"point": "Didn't flag delays until asked, many times", "values": ["Ownership"],
                         "dates": ["2026-08-20", "2026-10-01"]}],
         "context": ["Moved to the payments team in the summer"]}
WORK = {"jira": {"resolved": [{"key": "PROJ-12", "title": "Migrate billing", "type": "Story",
                               "parent": {"key": "PROJ-1", "title": "Billing", "type": "Epic"}, "status": "Done",
                               "url": "https://acme.atlassian.net/browse/PROJ-12", "date": "2026-09-01"}],
                 "open": [{"key": "PROJ-13", "title": "Retire old billing", "type": "Task", "parent": None,
                           "status": "In Progress", "url": "https://acme.atlassian.net/browse/PROJ-13"}]},
        "github": {"absent": True}}
NOTION = {"created": [{"title": "Billing plan", "url": "https://www.notion.so/billing-plan",
                       "between": ["2026-08-10", "2026-08-31"]}],
          "edited": [{"title": "Billing plan", "url": "https://www.notion.so/billing-plan", "date": "2026-09-02"}]}
SLACK = {"going_well": [{"point": "Explained the outage's cause in the incident channel, and colleagues thanked them",
                         "values": ["Teamwork"], "dates": ["2026-09-03"],
                         "links": ["https://acme.slack.com/archives/C1/p1"]}],
         "to_improve": [],
         "context": [{"point": "Posted the billing rollout plan in a cross-team channel", "dates": ["2026-08-20"],
                      "links": ["https://acme.slack.com/archives/C2/p2"]}]}
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
    path = os.path.join(root, "config.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"sources": {}, "output": {"root": os.path.join(root, "out")},
                   "company": {"perf-review-ratings": RATINGS, "values": VALUES}}, f)
    for target, attribute, value in ((config, "CONFIG_PATH", path),
                                     (output_folder, "TEMP_ROOT", os.path.join(root, "temp"))):
        patcher = mock.patch.object(target, attribute, value)
        patcher.start()
        test.addCleanup(patcher.stop)
    return os.path.join(root, "out", "perf-review-preps")


def write_prep(folder, request=REQUEST, identities=IDENTITIES, prep=PREP, orientation=ORIENTATION,
               feedback=FEEDBACK, check_ins=CHECK_INS, notes=NOTES, work=WORK, notion=NOTION, slack=SLACK):
    """Writes the prep `prep` in the output folder `folder`, holding `request`,
    `identities`, `orientation`, `feedback`, `check_ins`, `notes`, `work`,
    `notion` and `slack`, each left out when None."""
    os.makedirs(os.path.join(folder, prep), exist_ok=True)
    for name, value in (("request.json", request), ("identities.json", identities),
                        ("orientation.json", orientation), ("feedback.json", feedback),
                        ("check-ins.json", check_ins), ("notes.json", notes),
                        ("work.json", work), ("notion.json", notion), ("slack.json", slack)):
        if value is not None:
            with open(os.path.join(folder, prep, name), "w", encoding="utf-8") as f:
                json.dump(value, f)
