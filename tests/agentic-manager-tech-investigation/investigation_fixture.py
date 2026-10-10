"""An invented investigation shared by the generator tests: its content.json and
ledger."""
import copy
import json
import os
import tempfile
from unittest import mock

from common import FINDING_FIELDS
from agentic_manager import config, output_folder
from init_investigation import ledger_skeleton

INVESTIGATION = "Acme-Search_26-10-05"


def words(count):
    return " ".join(["word"] * count)


QUERY = {"title": "Search API — query",
         "lines": ["actor U as Client / operator", "participant A as Search API",
                   "participant D as Search index", "U->>A: Query", "A->>D: Read rows",
                   "D-->>A: Rows", "A-->>U: Results"]}
PUBLISH = {"title": "Publish job — publication",
           "lines": ["participant J as Publish job", "participant X as Embedding API",
                     "participant D as Search index", "J->>X: Embed documents",
                     "X-->>J: Vectors", "J->>D: Publish rows"]}

CONTENT = {
    "title": "Acme search",
    "evidence_snapshot": "2026-10-05",
    "problem": [words(90) + " [doc](https://example.com/doc) [F01](ledger:F01)."],
    "current_status": [words(190) + " [code](ledger:F01)."],
    "next_steps": [words(190) + " [code](ledger:F01)."],
    "key_decisions": [{"decision": "Index choice", "why": "Affects cost",
                       "position": "Unresolved", "evidence": "[proposal](https://example.com/p) [F01](ledger:F01)"}],
    "architecture": {
        "current": {"summary": [words(290) + " [code](ledger:F01)."], "sequence": QUERY},
        "next": {"summary": [words(290) + " [code](ledger:F01)."], "sequence": PUBLISH},
    },
    "decisions_and_gaps": [{"decision": "Index", "why": "Sets the cost", "position": "Unresolved",
                            "evidence": "[gap](ledger:G01)"}],
    "references": {"implementation": ["[Search API](https://example.com/code)"],
                   "delivery": [{"text": "[PROJ-1](https://example.com/PROJ-1)", "historical": True}],
                   "vision": []},
}

FINDING = ("### F01 — Search API is merged\n\n"
           + "\n".join(f"**{field}:** text." for field in FINDING_FIELDS))
LEDGER = (ledger_skeleton("Acme-Search")
          .replace("## Findings and validation chains\n\nNone yet.",
                   "## Findings and validation chains\n\n" + FINDING)
          .replace("## Evidence gaps\n\nNone yet.",
                   "## Evidence gaps\n\n- **G01** Deployment unverified.")
          .replace("## Reflection\n\nNone yet.",
                   "## Reflection\n\nConverged."))


def content():
    return copy.deepcopy(CONTENT)


def temp_output(test):
    """The skill's output folder in a temporary folder, for `test`: a config
    of its own setting the output root, never the developer's."""
    tmp = tempfile.TemporaryDirectory()
    test.addCleanup(tmp.cleanup)
    root = os.path.realpath(tmp.name)
    path = os.path.join(root, "config.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"sources": {}, "output": {
                  "root": os.path.join(root, "out")}}, f)
    for target, attribute, value in ((config, "CONFIG_PATH", path),
                                     (output_folder, "TEMP_ROOT", os.path.join(root, "temp"))):
        patcher = mock.patch.object(target, attribute, value)
        patcher.start()
        test.addCleanup(patcher.stop)
    return os.path.join(root, "out", "tech-investigations")
