"""An invented investigation shared by the generator tests: its maps.json,
content.json and ledger, and fake SVGs for the Mermaid CLI's output."""
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


def svg(width, height=100, nodes=()):
    """A rendered diagram: its viewBox, and flowchart nodes at positions."""
    groups = "".join(f'<g class="node default" id="my-svg-flowchart-{ident}-{i}" '
                     f'transform="translate({x}, {y})"><rect x="-5" y="-5" width="10" height="10"/></g>'
                     for i, (ident, x, y) in enumerate(nodes))
    return (f'<svg id="my-svg" viewBox="0 0 {width} {height}">{groups}'
            '<path id="L_A_B_0" class="flowchart-link" d="M10,10L10,50Q10,60 20,60L80,60"/></svg>')


SPEC = {
    "notes": ["The app cluster groups the API and its index."],
    "groups": [{"id": "app", "label": "APP CLUSTER · configured"},
               {"id": "jobs", "label": "PROPOSED JOBS · hosting undecided"}],
    "nodes": [
        {"id": "U", "name": "Client / operator", "kind": "person"},
        {"id": "A", "name": "Search API", "kind": "component",
            "status": "Implemented", "group": "app"},
        {"id": "D", "name": "Search index", "kind": "store",
            "status": "Implemented", "group": "app"},
        {"id": "L", "name": "Legacy indexer", "kind": "component",
            "status": "Legacy or superseded", "group": "app"},
        {"id": "J", "name": "Publish job", "kind": "component",
            "status": "No implementation found", "group": "jobs"},
        {"id": "X", "name": "Embedding API", "kind": "external"},
    ],
    "connections": [
        {"from": "U", "to": "A", "label": "HTTP query"},
        {"from": "A", "to": "D", "label": "read"},
        {"from": "L", "to": "D", "label": "write"},
        {"from": "J", "to": "D", "label": "publish"},
        {"from": "J", "to": "X", "label": "embeddings"},
    ],
    "stages": {
        "current": {"carried": ["A", "D", "L"], "labels": {"A": "Current", "D": "Current", "L": "Current"},
                    "connections": {"U->A": "implemented", "A->D": "implemented", "L->D": "implemented"}},
        "next": {"carried": ["A", "D", "J"], "labels": {"A": "Retained", "D": "Retained", "J": "Added — proposed"},
                 "decommissioned": {"L": "Planned decommissioning"},
                 "connections": {"U->A": "implemented", "A->D": "implemented",
                                 "J->D": "proposed", "J->X": "proposed"}},
        "target": {"carried": ["A", "D", "J"], "labels": {"A": "Retained", "D": "Retained", "J": "Retained"},
                   "decommissioned": {"L": "Planned decommissioning"},
                   "connections": {"U->A": "implemented", "A->D": "implemented",
                                   "J->D": "proposed", "J->X": "proposed"}},
    },
}

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
    "problem": [words(90) + " [doc](https://example.com/doc)."],
    "roadmap": {key: {"outcome": f"Outcome {key}", "commitment": "Proposed [plan](https://example.com/plan)",
                      "dependencies": "None"} for key in ("current", "next", "broader")},
    "deep_dive": [words(190) + " [code](ledger:F01)."],
    "key_decisions": [{"item": "Index choice", "why": "Affects cost [proposal](https://example.com/p)",
                       "role": "Not established"}],
    "architecture": {
        "current": {"summary": [words(290)], "sequences": [QUERY],
                    "commentary": ["**Search API:** steps 1–4 read the index; [code](ledger:F01). " + words(80)]},
        "next": {"summary": [words(290)], "sequences": [QUERY, PUBLISH],
                 "commentary": ["**Search API:** steps 1–4 unchanged. **Publish job:** steps 1–3 publish. "
                                + words(90)]},
        "target": {"summary": [words(290)], "sequences": [QUERY],
                   "commentary": ["Steps 1–4 as before. " + words(90)]},
    },
    "technical_decisions": [{"decision": "Index", "position": "Unresolved", "evidence": "[gap](ledger:G01)",
                             "status": "Open", "owner": "Not established"}],
    "discrepancies": "A ticket status can't override code [code](ledger:F01).",
    "remaining_gaps": "Deployment is unverified, see [G01](ledger:G01).",
    "references": {"implementation": ["[Search API](https://example.com/code)"],
                   "delivery": [{"text": "[PROJ-1](https://example.com/PROJ-1)", "historical": True}],
                   "vision": []},
}

FINDING = ("### F01 — Search API is merged\n\n"
           + "\n".join(f"**{field}:** text." for field in FINDING_FIELDS))
LEDGER = (ledger_skeleton("Acme-Search")
          .replace("## Findings and validation chains\n\nNone yet.",
                   "## Findings and validation chains\n\n" + FINDING)
          .replace("## Decisions and precise evidence gaps\n\nNone yet.",
                   "## Decisions and precise evidence gaps\n\n- **G01** Deployment unverified.")
          .replace("## Correction history\n\nNone yet.",
                   "## Correction history\n\n### Reflection\n\nConverged."))


def spec():
    return copy.deepcopy(SPEC)


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
