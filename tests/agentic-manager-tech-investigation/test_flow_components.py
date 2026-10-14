"""Unit tests for skills/agentic-manager-tech-investigation/scripts/flow_components.py.
Run with: python3 tests/run.py agentic-manager-tech-investigation
"""

import os
import sys
import unittest

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(TEST_DIR))
sys.path.insert(0, os.path.join(REPO_ROOT, "skills",
                os.path.basename(TEST_DIR), "scripts"))
from flow_components import INIT, Flow, components, flowchart, marks, unknown_participants  # noqa: E402


def row(name, status):
    return ["C01", name, "Role", "—", status, "None", "—", "F01", "Unchanged"]


KNOWN = components([row("[Search API](https://example.com/api) (service)", "🟩 Implemented"),
                    row("Search index (store)", "⬜ Unverified"),
                    row("Embedding API (external product)",
                        "🟥 No implementation found"),
                    row("Events (Kafka topics)", "🟩 Implemented")])


class FlowTest(unittest.TestCase):
    def test_parsing(self):
        # name: (sequence lines, participants as {id: [label, actor?, group]},
        # groups, requests)
        cases = [
            ("declared, with and without a label",
             ["actor U as Client / operator",
                 "participant A as Search API", "participant D"],
             {"U": ["Client / operator", True, None], "A": ["Search API", False, None],
              "D": ["D", False, None]}, [], []),
            ("only in a message", ["A->>D: Read rows"],
             {"A": ["A", False, None], "D": ["D", False, None]}, [], [("A", "D", "Read rows")]),
            # A dashed arrow is a reply, a call to itself an action: no request.
            ("replies and actions", ["A->>D: Read", "D-->>A: Rows", "A->>A: Rank", "A--)D: Ack"],
             {"A": ["A", False, None], "D": ["D", False, None]}, [], [("A", "D", "Read")]),
            ("async, failing and two-way calls", ["A-)D: Notify", "A-xD: Drop", "A<<->>D: Sync",
                                                  "A<<-->>D: Echo"],
             {"A": ["A", False, None], "D": ["D", False, None]}, [],
             [("A", "D", "Notify"), ("A", "D", "Drop"), ("A", "D", "Sync")]),
            # A box's colour is not its label; a block inside it keeps the group.
            ("boxes", ["box rgb(240,240,255) Acme cloud", "participant A as Search API", "alt cached",
                       "participant D as Search index", "end", "end", "box transparent Partner", "participant X",
                       "end",
                       "participant U"],
             {"A": ["Search API", False, 0], "D": ["Search index", False, 0], "X": ["X", False, 1],
              "U": ["U", False, None]}, ["Acme cloud", "Partner"], []),
            ("created participant", ["create participant W as Worker"],
             {"W": ["Worker", False, None]}, [], []),
        ]
        for name, lines, participants, groups, requests in cases:
            with self.subTest(name):
                flow = Flow(lines)
                self.assertEqual(flow.participants, participants)
                self.assertEqual(flow.groups, groups)
                self.assertEqual(flow.requests, requests)

    def test_unknown_participants(self):
        # A label names a component without its type, with an optional
        # qualifier; a person is an actor and names none.
        cases = [
            ("named as in the ledger", ["participant A as Search API"], []),
            ("any case, with a qualifier", [
             "participant A as search api (candidate)"], []),
            ("with its type", ["participant A as Search API (service)"], []),
            ("a person", ["actor U as Client / operator"], []),
            ("not a component", ["participant Q as Queue",
             "Q->>A: Push"], ["Queue", "A"]),
        ]
        for name, lines, unknown in cases:
            with self.subTest(name):
                self.assertEqual(unknown_participants(
                    Flow(lines), KNOWN), unknown)


class FlowchartTest(unittest.TestCase):
    def test_flowchart(self):
        flow = Flow(["actor U as Client / operator", "box Acme cloud", "participant A as Search API",
                     "participant D as Search index", "end", "participant X as Embedding API",
                     'U->>A: Query "cats"', "U->>D: `raw` read", "A->>D: Read rows", "D-->>A: Rows", "A->>D: Read again",
                     "A->>X: Embed", "participant E as Events", "A->>E: Publish"])
        self.assertEqual(flowchart(flow, KNOWN), "\n".join([
            INIT, "flowchart LR",
            '    n1(["Client / operator"])',
            '    n4[["Embedding API"]]',
            '    n5@{ shape: h-cyl, label: "Events" }',
            '    subgraph g1["Acme cloud"]',
            '        n2["Search API"]',
            '        n3[("Search index")]',
            "    end",
            # One arrow per pair, labelled with its first request.
            '    n1 -->|"Query #quot;cats#quot;"| n2',
            # A leading backtick would open a Mermaid Markdown string.
            '    n1 -->|"#96;raw#96; read"| n3',
            '    n2 -->|"Read rows"| n3',
            '    n2 -->|"Embed"| n4',
            '    n2 -->|"Publish"| n5',
            "    classDef actor fill:#f4f4f4,stroke:#8a8a8a,color:#1a1a1a",
            "    class n1 actor",
            "    classDef s0 fill:#dcf3dc,stroke:#0ca30c,color:#1a1a1a",
            "    class n2,n5 s0",
            "    classDef s4 fill:#ffffff,stroke:#8a8a8a,stroke-dasharray:4 3,color:#1a1a1a",
            "    class n3 s4",
            "    classDef s3 fill:#f9dcdc,stroke:#c62828,color:#1a1a1a",
            "    class n4 s3",
        ]) + "\n")

    def test_marks(self):
        # The statuses the flow's components have, in the ledger's order.
        flow = Flow(["participant D as Search index", "participant A as Search API",
                     "actor U as Client / operator"])
        self.assertEqual(marks(flow, KNOWN),
                         ["🟩 Implemented", "⬜ Unverified"])


if __name__ == "__main__":
    unittest.main()
