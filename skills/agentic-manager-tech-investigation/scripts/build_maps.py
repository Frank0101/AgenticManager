"""Builds the investigation's architecture maps from <investigation>/maps.json:
their Mermaid sources in mermaids.md and their SVGs, rendered dark.

    python3 build_maps.py --investigation <Topic>_<YY-MM-DD> [--png]

The agent decides what the maps show; this script owns how. One list of nodes
and connections serves all three stages, so every stage has the same nodes and
connections in the same order, and the renderer places each component at the
same position in every stage: a connection a stage doesn't have is hidden, not
removed. The script draws the red outline on the carried components, colours
red each connection added or changed from the preceding stage, greys and
crosses decommissioned components, greys replaced ones, and checks what an
instruction alone wouldn't hold: the line rules, the positions across stages,
and that no component carried at one stage silently leaves the next.

maps.json:

{
  "notes": ["Optional paragraphs for mermaids.md: what logical groups contain, material omissions."],
  "compact": false,
  "label_width": 260,
  "groups": [{"id": "app", "label": "APP CLUSTER · configured, live state unverified"}],
  "nodes": [
    {"id": "U", "name": "Client / operator", "kind": "person"},
    {"id": "A", "name": "Search API", "kind": "component", "status": "Implemented", "group": "app"},
    {"id": "D", "name": "Search index", "kind": "store", "status": "Implemented", "group": "app"},
    {"id": "X", "name": "Embedding API", "kind": "external"}
  ],
  "connections": [{"from": "U", "to": "A", "label": "HTTP query"}],
  "stages": {
    "current": {"carried": ["A", "D"], "labels": {"A": "Retained"},
                "connections": {"U->A": "implemented"},
                "decommissioned": {}, "replaced": {}, "transferred": {}},
    "next": {...}, "target": {...}
  }
}

"stages" holds all three, or "current" alone when the report skips evolution.

- kind: component or store (drawn as a cylinder), with its status, the same in
  every stage; or person or external, whose status line reads "Person" or
  "External" and who are never in the outline.
- A connection's key is "<from>-><to>", or its "id" when two connect the
  same nodes. A stage's "connections" names those it has, "implemented"
  (solid) or "proposed" (dashed); the others are hidden.
- "labels" is each node's change label at that stage ("Future unresolved —
  current context", "Alternative — unresolved"...); "decommissioned" maps a
  node to "Decommissioned", "Planned decommissioning" or "Proposed
  decommissioning"; "replaced" maps a node to the carried node that takes over
  its responsibility in that stage's design (next or target only: the current
  stage is evidence, not design); "transferred" maps a node to why it leaves
  the system.
- "compact" adds ELK's NETWORK_SIMPLEX placement to make a wide map tighter;
  "label_width" (px) must fit the longest label line.

Writes mermaids.md and the three SVGs, and prints one line of JSON: the path of
mermaids.md, each map's path, width and height, any warnings, whether the folder
is temporary, and with --png a PNG preview of each in the system temp folder (in
Mermaid's own colours). Map validation, rendering and layout errors exit 1
without writing maps. A PNG-preview error can occur after the maps are saved. Rendering needs
Node.js, and there is no fallback without it (see output_diagram.py).
"""
import argparse
import json
import os
import re
import tempfile

from common import (FOLDER_NAME, MAPS_SPEC, MERMAIDS, STAGE_TITLES, STAGES, connection_key,
                    investigation_dir, load_json, write_output_file)
import output_diagram

STATUSES = ["Implemented", "Implemented, needs significant work", "In development",
            "No implementation found", "Unverified", "Legacy or superseded"]
KINDS = {"component": None, "store": None,
         "person": "Person", "external": "External"}
DECOMMISSIONED = ["Decommissioned",
                  "Planned decommissioning", "Proposed decommissioning"]
CONNECTION_STYLES = ["implemented", "proposed"]
# Mermaid keywords that can't be node ids.
RESERVED = {"graph", "flowchart", "end", "subgraph", "style", "class", "classDef",
            "linkStyle", "click", "direction", "default", "call", "href"}
NODE_ID = re.compile(r"[A-Za-z][A-Za-z0-9_]*")
RED = "#e5484d"
RETIRED = "fill:#52525b,stroke:#a1a1aa,color:#d4d4d8"
# How far a node may move between stages and still count as in place.
POSITION_TOLERANCE = 0.5
RATIO = (1.5, 2.5)

