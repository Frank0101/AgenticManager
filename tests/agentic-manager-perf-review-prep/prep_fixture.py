"""What the skill's tests share: an invented request, identities,
orientation, previous feedback, check-ins, notes and company values and ratings, and an output folder of the
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
ORIENTATION = {"going_well": [{"point": "Has led the billing migration well since May", "value": "Ownership"}],
               "to_improve": [{"point": "Could share progress with the wider team more often", "value": None}],
               "context": ["Came back from a long leave in May"]}
PIECE = {"start": "2026-01-01", "end": "2026-06-30", "rating": "Meets",
         "going_well": [{"point": "Delivered the billing migration on time", "value": "Ownership"}],
         "to_improve": [{"point": "Could lead a design review alone", "value": "Teamwork"}], "context": []}
FEEDBACK = {"pieces": [PIECE]}
NOTE = {"start": "2026-08-01", "end": "2026-09-30",
        "going_well": [{"point": "Agreed to own the billing migration and has kept to its plan",
                        "value": "Ownership"}],
        "to_improve": [], "context": []}
CHECK_INS = {"pieces": [NOTE]}
NOTES = {"going_well": [{"point": "Presented the migration to the wider team", "value": "Teamwork",
                         "dates": ["2026-09-02"]}],
         "to_improve": [{"point": "Didn't flag delays until asked, many times", "value": "Ownership",
                         "dates": ["2026-08-20", "2026-10-01"]}],
         "context": ["Moved to the payments team in the summer"]}
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
               feedback=FEEDBACK, check_ins=CHECK_INS, notes=NOTES):
    """Writes the prep `prep` in the output folder `folder`, holding `request`,
    `identities`, `orientation`, `feedback`, `check_ins` and `notes`, each
    left out when None."""
    os.makedirs(os.path.join(folder, prep), exist_ok=True)
    for name, value in (("request.json", request), ("identities.json", identities),
                        ("orientation.json", orientation), ("feedback.json", feedback),
                        ("check-ins.json", check_ins), ("notes.json", notes)):
        if value is not None:
            with open(os.path.join(folder, prep, name), "w", encoding="utf-8") as f:
                json.dump(value, f)
