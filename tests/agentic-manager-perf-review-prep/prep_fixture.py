"""What the skill's tests share: an invented request, identities,
orientation, previous feedback and company ratings, and an output folder of the
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
ORIENTATION = {"going_well": ["Has led the billing migration well since May"],
               "to_improve": ["Could share progress with the wider team more often"],
               "context": ["Came back from a long leave in May"]}
REVIEW = {"start": "2026-01-01", "end": "2026-06-30", "rating": "Meets",
          "going_well": ["Delivered the billing migration on time"],
          "to_improve": ["Lead a design review on her own"], "context": []}
FEEDBACK = {"reviews": [REVIEW]}
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
                   "company": {"perf-review-ratings": RATINGS}}, f)
    for target, attribute, value in ((config, "CONFIG_PATH", path),
                                     (output_folder, "TEMP_ROOT", os.path.join(root, "temp"))):
        patcher = mock.patch.object(target, attribute, value)
        patcher.start()
        test.addCleanup(patcher.stop)
    return os.path.join(root, "out", "perf-review-preps")


def write_prep(folder, request=REQUEST, identities=IDENTITIES, prep=PREP, orientation=ORIENTATION,
               feedback=FEEDBACK):
    """Writes the prep `prep` in the output folder `folder`, holding `request`,
    `identities`, `orientation` and `feedback`, each left out when None."""
    os.makedirs(os.path.join(folder, prep), exist_ok=True)
    for name, value in (("request.json", request), ("identities.json", identities),
                        ("orientation.json", orientation), ("feedback.json", feedback)):
        if value is not None:
            with open(os.path.join(folder, prep, name), "w", encoding="utf-8") as f:
                json.dump(value, f)