LEGEND = (
    "Red outline = the complete architecture carried at that stage, unchanged components "
    "included; red arrow = a connection added or changed from the preceding stage. Solid "
    "arrow = an interaction the code has, on the default branch or a labelled development "
    "branch; dashed = a proposal or an open pull request. Red marks change, not "
    "implementation status. Grey crossed components are decommissioned, with their "
    "lifecycle label. Grey components without a cross are replaced: that stage's design "
    "gives their responsibility to the component named, which removes them from the "
    "design without implying a decommissioning decision. \"Future unresolved — current context\" keeps a component for "
    "comparison and is not a commitment to include it in the future solution. Components "
    "outside the outline aren't included at that stage yet. Every stage has the same "
    "components and connections, so positions stay fixed; a connection a stage doesn't "
    "have is hidden and implies no call.")


def validate(spec):
    """Every problem with the spec, as messages."""
    errors = []
    if not isinstance(spec, dict):
        return ["maps.json must be a JSON object"]
    groups = spec.get("groups", [])
    nodes = spec.get("nodes", [])
    connections = spec.get("connections", [])
    stages = spec.get("stages", {})
    # Reject malformed JSON shapes before hashing identifiers or walking fields.
    for field, values, required in (("groups", groups, ("id", "label")),
                                    ("nodes", nodes, ("id", "name", "kind")),
                                    ("connections", connections, ("from", "to", "label"))):
        if not isinstance(values, list):
            errors.append(f"{field}: must be an array of objects")
            continue
        for index, value in enumerate(values):
            if not isinstance(value, dict):
                errors.append(f"{field}[{index}]: must be an object")
                continue
            for name in required:
                if not isinstance(value.get(name), str) or not value[name].strip():
                    errors.append(
                        f"{field}[{index}].{name}: must be a nonempty string")
            for name in ("id", "group", "status"):
                if name == "group" and value.get(name) is None:
                    continue
                if name in value and not isinstance(value[name], str):
                    errors.append(f"{field}[{index}].{name}: must be a string")
    notes = spec.get("notes", [])
    if not isinstance(notes, list) or any(not isinstance(note, str) for note in notes):
        errors.append("notes: must be an array of strings")
    width = spec.get("label_width", 260)
    if type(width) is not int or width <= 0:
        errors.append("label_width: must be a positive integer")
    if not isinstance(spec.get("compact", False), bool):
        errors.append("compact: must be a boolean")
    if isinstance(stages, dict):
        for key, stage in stages.items():
            if not isinstance(stage, dict):
                errors.append(f"{key}: must be an object")
                continue
            carried = stage.get("carried", [])
            if not isinstance(carried, list) or any(not isinstance(i, str) for i in carried):
                errors.append(f"{key}.carried: must be an array of node ids")
            for name in ("labels", "decommissioned", "replaced", "transferred", "connections"):
                values = stage.get(name, {})
                if not isinstance(values, dict) or any(not isinstance(v, str) for v in values.values()):
                    errors.append(
                        f"{key}.{name}: must be an object with string values")
    if errors:
        return errors
    group_ids = [g.get("id") for g in groups if isinstance(g, dict)]
    if len(group_ids) != len(groups) or not all(isinstance(g, str) and NODE_ID.fullmatch(g) for g in group_ids):
        errors.append(
            "every group needs an id of letters, digits and underscores")
    if len(set(group_ids)) != len(group_ids):
        errors.append("group ids must be unique")
    if any(not isinstance(g, dict) or not str(g.get("label", "")).strip() for g in groups):
        errors.append("every group needs a label")
    ids = []
    for node in nodes:
        if not isinstance(node, dict):
            errors.append("every node must be an object")
            continue
        ident = node.get("id")
        ids.append(ident)
        if not isinstance(ident, str) or not NODE_ID.fullmatch(ident) or ident in RESERVED:
            errors.append(
                f"node {ident!r}: id must be letters, digits and underscores, and not a Mermaid keyword")
        if not str(node.get("name", "")).strip():
            errors.append(f"node {ident}: needs a name")
        kind = node.get("kind")
        if kind not in KINDS:
            errors.append(
                f"node {ident}: kind must be one of {', '.join(KINDS)}")
        elif KINDS[kind] is None and node.get("status") not in STATUSES:
            errors.append(
                f"node {ident}: status must be one of: {'; '.join(STATUSES)}")
        if node.get("group") is not None and node.get("group") not in group_ids:
            errors.append(f"node {ident}: unknown group {node.get('group')!r}")
    if not nodes:
        errors.append("maps.json has no nodes")
    if len(set(ids)) != len(ids):
        errors.append("node ids must be unique")
    names = [n.get("name") for n in nodes if isinstance(n, dict)]
    if len(set(names)) != len(names):
        errors.append(
            "node names must be unique: sequences match participants to them")
    kinds = {n.get("id"): n.get("kind") for n in nodes if isinstance(n, dict)}
    keys = []
    for connection in connections:
        if not isinstance(connection, dict):
            errors.append("every connection must be an object")
            continue
        key = connection_key(connection)
        keys.append(key)
        for end in ("from", "to"):
            if connection.get(end) not in kinds:
                errors.append(
                    f"connection {key}: unknown {end} node {connection.get(end)!r}")
        if not str(connection.get("label", "")).strip():
            errors.append(f"connection {key}: needs a label")
    if len(set(keys)) != len(keys):
        errors.append(
            "connection keys must be unique: give an \"id\" to connections between the same nodes")
    if not isinstance(stages, dict) or sorted(stages) not in (sorted(STAGE_TITLES), ["current"]):
        return errors + [f"stages must be exactly {', '.join(STAGE_TITLES)}, or current alone "
                         "when the report skips evolution"]
    previous = None
    for key, _, _ in shown_stages(spec):
        stage = stages[key]
        if not isinstance(stage, dict):
            errors.append(f"{key}: must be an object")
            continue
        carried = stage.get("carried", [])
        for ident in carried:
            if ident not in kinds:
                errors.append(f"{key}: carried node {ident!r} is unknown")
            elif kinds[ident] in ("person", "external"):
                errors.append(
                    f"{key}: {ident} is a {kinds[ident]}, never in the outline")
        for ident in stage.get("labels", {}):
            if ident not in kinds:
                errors.append(f"{key}: label for unknown node {ident!r}")
        for ident, label in stage.get("decommissioned", {}).items():
            if ident not in kinds or kinds[ident] not in ("component", "store"):
                errors.append(
                    f"{key}: decommissioned node {ident!r} must be a known component or store")
            if label not in DECOMMISSIONED:
                errors.append(
                    f"{key}: {ident}'s decommissioning must be one of: {', '.join(DECOMMISSIONED)}")
            if ident in stage.get("labels", {}):
                errors.append(
                    f"{key}: {ident} is decommissioned, so its label is its decommissioning")
        for ident, by in stage.get("replaced", {}).items():
            if key == STAGES[0][0]:
                errors.append(
                    f"{key}: nothing is replaced at the current stage, which is evidence, not design")
            if ident not in kinds or kinds[ident] not in ("component", "store"):
                errors.append(
                    f"{key}: replaced node {ident!r} must be a known component or store")
            if by not in carried:
                errors.append(
                    f"{key}: {ident} is replaced by {by!r}, which must be carried at this stage")
            if ident in carried or ident in stage.get("decommissioned", {}) or ident in stage.get("labels", {}):
                errors.append(f"{key}: {ident} is replaced, so it is neither carried, decommissioned "
                              "nor labelled: its label names its replacement")
        for ident, reason in stage.get("transferred", {}).items():
            if ident not in kinds or kinds[ident] not in ("component", "store") or not reason.strip():
                errors.append(
                    f"{key}: transferred node {ident!r} must be a known component or store, with a reason")
        dispositions = {}
        for name in ("carried", "decommissioned", "replaced", "transferred"):
            for ident in stage.get(name, []):
                if ident in dispositions:
                    errors.append(
                        f"{key}: {ident} cannot be both {dispositions[ident]} and {name}")
                dispositions[ident] = name
        for name, style in stage.get("connections", {}).items():
            if name not in keys:
                errors.append(f"{key}: unknown connection {name!r}")
            if style not in CONNECTION_STYLES:
                errors.append(
                    f"{key}: connection {name} must be implemented or proposed")
        if previous is not None:
            kept = (set(carried) | set(stage.get("decommissioned", {})) | set(stage.get("replaced", {}))
                    | set(stage.get("transferred", {})))
            for ident in previous.get("carried", []):
                if ident not in kept:
                    errors.append(
                        f"{key}: {ident} was carried at the preceding stage; keep it carried "
                        "(\"Future unresolved — current context\" if its future is unresolved), "
                        "decommission it, say what replaces it or why it's transferred")
            for ident in previous.get("decommissioned", {}):
                if ident not in stage.get("decommissioned", {}):
                    errors.append(
                        f"{key}: {ident} was decommissioned at the preceding stage and must stay so")
            for ident in previous.get("replaced", {}):
                if ident not in stage.get("replaced", {}) and ident not in stage.get("decommissioned", {}):
                    errors.append(f"{key}: {ident} was replaced at the preceding stage; keep it replaced "
                                  "or decommission it")
        previous = stage
    return errors


