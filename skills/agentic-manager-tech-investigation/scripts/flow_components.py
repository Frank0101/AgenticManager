"""Draws the components a sequence crosses as a Mermaid flowchart, the design
view of an architect section, from the sequence itself and the ledger's
component inventory.

The sequence is the one source: its participants are the boxes, its requests
the arrows and its `box` groups the boundaries, so the two diagrams can't
disagree and the agent writes nothing more. A solid arrow is a request and
draws an arrow, labelled with the first request between the pair; a dashed one
is a reply and adds none, nor does a call to itself, which is an action of its
component. Notes stay in the sequence.

Each participant other than an `actor` must be a ledger component, named as in
its Name and type cell, without the type: "Search API" for "Search API
(service)", optionally followed by a qualifier in brackets. The component
gives the box its status colour and, from its type, its shape. Text inside the
boxes is near black, as Mermaid's default grey is hard to read on the status
colours; the arrows keep the sequence's full message text, in a smaller font so
a long one doesn't stretch the diagram.
"""
import re

from common import STATUSES, link_text

# A message line: sender, arrow, optional activation, receiver, text.
MESSAGE = re.compile(
    r"^\s*([^\s:+\-<>]+)\s*(<<-->>|<<->>|-->>|->>|-->|->|--x|-x|--\)|-\))\s*[+-]?\s*([^\s:+\-<>]+)\s*:(.*)$")
DECLARATION = re.compile(
    r"^\s*(?:create\s+)?(participant|actor)\s+(\S+?)(?:\s+as\s+(.+?))?\s*$")
# A box's colour, if any, comes first: a function, such as rgb(), or transparent.
BOX = re.compile(
    r"^\s*box(?:\s+(?:rgba?\([^)]*\)|transparent))?(?:\s+(.*?))?\s*$")
# Blocks that `end` closes; only a box becomes a group.
BLOCK = re.compile(r"^\s*(alt|opt|loop|par|critical|break|rect)\b")
END = re.compile(r"^\s*end\s*$")

INIT = '%%{init: {"themeCSS": ".edgeLabel, .edgeLabel p, .edgeLabel span { font-size: 11px; }"}}%%'
STYLES = {"🟩": "fill:#dcf3dc,stroke:#0ca30c,color:#1a1a1a", "🟨": "fill:#fdf1cc,stroke:#c99a00,color:#1a1a1a",
          "🟦": "fill:#dae8fc,stroke:#2f6fd0,color:#1a1a1a", "🟥": "fill:#f9dcdc,stroke:#c62828,color:#1a1a1a",
          "⬜": "fill:#ffffff,stroke:#8a8a8a,stroke-dasharray:4 3,color:#1a1a1a",
          "⚫": "fill:#dddddd,stroke:#444444,color:#1a1a1a"}
ACTOR_STYLE = "fill:#f4f4f4,stroke:#8a8a8a,color:#1a1a1a"
CLASSES = {mark: f"s{i}" for i, mark in enumerate(STYLES)}


class Flow:
    """A sequence's participants, in order of appearance, as {id: [label,
    actor?, group]}, its groups and its requests as [(from, to, text)]."""

    def __init__(self, lines):
        self.participants, self.groups, self.requests = {}, [], []
        stack = []
        for line in lines:
            if END.match(line):
                if stack:
                    stack.pop()
                continue
            box = BOX.match(line)
            if box:
                self.groups.append(box[1] or "")
                stack.append(len(self.groups) - 1)
                continue
            if BLOCK.match(line):
                stack.append(None)
                continue
            group = next((g for g in reversed(stack) if g is not None), None)
            declared = DECLARATION.match(line)
            if declared:
                kind, ident, label = declared.groups()
                self.participants.setdefault(
                    ident, [(label or ident).strip(), kind == "actor", group])
                continue
            message = MESSAGE.match(line)
            if message:
                sender, arrow, receiver, text = message.groups()
                for ident in (sender, receiver):
                    self.participants.setdefault(ident, [ident, False, None])
                if "--" not in arrow and sender != receiver:
                    self.requests.append((sender, receiver, text.strip()))


def plain(cell):
    """A ledger cell's text, without Markdown link syntax."""
    return link_text(cell).strip()


def components(rows):
    """{name in lower case: (status mark, type)} from the component rows."""
    found = {}
    for row in rows:
        named = re.fullmatch(r"(.+?)\s*(?:\(([^()]*)\))?", plain(row[1]))
        if not named:
            continue
        mark = next((s[:1]
                    for s, _ in STATUSES if row[4].startswith(s[:1])), "⬜")
        found[named[1].lower()] = (mark, (named[2] or "").lower())
    return found


def component_of(label, known):
    """The ledger component a participant's label names, or None."""
    name = re.sub(r"\s*\([^()]*\)\s*$", "", plain(label)).strip().lower()
    return known.get(name)


def unknown_participants(flow, known):
    """Labels of the participants, other than actors, that name no component."""
    return [label for label, actor, _ in flow.participants.values()
            if not actor and component_of(label, known) is None]


def quoted(text):
    """A label quoted for Mermaid."""
    # A leading backtick would open a Mermaid Markdown string.
    return '"' + text.replace('"', "#quot;").replace("`", "#96;") + '"'


def node(number, label, actor, component):
    """A flowchart node, shaped by whether it is a person and by the component's type."""
    kind = component[1] if component else ""
    if actor:
        return f"n{number}([{quoted(label)}])"
    if "store" in kind:
        return f"n{number}[({quoted(label)})]"
    if re.search(r"queue|topic|stream", kind):
        return f"n{number}@{{ shape: h-cyl, label: {quoted(label)} }}"
    if "external" in kind:
        return f"n{number}[[{quoted(label)}]]"
    return f"n{number}[{quoted(label)}]"


def flowchart(flow, known):
    """The Mermaid flowchart of `flow`, styled from the components `known`."""
    numbers = {ident: i for i, ident in enumerate(flow.participants, 1)}
    found = {ident: component_of(label, known)
             for ident, (label, _, _) in flow.participants.items()}
    lines = [INIT, "flowchart LR"]
    nodes = {}
    for ident, (label, actor, group) in flow.participants.items():
        nodes.setdefault(group, []).append(
            "    " + node(numbers[ident], label, actor, found[ident]))
    lines += nodes.pop(None, [])
    for index, label in enumerate(flow.groups):
        if index in nodes:
            lines += [f"    subgraph g{index + 1}[{quoted(label or ' ')}]",
                      *("    " + n for n in nodes[index]), "    end"]
    seen = set()
    for sender, receiver, text in flow.requests:
        if (sender, receiver) not in seen:
            seen.add((sender, receiver))
            label = f"|{quoted(text)}|" if text else ""
            lines.append(
                f"    n{numbers[sender]} -->{label} n{numbers[receiver]}")
    used = {}
    for ident, (_, actor, _) in flow.participants.items():
        component = found[ident]
        style = "actor" if actor else CLASSES[component[0]
                                              ] if component else None
        if style:
            used.setdefault(style, []).append(f"n{numbers[ident]}")
    styles = {"actor": ACTOR_STYLE, **
              {CLASSES[mark]: style for mark, style in STYLES.items()}}
    for style, members in used.items():
        lines += [f"    classDef {style} {styles[style]}",
                  f"    class {','.join(members)} {style}"]
    return "\n".join(lines) + "\n"


def marks(flow, known):
    """The statuses the flow's components have, in the ledger's order."""
    present = {component[0] for label, actor, _ in flow.participants.values()
               if not actor and (component := component_of(label, known))}
    return [status for status, _ in STATUSES if status[:1] in present]