def shown_stages(spec):
    """The stages maps.json draws: all three, or the current one alone."""
    return [stage for stage in STAGES if stage[0] in spec["stages"]]


def text(value):
    """Label text safe inside a quoted Mermaid label."""
    return " ".join(str(value).split()).replace('"', "#quot;")


def edge_ids(connections):
    """Mermaid's id of each connection, L_<from>_<to>_<n>, n counting the
    earlier connections between the same nodes."""
    seen, ids = {}, []
    for c in connections:
        pair = (c["from"], c["to"])
        ids.append(f"L_{c['from']}_{c['to']}_{seen.get(pair, 0)}")
        seen[pair] = seen.get(pair, 0) + 1
    return ids


def node_line(node, stage, names):
    status = KINDS[node["kind"]] or node["status"]
    replaced = stage.get("replaced", {}).get(node["id"])
    change = (stage.get("decommissioned", {}).get(node["id"])
              or (f"Replaced by {names[replaced]}" if replaced else "")
              or stage.get("labels", {}).get(node["id"]) or "")
    label = "<br/>".join(text(part) if str(part).strip() else "&nbsp;"
                         for part in (node["name"], status, change))
    shape = '[("{}")]' if node["kind"] == "store" else '["{}"]'
    return node["id"] + shape.format(label)


def mermaid(spec, key, previous):
    """The Mermaid source of the map at stage `key`, with `previous` the
    preceding stage's spec or None."""
    stage = spec["stages"][key]
    connections = spec.get("connections", [])
    styles = stage.get("connections", {})
    before = previous.get("connections", {}) if previous is not None else None
    ids = edge_ids(connections)
    width = int(spec.get("label_width", 260))
    css = [f".node .label div{{width:{width}px !important;max-width:{width}px !important;"
           "white-space:nowrap !important}",
           ".edge-pattern-dotted{stroke-dasharray:6 4 !important}"]
    css += [f"[data-id={ident}]{{opacity:0}}" for c, ident in zip(connections, ids)
            if connection_key(c) not in styles]
    elk = {"lineHops": "gap"}
    if spec.get("compact"):
        elk["nodePlacementStrategy"] = "NETWORK_SIMPLEX"
    init = {"flowchart": {"curve": "rounded"},
            "elk": elk, "themeCSS": " ".join(css)}
    lines = [
        "%%{init: " + json.dumps(init, ensure_ascii=False) + "}%%", "flowchart LR"]
    nodes = spec["nodes"]
    names = {n["id"]: n["name"] for n in nodes}
    lines += ["  " + node_line(n, stage, names)
              for n in nodes if n.get("group") is None]
    for group in spec.get("groups", []):
        lines.append(f'  subgraph grp_{group["id"]}["{text(group["label"])}"]')
        lines += ["    " + node_line(n, stage, names)
                  for n in nodes if n.get("group") == group["id"]]
        lines.append("  end")
    red = []
    for index, connection in enumerate(connections):
        style = styles.get(connection_key(connection))
        arrow = "-.->" if style == "proposed" else "-->"
        lines.append(
            f'  {connection["from"]} {arrow}|"{text(connection["label"])}"| {connection["to"]}')
        if before is not None and style is not None and before.get(connection_key(connection)) != style:
            red.append(index)
    lines.append(f"  classDef carried stroke:{RED},stroke-width:3px")
    lines.append(f"  classDef retired {RETIRED}")
    if stage.get("carried"):
        lines.append("  class " + ",".join(stage["carried"]) + " carried")
    retired = list(stage.get("decommissioned", {})) + \
        list(stage.get("replaced", {}))
    if retired:
        lines.append("  class " + ",".join(retired) + " retired")
    crossed = list(stage.get("decommissioned", {}))
    if crossed:
        lines.append("  class " + ",".join(crossed) + " decommissioned")
    if red:
        lines.append("  linkStyle " +
                     ",".join(map(str, red)) + f" stroke:{RED}")
    return "\n".join(lines) + "\n"


def sources(spec):
    """{stage: Mermaid source} of the three maps."""
    result, previous = {}, None
    for key, _, _ in shown_stages(spec):
        result[key] = mermaid(spec, key, previous)
        previous = spec["stages"][key]
    return result


def preparation(spec, maps):
    """mermaids.md: the legend, the agent's notes and each stage's source."""
    parts = ["# System-map preparation", "",
             f"Generated by build_maps.py from {MAPS_SPEC}: change {MAPS_SPEC} and run it again, "
             "never this file.", "", LEGEND, ""]
    for note in spec.get("notes", []):
        parts += [note, ""]
    for key, title, filename in shown_stages(spec):
        parts += [f"## {title} — System map", "", f"Output: `{filename}`", "",
                  "```mermaid", maps[key].rstrip(), "```", ""]
    return "\n".join(parts)


def check_rendered(svgs):
    """(errors, warnings, sizes) of the rendered maps, {stage: SVG}."""
    errors, warnings, sizes, positions = [], [], {}, {}
    keys = [key for key, _, _ in STAGES if key in svgs]
    for key in keys:
        svg = svgs[key]
        errors += [f"{key}: {p}" for p in output_diagram.line_problems(svg)]
        width, height = output_diagram.svg_size(svg)
        sizes[key] = {"width": width, "height": height}
        if width and height and not RATIO[0] <= width / height <= RATIO[1]:
            warnings.append(f"{key}: {width:.0f}x{height:.0f} is {width / height:.2f}:1, outside "
                            f"{RATIO[0]}-{RATIO[1]}:1; regroup or shorten labels if it reads badly")
        positions[key] = output_diagram.node_positions(svg)
    first = positions[keys[0]]
    for key in keys[1:]:
        for ident, at in first.items():
            other = positions[key].get(ident)
            if other is None or max(abs(a - b) for a, b in zip(at, other)) > POSITION_TOLERANCE:
                errors.append(f"{key}: {ident} moves from {at} to {other}; make every label the same "
                              "number of lines and keep label_width wide enough for the longest")
    return errors, warnings, sizes


def build(relative, png=False):
    """Validates the spec, renders and checks the maps, then writes them.
    Returns the JSON result; exits on error."""
    folder, _, temporary = investigation_dir(relative)
    spec = load_json(os.path.join(folder, MAPS_SPEC))
    errors = validate(spec)
    if errors:
        raise SystemExit(
            "maps.json has problems, so nothing was written:\n  - " + "\n  - ".join(errors))
    maps = sources(spec)
    rendered = output_diagram.render_many(
        [maps[key] for key, _, _ in shown_stages(spec)], "dark")
    svgs = dict(zip([key for key, _, _ in shown_stages(spec)], rendered))
    errors, warnings, sizes = check_rendered(svgs)
    if errors:
        raise SystemExit(
            "the maps break the rules, so nothing was written:\n  - " + "\n  - ".join(errors[:30]))
    result = {"mermaids": write_output_file(FOLDER_NAME, f"{relative}/{MERMAIDS}",
                                            preparation(spec, maps).encode("utf-8"))[0],
              "maps": {}, "warnings": warnings, "temporary": temporary}
    for key, _, filename in shown_stages(spec):
        path, _ = write_output_file(
            FOLDER_NAME, f"{relative}/{filename}", svgs[key].encode("utf-8"))
        result["maps"][key] = {"path": path, **sizes[key]}
    if png:
        previews = tempfile.mkdtemp(prefix="maps-")
        result["png"] = {}
        for key, _, _ in shown_stages(spec):
            preview = os.path.join(previews, f"{key}.png")
            output_diagram.render(maps[key], "dark", preview)
            result["png"][key] = preview
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Build the three architecture maps from maps.json.")
    parser.add_argument("--investigation", required=True,
                        help="the investigation's folder, <Topic>_<YY-MM-DD>, inside tech-investigations")
    parser.add_argument("--png", action="store_true",
                        help="also write a PNG preview of each map to the system temp folder")
    args = parser.parse_args(argv)
    print(json.dumps(build(args.investigation, args.png)))


if __name__ == "__main__":
    main()
